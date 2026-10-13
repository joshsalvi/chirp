#!/usr/bin/env bash
# =============================================================================
# fix-gasket.sh — Fix Coral M.2 gasket driver for Raspberry Pi 5 kernel 6.12+
#
# Problem: The Coral apt package (gasket-dkms 1.0-18) fails to build on
# Pi OS kernel 6.12+ with "error exit status 10". The upstream google/gasket-driver
# also has issues on 6.12 unless a one-line patch is applied.
#
# This script tries three methods in order (most reliable first):
#   1. jnicolson/gasket-builder  — pre-patched, confirmed working on 6.12
#   2. google/gasket-driver      — upstream with inline 6.12 patch applied
#   3. Roberts/gasket-driver     — community maintained fork as final fallback
#
# Usage:
#   chmod +x fix-gasket.sh && ./fix-gasket.sh
#   sudo reboot   (then check: ls /dev/apex_*)
#
# After working:
#   Edit config.yaml → detection.birdnet.backend: "coral"
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

RUNNING_KERNEL="$(uname -r)"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         Coral M.2 Gasket Driver Fix — Pi 5             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
info "Running kernel: ${RUNNING_KERNEL}"
echo ""

# ── Sanity: check PCIe config.txt entries ────────────────────────────────────
BOOT_CFG="/boot/firmware/config.txt"
[ -f "$BOOT_CFG" ] || BOOT_CFG="/boot/config.txt"

info "Checking /boot/firmware/config.txt for required PCIe entries..."
MISSING_CFG=()
grep -qF "dtparam=pciex1" "$BOOT_CFG" 2>/dev/null || MISSING_CFG+=("dtparam=pciex1")
grep -qF "kernel=kernel8.img" "$BOOT_CFG" 2>/dev/null || MISSING_CFG+=("kernel=kernel8.img")

