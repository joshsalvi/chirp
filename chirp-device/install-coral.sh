#!/usr/bin/env bash
# =============================================================================
# Chirp: Google Coral Edge TPU Setup
#
# Supports ALL Coral form factors:
#   USB Accelerator       — USB 3.0, libedgetpu runtime
#   M.2 Accelerator A+E   — M.2 A+E key, gasket-dkms PCIe driver
#   M.2 Accelerator B+M   — NVMe-style connector, carries PCIe (NOT NVMe storage)
#   PCIe Accelerator      — PCIe x1 card, gasket-dkms PCIe driver
#
# Usage:
#   chmod +x install-coral.sh
#   ./install-coral.sh           # auto-detects form factor
#   ./install-coral.sh --usb     # force USB-only setup
#   ./install-coral.sh --pcie    # force PCIe/M.2 setup
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
bold()    { echo -e "${BOLD}$*${NC}"; }

# ── Paths — derived from script location, never hardcoded ────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHIRP_HOME="${SCRIPT_DIR}"
MODELS_DIR="${CHIRP_HOME}/models/coral"
VENV_DIR="${CHIRP_HOME}/venv"
CURRENT_USER="$(whoami)"

BIRDNET_BASE_URL="https://github.com/kahst/BirdNET-Analyzer/raw/main/checkpoints/V2.4"
EDGETPU_MODEL_FILE="BirdNET_GLOBAL_6K_V2.4_Model_FP32_edgetpu.tflite"
LABELS_FILE="BirdNET_GLOBAL_6K_V2.4_Labels.txt"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           Chirp — Google Coral Edge TPU Setup               ║"
echo "║    USB Accelerator · M.2 A+E · M.2 B+M (NVMe) · PCIe       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

if [ "$EUID" -eq 0 ]; then
    error "Do not run as root. Run as your regular user."
    exit 1
fi

# ── Form factor detection ─────────────────────────────────────────────────────
FORCE_USB=false
FORCE_PCIE=false
for arg in "${@:-}"; do
    case "$arg" in --usb) FORCE_USB=true ;; --pcie) FORCE_PCIE=true ;; esac
done

detect_form_factor() {
    ls /dev/apex_* 2>/dev/null | grep -q apex && echo "pcie" && return
    command -v lspci &>/dev/null && lspci 2>/dev/null | grep -qi "global unichip\|coral" && echo "pcie" && return
    command -v lsusb &>/dev/null && lsusb 2>/dev/null | grep -qi "1a6e:089a\|18d1:9302\|global unichip" && echo "usb" && return
    lsmod 2>/dev/null | grep -q gasket && echo "pcie" && return
    echo "unknown"
}

if $FORCE_USB; then FORM_FACTOR="usb"
elif $FORCE_PCIE; then FORM_FACTOR="pcie"
else FORM_FACTOR=$(detect_form_factor)
fi

bold "Detected form factor: ${FORM_FACTOR}"; echo ""
case "$FORM_FACTOR" in
    pcie) echo "  → M.2 A+E / M.2 B+M (PCIe signals on NVMe connector) / PCIe card" ;;
    usb)  echo "  → USB Accelerator" ;;
    unknown)
        warn "Could not auto-detect. Specify: ./install-coral.sh --usb  or  --pcie"
        warn "Continuing with BOTH drivers (safe to do)..."
        FORM_FACTOR="both" ;;
esac
echo ""

# ── Purge any broken gasket-dkms apt state from previous failed installs ──────
# gasket-dkms 1.0-18 from the Coral apt repo fails to build on kernel 6.12+ and
# leaves dpkg in a broken half-configured state that causes ALL subsequent apt
# install calls to fail with "Sub-process dpkg returned error code 1".
# We purge it unconditionally — the correct driver will be built from source below.
_purge_broken_gasket() {
    if dpkg -l gasket-dkms 2>/dev/null | grep -q "^iF\|^hF\|^uF"; then
        warn "gasket-dkms is in a broken dpkg state — purging before proceeding..."
        sudo dpkg --purge --force-all gasket-dkms 2>/dev/null || true
        sudo apt-get -f install -y 2>/dev/null || true
        success "Broken gasket-dkms state cleared."
    elif dpkg -l gasket-dkms 2>/dev/null | grep -q "^ii"; then
        # Installed but may be the broken 1.0-18 apt package
        local inst_ver
        inst_ver=$(dpkg -l gasket-dkms 2>/dev/null | awk '/^ii/{print $3}')
        info "gasket-dkms already installed (version: ${inst_ver})"
        # If it's the known-broken apt package version, replace with source build
        if [[ "${inst_ver}" == "1.0-18" ]]; then
            warn "gasket-dkms 1.0-18 (Coral apt) is incompatible with kernel 6.12+."
            warn "Purging and replacing with source build..."
            sudo dpkg --purge --force-all gasket-dkms 2>/dev/null || true
            sudo apt-get -f install -y 2>/dev/null || true
        fi
    fi
}
_purge_broken_gasket

