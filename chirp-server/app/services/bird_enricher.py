"""
Chirp Server — Bird Enricher
Fetches comprehensive bird data from:
  - Wikipedia MediaWiki API (full article sections)
  - iNaturalist API (photos, sounds, conservation, taxonomy)
  - Cornell eBird API (species code, bar chart frequency, range maps)

Range map priority (Merlin-equivalent):
  1. Macaulay Library / Cornell CDN PNG (same source as eBird web + Merlin)
  2. All About Birds PNG (Cornell Lab consumer site)
  3. Wikipedia Commons SVG (redirected to browser)

Seasonal frequency priority:
  1. eBird bar chart API (true 12-month checklist frequency, Merlin-style)
  2. iNaturalist monthly histogram (fallback)
"""

import html as _html
import logging
import os
import re as _re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import httpx

from ..config import settings
from ..models import BirdProfile
from .bat_profile_content import (
    BAT_LABEL, BAT_COMMON_NAME, BAT_SCIENTIFIC_NAME, BAT_DESCRIPTION_SECTIONS,
)

logger = logging.getLogger("chirp.enricher")


class AABBlockedError(Exception):
    """
    Raised when an All About Birds fetch hits Cloudflare's own challenge
    page ("Attention Required") rather than a species page or AAB's
    own clean "Search Results" not-found fallback. Deliberately distinct
    from a plain None return: a blocked request tells us nothing about
    whether AAB has a page for this species, so it must NOT be
    treated the same as a confirmed no-page result — see _do_enrich's
    aab_fetched_at handling, which only permanently skips future
    retries for a confirmed no-page result, not a blocked one.
    """
    pass

_enriching_now: Set[str] = set()
RATE_LIMIT_SECONDS = 1.0  # was 0.5 — iNaturalist's own API guidance is roughly
                          # 1 request/second as a courtesy limit; confirmed via
                          # real 429s in production logs that 0.5s wasn't
                          # enough headroom during a sustained bulk run
_last_request_time: float = 0.0

# Wikipedia requires UA with contact info
WIKIPEDIA_UA = "Chirp-BirdDetection/1.0 (https://github.com/chirp-bird; chirp@localhost) python-httpx/0.27"
UA = "Chirp-BirdDetection/1.0 (automated bird call monitor; non-commercial)"

BIRD_SECTIONS_INCLUDE = {
    "description", "identification", "appearance", "plumage",
    "distribution", "habitat", "range", "distribution and habitat",
    "behavior", "behaviour", "ecology", "behavior and ecology",
    "diet", "feeding", "food", "foraging",
    "voice", "song", "calls", "vocalizations", "sounds",
    "reproduction", "breeding", "nesting", "eggs",
    "migration", "flight", "movements",
    "conservation", "status", "population", "threats",
    "taxonomy", "systematics", "subspecies", "phylogeny",
    "relationship", "relationship with humans", "in culture",
}

BIRD_SECTIONS_EXCLUDE = {
    "references", "further reading", "external links", "see also",
    "notes", "footnotes", "bibliography", "sources", "citations",
    "gallery", "images",
}


def _throttle():
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _get(url: str, params: dict = None, headers: dict = None, timeout: int = 20) -> Optional[dict]:
    """
    Fetch JSON from `url`. Retries on 429 specifically — confirmed via real
    logs that iNaturalist's API ("normal_throttling") returns this for a
    sustained burst during bulk maps-only refreshes (139 birds, back-to-back
    calls at the shared 0.5s throttle), and even a single one-off request
    from the same container got 429 immediately afterward — the account/IP
    stays in a cooldown window for a while, not just during the burst
    itself. Respects a Retry-After header when iNaturalist sends one, else
    a fixed backoff; gives up after a few tries rather than looping forever.
    Every other status/exception path is unchanged — this only adds
    handling for 429.
    """
    hdrs = {"User-Agent": UA}
    if headers:
        hdrs.update(headers)
    max_retries = 3
    for attempt in range(max_retries + 1):
        _throttle()
        try:
            r = httpx.get(url, params=params, headers=hdrs, timeout=timeout, follow_redirects=True)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429 and attempt < max_retries:
                retry_after = r.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else (2.0 * (attempt + 1))
                except ValueError:
                    wait = 2.0 * (attempt + 1)
                logger.warning("GET %s -> 429, retrying in %.1fs (attempt %d/%d)",
                               url, wait, attempt + 1, max_retries)
                time.sleep(wait)
                continue
            logger.debug("GET %s -> %d", url, r.status_code)
            return None
        except Exception as e:
            logger.debug("GET %s failed: %s", url, e)
            return None
    return None


def _download_file(url: str, dest_path: str, timeout: int = 45,
                   extra_headers: dict = None) -> bool:
    """
    Download `url` to `dest_path`. Retries on 429 — same fix, same reason,
    as _get() above: confirmed via real logs that iNaturalist rate-limits
    sustained bursts, and this binary-download path had no retry and only
    logged failures at debug (invisible without verbose logging). This is
    the actual reason the Bat profile's photo has stayed empty — its
    fetch used to bypass this helper (and _get) entirely via a raw
    httpx.get() call with no retry at all; now routed through both.
    """
    hdrs = {"User-Agent": UA}
    if extra_headers:
        hdrs.update(extra_headers)
    max_retries = 3
    for attempt in range(max_retries + 1):
        _throttle()
        try:
            with httpx.stream("GET", url, timeout=timeout, follow_redirects=True,
                              headers=hdrs) as r:
                if r.status_code == 429 and attempt < max_retries:
                    retry_after = r.headers.get("Retry-After")
                    try:
                        wait = float(retry_after) if retry_after else (2.0 * (attempt + 1))
                    except ValueError:
                        wait = 2.0 * (attempt + 1)
                    logger.warning("Download %s -> 429, retrying in %.1fs (attempt %d/%d)",
                                   url, wait, attempt + 1, max_retries)
                    time.sleep(wait)
                    continue
                if r.status_code != 200:
                    logger.debug("Download %s -> %d", url, r.status_code)
                    return False
                Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=16384):
                        f.write(chunk)
            size = os.path.getsize(dest_path)
            if size < 500:
                os.remove(dest_path)
                logger.debug("Downloaded file too small (%d bytes): %s", size, url)
                return False
            return True
        except Exception as e:
            logger.debug("Download failed %s: %s", url, e)
            return False
    return False


def _strip_html(text: str) -> str:
    if not text:
        return text
    clean = _re.sub(r"\[\d+\]", "", text)
    clean = _re.sub(r"<[^>]+>", "", clean)
    clean = _html.unescape(clean)
    clean = _re.sub(r"\s+", " ", clean).strip()
    return clean


def _get_ebird_api_key(db=None) -> Optional[str]:
    """
    Resolve eBird API key: DB settings > env config.
    Always check DB first so web-UI changes are reflected immediately.
    """
    if db is not None:
        try:
            from ..models import AppSettings
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            if s and s.ebird_api_key:
                return s.ebird_api_key
        except Exception:
            pass
    return settings.ebird_api_key or None


def _upsize_inat_photo_url(url: Optional[str]) -> Optional[str]:
    """
    Given an iNaturalist large_url (1024px), derive the corresponding
    original-size URL (up to 2048px) by substituting the size qualifier in
    the URL path. Per iNaturalist's own documented photo URL convention,
    every size variant of a given photo shares an identical URL structure,
    differing only in the size-name path segment (e.g. ".../large.jpg" vs
    ".../original.jpg") — confirmed via iNaturalist's own API
    documentation, not assumed. This is a pure string transformation, so
    it works even in the case where a given API response shape doesn't
    return original_url as its own JSON key — the upstream caller already
    tries the field first and only falls back to this derivation.
    Returns None (not the original url unmodified) if the expected
    "/large." pattern isn't found, so callers can correctly fall through
    to their own next fallback rather than silently reusing the smaller
    large_url as if it were upsized.
    """
    if not url or "/large." not in url:
        return None
    return url.replace("/large.", "/original.", 1)


