"""
What only ourchirp.com runs. Other servers, Unraid and Docker Hub included,
are built without it (Dockerfile, CHIRP_WEBSITE build argument):

  - the website pages: about, guides, support, privacy (frontend/public);
    other servers redirect those addresses to ourchirp.com
  - hosted-site requests from the About page (site_requests.py)
  - the push relay other servers send iPhone notifications through
    (push_relay.py)
  - site traffic counts (traffic.py)
  - bird picture packs for Chirp Live (live_pack.py)
  - their Global Admin tabs (frontend/src/website/)

This file is kept in every build; the modules next to it are not.
chirp-server has the flags part only (app/website.py).
"""
import os

HOSTS_WEBSITE = os.environ.get("CHIRP_WEBSITE", "0") == "1"
WEBSITE_URL = "https://ourchirp.com"
WEBSITE_PAGES = {"about", "about.html", "setup.html", "guide.html", "troubleshooting.html", "support.html", "testflight.html",
                 "privacy.html", "docs.css", "site.js"}


def website_page(path: str) -> bool:
    path = path.strip("/")
    return path in WEBSITE_PAGES or path.startswith("about-img/")


CANONICAL_HOST = "ourchirp.com"
_WWW = "www." + CANONICAL_HOST


def www_redirect(host: str, method: str, path: str, query: str = ""):
    """The ourchirp.com address for a page asked for at www.ourchirp.com, or
    None. API calls and websockets stay on www: the apps and stations that
    use it would lose their sign-in or upload body on a redirect."""
    if (host or "").split(":")[0].lower() != _WWW or method not in ("GET", "HEAD"):
        return None
    if path.startswith("/api/") or path.startswith("/ws"):
        return None
    return f"https://{CANONICAL_HOST}{path}" + (f"?{query}" if query else "")


def mount(app):
    """Adds the ourchirp.com-only routes and traffic counting (main.py)."""
    if not HOSTS_WEBSITE:
        return
    from . import live_pack, push_relay, site_requests, traffic
    app.include_router(site_requests.router, prefix="/api/v1/site-requests", tags=["site-requests"])
    app.include_router(site_requests.admin_router, prefix="/api/v1/admin/site-requests", tags=["admin"])
    app.include_router(push_relay.router, prefix="/api/v1/push-relay", tags=["push-relay"])
    app.include_router(push_relay.admin_router, prefix="/api/v1/admin/relay-servers", tags=["admin"])
    app.include_router(traffic.admin_router, prefix="/api/v1/admin/traffic", tags=["admin"])
    app.include_router(live_pack.router, prefix="/api/v1/live-pack", tags=["live-pack"])
    import threading
    t = threading.Timer(120, live_pack.start_background_fill)   # after startup settles
    t.daemon = True
    t.start()

    @app.middleware("http")
    async def _www_to_apex(request, call_next):
        target = www_redirect(request.headers.get("host", ""), request.method, request.url.path, request.url.query)
        if target:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(target, status_code=301)
        return await call_next(request)

    @app.middleware("http")
    async def _count_traffic(request, call_next):
        # Counts every request after it's answered (counts only, no addresses kept).
        response = await call_next(request)
        try:
            from ..api.auth import client_address
            traffic.record(request.method, request.url.path, response.status_code, request.headers,
                           client_address(request))
        except Exception:
            pass
        return response
