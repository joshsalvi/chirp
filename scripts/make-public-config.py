#!/usr/bin/env python3
"""Writes chirp-device/config.yaml.public from the working config.yaml:
same settings and comments, with keys, the Headscale key, the location and
personal server addresses replaced. Fails if anything private is left.

  python3 scripts/make-public-config.py [chirp-device dir]
"""
import re
import sys
from pathlib import Path

import yaml

dev = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "chirp-device")
src = (dev / "config.yaml").read_text()

KEY = "chirp-PASTE_KEY_HERE"
out = src
# The multi-server `targets:` lists are personal; leave the single-server form.
out = re.sub(r"(?m)^  targets:\n(?:(?:    |      ).*\n)+", "", out)
out = re.sub(r'api_key: "chirp-[A-Za-z0-9_-]+"', f'api_key: "{KEY}"', out)
out = re.sub(r'(?m)^(\s*auth_key: )"[^"]*"', r'\1""', out)
out = re.sub(r"(?m)^(tailscale:\n  enabled: )true", r"\1false", out)
out = re.sub(r'(?m)^(\s*login_server: )"[^"]*"', r'\1""', out)
out = re.sub(r"(?m)^(\s*latitude: )[-\d.]+(\s*#.*)?$", r"\1null                  # set from the server's Settings → Location", out)
out = re.sub(r"(?m)^(\s*longitude: )[-\d.]+(\s*#.*)?$", r"\1null", out)
out = re.sub(r'(?m)^(\s*device_name: )"ChirpPi"', r'\1""', out)
out = out.replace("https://chirp.joshuasalvimd.com", "https://ourchirp.com")
out = out.replace("https://www.ourchirp.com", "https://ourchirp.com")
out = out.replace("# Natick, MA", "")

leaks = [p for p in (r"chirp-(?!PASTE)[A-Za-z0-9_-]{30,}", r"joshuasalvimd", r"Natick", r"auth_key: \"[^\"]+\"",
                     r"\b(?:\d{1,3}\.){3}\d{1,3}\b(?<!0\.0\.0\.0)(?<!127\.0\.0\.1)") if re.search(p, out)]
if leaks:
    sys.exit(f"Private values left in public config: {leaks}")
pub, live = yaml.safe_load(out), yaml.safe_load(src)
assert set(pub) == set(live), set(live) ^ set(pub)
assert pub["upload"]["api_key"] == KEY and pub["server_sync"]["api_key"] == KEY
assert "targets" not in pub["upload"] and "targets" not in pub["server_sync"]
(dev / "config.yaml.public").write_text(out)
print(f"Wrote {dev / 'config.yaml.public'} ({len(out.splitlines())} lines)")
