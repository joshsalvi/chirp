"""
eBird Service — Regional Species with True 12-Month Frequency

Strategy (Merlin-equivalent):
  1. Reverse-geocode lat/lon → ISO subdivision (state/province)
  2. Map subdivision → eBird region code (e.g. "US-NY", "CA-ON")
  3. Fetch eBird bar chart data for the region (52 weekly values per species)
  4. Aggregate 52 weekly → 12 monthly averages (normalized 0-1)

This is the same data source Merlin uses for its blue frequency bars.
Fallback: single-month abundance estimate from geo/recent if bar chart
data is unavailable (no API key or region lookup fails).
"""
import logging
import math
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger("chirp.ebird")
UA = "Chirp-BirdDetection/1.0 (automated bird call monitor; non-commercial)"

# eBird API base
EBIRD_API = "https://api.ebird.org/v2"
# eBird bar chart endpoint (same data as the eBird website bar charts)
EBIRD_BARCHART = "https://ebird.org/barchartData"

_rate_last: float = 0.0
_RATE_INTERVAL = 0.35   # seconds between requests


def _throttle() -> None:
    global _rate_last
    elapsed = time.monotonic() - _rate_last
    if elapsed < _RATE_INTERVAL:
        time.sleep(_RATE_INTERVAL - elapsed)
    _rate_last = time.monotonic()


# ── Region code lookup ────────────────────────────────────────────────────────

def get_country_code_from_latlon(lat: float, lon: float) -> Optional[str]:
    """
    Convert lat/lon → ISO 3166-1 alpha-2 country code (e.g. "US", "GB") via
    the same Nominatim reverse-geocoding endpoint get_region_code_from_latlon
    uses. Deliberately separate from that function rather than parsing its
    return value: callers that only need a country code (e.g. the eBird CSV
    export's "Country Code" field) shouldn't pay for or depend on the
    state/county eBird-region-verification logic that function performs.
    """
    try:
        _throttle()
        r = httpx.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 3},
            headers={"User-Agent": UA},
            timeout=10,
            follow_redirects=True,
        )
        if r.status_code != 200:
            logger.debug("Nominatim country lookup %d for %.4f,%.4f", r.status_code, lat, lon)
            return None
        address = r.json().get("address", {})
        code = address.get("country_code", "").upper()
        return code or None
    except Exception as e:
        logger.debug("Country code lookup error: %s", e)
        return None


def get_region_code_from_latlon(lat: float, lon: float, api_key: str = "") -> Optional[str]:
    """
    Convert lat/lon → eBird region code via Nominatim reverse geocoding.

    Returns codes in preference order:
      subnational2 (county)  → "US-NY-061"
      subnational1 (state)   → "US-NY"
      country                → "US"
    Falls back to nearest subnational1 if county lookup fails.
    """
    try:
        _throttle()
        r = httpx.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 10},
            headers={"User-Agent": UA},
            timeout=10,
            follow_redirects=True,
        )
        if r.status_code != 200:
            logger.debug("Nominatim %d for %.4f,%.4f", r.status_code, lat, lon)
            return None

        data = r.json()
        address = data.get("address", {})

        country_code = address.get("country_code", "").upper()   # "US"
        state_code   = address.get("ISO3166-2-lvl4", "")         # "US-NY"
        county_fips  = address.get("county_code", "")            # varies

        if not country_code:
            return None

        # Build eBird region code
        # state_code from Nominatim is already "US-NY" format for US/Canada
        if state_code:
            # Normalize — Nominatim sometimes uses full subdivision strings
            # e.g. "US-NY" or "US-CA" — extract the last segment
            parts = state_code.split("-")
            if len(parts) >= 2:
                region = "-".join(parts[:2])   # "US-NY"

                # Try county-level for an even more granular (and typically
                # LARGER) species list, since eBird county checklists span
                # the full historical record for that specific area.
                # county_fips from Nominatim is a raw FIPS code (e.g. "017"),
                # not an eBird county code — eBird uses its own county codes
                # (e.g. "US-MA-017") which don't map 1:1 from FIPS, so we
                # can't construct it directly. Verify it resolves before using it;
                # if eBird doesn't recognise it, fall back to state-level.
                if county_fips:
                    candidate = f"{region}-{county_fips}"
                    if _verify_region_code(candidate, api_key):
                        logger.info("eBird region from Nominatim (county): %s (%.4f,%.4f)", candidate, lat, lon)
                        return candidate

                logger.info("eBird region from Nominatim (state): %s (%.4f,%.4f)", region, lat, lon)
                return region

        logger.debug("No state code in Nominatim response for %.4f,%.4f", lat, lon)
        return country_code   # Last resort: country only

    except Exception as e:
        logger.debug("Region lookup error: %s", e)
        return None


