#!/usr/bin/env bash
# =============================================================================
# Chirp Installation Script for Raspberry Pi 5
# Raspberry Pi OS (64-bit, Bookworm) — Python 3.11+
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
#
# What this does:
#   1. Updates system packages
#   2. Installs system audio libraries (libsndfile, portaudio, ALSA)
#   3. Installs Python dependencies
#   4. Downloads BirdNET model (via birdnetlib auto-download)
#   5. Creates directories and adjusts permissions
#   6. Installs systemd service for auto-start
#   7. Runs a quick self-test
# =============================================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Config ────────────────────────────────────────────────────────────────────
# Paths — use the directory the script lives in, never hardcode /home/pi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHIRP_HOME="${SCRIPT_DIR}"
RECORDINGS_DIR="${CHIRP_HOME}/recordings"
LOGS_DIR="${CHIRP_HOME}/logs"
MODELS_DIR="${CHIRP_HOME}/models"
SERVICE_NAME="chirp-device"
PYTHON_BIN="python3"
VENV_DIR="${CHIRP_HOME}/venv"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║              Chirp Installation Script              ║"
echo "║          Raspberry Pi 5 Bird Call Detection             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Check running as correct user ─────────────────────────────────────────────
if [ "$EUID" -eq 0 ]; then
    error "Do not run as root. Run as your normal user: ./install.sh"
    exit 1
fi

CURRENT_USER=$(whoami)
info "Installing as user: ${CURRENT_USER}"
info "Chirp home: ${CHIRP_HOME}"
echo ""

# ── Step 1: System packages ───────────────────────────────────────────────────
info "Step 1/9: Updating system packages..."
sudo apt-get update -qq

# ── Purge broken gasket-dkms state if present ─────────────────────────────────
# gasket-dkms 1.0-18 from the Coral apt repo fails to build on kernel 6.12+ and
# leaves dpkg in a broken state that causes ALL apt-get install calls to fail.
# Purge it here so system package installs below succeed cleanly.
# The correct gasket driver will be built from source by install-coral.sh.
_purge_broken_gasket() {
    # Check for half-configured, failed, or broken state (iF, hF, uF flags)
    if dpkg -l gasket-dkms 2>/dev/null | grep -qE "^(iF|hF|uF|.F)"; then
        warn "gasket-dkms is in a broken dpkg state — purging before apt install..."
        sudo dpkg --purge --force-all gasket-dkms 2>/dev/null || true
        sudo apt-get -f install -y 2>/dev/null || true
        success "Broken gasket-dkms cleared."
    elif dpkg -l gasket-dkms 2>/dev/null | grep -q "^ii"; then
        local inst_ver
        inst_ver=$(dpkg -l gasket-dkms 2>/dev/null | awk '/^ii/{print $3}')
        if [[ "${inst_ver}" == "1.0-18" ]]; then
            warn "gasket-dkms 1.0-18 (incompatible with kernel 6.12+) — purging..."
            sudo dpkg --purge --force-all gasket-dkms 2>/dev/null || true
            sudo apt-get -f install -y 2>/dev/null || true
            success "Old gasket-dkms purged. Run install-coral.sh to build from source."
        fi
    fi
}
_purge_broken_gasket

info "Installing system audio libraries..."
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    libportaudio2 \
    libportaudiocpp0 \
    portaudio19-dev \
    libsndfile1 \
    libsndfile1-dev \
    ffmpeg \
    alsa-utils \
    alsa-tools \
    libasound2-dev \
    libffi-dev \
    libopenblas-dev \
    git \
    curl \
    jq \
    libcairo2-dev \
    gir1.2-glib-2.0 \
    pkg-config \
    meson \
    ninja-build

success "System packages installed."
echo ""