if [ ${#MISSING_CFG[@]} -gt 0 ]; then
    warn "The following lines are missing from ${BOOT_CFG}:"
    for line in "${MISSING_CFG[@]}"; do
        warn "  $line"
        echo "$line" | sudo tee -a "$BOOT_CFG" > /dev/null
        info "  → Added: $line"
    done
    # Also add Pi 5 PCIe compat overlay if not present
    grep -qF "pciex1-compat-pi5" "$BOOT_CFG" 2>/dev/null || {
        echo "dtoverlay=pciex1-compat-pi5,no-mip" | sudo tee -a "$BOOT_CFG" > /dev/null
        info "  → Added: dtoverlay=pciex1-compat-pi5,no-mip"
    }
else
    success "config.txt PCIe entries look good."
fi
echo ""

# ── Step 1: Purge broken apt package ─────────────────────────────────────────
info "Step 1/5: Purging broken gasket-dkms apt package (if present)..."
sudo dkms remove gasket/1.0 --all 2>/dev/null || true
sudo dpkg --purge --force-all gasket-dkms 2>/dev/null || true
sudo apt-get -f install -y 2>/dev/null || true
success "Purge complete."
echo ""

# ── Step 2: Install kernel headers ───────────────────────────────────────────
info "Step 2/5: Installing kernel headers for ${RUNNING_KERNEL}..."
sudo apt-get install -y --no-install-recommends \
    dkms git build-essential \
    raspberrypi-kernel-headers 2>/dev/null || true

if [ ! -d "/lib/modules/${RUNNING_KERNEL}/build" ]; then
    sudo apt-get install -y "linux-headers-${RUNNING_KERNEL}" 2>/dev/null || true
fi

if [ ! -d "/lib/modules/${RUNNING_KERNEL}/build" ]; then
    error "Kernel headers not found. Try: sudo rpi-update && sudo reboot"
    exit 1
fi
success "Headers present at /lib/modules/${RUNNING_KERNEL}/build"
echo ""

# ── Step 3: Build driver (jnicolson/gasket-builder — best for 6.12) ──────────
info "Step 3/5: Building gasket driver (jnicolson/gasket-builder)..."
info "  Source: https://github.com/jnicolson/gasket-builder"
info "  This fork is pre-patched for kernel 6.12+ and confirmed working on Pi 5."

BUILD_FAILED=false
GASKET_SRC="/tmp/gasket-builder-src"
rm -rf "$GASKET_SRC"

if git clone --depth=1 https://github.com/jnicolson/gasket-builder.git "$GASKET_SRC" 2>/dev/null; then
    cd "$GASKET_SRC"

    # gasket-builder produces a .deb via make or a build script
    if [ -f "Makefile" ]; then
        make KERNEL_VERSION="${RUNNING_KERNEL}" 2>&1 | tail -5 && \
            DEB_FILE=$(ls *.deb 2>/dev/null | head -1) && \
            [ -n "$DEB_FILE" ] && sudo dpkg -i "$DEB_FILE" && \
            success "gasket-builder .deb installed: $DEB_FILE" || BUILD_FAILED=true
    elif [ -f "build.sh" ]; then
        bash build.sh 2>&1 | tail -5 && \
            DEB_FILE=$(ls *.deb 2>/dev/null | head -1) && \
            [ -n "$DEB_FILE" ] && sudo dpkg -i "$DEB_FILE" && \
            success "gasket-builder .deb installed: $DEB_FILE" || BUILD_FAILED=true
    else
        # Direct dkms approach from gasket-builder
        GASKET_VER=$(grep "^PACKAGE_VERSION" src/dkms.conf 2>/dev/null \
            | cut -d= -f2 | tr -d '"' | tr -d ' ' || echo "1.0")
        sudo dkms remove "gasket/${GASKET_VER}" --all 2>/dev/null || true
        DKMS_SRC="/usr/src/gasket-${GASKET_VER}"
        sudo rm -rf "$DKMS_SRC"
        sudo mkdir -p "$DKMS_SRC"
        sudo cp -r src/* "$DKMS_SRC/"
        sudo dkms add "gasket/${GASKET_VER}" && \
        sudo dkms build -k "${RUNNING_KERNEL}" "gasket/${GASKET_VER}" && \
        sudo dkms install -k "${RUNNING_KERNEL}" "gasket/${GASKET_VER}" --force && \
            success "gasket/${GASKET_VER} installed via dkms" || BUILD_FAILED=true
    fi
    cd ~
else
    warn "Could not clone jnicolson/gasket-builder. Trying google/gasket-driver..."
    BUILD_FAILED=true
fi

# ── Step 3b: Fallback — google/gasket-driver with 6.12 patch ─────────────────
if $BUILD_FAILED; then
    warn "jnicolson method failed. Trying google/gasket-driver with inline 6.12 patch..."
    BUILD_FAILED=false
    GASKET_SRC="/tmp/gasket-driver-src"
    rm -rf "$GASKET_SRC"

    if git clone --depth=1 https://github.com/google/gasket-driver.git "$GASKET_SRC" 2>/dev/null; then
        cd "$GASKET_SRC"

        # Apply 6.12 kernel fix: comment out pci_enable_pcie_error_reporting call
        # This function was removed in kernel 6.5; its presence causes build failure
        CORE_C="src/gasket_core.c"
        if grep -q "pci_enable_pcie_error_reporting" "$CORE_C"; then
            info "Applying kernel 6.12 patch to gasket_core.c..."
            sed -i 's/.*pci_enable_pcie_error_reporting.*$/\/\/ PATCHED: pci_enable_pcie_error_reporting removed in kernel 6.5/' "$CORE_C"
            success "Patch applied."
        fi

        GASKET_VER=$(grep "^PACKAGE_VERSION" src/dkms.conf 2>/dev/null \
            | cut -d= -f2 | tr -d '"' | tr -d ' ' || echo "1.0")
        sudo dkms remove "gasket/${GASKET_VER}" --all 2>/dev/null || true
        DKMS_SRC="/usr/src/gasket-${GASKET_VER}"
        sudo rm -rf "$DKMS_SRC"
        sudo mkdir -p "$DKMS_SRC"
        sudo cp -r src/* "$DKMS_SRC/"
        sudo dkms add "gasket/${GASKET_VER}" 2>/dev/null || true
        sudo dkms build -k "${RUNNING_KERNEL}" "gasket/${GASKET_VER}" && \
        sudo dkms install -k "${RUNNING_KERNEL}" "gasket/${GASKET_VER}" --force && \
            success "gasket/${GASKET_VER} installed (google upstream + patch)" || BUILD_FAILED=true
        cd ~
    else
        warn "Could not clone google/gasket-driver either. Trying robertzaage fork..."
        BUILD_FAILED=true
    fi
fi

# ── Step 3c: Final fallback — community maintained fork ───────────────────────
if $BUILD_FAILED; then
    warn "Trying robertzaage/gasket-driver (community fork)..."
    BUILD_FAILED=false
    GASKET_SRC="/tmp/gasket-robertzaage"
    rm -rf "$GASKET_SRC"

    if git clone --depth=1 https://github.com/robertzaage/gasket-driver.git "$GASKET_SRC" 2>/dev/null; then
        cd "$GASKET_SRC"
        GASKET_VER=$(grep "^PACKAGE_VERSION" src/dkms.conf 2>/dev/null \
            | cut -d= -f2 | tr -d '"' | tr -d ' ' || echo "1.0")
        sudo dkms remove "gasket/${GASKET_VER}" --all 2>/dev/null || true
        DKMS_SRC="/usr/src/gasket-${GASKET_VER}"
        sudo rm -rf "$DKMS_SRC"
        sudo mkdir -p "$DKMS_SRC"
        sudo cp -r src/* "$DKMS_SRC/"
        sudo dkms add "gasket/${GASKET_VER}" 2>/dev/null || true
        sudo dkms build -k "${RUNNING_KERNEL}" "gasket/${GASKET_VER}" && \
        sudo dkms install -k "${RUNNING_KERNEL}" "gasket/${GASKET_VER}" --force && \
            success "gasket/${GASKET_VER} installed (robertzaage fork)" || BUILD_FAILED=true
        cd ~
    else
        BUILD_FAILED=true
    fi
fi

if $BUILD_FAILED; then
    error "All three build methods failed."
    error "Manual options:"
    error "  1. Try: sudo apt-get install raspberrypi-kernel-headers && re-run this script"
    error "  2. Use Docker: git clone https://github.com/jnicolson/gasket-builder && cd gasket-builder && docker build --output . . && sudo dpkg -i gasket-dkms_*.deb"
    exit 1
fi

echo ""

# ── Step 4: udev rules + group ────────────────────────────────────────────────
info "Step 4/5: Configuring udev rules and apex group..."

sudo groupadd -f apex 2>/dev/null || true
if ! groups "$(whoami)" | grep -q apex; then
    sudo usermod -aG apex "$(whoami)"
    warn "Added $(whoami) to 'apex' group (takes effect after reboot)."
fi

if [ ! -f /etc/udev/rules.d/65-apex.rules ]; then
    sudo tee /etc/udev/rules.d/65-apex.rules > /dev/null << 'UDEV'
SUBSYSTEM=="apex", MODE="0660", GROUP="apex"
UDEV
    sudo udevadm control --reload-rules && sudo udevadm trigger
    success "udev rules created."
else
    success "udev rules already present."
fi
echo ""

# ── Step 5: Load modules + verify ────────────────────────────────────────────
info "Step 5/5: Loading kernel modules..."
sudo modprobe gasket 2>/dev/null && sudo modprobe apex 2>/dev/null && {
    success "gasket + apex modules loaded."
} || {
    info "Module load will complete after reboot (normal for first install)."
}

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║              Gasket Driver Install Complete!            ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

if ls /dev/apex_* 2>/dev/null | grep -q apex; then
    success "/dev/apex_0 is PRESENT — Coral M.2 is ready NOW!"
    echo ""
    echo "  No reboot needed. Enable Coral in config.yaml:"
    echo "    detection:"
    echo "      birdnet:"
    echo "        backend: \"coral\""
    echo ""
    echo "  Then test:"
    echo "    source venv/bin/activate"
    echo "    python main.py --test-detection"
else
    warn "/dev/apex_0 not yet visible (normal — modules load fully on reboot)."
    echo ""
    echo "  ✅ Reboot to activate:"
    echo "       sudo reboot"
    echo ""
    echo "  After reboot verify:"
    echo "       ls /dev/apex_*           # should show /dev/apex_0"
    echo "       lspci | grep -i coral    # should show Global Unichip Corp."
    echo ""
    echo "  Then enable Coral in config.yaml:"
    echo "    detection:"
    echo "      birdnet:"
    echo "        backend: \"coral\""
fi
echo ""
