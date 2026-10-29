#!/bin/bash
# ============================================================
# Chirp Live (ios-live/): the Live Detect app. Native SwiftUI, BirdNET 2.4
# on the phone with TensorFlow Lite (its C library and Swift wrapper are
# fetched into ios-live/Vendor; no CocoaPods).
#
#   ./build-live.sh --test        run the BirdNET tests in the iPhone simulator
#   ./build-live.sh --sim         build and run in the iPhone simulator
#   ./build-live.sh --testflight  archive and upload to TestFlight (internal testers)
#   BUNDLE_ID=...                 another bundle ID
# The BirdNET models (about 66 MB) come from the birdnetlib package on first
# run and stay in ios-live/Models (not in the release zip).
# ============================================================
set -euo pipefail
GREEN='\033[0;32m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${BLUE}[chirp-live]${NC} $*"; }
success() { echo -e "${GREEN}[ok]${NC} $*"; }
error()   { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export LANG="${LANG:-en_US.UTF-8}" LC_ALL="${LC_ALL:-en_US.UTF-8}"   # CocoaPods needs UTF-8

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
L="$ROOT/ios-live"
MODE="${1:-}"
APP_ID="${BUNDLE_ID:-com.joshuasalvimd.chirplive}"
VERSION="${LIVE_VERSION:-1.0}"
BUILD_NUMBER="$(date +%Y%m%d%H%M)"
ASC_ENV="${ASC_ENV:-$HOME/Developer/Chirp/asc.env}"
[[ -f "$ASC_ENV" ]] && source "$ASC_ENV"
ASC_AUTH=()
if [[ -n "${ASC_KEY_ID:-}" && -n "${ASC_ISSUER_ID:-}" && -f "${ASC_KEY_PATH:-}" ]]; then
  ASC_AUTH=(-authenticationKeyPath "$ASC_KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID")
fi

# BirdNET models, from the birdnetlib wheel (BirdNET-Analyzer, CC BY-NC-SA 4.0).
M="$L/Models"
if [[ ! -f "$M/BirdNET_GLOBAL_6K_V2.4_Model_FP32.tflite" ]]; then
  info "Fetching the BirdNET models"
  T="$(mktemp -d)"
  python3 -m pip download -q --no-deps --only-binary=:all: birdnetlib==0.18.1 -d "$T" \
    || error "pip couldn't download birdnetlib"
  mkdir -p "$M"
  unzip -q -j -o "$T"/birdnetlib-*.whl 'birdnetlib/models/analyzer/*' -d "$M"
  rm -rf "$T"
fi
for f in BirdNET_GLOBAL_6K_V2.4_Model_FP32.tflite BirdNET_GLOBAL_6K_V2.4_MData_Model_V2_FP16.tflite BirdNET_GLOBAL_6K_V2.4_Labels.txt; do
  [[ -f "$M/$f" ]] || error "Missing $M/$f"
done
success "BirdNET models ready"

# TensorFlow Lite 2.17: the prebuilt C library (Google's release, as the
# TensorFlowLiteC pod uses) and the Swift wrapper's sources (Apache 2.0).
TFL=2.17.0
V="$L/Vendor"
if [[ ! -d "$V/TensorFlowLiteC.xcframework" ]]; then
  info "Fetching TensorFlow Lite $TFL"
  T="$(mktemp -d)"
  curl -fsSL "https://dl.google.com/tflite-release/ios/prod/tensorflow/lite/release/ios/release/32/20240729-115310/TensorFlowLiteC/$TFL/0c10b3543e01f547/TensorFlowLiteC-$TFL.tar.gz" -o "$T/tfl.tgz" \
    || error "Couldn't download TensorFlow Lite"
  tar xzf "$T/tfl.tgz" -C "$T"
  mkdir -p "$V"
  cp -R "$(find "$T" -type d -name TensorFlowLiteC.xcframework | head -1)" "$V/"
  rm -rf "$T"
fi
mkdir -p "$V/TensorFlowLiteSwift"
for f in Delegate Interpreter InterpreterError Model QuantizationParameters SignatureRunner SignatureRunnerError Tensor TensorFlowLite; do
  [[ -f "$V/TensorFlowLiteSwift/$f.swift" ]] && continue
  curl -fsSL "https://raw.githubusercontent.com/tensorflow/tensorflow/v$TFL/tensorflow/lite/swift/Sources/$f.swift" \
    -o "$V/TensorFlowLiteSwift/$f.swift" || error "Couldn't download $f.swift"
done
success "TensorFlow Lite $TFL ready"

ruby "$L/make-project.rb" "$APP_ID" "${TEAM_ID:-}" "$VERSION" "$BUILD_NUMBER"
WS=(-project "$L/build/ChirpLive.xcodeproj" -scheme ChirpLive)

sim() {
  local d
  d="$(xcrun simctl list devices available | grep -E 'iPhone 1[6-9] Pro \(' | grep -oE '[0-9A-F]{8}-([0-9A-F]{4}-){3}[0-9A-F]{12}' | head -1)"
  [[ -n "$d" ]] || d="$(xcrun simctl list devices available | grep 'iPhone' | grep -oE '[0-9A-F]{8}-([0-9A-F]{4}-){3}[0-9A-F]{12}' | head -1)"
  echo "$d"
}

case "$MODE" in
  --test)
    DEV="$(sim)"; [[ -n "$DEV" ]] || error "No iPhone simulator"
    LOG="$L/build/test.log"
    xcodebuild "${WS[@]}" -configuration Debug -destination "id=$DEV" -derivedDataPath "$L/build/dd" \
      CODE_SIGNING_ALLOWED=NO test > "$LOG" 2>&1 &
    XB=$!
    # Xcode 27's xcodebuild can sit idle after the tests finish; stop it then.
    while kill -0 $XB 2>/dev/null; do
      grep -qE "Executed [0-9]+ tests?, with|\*\* (TEST|BUILD) FAILED" "$LOG" && { sleep 10; kill $XB 2>/dev/null; break; }
      sleep 3
    done
    wait $XB 2>/dev/null || true
    grep -E "Test Case|error:|XCTAssert|\*\* " "$LOG" | tail -n 20
    grep -qE "Executed [0-9]+ tests?, with 0 failures" "$LOG" && success "Tests passed" || error "Tests failed (log: $LOG)"
    ;;
  --sim)
    DEV="$(sim)"; [[ -n "$DEV" ]] || error "No iPhone simulator"
    xcodebuild "${WS[@]}" -configuration Debug -destination "id=$DEV" -derivedDataPath "$L/build/dd" \
      CODE_SIGNING_ALLOWED=NO build | tail -n 3
    xcrun simctl boot "$DEV" 2>/dev/null || true
    xcrun simctl install "$DEV" "$L/build/dd/Build/Products/Debug-iphonesimulator/ChirpLive.app"
    xcrun simctl launch "$DEV" "$APP_ID" "${@:2}"
    success "Running in the simulator ($DEV)"
    ;;
  --testflight)
    TEAM_ID="${TEAM_ID:-F7N9ZF7U57}"
    ARCHIVE_PATH="$HOME/Library/Developer/Xcode/Archives/$(date +%Y-%m-%d)/Chirp Live $VERSION ($BUILD_NUMBER).xcarchive"
    EXPORT_DIR="$L/build/export"
    mkdir -p "$(dirname "$ARCHIVE_PATH")" "$EXPORT_DIR"
    xcodebuild "${WS[@]}" -configuration Release -destination 'generic/platform=iOS' -archivePath "$ARCHIVE_PATH" \
      DEVELOPMENT_TEAM="$TEAM_ID" CODE_SIGN_STYLE=Automatic CODE_SIGNING_ALLOWED=NO archive | tail -n 5
    [[ -d "$ARCHIVE_PATH" ]] || error "Archive failed (see above)."
    # Unsigned archive; the export signs it for App Store Connect.
    cat > "$EXPORT_DIR/ExportOptions.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>method</key><string>app-store-connect</string>
