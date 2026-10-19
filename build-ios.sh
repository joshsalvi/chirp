#!/usr/bin/env bash
# ============================================================
# Chirp iOS Build Script
# Run from the repo root (the folder holding chirp-server-instances/)
# on macOS with Xcode installed.
#
#   ./build-ios.sh                 build, sync, open Xcode
#   ./build-ios.sh --archive       ...and produce a signed archive (listed in
#                                  Xcode's Organizer) plus an installable .ipa
#   ./build-ios.sh --install       --archive, then install on a paired iPhone
#   TEAM_ID=XXXXXXXXXX ./build-ios.sh --archive   choose the signing team
#   EXPORT_METHOD=app-store-connect ./build-ios.sh --archive   paid account:
#                                  export for TestFlight / App Store
#   FRONTEND=chirp-server/frontend ./build-ios.sh  build from the other fork
#   SHARED_SIGNING=0 ./build-ios.sh --install   keep the plain bundle ID (see below)
#   RESIGN_HOST=root@192.168.1.224 ./build-ios.sh --archive   also copy the
#                                  IPA to the server's re-sign service
#   TEAM_ID=XXXXXXXXXX ./build-ios.sh --testflight   paid account: archive,
#                                  then upload to App Store Connect for
#                                  TestFlight (plain bundle ID, push on)
#   BUNDLE_ID=com.example.chirp    use another bundle ID (if the default is
#                                  taken by another team)
#   PICKER=1 ./build-ios.sh --testflight   test build that starts on a server
#                                  picker (ios-launcher/) instead of opening
#                                  ourchirp.com; named "Chirp β", uploaded but
#                                  never handed to external testers
#   WATCH=1 PICKER=1 ./build-ios.sh --testflight   also build the Apple Watch
#                                  app (ios-watch/: Live Detect, recent recordings). Needs
#                                  the xcodeproj gem and a paid team
#   PUSH=1 / PUSH=0                force push notifications on/off (default:
#                                  on for a paid team, off for a free one,
#                                  which can't sign the push entitlement)
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[chirp]${NC} $*"; }
success() { echo -e "${GREEN}[ok]${NC} $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC} $*"; }
error()   { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="${FRONTEND:-chirp-server-instances/frontend}"
ARCHIVE=0; INSTALL=0; TESTFLIGHT=0
case "${1:-}" in
  --archive) ARCHIVE=1 ;;
  --install) ARCHIVE=1; INSTALL=1 ;;
  --testflight) ARCHIVE=1; TESTFLIGHT=1 ;;
esac

echo ""
echo "╔════════════════════════════════════════╗"
echo "║     Chirp iOS App Build Script        ║"
echo "╚════════════════════════════════════════╝"
echo ""

# ── Check macOS + Xcode ──────────────────────────────────────────────────────
[[ "$(uname)" == "Darwin" ]] || error "This script requires macOS with Xcode installed."
command -v xcodebuild &>/dev/null || error "Xcode not found. Install from the App Store then run: xcode-select --install"
success "Xcode: $(xcodebuild -version | head -1)"

cd "$ROOT/$FRONTEND"
VERSION="$(cat ../VERSION)"
# App Store versions are three numbers and every release needs its own, so the
# patch letter is folded into the third: 0.X.Y.letter → 0.X.(Y*100 + n), where
# a=1 … z=26, aa=27 … (0.5.12.c → 0.5.1203, 0.5.13.a → 0.5.1301).
MARKETING_VERSION="$(echo "$VERSION" | awk -F. '{
  n = 0; s = tolower($4)
  for (i = 1; i <= length(s); i++) n = n * 26 + index("abcdefghijklmnopqrstuvwxyz", substr(s, i, 1))
  printf "%d.%d.%d", $1, $2, $3 * 100 + n }')"
BUILD_NUMBER="$(date +%Y%m%d%H%M)"
info "Chirp $VERSION → iOS $MARKETING_VERSION ($BUILD_NUMBER)"

