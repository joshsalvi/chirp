"""Security headers, the catch-all route's 404s, crawler files, sign-in and sign-up limits."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _client():
    from fastapi.testclient import TestClient
    from app import main
    return TestClient(main.app, follow_redirects=False)


def test_headers_on_every_response():
    c = _client()
    r = c.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in r.headers["permissions-policy"]
    assert "strict-transport-security" not in r.headers          # plain http: no HSTS
    r = c.get("/api/v1/health", headers={"x-forwarded-proto": "https"})
    assert r.headers["strict-transport-security"].startswith("max-age=")
    r = c.get("/api/v1/health", headers={"cf-visitor": '{"scheme":"https"}'})
    assert "strict-transport-security" in r.headers
    assert "x-frame-options" in c.get("/no-such-page.txt").headers   # errors too


def test_cors_not_credentialed():
    r = _client().get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert r.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in r.headers


def test_spa_404s(tmp_path):
    from starlette.requests import Request
    from app import main, security
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "logo.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("no")

    def req(path):
        return Request({"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b"",
                        "client": ("203.0.113.5", 1)})

    def spa(p):
        return main.spa_response(p, req("/" + p), tmp_path)
    assert spa("recordings/abc").status_code == 200                 # app route → app page
    assert spa("logo.svg").status_code == 200
    assert spa("api/v1/nope").status_code == 404 and spa("api/v1/nope").body == b'{"detail":"Not Found"}'
    assert spa("missing.js").status_code == 404                     # missing file, not the app page
    assert spa("../secret.txt").status_code == 404                  # stays inside static
    before = security.summary()["counts"].get("probe", 0)
    for p in (".env", ".git/config", "wp-login.php", "phpmyadmin/index.php", "backup.zip", "config.json"):
        assert spa(p).status_code == 404, p
    assert security.summary()["counts"]["probe"] == before + 6
    ev = security.summary()["events"][0]
    assert ev["kind"] == "probe" and ev["ip"] == "203.0.113.5"


def test_probe_pattern():
    from app.security import is_probe
    for p in ("/.env", "/.aws/credentials", "/wp-admin/", "/xmlrpc.php", "/cgi-bin/x", "/a/../../etc/passwd",
              "/server-status", "/actuator/health", "/db.sql", "/site.bak"):
        assert is_probe(p), p
    for p in ("/", "/recordings/abc", "/about", "/about.html", "/assets/index-1.js", "/manifest.json", "/logo.svg"):
        assert not is_probe(p), p


def test_robots_on_private_servers(monkeypatch):
    from app import website
    monkeypatch.setattr(website, "HOSTS_WEBSITE", False)
    c = _client()
    r = c.get("/robots.txt")
    assert r.status_code == 200 and "Disallow: /" in r.text and "Allow" not in r.text
    assert c.get("/sitemap.xml").status_code == 404
    assert c.get("/.well-known/security.txt").status_code == 404


def test_robots_sitemap_security_txt_on_website(monkeypatch):
    from app import website
    monkeypatch.setattr(website, "HOSTS_WEBSITE", True)
    c = _client()
    r = c.get("/robots.txt")
    assert "Allow: /about" in r.text and "Sitemap: https://ourchirp.com/sitemap.xml" in r.text
    r = c.get("/sitemap.xml")
    assert r.headers["content-type"].startswith("application/xml") and "<loc>https://ourchirp.com/privacy.html</loc>" in r.text
    r = c.get("/.well-known/security.txt")
    assert "Contact: https://ourchirp.com/support.html" in r.text and "Expires: " in r.text


def test_login_spraying_blocked_by_address(monkeypatch):
    from app.api import auth
    auth._failed_by_ip.clear(); auth._failed_login_attempts.clear()
    for i in range(auth.LOGIN_IP_MAX):
        auth._note_failed_login(f"user{i}:198.51.100.7", f"user{i}")
    with pytest.raises(auth.HTTPException) as e:
        auth._check_login_rate_limit("someoneelse:198.51.100.7")
    assert e.value.status_code == 429
    auth._check_login_rate_limit("someoneelse:198.51.100.8")      # other addresses unaffected
    auth._failed_by_ip.clear(); auth._failed_login_attempts.clear()


def test_signup_limit():
    from starlette.requests import Request
    from app.api import auth
    auth._signups_by_ip.clear()
    r = Request({"type": "http", "method": "POST", "path": "/", "headers": [(b"cf-connecting-ip", b"192.0.2.44")],
                 "query_string": b"", "client": ("10.0.0.1", 1)})
    for _ in range(auth.SIGNUP_IP_MAX):
        auth.check_signup_rate(r)
    with pytest.raises(auth.HTTPException) as e:
        auth.check_signup_rate(r)
    assert e.value.status_code == 429
    auth.check_signup_rate(None)                                     # direct calls (tests, scripts) skip it
    auth._signups_by_ip.clear()


def test_api_docs_flag(monkeypatch):
    import importlib
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "main.py")).read()
    assert 'openapi_url="/openapi.json" if _API_DOCS else None' in src
    assert '"0" if os.environ.get("CHIRP_WEBSITE") == "1" else "1"' in src
    importlib.import_module("app.main")
