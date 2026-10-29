"""
Security headers and security events.

SecurityHeaders: an ASGI middleware that adds the standard browser
protections to every response (main.py). HSTS is only sent over HTTPS
(directly, or behind Cloudflare / Caddy saying so).

Security events: failed and blocked sign-ins, sign-up limits and scanner
probes (/.env, /wp-login.php …). Kept in memory only (last EVENTS_MAX, with
the caller's address so an admin can see who is probing); per-day counts go
to listeners (ourchirp.com's traffic.db). Global Admin → Traffic shows them.
"""
import re
import threading
import time
from collections import Counter, deque

_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    # Live Detect needs the microphone and (optionally) location.
    (b"permissions-policy", b"camera=(), payment=(), usb=()"),
    (b"cross-origin-opener-policy", b"same-origin-allow-popups"),
]
_HSTS = (b"strict-transport-security", b"max-age=31536000")


def _is_https(scope) -> bool:
    if scope.get("scheme") == "https":
        return True
    for k, v in scope.get("headers") or []:
        if k == b"x-forwarded-proto" and v.split(b",")[0].strip().lower() == b"https":
            return True
        if k == b"cf-visitor" and b"https" in v:
            return True
    return False


class SecurityHeaders:
    """Adds browser security headers without buffering the response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        extra = _HEADERS + ([_HSTS] if _is_https(scope) else [])

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                have = {k.lower() for k, _ in headers}
                headers += [(k, v) for k, v in extra if k not in have]
                message["headers"] = headers
            await send(message)

        return await self.app(scope, receive, send_with_headers)


# ── Scanner probes ───────────────────────────────────────────────────────────
# Paths nobody but a vulnerability scanner asks a Chirp server for.
PROBE = re.compile(
    r"(^/\.(env|git|svn|hg|aws|ssh|docker|vscode|idea|DS_Store|htaccess|htpasswd)"
    r"|^/(wp-|wordpress|xmlrpc|phpmyadmin|pma|myadmin|cgi-bin|vendor/|actuator|server-status|server-info"
    r"|boaform|HNAP1|owa/|ecp/|autodiscover|solr/|druid/|jenkins|manager/html|console/|\.well-known/acme-challenge/\.\.)"
    r"|\.(php\d?|asp|aspx|jsp|cgi|pl|sql|bak|old|swp|ini|conf|log|tar|tgz|gz|zip|7z|rar)$"
    r"|/(config|credentials|secrets|database|backup|dump)\.(json|ya?ml|xml|txt)$"
    r"|\.\./|%2e%2e)",
    re.I,
)


def is_probe(path: str) -> bool:
    return bool(PROBE.search(path or ""))


# ── Events ───────────────────────────────────────────────────────────────────
EVENTS_MAX = 500
KINDS = {
    "failed_login": "Failed sign-in",
    "login_blocked": "Sign-in blocked (too many failures)",
    "signup_limited": "Sign-up blocked (too many from one address)",
    "bad_invite": "Wrong invite code",
    "probe": "Scanner probe",
    "rate_limited": "Rate limited",
}
_lock = threading.Lock()
_events: deque = deque(maxlen=EVENTS_MAX)
_since = time.time()
_totals: Counter = Counter()
listeners = []        # callables (kind) -> None, e.g. traffic.py's daily counts


def note(kind: str, ip: str = "", detail: str = ""):
    with _lock:
        _events.append((time.time(), kind, (ip or "")[:64], (detail or "")[:120]))
        _totals[kind] += 1
    for f in list(listeners):
        try:
            f(kind)
        except Exception:
            pass


def summary(hours: int = 24, limit: int = 100) -> dict:
    """Recent events, counts by kind and the busiest addresses."""
    cutoff = time.time() - hours * 3600
    with _lock:
        recent = [e for e in _events if e[0] >= cutoff]
        totals = dict(_totals)
    by_kind = Counter(e[1] for e in recent)
    by_ip = Counter(e[2] for e in recent if e[2])
    kinds_by_ip: dict = {}
    for _, kind, ip, _d in recent:
        if ip:
            kinds_by_ip.setdefault(ip, Counter())[kind] += 1
    return {
        "hours": hours,
        "since": _since,
        "kinds": KINDS,
        "counts": dict(by_kind),
        "totals_since_start": totals,
        "top_addresses": [{"ip": ip, "n": n, "kinds": dict(kinds_by_ip[ip])} for ip, n in by_ip.most_common(10)],
        "events": [{"t": t, "kind": k, "ip": ip, "detail": d} for t, k, ip, d in reversed(recent[-limit:])],
    }
