"""0.5.10.m: night callers use their own floors, the global threshold, or a
choice per species (Settings → Detection → Night-Caller Thresholds)."""
from app.services.birdnet_pass import (NIGHT_SPECIES_MIN_CONF, OWL_MIN_CONF, species_required,
                                       uses_night_floor)


def test_species_required_modes():
    assert species_required("Barred Owl", 0.3) == OWL_MIN_CONF
    assert species_required("Common Nighthawk", 0.3) == NIGHT_SPECIES_MIN_CONF
    assert species_required("Blue Jay", 0.3) == 0.3
    assert species_required("Barred Owl", 0.3, mode="global") == 0.3
    assert species_required("Common Nighthawk", 0.3, mode="global") == 0.3
    per = {"Great Horned Owl": False}
    assert species_required("Great Horned Owl", 0.3, mode="per_species", per_species=per) == 0.3
    assert species_required("Barred Owl", 0.3, mode="per_species", per_species=per) == OWL_MIN_CONF
    # a per-species score wins over every mode
    assert species_required("Barred Owl", 0.3, {"Barred Owl": 0.12}, mode="global") == 0.12
    assert not uses_night_floor("Blue Jay")
    assert uses_night_floor("Barn Owl") and not uses_night_floor("Barn Owl", "global")


def test_settings_round_trip_and_device_config(client):
    from app.database import SessionLocal
    from app.models import Device
    from app.api.devices import with_night_rule
    from app.models import AppSettings
    r = client.put("/api/v1/settings", json={"night_threshold_mode": "bogus"})
    assert r.status_code == 400
    r = client.put("/api/v1/settings", json={"night_threshold_mode": "per_species",
                                             "night_threshold_species": {"Great Horned Owl": False,
                                                                         "Barred Owl": True, "Blue Jay": False}})
    assert r.status_code == 200, r.text
    got = client.get("/api/v1/settings").json()
    assert got["night_threshold_mode"] == "per_species"
    assert got["night_threshold_species"] == {"Great Horned Owl": False, "Barred Owl": True}
    db = SessionLocal()
    try:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        cfg = {"detection": {"birdnet": {"min_confidence": 0.3}}}
        out = with_night_rule(cfg, s)
        assert out["detection"]["birdnet"]["night_global_species"] == ["Great Horned Owl"]
        assert out["detection"]["birdnet"]["night_species_min_confidence"] == NIGHT_SPECIES_MIN_CONF
        assert "night_global_species" not in cfg["detection"]["birdnet"]   # copy, not in place
        s.night_threshold_mode = "global"
        db.commit()
        out = with_night_rule(cfg, s)
        assert out["detection"]["birdnet"]["night_species_min_confidence"] == 0.3
        assert out["detection"]["birdnet"]["night_global_species"] == []
        s.night_threshold_mode = "night"
        db.commit()
        own = {"detection": {"birdnet": {"min_confidence": 0.35, "night_species_min_confidence": 0.2}}}
        assert with_night_rule(own, s)["detection"]["birdnet"]["night_species_min_confidence"] == 0.2
        assert db.query(Device).count() >= 0
    finally:
        s.night_threshold_mode, s.night_threshold_species = "night", {}
        db.commit()
        db.close()


def test_night_species_endpoint(client):
    r = client.get("/api/v1/near-misses/night-species")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "night"
    owl = next(i for i in d["items"] if i["species"] == "Barred Owl")
    assert owl["night_floor"] is True and owl["required"] == OWL_MIN_CONF


def test_global_mode_drops_owl_protection(client):
    from app.api.recordings import _night_caller_protects
    assert _night_caller_protects("Great Horned Owl", 0.25, "server")
    assert not _night_caller_protects("Great Horned Owl", 0.25, "server", night={"mode": "global"})
    assert not _night_caller_protects("Great Horned Owl", 0.25, "server",
                                      night={"mode": "per_species", "per_species": {"Great Horned Owl": False}})