# bluezero (for Bluetooth-based first-time setup, requirements.txt line
# ~56) needs PyGObject, which needs pycairo, which needs to COMPILE
# against these native libs — found the hard way: pip install failed
# on a real device with "Dependency 'cairo' not found (tried
# pkg-config)" because this package was never in the apt list above,
# only the ones bluezero's OWN direct deps obviously needed. The one
# piece genuinely uncertain across Debian releases is the
# GObject-Introspection dev package's name — genuinely not a simple
# rename, found the hard way from a live build log: PyGObject 3.50.2's
# meson build looks specifically for the pkg-config file
# gobject-introspection-1.0.pc, which on Debian 13 (trixie) is shipped
# by the NO-hyphen package libgirepository1.0-dev — a separate,
# still-existing package from the newer, hyphenated
# libgirepository-2.0-dev (that one ships GIRepository 2.0's own
# headers, a different library, not this compat file). The first
# version of this fix used || between the two — which meant that once
# libgirepository-2.0-dev installed successfully (it does exist on
# trixie), the actual package PyGObject needed never got installed at
# all, since || only runs its second half on FAILURE. Installs both,
# unconditionally, each with its own non-fatal warning — not an
# either/or.
info "Installing GObject-Introspection dev packages..."
sudo apt-get install -y libgirepository1.0-dev \
    || warn "Could not install libgirepository1.0-dev — this is the one PyGObject 3.50.x's build specifically needs (ships gobject-introspection-1.0.pc). Not fatal: only Bluetooth-based first-time setup needs PyGObject at all, chirp-device itself works fine without it."
sudo apt-get install -y libgirepository-2.0-dev \
    || warn "Could not install libgirepository-2.0-dev — some PyGObject versions also want this one. Not fatal for the same reason as above."
echo ""

# ── Step 2: Check USB audio devices ──────────────────────────────────────────
info "Step 2/9: Checking for USB audio devices..."
USB_AUDIO=$(arecord -l 2>/dev/null | grep -i "usb\|microphone" || true)
if [ -n "$USB_AUDIO" ]; then
    success "USB audio device(s) found:"
    echo "$USB_AUDIO" | sed 's/^/  /'
else
    warn "No USB audio devices detected. Connect your microphones and re-run if needed."
    warn "You can continue installation and plug in mics later."
fi
echo ""

# ── Step 3: Create directories ────────────────────────────────────────────────
info "Step 3/9: Creating directories..."
mkdir -p "${RECORDINGS_DIR}"
mkdir -p "${LOGS_DIR}"
mkdir -p "${MODELS_DIR}"
mkdir -p "${MODELS_DIR}/coral"

success "Directories created."
echo ""

# ── Step 4: Python virtual environment ───────────────────────────────────────
info "Step 4/9: Setting up Python virtual environment..."
if [ ! -d "${VENV_DIR}" ]; then
    ${PYTHON_BIN} -m venv "${VENV_DIR}"
    success "Created virtual environment at ${VENV_DIR}"
else
    info "Virtual environment already exists at ${VENV_DIR}"
fi

# Activate venv
source "${VENV_DIR}/bin/activate"

info "Upgrading pip, setuptools, wheel..."
pip install --upgrade pip setuptools wheel --quiet

info "Installing Python dependencies (this may take several minutes)..."
# Install from requirements.txt — the actual source of truth for this
# project's dependencies — rather than a separately hand-maintained list.
# A hand-typed list here previously existed alongside requirements.txt and
# silently drifted out of sync with it: luma.oled, smbus2, Pillow (all three
# needed for the OLED display) and pyusb (ReSpeaker LED control) were
# correctly declared in requirements.txt but never made it into the
# hand-typed list, so a fresh install would log "OLED disabled — luma.oled
# not installed" forever and the OLED would only ever show the Argon ONE's
# own default content, with nothing in the logs pointing at install.sh as
# the actual cause. There is now exactly one place dependencies are listed.
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"
if [ ! -f "${REQUIREMENTS_FILE}" ]; then
    error "requirements.txt not found at ${REQUIREMENTS_FILE} — cannot continue."
    exit 1
fi
pip install --upgrade -r "${REQUIREMENTS_FILE}"

success "Python dependencies installed."
echo ""

# ReSpeaker USB control (LED ring, XVF3800 raw-mic routing) runs as the
# service user, which needs read/write on the Seeed USB device.
UDEV_RULE=/etc/udev/rules.d/99-chirp-respeaker.rules
if [ ! -f "${UDEV_RULE}" ]; then
    info "Adding udev rule for ReSpeaker USB control (vendor 2886)..."
    echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="2886", MODE="0664", GROUP="plugdev"' | sudo tee "${UDEV_RULE}" >/dev/null
    sudo usermod -aG plugdev "$(whoami)" || true
    sudo udevadm control --reload-rules && sudo udevadm trigger || true
