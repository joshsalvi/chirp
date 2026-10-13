# Server Deployment

The server runs as a single Docker container — no external database,
message queue, or other infrastructure to stand up separately.

## Quick start

```bash
cp .env.example .env
# Edit .env — required: CHIRP_SECRET_KEY, CHIRP_DEVICE_API_KEY
docker-compose up -d --build
# WebGUI:   http://YOUR_IP:8765
# API docs: http://YOUR_IP:8765/api/docs
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `CHIRP_SECRET_KEY` | Yes | JWT signing secret — generate with `openssl rand -hex 32` |
| `CHIRP_DEVICE_API_KEY` | Yes | Default API key edge devices authenticate with |
| `CHIRP_EBIRD_API_KEY` | No | eBird API v2 key — enables the Field Guide feature |
| `CHIRP_AUTH_ENABLED` | No | Set `true` to require login for dashboard access |
| `CHIRP_ADMIN_PASSWORD` | No | Initial admin password (default: `chirp-admin` if unset) |

## Volume paths

Everything persistent lives under a single mounted volume:

| Container path | Contents |
|---|---|
| `/app/data` | Everything below — mount this whole path to persistent storage |
| `/app/data/chirp.db` | SQLite database |
| `/app/data/recordings/` | WAV audio files |
| `/app/data/spectrograms/` | Generated spectrogram PNGs |
| `/app/data/media/birds/` | Downloaded species photos and reference audio |

## Schema migrations

New database columns are added automatically on every container startup
(via a migration check built into the app, not a separate migration tool like Alembic)
— existing data is preserved, and adding a new field to the codebase is
enough for it to appear in the live schema on next restart.

## Frontend development

```bash
cd frontend
npm install
npm run dev      # dev server with hot reload, http://localhost:5173
npm run build    # production build → dist/, copied into the Docker image at build time
```
