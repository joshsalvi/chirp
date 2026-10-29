# Chirp Device

Raspberry Pi 5 bird call detection agent. Listens via USB microphones, detects bird calls with BirdNET (optionally accelerated by Google Coral), and uploads recordings to the Chirp Server.

## Hardware Requirements

- Raspberry Pi 5 (4 GB+ RAM recommended)
- 1–2 USB microphones — see **Microphone Recommendations** below
- Google Coral USB/M.2 Accelerator (optional — ~8x faster inference, ~$60)
- Power supply: 5V/5A USB-C for Pi 5

## Microphone Recommendations

**Beamforming/voice-array mics are the wrong tool for omnidirectional bird call capture, even though they're good hardware.** Beamforming DSP is designed to isolate sound from *one* direction (a person talking to a voice assistant) and suppress everything else — the opposite of what you want for catching calls from birds in any direction around the device. This isn't a guess: it's the consistent, well-reasoned recommendation from the BirdNET-Pi community (a much larger, longer-running version of this same setup) — see [their microphone discussion](https://github.com/mcguirepr89/BirdNET-Pi/discussions/39), where an ornithologist on the project makes the case in detail.

**If you're using the ReSpeaker USB Mic Array (XVF-3000/3800):** Chirp already avoids the beamforming problem by default — `respeaker.py` reads the 4 raw per-capsule channels (the default 6-ch firmware) and averages them to mono, bypassing the chip's onboard voice-isolation DSP entirely. The one thing to check: if you've specifically flashed the *1-channel* firmware variant, that single output channel **is** the beamformed signal — switch back to the default 6-ch firmware if so.

For new setups, in order of expected quality:

1. **Best results (~$100 total):** a lavalier mic built on the **Primo EM172** or **EM272** electret capsule (very low self-noise, ~14–15 dBA) connected via a USB audio interface that supplies plugin/phantom power — see [this writeup](https://www.dzombak.com/blog/2025/07/recommendation-microphone-setup-for-birdnet-pi/) for a specific tested combination. Omnidirectional, no in-mic "voice enhancement" DSP to fight against.
2. **Simpler one-box option (~$90):** **Blue Yeti Nano** set to omnidirectional pickup pattern — plug-and-play USB, no audio interface needed, flat response out to ~18kHz, decent SNR. The easiest upgrade path if you don't want to deal with a separate audio interface + lavalier cable.
3. **Budget/starter:** any plug-and-play USB mic explicitly sold as *omnidirectional* (Boya and Saramonic lavalier-style USB mics come up often in the community). Avoid generic unbranded USB desktop mics — frequency response typically rolls off well before 10kHz, well short of where many bird calls live.

### Running the ReSpeaker and an AudioMoth together

`config.yaml`'s default `device_name_hints` and `detection.bat_echolocation.device_name` are already set up for a ReSpeaker + **AudioMoth USB Microphone** combo (the cheapest mic that covers bat echolocation too, ~$80–100 — see `bat_echolocation`'s config comments for the full price range up to ~$800). With both plugged in:

- **For bird detection:** both mics get opened and merged via `snr_weighted_merge()` — whichever has the stronger signal at any given moment automatically dominates the mix, so the AudioMoth can only help, not dilute, bird-call quality.
- **For bat detection** (off by default — see `bat_echolocation.enabled` in `config.yaml`): the AudioMoth is matched separately and exclusively for the ultrasonic pipeline.

These are two independent `sounddevice` streams opened to the same physical device. Most USB audio class hardware (AudioMoth included) tolerates this fine, but it depends on your specific ALSA/PortAudio setup — if you hit a "device busy" error with bat detection enabled, dedicate the AudioMoth to one role (remove it from `device_name_hints` to free it for bat-only, or set `bat_echolocation.enabled: false` to keep it bird-only). The ReSpeaker alone already handles bird detection well, so bat-only is a reasonable default resolution if you hit that conflict.

## Installation

```bash
# CPU-only (BirdNET via Python/TFLite)
chmod +x install.sh && ./install.sh

# With Google Coral USB Accelerator support
chmod +x install-coral.sh && ./install-coral.sh
```

