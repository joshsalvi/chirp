"""Chirp Lite API (api/lite.py) and the Lite/Pro choice (api/auth.py ui_mode_for)."""
import datetime as _dt
import os
import shutil

import pytest

T = os.environ["CHIRP_DATA_DIR"]   # set by conftest.py


def test_words():
    from app.api.lite import first_sentences, how_often, likelihood_label, season_fact
    assert likelihood_label(0.4) == "common" and likelihood_label(0.06) == "uncommon" and likelihood_label(0.01) == "rare"
    assert season_fact([0.3] * 12) == "All year"
    assert season_fact([0, 0, 0, 0.2, 0.4, 0.5, 0.5, 0.4, 0.3, 0.1, 0, 0]) == "Apr–Sep"   # months at 25%+ of the peak
    assert season_fact([0.5, 0.4, 0.2, 0, 0, 0, 0, 0, 0, 0, 0.2, 0.5]) == "Nov–Mar"   # wraps the new year
    assert season_fact([0] * 12) is None and season_fact(None) is None
    assert how_often(25) == "Most days" and how_often(1) == "Once this month" and how_often(0) == "Not this month"
    s = first_sentences("Bold and loud. It sings all year. " + "x " * 300, 60)
    assert s == "Bold and loud. It sings all year."
    assert first_sentences(None) is None


def test_size_words():
    from app.api.lite import size_fact
    from app.models import BirdProfile
    assert size_fact(BirdProfile(aab_length_min_cm=24, aab_length_max_cm=26))["label"] == "About robin-sized"
    assert size_fact(BirdProfile(aab_length_min_cm=21, aab_length_max_cm=23))["label"] == "Smaller than a robin"
    assert size_fact(BirdProfile(aab_length_min_cm=9, aab_length_max_cm=11))["label"] == "Much smaller than a robin"
    assert size_fact(BirdProfile(aab_length_min_cm=60, aab_length_max_cm=70))["label"] == "Much bigger than a robin"
    assert size_fact(BirdProfile()) is None


def test_ui_mode_default_by_role():
    from app.api.auth import ui_mode_for
    from app.models import User
    assert ui_mode_for(User(role="viewer")) == "lite"
    assert ui_mode_for(User(role="admin")) == "pro"
    assert ui_mode_for(User(role="submitter")) == "pro"
    assert ui_mode_for(User(role="admin", ui_mode="lite")) == "lite"
    assert ui_mode_for(User(role="viewer", ui_mode="nonsense")) == "lite"


