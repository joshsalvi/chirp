# Managing a Chirp Device That Isn't on the Server's LAN

If every `chirp-device` (Raspberry Pi) you run is on the same local network
as `chirp-server`, you don't need anything on this page — normal device
pairing already works over the LAN. This is specifically for the case where
a device is somewhere else entirely (e.g. server in one location; a Pi at
a relative's house across the country).

> **Full setup, troubleshooting, and the issues hit getting this
> working live in production** are in the in-app Tech Docs page (Settings
> → Tech Docs, admin-only) or `techdocs/docs/remote-access.md` — this page
> is the shorter "why does this exist and where do the pieces live"
> overview.

## Why this needs more than "just use the WAN IP"

A device sitting behind a typical home router has a private LAN IP
(`192.168.x.x`) that's invisible from the outside — the router's public
(WAN) IP is shared across everything on that network and doesn't route
traffic to any specific device without port forwarding configured on that
*router*. Two problems with relying on that:

1. It requires the device owner to log into their own router and configure
   port forwarding — technical work you can't do for them remotely,
   and plenty of routers (especially ISP-provided ones) make this
   confusing or restrict it outright.
2. Many residential ISPs use **CGNAT** (carrier-grade NAT) — the router
   itself doesn't even have a real public IP to forward a port on in the
   first place, at which point port forwarding isn't possible *at all*,
   regardless of router configuration.

## The approach: a self-hosted private mesh (Headscale)

Both `chirp-server-instances` (the multi-tenant fork) and single-tenant
`chirp-server` can run a self-hosted [Headscale](https://headscale.net/)
— an open-source server speaking the same protocol as Tailscale's own
commercial service — though the two projects' own setups differ
genuinely, not just in name:

- **chirp-server-instances** bundles Headscale directly into its own
  `docker-compose.yml` — auto-bootstrapped (a user and auth key are
  generated with zero manual steps), paired with `caddy` (real TLS)
  and `cloudflare-ddns` (keeps the domain current) automatically.
- **chirp-server** has this as a separate, opt-in
  `docker-compose.headscale.yml` — not auto-bootstrapped (a couple of
  one-time `docker exec` commands are needed after first start, per
  that file's own comments), and doesn't bundle TLS or DNS automation
  the way chirp-server-instances does; getting a real domain/certificate
  in front of it is left to the operator. It does, however, include its
  own self-hosted DERP relay (chirp-server-instances' bundled setup
  doesn't — that one uses Tailscale's own public DERP servers as the
  fallback instead), so the whole mesh — coordination *and* the
  NAT-traversal relay fallback — can be kept genuinely self-hosted
  end to end on chirp-server, if that matters to you.

Every device (and the server itself) runs the standard Tailscale
client either way, pointed at whichever self-hosted instance you're
using instead of Tailscale's cloud. chirp-server's own Settings →
Server Network can also point at any Headscale instance already
running elsewhere — including a chirp-server-instances deployment's
own bundled one, on the same tailnet — as a third option, if you'd
rather not stand up chirp-server's own standalone Headscale at all.

**What this gets you, confirmed working, not just planned:**

- Device-to-server-to-your-laptop reachability from anywhere, using
  Tailscale's own mature NAT traversal and DERP relay fallback — reused
  from Tailscale's own public DERP map rather than self-hosting one, for
  simplicity.
- Nothing routes through Tailscale's own commercial coordination service —
  the coordination server (Headscale) is entirely your own deployment.
  DERP relay (the NAT-traversal fallback path) is the one piece still
  borrowed from Tailscale's own public infrastructure by default.
- Once joined, the server can reach any device by a stable private mesh
  IP (`100.64.x.x`), regardless of what network that device is physically
  on — what lets Settings → Devices' SSH/diagnostics features work on a
  device that isn't on the local LAN at all.

**One thing worth correcting from an earlier version of this document:**
individual *devices* need no inbound port forwarding at all —
they only ever dial *out*, same as any normal outbound web request. But
the **coordination server itself** (Headscale) does need to be reachable
from the internet for that outbound dial to land somewhere — this
requires exactly one inbound path into wherever Headscale runs. In
`chirp-server-instances`' bundled setup, this is a single router port
forward (`443` → the host's Caddy container), not something devices ever
need to configure themselves.

## Where the pieces live

**chirp-server-instances** — everything described here already exists
in its own `docker-compose.yml`, not a separate compose file:

| Piece | What it does |
|---|---|
| `headscale` service | The coordination server — auto-generates its own reusable key on first boot |
| `caddy` service | Terminates TLS for the Headscale domain, reverse-proxies to it (Cloudflare cannot sit in front of Headscale at all — see the Tech Docs page for why) |
| `cloudflare-ddns` service | Keeps the domain's DNS record current if your home IP changes |

**chirp-server** — a separate, opt-in compose file
(`docker-compose.headscale.yml`), brought up alongside the main one:
`docker compose -f docker-compose.yml -f docker-compose.headscale.yml up -d`

| Piece | What it does |
|---|---|
| `chirp-headscale` service | The coordination server, on port 8090 — needs a couple of one-time `docker exec` commands after first start (creating a user, generating a preauth key), see that compose file's own comments |
| `chirp-derper` service | A self-hosted DERP relay (the NAT-traversal fallback) — chirp-server-instances doesn't include this, relying on Tailscale's own public DERP servers instead |

Neither TLS nor DNS automation is bundled with chirp-server's own
standalone setup — getting a real domain/certificate in front of port
8090 (a reverse proxy of your own, or a second hostname on chirp-server's
existing Cloudflare Tunnel) is left to the operator.

See the Tech Docs "Remote Access (Tailscale/Headscale)" page for the full
one-time setup (DNS record, API token, port forward) and how to get a
device or another server onto the same tailnet.

## History: an earlier chirp-multi version of this document

An earlier version of this document described a similar mesh design
built specifically for chirp-multi, a since-removed earlier attempt at
a separate multi-tenant application (see `chirp-server/MULTI_INSTANCE.md`
for the full history). The tested implementation described above lives
in `chirp-server-instances` instead, which is the current recommended
multi-tenant approach.
