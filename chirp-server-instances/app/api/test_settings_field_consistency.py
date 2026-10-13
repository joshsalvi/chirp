#!/usr/bin/env python3
"""
Structural consistency check for app_settings.py — catches the exact
bug class that caused ai_personality_depth to silently not persist:
a field present in _MIGRATION_DEFAULTS (and on the AppSettings model
itself) but missing from SettingsIn (the PUT request schema) or
SettingsOut (the GET response schema).

That specific mismatch is a real, dangerous failure mode precisely
because it's SILENT — Pydantic drops unrecognized fields from an
incoming request body with no error, no warning, nothing in any log.
The frontend correctly sends the value, the backend correctly receives
the HTTP request, and the value simply vanishes before the database
write loop ever sees it. A person saving a setting has no way to know
it didn't take effect except by reloading the page and noticing the
old value is still there — exactly what happened.

This test doesn't require a running server or database; it's pure
introspection of the three Python objects and takes well under a
second to run — cheap enough to run before every release, not just
when a bug like this is reported.

Run directly: python3 app/api/test_settings_field_consistency.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.api.app_settings import SettingsIn, SettingsOut, _MIGRATION_DEFAULTS  # noqa: E402


def main():
    migration_default_fields = {name for name, _ in _MIGRATION_DEFAULTS}
    settings_in_fields = set(SettingsIn.model_fields.keys())
    settings_out_fields = set(SettingsOut.model_fields.keys())

    missing_from_in = migration_default_fields - settings_in_fields
    missing_from_out = migration_default_fields - settings_out_fields

    print("=== app_settings.py field consistency check ===\n")
    print(f"Fields in _MIGRATION_DEFAULTS: {len(migration_default_fields)}")
    print(f"Fields in SettingsIn (PUT request schema): {len(settings_in_fields)}")
    print(f"Fields in SettingsOut (GET response schema): {len(settings_out_fields)}\n")

    failed = False

    if missing_from_in:
        failed = True
        print("FAIL: the following fields have a real migration default but are")
        print("      MISSING from SettingsIn — a PUT request setting any of these")
        print("      will silently do nothing, exactly the bug this test exists to catch:")
        for f in sorted(missing_from_in):
            print(f"        - {f}")
        print()

    if missing_from_out:
        failed = True
        print("FAIL: the following fields have a real migration default but are")
        print("      MISSING from SettingsOut — GET /api/v1/settings will never")
        print("      return their real value to the frontend:")
        for f in sorted(missing_from_out):
            print(f"        - {f}")
        print()

    if failed:
        print("Fix: add the missing field(s) to SettingsIn and/or SettingsOut in")
        print("     app/api/app_settings.py, matching the type used elsewhere for")
        print("     that field on the AppSettings model.")
        sys.exit(1)

    print("PASS: every field with a real migration default is present in both")
    print("      SettingsIn and SettingsOut — no silently-unsettable fields.")


if __name__ == "__main__":
    main()