# App Store Connect API key (~/Developer/Chirp/asc.env): signing and upload
# authenticate with it instead of the Apple ID signed in to Xcode.
ASC_ENV="${ASC_ENV:-$HOME/Developer/Chirp/asc.env}"
[[ -f "$ASC_ENV" ]] && source "$ASC_ENV"
ASC_AUTH=()
if [[ -n "${ASC_KEY_ID:-}" && -n "${ASC_ISSUER_ID:-}" && -f "${ASC_KEY_PATH:-}" ]]; then
  ASC_AUTH=(-authenticationKeyPath "$ASC_KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID")
  info "Using App Store Connect API key $ASC_KEY_ID"
fi

# ── Server picker test build ────────────────────────────────────────────────
# Same app and bundle ID, but Capacitor starts on the bundled picker page and
# may open any server. capacitor.config.json is put back when the script ends.
PICKER="${PICKER:-0}"
if [[ "$PICKER" == "1" ]]; then
  cp capacitor.config.json capacitor.config.json.release
  trap 'mv -f capacitor.config.json.release capacitor.config.json' EXIT
  node -e '
    const fs = require("fs"); const c = JSON.parse(fs.readFileSync("capacitor.config.json"));
    c.webDir = "dist-picker";
    c.server = { allowNavigation: ["*"], cleartext: true, errorPath: "offline.html" };
    c.ios.limitsNavigationsToAppBoundDomains = false;
    c.ios.appendUserAgent = "ChirpApp/2";
    fs.writeFileSync("capacitor.config.json", JSON.stringify(c, null, 2) + "\n");'
  info "Server picker build (Chirp β): starts on ios-launcher/index.html"
fi

# ── Step 1: npm deps ─────────────────────────────────────────────────────────
info "Step 1/6: Installing npm dependencies..."
npm install --silent
success "npm dependencies installed"

# ── Step 2: Build web app (offline fallback; the app loads the live server) ──
info "Step 2/6: Building React app..."
npm run build
success "Web app built → dist/"
if [[ "$PICKER" == "1" ]]; then
  rm -rf dist-picker && mkdir dist-picker
  cp "$ROOT/ios-launcher/index.html" public/logo.svg public/offline.html dist-picker/
  success "Picker page → dist-picker/"
fi

# ── Step 3: Add/sync iOS platform ───────────────────────────────────────────
info "Step 3/6: Syncing Capacitor iOS project..."
[[ -d ios ]] || { info "  Adding iOS platform for the first time..."; npx cap add ios; }
npx cap sync ios
success "iOS Capacitor project synced"

# ── Step 4: Info.plist — Bluetooth permission (BLE device setup crashes without it)
info "Step 4/6: Info.plist..."
PLIST="ios/App/App/Info.plist"
BT_TEXT="Chirp uses Bluetooth to help you set up a new device's WiFi connection."
plutil -replace NSBluetoothAlwaysUsageDescription -string "$BT_TEXT" "$PLIST"
# Without this key iOS denies the microphone silently (no prompt) and Live Detect fails.
plutil -replace NSMicrophoneUsageDescription -string "Chirp uses the microphone for Live Detect, to listen for bird calls with this phone." "$PLIST"
# Live Detect can save where a recording was made (optional, asked on first use).
plutil -replace NSLocationWhenInUseUsageDescription -string "Chirp saves where Live Detect recordings are made and uses it to judge which birds are likely nearby." "$PLIST"
# App-bound domains let the web view run the service worker (cached app
# shell: faster launches, works through brief drops). Taken from the
# config's allowNavigation; localhost serves the offline page.
if [[ "$PICKER" == "1" ]]; then
  # Any server, including plain http:// on the home network.
  BOUND="(none: any server)"
  plutil -remove WKAppBoundDomains "$PLIST" 2>/dev/null || true
  plutil -replace NSAppTransportSecurity -json '{"NSAllowsArbitraryLoadsInWebContent":true,"NSAllowsLocalNetworking":true}' "$PLIST"
  plutil -replace NSLocalNetworkUsageDescription -string "Chirp connects to a Chirp server on your home network when you choose one." "$PLIST"
  plutil -replace CFBundleDisplayName -string "Chirp β" "$PLIST"
