"""ourchirp.com serves the website; other servers send its pages there."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_website_pages():
    from app.website import website_page
    for p in ("about", "/about/", "guide.html", "support.html", "testflight.html", "privacy.html", "about-img/hero.jpg", "site.js"):
        assert website_page(p), p
    for p in ("", "login", "offline.html", "sw.js", "manifest.json", "badges/app-store.svg", "recordings/1"):
        assert not website_page(p), p


def test_redirects_without_website(client, monkeypatch):
    from app import website
    monkeypatch.setattr(website, "HOSTS_WEBSITE", False)
    r = client.get("/guide.html?x=1#settings", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "https://ourchirp.com/guide.html?x=1"
    assert client.get("/about", follow_redirects=False).headers["location"] == "https://ourchirp.com/about"
    assert client.get("/api/v1/health").status_code == 200
    monkeypatch.setattr(website, "HOSTS_WEBSITE", True)
    assert client.get("/guide.html", follow_redirects=False).status_code != 302


