"""
BirdWatch BirdNET Coral Edge TPU Backend

Supports all Coral Edge TPU form factors:
  - Coral USB Accelerator (USB 3.0)       → /dev/apex_0 via USB
  - Coral M.2 Accelerator A+E key         → /dev/apex_0 via PCIe
  - Coral M.2 Accelerator B+M (NVMe-style)→ /dev/apex_0 via PCIe
  - Coral PCIe Accelerator                → /dev/apex_0 via PCIe

All PCIe-based Coral devices (M.2 A+E, M.2 B+M, PCIe card) present identically
to the OS via the gasket-dkms PCIe driver — no code changes needed between them.
The M.2 B+M "NVMe-style" connector carries PCIe lanes, not NVMe protocol.

Installation (all form factors):
  sudo apt install gasket-dkms  # for PCIe M.2 variants
  pip install --extra-index-url https://google-coral.github.io/py-repo/ pycoral~=2.0
  # Then run install-coral.sh from this repo

Model source:
  BirdNET-Analyzer (https://github.com/birdnet-team/BirdNET-Analyzer)
  EdgeTPU-compiled model: BirdNET_GLOBAL_6K_V2.4_Model_FP32_edgetpu.tflite
  (NOTE: as of this version, no actively-maintained source for a pre-built
  EdgeTPU model is confirmed to exist — see install-coral.sh's own Step 3
  output for the full, current explanation and real remaining options.)
"""

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .birdnet_cpu import BirdDetection, NIGHT_SPECIES_RE  # shared with the CPU backend

logger = logging.getLogger(__name__)

# Path where install-coral.sh places the EdgeTPU model + labels.
#
# Derived relative to this file's own real location (chirp-device/chirp/
# birdnet_coral.py -> chirp-device/models/coral), NOT hardcoded to a
# specific path. This was previously hardcoded to "/home/pi/chirp-device/
# models/coral" — a real, confirmed bug found via live device logs: for
# any user not named exactly "pi" (this one included, running as
# joshsalvi), the application was checking a directory that could never
# contain the real files, regardless of how correctly install-coral.sh
# placed them — install-coral.sh already correctly derives its own
# MODELS_DIR relative to wherever the installer script itself lives, not
# a hardcoded path, so the two never intersected. This mirrors that same
# already-correct relative-path approach instead of hardcoding anything.
CORAL_MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "coral"
EDGETPU_MODEL_PATH = CORAL_MODEL_DIR / "BirdNET_GLOBAL_6K_V2.4_Model_FP32_edgetpu.tflite"
LABELS_PATH = CORAL_MODEL_DIR / "BirdNET_GLOBAL_6K_V2.4_Labels.txt"

# BirdNET model expects exactly 144,000 samples at 48kHz (3 seconds)
BIRDNET_SAMPLE_RATE = 48000
BIRDNET_SAMPLES = 144000
BIRDNET_N_CLASSES = 6522  # BirdNET v2.4 label count


