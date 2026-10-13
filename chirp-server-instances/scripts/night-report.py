#!/usr/bin/env python3
"""Overnight detection report: Chirp devices vs Haikubox.

Run inside the server container (stdlib only):
  docker exec chirp-server-instances python3 /app/scripts/night-report.py
  docker exec chirp-server-instances python3 /app/scripts/night-report.py --nights 3 --tz America/New_York
  docker exec chirp-server-instances python3 /app/scripts/night-report.py --db /app/data/instances/<file>.db

Without --db it reports every database it finds (/app/data/chirp.db and
/app/data/instances/*.db).

Sections:
  1. Night activity by hour (device vs Haikubox detections)
  2. Nocturnal species: Chirp vs Haikubox counts, best confidence, last heard
  3. Missed: Haikubox nocturnal detections with no Chirp detection of the same
     species within +/- 10 min (night hours first, then daytime)
  4. Night recording quality: trigger level, SNR, empty recordings
  5. Owl confidence spread (is min_confidence cutting real calls?)
"""
import argparse
import glob
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:           # pragma: no cover
    ZoneInfo = None

# Whole-word match: "Owl" must not hit "Yellowlegs". Same list the server
# uses to keep these recordings out of auto-purge.
NOCTURNAL_RE = re.compile(r"\b(Owl|Whip-poor-will|Nighthawk|Chuck-will's-widow|Poorwill|"
                          r"Woodcock|Night-Heron|Rail|Sora|Bittern)\b")
NIGHT_HOURS = list(range(19, 24)) + list(range(0, 7))


def is_nocturnal(name):
    return bool(NOCTURNAL_RE.search(name or ""))


def find_dbs(data_dir):
    out = []
    main = os.path.join(data_dir, "chirp.db")
    if os.path.exists(main):
        out.append(main)
    out += sorted(glob.glob(os.path.join(data_dir, "instances", "*.db")))
    return [p for p in out if not os.path.basename(p).startswith("_")]


def server_tz(conn, fallback):
    try:
        row = conn.execute("SELECT timezone FROM app_settings WHERE id = 1").fetchone()
        if row and row[0]:
            return row[0]
    except sqlite3.Error:
        pass
    return fallback


def pct(values, q):
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * q / 100.0
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def fmt(x, nd=1):
    return "-" if x is None else f"{x:.{nd}f}"


