# API Reference

Full interactive Swagger UI is always available on a running server at
`http://YOUR_IP:8765/api/docs` — that's the authoritative, always-current
reference. This page covers the key endpoints worth knowing about
without opening it.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/recordings/upload` | Device recording upload (API-key authenticated) |
| `GET` | `/api/v1/recordings` | List recordings, paginated |
| `GET` | `/api/v1/recordings/statistics/full` | Detection analytics powering the Statistics page |
| `GET` | `/api/v1/birds/life-list` | Every detected species with its detection count |
| `GET` | `/api/v1/birds/regional-library` | eBird regional species list with local frequency data |
| `POST` | `/api/v1/recordings/{id}/submit-inaturalist` | Submit a recording to iNaturalist (admin/submitter role) |
| `GET` | `/api/v1/settings/backup/download` | Download a full database backup |
| `POST` | `/api/v1/settings/backup/restore` | Restore the database from an uploaded backup |

## Detection count consistency

Every endpoint that reports a detection count respects the same two
global settings, applied consistently rather than each endpoint having
its own separate filtering logic:

- **`min_confidence_display`** — hides detections below this confidence
  from counts and lists
- **`show_deleted_detections`** — whether soft-deleted recordings are
  included

This consistency matters specifically because these counts appear in
several different places (bird profile stats, the life list, dashboard
summary stats, the statistics page, and the regional library) — without
a shared filtering rule, the same underlying data could show different
numbers in different parts of the app depending on which endpoint
happened to compute it.
