# Chirp — Technical Documentation

Chirp is a self-hosted, edge-AI bioacoustic monitoring system for automated
detection, classification, recording, and archival of bird and bat
vocalizations. It runs entirely on your own hardware — a Raspberry Pi–class
edge device paired with a self-hosted server — with no cloud subscriptions,
no third-party data sharing, and no per-detection costs.

## What this system does

At a high level, Chirp continuously listens to one or more microphones
attached to an edge device deployed outdoors. When it detects a plausible
bird or bat vocalization, it classifies the species using an on-device
neural network, records a clip of the encounter, and uploads it to a
self-hosted server. The server re-analyzes the recording, generates a
spectrogram, enriches the detected species with information pulled from
several public data sources (range maps, photos, calls, descriptions), and
makes everything available through a web dashboard and installable
mobile-style app (PWA).

This is conceptually similar to commercial products like BirdWeather or
HaikuBox, but self-hosted (your data stays on your own hardware) and built
around a genuinely novel two-stage on-device detection architecture — see
[Detection Pipeline](detection-pipeline.md) for the specifics that
distinguish it from simpler "always run the full classifier" approaches.

## Document map

| Page | Covers |
|---|---|
| [System Architecture](architecture.md) | The overall edge-device / server split, how they communicate, and repository layout |
| [Detection Pipeline](detection-pipeline.md) | The two-stage filter-then-classify pipeline that makes continuous on-device detection practical on modest hardware |
| [Species Enrichment](enrichment.md) | How a raw species name becomes a full profile — photos, calls, range maps, descriptions |
| [Hardware & Edge Device](hardware.md) | What the edge device is, configuration parameters, microphone handling, OLED status display |
| [Microphones](microphones.md) | Model recommendations, ReSpeaker-specific setup, running a bird mic alongside a bat-detection mic |
| [Device Setup Guide](device-setup.md) | Step-by-step build: OS flashing, Argon ONE case assembly, Coral install, OLED, Zigbee, systemd, troubleshooting, bill of materials |
| [Server Deployment](deployment.md) | Docker-based deployment, environment variables, volumes |
| [Configuration Reference](configuration.md) | Every currently-used configuration knob, drawn directly from the config files |
| [AI Features](ai-features.md) | Optional LLM-powered features (Daily Journal, profile summaries, call re-analysis) and Ollama setup |
| [API Reference](api.md) | Key REST/WebSocket endpoints |
| [FAQ / Troubleshooting](faq.md) | Common issues and how they were diagnosed and fixed |

## Key features

| Feature | Details |
|---|---|
| Edge AI | BirdNET TFLite + optional Google Coral TPU (~8x speedup) |
| Pre-roll capture | 5-second circular buffer — never miss a call onset |
| Dual-path audio | Separate detection path (primary mic) and recording path (SNR-weighted mix) |
| Spectrograms | Mel-scale with per-species detection overlays |
| Server re-analysis | Second-opinion BirdNET pass with location + date filtering |
| AI Features (optional) | Daily Journal, profile summaries, spectrogram re-analysis — Anthropic/OpenAI/Gemini/Ollama, off by default |
| Species enrichment | Auto-pulls eBird, Xeno-canto, iNaturalist, Wikipedia, BirdLife |
| Range maps | Three sources — All About Birds, iNat Geomodel, BirdLife — with per-source toggle |
| Location-aware | eBird regional species with monthly frequency data |
| Live notifications | WebSocket push + email for new species / daily digest |
| iNaturalist submit | One-click sound observation upload |
| eBird export | Download life list as importable CSV |
| Backup & restore | One-click database backup / restore |
| SSH terminal | In-browser terminal to any paired Pi |
| PWA | Installable on iOS, Android, desktop |
| Auth | Optional login — admin / submitter / viewer roles |

## User roles

| Role | Permissions |
|---|---|
| Admin | Everything — settings, user management, iNat submit, backup/restore, SSH |
| Submitter | All views + iNaturalist submission + recording upload |
| Viewer | Read-only — recordings, life list, bird profiles, notes |

## Versioning

Chirp uses a four-part version number: `0.X.Y.Z`

```
  0 . 1 . 3 . d
  │   │   │   └─ Patch letter  (a b c d …)
  │   │   └───── Minor version (0, 1, 2, 3 …)
  │   └───────── Major version (0, 1, 2 …)
  └───────────── Epoch         (always 0 until public commercial launch)
```

**Epoch `0`** — the leading zero means Chirp is in pre-commercial
development. It becomes `1` at the first stable public/commercial
release.

**Major `X`** — increments when something breaks backwards compatibility
or requires a significant manual step: a database migration to run
yourself, a renamed config key, a hardware requirement change, or a
fundamental architectural rewrite. Always called out clearly in the
changelog when it changes.

**Minor `Y`** — increments when a new user-visible feature is added. New
pages, new integrations, new hardware support. The system still works
the same way, just has more capabilities.

**Patch `Z`** — a letter (`a`, `b`, `c`, `d` …) that resets to `a`
whenever `Y` increments. Contains only fixes and small improvements
within the same feature set:

| Letter | Meaning | Typical contents |
|---|---|---|
| `a` | Initial | First release of this X.Y |
| `b` | Bugfix | Stability patches, error handling |
| `c` | Critical | Hotfixes for crashes, data loss, or security issues |
| `d` | Developer | Audits, documentation, tooling, no user-facing change |
| `e` | Enhancement | UX polish, performance, no new features |
| `f` onwards | Extended patch | Additional fixes if needed before the next minor |

Where to find the current version: bottom of the sidebar in the app
("v0.X.Y.Z · What's New"), Settings → About, `GET /api/v1/health`, or
`CHANGELOG.md` at the repository root.

## A note on how this documentation was built

Every technical claim in this guide is drawn directly from the
running code and configuration files in this repository — not from a
generic description of "how a system like this might work." Where a
number, threshold, or mechanism is stated, it reflects the current
implementation. If the code changes, this documentation should be updated
to match; it isn't a static spec written once and left to drift.