fi

# Keep the service log across reboots (Raspberry Pi OS keeps it in RAM by
# default), so overnight detection checks still work after a restart.
if [ ! -d /var/log/journal ]; then
    info "Making the systemd journal persistent..."
    sudo mkdir -p /var/log/journal
    sudo systemd-tmpfiles --create --prefix /var/log/journal || true
    sudo systemctl restart systemd-journald || true
fi

# ── Step 5: Download BirdNET model ────────────────────────────────────────────
info "Step 5/9: Patching birdnetlib for Python 3.12+/aarch64 and pre-loading model..."

# birdnetlib 0.18.x tries: tflite_runtime → tensorflow → (no ai-edge-litert fallback yet)
# Neither tflite_runtime nor tensorflow has Python 3.12+/aarch64 wheels on PyPI.
# ai-edge-litert is Google's official replacement and has full 3.13/aarch64 support.
# Fix: install ai-edge-litert, then create a tflite_runtime shim package in the venv
# so birdnetlib's import resolves correctly without touching its source.

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
NEEDS_SHIM=false
case "$PY_VER" in
    3.9|3.10|3.11)
        # tflite-runtime has wheels for these — try it first
        if ! pip show tflite-runtime &>/dev/null 2>&1; then
            pip install --quiet "tflite-runtime>=2.14.0" 2>/dev/null &&                 success "tflite-runtime installed." || NEEDS_SHIM=true
        fi ;;
    *)
        # 3.12+ — no tflite-runtime wheels; go straight to ai-edge-litert
        NEEDS_SHIM=true ;;
esac

if $NEEDS_SHIM; then
    info "Python ${PY_VER}: installing ai-edge-litert + tflite_runtime shim..."
    pip install --quiet "ai-edge-litert>=1.1.0" || {
        warn "ai-edge-litert install failed — BirdNET inference may not work."
    }

    # Create a tflite_runtime shim package that forwards to ai_edge_litert.
    # This makes birdnetlib's  `import tflite_runtime.interpreter as tflite`  work.
    SITE_PACKAGES=$(python3 -c "import site; print(site.getsitepackages()[0])" 2>/dev/null ||                     python3 -c "import sysconfig; print(sysconfig.get_path('purelib'))")
    SHIM_DIR="${SITE_PACKAGES}/tflite_runtime"
    if [ ! -d "$SHIM_DIR" ]; then
        mkdir -p "$SHIM_DIR"
        cat > "${SHIM_DIR}/__init__.py" << 'SHIM'
# tflite_runtime compatibility shim — forwards to ai_edge_litert
# Created by Chirp install.sh for Python 3.12+ / aarch64
try:
    from ai_edge_litert import *  # noqa: F401, F403
except ImportError:
    pass
SHIM
        cat > "${SHIM_DIR}/interpreter.py" << 'SHIM'
# tflite_runtime.interpreter compatibility shim
from ai_edge_litert.interpreter import Interpreter, load_delegate  # noqa: F401
SHIM
        success "tflite_runtime shim created at ${SHIM_DIR}"
    else
        info "tflite_runtime shim already present."
    fi
fi

# Pre-download BirdNET model
${PYTHON_BIN} -c "
import sys
try:
    from birdnetlib.analyzer import Analyzer
    print('  Loading BirdNET model (downloading if needed)...')
    a = Analyzer()
    print('  BirdNET model ready.')
except Exception as e:
    print(f'  WARNING: Could not pre-load BirdNET model: {e}')
    print('  Model will download on first run.')
    sys.exit(0)
"

success "BirdNET model ready."
echo ""

# ── Step 6: ALSA configuration for dual USB mics (optional) ──────────────────
info "Step 6/9: Configuring audio settings..."

# Add pi user to audio group if not already
if ! groups "$CURRENT_USER" | grep -q audio; then
    sudo usermod -aG audio "$CURRENT_USER"
    warn "Added ${CURRENT_USER} to 'audio' group. You may need to log out and back in."
