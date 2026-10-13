"""
BirdWatch Configuration Loader
Loads, validates, and provides defaults for config.yaml
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)

# ── Defaults applied on top of user config (deep merge) ──────────────────────

DEFAULTS: Dict[str, Any] = {
    "audio": {
        "sample_rate": 48000,
        "channels_per_device": 1,
        "chunk_size": 4800,
        "bit_depth": 16,
        "device_name_hints": ["USB", "Microphone"],
        "device_name_excludes": [],
        "max_devices": 2,
        "fallback_to_default": True,
        "input_gain_db": 6.0,  # restored — the 0.0 revert silently pushed real bird calls below Stage 1's fixed -70dB energy threshold; the noise it was meant to fix traced to cicadas/mic spacing instead
    },
    "detection": {
        "pre_roll_seconds": 5.0,
        "energy_filter": {
            "enabled": True,
            "window_seconds": 0.5,
            "threshold_db": -90.0,
            "frequency_band_hz": [150, 12000],
            "filter_order": 4,
        },
        "birdnet": {
            "enabled": True,
            "analysis_window_seconds": 3.0,
            "min_confidence": 0.05,
            "overlap_seconds": 2.0,
            "sensitivity": 1.5,
            "backend": "cpu",
            "num_threads": 2,
            "night_species_min_confidence": 0.10,
            "night_global_species": [],
            "latitude": None,
            "longitude": None,
            "species_whitelist": [],
            "species_blacklist": ["Human_Human", "Noise_Noise"],
        },
        "cooldown_seconds": 10.0,
        "min_detections_to_trigger": 1,
    },
    "recording": {
        "duration_seconds": 30.0,
        "extend_on_activity": True,
        "extension_seconds": 10.0,
        "max_duration_seconds": 120.0,
        "output_dir": "~/chirp-device/recordings",
        "filename_format": "birdwatch_%Y%m%d_%H%M%S_{confidence:.2f}.wav",
        "include_metadata_sidecar": True,
        "max_disk_gb": 20.0,
        "auto_delete_days": 30,
        "format": "wav",
        "normalize_output": False,
    },
    "upload": {
        "enabled": False,
        "server_url": "PLACEHOLDER_SERVER_URL",
        "api_key": "PLACEHOLDER_API_KEY",
        "auth_header": "X-API-Key",
        "timeout_seconds": 60,
        "max_retries": 5,
        "retry_delay_seconds": 30,
        "retry_backoff_factor": 2.0,
        "include_metadata": True,
        "delete_after_upload": False,
        "upload_queue_max_size": 100,
        "retry_queued_interval_seconds": 300,
    },
    "system": {
        "health_check_interval_seconds": 30,
        "watchdog_timeout_seconds": 120,
        "detection_thread_priority": "normal",
        "timezone": "local",
    },
    "server_sync": {
        "enabled": False,
        "server_url": "",
        "api_key": "",
        "device_name": "",
        "config_poll_interval_seconds": 60,
        "heartbeat_interval_seconds": 30,
    },
    "logging": {
        "level": "INFO",
        "log_dir": "~/chirp-device/logs",
        "max_mb": 100,
        "backup_count": 10,
        "console_output": True,
        "log_detections": True,
        "log_energy_filter": False,
        "window_stats_interval_seconds": 600,
    },
}


def deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file, merged with defaults."""
    path = Path(config_path)
    if not path.exists():
        logger.warning(f"Config file {config_path} not found, using all defaults.")
        config = DEFAULTS.copy()
    else:
        with open(path, "r") as f:
            user_config = yaml.safe_load(f) or {}
        config = deep_merge(DEFAULTS, user_config)
        logger.info(f"Loaded config from {config_path}")

    _validate_config(config)
    _expand_paths(config)
    _warn_placeholders(config)
    return config


def _validate_config(config: Dict) -> None:
    """Validate critical config values and raise on fatal errors."""
    sr = config["audio"]["sample_rate"]
    if sr not in (16000, 22050, 32000, 44100, 48000):
        raise ValueError(f"Unsupported sample_rate: {sr}. Use 16000, 44100, or 48000.")

    band = config["detection"]["energy_filter"]["frequency_band_hz"]
    if len(band) != 2 or band[0] >= band[1]:
        raise ValueError(f"frequency_band_hz must be [low, high]: got {band}")

    if band[1] >= sr / 2:
        raise ValueError(
            f"Upper frequency band {band[1]} Hz must be < Nyquist ({sr/2} Hz)"
        )

    dur = config["recording"]["duration_seconds"]
    if dur <= 0:
        raise ValueError(f"recording.duration_seconds must be > 0, got {dur}")

    backend = config["detection"]["birdnet"]["backend"]
    if backend not in ("cpu", "coral"):
        raise ValueError(f"birdnet.backend must be 'cpu' or 'coral', got '{backend}'")


