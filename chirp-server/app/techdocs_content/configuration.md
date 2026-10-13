# Configuration Reference

Current values from `chirp-device/config.yaml`, grouped by
section. Comments in the file itself are often more detailed than what's
summarized here — worth reading directly for anything you're about to
change.

## Audio capture

| Setting | Value | Notes |
|---|---|---|
| `sample_rate` | 48000 Hz | Matched to BirdNET's expected input rate |
| `channels_per_device` | 1 (mono) | Merged to stereo for the final output stream |
| `chunk_size` | 8192 samples | Larger values trade latency for reliability on slower USB devices — increase further if you see "input overflow" warnings |
| `bit_depth` | 16-bit | WAV output |
| `max_devices` | 4 | Maximum simultaneous input streams |
| `input_gain_db` | 6.0 | Applied to every input stream at capture time, before Stage 1 ever sees the audio — Stage 1's threshold_db below is measured AFTER this gain, so lowering it shifts what survives Stage 1's gate |

## Detection — Stage 1 (energy filter)

| Setting | Value |
|---|---|
| `enabled` | true |
| `window_seconds` | 0.5 |
| `threshold_db` | −90.0 (relative full-scale) |
| `frequency_band_hz` | [150, 12000] — keeps Great Horned Owl (~200–400 Hz) and Barred Owl (~300–600 Hz) hoots inside the gate |
| `filter_order` | 4 (Butterworth) |

A device paired to a server runs the server's managed config on top of these values. Before 0.5.7.ae the server pushed `threshold_db: -55` and `input_gain_db: 0`, 36 dB stricter than the device defaults; devices still carrying those are upgraded automatically on their next heartbeat. Since 0.5.7.ag the default is −90 dB, and devices still on the earlier −85 dB default move to −90 the same way; a hand-set gate is left alone. The gate uses the loudest 0.5 s sub-window of each 3 s analysis window.

## Detection — Stage 2 (BirdNET)

| Setting | Value |
|---|---|
| `enabled` | true |
| `analysis_window_seconds` | 3.0 |
| `min_confidence` | 0.05 |
| `sensitivity` | 1.5 — BirdNET sigmoid sensitivity (0.5–1.5); applied on both CPU and Coral |
| `overlap_seconds` | 2.0 |
| `night_species_min_confidence` | 0.10 — owls, nightjars, rails, woodcock and bitterns trigger at this even when `min_confidence` (often pushed from the server) is higher |
| `night_global_species` | [] — night callers held to `min_confidence` instead (sent by the server from Settings → Detection → Night-Caller Thresholds, "Per species"; in "Global" mode the server sends `night_species_min_confidence` equal to `min_confidence`) |
| `backend` | `cpu` (default) or `coral`. Coral needs a compiled BirdNET EdgeTPU model, which isn't published upstream; a Coral that can't load falls back to CPU |
| `num_threads` | 2 — TFLite CPU threads for BirdNET (birdnetlib uses 1) |

The Devices page offers a switch to Coral only when the device has a compiled EdgeTPU model, and a switch back to CPU when Coral is selected but can't load. Since device 1.2.30 the heartbeat reports the backend actually running, not only the configured one.

Every 10 minutes the device logs a `Window stats` line: window count, how many passed the gate and BirdNET, the 10th/50th/90th percentile and max window level, the gate, and dropped windows. If owls are missed while p90 sits well below the gate, lower `threshold_db`. When BirdNET falls behind, the device temporarily cuts the overlap to 1 s (no gaps between 3 s windows) instead of dropping windows.

On the server, owls, nightjars, rails, woodcock and bitterns only need 0.10 confidence in the BirdNET pass (other species still need `birdnet_min_confidence`), a device detection of a nightjar, rail, woodcock or bittern at 0.10 or higher is kept when the server pass finds other species (a device owl stays only when the server pass finds that owl too), and auto-purge deletes any recording that shows nothing at the display threshold (the list's "Unknown" cards), at upload and in a sweep every 15 minutes. The one exception is an owl the server pass kept under its owl rules (0.20 plus a hoot at its pitch and a full-band score of 0.30). Manual uploads, labeled or noted recordings and iNaturalist submissions are never swept. Deletes run 20 recordings per database commit with files removed after each commit, so uploads and other deletes carry on during a large sweep. Recordings that auto-purge keeps but that still show nothing at the display threshold (an owl kept under its owl rules at 0.20–0.35, say) are hidden from Recordings and the Dashboard; the "Unknown only" filter lists them. Settings → Detection → Night-Caller Thresholds sets whether night callers use their own floors (default), the global BirdNET threshold, or a choice per species; a per-species score from Near Misses still wins. Changing the display threshold pre-renders spectrograms for the newest 500 recordings (`CHIRP_SPECTROGRAM_PREWARM`); the rest are drawn when opened, and Settings → Storage & Backup can clear images cached for old thresholds, palettes or deleted recordings. Set `logging.window_stats_interval_seconds: 0` to turn it off.

## Pre-roll

| Setting | Value |
|---|---|
| `pre_roll_seconds` | 5.0 |

## Location filtering

BirdNET's species list can be scoped to what's realistic at a given
latitude/longitude and time of year — normally pushed automatically from
the server's own Settings → General → Location & Time Zone configuration rather than set
independently per device.

## Upload

| Setting | Value |
|---|---|
| `retry_delay_seconds` | 30 |
| `retry_backoff_factor` | 2.0 (exponential) |
| `retry_queued_interval_seconds` | 300 |
| `delete_after_upload` | true |

Each configured device gets its own independent retry queue and thread
— one device's upload failures don't block or delay any other device's
uploads.

### Sending to more than one server

A single device's `upload.server_url`/`api_key` can be replaced with an
`upload.targets:` list to fan the same recordings out to more than one
server at once — for example a normal chirp-server plus a second
instance for parallel testing, from one physical device (a microphone
can only be claimed by one service, so this is how "also send elsewhere"
works without a second Pi). Each target gets its own independent retry
queue, so a broken secondary target never blocks or delays the primary's
uploads. Fully documented with a working example directly in
`config.yaml`'s own `upload:` section — the single-target form above
keeps working completely unchanged if this isn't needed.

## External API keys

Two optional third-party API keys unlock extra functionality server-side
(configured in the server's own Settings, not on the device):

| Key | Where to get it | Used for |
|---|---|---|
| eBird API key | ebird.org/api/keygen (free) | Field Guide, trends, species likelihood |
| iNaturalist token | inaturalist.org/users/api_token | Submitting observations |