## Configuration

Edit `config.yaml`:

```yaml
upload:
  enabled: true
  server_url: "http://YOUR_SERVER_IP:8765"
  api_key: "YOUR_DEVICE_API_KEY"   # from Chirp WebGUI → Settings → Device API Keys

detection:
  birdnet:
    backend: "cpu"    # or "coral" if Coral installed
    min_confidence: 0.25

server_sync:
  enabled: true
  server_url: "http://YOUR_SERVER_IP:8765"
  api_key: "YOUR_DEVICE_API_KEY"
```

**Sending to more than one server** (e.g. your normal chirp-server plus a
chirp-server-instances deployment, from this same device — a
microphone can only be claimed by one service, so this is how "also send
to a second server" works without a second Pi): replace the single
`server_url`/`api_key` above with an `upload.targets:` list instead. Fully
documented with a working example directly in `config.yaml`'s own
`upload:` section — the existing single-target config above keeps working
completely unchanged if you don't need this.

## Usage

```bash
source venv/bin/activate
python main.py --list-devices      # List audio input devices
python main.py --test-audio        # Check microphone levels
python main.py --test-detection    # Verify BirdNET is working
python main.py                     # Start detecting
```

> **If chirp is already running as a service**, stop it before running
> `--test-audio` or `--test-detection` — only one process can hold the
> microphone open at a time. Trying to test while the service is running
> fails with an ALSA error like `unable to open slave` or `Device or
> resource busy`:
> ```bash
> sudo systemctl stop chirp
> python main.py --test-audio
> sudo systemctl start chirp   # don't forget to restart it afterward
> ```

## Run as a Service

```bash
sudo systemctl enable chirp
sudo systemctl start chirp
journalctl -u chirp -f             # Watch logs
```

## Argon ONE v5 Industria OLED Display (optional)

The case and its screen are optional; without them the station runs headless.

If you're running an Argon ONE v5 Industria case, **`install.sh` now automatically disables the Argon ONE's own OLED daemon (`argononed.service`)** so Chirp's own display (bird detections, system stats, etc.) has sole control of the screen — without this, the Argon ONE's default screens (IP/CPU temp) win the conflict and Chirp's pages never show.

**Already installed before this was added?** Run the standalone fix instead of reinstalling:
```bash
chmod +x fix-argon-oled.sh
./fix-argon-oled.sh
```

**Trade-off to know about:** disabling `argononed` also disables the case's physical power button (press to reboot/shutdown) — that daemon handles both the OLED and the button. You can still shut down safely via SSH (`sudo shutdown now`). Cooling is **not** affected: the Argon ONE v5's fan is controlled by the Pi's own kernel thermal governor, not by this daemon (that's only true of the older v1–v3 Argon ONE cases). Chirp's own OLED page-advance button (GPIO 27) is a separate pin and unaffected either way.

## Coral EdgeTPU Performance

| Backend | Inference latency |
|---|---|
| CPU (Pi 5) | ~150–400 ms per 3-second window |
| Coral EdgeTPU | ~20–50 ms per 3-second window (~8x faster) |

The Coral allows real-time continuous processing without audio gaps. Supports USB Accelerator, M.2 A+E, M.2 B+M, and PCIe form factors.

## Server-Managed Config

When paired with the Chirp Server, the device polls for config updates every 60 seconds. Admins can push config changes from the Devices page without SSH access. The device also sends heartbeats every 30 seconds so the server shows live status.

## Night Audio (Nighthawk)

From 1.4.0, when a server turns on Settings → Experimental → Night flight calls, the device uploads its recording audio during that server's night hours as 10-minute 22.05 kHz FLAC chunks (about 60–90 MB per hour). Each upload target is asked every 15 minutes (`GET /api/v1/night-calls/accepting`); targets that haven't turned it on get nothing. Chunks wait in `night_audio.dir` (`~/chirp/night_audio`) until uploaded; past `night_audio.max_backlog_gb` (3 GB) the oldest are dropped. Set `night_audio.enabled: false` to never send night audio.