def test_lite_screens(client):
    pytest.importorskip("soundfile")
    from app.database import SessionLocal
    from app.models import BirdProfile, Detection, Recording
    db = SessionLocal()
    wav = os.path.join(T, "recordings_dir", "a.wav")
    now = _dt.datetime.utcnow() - _dt.timedelta(minutes=5)
    for i in range(3):
        rid = f"lite-{i}"
        path = os.path.join(T, "recordings_dir", f"{rid}.wav")
        shutil.copy(wav, path)
        db.add(Recording(id=rid, filename=f"{rid}.wav", wav_path=path, trigger_timestamp=now - _dt.timedelta(minutes=i),
                         created_at=now, duration_seconds=12, sample_rate=48000, channels=1, pre_roll_seconds=5,
                         device_count=1, processing_status="done"))
        db.add(Detection(recording_id=rid, common_name="Northern Cardinal", label="Cardinalis cardinalis_Northern Cardinal",
                         confidence=0.8 - i * 0.1, start_time=2 + i, end_time=5 + i, source="device"))
    db.add(Detection(recording_id="lite-0", common_name="Tufted Titmouse", label="x_Tufted Titmouse",
                     confidence=0.5, start_time=6, end_time=9, source="device"))
    db.add(BirdProfile(id="bp-cardinal", label="Cardinalis cardinalis_Northern Cardinal", common_name="Northern Cardinal",
                       scientific_name="Cardinalis cardinalis", aab_length_min_cm=21, aab_length_max_cm=23,
                       aab_description="A crested red songbird. Males are bright red all over. " + "More text. " * 40,
                       aab_cool_facts=["Cardinals sing year-round, and females sing too."], aab_food="Seeds",
                       monthly_frequency=[0.5] * 12, photo_url="https://example.org/cardinal.jpg"))
    db.commit()
    db.close()
    from app.cache import life_list_cache
    life_list_cache.clear() if hasattr(life_list_cache, "clear") else None

    t = client.get("/api/v1/lite/today").json()
    assert t["species_count"] >= 2 and t["recordings"] >= 3 and len(t["hourly"]) == 24 and sum(t["hourly"]) >= 3
    # The hero is the newest bird today (other tests may add newer ones).
    assert t["hero"]["today"] and t["hero"]["time"] == max(s["last"] for s in t["species"])
    assert t["first_song"]["time"] <= t["hero"]["time"] and t["first_song"]["name"]
    card = next(s for s in t["species"] if s["name"] == "Northern Cardinal")
    assert card["count"] == 3 and card["new"] is True
    assert card["profile_id"] == "bp-cardinal" and card["photo"] == "https://example.org/cardinal.jpg"
    assert "photo_large" in t["hero"] and "journal" in t

    b = client.get("/api/v1/lite/birds?sort=most").json()
    names = [x["name"] for x in b["birds"]]
    assert "Northern Cardinal" in names and b["count"] == len(names)
    assert client.get("/api/v1/lite/birds?sort=bogus").status_code == 422

    page = client.get("/api/v1/lite/listen", params={"limit": 2, "bird": "Northern Cardinal"}).json()
    assert len(page["recordings"]) == 2 and page["next_before"]
    first = page["recordings"][0]
    assert first["id"] == "lite-0" and first["bird"] == "Northern Cardinal" and first["others"] == ["Tufted Titmouse"]
    assert first["has_audio"] and first["audio"].endswith("/audio") and first["profile_id"] == "bp-cardinal"
    more = client.get("/api/v1/lite/listen", params={"limit": 2, "bird": "Northern Cardinal",
                                                     "before": page["next_before"]}).json()
    assert [r["id"] for r in more["recordings"]] == ["lite-2"] and more["next_before"] is None
    titmouse = client.get("/api/v1/lite/listen", params={"bird": "Tufted Titmouse"}).json()["recordings"]
    assert titmouse and titmouse[0]["bird"] == "Tufted Titmouse" and titmouse[0]["starts_at"] == 6
    assert client.get("/api/v1/lite/listen?before=yesterday").status_code == 400

    p = client.get("/api/v1/lite/bird/bp-cardinal").json()
    assert p["size"]["label"] == "Smaller than a robin" and p["season"] == "All year"
    assert p["heard_count"] == 3 and p["how_often"] == "Once this month"
    assert p["song"]["kind"] == "yours" and p["song"]["recording_id"] == "lite-0" and p["song"]["starts_at"] == 2
    assert p["blurb"].startswith("A crested red songbird.") and len(p["blurb"]) <= 241
    assert p["fun_fact"].startswith("Cardinals sing") and p["tags"] == [{"kind": "food", "label": "Seeds"}]
    assert p["photos"][0]["url"] == "https://example.org/cardinal.jpg"
    assert client.get("/api/v1/lite/bird/nope").status_code == 404

    g = client.get("/api/v1/lite/guide")
    assert g.status_code == 200 and set(g.json()) >= {"month", "count", "heard", "birds"}


def test_ui_mode_saved(client):
    # Auth is off in the test server, so /me/profile edits the default admin.
    from app.database import SessionLocal
    from app.models import User
    db = SessionLocal()
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", hashed_pw="x", role="admin"))
        db.commit()
    db.close()
    assert client.put("/api/v1/auth/me/profile", json={"ui_mode": "lite"}).status_code == 200
    db = SessionLocal()
    assert db.query(User).filter(User.username == "admin").first().ui_mode == "lite"
    db.close()
    assert client.put("/api/v1/auth/me/profile", json={"ui_mode": "max"}).status_code == 400
    assert client.get("/api/v1/auth/me").json()["ui_mode"] in ("lite", "pro")


