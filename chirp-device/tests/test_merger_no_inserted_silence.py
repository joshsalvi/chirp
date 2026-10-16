"""1.4.1: the audio merger never inserts silence when a mic's chunk takes
longer than the old 0.15 s wait (8192 samples at 48 kHz = 0.17 s)."""
import os
import queue
import sys
import threading
import time
from collections import deque
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chirp.audio import AudioCapture, PreRollBuffer  # noqa: E402

SR, CHUNK = 48000, 8192


def _capture(n_streams):
    a = AudioCapture.__new__(AudioCapture)
    a._running = threading.Event(); a._running.set()
    a._streams = [SimpleNamespace(queue=queue.Queue(), device=SimpleNamespace(index=i)) for i in range(n_streams)]
    a._raw_lock = threading.Lock()
    a._raw_buffers = {i: deque(maxlen=1000) for i in range(n_streams)}
    a._pre_roll = PreRollBuffer(30, SR, CHUNK)
    a.night_sink = None
    a._detection_source = "primary"
    a._detect_lock = threading.Lock(); a._detection_lock = threading.Lock()
    a._detect_accumulator = np.zeros(0, np.float32)
    a.analysis_window_samples = SR * 3
    a._effective_overlap = lambda: 0.0
    a.sample_rate = SR
    a._detection_queue = queue.Queue(maxsize=100)
    a.stats = {"chunks_merged": 0, "detection_windows_queued": 0}
    return a


def _feed(a, n_chunks, period):
    for k in range(n_chunks):
        for st in a._streams:
            st.queue.put((0, np.full(CHUNK, 0.1 + 0.01 * k, np.float32)))
        time.sleep(period)


def test_slow_chunks_add_no_zeros():
    a = _capture(2)
    fed = []
    a.night_sink = fed.append
    t = threading.Thread(target=a._merger_loop, daemon=True); t.start()
    _feed(a, 8, 0.17)          # real cadence of 8192-sample chunks at 48 kHz
    time.sleep(0.3)
    a._running.clear(); t.join(timeout=3)
    audio = np.concatenate(fed)
    assert len(fed) == 8, len(fed)                       # one mix per primary chunk, no extras
    assert not np.any(audio == 0)                       # no inserted silence
    assert sum(len(x) for x in a._raw_buffers[1]) == 8 * CHUNK


def test_secondary_falling_behind_is_left_out_not_zeroed():
    a = _capture(2)
    fed = []
    a.night_sink = fed.append
    t = threading.Thread(target=a._merger_loop, daemon=True); t.start()
    for k in range(4):
        a._streams[0].queue.put((0, np.full(CHUNK, 0.2, np.float32)))
        if k % 2 == 0:
            a._streams[1].queue.put((0, np.full(CHUNK - 100, 0.2, np.float32)))   # shorter chunk too
        time.sleep(0.05)
    time.sleep(0.3)
    a._running.clear(); t.join(timeout=3)
    assert len(fed) == 4 and all(len(x) == CHUNK for x in fed)
