"""
Chirp Device — Zigbee Integration
Future: publish detections to a Zigbee coordinator / home automation hub.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURRENT STATUS: Stub / placeholder.
This module is intentionally inert until a Zigbee coordinator is
configured. When enabled it will publish detection events as Zigbee
sensor updates, allowing home automation systems (Home Assistant,
openHAB, Domoticz) to react to bird detections.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SUPPORTED HARDWARE
──────────────────
The following USB Zigbee coordinator dongles are supported or planned:

  ConBee II / ConBee III (dresden elektronik)
    USB stick, widely supported, recommended for Home Assistant
    Typical device: /dev/ttyUSB0 or /dev/ttyACM0

  SONOFF Zigbee 3.0 USB Dongle Plus (EFR32MG21)
    USB stick, high-power antenna, good range
    Typical device: /dev/ttyUSB0 or /dev/ttyACM0

  Zig-a-Zig-Ah! (ZZH) or Tube's ZB coordinator
    USB stick variants

  SLZB-06 / SLZB-07 (SMLIGHT)
    Ethernet and USB Zigbee coordinator

  Argon ONE m.2 Zigbee HAT (if using Argon ONE v5 M.2 expansion)
    Pins via internal M.2 B+M slot — check /dev/ttyAMA0 or ttyS0

All devices must be flashed with Zigbee Coordinator firmware
(e.g. EmberZNet, Z-Stack).

INTEGRATION MODES
─────────────────
  mode: "zigbee2mqtt"   (recommended)
    Publishes JSON payloads to an MQTT broker. Zigbee2MQTT bridge
    running separately translates to Zigbee frames.
    Requires: paho-mqtt, a running MQTT broker, and zigbee2mqtt.

  mode: "deconz"        (planned)
    REST/WebSocket API on ConBee II running deCONZ.
    Requires: deCONZ running on same or remote host.

  mode: "znp_direct"    (planned)
    Direct Zigbee NWK via zigpy + bellows or zigpy-znp.
    Requires: zigpy, zigpy-znp or bellows, Z-Stack coordinator firmware.

DETECTION PAYLOAD (Zigbee2MQTT example)
────────────────────────────────────────
Topic: chirp/detection
```json
{
  "event":       "detection",
  "species":     "American Robin",
  "confidence":  0.89,
  "timestamp":   "2026-05-30T14:23:11Z",
  "device_name": "Garden Pi",
  "recording_id": "abc123...",
  "backend":     "coral"
}
```

HEARTBEAT PAYLOAD
──────────────────
Topic: chirp/status
```json
{
  "online":      true,
  "triggers_today": 12,
  "recordings":  8,
  "cpu_temp_c":  41.2,
  "disk_free_gb": 14.3
}
```

SETUP (zigbee2mqtt mode)
─────────────────────────
1. Install and run MQTT broker (Mosquitto):
     sudo apt install mosquitto mosquitto-clients
     sudo systemctl enable --now mosquitto

2. Install zigbee2mqtt and configure your coordinator device.
   See: https://www.zigbee2mqtt.io/guide/installation/

3. Add to config.yaml:
     zigbee:
       enabled: true
       mode: "zigbee2mqtt"
       mqtt_broker: "localhost"
       mqtt_port: 1883
       mqtt_topic_prefix: "chirp"
       mqtt_username: ""      # optional
       mqtt_password: ""      # optional
       # coordinator_port: "/dev/ttyUSB0"   # only needed for znp_direct mode

4. Install paho-mqtt:
     pip install paho-mqtt

5. Restart chirp-device. On each detection, a message is published to
   chirp/detection and chirp/status on your MQTT broker.

Home Assistant auto-discovery is planned for a future release.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ZigbeeIntegration:
    """
    Publishes Chirp detection events and status heartbeats to a Zigbee
    coordinator or MQTT broker.

    Currently only mode="zigbee2mqtt" (via paho-mqtt) is implemented.
    Other modes return immediately with a "not yet implemented" log.
    """

    def __init__(self, config: Dict):
        zb_cfg = config.get("zigbee", {})
        self.enabled  = zb_cfg.get("enabled", False)
        self.mode     = zb_cfg.get("mode", "zigbee2mqtt")

        # zigbee2mqtt / MQTT settings
        self.mqtt_broker       = zb_cfg.get("mqtt_broker", "localhost")
        self.mqtt_port         = int(zb_cfg.get("mqtt_port", 1883))
        self.mqtt_topic_prefix = zb_cfg.get("mqtt_topic_prefix", "chirp")
        self.mqtt_username     = zb_cfg.get("mqtt_username", "")
        self.mqtt_password     = zb_cfg.get("mqtt_password", "")
        self.coordinator_port  = zb_cfg.get("coordinator_port", "/dev/ttyUSB0")

        self._client = None
        self._connected = False
        self._device_name = config.get("server_sync", {}).get("device_name", "chirp-device")

        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_stats: Dict = {}

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Connect to broker and start heartbeat. Returns True if enabled and connected."""
        if not self.enabled:
            logger.debug("Zigbee integration disabled (zigbee.enabled = false)")
            return False

        if self.mode == "zigbee2mqtt":
            return self._start_mqtt()
        elif self.mode == "deconz":
            logger.info("Zigbee deCONZ mode: not yet implemented — enable when ready")
            return False
        elif self.mode == "znp_direct":
            logger.info("Zigbee znp_direct mode: not yet implemented — enable when ready")
            return False
        else:
            logger.warning("Unknown Zigbee mode '%s' — integration disabled", self.mode)
            return False

    def stop(self):
        self._stop_event.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
        if self._client:
            try:
                self._publish_status(online=False)
                self._client.disconnect()
            except Exception:
                pass

    # ── Detection publishing ───────────────────────────────────────────────────

    def publish_detection(self, species: str, confidence: float,
                          recording_id: Optional[str] = None,
                          backend: str = "cpu") -> bool:
        """
        Publish a detection event. Call from watcher._on_detection().
        Returns True if published successfully.
        """
        if not self.enabled or not self._connected:
            return False

        payload = {
            "event":        "detection",
            "species":      species,
            "confidence":   round(confidence, 3),
            "timestamp":    datetime.now(timezone.utc).isoformat(),
            "device_name":  self._device_name,
            "backend":      backend,
        }
        if recording_id:
            payload["recording_id"] = recording_id

        return self._publish(
            f"{self.mqtt_topic_prefix}/detection",
            json.dumps(payload),
        )

    def update_stats(self, stats: Dict[str, Any]):
        """Update internal stats for heartbeat payload."""
        self._last_stats = dict(stats)

    # ── MQTT backend ───────────────────────────────────────────────────────────

    def _start_mqtt(self) -> bool:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.warning(
                "paho-mqtt not installed — Zigbee MQTT integration disabled. "
                "Install with: pip install paho-mqtt"
            )
            return False

        client_id = f"chirp-{self._device_name}"
        self._client = mqtt.Client(client_id=client_id, clean_session=True)

        if self.mqtt_username:
            self._client.username_pw_set(self.mqtt_username, self.mqtt_password or "")

        # Will message — published by broker if we disconnect ungracefully
        will_payload = json.dumps({
            "online": False,
            "device_name": self._device_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._client.will_set(
            f"{self.mqtt_topic_prefix}/status",
            will_payload,
            qos=1,
            retain=True,
        )

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                self._connected = True
                logger.info(
                    "Zigbee/MQTT connected to %s:%d (topic prefix: %s)",
                    self.mqtt_broker, self.mqtt_port, self.mqtt_topic_prefix,
                )
                self._publish_status(online=True)
            else:
                logger.warning("MQTT connection failed (rc=%d)", rc)

        def on_disconnect(client, userdata, rc):
            self._connected = False
            if rc != 0:
                logger.warning("MQTT disconnected unexpectedly (rc=%d), will retry", rc)

        self._client.on_connect    = on_connect
        self._client.on_disconnect = on_disconnect

        try:
            self._client.connect_async(self.mqtt_broker, self.mqtt_port, keepalive=60)
            self._client.loop_start()
        except Exception as e:
            logger.warning("MQTT connection error: %s", e)
            return False

        # Heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, name="ZigbeeHeartbeat", daemon=True
        )
        self._heartbeat_thread.start()
        logger.info(
            "Zigbee/MQTT integration started (broker: %s:%d)",
            self.mqtt_broker, self.mqtt_port,
        )
        return True

    def _publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> bool:
        if not self._client or not self._connected:
            return False
        try:
            result = self._client.publish(topic, payload, qos=qos, retain=retain)
            return result.rc == 0
        except Exception as e:
            logger.debug("MQTT publish error: %s", e)
            return False

    def _publish_status(self, online: bool = True):
        s = self._last_stats
        payload = {
            "online":          online,
            "device_name":     self._device_name,
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "triggers_today":  s.get("triggers", 0),
            "recordings":      s.get("recordings_completed", 0),
            "uploads_ok":      s.get("uploads_succeeded", 0),
            "cpu_temp_c":      s.get("cpu_temp_c"),
            "disk_free_gb":    s.get("disk_free_gb"),
        }
        self._publish(
            f"{self.mqtt_topic_prefix}/status",
            json.dumps(payload),
            qos=1,
            retain=True,
        )

    def _heartbeat_loop(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(60)  # publish status every minute
            if not self._stop_event.is_set() and self._connected:
                self._publish_status(online=True)