def _verify_region_code(region_code: str, api_key: str = "") -> bool:
    """Quick sanity check: does eBird recognise this region code at all?
    Uses the lightweight /ref/region/info endpoint rather than a full species
    fetch, so a bad guess doesn't cost an expensive API call."""
    try:
        _throttle()
        headers = {"User-Agent": UA}
        if api_key:
            headers["X-eBirdApiToken"] = api_key
        r = httpx.get(
            f"{EBIRD_API}/ref/region/info/{region_code}",
            headers=headers,
            timeout=8,
        )
        return r.status_code == 200
    except Exception:
        return False


# ── Bar chart data ────────────────────────────────────────────────────────────

def fetch_bar_chart_data(region_code: str, api_key: str) -> Dict[str, List[float]]:
    """
    Fetch eBird bar chart data for a region.

    Returns: { species_code: [freq_jan, freq_feb, ..., freq_dec] }
    where each value is 0.0–1.0 (fraction of eBird checklists that reported
    the species in that month — same metric Merlin shows as blue bars).

    The bar chart endpoint returns 48 bi-weekly frequency periods per species.
    We aggregate into 12 monthly averages.
    """
    current_year = datetime.utcnow().year
    try:
        _throttle()
        # Note: follow_redirects=False — a redirect means the endpoint requires a
        # web session (Cornell SSO login), not just an API key. Detect and bail out.
        r = httpx.get(
            EBIRD_BARCHART,
            params={
                "r": region_code,
                "bmo": "1",
                "emo": "12",
                "byr": "1900",
                "eyr": str(current_year),
                "fmt": "tsv",
            },
            headers={
                "X-eBirdApiToken": api_key,
                "User-Agent": UA,
            },
            timeout=30,
            follow_redirects=False,
        )
        if r.status_code in (301, 302, 303, 307, 308):
            logger.info(
                "eBird bar chart redirected (requires web session) for region %s — "                "falling back to geo/recent", region_code
            )
            return {}
        if r.status_code != 200:
            logger.warning("eBird bar chart HTTP %d for region %s", r.status_code, region_code)
            return {}

        result = _parse_bar_chart_tsv(r.text)
        if not result:
            logger.info("eBird bar chart: empty parse for %s (response may be HTML)", region_code)
        return result

    except Exception as e:
        logger.warning("eBird bar chart fetch error for %s: %s", region_code, e)
        return {}


