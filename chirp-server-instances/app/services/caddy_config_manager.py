"""
Pushes a live Basic Auth config change to Caddy's own admin API, for
Global Admin's "edit Headscale settings directly in Chirp" feature —
specifically, password-protecting Headscale's public helper pages
(/apple, /windows, /linux) without needing manual Caddyfile editing or
a container restart.

How this actually takes effect, and survives a restart: Caddy's admin
API (see caddyserver.com/docs/api) accepts a POST to /load with
Content-Type: text/caddyfile, applies it immediately with zero
downtime, and — because caddy/Dockerfile's own CMD now includes
--resume — auto-saves the applied config to the persistent /config
volume, so a full container restart resumes THIS config instead of
falling back to the static Caddyfile on disk. Confirmed directly: a
real Caddy 2.9.1 binary was used to `caddy validate` the exact
Caddyfile shape this renders, and the admin API's Caddyfile-text
acceptance (not just its native JSON) is Caddy's own documented
behavior, not assumed.

Why chirp-server-instances renders the WHOLE Caddyfile on every change,
not just a scoped patch to the basic_auth block specifically: Caddy's
admin API has granular JSON-path PATCH/PUT endpoints, but those operate
on Caddy's native JSON config tree, not Caddyfile syntax — reusing this
already-validated Caddyfile template and reloading the whole thing via
/load (which Caddy itself only actually restarts/reconfigures the parts
that changed, with zero downtime either way) avoids maintaining two
parallel representations of the same config.

Reachability: Caddy's admin API is bound to 0.0.0.0:2019 inside the
caddy container (via the CADDY_ADMIN env var — its documented default,
localhost:2019, is unreachable via Docker's port-publishing, the same
lesson already learned for headscale's own grpc_listen_addr and the
node-list wrapper), published to the HOST's loopback only
(127.0.0.1:2019:2019), reachable from chirp-server-instances
(network_mode: host) but never the LAN or internet.
"""
import logging
from typing import Optional

import httpx

logger = logging.getLogger("chirp.caddy_config_manager")

CADDY_ADMIN_BASE = "http://127.0.0.1:2019"

CADDYFILE_TEMPLATE = """\
headscale.ourchirp.com {{
    tls {{
        dns cloudflare {{env.CF_API_TOKEN}}
    }}
{basic_auth_block}
    reverse_proxy headscale:9877
}}
"""

BASIC_AUTH_BLOCK_TEMPLATE = """\
    @helperpages path /apple /apple/* /windows /windows/* /linux /linux/*
    basic_auth @helperpages {{
        {username} {password_hash}
    }}
"""


def render_caddyfile(basic_auth_enabled: bool, username: Optional[str], password_hash: Optional[str]) -> str:
    """
    Pure function, no I/O — deliberately separated from the network
    call below so this can be (and is) unit-tested against a real
    `caddy validate` run without needing Caddy's admin API live.
    """
    block = ""
    if basic_auth_enabled and username and password_hash:
        block = "\n" + BASIC_AUTH_BLOCK_TEMPLATE.format(username=username, password_hash=password_hash)
    return CADDYFILE_TEMPLATE.format(basic_auth_block=block)


def push_live_config(basic_auth_enabled: bool, username: Optional[str], password_hash: Optional[str]) -> dict:
    """
    Returns {"ok": bool, "error": str|None}. Never raises — a Global
    Admin save action calling this should show a clear error message,
    not a 500, if Caddy itself is unreachable (e.g. mid-restart).
    """
    caddyfile_text = render_caddyfile(basic_auth_enabled, username, password_hash)
    try:
        resp = httpx.post(
            f"{CADDY_ADMIN_BASE}/load",
            headers={"Content-Type": "text/caddyfile", "Cache-Control": "must-revalidate"},
            content=caddyfile_text.encode(),
            timeout=10.0,
        )
        if resp.status_code >= 400:
            logger.warning("Caddy admin API rejected the new config: %s", resp.text[:500])
            return {"ok": False, "error": resp.text[:500]}
        return {"ok": True, "error": None}
    except Exception as e:
        logger.warning("Could not reach Caddy's admin API: %s", e)
        return {"ok": False, "error": str(e)}
