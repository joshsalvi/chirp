# Device Setup Guide

A full walkthrough for building a chirp-device edge node from bare hardware:
Raspberry Pi 5, Argon ONE v5 Industria case, Google Coral M.2 accelerator,
USB microphones, and an optional Zigbee coordinator. For the concepts
behind each piece (why this hardware, how the software handles it), see
[Hardware & Edge Device](hardware.md) and [Microphones](microphones.md);
this page is the procedural companion to those.

## Hardware overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Argon ONE v5 Case                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Raspberry Pi 5 (4GB or 8GB)                │   │
│  │                                                         │   │
│  │  [USB 3.0 ×2]──── USB Microphones (1 or 2)             │   │
│  │  [USB 2.0 ×2]──── Zigbee Dongle (if not M.2)           │   │
│  │  [PCIe/M.2 slot]─ Google Coral M.2 B+M Accelerator     │   │
│  │  [I²C GPIO]─────  Argon ONE Industria OLED (built-in)   │   │
│  │  [I²C 0x1A]─────  Argon ONE fan/power controller        │   │
│  │  [GbE]──────────  Network (or USB WiFi)                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  TOP PANEL: 128×32 SSD1306 OLED display (Industria edition)    │
│  BACK PANEL: HDMI ×2, USB-A ×4, USB-C power, Ethernet         │
└─────────────────────────────────────────────────────────────────┘
```

## Raspberry Pi 5 — initial OS setup

### 1. Flash Raspberry Pi OS

Use the **Raspberry Pi Imager** tool (raspberrypi.com/software) on your PC/Mac.

- **OS:** Raspberry Pi OS Lite (64-bit, Bookworm or newer) — no desktop needed
- **Storage:** MicroSD 32 GB+ Class 10, or USB SSD in the Argon ONE v5's M.2 slot

In Imager settings (⚙️ icon) before flashing:

```
Hostname:    chirp-pi (or your preferred name)
Username:    pi
Password:    (choose a strong password)
WiFi:        (configure if not using ethernet)
SSH:         Enable — Allow public-key authentication
```

The username above is a placeholder — any username works, and every
`pi@`/`/home/pi/...` path in this guide is that placeholder's stand-in,
not a hard requirement. Substitute your actual username throughout;
`config.yaml`, the systemd unit, and every install script all key off
wherever the repo actually lives, not a specific username.

### 2. First boot

Insert the storage, connect ethernet, power on. Find the Pi's IP with
`ping chirp-pi.local` or check your router.

```bash
ssh pi@chirp-pi.local
```

### 3. Initial system update

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git curl wget htop nano i2c-tools python3-pip python3-venv ffmpeg
sudo reboot
```

### 4. Enable required interfaces

```bash
sudo raspi-config
```

Navigate to **Interface Options** and enable:

- **I2C** — required for the OLED display and Argon ONE controller
- **PCIe / PCIe Gen 2** — required for the Coral M.2 (see below)

Or add directly to `/boot/firmware/config.txt`:

```ini
# I2C
dtparam=i2c_arm=on

# PCIe for Coral M.2 (required for the Coral M.2 B+M accelerator)
dtparam=pciex1
# Optional: enable Gen 2 speeds (slightly faster inference)
# dtparam=pciex1_gen=2
```

```bash
sudo reboot
```

## Argon ONE v5 case assembly

The Argon ONE v5 is an aluminum Pi 5 case with passive+active cooling, an
OLED top panel, an M.2 slot on the underside, and an integrated
power/fan controller.

### Assembly steps

1. Do **not** power on the Pi before assembly.
2. Slide the Pi into the Argon ONE base plate — align the GPIO pins with
   the internal connector.
3. If installing the Coral M.2 B+M, do so now (see next section) before
   closing the case.
4. If installing a Zigbee M.2 HAT (if using internal expansion), seat it
   on the secondary M.2 slot if available.
5. Connect the flat-flex cable from the Argon ONE top board (OLED) to the
   GPIO header adapter — this connects the SSD1306 OLED over I²C.