else
  BOUND="$(node -e 'const c=require("./capacitor.config.json");console.log(JSON.stringify([...new Set([...(c.server.allowNavigation||[]),new URL(c.server.url).hostname,"localhost"])]))')"
  plutil -replace WKAppBoundDomains -json "$BOUND" "$PLIST"
  plutil -remove NSAppTransportSecurity "$PLIST" 2>/dev/null || true
  plutil -remove NSLocalNetworkUsageDescription "$PLIST" 2>/dev/null || true
  plutil -replace CFBundleDisplayName -string "Chirp" "$PLIST"
fi
# iOS 27 ends apps built with its SDK at launch unless they use the UIScene
# lifecycle. Capacitor's template doesn't, so add a scene manifest and a
# SceneDelegate (in AppDelegate.swift, so the Xcode project needs no edits).
plutil -replace UIApplicationSceneManifest -json '{"UIApplicationSupportsMultipleScenes":false,"UISceneConfigurations":{"UIWindowSceneSessionRoleApplication":[{"UISceneConfigurationName":"Default Configuration","UISceneDelegateClassName":"$(PRODUCT_MODULE_NAME).SceneDelegate","UISceneStoryboardFile":"Main"}]}}' "$PLIST"
APPDELEGATE="ios/App/App/AppDelegate.swift"
if ! grep -q "class SceneDelegate" "$APPDELEGATE"; then
  cat >> "$APPDELEGATE" <<'SWIFT'

// Added by build-ios.sh: UIScene lifecycle (required from iOS 27). The Main
// storyboard creates the window; URL opens and Universal Links go to
// Capacitor the same way AppDelegate's handlers do.
class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        guard scene is UIWindowScene else { return }
        for ctx in connectionOptions.urlContexts {
            _ = ApplicationDelegateProxy.shared.application(UIApplication.shared, open: ctx.url, options: [:])
        }
        for activity in connectionOptions.userActivities {
            _ = ApplicationDelegateProxy.shared.application(UIApplication.shared, continue: activity, restorationHandler: { _ in })
        }
    }

    func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
        for ctx in URLContexts {
            _ = ApplicationDelegateProxy.shared.application(UIApplication.shared, open: ctx.url, options: [:])
        }
    }

    func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
        _ = ApplicationDelegateProxy.shared.application(UIApplication.shared, continue: userActivity, restorationHandler: { _ in })
    }
}
SWIFT
fi
# Only standard HTTPS: answers App Store Connect's export-compliance question.
plutil -replace ITSAppUsesNonExemptEncryption -bool NO "$PLIST"
# Capacitor's push plugin hears about the APNs token through these two
# AppDelegate callbacks, which the template leaves out. An extension keeps
# AppDelegate itself untouched.
if ! grep -q "capacitorDidRegisterForRemoteNotifications" "$APPDELEGATE"; then
  cat >> "$APPDELEGATE" <<'SWIFT'

// Added by build-ios.sh: hand the APNs token (or the error) to Capacitor's
// push-notifications plugin.
extension AppDelegate {
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        NotificationCenter.default.post(name: .capacitorDidRegisterForRemoteNotifications, object: deviceToken)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        NotificationCenter.default.post(name: .capacitorDidFailToRegisterForRemoteNotifications, object: error)
    }
}
SWIFT
fi
success "Usage descriptions, app-bound domains $BOUND, scene lifecycle, push callbacks set"

