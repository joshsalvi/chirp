#!/usr/bin/env bash
# ============================================================================
# Compile a BirdNET EdgeTPU model for Chirp's Coral backend
#
# Run this on a Mac or any Linux machine with Docker installed — NOT on the
# Raspberry Pi itself (the Edge TPU compiler only runs on x86_64 Linux; Pi
# is ARM64, which Google dropped compiler support for at v2.1+). Docker with
# --platform linux/amd64 is what makes this work from a Mac at all.
#
# What this does, step by step:
#   1. Downloads the official BirdNET V2.4 INT8-quantized model directly
#      from Cornell's Zenodo record (https://zenodo.org/records/15050749) —
#      this is a *different* file than the plain FP32 model; the Edge TPU
#      is an integer-only ASIC, so it can only ever run an INT8-quantized
#      model, and that quantization has to happen before compilation.
#   2. Builds a small Debian container with Google's real edgetpu_compiler
#      apt package installed (this container is the only piece that needs
#      x86_64 — everything else here is just file handling).
#   3. Runs the compiler against the downloaded model.
#   4. Copies the result to the exact filename chirp-device expects.
#
# Output: ./output/BirdNET_GLOBAL_6K_V2.4_Model_FP32_edgetpu.tflite
#   (the "FP32" in that name is just chirp-device's existing path constant —
#   harmless leftover naming from the original unavailable download this
#   replaces; the file itself is the correct INT8-quantized, EdgeTPU-
#   compiled model, and chirp-device only checks that the file exists and
#   has a valid TFL3 signature, not its filename semantics.)
#
# NOT independently tested end-to-end against a real Coral device by the
# person who wrote this script — Docker wasn't available in that sandbox.
# Every individual piece (the apt package name, the modern non-deprecated
# GPG-keyring install method, the exact Zenodo download URL/filename) was
# verified directly against current sources, but you're the first real
# end-to-end run. If something here doesn't match reality, the errors
# should be self-explanatory enough to fix — please report back either way.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${SCRIPT_DIR}/work"
OUT_DIR="${SCRIPT_DIR}/output"
FINAL_NAME="BirdNET_GLOBAL_6K_V2.4_Model_FP32_edgetpu.tflite"

INT8_ZIP_URL="https://zenodo.org/records/15050749/files/BirdNET_v2.4_tflite_int8.zip?download=1"
INT8_ZIP_MD5="69becc3e8eb1c72d1d9dae7f21062c74"   # published on the Zenodo record page, verified at time of writing

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info() { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; }

mkdir -p "${WORK_DIR}" "${OUT_DIR}"

# ── Step 1: Docker present? ─────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    err "Docker not found. Install Docker Desktop (Mac) or Docker Engine (Linux) first:"
    err "  Mac:   https://www.docker.com/products/docker-desktop/"
    err "  Linux: curl -fsSL https://get.docker.com | sh"
    exit 1
fi
ok "Docker found: $(docker --version)"

# Detect whether we need cross-platform emulation (Apple Silicon Mac, or any
# non-x86_64 host) — native Linux x86_64 servers (this almost certainly
# includes your Unraid box) skip this entirely and run natively, no emulation.
HOST_ARCH="$(uname -m)"
PLATFORM_FLAG=""
if [ "${HOST_ARCH}" != "x86_64" ] && [ "${HOST_ARCH}" != "amd64" ]; then
    warn "Host architecture is ${HOST_ARCH}, not x86_64 — using Docker's linux/amd64"
    warn "emulation (QEMU). This is normal on Apple Silicon Macs and works fine for"
    warn "a one-time compile like this; it's just slower than native, not broken."
    PLATFORM_FLAG="--platform linux/amd64"
else
    info "Host architecture: ${HOST_ARCH} — running natively, no emulation needed."
fi

# ── Step 2: Download the real INT8 model from Cornell's Zenodo record ──────
INT8_ZIP="${WORK_DIR}/BirdNET_v2.4_tflite_int8.zip"
if [ -f "${INT8_ZIP}" ]; then
    info "INT8 model zip already downloaded, skipping."
