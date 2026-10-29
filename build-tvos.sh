#!/bin/bash
# ============================================================
# Chirp Apple TV app (ios-tv/): build, run in the simulator, or upload to
# TestFlight. Native SwiftUI (tvOS has no web view); same bundle ID as the
# iPhone app, so it joins the same App Store Connect record.
#
#   ./build-tvos.sh --sim                    build and run in the tvOS simulator
#   CHIRP_SERVER=… CHIRP_TOKEN=… ./build-tvos.sh --uitest
#                                            remote-focus UI tests in the simulator
#   TEAM_ID=XXXXXXXXXX ./build-tvos.sh --testflight
#                                            archive and upload; TestFlight only
#   BUNDLE_ID=...                            another bundle ID
# ============================================================
set -euo pipefail
GREEN='\033[0;32m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${BLUE}[chirp-tv]${NC} $*"; }
success() { echo -e "${GREEN}[ok]${NC} $*"; }
error()   { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-}"
APP_ID="${BUNDLE_ID:-com.joshuasalvimd.chirp}"
VERSION="$(cat "$ROOT/chirp-server-instances/VERSION")"
MARKETING_VERSION="$(echo "$VERSION" | awk -F. '{
  n = 0; s = tolower($4)
  for (i = 1; i <= length(s); i++) n = n * 26 + index("abcdefghijklmnopqrstuvwxyz", substr(s, i, 1))
  printf "%d.%d.%d", $1, $2, $3 * 100 + n }')"
BUILD_NUMBER="$(date +%Y%m%d%H%M)"
info "Chirp $VERSION → tvOS $MARKETING_VERSION ($BUILD_NUMBER)"

ASC_ENV="${ASC_ENV:-$HOME/Developer/Chirp/asc.env}"
[[ -f "$ASC_ENV" ]] && source "$ASC_ENV"
ASC_AUTH=()
if [[ -n "${ASC_KEY_ID:-}" && -n "${ASC_ISSUER_ID:-}" && -f "${ASC_KEY_PATH:-}" ]]; then
  ASC_AUTH=(-authenticationKeyPath "$ASC_KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID")
fi

[[ "${1:-}" == --uitest ]] && export UITESTS=1
ruby "$ROOT/ios-tv/make-project.rb" "$APP_ID" "${TEAM_ID:-}"
PROJ=(-project "$ROOT/ios-tv/build/ChirpTV.xcodeproj" -scheme ChirpTV)

