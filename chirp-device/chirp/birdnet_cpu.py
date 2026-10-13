"""
BirdWatch BirdNET CPU Backend
Uses birdnetlib (wraps BirdNET-Analyzer TFLite model) for inference on CPU.
"""

import logging
import re
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

# Same list the server uses (api/recordings.py _PURGE_PROTECTED_RE).
NIGHT_SPECIES_RE = re.compile(
    r"\b(Owl|Whip-poor-will|Nighthawk|Chuck-will's-widow|Poorwill|Woodcock|"
    r"Night-Heron|Rail|Sora|Bittern)\b")
_OWL_RE = re.compile(r"\bOwl\b")

# Location filter, same rule as the server pass (birdnet_pass.allowed_labels).
# birdnetlib's own filter keeps species whose meta-model score for the week
# is >= 0.03. Owls call year-round but score low (Barred Owl in eastern
# Massachusetts: 0.016 in late September), so that filter silently dropped
# a 0.95-1.00 Barred Owl. Night callers pass when their best week of the
# year reaches these instead.
LOCATION_THRESHOLD = 0.03
OWL_LOCATION_MIN = 0.0015
NIGHT_LOCATION_MIN = 0.005

_loc_lock = threading.Lock()
_loc_cache: Dict[tuple, dict] = {}


def _week_48(day) -> int:
    import calendar
    import math
    doy = day.timetuple().tm_yday
    days = 366 if calendar.isleap(day.year) else 365
    return max(1, min(48, math.ceil(doy / days * 48)))


def _location_lists(lat: float, lon: float) -> dict:
    """{"weeks": {week: set(labels)}, "night": set(labels)}: 48 meta-model
    runs per rounded lat/lon (about a second on a Pi 5), kept in memory."""
    key = (round(float(lat), 2), round(float(lon), 2))
    with _loc_lock:
        if key in _loc_cache:
            return _loc_cache[key]
        import contextlib
        import io
        from birdnetlib.species import SpeciesList
        weeks, best = {}, {}
        # birdnetlib prints progress to stdout (into the service journal).
        with contextlib.redirect_stdout(io.StringIO()):
            sl = SpeciesList()
            lists = {wk: sl.return_list(lat=key[0], lon=key[1], week_48=wk, threshold=0.0)
                     for wk in range(1, 49)}
        for wk in range(1, 49):
            rows = lists[wk]
            weeks[wk] = {f"{r['scientific_name']}_{r['common_name']}"
                         for r in rows if float(r["threshold"]) >= LOCATION_THRESHOLD}
            for r in rows:
                if NIGHT_SPECIES_RE.search(r["common_name"]):
                    lbl = f"{r['scientific_name']}_{r['common_name']}"
                    best[lbl] = max(best.get(lbl, 0.0), float(r["threshold"]))
        night = {lbl for lbl, v in best.items()
                 if v >= (OWL_LOCATION_MIN if _OWL_RE.search(lbl) else NIGHT_LOCATION_MIN)}
        _loc_cache[key] = {"weeks": weeks, "night": night}
        logger.info("BirdNET location list for %.2f,%.2f: %d night callers kept year-round",
                    key[0], key[1], len(night))
        return _loc_cache[key]


def allowed_labels(lat: float, lon: float, day) -> set:
    """Labels expected at lat/lon in day's week, plus night callers."""
    d = _location_lists(lat, lon)
    return d["weeks"][_week_48(day)] | d["night"]


@dataclass
class BirdDetection:
    """A single detection result from BirdNET."""
    common_name: str
    scientific_name: str
    label: str
    confidence: float
    start_time: float
    end_time: float

    def __str__(self) -> str:
        return f"{self.common_name} ({self.scientific_name}) [{self.confidence:.0%}]"


