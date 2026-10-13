"""
Chirp — Range Map Service
Fetches and renders species range maps from multiple sources.

Sources:
  ebird_st  — eBird Status & Trends Data Products (seasonal abundance GeoTIFF).
               Requires a separate S&T access key from https://ebird.org/st/request
               Renders multi-season abundance raster → PNG with season colours.

  gbif      — GBIF occurrence density map tiles (free, no key required).
               Stitches base-map + occurrence tiles covering North + Central America
               (zoom 3, x=0-2, y=0-3) into a single PNG.
"""

import io
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Tuple

import httpx
import numpy as np
from PIL import Image

logger = logging.getLogger("chirp.range_map")

UA = "Chirp-BirdDetection/1.0 (Raspberry Pi bird-call monitor; non-commercial)"

# eBird S&T API base
EBIRD_ST_BASE    = "https://st-download.ebird.org/v1"
EBIRD_ST_VERSION = "2023"

# GBIF APIs
GBIF_SPECIES_API = "https://api.gbif.org/v1/species"
GBIF_MAP_TILES   = "https://api.gbif.org/v2/map/occurrence/density"
GBIF_BG_TILES    = "https://tile.gbif.org/3857/omt"

# Seasonal colour palette (RGBA) matching eBird / Merlin conventions
SEASON_COLOURS: dict[str, Tuple[int, int, int, int]] = {
    "breeding":               (255, 140,  30, 230),   # orange
    "nonbreeding":            (  0, 130, 255, 230),   # blue
    "prebreeding_migration":  (255, 220,   0, 210),   # yellow
    "postbreeding_migration": (255, 220,   0, 210),   # yellow
    "resident":               (102,   0, 200, 230),   # purple
}


# ── eBird S&T ─────────────────────────────────────────────────────────────────