fi
# Add to i2c group for OLED display access
if getent group i2c &>/dev/null; then
    if ! groups "$CURRENT_USER" | grep -q i2c; then
        sudo usermod -aG i2c "$CURRENT_USER"
        warn "Added ${CURRENT_USER} to 'i2c' group (needed for OLED display)."
    fi
fi

# Set USB mic as default ALSA device (if USB audio detected)
CARD_NUM=$(arecord -l 2>/dev/null | grep -i "usb" | head -1 | grep -oP 'card \K[0-9]+' || echo "")
if [ -n "$CARD_NUM" ]; then
    info "Setting USB audio card $CARD_NUM as default ALSA input..."
    cat > "${HOME}/.asoundrc" << EOF
# Chirp ALSA configuration
# Generated by install.sh
defaults.pcm.card ${CARD_NUM}
defaults.ctl.card ${CARD_NUM}
EOF
    success "ALSA configured to prefer USB audio card ${CARD_NUM}"
else
    info "ALSA default unchanged (no USB card detected yet)"
fi

echo ""

# ── Step 7: Hand the OLED over from the Argon ONE's own software ─────────────
info "Step 7/9: Checking for the Argon ONE's own OLED service..."

# The Argon ONE v5 Industria case ships with its own setup script
# (curl https://download.argon40.com/argon1v5.sh | bash) which installs
# "argononed.service" — a daemon that controls the OLED *and* the power
# button. If it's running, it fights Chirp's own display.py for control of
# the same physical screen, and (per reports) tends to win, so Chirp's
# custom pages never actually show — just the Argon default (IP/CPU temp/etc).
#
# Note for the Argon ONE v5 specifically: the fan is controlled by the Pi's
# own kernel thermal governor, NOT by argononed over I2C (that's only true
# of the older v1-v3 Argon ONE cases). So stopping argononed on a v5 does
# NOT affect cooling. What it DOES lose: the case's physical power button
# (single-press reboot / long-press shutdown) stops working, since that's
# also handled by this same daemon. Chirp's own GPIO 27 OLED page-button
# is unaffected either way (separate pin, handled entirely by display.py).
ARGON_SERVICE=""
for candidate in argononed argoneon; do
    if systemctl list-unit-files 2>/dev/null | grep -q "^${candidate}\.service"; then
        ARGON_SERVICE="${candidate}"
        break
    fi
done

if [ -n "${ARGON_SERVICE}" ]; then
    warn "Found ${ARGON_SERVICE}.service (Argon ONE's own OLED/power-button daemon)."
    warn "Stopping and disabling it so Chirp's display.py can take over the OLED."
    warn "Trade-off: the case's physical power button (press to reboot/shutdown)"
    warn "will stop working. Cooling is unaffected — the Argon ONE v5's fan is"
    warn "controlled by the Pi's kernel thermal governor, not by this daemon."
    sudo systemctl stop "${ARGON_SERVICE}" 2>/dev/null || true
    sudo systemctl disable "${ARGON_SERVICE}" 2>/dev/null || true
    success "Argon ONE OLED service disabled — Chirp's display.py now has sole control of the screen."
else
    info "No Argon ONE OLED service found (not installed, or already removed) — nothing to do."
fi
echo ""

# ── Step 8: Tailscale (optional) ───────────────────────────────────────────────
info "Step 8/9: Installing Tailscale client (optional remote access)..."
if command -v tailscale &> /dev/null; then
    info "Tailscale already installed — skipping (run 'sudo tailscale up' yourself, or configure tailscale: in config.yaml to have chirp-device manage the connection)."