def _parse_bar_chart_tsv(text: str) -> Dict[str, List[float]]:
    """
    Parse eBird bar chart TSV response.

    Format (after header line):
      Column 0:  Species common name
      Column 1:  Species scientific name (space-separated from common)
      Columns 2–49: 48 bi-weekly frequency values (floats, 0.0–1.0)
      Column 50+: sample size columns

    The 48 columns correspond to 4 per month × 12 months = 48 periods.
    We average groups of 4 to get 12 monthly values.

    Actually eBird returns lines like:
    "Common Name (Scientific name)\t0.23\t0.31\t...\t(52 or 48 values)"

    The exact number of frequency columns varies by eBird version.
    We detect it from the header row.
    """
    result: Dict[str, List[float]] = {}
    lines = text.strip().splitlines()
    if not lines:
        return result

    # First line is the header — count frequency columns
    header_parts = lines[0].split("\t")
    # Header is typically: "Species Name\tSpecies Code\tFreq1\tFreq2\t..."
    # We find where numeric-looking columns start
    freq_cols_start = 0
    for i, h in enumerate(header_parts):
        # First column that looks like a date/week period
        if re.match(r'\d', h) or h.lower().startswith(("jan", "feb", "mar")):
            freq_cols_start = i
            break
    else:
        # Fall back: skip first 2 columns (name, code)
        freq_cols_start = 2

    num_freq_cols = sum(
        1 for h in header_parts[freq_cols_start:]
        if not h.lower().startswith("sample")
    )
    # eBird typically has 48 frequency cols (4 per month) or 52 (weekly)
    # Determine periods per month
    if num_freq_cols >= 48:
        periods_per_month = num_freq_cols // 12
    else:
        periods_per_month = 4  # default assumption

    parsed = 0
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < freq_cols_start + 12:
            continue

        # Extract species name and code
        # eBird bar chart format: "Common Name (Scientific Name)" in column 0
        # species code in column 1 (if present), or derive from name
        raw_name = parts[0].strip()
        # Remove "(Scientific Name)" suffix
        common_name = re.sub(r'\s*\([^)]+\)\s*$', '', raw_name).strip()
        species_code = parts[1].strip() if len(parts) > 1 and not _is_float(parts[1]) else ""

        # Extract frequency values
        freq_vals = []
        for col in parts[freq_cols_start:freq_cols_start + periods_per_month * 12]:
            try:
                freq_vals.append(float(col))
            except (ValueError, IndexError):
                freq_vals.append(0.0)

        if not freq_vals or all(v == 0 for v in freq_vals):
            continue

        # Aggregate into 12 monthly averages
        monthly = []
        for m in range(12):
            start = m * periods_per_month
            end = start + periods_per_month
            chunk = freq_vals[start:end]
            monthly.append(round(sum(chunk) / len(chunk), 4) if chunk else 0.0)

        # Keep eBird's raw checklist frequency. Scaling each species to its
        # own peak made a one-off rarity look as likely as a Blue Jay.

        key = species_code or common_name
        if key:
            result[key] = monthly
            if species_code:
                result[common_name] = monthly  # also index by name
        parsed += 1

    logger.info("Parsed bar chart: %d species from %d lines (region data)",
                parsed, len(lines) - 1)
    return result


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


# ── Full year-round species list ─────────────────────────────────────────────

def fetch_full_species_list(region_code: str, api_key: str) -> List[str]:
    """
    Fetch the complete historical species list for a region from eBird.

    Uses /v2/product/spplist/{regionCode} — returns every species code ever
    recorded in the region, across all years.  This is the same list Merlin
    uses to populate its full regional checklist, including rare/irregular
    visitors that wouldn't show up in a 30-day geo/recent window.

    Returns a list of species codes, e.g. ["norcow", "bkcchi", ...].
    """
    if not region_code or not api_key:
        return []
    try:
        _throttle()
        r = httpx.get(
            f"{EBIRD_API}/product/spplist/{region_code}",
            headers={"X-eBirdApiToken": api_key, "User-Agent": UA},
            timeout=30,
        )
        if r.status_code != 200:
            logger.warning("eBird spplist → %d for %s", r.status_code, region_code)
            return []
        codes = r.json()
        logger.info("eBird spplist: %d species for %s", len(codes), region_code)
        return codes if isinstance(codes, list) else []
    except Exception as e:
        logger.warning("eBird spplist error for %s: %s", region_code, e)
        return []


