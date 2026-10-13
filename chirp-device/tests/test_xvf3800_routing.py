"""XVF3800 raw-mic routing: control transfers, channel plans, hot switch."""
import struct
import sys
import types

import numpy as np
import pytest

# Minimal pyusb stand-in so the module can be exercised without hardware.
_usb = types.ModuleType("usb")
_usb_util = types.ModuleType("usb.util")
_usb_util.CTRL_IN, _usb_util.CTRL_OUT = 0x80, 0x00
_usb_util.CTRL_TYPE_VENDOR, _usb_util.CTRL_RECIPIENT_DEVICE = 0x40, 0x00
_usb_core = types.ModuleType("usb.core")
_usb.util, _usb.core = _usb_util, _usb_core
sys.modules.setdefault("usb", _usb)
sys.modules.setdefault("usb.util", _usb_util)
sys.modules.setdefault("usb.core", _usb_core)

from chirp import xvf3800                                   # noqa: E402
from chirp.respeaker import (configure_xvf3800,  # noqa: E402
                             extract_mono, xvf3800_channel_plan, _is_xvf3800)


class FakeChip:
    """Answers vendor control transfers like the XVF3800 servicer."""

    def __init__(self, left=(8, 0), right=(8, 1), retries=1):
        self.regs = {(35, 15): bytes(left), (35, 19): bytes(right)}
        self.retries = retries
        self.writes = []

    def ctrl_transfer(self, req, _r, wvalue, windex, data_or_len, _timeout):
        if req & 0x80:                                       # read
            if self.retries:
                self.retries -= 1
                return np.array([64] + [0] * (data_or_len - 1), dtype=np.uint8)
            payload = self.regs[(windex, wvalue & 0x7F)]
            return np.array([0] + list(payload), dtype=np.uint8)
        self.writes.append((windex, wvalue, bytes(data_or_len)))
        self.regs[(windex, wvalue)] = bytes(data_or_len)
        return len(data_or_len)


@pytest.fixture
def chip(monkeypatch, tmp_path):
    fake = FakeChip()
    monkeypatch.setattr(xvf3800, "_STATE_PATH", str(tmp_path / "routing.json"))
    monkeypatch.setattr(xvf3800.XVF3800, "find", classmethod(lambda cls: cls(fake)))
    return fake


def test_read_retries_then_returns_routing(chip):
    c = xvf3800.XVF3800(chip)
    assert c.routing() == ((8, 0), (8, 1))


def test_raw_then_processed_restores_original(chip):
    assert xvf3800.apply_output_mode("raw") == "raw"
    assert chip.regs[(35, 15)] == bytes((3, 0)) and chip.regs[(35, 19)] == bytes((3, 2))
    n = len(chip.writes)
    assert xvf3800.apply_output_mode("raw") == "raw"           # idempotent, no rewrite
    assert len(chip.writes) == n
    assert xvf3800.apply_output_mode("processed") == "processed"
    assert chip.regs[(35, 15)] == bytes((8, 0)) and chip.regs[(35, 19)] == bytes((8, 1))


def test_unchanged_and_missing_chip(monkeypatch):
    assert xvf3800.apply_output_mode("unchanged") is None
    monkeypatch.setattr(xvf3800.XVF3800, "find", classmethod(lambda cls: None))
    assert xvf3800.apply_output_mode("raw") is None


def test_float_write_encoding(chip):
    c = xvf3800.XVF3800(chip)
    c.write("AUDIO_MGR_MIC_GAIN", [90.0])
    assert chip.writes[-1] == (35, 0, struct.pack("<f", 90.0))


def test_channel_plans():
    assert xvf3800_channel_plan(6, "raw").valid_channels == [2, 3, 4, 5]
    assert xvf3800_channel_plan(6, "processed").valid_channels == [0]
    p = xvf3800_channel_plan(2, "raw")
    assert p.valid_channels == [0, 1] and p.mix_to_mono
    p = xvf3800_channel_plan(2, "processed")
    assert p.valid_channels == [0] and not p.mix_to_mono


