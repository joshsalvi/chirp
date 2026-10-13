"""
iNaturalist Geomodel Range Map Service
Reads from locally cached GeoPackage files to render species range maps.
The GeoPackage format (SQLite) stores hexagonal grid predictions at H3
resolution 6 with a score per taxon_id.
"""
import logging
import sqlite3
import struct
import threading
from pathlib import Path

logger = logging.getLogger("chirp.geomodel")

GEOMODEL_URLS = [
    "https://inaturalist-open-data.s3.us-east-1.amazonaws.com/geomodel/geopackages/latest/iNaturalist_geomodel_Aves_1.gpkg",
    "https://inaturalist-open-data.s3.us-east-1.amazonaws.com/geomodel/geopackages/latest/iNaturalist_geomodel_Aves_2.gpkg",
]
COASTLINE_URL = "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"

_download_progress: dict[str, dict] = {}   # filename → {status, downloaded, total}
_download_lock = threading.Lock()


# ── Paths ─────────────────────────────────────────────────────────────────────

def _geomodel_dir(data_dir: str) -> Path:
    d = Path(data_dir) / "geomodels"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _gpkg_paths(data_dir: str) -> list[Path]:
    d = _geomodel_dir(data_dir)
    return [d / Path(u).name for u in GEOMODEL_URLS]

def _coastline_path(data_dir: str) -> Path:
    return _geomodel_dir(data_dir) / "countries.geojson"


# ── Download status ────────────────────────────────────────────────────────────

def get_status(data_dir: str) -> dict:
    paths = _gpkg_paths(data_dir)
    result = {"files": {}, "ready": False, "downloading": False}
    all_ready = True
    for url, path in zip(GEOMODEL_URLS, paths):
        name = path.name
        with _download_lock:
            prog = _download_progress.get(name, {})
        if prog.get("status") == "downloading":
            result["downloading"] = True
            result["files"][name] = {
                "status": "downloading",
                "downloaded_mb": round(prog.get("downloaded", 0) / 1e6, 1),
                "total_mb": round(prog.get("total", 0) / 1e6, 1),
                "pct": prog.get("pct", 0),
            }
            all_ready = False
        elif path.exists() and path.stat().st_size > 1_000_000:
            size_gb = path.stat().st_size / 1e9
            result["files"][name] = {"status": "ready", "size_gb": round(size_gb, 2)}
        else:
            result["files"][name] = {"status": "missing"}
            all_ready = False
    result["ready"] = all_ready
    return result


def start_download(data_dir: str) -> None:
    """Start background download of both GeoPackage files (non-blocking)."""
    t = threading.Thread(target=_download_all, args=(data_dir,), daemon=True)
    t.start()


