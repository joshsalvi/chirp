"""
When a recording was made, for uploads and edits.

parse_recorded_at("2026-10-01T00:11:58-04:00", tz)  -> naive UTC
parse_recorded_at("2026-10-01T00:11:58", tz)        -> read in tz, naive UTC
time_from_filename("Barred_Owl_H_Oct_1_2026_121158_AM.wav", tz) -> naive UTC

Filenames carry local time. Patterns: HaikuBox (Mon_D_YYYY_HHMMSS_AM),
YYYYMMDD_HHMMSS (Chirp, AudioMoth, Song Meter, most recorders) and
YYYY-MM-DD[ _T]HH[-:.]MM[-:.]SS.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

_HAIKU = re.compile(
    r"(?<![A-Za-z])(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[_\- ](\d{1,2})[_\- ,]+(\d{4})"
    r"[_\- ]+(\d{1,2})(\d{2})(\d{2})[_\- ]?(AM|PM)?", re.I)
_COMPACT = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})[_\-T ]?(\d{2})(\d{2})(\d{2})(?!\d)")
_ISOISH = re.compile(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})[_T ](\d{2})[-:.](\d{2})[-:.](\d{2})(?!\d)")


def _zone(tz_name: Optional[str]):
    if ZoneInfo and tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    return timezone.utc


def _to_utc(local: datetime, tz_name: Optional[str]) -> datetime:
    if local.tzinfo is None:
        local = local.replace(tzinfo=_zone(tz_name))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _sane(ts: datetime) -> bool:
    return datetime(2000, 1, 1) <= ts <= datetime.utcnow() + timedelta(days=1)


def parse_recorded_at(value: Optional[str], tz_name: Optional[str]) -> Optional[datetime]:
    """ISO 8601 date-time to naive UTC; None if empty or unreadable.
    Without an offset it's read in tz_name. Raises ValueError for a time in
    the future or before 2000."""
    if not value or not str(value).strip():
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(s)
    except ValueError:
        try:
            from dateutil.parser import parse as _p
            ts = _p(s)
        except Exception:
            return None
    out = _to_utc(ts, tz_name)
    if not _sane(out):
        raise ValueError("Recording time must be after 2000 and not in the future")
    return out


def time_from_filename(name: Optional[str], tz_name: Optional[str]) -> Optional[datetime]:
    """Recording time from a file name in the recording's local time, or None."""
    if not name:
        return None
    try:
        m = _HAIKU.search(name)
        if m:
            mon, day, year, hh, mm, ss, ampm = m.groups()
            h = int(hh)
            if ampm:
                h = h % 12 + (12 if ampm.upper() == "PM" else 0)
            local = datetime(int(year), _MONTHS[mon[:3].lower()], int(day), h, int(mm), int(ss))
        else:
            m = _COMPACT.search(name) or _ISOISH.search(name)
            if not m:
                return None
            local = datetime(*(int(x) for x in m.groups()))
    except (ValueError, KeyError):
        return None
    out = _to_utc(local, tz_name)
    return out if _sane(out) else None