# ── Step 5: App icon + launch screen ────────────────────────────────────────
info "Step 5/6: Installing app icon and launch screen..."
ICON_DST="ios/App/App/Assets.xcassets/AppIcon.appiconset"
SPLASH_DST="ios/App/App/Assets.xcassets/Splash.imageset"
if [[ -d "$ICON_DST" ]]; then
  rm -f "$ICON_DST"/*.png
  cp "$ROOT/ios-icons/icon-1024.png" "$ROOT/ios-icons/Contents.json" "$ICON_DST/"
  success "App icon installed (single 1024 px image)"
else
  warn "No AppIcon.appiconset found — using Capacitor's default icon"
fi
if [[ -d "$SPLASH_DST" ]]; then
  rm -f "$SPLASH_DST"/*.png
  cp "$ROOT"/ios-splash/*.png "$ROOT/ios-splash/Contents.json" "$SPLASH_DST/"
  success "Launch screen installed"
fi

# ── Step 6: Archive or open Xcode ───────────────────────────────────────────
if [[ $ARCHIVE -eq 1 ]]; then
  info "Step 6/6: Archiving (signed with automatic provisioning)..."
  if [[ -z "${TEAM_ID:-}" ]]; then
    TEAM_ID="$(security find-certificate -c 'Apple Development' -p 2>/dev/null \
      | openssl x509 -noout -subject 2>/dev/null | sed -n 's/.*OU *= *\([A-Z0-9]\{10\}\).*/\1/p' | head -1)"
  fi
  [[ -n "$TEAM_ID" ]] || error "No signing team found. Sign in to Xcode (Settings → Accounts) or pass TEAM_ID=..."
  # Is this a free (personal) team? Xcode records it per team.
  # (Only that key: the whole preferences file holds values JSON can't carry.)
  FREE_TEAM="$( { plutil -extract IDEProvisioningTeamByIdentifier json -o - "$HOME/Library/Preferences/com.apple.dt.Xcode.plist" 2>/dev/null || echo '{}'; } \
    | node -e 'let d="";process.stdin.on("data",c=>d+=c).on("end",()=>{try{const j=JSON.parse(d);const t=Object.values(j||{}).flat().find(x=>x&&x.teamID===process.argv[1]);console.log(t?(t.isFreeProvisioningTeam?1:0):"")}catch{console.log("")}})' "$TEAM_ID" || true)"
  if [[ $TESTFLIGHT -eq 1 ]]; then
    [[ "$FREE_TEAM" != "1" ]] || error "Team $TEAM_ID is a free personal team; TestFlight needs the paid Apple Developer team (pass TEAM_ID=...)."
    SHARED_SIGNING=0
  fi
  case "${PUSH:-auto}" in
    1) PUSH=1 ;; 0) PUSH=0 ;;
    *) [[ "$FREE_TEAM" == "1" ]] && PUSH=0 || PUSH=1 ;;
  esac
  # iPhone only: the layout is built for phones, and an iPad build would need
  # its own App Store screenshots. IPHONE_ONLY=0 builds for iPad too.
  ENTITLEMENTS=()
  [[ "${IPHONE_ONLY:-1}" == "1" ]] && ENTITLEMENTS+=(TARGETED_DEVICE_FAMILY=1)
  if [[ $PUSH -eq 1 ]]; then
    # Development here; App Store Connect exports switch it to production.
    cat > ios/App/App/App.entitlements <<'ENT'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>aps-environment</key><string>development</string>