def fetch_ebird_st_map(
    species_code: str,
    api_key: str,
    output_path: str,
) -> bool:
    """
    Download eBird Status & Trends seasonal abundance data and render a PNG.

    Steps:
      1. Validate inputs.
      2. List available product files for the species.
      3. Prefer any pre-rendered PNG found in the listing.
      4. Otherwise download the seasonal mean GeoTIFF and render it.

    Returns True on success (output_path exists with non-trivial content).
    """
    if not species_code:
        logger.warning("fetch_ebird_st_map: no species_code provided")
        return False
    if not api_key or api_key.strip() == "":
        logger.warning("fetch_ebird_st_map: no eBird S&T API key configured — "
                       "add it in Settings → eBird S&T API Key")
        return False

    species_code = species_code.strip().lower()

    try:
        # ── 1. List available files ────────────────────────────────────────────
        logger.info("eBird S&T: listing files for %s (version %s)", species_code, EBIRD_ST_VERSION)
        r = httpx.get(
            f"{EBIRD_ST_BASE}/list-obj/{EBIRD_ST_VERSION}/{species_code}",
            params={"key": api_key},
            headers={"User-Agent": UA},
            timeout=30,
        )
        if r.status_code == 401 or r.status_code == 403:
            logger.error("eBird S&T: authentication failed (HTTP %d) — check your S&T API key", r.status_code)
            return False
        if r.status_code == 404:
            logger.warning("eBird S&T: no data found for species '%s' (HTTP 404) — "
                           "check the eBird species code is correct", species_code)
            return False
        if r.status_code != 200:
            logger.warning("eBird S&T list-obj HTTP %d for %s — body: %s",
                           r.status_code, species_code, r.text[:200])
            return False

        raw = r.json()
        # The S&T list-obj API returns EITHER:
        #   a) A plain list of strings: ["2023/woothr/seasonal/woothr_...", ...]
        #   b) A list of dicts: [{"objKey": "2023/...", "size": N}, ...]
        # Handle both gracefully.
        if isinstance(raw, list):
            if raw and isinstance(raw[0], str):
                keys = raw                           # plain list of key paths
            else:
                keys = [
                    obj.get("objKey", obj.get("key", str(obj)))
                    if isinstance(obj, dict) else str(obj)
                    for obj in raw
                ]
        elif isinstance(raw, dict):
            inner = raw.get("objects") or raw.get("files") or raw.get("keys") or []
            keys = [x if isinstance(x, str) else x.get("objKey", str(x)) for x in inner]
        else:
            keys = []

        logger.info("eBird S&T: %d files for %s (format: %s)",
                    len(keys), species_code,
                    "strings" if (keys and isinstance(keys[0], str)) else "dicts")
        for k in keys[:5]:
            logger.debug("  S&T file: %s", k)
        if not keys:
            logger.warning("eBird S&T: empty file list for %s", species_code)
            return False

        # Debug: log first 10 keys so user can see what's available
        for k in keys[:10]:
            logger.debug("  available: %s", k)

        # ── 2. Look for pre-rendered PNG first (rare, but worth checking) ──────
        for k in keys:
            kl = k.lower()
            if kl.endswith(".png") and any(x in kl for x in ("seasonal", "range", "abundance")):
                png_data = _st_download(k, api_key)
                if png_data and len(png_data) > 5_000:
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(png_data)
                    logger.info("eBird S&T: used pre-rendered PNG for %s (%d bytes)", species_code, len(png_data))
                    return True

        # ── 3. Find best GeoTIFF ────────────────────────────────────────────────
        # Confirmed via eBird's own ebirdst documentation: the seasonal-mean
        # abundance file's band order corresponds to whichever seasons
        # actually passed expert review for THIS species (commonly all 4 —
        # breeding/nonbreeding/prebreeding_migration/postbreeding_migration
        # — for a migrant, but as few as 1 for a resident, or fewer than 4
        # if some seasons failed review). The original scorer never required
        # "abundance" specifically, so for some species it could match the
        # seasonal-mean file for an entirely different product (occurrence,
        # count, proportion-population, or even a predictive-performance-
        # metric file) that happens to also contain "seasonal" and "mean" in
        # its key — explaining a real production case where only 1 band was
        # present for a known 4-season migrant (American Redstart).
        def _score(k: str) -> int:
            k = k.lower()
            has_abundance = "abundance" in k
            # The "full-year" product is explicitly a SINGLE-LAYER summary
            # (confirmed directly: a real production log showed
            # ".../seasonal/brwhaw_abundance_full-year_mean_3km_2023.tif"
            # winning the highest-priority score below, because "seasonal"
            # matched the DIRECTORY PATH component the file happens to sit
            # in — not because the file itself is the real multi-band
            # seasonal product, which it explicitly is NOT: the filename
            # itself says "full-year", and eBird's own documentation
            # confirms full-year files always have exactly one layer. The
            # exclusion below used to only apply at the lowest-priority
            # fallback tier, so it never even ran — this file already won
            # at the very first check before reaching it. Reject "full-
            # year" universally, before any other scoring, so a full-year
            # file can never outscore a real seasonal file no matter which
            # directory it's listed under.
            if "full-year" in k or "full_year" in k:
                return 0
            # Prefer 3km seasonal mean (best quality); avoid 27km global mean.
            # Checking the FILENAME's own basename-level tokens (the part
            # after the last "/") would be more precise than substring-
            # matching the whole path, but "seasonal" appearing in a
            # directory name for a file that isn't otherwise excluded above
            # is actually consistent with eBird's real layout (config.json,
            # pis/, seasonal/, weekly/ subdirectories all sit under the
            # species code), so this is intentionally still a path-wide
            # substring match — just no longer one a full-year file can win.
            if has_abundance and "seasonal" in k and "mean" in k and "3km" in k and k.endswith(".tif"):  return 12
            if has_abundance and "seasonal" in k and "mean" in k and "9km" in k and k.endswith(".tif"):  return 10
            if has_abundance and "seasonal" in k and "mean" in k and k.endswith(".tif"):                  return 8
            if has_abundance and "seasonal" in k and k.endswith(".tif"):                                   return 6
            if "breeding" in k and "range" in k and k.endswith(".tif"):                 return 4
            if has_abundance and k.endswith(".tif"):                                     return 2
            return 0

        ranked = sorted(keys, key=_score, reverse=True)
        tif_key = next((k for k in ranked if _score(k) > 0), None)
        if not tif_key:
            # Nothing scored above 0 — every seasonal/per-season candidate
            # was rejected. Before giving up entirely, fall back to a
            # full-year file specifically (deliberately, visibly, only
            # here — never allowed to outscore a real seasonal file in
            # _score itself) since a single-layer full-year map is still
            # better than no map at all for a species with no seasonal
            # breakdown available.
            full_year_candidates = [k for k in keys if "abundance" in k.lower()
                                     and ("full-year" in k.lower() or "full_year" in k.lower())
                                     and k.lower().endswith(".tif")]
            if full_year_candidates:
                tif_key = full_year_candidates[0]
                logger.info("eBird S&T: no seasonal file found for %s — falling back to "
                            "single-layer full-year file: %s", species_code, tif_key)
            else:
                logger.warning("eBird S&T: no abundance .tif file found for %s — "
                                "available keys: %s", species_code, keys[:10])
                return False
        else:
            logger.info("eBird S&T: selected file for %s: %s", species_code, tif_key)

        logger.info("eBird S&T: downloading %s", tif_key)
        tif_data = _st_download(tif_key, api_key)
        if not tif_data or len(tif_data) < 1_000:
            logger.warning("eBird S&T: download empty or failed for %s", species_code)
            return False

        logger.info("eBird S&T: downloaded %d bytes, rendering…", len(tif_data))
        return _render_abundance_tif(tif_data, output_path, species_code, source_filename=tif_key)

    except Exception as e:
        logger.error("fetch_ebird_st_map error for %s: %s", species_code, e, exc_info=True)
        return False


def _st_download(obj_key: str, api_key: str) -> Optional[bytes]:
    """Download one file from the eBird S&T Data Products API."""
    try:
        r = httpx.get(
            f"{EBIRD_ST_BASE}/fetch",
            params={"objKey": obj_key, "key": api_key},
            headers={"User-Agent": UA},
            timeout=180,
            follow_redirects=True,
        )
        if r.status_code == 200 and r.content:
            return r.content
        logger.debug("S&T fetch HTTP %d for %s", r.status_code, obj_key)
        return None
    except Exception as e:
        logger.debug("S&T download error %s: %s", obj_key, e)
        return None


