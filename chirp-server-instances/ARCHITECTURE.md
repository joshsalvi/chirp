# Multi-Instance-in-One-Container — Architecture

A separate container from the main `chirp-server` (own port, own image,
built and tested in isolation) that lets ONE running process serve
MULTIPLE locations, each with its own real, completely independent
SQLite database — but a single login, one URL, and the ability to
switch between locations you've been invited to.

**Status: early build, real but incomplete.** This document describes
the target design and what's actually built so far. Not yet merged
into the main `chirp-server` — per explicit instruction, changes here
stay isolated on their own port until this is proven, then get merged
back.

## The core idea: don't touch chirp-server's own code at all

Every single one of chirp-server's 16 database models, and every one
of its ~168 endpoints' own business logic, stays **completely
unmodified** — copied byte-for-byte from the real chirp-server
codebase, not reimplemented. This is the entire lesson from the
original chirp-multi attempt (no longer in this repo — it reimplemented
features from scratch instead of reusing chirp-server's own code, and
real deployment surfaced repeated gaps because of it): reimplementing
features from scratch is where real gaps come from, not the
tenant-isolation logic itself.

What makes this possible: virtually every endpoint in chirp-server
gets its database session the same way —
`db: Session = Depends(get_db)`. If `get_db()` itself is made to
resolve a *different* database engine depending on who's asking, every
existing endpoint automatically becomes instance-aware with **zero
changes to its own code**. That's the one load-bearing trick this
whole design rests on.

## Two separate databases, not one

**Per-instance databases** — one real, complete SQLite file per
location, using the exact same schema chirp-server already has today
(recordings, detections, bird_profiles, app_settings, users, everything
— unchanged). A location's own data — species detected, recordings,
journal entries, settings — lives here and only here, genuinely
isolated by being a separate file, not by a `tenant_id` column
something could someday forget to filter on.

**One registry database** (`instances.db`) — small, new, lives outside
any instance's own database:
- `instances`: id, name, location_name, db_path, invite_code, created_at
- `global_users`: id, username, hashed_pw, email, created_at — the
  **real identity** a person logs in with. One login, not one per
  instance.
- `memberships`: user_id, instance_id, role, joined_at — the join
  table. A user can belong to more than one instance; an instance can
  have more than one user. This is what "an instance can have multiple
  users" and "a user can switch between instances" both actually mean
  underneath.

Chirp-server's own existing `User` table, inside each instance's own
database, is **left completely alone** — every existing query against
it keeps working unmodified. When someone joins an instance, a
lightweight, real local `User` row gets created in that instance's own
database too (synced from the global identity), so all of chirp-server's
existing per-instance code that queries its own `User` table — current
user lookups, ownership checks, notification preferences — never needs
to know any of this exists. The registry is the source of truth for
"who is this person and which locations can they reach"; each
instance's own local `User` row is what that instance's own unmodified
code actually uses day to day.

## How a request actually resolves to the right database

1. Login happens against the registry (`global_users`), not any
   instance's own database — there's no instance to pick a database
   from yet at that point.
2. The JWT issued on login carries the user's id, plus (once they've
   picked one) their **currently active instance id** — a real claim
   on the token, not just client-side state, so every subsequent
   request can resolve the right database without an extra database
   round-trip to look it up.
3. `get_db()` decodes the token, reads the active instance id, looks up
   (or opens, if not already cached) that instance's own SQLAlchemy
   engine, and yields a session from it — exactly like today's
   single-database `get_db()`, just resolved per-request instead of
   once at import time.
4. Every existing chirp-server endpoint, completely unaware any of this
   exists, gets a session pointed at the correct instance's own real
   database.

## Switching instances

A real, explicit action — not automatic. `POST /api/v1/instances/switch`
with a target instance id (must be one the user actually has a
membership for) issues a **new** JWT with that instance as the active
one. The frontend swaps tokens and refetches; there is no
silently-wrong-instance state, since every request's instance comes
from the token it carries, not from anything server-side that could
drift out of sync between requests.

## Creating and joining instances

