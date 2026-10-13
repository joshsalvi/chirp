"""The daily digest push opens the app's digest page, never a full URL."""
from collections import Counter
from datetime import date, datetime

import tests.test_notifications_inbox  # noqa: F401  (pywebpush stub on bare machines)


def _stats():
    counts = Counter({"Blue Jay": 9, "Barred Owl": 2, "Carolina Wren": 4})
    return {
        "yesterday": date(2026, 10, 8), "day_str": "Thursday, October 8",
        "day_start": datetime(2026, 10, 8), "day_end": datetime(2026, 10, 9),
        "total_recs": 12, "total_dets": 15, "species_counts": counts,
        "top_species": counts.most_common(6), "unique_species": 3,
        "best_conf": {"Blue Jay": 0.913, "Barred Owl": 0.44, "Carolina Wren": 0.8},
        "scientific": {"Barred Owl": "Strix varia"}, "new_species": ["Barred Owl"],
        "busiest_hour": 7, "display_min": 0.15, "tz": None, "first_heard": {},
    }


def test_app_path():
    from app.services.push_notifications import app_path
    assert app_path("https://chirp.joshuasalvimd.com/") == "/"
    assert app_path("https://x.org/journal?entry=daily#t") == "/journal?entry=daily#t"
    assert app_path("chirp.example.com/recordings/5") == "/recordings/5"
    assert app_path("/notifications") == "/notifications"
    assert app_path(None) is None and app_path("") is None


def test_digest_push_links_into_app_with_details(client, monkeypatch):
    from app.models import AppSettings
    from app.services import email_service, push_notifications
    from app.database import SessionLocal

    monkeypatch.setattr(email_service, "compute_yesterday_stats", lambda db: _stats())
    client.delete("/api/v1/notifications")
    db = SessionLocal()
    try:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        old = s.server_url if s else None
        if s:
            s.server_url = "https://chirp.joshuasalvimd.com"
            db.commit()
        push_notifications.send_daily_digest_push(db)
        if s:
            s.server_url = old
            db.commit()
    finally:
        db.close()

    items = client.get("/api/v1/notifications").json()["items"]
    n = next(i for i in items if i["kind"] == "daily-digest")
    assert n["url"] == "/digest?date=2026-10-08"
    d = n["data"]
    assert d["date"] == "2026-10-08" and d["recordings"] == 12 and d["species_count"] == 3
    assert [x["name"] for x in d["species"]] == ["Blue Jay", "Carolina Wren", "Barred Owl"]
    owl = d["species"][2]
    assert owl["new"] and owl["scientific"] == "Strix varia" and owl["best"] == 0.44
    assert d["new_species"] == ["Barred Owl"] and d["busiest_hour"].startswith("7 AM")
    client.delete("/api/v1/notifications")


def test_full_urls_are_stored_as_paths(client):
    from app.database import SessionLocal
    from app.services.push_notifications import send_push_to_all
    client.delete("/api/v1/notifications")
    db = SessionLocal()
    try:
        send_push_to_all(db, "t", "b", url="https://other.host/recordings/abc", tag="test")
    finally:
        db.close()
    assert client.get("/api/v1/notifications").json()["items"][0]["url"] == "/recordings/abc"
    client.delete("/api/v1/notifications")
