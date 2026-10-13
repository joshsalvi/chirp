# ReSpeaker Setup Guide for Chirp

This guide covers all ReSpeaker variants and answers the common questions about standalone use and microphone recommendations.

---

## Your device: ReSpeaker USB Mic Array

If you have the circular ReSpeaker with a USB cable (XVF-3000 or XVF-3800 chip, with case), it is a **USB plug-and-play device**. No driver installation needed. Just plug the USB cable into any port on the Pi and Chirp detects it automatically.

- Do **not** run `install-respeaker-hat.sh` (that's only for GPIO HAT variants)
- The LED ring will flash green on every bird detection (requires `pyusb`, installed by `install.sh`)
- All 4 mic channels are mixed to mono automatically for BirdNET

---

## Quick: Can I just plug it into the Pi's USB port?

**Yes, completely.** The ReSpeaker USB Mic Array uses USB Audio Class 1.0 and appears as a generic USB microphone to any application — no drivers, no setup on any OS (Linux, Windows, Mac).

To use it standalone without Chirp:
```bash
# List audio input devices
arecord -l

# Record 10 seconds of audio (replace N with card number from arecord -l)
arecord -D plughw:N -f S16_LE -r 16000 -c 1 -d 10 test.wav

# Set as system default (edit ~/.asoundrc):
defaults.pcm.card N
defaults.ctl.card N
```

For Chirp, just run `install.sh` as normal. The `respeaker.mode: auto` setting in config.yaml handles detection automatically.

---

## Verify Chirp sees your ReSpeaker

```bash
source venv/bin/activate
python main.py --list-devices
# Should show: ★ ReSpeaker  next to the device

python main.py --respeaker-info
# Shows full probe details, channel plan, LED status

python main.py --test-audio
# Shows live dB levels — talk/clap near the mic to verify
```

---

## Which form factor do you have?

| Device | Connection | Driver needed? | Install script |
|---|---|---|---|
| ReSpeaker USB Mic Array v2.0/v2.1 | USB cable | ❌ No | `install.sh` (standard) |
| ReSpeaker USB 4-Mic Array XVF3800 | USB cable | ❌ No | `install.sh` (standard) |
| ReSpeaker 2-Mics Pi HAT | GPIO header (40-pin) | ✅ Yes | `install-respeaker-hat.sh` |
| ReSpeaker 4-Mic Array HAT | GPIO header (40-pin) | ✅ Yes | `install-respeaker-hat.sh` |
| ReSpeaker 4-Mic Linear Array Kit | GPIO header (40-pin) | ✅ Yes | `install-respeaker-hat.sh` |
| ReSpeaker 6-Mic Circular Array Kit | GPIO header (40-pin) | ✅ Yes | `install-respeaker-hat.sh` |

---

## HAT variants: install driver first

HAT variants require the seeed-voicecard kernel driver. Chirp uses HinTak's Pi 5-compatible fork automatically:

```bash
chmod +x install-respeaker-hat.sh
./install-respeaker-hat.sh
sudo reboot   # required
```

> ⚠️ **Pi 5 note**: The original Seeed driver does not support the Pi 5's RP1 I²S controller. The HAT installer uses HinTak's fork which does.

After reboot:
```bash
arecord -l                       # should show seeed-voicecard or ac108
python main.py --list-devices
```

---

## Channel layouts by model

| Model | ALSA channels | Valid mic channels | How Chirp uses it |
|---|---|---|---|
| USB v2.0/v2.1 (1-ch firmware) | 1 | 0 | Direct mono |
| USB v2.0/v2.1 (6-ch firmware, default) | 6 | 0,1,2,3 | Average 4 mic channels → mono |
| 2-Mics HAT (WM8960) | 2 | 0,1 | Average 2 mics → mono |
| 4-Mic Array HAT (AC108) | 4 | 0,1,2,3 | Average 4 mics → mono |
| 4-Mic Linear Array (2×AC108) | 8 | 0,1,2,3 | Average 4 mics → mono (ch4-7 discarded) |
| 6-Mic Circular (2×AC108) | 12 | 0,1,2,3,4,5 | Average 6 mics → mono (ch6-11 discarded) |

---

## LED ring (USB mic array only)

The USB array has a 12-pixel APA102 LED ring. Chirp flashes it green on detection.

```bash
# Test LED colors manually:
python main.py --respeaker-leds 0,200,80    # green
python main.py --respeaker-leds 200,80,0    # amber
python main.py --respeaker-leds 0,0,200     # blue
python main.py --respeaker-leds 0,0,0       # off
```

If LEDs don't respond, add udev rules for USB access:
```bash
sudo tee /etc/udev/rules.d/65-respeaker.rules << 'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="2886", ATTRS{idProduct}=="0018", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="2886", ATTRS{idProduct}=="0019", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="2886", ATTRS{idProduct}=="001b", MODE="0666"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

---

## config.yaml: ReSpeaker settings

```yaml
respeaker:
  mode: auto                          # auto | usb | hat | disabled
  led_on_detection: true              # Flash LED ring on bird detection
  led_color_idle: [0, 0, 0]          # Off when idle
  led_color_detection: [0, 200, 80]  # Green flash on detection
  led_flash_seconds: 3.0
```

`mode: auto` tries USB first, then HAT — works for most setups with no changes.

---

## Recommended external microphones

The ReSpeaker USB array is a strong choice on its own for outdoor bird detection. If you want additional or replacement USB mics, these work well with Chirp:

### Best value
**Primo EM272 capsule** (~$30–50 each) — used by professional passive acoustic monitoring researchers. Lowest self-noise (~14 dB-A) of anything in this price range, excellent high-frequency response for bird calls. Requires a small USB preamp (e.g. Roland CS-10EM or Tascam iM2).

### Plug-and-play USB
| Mic | Price | Notes |
|---|---|---|
| **Blue Snowball iCE** | ~$50 | Omnidirectional, already in Chirp's device hints, widely Pi-compatible |
| **Audio-Technica ATR2100x-USB** | ~$80 | Low noise floor, cardioid — good for fixed directional position |
| **Rode NT-USB Mini** | ~$100 | Excellent preamp quality, "Rode" in device hints, auto-detected |
| **Samson Go Mic** | ~$40 | Compact, omnidirectional option, USB |

### For outdoor mounting
Whatever mic you use outdoors, protect it with a simple rain baffle — a PVC pipe cap with mesh screen keeps water out while allowing 360° sound in. The ReSpeaker's circular enclosure handles light rain well if mounted under an eave. For full exposure, wrap in a windscreen "dead cat" foam cover (available for ~$10 on Amazon).

---

## Troubleshooting

**USB ReSpeaker not detected:**
```bash
lsusb | grep -i "2886\|seeed\|xvf"   # should show the device
python main.py --list-devices          # check sounddevice sees it
```
If lsusb shows it but sounddevice doesn't, add udev rules (see LED section above).

**Audio overflow warnings:**
Increase `chunk_size` in config.yaml:
```yaml
audio:
  chunk_size: 16384   # was 8192
```

**HAT not detected after reboot:**
```bash
dmesg | grep -i "seeed\|ac108\|wm8960" | tail -20
cat /proc/asound/cards
```
If empty, the driver didn't load — re-run `install-respeaker-hat.sh`.