else
    # Only INSTALLS the client here — never authenticates or connects.
    # A freshly-installed, never-activated tailscale binary is inert and
    # harmless, so this always runs regardless of whether the person
    # plans to use it, the same way every other optional dependency in
    # this script is installed unconditionally. Actual connection is
    # handled at runtime by chirp/tailscale_manager.py, driven entirely
    # by config.yaml's own tailscale.enabled flag — never by this
    # script — since that needs a real auth key (and, for a
    # self-hosted Headscale instance, a login_server URL) that only the
    # person running this install actually has.
    if curl -fsSL https://tailscale.com/install.sh | sh; then
        # tailscaled only lets root (or an explicitly granted
        # "operator") control it — found the hard way: chirp-device
        # runs as $CURRENT_USER, not root, so its own automatic
        # `tailscale up` call failed with "Access denied: checkprefs"
        # on every attempt until this was set. Safe to set before any
        # login/auth has happened — it's a standing daemon permission,
        # not tied to being connected to any particular tailnet yet.
        sudo tailscale set --operator="$CURRENT_USER" 2>/dev/null || true
        info "Tailscale client installed (chirp-device's own user granted operator permission, so it can manage the connection without sudo). To actually connect, set tailscale.enabled: true (and your own auth_key — and login_server if using a self-hosted Headscale instance instead of Tailscale's own service) in config.yaml, then restart the chirp-device service."
    else
        info "Tailscale install failed or was skipped — not fatal, chirp-device works fully without it. Install manually later if you want it: https://tailscale.com/download"
    fi
fi
echo ""

# ── Step 9: Systemd service ───────────────────────────────────────────────────
info "Step 9/9: Installing systemd service..."

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

sudo tee "${SERVICE_FILE}" > /dev/null << EOF
[Unit]
Description=Chirp - Automated Bird Call Detection
After=network.target sound.target
Wants=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${CHIRP_HOME}
ExecStart=${VENV_DIR}/bin/python ${CHIRP_HOME}/main.py --config ${CHIRP_HOME}/config.yaml
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=chirp

# Give audio and I2C access (I2C needed for OLED display)
SupplementaryGroups=audio i2c

# Resource limits
CPUQuota=80%
MemoryMax=1G

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
success "Systemd service installed: ${SERVICE_NAME}"
echo ""

# ── Self-Test ─────────────────────────────────────────────────────────────────
info "Running quick self-test..."
${PYTHON_BIN} -c "
import sounddevice as sd
import numpy as np
import soundfile
import scipy.signal
import birdnetlib
import yaml
import requests
import psutil
print('  Core imports OK')
devices = [d for d in sd.query_devices() if d['max_input_channels'] > 0]
print(f'  Input devices found: {len(devices)}')
usb_devs = [d for d in devices if 'USB' in d['name'] or 'Microphone' in d['name']]
print(f'  USB/Microphone devices: {len(usb_devs)}')

# OLED display stack — checked explicitly because a missing piece here
# doesn't crash anything; display.py degrades silently to 'OLED disabled'
# and logs it once at startup, easy to miss. A previous version of this
# script installed from a hand-typed package list that didn't include
# these, so the import succeeding here is the actual confirmation the
# OLED will work — not just that install.sh ran without error.
try:
    import luma.oled, smbus2
    from PIL import ImageFont
    print('  OLED display imports OK (luma.oled, smbus2, Pillow)')
except ImportError as e:
    print(f'  WARNING: OLED display import failed: {e}')
    print('  The OLED will silently show only the case\'s own default content.')
    print('  Re-run: pip install -r requirements.txt (inside the venv)')
"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                Installation Complete!                   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Next steps (full guide: https://ourchirp.com/setup.html):"
echo ""
echo "  1. Edit config.yaml to set your preferences:"
echo "     nano ${CHIRP_HOME}/config.yaml"
echo ""
echo "  2. Test audio levels:"
echo "     source ${VENV_DIR}/bin/activate"
echo "     python main.py --test-audio"
echo ""
echo "  3. Test detection (doesn't record):"
echo "     python main.py --test-detection"
echo ""
echo "  4. Start Chirp:"
echo "     python main.py              # foreground"
echo "     sudo systemctl start chirp-device   # as a service"
echo ""
echo "  5. View logs:"
echo "     journalctl -u chirp-device -f"
echo "     tail -f ${LOGS_DIR}/chirp.log"
echo ""
echo "  6. When server is ready, edit config.yaml:"
echo "     upload:"
echo "       enabled: true"
echo "       server_url: 'https://your-server/api/recordings'"
echo "       api_key: 'your-api-key'"
echo ""
echo "  For Coral USB Accelerator (optional, ~10x faster):"
echo "     ./install-coral.sh"
echo ""