def _render_abundance_tif(tif_bytes: bytes, output_path: str, species_code: str,
                           source_filename: str = "") -> bool:
    """
    Render a multi-band seasonal abundance GeoTIFF to a coloured PNG.

    Band-to-season mapping: GDAL-written GeoTIFFs from eBird S&T commonly
    store each band's season name in its TIFF description/GDAL_METADATA
    tag — confirmed via eBird's own ebirdst R package documentation that
    a seasonal-mean abundance file's bands correspond to whichever seasons
    actually passed expert review for THAT species (e.g. a migrant
    commonly has 4: breeding/nonbreeding/prebreeding_migration/
    postbreeding_migration, but a resident has 1, and a migrant with one
    season failing review could have only 2 or 3). A fixed band-index
    assumption is NOT reliable — a real production case (American
    Redstart, a known 4-season migrant) returned a file with only 1 band,
    which the original code unconditionally labeled "breeding" regardless
    of which season that single surviving band actually represented.

    Reads real per-band descriptions first; only falls back to the
    documented index convention (logged explicitly as a fallback, not
    asserted as fact) when no real band names are present in the file.
    """
    try:
        import tifffile
    except ImportError:
        logger.warning("tifffile not installed — falling back to PIL for TIFF reading "
                       "(run: pip install tifffile)")
        return _render_tif_with_pil(tif_bytes, output_path, species_code)

    try:
        with tifffile.TiffFile(io.BytesIO(tif_bytes)) as tif:
            # tif.asarray() only reads the FIRST page/series by default —
            # confirmed by direct reproduction that a GeoTIFF with each
            # band written as its own page/series (rather than one combined
            # multi-page series) silently returns only the first band this
            # way, with no error or warning. This is the likely TRUE root
            # cause of a real production case (American Redstart, a known
            # 4-season migrant) showing only 1 band — not necessarily that
            # eBird's file only had 1 band, but that this reading method
            # was dropping the rest. Reading every page explicitly and
            # stacking them is correct regardless of how the file's bands
            # are organized into series.
            try:
                # Real eBird GeoTIFFs can contain reduced-resolution
                # overview/pyramid pages (a separate, common GDAL/COG
                # structure for fast zoom rendering) mixed in alongside the
                # genuine full-resolution band page(s). Confirmed directly:
                # stacking every page blindly — which was correct for the
                # genuinely-separate-same-sized-bands case this fix
                # originally targeted — produced a corrupted shape
                # (1, 11484, 4) on a real downloaded file instead of either
                # the correct shape or a clean exception, because some
                # pages were smaller overview images, not separate bands.
                # Filter to only full-resolution pages (largest pixel
                # count) before stacking, which correctly keeps genuine
                # multi-band pages together while excluding any smaller
                # overview pages regardless of how tifffile's internal
                # subfiletype/series detection happens to report them.
                page_sizes = [p.shape[0] * p.shape[1] for p in tif.pages]
                max_size = max(page_sizes) if page_sizes else 0
                full_res_pages = [p for p, sz in zip(tif.pages, page_sizes) if sz == max_size]
                if len(full_res_pages) < len(tif.pages):
                    logger.info("GeoTIFF: filtered %d overview/pyramid page(s) out of %d total "
                                "(kept %d full-resolution page(s))",
                                len(tif.pages) - len(full_res_pages), len(tif.pages), len(full_res_pages))
                data = np.stack([p.asarray() for p in full_res_pages])
                if data.ndim == 4:
                    # Two genuinely different 4D shapes can reach here,
                    # and must be told apart by WHICH axis is the spurious
                    # singleton, not by assuming it's always axis 1:
                    #   (n_pages, 1, H, W)    — each page already had its
                    #     own leading band axis before stacking; the
                    #     singleton is axis 1.
                    #   (1, H, W, bands)      — exactly ONE page, but that
                    #     page itself is genuinely multi-band and
                    #     tifffile returned it channels-last (a real,
                    #     confirmed production case: reproduced the exact
                    #     corrupted shape (1, 11484, 4) from a real log
                    #     using this precise mechanism). The singleton
                    #     here is axis 0 (there's only one page), and the
                    #     real bands are axis 3, not axis 1 — squeezing
                    #     axis 1 here would slice away nearly all of axis
                    #     1 (the real height) down to a single row,
                    #     exactly the bug that produced shape (1, 11484, 4)
                    #     instead of the correct (4, 5562, 11484).
                    if data.shape[1] == 1:
                        data = data[:, 0]
                    elif data.shape[0] == 1 and data.shape[3] <= 8:
                        # channels-last, single page: move the real band
                        # axis (last) to the front, then drop the now-
                        # redundant page axis.
                        data = np.moveaxis(data[0], -1, 0)
                    else:
                        logger.warning("GeoTIFF: unexpected 4D shape %s after stacking — "
                                       "leaving as-is rather than guessing which axis to "
                                       "squeeze, which could silently corrupt the data "
                                       "the way a wrong guess did for a real production "
                                       "file (shape (1, 11484, 4) instead of the correct "
                                       "(4, 5562, 11484)).", data.shape)
            except Exception as e:
                logger.debug("GeoTIFF: per-page stacking failed (%s), falling back to tif.asarray()", e)
                data = tif.asarray()
            # Read the real GDAL band-metadata tag (42112) once, up front
            # — applied AFTER n_bands is known below, since it's keyed by
            # the real per-band "sample" index, not by physical page
            # index. This matters: for the confirmed-real channels-last
            # case there is only ONE physical page but FOUR real bands,
            # so keying by page index would only ever see sample=0 and
            # silently miss samples 1-3 — a real bug caught while writing
            # this fix, not shipped.
            try:
                gdal_meta_xml = full_res_pages[0].tags.valueof(42112) if full_res_pages else None
            except Exception as e:
                gdal_meta_xml = None
                logger.debug("GeoTIFF: could not read tag 42112 (GDAL_METADATA): %s", e)

            gdal_band_names = {}
            if gdal_meta_xml:
                try:
                    import xml.etree.ElementTree as _ET
                    root = _ET.fromstring(gdal_meta_xml)
                    for item in root.findall("Item"):
                        if item.get("name") == "DESCRIPTION" and item.get("sample") is not None:
                            gdal_band_names[int(item.get("sample"))] = (item.text or "").strip().lower()
                    if gdal_band_names:
                        logger.info("GeoTIFF: found real band names via TIFFTAG_GDAL_METADATA (tag 42112): %s",
                                    gdal_band_names)
                    else:
                        logger.warning("GeoTIFF: tag 42112 (GDAL_METADATA) is present but contains no "
                                       "DESCRIPTION items — real season names are NOT recoverable this "
                                       "way for this file either.")
                except Exception as e:
                    logger.debug("GeoTIFF: failed to parse tag 42112 XML: %s", e)
            else:
                logger.warning("GeoTIFF: tag 42112 (GDAL_METADATA) is absent from this file — real "
                               "season names are not recoverable via GDAL's band-naming convention "
                               "for this file. Falling through to page.description, then the "
                               "positional order assumption if that's empty too.")

            # page.description (tag 270, ImageDescription) as a secondary
            # fallback source, read per physical page — kept for
            # non-channels-last files (genuinely separate pages) where
            # this might still carry a real value, or for files from a
            # non-GDAL tool that used this baseline tag instead.
            page_descriptions = []
            try:
                for page in full_res_pages:
                    page_descriptions.append((page.description or "").strip().lower())
            except Exception as e:
                logger.debug("GeoTIFF: could not read page descriptions: %s", e)

        # Normalise to (bands, H, W)
        if data.ndim == 2:
            data = data[np.newaxis]
        elif data.ndim == 3 and data.shape[2] < data.shape[0]:
            data = np.moveaxis(data, -1, 0)

        n_bands, H, W = data.shape

        # Build the final per-band description list now that n_bands is
        # known for certain — gdal_band_names (keyed by real band index)
        # takes priority; page_descriptions (keyed by physical page
        # index) only applies where it still makes sense, i.e. when there
        # were genuinely as many physical pages as real bands.
        raw_descriptions = []
        for i in range(n_bands):
            if i in gdal_band_names:
                raw_descriptions.append(gdal_band_names[i])
            elif i < len(page_descriptions):
                raw_descriptions.append(page_descriptions[i])
            else:
                raw_descriptions.append("")

        logger.info("GeoTIFF: file=%s shape=%s dtype=%s bands=%d descriptions=%s",
                    source_filename or "(unknown)", data.shape, data.dtype, n_bands,
                    raw_descriptions or "(none found)")

        # Map each band index to a real season name. Known season labels
        # (matching SEASON_COLOURS' keys, plus the "nonbreeding"/
        # "non-breeding" spelling variants GDAL metadata might use).
        KNOWN_SEASON_ALIASES = {
            "breeding": "breeding",
            "nonbreeding": "nonbreeding", "non-breeding": "nonbreeding",
            "prebreeding_migration": "prebreeding_migration", "prebreeding migration": "prebreeding_migration",
            "postbreeding_migration": "postbreeding_migration", "postbreeding migration": "postbreeding_migration",
            "resident": "resident", "year_round": "resident", "year-round": "resident",
        }
        band_to_season = {}
        # Sort aliases longest-first: "breeding" is a substring of
        # "nonbreeding"/"prebreeding_migration"/"postbreeding_migration",
        # so checking it first would incorrectly match every one of those
        # before ever reaching its own correct, more specific alias.
        # Confirmed this happened for real: a 4-band test file with
        # genuinely distinct descriptions all mapped to "breeding".
        sorted_aliases = sorted(KNOWN_SEASON_ALIASES.items(), key=lambda kv: -len(kv[0]))
        for i, desc in enumerate(raw_descriptions[:n_bands]):
            for alias, canonical in sorted_aliases:
                if alias in desc:
                    band_to_season[i] = canonical
                    break

        used_real_names = len(band_to_season) > 0
        if used_real_names and len(band_to_season) == n_bands:
            logger.info("GeoTIFF: using real per-band season names from file metadata: %s",
                        band_to_season)
        else:
            # Fall back to the documented eBird ebirdst convention (bands
            # present in breeding/nonbreeding/prebreeding/postbreeding/
            # resident order when ALL seasons passed review) — but ONLY
            # for whichever bands didn't already get a real name from
            # their own description. A real, confirmed gap: when some
            # bands have real descriptions but others don't (description-
            # reading partially failing on some pages), those bands were
            # previously left out of band_to_season entirely and silently
            # DROPPED from the render — not mislabeled, genuinely missing,
            # confirmed by testing a 4-band file where 2 real bands with
            # no readable description vanished from the output entirely.
            # Log this explicitly as an assumption for the affected bands
            # specifically, not a confirmed fact, since a file with fewer
            # bands than the fallback order covers (a season failed
            # review) would make a purely-positional guess wrong — exactly
            # the bug that produced a mislabeled single "breeding" band
            # for American Redstart in an earlier session.
            fallback_order = ["breeding", "nonbreeding", "prebreeding_migration",
                              "postbreeding_migration", "resident"]
            newly_assigned = []
            for i in range(n_bands):
                if i not in band_to_season and i < len(fallback_order):
                    band_to_season[i] = fallback_order[i]
                    newly_assigned.append(i)
            if used_real_names:
                logger.warning("GeoTIFF: %d of %d bands had real season names from file "
                               "metadata (%s); band(s) %s had none and fall back to the "
                               "standard order ASSUMPTION for their position specifically — "
                               "may not reflect the actual season for those bands.",
                               n_bands - len(newly_assigned), n_bands, band_to_season, newly_assigned)
            else:
                logger.warning("GeoTIFF: no real per-band season names found in file metadata for "
                               "%s (%d bands) — falling back to the standard breeding/nonbreeding/"
                               "premigration/postmigration/resident ORDER ASSUMPTION, which is only "
                               "correct if every season passed review and none were omitted. "
                               "Band labels below may not reflect the actual season.", species_code, n_bands)

        # Replace NaN / negative with 0
        data = np.where(np.isfinite(data) & (data > 0), data.astype(float), 0.0)

        # Per-band normalisation (preserve relative brightness between seasons)
        peaks = []
        for b in data:
            valid = b[b > 0]
            peaks.append(float(np.percentile(valid, 99)) if len(valid) > 0 else 1.0)
        peaks = np.array([p if p > 0 else 1.0 for p in peaks])
        normed = data / peaks[:, np.newaxis, np.newaxis]

        # Build RGBA canvas (float)
        canvas = np.zeros((H, W, 4), dtype=np.float32)

        for i in range(n_bands):
            season = band_to_season.get(i)
            if season is None:
                # A band with no resolvable season name at all (more bands
                # than the fallback order covers, or an unrecognized
                # description) — skip it rather than guess, so it doesn't
                # get silently mislabeled.
                logger.debug("GeoTIFF: band %d has no resolvable season name — skipping", i)
                continue
            cr, cg, cb, ca = SEASON_COLOURS.get(season, SEASON_COLOURS["breeding"])
            band = np.clip(normed[i], 0, 1)
            mask = band > 0.02

            # Alpha-over compositing
            alpha = band * (ca / 255.0)
            inv_a = 1.0 - alpha

            canvas[mask, 0] = canvas[mask, 0] * inv_a[mask] + (cr / 255.0) * alpha[mask]
            canvas[mask, 1] = canvas[mask, 1] * inv_a[mask] + (cg / 255.0) * alpha[mask]
            canvas[mask, 2] = canvas[mask, 2] * inv_a[mask] + (cb / 255.0) * alpha[mask]
            canvas[mask, 3] = np.minimum(1.0, canvas[mask, 3] + alpha[mask])

        # ── Coastline basemap ────────────────────────────────────────────────
        # Previously this rendered on a flat grey background with no land/
        # ocean context at all — just colored abundance pixels floating in
        # empty space, confirmed directly from reported screenshots. Adds a
        # real basemap, but this requires correctly reprojecting the lat/
        # lon coastline data into the GeoTIFF's own native projection — per
        # eBird's own ebirdst documentation, these files use the Equal
        # Earth projection (EPSG:8857), NOT plain lat/lon, so a naive
        # pixel-for-pixel overlay would be badly misaligned.
        #
        # This reads the file's OWN geo-referencing tags (GeoTIFF's
        # standard ModelPixelScale/ModelTiepoint + EPSG code, via
        # tifffile's geotiff_tags) rather than assuming Equal Earth blindly
        # — if a different product or future data version uses a different
        # projection, this still transforms correctly. Every step here is
        # wrapped defensively: if the file's geo-tags can't be read, or the
        # coastline data is missing, this falls back cleanly to the
        # previous flat-grey background rather than risk drawing a
        # plausible-looking but actually-misaligned map, which would be
        # worse than no basemap at all and isn't something verifiable
        # without a real downloaded eBird file to test against.
        bg = np.full((H, W, 3), 0.93, dtype=np.float32)
        try:
            # Use the same full_res_pages[0] reference the pixel data
            # itself came from, not tif.pages[0] — confirmed during review
            # that these could be DIFFERENT pages if an overview/pyramid
            # page happens to come first in file order (the same mixed-
            # page-ordering issue fixed for pixel data two sessions ago).
            # Reading geo-tags from the wrong page would silently use a
            # smaller overview's tags instead of the real full-resolution
            # page's, which could misalign the basemap without any error.
            page0 = full_res_pages[0] if full_res_pages else tif.pages[0]
            geo = page0.geotiff_tags or {}
            epsg = geo.get("ProjectedCSTypeGeoKey") or geo.get("GeographicTypeGeoKey")
            # ModelPixelScale (tag 33550) and ModelTiepoint (tag 33922) are
            # separate standard TIFF tags, not part of geotiff_tags (which
            # only carries GeoKey/CRS metadata) — confirmed directly by
            # inspecting tifffile's own implementation rather than assuming.
            pixel_scale = page0.tags.valueof(33550)
            tiepoint = page0.tags.valueof(33922)
            if epsg and pixel_scale and tiepoint:
                import pyproj
                from pathlib import Path as _Path
                # tiepoint format: (raster_i, raster_j, raster_k, x, y, z) —
                # the real-world coordinate of one known pixel, used with
                # pixel_scale to map any other pixel to real-world coords.
                tp_i, tp_j, _tp_k, tp_x, tp_y, _tp_z = tiepoint[:6]
                sx, sy = pixel_scale[0], pixel_scale[1]

                coast_path = _Path(__file__).parent.parent.parent / "data" / "geomodels" / "countries.geojson"
                # Reuse the same coastline file the iNat geomodel tab
                # already downloads, rather than fetching a separate copy.
                if not coast_path.exists():
                    # Try the configured data dir directly as a fallback
                    # location, in case this module is invoked from a
                    # different working layout than assumed above.
                    from ..config import settings as _settings
                    coast_path = _Path(_settings.data_dir) / "geomodels" / "countries.geojson"

                if coast_path.exists():
                    transformer = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
                    with open(coast_path) as f:
                        world = json.load(f)

                    from PIL import ImageDraw
                    basemap_img = Image.new("RGB", (W, H), (14, 26, 20))
                    draw = ImageDraw.Draw(basemap_img)

                    def world_to_pixel(x, y):
                        col = tp_i + (x - tp_x) / sx
                        row = tp_j - (y - tp_y) / sy
                        return (col, row)

                    n_drawn = 0
                    for feat in world.get("features", []):
                        geom = feat.get("geometry", {})
                        gtype = geom.get("type", "")
                        coords_list = geom.get("coordinates", [])
                        rings = []
                        if gtype == "Polygon":
                            rings = [coords_list[0]] if coords_list else []
                        elif gtype == "MultiPolygon":
                            rings = [poly[0] for poly in coords_list if poly]
                        for ring in rings:
                            try:
                                xs, ys = zip(*ring)
                                wx, wy = transformer.transform(xs, ys)
                                pts = [world_to_pixel(x, y) for x, y in zip(wx, wy)]
                                draw.polygon(pts, fill=(26, 46, 34), outline=(45, 74, 56))
                                n_drawn += 1
                            except Exception:
                                continue
                    if n_drawn > 0:
                        bg = np.asarray(basemap_img).astype(np.float32) / 255.0
                        logger.info("eBird S&T: drew coastline basemap (%d features, EPSG:%s)",
                                    n_drawn, epsg)
                    else:
                        logger.debug("eBird S&T: coastline file had no usable polygons — "
                                     "falling back to flat background")
                else:
                    logger.debug("eBird S&T: no countries.geojson basemap file found at %s — "
                                 "falling back to flat background (run the iNat geomodel "
                                 "download in Settings to fetch it)", coast_path)
            else:
                logger.debug("eBird S&T: GeoTIFF missing expected geo-referencing tags "
                             "(epsg=%s, pixel_scale=%s, tiepoint=%s) — falling back to flat "
                             "background rather than guess the projection", epsg, pixel_scale, tiepoint)
        except Exception as e:
            logger.warning("eBird S&T: basemap render failed (%s) — falling back to flat "
                           "background; this doesn't affect the abundance data itself", e)
            bg = np.full((H, W, 3), 0.93, dtype=np.float32)

        a = canvas[:, :, 3:4]
        rgb = (1 - a) * bg + a * canvas[:, :, :3]
        rgb_u8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)

        # Crop to content bounding box so the range fills the image rather
        # than appearing as a tiny blip on a global canvas. Detects "where
        # the abundance data is" by comparing against the FLAT grey value
        # specifically — not "any non-background color" — since with a
        # real basemap now present, large areas of land/ocean color would
        # otherwise be mistaken for "content" and prevent any meaningful
        # cropping at all.
        rgb_full = rgb_u8
        abundance_only = np.clip(canvas[:, :, 3], 0, 1) > 0.05
        rows_with = np.where(abundance_only.any(axis=1))[0]
        cols_with = np.where(abundance_only.any(axis=0))[0]
        if len(rows_with) > 0 and len(cols_with) > 0:
            r0, r1 = rows_with[0], rows_with[-1]
            c0, c1 = cols_with[0], cols_with[-1]
            h_range = r1 - r0
            w_range = c1 - c0
            # Generous padding: 60% of range extent (centres the range nicely)
            pad_r = max(20, int(h_range * 0.60))
            pad_c = max(20, int(w_range * 0.60))
            r0 = max(0, r0 - pad_r)
            r1 = min(H - 1, r1 + pad_r)
            c0 = max(0, c0 - pad_c)
            c1 = min(W - 1, c1 + pad_c)
            rgb_u8 = rgb_full[r0:r1+1, c0:c1+1]
            logger.info("eBird S&T: cropped %d×%d → %d×%d (content bbox)",
                        W, H, c1-c0+1, r1-r0+1)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgb_u8, "RGB").save(output_path, format="PNG", optimize=True)
        size = os.path.getsize(output_path)
        logger.info("eBird S&T rendered for %s: %d×%d, %d bytes → %s", species_code, W, H, size, output_path)
        return size > 1_000

    except Exception as e:
        logger.error("GeoTIFF render error for %s: %s", species_code, e, exc_info=True)
        return _render_tif_with_pil(tif_bytes, output_path, species_code)


