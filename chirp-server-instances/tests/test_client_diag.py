"""0.5.10.o: client viewport diagnostics are logged."""
import logging


def test_client_diag_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger="chirp.api.diagnostics"):
        r = client.post("/api/v1/diagnostics/client", json={"kind": "viewport", "innerH": 812, "screenH": 874})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert any("client-diag" in m and "812" in m for m in caplog.messages)


def test_client_diag_bad_body(client):
    r = client.post("/api/v1/diagnostics/client", content=b"not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 200
