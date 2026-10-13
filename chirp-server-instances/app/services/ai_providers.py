"""
AI provider abstraction for text generation.

Two things live here: feature-to-provider assignment (AppSettings.ai_feature_providers
maps a feature name to a provider, or None to disable it) and a unified
call_chat_completion() that normalizes Anthropic/OpenAI/Gemini/Ollama into one
signature.

Vision (photo ID) stays in services/photo_id.py as its own direct Anthropic call.
Uses raw httpx rather than an SDK — one dependency less to track for what's a
single POST per call.
"""

import logging
from typing import Optional, Tuple

import os
import httpx

logger = logging.getLogger("chirp.ai_providers")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_TEXT_MODEL = "claude-sonnet-5"
# Spectrogram second opinions: low temperature for repeatable verdicts.
VISION_TEMPERATURE = 0.2
OLLAMA_KEEP_ALIVE = "30m"
# Context window for Ollama requests. Ollama's default (2-8k tokens by
# version) is less than an AI Second Opinion needs: a ~3k-token prompt, the
# spectrogram image and a thinking model's hidden reasoning all share it,
# and when reasoning fills it the visible answer never starts.
OLLAMA_NUM_CTX = int(os.environ.get("CHIRP_OLLAMA_NUM_CTX", "16384") or 16384)
# AI Second Opinion asks thinking models (Gemma 4, Qwen 3...) to answer
# directly: hidden reasoning was most of the wait (often 1-3k tokens before
# the first visible word, and a second full request when it used up the
# context). CHIRP_OLLAMA_THINK=1 lets the model think first.
OLLAMA_VISION_THINK = os.environ.get("CHIRP_OLLAMA_THINK", "0").strip().lower() in ("1", "true", "yes", "on")

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_TEXT_MODEL = "gpt-4.1"

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_TEXT_MODEL = "gemini-flash-latest"   # Google's alias for the current model, not a pinned version — this lineup changes often

# Every feature that can be assigned an AI provider. Kept as a single list
# so Settings' UI and this module's validation stay in sync automatically
# rather than needing the same set of strings maintained in two places.
FEATURES = ("photo_id", "call_reanalysis", "daily_summary", "profile_summary")


def _looks_truncated(text: str) -> bool:
    """
    Heuristic for "did this response get cut off mid-thought" — used
    only to decide whether to spend an extra Ollama round-trip
    continuing it, so false positives just cost one harmless extra
    call, not correctness. A genuinely complete response ends with
    real sentence-ending punctuation, or a closing markdown structure;
    one cut off by running out of room stops mid-word or mid-clause,
    with no terminal punctuation at all.
    """
    stripped = text.rstrip()
    if not stripped:
        return True
    return stripped[-1] not in ".!?\"'”’)`"


def _ollama_chat(cfg: dict, messages: list, options: dict, timeout: float,
                 think: Optional[bool] = None) -> tuple:
    """POST /api/chat; returns (response json, think) where think is None
    (model default) or False. think=False asks a thinking model to answer
    directly (other models ignore it). A thinking model that spends the
    whole context on reasoning returns no visible answer: ask again once
    with thinking off, which answers directly."""
    body = {"model": cfg["model"], "stream": False, "messages": messages,
            "options": {"num_ctx": OLLAMA_NUM_CTX, **options}, "keep_alive": OLLAMA_KEEP_ALIVE}
    if think is False:
        body["think"] = False
    resp = httpx.post(f"{cfg['base_url']}/api/chat", json=body, timeout=timeout)
    if think is False and resp.status_code == 400 and "think" in resp.text.lower():
        # An Ollama too old for the think option: ask without it.
        body.pop("think", None)
        think = None
        resp = httpx.post(f"{cfg['base_url']}/api/chat", json=body, timeout=timeout)
    _check_response(resp)
    data = resp.json()
    msg = data.get("message") or {}
    if msg.get("content") or not msg.get("thinking") or think is False:
        return data, think
    logger.info("Ollama %s spent its whole answer on reasoning; asking again with thinking off",
                cfg["model"])
    resp = httpx.post(f"{cfg['base_url']}/api/chat", json={**body, "think": False}, timeout=timeout)
    _check_response(resp)
    return resp.json(), False