def _expand_paths(config: Dict) -> None:
    """
    Expand ~ and env vars in path configs, create directories.

    Also resolves any remaining relative path to an absolute one, anchored
    to the user's home directory — NOT left relative to the process's
    current working directory. A relative output_dir ("recordings", the
    shipped default, documented as "relative to chirp-device directory")
    is fragile: it depends on CWD being correct at the exact moment each
    path operation runs, which systemd's WorkingDirectory setting usually
    ensures but doesn't structurally guarantee for the whole process
    lifetime. Confirmed as a real, live bug: a FileNotFoundError for the
    literal relative path 'recordings' crashed the recording thread mid-
    run on a real device. Resolving to an absolute path once here means
    every later path operation against this same config value resolves
    identically regardless of CWD.
    """
    for section, key in [
        ("recording", "output_dir"),
        ("logging", "log_dir"),
    ]:
        raw = config[section][key]
        expanded = os.path.expandvars(os.path.expanduser(raw))
        if not os.path.isabs(expanded):
            expanded = str(Path.home() / expanded)
        expanded = _fix_wrong_user_home(expanded)
        config[section][key] = expanded
        Path(expanded).mkdir(parents=True, exist_ok=True)

    # bat_echolocation.events_dir — same fix, applied separately since it's
    # nested three levels deep rather than the two-level (section, key)
    # structure the loop above handles. Found via the same real device
    # logs: config.yaml had this hardcoded to "/home/pi/chirp/bat_events",
    # the identical hardcoded-user-path bug already fixed once this
    # session elsewhere. bat_detector.py reads this value directly with no
    # expansion of its own (confirmed: plain Path() does not auto-expand
    # ~), so this needs real coverage here, not just a config-string change.
    try:
        bat_cfg = config.get("detection", {}).get("bat_echolocation", {})
        if "events_dir" in bat_cfg:
            raw = bat_cfg["events_dir"]
            expanded = os.path.expandvars(os.path.expanduser(raw))
            if not os.path.isabs(expanded):
                expanded = str(Path.home() / expanded)
            expanded = _fix_wrong_user_home(expanded)
            bat_cfg["events_dir"] = expanded
            Path(expanded).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning("Could not expand bat_echolocation.events_dir: %s", e)


def _fix_wrong_user_home(path: str) -> str:
    """
    Catch the SPECIFIC real bug confirmed via live device logs this
    session: an already-absolute path hardcoded to "/home/pi/..." on a
    system where the actual current user is genuinely someone else (e.g.
    joshsalvi). isabs()-based expansion alone doesn't catch this, since
    the path already IS absolute — just absolute-and-wrong, not
    absolute-and-right. This specifically protects an existing, already-
    deployed config.yaml carrying the old hardcoded default, not just
    fresh configs using a corrected relative/~ default. Intentionally
    narrow (only rewrites the literal "/home/pi/" prefix) rather than a
    broad "any /home/<other-user>/" rewrite, to avoid silently
    "correcting" a path some other user may have genuinely, deliberately
    set to point at the literal 'pi' user's home on purpose (e.g. a
    multi-user setup).
    """
    real_home = str(Path.home())
    if path.startswith("/home/pi/") and real_home != "/home/pi":
        fixed = real_home + path[len("/home/pi"):]
        logger.warning(
            "Config path '%s' is hardcoded to /home/pi, but this system's real "
            "home directory is %s — using %s instead. Update your config.yaml "
            "to avoid relying on this automatic correction.",
            path, real_home, fixed,
        )
        return fixed
    return path


