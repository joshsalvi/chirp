# Chirp Server

Docker-based bird call detection server. Receives recordings from Chirp devices, generates spectrograms, enriches bird profiles from Cornell Lab / Xeno-canto / Wikipedia, and serves a React WebGUI.

## Quick Start (Unraid / Docker)
```bash
cp .env.example .env
# Edit .env — required: CHIRP_SECRET_KEY, CHIRP_DEVICE_API_KEY
docker-compose up -d --build
# WebGUI: http://YOUR_IP:8765
# API docs: http://YOUR_IP:8765/api/docs
```

## Environment Variables (.env)

| Variable | Required | Description |
|---|---|---|
| `CHIRP_SECRET_KEY` | ✅ | JWT signing secret (generate with `openssl rand -hex 32`) |
| `CHIRP_DEVICE_API_KEY` | ✅ | Default API key for Chirp devices |
| `CHIRP_EBIRD_API_KEY` | Optional | eBird API v2 key (enables Field Guide) |
| `CHIRP_AUTH_ENABLED` | Optional | Set `true` to require login |
| `CHIRP_ADMIN_PASSWORD` | Optional | Initial admin password (default: `chirp-admin`) |

## Volume Paths

| Container path | Purpose |
|---|---|
| `/app/data` | All persistent data (mount to Unraid share) |
| `/app/data/chirp.db` | SQLite database |
| `/app/data/recordings/` | WAV files |
| `/app/data/spectrograms/` | Generated PNG spectrograms |
| `/app/data/media/birds/` | Bird photos, call audio |

## Schema Migrations

New columns are added automatically via `_migrate_columns()` in `database.py` on every startup. No Alembic required — just add the column to the `pending` dict and the model.

## API Documentation

Full Swagger UI: `http://YOUR_IP:8765/api/docs`

Key endpoints:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/recordings/upload` | Device recording upload (API key auth) |
| `GET` | `/api/v1/recordings` | List recordings with pagination |
| `GET` | `/api/v1/recordings/statistics/full` | Detection analytics for Statistics page |
| `GET` | `/api/v1/birds/life-list` | All detected species with detection counts |
| `GET` | `/api/v1/birds/regional-library` | eBird regional species with frequencies |
| `POST` | `/api/v1/recordings/{id}/submit-inaturalist` | Submit to iNat (admin/submitter) |
| `GET` | `/api/v1/settings/backup/download` | Download database backup |
| `POST` | `/api/v1/settings/backup/restore` | Restore database from upload |

## Detection Count Consistency

All detection counts in the API respect two global settings:
- **`min_confidence_display`** — hides detections below this confidence threshold
- **`show_deleted_detections`** — whether to include recordings that have been soft-deleted

These are applied consistently across: bird profile stats, life list, dashboard stats, statistics page, and regional library.

## Multiple Locations / Tenants

Running more than one location? See [MULTI_INSTANCE.md](MULTI_INSTANCE.md)
for two supported approaches — separate independent chirp-server
containers (with `chirp-launcher`, a small bundled switcher page for
navigating between them) or the actively maintained
`chirp-server-instances` fork (one shared app, per-tenant databases,
a Global Admin panel).

## Remote Devices (a chirp-device not on this server's own LAN)

Got a Raspberry Pi somewhere other than this server's own network?
`docker-compose.headscale.yml` is a separate, opt-in compose file with
a self-hosted Tailscale-compatible mesh (Headscale + its own DERP
relay) — bring it up alongside the main one:

```bash
docker compose -f docker-compose.yml -f docker-compose.headscale.yml up -d
```

Needs a couple of one-time `docker exec` setup commands after first
start (see that file's own comments), and doesn't bundle TLS/DNS
automation the way `chirp-server-instances`' own equivalent does —
see [docs/REMOTE_DEVICES.md](../docs/REMOTE_DEVICES.md) at the repo
root for the full walkthrough and how this compares to that project's
bundled setup.

## Frontend Development

```bash
cd frontend
npm install
npm run dev        # Dev server with HMR at :5173
npm run build      # Production build to dist/
```

The built `dist/` is copied into the Docker image at build time.