def _render_tif_with_pil(tif_bytes: bytes, output_path: str, species_code: str) -> bool:
    """Fallback: render a single-band TIFF with PIL (no tifffile)."""
    try:
        img = Image.open(io.BytesIO(tif_bytes))
        arr = np.array(img).astype(float)
        if arr.ndim == 3:
            arr = arr.mean(axis=2)
        valid = arr[arr > 0]
        peak = float(np.percentile(valid, 99)) if len(valid) > 0 else 1.0
        normed = np.clip(arr / peak, 0, 1)
        cr, cg, cb, ca = SEASON_COLOURS["breeding"]
        bg = np.full((*arr.shape, 3), 237, dtype=np.uint8)
        alpha = normed * (ca / 255.0)
        mask = normed > 0.02
        for ch, c in enumerate([cr, cg, cb]):
            bg[:, :, ch] = np.where(
                mask,
                ((1 - alpha) * bg[:, :, ch] + alpha * c).astype(np.uint8),
                bg[:, :, ch],
            )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(bg, "RGB").save(output_path, format="PNG", optimize=True)
        size = os.path.getsize(output_path)
        logger.info("PIL TIFF fallback for %s: %d bytes", species_code, size)
        return size > 1_000
    except Exception as e:
        logger.error("PIL TIF fallback failed for %s: %s", species_code, e)
        return False


