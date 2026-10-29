"""
ourchirp.com also serves the Chirp website: about, guides, support and
privacy pages (frontend/public). Other servers, Unraid and Docker Hub
included, are built without them (Dockerfile, CHIRP_WEBSITE build arg)
and redirect those addresses to ourchirp.com. Same file in both forks.
"""
import os

HOSTS_WEBSITE = os.environ.get("CHIRP_WEBSITE", "0") == "1"
WEBSITE_URL = "https://ourchirp.com"
WEBSITE_PAGES = {"about", "about.html", "setup.html", "guide.html", "troubleshooting.html", "support.html", "testflight.html",
                 "privacy.html", "docs.css", "site.js"}


def website_page(path: str) -> bool:
    path = path.strip("/")
    return path in WEBSITE_PAGES or path.startswith("about-img/")
