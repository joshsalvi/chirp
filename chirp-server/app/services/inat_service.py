"""
iNaturalist submission service.

Submits a bird call recording as a Sound observation to iNaturalist
using the personal API token (JWT) from the user's account settings.

Token: https://www.inaturalist.org/users/api_token
API docs: https://api.inaturalist.org/v1/docs/
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("chirp.inat")

INAT_API_BASE = "https://api.inaturalist.org/v1"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"JWT {token}",
        "User-Agent": "Chirp-BirdDetection/1.0 (https://github.com/chirp)",
    }


def submit_observation(
    *,
    token: str,
    common_name: str,
    scientific_name: Optional[str],
    taxon_id: Optional[int],
    wav_path: str,
    observed_at: datetime,
    latitude: Optional[float],
    longitude: Optional[float],
    notes: str = "",
) -> dict:
    """
    Phase 1 — fast (≤10 s): create the iNaturalist observation and return.
    Sound attachment is deliberately NOT done here; call attach_sound_background()
    from a FastAPI BackgroundTask so the HTTP response beats Cloudflare's timeout.
    """
    if not token or not token.strip():
        raise RuntimeError("No iNaturalist API token configured in Settings.")
    token = token.strip()

    # Resolve taxon_id from name if missing
    if not taxon_id and scientific_name:
        taxon_id = _resolve_taxon_id(token, scientific_name, common_name)

    description = notes or (
        f"Automated detection by Chirp bird monitoring system. Species: {common_name}."
    )
    description = with_chirp_link(description)
    # Clamp observed date to today — iNaturalist rejects future dates with
    # a 422 "date observed can't be in the future" error. This can happen
    # if the recording timestamp is UTC while the local date is behind, or
    # from clock drift on the Pi. Using today's date as the ceiling is safe:
    # iNaturalist only needs the date, not the exact time.
    from datetime import date as _date
    today_str = _date.today().strftime("%Y-%m-%d")
    obs_date_str = observed_at.strftime("%Y-%m-%d")
    safe_date_str = obs_date_str if obs_date_str <= today_str else today_str
    obs_payload: dict = {
        "observation": {
            "species_guess":      common_name,
            "observed_on_string": safe_date_str,
            "description":        description,
            "captive_flag":       False,
        }
    }
    if taxon_id:
        obs_payload["observation"]["taxon_id"] = taxon_id
    if latitude and longitude:
        obs_payload["observation"]["latitude"]            = latitude
        obs_payload["observation"]["longitude"]           = longitude
        obs_payload["observation"]["positional_accuracy"] = 100

    with httpx.Client(timeout=20) as client:
        r = client.post(
            f"{INAT_API_BASE}/observations",
            json=obs_payload,
            headers=_headers(token),
        )
        if r.status_code not in (200, 201):
            body = r.text
            logger.error("iNat observation create failed %d: %s", r.status_code, body[:500])
            # Detect expired/invalid JWT — very common as tokens expire every 24 h
            if r.status_code in (401, 422) and (
                "expired" in body.lower() or "invalid" in body.lower() or
                "jwt" in body.lower() or "token" in body.lower()
            ):
                raise RuntimeError(
                    "Your iNaturalist API token has expired (tokens are valid for 24 hours). "
                    "Please go to Settings → API Keys, click the iNaturalist token field, "
                    "and paste a fresh token from https://www.inaturalist.org/users/api_token"
                )
            raise RuntimeError(
                f"iNaturalist observation creation failed ({r.status_code}): {body[:400]}"
            )
        obs      = r.json()
        obs_id   = obs.get("id")
        obs_uuid = obs.get("uuid", "")
        if not obs_id:
            raise RuntimeError(f"iNaturalist returned no observation ID: {obs}")

    logger.info("Created iNaturalist observation #%s for %s", obs_id, common_name)
    obs_url = f"https://www.inaturalist.org/observations/{obs_id}"
    return {"inat_id": obs_id, "inat_uuid": obs_uuid, "inat_url": obs_url, "sound_attached": False}


def attach_sound_background(
    *,
    token: str,
    obs_id: int,
    wav_path: str,
    recording_id: str,
    db_factory,
) -> None:
    """
    Phase 2 — background (slow): transcode WAV→MP3, attach sound to the observation,
    update the recording row.  Run via FastAPI BackgroundTask — never blocks the response.
    """
    import requests as _requests, subprocess, tempfile
    from time import sleep

    audio_bytes: bytes | None = None
    mp3_fd, mp3_str = tempfile.mkstemp(suffix=".mp3")
    os.close(mp3_fd)
    mp3 = Path(mp3_str)
    try:
        wav = Path(wav_path)
        if wav.exists() and wav.stat().st_size > 0:
            proc = subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav),
                 "-codec:a", "libmp3lame", "-ar", "44100", "-ac", "1", "-b:a", "128k",
                 str(mp3)],
                capture_output=True, timeout=60,
            )
            if proc.returncode == 0 and mp3.stat().st_size > 0:
                audio_bytes = mp3.read_bytes()
                logger.info("iNat bg: transcoded %s → %d bytes", wav.name, len(audio_bytes))
            else:
                logger.warning("iNat bg: ffmpeg rc=%d: %s", proc.returncode, proc.stderr.decode()[:200])
        else:
            logger.warning("iNat bg: WAV missing: %s", wav_path)
    except Exception as e:
        logger.warning("iNat bg: transcode error: %s", e)
    finally:
        mp3.unlink(missing_ok=True)

    sound_attached = False
    if audio_bytes:
        sleep(2.0)  # let iNat DB commit the observation
        try:
            resp = _requests.post(
                f"{INAT_API_BASE}/observation_sounds",
                headers={"Authorization": f"JWT {token}", "User-Agent": "Chirp-BirdDetection/1.0"},
                data={"observation_sound[observation_id]": str(obs_id)},
                files={"file": ("chirp.mp3", audio_bytes, "audio/mpeg")},
                timeout=30,
            )
            logger.debug("iNat bg: sound → %d: %s", resp.status_code, resp.text[:200])
            if resp.status_code in (200, 201):
                sound_attached = True
                logger.info("iNat bg: sound attached to obs #%s", obs_id)
            else:
                logger.warning("iNat bg: sound failed (%d): %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("iNat bg: sound exception: %s", e)

    # Update DB with actual sound status
    try:
        from ..models import Recording
        db = db_factory()
        try:
            rec = db.query(Recording).filter(Recording.id == recording_id).first()
            if rec and not sound_attached and rec.notes:
                rec.notes = rec.notes.replace("📎 iNaturalist:", "📎 iNaturalist 🔇:", 1)
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning("iNat bg: DB update failed: %s", e)



def _resolve_taxon_id(token: str, scientific_name: str, common_name: str) -> Optional[int]:
    """Look up iNaturalist taxon ID from scientific or common name."""
    for query in [scientific_name, common_name]:
        if not query:
            continue
        try:
            with httpx.Client(timeout=10) as c:
                r = c.get(
                    f"{INAT_API_BASE}/taxa",
                    params={"q": query, "rank": "species", "per_page": 1, "locale": "en"},
                    headers=_headers(token),
                )
                if r.status_code == 200:
                    results = r.json().get("results", [])
                    if results:
                        return results[0]["id"]
        except Exception as e:
            logger.debug("Taxon lookup failed for %r: %s", query, e)
    return None


def check_token(token: str) -> dict:
    """Verify a token against the iNaturalist /users/me endpoint."""
    if not token or not token.strip():
        return {"valid": False, "error": "No token provided"}
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{INAT_API_BASE}/users/me", headers=_headers(token.strip()))
        if r.status_code == 200:
            me = r.json().get("results", [{}])[0]
            return {"valid": True, "username": me.get("login"), "user_id": me.get("id")}
        return {"valid": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def attach_photo_background(
    *,
    token: str,
    obs_id: int,
    image_path: str,
) -> None:
    """
    Best-effort: attach an existing image file (e.g. the spectrogram, with
    detection-box overlays already baked in) to an observation as a second
    photo. Mirrors attach_sound_background's structure — runs as a
    FastAPI BackgroundTask, never blocks the response, and never raises;
    a failure here just means the observation ends up with one fewer
    photo, not a failed submission overall.
    """
    import requests as _requests
    from time import sleep

    path = Path(image_path)
    if not path.exists() or path.stat().st_size == 0:
        logger.warning("iNat bg: spectrogram image missing or empty: %s", image_path)
        return

    sleep(2.0)  # let iNat DB commit the observation, same as the sound attachment
    try:
        with open(path, "rb") as f:
            resp = _requests.post(
                f"{INAT_API_BASE}/observation_photos",
                headers={"Authorization": f"JWT {token}", "User-Agent": "Chirp-BirdDetection/1.0"},
                data={"observation_photo[observation_id]": str(obs_id)},
                files={"file": ("chirp_spectrogram.png", f, "image/png")},
                timeout=30,
            )
        logger.debug("iNat bg: spectrogram photo -> %d: %s", resp.status_code, resp.text[:200])
        if resp.status_code in (200, 201):
            logger.info("iNat bg: spectrogram attached to obs #%s", obs_id)
        else:
            logger.warning("iNat bg: spectrogram attach failed (%d): %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.warning("iNat bg: spectrogram attach exception: %s", e)


CHIRP_LINK = "https://ourchirp.com"


def with_chirp_link(text: str) -> str:
    """Append the Chirp link to text posted to iNaturalist, once."""
    text = (text or "").rstrip()
    if "ourchirp.com" in text.lower():
        return text
    line = f"Recorded with Chirp: {CHIRP_LINK}"
    return f"{text}\n\n{line}" if text else line


def post_comment(token: str, obs_id, body: str) -> dict:
    """
    Post a real comment on an existing iNaturalist observation, using
    the same POST /comments shape iNaturalist's own reference client
    (inaturalistjs) uses: {"comment": {"body": ..., "parent_type":
    "Observation", "parent_id": ...}} — user_id is inferred from the
    JWT the same way it already is for submit_observation's own POST
    /observations call, not passed explicitly.

    Raises RuntimeError with a real, specific message on failure — same
    convention as submit_observation, including the same expired-token
    detection (tokens last 24h and this is a very common real failure
    mode for exactly this kind of on-demand, less-frequently-used
    action, where a token generated for an earlier submission may well
    have expired by the time someone comes back to post a follow-up
    comment).
    """
    if not token or not token.strip():
        raise RuntimeError("No iNaturalist API token configured in Settings.")
    if not obs_id:
        raise RuntimeError("No iNaturalist observation to comment on — submit this recording to iNaturalist first.")
    if not body or not body.strip():
        raise RuntimeError("Comment body is empty.")
    token = token.strip()

    payload = {
        "comment": {
            "body": with_chirp_link(body.strip()),
            "parent_type": "Observation",
            "parent_id": int(obs_id) if str(obs_id).isdigit() else obs_id,
        }
    }

    with httpx.Client(timeout=20) as client:
        r = client.post(
            f"{INAT_API_BASE}/comments",
            json=payload,
            headers=_headers(token),
        )
        if r.status_code not in (200, 201):
            resp_body = r.text
            logger.error("iNat comment post failed %d for obs #%s: %s", r.status_code, obs_id, resp_body[:500])
            if r.status_code in (401, 422) and (
                "expired" in resp_body.lower() or "invalid" in resp_body.lower() or
                "jwt" in resp_body.lower() or "token" in resp_body.lower()
            ):
                raise RuntimeError(
                    "Your iNaturalist API token has expired (tokens are valid for 24 hours). "
                    "Please go to Settings → API Keys, click the iNaturalist token field, "
                    "and paste a fresh token from https://www.inaturalist.org/users/api_token"
                )
            raise RuntimeError(f"iNaturalist comment post failed ({r.status_code}): {resp_body[:400]}")
        comment = r.json()

    logger.info("Posted iNaturalist comment on observation #%s (comment id %s)", obs_id, comment.get("id"))
    return {"comment_id": comment.get("id"), "obs_id": obs_id}


def post_comment_background(token: str, obs_id, body: str) -> None:
    """
    Fire-and-forget wrapper around post_comment for use as a FastAPI
    BackgroundTask — same reasoning as attach_sound_background/
    attach_photo_background just above: a background task's own
    exception doesn't become a visible error for the person who already
    got a successful HTTP response for the main submission, so this
    catches and logs rather than letting post_comment's real
    RuntimeError propagate into an unhandled background-task exception.
    post_comment itself is left raising, unwrapped, for the separate
    interactive "post as comment" endpoint, where a real error SHOULD
    become a real HTTP error the person actually sees.
    """
    try:
        post_comment(token, obs_id, body)
    except Exception as e:
        logger.warning("iNat bg: comment post failed for obs #%s: %s", obs_id, e)
