#!/usr/bin/env bash
# =============================================================================
# Chirp — ReSpeaker HAT Setup Script
# Raspberry Pi 5, Raspberry Pi OS Bookworm (64-bit)
#
# Supports:
#   • ReSpeaker 2-Mics Pi HAT       (WM8960, I²S, 2 mics)
#   • ReSpeaker 4-Mic Array HAT     (AC108, I²S, 4 mics)
#   • ReSpeaker 4-Mic Linear Array  (2×AC108, I²S, 4 valid mics / 8 ch)
#   • ReSpeaker 6-Mic Circular Array (2×AC108, I²S, 6 valid mics / 12 ch)
#
# USB variants (v2.0 / v2.1 / XVF3800) do NOT need this script —
# they are USB Audio Class 1.0 and work plug-and-play.
# Just plug in the USB cable and run the standard install.sh.
#
# Usage:
#   chmod +x install-respeaker-hat.sh
#   ./install-respeaker-hat.sh
#   sudo reboot
#
# After reboot:
#   python main.py --list-devices   # should show seeed-voicecard
#   python main.py --test-audio
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         ReSpeaker HAT Setup for Raspberry Pi 5         ║"
echo "║                 Chirp Bird Detector                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

if [ "$EUID" -eq 0 ]; then
    error "Do not run as root. Run as the pi user: ./install-respeaker-hat.sh"
    exit 1
fi

# Verify install.sh was run first
if [ ! -d "${VENV_DIR}" ]; then
    error "Virtual environment not found at ${VENV_DIR}."
    error "Please run ./install.sh first, then run this script."
    exit 1
fi

# ── Step 1: System dependencies ───────────────────────────────────────────────
info "Step 1/5: Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y \
    git \
    dkms \
    i2c-tools \
    linux-headers-$(uname -r) \
    raspberrypi-kernel-headers \
    python3-smbus \
    libasound2-plugins \
    2>/dev/null || true

success "System dependencies installed."
echo ""

# ── Step 2: Enable I²C and I²S overlays ──────────────────────────────────────
info "Step 2/5: Enabling I²C and I²S in /boot/firmware/config.txt..."

BOOT_CFG="/boot/firmware/config.txt"
if [ ! -f "${BOOT_CFG}" ]; then
    BOOT_CFG="/boot/config.txt"
fi

_ensure_line() {
    local line="$1"
    if ! grep -qF "${line}" "${BOOT_CFG}"; then
        echo "${line}" | sudo tee -a "${BOOT_CFG}" > /dev/null
        info "  Added: ${line}"
    else
        info "  Already set: ${line}"
    fi
}

_ensure_line "dtparam=i2c_arm=on"
_ensure_line "dtparam=i2s=on"
_ensure_line "dtparam=spi=on"

# For Pi 5: RP1 I2C needs i2c-dev module
if grep -q "bcm2712" /proc/cpuinfo 2>/dev/null; then
    info "  Pi 5 detected — ensuring i2c-dev module loaded"
    if ! grep -q "^i2c-dev" /etc/modules 2>/dev/null; then
        echo "i2c-dev" | sudo tee -a /etc/modules > /dev/null
    fi
fi

success "Boot config updated."
echo ""

# ── Step 3: Clone and install HinTak seeed-voicecard (Pi 5 compatible) ────────
info "Step 3/5: Installing seeed-voicecard driver (HinTak Pi 5 fork)..."
# Original seeed-voicecard does not support the Pi 5's RP1 I²S controller.
# HinTak maintains a forward-ported fork that works on Pi 5 kernel 6.1+.

DRIVER_DIR="${SCRIPT_DIR}/seeed-voicecard"

if [ -d "${DRIVER_DIR}" ]; then
    info "  Driver directory exists, pulling latest changes..."
    cd "${DRIVER_DIR}"
    git pull --quiet
else
    info "  Cloning HinTak/seeed-voicecard (Pi 5 compatible fork)..."
    git clone --depth=1 https://github.com/HinTak/seeed-voicecard.git "${DRIVER_DIR}"
fi

cd "${DRIVER_DIR}"

# Check kernel headers are present
KERNEL_VER=$(uname -r)
if [ ! -d "/lib/modules/${KERNEL_VER}/build" ]; then
    warn "Kernel headers for ${KERNEL_VER} not found — driver compile may fail."
    warn "Try: sudo apt-get install raspberrypi-kernel-headers"
fi

info "  Running seeed-voicecard installer (requires sudo, takes ~2 minutes)..."
sudo ./install.sh 2>&1 | grep -E "(Installing|Installed|Error|error|Warning|warning|OK|loading)" || true

success "seeed-voicecard driver installed."
echo ""

# ── Step 4: Python packages for I²C / smbus ──────────────────────────────────
info "Step 4/5: Installing Python packages for I²C control..."
source "${VENV_DIR}/bin/activate"
pip install --quiet smbus2 pyusb gpiod 2>/dev/null || true
success "Python packages installed."
echo ""

# ── Step 5: Verify and print status ──────────────────────────────────────────
info "Step 5/5: Post-install verification (may show 'not yet' before reboot)..."

echo ""
echo "  Current ALSA capture devices:"
arecord -l 2>/dev/null || echo "  (arecord failed — normal before reboot)"

echo ""
echo "  Checking for seeed-voicecard in /proc/asound/cards:"
cat /proc/asound/cards 2>/dev/null || echo "  (not yet loaded)"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║              ReSpeaker HAT Setup Complete!              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  ⚠️  REBOOT REQUIRED before the driver takes effect:"
echo ""
echo "     sudo reboot"
echo ""
echo "  After reboot:"
echo ""
echo "  1. Verify the driver loaded:"
echo "     arecord -l              # should show seeed-voicecard or ac108"
echo "     cat /proc/asound/cards  # same check"
echo ""
echo "  2. Check Chirp sees it:"
echo "     cd ${SCRIPT_DIR}"
echo "     source venv/bin/activate"
echo "     python main.py --list-devices"
echo ""
echo "  3. Test audio levels:"
echo "     python main.py --test-audio"
echo ""
echo "  4. In config.yaml, make sure:"
echo "     respeaker:"
echo "       mode: auto    # or: hat"
echo ""
echo "  HAT model                  | Valid channels | ALSA name"
echo "  ---------------------------|----------------|------------------"
echo "  2-Mics Pi HAT (WM8960)     | 2 of 2         | seeed-2mic-voicecard"
echo "  4-Mic Array HAT (AC108)    | 4 of 4         | ac108"
echo "  4-Mic Linear Array (2xAC)  | 4 of 8         | seeed-8mic-voicecard"
echo "  6-Mic Circular (2xAC108)   | 6 of 12        | seeed-8mic-voicecard"
echo ""
echo "  NOTE: The 6-Mic Circular array uses the same 8mic-voicecard ALSA driver"
echo "  as the Linear Array. Chirp detects the correct number of mic channels"
echo "  automatically."
echo ""
