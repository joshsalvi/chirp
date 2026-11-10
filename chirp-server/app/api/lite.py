"""
Chirp Lite: compact, photo-first data for the simplified app (/lite on the
web, and the Chirp Lite iPhone app). Same accounts and data as Chirp Pro;
each route returns only what one Lite screen draws, in one request.

  GET /lite/today            today at a glance: hero bird, species, hourly activity, one-line journal
  GET /lite/birds            every bird heard, as a photo grid (sort: recent | most | new | az)
  GET /lite/listen           recordings as cards (bird=…, before=… for paging)
  GET /lite/guide            birds expected near you this month, with how likely and whether heard
  GET /lite/bird/{id}        a simple profile: photos, song, three facts, blurb
  GET /lite/recording/{id}/songline   loudness bars, where each bird was identified, and call marks

Which app someone sees is User.ui_mode (api/auth.py ui_mode_for).
"""
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSettings, BirdPhoto, BirdProfile, Detection, Recording

router = APIRouter()

ROBIN_CM = 25.0          # American Robin, the everyday size yardstick
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ── Shared helpers ───────────────────────────────────────────────────────────

def _settings(db: Session):
    return db.query(AppSettings).filter(AppSettings.id == 1).first()


def _tz(s) -> ZoneInfo:
    try:
        return ZoneInfo((s.timezone if s else None) or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat() + ("Z" if dt.tzinfo is None else "")


def photo_of(p: Optional[BirdProfile]) -> Optional[str]:
    if p is None:
        return None
    if p.photo_path and os.path.exists(p.photo_path):
        return f"/api/v1/birds/{p.id}/photo"
    return p.photo_url or None


def _bird_filters(s):
    """Recordings a Lite screen counts: birds (not bats), not deleted, not Haikubox
    imports or Live Detect clips, at or above the site's display confidence."""
    f = [Recording.is_bat.isnot(True),
         Recording.haikubox_detection_id.is_(None),
         Recording.is_live_detect_clip.isnot(True)]
    if not (s and getattr(s, "show_deleted_detections", False)):
        f.append(Recording.deleted_at.is_(None))
    min_conf = float(getattr(s, "min_confidence_display", 0.0) or 0.0) if s else 0.0
    if min_conf > 0:
        f.append(Detection.confidence >= min_conf)
    return f


def _profiles(db: Session, names) -> dict:
    names = {n for n in names if n}
    if not names:
        return {}
    return {p.common_name: p for p in db.query(BirdProfile).filter(BirdProfile.common_name.in_(names)).all()}


def first_sentences(text: Optional[str], limit: int = 240) -> Optional[str]:
    """The first sentence or two of `text`, under `limit` characters."""
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    out = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if out and len(out) + 1 + len(sentence) > limit:
            break
        out = f"{out} {sentence}".strip()
        if len(out) >= limit * 0.6:
            break
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0] + "…"
    return out or None


def journal_excerpt(text: Optional[str], limit: int = 200) -> Optional[str]:
    """A line from the journal for a dashboard: its first sentence or two,
    skipping an opening question ("What keeps the yard so busy…?")."""
    text = re.sub(r"\s+", " ", text or "").strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    while len(parts) > 1 and parts[0].endswith("?"):
        parts.pop(0)
    return first_sentences(" ".join(parts), limit)


def larger_photo(url: Optional[str]) -> Optional[str]:
    """iNaturalist serves sizes by name; the dashboard's big photo uses "large"."""
    if url and "inaturalist" in url:
        return re.sub(r"/(medium|small)\.(jpe?g|png)$", r"/large.\2", url)
    return url


# ── Today ────────────────────────────────────────────────────────────────────

