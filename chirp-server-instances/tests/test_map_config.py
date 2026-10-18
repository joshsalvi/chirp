"""GET /map-config hands the CARTO tile key to the maps."""


def test_map_config(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        monkeypatch.setenv("CHIRP_CARTO_KEY", "abc_123")
        assert c.get("/api/v1/map-config").json() == {"carto_key": "abc_123"}
        monkeypatch.setenv("CHIRP_CARTO_KEY", "")
        assert c.get("/api/v1/map-config").json() == {"carto_key": None}