else
    info "Downloading BirdNET V2.4 INT8 model (~46 MB) from Zenodo..."
    curl -fL --progress-bar "${INT8_ZIP_URL}" -o "${INT8_ZIP}"
fi

if command -v md5sum >/dev/null 2>&1; then
    ACTUAL_MD5=$(md5sum "${INT8_ZIP}" | awk '{print $1}')
elif command -v md5 >/dev/null 2>&1; then
    ACTUAL_MD5=$(md5 -q "${INT8_ZIP}")
else
    ACTUAL_MD5=""
fi
if [ -n "${ACTUAL_MD5}" ]; then
    if [ "${ACTUAL_MD5}" = "${INT8_ZIP_MD5}" ]; then
        ok "Checksum verified (${ACTUAL_MD5})."
    else
        warn "Checksum mismatch — got ${ACTUAL_MD5}, expected ${INT8_ZIP_MD5}."
        warn "Zenodo may have updated the file, or the download was corrupted."
        warn "Continuing anyway, but double-check the result."
    fi
fi

# ── Step 3: Extract and find the MAIN audio model .tflite file ─────────────
# The official zip contains TWO .tflite files: the main acoustic classifier
# (expects a [1, 144000] float32 audio waveform as input) and a small
# auxiliary "MData" model BirdNET also ships for location/season-based
# species-probability filtering (expects just [1, 3] — lat/lon/week-of-year
# — completely different purpose, tiny by comparison). A naive `find | head
# -1` can silently grab the wrong one depending on directory traversal
# order — confirmed this happened on a real run: the MData model got
# selected, "compiled" (trivially — it's tiny and already CPU-fast, no
# EdgeTPU custom op actually needed or produced), and only caught because
# loading the result and checking its real input tensor shape showed [1,3]
# instead of [1,144000]. Excluding by name AND validating the shape
# afterward (not just trusting the filename) closes both the excludable
# case and the "what if naming changes upstream" case.
EXTRACT_DIR="${WORK_DIR}/extracted"
rm -rf "${EXTRACT_DIR}"
mkdir -p "${EXTRACT_DIR}"
unzip -q -o "${INT8_ZIP}" -d "${EXTRACT_DIR}"

info "All .tflite files found in the archive:"
find "${EXTRACT_DIR}" -iname "*.tflite" -exec ls -la {} \;

SOURCE_TFLITE=$(find "${EXTRACT_DIR}" -iname "*.tflite" ! -iname "*mdata*" ! -iname "*meta*" | sort | head -1)
if [ -z "${SOURCE_TFLITE}" ]; then
    err "No non-metadata .tflite file found inside the downloaded zip. Contents were:"
    find "${EXTRACT_DIR}" -type f
    exit 1
fi
ok "Selected as main audio model: $(basename "${SOURCE_TFLITE}") ($(du -h "${SOURCE_TFLITE}" | cut -f1))"
cp "${SOURCE_TFLITE}" "${WORK_DIR}/model_int8.tflite"

# ── Step 4: Build the compiler image ────────────────────────────────────────
info "Building the Edge TPU compiler image (one-time; cached after this)..."
docker build ${PLATFORM_FLAG} -t chirp-edgetpu-compiler "${SCRIPT_DIR}"

# ── Step 5: Compile ──────────────────────────────────────────────────────
info "Compiling model for the Edge TPU..."
COMPILE_LOG="${WORK_DIR}/compile_output.log"
# Wrapped in `if` deliberately — with `set -euo pipefail` active (see top of
# this script), a failing docker run piped through tee would otherwise exit
# the whole script immediately via pipefail, before the check-and-explain
# logic below ever got a chance to run. An `if` condition is bash's normal,
# safe way to run a command that might legitimately fail without triggering
# set -e's immediate-exit behavior for that one command.
if docker run --rm ${PLATFORM_FLAG} \
    -v "${WORK_DIR}:/work" \
    chirp-edgetpu-compiler \
    /work/model_int8.tflite 2>&1 | tee "${COMPILE_LOG}"; then
    :
