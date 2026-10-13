#!/usr/bin/env python3
"""
test_mic_noise.py — standalone AudioMoth noise check.

Run this directly on the Pi with the fan on, then again with it off (or
disconnected), and compare the printed summaries. Records a short clip
straight from the AudioMoth (bypassing the rest of Chirp entirely) and
prints whether there's a persistent low-frequency tone, whether it's a
fixed frequency or wobbling, and roughly how strong it is relative to
the noise floor.

Usage:
    python3 test_mic_noise.py [--seconds 5] [--label fan-on]

Requires nothing beyond what chirp-device already has installed
(sounddevice, numpy, scipy) — run it from the same venv:
    /home/joshsalvi/chirp-device/venv/bin/python test_mic_noise.py --label fan-on
"""

import argparse
import sys
import numpy as np
import sounddevice as sd
from scipy import signal
from scipy.io import wavfile


def find_audiomoth_device():
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0 and "audiomoth" in d["name"].lower():
            return i, d
    return None, None


def analyze(data, sr):
    data = data.astype(np.float64)
    peak = np.max(np.abs(data))
    if peak > 0:
        data = data / peak

    # Track the dominant frequency in the low band (500Hz-5kHz) over time —
    # this is where fan/electrical noise typically sits, well below real
    # bat calls (15-120kHz).
    f, t, Sxx = signal.spectrogram(data, sr, nperseg=2048, noverlap=1536)
    low_mask = (f > 300) & (f < 5000)
    low_power = Sxx[low_mask, :]
    low_freqs = f[low_mask]

    # Overall level in this band vs. the noise floor elsewhere, in dB
    low_db = 10 * np.log10(np.mean(low_power) + 1e-15)
    rest_mask = ~low_mask & (f > 100)
    rest_db = 10 * np.log10(np.mean(Sxx[rest_mask, :]) + 1e-15)

    peak_freq_per_time = low_freqs[np.argmax(low_power, axis=0)]
    tone_present = (low_db - rest_db) > 6  # at least 6dB above the general floor

    return {
        "low_band_db": low_db,
        "rest_db": rest_db,
        "delta_db": low_db - rest_db,
        "tone_present": tone_present,
        "freq_min": float(peak_freq_per_time.min()),
        "freq_max": float(peak_freq_per_time.max()),
        "freq_mean": float(peak_freq_per_time.mean()),
        "freq_std": float(peak_freq_per_time.std()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--label", type=str, default="test")
    args = parser.parse_args()

    idx, dev = find_audiomoth_device()
    if idx is None:
        print("Could not find an AudioMoth input device. Available devices:")
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                print(f"  [{i}] {d['name']} ({d['max_input_channels']}ch)")
        sys.exit(1)

    sr = int(dev["default_samplerate"])
    print(f"Recording {args.seconds}s from '{dev['name']}' at {sr}Hz...")
    audio = sd.rec(int(args.seconds * sr), samplerate=sr, channels=1, device=idx, dtype="float32")
    sd.wait()
    audio = audio.flatten()

    out_path = f"mic_noise_test_{args.label}.wav"
    wavfile.write(out_path, sr, audio)
    print(f"Saved: {out_path}\n")

    result = analyze(audio, sr)

    print("=" * 50)
    print(f"RESULTS — {args.label}")
    print("=" * 50)
    print(f"Low-band (300Hz-5kHz) level:  {result['low_band_db']:.1f} dB")
    print(f"Rest-of-spectrum level:       {result['rest_db']:.1f} dB")
    print(f"Difference:                  {result['delta_db']:+.1f} dB")
    print()
    if result["tone_present"]:
        print("⚠️  Persistent low-frequency tone DETECTED")
        print(f"   Frequency range: {result['freq_min']:.0f}Hz - {result['freq_max']:.0f}Hz")
        print(f"   Mean: {result['freq_mean']:.0f}Hz, wobble (std dev): {result['freq_std']:.0f}Hz")
        if result["freq_std"] > 50:
            print("   -> Frequency is WOBBLING, not fixed (consistent with a fan/mechanical source)")
        else:
            print("   -> Frequency is relatively STABLE (more consistent with electrical/EMI)")
    else:
        print("✅ No significant low-frequency tone detected — clean")
    print("=" * 50)
    print()
    print(f"Share {out_path} back along with this output if you want it looked at further.")


if __name__ == "__main__":
    main()