def test_processed_plan_does_not_halve_level():
    # R silent (firmware default on some units): averaging L+R would cost 6 dB.
    raw = np.zeros((1000, 2), dtype=np.float32)
    raw[:, 0] = 0.5
    mono = extract_mono(raw, xvf3800_channel_plan(2, "processed"))
    assert np.allclose(mono, 0.5)


def test_configure_mutates_live_plan(chip):
    plan = xvf3800_channel_plan(2, "processed")
    configure_xvf3800(plan, "raw")
    assert plan.valid_channels == [0, 1] and plan.mix_to_mono
    configure_xvf3800(plan, "processed")
    assert plan.valid_channels == [0] and not plan.mix_to_mono


def test_six_channel_raw_needs_no_control_writes(chip):
    plan = xvf3800_channel_plan(6, "processed")
    configure_xvf3800(plan, "raw")
    assert plan.valid_channels == [2, 3, 4, 5]
    assert chip.writes == []


def test_xvf3800_identification():
    assert _is_xvf3800(("2886", "001a", "x"), None)
    assert _is_xvf3800(None, "reSpeaker XVF3800 4-Mic Array: USB Audio (hw:2,0)")
    assert not _is_xvf3800(("2886", "0018", "ReSpeaker USB Mic Array v2.0"), "ReSpeaker 4 Mic Array (UAC1.0)")


def test_coral_load_failure_falls_back_to_cpu(monkeypatch):
    import chirp.birdnet_cpu as cpu
    from chirp.detector import DetectionPipeline

    class BirdNetCoral:
        def load(self):
            return False

    monkeypatch.setattr(cpu.BirdNetCPU, "__init__", lambda self, cfg: None)
    monkeypatch.setattr(cpu.BirdNetCPU, "load", lambda self: True)
    p = DetectionPipeline.__new__(DetectionPipeline)
    p.config, p._birdnet = {}, BirdNetCoral()
    assert p.load_model() is True
    assert p.active_backend == "cpu"


def test_overlap_throttles_under_backlog_and_recovers():
    import queue
    from chirp.audio import AudioCapture
    a = AudioCapture.__new__(AudioCapture)
    a.config = {"detection": {"birdnet": {"overlap_seconds": 2.0}}}
    a._detection_queue = queue.Queue(maxsize=10)
    a._overlap_throttled = False
    a.stats = {}
    assert a._effective_overlap() == 2.0
    for _ in range(5):
        a._detection_queue.put(0)
    assert a._effective_overlap() == 1.0
    for _ in range(3):
        a._detection_queue.get()
    assert a._effective_overlap() == 1.0          # still draining (hysteresis)
    a._detection_queue.get()
    assert a._effective_overlap() == 2.0          # backlog 1 → back to normal
    assert a.stats["overlap_throttle_events"] == 1


def test_device_night_species_floor(monkeypatch):
    import sys, types
    from chirp.birdnet_cpu import BirdNetCPU
    fake = types.ModuleType("birdnetlib")

    class Rec:
        def __init__(self, analyzer, path, **kw):
            Rec.kw = kw
            self.detections = None

        def analyze(self):
            self.detections = [
                {"common_name": "Barred Owl", "label": "Strix varia_Barred Owl", "confidence": 0.15},
                {"common_name": "Blue Jay", "label": "Cyanocitta cristata_Blue Jay", "confidence": 0.15},
                {"common_name": "Greater Yellowlegs", "label": "x_Greater Yellowlegs", "confidence": 0.15},
                {"common_name": "American Crow", "label": "x_American Crow", "confidence": 0.5},
            ]
    fake.Recording = Rec
    monkeypatch.setitem(sys.modules, "birdnetlib", fake)
    b = BirdNetCPU({"detection": {"birdnet": {"min_confidence": 0.30, "species_blacklist": [], "species_whitelist": []}},
                    "audio": {"sample_rate": 48000}})
    b._analyzer, b._ready = object(), True
    names = sorted(d.common_name for d in b.analyze(np.zeros(144000, dtype=np.float32)))
    assert Rec.kw["min_conf"] == 0.10
    assert names == ["American Crow", "Barred Owl"]
