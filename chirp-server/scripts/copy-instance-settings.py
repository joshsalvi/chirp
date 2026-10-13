#!/usr/bin/env python3
"""
Copies ONLY the shared AI/eBird credentials from one chirp-server
instance's database into another's — not tenant-specific settings
(location, notification preferences, device keys, users, anything
else), which stay genuinely independent per instance, matching the
"centralized keys, everything else separate" model this multi-instance
approach was chosen for.

Operates directly on each instance's own chirp.db file via plain
sqlite3 — no need to go through either instance's running API, and no
dependency on the app's own code at all, since both databases share the
identical schema (same Docker image, same migrations). Real, not
theoretical: both are literally the same file format, this just copies
specific column values from one AppSettings row to another.

Usage:
    python3 scripts/copy-instance-settings.py <source-data-dir> <dest-data-dir>

Example (using the actual host paths from docker-compose.yml's volume
mounts, not paths inside any container):
    python3 scripts/copy-instance-settings.py \\
        /mnt/user/data/media/miscellaneous/chirp-data \\
        /mnt/user/data/media/miscellaneous/chirp-data-natick

Only copies keys that are actually SET on the source (non-empty) — never
overwrites a real destination value with a genuinely blank one, so
running this against a destination that already has its own key
configured won't silently wipe it.
"""
import argparse
import os
import sqlite3
import sys

# The specific fields this copies — deliberately a short, explicit list,
# not "everything in app_settings" — see this script's own docstring for
# why only these are meant to be shared across instances at all.
SHARED_FIELDS = [
    "anthropic_api_key",
    "openai_api_key",
    "gemini_api_key",
    "ollama_base_url",
    "ollama_model",
    "ebird_api_key",
    "ebird_st_api_key",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source_data_dir", help="Host path to the SOURCE instance's data directory (contains chirp.db)")
    parser.add_argument("dest_data_dir", help="Host path to the DESTINATION instance's data directory (contains chirp.db)")
    parser.add_argument("--force", action="store_true", help="Overwrite a real, already-set destination value too, not just blank ones")
    args = parser.parse_args()

    source_db = os.path.join(args.source_data_dir, "chirp.db")
    dest_db = os.path.join(args.dest_data_dir, "chirp.db")

    for path, label in [(source_db, "source"), (dest_db, "destination")]:
        if not os.path.isfile(path):
            print(f"Error: {label} database not found at {path}", file=sys.stderr)
            print("Both instances need to have started at least once (so their database and default AppSettings row exist) before this can run.", file=sys.stderr)
            sys.exit(1)

    src_conn = sqlite3.connect(source_db)
    dst_conn = sqlite3.connect(dest_db)
    try:
        src_row = src_conn.execute(
            f"SELECT {', '.join(SHARED_FIELDS)} FROM app_settings WHERE id = 1"
        ).fetchone()
        if src_row is None:
            print(f"Error: no app_settings row (id=1) found in {source_db} — has that instance completed first-run setup?", file=sys.stderr)
            sys.exit(1)

        dst_row = dst_conn.execute(
            f"SELECT {', '.join(SHARED_FIELDS)} FROM app_settings WHERE id = 1"
        ).fetchone()
        if dst_row is None:
            print(f"Error: no app_settings row (id=1) found in {dest_db} — has that instance completed first-run setup?", file=sys.stderr)
            sys.exit(1)

        updates = {}
        skipped = []
        for field, src_value, dst_value in zip(SHARED_FIELDS, src_row, dst_row):
            if not src_value:
                continue  # nothing real to copy for this field
            if dst_value and not args.force:
                skipped.append(field)
                continue
            updates[field] = src_value

        if not updates:
            print("Nothing to copy — either the source has no keys set, or the destination already has its own values for everything the source has (use --force to overwrite).")
            return

        set_clause = ", ".join(f"{f} = ?" for f in updates)
        dst_conn.execute(f"UPDATE app_settings SET {set_clause} WHERE id = 1", list(updates.values()))
        dst_conn.commit()

        print(f"Copied {len(updates)} field(s) from {args.source_data_dir} to {args.dest_data_dir}:")
        for f in updates:
            print(f"  {f}")
        if skipped:
            print(f"\nSkipped {len(skipped)} field(s) already set on the destination (use --force to overwrite anyway):")
            for f in skipped:
                print(f"  {f}")
        print("\nRestart the destination instance's container for the change to take effect if it's currently running with these values already cached in memory.")
    finally:
        src_conn.close()
        dst_conn.close()


if __name__ == "__main__":
    main()