def fetch_taxonomy_for_codes(
    species_codes: List[str], api_key: str, batch_size: int = 200
) -> Dict[str, Dict]:
    """
    Look up common name, scientific name, family, and order for a list of
    species codes using the eBird taxonomy endpoint.

    Batches requests to stay within URL length limits.
    Returns {code: {common_name, scientific_name, family_com_name, order_name}}.
    """
    if not species_codes or not api_key:
        return {}

    result: Dict[str, Dict] = {}
    total = len(species_codes)
    for batch_start in range(0, total, batch_size):
        batch = species_codes[batch_start:batch_start + batch_size]
        try:
            _throttle()
            r = httpx.get(
                f"{EBIRD_API}/ref/taxonomy/ebird",
                params={
                    "speciesCodes": ",".join(batch),
                    "fmt": "json",
                    "locale": "en",
                },
                headers={"X-eBirdApiToken": api_key, "User-Agent": UA},
                timeout=20,
            )
            if r.status_code != 200:
                logger.warning("taxonomy batch %d → HTTP %d", batch_start, r.status_code)
                continue
            for entry in r.json():
                code = entry.get("speciesCode", "")
                if code:
                    result[code] = {
                        "common_name":     entry.get("comName",    code),
                        "scientific_name": entry.get("sciName",    ""),
                        "family_com_name": entry.get("familyComName", ""),
                        "order_name":      entry.get("order",      ""),
                    }
        except Exception as e:
            logger.warning("taxonomy batch %d error: %s", batch_start, e)

    logger.info("Taxonomy lookup: %d/%d codes resolved", len(result), total)
    return result


# ── iNaturalist regional seasonality ─────────────────────────────────────────

INAT_SPECIES_COUNTS = "https://api.inaturalist.org/v1/observations/species_counts"


def fetch_inat_regional_monthly(lat: float, lon: float, radius_km: int = 50) -> Dict[str, List[float]]:
    """
    Month-by-month bird observations within radius_km, from iNaturalist
    research-grade records: 12 calls, one per month.

    Returns {scientific name (lower case): [jan..dec]}, each value the
    species' count that month divided by the most-observed species' count
    that month (so 1.0 = the commonest bird around then, a one-off stray is
    close to 0). Comparable across species, unlike per-species peaks.
    """
    counts: Dict[str, List[int]] = defaultdict(lambda: [0] * 12)
    top = [0] * 12
    for m in range(12):
        for page in (1, 2, 3):
            try:
                r = httpx.get(INAT_SPECIES_COUNTS, params={
                    "lat": lat, "lng": lon, "radius": radius_km, "month": m + 1,
                    "taxon_id": 3, "quality_grade": "research", "rank": "species",
                    "per_page": 500, "page": page,
                }, headers={"User-Agent": UA}, timeout=30)
                if r.status_code != 200:
                    logger.warning("iNat species_counts month %d → HTTP %d", m + 1, r.status_code)
                    break
                data = r.json()
            except Exception as e:
                logger.warning("iNat species_counts month %d error: %s", m + 1, e)
                break
            results = data.get("results") or []
            for row in results:
                name = ((row.get("taxon") or {}).get("name") or "").strip().lower()
                n = int(row.get("count") or 0)
                if name and n:
                    counts[name][m] += n
                    top[m] = max(top[m], counts[name][m])
            time.sleep(1.0)  # iNat asks for about one request a second
            if page * 500 >= int(data.get("total_results") or 0):
                break
    out = {name: [round(v / top[i], 4) if top[i] else 0.0 for i, v in enumerate(vals)]
           for name, vals in counts.items()}
    logger.info("iNat regional seasonality: %d species within %d km", len(out), radius_km)
    return out


# ── Main entry point ──────────────────────────────────────────────────────────