# ── GBIF ──────────────────────────────────────────────────────────────────────

# Correct tile coverage for North + Central America at zoom 3:
#   x=0  lon -180..-135  (Pacific / Alaska far west)
#   x=1  lon -135..-90   (Alaska, western Canada/US)
#   x=2  lon  -90..-45   (eastern US/Canada, Mexico east coast)
#   y=0  lat  ~85..66°N  (Arctic Canada, northern Alaska)
#   y=1  lat  ~66..41°N  (most of Canada, northern US)
#   y=2  lat  ~41..21°N  (southern US, Mexico)
#   y=3  lat  ~21..0°N   (Central America, Caribbean)
GBIF_ZOOM  = 3
GBIF_X0, GBIF_X1 = 0, 2    # 3 columns
GBIF_Y0, GBIF_Y1 = 0, 3    # 4 rows

# GBIF confirmed background tile styles (osm-bright is the light default)
GBIF_BG_STYLES = ["osm-bright", "gbif-classic"]

# Standard tile size at @1x
TILE_PX = 256


def fetch_gbif_map(
    scientific_name: str,
    common_name: str,
    output_path: str,
) -> bool:
    """
    Build a range map by stitching GBIF occurrence density tiles.

    Layout (zoom 3): 3 cols × 4 rows = 768×1024 px (before crop).
    Background: GBIF osm-bright base tiles.
    Overlay:    GBIF occurrence density with classic.poly style.

    No API key required.
    """
    if not scientific_name:
        logger.warning("fetch_gbif_map: no scientific_name provided")
        return False

    try:
        # ── 1. Resolve GBIF taxon key ─────────────────────────────────────────
        taxon_key = _gbif_taxon_key(scientific_name)
        if not taxon_key and common_name:
            logger.info("GBIF: no match for scientific name '%s', trying common name '%s'",
                        scientific_name, common_name)
            taxon_key = _gbif_taxon_key(common_name)
        if not taxon_key:
            logger.warning("GBIF: could not resolve taxon key for '%s'", scientific_name)
            return False
        logger.info("GBIF: taxon key for %s (%s) = %d", scientific_name, common_name, taxon_key)

        # ── 2. Build canvas ───────────────────────────────────────────────────
        n_cols = GBIF_X1 - GBIF_X0 + 1   # 3
        n_rows = GBIF_Y1 - GBIF_Y0 + 1   # 4
        # Default: GBIF water/background colour (#C2D9EA — light blue-grey)
        canvas = Image.new("RGBA", (n_cols * TILE_PX, n_rows * TILE_PX), (194, 217, 234, 255))

        # ── 3. Fetch background + occurrence tiles ────────────────────────────
        bg_hits = 0
        occ_hits = 0
        bg_style = _probe_bg_style()   # find which GBIF bg style is accessible

        for tx in range(GBIF_X0, GBIF_X1 + 1):
            for ty in range(GBIF_Y0, GBIF_Y1 + 1):
                px = (tx - GBIF_X0) * TILE_PX
                py = (ty - GBIF_Y0) * TILE_PX

                # Background tile (land/water/labels)
                if bg_style:
                    if _fetch_tile(canvas, px, py,
                                   f"{GBIF_BG_TILES}/{GBIF_ZOOM}/{tx}/{ty}@1x.png",
                                   {"style": bg_style},
                                   overlay=False):
                        bg_hits += 1

                # Occurrence density overlay (semi-transparent hex/poly)
                if _fetch_tile(canvas, px, py,
                               f"{GBIF_MAP_TILES}/{GBIF_ZOOM}/{tx}/{ty}@1x.png",
                               {
                                   "taxonKey": str(taxon_key),
                                   "style":    "classic.poly",
                                   "bin":      "hex",
                                   "hexPerTile": "25",
                               },
                               overlay=True):
                    occ_hits += 1

        logger.info("GBIF tiles: bg_hits=%d/%d, occ_hits=%d/%d",
                    bg_hits, n_cols * n_rows, occ_hits, n_cols * n_rows)

        if occ_hits == 0:
            logger.warning("GBIF: no occurrence tiles fetched — species may have no GBIF records")
            return False

        # ── 4. Crop: remove left dead space (Pacific Ocean from x=0 tiles)
        #    and bottom 20% (Central America / Amazon for most NA birds).
        # x=0 spans lon -180..-135; the leftmost ~200px are open Pacific.
        # Cropping 200px removes the blank left margin without cutting Alaska.
        left_crop = 200
        crop_h = int(canvas.height * 0.82)
        canvas = canvas.crop((left_crop, 0, canvas.width, crop_h))

        # ── 5. Flatten RGBA → RGB ─────────────────────────────────────────────
        bg_img = Image.new("RGB", canvas.size, (194, 217, 234))
        bg_img.paste(canvas, mask=canvas.split()[3])

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        bg_img.save(output_path, format="PNG", optimize=True)
        size = os.path.getsize(output_path)
        logger.info("GBIF map saved for %s: %d bytes → %s", scientific_name, size, output_path)
        return size > 5_000

    except Exception as e:
        logger.error("fetch_gbif_map error for %s: %s", scientific_name, e, exc_info=True)
        return False