def _warn_placeholders(config: Dict) -> None:
    """
    Warn if upload is enabled but placeholders remain.

    A real bug found via live end-to-end testing, not by inspection:
    this function originally only ever checked the LEGACY top-level
    upload.server_url/api_key fields. DEFAULT_CONFIG's own defaults
    still set those to "PLACEHOLDER_SERVER_URL"/"PLACEHOLDER_API_KEY"
    unconditionally — meaning anyone who switched to the newer
    upload.targets: list format (see docs/MULTI_SERVER_DEVICE.md),
    without ALSO redundantly setting the now-superseded top-level
    fields to something else, hit a false-positive "still a
    placeholder" error and the device refused to start AT ALL, for
    every run mode (normal operation, --test-audio, --test-detection,
    --test-upload) — load_config() calls this unconditionally. Caught
    by actually running a real targets:-based config.yaml through
    --test-upload against a live server and watching it fail before
    ever reaching the upload attempt itself.
    """
    upload = config["upload"]
    if upload["enabled"]:
        target_configs = upload.get("targets")
        if target_configs:
            # New format: check each individually-enabled target's own
            # fields, not the legacy top-level ones — a disabled target
            # left at its placeholder default is not something to warn
            # about, since it was never going to be used anyway.
            for i, tc in enumerate(target_configs):
                if not tc.get("enabled", True):
                    continue
                label = tc.get("name", f"target #{i+1}")
                if "PLACEHOLDER" in str(tc.get("server_url", "")):
                    raise ValueError(
                        f"upload.targets[{label}].server_url is still a placeholder. "
                        f"Set the real server URL, or set enabled: false for this target."
                    )
                credential_field = "api_key"
                if "PLACEHOLDER" in str(tc.get(credential_field, "")):
                    logger.warning(
                        "upload.targets[%s].%s appears to still be a placeholder. Authentication may fail.",
                        label, credential_field,
                    )
        else:
            # Legacy format: no targets: list at all, so the top-level
            # fields are genuinely what's in effect — the original check.
            if "PLACEHOLDER" in str(upload.get("server_url", "")):
                raise ValueError(
                    "upload.enabled is True but server_url is still a placeholder. "
                    "Set the real server URL or disable upload in config.yaml."
                )
            if "PLACEHOLDER" in str(upload.get("api_key", "")):
                logger.warning(
                    "upload.api_key appears to still be a placeholder. "
                    "Authentication may fail."
                )
    sync = config.get("server_sync", {})
    if sync.get("enabled"):
        sync_targets = sync.get("targets")
        if sync_targets:
            # New format: check each individually-enabled target's own
            # fields, not the legacy top-level ones — same reasoning as
            # upload.targets' own validation just above.
            for i, tc in enumerate(sync_targets):
                if not tc.get("enabled", True):
                    continue
                label = tc.get("name", f"target #{i+1}")
                if "PLACEHOLDER" in str(tc.get("server_url", "")):
                    raise ValueError(
                        f"server_sync.targets[{label}].server_url is still a placeholder. "
                        f"Set the real server URL, or set enabled: false for this target."
                    )
                if "PLACEHOLDER" in str(tc.get("api_key", "")):
                    logger.warning(
                        "server_sync.targets[%s].api_key appears to still be a placeholder. "
                        "Authentication may fail.", label,
                    )
        else:
            # Legacy format: no targets: list at all, so the top-level
            # fields are genuinely what's in effect — the original check.
            if "PLACEHOLDER" in str(sync.get("server_url", "")):
                raise ValueError(
                    "server_sync.enabled is True but server_url is still a placeholder. "
                    "Set the real server URL or disable server_sync in config.yaml."
                )
            if "PLACEHOLDER" in str(sync.get("api_key", "")):
                raise ValueError(
                    "server_sync.enabled is True but api_key is still a placeholder. "
                    "Generate a key in the Chirp web UI under Settings → Devices."
                )
    else:
        logger.info("Server sync disabled — device will run standalone")

    ts = config.get("tailscale", {})
    if ts.get("enabled"):
        # Warning, not a raised error, unlike server_sync's own equivalent
        # check above — Tailscale is a genuinely optional, additive
        # connectivity layer (see TailscaleManager's own docstring), not
        # something the rest of the device depends on to function.
        # TailscaleManager.start() already handles a placeholder key the
        # same way (skips starting, logs a warning) — this just surfaces
        # the same problem earlier, at config-validation time, rather
        # than only once the device actually tries to bring Tailscale up.
        if "PLACEHOLDER" in str(ts.get("auth_key", "")):
            logger.warning(
                "tailscale.enabled is True but auth_key still looks like a placeholder. "
                "Generate a real one from your Tailscale/Headscale admin console — "
                "Tailscale will not actually connect until this is set."
            )
    if not upload.get("enabled"):
        logger.info(
            "Upload is disabled — recordings will be saved locally to: %s",
            config["recording"]["output_dir"],
        )
