#!/usr/bin/env python3
"""
Syncs the canonical /techdocs/docs/*.md source (used for `mkdocs serve` and
ReadTheDocs) into app/techdocs_content/ so it's actually bundled into the
Docker image — the Dockerfile's `COPY app/ ./app/` picks it up automatically
from there, but the top-level techdocs/ directory sits OUTSIDE this
project's Docker build context entirely and would otherwise never make it
into the running container. Without this, the in-app admin Tech Docs page
would have nothing to serve.

Run standalone: `python3 scripts/sync-techdocs.py`
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # chirp-server/
REPO_ROOT = ROOT.parent                                  # top-level repo
SRC = REPO_ROOT / "techdocs" / "docs"
DEST = ROOT / "app" / "techdocs_content"


def main() -> int:
    if not SRC.exists():
        print(f"Source not found: {SRC}", file=sys.stderr)
        return 1
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(SRC, DEST)
    md_files = sorted(p.name for p in DEST.glob("*.md"))
    print(f"Synced {len(md_files)} pages + assets/ from {SRC} -> {DEST}")
    for f in md_files:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