def warm_ollama(cfg: dict, timeout: float = 5.0) -> str:
    """Load the Ollama model into memory ahead of a request (an empty
    /api/generate with keep_alive), so an AI Second Opinion doesn't also wait
    for a multi-GB vision model to load. Returns "loaded" (already in
    memory), "loading" (load started) or "unavailable"."""
    try:
        ps = httpx.get(f"{cfg['base_url']}/api/ps", timeout=timeout)
        if ps.status_code == 200:
            names = {m.get("name") or m.get("model") for m in (ps.json().get("models") or [])}
            want = cfg["model"]
            if want in names or (":" not in want and f"{want}:latest" in names):
                return "loaded"
    except Exception as e:
        logger.debug("Ollama /api/ps failed: %s", e)
        return "unavailable"

    def _load():
        try:
            httpx.post(f"{cfg['base_url']}/api/generate",
                       json={"model": cfg["model"], "keep_alive": OLLAMA_KEEP_ALIVE}, timeout=300)
        except Exception as e:
            logger.debug("Ollama warm-up failed: %s", e)
    import threading
    threading.Thread(target=_load, daemon=True, name="ollama-warm").start()
    return "loading"


def _check_response(resp):
    """
    Raises with the provider's actual error message instead of httpx's
    generic "400 Bad Request" text. Anthropic/OpenAI/Gemini all nest the
    real reason under {"error": {"message": ...}}; falls back to the
    default httpx exception if the body isn't JSON or doesn't match.
    """
    if resp.status_code < 400:
        return
    detail = None
    try:
        body = resp.json()
        detail = (body.get("error") or {}).get("message")
    except Exception:
        pass
    if detail:
        raise RuntimeError(detail)
    resp.raise_for_status()


def _extract_usage(provider: str, data: dict):
    """Pulls (input_tokens, output_tokens) out of each provider's response
    shape — every one of them returns real usage figures, just under
    different key names. Returns (None, None) if the shape doesn't match
    what's expected (a future API change, etc.) rather than raising —
    usage tracking is a nice-to-have, never worth failing an otherwise-
    successful generation over."""
    try:
        if provider == "anthropic":
            u = data.get("usage") or {}
            return u.get("input_tokens"), u.get("output_tokens")
        elif provider == "openai":
            u = data.get("usage") or {}
            return u.get("prompt_tokens"), u.get("completion_tokens")
        elif provider == "gemini":
            u = data.get("usageMetadata") or {}
            return u.get("promptTokenCount"), u.get("candidatesTokenCount")
        elif provider == "ollama":
            # Ollama reports these directly on the response itself, not
            # nested under a "usage" key like the hosted providers.
            return data.get("prompt_eval_count"), data.get("eval_count")
    except Exception:
        pass
    return None, None


def _log_usage(db, provider: str, feature: str, input_tokens, output_tokens):
    """Best-effort usage log — swallows failures so bookkeeping never
    breaks an otherwise-successful generation. db/feature are optional
    so callers that don't care about tracking don't need to change."""
    if db is None or feature is None:
        return
    try:
        import uuid
        from ..models import AiUsageLog
        db.add(AiUsageLog(
            id=str(uuid.uuid4()), provider=provider, feature=feature,
            input_tokens=input_tokens, output_tokens=output_tokens,
        ))
        db.commit()
    except Exception as e:
        logger.warning("AI usage logging failed (non-fatal): %s", e)



def get_feature_config(feature_key: str, db) -> Optional[Tuple[str, str]]:
    """
    Returns (provider, credential) for the given feature, or None if
    disabled or unconfigured. None means "hide this feature's UI" — not
    a call to attempt and handle a failure.

    For hosted providers, credential is a plain API key. For "ollama"
    (self-hosted, no API key) it's a JSON string of {"base_url", "model"}
    packed into the same slot every caller already treats as "api_key",
    so adding this provider didn't require touching existing callers.
    """
    from ..models import AppSettings
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if s is None:
        return None
    providers_map = s.ai_feature_providers or {}
    provider = providers_map.get(feature_key)
    if not provider:
        return None

    if provider == "ollama":
        base_url = getattr(s, "ollama_base_url", None)
        model = getattr(s, "ollama_model", None)
        if not base_url or not model:
            return None
        import json as _json
        return provider, _json.dumps({"base_url": base_url.rstrip("/"), "model": model})

    key_map = {"anthropic": s.anthropic_api_key, "openai": s.openai_api_key, "gemini": getattr(s, "gemini_api_key", None)}
    api_key = key_map.get(provider)
    if not api_key:
        return None
    return provider, api_key