</dict></plist>
ENT
    ENTITLEMENTS+=(CODE_SIGN_ENTITLEMENTS=App/App.entitlements)
    info "Push notifications: on (team $TEAM_ID)"
  else
    info "Push notifications: off (free team; pass PUSH=1 to force)"
  fi
  # Free (personal team) profiles last 7 days and Xcode keeps reusing a valid
  # one, so a scheduled rebuild wouldn't extend it. Set aside this app's
  # cached profiles that expire within 3 days; -allowProvisioningUpdates then
  # fetches a fresh one. (Moved to build/old-profiles, not deleted.)
  BASE_APP_ID="$(plutil -extract appId raw capacitor.config.json 2>/dev/null || echo com.joshuasalvimd.chirp)"
  # Shared signing (default): the Mac and the server's re-sign service
  # (chirp-server-instances/ios-resign) install the SAME app, so either one
  # renewing it resets the 7 days. AltServer always signs a free-account app
  # as <bundle id>.<team id>, so the Mac builds under that ID too.
  # SHARED_SIGNING=0 keeps the plain ID (then the two install separate apps).
  if [[ -n "${BUNDLE_ID:-}" ]]; then
    APP_ID="$BUNDLE_ID"
  elif [[ "${SHARED_SIGNING:-1}" == "1" ]]; then
    APP_ID="$BASE_APP_ID.$TEAM_ID"
    info "Bundle ID $APP_ID (shared with the server's re-sign service)"
  else
    APP_ID="$BASE_APP_ID"
  fi
  # Settings for the iPhone app only. On the xcodebuild command line they'd
  # also apply to the watch app, so WATCH=1 writes them into the project.
  TARGET_SETTINGS=(PRODUCT_BUNDLE_IDENTIFIER="$APP_ID" ${ENTITLEMENTS[@]+"${ENTITLEMENTS[@]}"})
  if [[ "${WATCH:-0}" == "1" ]]; then
    info "Adding the Apple Watch app (ios-watch/)"
    command -v ruby &>/dev/null && ruby -e 'require "xcodeproj"' 2>/dev/null \
      || error "WATCH=1 needs the xcodeproj gem: sudo gem install xcodeproj"
    cp "$ROOT"/ios-watch/phone/*.swift ios/App/App/
    rm -rf ios/App/ChirpWatch && cp -R "$ROOT/ios-watch/ChirpWatch" ios/App/ChirpWatch
    cp "$ROOT/ios-icons/icon-1024.png" ios/App/ChirpWatch/Assets.xcassets/AppIcon.appiconset/
    # Main.storyboard's view controller registers the ChirpWatch plugin.
    sed -i '' 's/customClass="CAPBridgeViewController" customModule="Capacitor"/customClass="ChirpBridgeViewController" customModule="App" customModuleProvider="target"/' \
      ios/App/App/Base.lproj/Main.storyboard
    ruby "$ROOT/ios-watch/add-watch-target.rb" ios/App/App.xcodeproj "$APP_ID" "$TEAM_ID" "${TARGET_SETTINGS[@]}" \
      || error "Could not add the watch app to the Xcode project"
    TARGET_SETTINGS=()
  elif grep -q ChirpWatch ios/App/App.xcodeproj/project.pbxproj 2>/dev/null; then
    # An earlier WATCH=1 build left the watch app in ios/; take it out.
    ruby "$ROOT/ios-watch/add-watch-target.rb" ios/App/App.xcodeproj --remove \
      || error "Could not remove the watch app from the Xcode project (delete ios/ and run again)"
    sed -i '' 's/customClass="ChirpBridgeViewController" customModule="App" customModuleProvider="target"/customClass="CAPBridgeViewController" customModule="Capacitor"/' \
      ios/App/App/Base.lproj/Main.storyboard
    rm -rf ios/App/ChirpWatch
    (cd "$ROOT/ios-watch/phone" && for f in *.swift; do rm -f "$OLDPWD/ios/App/App/$f"; done)
  fi
  SOON=$(( $(date +%s) + 3*86400 ))
  mkdir -p "$ROOT/build/old-profiles"
  for PDIR in "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles" "$HOME/Library/MobileDevice/Provisioning Profiles"; do
    [[ -d "$PDIR" ]] || continue
    for PF in "$PDIR"/*; do
      [[ -f "$PF" ]] || continue
      PL="$(security cms -D -i "$PF" 2>/dev/null)" || continue
      echo "$PL" | plutil -extract Entitlements.application-identifier raw - 2>/dev/null | grep -q "^$TEAM_ID\.$APP_ID$" || continue
      END="$(echo "$PL" | plutil -extract ExpirationDate raw - 2>/dev/null)"
      END_S="$(date -j -u -f '%Y-%m-%dT%H:%M:%SZ' "$END" +%s 2>/dev/null || echo 0)"
      if [[ "$END_S" -lt "$SOON" ]]; then
        mv "$PF" "$ROOT/build/old-profiles/" && info "Renewing signing profile (was due $END)"
      fi
    done
  done

  # Every paired iPhone/iPad reachable right now. Xcode 26.6+ lists these as
  # "connected" with UDIDs; earlier versions as "available" with UUIDs.
  DEVICES=($(xcrun devicectl list devices 2>/dev/null | awk '/iPhone|iPad/ && / (available|connected)/ && !/unavailable|disconnected/ {for (i=1;i<=NF;i++) if ($i ~ /^[0-9A-F]{8}-/) print $i}'))
  if [[ -f ios/App/Podfile ]]; then PROJ=(-workspace ios/App/App.xcworkspace); else PROJ=(-project ios/App/App.xcodeproj); fi

  # A generic archive never registers a new phone, so the profile wouldn't
  # include it and the install fails ("profile cannot be installed on this
  # device"). For a phone missing from the cached profile, set the profile
  # aside and build once for that phone, which registers it.
  PROFILE_DEVICES=""
  for PDIR in "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles" "$HOME/Library/MobileDevice/Provisioning Profiles"; do
    [[ -d "$PDIR" ]] || continue
    for PF in "$PDIR"/*; do
      [[ -f "$PF" ]] || continue
      PL="$(security cms -D -i "$PF" 2>/dev/null)" || continue
      echo "$PL" | plutil -extract Entitlements.application-identifier raw - 2>/dev/null | grep -q "^$TEAM_ID\.$APP_ID$" || continue
      # App Store profiles have no device list; a missing key must not end the script (set -e).
      PROFILE_DEVICES+=" $(echo "$PL" | plutil -extract ProvisionedDevices json -o - - 2>/dev/null || true)"
    done
  done
  # A new team (free or paid) can't make any signing profile until it has a
  # device registered, and a TestFlight archive is signed for development
  # first, so this runs for --testflight too.
  # A fresh free-team profile lists only the phones Xcode has built for, so
  # when one is missing, drop the cached profile and build once per phone:
  # the last build's profile then covers all of them.
  MISSING=0
  for D in ${DEVICES[@]+"${DEVICES[@]}"}; do   # bash 3.2: empty array + set -u
    [[ "$PROFILE_DEVICES" == *"$D"* ]] || MISSING=1
  done
  if [[ $MISSING -eq 1 ]]; then
    info "A paired device isn't in the signing profile; registering all ${#DEVICES[@]}..."
    for PDIR in "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles" "$HOME/Library/MobileDevice/Provisioning Profiles"; do
      [[ -d "$PDIR" ]] || continue
      for PF in "$PDIR"/*; do
        [[ -f "$PF" ]] || continue
        security cms -D -i "$PF" 2>/dev/null | grep -q "$TEAM_ID\.$APP_ID" && mv "$PF" "$ROOT/build/old-profiles/"
      done
    done
    for D in "${DEVICES[@]}"; do
      xcodebuild "${PROJ[@]}" -scheme App -configuration Release -destination "id=$D" \
        -allowProvisioningUpdates -allowProvisioningDeviceRegistration \
        DEVELOPMENT_TEAM="$TEAM_ID" CODE_SIGN_STYLE=Automatic \
        ${TARGET_SETTINGS[@]+"${TARGET_SETTINGS[@]}"} \
        build | tail -n 1 || warn "Could not register $D"
    done
  fi

  # Xcode's Organizer only lists archives stored under its own Archives folder.
  ARCHIVE_PATH="$HOME/Library/Developer/Xcode/Archives/$(date +%Y-%m-%d)/Chirp $VERSION.xcarchive"
  EXPORT_DIR="$ROOT/build/Chirp-$VERSION"
  mkdir -p "$(dirname "$ARCHIVE_PATH")" "$EXPORT_DIR"
  xcodebuild "${PROJ[@]}" -scheme App -configuration Release \
    -destination 'generic/platform=iOS' -archivePath "$ARCHIVE_PATH" \
    -allowProvisioningUpdates -allowProvisioningDeviceRegistration ${ASC_AUTH[@]+"${ASC_AUTH[@]}"} \
    DEVELOPMENT_TEAM="$TEAM_ID" CODE_SIGN_STYLE=Automatic \
    MARKETING_VERSION="$MARKETING_VERSION" CURRENT_PROJECT_VERSION="$BUILD_NUMBER" \
    ${TARGET_SETTINGS[@]+"${TARGET_SETTINGS[@]}"} \
    archive | tail -n 5
  [[ -d "$ARCHIVE_PATH" ]] || error "Archive failed (see the xcodebuild output above)."
  success "Archive: $ARCHIVE_PATH"

  # Installable .ipa. "debugging" = your own registered devices (free or paid
  # account); a paid account can use app-store-connect for TestFlight.
  METHOD="${EXPORT_METHOD:-debugging}"
  UPLOAD=""
  if [[ $TESTFLIGHT -eq 1 ]]; then
    # Signs for distribution and uploads straight to App Store Connect with
    # the API key (or the Apple ID signed in to Xcode). The app record must
    # already exist.
    METHOD=app-store-connect
    UPLOAD="<key>destination</key><string>upload</string><key>manageAppVersionAndBuildNumber</key><false/><key>uploadSymbols</key><true/>"
  fi
  cat > "$EXPORT_DIR/ExportOptions.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>method</key><string>$METHOD</string>
<key>signingStyle</key><string>automatic</string>
<key>teamID</key><string>$TEAM_ID</string>
$UPLOAD
</dict></plist>
PLIST
  if [[ $TESTFLIGHT -eq 1 ]]; then
    xcodebuild -exportArchive -archivePath "$ARCHIVE_PATH" -exportPath "$EXPORT_DIR" \
      -exportOptionsPlist "$EXPORT_DIR/ExportOptions.plist" -allowProvisioningUpdates ${ASC_AUTH[@]+"${ASC_AUTH[@]}"} 2>&1 | tee "$EXPORT_DIR/upload.log" | tail -n 8
    grep -q -E "EXPORT SUCCEEDED|Upload succeeded|Uploaded" "$EXPORT_DIR/upload.log" \
      || error "Upload to App Store Connect failed (log: $EXPORT_DIR/upload.log). If it says the app record is missing, create the app in App Store Connect with bundle ID $APP_ID."
    success "Uploaded $MARKETING_VERSION ($BUILD_NUMBER) to App Store Connect. It appears in TestFlight after Apple processes it (usually 5-30 minutes)."
    # Record the build for the Changelog's iPhone App tab (both forks); the
    # next server deploy shows it. Server-only releases never get an entry.
    for f in "$ROOT"/chirp-server*/frontend/src/lib/appReleases.json; do
      [[ -f "$f" ]] || continue
      python3 - "$f" "$VERSION" "$MARKETING_VERSION" "$BUILD_NUMBER" "$PICKER" <<'PY' || warn "Could not record the build in $f"
