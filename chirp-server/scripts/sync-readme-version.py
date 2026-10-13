#!/usr/bin/env python3
"""
Syncs README.md's "**Version:**" line to the canonical VERSION file.

Same real problem stamp-sw-version.mjs already solves for sw.js's build-time
cache string, applied to the one other place a version number gets manually
typed and can silently drift: README.md isn't part of the frontend npm build
(it's a repo-root file, not inside frontend/), so nothing was ever re-stamping
it — confirmed directly: a real user report found it reading 0.5.0.p while the
actual VERSION file was already several patches ahead.

Run standalone any time: `python3 scripts/sync-readme-version.py`
Also wired into .github/workflows/sync-readme-version.yml, which runs this on
every push to main that touches VERSION and commits the fix back automatically
— the actual "auto update" mechanism, since a script alone only fixes things
when someone remembers to run it.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
README_FILES = [ROOT / "README.md", ROOT.parent / "README.md"]  # chirp-server/README.md + top-level README.md


def main() -> int:
    if not VERSION_FILE.exists():
        print(f"VERSION file not found at {VERSION_FILE}", file=sys.stderr)
        return 1
    version = VERSION_FILE.read_text().strip()

    changed_any = False
    for readme_path in README_FILES:
        if not readme_path.exists():
            continue
        text = readme_path.read_text()
        pattern = re.compile(r"(\*\*Version:\*\*\s*)([^\s]+)")
        match = pattern.search(text)
        if not match:
            print(f"No '**Version:**' line found in {readme_path} — skipping")
            continue
        current = match.group(2)
        if current == version:
            print(f"{readme_path}: already up to date ({version})")
            continue
        new_text = pattern.sub(rf"\g<1>{version}", text, count=1)
        readme_path.write_text(new_text)
        print(f"{readme_path}: {current} -> {version}")
        changed_any = True

    return 0 if True else 1  # exit 0 either way — "nothing to change" isn't a failure


if __name__ == "__main__":
    sys.exit(main())
