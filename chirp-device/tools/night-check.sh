#!/usr/bin/env bash
# Overnight detection health check for a Chirp device.
#   bash ~/chirp-device/tools/night-check.sh            # last night (19:00 yesterday → now)
#   SINCE="2 days ago" bash ~/chirp-device/tools/night-check.sh
# Read-only: nothing is changed on the device.

# Install dir = this script's parent (~/chirp-device); bat events go to ~/chirp.
CHIRP_HOME="${CHIRP_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PY="${CHIRP_HOME}/venv/bin/python"
SINCE_IN="${SINCE:-yesterday 19:00}"
# journalctl can't parse "yesterday 19:00"; GNU date can.
SINCE=$(date -d "$SINCE_IN" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "$SINCE_IN")
UNIT=chirp-device
systemctl list-units --all --type=service 2>/dev/null | grep -q "^ *chirp.service" && UNIT=chirp
systemctl list-units --all --type=service 2>/dev/null | grep -q "chirp-device.service" && UNIT=chirp-device

hr() { printf '\n── %s ─────────────────────────────────────────\n' "$1"; }
J() { journalctl -u "$UNIT" --since "$SINCE" --no-pager -o short-iso "$@" 2>/dev/null; }

hr "Service"
echo "unit=$UNIT  home=$CHIRP_HOME  version=$(cat "$CHIRP_HOME/VERSION" 2>/dev/null)  since=$SINCE"
VER=$(cat "$CHIRP_HOME/VERSION" 2>/dev/null)
if [ -n "$VER" ] && [ "$(printf '%s\n1.3.1\n' "$VER" | sort -V | head -n1)" != "1.3.1" ]; then
    echo "!! version $VER is older than 1.3.1: the CPU location filter drops Barred Owl and other owls in autumn. Update this device."
fi
echo "running since: $(systemctl show "$UNIT" -p ActiveEnterTimestamp --value 2>/dev/null)  (a restart is needed after updating the code)"
echo "state=$(systemctl is-active "$UNIT")  restarts/started: $(systemctl show "$UNIT" -p NRestarts -p ActiveEnterTimestamp --value 2>/dev/null | paste -sd' ')"
if [ -d /var/log/journal ]; then
    echo "journal: persistent"
else
    echo "journal: VOLATILE — logs before the last boot ($(uptime -s)) are gone. Fix: sudo mkdir -p /var/log/journal && sudo systemctl restart systemd-journald"
fi

hr "Effective detection settings (config.yaml; server push overrides are in the 'Applied server config' lines below)"
cd "$CHIRP_HOME" && "$PY" - <<'EOF'
import yaml
c = yaml.safe_load(open("config.yaml"))
d, a = c.get("detection", {}), c.get("audio", {})
ef, bn = d.get("energy_filter", {}), d.get("birdnet", {})
print(f"gate {ef.get('threshold_db')} dB  band {ef.get('frequency_band_hz')} Hz")
print(f"gain {a.get('input_gain_db')} dB  backend {bn.get('backend')}  min_conf {bn.get('min_confidence')}  "
      f"sensitivity {bn.get('sensitivity')}  overlap {bn.get('overlap_seconds')} s")
print(f"xvf3800_output {c.get('respeaker', {}).get('xvf3800_output', 'raw')}  "
      f"bat detector {'on' if d.get('bat_echolocation', {}).get('enabled') else 'off'}")
EOF

hr "Location filter (1.3.1+ logs this once after each start)"
journalctl -u "$UNIT" --no-pager -o short-iso 2>/dev/null | grep "BirdNET location list" | tail -n 1 \
  || true
journalctl -u "$UNIT" --no-pager 2>/dev/null | grep -q "BirdNET location list" \
  || echo "no 'BirdNET location list' line: the running service predates 1.3.1, has no latitude/longitude, or uses Coral before 1.3.2"

hr "Server config pushes applied"
J | grep -E "Applied server config|Energy filter:|Audio gain|XVF3800|Backend changed" | tail -n 8

hr "Gate stats (every 10 min) — is p90 near or above the gate at night?"
# Older builds wrapped this line in two; -A1 keeps the level/gate half.
J | grep -A1 "Window stats" | grep -v "^--" | tail -n 40

hr "Dropped analysis windows (CPU can't keep up)"
J | grep -E "falling behind|backlog" | tail -n 5
echo "(none above = no drops or overlap cuts)"

hr "Night detections (owls, nightjars, rails, woodcock, bitterns)"
# Species names can sit on the line after "DETECTION" in older (wrapped) logs,
# so match the names themselves.
J | grep -iE "\b(owl|screech-owl|whip-poor-will|nighthawk|chuck-will|woodcock|night-heron|rail|sora|bittern)\b" \
  | grep -viE "yellowlegs" | tail -n 30
echo "detection events since $SINCE: $(J | grep -c 'DETECTION')"

hr "Warnings / errors"
J -p warning | grep -vE "Window stats" | cut -c1-200 | sort | uniq -c | sort -rn | head -n 15

hr "Coral"
ls /dev/apex_* 2>/dev/null || echo "no /dev/apex_* (M.2/PCIe Coral)"
lsusb 2>/dev/null | grep -Ei "1a6e:089a|18d1:9302" || echo "no USB Coral"
J | grep -E "BirdNET backend|configured for .* but running|Coral" | tail -n 5

hr "Microphones"
lsusb 2>/dev/null | grep -viE "hub|root" 
arecord -l 2>/dev/null | grep -E "^card"
J | grep -iE "ReSpeaker|Using audio|stream active|audio device|mic" | tail -n 6

hr "ReSpeaker XVF3800"
lsusb 2>/dev/null | grep -iE "2886:|20b1:" || echo "no Seeed/XMOS USB device on the bus"
"$PY" -m chirp.xvf3800 status 2>/dev/null || echo "chirp.xvf3800 not available (device < 1.2.30)"
ls -l /etc/udev/rules.d/99-chirp-respeaker.rules 2>/dev/null || echo "udev rule missing — rerun install.sh for USB control as $(whoami)"

hr "CPU, temperature, throttling"
uptime
command -v vcgencmd >/dev/null && { vcgencmd measure_temp; vcgencmd get_throttled; }
ps -o pid,pcpu,pmem,etime,cmd -C python3,python 2>/dev/null | grep -E "PID|main.py" | cut -c1-150
echo "get_throttled: 0x0 = never throttled; bit 0/2 = under-voltage/throttled now; bit 16/18 = happened since boot"

hr "Disk"
df -h "$CHIRP_HOME" | tail -n 1
du -sh "$HOME/chirp" 2>/dev/null | sed 's/^/bat recordings (~\/chirp): /'

hr "Next step"
echo "Have a clip another recorder caught that this device missed? Copy it here and run:"
echo "  $PY $CHIRP_HOME/tools/check-file.py clip.wav --when \"YYYY-MM-DD HH:MM\""
echo "It runs the clip through this device's gate, BirdNET backend and location filter and says where the call is lost."