<key>signingStyle</key><string>automatic</string>
<key>teamID</key><string>$TEAM_ID</string>
<key>destination</key><string>upload</string>
<key>manageAppVersionAndBuildNumber</key><false/>
<key>uploadSymbols</key><true/>
</dict></plist>
PLIST
    # System PATH: Xcode's export runs /usr/bin/rsync, which breaks if Homebrew's rsync comes first.
    PATH=/usr/bin:/bin:/usr/sbin:/sbin xcodebuild -exportArchive -archivePath "$ARCHIVE_PATH" -exportPath "$EXPORT_DIR" \
      -exportOptionsPlist "$EXPORT_DIR/ExportOptions.plist" -allowProvisioningUpdates ${ASC_AUTH[@]+"${ASC_AUTH[@]}"} 2>&1 \
      | tee "$EXPORT_DIR/upload.log" | tail -n 8
    grep -q -E "EXPORT SUCCEEDED|Upload succeeded|Uploaded" "$EXPORT_DIR/upload.log" || error "Upload failed (log: $EXPORT_DIR/upload.log)."
    success "Uploaded Chirp Live $VERSION ($BUILD_NUMBER). Internal testers get it in TestFlight once Apple processes it."
    ;;
  *)
    error "Use --test, --sim or --testflight"
    ;;
esac