# ── Step 1: Coral apt repo + libedgetpu ──────────────────────────────────────
info "Step 1/4: Installing Coral Edge TPU runtime..."

CORAL_KEYRING="/usr/share/keyrings/coral-edgetpu-archive-keyring.gpg"
CORAL_SOURCES="/etc/apt/sources.list.d/coral-edgetpu.list"

_setup_coral_repo() {
    info "Adding Coral apt repository (signed-by method for Bookworm/Trixie)..."
    sudo rm -f "$CORAL_SOURCES"
    sudo apt-key del 35BAA0B33E9EB396F59CA838C0BA5CE6DC6315A3 2>/dev/null || true

    local key_ok=false
    for key_url in \
        "https://packages.cloud.google.com/apt/doc/apt-key.gpg" \
        "https://dl.google.com/linux/linux_signing_key.pub"; do
        if curl -fsSL --max-time 15 "$key_url" \
                | sudo gpg --dearmor --yes -o "$CORAL_KEYRING" 2>/dev/null \
           && [ -s "$CORAL_KEYRING" ]; then
            key_ok=true
            success "Coral GPG key installed."
            break
        fi
    done

    if $key_ok; then
        echo "deb [signed-by=${CORAL_KEYRING}] https://packages.cloud.google.com/apt coral-edgetpu-stable main" \
            | sudo tee "$CORAL_SOURCES" > /dev/null
        success "Coral repository configured."
    else
        warn "GPG key download failed — using trusted=yes fallback."
        echo "deb [trusted=yes] https://packages.cloud.google.com/apt coral-edgetpu-stable main" \
            | sudo tee "$CORAL_SOURCES" > /dev/null
    fi
}

if [ ! -f "$CORAL_SOURCES" ] || [ ! -f "$CORAL_KEYRING" ] || \
   ! grep -q "signed-by" "$CORAL_SOURCES" 2>/dev/null; then
    _setup_coral_repo
else
    info "Coral apt repository already configured."
fi

sudo apt-get update -qq 2>&1 | grep -v "^$\|^Hit\|^Get" || true

# Install libedgetpu (shared runtime for both USB and PCIe)
info "Installing libedgetpu1-std..."
sudo apt-get install -y libedgetpu1-std 2>/dev/null || \
sudo apt-get install -y --allow-unauthenticated libedgetpu1-std || \
warn "libedgetpu1-std install failed — pycoral USB delegate may not work."
success "libedgetpu1-std done."

# ── PCIe/M.2: gasket driver from source ──────────────────────────────────────
# IMPORTANT: gasket-dkms 1.0-18 from the Coral apt repo does NOT build on
# kernel 6.12+ (RPi OS Bookworm/Trixie). It calls pci_enable_pcie_error_reporting()
# which was removed in kernel 6.5, and has other incompatibilities with 6.12.
# The upstream google/gasket-driver on GitHub has all these fixes.
# We SKIP the apt package entirely and build from source.