def fetch_regional_species_with_monthly_frequency(
    lat: float,
    lon: float,
    api_key: str,
    radius_km: int = 50,
) -> List[Dict]:
    """
    Return species list with true 12-month frequency data.

    Priority:
    1. eBird bar chart API (exact same data as Merlin frequency bars)
    2. Fallback: geo/recent abundance data with single-month estimate
    """
    current_month = datetime.utcnow().month - 1  # 0-indexed

    # ── Step 1: eBird region code ─────────────────────────────────────────────
    region_code = get_region_code_from_latlon(lat, lon, api_key)

    # ── Step 2: Full year-round species list (spplist) ────────────────────────
    # Returns ALL species ever recorded in the region across all years.
    # This is the authoritative source for "what could appear here" — includes
    # seasonal visitors, rare strays, and winter-only species not in a 30-day
    # geo/recent window.
    all_codes: List[str] = []
    if region_code and api_key:
        all_codes = fetch_full_species_list(region_code, api_key)

    # ── Step 3: Taxonomy (names, family, order) for every code ────────────────
    taxonomy: Dict[str, Dict] = {}
    if all_codes and api_key:
        taxonomy = fetch_taxonomy_for_codes(all_codes, api_key)

    # ── Step 4: Bar chart for 12-month frequency shape ────────────────────────
    # Works when the eBird TSV endpoint is accessible.  Falls back gracefully.
    bar_chart_data: Dict[str, List[float]] = {}
    if region_code and api_key:
        bar_chart_data = fetch_bar_chart_data(region_code, api_key)
        logger.info("Bar chart: %d species for region %s", len(bar_chart_data), region_code)

    # ── Step 4b: regional seasonality from iNaturalist ───────────────────────
    # The bar chart needs an eBird web login and is usually empty; without
    # this, frequencies came from worldwide data and rarities ranked high.
    inat_monthly: Dict[str, List[float]] = {}
    if not bar_chart_data:
        inat_monthly = fetch_inat_regional_monthly(lat, lon, radius_km)

    # ── Step 5: geo/recent for recency + abundance ranking ────────────────────
    # Only 30 days, but gives obs_count / days_seen for sorting.
    geo_species = _fetch_geo_recent(lat, lon, api_key, radius_km)

    if not all_codes and not geo_species and not bar_chart_data:
        return []

    # ── Step 6: Build full merged species dict ─────────────────────────────────
    # Start with the full year-round spplist, augmented by geo/recent presence.
    all_species: Dict[str, Dict] = {}

    # Populate from spplist + taxonomy (year-round base)
    for code in all_codes:
        info = taxonomy.get(code, {})
        name = info.get("common_name") or code
        all_species[code] = {
            "ebird_species_code": code,
            "common_name":        name,
            "scientific_name":    info.get("scientific_name", ""),
            "family_com_name":    info.get("family_com_name", ""),
            "order_name":         info.get("order_name", ""),
            "obs_count":          0,
            "days_seen":          0,
        }

    # Overlay geo/recent data (obs_count, days_seen, and fill gaps in spplist)
    for code, info in geo_species.items():
        if code in all_species:
            all_species[code]["obs_count"] = info.get("obs_count", 0)
            all_species[code]["days_seen"] = info.get("days_seen", 0)
        else:
            # Species in geo/recent but not in spplist (provisional, etc.)
            all_species[code] = {
                "ebird_species_code": code,
                "common_name":        info.get("common_name", code),
                "scientific_name":    info.get("scientific_name", ""),
                "family_com_name":    "",
                "order_name":         "",
                "obs_count":          info.get("obs_count", 0),
                "days_seen":          info.get("days_seen", 0),
            }

    # Also absorb any bar-chart-only codes not in the above
    for key in bar_chart_data:
        if key not in all_species and len(key) <= 8:
            all_species[key] = {
                "ebird_species_code": key,
                "common_name":        key,
                "scientific_name":    "",
                "family_com_name":    "",
                "order_name":         "",
                "obs_count":          0,
                "days_seen":          0,
            }

    max_obs = max((s.get("obs_count", 0) for s in all_species.values()), default=1) or 1

    results = []
    for code, info in all_species.items():
        name = info.get("common_name", code)
        if not name or name == code and len(code) <= 6:
            # Skip unresolved codes with no name
            continue

        # 12-month frequency: bar chart preferred, else estimate from geo/recent
        monthly = (
            bar_chart_data.get(code)
            or bar_chart_data.get(name)
            or inat_monthly.get((info.get("scientific_name") or "").strip().lower())
        )
        if not monthly or not any(v > 0 for v in monthly):
            obs = info.get("obs_count", 0)
            if obs > 0:
                rel = round(math.sqrt(obs) / math.sqrt(max_obs), 4)
                monthly = [rel] * 12   # present but unknown seasonality
            else:
                monthly = [0.0] * 12

        current_freq = float(monthly[current_month]) if monthly else 0.0

        results.append({
            "ebird_species_code": code,
            "common_name":        name,
            "scientific_name":    info.get("scientific_name", ""),
            "family_com_name":    info.get("family_com_name", ""),
            "order_name":         info.get("order_name", ""),
            "monthly_frequency":  monthly,
            "current_likelihood": current_freq,
            "obs_count":          info.get("obs_count", 0),
            "days_seen":          info.get("days_seen", 0),
            "total_days":         30,
        })

    # Sort: most likely this month first, then by annual peak frequency
    results.sort(
        key=lambda x: (x["current_likelihood"], max(x["monthly_frequency"] or [0])),
        reverse=True,
    )

    # Deduplicate by common name (codes can alias)
    seen_names: set = set()
    unique = []
    for r in results:
        nm = r["common_name"]
        if nm and nm not in seen_names:
            seen_names.add(nm)
            unique.append(r)

    logger.info(
        "Regional library: %d species total (spplist=%d, geo/recent=%d, bar_chart=%d)",
        len(unique), len(all_codes), len(geo_species), len(bar_chart_data),
    )
    return unique