import json, sys, datetime
path, chirp, ios, build, picker = sys.argv[1:]
rows = [r for r in json.load(open(path)) if r["build"] != build]
row = {"chirp": chirp, "ios": ios, "build": build, "date": datetime.date.today().isoformat()}
if picker == "1":
    row["test"] = True
rows.insert(0, row)
with open(path, "w") as fh:
    fh.write("[\n" + ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in rows) + "\n]\n")
PY
    done
    if [[ "$PICKER" == "1" ]]; then
      # Not recorded for testflight-auto.sh, so it never reaches external testers.
      echo "$BUILD_NUMBER" > "$ROOT/build/last-picker-build"
      success "Picker build $BUILD_NUMBER: internal testers only. Install \"Chirp β\" from TestFlight; it replaces Chirp on that iPhone."
      exit 0
    fi
    # testflight-auto.sh counts the 40 days from this.
    mkdir -p "$ROOT/build" && date +%s > "$ROOT/build/last-testflight"
    # testflight-auto.sh hands this build to scripts/asc.py distribute.
    echo "$BUILD_NUMBER" > "$ROOT/build/last-testflight-build"
    exit 0
  fi
  xcodebuild -exportArchive -archivePath "$ARCHIVE_PATH" -exportPath "$EXPORT_DIR" \
    -exportOptionsPlist "$EXPORT_DIR/ExportOptions.plist" -allowProvisioningUpdates | tail -n 2
  IPA="$EXPORT_DIR/App.ipa"
  success "IPA ($METHOD): $IPA"
  cp "$IPA" "$ROOT/build/App.ipa"

  # The server's re-sign service signs this same IPA (it sets the bundle ID
  # back to the plain one before AltServer adds the team ID).
  if [[ -n "${RESIGN_HOST:-}" ]]; then
    RESIGN_KEY="${RESIGN_KEY:-$HOME/.ssh/chirp_unraid}"
    RESIGN_DIR="${RESIGN_DIR:-/mnt/user/appdata/chirp-ios-resign/ipa}"
    if ssh -i "$RESIGN_KEY" -o IdentityAgent=none -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
          "$RESIGN_HOST" "mkdir -p '$RESIGN_DIR'" 2>/dev/null \
       && scp -q -i "$RESIGN_KEY" -o IdentityAgent=none -o IdentitiesOnly=yes -o BatchMode=yes \
          "$IPA" "$RESIGN_HOST:$RESIGN_DIR/App.ipa"; then
      success "IPA copied to $RESIGN_HOST:$RESIGN_DIR/App.ipa"
    else
      warn "Couldn't copy the IPA to $RESIGN_HOST (not on the home network?)"
    fi
  fi

  # Free (personal team) signing expires after 7 days; say so when it applies.
  PROFILE_END="$(security cms -D -i "$ARCHIVE_PATH/Products/Applications/App.app/embedded.mobileprovision" 2>/dev/null \
    | plutil -extract ExpirationDate raw - 2>/dev/null || true)"
  [[ -n "$PROFILE_END" ]] && info "Signing profile expires $PROFILE_END (free accounts: rebuild weekly)"

  if [[ $INSTALL -eq 1 ]]; then
    [[ ${#DEVICES[@]} -gt 0 ]] || error "No paired iPhone/iPad available. Unlock it, keep it on the same network (or plug it in), and retry."
    FAILED=0
    for D in "${DEVICES[@]}"; do
      NAME="$(xcrun devicectl list devices 2>/dev/null | grep "$D" | awk -F'  +' '{print $1}')"
      if xcrun devicectl device install app --device "$D" "$IPA" >/dev/null 2>"$EXPORT_DIR/install-$D.log"; then
        success "Installed on $NAME ($D)"
      elif grep -q -i "locked" "$EXPORT_DIR/install-$D.log"; then
        warn "$NAME is locked: unlock it and rerun --install"; FAILED=1
      else
        warn "Install on $NAME failed: $(grep -m1 -i error "$EXPORT_DIR/install-$D.log")"; FAILED=1
      fi
    done
    [[ $FAILED -eq 0 ]] || exit 2
  else
    echo ""
    echo "  Install on your iPhone:  xcrun devicectl device install app --device ${DEVICES[0]:-<device-id>} \"$IPA\""
    echo "  Or: Xcode → Window → Organizer → Chirp $VERSION → Distribute App."
    echo ""
  fi
else
  info "Step 6/6: Opening Xcode..."
  echo ""
  echo "  Next steps in Xcode:"
  echo "  1. App target → Signing & Capabilities → set your Team"
  echo "  2. Product → Run (Cmd+R) to run on a simulator or your iPhone"
  echo "  3. Product → Archive to build for App Store / TestFlight"
  echo "  Or rerun with --archive to do it from the command line."
  echo ""
  npx cap open ios
fi
