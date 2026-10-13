#!/usr/bin/env python3
"""Download the clips in manifest.json from Xeno-canto and convert them to
48 kHz mono 16-bit WAV (first `first_seconds` seconds), the format the
server pass reads.

    python3 scripts/owl-eval/fetch.py [--dir ~/.cache/chirp-owl-eval]

Needs curl and ffmpeg. Already-converted clips are skipped.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.expanduser("~/.cache/chirp-owl-eval"))
    args = ap.parse_args()
    man = json.load(open(os.path.join(HERE, "manifest.json")))
    raw_dir = os.path.join(args.dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    failed = 0
    for c in man["clips"]:
        wav = os.path.join(args.dir, f"XC{c['xc']}.wav")
        if os.path.exists(wav) and os.path.getsize(wav) > 0:
            continue
        raw = os.path.join(raw_dir, f"XC{c['xc']}")
        if not os.path.exists(raw):
            r = subprocess.run(["curl", "-sfL", "-m", "180", "-o", raw,
                                f"https://xeno-canto.org/{c['xc']}/download"])
            if r.returncode:
                print(f"download failed: XC{c['xc']}", file=sys.stderr)
                failed += 1
                continue
        r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw,
                            "-t", str(man["first_seconds"]), "-ac", "1", "-ar", "48000",
                            "-sample_fmt", "s16", wav])
        if r.returncode:
            print(f"convert failed: XC{c['xc']}", file=sys.stderr)
            failed += 1
        else:
            print(f"XC{c['xc']}  {c['label']}")
    print(f"{len(man['clips']) - failed} of {len(man['clips'])} clips in {args.dir}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