def test_provider_key(provider: str, api_key: str) -> dict:
    """
    Validates a key with the cheapest real call each provider offers.
    Raises on failure (bad key, network error) — caller decides how to
    present that.
    """
    if not api_key or not api_key.strip():
        raise ValueError("No API key provided")
    api_key = api_key.strip()

    if provider == "anthropic":
        resp = httpx.post(
            ANTHROPIC_API_URL,
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"},
            json={"model": ANTHROPIC_TEXT_MODEL, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
            timeout=15.0,
        )
        _check_response(resp)
        return {"ok": True, "provider": "anthropic", "model": ANTHROPIC_TEXT_MODEL}

    elif provider == "openai":
        resp = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15.0,
        )
        _check_response(resp)
        return {"ok": True, "provider": "openai"}

    elif provider == "gemini":
        resp = httpx.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            timeout=15.0,
        )
        _check_response(resp)
        return {"ok": True, "provider": "gemini"}

    elif provider == "ollama":
        # api_key here is really the JSON-encoded {base_url, model} —
        # see get_feature_config's own docstring for why. Confirms the
        # server is reachable AND the specific model is actually pulled
        # locally (a real, common failure mode with Ollama — the server
        # can be up with a completely different model list than expected).
        import json as _json
        cfg = _json.loads(api_key)
        resp = httpx.get(f"{cfg['base_url']}/api/tags", timeout=10.0)
        _check_response(resp)
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        model_available = any(cfg["model"] == m or m.startswith(cfg["model"] + ":") for m in models)
        if not model_available:
            raise RuntimeError(f"Ollama server reachable, but model '{cfg['model']}' isn't pulled there. Available: {', '.join(models) or '(none)'}")
        return {"ok": True, "provider": "ollama", "model": cfg["model"]}

    else:
        raise ValueError(f"Unknown AI provider: {provider!r}")


