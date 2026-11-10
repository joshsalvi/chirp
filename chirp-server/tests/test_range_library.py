"""Local range maps (services/range_library.py) on a tiny made-up dataset."""
import sqlite3
import struct
import threading


def _blob(cx, cy, r=1.0):
    """A GeoPackage geometry: one square polygon around (cx, cy)."""
    ring = [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r), (cx - r, cy - r)]
    wkb = struct.pack("<BII", 1, 3, 1) + struct.pack("<I", len(ring)) + b"".join(struct.pack("<dd", *p) for p in ring)
    return b"GP" + bytes([0, 1]) + struct.pack("<i", 4326) + wkb


def _gpkg(path, rows):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE gpkg_contents (table_name TEXT, data_type TEXT)")
    c.execute("INSERT INTO gpkg_contents VALUES ('ranges', 'features')")
    c.execute("CREATE TABLE ranges (fid INTEGER PRIMARY KEY, geom BLOB, taxon_id INTEGER, name TEXT)")
    for tid, name, cx, cy in rows:
        c.execute("INSERT INTO ranges (geom, taxon_id, name) VALUES (?, ?, ?)", (_blob(cx, cy), tid, name))
    c.commit()
    c.close()
    # Real files are hundreds of MB; the code skips anything under 1 MB.
    with open(path, "ab") as f:
        f.write(b"\0" * 1_100_000)


def _setup(tmp_path, monkeypatch):
    from app.config import settings
    from app.services import geomodel_service as gm
    from app.services import range_library as rl
    data = tmp_path / "data"
    geo = data / "geomodels"
    geo.mkdir(parents=True)
    monkeypatch.setattr(settings, "data_dir", str(data))
    monkeypatch.setattr(settings, "media_dir", str(tmp_path / "media"))
    _gpkg(geo / "iNaturalist_geomodel_Aves_1.gpkg", [(9083, "Cardinalis cardinalis", -80, 35)])
    _gpkg(geo / "iNaturalist_geomodel_Aves_2.gpkg", [])
    _gpkg(geo / "iNaturalist_geomodel_Mammalia.gpkg",
          [(41000, "Eptesicus fuscus", -71.3, 42.3), (41001, "Lasiurus borealis", -71, 42), (41002, "Myotis far", 10, 50),
           (42000, "Odocoileus virginianus", -71.3, 42.3)])
    (geo / "taxonomy.csv").write_text(
        "taxon_id,parent_taxon_id,name,rank_level,rank,iconic_taxon_id,is_leaf\n"
        "40268,,Chiroptera,40,order,40151,False\n"
        "40269,40268,Vespertilionidae,30,family,40151,False\n"
        "41000,40269,Eptesicus fuscus,10,species,40151,True\n"
        "41001,40269,Lasiurus borealis,10,species,40151,True\n"
        "41002,40269,Myotis far,10,species,40151,True\n"
        "42000,,Odocoileus virginianus,10,species,40151,True\n")
    (geo / "countries.geojson").write_text('{"type":"FeatureCollection","features":[]}')
    monkeypatch.setattr(rl, "ensure_files", lambda d: True)
    rl._name_cache.clear()
    rl._bats_cache.clear()
    return rl, gm, settings


def test_lookups(tmp_path, monkeypatch):
    rl, gm, _ = _setup(tmp_path, monkeypatch)
    assert rl.taxon_for(str(tmp_path / "data"), "Cardinalis cardinalis") == 9083
    assert rl.taxon_for(str(tmp_path / "data"), "Nobody here") is None
    assert rl.bat_taxa(str(tmp_path / "data")) == {41000, 41001, 41002}       # not the deer
    assert sorted(rl.bats_at(str(tmp_path / "data"), 42.28, -71.35)) == [41000, 41001]


def test_draw_all(tmp_path, monkeypatch, client):
    rl, gm, settings = _setup(tmp_path, monkeypatch)
    from app.database import SessionLocal
    from app.models import AppSettings, BirdProfile
    db = SessionLocal()
    s = db.query(AppSettings).first()
    if s is None:
        s = AppSettings(id=1)
        db.add(s)
    s.latitude, s.longitude = 42.28, -71.35
    for pid, label, name, sci, bat in (("rl-card", "x_Northern Cardinal", "Northern Cardinal", "Cardinalis cardinalis", False),
                                       ("rl-bat", "Bat", "Bat", None, True),
                                       ("rl-none", "x_Mystery Bird", "Mystery Bird", "Avis ignota", False)):
        if not db.get(BirdProfile, pid):
            db.add(BirdProfile(id=pid, label=label, common_name=name, scientific_name=sci, is_bat=bat))
    db.commit()
    db.close()

    def one_site():                       # the test server's single database
        d = SessionLocal()
        try:
            yield type("Site", (), {"name": "test"})(), d
        finally:
            d.close()
    monkeypatch.setattr(rl, "_sessions", one_site)

    counts = rl.draw_all(stop=threading.Event(), pause=0)
    media = tmp_path / "media"
    assert (media / "northern_cardinal" / "range_map_geomodel.png").stat().st_size > 1000
    assert (media / "bat" / "range_map_geomodel_42.3_-71.3.png").stat().st_size > 1000
    assert counts["drawn"] >= 2 and counts["no_range"] >= 1
    again = rl.draw_all(stop=threading.Event(), pause=0)                       # kept, not redrawn
    assert again["drawn"] == 0 and again["kept"] >= 2

    from app.api.lite import range_map_of
    db = SessionLocal()
    bat = db.get(BirdProfile, "rl-bat")
    assert range_map_of(bat, db.query(AppSettings).first())["range_map"] == "/api/v1/birds/rl-bat/range-map/local"
    db.close()
    r = client.get("/api/v1/birds/rl-bat/range-map/local")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