class BirdEnricher:
    ENRICH_INTERVAL_DAYS = 30

    def __init__(self, db):
        self.db = db
        # Read range_maps_enabled from AppSettings
        try:
            from ..models import AppSettings
            s = db.query(AppSettings).filter(AppSettings.id == 1).first()
            self._range_maps_enabled = bool(getattr(s, 'range_maps_enabled', False)) if s else False
            # Per-source visibility toggles — {"aab": bool, "geomodel": bool, "birdlife": bool}.
            # Used by the eager pre-fetch step in _resolve_range_map() so we
            # don't spend a Playwright session capturing a BirdLife map (or
            # rendering a geomodel one) the person has that source's toggle
            # turned off for and will never see.
            self._range_map_sources = getattr(s, 'range_map_sources', None) or {} if s else {}
        except Exception:
            self._range_maps_enabled = False
            self._range_map_sources = {}

    def ensure_profile(self, label: str, is_bat: bool = False) -> Optional[BirdProfile]:
        # "Bat" is not a species — Chirp's bat detector identifies
        # activity, not species (see bat_detector.py). Rather than running
        # it through the normal Wikipedia/iNaturalist/eBird lookup pipeline
        # (which expects a binomial name), seed it once from a static,
        # hand-written profile and never re-enrich it. See
        # services/bat_profile_content.py for the full rationale.
        if label == BAT_LABEL:
            return self._ensure_bat_profile()

        profile = self.db.query(BirdProfile).filter(BirdProfile.label == label).first()
        if not profile:
            profile = self._create_profile(label, is_bat=is_bat)
            if not profile:
                return None
        elif is_bat and not profile.is_bat:
            # Self-heal: a profile created before is_bat existed, or
            # created through a path that didn't know this was a bat
            # species yet. Confirmed value in this pattern already
            # this session (the BirdProfile de-duplication fix) — cheap
            # to check, meaningfully fixes stale data going forward
            # without needing a separate one-off migration script.
            profile.is_bat = True
            self.db.add(profile)
            self.db.commit()
        should_enrich = (
            not profile.enrichment_complete
            or profile.last_enriched is None
            or datetime.utcnow() - profile.last_enriched > timedelta(days=self.ENRICH_INTERVAL_DAYS)
        )
        if should_enrich:
            self.enrich_profile(profile)
        return profile

    def _ensure_bat_profile(self, force: bool = False) -> BirdProfile:
        """
        Create (once) or return the single static "Bat" profile.
        Downloads an iNaturalist photo if one isn't already stored, or
        unconditionally re-downloads it when force=True (a manual "refresh"
        trigger, e.g. if the photo failed to download the first time or
        just to retry against iNaturalist again).
        """
        candidates = (
            self.db.query(BirdProfile)
            .filter(BirdProfile.label == BAT_LABEL)
            .order_by(BirdProfile.last_enriched.desc().nullslast())
            .all()
        )
        if len(candidates) > 1:
            # Self-healing de-duplication — fix for a confirmed
            # inconsistency: label has unique=True at the model level, but
            # that's only enforced if the database table was
            # created with that constraint present. A table that predates
            # this constraint being added to the model (this project
            # migrates schemas by adding columns via ALTER TABLE, not by
            # retroactively adding constraints to existing tables) could
            # genuinely have accumulated more than one "Bat" row over the
            # many iterations bat-profile handling went through this
            # project's history. Different code paths independently doing
            # `.filter(label==BAT_LABEL).first()` would then non-
            # deterministically get back whichever row the database
            # happened to return first — exactly the reported symptom of
            # the same profile showing a photo in some places (recent
            # detection rows) and a blank fallback in others (Dashboard,
            # Life List), depending on which duplicate row each one
            # happened to resolve to.
            keep = next((p for p in candidates if p.photo_path and os.path.exists(p.photo_path)), candidates[-1])
            removed = [p.id for p in candidates if p.id != keep.id]
            logger.warning(
                "Found %d duplicate 'Bat' BirdProfile rows — keeping %s (photo_path=%r), removing %s",
                len(candidates), keep.id, keep.photo_path, removed,
            )
            # Re-point anything that references a duplicate being removed
            # to the one being kept FIRST — BirdPhoto (user-uploaded
            # photos) and Comment both have a bird_profile_id foreign key;
            # deleting a referenced row without this would either violate
            # the constraint outright or, since SQLite doesn't enforce
            # foreign keys by default, silently leave those rows pointing
            # at a profile id that no longer exists.
            from ..models import BirdPhoto, Comment
            if removed:
                self.db.query(BirdPhoto).filter(BirdPhoto.bird_profile_id.in_(removed)).update(
                    {"bird_profile_id": keep.id}, synchronize_session=False,
                )
                self.db.query(Comment).filter(Comment.bird_profile_id.in_(removed)).update(
                    {"bird_profile_id": keep.id}, synchronize_session=False,
                )
            for dup in candidates:
                if dup.id != keep.id:
                    self.db.delete(dup)
            self.db.commit()
            profile = keep
        else:
            profile = candidates[0] if candidates else None

        if profile:
            # If photo is missing, try to fetch it without re-enriching everything
            if force or not profile.photo_path or not os.path.exists(profile.photo_path or ""):
                self._fetch_bat_photo(profile)
            # The caller (trigger_enrichment) sets enrichment_complete=False
            # before queuing this so the frontend can poll for completion —
            # must set it back to True here or a manual refresh on an
            # already-existing profile leaves it stuck showing "in progress"
            # forever, since nothing else would ever flip it back.
            # BUT only when the photo is actually there — was unconditional
            # before, which is the real reason this profile's photo stayed
            # empty for months: one failed attempt (rate limiting) got
            # marked "done" anyway, so nothing ever retried it.
            profile.enrichment_complete = bool(profile.photo_path and os.path.exists(profile.photo_path))
            profile.last_enriched = datetime.utcnow()
            # Self-heal: a profile created before is_bat existed as a
            # column at all — same pattern as the de-duplication fix
            # above, cheap to check and fixes stale data going forward.
            if not profile.is_bat:
                profile.is_bat = True
            # Self-heal the profile's identity too — common_name and
            # scientific_name should always be the canonical "Bat" /
            # "Chiroptera" for this pseudo-species, regardless of any
            # prior manual edit. The representative photo (currently
            # Little Brown Bat, the most common regional species) is
            # intentionally decoupled from the profile's identity — it's
            # just a stock image standing in for "some unidentified bat,"
            # not an identification, and the title shouldn't ever
            # look like one. Confirmed this exact drift was the root
            # cause behind several separate-looking bugs earlier this
            # session (missing recordings, missing photos on Dashboard/
            # Life List) — all traced back to one stale manual edit.
            if profile.common_name != BAT_COMMON_NAME:
                profile.common_name = BAT_COMMON_NAME
            if profile.scientific_name != BAT_SCIENTIFIC_NAME:
                profile.scientific_name = BAT_SCIENTIFIC_NAME
            self.db.add(profile)
            self.db.commit()
            return profile

        profile = BirdProfile(
            label=BAT_LABEL,
            common_name=BAT_COMMON_NAME,
            scientific_name=BAT_SCIENTIFIC_NAME,
            is_bat=True,
            description=BAT_DESCRIPTION_SECTIONS[1]["text"],
            description_source="https://en.wikipedia.org/wiki/Bat",
            description_sections=BAT_DESCRIPTION_SECTIONS,
            order_name="Chiroptera",
            family_name=None,
            range_map_url=None,
            conservation_status=None,
            inaturalist_id=40346, # Little Brown Bat — used for photo only
            inaturalist_url="https://www.inaturalist.org/taxa/40346",
            enrichment_complete=True,
            last_enriched=datetime.utcnow(),
        )
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        self._fetch_bat_photo(profile)
        logger.info("Created static 'Bat' profile (not enriched via normal pipeline)")
        return profile

    def _fetch_bat_photo(self, profile: BirdProfile) -> None:
        """
        Download and store a representative bat photo from iNaturalist.

        Was a raw httpx.get() call with no retry at all and failures
        logged only at debug — meaning a single 429 from iNaturalist (the
        same sustained rate-limiting confirmed elsewhere this session via
        real logs and a direct curl test) silently killed this the very
        first time it ran, and nothing ever retried it afterward since
        profile.photo_path stays set to None, which doesn't itself
        trigger another attempt. Now routes through _get() (JSON, already
        has 429 retry-with-backoff) and _download_file() (binary, same
        fix just added above) instead of a bare httpx call, and logs a
        real reason on failure instead of a silent debug line.
        """
        bat_dir = os.path.join(settings.media_dir, "Bat")
        os.makedirs(bat_dir, exist_ok=True)
        photo_path = os.path.join(bat_dir, "photo.jpg")

        # Little Brown Bat, taxon 40346
        data = _get("https://api.inaturalist.org/v1/taxa/40346")
        if not data:
            logger.warning("Bat profile photo: iNaturalist taxon lookup failed — "
                           "see the 429/retry warnings above if this was rate limiting")
            return

        taxon = (data.get("results") or [{}])[0]
        photo_url = None
        dp = taxon.get("default_photo") or {}
        if dp.get("medium_url"):
            photo_url = dp["medium_url"]
        elif taxon.get("taxon_photos"):
            tp = taxon["taxon_photos"][0].get("photo", {})
            photo_url = tp.get("medium_url") or tp.get("url")

        if not photo_url:
            logger.warning("Bat profile photo: iNaturalist taxon 40346 has no usable photo URL")
            return

        if not _download_file(photo_url, photo_path, extra_headers={"User-Agent": UA}):
            logger.warning("Bat profile photo: download failed for %s", photo_url)
            return

        credit = dp.get("attribution") or "© iNaturalist contributors"
        profile.photo_path = photo_path
        profile.photo_url = photo_url
        profile.photo_credit = credit
        self.db.commit()
        logger.info("Bat profile photo saved to %s", photo_path)

    def _create_profile(self, label: str, is_bat: bool = False) -> Optional[BirdProfile]:
        parts = label.split("_", 1)

        def _looks_scientific(name: str) -> bool:
            words = name.strip().split()
            # a genus name is a single Title-Case word with no
            # internal hyphen. Without the hyphen check on words[0], a
            # hyphenated common name that happens to split into exactly
            # two whitespace-separated tokens with a capitalized first
            # word — e.g. "Silver-haired bat", "Red-winged blackbird",
            # "Big-eared bat" — false-positives as "scientific-looking"
            # (confirmed directly: this swapped common_name/scientific_name
            # for the "Lasionycteris noctivagans_Silver-haired bat"
            # profile in production). Genus names in binomial nomenclature
            # are never hyphenated, so this check has no legitimate
            # scientific name it could wrongly exclude.
            return (
                len(words) == 2
                and "-" not in words[0]
                and words[0][0].isupper()
                and words[0][1:].islower()
                and words[1][0].islower()
                and all(c.isalpha() or c == "-" for c in words[1])
            )

        if len(parts) == 2:
            p0, p1 = parts[0].strip(), parts[1].strip()
            if _looks_scientific(p0) and not _looks_scientific(p1):
                common_name, scientific_name = p1, p0
            else:
                common_name, scientific_name = p0, p1
        else:
            common_name = parts[0].strip() if parts else label
            scientific_name = None

        profile = BirdProfile(
            id=str(uuid.uuid4()), label=label,
            common_name=common_name, scientific_name=scientific_name,
            is_bat=is_bat,
        )
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def enrich_profile(self, profile: BirdProfile, force: bool = False, maps_only: bool = False) -> None:
        key = profile.id
        if key in _enriching_now:
            return
        _enriching_now.add(key)
        try:
            self._do_enrich(profile, force, maps_only)
        finally:
            _enriching_now.discard(key)

    def _do_enrich(self, profile: BirdProfile, force: bool = False, maps_only: bool = False) -> None:
        logger.info("Enriching: %s (force=%s, maps_only=%s)", profile.common_name, force, maps_only)

        # The "Bat" pseudo-species has its own dedicated, deliberately
        # curated photo path (_fetch_bat_photo — Little Brown Bat, a
        # single stable representative image) and isn't a real species
        # with a genuine Wikipedia/iNaturalist page of its own. Found the
        # hard way: this general pipeline has no is_bat awareness at
        # all, so if it ever ran for this profile (any caller passing
        # force=True — a "Refresh All Data" button, a startup sweep that
        # flips enrichment_complete — see main.py's own range-map reset
        # for the same finding), Step 2 below would overwrite the
        # carefully-set photo with whatever iNaturalist happens to
        # return for a bare "Chiroptera" search — an entire order, not
        # one species, so not a query with any single correct answer.
        # Routed to the dedicated function instead, every time.
        if getattr(profile, "is_bat", False):
            if force or not profile.photo_path or not os.path.exists(profile.photo_path or ""):
                self._fetch_bat_photo(profile)
            # Only mark complete if the photo is actually there now — was
            # unconditional before, which is the real reason this stayed
            # broken since the profile's first enrichment attempt: a single
            # transient failure (rate limiting, a network blip) got the
            # profile marked "done" anyway, so nothing ever retried it again
            # afterward — not a startup sweep, not a bulk refresh, nothing
            # that gates on enrichment_complete. Leaving it False on failure
            # means the next of any of those passes will actually try again.
            profile.enrichment_complete = bool(profile.photo_path and os.path.exists(profile.photo_path))
            profile.last_enriched = datetime.utcnow()
            self.db.commit()
            return

        # ── Step 0: Resolve scientific name ───────────────────────────────────
        # Kept even in maps_only mode — _resolve_range_map and the S&T/GBIF
        # prefetch both need this. Skipping it would silently produce no map
        # at all for any bird that hasn't already been fully enriched once.
        if not profile.scientific_name:
            sci = self._resolve_scientific_name(profile.common_name)
            if sci:
                profile.scientific_name = sci

        sci_name = profile.scientific_name
        common_name = profile.common_name

        range_map_wiki = None

        if not maps_only:
            # ── Step 1: Wikipedia full article ────────────────────────────────
            if not profile.description or not profile.description_sections or force:
                sections, wiki_url, range_map_wiki = self._fetch_wikipedia_full(common_name, sci_name)
                if sections:
                    profile.description = sections[0]["text"] if sections else ""
                    profile.description_source = wiki_url
                    profile.description_sections = sections
                    logger.info("Wikipedia: %d sections for %s", len(sections), common_name)

            # ── Step 2: iNaturalist ───────────────────────────────────────────
            inat = self._fetch_inaturalist_full(sci_name or common_name)
            if inat:
                taxon_id = inat.get("taxon_id")
                if not profile.scientific_name and inat.get("scientific_name"):
                    profile.scientific_name = inat["scientific_name"]
                    sci_name = profile.scientific_name
                if not profile.order_name:
                    profile.order_name = inat.get("order")
                if not profile.family_name:
                    profile.family_name = inat.get("family")
                profile.inaturalist_id = taxon_id
                profile.inaturalist_url = f"https://www.inaturalist.org/taxa/{taxon_id}"

                # Fallback description
                if not profile.description and inat.get("wikipedia_summary"):
                    clean = _strip_html(inat["wikipedia_summary"])
                    profile.description = clean
                    profile.description_source = inat.get("wikipedia_url", "")
                    profile.description_sections = [{"section": "Overview", "text": clean}]

                if (not profile.photo_path or force) and inat.get("photo_url"):
                    profile.photo_url = inat["photo_url"]
                    profile.photo_credit = inat.get("photo_credit", "")
                    if settings.media_download_enabled:
                        local = self._download_photo(inat["photo_url"], common_name, "inaturalist")
                        if local:
                            profile.photo_path = local

                if (not profile.extra_photos or force) and inat.get("extra_photos"):
                    profile.extra_photos = inat["extra_photos"]

                if (not profile.conservation_status or force) and inat.get("conservation_status"):
                    profile.conservation_status = inat["conservation_status"]
                    profile.conservation_authority = inat.get("conservation_authority", "IUCN")

            # ── Step 2.5: Cornell Lab of Ornithology / All About Birds ──────
            # A distinct source from Wikipedia/iNaturalist above —
            # curated specifically for birds (behavior, ID, backyard tips),
            # not general-purpose. Fetched AFTER Wikipedia/iNaturalist
            # (Step 1/2) rather than before, deliberately: if AAB has no
            # page for this species (a non-error outcome —
            # _fetch_aab_overview returns None cleanly), profile.description
            # is already populated from Wikipedia by this point and stays
            # that way, rather than the ordering accidentally leaving a
            # profile with no description at all.
            if not profile.aab_fetched_at or force:
                aab_blocked = False
                try:
                    aab = self._fetch_aab_overview(common_name)
                except AABBlockedError as e:
                    # Cloudflare blocked every slug attempt — this says
                    # nothing about whether AAB has a page for
                    # this species, so deliberately do NOT stamp
                    # aab_fetched_at here. Leaving it unset means the next
                    # time this profile goes through _do_enrich (a force
                    # refresh, or a startup migration marking it for
                    # re-enrichment) will genuinely retry AAB instead of
                    # being permanently, silently stuck with no Cool Facts
                    # from a single blocked attempt — the confirmed
                    # cause of profiles that show no AAB content despite
                    # AAB genuinely having a page for that species.
                    aab = None
                    aab_blocked = True
                    logger.info("AAB blocked for %s, will retry later: %s", common_name, e)
                if aab:
                    profile.aab_url = aab["aab_url"]
                    profile.aab_description = aab["description"]
                    profile.aab_cool_facts = aab["cool_facts"]
                    profile.aab_habitat = aab["habitat"]
                    profile.aab_food = aab["food"]
                    profile.aab_nesting = aab["nesting"]
                    profile.aab_behavior = aab["behavior"]
                    # Confirmed find while building the Life History card: this
                    # exact scraper (the same tagAnchors query above) was
                    # already extracting a "conservation" tag alongside the
                    # other four — it just never got assigned to anything,
                    # silently discarded on every enrichment pass.
                    if aab.get("conservation"):
                        profile.aab_conservation = aab["conservation"]
                    profile.aab_fetched_at = datetime.utcnow()
                    # Prefer Cornell Lab's own description over Wikipedia's
                    # when both are available — genuinely more specific to
                    # bird identification/behavior than a general-purpose
                    # encyclopedia entry, and this project's stated
                    # motivation for adding this source at all. Still keeps
                    # description_source/description_sections (Wikipedia)
                    # intact underneath — nothing is deleted, only which
                    # field wins as the PRIMARY description changes.
                    if aab.get("description"):
                        profile.description = aab["description"]
                        profile.description_source = aab["aab_url"]
                elif not aab_blocked:
                    # A deliberate no-op: AAB genuinely has no page
                    # for some species (e.g. bats, which aren't birds and
                    # were never expected to match), or the slug attempts
                    # all failed for a non-block reason — still stamp
                    # aab_fetched_at so this species isn't silently
                    # retried (and rate-limited against) on every single
                    # enrichment pass forever. A blocked attempt (handled
                    # above) deliberately skips this stamp instead.
                    profile.aab_fetched_at = datetime.utcnow()

                # Step 2.6: AAB size/length (At a Glance size-comparison
                # ruler) — a genuinely separate page/tab fetch from
                # everything above (see _fetch_aab_size's docstring), so
                # it runs as its own try/except rather than reusing the
                # overview result. Shares the same outer retry gate
                # (only attempted once per enrichment pass, same as
                # everything else in this block) rather than a fully
                # independent one — an accepted tradeoff for not
                # adding yet another separate blocked/no-op stamping
                # scheme for a single supplementary field.
                try:
                    size = self._fetch_aab_size(common_name)
                except AABBlockedError as e:
                    size = None
                    logger.info("AAB size blocked for %s, will retry later: %s", common_name, e)
                if size:
                    profile.aab_length_min_cm = size["length_min_cm"]
                    profile.aab_length_max_cm = size["length_max_cm"]
                    profile.aab_length_text = size["length_text"]

                # Step 2.7: AAB Life History — the full narrative
                # paragraphs behind Habitat/Food/Nesting/Behavior/
                # Conservation, from yet another separate AAB page/tab
                # (see _fetch_aab_lifehistory's docstring). Same shared-
                # retry-gate tradeoff as Step 2.6 above.
                try:
                    lifehistory = self._fetch_aab_lifehistory(common_name)
                except AABBlockedError as e:
                    lifehistory = None
                    logger.info("AAB lifehistory blocked for %s, will retry later: %s", common_name, e)
                if lifehistory:
                    if lifehistory.get("habitat"):
                        profile.aab_habitat_text = lifehistory["habitat"]
                    if lifehistory.get("food"):
                        profile.aab_food_text = lifehistory["food"]
                    if lifehistory.get("nesting"):
                        profile.aab_nesting_text = lifehistory["nesting"]
                    if lifehistory.get("behavior"):
                        profile.aab_behavior_text = lifehistory["behavior"]
                    if lifehistory.get("conservation"):
                        profile.aab_conservation_text = lifehistory["conservation"]
        else:
            # maps_only: we still need profile.inaturalist_id for the geomodel
            # prefetch below. If it's missing, do the lightweight iNat lookup
            # just for the taxon ID — skip everything else iNat-related.
            #
            # Added logging on both outcomes here — this branch previously had
            # none at all, and _fetch_inaturalist_full's own underlying _get()
            # only logs failures at debug level (same invisible-without-
            # verbose-logging class of bug already fixed for AAB/Playwright
            # elsewhere this session). A bird stuck with no inaturalist_id
            # across repeated maps-only refreshes was indistinguishable from
            # "never attempted" and "attempted, failed every time" with no
            # way to tell which from normal logs — reported directly as
            # geomodel showing "no inaturalist_id on file" even after
            # refreshing multiple times.
            if not profile.inaturalist_id:
                inat = self._fetch_inaturalist_full(sci_name or common_name)
                if inat and inat.get("taxon_id"):
                    profile.inaturalist_id = inat["taxon_id"]
                    profile.inaturalist_url = f"https://www.inaturalist.org/taxa/{profile.inaturalist_id}"
                    if not profile.scientific_name and inat.get("scientific_name"):
                        profile.scientific_name = inat["scientific_name"]
                        sci_name = profile.scientific_name
                    logger.info("iNaturalist taxon ID backfilled for %s: %s",
                                common_name, profile.inaturalist_id)
                else:
                    logger.warning("iNaturalist taxon ID lookup found nothing for %s (query=%r) — "
                                   "geomodel will stay unavailable until this succeeds",
                                   common_name, sci_name or common_name)

        # ── Step 3: eBird taxonomy + species code ─────────────────────────────
        # Kept in maps_only mode too — Macaulay and S&T both key off
        # ebird_species_code, same reasoning as Step 0 above.
        api_key = _get_ebird_api_key(self.db)
        if (not profile.ebird_species_code or force) and api_key:
            ebird = self._fetch_ebird_taxonomy(sci_name or common_name, api_key)
            if ebird:
                profile.ebird_species_code = ebird.get("speciesCode")
                profile.ebird_data = ebird
                if not profile.order_name:
                    profile.order_name = ebird.get("order")
                if not profile.family_name:
                    profile.family_name = ebird.get("familyComName")
                logger.info("eBird code: %s for %s", profile.ebird_species_code, common_name)

        # ── Range map (primary tab) — always attempted in maps_only mode;
        # otherwise only if not already resolved or force is set, matching
        # the original code's guard (calling _resolve_range_map unconditionally
        # would re-run AAB's Playwright session on every bird on every routine
        # enrichment pass, not just on a refresh).
        map_force = force or maps_only
        if maps_only or not profile.range_map_url or force:
            self._resolve_range_map(profile, range_map_wiki, map_force)

        if maps_only:
            profile.last_enriched = datetime.utcnow()
            self.db.add(profile)
            self.db.commit()
            logger.info("Range map refresh complete: %s", common_name)
            return

        # ── Step 4: iNaturalist sounds ────────────────────────────────────────
        if len(profile.call_media or []) < 8 or force:
            calls = self._fetch_inaturalist_sounds(sci_name or common_name, common_name)
            if calls:
                profile.call_media = calls

        # ── Step 5: Seasonal frequency (Merlin-style eBird bar chart) ─────────
        existing_freq = profile.monthly_frequency or []
        freq_empty = not existing_freq or all(v == 0 for v in existing_freq)
        if freq_empty or force:
            self._fetch_and_set_monthly_frequency(profile, api_key)

        # ── Step 6: Validate stored range map ─────────────────────────────────
        if profile.range_map_url:
            self._validate_range_map(profile)

        profile.enrichment_complete = True
        profile.last_enriched = datetime.utcnow()
        self.db.add(profile)
        self.db.commit()
        logger.info("Enrichment complete: %s", common_name)


    # ── Range map resolution ──────────────────────────────────────────────────

    def _resolve_range_map(
        self,
        profile: BirdProfile,
        wiki_map_url: Optional[str],
        force: bool,
    ) -> None:
        """
        Try range map sources in priority order, save result to profile.
        Priority: All About Birds (Playwright) → Macaulay Library (Cornell CDN) → Wikipedia SVG

        Each of the first two steps is individually gated by
        self._range_map_sources (the same per-source settings dict
        Settings' checkboxes write to) — confirmed via a previously
        live bug that this function only checked the single global
        range_maps_enabled flag, never the granular per-source dict at
        all, meaning unchecking "All About Birds" in Settings had NO
        EFFECT on this code path specifically (it kept running anyway).
        Fixed by checking sources.get("aab", True) / sources.get(
        "macaulay", True) before each respective attempt, defaulting to
        True so existing configs that never set these keys keep their
        current (working) behavior.
        """
        if not self._range_maps_enabled:
            logger.debug("Range maps disabled — skipping fetch for %s", getattr(profile, 'common_name', '?'))
            return

        common_name = profile.common_name
        sources = self._range_map_sources or {}

        # 1. All About Birds — highest-quality illustrated range maps (uses Playwright)
        primary_resolved = False
        if sources.get("aab", True):
            try:
                aab_url, aab_legend = self._fetch_aab_range_map(common_name)
                if aab_legend:
                    profile.aab_legend = aab_legend
                if aab_url:
                    local = self._download_range_map(aab_url, common_name)
                    if local:
                        profile.range_map_url = f"file://{local}"
                        profile.range_map_source = "aab"
                        logger.info("Range map: All About Birds for %s", common_name)
                        primary_resolved = True
                    else:
                        # Download failed (often a 404 — the captured URL is frequently
                        # tied to the Playwright session via Cloudflare bot-protection
                        # cookies/headers that a plain browser <img> request won't have,
                        # unlike the Wikipedia case below where storing the raw URL as
                        # a fallback is deliberate). Don't commit to a URL we already
                        # know is broken — fall through to the next source instead.
                        logger.debug("AAB image URL for %s failed to download — falling back", common_name)
            except Exception as e:
                logger.debug("AAB range map error: %s", e)
        else:
            logger.debug("AAB disabled in range_map_sources — skipping for %s", common_name)

        if not primary_resolved and sources.get("macaulay", True):
            # 2. Macaulay Library / Cornell CDN fallback — now independently
            # gated (previously only ever reachable as AAB's invisible
            # fallback, with no way to disable it on its own or confirm it
            # was the active source from the Settings UI).
            if profile.ebird_species_code:
                ml_url = self._fetch_ml_range_map(profile.ebird_species_code)
                if ml_url:
                    local = self._download_range_map(ml_url, common_name)
                    if local:
                        profile.range_map_url = f"file://{local}"
                        profile.range_map_source = "macaulay"
                        logger.info("Range map: Macaulay Library for %s", common_name)
                        primary_resolved = True
                    else:
                        logger.debug("Macaulay Library image URL for %s failed to download — falling back", common_name)

        if not primary_resolved:
            # 3. Wikipedia SVG
            wiki_url = wiki_map_url
            if not wiki_url:
                try:
                    wiki_url = self._fetch_wikipedia_range_map(common_name, profile.scientific_name or "")
                except Exception as e:
                    logger.debug("Wikipedia range map error: %s", e)

            if wiki_url:
                # Try to download; if blocked (Wikimedia CDN blocks server-side),
                # store the URL directly and redirect browser at serve-time
                local = None
                try:
                    local = self._download_range_map(wiki_url, common_name)
                except Exception:
                    pass
                profile.range_map_url = f"file://{local}" if local else wiki_url
                profile.range_map_source = "wikipedia"
                logger.info("Range map: Wikipedia (%s) for %s",
                            "local" if local else "redirect", common_name)
                primary_resolved = True

        if not primary_resolved:
            logger.info("No range map found for %s", common_name)

        # ── Eager pre-fetch: BirdLife + geomodel ────────────────────────────
        # Both of these were previously lazy-only — never touched until the
        # person opened a bird's profile page and clicked that specific map
        # tab. That meant the very first view always had to wait for a fresh
        # Playwright capture (BirdLife) or a fresh render (geomodel), and the
        # BirdLife screenshot had no chance to be checked/retried in advance.
        # Pre-fetching here, during the same enrichment pass that already
        # runs on "Refresh All Data" and on new-species detection, means
        # both are already cached and ready by the time anyone looks.
        # Respects each source's individual enabled-toggle in Settings, and
        # skips species that were already pre-fetched recently so a repeated
        # "Refresh All Data" doesn't re-run Playwright for every bird every
        # time — only profiles that have never been pre-fetched, or whose
        # cached map file is now missing, are re-captured.
        self._prefetch_secondary_range_maps(profile, force)

    def _prefetch_secondary_range_maps(self, profile: BirdProfile, force: bool) -> None:
        """
        Eagerly fetch + cache the BirdLife, geomodel, eBird Status & Trends,
        and GBIF range maps (and the BirdLife per-species legend) during
        enrichment, instead of waiting for the person to open the profile
        page and click that map's tab.
        Best-effort: failures here never block the rest of enrichment, since
        the primary range_map_url resolved above is what gates
        enrichment_complete. None of the four sources below ever overwrite
        the primary range_map_url/range_map_source — they only pre-cache
        each tab's own file so it's instant when clicked, matching the
        existing BirdLife/geomodel behavior exactly.
        """
        import os as _os
        from datetime import datetime as _dt, timedelta as _td

        common_name = profile.common_name
        sources = self._range_map_sources or {}

        # Skip entirely if pre-fetched recently and not forced — avoids
        # spending a Playwright session on every bird on every
        # "Refresh All Data" click when nothing has changed.
        if not force and profile.range_maps_prefetched_at:
            age = _dt.utcnow() - profile.range_maps_prefetched_at
            if age < _td(days=self.ENRICH_INTERVAL_DAYS):
                logger.debug("Secondary range maps for %s pre-fetched %s ago — skipping",
                            common_name, age)
                return

        from ..config import settings as cfg
        # Use the exact same directory convention as the on-demand S&T/GBIF
        # endpoint (_fetch_range_map_bg in api/birds.py) and the existing
        # AAB/Macaulay/Wikipedia downloader (_download_range_map below) —
        # media_dir/lowercase_safe_name/, no "birds/" prefix. Confirmed by
        # direct test that _species_media_dir (used elsewhere for photos/
        # calls) does NOT lowercase and so does NOT match — using
        # the identical regex inline instead, the same one _download_range_map
        # uses, rather than introducing a fourth helper or reusing one that
        # silently produces a different path.
        # This was a log-confirmed bug: the previous convention here
        # (media_dir/birds/Title_Case_Name/) meant the bulk recency check
        # below could never see a file the on-demand S&T tab had just
        # written (different directory entirely), so every bulk refresh
        # re-fetched S&T from scratch for any bird whose tab had ever been
        # clicked manually — the opposite of the intended "skip if already
        # fresh" behavior.
        safe_name = _re.sub(r"[^a-zA-Z0-9_-]", "_", common_name.lower())
        species_dir = _os.path.join(cfg.media_dir, safe_name)
        _os.makedirs(species_dir, exist_ok=True)

        any_attempted = False

        # BirdLife — only if that source is enabled (default True if unset,
        # matching the frontend's existing default-on behavior for sources
        # not present in a not-yet-saved settings row).
        if sources.get("birdlife", True) and profile.scientific_name:
            any_attempted = True
            png_path = _os.path.join(species_dir, "range_map_birdlife.png")
            need_fetch = force or not (_os.path.exists(png_path) and _os.path.getsize(png_path) > 5_000)
            if need_fetch:
                try:
                    result = self.fetch_birdlife_range_map_full(
                        common_name=common_name,
                        scientific_name=profile.scientific_name,
                        output_path=png_path,
                    )
                    if result.get("ok"):
                        if result.get("legend"):
                            profile.birdlife_legend = result["legend"]
                        logger.info("Pre-fetched BirdLife map for %s", common_name)
                    else:
                        logger.info("BirdLife pre-fetch for %s did not succeed (%s) — "
                                    "will retry on next enrichment pass",
                                    common_name, result.get("error"))
                except Exception as e:
                    logger.debug("BirdLife pre-fetch error for %s: %s", common_name, e)

        # Geomodel — only if enabled and we have an iNaturalist taxon ID to render from
        if sources.get("geomodel", True) and profile.inaturalist_id:
            any_attempted = True
            png_path = _os.path.join(species_dir, "range_map_geomodel.png")
            need_fetch = force or not (_os.path.exists(png_path) and _os.path.getsize(png_path) > 1_000)
            if need_fetch:
                try:
                    from .geomodel_service import render_range_map, get_status
                    status = get_status(cfg.data_dir)
                    if status.get("ready"):
                        ok = render_range_map(
                            taxon_id=profile.inaturalist_id,
                            data_dir=cfg.data_dir,
                            output_path=png_path,
                            common_name=common_name,
                        )
                        if ok:
                            logger.info("Pre-fetched geomodel map for %s", common_name)
                        else:
                            logger.debug("Geomodel pre-fetch for %s did not succeed", common_name)
                    else:
                        logger.debug("Geomodel pre-fetch skipped for %s — geopackages not downloaded", common_name)
                except Exception as e:
                    logger.debug("Geomodel pre-fetch error for %s: %s", common_name, e)

        # eBird Status & Trends — disabled by default (matches the Settings
        # checkbox, which defaults this one specific source to False since
        # it's marked "(testing)" there and needs its own separate S&T key).
        # Confirmed via a code trace this session: before this fix,
        # S&T was ONLY ever reachable via the single-profile
        # POST /{id}/range-map/fetch?source=ebird_st endpoint (a person
        # manually clicking the S&T tab) — "Refresh All Data" never touched
        # it at all, despite enrich-all otherwise covering every other
        # source. Same applies to GBIF below.
        if sources.get("ebird_st", False) and profile.ebird_species_code:
            any_attempted = True
            png_path = _os.path.join(species_dir, "range_map_ebird_st.png")
            need_fetch = force or not (_os.path.exists(png_path) and _os.path.getsize(png_path) > 1_000)
            if need_fetch:
                try:
                    from ..models import AppSettings
                    s = self.db.query(AppSettings).filter(AppSettings.id == 1).first()
                    api_key = (s.ebird_st_api_key if s else None) or getattr(cfg, "ebird_st_api_key", None)
                    if not api_key:
                        logger.debug("eBird S&T pre-fetch skipped for %s — no S&T API key configured", common_name)
                    else:
                        from .range_map_service import fetch_ebird_st_map
                        ok = fetch_ebird_st_map(profile.ebird_species_code, api_key, png_path)
                        if ok:
                            logger.info("Pre-fetched eBird S&T map for %s", common_name)
                        else:
                            logger.debug("eBird S&T pre-fetch for %s did not succeed", common_name)
                except Exception as e:
                    logger.debug("eBird S&T pre-fetch error for %s: %s", common_name, e)

        # GBIF — not a Settings-toggleable source (no checkbox exists for it
        # there, matching its existing unguarded behavior at the per-profile
        # fetch endpoint), so always attempted; no API key required.
        if profile.scientific_name:
            any_attempted = True
            png_path = _os.path.join(species_dir, "range_map_gbif.png")
            need_fetch = force or not (_os.path.exists(png_path) and _os.path.getsize(png_path) > 1_000)
            if need_fetch:
                try:
                    from .range_map_service import fetch_gbif_map
                    ok = fetch_gbif_map(profile.scientific_name, common_name, png_path)
                    if ok:
                        logger.info("Pre-fetched GBIF map for %s", common_name)
                    else:
                        logger.debug("GBIF pre-fetch for %s did not succeed", common_name)
                except Exception as e:
                    logger.debug("GBIF pre-fetch error for %s: %s", common_name, e)

        if any_attempted:
            profile.range_maps_prefetched_at = _dt.utcnow()

    def _fetch_ml_range_map(self, ebird_code: str) -> Optional[str]:
        """
        Disabled as of 0.5.6.i — both fetch patterns this used to try are
        confirmed dead, tested directly against the live endpoints:
          - Direct CDN (/api/v1/asset/range/{code}/{size}): 422 for every
            size now.
          - Catalog search (search.macaulaylibrary.org/catalog.json): 200,
            but the body is an Anubis bot-challenge HTML page, not JSON —
            Cornell added bot-protection since this was built, and Anubis
            is specifically designed to resist exactly this kind of
            automated scraping.
        Neither is a Chirp bug and neither is fixable by patching this
        function — kept as a stub (rather than deleted outright) so
        profile.range_map_source == "macaulay" stays meaningful for
        already-cached historical data and the resolution order in
        _resolve_range_map() below doesn't need touching: this always
        returning None already falls through to Wikipedia SVG correctly.
        Real network calls removed entirely so this never wastes a round
        trip or logs a confusing failure for something that can't succeed.
        """
        return None

    def _download_range_map(self, url: str, common_name: str) -> Optional[str]:
        """Download range map image to local media dir. Returns local path or None."""
        safe = _re.sub(r"[^a-zA-Z0-9_-]", "_", common_name.lower())
        save_dir = os.path.join(settings.media_dir, safe)
        os.makedirs(save_dir, exist_ok=True)

        # Choose extension based on URL
        if ".svg" in url.lower():
            save_path = os.path.join(save_dir, "range_map.svg")
        else:
            save_path = os.path.join(save_dir, "range_map.png")

        # For Wikipedia/Wikimedia SVG URLs — try PNG thumbnail first
        thumb_url = url
        if ".svg" in url.lower() and "wikimedia.org" in url:
            # Wikipedia Commons thumb URL pattern:
            # Original: https://upload.wikimedia.org/wikipedia/commons/9/9d/Name.svg
            # Thumb: https://upload.wikimedia.org/wikipedia/commons/thumb/9/9d/Name.svg/800px-Name.svg.png
            m = _re.search(r"/commons/(.+\.svg)$", url)
            if m:
                commons_path = m.group(1) # e.g. "9/9d/Dendroica_virens_map.svg"
                filename = commons_path.split("/")[-1]
                thumb_url = (
                    f"https://upload.wikimedia.org/wikipedia/commons/thumb/"
                    f"{commons_path}/800px-{filename}.png"
                )

        wiki_headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Chirp/1.0)",
            "Referer": "https://en.wikipedia.org/",
        }

        # Try thumbnail PNG first (smaller, faster), then original SVG
        for try_url in ([thumb_url, url] if thumb_url != url else [url]):
            try:
                _throttle()
                dest = save_path if ".svg" in try_url else save_path.replace(".svg", ".png")

                r = httpx.get(try_url, headers=wiki_headers if "wikimedia" in try_url else {"User-Agent": UA},
                              timeout=25, follow_redirects=True)
                if r.status_code == 200 and len(r.content) > 500:
                    ct = r.headers.get("content-type", "")
                    if "svg" in ct:
                        dest = os.path.join(save_dir, "range_map.svg")
                    elif "png" in ct or "jpeg" in ct:
                        dest = os.path.join(save_dir, "range_map.png")

                    with open(dest, "wb") as f:
                        f.write(r.content)
                    logger.info("Range map saved: %s (%d KB) → %s",
                                common_name, len(r.content) // 1024, dest)
                    return dest
                elif r.status_code == 403:
                    logger.debug("Range map blocked (403) from %s for %s", try_url[:60], common_name)
            except Exception as e:
                logger.debug("Range map download error %s: %s", try_url[:60], e)

        return None

    def _validate_range_map(self, profile: BirdProfile) -> None:
        """Verify stored range map is usable; clear if missing/tiny."""
        url = profile.range_map_url or ""
        if url.startswith("file://"):
            path = url[7:]
            if not os.path.exists(path):
                logger.warning("Range map missing on disk for %s: %s", profile.common_name, path)
                profile.range_map_url = None
                profile.enrichment_complete = False
                return
            size = os.path.getsize(path)
            if size < 500:
                logger.warning("Range map too small (%d bytes) for %s", size, profile.common_name)
                os.remove(path)
                profile.range_map_url = None
                profile.enrichment_complete = False
        elif url.startswith("http"):
            logger.debug("Range map remote URL for %s: %s", profile.common_name, url[:80])

    # ── Seasonal frequency ────────────────────────────────────────────────────

    def _fetch_and_set_monthly_frequency(
        self, profile: BirdProfile, api_key: Optional[str]
    ) -> None:
        """
        Fetch 12-month seasonal frequency using eBird bar chart data
        (same source as Merlin frequency bars). Falls back to iNaturalist.
        """
        common_name = profile.common_name

        # Method 1: eBird bar chart (true 12-month checklist frequency)
        if api_key and profile.ebird_species_code:
            monthly = self._fetch_ebird_bar_chart_for_species(
                profile.ebird_species_code, api_key
            )
            if monthly and any(v > 0 for v in monthly):
                profile.monthly_frequency = monthly
                logger.info("Seasonal: eBird bar chart for %s → peak=%.2f",
                            common_name, max(monthly))
                return

        # Method 2: iNaturalist monthly histogram (global, not regional)
        if profile.inaturalist_id:
            monthly = self._fetch_inaturalist_monthly(profile.inaturalist_id)
            if monthly and any(v > 0 for v in monthly):
                profile.monthly_frequency = monthly
                logger.info("Seasonal: iNaturalist histogram for %s", common_name)
                return

        logger.info("Seasonal: no data available for %s", common_name)

    def _fetch_ebird_bar_chart_for_species(
        self, ebird_code: str, api_key: str
    ) -> Optional[List[float]]:
        """
        Get 12-month bar chart frequency for ONE species using eBird bar chart API.

        Strategy: Look up location from DB settings → get region code →
        fetch full regional bar chart → extract this species' row.

        Caches the full region bar chart in memory during enrichment batch
        to avoid 200+ redundant API calls.
        """
        # Get location from DB settings
        try:
            from ..models import AppSettings
            s = self.db.query(AppSettings).filter(AppSettings.id == 1).first()
            lat = s.latitude if s else None
            lon = s.longitude if s else None
        except Exception:
            lat, lon = None, None

        if lat is None or lon is None:
            logger.debug("No location set — skipping bar chart for %s", ebird_code)
            return None

        # Use module-level cache to avoid re-fetching for every species
        from ..services.ebird_service import (
            get_region_code_from_latlon,
            fetch_bar_chart_data,
        )
        cache_key = f"_bar_chart_cache_{lat:.2f}_{lon:.2f}"
        bar_chart = getattr(BirdEnricher, cache_key, None)

        if bar_chart is None:
            region = get_region_code_from_latlon(lat, lon)
            if not region:
                return None
            bar_chart = fetch_bar_chart_data(region, api_key)
            setattr(BirdEnricher, cache_key, bar_chart)
            logger.info("Bar chart cached for region %s (%d species)", region, len(bar_chart))

        # Look up this species in the cached data
        monthly = bar_chart.get(ebird_code)
        if not monthly:
            # Also try common name lookup
            try:
                profile = self.db.query(BirdProfile).filter(
                    BirdProfile.ebird_species_code == ebird_code
                ).first()
                if profile:
                    monthly = bar_chart.get(profile.common_name)
            except Exception:
                pass

        return monthly

    def _fetch_inaturalist_monthly(self, taxon_id: int) -> Optional[List[float]]:
        """Fetch monthly observation frequency from iNaturalist histogram."""
        try:
            _throttle()
            r = httpx.get(
                "https://api.inaturalist.org/v1/observations/histogram",
                params={
                    "taxon_id": taxon_id,
                    "quality_grade": "research",
                    "verifiable": "true",
                    "date_field": "observed",
                    "interval": "month_of_year",
                },
                headers={"User-Agent": UA},
                timeout=15,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            results = data.get("results", {})
            # iNat response: { "results": { "month_of_year": { "1": N, ... } } }
            monthly_data = results.get("month_of_year", results)
            raw = [float(monthly_data.get(str(m), 0)) for m in range(1, 13)]
            peak = max(raw) or 1.0
            return [round(v / peak, 3) for v in raw]
        except Exception as e:
            logger.debug("iNat monthly histogram error for taxon %s: %s", taxon_id, e)
            return None

    # ── Wikipedia full article ────────────────────────────────────────────────

    def _fetch_wikipedia_full(
        self, common_name: str, scientific_name: Optional[str]
    ) -> Tuple[List[Dict], str, Optional[str]]:
        QUALIFIERS = ("Northern", "Southern", "Eastern", "Western", "American",
                      "Common", "Eurasian", "European", "Greater", "Lesser", "Little")
        stripped = common_name
        for q in QUALIFIERS:
            if common_name.startswith(q + " "):
                stripped = common_name[len(q) + 1:]
                break

        def wiki_title(name: str) -> str:
            if not name:
                return ""
            parts = name.split()
            if len(parts) == 1:
                return parts[0].replace(" ", "_")
            return (parts[0] + " " + " ".join(p.lower() for p in parts[1:])).replace(" ", "_")

        for title_query in filter(None, [
            wiki_title(common_name),
            wiki_title(stripped) if stripped != common_name else None,
            (scientific_name or "").replace(" ", "_"),
        ]):
            sections = self._fetch_wikipedia_action_api(title_query)
            if sections:
                wiki_url = f"https://en.wikipedia.org/wiki/{title_query.replace('_', ' ')}"
                range_map = None
                try:
                    range_map = self._fetch_wikipedia_range_map(common_name, scientific_name or "")
                except Exception as e:
                    logger.debug("Range map fetch failed: %s", e)
                return sections, wiki_url, range_map

        return [], "", None

    def _fetch_wikipedia_action_api(self, title: str) -> List[Dict]:
        try:
            _throttle()
            r = httpx.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "prop": "extracts",
                    "titles": title.replace("_", " "),
                    "format": "json",
                    "explaintext": "1",
                    "exsectionformat": "wiki",
                    "formatversion": "2",
                    # Same fix as _fetch_wikipedia_range_map below: without
                    # this, querying a title that's a Wikipedia
                    # redirect (common for species with regional/historical
                    # common-name differences, the same class of mismatch
                    # already confirmed for BirdLife's naming) returns
                    # nothing useful instead of following through to the
                    # article.
                    "redirects": "1",
                },
                headers={"User-Agent": WIKIPEDIA_UA},
                timeout=15,
                follow_redirects=True,
            )
            if r.status_code != 200:
                return []
            data = r.json()
            pages = data.get("query", {}).get("pages", [])
            if not pages or pages[0].get("missing"):
                return []
            extract = pages[0].get("extract", "").strip()
            if len(extract) < 100:
                return []

            import re as _local_re
            sections = []
            parts = _local_re.split(r"\n==+\s*([^=]+?)\s*==+\n", extract)
            if parts[0].strip() and len(parts[0]) > 50:
                sections.append({"section": "Overview", "text": parts[0].strip()})
            for i in range(1, len(parts) - 1, 2):
                sec_title = parts[i].strip()
                sec_text = parts[i + 1].strip() if i + 1 < len(parts) else ""
                if not sec_text or len(sec_text) < 50:
                    continue
                title_lower = sec_title.lower()
                if any(excl in title_lower for excl in BIRD_SECTIONS_EXCLUDE):
                    continue
                if any(incl in title_lower for incl in BIRD_SECTIONS_INCLUDE):
                    sections.append({"section": sec_title, "text": sec_text})
            return sections
        except Exception as e:
            logger.debug("MediaWiki action API error for %s: %s", title, e)
            return []

    @staticmethod
    def _aab_slugs(common_name: str) -> list:
        """
        AAB URL slug candidates, in order of confidence. A genuine gap
        found while building the new overview/facts fetcher below and
        verified live against the site (not assumed): AAB's slugs
        PRESERVE hyphens in the common name itself (confirmed via
        Gray-cheeked_Thrush and Red-bellied_Woodpecker both returning
        200 pages) — the two variants this method already had before never
        tried that, only replacing hyphens with underscores or lowercasing
        everything, neither of which matches the site for any
        hyphenated common name. Hyphenated names are common (most
        woodpeckers, several chickadees/kinglets/warblers), so this wasn't
        an edge case — it was a silent miss for a meaningful slice of
        species that the range-map fetcher below has been quietly retrying
        with a wrong-order fallback for. Now tried first, since it's the
        one confirmed correct.
        """
        base = common_name.strip().replace(" ", "_").replace("'", "")
        return [
            base, # 'Red-bellied_Woodpecker' — confirmed correct
            base.replace("-", "_"), # 'Red_bellied_Woodpecker' — old slug_us
            common_name.strip().replace(" ", "-").replace("'", "").lower(), # 'red-bellied-woodpecker' — old slug_hy
        ]

    def _fetch_aab_range_map(self, common_name: str) -> Tuple[Optional[str], Optional[list]]:
        """
        Fetch range map image + per-species legend from All About Birds.
        Uses Playwright (headless Chromium) to bypass Cloudflare and intercept
        the image URL that loads on the maps-range page.
        Returns (image_url, legend) — legend is None if extraction failed,
        which is distinct from "page has no legend for this species" (handled
        inside _playwright_aab_image, which returns [] in that case).
        """
        for slug in self._aab_slugs(common_name):
            page_url = f"https://www.allaboutbirds.org/guide/{slug}/maps-range"
            try:
                url, legend = self._playwright_aab_image(page_url, common_name)
                if url:
                    return url, legend
            except Exception as e:
                # Was logger.debug — invisible unless debug logging is
                # on. Promoted to warning: a missing/broken Chromium
                # runtime (the Dockerfile's `playwright install-deps`
                # step swallows its own failure with `|| true`) fails
                # exactly this way — fast, and silently, without this.
                logger.warning("AAB Playwright failed for %s (%s): %s", common_name, slug, e)
        return None, None

    def _playwright_aab_image(self, page_url: str, common_name: str) -> Tuple[Optional[str], Optional[list]]:
        """
        Navigate to AAB maps-range page and capture the range map image URL
        AND the per-species legend.
        Strategy: wait for the page to fully render, then collect ALL loaded images.
        The range map is a lazy-loaded asset that appears AFTER the hero photo,
        so we wait for networkidle and prefer the LAST seen high-res image.
        We also try to directly query the map container element for its img src.

        Legend: AAB/Birds of the World pages render a per-species legend
        strip (e.g. "Year-round Breeding Migration Nonbreeding" for Arctic
        Tern) listing only the categories that apply to that species
        — not every species shows all four. Read directly from the DOM,
        same approach as BirdLife's _extract_birdlife_legend, since it's
        exact rather than an approximation. AAB's fixed 4-color convention
        (orange=Breeding, blue=Nonbreeding, green=Year-round, yellow=Migration)
        is well-documented and stable, so colors are assigned from that known
        mapping by label rather than read from computed CSS — AAB's legend
        text isn't always inside an element with the swatch as a sibling, so
        a DOM color read is less reliable here than it was for BirdLife.
        Returns (image_url, legend); legend is [] (not None) if the page
        loaded fine but no legend text was found, vs. None on a hard failure.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("AAB range map: Playwright not importable — skipping (pip install may have failed in this container)")
            return None, None

        # Capture responses so we only get images that loaded
        captured: list[tuple[float, str]] = [] # (timestamp, url)
        import time as _time

        def _on_response(resp):
            url = resp.url
            ct = resp.headers.get("content-type", "")
            if ("allaboutbirds.org/guide/assets/photo/" in url
                    and ("image/" in ct or url.endswith((".jpg", ".png")))
                    and not url.endswith((".gif",))):
                captured.append((_time.monotonic(), url))

        legend: Optional[list] = None
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 900},
                )
                page = ctx.new_page()
                page.on("response", _on_response)

                try:
                    page.goto(page_url, timeout=25_000, wait_until="domcontentloaded")
                    # Scroll down to trigger lazy loading of the map section
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    # Wait for all network activity to settle (map tiles, images)
                    page.wait_for_load_state("networkidle", timeout=12_000)
                except Exception:
                    pass

                legend = self._extract_aab_legend(page)
                if legend:
                    logger.info("AAB legend for %s: %d entries (%s)",
                                common_name, len(legend), [l["label"] for l in legend])
                else:
                    logger.info("AAB legend for %s: none extracted", common_name)

                # Directly probe the map section for an img element
                map_src = None
                for map_sel in [
                    ".sp-range-map img",
                    "[class*='range'] img",
                    "[class*='map'] img[src*='assets/photo']",
                    "#range-map img",
                    "figure img[src*='assets/photo']",
                ]:
                    try:
                        srcs = page.eval_on_selector_all(
                            map_sel, "els => els.map(e => e.currentSrc || e.src)"
                        )
                        if srcs:
                            map_src = [s for s in srcs if "allaboutbirds.org/guide/assets/photo/" in (s or "")]
                            if map_src:
                                break
                    except Exception:
                        pass

                browser.close()

            # If we got a direct hit from the map container, use it
            if map_src:
                best = sorted(map_src, key=lambda u: (
                    "1280" in u, "960" in u, "480" in u
                ))[-1]
                logger.info("AAB range map (direct) for %s: %s", common_name, best[:120])
                return best, legend

            if not captured:
                logger.debug("AAB Playwright: no images captured for %s", common_name)
                return None, legend

            # Sort by load time — range map loads AFTER hero photo
            # Sort descending (latest first), prefer highest resolution
            captured_sorted = sorted(captured, key=lambda x: x[0], reverse=True)
            by_base: dict[str, str] = {}
            for _t, url in captured_sorted:
                base = url.rsplit("-", 1)[0]
                if base not in by_base: # keep latest (range map) not earliest (hero)
                    by_base[base] = url

            all_urls = list(by_base.values())
            for size in ("1280px", "960px", "480px"):
                for u in all_urls:
                    if size in u:
                        logger.info("AAB range map (intercepted) for %s: %s", common_name, u[:120])
                        return u, legend
            return (all_urls[0] if all_urls else None), legend

        except Exception as e:
            logger.warning("Playwright AAB session error for %s: %s", common_name, e)
            return None, legend

    @staticmethod
    def _extract_aab_legend(page) -> list:
        """
        Read the per-species legend from an AAB/Birds of the World page.
        The legend renders as a short run of category labels right above the
        map (e.g. "Year-roundBreedingMigrationNonbreeding" for Arctic Tern
        and European Starling alike, concatenated with no separator in the
        raw text) — only the categories that apply to that species
        are present, so a year-round resident might show only "Year-round"
        while a migratory species shows all four.

        Color strategy, in order:
        1. Try to read each matched label's own computed text/background
           color directly from the DOM if the legend renders as separate
           colored spans/chips (one per category word) rather than one plain
           text run — exact when it works.
        2. Fall back to a hardcoded palette only if no color could be
           read for a given label. That palette was previously wrong: it had
           breeding=orange and migration=yellow-green, which contradicts
           AAB/Cornell's own documented, decades-old mnemonic — confirmed via
           Cornell-affiliated Merlin training material and corroborated by
           Sibley Guides' identical convention: Breeding=red/orange ("hot" —
           summer), Migration=yellow (between red and blue), Non-breeding=
           blue ("cool" — winter), Year-round=purple (the red+blue blend, not
           its own flat color). Corrected to match that documented convention.

        Searches the page's FULL body text rather than scoping to a
        candidate container element first — a direct fetch of a
        /maps-range page confirmed the legend text sits in a plain element
        with no "legend"/"map"/"key" anywhere in its class name (AAB's
        Cornell Lab stack very likely uses framework-generated class names,
        the same root cause that affected BirdLife's selectors).

        Returns [] (not None) if the page loaded but no legend text matched
        any known category — an outcome, not a failure, since some
        species pages may render the legend differently or not at all.
        """
        KNOWN_LABELS = {
            "year-round": {"fallback_color": "rgb(147,51,234)", "order": 0}, # purple (red+blue blend)
            "breeding": {"fallback_color": "rgb(239,68,68)", "order": 1}, # red/orange-red ("hot")
            "migration": {"fallback_color": "rgb(250,204,21)", "order": 2}, # yellow (between red & blue)
            "nonbreeding": {"fallback_color": "rgb(59,130,246)", "order": 3}, # blue ("cool")
            "non-breeding": {"fallback_color": "rgb(59,130,246)", "order": 3},
        }
        DISPLAY_LABEL_BY_ORDER = {
            0: "Year-round",
            1: "Breeding",
            2: "Migration",
            3: "Non-breeding",
        }

        # Strategy 1: scan small leaf-ish elements directly for the
        # concatenated legend string. AAB's legend renders as one run of
        # category words with no separator/whitespace between them (e.g.
        # "Year-roundBreedingMigrationNonbreeding"), so rather than guessing
        # a container we look at every element whose OWN short text (not a
        # huge container's combined text) contains at least one known label
        # as a substring, then check whether the SAME short text contains
        # the others too — since they're concatenated, a match on one nearly
        # always means the whole run is in that exact element. Also try to
        # read each individual category word's own color if the
        # legend renders as separate colored spans/chips rather than one
        # plain text node.
        js = r"""(labels) => {
            const allEls = document.querySelectorAll('body *');
            for (const el of allEls) {
                const text = (el.textContent || '').trim();
                if (!text || text.length > 80) continue;
                const lowered = text.toLowerCase();
                const matchCount = labels.filter(l => lowered.includes(l)).length;
                if (matchCount > 0) {
                    const childHasSame = Array.from(el.children).some(c => {
                        const ct = (c.textContent || '').trim().toLowerCase();
                        return labels.filter(l => ct.includes(l)).length === matchCount;
                    });
                    if (childHasSame) continue;

                    const perLabelColors = {};
                    // Sort labels longest-first before matching: "breeding"
                    // is itself a substring of "nonbreeding"/"non-breeding",
                    // so without this a child whose text is "Nonbreeding"
                    // could incorrectly match "breeding" first (whichever
                    // label happened to come first in the array), assigning
                    // that swatch's color to the WRONG category. Checking
                    // the longest candidates first ensures "nonbreeding" is
                    // matched as itself, not as a fragment of "breeding".
                    const sortedLabels = [...labels].sort((a, b) => b.length - a.length);
                    for (const child of el.children) {
                        const ct = (child.textContent || '').trim().toLowerCase();
                        const matched = sortedLabels.find(l => ct === l || ct.includes(l));
                        if (matched) {
                            const cs = window.getComputedStyle(child);
                            // Reject near-greyscale colors outright — a
                            // category swatch color (red, blue, yellow,
                            // purple) has a meaningfully different max and
                            // min RGB channel; plain inherited body text
                            // (often a mid-grey like rgb(110,110,110)) does
                            // not, and "not pure black" alone (the original
                            // check) isn't enough to tell the two apart —
                            // that's exactly what let an inherited default
                            // text color through as if it were a
                            // per-label color before this fix.
                            const isVivid = (rgbStr) => {
                                const m = rgbStr && rgbStr.match(/\d+/g);
                                if (!m || m.length < 3) return false;
                                const [r, g, b] = m.map(Number);
                                return (Math.max(r, g, b) - Math.min(r, g, b)) > 25;
                            };
                            let color = null;
                            if (cs.color && isVivid(cs.color)) color = cs.color;
                            else if (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)'
                                     && isVivid(cs.backgroundColor)) color = cs.backgroundColor;
                            if (color) perLabelColors[matched] = color;
                        }
                    }
                    // If every matched label resolved to the EXACT same
                    // color, that's a strong signal it's one shared
                    // inherited value rather than per-category
                    // styling (genuine swatches would differ) — discard
                    // the whole result so the caller falls back to the
                    // documented-convention palette instead of displaying
                    // four identical, wrong-looking dots.
                    const distinctColors = new Set(Object.values(perLabelColors));
                    if (Object.keys(perLabelColors).length > 1 && distinctColors.size === 1) {
                        for (const k of Object.keys(perLabelColors)) delete perLabelColors[k];
                    }
                    return { text: lowered, perLabelColors };
                }
            }
            return null;
        }"""
        try:
            result = page.evaluate(js, list(KNOWN_LABELS.keys()))
        except Exception as e:
            logger.debug("AAB: legend text-scan error: %s", e)
            result = None

        if result and result.get("text"):
            matched_text = result["text"]
            per_label_colors = result.get("perLabelColors") or {}
            found = [
                (KNOWN_LABELS[lbl]["order"],
                 per_label_colors.get(lbl) or KNOWN_LABELS[lbl]["fallback_color"],
                 bool(per_label_colors.get(lbl)))
                for lbl in KNOWN_LABELS
                if lbl in matched_text
            ]
            if found:
                by_order = {}
                for order, color, _is_real in found:
                    by_order.setdefault(order, color)
                legend = [
                    {"color": color, "label": DISPLAY_LABEL_BY_ORDER[order]}
                    for order, color in sorted(by_order.items())
                ]
                n_real = sum(1 for _, _, is_real in found if is_real)
                logger.info("AAB: extracted %d legend entries via body text scan "
                            "(%d with DOM colors, %d using documented-convention fallback): %s",
                            len(legend), n_real, len(legend) - n_real, [l["label"] for l in legend])
                return legend

        # Strategy 2 (fallback): the original class-name guesses, kept in
        # case AAB's markup varies by page/species and does sometimes use a
        # literal "legend"-ish class somewhere.
        for sel in ["[class*='legend']", "[class*='range-map'] [class*='key']",
                    "[class*='maps'] [class*='legend']"]:
            try:
                texts = page.eval_on_selector_all(sel, "els => els.map(e => e.innerText || '')")
            except Exception:
                texts = []
            for raw_text in texts:
                if not raw_text:
                    continue
                lowered = raw_text.lower()
                found = [
                    (KNOWN_LABELS[lbl]["order"], KNOWN_LABELS[lbl]["fallback_color"])
                    for lbl in KNOWN_LABELS
                    if lbl in lowered
                ]
                if found:
                    by_order = {}
                    for order, color in found:
                        by_order.setdefault(order, color)
                    legend = [
                        {"color": color, "label": DISPLAY_LABEL_BY_ORDER[order]}
                        for order, color in sorted(by_order.items())
                    ]
                    logger.info("AAB: extracted %d legend entries via class selector '%s': %s",
                                len(legend), sel, [l["label"] for l in legend])
                    return legend

        logger.debug("AAB: could not extract legend text via body scan or class selectors")
        return []

    def _fetch_aab_overview(self, common_name: str) -> Optional[dict]:
        """
        Fetch the Basic Description, Cool Facts, and Habitat/Food/
        Nesting/Behavior/Conservation tags from All About Birds' own
        /overview page — new, distinct content from the existing
        _fetch_aab_range_map (which only ever pulled the map image).
        Uses the same Playwright-based Cloudflare bypass, same
        User-Agent, same slug-retry strategy via _aab_slugs.

        Returns None if every slug attempt failed to load a species
        page (as opposed to AAB's own search-results fallback page, which
        loads successfully but isn't the page we asked for — checked via
        the page <title>, since a wrong-slug URL still returns HTTP
        200 with AAB's own generic "Search Results" page rather than a
        404, confirmed live against the site: neither of the two
        pre-existing slug variants matched a hyphenated species page,
        both silently landed on this exact fallback instead).

        Raises AABBlockedError if every slug attempt hit Cloudflare's
        challenge page rather than a confirmed no-page result — the
        caller (_do_enrich) treats this differently from a plain None,
        since a block says nothing about whether AAB has a page.
        """
        any_blocked = False
        for slug in self._aab_slugs(common_name):
            page_url = f"https://www.allaboutbirds.org/guide/{slug}/overview"
            try:
                result = self._playwright_aab_overview(page_url, common_name)
                if result:
                    result["aab_url"] = page_url
                    return result
            except AABBlockedError as e:
                any_blocked = True
                logger.debug("AAB overview blocked for %s (%s): %s", common_name, slug, e)
            except Exception as e:
                logger.debug("AAB overview fetch failed for %s (%s): %s", common_name, slug, e)
        if any_blocked:
            raise AABBlockedError(f"All slug attempts blocked for {common_name}")
        return None

    def _playwright_aab_overview(self, page_url: str, common_name: str) -> Optional[dict]:
        """
        Navigate to an AAB /overview page and extract Basic Description,
        Cool Facts, and the five category tags — DOM structure
        confirmed by directly inspecting a live fetch (American Robin),
        not assumed from the site's general layout conventions:
          - "Basic Description" is a <h2>; its nextElementSibling is
            directly the description <p>.
          - "Cool Facts" is an accordion trigger (<a class="accordion-title">
            inside an <li>) — the bullet items are <li>
            elements already present in the DOM inside that same <li>,
            no click/expand needed to read them.
          - The five tags render as <a> elements whose href ends in
            #habitat / #food / #nesting / #behavior / #conservation —
            confirmed more reliable than text-matching, since each <a>
            contains an <img> icon plus the label+value concatenated as
            one text run (e.g. "HabitatOpen Woodlands"), which fails a
            leaf-element-only text scan (the <a> isn't a leaf) the same
            way the OLD legend scan would have missed it.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("AAB overview: Playwright not importable — skipping")
            return None

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 900},
                )
                page = ctx.new_page()
                try:
                    page.goto(page_url, timeout=25_000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3_000)
                except Exception:
                    pass

                title = page.title()
                # AAB's own fallback for an unrecognized slug is a
                # 200-status "Search Results" page, not a 404 — checking
                # the title is the only reliable way to tell a genuine
                # species page from that fallback, confirmed by directly
                # observing this exact title live for a wrong-slug URL.
                # "Attention Required" is Cloudflare's own challenge page
                # title, NOT AAB's — a confirmed, previously-missed
                # distinction: this used to be treated identically to
                # "Search Results" (both silently returned None, and the
                # caller then permanently stamped aab_fetched_at either
                # way), which meant a species blocked by Cloudflare at
                # enrichment time got the exact same permanent "no data"
                # treatment as a species AAB genuinely has no page for —
                # silently disabling all future retries for a temporary,
                # infrastructure-level block. Raising a distinct exception
                # here lets the caller retry a block later while still
                # correctly never retrying a confirmed no-page result.
                if "Attention Required" in title:
                    browser.close()
                    raise AABBlockedError(f"Cloudflare challenge page for {page_url}")
                if "Search Results" in title:
                    browser.close()
                    return None

                result = page.evaluate(r"""() => {
                    const out = {description: null, cool_facts: [], tags: {}};

                    // Basic Description
                    for (const h of document.querySelectorAll('h2')) {
                        if (h.textContent.trim() === 'Basic Description') {
                            const p = h.nextElementSibling;
                            if (p && p.tagName === 'P') out.description = p.textContent.trim();
                            break;
                        }
                    }

                    // Cool Facts — <li> bullets already in the DOM
                    for (const el of document.querySelectorAll('body *')) {
                        if (el.children.length === 0 && el.textContent.trim() === 'Cool Facts') {
                            const li = el.closest('li');
                            if (li) {
                                const items = li.querySelectorAll('ul li');
                                out.cool_facts = Array.from(items)
                                    .map(i => i.textContent.trim())
                                    .filter(t => t.length > 0);
                            }
                            break;
                        }
                    }

                    // Habitat/Food/Nesting/Behavior/Conservation tags
                    const tagAnchors = document.querySelectorAll(
                        'a[href*="#habitat"], a[href*="#food"], a[href*="#nesting"], ' +
                        'a[href*="#behavior"], a[href*="#conservation"]'
                    );
                    const labels = ['Habitat', 'Food', 'Nesting', 'Behavior', 'Conservation'];
                    for (const a of tagAnchors) {
                        const text = a.textContent.trim();
                        for (const label of labels) {
                            if (text.startsWith(label)) {
                                out.tags[label.toLowerCase()] = text.slice(label.length).trim();
                                break;
                            }
                        }
                    }
                    return out;
                }""")
                browser.close()

                if not result or not (result.get("description") or result.get("cool_facts")):
                    logger.debug("AAB overview: page loaded but no content extracted for %s", common_name)
                    return None

                logger.info(
                    "AAB overview for %s: description=%s, %d cool facts, tags=%s",
                    common_name, bool(result.get("description")),
                    len(result.get("cool_facts") or []), result.get("tags"),
                )
                return {
                    "description": result.get("description"),
                    "cool_facts": result.get("cool_facts") or [],
                    "habitat": (result.get("tags") or {}).get("habitat"),
                    "food": (result.get("tags") or {}).get("food"),
                    "nesting": (result.get("tags") or {}).get("nesting"),
                    "behavior": (result.get("tags") or {}).get("behavior"),
                    # confirmed bug: this was scraped into `tags`
                    # correctly all along (visible in the log line just
                    # above, which logs `tags` directly) but never
                    # copied into this function's own return
                    # value — silently dropped at exactly this line,
                    # despite _do_enrich already being ready to receive
                    # and assign it. Reported directly: the log showed
                    # 'conservation': 'Low Concern' but no 5th tile or
                    # Conservation section ever appeared.
                    "conservation": (result.get("tags") or {}).get("conservation"),
                }
        except AABBlockedError:
            # Must NOT be swallowed by the generic session-error handler
            # below — a caught-and-return-None here would silently
            # collapse back into the exact bug this exception exists to
            # avoid (see _do_enrich's aab_fetched_at handling).
            raise
        except Exception as e:
            logger.warning("Playwright AAB overview session error for %s: %s", common_name, e)
            return None

    def _fetch_aab_size(self, common_name: str) -> Optional[dict]:
        """
        Fetch the Length measurement from AAB's own /id (not
        /overview) page — a genuinely separate page/tab from everything
        _fetch_aab_overview pulls, confirmed by directly fetching a live
        page (Blue Jay): the "Measurements" data (Length/Weight/Wingspan)
        only exists under "The Four Keys to ID" → "Size & Shape" on /id,
        not on /overview. This is a second full Playwright page load per
        species on top of the overview fetch — a deliberate cost,
        accepted because this data doesn't exist anywhere else in the
        pipeline and powers the At a Glance size-comparison ruler.

        Same slug-retry / AABBlockedError semantics as
        _fetch_aab_overview — see that function's docstring.
        """
        any_blocked = False
        for slug in self._aab_slugs(common_name):
            page_url = f"https://www.allaboutbirds.org/guide/{slug}/id"
            try:
                result = self._playwright_aab_size(page_url, common_name)
                if result:
                    return result
            except AABBlockedError as e:
                any_blocked = True
                logger.debug("AAB size blocked for %s (%s): %s", common_name, slug, e)
            except Exception as e:
                logger.debug("AAB size fetch failed for %s (%s): %s", common_name, slug, e)
        if any_blocked:
            raise AABBlockedError(f"All slug attempts blocked for {common_name}")
        return None

    def _playwright_aab_size(self, page_url: str, common_name: str) -> Optional[dict]:
        """
        Navigate to an AAB /id page and extract the Length measurement
        via a text regex against the whole rendered page's visible text
        rather than DOM-element traversal (unlike _playwright_aab_overview) —
        deliberate: the exact heading/element structure of the
        "Measurements" block wasn't independently confirmed against live
        DOM the way Basic Description's <h2> was, so matching the
        rendered text pattern directly ("Length: 9.8-11.8 in (25-30 cm)",
        confirmed against a live fetch of this exact page) is more
        robust to markup details than guessing element structure would
        be. Handles both a range ("9.8-11.8 in") and a single value
        ("10 in") — not every species' page reports a range.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("AAB size: Playwright not importable — skipping")
            return None

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 900},
                )
                page = ctx.new_page()
                try:
                    page.goto(page_url, timeout=25_000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3_000)
                except Exception:
                    pass

                title = page.title()
                # Same distinction as _playwright_aab_overview — see
                # that function's comment for why these two checks (block
                # vs. genuine no-page) must never be collapsed together.
                if "Attention Required" in title:
                    browser.close()
                    raise AABBlockedError(f"Cloudflare challenge page for {page_url}")
                if "Search Results" in title:
                    browser.close()
                    return None

                body_text = page.evaluate("() => document.body.innerText")
                browser.close()

                if not body_text:
                    return None

                import re as _re
                m = _re.search(
                    r"Length:\s*([\d.]+)\s*(?:[-\u2013]\s*([\d.]+))?\s*in\s*\(\s*([\d.]+)\s*(?:[-\u2013]\s*([\d.]+))?\s*cm\s*\)",
                    body_text,
                )
                if not m:
                    logger.debug("AAB size: page loaded but no Length measurement found for %s", common_name)
                    return None

                cm_lo = float(m.group(3))
                cm_hi = float(m.group(4)) if m.group(4) else cm_lo
                in_lo = m.group(1)
                in_hi = m.group(2) or m.group(1)
                display_text = f"{in_lo}-{in_hi} in ({cm_lo:g}-{cm_hi:g} cm)" if m.group(2) else f"{in_lo} in ({cm_lo:g} cm)"

                logger.info("AAB size for %s: %.1f-%.1f cm", common_name, cm_lo, cm_hi)
                return {
                    "length_min_cm": cm_lo,
                    "length_max_cm": cm_hi,
                    "length_text": display_text,
                }
        except AABBlockedError:
            raise
        except Exception as e:
            logger.warning("Playwright AAB size session error for %s: %s", common_name, e)
            return None

    def _fetch_aab_lifehistory(self, common_name: str) -> Optional[dict]:
        """
        Fetch the full narrative paragraphs behind Habitat/Food/Nesting/
        Behavior/Conservation from AAB's own /lifehistory page — a third
        separate AAB page/tab from both /overview and /id, confirmed
        directly by fetching a live page (Blue Jay): /overview only has
        short tag values ("Open Woodlands"), not the full paragraphs
        shown on the site's own "Life History" tab, which is what powers
        the At a Glance card's "click through for the full explanation"
        request this was built for.

        Same slug-retry / AABBlockedError semantics as the other AAB
        fetchers — see _fetch_aab_overview's docstring.
        """
        any_blocked = False
        for slug in self._aab_slugs(common_name):
            page_url = f"https://www.allaboutbirds.org/guide/{slug}/lifehistory"
            try:
                result = self._playwright_aab_lifehistory(page_url, common_name)
                if result:
                    return result
            except AABBlockedError as e:
                any_blocked = True
                logger.debug("AAB lifehistory blocked for %s (%s): %s", common_name, slug, e)
            except Exception as e:
                logger.debug("AAB lifehistory fetch failed for %s (%s): %s", common_name, slug, e)
        if any_blocked:
            raise AABBlockedError(f"All slug attempts blocked for {common_name}")
        return None

    def _playwright_aab_lifehistory(self, page_url: str, common_name: str) -> Optional[dict]:
        """
        Navigate to an AAB /lifehistory page and extract the Habitat,
        Food, Nesting, Behavior, and Conservation sections' full prose.

        Each section is a <h2> (confirmed directly against a live
        fetch: "Habitat", "Food", "Nesting", "Behavior", "Conservation",
        in that order, followed by "Credits" which is deliberately not
        collected) — extraction walks siblings from one <h2> up to the
        next, joining their text. Nesting's <h2> siblings include two
        <h3> subsections ("Nest Placement", "Nest Description") before a
        third, "Nesting Facts" — a structured table (clutch size, egg
        dimensions, incubation period, etc.), deliberately excluded here
        and stopped at explicitly: dumped as flowing prose it reads as a
        wall of disconnected numbers, and the two prose subsections
        (Nest Placement + Nest Description) are what's wanted
        for a readable "explanation," matching the source page's own
        prose framing for the other four sections.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("AAB lifehistory: Playwright not importable — skipping")
            return None

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 900},
                )
                page = ctx.new_page()
                try:
                    page.goto(page_url, timeout=25_000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3_000)
                except Exception:
                    pass

                title = page.title()
                # Same distinction as every other AAB fetcher — see
                # _playwright_aab_overview's comment for why these two
                # checks must never be collapsed together.
                if "Attention Required" in title:
                    browser.close()
                    raise AABBlockedError(f"Cloudflare challenge page for {page_url}")
                if "Search Results" in title:
                    browser.close()
                    return None

                result = page.evaluate(r"""() => {
                    function sectionText(headingText, stopAtText) {
                        const h2s = Array.from(document.querySelectorAll('h2'));
                        const h = h2s.find(el => el.textContent.trim() === headingText);
                        if (!h) return null;
                        let out = [];
                        let node = h.nextElementSibling;
                        while (node && node.tagName !== 'H2') {
                            if (stopAtText && node.tagName === 'H3' &&
                                node.textContent.trim() === stopAtText) break;
                            // Skip H3 subsection headings themselves (e.g.
                            // "Nest Placement") — keep walking into their
                            // content, just don't fold the heading's own
                            // text into the joined prose.
                            if (node.tagName !== 'H3') {
                                const t = node.textContent.replace(/Back to top/gi, '').trim();
                                if (t) out.push(t);
                            }
                            node = node.nextElementSibling;
                        }
                        return out.join(' ').replace(/\s+/g, ' ').trim() || null;
                    }
                    return {
                        habitat: sectionText('Habitat'),
                        food: sectionText('Food'),
                        nesting: sectionText('Nesting', 'Nesting Facts'),
                        behavior: sectionText('Behavior'),
                        conservation: sectionText('Conservation'),
                    };
                }""")
                browser.close()

                if not result or not any(result.values()):
                    logger.debug("AAB lifehistory: page loaded but no sections found for %s", common_name)
                    return None

                logger.info("AAB lifehistory for %s: sections found = %s",
                            common_name, [k for k, v in result.items() if v])
                return result
        except AABBlockedError:
            raise
        except Exception as e:
            logger.warning("Playwright AAB lifehistory session error for %s: %s", common_name, e)
            return None

    def fetch_birdlife_range_map(self, common_name: str, scientific_name: str,
                                  output_path: str) -> bool:
        """
        Capture a BirdLife DataZone range map using Playwright, with its
        per-species legend extracted from the live page.

        Thin bool-returning wrapper around fetch_birdlife_range_map_full()
        for backwards compatibility with existing callers that only need
        the screenshot. Use fetch_birdlife_range_map_full() directly to
        also get the extracted legend (used by enrich_profile() so the
        legend can be cached alongside the map at enrichment time, and by
        the on-demand /range-map/birdlife endpoint for fresher data).
        """
        result = self.fetch_birdlife_range_map_full(common_name, scientific_name, output_path)
        return bool(result.get("ok"))

    def fetch_birdlife_range_map_full(self, common_name: str, scientific_name: str,
                                       output_path: str) -> dict:
        """
        Capture a BirdLife DataZone range map using Playwright.

        Returns {"ok": bool, "legend": list[{"color","label"}] | None, "error": str | None}.

        Slug resolution — this is the fix for the reported 404s:
        BirdLife's IUCN-based English names frequently differ from the
        common_name Chirp/BirdNET uses (e.g. Chirp's "European Starling" is
        BirdLife's "Common Starling" — same species, Sturnus vulgaris, but a
        different slug). Guessing the slug from common_name alone 404s for
        every such species. Scientific names are the one thing guaranteed
        to match everywhere, so we resolve the factsheet URL via
        BirdLife's own species search (keyed on scientific_name) and follow
        whatever it redirects/links to, falling back to the guessed
        common-name slug only if search comes up empty.

        Regardless of how the URL was resolved, we explicitly check for
        BirdLife's "can't find this page" 404 content before screenshotting
        — this is the safety net that stops a 404 page from ever being
        saved as if it were a successful map (the exact bug reported: a
        404 page screenshotted and served as "the range map").
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright not installed — BirdLife map unavailable")
            return {"ok": False, "legend": None, "error": "playwright_not_installed"}

        import re as _re
        slug_part = lambda s: _re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
        guessed_slug = f"{slug_part(common_name)}-{slug_part(scientific_name)}"
        guessed_url = f"https://datazone.birdlife.org/species/factsheet/{guessed_slug}"

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 900},
                )
                page = ctx.new_page()

                # ── Try the guessed common-name slug FIRST ──────────────────────
                # Two opposite cases now confirmed: European Starling
                # needed the en_HBW/search-based resolution below (BirdLife
                # calls it "Common Starling"), but American Robin's GUESSED
                # slug is correct — BirdLife's own page confirms
                # "American Robin" is exactly right — while en_HBW returns
                # "American/San Lucas Robin" for this species, which 404s.
                # Neither strategy is reliably better than the other, so try
                # the free, fast guess first and only spend an extra
                # navigation + the en_HBW API call if it genuinely 404s.
                page.goto(guessed_url, timeout=30_000, wait_until="domcontentloaded")
                page.wait_for_timeout(2_500)
                guess_failed = self._is_birdlife_404(page)
                if guess_failed:
                    page.wait_for_timeout(2_000)
                    guess_failed = self._is_birdlife_404(page)

                if not guess_failed:
                    resolved_url = guessed_url
                    logger.info("BirdLife range map: %s → %s (guessed slug worked)", common_name, resolved_url)
                else:
                    logger.info("BirdLife: guessed slug 404'd for %s, trying en_HBW/search resolution", common_name)
                    resolved_url = self._resolve_birdlife_factsheet_url(
                        page, scientific_name, common_name
                    )
                    if not resolved_url or resolved_url == guessed_url:
                        browser.close()
                        logger.warning("BirdLife: no working URL found for %s (guessed slug 404'd, "
                                        "en_HBW/search resolution found nothing new) — not saving", common_name)
                        return {"ok": False, "legend": None, "error": "404_not_found"}

                    logger.info("BirdLife range map: %s → %s (via en_HBW/search, guess had 404'd)",
                                common_name, resolved_url)
                    page.goto(resolved_url, timeout=30_000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2_500)
                    still_404 = self._is_birdlife_404(page)
                    if still_404:
                        page.wait_for_timeout(2_000)
                        still_404 = self._is_birdlife_404(page)
                    if still_404:
                        browser.close()
                        logger.warning("BirdLife: 404 at %s for %s (both guess and en_HBW/search resolution "
                                        "failed) — not saving", resolved_url, common_name)
                        return {"ok": False, "legend": None, "error": "404_not_found"}

                # The BirdLife factsheet has a tab bar — find and click the map/range tab
                map_tab_selectors = [
                    "a:text-matches('(?i)map')",
                    "a:text-matches('(?i)range')",
                    "button:text-matches('(?i)map')",
                    ".tab-item:text-matches('(?i)map')",
                    "li:text-matches('(?i)map') a",
                ]
                for sel in map_tab_selectors:
                    try:
                        el = page.locator(sel).first
                        if el.is_visible(timeout=2_000):
                            el.click()
                            page.wait_for_load_state("networkidle", timeout=8_000)
                            break
                    except Exception:
                        continue

                # Wait extra time for tiles / canvas to render
                page.wait_for_timeout(4_000)

                # ── Open the LEGEND panel, THEN extract, THEN close it ──────────
                # BirdLife's map legend is collapsed by default (a "LEGEND"
                # button with a layers icon, confirmed from a production
                # screenshot) — it has to be clicked open before the category
                # list exists/is populated in the DOM at all. The previous
                # version only ever clicked this button in the dismiss pass
                # AFTER already trying (and failing) to extract the legend,
                # so extraction always ran against a still-collapsed panel.
                legend_opened = False
                for sel in [
                    'button:has-text("LEGEND")',
                    '[aria-label*="legend" i]',
                    'button:has-text("Legend")',
                ]:
                    try:
                        el = page.locator(sel).first
                        if el.is_visible(timeout=1_500):
                            el.click()
                            page.wait_for_timeout(800)
                            legend_opened = True
                            break
                    except Exception:
                        continue

                # ── Extract the per-species legend BEFORE hiding it ───────
                # Reads computed colors + labels for whichever
                # categories this specific species' map shows (BirdLife's
                # full category set has 12 entries — Resident, Breeding,
                # Non-breeding, Re-introduced, Introduced, Origin uncertain,
                # Possibly extinct, Extinct, Possibly extant, Passage, Season
                # uncertain, Assisted colonisation — but any given species'
                # map only renders the ones that apply to it).
                legend = self._extract_birdlife_legend(page)
                if not legend and legend_opened:
                    logger.debug("BirdLife: legend panel opened but extraction still found nothing for this species")

                # Close/hide whatever legend or popup panels are now open so
                # they don't appear in the screenshot below. Click the same
                # toggle again first (cleaner than CSS-hiding a panel mid-
                # animation), then fall back to hiding by class as a safety
                # net for anything that doesn't toggle closed cleanly.
                if legend_opened:
                    for sel in ['button:has-text("LEGEND")', 'button:has-text("Legend")']:
                        try:
                            el = page.locator(sel).first
                            if el.is_visible(timeout=800):
                                el.click()
                                page.wait_for_timeout(400)
                                break
                        except Exception:
                            pass
                for sel in [
                    'button[aria-label*="close" i]', '.legend-close', '.close-btn',
                    '[data-dismiss]', '.modal-close', '.leaflet-popup-close-button',
                ]:
                    try:
                        el = page.locator(sel).first
                        if el.is_visible(timeout=800):
                            el.click()
                            page.wait_for_timeout(400)
                    except Exception:
                        pass

                # Hide ALL known map UI chrome via JS before the screenshot.
                # Production screenshots showed the legend panel AND
                # the EXPAND button, zoom +/- controls, and the share/
                # download icons all still visible in the saved image —
                # clicking LEGEND closed (in theory) only removes that one
                # panel, and the chrome-hiding selectors before this point
                # were too narrow (legend/popup/tooltip only) to catch the
                # rest of BirdLife's map toolbar. This hides by content
                # (the panel's own distinctive text), by class-name
                # pattern, by visible button text, AND by position for
                # icon-only buttons (zoom +/-, share, download) that have
                # no text content to match on at all.
                try:
                    page.evaluate(
                        """(mapSelector) => {
                            // ── Content-based hide for the legend panel itself ──
                            // The panel is very likely a plain <div> with a
                            // CSS-module-hashed class name (no literal
                            // "legend" in it), so neither the class-name nor
                            // the button-text pass below can find IT — only
                            // its toggle BUTTON. Find it by its
                            // distinctive content instead: it contains both
                            // "Show IBAs/KBAs" and "Show protected areas" as
                            // visible text, which is unique to this panel.
                            //
                            // IMPORTANT: querySelectorAll('div') visits
                            // elements in document order, so the FIRST match
                            // is the OUTERMOST ancestor containing both
                            // strings somewhere in its subtree — which could
                            // be the entire map container, not the legend
                            // panel. Hiding that would blank out the whole
                            // screenshot, not just the legend. Must instead
                            // find the INNERMOST (most specific) matching
                            // element — the one with no child that ALSO
                            // contains both strings.
                            const candidates = [];
                            document.querySelectorAll('div').forEach(el => {
                                const t = el.textContent || '';
                                if (t.includes('Show IBAs/KBAs') && t.includes('Show protected areas')) {
                                    candidates.push(el);
                                }
                            });
                            if (candidates.length > 0) {
                                // The innermost match is the one with the
                                // fewest descendant elements among the
                                // candidates (every candidate is an ancestor
                                // of every other, by construction, since they
                                // all contain the same two strings nested in
                                // the same spot) — so pick the one deepest in
                                // the chain by checking which has no OTHER
                                // candidate as a descendant.
                                let innermost = candidates[candidates.length - 1];
                                for (const c of candidates) {
                                    const containsAnotherCandidate = candidates.some(
                                        other => other !== c && c.contains(other)
                                    );
                                    if (!containsAnotherCandidate) { innermost = c; break; }
                                }
                                let target = innermost;
                                let depth = 0;
                                while (target.parentElement && depth < 4) {
                                    const rect = target.parentElement.getBoundingClientRect();
                                    if (rect.width > 500 || rect.height > 500) break;
                                    target = target.parentElement;
                                    depth++;
                                }
                                target.style.display = 'none';
                            }

                            const classSelectors = [
                                '.legend-panel', '.leaflet-popup', '.map-legend-container',
                                '[class*=legend]', '[class*=popup]', '[class*=tooltip]',
                                '[class*=Legend]', '[class*=toolbar]', '[class*=Toolbar]',
                                '[class*=control]', '[class*=Control]',
                            ];
                            document.querySelectorAll(classSelectors.join(',')).forEach(
                                el => { el.style.display = 'none'; }
                            );

                            const textsToHide = ['legend', 'expand', 'show ibas', 'show protected'];
                            document.querySelectorAll('button, a').forEach(el => {
                                const t = (el.textContent || '').trim().toLowerCase();
                                if (textsToHide.some(needle => t.includes(needle))) {
                                    let target = el;
                                    let depth = 0;
                                    while (target.parentElement && depth < 3) {
                                        const rect = target.parentElement.getBoundingClientRect();
                                        if (rect.width > 250) break;
                                        target = target.parentElement;
                                        depth++;
                                    }
                                    target.style.display = 'none';
                                }
                            });

                            // Positional pass for icon-only buttons (zoom,
                            // share, download) with no matching text/class.
                            const mapEl = document.querySelector(mapSelector)
                                          || document.querySelector('canvas')
                                          || document.body;
                            const mapRect = mapEl.getBoundingClientRect();
                            const EDGE = 90; // px from a map edge counted as "corner chrome"
                            document.querySelectorAll('button, a, [role="button"]').forEach(el => {
                                if (el.offsetParent === null) return; // already hidden
                                const r = el.getBoundingClientRect();
                                if (r.width === 0 || r.height === 0) return;
                                if (r.width > 60 || r.height > 60) return; // not icon-sized
                                const nearRight = (mapRect.right - r.right) <= EDGE && r.right <= mapRect.right + 5;
                                const nearTop = (r.top - mapRect.top) <= EDGE && r.top >= mapRect.top - 5;
                                const nearBottom = (mapRect.bottom - r.bottom) <= EDGE && r.bottom <= mapRect.bottom + 5;
                                if ((nearRight && nearTop) || (nearRight && nearBottom)) {
                                    el.style.display = 'none';
                                }
                            });
                        }""",
                        ".leaflet-container, .map-container, #map, div[class*='map']"
                    )
                except Exception:
                    pass
                # Run the hide pass TWICE with a wait in between — BirdLife's
                # panel close animation/re-render could otherwise still be
                # in flight when the first pass runs, leaving it visible.
                page.wait_for_timeout(400)
                try:
                    page.evaluate(
                        """() => {
                            const candidates = [];
                            document.querySelectorAll('div').forEach(el => {
                                const t = el.textContent || '';
                                if (t.includes('Show IBAs/KBAs') && t.includes('Show protected areas')) {
                                    candidates.push(el);
                                }
                            });
                            if (candidates.length > 0) {
                                let innermost = candidates[candidates.length - 1];
                                for (const c of candidates) {
                                    const containsAnotherCandidate = candidates.some(
                                        other => other !== c && c.contains(other)
                                    );
                                    if (!containsAnotherCandidate) { innermost = c; break; }
                                }
                                let target = innermost;
                                let depth = 0;
                                while (target.parentElement && depth < 4) {
                                    const rect = target.parentElement.getBoundingClientRect();
                                    if (rect.width > 500 || rect.height > 500) break;
                                    target = target.parentElement;
                                    depth++;
                                }
                                target.style.display = 'none';
                            }
                        }"""
                    )
                except Exception:
                    pass
                page.wait_for_timeout(300)

                # Try map container selectors in order of specificity
                map_selectors = [
                    ".species-map-container",
                    "#species-map",
                    ".leaflet-container",
                    ".map-container",
                    "#map",
                    "div[class*='map']",
                    "iframe[src*='map']",
                    "canvas",
                ]
                screenshot_bytes = None
                for sel in map_selectors:
                    try:
                        el = page.locator(sel).first
                        if el.is_visible(timeout=2_000):
                            bb = el.bounding_box()
                            if bb and bb["width"] > 200 and bb["height"] > 150:
                                screenshot_bytes = el.screenshot()
                                logger.info("BirdLife: screenshotted %s (%.0fx%.0f) for %s",
                                            sel, bb["width"], bb["height"], common_name)
                                break
                    except Exception:
                        continue

                # Fall back: full page screenshot cropped to visible viewport
                if not screenshot_bytes:
                    screenshot_bytes = page.screenshot(
                        clip={"x": 0, "y": 0, "width": 900, "height": 600}
                    )
                    logger.info("BirdLife: full-page screenshot for %s", common_name)

                browser.close()

            if screenshot_bytes:
                import pathlib
                pathlib.Path(output_path).write_bytes(screenshot_bytes)
                logger.info("BirdLife range map saved: %s (%d bytes, %d legend entries)",
                            output_path, len(screenshot_bytes), len(legend or []))
                return {"ok": True, "legend": legend, "error": None}

        except Exception as e:
            logger.warning("BirdLife Playwright error for %s: %s", common_name, e)
            return {"ok": False, "legend": None, "error": str(e)}

        return {"ok": False, "legend": None, "error": "no_screenshot_captured"}

    @staticmethod
    def _is_birdlife_404(page) -> bool:
        """
        Detect BirdLife's 404 page. Checked by literal page text rather than
        a specific selector, since a markup change shouldn't silently disable
        this safety net — the visible "404" / "can't find this page" copy is
        the most stable signal across redesigns.
        """
        try:
            body_text = page.inner_text("body", timeout=3_000)
        except Exception:
            return False
        lowered = (body_text or "").lower()
        return (
            ("404" in lowered and "find this page" in lowered)
            or "we can't seem to find this page" in lowered
            or "page not found" in lowered
        )

    def _resolve_birdlife_factsheet_url(self, page, scientific_name: str, common_name: str) -> Optional[str]:
        """
        Resolve an ALTERNATIVE BirdLife factsheet URL, tried only after the
        caller's guessed common-name slug has already 404'd. The guess is
        tried first (see fetch_birdlife_range_map_full) because it's often
        correct — confirmed directly for American Robin, where BirdLife's
        slug genuinely is "american-robin-turdus-migratorius" — so
        spending an extra navigation + API call here unconditionally would
        be wasted work most of the time, not a reliability improvement.

        Tries, in order:

        1. eBird's own "English, HBW" (en_HBW) taxonomy locale. eBird
           maintains this as an official cross-walk between the eBird/
           Clements taxonomy (what Chirp/BirdNET uses for common_name) and
           the BirdLife/HBW taxonomy — querying the eBird taxonomy API with
           locale=en_HBW for this species' code returns BirdLife's own
           common name (e.g. "Common Starling" for the species Chirp calls
           "European Starling"). This fixed European Starling's 404 —
           but is NOT universally more reliable than the guess: for American
           Robin specifically, en_HBW returns "American/San Lucas Robin",
           which itself 404s, while the plain guessed slug was correct.
           Requires only the eBird API key Chirp already uses elsewhere.

        2. BirdLife's own site search, scraped via Playwright. Kept as a
           fallback for the case where eBird has no en_HBW entry for this
           species, or the en_HBW name itself doesn't match BirdLife's
           current slug either. BirdLife's DataZone Explorer (relaunched
           April 2025, built by Trifork) is a heavily client-rendered SPA,
           so the exact search markup/query parameter isn't something we
           can fully verify without live access; this step is best-effort.

        Returns the resolved factsheet URL, or None if every step here
        failed too (caller treats that as a genuine 404 — the species
        likely isn't on BirdLife under any name we can find).
        """
        if not scientific_name:
            return None

        # ── 1. eBird en_HBW cross-walk ───────────────────────────────────
        ebird_resolved = self._resolve_birdlife_url_via_ebird_hbw(scientific_name, common_name)
        if ebird_resolved:
            return ebird_resolved

        # ── 2. BirdLife site search (best-effort fallback) ──────────────
        try:
            search_url = f"https://datazone.birdlife.org/search?q={scientific_name.strip().replace(' ', '+')}"
            page.goto(search_url, timeout=20_000, wait_until="domcontentloaded")
            page.wait_for_timeout(1_500) # client-rendered results need a beat to populate

            # Look for a results link pointing at a species factsheet
            try:
                hrefs = page.eval_on_selector_all(
                    "a[href*='/species/factsheet/']",
                    "els => els.map(e => e.getAttribute('href'))"
                )
            except Exception:
                hrefs = []

            if not hrefs:
                logger.debug("BirdLife search: no factsheet links found for '%s'", scientific_name)
                return None

            # Prefer a link whose slug contains every word of the scientific
            # name (most specific match); otherwise take the first result.
            sci_words = [w.lower() for w in scientific_name.strip().split() if len(w) > 2]
            for href in hrefs:
                href_l = (href or "").lower()
                if all(w in href_l for w in sci_words):
                    resolved = href if href.startswith("http") else f"https://datazone.birdlife.org{href}"
                    logger.info("BirdLife search resolved '%s' (%s) → %s",
                                common_name, scientific_name, resolved)
                    return resolved

            # No exact word match — take first result rather than nothing,
            # still far more reliable than a blind common-name guess.
            first = hrefs[0]
            resolved = first if first.startswith("http") else f"https://datazone.birdlife.org{first}"
            logger.info("BirdLife search: no exact match for '%s', using first result → %s",
                        scientific_name, resolved)
            return resolved

        except Exception as e:
            logger.debug("BirdLife search resolution failed for '%s': %s", scientific_name, e)
            return None

    def _resolve_birdlife_url_via_ebird_hbw(self, scientific_name: str, common_name: str) -> Optional[str]:
        """
        Query eBird's taxonomy API with locale=en_HBW to get BirdLife's own
        common name for this species, then build the factsheet slug from
        THAT name instead of Chirp's eBird/Clements common_name.

        en_HBW is an officially maintained cross-walk between the eBird/
        Clements taxonomy and the BirdLife/HBW taxonomy (eBird Central +
        Denis Lepage, in collaboration with BirdLife International) — this
        is the authoritative source for "what does BirdLife call this
        species", not a guess. Scientific names never change between the
        two locale responses (per eBird's own documentation), only the
        common name does, which is exactly the piece that was wrong before.

        Returns the resolved factsheet URL, or None if no API key is
        configured, the species has no en_HBW entry, or the request fails
        for any reason — all of which are legitimate "fall through to the
        next strategy" outcomes, not something to surface as an error.
        """
        db = getattr(self, "db", None)
        api_key = _get_ebird_api_key(db) if db is not None else None
        if not api_key:
            return None
        try:
            data = _get(
                "https://api.ebird.org/v2/ref/taxonomy/ebird",
                params={"fmt": "json", "species": scientific_name, "locale": "en_HBW"},
                headers={"X-eBirdApiToken": api_key},
            )
        except Exception as e:
            logger.debug("eBird en_HBW lookup failed for '%s': %s", scientific_name, e)
            return None

        if not data or not isinstance(data, list) or not data:
            logger.debug("eBird en_HBW lookup returned nothing for '%s'", scientific_name)
            return None

        hbw_name = data[0].get("comName")
        if not hbw_name:
            return None

        slug_part = lambda s: _re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
        hbw_slug = f"{slug_part(hbw_name)}-{slug_part(scientific_name)}"
        resolved = f"https://datazone.birdlife.org/species/factsheet/{hbw_slug}"

        if hbw_name.lower() != common_name.lower():
            logger.info("eBird en_HBW: '%s' is BirdLife's name for '%s' (%s) → %s",
                        hbw_name, common_name, scientific_name, resolved)
        else:
            logger.debug("eBird en_HBW: name matches Chirp's common_name for '%s' — %s",
                        common_name, resolved)
        return resolved

    @staticmethod
    def _extract_birdlife_legend(page) -> Optional[list]:
        """
        Read the per-species legend directly from the live DOM —
        the rendered swatch colors and labels for whichever categories
        THIS species' map shows, not a guess. This is what makes the legend
        correct per-bird instead of one fixed global swatch list: BirdLife's
        map has up to 12 possible legend categories (Resident, Breeding,
        Non-breeding, Re-introduced, Introduced, Origin uncertain, Possibly
        extinct, Extinct, Possibly extant, Passage, Season uncertain,
        Assisted colonisation) but any given species only shows the subset
        that applies to it.

        Matches on the visible TEXT of each known category label
        rather than guessing CSS class names, since BirdLife's DataZone is a
        Trifork-built React app with CSS-module-hashed class names.

        IMPORTANT — scoped to the legend container, not the whole page.
        a production run for Warbling Vireo (a simple breeding/
        non-breeding migrant with no plausible reason to have more than
        2-3 categories) returned 11 of the 12 possible category
        labels — confirmed implausible by checking multiple independent
        sources for this species' range. The original version
        searched `document.querySelectorAll('body *')` — the ENTIRE page —
        which would also match a static reference/glossary panel
        explaining what each possible color means (if BirdLife's page has
        one anywhere, e.g. a help tooltip or sidebar key), not just the
        species-specific legend shown on the map. Now finds the
        literal "Legend" heading first (confirmed present on pages via
        direct fetch in an earlier session) and scopes the label search to
        its container, falling back to the whole-page search only if no
        such heading is found — and even then, treats more than 6 matches
        as suspicious, since no species in BirdLife's system plausibly
        shows more than half the possible categories at once.

        For each matched label, the color is read from a candidate that
        passes a strict "looks like a swatch" check — small (under
        40px), no children, no text content of its own — rather than just
        the first nearby element with a non-white background.

        Returns None (not an empty list) if nothing matched, so callers can
        tell "no legend found" apart from "legend found but empty" and keep
        the previous legend rather than overwriting it with nothing.
        """
        KNOWN_CATEGORY_LABELS = [
            "Resident", "Breeding", "Non-breeding", "Nonbreeding",
            "Re-introduced", "Reintroduced", "Introduced",
            "Origin uncertain", "Possibly extinct", "Extinct",
            "Possibly extant", "Passage", "Season uncertain",
            "Assisted colonisation", "Assisted colonization",
        ]

        js = """(labels) => {
            const isLikelySwatch = (el) => {
                if (!el || el.children.length > 0) return false;
                const text = (el.textContent || '').trim();
                if (text.length > 0) return false;
                const rect = el.getBoundingClientRect();
                if (rect.width > 40 || rect.height > 40) return false;
                if (rect.width === 0 || rect.height === 0) return false;
                return true;
            };

            const extractFrom = (root) => {
                const results = [];
                const seen = new Set();
                const allEls = root.querySelectorAll('*');
                for (const el of allEls) {
                    const text = (el.textContent || '').trim();
                    if (!text || text.length > 30) continue;
                    const matchedLabel = labels.find(l => text.toLowerCase() === l.toLowerCase());
                    if (!matchedLabel) continue;
                    const hasMatchingChild = Array.from(el.children).some(
                        c => (c.textContent || '').trim().toLowerCase() === matchedLabel.toLowerCase()
                    );
                    if (hasMatchingChild) continue;
                    if (seen.has(matchedLabel.toLowerCase())) continue;

                    const candidates = [
                        el.previousElementSibling,
                        el.nextElementSibling,
                        ...Array.from(el.children),
                        el.parentElement ? el.parentElement.previousElementSibling : null,
                        el.parentElement ? el.parentElement.firstElementChild : null,
                    ].filter(isLikelySwatch);

                    let color = null;
                    for (const c of candidates) {
                        const cs = window.getComputedStyle(c);
                        const bg = cs.backgroundColor;
                        if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent'
                                && bg !== 'rgb(255, 255, 255)') {
                            color = bg;
                            break;
                        }
                    }
                    if (color) {
                        seen.add(matchedLabel.toLowerCase());
                        results.push({ label: matchedLabel, color });
                    }
                }
                return results;
            };

            // First, try to find a "Legend" heading and scope the
            // search to its container — this is the per-species
            // legend panel, not the whole page.
            const allTextEls = document.querySelectorAll('body *');
            let legendHeading = null;
            for (const el of allTextEls) {
                const t = (el.textContent || '').trim().toLowerCase();
                if (t === 'legend') {
                    const hasMatchingChild = Array.from(el.children).some(
                        c => (c.textContent || '').trim().toLowerCase() === 'legend'
                    );
                    if (!hasMatchingChild) { legendHeading = el; break; }
                }
            }

            if (legendHeading) {
                // Search the heading's parent container (the legend
                // panel), walking up a couple levels if the immediate
                // parent is too small to contain the swatch rows too.
                let container = legendHeading.parentElement;
                let depth = 0;
                while (container && depth < 3) {
                    const rect = container.getBoundingClientRect();
                    if (rect.width > 80 && rect.height > 80) break;
                    container = container.parentElement;
                    depth++;
                }
                if (container) {
                    const scoped = extractFrom(container);
                    if (scoped.length > 0) return { results: scoped, scoped: true };
                }
            }

            // Fall back to the whole page if no Legend heading was found
            // or the scoped search came up empty.
            return { results: extractFrom(document.body), scoped: false };
        }"""

        try:
            result = page.evaluate(js, KNOWN_CATEGORY_LABELS)
            items = result.get("results", [])
            was_scoped = result.get("scoped", False)
        except Exception as e:
            logger.debug("BirdLife: legend text-match extraction error: %s", e)
            items, was_scoped = [], False

        if not items:
            logger.debug("BirdLife: could not extract legend from DOM by label text match")
            return None

        # a species plausibly shows at most a handful of categories;
        # an unscoped match returning more than 6 is the same implausible
        # pattern confirmed for Warbling Vireo (11 of 12) and is far more
        # likely a static reference panel than a per-species legend.
        # Scoped matches are trusted regardless of count, since they came
        # from the legend container, not the whole page.
        if not was_scoped and len(items) > 6:
            logger.warning("BirdLife: unscoped legend match found %d categories (implausible for "
                            "a single species) — discarding as likely a static reference panel, "
                            "not this species' legend", len(items))
            return None

        # Normalize duplicate-meaning labels (Reintroduced/Re-introduced,
        # Nonbreeding/Non-breeding) to one canonical spelling before
        # returning, since the text-match above intentionally checks both
        # spellings to maximize match chances but shouldn't return both.
        CANONICAL = {
            "reintroduced": "Re-introduced", "re-introduced": "Re-introduced",
            "nonbreeding": "Non-breeding", "non-breeding": "Non-breeding",
            "assisted colonization": "Assisted colonisation",
            "assisted colonisation": "Assisted colonisation",
        }
        legend = []
        seen_canonical = set()
        for it in items:
            label = it.get("label", "")
            canonical = CANONICAL.get(label.lower(), label)
            if canonical.lower() in seen_canonical:
                continue
            seen_canonical.add(canonical.lower())
            legend.append({"color": it.get("color"), "label": canonical})

        logger.info("BirdLife: extracted %d legend entries via text match (%s): %s",
                    len(legend), "scoped to Legend heading" if was_scoped else "whole-page fallback",
                    [l["label"] for l in legend])
        return legend[:12] # hard cap matching BirdLife's known max category count






    def _fetch_wikipedia_range_map(self, common_name: str, sci_name: str = "") -> Optional[str]:
        """Fetch range map from Wikipedia Commons."""
        range_keywords = ["range", "distribution", "map"]
        QUALIFIERS = ("Northern", "Southern", "Eastern", "Western", "American",
                      "Common", "Eurasian", "European", "Greater", "Lesser", "Little")
        words = common_name.split()
        sentence_case = " ".join([words[0]] + [w.lower() for w in words[1:]]) if words else common_name
        stripped = common_name
        for q in QUALIFIERS:
            if common_name.startswith(q + " "):
                stripped = common_name[len(q) + 1:]
                break

        for title in list(dict.fromkeys(filter(None, [sentence_case, common_name, stripped]))):
            try:
                _throttle()
                r = httpx.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={"action": "query", "titles": title,
                            "prop": "images", "format": "json",
                            "formatversion": "2", "imlimit": "50",
                            # Without this, querying a REDIRECT title (e.g.
                            # Chirp's "European Starling" -> Wikipedia's
                            # article "Common starling") returns nothing
                            # useful instead of following through to the
                            # article's images — confirmed directly:
                            # Wikipedia's canonical title for this
                            # species is "Common starling", not "European
                            # starling" at all, so this query was silently
                            # failing and falling through to the much worse
                            # "Starling" qualifier-stripped guess instead.
                            "redirects": "1"},
                    headers={"User-Agent": WIKIPEDIA_UA},
                    timeout=10, follow_redirects=True,
                )
                if r.status_code != 200:
                    continue
                pages = r.json().get("query", {}).get("pages", [])
                if not pages or pages[0].get("missing"):
                    continue
                for img in pages[0].get("images", []):
                    t = img.get("title", "").lower()
                    if any(kw in t for kw in range_keywords) and any(
                        t.endswith(e) for e in (".svg", ".png")
                    ):
                        fn = img["title"].replace("File:", "").replace(" ", "_")
                        url = self._get_commons_image_url(fn)
                        if url:
                            return url
            except Exception as e:
                logger.debug("Wikipedia range map error %s: %s", title, e)
        return None

    def _get_commons_image_url(self, filename: str) -> Optional[str]:
        """Construct deterministic Wikimedia Commons URL from filename."""
        import hashlib as _md5
        fn_clean = filename.replace(" ", "_")
        h = _md5.md5(fn_clean.encode()).hexdigest()
        url = f"https://upload.wikimedia.org/wikipedia/commons/{h[0]}/{h[:2]}/{fn_clean}"
        logger.info("Wikimedia URL: %s → %s", fn_clean[:50], url[:80])
        return url

    # ── iNaturalist ───────────────────────────────────────────────────────────

    def _fetch_inaturalist_full(self, query: str, taxon_id: Optional[int] = None) -> Optional[Dict]:
        if taxon_id:
            # Direct taxon ID lookup — skip the search entirely, guaranteed
            # to return the right taxon regardless of rank.
            detail = _get(f"https://api.inaturalist.org/v1/taxa/{taxon_id}")
        else:
            # Name search — deliberately no rank filter so higher-level taxa
            # (order, genus, etc.) are found correctly. The old rank=species
            # filter caused silent failures for non-species profiles like
            # Chiroptera (bat order), returning random mammals instead.
            search = _get(
                "https://api.inaturalist.org/v1/taxa",
                params={"q": query, "per_page": 1, "locale": "en"},
            )
            if not search or not search.get("results"):
                return None
            found_id = search["results"][0].get("id")
            if not found_id:
                return None
            detail = _get(f"https://api.inaturalist.org/v1/taxa/{found_id}")
        if not detail or not detail.get("results"):
            return None

        taxon = detail["results"][0]
        result = {
            "taxon_id": taxon_id,
            "scientific_name": taxon.get("name"),
            "wikipedia_url": taxon.get("wikipedia_url", ""),
            "wikipedia_summary": taxon.get("wikipedia_summary", ""),
            "order": None, "family": None,
            "photo_url": None, "photo_credit": None,
            "extra_photos": [],
            "conservation_status": None, "conservation_authority": None,
        }

        for anc in taxon.get("ancestors", []):
            rank = anc.get("rank", "")
            if rank == "order":
                result["order"] = anc.get("preferred_common_name") or anc.get("name")
            elif rank == "family":
                result["family"] = anc.get("name")

        dp = taxon.get("default_photo")
        if dp:
            result["photo_url"] = (
                dp.get("original_url")
                or _upsize_inat_photo_url(dp.get("large_url"))
                or dp.get("large_url") or dp.get("medium_url") or dp.get("small_url") or dp.get("square_url")
            )
            result["photo_credit"] = dp.get("attribution", "")

        extra = []
        # Raised from [1:6] (5 photos) to [1:13] (12 photos) to genuinely
        # deliver more photos per species, per request. The true upper bound
        # is whatever iNaturalist's own taxon_photos array contains
        # for a given species — some have many more than 12, some have far
        # fewer than even the old cap of 5. This slice just stops asking for
        # more than 12 once that many are available; it does not claim every
        # species will have 12. The frontend's PhotoGallery/
        # BirdPhotoGallery components already slice defensively to whatever
        # count is present, so raising this is the only change
        # needed to make more photos available end-to-end.
        for tp in taxon.get("taxon_photos", [])[1:13]:
            p = tp.get("photo", {})
            url = (
                p.get("original_url")
                or _upsize_inat_photo_url(p.get("large_url"))
                or p.get("large_url") or p.get("medium_url") or p.get("small_url") or p.get("square_url")
            )
            if url and url != result.get("photo_url"):
                # iNaturalist's documented fixed photo sizes (per their own
                # open-data docs): original 2048px, large 1024px, medium
                # 500px, small 240px, thumb 100px, square exactly 75x75px
                # cropped. medium_url is the right thumb size for this
                # gallery's ~150-220px grid tiles — sharp without being
                # wastefully large. The bug this fixes: when a given photo
                # entry has no medium_url at all, the previous fallback
                # dropped straight to square_url (75px), which then gets
                # CSS-upscaled 2-3x across the grid tile — always visibly
                # blurry. Falling to large_url instead when medium_url is
                # missing stays sharp; only square_url as an absolute last
                # resort, when literally nothing else is available.
                thumb = p.get("medium_url") or p.get("large_url") or p.get("small_url") or p.get("square_url", url)
                extra.append({
                    "url": url,
                    "thumb": thumb,
                    "credit": p.get("attribution", ""),
                })
        result["extra_photos"] = extra

        cs = taxon.get("conservation_status")
        if cs:
            result["conservation_status"] = cs.get("status_name") or cs.get("status")
            result["conservation_authority"] = cs.get("authority", "IUCN")

        return result

    def _resolve_scientific_name(self, common_name: str) -> Optional[str]:
        data = _get(
            "https://api.inaturalist.org/v1/taxa",
            params={"q": common_name, "rank": "species", "per_page": 1, "locale": "en"},
        )
        if data and data.get("results"):
            return data["results"][0].get("name")
        return None

    # ── eBird ─────────────────────────────────────────────────────────────────

    def _fetch_ebird_taxonomy(self, scientific_name: str, api_key: str) -> Optional[Dict]:
        data = _get(
            "https://api.ebird.org/v2/ref/taxonomy/ebird",
            params={"fmt": "json", "species": scientific_name},
            headers={"X-eBirdApiToken": api_key},
        )
        if data and isinstance(data, list) and data:
            e = data[0]
            return {
                "speciesCode": e.get("speciesCode"),
                "comName": e.get("comName"),
                "sciName": e.get("sciName"),
                "order": e.get("order"),
                "familyComName": e.get("familyComName"),
                "familySciName": e.get("familySciName"),
                "category": e.get("category"),
            }
        return None

    # ── iNaturalist sounds ────────────────────────────────────────────────────

    # DEFERRED (not started — noted for a future session, per explicit
    # request): explore better bird call/song sources beyond iNaturalist.
    #
    # Already investigated this session: Macaulay Library (Cornell's media
    # archive — much larger, more curated bird-call collection than
    # iNaturalist's) has NO public API for bulk-fetching raw audio files.
    # Confirmed via their own documentation: non-owned media "are not
    # available for personal download" outside a manual request/licensing
    # process. The only sanctioned access pattern is a per-clip embed
    # widget (an iframe pointing at Macaulay's own player, not a
    # downloadable file), explicitly capped at "20 distinct taxonomic
    # searches" before requiring a manual support ticket — that doesn't
    # fit this codebase's automated per-species background enrichment
    # pattern at all. Chirp's BirdProfile External Resources card already
    # links out to Macaulay's catalog search for the species' eBird
    # code, which is the legitimate way to surface their audio today.
    #
    # Worth evaluating when this is picked back up:
    # - Xeno-canto's API (mentioned in this project's own README/patent
    # docs as an intended source but not wired up anywhere in
    # this file currently — worth checking whether that's a gap
    # or just stale documentation).
    # - Whether Macaulay's embed widget could be used as a genuinely
    # different UI integration (an embedded player on the bird profile
    # page, not a stored/served file) rather than trying to fit it
    # into the existing "fetch and cache audio files" pattern that
    # iNaturalist sounds currently use.
    # - Whether reaching out to Cornell Lab (an already-verified
    # contact exists from this project's prior outreach — see
    # PATENT_APPLICATION.md / prior session notes) about API access
    # for this specific use case is worth pursuing, rather than
    # working around their stated terms.

    def _fetch_inaturalist_sounds(self, query: str, common_name: str = "") -> List[Dict]:
        species_dir = self._species_media_dir(common_name or query)
        data = _get(
            "https://api.inaturalist.org/v1/observations",
            params={
                "taxon_name": query, "sounds": "true",
                "quality_grade": "research", "order_by": "votes",
                "per_page": 10, "locale": "en",
            },
        )
        if not data or not data.get("results"):
            data = _get(
                "https://api.inaturalist.org/v1/observations",
                params={"taxon_name": query, "sounds": "true",
                        "order_by": "votes", "per_page": 10},
            )
        if not data or not data.get("results"):
            return []

        calls = []
        for obs in data["results"]:
            if len(calls) >= 8:
                break
            for sound in obs.get("sounds", [])[:2]:
                if len(calls) >= 8:
                    break
                file_url = sound.get("file_url", "")
                if not file_url:
                    continue
                ext = ".ogg"
                for e in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
                    if e in file_url.lower():
                        ext = e
                        break
                sound_id = sound.get("id", "")

                # Determine call type
                raw_type = (sound.get("subtype") or "").lower().strip()
                obs_tags = []
                for t in obs.get("tags", []):
                    if isinstance(t, dict):
                        obs_tags.append(t.get("name", "").lower())
                    elif isinstance(t, str):
                        obs_tags.append(t.lower())
                if not raw_type:
                    if any("song" in t for t in obs_tags): raw_type = "song"
                    elif any("call" in t for t in obs_tags): raw_type = "call"
                    elif any("alarm" in t for t in obs_tags): raw_type = "alarm call"
                    elif any("chip" in t for t in obs_tags): raw_type = "chip note"
                    elif any("flight" in t for t in obs_tags): raw_type = "flight call"
                    elif any("drum" in t or "tap" in t for t in obs_tags): raw_type = "drumming"
                    else: raw_type = "call"

                TYPE_MAP = {
                    "song": "Song", "call": "Call", "alarm": "Alarm Call",
                    "alarm call": "Alarm Call", "chip": "Chip Note",
                    "chip note": "Chip Note", "flight": "Flight Call",
                    "flight call": "Flight Call", "drumming": "Drumming",
                    "contact": "Contact Call", "": "Call",
                }
                call_type = TYPE_MAP.get(raw_type, raw_type.title() if raw_type else "Call")

                entry = {
                    "url": file_url, "source": "inaturalist",
                    "obs_id": str(obs.get("id", "")), "sound_id": str(sound_id),
                    "type": call_type, "quality": obs.get("quality_grade", ""),
                    "recordist": obs.get("user", {}).get("login", ""),
                    "country": (obs.get("place_guess") or "")[:40],
                    "license": sound.get("license_code", ""), "path": None,
                }
                if settings.media_download_enabled and species_dir:
                    dest = os.path.join(species_dir, "calls", f"inaturalist_{sound_id}{ext}")
                    if _download_file(file_url, dest):
                        entry["path"] = dest
                calls.append(entry)
        return calls

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _species_media_dir(self, name: str) -> str:
        safe = "".join(c if c.isalnum() or c in " -" else "_" for c in name)
        safe = safe.strip().replace(" ", "_")
        d = os.path.join(settings.media_dir, safe)
        Path(d).mkdir(parents=True, exist_ok=True)
        Path(d, "calls").mkdir(exist_ok=True)
        return d

    def _download_photo(self, photo_url: str, common_name: str, source: str) -> Optional[str]:
        species_dir = self._species_media_dir(common_name)
        ext = ".jpg"
        for e in (".png", ".webp", ".jpeg"):
            if e in photo_url.lower():
                ext = e
                break
        dest = os.path.join(species_dir, f"photo_{source}{ext}")
        return dest if _download_file(photo_url, dest) else None

def fetch_birdlife_range_map_standalone(common_name: str, scientific_name: str,
                                         output_path: str, db=None) -> bool:
    """
    Module-level wrapper so birds.py can call without separately
    instantiating BirdEnricher. Accepts an optional db session — without
    one, BirdLife URL resolution can't use the eBird en_HBW cross-walk
    (it needs the eBird API key from AppSettings) and silently falls back
    to the less-reliable site-search/guessed-slug strategies instead.
    """
    e = BirdEnricher(db) if db is not None else BirdEnricher.__new__(BirdEnricher)
    return e.fetch_birdlife_range_map(common_name, scientific_name, output_path)


def fetch_birdlife_range_map_full_standalone(common_name: str, scientific_name: str,
                                              output_path: str, db=None) -> dict:
    """
    Module-level wrapper returning the full result dict (ok/legend/error),
    so callers — the /range-map/birdlife endpoint and enrich_profile()'s
    eager pre-fetch — can persist the per-species legend alongside the map
    instead of only getting a bare success/failure bool.

    Accepts an optional db session for the same reason as
    fetch_birdlife_range_map_standalone above: without it,
    _resolve_birdlife_url_via_ebird_hbw has no way to read the eBird API
    key and the most reliable resolution strategy is skipped entirely —
    this was a gap until the call site in birds.py started passing
    its already-available db session through.
    """
    e = BirdEnricher(db) if db is not None else BirdEnricher.__new__(BirdEnricher)
    return e.fetch_birdlife_range_map_full(common_name, scientific_name, output_path)


def refetch_aab_range_map_standalone(common_name: str) -> dict:
    """
    Force a fresh AAB capture (URL + legend), for the on-demand refresh
    button now available on the AAB map tab — previously only BirdLife had
    a refresh control; AAB always served whatever was cached from
    enrichment with no way to re-capture from the UI without re-running
    full enrichment for the whole profile.

    Returns {"ok": bool, "url": str|None, "legend": list|None}. Does NOT
    download/save the image itself — the caller (the /range-map endpoint)
    downloads the returned URL the same way _resolve_range_map already does,
    so there's exactly one download code path rather than two.
    """
    e = BirdEnricher.__new__(BirdEnricher)
    url, legend = e._fetch_aab_range_map(common_name)
    return {"ok": bool(url), "url": url, "legend": legend}