def test_lite_token_paths():
    from app.main import lite_may_use as ok
    for p in ("/api/v1/auth/me", "/api/v1/lite/today", "/api/v1/lite/bird/bp-1", "/api/v1/lite/listen",
              "/api/v1/recordings/statistics/daily-journal", "/api/v1/watch/audio/3f2a-11"):
        assert ok("GET", p), p
    assert ok("POST", "/api/v1/auth/lite-token")
    for m, p in (("GET", "/api/v1/recordings"), ("GET", "/api/v1/settings"), ("PUT", "/api/v1/auth/me/profile"),
                 ("POST", "/api/v1/lite/today"), ("GET", "/api/v1/auth/watch-token"), ("DELETE", "/api/v1/lite/bird/x"),
                 ("GET", "/api/v1/lite"), ("POST", "/api/v1/auth/watch-token"), ("GET", "/api/v1/watch/recent"),
                 ("GET", "/api/v1/watch/audio/../x")):
        assert not ok(m, p), (m, p)


def test_lite_token_claims():
    from fastapi import HTTPException
    from app.api.auth import LITE_TOKEN_DAYS, create_access_token, lite_token, verify_token
    user = object()
    phone = create_access_token({"sub": "josh", "global_user_id": "g1", "active_instance_id": "i1", "role": "viewer", "x": 1})
    out = lite_token(phone, user)
    claims = verify_token(out["access_token"])
    assert claims["scope"] == "lite" and claims["active_instance_id"] == "i1" and "x" not in claims
    assert out["expires_days"] == LITE_TOKEN_DAYS
    again = verify_token(lite_token(out["access_token"], user)["access_token"])   # renews itself
    assert again["scope"] == "lite" and again["sub"] == "josh"
    tv = create_access_token({"sub": "josh", "scope": "watch"})
    with pytest.raises(HTTPException) as e:
        lite_token(tv, user)
    assert e.value.status_code == 403
    assert lite_token(phone, None) == {"access_token": None, "auth_required": False}


def test_lite_token_limited(client):
    from app.api.auth import create_access_token
    t = create_access_token({"sub": "admin", "scope": "lite"})
    h = {"Authorization": "Bearer " + t}
    assert client.get("/api/v1/settings", headers=h).status_code == 403
    assert client.put("/api/v1/auth/me/profile", json={"ui_mode": "pro"}, headers=h).status_code == 403
    assert client.get("/api/v1/lite/guide", headers=h).status_code != 403


def test_range_map_choice(tmp_path, monkeypatch):
    from app.api.lite import range_map_of
    from app.config import settings
    from app.models import AppSettings, BirdProfile
    monkeypatch.setattr(settings, "media_dir", str(tmp_path))
    folder = tmp_path / "blue_jay"
    folder.mkdir()
    p = BirdProfile(id="bp-j", common_name="Blue Jay", range_map_url="https://upload.wikimedia.org/x.svg", range_map_source="wikipedia")
    r = range_map_of(p)
    assert r["range_map_vector"] and r["range_map_source"] == "Wikipedia"
    assert r["range_map_image"] == "/api/v1/birds/bp-j/range-map/png"
    cornell = tmp_path / "aab.png"
    cornell.write_bytes(b"x" * 2000)
    p.range_map_url, p.range_map_source = f"file://{cornell}", "aab"
    r = range_map_of(p)
    assert r == {"range_map": "/api/v1/birds/bp-j/range-map", "range_map_source": "All About Birds", "range_map_vector": False,
                 "range_map_image": "/api/v1/birds/bp-j/range-map"}
    (folder / "range_map_ebird_st.png").write_bytes(b"x" * 2000)
    assert range_map_of(p)["range_map"].endswith("/range-map/ebird_st")
    (folder / "range_map_geomodel.png").write_bytes(b"x" * 2000)          # the local library comes first
    assert range_map_of(p)["range_map_source"] == "iNaturalist"
    assert range_map_of(BirdProfile(id="x", common_name="Nobody"))["range_map"] is None
    # The generic Bat profile: one map per site location.
    bat = BirdProfile(id="bp-bat", label="Bat", common_name="Bat", is_bat=True)
    site = AppSettings(latitude=42.28, longitude=-71.35)
    assert range_map_of(bat, site)["range_map"] is None
    (tmp_path / "bat").mkdir()
    (tmp_path / "bat" / "range_map_geomodel_42.3_-71.3.png").write_bytes(b"x" * 2000)
    assert range_map_of(bat, site)["range_map"] == "/api/v1/birds/bp-bat/range-map/local"
    assert range_map_of(bat)["range_map"] is None