class BirdNetCoral:
    """
    BirdNET inference using Google Coral USB Accelerator (Edge TPU).
    Runs TFLite model with EdgeTPU delegate for ~10x CPU speedup.
    Thread-safe inference with a single lock.
    """

    def __init__(self, config: Dict):
        self.config = config["detection"]["birdnet"]
        self.sample_rate: int = config["audio"]["sample_rate"]
        self.min_confidence: float = self.config["min_confidence"]
        self.lat: Optional[float] = self.config.get("latitude")
        self.lon: Optional[float] = self.config.get("longitude")
        self.species_whitelist: List[str] = self.config.get("species_whitelist", [])
        self.species_blacklist: List[str] = self.config.get("species_blacklist", [])

        self._interpreter = None
        self._input_details = None
        self._output_details = None
        self._labels: List[str] = []
        self._lock = threading.Lock()
        self._ready = False
        self.backend: Optional[str] = None  # set by load(): "pycoral" | "tflite-runtime" | "tensorflow"

        # Performance stats
        self.stats = {
            "analyses_run": 0,
            "total_detections": 0,
            "total_time_seconds": 0.0,
        }

    def load(self) -> bool:
        """Load the EdgeTPU model and labels. Call once at startup."""
        logger.info("Loading BirdNET EdgeTPU model from %s ...", EDGETPU_MODEL_PATH)

        if not EDGETPU_MODEL_PATH.exists():
            logger.error(
                "EdgeTPU model not found at %s. "
                "Did you run install-coral.sh?",
                EDGETPU_MODEL_PATH,
            )
            return False

        # Real content check, not just existence — confirmed via a real,
        # live incident this was built to catch: install-coral.sh's old
        # download URL silently saved a ~300KB GitHub 404 HTML error page
        # in place of the real model (curl -L followed a genuine org-
        # rename redirect successfully, then got a real 404 for the file
        # itself, which GitHub serves as HTML). That file passed the old
        # "exists" check and the installer's own too-lenient size check,
        # only failing here with a confusing TFLite-parser error instead
        # of a clear message about what's actually wrong. A real TFLite
        # FlatBuffer file has the literal 4-byte identifier "TFL3" at a
        # fixed offset (bytes 4-8) — checking for it directly is a
        # reliable way to catch an HTML/text file masquerading as a
        # model, independent of file size alone.
        try:
            with open(EDGETPU_MODEL_PATH, "rb") as f:
                header = f.read(8)
            if len(header) < 8 or header[4:8] != b"TFL3":
                logger.error(
                    "File at %s does not look like a real TFLite model "
                    "(missing the expected 'TFL3' FlatBuffer signature — "
                    "this usually means an HTML error page was downloaded "
                    "instead of the real model file, e.g. from a moved/dead "
                    "URL). Re-run install-coral.sh, which now detects and "
                    "removes exactly this kind of bad file automatically, "
                    "or see its Step 3 output for current options.",
                    EDGETPU_MODEL_PATH,
                )
                return False
        except Exception as e:
            logger.error("Could not read %s to verify it: %s", EDGETPU_MODEL_PATH, e)
            return False

        resolved_labels_path = LABELS_PATH
        if not LABELS_PATH.exists():
            # Fall back to birdnetlib's own bundled copy of the exact same
            # official label file — birdnetlib is already a required
            # dependency (the CPU backend uses it), so this is very likely
            # to already be sitting on disk even if install-coral.sh's own
            # copy step was never run or the models/coral directory was
            # wiped. find_spec locates the package without executing its
            # __init__.py — a full `import birdnetlib` would transitively
            # pull in birdnetlib.analyzer, which unconditionally imports
            # tflite_runtime or tensorflow at module load time, which we
            # don't want triggered just to find a label file's path.
            import importlib.util
            fallback_path = None
            try:
                spec = importlib.util.find_spec("birdnetlib")
                if spec and spec.origin:
                    candidate = Path(spec.origin).parent / "models" / "analyzer" / LABELS_PATH.name
                    if candidate.exists():
                        fallback_path = candidate
            except Exception as e:
                logger.debug("birdnetlib labels fallback lookup failed: %s", e)

            if fallback_path is not None:
                logger.warning(
                    "Labels file not found at %s — using birdnetlib's bundled copy "
                    "at %s instead (same official label file).",
                    LABELS_PATH, fallback_path,
                )
                resolved_labels_path = fallback_path
            else:
                logger.error("Labels file not found at %s (and no birdnetlib fallback available)", LABELS_PATH)
                return False

        # Three-tier interpreter backend, tried in order of install weight
        # (lightest first). pycoral and tflite-runtime are both confirmed
        # dead ends for any Python newer than 3.11 — pycoral's last release
        # only ever supported up to 3.9, tflite-runtime's last release
        # (2.14.0, Oct 2023) tops out at 3.11, and neither project has
        # shipped a newer wheel since (see google-coral/pycoral#137, #149 —
        # community build attempts for 3.10+ hit real, unresolved Bazel
        # build errors, not just a missing-wheel inconvenience).
        #
        # The actual fix: pycoral and tflite-runtime are both just thin
        # wrappers around the SAME underlying TFLite C++ interpreter that
        # the full `tensorflow` package also exposes via
        # `tf.lite.Interpreter` — and unlike the other two, `tensorflow`
        # is actively maintained and genuinely ships official Python 3.13
        # wheels for linux_aarch64 (confirmed: tensorflow 2.21.0 includes
        # tensorflow-2.21.0-cp313-cp313-manylinux_2_27_aarch64.whl on
        # PyPI). Loading the EdgeTPU delegate library directly via
        # `tf.lite.experimental.load_delegate('libedgetpu.so.1')` gets the
        # exact same hardware-accelerated inference pycoral's
        # make_interpreter() would have given us — pycoral was always just
        # a convenience wrapper around this, never a requirement (see
        # Coral's own docs: "You can run inference in Python without
        # [pycoral], using only the tflite_runtime API"). `libedgetpu.so.1`
        # itself comes from install-coral.sh's apt-installed
        # libedgetpu1-std package — that part was never Python-version-
        # sensitive at all.
        #
        # Tradeoff worth knowing: full `tensorflow` is a much heavier
        # install (100s of MB) than pycoral/tflite-runtime (a few MB) — a
        # real cost on a Pi's storage/RAM, but the only currently-viable
        # path on Python 3.12+.
        self._interpreter = None
        backend_used = None
        errors = []

        try:
            from pycoral.utils.edgetpu import make_interpreter
            self._interpreter = make_interpreter(str(EDGETPU_MODEL_PATH))
            backend_used = "pycoral"
        except Exception as e:
            errors.append(f"pycoral: {e}")

        if self._interpreter is None:
            try:
                from tflite_runtime.interpreter import Interpreter, load_delegate
                delegate = load_delegate("libedgetpu.so.1")
                self._interpreter = Interpreter(
                    model_path=str(EDGETPU_MODEL_PATH),
                    experimental_delegates=[delegate],
                )
                backend_used = "tflite-runtime"
            except Exception as e:
                errors.append(f"tflite-runtime: {e}")

        if self._interpreter is None:
            try:
                import tensorflow as tf
                delegate = tf.lite.experimental.load_delegate("libedgetpu.so.1")
                self._interpreter = tf.lite.Interpreter(
                    model_path=str(EDGETPU_MODEL_PATH),
                    experimental_delegates=[delegate],
                )
                backend_used = "tensorflow"
            except Exception as e:
                errors.append(f"tensorflow: {e}")

        if self._interpreter is None:
            logger.error(
                "Could not create an EdgeTPU interpreter via any backend "
                "(pycoral, tflite-runtime, or tensorflow). Tried, in order:\n  %s\n"
                "Run install-coral.sh, which picks the right backend for your "
                "Python version automatically, or install one manually:\n"
                "  pip install tensorflow   # heaviest but works on any current Python\n"
                "Also confirm libedgetpu1-std is installed (apt) and the "
                "Coral device is plugged in.",
                "\n  ".join(errors),
            )
            return False

        logger.info("EdgeTPU interpreter backend: %s", backend_used)

        try:
            self._interpreter.allocate_tensors()
            self._input_details = self._interpreter.get_input_details()
            self._output_details = self._interpreter.get_output_details()

            logger.info(
                "EdgeTPU interpreter ready. Input shape: %s",
                self._input_details[0]["shape"],
            )
        except Exception as e:
            logger.error("Failed to initialize EdgeTPU interpreter: %s", e)
            return False

        # Load labels
        try:
            with open(resolved_labels_path, "r", encoding="utf-8") as f:
                self._labels = [line.strip() for line in f if line.strip()]
            logger.info("Loaded %d BirdNET labels", len(self._labels))
        except Exception as e:
            logger.error("Failed to load labels: %s", e)
            return False

        self._ready = True
        self.backend = backend_used  # "pycoral" | "tflite-runtime" | "tensorflow" — for diagnostics/status reporting
        logger.info("BirdNET EdgeTPU model loaded successfully.")
        return True

    @property
    def is_ready(self) -> bool:
        return self._ready and self._interpreter is not None

    def analyze(
        self,
        audio: np.ndarray,
        timestamp: Optional[datetime] = None,
    ) -> List[BirdDetection]:
        """
        Analyze a float32 mono audio array for bird calls.
        Audio should be 3 seconds (144,000 samples) at 48kHz.
        Resamples if audio length differs from expected.
        Returns list of BirdDetection objects above min_confidence.
        """
        if not self.is_ready:
            logger.warning("Coral model not loaded; skipping analysis.")
            return []

        t_start = time.monotonic()

        # Resample to 48kHz / 144000 samples if needed
        audio_prep = self._prepare_audio(audio)
        if audio_prep is None:
            return []

        detections = []
        try:
            with self._lock:
                # Set input tensor
                input_tensor = self._input_details[0]
                # BirdNET expects shape [1, 144000] float32
                input_data = audio_prep.reshape(input_tensor["shape"])
                self._interpreter.set_tensor(input_tensor["index"], input_data)

                # Run inference
                self._interpreter.invoke()

                # Get output logits
                output = self._interpreter.get_tensor(
                    self._output_details[0]["index"]
                )[0]  # shape: [n_classes]

                # Sigmoid with BirdNET's sensitivity scaling (same formula
                # birdnetlib uses on the CPU path)
                # Same mapping birdnetlib's Recording applies on the CPU path:
                # the setting (higher = more detections) becomes the slope
                # 1 - (s - 1), clamped to 0.5-1.5, so 1.5 means slope 0.5.
                # This used the setting as the slope directly, the reverse:
                # 1.5 sharpened scores and pushed faint calls (owls) down.
                sens = float(self.config.get("sensitivity", 1.0) or 1.0)
                slope = max(0.5, min(1.0 - (sens - 1.0), 1.5))
                logits = np.clip(output.astype(np.float32), -15.0, 15.0)
                confidences = 1.0 / (1.0 + np.exp(-slope * logits))

                self.stats["analyses_run"] += 1

            # Threshold and build detections
            # Read live config so a server push applies without a restart
            min_conf = float(self.config.get("min_confidence", self.min_confidence))
            blacklist = self.config.get("species_blacklist", self.species_blacklist) or []
            whitelist = self.config.get("species_whitelist", self.species_whitelist) or []
            # Night callers (owls etc.) at their own floor, and the location
            # filter: the same rules as the CPU backend (birdnet_cpu.py).
            night_floor = min(min_conf, float(self.config.get("night_species_min_confidence", 0.10) or min_conf))
            night_global = set(self.config.get("night_global_species") or [])
            allowed = None
            lat = self.config.get("latitude") or self.lat
            lon = self.config.get("longitude") or self.lon
            if lat is not None and lon is not None:
                try:
                    from .birdnet_cpu import allowed_labels
                    day = timestamp.date() if hasattr(timestamp, "date") else datetime.utcnow().date()
                    allowed = allowed_labels(lat, lon, day)
                except Exception as e:
                    logger.debug("Location list unavailable (%s); no location filter.", e)
            passing = np.where(confidences >= night_floor)[0]
            for idx in passing:
                if idx >= len(self._labels):
                    continue
                label = self._labels[idx]
                confidence = float(confidences[idx])
                if confidence < min_conf and (not NIGHT_SPECIES_RE.search(label)
                                              or label.split("_", 1)[-1] in night_global):
                    continue
                if allowed is not None and label not in allowed:
                    continue

                # Parse label: "Scientific Name_Common Name" — this is the
                # official BirdNET label format (confirmed directly against
                # birdnetlib's bundled BirdNET_GLOBAL_6K_V2.4_Labels.txt,
                # e.g. "Abroscopus albogularis_Rufous-faced Warbler" — a
                # Latin binomial first, English common name second). This
                # was previously backwards (assumed "Common_Scientific"),
                # which would have swapped common/scientific names on every
                # single Coral detection — never caught because Coral
                # inference had never successfully completed a load()+
                # inference cycle before (blocked first by the pycoral
                # Python-version gap, then by the missing model file).
                parts = label.split("_", 1)
                scientific = parts[0] if len(parts) >= 1 else label
                common = parts[1] if len(parts) >= 2 else ""

                # Apply blacklist/whitelist
                if any(bl.lower() in label.lower() for bl in blacklist):
                    continue
                if whitelist and not any(
                    wl.lower() in label.lower() for wl in whitelist
                ):
                    continue

                detections.append(BirdDetection(
                    common_name=common,
                    scientific_name=scientific,
                    label=label,
                    confidence=confidence,
                    start_time=0.0,
                    end_time=3.0,
                ))

            # Sort by confidence descending
            detections.sort(key=lambda d: d.confidence, reverse=True)

        except Exception as e:
            logger.error("EdgeTPU inference error: %s", e, exc_info=True)
            return []

        elapsed = time.monotonic() - t_start
        self.stats["total_detections"] += len(detections)
        self.stats["total_time_seconds"] += elapsed

        if detections:
            logger.debug(
                "BirdNET (Coral) found %d detection(s) in %.1fms: %s",
                len(detections),
                elapsed * 1000,
                ", ".join(str(d) for d in detections),
            )
        else:
            logger.debug("BirdNET (Coral): no detections in %.1fms", elapsed * 1000)

        return detections

    def _prepare_audio(self, audio: np.ndarray) -> Optional[np.ndarray]:
        """
        Normalize and resize audio to exactly BIRDNET_SAMPLES float32 samples.
        Handles resampling if input sample rate differs.
        """
        try:
            audio_f32 = audio.astype(np.float32)

            # Resample if needed
            if self.sample_rate != BIRDNET_SAMPLE_RATE:
                from scipy.signal import resample_poly
                from math import gcd
                g = gcd(BIRDNET_SAMPLE_RATE, self.sample_rate)
                up = BIRDNET_SAMPLE_RATE // g
                down = self.sample_rate // g
                audio_f32 = resample_poly(audio_f32, up, down).astype(np.float32)

            # Pad or truncate to exactly BIRDNET_SAMPLES
            if len(audio_f32) < BIRDNET_SAMPLES:
                audio_f32 = np.pad(
                    audio_f32,
                    (0, BIRDNET_SAMPLES - len(audio_f32)),
                    mode="constant",
                )
            elif len(audio_f32) > BIRDNET_SAMPLES:
                audio_f32 = audio_f32[:BIRDNET_SAMPLES]

            # Normalize to [-1, 1]
            max_val = np.max(np.abs(audio_f32))
            if max_val > 0:
                audio_f32 = audio_f32 / max_val

            return audio_f32

        except Exception as e:
            logger.error("Audio preparation failed: %s", e)
            return None

    def get_stats_str(self) -> str:
        n = self.stats["analyses_run"]
        if n == 0:
            return "No analyses run yet (Coral)."
        avg_ms = (self.stats["total_time_seconds"] / n) * 1000
        return (
            f"BirdNET Coral: {n} analyses, "
            f"{self.stats['total_detections']} detections, "
            f"avg {avg_ms:.0f}ms/window"
        )


