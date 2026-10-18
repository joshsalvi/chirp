"""Spectrogram pitch spacing: mel for owls and other low callers (auto), or as asked."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_low_pitch_view_choice():
    from types import SimpleNamespace as NS
    from app.api.recordings import _low_pitch_view, _low_suffix
    owl = NS(detections=[NS(common_name="Barred Owl"), NS(common_name="Blue Jay")])
    jay = NS(detections=[NS(common_name="Blue Jay")])
    assert _low_pitch_view(owl, "auto") and not _low_pitch_view(jay, "auto")
    assert _low_pitch_view(jay, "mel") and not _low_pitch_view(owl, "linear")
    assert _low_suffix("/x/a_spectrogram_0.png", True) == "/x/a_spectrogram_0_low.png"
    assert _low_suffix("/x/a.png", False) == "/x/a.png"


def test_low_pitch_spectrogram_file(tmp_path):
    import numpy as np
    import soundfile as sf
    from app.services.audio_processor import AudioProcessor
    sr = 22050
    t = np.arange(sr * 2) / sr
    wav = tmp_path / "owl.wav"
    sf.write(str(wav), (0.3 * np.sin(2 * np.pi * 400 * t)).astype("float32"), sr)
    p = AudioProcessor().generate_spectrogram(str(wav), str(tmp_path), "rec1", conf_key="0_low", low_pitch=True)
    assert p.endswith("rec1_spectrogram_0_low.png") and os.path.getsize(p) > 1000
