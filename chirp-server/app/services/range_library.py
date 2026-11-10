"""
Local range maps for every bird and bat.

Source: the iNaturalist Open Range Map Dataset (CC BY), as GeoPackages per
group: Aves (about 7,000 bird ranges, the files Settings → Range Maps already
downloads) and Mammalia (bats among them), plus taxonomy.csv to find the bats.
The files are refreshed when they're over 35 days old (iNaturalist updates
them about monthly).

A background job draws each profile's map once (range_map_geomodel.png,
beside its other maps), so every bird with a range has a local picture and
the other sources (eBird S&T, Cornell, BirdLife, Wikipedia) are extras or
fallbacks. Maps are redrawn after the data is refreshed.

The generic "Bat" profile gets one map per site location: every bat species
whose range covers the site, drawn together.
"""
import csv
import logging
import os
import re
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Optional

from . import geomodel_service as gm

logger = logging.getLogger("chirp.range_library")

BASE = "https://inaturalist-open-data.s3.us-east-1.amazonaws.com/geomodel/geopackages/latest/"
TAXONOMY_URL = BASE + "taxonomy.csv"
REFRESH_DAYS = 35
CHIROPTERA = "Chiroptera"


# ── Files ─────────────────────────────────────────────────────────────────────

def _files(data_dir: str) -> list[tuple[str, Path]]:
    d = gm._geomodel_dir(data_dir)
    urls = gm.GEOMODEL_URLS + gm.EXTRA_URLS + [TAXONOMY_URL]
    return [(u, d / Path(u).name) for u in urls]


def _stale(path: Path) -> bool:
    return not path.exists() or path.stat().st_size < 1000 or time.time() - path.stat().st_mtime > REFRESH_DAYS * 86400