def _probe_bg_style() -> Optional[str]:
    """
    Probe which GBIF background tile style is accessible from this server.
    Returns the style name, or None if all fail (occurrence-only mode).
    """
    for style in GBIF_BG_STYLES:
        try:
            r = httpx.get(
                f"{GBIF_BG_TILES}/{GBIF_ZOOM}/1/1@1x.png",
                params={"style": style},
                headers={"User-Agent": UA, "Accept": "image/png"},
                timeout=8,
            )
            if r.status_code == 200 and len(r.content) > 500:
                logger.info("GBIF background tiles: using style '%s'", style)
                return style
        except Exception:
            pass
    logger.warning("GBIF background tiles: all styles failed — occurrence-only mode")
    return None


def _gbif_taxon_key(name: str) -> Optional[int]:
    """Match a name to GBIF backbone taxonomy. Returns usageKey or None."""
    if not name:
        return None
    try:
        r = httpx.get(
            f"{GBIF_SPECIES_API}/match",
            params={"name": name, "rank": "SPECIES", "strict": "false"},
            headers={"User-Agent": UA},
            timeout=10,
        )
        if r.status_code != 200:
            logger.debug("GBIF species/match HTTP %d for '%s'", r.status_code, name)
            return None
        d = r.json()
        key = d.get("usageKey") or d.get("speciesKey") or d.get("genusKey")
        if key:
            logger.debug("GBIF match for '%s': confidence=%s matchType=%s key=%s",
                         name, d.get("confidence"), d.get("matchType"), key)
        return key
    except Exception as e:
        logger.debug("GBIF match error for '%s': %s", name, e)
        return None


