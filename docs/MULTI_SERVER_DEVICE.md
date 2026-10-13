# Sending One Device to Multiple Servers

A single `chirp-device` (Raspberry Pi) can send its recordings and
detections to more than one server at once — for example, your normal
`chirp-server` deployment *and* a `chirp-server-instances` deployment, from
the same physical Pi. This matters because a microphone can only be claimed
by one capture pipeline at a time — you can't run two separate
`chirp-device` processes against the same hardware, so "send to two
places" has to happen *after* capture, inside the upload step, on a single
running service. That's exactly what this does.

This is real, tested functionality already built into `chirp-device`'s
`uploader.py` — this page exists to give it one clear, complete
walkthrough in one place, rather than leaving it split across
`config.yaml`'s own comments and that module's docstring.

## How it works, briefly

Audio capture and BirdNET inference happen exactly once, same as always.
The resulting recording and its detections then get handed to **every
configured upload target**, each with its own independent queue, its own
thread, and its own retry logic — a slow or temporarily-unreachable
second target can never block or slow down delivery to the first. Local
file deletion is decided by the *first* configured target only (the
"primary" one); every target after that is treated as best-effort and
secondary, which is exactly the shape "also send a copy somewhere else"
needs — a flaky secondary server should never be able to make recordings
pile up on the SD card.

Every target speaks the same upload protocol (a device API key, sent as
a header, with lazy one-time pairing to obtain a `device_id` that's then
cached to disk) — a second target just means a second URL/key pair
pointed at a different server, not a different contract to configure
around.

## Setup

Open `chirp-device/config.yaml` and find the `upload:` section. By
default it has a single `server_url`/`api_key` pair (unchanged, original
behavior). To send to more than one server, replace that with a
`targets:` list instead:

```yaml
upload:
  enabled: true
  targets:
    - name: "chirp-server"           # your normal, primary server
      type: "chirp-server"
      enabled: true
      server_url: "https://chirp.yourdomain.com/api/v1/recordings/upload"
      api_key: "YOUR_DEVICE_API_KEY"   # Chirp WebGUI → Settings → Devices → New Key
      auth_header: "X-API-Key"

    - name: "chirp-server-instances"  # a second server — e.g. the
                                       # multi-tenant fork, or any other
                                       # chirp-server/-instances deployment
      type: "chirp-server"
      enabled: true
      server_url: "https://your-instances-domain.com/api/v1/recordings/upload"
      api_key: "ANOTHER_DEVICE_API_KEY"   # generated the same way, on that server's own Settings → Devices page
      auth_header: "X-API-Key"

  # Connection settings (shared by every target unless overridden per-target)
  timeout_seconds: 60
  max_retries: 5
  retry_delay_seconds: 30
  retry_backoff_factor: 2.0
  delete_after_upload: true
  upload_queue_max_size: 100
```

Restart the `chirp-device` service after editing config.yaml. That's the
entire setup — no second Pi, no second capture pipeline, no code changes.

## Verifying it's working

Check the device's own logs — each target logs independently, so you'll
see something like:

```
Upload target 'chirp-server' (chirp-server) started → https://chirp.yourdomain.com/...
Upload target 'chirp-server-instances' (chirp-server) started → https://your-instances-domain.com/...
...
[chirp-server-instances] Paired successfully, device_id=...
✅ [chirp-server] Uploaded: recording_20260809_...wav [201]
✅ [chirp-server-instances] Uploaded: recording_20260809_...wav [201]
```

Both servers should show the device as paired and start receiving
recordings within one detection cycle.

## Turning a target off without removing it

Set `enabled: false` on any target's entry — useful for temporarily
pausing delivery to a second server without losing the configuration
(API key, cached device_id) when you want to turn it back on later.

## What this doesn't do

This sends the *same* recordings and detections to every enabled
target — it's not a way to split different microphones or different
detection types across different servers. If that's ever a real need,
it would be a different, new feature, not something this multi-target
design already supports.
