"""www.ourchirp.com pages move to ourchirp.com; API calls stay put."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.website import www_redirect  # noqa: E402


def test_pages_redirect():
    assert www_redirect("www.ourchirp.com", "GET", "/recordings/abc", "x=1") == "https://ourchirp.com/recordings/abc?x=1"
    assert www_redirect("WWW.ourchirp.com:443", "HEAD", "/", "") == "https://ourchirp.com/"
    assert www_redirect("www.ourchirp.com", "GET", "/about", "") == "https://ourchirp.com/about"


def test_api_and_other_hosts_stay():
    assert www_redirect("www.ourchirp.com", "GET", "/api/v1/health", "") is None
    assert www_redirect("www.ourchirp.com", "POST", "/recordings", "") is None
    assert www_redirect("www.ourchirp.com", "GET", "/ws/notifications", "") is None
    assert www_redirect("ourchirp.com", "GET", "/", "") is None
    assert www_redirect("192.168.1.224:8765", "GET", "/", "") is None
