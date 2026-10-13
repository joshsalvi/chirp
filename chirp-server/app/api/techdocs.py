"""
Serves the internal technical documentation (originally written for the
techdocs/ MkDocs project — see scripts/sync-techdocs.py) as an in-app,
admin-only page, so an admin can read it directly from the WebGUI without
needing to run `mkdocs serve` locally.

Every route here requires require_admin — this content is internal
technical detail, not meant for general users, and must not be reachable
by a non-admin user, an unauthenticated request, or a public crawler.
This is access control, not just a hidden nav link — a non-admin hitting
these URLs directly gets a 403, matching the same require_admin pattern
already used for /api/v1/auth/users and friends.
"""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse

from .auth import require_admin

router = APIRouter()

CONTENT_DIR = Path(__file__).resolve().parent.parent / "techdocs_content"
ASSETS_DIR = CONTENT_DIR / "assets"

# Fixed nav order + display titles — mirrors techdocs/mkdocs.yml's own nav
# list, kept in sync by hand since it's a handful of entries that rarely
# change (see scripts/sync-techdocs.py for the content sync itself).
PAGES = [
    {"id": "index",               "title": "Overview"},
    {"id": "architecture",        "title": "System Architecture"},
    {"id": "detection-pipeline",  "title": "Detection Pipeline"},
    {"id": "enrichment",          "title": "Species Enrichment"},
    {"id": "hardware",            "title": "Hardware & Edge Device"},
    {"id": "microphones",         "title": "Microphones"},
    {"id": "device-setup",        "title": "Device Setup Guide"},
    {"id": "deployment",          "title": "Server Deployment"},
    {"id": "remote-access",       "title": "Remote Access (Tailscale/Headscale)"},
    {"id": "configuration",       "title": "Configuration Reference"},
    {"id": "ai-features",         "title": "AI Features"},
    {"id": "api",                 "title": "API Reference"},
    {"id": "faq",                 "title": "FAQ / Troubleshooting"},
]
_VALID_IDS = {p["id"] for p in PAGES}
_ASSET_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+\.(png|jpg|jpeg|svg)$")


@router.get("/pages")
def list_pages(_admin=Depends(require_admin)):
    return {"pages": PAGES, "available": CONTENT_DIR.exists()}


@router.get("/pages/{page_id}", response_class=PlainTextResponse)
def get_page(page_id: str, _admin=Depends(require_admin)):
    if page_id not in _VALID_IDS:
        raise HTTPException(status_code=404, detail="Unknown page")
    path = CONTENT_DIR / f"{page_id}.md"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Content not bundled — run scripts/sync-techdocs.py and rebuild the image",
        )
    return path.read_text()


@router.get("/assets/{filename}")
def get_asset(filename: str, _admin=Depends(require_admin)):
    # Filename is validated against a strict allowlist pattern before ever
    # touching the filesystem — this prevents path traversal (e.g.
    # "../../app/main.py") regardless of what FastAPI's own path parameter
    # parsing does or doesn't already normalize.
    if not _ASSET_NAME_RE.match(filename):
        raise HTTPException(status_code=404, detail="Not found")
    path = ASSETS_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    # Was a week-long cache — reported directly: after redeploying with
    # a changed figure, the old one kept rendering in the browser even
    # though the file on disk was confirmed correct, because the browser
    # honored this Cache-Control and never re-fetched. An admin actively
    # iterating on Tech Docs content (edit, rebuild, redeploy, check)
    # needs to see the new file within minutes, not up to a week later —
    # these aren't content-hashed/immutable filenames like /assets/*'s
    # JS bundles, they're plain names that get overwritten in place on
    # every rebuild, so a long cache actively fights that workflow.
    return FileResponse(path, headers={"Cache-Control": "public, max-age=300"})
