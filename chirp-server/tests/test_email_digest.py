"""0.5.10.m: daily digest with inline logo and bird photos, light layout,
counts at the display threshold."""
import base64
import datetime
import email
import os

T = os.environ["CHIRP_DATA_DIR"]   # set by conftest.py

SPECIES = [("Blue Jay", "Cyanocitta cristata", 9, 0.91, (60, 110, 200)),
           ("American Robin", "Turdus migratorius", 6, 0.84, (200, 90, 40)),
           ("Black-capped Chickadee", "Poecile atricapillus", 5, 0.77, (90, 90, 90)),
           ("Northern Cardinal", "Cardinalis cardinalis", 3, 0.66, (190, 30, 40)),
           ("Barred Owl", "Strix varia", 2, 0.58, (130, 100, 70)),
           ("Carolina Wren", "Thryothorus ludovicianus", 1, 0.52, (150, 110, 60))]


def _photo(path, rgb):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (900, 700), (210, 225, 205))
    d = ImageDraw.Draw(im)
    d.ellipse((250, 180, 650, 560), fill=rgb)
    d.ellipse((520, 150, 700, 330), fill=rgb)
    im.save(path, "JPEG")


def seed(db):
    from app.models import BirdProfile, Detection, Recording
    y = datetime.datetime.combine(datetime.date.today() - datetime.timedelta(days=1), datetime.time(11, 0))
    for i, (name, sci, n, best, rgb) in enumerate(SPECIES):
        path = os.path.join(T, f"dg-photo-{i}.jpg")
        _photo(path, rgb)
        if not db.query(BirdProfile).filter(BirdProfile.common_name == name).first():
            db.add(BirdProfile(common_name=name, scientific_name=sci, label=f"{sci}_{name}", photo_path=path))
        for k in range(n):
            rid = f"dg-{i}-{k}"
            db.add(Recording(id=rid, filename=f"{rid}.wav", wav_path="", trigger_timestamp=y + datetime.timedelta(minutes=7 * k + i),
                             duration_seconds=12, sample_rate=48000, channels=1, pre_roll_seconds=5,
                             device_count=1, processing_status="done", device_id="dev1"))
            db.add(Detection(recording_id=rid, common_name=name, scientific_name=sci, label=f"{sci}_{name}",
                             confidence=best if k == 0 else 0.5, source="server"))
    # Under the display threshold: not counted
    db.add(Recording(id="dg-unknown", filename="u.wav", wav_path="", trigger_timestamp=y, duration_seconds=12,
                     sample_rate=48000, channels=1, pre_roll_seconds=5, device_count=1,
                     processing_status="done", device_id="dev1"))
    db.add(Detection(recording_id="dg-unknown", common_name="Great Horned Owl", label="Bubo_GHO",
                     confidence=0.05, source="server"))
    db.commit()


def cleanup(db):
    from app.models import BirdProfile, Recording
    for r in db.query(Recording).filter(Recording.id.like("dg-%")).all():
        db.delete(r)
    for name, *_ in SPECIES:
        p = db.query(BirdProfile).filter(BirdProfile.common_name == name).first()
        if p and (p.photo_path or "").startswith(T):
            db.delete(p)
    db.commit()


def test_digest_content_and_mime(client, monkeypatch):
    from app.database import SessionLocal
    from app.services import email_service as es
    db = SessionLocal()
    seed(db)
    try:
        stats = es.compute_yesterday_stats(db)
        assert stats["unique_species"] == 6 and "Great Horned Owl" not in stats["species_counts"]
        assert stats["total_recs"] == sum(s[2] for s in SPECIES)
        assert "American Robin" in stats["new_species"] and "Blue Jay" not in stats["new_species"]  # rec-a heard it before
        subject, html, images, text = es.build_daily_digest(db, "https://chirp.example")
        assert "6 species" in subject
        assert html.count("cid:img-") == 7 and "cid:chirp-logo" in html   # 6 cards + the new-species banner
        assert len(images) == 6 and all(i["mimetype"] == "image/jpeg" for i in images)
        assert "https://chirp.example/library/" in html
        assert "New to your life list" in html and "Busiest hour" in html

        sent = {}

        class _SMTP:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def ehlo(self): pass
            def starttls(self, context=None): pass
            def login(self, u, p): pass
            def sendmail(self, f, to, msg): sent["msg"] = msg
        monkeypatch.setattr(es.smtplib, "SMTP", _SMTP)
        cfg = {"host": "x", "port": 587, "use_tls": True, "username": "", "password": "", "from_addr": "c@x.org"}
        assert es._send(cfg, "a@b.org", subject, html, text=text, inline_images=images)
        m = email.message_from_string(sent["msg"])
        assert m.get_content_type() == "multipart/related"
        cids = {p["Content-ID"] for p in m.walk() if p.get("Content-ID")}
        assert "<chirp-logo>" in cids and len(cids) == 7

        # Preview with the images inlined, for a visual check.
        prev = html
        for i in images:
            prev = prev.replace(f"cid:{i['cid']}", "data:image/jpeg;base64," + base64.b64encode(i["content"]).decode())
        from app.services.email_theme import logo_png
        prev = prev.replace("cid:chirp-logo", "data:image/png;base64," + base64.b64encode(logo_png()).decode())
        with open(os.path.join(T, "digest-preview.html"), "w") as f:
            f.write(prev)
    finally:
        cleanup(db)
        db.close()
