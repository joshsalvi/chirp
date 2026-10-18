"""GET /map-config hands the CARTO tile key to the maps."""
import asyncio


def test_map_config(monkeypatch):
    # Called directly: starting the whole app (TestClient lifespan) here
    # changed auth state for the tests that run after it.
    from app.main import map_config, UNPROTECTED
    assert "/api/v1/map-config" in UNPROTECTED
    monkeypatch.setenv("CHIRP_CARTO_KEY", "abc_123")
    assert asyncio.run(map_config()) == {"carto_key": "abc_123"}
    monkeypatch.setenv("CHIRP_CARTO_KEY", "")
    assert asyncio.run(map_config()) == {"carto_key": None}