def _download_all(data_dir: str) -> None:
    import urllib.request
    paths = _gpkg_paths(data_dir)
    # Also download the small coastline file if missing
    _ensure_coastline(data_dir)
    for url, path in zip(GEOMODEL_URLS, paths):
        if path.exists() and path.stat().st_size > 1_000_000:
            logger.info("Geomodel %s already downloaded", path.name)
            continue
        logger.info("Downloading geomodel: %s → %s", url, path)
        name = path.name
        with _download_lock:
            _download_progress[name] = {"status": "downloading", "downloaded": 0, "total": 0, "pct": 0}
        try:
            tmp = path.with_suffix(".part")
            req = urllib.request.Request(url, headers={"User-Agent": "Chirp/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk = 1 << 20  # 1 MB chunks
                with open(tmp, "wb") as f:
                    while True:
                        block = resp.read(chunk)
                        if not block:
                            break
                        f.write(block)
                        downloaded += len(block)
                        pct = int(100 * downloaded / total) if total else 0
                        with _download_lock:
                            _download_progress[name] = {
                                "status": "downloading",
                                "downloaded": downloaded,
                                "total": total,
                                "pct": pct,
                            }
            tmp.rename(path)
            with _download_lock:
                _download_progress[name] = {"status": "ready"}
            logger.info("Geomodel %s downloaded (%.1f GB)", name, path.stat().st_size / 1e9)
        except Exception as e:
            with _download_lock:
                _download_progress[name] = {"status": "error", "error": str(e)}
            logger.error("Geomodel download failed for %s: %s", name, e)


def _ensure_coastline(data_dir: str) -> None:
    """Download a small world countries GeoJSON for the basemap if not present."""
    import urllib.request
    path = _coastline_path(data_dir)
    if path.exists() and path.stat().st_size > 1000:
        return
    try:
        logger.info("Downloading world coastline basemap…")
        req = urllib.request.Request(COASTLINE_URL, headers={"User-Agent": "Chirp/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            path.write_bytes(resp.read())
        logger.info("Coastline basemap downloaded (%s KB)", path.stat().st_size // 1024)
    except Exception as e:
        logger.warning("Coastline download failed: %s", e)


# ── GeoPackage reading ─────────────────────────────────────────────────────────

def _parse_gpkg_geom(blob: bytes):
    """
    Parse a GeoPackage binary geometry blob to raw polygon exterior ring coords.
    GeoPackage header: 2-byte magic (GP) + 1-byte version + 1-byte flags +
                       4-byte SRS_ID + optional envelope + WKB geometry.
    Returns a LIST OF RINGS — one list of (lon, lat) tuples per separate
    polygon/sub-polygon — not a single flattened list. iNaturalist's
    geomodel stores each taxon's range as many disjoint hexagonal grid
    cells, frequently as a single MultiPolygon row; treating all of them
    as one ring (the original behavior) made ax.fill() draw one giant
    self-intersecting path connecting unrelated hexagons across the globe
    — exactly the star-burst/triangle artifact seen in production renders.
    Returns [] on failure.
    """
    if not blob or len(blob) < 8:
        return []
    try:
        magic = blob[:2]
        if magic != b'GP':
            return []
        flags = blob[3]
        envelope_type = (flags & 0x0E) >> 1  # bits 1-3
        # Envelope sizes in bytes: 0=none, 1=2D(32), 2=3D(48), 3=3D(48), 4=4D(64)
        env_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
        wkb_start = 8 + env_sizes.get(envelope_type, 0)
        wkb = blob[wkb_start:]
        return _parse_wkb_polygon(wkb)
    except Exception:
        return []


def _parse_wkb_polygon(wkb: bytes) -> list:
    """
    Minimal WKB parser — returns a LIST OF RINGS (one per Polygon, or one
    per sub-polygon of a MultiPolygon), each ring itself a list of
    (lon, lat) exterior-ring coordinate tuples. Each ring must be rendered
    as its own separate shape — concatenating multiple sub-polygons'
    points together (the original behavior here) produces a single
    self-intersecting path instead of N separate hexagons.
    """
    if len(wkb) < 5:
        return []
    byte_order = wkb[0]          # 0=big-endian, 1=little-endian
    le = byte_order == 1
    fmt = '<' if le else '>'

    def u32(offset): return struct.unpack_from(fmt + 'I', wkb, offset)[0]
    def f64(offset): return struct.unpack_from(fmt + 'd', wkb, offset)[0]

    geom_type = u32(1)
    polygons = []  # list of rings, each ring a list of (lon, lat)

    if geom_type == 3:   # Polygon
        n_rings = u32(5)
        pos = 9
        for r in range(n_rings):
            n_pts = u32(pos); pos += 4
            if r == 0:  # exterior ring only
                pts = [(f64(pos + i*16), f64(pos + i*16 + 8)) for i in range(n_pts)]
                polygons.append(pts)
            pos += n_pts * 16

    elif geom_type == 6:  # MultiPolygon
        n_poly = u32(5)
        pos = 9
        for _ in range(n_poly):
            pos += 1  # byte order
            pos += 4  # type
            n_rings = u32(pos); pos += 4
            for r in range(n_rings):
                n_pts = u32(pos); pos += 4
                if r == 0:  # exterior ring only — each sub-polygon is its
                            # own separate hexagon and must stay separate
                    pts = [(f64(pos + i*16), f64(pos + i*16 + 8)) for i in range(n_pts)]
                    polygons.append(pts)
                pos += n_pts * 16

    return polygons


def _discover_schema(conn: sqlite3.Connection):
    """
    Auto-discover feature table name and column names for taxon_id and
    geometry in this GeoPackage. Returns (table, taxon_col, geom_col) or
    None.

    No score/probability column is looked for here — confirmed directly
    from a real production schema (via /api/v1/settings/geomodel/debug)
    that this product has none: the real columns are fid/geom/taxon_id/
    parent_taxon_id/name/rank/iconic_taxon_id/iconic_taxon_name/
    geomodel_version. iNaturalist's geomodel range product is a binary
    presence polygon per taxon, not a per-cell abundance/likelihood
    gradient.
    """
    try:
        feature_tables = [
            r[0] for r in conn.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type='features'"
            ).fetchall()
        ]
    except Exception:
        # Fallback: list all tables
        feature_tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            if r[0] not in ("gpkg_contents", "gpkg_geometry_columns",
                            "gpkg_spatial_ref_sys", "gpkg_tile_matrix",
                            "gpkg_tile_matrix_set", "sqlite_sequence")
        ]

    for tbl in feature_tables:
        try:
            cols = {r[1].lower(): r[1] for r in conn.execute(f"PRAGMA table_info('{tbl}')").fetchall()}
        except Exception:
            continue

        # Find taxon column — try many naming conventions used by iNat geopackages
        taxon_col = next((cols[c] for c in (
            "taxon_id", "taxonid", "taxon", "id", "species_id", "speciesid", "fid",
        ) if c in cols), None)
        # Find geometry column
        geom_col  = next((cols[c] for c in (
            "geom", "geometry", "shape", "geom_wkb", "the_geom", "wkb_geometry",
        ) if c in cols), None)
        # NOTE: there is no score/probability/likelihood column in this
        # product, confirmed directly from the real schema via
        # /api/v1/settings/geomodel/debug: the only columns are
        # fid/geom/taxon_id/parent_taxon_id/name/rank/iconic_taxon_id/
        # iconic_taxon_name/geomodel_version — pure taxonomy metadata plus
        # the range polygon itself. iNaturalist's geomodel range product
        # is a binary presence polygon per taxon ("the species occurs
        # somewhere within this shape"), not a per-cell abundance/
        # likelihood gradient. A uniform render is the correct, complete
        # representation of this data, not a fallback for missing data —
        # see render_range_map() below, which no longer pretends
        # otherwise.

        if taxon_col and geom_col:
            return tbl, taxon_col, geom_col

    return None


# ── Rendering ─────────────────────────────────────────────────────────────────

def render_range_map(taxon_id: int, data_dir: str, output_path: str,
                     common_name: str = "") -> bool:
    """
    Query the geopackage for the taxon, render a PNG range map.
    Returns True on success.
    """
    import json
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    # Find which gpkg file has this taxon
    gpkg_file = None
    schema     = None
    conn_used  = None
    for path in _gpkg_paths(data_dir):
        if not path.exists() or path.stat().st_size < 1_000_000:
            continue
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            s = _discover_schema(conn)
            if s is None:
                conn.close()
                continue
            tbl, tc, gc = s
            row = conn.execute(f"SELECT COUNT(*) FROM '{tbl}' WHERE {tc}=?", (taxon_id,)).fetchone()
            if row and row[0] > 0:
                gpkg_file = path
                schema = s
                conn_used = conn
                break
            conn.close()
        except Exception as e:
            logger.debug("Geomodel file error %s: %s", path, e)

    if not gpkg_file or not schema or not conn_used:
        logger.warning(
            "Geomodel: taxon %d not found in any gpkg file. "
            "Try GET /api/v1/settings/geomodel/debug to inspect the schema.",
            taxon_id,
        )
        return False

    tbl, taxon_col, geom_col = schema
    logger.info("Rendering geomodel map: taxon=%d in %s.%s (taxon_col=%s, geom_col=%s)",
                taxon_id, gpkg_file.name, tbl, taxon_col, geom_col)

    try:
        rows = conn_used.execute(
            f"SELECT {geom_col} FROM '{tbl}' WHERE {taxon_col}=?",
            (taxon_id,),
        ).fetchall()
    finally:
        conn_used.close()

    if not rows:
        logger.warning("Geomodel: no geometry rows for taxon %d", taxon_id)
        return False

    # Parse geometries — every polygon represents the same thing (this
    # taxon's range), so there is nothing per-polygon to vary the color
    # by. Confirmed directly from the real schema: no score/probability/
    # likelihood column exists in this product at all.
    polys = []
    for (blob,) in rows:
        # _parse_gpkg_geom returns a LIST OF RINGS — one per separate
        # sub-polygon (a MultiPolygon row is often many disjoint hexagons,
        # which must each be rendered as their own shape, not flattened
        # into one self-intersecting path — see _parse_wkb_polygon's
        # docstring for the rendering artifact this previously caused).
        rings = _parse_gpkg_geom(bytes(blob) if isinstance(blob, memoryview) else blob)
        for ring in rings:
            if len(ring) >= 3:
                polys.append(ring)

    if not polys:
        logger.warning("Geomodel: no valid polygons for taxon %d", taxon_id)
        return False

    # ── Figure setup ──────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("#0e1a14")
    ax.set_facecolor("#0e1a14")

    # World basemap
    coast_path = _coastline_path(data_dir)
    if coast_path.exists():
        try:
            with open(coast_path) as f:
                world = json.load(f)
            for feat in world.get("features", []):
                geom = feat.get("geometry", {})
                gtype = geom.get("type", "")
                coords_list = geom.get("coordinates", [])
                if gtype == "Polygon":
                    for ring in coords_list[:1]:
                        xs, ys = zip(*ring)
                        ax.fill(xs, ys, color="#1a2e22", linewidth=0)
                        ax.plot(xs, ys, color="#2d4a38", linewidth=0.3)
                elif gtype == "MultiPolygon":
                    for poly in coords_list:
                        for ring in poly[:1]:
                            xs, ys = zip(*ring)
                            ax.fill(xs, ys, color="#1a2e22", linewidth=0)
                            ax.plot(xs, ys, color="#2d4a38", linewidth=0.3)
        except Exception as e:
            logger.debug("Basemap render error: %s", e)

    # Species range polygons — every polygon gets the SAME color, since
    # this product has no per-polygon score to vary it by (confirmed
    # directly from the real schema: no score/probability/likelihood
    # column exists at all). This is the correct, complete representation
    # of "the iNaturalist community geomodel estimates this species
    # occurs somewhere within this shape" — not a placeholder standing in
    # for missing gradient data.
    RANGE_COLOR = "#4ade80"
    for coords in polys:
        xs, ys = zip(*coords)
        ax.fill(xs, ys, color=RANGE_COLOR, alpha=0.55, linewidth=0)

    # Map bounds
    all_x = [c[0] for poly in polys for c in poly]
    all_y = [c[1] for poly in polys for c in poly]
    pad_x = (max(all_x) - min(all_x)) * 0.08 or 5
    pad_y = (max(all_y) - min(all_y)) * 0.08 or 5
    ax.set_xlim(max(-180, min(all_x) - pad_x), min(180, max(all_x) + pad_x))
    ax.set_ylim(max(-90,  min(all_y) - pad_y), min(90,  max(all_y) + pad_y))

    ax.set_aspect("equal")
    ax.axis("off")

    # Legend — describes what this data actually is (a single estimated
    # range, not a likelihood scale). The previous "High likelihood /
    # Low likelihood" legend implied a gradient this product has never
    # actually contained, confirmed directly from its real schema.
    legend_patches = [
        mpatches.Patch(color=RANGE_COLOR, alpha=0.55, label="Estimated range"),
    ]
    ax.legend(handles=legend_patches, loc="lower left", framealpha=0.6,
              facecolor="#0e1a14", edgecolor="#2d4a38", labelcolor="white",
              fontsize=7)

    title = f"{common_name} — iNaturalist Community Range" if common_name else "iNaturalist Community Range"
    ax.set_title(title, color="#86efac", fontsize=9, pad=6)

    plt.tight_layout(pad=0.3)
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    logger.info("Geomodel map saved: %s", output_path)
    return True