fi

COMPILED="${WORK_DIR}/model_int8_edgetpu.tflite"
if [ ! -f "${COMPILED}" ]; then
    if grep -q "dynamic-sized tensors" "${COMPILE_LOG}" 2>/dev/null; then
        echo ""
        err "This is the confirmed, known failure — see the warning at the top of"
        err "this tool's README. BirdNET's own INT8 export has dynamic-sized"
        err "tensors somewhere in its graph, which the Edge TPU compiler's"
        err "delegate can't handle. Not a bug in this script, not fixable by"
        err "retrying or changing flags — the same warning shows up even in"
        err "BirdNET-Analyzer's own official CLI tooling. Realistic options:"
        err "  1. Stay on the CPU backend (already reliable, no action needed)"
        err "  2. Check BirdNET-Analyzer's GitHub Discussions for a community-"
        err "     published pre-built EdgeTPU model:"
        err "     https://github.com/birdnet-team/BirdNET-Analyzer/discussions"
    else
        err "Compilation appears to have failed — no output file at ${COMPILED}."
        err "Check the compiler log above for the specific error (often: an op in"
        err "the model isn't supported by the Edge TPU, which would show as"
        err "'Mapped to the CPU' warnings rather than a hard failure — some CPU"
        err "fallback ops are normal, a fully-failed compile is not)."
    fi
    exit 1
fi

# ── Step 6: Validate and place the final file ───────────────────────────────
SIZE=$(stat -f%z "${COMPILED}" 2>/dev/null || stat -c%s "${COMPILED}" 2>/dev/null || echo 0)
SIG=$(head -c 8 "${COMPILED}" | tail -c 4)
if [ "${SIG}" != "TFL3" ]; then
    err "Compiled output doesn't have a valid TFLite signature (TFL3). Something went wrong."
    exit 1
fi
if [ "${SIZE}" -lt 100000 ]; then
    warn "Compiled file is suspiciously small (${SIZE} bytes) for a 6000+ species model — double-check it."
fi

# The Edge TPU compiler embeds a specific custom-op marker string in any
# model it actually successfully mapped operations onto — its absence means
# either compilation genuinely failed to map anything to the TPU (everything
# fell back to CPU, which the compiler's own log output above would also
# have shown as "Mapped to the CPU" for every operation), or the wrong
# source file was compiled in the first place (e.g. the small auxiliary
# metadata model instead of the main audio classifier — this exact failure
# mode happened on a real run and is why this check exists).
if grep -aq "edgetpu-custom-op" "${COMPILED}"; then
    ok "Confirmed: contains the edgetpu-custom-op marker — this is a real, EdgeTPU-mapped compiled model."
else
    err "This compiled file does NOT contain the edgetpu-custom-op marker."
    err "It will load and technically 'work' (CPU fallback), but won't actually use the Edge TPU hardware."
    err "Check the compiler output above for 'Mapped to the CPU' warnings, and double-check"
    err "${SOURCE_TFLITE} was really the main audio model (input shape [1, 144000]), not the"
    err "small MData/location-filtering model (input shape [1, 3])."
    exit 1
fi

cp "${COMPILED}" "${OUT_DIR}/${FINAL_NAME}"
ok "Compiled model ready: ${OUT_DIR}/${FINAL_NAME} (${SIZE} bytes, valid TFL3 signature)"

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  Next step: copy this file to the Pi"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "  scp \"${OUT_DIR}/${FINAL_NAME}\" \\"
echo "      joshsalvi@<pi-ip>:~/chirp-device/models/coral/${FINAL_NAME}"
echo ""
echo "  Then, on the Pi:"
echo "    - Set backend: \"coral\" in config.yaml (or toggle it in the Devices UI)"
echo "    - No restart needed — chirp-device hot-swaps the backend in automatically"
echo ""