@router.get("/today")
def today(db: Session = Depends(get_db)):
    s = _settings(db)
    tz = _tz(s)
    now = datetime.now(ZoneInfo("UTC")).astimezone(tz)
    start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    rows = (db.query(Detection.common_name, Recording.id, Recording.trigger_timestamp, Recording.wav_path)
            .join(Recording, Detection.recording_id == Recording.id)
            .filter(Recording.trigger_timestamp >= start_utc, *_bird_filters(s))
            .order_by(Recording.trigger_timestamp.desc(), Detection.confidence.desc())
            .all())

    counts: Counter = Counter()
    last: dict = {}
    hourly = [0] * 24
    seen_recs = set()
    for name, rec_id, ts, _wav in rows:
        counts[name] += 1
        last.setdefault(name, ts)
        if rec_id not in seen_recs:
            seen_recs.add(rec_id)
            local = ts.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
            hourly[local.hour] += 1

    # Birds heard for the first time ever today.
    new_today = set()
    if counts:
        firsts = (db.query(Detection.common_name, func.min(Recording.trigger_timestamp))
                  .join(Recording, Detection.recording_id == Recording.id)
                  .filter(Detection.common_name.in_(list(counts)), *_bird_filters(s))
                  .group_by(Detection.common_name).all())
        new_today = {n for n, first in firsts if first and first >= start_utc}

    profiles = _profiles(db, counts)
    species = [{
        "name": n,
        "profile_id": profiles[n].id if n in profiles else None,
        "photo": photo_of(profiles.get(n)),
        "count": c,
        "last": _iso(last[n]),
        "new": n in new_today,
    } for n, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    # The hero: the newest bird today, else the newest ever.
    hero = None
    if rows:
        name, rec_id, ts, wav = rows[0]
        hero = {"name": name, "recording_id": rec_id, "time": _iso(ts), "today": True,
                "has_audio": bool(wav and os.path.exists(wav))}
    else:
        from .watch import recent_rows
        r = recent_rows(db, 1)
        if r:
            hero = {"name": r[0]["species"], "recording_id": r[0]["id"], "time": r[0]["time"], "today": False,
                    "has_audio": r[0]["has_audio"]}
    if hero:
        p = profiles.get(hero["name"]) or _profiles(db, [hero["name"]]).get(hero["name"])
        hero["profile_id"] = p.id if p else None
        hero["photo"] = photo_of(p)
        hero["photo_large"] = larger_photo(hero["photo"])

    # One line from today's Daily Journal, when it's been written today.
    summary = None
    if s and s.daily_summary_text and s.daily_summary_generated_at:
        made = s.daily_summary_generated_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        if made.date() == now.date():
            summary = first_sentences(s.daily_summary_text, 200)
    # The latest journal (today's or yesterday's), for the web dashboard.
    journal = None
    if s and s.daily_summary_text and s.daily_summary_generated_at:
        made = s.daily_summary_generated_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        age = (now.date() - made.date()).days
        if 0 <= age <= 1:
            journal = {"text": journal_excerpt(s.daily_summary_text), "day": "today" if age == 0 else "yesterday"}

    from .tv import stations
    return {
        "date": now.date().isoformat(),
        "species_count": len(counts),
        "detections": sum(counts.values()),
        "recordings": len(seen_recs),
        "new_count": len(new_today),
        # The day's first bird (rows run newest first).
        "first_song": {"name": rows[-1][0], "time": _iso(rows[-1][2])} if rows else None,
        "hero": hero,
        "species": species,
        "hourly": hourly,
        "summary": summary,
        "journal": journal,
        "can_listen_live": bool(stations(db)),
    }


# ── Birds (life list as a photo grid) ────────────────────────────────────────

@router.get("/birds")
def birds(sort: str = Query("recent", pattern="^(recent|most|new|az)$"), db: Session = Depends(get_db)):
    from .birds import get_life_list
    life = get_life_list(BackgroundTasks(), db)
    week_ago = datetime.utcnow() - timedelta(days=7)
    out = []
    for b in life:
        if b.get("is_bat"):
            continue
        first = b.get("first_detected")
        out.append({
            "name": b["common_name"],
            "profile_id": b.get("profile_id"),
            "photo": b.get("photo_url"),
            "count": b.get("total_detections") or 0,
            "first": first,
            "last": b.get("last_detected"),
            "new": bool(first and datetime.fromisoformat(first.replace("Z", "")) >= week_ago),
        })
    key = {
        "recent": lambda x: x["last"] or "",
        "most": lambda x: x["count"],
        "new": lambda x: x["first"] or "",
        "az": lambda x: x["name"].lower(),
    }[sort]
    out.sort(key=key, reverse=sort != "az")
    return {"count": len(out), "birds": out}


# ── Listen (recordings as cards) ─────────────────────────────────────────────

@router.get("/listen")
def listen(limit: int = Query(24, ge=1, le=60), before: Optional[str] = None, bird: Optional[str] = None,
           db: Session = Depends(get_db)):
    s = _settings(db)
    q = (db.query(Recording)
         .join(Detection, Detection.recording_id == Recording.id)
         .filter(*_bird_filters(s)))
    if bird:
        q = q.filter(Detection.common_name == bird)
    if before:
        try:
            q = q.filter(Recording.trigger_timestamp < datetime.fromisoformat(before.replace("Z", "")))
        except ValueError:
            raise HTTPException(400, "before must be an ISO date-time")
    recs = q.distinct().order_by(Recording.trigger_timestamp.desc()).limit(limit).all()

    min_conf = float(getattr(s, "min_confidence_display", 0.0) or 0.0) if s else 0.0
    cards, names = [], set()
    for r in recs:
        dets = sorted((d for d in r.detections if (d.confidence or 0) >= min_conf),
                      key=lambda d: d.confidence or 0, reverse=True)
        birds_in = []
        for d in dets:
            if d.common_name not in birds_in:
                birds_in.append(d.common_name)
        if bird and bird in birds_in:          # the filtered bird leads its card
            birds_in.remove(bird)
            birds_in.insert(0, bird)
        names.update(birds_in[:3])
        lead = next((d for d in dets if d.common_name == birds_in[0]), None) if birds_in else None
        cards.append({
            "id": r.id,
            "time": _iso(r.trigger_timestamp),
            "duration": round(float(r.duration_seconds or 0), 1),
            "bird": birds_in[0] if birds_in else "Recording",
            "others": birds_in[1:3],
            "starts_at": round(float(lead.start_time or 0), 1) if lead else 0,
            "has_audio": bool(r.wav_path and os.path.exists(r.wav_path)),
            "audio": f"/api/v1/recordings/{r.id}/audio",
            "spectrogram": f"/api/v1/recordings/{r.id}/spectrogram",
        })
    profiles = _profiles(db, names)
    for c in cards:
        p = profiles.get(c["bird"])
        c["profile_id"] = p.id if p else None
        c["photo"] = photo_of(p)
        c["other_photos"] = [photo_of(profiles.get(n)) for n in c["others"]]
    return {"recordings": cards, "next_before": cards[-1]["time"] if len(cards) == limit else None}


# ── Song line (the players' scrub bar) ───────────────────────────────────────

@router.get("/recording/{recording_id}/songline")
def songline(recording_id: str, bird: Optional[str] = None, db: Session = Depends(get_db)):
    """Loudness bars of the clip, where each bird was identified, and call
    marks for `bird` (default: the most confident bird in it)."""
    from ..services import songline as sl
    r = db.query(Recording).filter(Recording.id == recording_id).first()
    if not r:
        raise HTTPException(404, "Recording not found")
    s = _settings(db)
    min_conf = float(getattr(s, "min_confidence_display", 0.0) or 0.0) if s else 0.0
    dets = [d for d in r.detections if (d.confidence or 0) >= min_conf and d.common_name]
    spans = defaultdict(list)
    for d in dets:
        spans[d.common_name].append((float(d.start_time or 0), float(d.end_time or (d.start_time or 0) + 3)))
    if not bird or bird not in spans:
        best = max(dets, key=lambda d: d.confidence or 0, default=None)
        bird = best.common_name if best else None
    path = r.wav_path if r.wav_path and os.path.exists(r.wav_path) else None
    return sl.build(path, float(r.duration_seconds or 0), dict(spans), bird)


# ── Guide (birds near you this month) ────────────────────────────────────────

def likelihood_label(freq: float) -> str:
    """eBird checklist frequency for this month → a word. 25%+ of checklists
    is common, 5%+ uncommon, anything less rare."""
    if freq >= 0.25:
        return "common"
    if freq >= 0.05:
        return "uncommon"
    return "rare"


@router.get("/guide")
def guide(limit: int = Query(150, ge=1, le=400), db: Session = Depends(get_db)):
    from .birds import get_regional_library
    regional = get_regional_library(BackgroundTasks(), limit=1000, search=None, detected_only=False, db=db)
    month = datetime.now().month - 1
    rows = []
    for r in regional:
        mf = r.get("monthly_frequency") or []
        freq = float(mf[month]) if len(mf) == 12 and mf[month] is not None else float(r.get("current_likelihood") or 0)
        heard = bool(r.get("locally_detected"))
        if freq <= 0 and not heard:
            continue
        rows.append({"name": r["common_name"], "photo": r.get("photo_url"), "chance": round(freq, 3),
                     "likely": likelihood_label(freq), "heard": heard})
    profiles = _profiles(db, [r["name"] for r in rows])
    rows = [r for r in rows if not getattr(profiles.get(r["name"]), "is_bat", False)]   # birds only
    rows.sort(key=lambda x: x["chance"], reverse=True)
    rows = rows[:limit]
    for r in rows:
        p = profiles.get(r["name"])
        r["profile_id"] = p.id if p else None
        r["photo"] = r["photo"] or photo_of(p)
    return {"month": MONTHS[month], "count": len(rows), "heard": sum(r["heard"] for r in rows), "birds": rows}


# ── Bird (simple profile) ────────────────────────────────────────────────────

def size_fact(p: BirdProfile) -> Optional[dict]:
    lo, hi = p.aab_length_min_cm, p.aab_length_max_cm
    if not lo and not hi:
        return None
    cm = ((lo or hi) + (hi or lo)) / 2
    ratio = cm / ROBIN_CM
    if ratio < 0.6:
        word = "Much smaller than a robin"
    elif ratio < 0.9:
        word = "Smaller than a robin"
    elif ratio <= 1.15:
        word = "About robin-sized"
    elif ratio <= 1.8:
        word = "Bigger than a robin"
    else:
        word = "Much bigger than a robin"
    return {"label": word, "cm": round(cm), "detail": p.aab_length_text}


def season_fact(freq) -> Optional[str]:
    """Months a bird is around (10%+ of checklists, or 1/4 of its peak) as words."""
    if not freq or len(freq) != 12:
        return None
    peak = max(f or 0 for f in freq)
    if peak <= 0:
        return None
    on = [(f or 0) >= max(0.1 * peak, 0.01) and (f or 0) >= 0.25 * peak for f in freq]
    if all(on):
        return "All year"
    if not any(on):
        return None
    # Longest run, wrapping around the new year.
    best, best_start = 0, 0
    for start in range(12):
        n = 0
        while n < 12 and on[(start + n) % 12]:
            n += 1
        if n > best:
            best, best_start = n, start
    if best == 1:
        return MONTHS[best_start]
    return f"{MONTHS[best_start]}–{MONTHS[(best_start + best - 1) % 12]}"


def how_often(days_30: int) -> str:
    if days_30 >= 20:
        return "Most days"
    if days_30 >= 8:
        return "Many days"
    if days_30 >= 2:
        return "Now and then"
    if days_30 == 1:
        return "Once this month"
    return "Not this month"


# Range maps already on disk, best first (see range_map_of).
_CORNELL = {"aab": "All About Birds", "macaulay": "Macaulay Library"}


def range_map_of(p: BirdProfile, s=None) -> dict:
    """range_map: the URL to show (an SVG for Wikipedia maps); range_map_image:
    the same map as a picture, for the iPhone app (Wikipedia SVGs are drawn
    to PNG by /birds/{id}/range-map/png).

    First choice is the local map from the iNaturalist range dataset
    (services/range_library.py draws one for every bird and bat); then
    eBird Status & Trends, Cornell, BirdLife and Wikipedia."""
    from ..config import settings as cfg
    from ..services import range_library as rl
    folder = rl.species_dir(cfg.media_dir, p.common_name)

    def found(url, label, vector=False):
        return {"range_map": url, "range_map_source": label, "range_map_vector": vector,
                "range_map_image": f"/api/v1/birds/{p.id}/range-map/png" if vector else url}

    def on_disk(src):
        f = os.path.join(folder, f"range_map_{src}.png")
        return os.path.exists(f) and os.path.getsize(f) > 1000

    lat, lon = (getattr(s, "latitude", None), getattr(s, "longitude", None)) if s else (None, None)
    if rl.generic_bat(p):
        local = rl.map_file(cfg.media_dir, p, lat, lon)
        if rl.have_map(local):
            return found(f"/api/v1/birds/{p.id}/range-map/local", "iNaturalist")
    elif on_disk("geomodel"):
        return found(f"/api/v1/birds/{p.id}/range-map/geomodel", "iNaturalist")
    if on_disk("ebird_st"):
        return found(f"/api/v1/birds/{p.id}/range-map/ebird_st", "eBird Status & Trends")
    u = p.range_map_url or ""
    if p.range_map_source in _CORNELL and u.startswith("file://"):
        f = u[7:]
        if os.path.exists(f) and os.path.getsize(f) > 500 and not f.lower().endswith(".svg"):
            return found(f"/api/v1/birds/{p.id}/range-map", _CORNELL[p.range_map_source])
    if on_disk("birdlife"):
        return found(f"/api/v1/birds/{p.id}/range-map/birdlife", "BirdLife")
    if u or p.range_map_source:
        vector = p.range_map_source == "wikipedia" or "svg" in u.lower()
        return found(f"/api/v1/birds/{p.id}/range-map", _CORNELL.get(p.range_map_source) or "Wikipedia", vector)
    return {"range_map": None, "range_map_source": None, "range_map_vector": False, "range_map_image": None}


@router.get("/bird/{profile_id}")
def bird(profile_id: str, db: Session = Depends(get_db)):
    p = db.query(BirdProfile).filter(BirdProfile.id == profile_id).first()
    if not p:
        raise HTTPException(404, "Bird not found")
    s = _settings(db)
    filters = [Detection.common_name == p.common_name, *_bird_filters(s)]

    total, first, last = (db.query(func.count(Detection.id), func.min(Recording.trigger_timestamp),
                                   func.max(Recording.trigger_timestamp))
                          .join(Recording, Detection.recording_id == Recording.id).filter(*filters).one())
    month_ago = datetime.utcnow() - timedelta(days=30)
    days_30 = (db.query(func.count(func.distinct(func.date(Recording.trigger_timestamp))))
               .join(Detection, Detection.recording_id == Recording.id)
               .filter(*filters, Recording.trigger_timestamp >= month_ago).scalar()) or 0

    # Its song: the clearest recording here, else a reference call.
    song = None
    best = (db.query(Detection, Recording).join(Recording, Detection.recording_id == Recording.id)
            .filter(*filters).order_by(Detection.confidence.desc()).limit(10).all())
    for d, r in best:
        if r.wav_path and os.path.exists(r.wav_path):
            song = {"kind": "yours", "recording_id": r.id, "audio": f"/api/v1/recordings/{r.id}/audio",
                    "starts_at": round(float(d.start_time or 0), 1), "time": _iso(r.trigger_timestamp)}
            break
    if song is None:
        for i, c in enumerate(p.call_media or []):
            path, url = c.get("path"), c.get("url")
            if (path and os.path.exists(path)) or url:
                song = {"kind": "reference", "audio": f"/api/v1/birds/{p.id}/calls/{i}" if path and os.path.exists(path) else url,
                        "credit": c.get("credit") or c.get("attribution")}
                break

    photos = []
    main = photo_of(p)
    if main:
        photos.append({"url": main, "credit": p.photo_credit})
    for x in (p.extra_photos or [])[:5]:
        if x.get("url"):
            photos.append({"url": x["url"], "credit": x.get("credit")})
    for bp in (db.query(BirdPhoto).filter(BirdPhoto.bird_profile_id == p.id, BirdPhoto.ai_match.isnot(False))
               .order_by(BirdPhoto.uploaded_at.desc()).limit(4).all()):
        photos.append({"url": f"/api/v1/birds/photos/{bp.id}/file", "credit": bp.uploaded_by, "yours": True})

    tags = [{"kind": k, "label": v} for k, v in (("habitat", p.aab_habitat), ("food", p.aab_food),
            ("nesting", p.aab_nesting), ("behavior", p.aab_behavior)) if v]
    facts = [f for f in (p.aab_cool_facts or []) if isinstance(f, str)]

    return {
        "id": p.id,
        "name": p.common_name,
        "scientific": p.scientific_name,
        "photos": photos,
        "song": song,
        "size": size_fact(p),
        "season": season_fact(p.monthly_frequency),
        "how_often": how_often(int(days_30)),
        "heard_count": int(total or 0),
        "first_heard": _iso(first),
        "last_heard": _iso(last),
        "blurb": first_sentences(p.aab_description or p.description, 240),
        "fun_fact": first_sentences(facts[0], 220) if facts else None,
        "tags": tags,
        **range_map_of(p, _settings(db)),
        "conservation": p.conservation_status,
    }