def call_vision_completion(
    provider: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
    media_type: str,
    max_tokens: int = 500,
    timeout: Optional[float] = None,
    db=None,
    feature: str = None,
) -> str:
    """
    Same idea as call_chat_completion, but for a single-image + text
    request — the shape services/photo_id.py already uses for bird photo
    confirmation (Anthropic-only there), generalized across all three
    providers for services/call_reanalysis.py's spectrogram-image
    second-opinion feature. None of these providers have a native
    bioacoustic audio classifier; this works by showing the model the
    spectrogram image and asking whether it's consistent with the current
    species guess, using general vision + ornithology knowledge — a
    sanity check, not a replacement for the actual BirdNET detection.

    timeout resolution follows the same provider-appropriate logic as
    call_chat_completion — see that function's docstring for why a flat
    30s default previously broke every Ollama request past that point
    for slower local models, regardless of how close to finishing they
    actually were.

    Image requests get longer: a spectrogram plus a long answer (AI Second
    Opinion asks for up to 1000 tokens) regularly took over 30 s on hosted
    models and over 3 min on a local model reading a large image.
    """
    if timeout is None:
        timeout = 420.0 if provider == "ollama" else 120.0

    import base64
    b64 = base64.b64encode(image_bytes).decode("ascii")

    if provider == "anthropic":
        resp = httpx.post(
            ANTHROPIC_API_URL,
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"},
            json={
                "model": ANTHROPIC_TEXT_MODEL,
                "max_tokens": max_tokens,
                "temperature": VISION_TEMPERATURE,
                # The instructions are the same on every request: cached, the
                # model starts on the image sooner and they cost a tenth.
                "system": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                        {"type": "text", "text": user_prompt},
                    ],
                }],
            },
            timeout=timeout,
        )
        _check_response(resp)
        data = resp.json()
        blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        if not text:
            raise RuntimeError("Anthropic response contained no text content")
        _log_usage(db, provider, feature, *_extract_usage(provider, data))
        return text.strip()

    elif provider == "openai":
        resp = httpx.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": OPENAI_TEXT_MODEL,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                        {"type": "text", "text": user_prompt},
                    ]},
                ],
            },
            timeout=timeout,
        )
        _check_response(resp)
        data = resp.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not text:
            raise RuntimeError("OpenAI response contained no text content")
        _log_usage(db, provider, feature, *_extract_usage(provider, data))
        return text.strip()

    elif provider == "gemini":
        resp = httpx.post(
            f"{GEMINI_API_BASE}/{GEMINI_TEXT_MODEL}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"role": "user", "parts": [
                    {"inline_data": {"mime_type": media_type, "data": b64}},
                    {"text": user_prompt},
                ]}],
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {"maxOutputTokens": max_tokens},
            },
            timeout=timeout,
        )
        _check_response(resp)
        data = resp.json()
        candidates = data.get("candidates") or []
        parts = (candidates[0].get("content", {}).get("parts", []) if candidates else [])
        text = "".join(p.get("text", "") for p in parts)
        if not text:
            raise RuntimeError("Gemini response contained no text content")
        _log_usage(db, provider, feature, *_extract_usage(provider, data))
        return text.strip()

    elif provider == "ollama":
        # api_key is really the JSON-encoded {base_url, model} — see
        # get_feature_config's docstring. Requires whatever model the
        # user configured to actually be vision-capable locally (llava,
        # llama3.2-vision, etc.) — nothing here can check that in
        # advance, it'll just fail with an unhelpful model-specific error
        # if it isn't, the same way it would running this by hand.
        import json as _json
        cfg = _json.loads(api_key)
        # Thinking-capable local models (e.g. Gemma 4) spend part of the
        # budget on hidden reasoning before the visible answer; any fixed
        # num_predict eventually truncates (a 296 s, 4-species recording
        # did, even at 3072), so generation is unbounded (-1) and limited
        # only by num_ctx. _ollama_chat retries with thinking off when the
        # reasoning used it all.
        data, think = _ollama_chat(
            cfg,
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user_prompt, "images": [b64]}],
            {"num_predict": -1, "temperature": VISION_TEMPERATURE},
            timeout, think=None if OLLAMA_VISION_THINK else False,
        )
        msg = data.get("message") or {}
        text = msg.get("content", "")
        if not text:
            if msg.get("thinking"):
                raise RuntimeError(
                    f"Ollama ({cfg['model']}) spent its whole answer on hidden reasoning, "
                    "even with thinking turned off. Choose a non-thinking model in "
                    "Settings → AI Features, or raise CHIRP_OLLAMA_NUM_CTX "
                    f"(now {OLLAMA_NUM_CTX})"
                )
            raise RuntimeError("Ollama response contained no text content")
        _log_usage(db, provider, feature, *_extract_usage(provider, data))

        # num_predict: -1 above removes the artificial per-call cap, but
        # generation is still bounded by the model's own context window
        # (num_ctx) — on a long-enough recording (confirmed directly: a
        # 296s, 4-species recording still cut off mid-sentence even
        # after the cap was already removed), that's the real remaining
        # limit, and there's no safe generic num_ctx to just set higher
        # (too small helps nothing; too large can exceed what the
        # model/GPU actually supports and fail outright). Reported
        # directly, with a suggested fix that's implemented here: if the
        # response still looks cut off, continue the SAME conversation
        # (full message history + the partial answer so far) rather than
        # starting over, and concatenate — up to 2 extra rounds, since
        # an actually-complete response should never need more than
        # that, and this must terminate even if a model somehow never
        # produces a clean-looking ending.
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt, "images": [b64]},
        ]
        full_text = text
        for _ in range(2):
            if not _looks_truncated(full_text):
                break
            # The assistant turn carries everything written so far (it used
            # to carry only the latest chunk, so a second continuation lost
            # the first part of the answer from the model's view).
            messages = messages[:2] + [
                {"role": "assistant", "content": full_text},
                {"role": "user", "content": "Continue your answer exactly where you left off. Do not repeat anything you already said, and do not restart or summarize — just keep writing from the exact point you stopped."},
            ]
            cont_body = {"model": cfg["model"], "stream": False, "messages": messages,
                         "options": {"num_ctx": OLLAMA_NUM_CTX, "num_predict": -1,
                                     "temperature": VISION_TEMPERATURE},
                         "keep_alive": OLLAMA_KEEP_ALIVE}
            if think is False:
                cont_body["think"] = False
            cont_resp = httpx.post(f"{cfg['base_url']}/api/chat", json=cont_body, timeout=timeout)
            _check_response(cont_resp)
            cont_data = cont_resp.json()
            cont_msg = cont_data.get("message") or {}
            text = cont_msg.get("content", "")
            if not text:
                break
            _log_usage(db, provider, feature, *_extract_usage(provider, cont_data))
            full_text += text
        return full_text.strip()

    else:
        raise ValueError(f"Unknown AI provider: {provider!r}")