6. Close the case (four screws on the underside).
7. Connect the Argon ONE USB-C power controller cable (internal
   micro-USB from the Argon ONE board to the Pi's USB-C power input).

### Post-assembly I²C check

After booting:

```bash
sudo i2cdetect -y 1
```

Expected addresses:

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:          -- -- -- -- -- -- -- -- -- -- -- -- --
10: -- -- -- -- -- -- -- -- -- -- 1a -- -- -- -- --
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
30: -- -- -- -- -- -- -- -- -- -- -- -- 3c -- -- --
```

| Address | Device |
|---|---|
| `0x1A` | Argon ONE fan/power controller |
| `0x3C` | SSD1306 OLED display (Industria panel) |

If `0x3C` is missing, check the flat-flex OLED cable connection inside
the case.

## Argon ONE v5 fan & power controller

The Argon ONE v5 includes a power management and fan controller on I²C
`0x1A`. Install the official Argon ONE script for fan-curve control and
safe shutdown button support:

```bash
curl -L https://download.argon40.com/argon1.sh | bash
```

This installs:

- `argonone-config` — fan curve configuration utility
- Safe shutdown via the Argon ONE power button
- Auto-fan control based on CPU temperature

Configure the fan curve:

```bash
argonone-config
```

Recommended settings for a continuous detection workload:

```
55°C → 10%
65°C → 50%
70°C → 100%
```

!!! note "Argon ONE and Chirp run independently"
    Chirp's OLED display reads CPU temperature directly from sysfs and
    doesn't conflict with the Argon ONE fan/power controller itself. It
    **does** conflict with the Argon ONE's own OLED daemon — see
    "Argon ONE OLED daemon conflict" under [OLED display](#oled-display-industria-panel)
    below.

## Google Coral M.2 B+M accelerator

The Coral M.2 B+M uses an NVMe-style M.2 B+M connector but carries PCIe
signals, not NVMe storage. It requires the `gasket-dkms` kernel driver —
not `libedgetpu` alone.

### Hardware installation

1. Power off the Pi completely.
2. Remove the Argon ONE case bottom.
3. Insert the Coral M.2 card into the M.2 B+M slot at a 30° angle, press
   down, and secure with the M.2 screw.
4. Reassemble the case.

### Software installation

Run the Chirp Coral installer from the `chirp-device` directory:

```bash
chmod +x install-coral.sh
./install-coral.sh --pcie   # M.2 B+M / M.2 A+E / PCIe card
# or:
./install-coral.sh --usb    # USB Accelerator
```

!!! note "Raspberry Pi OS Bookworm / Trixie notes"
    - The old `apt-key` method is deprecated. The installer uses the
      modern `signed-by=` format automatically.
    - `gasket-dkms 1.0-18` from the Coral apt repo fails to build against
      recent RPi kernels (6.12+). The installer falls back to building
      from the upstream [google/gasket-driver](https://github.com/google/gasket-driver)
      source, which tracks current kernels. This takes a few minutes.
    - pycoral only has pre-built wheels for Python ≤ 3.11. Recent
      Raspberry Pi OS releases ship newer Python (3.12/3.13+). The
      installer falls back through `tflite-runtime`, then plain
      `tensorflow` (which has real wheels for current Python/aarch64 and
      works via `tf.lite.Interpreter` + the EdgeTPU delegate) — see
      `chirp/birdnet_coral.py`'s own fallback chain for the exact order.
    - A reboot is required after the first install for the gasket module
      to load and `/dev/apex_0` to appear.

The script:

- Installs the `gasket-dkms` kernel module (the correct driver for
  M.2/PCIe Coral)
- Installs `libedgetpu1-std`
- Adds your user to the `apex` group
- Creates udev rules for `/dev/apex_*`
- Downloads the BirdNET EdgeTPU TFLite model
- Runs a detection test

### Verify the device node

```bash
ls -la /dev/apex*
# Expected: crw-rw---- 1 root apex ... /dev/apex_0
```

If `/dev/apex_0` doesn't appear after reboot:

```bash
# Check PCIe is enabled
grep pciex1 /boot/firmware/config.txt

# Check gasket module is loaded
lsmod | grep gasket

# Check dmesg for Coral
sudo dmesg | grep -i "coral\|apex\|gasket"
```

### Enable Coral in Chirp

Edit `config.yaml`:

```yaml
detection:
  birdnet:
    backend: "coral"    # change from "cpu"
```

Or push from the Chirp server: **Settings → Devices → [your device] →
Inference Backend → Coral M.2**.

### Verify inference speed

```bash
source venv/bin/activate
python main.py --test-detection
```

| Backend | Inference latency (per 3s window) |
|---|---|
| CPU (Pi 5) | ~150–400 ms |
| Coral EdgeTPU | ~20–50 ms (~8x faster) |

The Coral allows real-time continuous processing without audio gaps.
Supports USB Accelerator, M.2 A+E, M.2 B+M, and PCIe form factors.

## OLED display (Industria panel)

The Argon ONE v5 Industria edition includes a 128×32 SSD1306 OLED in the
top panel, connected via I²C on address `0x3C`.

### Install display dependencies

```bash
source ~/chirp-device/venv/bin/activate
pip install luma.oled pillow smbus2
```

Or re-run the install script (it includes these):

```bash
./install.sh
```

### Verify I²C

```bash
sudo i2cdetect -y 1 | grep 3c
# Should show: 3c
```

### Display pages

The display automatically rotates through 5 pages every 5 seconds:

| Page | Content |
|---|---|
| 0 — Status | CHIRP header · online/offline indicator · detection + recording counts |
| 1 — Last Detection | Most recent species · confidence percentage · time ago |
| 2 — Upload | Successful uploads · failed · queue depth · bytes sent |
| 3 — System | CPU temperature · RAM used · disk free · uptime |
| 4 — Hardware | BirdNET backend · Coral form factor · mic count · config sync status |

A new detection temporarily flashes to page 1 for 5 seconds, then returns
to auto-rotation.

### Configure display in config.yaml

```yaml
display:
  enabled: true
  i2c_bus: 1
  i2c_address: "0x3C"
  page_interval_seconds: 5      # seconds per page
  flash_on_detection: true      # show detection page on trigger
  brightness: 200               # 0-255
```

### Disable display

If you're not using the Industria OLED panel:

```yaml
display:
  enabled: false
```

The display code is entirely non-blocking — if the display is absent or
I²C fails, Chirp continues running normally with a single log warning.

### Argon ONE OLED daemon conflict

The Argon ONE v5 Industria case ships with its own OLED daemon
(`argononed.service`) driving the same physical screen — left running,
its default screens (IP address, CPU temp) win the conflict and Chirp's
own pages above never show at all. `install.sh` now disables
`argononed.service` automatically so Chirp's display has sole control of
the screen.

Already installed before this was added? Run the standalone fix instead
of reinstalling:

```bash
chmod +x fix-argon-oled.sh
./fix-argon-oled.sh
```

**Trade-off to know about:** disabling `argononed` also disables the
case's physical power button (press-to-reboot/shutdown) — that one
daemon handles both the OLED and the button. You can still shut down
safely via SSH (`sudo shutdown now`). Cooling is unaffected either way:
the Argon ONE v5's fan is controlled by the Pi's own kernel thermal
governor, not by this daemon (that's only true of the older v1–v3 Argon
ONE cases). Chirp's own OLED page-advance button (GPIO 27) is a separate
pin and unaffected regardless.

## USB microphones

See [Microphones](microphones.md) for model recommendations, the
ReSpeaker deep-dive, and mic-specific troubleshooting. The short version
for initial setup:

```bash
source ~/chirp-device/venv/bin/activate
python main.py --list-devices      # find your mic's device number
python main.py --test-audio        # live dBFS meter — whistle/clap to check levels
```

Plug USB mics into the Pi's USB 3.0 (blue) ports where possible — higher
bandwidth and cleaner power than USB 2.0. With two mics connected, Chirp
merges them automatically for the recording path (see
[Microphones](microphones.md#dual-path-audio) for how the detection path
differs).

## Zigbee coordinator (optional)

Chirp includes a Zigbee integration module for publishing detection
events to home automation systems. This is an optional feature — the
default config has it disabled.

### Supported hardware

| Device | Notes |
|---|---|
| ConBee II / III (dresden elektronik) | Excellent compatibility, widely supported |
| SONOFF Zigbee 3.0 USB Dongle Plus | EFR32MG21, good range, inexpensive |
| SLZB-06 (SMLIGHT) | Ethernet + USB Zigbee coordinator |
| Zig-a-Zig-Ah! (ZZH) | Open hardware, CC2652 |

### Hardware setup

1. Plug the Zigbee USB dongle into a USB 2.0 port (not USB 3.0, which
   can cause RF interference on the 2.4 GHz band — use a short USB
   extension cable if needed).
2. Check it's detected:

```bash
ls /dev/ttyUSB* /dev/ttyACM*
# Expected: /dev/ttyUSB0 or /dev/ttyACM0
```

3. Ensure your user has access:

```bash
sudo usermod -aG dialout pi
# Log out and back in
```

### Option A: zigbee2mqtt mode (recommended)

The most flexible approach — connects Chirp to any MQTT-capable home
automation system (Home Assistant, Node-RED, openHAB).

**1. Install the Mosquitto MQTT broker:**

```bash
sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto
# Test: mosquitto_sub -t '#' -v &
```

**2. Install zigbee2mqtt:** follow the official guide at
zigbee2mqtt.io/guide/installation/raspberry_pi/ — point it at your
dongle (`/dev/ttyUSB0`) and broker (`localhost`).

**3. Install paho-mqtt:**

```bash
source ~/chirp-device/venv/bin/activate
pip install paho-mqtt
```

**4. Enable in config.yaml:**

```yaml
zigbee:
  enabled: true
  mode: "zigbee2mqtt"
  coordinator_port: "/dev/ttyUSB0"
  mqtt_broker: "localhost"
  mqtt_port: 1883
  mqtt_topic_prefix: "chirp"
```

**5. Subscribe to detections:**

```bash
mosquitto_sub -t 'chirp/#' -v
```

Detection events appear as:

```json
chirp/detection {"event":"detection","species":"American Robin","confidence":0.89,"timestamp":"2026-05-30T14:23:11Z","device_name":"Garden Pi","backend":"coral"}
chirp/status    {"online":true,"triggers_today":12,"recordings":8,"cpu_temp_c":41.2,"disk_free_gb":14.3}
```

### Option B: Home Assistant auto-discovery (planned)

A future release will publish MQTT discovery payloads so the Chirp
device appears automatically as a sensor entity in Home Assistant, with
attributes for last species, confidence, detection count, CPU
temperature, and disk free.

### USB interference note

Zigbee operates on 2.4 GHz. USB 3.0 can generate interference on the
same band. If Zigbee is unstable: move the dongle away from USB 3.0
devices using a 15–30 cm USB 2.0 extension cable, and plug into a USB
2.0 (black) port specifically.

## Chirp software installation

### 1. Clone the repository

```bash
cd ~
git clone <your-repo-url> chirp-device
cd chirp-device
```

### 2. Run the installer

```bash
chmod +x install.sh
./install.sh
```

This installs a Python virtual environment, audio libraries
(libportaudio2, libsndfile1, ALSA tools), the Python package set
(sounddevice, birdnetlib, scipy, numpy, zeroconf, luma.oled, etc.), the
BirdNET model (auto-downloaded on first run), and the systemd service.

### 3. Install Coral support (if using Coral M.2)

```bash
chmod +x install-coral.sh
./install-coral.sh
# Auto-detects the M.2/PCIe form factor and installs gasket-dkms
```

### 4. Edit config.yaml

```bash
nano ~/chirp-device/config.yaml
```

Minimum required configuration:

```yaml
detection:
  birdnet:
    backend: "coral"     # or "cpu" if no Coral
    latitude: 40.7128    # your location for species filtering
    longitude: -74.0060

upload:
  enabled: true
  server_url: "https://chirp.yourdomain.com"
  api_key: "YOUR_DEVICE_API_KEY"   # from server Settings → Devices → New Key

server_sync:
  enabled: true
  server_url: "https://chirp.yourdomain.com"
  api_key: "YOUR_DEVICE_API_KEY"
  device_name: "Garden Pi"
```

### 5. Test everything

```bash
source venv/bin/activate

python main.py --list-devices      # list audio input devices
python main.py --test-audio        # live dB levels — whistle or play a bird call
python main.py --test-detection    # test BirdNET (plays synthetic audio internally)
python main.py                     # run in foreground to watch output
```

!!! warning "Stop the service first"
    If chirp-device is already running as a systemd service, stop it
    before running `--test-audio` or `--test-detection` — only one
    process can hold a microphone open at a time. Testing while the
    service is running fails with an ALSA error like
    `unable to open slave` or `Device or resource busy`:

    ```bash
    sudo systemctl stop chirp-device
    python main.py --test-audio
    sudo systemctl start chirp-device   # don't forget to restart it afterward
    ```

## Server pairing

Once the server is running, pair automatically (recommended) or manually.

### Option A: auto-discovery from the server (easiest)

1. Open the Chirp web UI → Settings → Devices → Discover
2. The server scans the local network for Raspberry Pi devices via mDNS
   (`_chirp._tcp`) and the ARP table
3. Click Auto-configure next to your Pi
4. Enter the Pi's SSH password (change the default before doing this!)
5. The server generates an API key, writes it to `config.yaml`, and
   restarts `chirp-device`
6. Your Pi appears in the Devices list within 60 seconds

### Option B: manual pairing

1. In the Chirp web UI → Settings → Devices → New Device Key — generate
   a key
2. Copy the key
3. On the Pi, edit `~/chirp-device/config.yaml`:

```yaml
server_sync:
  enabled: true
  server_url: "https://chirp.yourdomain.com"
  api_key: "chirp-PASTE_KEY_HERE"
  device_name: "Garden Pi"

upload:
  enabled: true
  server_url: "https://chirp.yourdomain.com/api/v1/recordings/upload"
  api_key: "chirp-PASTE_KEY_HERE"
```

4. Restart:

```bash
sudo systemctl restart chirp-device
```

Once paired, the device polls the server for config updates every 60
seconds and sends a heartbeat every 30 seconds — see
[Hardware & Edge Device](hardware.md#server-managed-config) for what
that enables.

## Systemd service

chirp-device runs as a systemd service for auto-start on boot.

```bash
# Installed automatically by install.sh — just start it:
sudo systemctl start chirp-device
sudo systemctl status chirp-device
```

### Useful commands

```bash
sudo systemctl status chirp-device       # check if running
sudo journalctl -u chirp-device -f       # live logs
sudo systemctl restart chirp-device      # restart after config changes
sudo systemctl stop chirp-device         # stop
sudo systemctl enable chirp-device       # auto-start on boot (already set by install.sh)
```

The service auto-restarts on failure with a 15-second delay (up to 5
times in 5 minutes).

## Troubleshooting

### OLED display not showing anything

```bash
# Check I²C is enabled and the device is detected
sudo i2cdetect -y 1 | grep 3c
# If no output: check the flat-flex cable inside the case

# Check luma.oled is installed
python3 -c "from luma.oled.device import ssd1306; print('OK')"

# Check the Chirp log for display errors
journalctl -u chirp-device | grep -i oled
```

If I²C shows `0x3C` and `luma.oled` imports fine but the screen is still
blank, also check for the Argon ONE daemon conflict above — a
still-running `argononed.service` will win control of the display even
though Chirp itself is working correctly.

### Coral M.2 not detected (`/dev/apex_0` missing)

```bash
# Check PCIe is enabled in firmware
grep pciex1 /boot/firmware/config.txt

# Check the gasket module
lsmod | grep gasket

# Check dmesg
sudo dmesg | grep -i "coral\|apex\|gasket\|pcie"

# Try reloading the module
sudo modprobe gasket
sudo modprobe apex
ls /dev/apex*
```

If the module loads but `/dev/apex_0` is absent, the M.2 card may not be
seated properly — reseat it and ensure the retaining screw is tight.

### No audio devices found

```bash
# Check USB mics are connected to USB 3.0 ports
lsusb | grep -i "audio\|mic\|blue\|rode\|samson"

# List ALSA devices
arecord -l

# Check sounddevice
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```

### BirdNET returning no detections

```bash
# Test with verbose output
python main.py --test-detection --verbose

# Check the confidence threshold isn't too high
grep min_confidence ~/chirp-device/config.yaml

# Check the energy filter isn't blocking everything —
# reduce threshold_db if in a very quiet environment (more sensitive):
# threshold_db: -70.0
```

### Owls or other night calls missed

```bash
bash ~/chirp-device/tools/night-check.sh                 # last night: settings, gate stats, drops, night detections, Coral, XVF3800, throttling
SINCE="3 days ago" bash ~/chirp-device/tools/night-check.sh
```

On the server, `docker exec chirp-server-instances python3 /app/scripts/night-report.py` compares overnight Chirp and Haikubox detections hour by hour and lists Haikubox nocturnal detections Chirp missed.

### Upload failing / not reaching the server

```bash
# Check network
curl -f https://chirp.yourdomain.com/api/v1/health

# Check the API key is correct
grep api_key ~/chirp-device/config.yaml

# Watch upload logs
journalctl -u chirp-device | grep -i "upload\|HTTP\|retry"
```

### Zigbee MQTT not connecting

```bash
# Check the broker is running
sudo systemctl status mosquitto

# Test manually
mosquitto_pub -t test -m hello
mosquitto_sub -t test &

# Check paho-mqtt is installed
python3 -c "import paho.mqtt.client; print('OK')"

# Watch Chirp's Zigbee logs
journalctl -u chirp-device | grep -i "zigbee\|mqtt"
```

## Reference: bill of materials

| Item | Approx. cost |
|---|---|
| Raspberry Pi 5 — 8GB | $80 |
| Argon ONE v5 Industria case | $45 |
| Google Coral M.2 B+M Accelerator | $25 |
| MicroSD 64 GB (Class 10 / A2) | $12 |
| 5V / 5A USB-C power supply | $12 |
| USB microphone × 2 (e.g. Samson Go Mic) | $35–$80 |
| ConBee II Zigbee dongle (optional) | $35 |
| Short USB 2.0 extension, 15 cm (Zigbee RF isolation) | $3 |
| M.2 SSD (optional, for storage) | $15–$30 |
| **Total (without optional items)** | **~$210** |

See also: [Hardware & Edge Device](hardware.md) ·
[Microphones](microphones.md) · [Server Deployment](deployment.md)