class BirdNetCPU:
    """
    Wraps birdnetlib for bird detection on CPU.
    Thread-safe: uses a lock to prevent concurrent analyses.
    """

    def __init__(self, config: Dict):
        self.config = config["detection"]["birdnet"]
        self.sample_rate = config["audio"]["sample_rate"]
        self.min_confidence: float = self.config["min_confidence"]
        self.lat: Optional[float] = self.config.get("latitude")
        self.lon: Optional[float] = self.config.get("longitude")
        self.species_whitelist: List[str] = self.config.get("species_whitelist", [])
        self.species_blacklist: List[str] = self.config.get("species_blacklist", [])
        self._lock = threading.Lock()
        self._analyzer = None
        self._ready = False

        # Performance stats
        self.stats = {
            "analyses_run": 0,
            "total_detections": 0,
            "total_time_seconds": 0.0,
        }

    def load(self) -> bool:
        """Load the BirdNET model. Call once at startup (slow)."""
        logger.info("Loading BirdNET-Analyzer model (CPU)...")
        try:
            from birdnetlib.analyzer import Analyzer
            self._analyzer = Analyzer()
            self._set_threads(int(self.config.get("num_threads", 2) or 1))
            self._ready = True
            logger.info("BirdNET model loaded successfully.")
            if self.lat is not None and self.lon is not None:
                threading.Thread(target=self._warm_location, daemon=True).start()
            return True
        except ImportError:
            logger.error(
                "birdnetlib not installed. Run: pip install birdnetlib"
            )
            return False
        except Exception as e:
            logger.error("Failed to load BirdNET model: %s", e)
            return False

    def _set_threads(self, n: int) -> None:
        """birdnetlib hardcodes num_threads=1. Rebuild its interpreter with n
        threads so one 3 s window takes less wall time and night windows
        (BirdNET plus the bat detector) don't back up. Keeps the original
        interpreter if anything fails."""
        if n <= 1:
            return
        a = self._analyzer
        try:
            interp = type(a.interpreter)(model_path=a.model_path, num_threads=n)
            interp.allocate_tensors()
            inp, out = interp.get_input_details(), interp.get_output_details()
            a.interpreter, a.input_details, a.output_details = interp, inp, out
            a.input_layer_index = inp[0]["index"]
            a.output_layer_index = out[0]["index"] - (1 if getattr(a, "use_custom_classifier", False) else 0)
            logger.info("BirdNET CPU interpreter: %d threads", n)
        except Exception as e:
            logger.warning("Could not set BirdNET threads to %d (%s); using birdnetlib's single thread", n, e)

    @property
    def is_ready(self) -> bool:
        return self._ready and self._analyzer is not None

    def analyze(
        self,
        audio: np.ndarray,
        timestamp: Optional[datetime] = None,
    ) -> List[BirdDetection]:
        """
        Analyze a float32 mono audio array for bird calls.
        Audio should be ~3 seconds at the configured sample rate.

        Returns list of BirdDetection objects above min_confidence.
        """
        if not self.is_ready:
            logger.warning("BirdNET model not loaded; skipping analysis.")
            return []

        t_start = time.monotonic()

        # Write audio to a temporary WAV file in /tmp (RAM-backed on Linux)
        tmp_path = None
        try:
            with self._lock:
                # Create temp file
                fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="birdwatch_")
                os.close(fd)

                # Ensure audio is float32 and correct dtype for soundfile
                audio_f32 = audio.astype(np.float32)
                # Clamp to [-1, 1]
                audio_f32 = np.clip(audio_f32, -1.0, 1.0)

                sf.write(tmp_path, audio_f32, self.sample_rate, subtype="FLOAT")

                # Run BirdNET analysis
                from birdnetlib import Recording

                from datetime import date as _date
                # Read dynamically from self.config (not the cached self.min_confidence
                # set at __init__) so a hot-applied managed-config push actually changes
                # behavior without a restart. watcher.apply_config() keeps self.config
                # pointed at the live config sub-dict — see watcher.py for the other half
                # of this fix.
                _min_conf = self.config.get("min_confidence", self.min_confidence)
                # Night callers (owls etc.) score low when faint and far; let
                # them through at their own floor, everything else at min_conf.
                _night_floor = min(_min_conf, float(self.config.get("night_species_min_confidence", 0.10) or _min_conf))
                kwargs = {
                    "min_conf": _night_floor,
                    "sensitivity": float(self.config.get("sensitivity", 1.0) or 1.0),
                }
                # Read lat/lon dynamically from config so hot-applied updates
                # (server managed config push) take effect without restarting.
                # The location filter is applied below (allowed_labels), not
                # by birdnetlib, so owls aren't dropped (see _location_lists).
                _lat = self.config.get("latitude") or self.lat
                _lon = self.config.get("longitude") or self.lon
                _day = (timestamp.date() if hasattr(timestamp, "date") else timestamp) \
                    if timestamp is not None else _date.today()
                kwargs["date"] = _day
                _allowed = None
                if _lat is not None and _lon is not None:
                    try:
                        _allowed = allowed_labels(_lat, _lon, _day)
                    except Exception as e:
                        # Fall back to birdnetlib's own (stricter) filter.
                        logger.warning("Location list failed (%s); using birdnetlib's filter.", e)
                        kwargs["lat"], kwargs["lon"] = _lat, _lon
                    logger.debug("BirdNET location filter active: lat=%.4f lon=%.4f date=%s",
                                 _lat, _lon, _day)

                recording = Recording(self._analyzer, tmp_path, **kwargs)
                recording.analyze()
                raw_detections = recording.detections or []

                self.stats["analyses_run"] += 1

        except Exception as e:
            logger.error("BirdNET analysis error: %s", e, exc_info=True)
            return []
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        # Convert to BirdDetection objects and apply filters
        # Read dynamically so a hot-applied managed-config push (e.g. server
        # adding "Engine_Engine" to the blacklist) takes effect immediately —
        # same root cause as the min_confidence/lat/lon fixes above.
        _blacklist = self.config.get("species_blacklist", self.species_blacklist)
        # Night callers the server set to the global threshold (Settings →
        # Detection → Night-Caller Thresholds, "Per species").
        _night_global = set(self.config.get("night_global_species") or [])
        _whitelist = self.config.get("species_whitelist", self.species_whitelist)
        detections = []
        for d in raw_detections:
            label = d.get("label", "")
            common = d.get("common_name", label.split("_")[0] if "_" in label else label)
            scientific = d.get("scientific_name", "")
            confidence = float(d.get("confidence", 0.0))
            if confidence < _min_conf and (not NIGHT_SPECIES_RE.search(common) or common in _night_global):
                continue
            if _allowed is not None and label not in _allowed:
                logger.debug("Not expected here this week: %s (%.2f)", label, confidence)
                continue

            # Apply blacklist
            if any(bl.lower() in label.lower() for bl in _blacklist):
                logger.debug("Blacklisted: %s", label)
                continue

            # Apply whitelist (if not empty)
            if _whitelist and not any(
                wl.lower() in label.lower() for wl in _whitelist
            ):
                logger.debug("Not in whitelist: %s", label)
                continue

            detections.append(BirdDetection(
                common_name=common,
                scientific_name=scientific,
                label=label,
                confidence=confidence,
                start_time=float(d.get("start_time", 0.0)),
                end_time=float(d.get("end_time", 3.0)),
            ))

        elapsed = time.monotonic() - t_start
        self.stats["total_detections"] += len(detections)
        self.stats["total_time_seconds"] += elapsed

        if detections:
            logger.debug(
                "BirdNET found %d detection(s) in %.3fs: %s",
                len(detections),
                elapsed,
                ", ".join(str(d) for d in detections),
            )
        else:
            logger.debug("BirdNET: no detections in %.3fs", elapsed)

        return detections

    def _warm_location(self):
        try:
            _location_lists(self.lat, self.lon)
        except Exception as e:
            logger.warning("Location list warm-up failed: %s", e)

    def get_stats_str(self) -> str:
        n = self.stats["analyses_run"]
        if n == 0:
            return "No analyses run yet."
        avg_ms = (self.stats["total_time_seconds"] / n) * 1000
        return (
            f"BirdNET CPU: {n} analyses, "
            f"{self.stats['total_detections']} detections, "
            f"avg {avg_ms:.0f}ms/window"
        )