def test_range_map_routes(client):
    # Each map source has its own route (the BirdLife one had lost its decorator).
    for src in ("ebird_st", "geomodel", "birdlife", "png"):
        r = client.get(f"/api/v1/birds/no-such-bird/range-map/{src}")
        assert r.status_code == 404 and "not found" in r.json()["detail"].lower(), (src, r.text[:80])


def test_svg_to_png():
    pytest.importorskip("playwright")
    from app.api.birds import svg_to_png
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><rect width="200" height="100" fill="#2a6"/></svg>'
    png = svg_to_png(svg, width=400)
    if png is None:
        pytest.skip("no Chromium here")
    from io import BytesIO
    from PIL import Image
    im = Image.open(BytesIO(png))
    assert im.size == (400, 200) and im.getpixel((200, 100))[:3] == (0x22, 0xaa, 0x66)


def test_journal_line_and_photo_size():
    from app.api.lite import journal_excerpt, larger_photo
    text = "What keeps the yard so busy in November? Today's 1,500 detections were above average. Juncos arrived."
    assert journal_excerpt(text) == "Today's 1,500 detections were above average. Juncos arrived."
    assert journal_excerpt("Is it spring?") == "Is it spring?"      # nothing else to show
    assert journal_excerpt(None) is None
    assert larger_photo("https://inaturalist-open-data.s3.amazonaws.com/photos/1/medium.jpg").endswith("/photos/1/large.jpg")
    assert larger_photo("https://static.inaturalist.org/photos/2/small.jpeg").endswith("/photos/2/large.jpeg")
    assert larger_photo("/api/v1/birds/x/photo") == "/api/v1/birds/x/photo" and larger_photo(None) is None


def test_today_journal(client):
    from app.database import SessionLocal
    from app.models import AppSettings
    db = SessionLocal()
    s = db.query(AppSettings).first()
    s.daily_summary_text = "Why so quiet? Nine species sang today. A first Fox Sparrow."
    s.daily_summary_generated_at = _dt.datetime.utcnow()
    db.commit()
    t = client.get("/api/v1/lite/today").json()
    assert t["journal"] == {"text": "Nine species sang today. A first Fox Sparrow.", "day": "today"}
    s.daily_summary_generated_at = _dt.datetime.utcnow() - _dt.timedelta(days=3)
    db.commit()
    assert client.get("/api/v1/lite/today").json()["journal"] is None
    db.close()


def test_dashboard_mode_saved(client):
    from app.database import SessionLocal
    from app.models import User
    db = SessionLocal()
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", hashed_pw="x", role="admin"))
        db.commit()
    db.close()
    def mode():
        d = SessionLocal()
        try:
            return d.query(User).filter(User.username == "admin").first().dashboard_mode
        finally:
            d.close()
    assert client.put("/api/v1/auth/me/profile", json={"dashboard_mode": "advanced"}).status_code == 200 and mode() == "advanced"
    assert client.put("/api/v1/auth/me/profile", json={"dashboard_mode": "simplified"}).status_code == 200 and mode() == "standard"
    assert client.put("/api/v1/auth/me/profile", json={"dashboard_mode": "detailed"}).status_code == 200 and mode() == "advanced"
    assert client.put("/api/v1/auth/me/profile", json={"dashboard_mode": "fancy"}).status_code == 400