def ensure_files(data_dir: str) -> bool:
    """Download missing or month-old files. True when every file is present."""
    gm._ensure_coastline(data_dir)
    ok = True
    for url, path in _files(data_dir):
        if not _stale(path):
            continue
        tmp = path.with_suffix(path.suffix + ".part")
        try:
            logger.info("Range library: downloading %s", path.name)
            req = urllib.request.Request(url, headers={"User-Agent": "Chirp/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
                while True:
                    block = resp.read(1 << 20)
                    if not block:
                        break
                    f.write(block)
            os.replace(tmp, path)
            _name_cache.clear()
            _bats_cache.clear()
        except Exception as e:
            logger.warning("Range library: %s not downloaded: %s", path.name, e)
            tmp.unlink(missing_ok=True)
            ok = ok and path.exists()
    return ok


def data_version(data_dir: str) -> float:
    """When the range data last changed (newest GeoPackage)."""
    times = [p.stat().st_mtime for p in gm._all_gpkg_paths(data_dir) if p.exists()]
    return max(times) if times else 0.0


# ── Lookups ───────────────────────────────────────────────────────────────────

_name_cache: dict[str, Optional[int]] = {}
_bats_cache: dict[str, list] = {}


def taxon_for(data_dir: str, scientific_name: str) -> Optional[int]:
    """The range dataset's taxon ID for a scientific name, if it has a range."""
    name = (scientific_name or "").strip()
    if not name:
        return None
    if name in _name_cache:
        return _name_cache[name]
    found = None
    for path in gm._all_gpkg_paths(data_dir):
        if not path.exists():
            continue
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                schema = gm._discover_schema(conn)
                if not schema:
                    continue
                row = conn.execute(f"SELECT {schema[1]} FROM '{schema[0]}' WHERE name=? LIMIT 1", (name,)).fetchone()
                if row:
                    found = int(row[0])
                    break
            finally:
                conn.close()
        except Exception as e:
            logger.debug("Range library lookup %s in %s: %s", name, path.name, e)
    _name_cache[name] = found
    return found


def bat_taxa(data_dir: str) -> set[int]:
    """Every species-level taxon under the bat order, from taxonomy.csv."""
    path = gm._geomodel_dir(data_dir) / "taxonomy.csv"
    if not path.exists():
        return set()
    parent, rank, order_id = {}, {}, None
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                tid = int(r["taxon_id"])
            except (TypeError, ValueError):
                continue
            parent[tid] = int(r["parent_taxon_id"]) if r.get("parent_taxon_id") else None
            rank[tid] = r.get("rank")
            if r.get("name") == CHIROPTERA:
                order_id = tid
    if order_id is None:
        return set()
    out = set()
    for tid, rk in rank.items():
        if rk != "species":
            continue
        p, hops = parent.get(tid), 0
        while p and hops < 12:
            if p == order_id:
                out.add(tid)
                break
            p, hops = parent.get(p), hops + 1
    return out


def _contains(ring, lon: float, lat: float) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def bats_at(data_dir: str, lat: float, lon: float) -> list[int]:
    """Bat species whose range covers this place (or comes within ~50 km)."""
    key = f"{lat:.1f},{lon:.1f}"
    if key in _bats_cache:
        return _bats_cache[key]
    bats = bat_taxa(data_dir)
    found = []
    if bats:
        for path in gm._all_gpkg_paths(data_dir):
            if not path.exists() or "Mammalia" not in path.name:
                continue
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                schema = gm._discover_schema(conn)
                if not schema:
                    continue
                tbl, tc, gc = schema
                for tid, blob in conn.execute(f"SELECT {tc}, {gc} FROM '{tbl}'"):
                    if int(tid) not in bats:
                        continue
                    rings = gm._parse_gpkg_geom(bytes(blob) if isinstance(blob, memoryview) else blob)
                    near = [(lon + dx, lat + dy) for dx in (0, -0.5, 0.5) for dy in (0, -0.4, 0.4)]
                    if any(_contains(ring, x, y) for ring in rings for (x, y) in near):
                        found.append(int(tid))
            finally:
                conn.close()
    _bats_cache[key] = found
    return found


# ── Map files ─────────────────────────────────────────────────────────────────

def species_dir(media_dir: str, common_name: str) -> str:
    return os.path.join(media_dir, re.sub(r"[^a-zA-Z0-9_-]", "_", (common_name or "").lower()))


def generic_bat(p) -> bool:
    return bool(getattr(p, "is_bat", False)) and (p.label == "Bat" or p.common_name == "Bat")


def map_file(media_dir: str, p, lat: Optional[float] = None, lon: Optional[float] = None) -> Optional[str]:
    """Where this profile's local map is (or would be) kept. The generic Bat
    profile's map depends on the site's location; without one it has none."""
    folder = species_dir(media_dir, p.common_name)
    if generic_bat(p):
        if lat is None or lon is None:
            return None
        return os.path.join(folder, f"range_map_geomodel_{lat:.1f}_{lon:.1f}.png")
    return os.path.join(folder, "range_map_geomodel.png")


def have_map(path: Optional[str]) -> bool:
    return bool(path) and os.path.exists(path) and os.path.getsize(path) > 1000


# ── Drawing every map ─────────────────────────────────────────────────────────

def _sessions():
    """(site name, session) for every site's database."""
    try:
        from ..instance_registry import iter_instance_sessions
        yield from iter_instance_sessions()
        return
    except ImportError:
        pass
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        yield type("Site", (), {"name": "this site"})(), db
    finally:
        db.close()


def draw_all(stop=None, pause: float = 0.2) -> dict:
    """Draw every missing or out-of-date map. Returns counts."""
    from ..config import settings as cfg
    from ..models import AppSettings, BirdProfile

    counts = {"drawn": 0, "kept": 0, "no_range": 0, "failed": 0}
    if not ensure_files(cfg.data_dir):
        logger.info("Range library: some files are missing; drawing what's possible")
    version = data_version(cfg.data_dir)
    done = set()
    for site, db in _sessions():
        s = db.query(AppSettings).first()
        lat, lon = (getattr(s, "latitude", None), getattr(s, "longitude", None)) if s else (None, None)
        for p in db.query(BirdProfile).all():
            if stop is not None and stop.is_set():
                return counts
            path = map_file(cfg.media_dir, p, lat, lon)
            if not path or path in done:
                continue
            done.add(path)
            if have_map(path) and os.path.getmtime(path) >= version:
                counts["kept"] += 1
                continue
            if generic_bat(p):
                ids, title = bats_at(cfg.data_dir, lat, lon), "Bats near you — iNaturalist ranges"
            else:
                # iNaturalist's own ID first (the dataset uses iNaturalist taxa), then the scientific name.
                ids = [t for t in dict.fromkeys([p.inaturalist_id, taxon_for(cfg.data_dir, p.scientific_name)]) if t]
                title = ""
            if not ids:
                counts["no_range"] += 1
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path[:-4] + ".part.png"
            try:
                ok = False
                for attempt in ([ids] if generic_bat(p) else [[t] for t in ids]):
                    ok = gm.render_range_map(attempt, cfg.data_dir, tmp, common_name=p.common_name or "", title=title)
                    if ok:
                        break
                if ok and os.path.exists(tmp):
                    os.replace(tmp, path)
                    counts["drawn"] += 1
                else:
                    counts["no_range"] += 1
            except Exception as e:
                counts["failed"] += 1
                logger.warning("Range library: %s not drawn: %s", p.common_name, e)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
            time.sleep(pause)
    logger.info("Range library: %s", counts)
    return counts


def loop(stop, first_delay: int = 180):
    """Draw maps soon after startup, then check once a day."""
    if stop.wait(first_delay):
        return
    while True:
        try:
            draw_all(stop)
        except Exception as e:
            logger.warning("Range library pass failed: %s", e)
        if stop.wait(86400):
            return
