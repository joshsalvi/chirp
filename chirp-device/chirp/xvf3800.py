"""
ReSpeaker XVF3800 output routing (raw capsules vs. processed beam).

The XVF3800's USB stereo output is, by default, the chip's voice pipeline:
AEC, beamforming, noise suppression and AGC tuned for speech. That pipeline
treats steady, low, distant sounds (owl hoots, dove coos) as noise. This
module re-routes the two USB channels to the amplified raw capsules instead,
using the vendor control protocol over pyusb (same transfers as Seeed's
python_control/xvf_host.py), so no extra binary is needed.

Output modes (config: respeaker.xvf3800_output):
  raw        L = mic 0, R = mic 2 (opposite capsules, category 3 "amplified
             mic data"); the channel plan averages both.
  processed  Firmware voice output (L = auto-select beam). Only L is used.
  unchanged  Don't touch the chip; channel plan uses L only.

6-channel firmware (respeaker_xvf3800_usb_dfu_firmware_6chl_*) already
carries the four raw capsules on USB channels 3-6, so "raw" there needs no
control writes: the channel plan just averages those four.

Routing writes are volatile (not saved to flash), so unplugging the array or
rebooting it restores the firmware default. Chirp re-applies on every start
and on a config push.

CLI (on the Pi):
  python -m chirp.xvf3800 status
  python -m chirp.xvf3800 raw | processed
"""

from __future__ import annotations

import json
import logging
import os
import struct
import sys
import time
from typing import Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

VID = 0x2886
PIDS = (0x001A, 0x001B)          # 0x001A is what the XVF3800 USB firmware reports

# name: (resid, cmdid, count, type)
_PARAMS = {
    "VERSION":            (48, 0, 3, "uint8"),
    "AUDIO_MGR_MIC_GAIN": (35, 0, 1, "float"),
    "AUDIO_MGR_OP_L":     (35, 15, 2, "uint8"),
    "AUDIO_MGR_OP_R":     (35, 19, 2, "uint8"),
    "AEC_HPFONOFF":       (33, 1, 1, "int32"),
    "PP_AGCONOFF":        (17, 10, 1, "int32"),
}

# (category, source) pairs
RAW_L = (3, 0)                   # amplified mic 0
RAW_R = (3, 2)                   # amplified mic 2 (opposite side of the ring)
FIRMWARE_DEFAULT_L = (8, 0)      # "user chosen" = copy of the auto-select beam
FIRMWARE_DEFAULT_R = (8, 1)
_RAW_CATEGORIES = (1, 3, 11)     # raw / amplified mic categories

VALID_MODES = ("raw", "processed", "unchanged")

_STATE_PATH = os.path.expanduser("~/.chirp/xvf3800_routing.json")

_CONTROL_SUCCESS = 0
_SERVICER_RETRY = 64
_TIMEOUT_MS = 2000


class XVF3800Error(RuntimeError):
    pass