if [[ "$FORM_FACTOR" == "pcie" || "$FORM_FACTOR" == "both" ]]; then
    info "Installing gasket driver from source (kernel 6.12+ compatible)..."
    echo ""
    echo "  The Coral apt package (gasket-dkms 1.0-18) does not build on"
    echo "  kernel 6.12+. Building from upstream source instead (~3 min)."
    echo ""

    RUNNING_KERNEL="$(uname -r)"
    info "Running kernel: ${RUNNING_KERNEL}"

    # Install build dependencies
    info "Installing build dependencies..."
    sudo apt-get install -y --no-install-recommends \
        dkms git build-essential 2>/dev/null || true

    # Install kernel headers for running kernel
    # Try exact match first, then rpi variants, then generic
    HEADERS_OK=false
    for hdr_pkg in \
        "linux-headers-${RUNNING_KERNEL}" \
        "linux-headers-rpi" \
        "linux-headers-$(uname -r | sed 's/+.*//')" \
        "raspberrypi-kernel-headers"; do
        if sudo apt-get install -y "$hdr_pkg" 2>/dev/null; then
            HEADERS_OK=true
            success "Kernel headers installed: ${hdr_pkg}"
            break
        fi
    done

    if ! $HEADERS_OK; then
        warn "Could not install kernel headers from apt."
        warn "Trying to locate existing headers..."
        if ls /lib/modules/"${RUNNING_KERNEL}"/build 2>/dev/null | head -1; then
            HEADERS_OK=true
            success "Kernel headers already present at /lib/modules/${RUNNING_KERNEL}/build"
        else
            error "No kernel headers found for ${RUNNING_KERNEL}."
            error "Try: sudo apt-get install raspberrypi-kernel-headers"
            error "Or: sudo rpi-update && sudo reboot  (then re-run this script)"
        fi
    fi

    # Clone and build gasket from upstream source
    GASKET_SRC="/tmp/gasket-driver-src"
    GASKET_OK=false

    rm -rf "$GASKET_SRC"
    if git clone --depth=1 https://github.com/google/gasket-driver.git "$GASKET_SRC" 2>/dev/null; then
        cd "$GASKET_SRC"

        # Extract version from dkms.conf
        GASKET_VER=$(grep "^PACKAGE_VERSION" src/dkms.conf 2>/dev/null \
            | cut -d= -f2 | tr -d '"' | tr -d ' ')
        GASKET_VER="${GASKET_VER:-1.0}"
        info "gasket version from source: ${GASKET_VER}"

        # Remove any previous DKMS entry for this version
        sudo dkms remove "gasket/${GASKET_VER}" --all 2>/dev/null || true

        # Install source into DKMS tree
        DKMS_SRC="/usr/src/gasket-${GASKET_VER}"
        sudo rm -rf "$DKMS_SRC"
        sudo mkdir -p "$DKMS_SRC"
        sudo cp -r src/* "$DKMS_SRC/"

        # Build
        sudo dkms add "gasket/${GASKET_VER}" 2>/dev/null || true
        if sudo dkms build -k "${RUNNING_KERNEL}" "gasket/${GASKET_VER}"; then
            if sudo dkms install -k "${RUNNING_KERNEL}" "gasket/${GASKET_VER}" --force; then
                GASKET_OK=true
                success "gasket/${GASKET_VER} built and installed for kernel ${RUNNING_KERNEL}."
                # Also try to load the module now (before reboot)
                sudo modprobe gasket 2>/dev/null && \
                sudo modprobe apex 2>/dev/null && \
                success "gasket/apex modules loaded." || \
                info "Module load deferred to reboot (normal)."
            else
                error "dkms install failed — check: sudo dkms status"
            fi
        else
            error "dkms build failed."
            MAKE_LOG=$(find /var/lib/dkms/gasket -name "make.log" 2>/dev/null | head -1)
            if [ -n "$MAKE_LOG" ]; then
                warn "Build log (last 30 lines): ${MAKE_LOG}"
                tail -30 "$MAKE_LOG" | sed 's/^/  /'
            else
                warn "No make.log found — check: /var/lib/dkms/gasket/"
            fi
        fi

        cd "$CHIRP_HOME"
    else
        error "Could not clone google/gasket-driver from GitHub."
        error "Check network: curl -I https://github.com"
    fi

    if ! $GASKET_OK; then
        warn "═══════════════════════════════════════════════════════════════"
        warn "gasket driver build failed. Manual steps:"
        warn ""
        warn "  1. Check your kernel headers:"
        warn "       ls /lib/modules/\$(uname -r)/build"
        warn ""
        warn "  2. Build the log:"
        warn "       cat /var/lib/dkms/gasket/*/\$(uname -r)/*/log/make.log"
        warn ""
        warn "  3. Manual build:"
        warn "       git clone https://github.com/google/gasket-driver /tmp/gasket"
        warn "       cd /tmp/gasket"
        warn "       sudo dkms add ./src"
        warn "       sudo dkms build gasket/\$(grep PACKAGE_VERSION src/dkms.conf | cut -d= -f2 | tr -d '\"')"
        warn "       sudo dkms install gasket/\$(grep PACKAGE_VERSION src/dkms.conf | cut -d= -f2 | tr -d '\"') --force"
        warn "═══════════════════════════════════════════════════════════════"
    fi

    # apex group + udev
    sudo groupadd -f apex 2>/dev/null || true
    if ! groups "$CURRENT_USER" | grep -q apex; then
        sudo usermod -aG apex "$CURRENT_USER"
        warn "Added ${CURRENT_USER} to 'apex' group — reboot required."
    else
        success "User ${CURRENT_USER} already in 'apex' group."
    fi

    if [ ! -f /etc/udev/rules.d/65-apex.rules ]; then
        sudo tee /etc/udev/rules.d/65-apex.rules > /dev/null << 'UDEV'
SUBSYSTEM=="apex", MODE="0660", GROUP="apex"
UDEV
        sudo udevadm control --reload-rules && sudo udevadm trigger
        success "Udev rules added for /dev/apex_*."
    fi
fi

# USB udev rules
if [[ "$FORM_FACTOR" == "usb" || "$FORM_FACTOR" == "both" ]]; then
    if [ ! -f /etc/udev/rules.d/65-coral.rules ]; then
        sudo tee /etc/udev/rules.d/65-coral.rules > /dev/null << 'UDEV'
SUBSYSTEM=="usb", ATTRS{idVendor}=="1a6e", ATTRS{idProduct}=="089a", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="18d1", ATTRS{idProduct}=="9302", MODE="0666"
UDEV
        sudo udevadm control --reload-rules && sudo udevadm trigger
        success "Udev rules added for Coral USB."
    fi
fi

# ── /boot/firmware/config.txt: PCIe entries ──────────────────────────────────
# Duplicate dtparam=pciex1 entries are harmless but messy. We ensure exactly
# one entry is present and clean up any duplicates.
_fix_pcie_config() {
    local CONFIG_FILE=""
    # Find the correct boot config file (varies by OS version)
    for f in /boot/firmware/config.txt /boot/config.txt; do
        [ -f "$f" ] && CONFIG_FILE="$f" && break
    done
    [ -z "$CONFIG_FILE" ] && return

    local pcie_count
    pcie_count=$(grep -c "^dtparam=pciex1" "$CONFIG_FILE" 2>/dev/null || echo 0)

    if [ "$pcie_count" -eq 0 ]; then
        info "Adding dtparam=pciex1 to ${CONFIG_FILE}..."
        sudo tee -a "$CONFIG_FILE" > /dev/null << 'CFG'

# Google Coral M.2 PCIe — added by Chirp install-coral.sh
dtparam=pciex1
CFG
        success "PCIe enabled in ${CONFIG_FILE}"
    elif [ "$pcie_count" -gt 1 ]; then
        warn "Found ${pcie_count} duplicate dtparam=pciex1 entries in ${CONFIG_FILE} — deduplicating..."
        # Keep only the first occurrence, remove the rest
        sudo python3 -c "
import re
with open('${CONFIG_FILE}') as f:
    lines = f.readlines()
seen = False
out = []
for line in lines:
    if re.match(r'^dtparam=pciex1', line.strip()):
        if not seen:
            out.append(line)
            seen = True
        # else: skip duplicate
    else:
        out.append(line)
with open('${CONFIG_FILE}', 'w') as f:
    f.writelines(out)
print(f'  Deduplicated: kept 1 of ${pcie_count} entries')
"
        success "Duplicate pciex1 entries removed."
    else
        info "dtparam=pciex1 already present in ${CONFIG_FILE} (1 entry — OK)."
    fi
}
_fix_pcie_config

# ── Step 2: pycoral / tflite-runtime ─────────────────────────────────────────
info "Step 2/4: Installing EdgeTPU Python backend (pycoral, tflite-runtime, or tensorflow)..."

if [ -d "${VENV_DIR}" ]; then
    source "${VENV_DIR}/bin/activate"
    PIP_CMD="pip"
    info "Using venv: ${VENV_DIR}"
else
    warn "Venv not found at ${VENV_DIR} — run ./install.sh first, then re-run this."
    PIP_CMD="pip3"
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python version: ${PY_VER}"

PYCORAL_OK=false
case "$PY_VER" in
    3.9|3.10|3.11)
        info "Trying pycoral from Google Coral py-repo (has wheels for Python ≤3.11)..."
        if $PIP_CMD install --quiet --extra-index-url https://google-coral.github.io/py-repo/ \
                "pycoral~=2.0" 2>/dev/null; then
            PYCORAL_OK=true
            success "pycoral installed."
        else
            warn "pycoral wheel not available for this platform."
        fi ;;
    *)
        warn "pycoral has no pre-built wheels for Python ${PY_VER} (only 3.9–3.11)." ;;
esac

TFLITE_RUNTIME_OK=false
if ! $PYCORAL_OK; then
    info "Installing tflite-runtime (works with Coral via delegate)..."
    # tflite-runtime's last PyPI release (2.14.0, Oct 2023) ships wheels for
    # cp38-cp311 on aarch64 — Python 3.12+ has no wheel available at all, this
    # isn't a flaky-install issue, it's the project's actual final release.
    if $PIP_CMD install --quiet "tflite-runtime>=2.14.0" 2>/dev/null || \
       $PIP_CMD install --quiet tflite-runtime 2>/dev/null; then
        TFLITE_RUNTIME_OK=true
        success "tflite-runtime installed — Coral inference will use the EdgeTPU delegate."
    else
        warn "tflite-runtime has no wheel for Python ${PY_VER} (its last release, 2.14.0, tops out at 3.11)."
    fi
fi

# ── Step 2b: tensorflow fallback (only reached if both of the above failed) ──
# The only currently-viable path on Python 3.12+: pycoral and tflite-runtime
# are both permanently stuck (see warnings above) with no newer release in
# sight, but the full `tensorflow` package is actively maintained and does
# ship real Python 3.13/aarch64 wheels. It's a genuinely heavier install
# (100s of MB vs a few MB) — only installed here as a last resort, and only
# with the person's explicit go-ahead, never silently.
if ! $PYCORAL_OK && ! $TFLITE_RUNTIME_OK; then
    echo ""
    warn "Neither pycoral nor tflite-runtime has a usable wheel for Python ${PY_VER}."
    info "The one remaining path: the full 'tensorflow' package bundles its own TFLite"
    info "interpreter with EdgeTPU delegate support, and has real Python 3.13/aarch64 wheels."
    info "Tradeoff: ~270+ MB download, slower import/startup, more RAM than tflite-runtime's"
    info "~2 MB — real cost on a Pi's storage/RAM, but the only currently-viable option here."
    echo ""
    read -p "  Install full tensorflow as the EdgeTPU backend? [y/N] " -n 1 -r REPLY_TF
    echo ""
    if [[ "$REPLY_TF" =~ ^[Yy]$ ]]; then
        info "Installing tensorflow (this will take a while)..."
        if $PIP_CMD install --quiet tensorflow 2>/dev/null; then
            success "tensorflow installed — Coral inference will use tf.lite.Interpreter + the EdgeTPU delegate."
        else
            error "tensorflow install failed. Falling back to CPU backend is your remaining option:"
            error "  config.yaml -> detection.birdnet.backend: \"cpu\""
        fi
    else
        info "Skipped. The CPU backend (already confirmed working) remains available:"
        info "  config.yaml -> detection.birdnet.backend: \"cpu\""
    fi
fi

# ── Step 3: BirdNET EdgeTPU model ────────────────────────────────────────────
info "Step 3/4: BirdNET EdgeTPU model..."
mkdir -p "${MODELS_DIR}"

# IMPORTANT — read this before reporting an issue with this step:
#
# As of this script version, there is NO confirmed, currently-maintained
# source for a pre-built BirdNET V2.4 EdgeTPU model. This was real,
# working infrastructure when this installer was first written
# (checkpoints/V2.4/*_edgetpu.tflite in the kahst/BirdNET-Analyzer repo),
# but has since changed upstream:
#   - That repo was renamed to birdnet-team/BirdNET-Analyzer (the old URL
#     correctly 301-redirects there).
#   - The checkpoints/V2.4/ directory containing pre-built .tflite files
#     no longer exists in that repo's main branch at all (confirmed via
#     a direct GitHub API 404 on the directory itself, not just one
#     file) — models appear to now be downloaded at runtime by the
#     analyzer tooling instead of being committed as static repo files.
#   - birdnetlib (the Python package this project's CPU backend already
#     uses successfully) has never bundled an EdgeTPU variant — only
#     FP32 and the MData/metadata model, confirmed directly from its
#     actual installed package contents.
#   - The project's own official, citable model archive (Zenodo, DOI
#     10.5281/zenodo.15050749) does not offer an EdgeTPU variant either
#     — only keras/protobuf/raven/tfjs/tflite/tflite_fp16/tflite_int8.
#
# This previously caused a REAL crash: curl would silently download a
# ~300KB GitHub 404 HTML error page (because -L follows the org-rename
# redirect successfully, then gets a genuine 404 for the missing file)
# and save it as if it were the model — passing the previous, too-lenient
# size check (only caught files under 100KB) and only failing loudly
# later, when chirp-device actually tried to load it as a real model.
#
# Rather than keep guessing at another stale URL, this step now fails
# honestly instead of silently saving a fake "model" file. Your real
# options right now:
#
#   1. Use the CPU backend instead. It already works (the standard
#      FP32 model ships inside birdnetlib itself, no extra download
#      needed) — set detection.birdnet.backend: "cpu" in config.yaml.
#      Coral gives a real speed advantage but isn't required to run.
#
#   2. Self-compile from the official int8-quantized source — CONFIRMED
#      BROKEN as of 2026-07-03, via a real compile attempt, not a guess:
#        - Download BirdNET_v2.4_tflite_int8.zip from
#          https://zenodo.org/records/15050749 (the official, DOI-
#          archived model release — this IS still genuinely available)
#        - Install edgetpu_compiler (requires an x86_64 Linux machine —
#          it's not available for ARM/Raspberry Pi):
#          https://coral.ai/docs/edgetpu/compiler/
#        - Run: edgetpu_compiler BirdNET_GLOBAL_6K_V2.4_Model_INT8.tflite
#        - Result: "ERROR: Attempting to use a delegate that only supports
#          static-sized tensors with a graph that has dynamic-sized
#          tensors. Compilation failed: Model failed in Tflite
#          interpreter." — a hard failure, not a warning, and not
#          something wrong with how the compile was invoked.
#      This is a genuine, structural property of BirdNET's own INT8
#      export having dynamic-sized tensors somewhere in its graph — the
#      SAME "dynamic-sized tensors" warning shows up even in BirdNET-
#      Analyzer's own official CLI tooling (confirmed via their GitHub
#      issue tracker), meaning this isn't a chirp-specific problem or a
#      mistake in how the compile was run — the source model itself
#      isn't currently structured in a way the Edge TPU compiler accepts.
#      Fixing it would require BirdNET-Analyzer re-exporting with fully
#      static tensor shapes from their original training checkpoint,
#      which is outside what's achievable by post-processing the public
#      .tflite file alone. The compile-edgetpu-model/ tool in this repo
#      still exists and correctly automates every step up to this exact
#      wall — kept because model exports do change over time and this
#      exact failure could be fixed upstream someday without any change
#      needed on this side, but don't expect it to succeed today.
#
#   3. Check if a community member has since published a current,
#      working pre-built EdgeTPU build for V2.4 — the BirdNET-Analyzer
#      GitHub Discussions (https://github.com/birdnet-team/BirdNET-Analyzer/discussions)
#      is the right place to ask, since this is a real, confirmed gap
#      that others doing Coral+BirdNET setups will likely have hit too.
#      Already checked and ruled out (2026-07-03): PINTO0309/PINTO_model_zoo
#      (a large, actively-maintained repo that specifically converts models
#      to EdgeTPU format, and already has a BirdNET-Lite entry #177 with
#      FP32/FP16/INT8 variants) — its own table shows the TPU column empty
#      for that entry. Even the most likely existing source doesn't have one.

if [ -f "${MODELS_DIR}/${EDGETPU_MODEL_FILE}" ]; then
    EXISTING_SIZE=$(stat -c%s "${MODELS_DIR}/${EDGETPU_MODEL_FILE}" 2>/dev/null || echo 0)
    EXISTING_TYPE=$(file -b --mime-type "${MODELS_DIR}/${EDGETPU_MODEL_FILE}" 2>/dev/null || echo "unknown")
    if [ "${EXISTING_TYPE}" = "text/html" ] || [ "${EXISTING_SIZE}" -lt 5000000 ]; then
        warn "Existing file at ${MODELS_DIR}/${EDGETPU_MODEL_FILE} (${EXISTING_SIZE} bytes, type: ${EXISTING_TYPE})"
        warn "does not look like a real EdgeTPU model (a genuine one should be several MB and binary,"
        warn "not HTML). This is almost certainly a saved error page from a previous run of this"
        warn "script against the now-dead download URL. Removing it so it can't be silently loaded"
        warn "as if it were real and crash chirp-device with a confusing error."
        rm -f "${MODELS_DIR}/${EDGETPU_MODEL_FILE}"
    else
        success "Existing EdgeTPU model looks genuinely valid (${EXISTING_SIZE} bytes, binary) — keeping it."
    fi
fi

if [ ! -f "${MODELS_DIR}/${EDGETPU_MODEL_FILE}" ]; then
    error "No working source for a pre-built EdgeTPU model is currently known (see the full"
    error "explanation printed above this step). Not downloading anything further automatically —"
    error "the old URL only serves a 404 error page now, and silently saving that as a 'model'"
    error "is exactly the bug that caused this to fail confusingly before. See the options listed"
    error "above. If you have a real, working *_edgetpu.tflite file from another source, place it"
    error "at: ${MODELS_DIR}/${EDGETPU_MODEL_FILE}"
    error "Continuing with the rest of this script (pycoral/runtime setup), but Coral inference"
    error "will not work until a real model file is present."
fi

# The labels file needs no download at all: birdnetlib (already installed
# and working for the CPU backend) bundles the exact same official BirdNET
# V2.4 label file as one of its own package data files. Confirmed present
# and correctly formatted (Scientific Name_Common Name, one per line,
# 6521 entries) via a real install — just copy it, no network round trip,
# no dead-URL risk at all. Only falls back to the (known-broken) old URL
# if birdnetlib somehow isn't installed or its copy can't be found.
if [ ! -f "${MODELS_DIR}/${LABELS_FILE}" ]; then
    BIRDNETLIB_LABELS=$("${VENV_DIR}/bin/python3" -c "
import importlib.util, os
# find_spec locates the package WITHOUT executing its __init__.py — a full
# 'import birdnetlib' would transitively import birdnetlib.analyzer, which
# unconditionally imports tflite_runtime or tensorflow at module load time.
# We only need this package's bundled data file path, not to actually run
# its inference code, so avoiding that import chain entirely is both safer
# and correct regardless of exactly what's installed at this point in setup.
spec = importlib.util.find_spec('birdnetlib')
if spec and spec.origin:
    d = os.path.join(os.path.dirname(spec.origin), 'models', 'analyzer')
    p = os.path.join(d, '${LABELS_FILE}')
    print(p if os.path.exists(p) else '')
" 2>/dev/null)
    if [ -n "${BIRDNETLIB_LABELS}" ] && [ -f "${BIRDNETLIB_LABELS}" ]; then
        cp "${BIRDNETLIB_LABELS}" "${MODELS_DIR}/${LABELS_FILE}"
        success "Copied ${LABELS_FILE} from the already-installed birdnetlib package (no download needed)."
    else
        warn "birdnetlib's bundled labels file not found — falling back to the old download URL."
        info "Downloading ${LABELS_FILE}..."
        # NOTE: confirmed via a real install run that this URL 404s — the
        # entire checkpoints/V2.4/ directory is gone upstream, not just the
        # model file. This is only reached if the birdnetlib copy above
        # failed for some reason. -f makes curl fail loudly (exit 22) on a
        # real HTTP error instead of silently saving the resulting error page.
        if curl -fL --progress-bar "${BIRDNET_BASE_URL}/${LABELS_FILE}" -o "${MODELS_DIR}/${LABELS_FILE}"; then
            LABELS_TYPE=$(file -b --mime-type "${MODELS_DIR}/${LABELS_FILE}" 2>/dev/null || echo "unknown")
            if [ "${LABELS_TYPE}" = "text/html" ]; then
                warn "Labels download also looks like an HTML error page, not a real labels file. Removing it."
                rm -f "${MODELS_DIR}/${LABELS_FILE}"
            else
                success "Downloaded: ${LABELS_FILE}"
            fi
        else
            warn "Labels download failed (curl exit code $?). This file may have moved too."
        fi
    fi
else
    info "Already exists: ${LABELS_FILE}"
fi

# ── Step 4: Verify ────────────────────────────────────────────────────────────
info "Step 4/4: Verifying installation..."

if ls /dev/apex_* 2>/dev/null | grep -q apex; then
    success "Device node found: $(ls /dev/apex_* 2>/dev/null | tr '\n' ' ')"
elif lsusb 2>/dev/null | grep -qi "1a6e:089a\|18d1:9302"; then
    success "Coral USB Accelerator detected on USB bus."
else
    info "Coral device not yet visible (normal — reboot required for gasket module)."
fi

PYCORAL_USABLE=$(python3 -c "
try:
    from pycoral.utils.edgetpu import list_edge_tpus
    tpus = list_edge_tpus()
    print('  pycoral:', tpus if tpus else 'no TPU devices yet (reboot required)')
    print('USABLE')
except ImportError:
    try:
        import tflite_runtime.interpreter
        print('  tflite-runtime: available')
        print('USABLE')
    except ImportError:
        try:
            import tensorflow
            print('  tensorflow:', tensorflow.__version__, '(EdgeTPU via tf.lite.experimental.load_delegate)')
            print('USABLE')
        except ImportError:
            print('  WARNING: none of pycoral, tflite-runtime, or tensorflow are importable')
except Exception as e:
    print(f'  check error: {e}')
" 2>/dev/null | tee /dev/stderr | grep -c "USABLE" || true)

echo ""
MODEL_ACTUALLY_PRESENT=false
if [ -f "${MODELS_DIR}/${EDGETPU_MODEL_FILE}" ]; then
    EXISTING_SIZE=$(stat -c%s "${MODELS_DIR}/${EDGETPU_MODEL_FILE}" 2>/dev/null || echo 0)
    if [ "${EXISTING_SIZE}" -ge 1000 ]; then
        MODEL_ACTUALLY_PRESENT=true
    fi
fi

if [ "${MODEL_ACTUALLY_PRESENT}" = "true" ] && [ "${PYCORAL_USABLE}" != "0" ]; then
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                  Coral Setup Complete!                      ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "  ⚠️  REBOOT REQUIRED for gasket kernel module to load:"
    echo "       sudo reboot"
    echo ""
    echo "  After reboot, verify: ls /dev/apex_*"
    echo ""
    echo "  Enable in config.yaml:"
    echo "    detection:"
    echo "      birdnet:"
    echo "        backend: \"coral\""
    echo ""
    echo "  Test: source ${VENV_DIR}/bin/activate && python main.py --test-detection"
    echo ""
else
    # Deliberately NOT the cheerful "Setup Complete!" banner — Coral cannot
    # actually run detection yet without a real model file, and printing a
    # success banner plus "enable backend: coral, then test" instructions
    # here would just send the person straight back into the exact
    # "EdgeTPU model not found" error Step 3 already reported above, making
    # this script look broken/inconsistent rather than honestly reflecting
    # what's actually still missing.
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║         Python/runtime layer ready — model file still needed ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    if [ "${MODEL_ACTUALLY_PRESENT}" != "true" ]; then
        warn "No EdgeTPU model file at ${MODELS_DIR}/${EDGETPU_MODEL_FILE} — see Step 3 above for why and your real options."
    fi
    if [ "${PYCORAL_USABLE}" = "0" ]; then
        warn "No usable Python EdgeTPU backend either — see Step 2 above for why."
    fi
    echo ""
    echo "  Do NOT set backend: \"coral\" in config.yaml yet — it will not work"
    echo "  without a real model file in place, and chirp-device will (correctly)"
    echo "  refuse to load one, not silently do nothing."
    echo ""
    echo "  Your real options right now:"
    echo "    1. Stay on the CPU backend (already working, no action needed)."
    echo "    2. Ask in BirdNET-Analyzer's GitHub Discussions in case someone has"
    echo "       since published a working pre-built EdgeTPU model:"
    echo "       https://github.com/birdnet-team/BirdNET-Analyzer/discussions"
    echo "    3. Self-compile — CONFIRMED BROKEN as of 2026-07-03 via a real"
    echo "       compile attempt (not a guess): the official INT8 model fails"
    echo "       with 'delegate that only supports static-sized tensors with a"
    echo "       graph that has dynamic-sized tensors' — a genuine structural"
    echo "       property of BirdNET's own export (the same warning shows up"
    echo "       even in BirdNET-Analyzer's own official CLI tooling), not"
    echo "       something fixable by changing how the compile is invoked."
    echo "       The compile-edgetpu-model/ tool still automates every step up"
    echo "       to this exact wall, kept in case this gets fixed upstream"
    echo "       someday — don't expect it to succeed today."
    echo ""
    echo "  Once you have a real *_edgetpu.tflite file, place it at:"
    echo "    ${MODELS_DIR}/${EDGETPU_MODEL_FILE}"
    echo "  then set backend: \"coral\" in config.yaml — no restart needed, it"
    echo "  hot-swaps in automatically."
    echo ""
fi