def report(db, nights, tz_name, min_gap_min=10):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    tz_name = tz_name or server_tz(conn, "America/New_York")
    tz = ZoneInfo(tz_name) if ZoneInfo else timezone.utc
    since = datetime.utcnow() - timedelta(days=nights)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(recordings)")}
    bb = "r.bird_buddy_media_id" if "bird_buddy_media_id" in cols else "NULL"
    rows = conn.execute(f"""
        SELECT r.id, r.trigger_timestamp, r.energy_db, r.snr_db, r.device_id,
               r.haikubox_detection_id, {bb}, COALESCE(r.is_bat, 0),
               d.common_name, d.confidence, d.source
        FROM recordings r LEFT JOIN detections d ON d.recording_id = r.id
        WHERE r.deleted_at IS NULL AND r.trigger_timestamp >= ?
    """, (since.strftime("%Y-%m-%d %H:%M:%S"),)).fetchall()

    def local(ts):
        t = datetime.fromisoformat(str(ts).replace("Z", "")[:26])
        return t.replace(tzinfo=timezone.utc).astimezone(tz)

    def origin(hk, bbid):
        return "haikubox" if hk else "birdbuddy" if bbid else "device"

    print(f"\n=== {db}  (last {nights} night(s), {tz_name}) ===")
    if not rows:
        print("No recordings in range.")
        return

    by_hour = defaultdict(Counter)
    species = defaultdict(lambda: {"device": 0, "haikubox": 0, "best": 0.0, "last": None})
    chirp_hits = defaultdict(list)      # species -> [local times]
    hk_hits = []                        # (time, species, conf)
    recs = {}
    owl_conf = []

    for (rid, ts, energy, snr, dev, hk, bbid, is_bat, name, conf, src) in rows:
        t = local(ts)
        o = origin(hk, bbid)
        night = t.hour in NIGHT_HOURS
        if o == "device" and not is_bat and night:
            r = recs.setdefault(rid, {"energy": energy, "snr": snr, "n": 0})
            if name:
                r["n"] += 1
        if not name or is_bat:
            continue
        if night:
            by_hour[t.hour][o] += 1
        if is_nocturnal(name):
            s = species[name]
            s[o if o in ("device", "haikubox") else "device"] += 1
            if o == "device":
                s["best"] = max(s["best"], conf or 0)
                chirp_hits[name].append(t)
                if "Owl" in name:
                    owl_conf.append(conf or 0)
            else:
                hk_hits.append((t, name, conf))
            s["last"] = max(s["last"], t) if s["last"] else t

    print("\n1. Night activity by local hour (detections)")
    print("   hour  device  haikubox")
    for h in NIGHT_HOURS:
        c = by_hour.get(h, Counter())
        print(f"   {h:02d}    {c['device']:6d}  {c['haikubox']:8d}")

    print("\n2. Nocturnal species")
    if not species:
        print("   none")
    else:
        print(f"   {'species':32s} {'chirp':>6s} {'haikubox':>9s} {'best':>5s}  last heard")
        for name, s in sorted(species.items(), key=lambda kv: -(kv[1]["haikubox"] + kv[1]["device"])):
            last = s["last"].strftime("%m-%d %H:%M") if s["last"] else "-"
            best = fmt(s["best"], 2) if s["device"] else "-"
            print(f"   {name[:32]:32s} {s['device']:6d} {s['haikubox']:9d} {best:>5s}  {last}")

    print(f"\n3. Missed (Haikubox nocturnal, no Chirp same species within {min_gap_min} min)")
    missed = []
    gap = timedelta(minutes=min_gap_min)
    for t, name, conf in sorted(hk_hits):
        if not any(abs(t - c) <= gap for c in chirp_hits.get(name, [])):
            missed.append((t, name, conf))
    if not missed:
        print("   none")
    # Haikubox's API has no confidence score (stored as a fixed 0.90), so it isn't shown.
    missed.sort(key=lambda m: (m[0].hour not in NIGHT_HOURS, m[0]))
    for t, name, _conf in missed[:40]:
        tag = "" if t.hour in NIGHT_HOURS else "  (daytime)"
        print(f"   {t.strftime('%m-%d %H:%M')}  {name}{tag}")
    if len(missed) > 40:
        print(f"   … {len(missed) - 40} more")
    total_hk = len(hk_hits)
    if total_hk:
        print(f"   Chirp caught {total_hk - len(missed)}/{total_hk} ({100 * (total_hk - len(missed)) / total_hk:.0f}%) of Haikubox nocturnal detections")

    print("\n4. Night device recordings")
    en = [r["energy"] for r in recs.values() if r["energy"] is not None]
    sn = [r["snr"] for r in recs.values() if r["snr"] is not None]
    empty = sum(1 for r in recs.values() if r["n"] == 0)
    print(f"   recordings={len(recs)}  with no detection={empty}"
          "  (auto-purged recordings are gone and not counted; check docker logs for 'Auto-purge')")
    print(f"   trigger level dBFS p10/p50/p90: {fmt(pct(en, 10))} / {fmt(pct(en, 50))} / {fmt(pct(en, 90))}")
    print(f"   SNR dB p10/p50/p90:             {fmt(pct(sn, 10))} / {fmt(pct(sn, 50))} / {fmt(pct(sn, 90))}")

    print("\n5. Owl confidence (device)")
    if not owl_conf:
        print("   no owl detections from devices")
    else:
        bins = Counter(min(int(c * 10), 9) for c in owl_conf)
        for b in range(10):
            if bins[b]:
                print(f"   {b / 10:.1f}-{(b + 1) / 10:.1f}  {'#' * min(bins[b], 60)} {bins[b]}")
    conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="SQLite database (default: all found under --data-dir)")
    ap.add_argument("--data-dir", default=os.environ.get("CHIRP_DATA_DIR", "/app/data"))
    ap.add_argument("--nights", type=int, default=7)
    ap.add_argument("--tz", help="IANA timezone (default: server setting)")
    ap.add_argument("--gap", type=int, default=10, help="Match window in minutes for section 3")
    a = ap.parse_args()
    dbs = [a.db] if a.db else find_dbs(a.data_dir)
    if not dbs:
        print(f"No databases found under {a.data_dir}", file=sys.stderr)
        return 1
    for db in dbs:
        try:
            report(db, a.nights, a.tz, a.gap)
        except sqlite3.Error as e:
            print(f"\n=== {db} ===\n  skipped: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
