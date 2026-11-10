#!/bin/bash
# ============================================================
# Chirp Lite (ios-lite/): the simple, picture-first Chirp app. Native
# SwiftUI on the /api/v1/lite routes; no dependencies.
#
#   ./build-lite.sh --test        run the unit tests in the iPhone simulator
#   ./build-lite.sh --sim         build and run in the iPhone simulator
#   ./build-lite.sh --shots       App Store screenshots (6.9" iPhone) with a site's
#                                 data: a one-hour Lite sign-in is made on the
#                                 server for LITE_USER (never printed or saved)
#   ./build-lite.sh --testflight  archive and upload to TestFlight
#   BUNDLE_ID=... LITE_VERSION=1.0
# ============================================================
set -euo pipefail
GREEN='\033[0;32m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${BLUE}[chirp-lite]${NC} $*"; }
success() { echo -e "${GREEN}[ok]${NC} $*"; }
error()   { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export LANG="${LANG:-en_US.UTF-8}" LC_ALL="${LC_ALL:-en_US.UTF-8}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
L="$ROOT/ios-lite"
MODE="${1:-}"
APP_ID="${BUNDLE_ID:-com.joshuasalvimd.chirp.lite}"
VERSION="${LITE_VERSION:-1.0}"
BUILD_NUMBER="$(date +%Y%m%d%H%M)"
ASC_ENV="${ASC_ENV:-$HOME/Developer/Chirp/asc.env}"
[[ -f "$ASC_ENV" ]] && source "$ASC_ENV"
ASC_AUTH=()
if [[ -n "${ASC_KEY_ID:-}" && -n "${ASC_ISSUER_ID:-}" && -f "${ASC_KEY_PATH:-}" ]]; then
  ASC_AUTH=(-authenticationKeyPath "$ASC_KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID")
fi

ruby "$L/make-project.rb" "$APP_ID" "${TEAM_ID:-}" "$VERSION" "$BUILD_NUMBER"
WS=(-project "$L/build/ChirpLite.xcodeproj" -scheme ChirpLite)

sim() {   # $1: device name pattern
  local d
  d="$(xcrun simctl list devices available | grep -E "${1:-iPhone 1[6-9] Pro \(}" | grep -oE '[0-9A-F]{8}-([0-9A-F]{4}-){3}[0-9A-F]{12}' | head -1)"
  [[ -n "$d" ]] || d="$(xcrun simctl list devices available | grep 'iPhone' | grep -oE '[0-9A-F]{8}-([0-9A-F]{4}-){3}[0-9A-F]{12}' | head -1)"
  echo "$d"
}

build_sim() {   # $1: device id
  xcodebuild "${WS[@]}" -configuration Debug -destination "id=$1" -derivedDataPath "$L/build/dd" \
    CODE_SIGNING_ALLOWED=NO build > "$L/build/sim.log" 2>&1 || { grep -E "error:" "$L/build/sim.log" | head -20; error "Build failed (log: $L/build/sim.log)"; }
  xcrun simctl boot "$1" 2>/dev/null || true
  xcrun simctl install "$1" "$L/build/dd/Build/Products/Debug-iphonesimulator/ChirpLite.app"
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
    grep -E "error:|Test Case.*failed|XCTAssert|\*\* " "$LOG" | tail -n 20
    grep -qE "Executed [0-9]+ tests?, with 0 failures" "$LOG" && success "Tests passed" || error "Tests failed (log: $LOG)"
    ;;
  --sim)
    DEV="$(sim)"; [[ -n "$DEV" ]] || error "No iPhone simulator"
    build_sim "$DEV"
    xcrun simctl launch "$DEV" "$APP_ID" "${@:2}"
    success "Running in the simulator ($DEV)"
    ;;
  --shots)
    HOST="${UNRAID:-root@192.168.1.224}"; KEY="${UNRAID_KEY:-$HOME/.ssh/chirp_unraid}"
    LITE_USER="${LITE_USER:?Set LITE_USER to the ourchirp.com account to show}"
    DEV="$(sim 'iPhone 1[6-9] Pro Max \(')"; [[ -n "$DEV" ]] || error "No iPhone Pro Max simulator"
    build_sim "$DEV"
    # A one-hour Lite sign-in for LITE_USER's first site, kept in this variable only.
    TOKEN="$(ssh -i "$KEY" -o BatchMode=yes "$HOST" "docker exec -i -w /app -e PYTHONPATH=/app -e U='$LITE_USER' chirp-server-instances python -" <<'PY'
import os
from app.registry_db import RegistrySessionLocal
from app.registry_models import GlobalUser, Membership
from app.api.auth import create_access_token
db = RegistrySessionLocal()
u = db.query(GlobalUser).filter(GlobalUser.username == os.environ["U"]).first()
m = u and db.query(Membership).filter(Membership.user_id == u.id).first()
if m:
    print(create_access_token({"sub": u.username, "global_user_id": u.id, "active_instance_id": m.instance_id,
                               "role": m.role, "scope": "lite"}, expires_minutes=60))
PY
)"
    [[ -n "$TOKEN" ]] || error "No sign-in for $LITE_USER"
    OUT="${SHOTS_DIR:-$L/build/shots}"; mkdir -p "$OUT"
    xcrun simctl status_bar "$DEV" override --time "9:41" --batteryState charged --batteryLevel 100 --wifiBars 3 --cellularBars 4 || true
    xcrun simctl ui "$DEV" appearance light
    shot() {   # name, launch args…
      local name="$1"; shift
      xcrun simctl terminate "$DEV" "$APP_ID" 2>/dev/null || true
      SIMCTL_CHILD_LITE_TOKEN="$TOKEN" SIMCTL_CHILD_LITE_USER="$LITE_USER" xcrun simctl launch "$DEV" "$APP_ID" "$@" > /dev/null
      sleep "${SHOT_WAIT:-9}"
      xcrun simctl io "$DEV" screenshot "$OUT/$name.png" > /dev/null 2>&1
      info "  $name.png"
    }
    # The sign-in screen first (no sign-in handed over), for a layout check.
    xcrun simctl terminate "$DEV" "$APP_ID" 2>/dev/null || true
    xcrun simctl launch "$DEV" "$APP_ID" > /dev/null; sleep 6
    xcrun simctl io "$DEV" screenshot "$OUT/0-signin.png" > /dev/null 2>&1; info "  0-signin.png"
    shot 1-today -LiteTab 0
    shot 2-birds -LiteTab 1
    shot 3-listen -LiteTab 2
    shot 4-guide -LiteTab 3
    # The bird page: LITE_BIRD, or today's latest visitor.
    BIRD="${LITE_BIRD:-$(curl -fsS -H "Authorization: Bearer $TOKEN" "${LITE_SERVER:-https://www.ourchirp.com}/api/v1/lite/today" \
      | python3 -c 'import json,sys; print((json.load(sys.stdin).get("hero") or {}).get("profile_id") or "")' 2>/dev/null || true)}"
    [[ -n "$BIRD" ]] && shot 5-bird -LiteTab 0 -LiteBird "$BIRD"
    APPEARANCE=dark; xcrun simctl ui "$DEV" appearance dark
    shot 6-today-dark -LiteTab 0
    xcrun simctl ui "$DEV" appearance light
    unset TOKEN
    xcrun simctl terminate "$DEV" "$APP_ID" 2>/dev/null || true
    success "Screenshots in $OUT"
    ;;
  --testflight)
    TEAM_ID="${TEAM_ID:-F7N9ZF7U57}"
    ARCHIVE_PATH="$HOME/Library/Developer/Xcode/Archives/$(date +%Y-%m-%d)/Chirp Lite $VERSION ($BUILD_NUMBER).xcarchive"
    EXPORT_DIR="$L/build/export"
    mkdir -p "$(dirname "$ARCHIVE_PATH")" "$EXPORT_DIR"
    xcodebuild "${WS[@]}" -configuration Release -destination 'generic/platform=iOS' -archivePath "$ARCHIVE_PATH" \
      DEVELOPMENT_TEAM="$TEAM_ID" CODE_SIGN_STYLE=Automatic CODE_SIGNING_ALLOWED=NO archive | tail -n 5
    [[ -d "$ARCHIVE_PATH" ]] || error "Archive failed (see above)."
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
    success "Uploaded Chirp Lite $VERSION ($BUILD_NUMBER). Internal testers get it in TestFlight once Apple processes it."
    ;;
  *)
    error "Use --test, --sim, --shots or --testflight"
    ;;
esac
