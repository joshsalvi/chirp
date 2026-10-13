"""
Chirp Device — ReSpeaker Support Module
========================================

Supports all common ReSpeaker form factors:

  USB variants (plug-and-play, no driver needed):
    • ReSpeaker USB Mic Array v2.0 / v2.1  — XMOS XVF-3000, 4 mics, UAC 1.0
    • ReSpeaker USB 4-Mic Array XVF3000     — same chip, with case

  HAT variants (GPIO / I²S, requires seeed-voicecard driver):
    • ReSpeaker 2-Mics Pi HAT               — WM8960, 2 mics
    • ReSpeaker 4-Mic Array for Raspberry Pi — AC108, 4 mics
    • ReSpeaker 4-Mic Linear Array Kit       — 2×AC108, 8 channels (4 valid)
    • ReSpeaker 6-Mic Circular Array Kit     — 2×AC108, 12 channels (6 valid)

Detection logic
---------------
1. probe_respeaker() — auto-detects any connected ReSpeaker and returns a
   ReSpeakerDevice descriptor.
2. AudioCapture (audio.py) calls probe_respeaker() in its start() path when
   respeaker.mode != "disabled".
3. For USB variants the descriptor contains the sounddevice index and an
   optimal channel extraction plan.
4. For HAT variants (mode="hat") the descriptor contains the ALSA device name
   ("ac108" or "seeed-voicecard") and the number of valid capture channels.

Channel extraction for BirdNET
-------------------------------
BirdNET expects mono, 48 kHz.  For multi-channel devices we:
  • Mix valid microphone channels down to mono (average).
  • Discard echo-reference / playback-feedback channels.
  • Optionally expose individual channel streams for direction-of-arrival
    display on the OLED (future).

Pi 5 note for HAT variants
---------------------------
The stock seeed-voicecard driver does NOT support the Pi 5's RP1 I²S
controller.  HinTak maintains a forward-ported fork:
    https://github.com/HinTak/seeed-voicecard
install-respeaker-hat.sh uses that fork automatically.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

try:
    import numpy as np
    _NP_OK = True
except ImportError:
    np = None  # type: ignore
    _NP_OK = False

logger = logging.getLogger(__name__)


# ── Enumerations ──────────────────────────────────────────────────────────────

class ReSpeakerMode(str, Enum):
    DISABLED   = "disabled"   # explicitly disabled in config
    USB        = "usb"        # USB UAC mic array (plug-and-play)
    HAT        = "hat"        # I²S HAT via seeed-voicecard driver
    AUTO       = "auto"       # auto-detect (default)


class ReSpeakerModel(str, Enum):
    USB_V2          = "usb_v2"           # Mic Array v2.0 / v2.1 (XVF-3000)
    USB_XVF3800     = "usb_xvf3800"      # USB 4-Mic Array XVF3800
    HAT_2MIC        = "hat_2mic"         # 2-Mics Pi HAT (WM8960)
    HAT_4MIC        = "hat_4mic"         # 4-Mic Array HAT (AC108)
    HAT_4MIC_LINEAR = "hat_4mic_linear"  # 4-Mic Linear Kit (2×AC108, 8ch)
    HAT_6MIC        = "hat_6mic"         # 6-Mic Circular Kit (2×AC108, 12ch)
    UNKNOWN         = "unknown"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ChannelPlan:
    """Describes which raw channels contain valid mic data."""
    total_channels: int          # total channels the device exposes
    valid_channels: List[int]    # 0-based indices of mic channels to keep
    mix_to_mono: bool = True     # average valid channels → mono
    description: str = ""

    @property
    def valid_count(self) -> int:
        return len(self.valid_channels)


@dataclass
class ReSpeakerDevice:
    """Fully-resolved descriptor for a connected ReSpeaker."""
    model: ReSpeakerModel
    mode: ReSpeakerMode
    display_name: str

    # USB-mode fields
    sd_device_index: Optional[int] = None   # sounddevice index
    sd_device_name:  Optional[str] = None

    # HAT-mode fields
    alsa_device: Optional[str] = None       # e.g. "ac108" or "seeed-voicecard"
    alsa_card:   Optional[int] = None       # ALSA card number

    # Common
    channel_plan: ChannelPlan = field(default_factory=lambda: ChannelPlan(1, [0]))
    sample_rate:  int = 16000
    has_leds:     bool = False
    has_doa:      bool = False    # Direction-of-Arrival chip present
    has_vad:      bool = False    # Hardware VAD flag

    def __str__(self) -> str:
        if self.mode == ReSpeakerMode.USB:
            return (f"{self.display_name} (USB, sd_index={self.sd_device_index}, "
                    f"{self.channel_plan.valid_count} mic ch)")
        else:
            return (f"{self.display_name} (HAT, alsa={self.alsa_device}, "
                    f"{self.channel_plan.valid_count} mic ch)")


# ── Known USB VID:PID pairs ───────────────────────────────────────────────────

# XMOS XVF-3000 shows two USB IDs depending on firmware loaded
_USB_IDS: List[Tuple[str, str, str]] = [
    # Seeed Studio / ReSpeaker VID 0x2886
    ("2886", "0018", "ReSpeaker USB Mic Array v2.0"),
    ("2886", "0019", "ReSpeaker USB Mic Array v2.1"),
    ("2886", "001a", "ReSpeaker USB 4-Mic Array XVF3800"),   # PID the XVF3800 USB firmware reports
    ("2886", "001b", "ReSpeaker USB 4-Mic Array XVF3800"),
    ("2886", "002a", "ReSpeaker USB Mic Array"),   # some units report this PID
    ("2886", "0039", "ReSpeaker USB Mic Array"),   # newer batch variant
    # XMOS VID 0x20B1 — XVF-3000 and XVF-3800 chips
    ("20b1", "0008", "XMOS XVF-3000"),
    ("20b1", "0014", "XMOS XVF-3800"),
    ("20b1", "f7d1", "XMOS USB Audio (ReSpeaker)"),
    # Global Unichip / older firmware DFU mode
    ("04b4", "0008", "ReSpeaker (Cypress DFU)"),
]

# Substrings that identify a ReSpeaker in the sounddevice / ALSA device name.
# Deliberately broad — the Linux driver can name the device many ways.
_SD_NAME_HINTS = [
    "respeaker", "ReSpeaker",
    "seeed", "Seeed",
    "xvf", "XVF",
    "xmos", "XMOS",
    "2886",           # vendor ID sometimes appears in ALSA name
    "20b1",
    "mic array", "Mic Array", "mic_array",
    "4-mic", "4 mic",
    "voicecard",
    "ac108",
]

# ALSA card name substrings for HAT variants
_ALSA_HAT_NAMES = [
    "seeed",
    "ac108",
    "wm8960",
    "voicecard",
]


# ── USB detection helpers ──────────────────────────────────────────────────────

def _lsusb_respeaker() -> Optional[Tuple[str, str, str]]:
    """
    Run lsusb and look for a known ReSpeaker VID:PID.
    Returns (vid, pid, description) or None.
    """
    try:
        out = subprocess.check_output(["lsusb"], stderr=subprocess.DEVNULL,
                                       timeout=5).decode()
    except Exception:
        return None
    for line in out.splitlines():
        for vid, pid, desc in _USB_IDS:
            if f"{vid}:{pid}".lower() in line.lower():
                return vid, pid, desc
    return None


def _find_sd_respeaker() -> Optional[Tuple[int, str]]:
    """
    Scan sounddevice list for any device whose name looks like a ReSpeaker.
    Returns (index, name) or None.
    Case-insensitive; also matches partial strings.
    """
    try:
        import sounddevice as sd
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] < 1:
                continue
            name_lower = dev["name"].lower()
            if any(h.lower() in name_lower for h in _SD_NAME_HINTS):
                return i, dev["name"]
    except Exception as e:
        logger.debug("sounddevice probe failed: %s", e)
    return None


def _sd_channels_for_index(index: int) -> int:
    try:
        import sounddevice as sd
        return sd.query_devices(index)["max_input_channels"]
    except Exception:
        return 1


def _usb_channel_plan(total_ch: int) -> ChannelPlan:
    """
    Map USB ReSpeaker v2.0 channel layout:
      1-ch firmware → 1 channel  (processed/beamformed output)
      6-ch firmware → 6 channels (ch0-3 = raw mics, ch4-5 = echo ref)
    Firmware selection depends on which .bin was flashed to the device.
    Most users have the default 6-ch firmware, which is what you want here:
    raw per-capsule channels averaged to mono, bypassing the chip's onboard
    beamforming/voice-isolation DSP entirely. That DSP is built to isolate
    a voice from one direction and suppress everything else — the opposite
    of what's wanted for catching bird calls from any direction around the
    device (this is also the BirdNET-Pi community's consistent recommendation:
    https://github.com/mcguirepr89/BirdNET-Pi/discussions/39). If you've
    flashed the 1-ch firmware, its single output channel IS that beamformed
    signal — it'll work, but a raw omnidirectional capture (6-ch firmware,
    or a dedicated omnidirectional mic per the README) should perform better.
    """
    if total_ch == 1:
        return ChannelPlan(
            total_channels=1,
            valid_channels=[0],
            mix_to_mono=False,
            description="1-ch beamformed output (single-channel firmware — "
                        "consider 6-ch firmware or an omnidirectional mic instead)"
        )
    elif total_ch <= 2:
        return ChannelPlan(
            total_channels=total_ch,
            valid_channels=list(range(total_ch)),
            mix_to_mono=True,
            description=f"{total_ch}-ch, all mic"
        )
    elif total_ch == 6:
        # 6-ch default firmware: ch0-3 = mic, ch4-5 = echo reference
        return ChannelPlan(
            total_channels=6,
            valid_channels=[0, 1, 2, 3],
            mix_to_mono=True,
            description="6-ch firmware: ch0-3=mic, ch4-5=echo (discarded)"
        )
    else:
        # Unknown layout — use all channels
        return ChannelPlan(
            total_channels=total_ch,
            valid_channels=list(range(total_ch)),
            mix_to_mono=True,
            description=f"{total_ch}-ch (all used)"
        )


def _is_xvf3800(usb_match, sd_name: Optional[str]) -> bool:
    if usb_match and ("3800" in usb_match[2] or (usb_match[0], usb_match[1]) in
                      (("2886", "001a"), ("2886", "001b"), ("20b1", "0014"))):
        return True
    return bool(sd_name and "3800" in sd_name)


def xvf3800_channel_plan(total_ch: int, mode: str) -> ChannelPlan:
    """Channel plan for the XVF3800 USB array.

    2-ch firmware: L/R are whatever the chip's output mux routes there. In
      "raw" mode (see xvf3800.apply_output_mode) that's mic 0 and mic 2, so
      both are averaged; otherwise only L (the processed beam) is used —
      R is the ASR beam or silence, and averaging it in costs up to 6 dB.
    6-ch firmware: ch0-1 = routed stereo, ch2-5 = the four raw capsules.
    """
    raw = (mode == "raw")
    if total_ch >= 6:
        if raw:
            return ChannelPlan(total_ch, [2, 3, 4, 5], True,
                               "XVF3800 6-ch: raw capsules ch2-5 averaged")
        return ChannelPlan(total_ch, [0], False, "XVF3800 6-ch: processed beam (ch0)")
    if total_ch == 2 and raw:
        return ChannelPlan(2, [0, 1], True, "XVF3800: raw capsules mic0+mic2 averaged")
    return ChannelPlan(total_ch, [0], False,
                       "XVF3800: processed beam (L only)" if total_ch > 1 else "XVF3800: 1-ch output")


def configure_xvf3800(plan: ChannelPlan, mode: str) -> str:
    """Apply respeaker.xvf3800_output to the chip and update `plan` in place
    (safe on a running stream). Returns the plan description."""
    mode = (mode or "raw").lower()
    total = plan.total_channels
    effective = "processed"
    if total >= 6:
        effective = "raw" if mode == "raw" else "processed"
    elif total == 2:
        from .xvf3800 import apply_output_mode
        effective = apply_output_mode(mode) or "processed"
    new = xvf3800_channel_plan(total, effective)
    plan.mix_to_mono = new.mix_to_mono
    plan.valid_channels = new.valid_channels
    plan.description = new.description
    return new.description


# ── ALSA / HAT detection helpers ──────────────────────────────────────────────

def _list_alsa_cards() -> List[Tuple[int, str]]:
    """Return [(card_num, card_name), ...] from /proc/asound/cards."""
    cards = []
    try:
        with open("/proc/asound/cards") as f:
            content = f.read()
        for line in content.splitlines():
            m = re.match(r"\s*(\d+)\s+\[.*?\]:\s+(.+)", line)
            if m:
                cards.append((int(m.group(1)), m.group(2).strip()))
    except FileNotFoundError:
        pass
    return cards


def _find_alsa_respeaker() -> Optional[Tuple[int, str, str]]:
    """
    Scan ALSA cards for a seeed-voicecard / ac108 / wm8960 device.
    Returns (card_num, alsa_name, display_name) or None.
    """
    for card_num, card_name in _list_alsa_cards():
        for hint in _ALSA_HAT_NAMES:
            if hint.lower() in card_name.lower():
                return card_num, hint, card_name
    return None


def _hat_channel_plan(alsa_name: str, total_ch: int) -> Tuple[ChannelPlan, ReSpeakerModel]:
    """
    Map known HAT ALSA channel layouts to a ChannelPlan.
    Returns (plan, model).
    """
    name_lower = alsa_name.lower()
    if "wm8960" in name_lower:
        # 2-Mic HAT: 2 real mic channels
        return (
            ChannelPlan(total_channels=2, valid_channels=[0, 1], mix_to_mono=True,
                        description="2-Mic HAT: ch0+ch1=mic"),
            ReSpeakerModel.HAT_2MIC,
        )
    elif total_ch >= 12:
        # 6-Mic Circular: 2×AC108 = 12ch, first 6 are mics
        return (
            ChannelPlan(total_channels=12, valid_channels=[0,1,2,3,4,5], mix_to_mono=True,
                        description="6-Mic Circular: ch0-5=mic, ch6-11=echo/dummy"),
            ReSpeakerModel.HAT_6MIC,
        )
    elif total_ch >= 8:
        # 4-Mic Linear: 2×AC108 = 8ch, first 4 are mics
        return (
            ChannelPlan(total_channels=8, valid_channels=[0,1,2,3], mix_to_mono=True,
                        description="4-Mic Linear: ch0-3=mic, ch4-7=echo/dummy"),
            ReSpeakerModel.HAT_4MIC_LINEAR,
        )
    elif total_ch >= 4:
        # 4-Mic Array HAT: 4ch, all mic (single AC108)
        return (
            ChannelPlan(total_channels=4, valid_channels=[0,1,2,3], mix_to_mono=True,
                        description="4-Mic HAT: ch0-3=mic"),
            ReSpeakerModel.HAT_4MIC,
        )
    else:
        return (
            ChannelPlan(total_channels=total_ch, valid_channels=list(range(total_ch)),
                        mix_to_mono=True, description=f"HAT {total_ch}ch"),
            ReSpeakerModel.UNKNOWN,
        )


def _alsa_channels_for_card(card_num: int, alsa_device_name: str) -> int:
    """Query number of capture channels from ALSA for a card."""
    try:
        out = subprocess.check_output(
            ["arecord", f"-Dhw:{card_num}", "--dump-hw-params"],
            stderr=subprocess.STDOUT, timeout=5
        ).decode()
        # look for "CHANNELS: min=N max=M" or "channels: N"
        m = re.search(r"(?:CHANNELS|channels).*?(\d+)", out, re.IGNORECASE)
        if m:
            return int(m.group(1))
    except Exception as e:
        logger.debug("arecord channel probe failed for card %d: %s", card_num, e)
    # Fallback: sounddevice
    try:
        import sounddevice as sd
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0 and str(card_num) in dev.get("name", ""):
                return dev["max_input_channels"]
    except Exception:
        pass
    return 4  # safe default for AC108


# ── Public API ────────────────────────────────────────────────────────────────

def probe_respeaker(mode: str = "auto") -> Optional[ReSpeakerDevice]:
    """
    Auto-detect any connected ReSpeaker device.

    Parameters
    ----------
    mode : str
        "auto"     — try USB first, then HAT
        "usb"      — only check USB
        "hat"      — only check HAT / ALSA
        "disabled" — skip all probing, return None

    Returns
    -------
    ReSpeakerDevice if found, else None.
    """
    m = mode.lower()
    if m == ReSpeakerMode.DISABLED:
        logger.debug("ReSpeaker probe skipped (mode=disabled)")
        return None

    if m in (ReSpeakerMode.USB, ReSpeakerMode.AUTO):
        dev = _probe_usb()
        if dev:
            logger.info("ReSpeaker detected (USB): %s", dev)
            return dev

    if m in (ReSpeakerMode.HAT, ReSpeakerMode.AUTO):
        dev = _probe_hat()
        if dev:
            logger.info("ReSpeaker detected (HAT): %s", dev)
            return dev

    if m == ReSpeakerMode.AUTO:
        logger.debug("No ReSpeaker detected (auto probe found nothing)")
    else:
        logger.debug("No ReSpeaker found with mode=%s", mode)

    return None


def _probe_usb() -> Optional[ReSpeakerDevice]:
    """Try to find a USB ReSpeaker via lsusb and sounddevice."""
    # 1. Check lsusb for known VID:PID
    usb_match = _lsusb_respeaker()

    # 2. Find the sounddevice entry (may exist even without lsusb match on some systems)
    sd_match = _find_sd_respeaker()

    if usb_match is None and sd_match is None:
        return None

    display_name = (usb_match[2] if usb_match else "ReSpeaker USB (unknown model)")
    sd_idx, sd_name = sd_match if sd_match else (None, None)

    if sd_idx is None:
        # VID:PID match but not in sounddevice — device may need firmware init
        logger.warning(
            "ReSpeaker USB found via lsusb (%s) but not visible to sounddevice. "
            "Try: sudo python3 -c \"import usb.core\" or check udev rules.",
            usb_match[2] if usb_match else "unknown"
        )
        return None

    total_ch = _sd_channels_for_index(sd_idx)
    is_xvf3800 = _is_xvf3800(usb_match, sd_name)
    plan = _usb_channel_plan(total_ch) if not is_xvf3800 else xvf3800_channel_plan(total_ch, "processed")

    logger.info(
        "ReSpeaker USB: %s | sd_index=%d | %d total ch → plan: %s",
        display_name, sd_idx, total_ch, plan.description
    )

    return ReSpeakerDevice(
        model        = ReSpeakerModel.USB_XVF3800 if is_xvf3800 else ReSpeakerModel.USB_V2,
        mode         = ReSpeakerMode.USB,
        display_name = display_name,
        sd_device_index = sd_idx,
        sd_device_name  = sd_name,
        channel_plan = plan,
        sample_rate  = 16000,   # XVF-3000 native rate
        has_leds     = True,
        has_doa      = True,
        has_vad      = True,
    )


def _probe_hat() -> Optional[ReSpeakerDevice]:
    """Try to find a ReSpeaker HAT via ALSA card enumeration."""
    alsa_match = _find_alsa_respeaker()
    if alsa_match is None:
        return None

    card_num, alsa_name, full_name = alsa_match
    total_ch = _alsa_channels_for_card(card_num, alsa_name)
    plan, model = _hat_channel_plan(full_name, total_ch)

    _model_display = {
        ReSpeakerModel.HAT_2MIC:        "ReSpeaker 2-Mics Pi HAT",
        ReSpeakerModel.HAT_4MIC:        "ReSpeaker 4-Mic Array HAT",
        ReSpeakerModel.HAT_4MIC_LINEAR: "ReSpeaker 4-Mic Linear Array",
        ReSpeakerModel.HAT_6MIC:        "ReSpeaker 6-Mic Circular Array",
    }
    display_name = _model_display.get(model, f"ReSpeaker HAT ({full_name})")

    logger.info(
        "ReSpeaker HAT: %s | alsa_card=%d | %d total ch → plan: %s",
        display_name, card_num, total_ch, plan.description
    )

    return ReSpeakerDevice(
        model        = model,
        mode         = ReSpeakerMode.HAT,
        display_name = display_name,
        alsa_device  = alsa_name,
        alsa_card    = card_num,
        channel_plan = plan,
        sample_rate  = 16000,
        has_leds     = model != ReSpeakerModel.HAT_2MIC,
        has_doa      = model != ReSpeakerModel.HAT_2MIC,
        has_vad      = False,
    )


# ── Audio extraction helper used by AudioCapture ─────────────────────────────

def extract_mono(raw: "np.ndarray", plan: ChannelPlan) -> "np.ndarray":
    """
    Given a raw multi-channel numpy array (shape: [frames, total_channels]
    or [frames] for mono), return a mono float32 array using plan.valid_channels.

    This is called inside the sounddevice callback so must be fast.
    """
    import numpy as np
    if raw.ndim == 1 or plan.total_channels == 1:
        return raw.reshape(-1).astype(np.float32)
    if not plan.mix_to_mono:
        ch = plan.valid_channels[0]
        return raw[:, ch].astype(np.float32)
    # Average valid channels
    valid = [raw[:, c] for c in plan.valid_channels if c < raw.shape[1]]
    if not valid:
        return raw[:, 0].astype(np.float32)
    return np.mean(np.stack(valid, axis=1), axis=1).astype(np.float32)


# ── LED helpers (USB mic array only) ─────────────────────────────────────────

def set_led_color_usb(color: Tuple[int,int,int], brightness: int = 32) -> bool:
    """
    Set all LED pixels on the USB ReSpeaker v2.0 ring to a solid color.
    color = (R, G, B), brightness = 0-255.
    Returns True on success, False if pyusb / usb not available.
    """
    try:
        import usb.core
        dev = usb.core.find(idVendor=0x2886, idProduct=0x0018)
        if dev is None:
            dev = usb.core.find(idVendor=0x2886, idProduct=0x0019)
        if dev is None:
            return False
        r, g, b = color
        # CTRL_LEDS command: set all 12 APA102 pixels
        pixel = bytes([0x00, r, g, b, brightness] * 12)
        dev.ctrl_transfer(0x40, 0x03, 0, 0, (0x1C,) + tuple(pixel))
        return True
    except Exception as e:
        logger.debug("LED set failed: %s", e)
        return False


def led_detection_flash(color: Tuple[int,int,int] = (0, 200, 80),
                         duration_secs: float = 2.0) -> None:
    """
    Flash the USB mic array LEDs for duration_secs to indicate a detection.
    Runs in a background thread so it never blocks the audio pipeline.
    """
    import threading
    import time
    def _flash():
        set_led_color_usb(color, brightness=64)
        time.sleep(duration_secs)
        set_led_color_usb((0, 0, 0), brightness=0)
    t = threading.Thread(target=_flash, daemon=True, name="RespeakerLED")
    t.start()


# ── Diagnostic / info ─────────────────────────────────────────────────────────

def respeaker_info() -> str:
    """Return a human-readable summary of detected ReSpeaker hardware."""
    lines = ["=== ReSpeaker Probe ==="]

    # Raw lsusb output — always show, even if not a known VID:PID
    try:
        import subprocess
        lsusb_out = subprocess.check_output(["lsusb"], stderr=subprocess.DEVNULL,
                                             timeout=5).decode().strip()
        lines.append("")
        lines.append("lsusb output:")
        for line in lsusb_out.splitlines():
            marker = "  ★ " if any(vid in line.lower() for vid in
                                    ["2886", "20b1", "seeed", "xvf", "respeaker", "xmos"]) \
                    else "    "
            lines.append(f"{marker}{line}")
    except Exception as e:
        lines.append(f"  lsusb failed: {e}")

    lines.append("")
    usb_match = _lsusb_respeaker()
    lines.append(f"  Known VID:PID match : {usb_match}")

    sd_match = None
    try:
        sd_match = _find_sd_respeaker()
    except Exception as e:
        lines.append(f"  sounddevice probe   : failed ({e})")

    lines.append(f"  sounddevice match   : {sd_match}")

    # Show all sounddevice input devices for diagnosis
    try:
        import sounddevice as sd
        lines.append("")
        lines.append("  All input devices (sounddevice):")
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                lines.append(f"    [{i:2d}] {dev['name']:<50} ch={dev['max_input_channels']} "
                              f"rate={dev['default_samplerate']:.0f}")
    except Exception as e:
        lines.append(f"  sounddevice device list failed: {e}")

    alsa_match = _find_alsa_respeaker()
    lines.append(f"\n  ALSA card match     : {alsa_match}")

    lines.append("")
    dev = probe_respeaker("auto")
    if dev:
        lines.append(f"  ✓ Resolved device   : {dev}")
        lines.append(f"  Channel plan        : {dev.channel_plan.description}")
        lines.append(f"  Has LEDs            : {dev.has_leds}")
        lines.append(f"  Has DoA             : {dev.has_doa}")
    else:
        lines.append("  ✗ No ReSpeaker detected")
        lines.append("")
        lines.append("  Tip: If your device shows in lsusb but not sounddevice,")
        lines.append("  try: sudo usermod -aG audio $USER  then log out and back in")
        lines.append("  Also check: arecord -l")

    return "\n".join(lines)