class XVF3800:
    """Minimal vendor-control client for the XVF3800 over USB."""

    def __init__(self, dev):
        self.dev = dev

    @classmethod
    def find(cls) -> Optional["XVF3800"]:
        try:
            import usb.core
        except ImportError:
            logger.debug("pyusb not installed; XVF3800 control unavailable")
            return None
        for pid in PIDS:
            try:
                dev = usb.core.find(idVendor=VID, idProduct=pid)
            except Exception as e:           # backend missing, permissions
                logger.debug("usb.core.find failed: %s", e)
                return None
            if dev is not None:
                return cls(dev)
        return None

    def read(self, name: str) -> Tuple:
        import usb.util
        resid, cmdid, count, typ = _PARAMS[name]
        width = 1 if typ == "uint8" else 4
        length = count * width + 1
        req = usb.util.CTRL_IN | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE
        for _ in range(100):
            resp = self.dev.ctrl_transfer(req, 0, 0x80 | cmdid, resid, length, _TIMEOUT_MS)
            status = resp[0]
            if status == _CONTROL_SUCCESS:
                payload = bytes(resp[1:])
                fmt = {"uint8": "B", "float": "f", "int32": "i"}[typ]
                return struct.unpack("<" + fmt * count, payload[: count * width])
            if status != _SERVICER_RETRY:
                raise XVF3800Error(f"{name}: status {status}")
            time.sleep(0.01)
        raise XVF3800Error(f"{name}: device kept asking to retry")

    def write(self, name: str, values: Sequence) -> None:
        import usb.util
        resid, cmdid, count, typ = _PARAMS[name]
        if len(values) != count:
            raise ValueError(f"{name} takes {count} value(s)")
        fmt = {"uint8": "B", "float": "f", "int32": "i"}[typ]
        payload = struct.pack("<" + fmt * count, *values)
        req = usb.util.CTRL_OUT | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE
        self.dev.ctrl_transfer(req, 0, cmdid, resid, payload, _TIMEOUT_MS)

    def routing(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        return tuple(self.read("AUDIO_MGR_OP_L")), tuple(self.read("AUDIO_MGR_OP_R"))

    def set_routing(self, left: Tuple[int, int], right: Tuple[int, int]) -> None:
        self.write("AUDIO_MGR_OP_L", left)
        self.write("AUDIO_MGR_OP_R", right)


def _load_saved() -> Optional[dict]:
    try:
        with open(_STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def _save(left, right) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w") as f:
            json.dump({"left": list(left), "right": list(right)}, f)
    except OSError as e:
        logger.debug("Could not save XVF3800 routing snapshot: %s", e)


def apply_output_mode(mode: str) -> Optional[str]:
    """Route the 2-channel USB output for `mode`. Returns the mode now in
    effect ("raw" / "processed"), or None if the chip couldn't be reached
    (the caller then keeps the plan that reads L only)."""
    mode = (mode or "unchanged").lower()
    if mode not in VALID_MODES:
        logger.warning("respeaker.xvf3800_output=%r not recognised; leaving the chip alone", mode)
        return None
    if mode == "unchanged":
        return None
    chip = XVF3800.find()
    if chip is None:
        logger.warning(
            "XVF3800 output '%s' requested but the chip's control interface isn't reachable "
            "(pyusb missing or no udev rule for 2886:001a — rerun install.sh). Using the "
            "processed left channel.", mode)
        return None
    try:
        left, right = chip.routing()
        if mode == "raw":
            if (left, right) != (RAW_L, RAW_R):
                _save(left, right)          # remember what "processed" looked like
                chip.set_routing(RAW_L, RAW_R)
            logger.info("XVF3800 output → raw capsules (L=mic0, R=mic2); was L=%s R=%s", left, right)
            return "raw"
        saved = _load_saved()
        tgt_l = tuple(saved["left"]) if saved else FIRMWARE_DEFAULT_L
        tgt_r = tuple(saved["right"]) if saved else FIRMWARE_DEFAULT_R
        if left[0] in _RAW_CATEGORIES:
            chip.set_routing(tgt_l, tgt_r)
            left, right = tgt_l, tgt_r
        logger.info("XVF3800 output → processed (L=%s R=%s)", left, right)
        return "processed"
    except Exception as e:
        logger.warning("XVF3800 routing change failed: %s", e)
        return None


def status() -> dict:
    chip = XVF3800.find()
    if chip is None:
        return {"found": False}
    out = {"found": True}
    for name in ("VERSION", "AUDIO_MGR_OP_L", "AUDIO_MGR_OP_R", "AUDIO_MGR_MIC_GAIN",
                 "AEC_HPFONOFF", "PP_AGCONOFF"):
        try:
            v = chip.read(name)
            out[name] = list(v) if len(v) > 1 else v[0]
        except Exception as e:
            out[name] = f"error: {e}"
    l = out.get("AUDIO_MGR_OP_L")
    out["mode"] = ("raw" if isinstance(l, list) and l[0] in _RAW_CATEGORIES
                   else "processed" if isinstance(l, list) else "unknown")
    return out


def _main(argv) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0
    if cmd in ("raw", "processed"):
        return 0 if apply_output_mode(cmd) == cmd else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
