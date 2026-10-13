"""
Bird Photo Species Confirmation (services/photo_id.py)
========================================================

When a user uploads a photo to a bird profile, this optionally asks the
Anthropic API (Claude, with vision) "what species is this?" and compares
the answer against the profile's species name as a sanity check — not a
replacement for the BirdNET audio detection, just a second opinion on a
photo someone is attaching to a profile.

Entirely optional: if no `anthropic_api_key` is configured in Settings,
photo upload still works fine — `ai_checked` stays False and the photo is
just saved without a confirmation badge. This is a real API call to a real
model; it is not a bundled/offline classifier, so it requires the user's
own Anthropic API key (same pattern as the eBird/iNaturalist keys already
used elsewhere in Settings) and is subject to that account's usage/billing.
"""

import base64
import json
import logging
import mimetypes
from typing import Optional, Tuple

import httpx

logger = logging.getLogger("chirp.photo_id")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MODEL = "claude-haiku-4-5-20251001"   # fast + cheap is plenty for this sanity-check task
MAX_IMAGE_BYTES = 5 * 1024 * 1024     # Anthropic's vision input limit is more generous than
                                       # this, but keep uploads reasonable regardless


def _log_photo_id_usage(db, data: dict):
    """Same best-effort usage logging as services/ai_providers.py's
    _log_usage — this module makes its own direct Anthropic call rather
    than going through that shared abstraction (see this file's own
    docstring for why), so it needs its own small copy rather than a
    real dependency on that module."""
    if db is None:
        return
    try:
        import uuid
        from ..models import AiUsageLog
        u = (data or {}).get("usage") or {}
        db.add(AiUsageLog(
            id=str(uuid.uuid4()), provider="anthropic", feature="photo_id",
            input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
        ))
        db.commit()
    except Exception as e:
        logger.warning("Photo ID usage logging failed (non-fatal): %s", e)



def _guess_media_type(filename: str, data: bytes) -> str:
    mt, _ = mimetypes.guess_type(filename)
    if mt in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        return mt
    # Fall back to sniffing magic bytes
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"  # reasonable default; Anthropic will reject if truly wrong


def identify_species_from_photo(
    image_bytes: bytes,
    filename: str,
    expected_common_name: str,
    api_key: str,
    db=None,
) -> Tuple[bool, Optional[bool], Optional[str], Optional[str]]:
    """
    Returns (checked, match, ai_guess, note):
      checked  — True if the API call completed (regardless of match result)
      match    — True/False if the AI's answer was parsed and compared, else None
      ai_guess — the species name(s) the AI named, for display
      note     — short free-text explanation from the AI

    Never raises — any failure (network, bad key, malformed response) returns
    (False, None, None, <error message>) so the caller can save the photo
    either way and just skip showing a confirmation badge.
    """
    if not api_key:
        return False, None, None, None
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return False, None, None, "Image too large for AI confirmation (5MB limit)"

    media_type = _guess_media_type(filename, image_bytes)
    b64 = base64.b64encode(image_bytes).decode("ascii")

    prompt = (
        f"This photo was uploaded to a bird profile for \"{expected_common_name}\". "
        "Look at the photo and identify the bird species you see. "
        "Respond with ONLY a JSON object, no other text, in this exact shape: "
        '{"species_seen": "<common name(s) you identify, or \\"no bird visible\\" '
        'if you can\'t see a bird clearly>", '
        '"matches_expected": <true, false, or null if you\'re not confident enough '
        'to judge either way>, '
        '"note": "<one short sentence explaining your answer>"}'
    )

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": MODEL,
                    "max_tokens": 300,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {
                                "type": "base64", "media_type": media_type, "data": b64,
                            }},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                },
            )
    except httpx.RequestError as e:
        logger.warning("Photo ID: request failed: %s", e)
        return False, None, None, f"Could not reach Anthropic API: {e}"

    if resp.status_code == 401:
        return False, None, None, "Anthropic API key was rejected (check Settings → API Keys)"
    if resp.status_code != 200:
        logger.warning("Photo ID: API returned %s: %s", resp.status_code, resp.text[:300])
        return False, None, None, f"AI confirmation failed (HTTP {resp.status_code})"

    try:
        data = resp.json()
        text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        raw_text = "\n".join(text_blocks).strip()
        # Models sometimes wrap JSON in a code fence despite instructions — strip it
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.lower().startswith("json"):
                raw_text = raw_text[4:].strip()
        parsed = json.loads(raw_text)
        ai_guess = parsed.get("species_seen")
        matches = parsed.get("matches_expected")
        note = parsed.get("note")
        match_bool = bool(matches) if isinstance(matches, bool) else None
        _log_photo_id_usage(db, data)
        return True, match_bool, ai_guess, note
    except Exception as e:
        logger.warning("Photo ID: could not parse model response: %s", e)
        _log_photo_id_usage(db, data)
        return True, None, None, "AI responded but the answer couldn't be parsed"