case "$MODE" in
  --sim)
    # 1080p simulator: screenshots come out at 1920×1080, the App Store size.
    DEV="$(xcrun simctl list devices available | grep 'Apple TV 4K' | grep '1080p' | grep -oE '[0-9A-F]{8}-([0-9A-F]{4}-){3}[0-9A-F]{12}' | head -1)"
    [[ -n "$DEV" ]] || DEV="$(xcrun simctl create "Apple TV 4K (at 1080p)" com.apple.CoreSimulator.SimDeviceType.Apple-TV-4K-3rd-generation-1080p)"
    xcodebuild "${PROJ[@]}" -configuration Debug -destination "id=$DEV" -derivedDataPath "$ROOT/ios-tv/build/dd" \
      CODE_SIGNING_ALLOWED=NO build | tail -n 3
    xcrun simctl boot "$DEV" 2>/dev/null || true
    APP="$ROOT/ios-tv/build/dd/Build/Products/Debug-appletvsimulator/Chirp.app"
    xcrun simctl install "$DEV" "$APP"
    xcrun simctl launch "$DEV" "$APP_ID" "${@:2}"
    success "Running in the simulator ($DEV)"
    ;;
  --uitest)
    DEV="$(xcrun simctl list devices available | grep 'Apple TV 4K' | grep '1080p' | grep -oE '[0-9A-F]{8}-([0-9A-F]{4}-){3}[0-9A-F]{12}' | head -1)"
    [[ -n "$DEV" ]] || error "No Apple TV 4K (1080p) simulator; run --sim once first."
    LOG="$ROOT/ios-tv/build/uitest.log"; SHOTS="$ROOT/ios-tv/build/uitest-shots"
    rm -rf "$ROOT/ios-tv/build/uitest.xcresult" "$SHOTS"; mkdir -p "$SHOTS"
    TEST_RUNNER_CHIRP_SERVER="${CHIRP_SERVER:-}" TEST_RUNNER_CHIRP_TOKEN="${CHIRP_TOKEN:-}" \
    TEST_RUNNER_CHIRP_USER="${CHIRP_USER:-}" TEST_RUNNER_CHIRP_SHOTS="$SHOTS" \
    xcodebuild "${PROJ[@]}" -configuration Debug -destination "id=$DEV" -derivedDataPath "$ROOT/ios-tv/build/dd" \
      -resultBundlePath "$ROOT/ios-tv/build/uitest.xcresult" CODE_SIGNING_ALLOWED=NO test > "$LOG" 2>&1 &
    XB=$!
    # Xcode 27's xcodebuild can sit idle after the tests finish; stop it then.
    while kill -0 $XB 2>/dev/null; do
      grep -qE "Test Suite 'All tests' (passed|failed)|\*\* (TEST|BUILD) FAILED" "$LOG" && { sleep 20; kill $XB 2>/dev/null; break; }
      sleep 3
    done
    wait $XB 2>/dev/null || true
    grep -E "Test Case|error:|Executed|\*\* " "$LOG" | tail -n 20
    grep -q "Test Suite 'All tests' passed" "$LOG" && success "UI tests passed (screens: $SHOTS)" || error "UI tests failed (log: $LOG)"
    ;;
  --testflight)
    # The paid team (this Mac also has a personal team's certificate).
    TEAM_ID="${TEAM_ID:-F7N9ZF7U57}"
    [[ -n "${TEAM_ID:-}" ]] || error "Pass TEAM_ID=... (the paid Apple Developer team)."
    ARCHIVE_PATH="$HOME/Library/Developer/Xcode/Archives/$(date +%Y-%m-%d)/Chirp TV $VERSION.xcarchive"
    EXPORT_DIR="$ROOT/build/ChirpTV-$VERSION"
    mkdir -p "$(dirname "$ARCHIVE_PATH")" "$EXPORT_DIR"
    xcodebuild "${PROJ[@]}" -configuration Release -destination 'generic/platform=tvOS' -archivePath "$ARCHIVE_PATH" \
      DEVELOPMENT_TEAM="$TEAM_ID" CODE_SIGN_STYLE=Automatic CODE_SIGNING_ALLOWED=NO \
      MARKETING_VERSION="$MARKETING_VERSION" CURRENT_PROJECT_VERSION="$BUILD_NUMBER" archive | tail -n 5
    [[ -d "$ARCHIVE_PATH" ]] || error "Archive failed (see above)."
    # The archive is unsigned: a development profile would need a registered
    # Apple TV. The export below signs it for App Store Connect.
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
    xcodebuild -exportArchive -archivePath "$ARCHIVE_PATH" -exportPath "$EXPORT_DIR" \
      -exportOptionsPlist "$EXPORT_DIR/ExportOptions.plist" -allowProvisioningUpdates ${ASC_AUTH[@]+"${ASC_AUTH[@]}"} 2>&1 \
      | tee "$EXPORT_DIR/upload.log" | tail -n 8
    grep -q -E "EXPORT SUCCEEDED|Upload succeeded|Uploaded" "$EXPORT_DIR/upload.log" || error "Upload failed (log: $EXPORT_DIR/upload.log)."
    # TestFlight only: never recorded for testflight-auto.sh or App Store submission.
    echo "$BUILD_NUMBER" > "$ROOT/build/last-tvos-build" 2>/dev/null || true
    success "Uploaded tvOS $MARKETING_VERSION ($BUILD_NUMBER). Internal testers get it in TestFlight on the Apple TV once Apple processes it."
    ;;
  *) error "usage: ./build-tvos.sh --sim | --uitest | --testflight" ;;
esac
