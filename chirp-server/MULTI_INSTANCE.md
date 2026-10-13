# Multiple Locations / Tenants — One chirp-server Per Location

This document covers running one **complete, independent chirp-server
instance** per location/household/tenant — the same real, mature
application every other single-location deployment uses, not a
separate, simplified reimplementation of it. If you want shared
infrastructure across locations instead, see the note on
`chirp-server-instances` below.

## Why separate containers, not one shared multi-tenant app

An earlier attempt at a genuinely separate multi-tenant application
(`chirp-multi/`) is no longer in this repo — real deployment surfaced
repeated gaps between what it reimplemented and what chirp-server's own,
much more battle-tested code actually does (a concrete example:
chirp-server's regional species feature has a real fallback data source
when eBird's bar-chart endpoint requires a login session it doesn't
have; chirp-multi's port of that feature didn't carry the fallback
over, so it failed in the common case, not just an edge case). Multiple
independent instances of the one real application, as this document
describes, sidesteps that whole class of bug — there's nothing to
reimplement, and each instance gets the full, current feature set
automatically.

**If you specifically want shared infrastructure instead** (one login
system across every location, one container to update, less total
resource overhead than N separate ones) — that's what
`chirp-server-instances` is for: a genuinely different, actively
maintained fork built around a shared FastAPI/React app with per-tenant
databases and a Global Admin panel, rather than N fully separate
containers. It exists precisely because chirp-multi's shared-app
approach failed; this time it worked, by reusing chirp-server's own
mature code as a shared base instead of reimplementing features from
scratch. The two approaches (this document's separate containers, or
that one shared multi-tenant app) are both real, current, and
independently maintained — pick based on whether you want full
isolation per location or shared infrastructure.

What separate containers (this document's approach) trades away, for
now: a single *sign-on* that works across every location (each instance
still has its own separate login — see
"The launcher," below, for the real switcher page that gets you to the
right instance quickly, without merging their user databases), and no
unified cross-location data model. Both are real, deliberately
deferred — see this file's own "Later: unifying instances further"
section at the end.

## Creating a new instance

```bash
cd chirp-server
./scripts/new-instance.sh <name> <port>
```

`<name>`: lowercase letters/numbers/hyphens only — becomes part of the
container name, data directory, and this instance's own env var prefix.
`<port>`: any free port on this host. The three original example
instances use 8765 (the main `docker-compose.yml`'s own default),
8766, and 8767 — pick anything else free, like 8768 onward.

```bash
./scripts/new-instance.sh natick 8768
docker compose -f docker-compose.instance-natick.yml up -d
```

Open `http://<host-ip>:8768` and complete first-run setup — this new
instance has its own empty database, own users, own devices, own
settings, exactly like any other fresh chirp-server install.

## Sharing AI/eBird keys across instances, without re-entering them

Each instance's AI provider keys (Anthropic/OpenAI/Gemini/Ollama) and
eBird keys live in that instance's own database (Settings → AI Provider
/ eBird), same as ever — chirp-server itself has no separate
"multi-instance" concept for this. To avoid manually re-typing the same
key into every new instance's Settings page:

```bash
python3 scripts/copy-instance-settings.py <source-data-dir> <dest-data-dir>
```

Uses the real host paths from each instance's own `docker-compose.yml`
volume mount, e.g.:

```bash
python3 scripts/copy-instance-settings.py \
  /mnt/user/data/media/miscellaneous/chirp-data \
  /mnt/user/data/media/miscellaneous/chirp-data-natick
```

Copies only the specific shared credential fields (never location,
device keys, users, or anything else genuinely per-instance), and never
overwrites a real value already set on the destination unless you pass
`--force`. Restart the destination instance's container afterward if
it's already running.

## HTTPS for each instance

Each generated instance includes its own Cloudflare Tunnel service
(`chirp-server-<name>-cloudflared`) — a real, separate tunnel per
instance, same reasoning as the main `docker-compose.yml`'s own tunnel:
if you ever need to rotate or debug one location's public access, a
dedicated tunnel means zero risk of touching any other location's. See
`docs/CLOUDFLARE_TUNNEL.md` for the actual dashboard setup steps —
same process, just create one more tunnel per new instance, name it to
match, and set that instance's own `CHIRP_<NAME>_CLOUDFLARE_TUNNEL_TOKEN`
in your `.env` file.

## Devices — pairing a Pi to a specific instance

A device pairs to whichever server its own `config.yaml` points at —
see `docs/MULTI_SERVER_DEVICE.md` for the full mechanics, including
sending one device's data to more than one instance at once if that's
ever useful (e.g. testing a new location's server before fully cutting
a device over to it).

## The launcher — one place to see and reach every instance

`chirp-launcher` (part of the main `docker-compose.yml`, port 8760 by
default) is a real, working switcher page — not a shared backend, not a
shared database, no way for it to reach into any instance's actual
data. It's a single static HTML page plus `launcher/instances.json` (a
plain list of `{name, display_name, port, public_url}`), served by a
plain nginx container. It reads that list, builds a link to each instance
(using that instance's own `public_url` if set — e.g. its own
Cloudflare Tunnel subdomain — or constructing one from the launcher's
own hostname + that instance's port otherwise, so it works correctly
whether you're viewing it via localhost, a LAN IP, or a domain), and
does a real, best-effort health check against each instance's own
`/api/v1/health` to show which ones are actually up.

`scripts/new-instance.sh` registers every new instance in
`launcher/instances.json` automatically — nothing to hand-edit for the
common case. Lives inside `launcher/` itself, not as a separate
top-level file, so it can be served by the same single, read-only
directory mount as `launcher/index.html` — mounting it as a second,
separate bind mount nested inside that already-read-only directory
mount is a real, confirmed way to make the container fail to start at
all ("read-only file system" from the OCI runtime, on any machine, not
environment-specific) — a genuine bug this project shipped with and
fixed only after it broke a real deployment. Verified with a real headless-browser test (Playwright, not just
reading the code back): confirmed the link is built correctly, that a
genuinely unreachable instance settles to an "offline" indicator rather
than hanging, and that a genuinely reachable one correctly shows
"online" — both the failure and success paths checked for real, not
assumed.

This is deliberately *not* a single sign-on across instances — clicking
a link takes you to that instance's own real login page, same as
navigating there directly. See below for why that specific piece is
still out of scope.

## Later: unifying instances further

The launcher above covers "one place to see and click into every
location." Two real, separate things still deliberately not built,
worth designing properly when they're actually needed, not before:

- **A single login that works across every instance** — the launcher
  gets you to the right place quickly, but you still authenticate
  separately with each instance, since each one has its own completely
  independent user database. A real shared-auth layer is meaningfully
  more engineering (and its own new security surface) than a page of
  links.
- **Cross-location visibility** — seeing a summary from another
  location without full access to its own recordings, matching the
  original "sharing" idea from early multi-tenant discussions. Real
  design work (what exactly is shared, who grants it, whether it's a
  push from one instance to another or a pull) that's explicitly out of
  scope until every instance's own core experience is solid.