def call_chat_completion(
    provider: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1200,
    timeout: Optional[float] = None,
    db=None,
    feature: str = None,
) -> str:
    """
    Single text-generation call, provider-agnostic. Raises on any failure
    (network, auth, malformed response) — callers are expected to catch
    and store the error rather than let it propagate to a user-facing 500,
    since every consumer of this (daily summary, profile summary) is an
    optional, best-effort enhancement, not a core feature.

    timeout=None (the default) resolves to a provider-appropriate value
    rather than one flat number for everyone: a hosted API (Anthropic/
    OpenAI/Gemini) that hasn't responded in 30s is very likely actually
    broken, so a short timeout surfaces that quickly. Self-hosted Ollama
    is a different situation entirely — the exact same request that's
    "stuck" for a cloud API is completely normal there, especially
    running an 8B+ model on CPU-only hardware with a several-hundred-
    token system prompt: real testing showed >30s just to finish prompt
    processing alone, before any output generation had even started. A
    flat 30s default previously applied to every provider including
    Ollama, which meant every Ollama request past that point was killed
    client-side mid-generation — Ollama's own log shows this exactly as
    a request ending in "500 ... 30.0xxx s", a suspiciously precise
    cutoff rather than organic completion time, since something (this
    function) was disconnecting the client at almost exactly 30 seconds
    every time regardless of how close the model actually was to
    finishing. This is why a smaller/faster local model (e.g.
    llama3.2:3b) could appear to "work great" while a larger one on the
    same hardware (e.g. llama3.1:8b) never completed a single request —
    not a model or GPU problem, a client timeout problem.

    Note on web search: this function deliberately does NOT expose any
    provider's built-in web-search tool (Anthropic's server-executed
    web_search, or equivalents) — see services/web_search.py instead,
    which runs a search directly from Chirp's own server (no AI vendor
    involved in the search itself) and feeds results into the prompt as
    plain grounded text. That keeps "did we search the web" independent
    of which AI provider is assigned to a feature, and independent of
    any vendor's own infrastructure.
    """
    if timeout is None:
        timeout = 180.0 if provider == "ollama" else 30.0

    if provider == "anthropic":
        resp = httpx.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_TEXT_MODEL,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=timeout,
        )
        _check_response(resp)
        data = resp.json()
        blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        if not text:
            raise RuntimeError("Anthropic response contained no text content")
        _log_usage(db, provider, feature, *_extract_usage(provider, data))
        return text.strip()

    elif provider == "openai":
        resp = httpx.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_TEXT_MODEL,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=timeout,
        )
        _check_response(resp)
        data = resp.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not text:
            raise RuntimeError("OpenAI response contained no text content")
        _log_usage(db, provider, feature, *_extract_usage(provider, data))
        return text.strip()

    elif provider == "gemini":
        resp = httpx.post(
            f"{GEMINI_API_BASE}/{GEMINI_TEXT_MODEL}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {"maxOutputTokens": max_tokens},
            },
            timeout=timeout,
        )
        _check_response(resp)
        data = resp.json()
        candidates = data.get("candidates") or []
        parts = (candidates[0].get("content", {}).get("parts", []) if candidates else [])
        text = "".join(p.get("text", "") for p in parts)
        if not text:
            raise RuntimeError("Gemini response contained no text content")
        _log_usage(db, provider, feature, *_extract_usage(provider, data))
        return text.strip()

    elif provider == "ollama":
        # api_key is really the JSON-encoded {base_url, model} — see
        # get_feature_config's docstring.
        import json as _json
        cfg = _json.loads(api_key)
        # Unbounded generation (see call_vision_completion's Ollama branch);
        # retried with thinking off if reasoning uses the whole context.
        data, _think = _ollama_chat(
            cfg,
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user_prompt}],
            {"num_predict": -1},
            timeout,
        )
        msg = data.get("message") or {}
        text = msg.get("content", "")
        if not text:
            if msg.get("thinking"):
                raise RuntimeError(
                    f"Ollama ({cfg['model']}) spent its whole answer on hidden reasoning, "
                    "even with thinking turned off. Choose a non-thinking model in "
                    "Settings → AI Features, or raise CHIRP_OLLAMA_NUM_CTX "
                    f"(now {OLLAMA_NUM_CTX})"
                )
            raise RuntimeError("Ollama response contained no text content")
        _log_usage(db, provider, feature, *_extract_usage(provider, data))
        return text.strip()

    else:
        raise ValueError(f"Unknown AI provider: {provider!r}")
