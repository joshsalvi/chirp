"""0.5.16.q: night calls filter by level, confidence and a search."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NIGHT = "2025-01-15"


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import night_calls
    from app.database import SessionLocal, init_db
    from app.models import FlightCall
    init_db()
    db = SessionLocal()
    db.query(FlightCall).filter(FlightCall.id.like("ncf-%")).delete(synchronize_session=False)
    rows = [
        ("ncf-sp1", "species", "swathr", dict(common_name="Swainson's Thrush", scientific_name="Catharus ustulatus",
                                               family="Turdidae", order="Passeriformes"), 0.92),
        ("ncf-sp2", "species", "amered", dict(common_name="American Redstart", scientific_name="Setophaga ruticilla",
                                               family="Parulidae", order="Passeriformes"), 0.55),
        ("ncf-gr", "group", "ZEEP", dict(family="Parulidae", order="Passeriformes", group="ZEEP"), 0.81),
        ("ncf-fa", "family", "Parulidae", dict(family="Parulidae", order="Passeriformes"), 0.40),
        ("ncf-or", "order", "Passeriformes", dict(order="Passeriformes"), 0.95),
    ]
    for i, (cid, level, cat, extra, prob) in enumerate(rows):
        db.add(FlightCall(id=cid, detected_at=dt.datetime(2025, 1, 16, 4, i), night=NIGHT, level=level,
                          category=cat, prob=prob, duration=0.1, **extra))
    db.commit(); db.close()
    app = FastAPI(); app.include_router(night_calls.router, prefix="/api/v1/night-calls")
    return TestClient(app)


def _cleanup():
    from app.database import SessionLocal
    from app.models import FlightCall
    db = SessionLocal()
    db.query(FlightCall).filter(FlightCall.id.like("ncf-%")).delete(synchronize_session=False)
    db.commit(); db.close()


def _ids(r):
    return {x["id"] for x in r["calls"]}


def test_night_call_filters():
    c = _client()
    try:
        get = lambda **p: c.get("/api/v1/night-calls", params={"night": NIGHT, **p}).json()

        r = get()                                            # default: no order level
        assert _ids(r) == {"ncf-sp1", "ncf-sp2", "ncf-gr", "ncf-fa"}
        assert r["by_level"] == {"species": 2, "group": 1, "family": 1, "order": 1} and r["unnarrowed"] == 1

        r = get(levels="species")                            # species-level only
        assert _ids(r) == {"ncf-sp1", "ncf-sp2"} and r["total"] == 2
        assert r["by_level"]["family"] == 1                  # counts still cover every level

        assert _ids(get(levels="species,order")) == {"ncf-sp1", "ncf-sp2", "ncf-or"}
        assert _ids(get(levels="nonsense")) == set()

        r = get(min_prob=0.8)                                # confidence
        assert _ids(r) == {"ncf-sp1", "ncf-gr"}
        assert r["by_level"] == {"species": 1, "group": 1, "family": 0, "order": 1}
        assert _ids(get(levels="species", min_prob=0.6)) == {"ncf-sp1"}

        assert _ids(get(q="thrush")) == {"ncf-sp1"}          # common name
        assert _ids(get(q="setophaga")) == {"ncf-sp2"}       # scientific name
        assert _ids(get(q="ameri red")) == {"ncf-sp2"}       # every word, word starts
        assert _ids(get(q="hrush")) == set()                 # not mid-word
        assert _ids(get(q="parulidae")) == {"ncf-sp2", "ncf-gr", "ncf-fa"}
        r = get(q="songbird", levels="order")                # order's plain name
        assert _ids(r) == {"ncf-or"} and r["by_level"]["order"] == 1
        r = get(q="parulidae", min_prob=0.5, levels="species,group")
        assert _ids(r) == {"ncf-sp2", "ncf-gr"} and r["by_level"]["family"] == 0

        r = get(q="parulidae", limit=1)                      # paging after the search
        assert r["total"] == 3 and len(r["calls"]) == 1
        assert c.get("/api/v1/night-calls", params={"min_prob": 1.5}).status_code == 422
    finally:
        _cleanup()