def _fetch_geo_recent(
    lat: float, lon: float, api_key: str, radius_km: int
) -> Dict[str, Dict]:
    """Fetch recent observations near lat/lon → {speciesCode: info_dict}."""
    if not api_key:
        return {}
    try:
        _throttle()
        r = httpx.get(
            f"{EBIRD_API}/data/obs/geo/recent",
            params={
                "lat": lat, "lng": lon,
                "dist": radius_km,
                "back": 30,
                "maxResults": 10000,
                "fmt": "json",
                "includeProvisional": "true",
            },
            headers={"X-eBirdApiToken": api_key, "User-Agent": UA},
            timeout=30,
        )
        if r.status_code != 200:
            logger.warning("eBird geo/recent → %d", r.status_code)
            return {}

        obs_list = r.json()
        species: Dict[str, Dict] = {}
        abundance: Dict[str, int] = defaultdict(int)
        dates: Dict[str, set] = defaultdict(set)

        for obs in obs_list:
            code = obs.get("speciesCode", "")
            name = obs.get("comName", "")
            if not code or not name:
                continue
            if code not in species:
                species[code] = {
                    "ebird_species_code": code,
                    "common_name": name,
                    "scientific_name": obs.get("sciName", ""),
                    "obs_count": 0,
                    "days_seen": 0,
                }
            n = obs.get("howMany") or 1
            abundance[code] += int(n)
            # Track unique dates for days_seen
            obs_date = (obs.get("obsDt", "") or "")[:10]
            if obs_date:
                dates[code].add(obs_date)

        for code in species:
            species[code]["obs_count"] = abundance[code]
            species[code]["days_seen"] = len(dates[code])

        logger.info("geo/recent: %d species near %.4f,%.4f", len(species), lat, lon)
        return species

    except Exception as e:
        logger.error("eBird geo/recent error: %s", e)
        return {}


def get_ebird_api_key_from_db() -> Optional[str]:
    """
    Read eBird API key from DB settings (preferred) or env config (fallback).
    Use this whenever you need the key in a background task where the
    per-request DB session is not available.
    """
    try:
        from ..database import SessionLocal
        from ..models import AppSettings
        from ..config import settings
        with SessionLocal() as db:
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            key = (s.ebird_api_key if s else None) or settings.ebird_api_key
            return key or None
    except Exception:
        from ..config import settings
        return settings.ebird_api_key or None