def check_coral_available() -> bool:
    """
    Quick check: is any Coral Edge TPU reachable?
    Supports all form factors:
      - USB Accelerator       → detected via pycoral list_edge_tpus
      - M.2 A+E / B+M / PCIe → /dev/apex_0 exists (gasket-dkms driver)
    """
    import subprocess

    # PCIe / M.2 variants expose /dev/apex_N via gasket-dkms
    for n in range(4):
        if os.path.exists(f"/dev/apex_{n}"):
            logger.info("Coral Edge TPU found at /dev/apex_%d (PCIe/M.2)", n)
            return True

    # /dev/apex_0 missing — diagnose why and give actionable guidance
    if os.path.exists("/dev/apex_0") is False:
        # Check if gasket module is loaded
        try:
            lsmod = subprocess.check_output(["lsmod"], timeout=3).decode()
            if "gasket" not in lsmod:
                logger.warning(
                    "Coral M.2/PCIe: /dev/apex_0 not found and gasket module not loaded. "
                    "A reboot is required after gasket driver installation. "
                    "Run: sudo reboot  — then restart chirp-device."
                )
            else:
                logger.warning(
                    "Coral M.2/PCIe: gasket module is loaded but /dev/apex_0 not found. "
                    "Check PCIe is enabled: grep pciex1 /boot/firmware/config.txt  "
                    "and that the M.2 card is properly seated."
                )
        except Exception:
            pass

    # USB variant — detected via pycoral or lsusb
    try:
        from pycoral.utils.edgetpu import list_edge_tpus
        tpus = list_edge_tpus()
        if tpus:
            logger.info("Coral Edge TPU(s) found via pycoral: %s", tpus)
            return True
    except ImportError:
        pass
    except Exception as e:
        logger.debug("pycoral check error: %s", e)

    # tflite delegate check — tflite-runtime + libedgetpu may work even without pycoral
    try:
        import tflite_runtime.interpreter as tflite
        delegates = tflite.load_delegate("libedgetpu.so.1")
        if delegates:
            logger.info("Coral available via libedgetpu delegate (tflite-runtime)")
            return True
    except Exception:
        pass

    # Third tier, consistent with load()'s own fallback chain: on Python
    # 3.12+ neither pycoral nor tflite-runtime has an installable wheel at
    # all (see load()'s docstring/comments for the full explanation), so
    # without this check, a system that only has `tensorflow` installed
    # would report "no Coral available" here and load() would never even
    # be attempted — even though load() itself is fully capable of using
    # tensorflow's tf.lite.Interpreter + EdgeTPU delegate successfully.
    try:
        import tensorflow as tf
        delegates = tf.lite.experimental.load_delegate("libedgetpu.so.1")
        if delegates:
            logger.info("Coral available via libedgetpu delegate (tensorflow)")
            return True
    except Exception:
        pass

    logger.info("No Coral Edge TPU found — falling back to CPU inference.")
    return False