def _fetch_tile(
    canvas: Image.Image,
    px: int,
    py: int,
    url: str,
    params: dict,
    overlay: bool,
    retries: int = 2,
) -> bool:
    """
    Download one map tile and composite it onto the canvas.

    overlay=False → paste as opaque background (RGB)
    overlay=True  → alpha-composite over existing content (RGBA)
    Retries up to `retries` times on transient failures.
    """
    for attempt in range(retries + 1):
        try:
            if attempt > 0:
                time.sleep(0.3 * attempt)
            r = httpx.get(
                url,
                params=params,
                headers={
                    "User-Agent": UA,
                    "Accept":     "image/png,image/*",
                    "Referer":    "https://www.gbif.org/",
                },
                timeout=12,
            )
            # 204 = no occurrences in this tile (valid, don't retry)
            if r.status_code == 204:
                return False
            if r.status_code != 200 or not r.content or len(r.content) < 100:
                continue
            tile = Image.open(io.BytesIO(r.content)).convert("RGBA")
            if overlay:
                # Only paste if tile has actual content (not blank transparent)
                arr = np.array(tile)
                if arr[:, :, 3].max() < 10:
                    return False   # fully transparent → no occurrences here
                canvas.paste(tile, (px, py), mask=tile.split()[3])
            else:
                canvas.paste(tile.convert("RGB"), (px, py))
            return True
        except Exception as e:
            logger.debug("Tile attempt %d/%d failed %s: %s", attempt + 1, retries + 1, url[:80], e)
    return False