- **Create a new instance**: any authenticated user can create one
  (becoming its first admin) — this is "add a location," the
  self-service path the actual request described ("users elsewhere
  able to create accounts and add locations"). Provisions a fresh
  SQLite file, runs chirp-server's own real `init_db()` against it
  (the exact same function that already runs for a normal single-instance
  chirp-server on first boot — not reimplemented), generates a real
  invite code.
- **Join an existing instance**: `POST /api/v1/instances/join` with an
  invite code an admin shared. Creates the membership, creates the
  synced local `User` row in that instance's own database, defaults to
  `viewer` role (an instance's own admin can promote them from inside
  that instance's own real Settings/user-management UI — unmodified
  existing functionality).

## Background jobs — real progress, one piece genuinely deferred

Confirmed by checking: four real background loops (not three, as
originally scoped here — auto-backup was missed on the first pass)
construct their own database session directly, outside of any HTTP
request — `get_db()`'s per-request resolution can't help them, since
there's no "current user" for a timer-driven job to resolve an instance
from. `iter_instance_sessions()` (instance_registry.py) is the real,
shared, tested fix: yields `(instance, session)` for every registered
instance, so an existing loop's own logic can run unchanged, just once
per instance instead of once globally.

**Done, and the one that actually mattered most**: auto-backup. This
one is on by default (`auto_backup_enabled` defaults to `True`, unlike
the three below), so before this fix, no real instance's data was ever
being automatically backed up at all — a real reliability gap, not a
theoretical one. Now iterates every instance, using that instance's own
backup config, own real database file, and its own separate backup
output directory. Verified with a real test across three genuinely
different config states (backup on, off, and unset-defaults-to-on) —
confirmed it correctly identifies which instances need a backup this
cycle and which to skip.

**Deliberately deferred**: Haikubox sync, Bird Buddy sync, and
iNaturalist token auto-refresh still operate on the single legacy
database. Checked the actual refactor scope before deciding this:
unlike auto-backup (one clean entry point, `run_scheduled_backup`),
each of these services calls `SessionLocal()` directly from five or
more separate internal methods — genuinely threading a per-instance
session through all of them safely is a real, deeper piece of work,
not a quick wrap. Lower urgency than auto-backup was: all three are
genuinely opt-in (need explicit credentials configured), so on the
legacy database they idle harmlessly rather than silently skip
something a person is actually relying on. Real, scoped follow-up —
not silently dropped, not rushed into an undertested state either.

## One device to multiple instances

Already real and working — chirp-device's own multi-target uploader
(see `docs/MULTI_SERVER_DEVICE.md`) already supports sending one
device's recordings to more than one server. Each per-instance database
here is a real, ordinary chirp-server database from that uploader's own
point of view; nothing new needed on the device side.

## Deliberately not decided yet: SQLite-per-instance vs. a shared MariaDB

Went with SQLite-file-per-instance for the reasons above — real
isolation by being a separate file, zero query changes needed anywhere
in chirp-server's own code, and it's the exact same storage engine and
tuning (WAL mode, busy_timeout) chirp-server already uses successfully
today. A shared MariaDB server (with the same design otherwise — a
database or schema per instance) is a real, viable alternative if this
needs to scale to a genuinely large number of instances someday, but
would add a whole second infrastructure dependency this project hasn't
needed before, for a scale this hasn't been shown to need yet. Worth
revisiting with real evidence (how many instances, how much concurrent
load) rather than switching pre-emptively.

## Bundled containers beyond the main app

The multi-tenant database model above is the core of what makes this
fork different from chirp-server — but the deployment also bundles a
few supporting containers for remote access and HTTPS, none of which
touch the tenant-isolation logic itself:

- **`headscale`** — a self-hosted, open-source Tailscale control plane.
  Not a chirp-specific idea — chirp-device and chirp-server can both be
  configured to join the same tailnet this hosts, giving every device
  a stable identity reachable from anywhere, not just the local network.
  Auto-bootstraps its own long-lived Tailscale auth key AND (added
  alongside Global Admin's Network tab) a Headscale API key on first
  boot, both written to a shared Docker volume this app reads at
  startup — zero manual key-copying for the common case. See
  `headscale/entrypoint.sh` for the exact bootstrap logic and
  [Remote Access](../techdocs/docs/remote-access.md) for the full
  setup walkthrough.
- **`caddy`** — terminates real TLS for the Headscale subdomain
  specifically, via the DNS-01 certificate challenge (a Cloudflare DNS
  TXT record proves domain ownership, needing no inbound port 80 at
  all — see `headscale/config.yaml`'s own comments). This exists
  because Cloudflare's own proxying, Tunnel or regular DNS proxying
  alike, cannot carry Headscale's protocol at all — confirmed directly
  against Headscale's own documentation, not a guess.
- **`cloudflare-ddns`** — keeps the Headscale subdomain's own DNS
  record pointed at this host's current public IP, checked every 5
  minutes, reusing the same Cloudflare API token `caddy` already has
  (`PROXIED=false` is hardcoded here, not left as a default — a
  proxied record would break Headscale's protocol the same way
  `caddy`'s own DNS-01 note above explains). This app's own main
  public domain is reached differently — pointed directly at this
  host's IP too, but through Cloudflare's regular proxying (the
  "orange cloud" DNS toggle) rather than DDNS + a dedicated reverse
  proxy, since the main app's own HTTP traffic (unlike Headscale's)
  has no problem being proxied by Cloudflare.

A fourth piece, running inside the `headscale` container itself rather
than as a separate service: a small stdlib-only Python HTTP wrapper
(`headscale/api-wrapper.py`) around headscale's own CLI, listening on
`127.0.0.1:50444` (published loopback-only, same pattern as `caddy`
above). This exists because headscale's real gRPC admin API — the
documented way to query it programmatically — only speaks raw gRPC
(HTTP/2 + protobuf framing), not REST/JSON; confirmed directly, the
hard way, with a real "illegal request line" error from trying plain
HTTP against it. Standing up a genuine gRPC client from Python needs
generated protobuf stubs matching headscale's exact .proto schema — a
real new dependency for one read-only endpoint (Global Admin's Network
tab, "who's connected") the officially-supported CLI already answers
correctly. This wrapper shells out to `headscale nodes list --output
json` and serves the result over plain HTTP instead. See
`app/services/headscale_admin_client.py` for the client side.

None of these four are required for the core multi-tenant database
model above to work — they're specifically for reaching a device or
another server that isn't on this host's own local network, or for
Global Admin's own convenience panel. A single-LAN deployment with no
remote devices can disable all four without losing any tenant-isolation
functionality.
