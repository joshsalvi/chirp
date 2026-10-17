"""CHIRP_NOTIFICATIONS_OFF=1: this server sends no push notifications or
emails and runs none of the timed journals, digests or summaries. For a
retired server kept running only for its redirect or LAN access, so phones
registered with both it and the new server don't get everything twice."""
import os


def notifications_off() -> bool:
    return os.environ.get("CHIRP_NOTIFICATIONS_OFF", "").strip().lower() in ("1", "true", "yes", "on")
