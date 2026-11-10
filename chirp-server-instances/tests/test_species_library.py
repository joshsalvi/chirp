"""Shared species library: a location's new profile comes from another
location's enrichment instead of the web; regional and personal fields stay put."""
import os
import sys
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db(fname):
    from sqlalchemy.orm import sessionmaker
    from app.instance_registry import get_engine_for_instance, provision_instance_database
    provision_instance_database(fname)
    return sessionmaker(bind=get_engine_for_instance(fname))()


def test_library_fills_new_profile(tmp_path, monkeypatch):
    from app.models import BirdProfile
    from app.registry_db import init_registry_db
    from app.services import bird_enricher, species_library as lib
    init_registry_db()
    tag = uuid.uuid4().hex[:6]
    label = f"Testus avis{tag}_Test Warbler {tag}"
    photo = tmp_path / "warbler.jpg"
    photo.write_bytes(b"jpg")

    a = _db(f"liba-{tag}.db")
    p = BirdProfile(label=label, common_name=f"Test Warbler {tag}", scientific_name=f"Testus avis{tag}",
                    description="A small test bird.", description_sections=[{"section": "Overview", "text": "A small test bird."}],
                    photo_path=str(photo), photo_url="https://example.org/w.jpg", call_media=[{"url": "u"}],
                    ebird_species_code="tstwar", aab_cool_facts=["Sings at dawn."], aab_fetched_at=datetime.utcnow(),
                    monthly_frequency=[0.9] * 12, notes="Seen at the feeder", ai_presence_summary="Common here",
                    enrichment_complete=True, last_enriched=datetime.utcnow())
    a.add(p)
    a.commit()
    bird_enricher.BirdEnricher(a)._share_with_library(p)
    a.close()

    # A second location hears the bird: no web enrichment, one regional lookup.
    b = _db(f"libb-{tag}.db")
    monkeypatch.setattr(bird_enricher.BirdEnricher, "_do_enrich",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("went to the web")))
    monkeypatch.setattr(bird_enricher.BirdEnricher, "_fetch_and_set_monthly_frequency",
                        lambda self, prof, key: setattr(prof, "monthly_frequency", [0.2] * 12))
    got = bird_enricher.BirdEnricher(b).ensure_profile(label)
    assert got.description == "A small test bird." and got.photo_path == str(photo)
    assert got.ebird_species_code == "tstwar" and got.aab_cool_facts == ["Sings at dawn."]
    assert isinstance(got.aab_fetched_at, datetime)
    assert got.monthly_frequency == [0.2] * 12            # regional, fetched here
    assert got.notes is None and got.ai_presence_summary is None
    assert got.enrichment_complete and got.id != p.id
    b.close()

    # A copy older than a month, or missing its photo, isn't used.
    e = lib.get(label)
    assert e is not None
    photo.unlink()
    assert lib.get(label) is None
    photo.write_bytes(b"jpg")
    from app.registry_db import RegistrySessionLocal
    reg = RegistrySessionLocal()
    reg.query(lib.SpeciesLibraryEntry).filter(lib.SpeciesLibraryEntry.label == label).update(
        {"enriched_at": datetime.utcnow() - timedelta(days=40)})
    reg.commit()
    reg.close()
    assert lib.get(label) is None


def test_backfill_and_bats(tmp_path):
    from app.models import BirdProfile
    from app.registry_db import RegistrySessionLocal, init_registry_db
    from app.registry_models import Instance
    from app.services import species_library as lib
    init_registry_db()
    tag = uuid.uuid4().hex[:6]
    fname = f"libc-{tag}.db"
    db = _db(fname)
    db.add(BirdProfile(label=f"Seedus x{tag}_Seed Sparrow {tag}", common_name=f"Seed Sparrow {tag}",
                       description="d", enrichment_complete=True, last_enriched=datetime.utcnow()))
    db.add(BirdProfile(label=f"Myotis y{tag}_Bat {tag}", common_name=f"Bat {tag}", is_bat=True,
                       enrichment_complete=True, last_enriched=datetime.utcnow()))
    db.add(BirdProfile(label=f"Halfus z{tag}_Half Done {tag}", common_name=f"Half Done {tag}", enrichment_complete=False))
    db.commit()
    db.close()
    reg = RegistrySessionLocal()
    reg.add(Instance(id=f"lib-{tag}", name="Lib", db_filename=fname, invite_code=f"L{tag}"))
    reg.commit()
    reg.close()

    assert lib.backfill() >= 1
    assert lib.get(f"Seedus x{tag}_Seed Sparrow {tag}").data["description"] == "d"
    assert lib.get(f"Myotis y{tag}_Bat {tag}") is None
    assert lib.get(f"Halfus z{tag}_Half Done {tag}") is None
    assert lib.stats()["species"] >= 1
