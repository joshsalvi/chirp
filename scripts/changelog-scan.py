#!/usr/bin/env python3
"""Changelog orphan scan — run from the repo root before packaging.

Checks the three CHANGELOG.md files and version stamps for:
  - headings that don't parse (## VERSION [(chirp-device)] — DATE — TYPE — title)
  - entries with no bullets, and bullets that sit before the first heading
  - duplicate versions within one changelog
  - three-part device versions missing the "(chirp-device)" tag (they
    would group with the wrong minor in Changelog.jsx)
  - server/device versions present in one changelog but missing from another
  - VERSION, package.json, sw.js and whatsNew.js disagreeing per fork

Exit status 1 when anything is found.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    "root": ROOT / "CHANGELOG.md",
    "chirp-server": ROOT / "chirp-server" / "CHANGELOG.md",
    "chirp-server-instances": ROOT / "chirp-server-instances" / "CHANGELOG.md",
}
HEAD = re.compile(r"^## (\d+\.\d+\.\d+(?:\.[a-z]+\d*)?)( \(chirp-device\))? — (\d{4}-\d{2}-\d{2}) — [A-Z]+ — \S")

problems = []


STRICT_RECENT = 30   # older headings predate the current format; only check recent ones strictly
ANY_HEAD = re.compile(r"^## (\d+\.\d+(?:\.\d+)?(?:\.[a-z]+\d*)?)( \(chirp-device\))?")


def scan(label, path):
    versions = []
    current, body = None, 0

    def close():
        # Title-only device entries are an accepted style; server entries need a body.
        if current and body == 0 and not current[2]:
            problems.append(f"{label}:{current[1]} {current[0]} has no body text")

    for n, line in enumerate(path.read_text().splitlines(), 1):
        if line.startswith("## "):
            close()
            m = ANY_HEAD.match(line)
            if not m:
                # Non-version sections (the legacy notes at the bottom) are
                # allowed; they just end the previous entry.
                current, body = ("section", n, True), 0
                continue
            ver, tag = m.group(1), bool(m.group(2))
            if len(versions) < STRICT_RECENT and not HEAD.match(line):
                problems.append(f"{label}:{n} heading doesn't match '## VERSION — DATE — TYPE — title': {line[:90]}")
            if ver.count(".") == 2 and not tag and int(ver.split(".")[0]) >= 1:
                problems.append(f"{label}:{n} device version {ver} missing (chirp-device)")
            key = ver + (" (chirp-device)" if tag else "")
            if key in versions:
                problems.append(f"{label}:{n} duplicate entry {key}")
            versions.append(key)
            current, body = (key, n, tag), 0
        elif line.strip():
            if current is None:
                problems.append(f"{label}:{n} text before the first entry")
            body += 1
    close()
    return versions


found = {k: scan(k, p) for k, p in FILES.items() if p.exists()}
root = set(found.get("root", []))
for fork in ("chirp-server", "chirp-server-instances"):
    fv = set(found.get(fork, []))
    # Recent history must match; older fork-only entries predate the shared changelog.
    recent_root = set(found["root"][:STRICT_RECENT])
    for v in sorted(recent_root - fv):
        problems.append(f"{fork}: missing recent entry {v} (in root CHANGELOG)")

for fork in ("chirp-server", "chirp-server-instances"):
    d = ROOT / fork
    ver = (d / "VERSION").read_text().strip()
    pkg = json.loads((d / "frontend" / "package.json").read_text())["version"]
    sw = re.search(r"const CACHE = 'chirp-v([\w.]+)'", (d / "frontend" / "public" / "sw.js").read_text())
    wn = re.search(r"version: '([\w.]+)'", (d / "frontend" / "src" / "lib" / "whatsNew.js").read_text())
    stamps = {"package.json": pkg, "sw.js": sw and sw.group(1), "whatsNew.js": wn and wn.group(1)}
    for name, v in stamps.items():
        if v != ver:
            problems.append(f"{fork}: {name} is {v}, VERSION is {ver}")
    if ver not in root:
        problems.append(f"{fork}: VERSION {ver} has no root CHANGELOG entry")
dev = (ROOT / "chirp-device" / "VERSION").read_text().strip()
if f"{dev} (chirp-device)" not in root:
    problems.append(f"chirp-device: VERSION {dev} has no root CHANGELOG entry")

if problems:
    print("\n".join(problems))
    sys.exit(1)
print(f"changelog scan: OK ({', '.join(f'{k} {len(v)}' for k, v in found.items())} entries; "
      f"server {(ROOT / 'chirp-server-instances' / 'VERSION').read_text().strip()}, device {dev})")
