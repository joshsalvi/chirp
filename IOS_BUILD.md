# Chirp — iOS App Build Guide

*Last verified against Chirp v0.5.0.w and Capacitor 8.4 — capacitor.config.json (not .ts or .js; see Step 5) confirmed working via a real build.*

Chirp uses [Capacitor](https://capacitorjs.com) to wrap the existing React PWA
in a native WKWebView iOS app. The web UI is **identical** — all the React code,
routing, and API calls work exactly the same. Capacitor adds native features:
haptic feedback, push notifications, status bar control, and App Store packaging.

---

## Quick path (0.5.8.d and later)

From the repo root on your Mac:

```bash
./build-ios.sh             # build, sync, open Xcode
./build-ios.sh --archive   # signed archive (in Xcode's Organizer) + App.ipa in build/
./build-ios.sh --install   # ...and install on your paired iPhone
```

The script does Steps 1–4b for you: web build, `cap add/sync ios`, the
Bluetooth permission text, the app icon (one 1024 px image) and the launch
screen. `--archive` signs automatically with the team from your Xcode account
(override with `TEAM_ID=...`), sets the iOS version from `VERSION`
(`0.5.8.d` → version `0.5.8`, build number = date and time) and exports
`build/Chirp-<version>/App.ipa` for your own registered devices. With a paid
account, `EXPORT_METHOD=app-store-connect ./build-ios.sh --archive` exports for
TestFlight instead. Free (personal team) signing expires after 7 days; the
script prints the date. It builds `chirp-server-instances/frontend` by default;
`FRONTEND=chirp-server/frontend ./build-ios.sh` builds the other fork.

The app is built as `com.joshuasalvimd.chirp.<team ID>`. That is the ID
AltServer gives a free-account app, so the server's re-sign service
(`chirp-server-instances/ios-resign`) renews this same app, and either the
server or the Mac can reset the 7 days. `SHARED_SIGNING=0` builds the plain
ID instead. `RESIGN_HOST=root@192.168.1.224` also copies the IPA to the server.

It also patches the generated iOS project each run:

- Microphone text, and app-bound domains (from `server.allowNavigation`), so the service worker runs.
- A UIScene manifest plus a `SceneDelegate` appended to `AppDelegate.swift`. iOS 27 closes apps built with Xcode 27 at launch without them.
- New phones: `--install` targets every paired iPhone that's unlocked and on the same Wi-Fi. If one is missing from the signing profile, the script builds once per phone so the new profile lists all of them.
- After an Xcode update, check Xcode → Settings → Accounts is still signed in, and run `sudo xcodebuild -license accept` if builds stop at the license.

---

## Three ways to get this on a phone

| Path | Cost | Time limit | Who can install it |
|---|---|---|---|
| **Simulator** | Free | None | Just you, on your Mac (no real device) |
| **Sideload** (Step 6B below) | Free | App expires after 7 days, re-sign to renew | Only devices you personally plug into your Mac |
| **App Store / TestFlight** | $99/year Apple Developer account | None | Anyone (App Store) or up to 10,000 testers (TestFlight) |

If you just want Chirp on your own phone without paying Apple's $99/year fee,
skip straight to **Step 6B: Sideloading**. You'll re-run one command every 7
days to keep it working. The other path (Step 6A) is for getting it onto the
public App Store or sharing it with other people via TestFlight.

**One dependency worth knowing up front:** Step 4c (native Push Notifications)
also needs that same $99/year account — skip it on the free path too. You still
get push notifications via Web Push either way (see Step 4c for why); you only
lose the native-APNs-specific delivery path.

---

## Architecture

```
iOS App (WKWebView)
  └── loads YOUR-SERVER-ADDRESS over HTTPS
       └── same React app as the web browser version
            └── capacitor plugins provide native features
```

**Yes, this app just pulls the live server GUI — it doesn't bundle a separate
copy of the frontend as its primary content.** `capacitor.config.json` points the
WKWebView at `server.url` (your real Chirp server's HTTPS address), so on every
launch it's loading whatever version is actually running on your server right
now, exactly like opening it in Safari. The `dist/` folder built in Step 1 is
only ever used as an **offline fallback** (`ios.scheme` in
`capacitor.config.json` — iOS's own local-load path, for when the server
genuinely can't be reached) — it is not what you see day to day.

**The practical consequence:** most updates need zero iOS rebuild at all. If
you change anything in the web app (a new page, a bug fix, a new feature) and
deploy it to your server the normal way (`docker-compose build && up -d`), the
iOS app picks it up automatically on next launch — no Xcode, no App Store
resubmission, nothing. **You only need to go through Steps 6-7 again when a
change is genuinely native** — a new Capacitor plugin, a changed entitlement
(like Push Notifications below), a new app icon, or a change to
`capacitor.config.json` itself.

The app talks to your Chirp server over the internet — it works on WiFi or
cellular. No local server needed on the phone.

---

## Prerequisites (macOS only — Xcode is required)

```bash
# 1. Install Xcode from the App Store (free, ~15GB)
# 2. Install Xcode command-line tools
xcode-select --install

# 3. Install CocoaPods (used by Capacitor for iOS dependencies)
sudo gem install cocoapods
# OR use Homebrew:
brew install cocoapods

# 4. Accept Xcode license
sudo xcodebuild -license accept
```

---

## Step 1: Install dependencies and build the web app

```bash
cd chirp-server/frontend
npm install
npm run build          # builds the React app into dist/
```

---

## Step 2: Add the iOS platform

```bash
cd chirp-server/frontend
npx cap add ios        # creates the ios/ Xcode project
npx cap sync ios       # copies dist/ into the Xcode project + installs pods
```

This creates `chirp-server/frontend/ios/` — the complete Xcode project.

---

## Step 3: Add the app icons

Copy the generated icons into the Xcode project:

```bash
# Copy all icons into the Xcode AppIcon.appiconset
ICON_SRC="../../ios-icons"
ICON_DST="ios/App/App/Assets.xcassets/AppIcon.appiconset"

cp ${ICON_SRC}/*.png ${ICON_DST}/
cp ${ICON_SRC}/Contents.json ${ICON_DST}/
```

---

## Step 4: Open Xcode and configure signing

```bash
npx cap open ios       # opens ios/App/App.xcworkspace in Xcode
```

In Xcode:
1. Click the **App** project in the Navigator
2. Select the **App** target → **Signing & Capabilities**
3. Check **Automatically manage signing**
4. Choose your **Team** (Apple Developer account — $99/year for App Store)
5. Xcode will create a provisioning profile automatically

**Bundle identifier:** `com.yourname.chirp` (set in capacitor.config.json)

---

## Step 4b: Bluetooth permission (required for BLE device setup)

**This step is required, not optional, if you want the "Find nearby device" Bluetooth
setup feature to work** (see Settings/Devices → Bluetooth device setup, for provisioning
a brand-new Pi's WiFi over Bluetooth before it has a network connection). Without this,
the app will crash the moment it tries to use Bluetooth — iOS requires an explicit
usage-description string for every sensitive permission, and there's no way to add this
from the web code side; it has to go directly into the generated Xcode project.

In Xcode, with `ios/App/App.xcworkspace` open:
1. In the Navigator, find `ios/App/App/Info.plist`
2. Right-click → **Open As** → **Source Code**
3. Add this, anywhere inside the outermost `<dict>` tag:
   ```xml
   <key>NSBluetoothAlwaysUsageDescription</key>
   <string>Chirp uses Bluetooth to help you set up a new device's WiFi connection.</string>
   ```
4. Save

This step doesn't survive `npx cap sync ios` re-running from scratch on a fresh
`ios/` folder — if you ever delete and re-add the iOS platform, redo this step before
building again, or the crash will come back with no obvious explanation from the crash
log alone (it just says the app terminated, not why).

---

## Step 4c: Push Notifications capability (needs a paid Apple Developer account — skip entirely if sideloading for free)

**Confirmed directly: this requires the $99/year Apple Developer Program membership.**
A free "personal team" signing identity (the one used for sideloading in Step 6B)
cannot hold the Push Notifications entitlement at all — Apple restricts it at the
account tier itself, not something you can work around with configuration. If
you're on the free sideload path, skip this entire step.

**You still get push notifications without this.** Web Push (the separate system
covering the browser/PWA experience) needs zero Apple Developer account and
self-configures automatically — you only lose the *native* APNs-specific delivery
path by skipping this step, not push notifications altogether.

If you do have a paid account and want native push: native push (real
notifications delivered via Apple's APNs, including while the app is closed)
needs configuration in **three separate places** — Xcode, Apple's own developer
console, and Chirp's own Settings. All three, or it won't work; this isn't
optional-but-partial the way some other features are.

**1. Enable the capability in Xcode**, with `ios/App/App.xcworkspace` open:
1. Click the **App** project → **App** target → **Signing & Capabilities**
2. Click **+ Capability**, add **Push Notifications**
3. Save (⌘S)

**2. Generate a .p8 auth key** at
[Apple Developer → Certificates, IDs & Profiles → Keys](https://developer.apple.com/account/resources/authkeys/list):
1. Click **+**, name it anything (e.g. "Chirp Push Key")
2. Check **Apple Push Notifications service (APNs)**
3. Register, then **download the .p8 file — this is the only chance to download it**;
   Apple doesn't let you re-download later, only revoke and create a new one
4. Note the **Key ID** shown on this page, and your **Team ID** (top-right of the
   Apple Developer account page, under your name)

**3. Enter all four values in Chirp itself** — Settings → Alerts & Email → iPhone
App Push (APNs): Team ID, Key ID, Bundle ID (must exactly match
`capacitor.config.json`'s `appId`), and the full contents of the .p8 file (paste the
whole thing, including the `-----BEGIN PRIVATE KEY-----`/`-----END-----` lines).

This is genuinely different from Web Push (the PWA/browser version), which needs no
setup at all — it self-generates its own keys automatically. APNs and Web Push are
two different delivery systems under the hood (see `apns_push.py` and
`push_notifications.py` in the server code if curious why they couldn't share one
implementation) — Chirp sends through both when a notification fires, so a browser
user and a native-app user both get notified correctly, but each system needs its
own setup, done once, per install.

**Sandbox vs. Production:** an Xcode debug build (Step 6, running from Xcode directly)
talks to Apple's **sandbox** APNs environment; a TestFlight or App Store build talks to
**production**. Set the matching environment in Chirp's Settings — a mismatch here is
the most common reason push "isn't working" even though everything else was configured
correctly, since a production-environment token silently gets rejected by the sandbox
endpoint and vice versa.

---

## Step 5: Configure the server URL

The server URL is set in `capacitor.config.json`:

```json
"server": {
  "url": "https://YOUR-SERVER-ADDRESS"
}
```

After changing this, run `npx cap sync ios` again to update the Xcode project.

---

## Step 6: Build and run

### Run on a simulator
```bash
npx cap run ios        # interactive — choose a simulator
```

### Step 6A: Archive for App Store / TestFlight
Requires the $99/year Apple Developer account from Step 4.

In Xcode: **Product → Archive → Distribute App**

Or via command line:
```bash
xcodebuild archive \
  -workspace ios/App/App.xcworkspace \
  -scheme App \
  -archivePath build/Chirp.xcarchive \
  -configuration Release

xcodebuild -exportArchive \
  -archivePath build/Chirp.xcarchive \
  -exportPath build/Chirp.ipa \
  -exportOptionsPlist exportOptions.plist
```
From there, upload the `.ipa` via Xcode Organizer or `xcrun altool`/`notarytool`
to App Store Connect, then either submit for App Store review or distribute
through TestFlight (no review needed for internal testers, ~24h for external).

#### Automated TestFlight with the App Store Connect API key

Each release gets its own iOS version, 0.X.Y.letter → (X-4).Y.n with a=1, b=2 …
(0.5.18.a → 1.18.1, 0.6.0.a → 2.0.1); the build number is the upload time. Versions up to
0.5.1602 used 0.X.(Y*100 + n); `IOS_LEGACY_VERSION=1` rebuilds with that scheme.

`scripts/ios-update-on-approval.py` submits the queued 1.x update the day the version in
review is approved (see "Update on approval" below).

`~/Developer/Chirp/asc.env` (not in the repo) holds `ASC_KEY_ID`, `ASC_ISSUER_ID` and
`ASC_KEY_PATH` (the `AuthKey_<id>.p8`, kept in `~/.appstoreconnect/private_keys`, mode 600).
With it, `./build-ios.sh --testflight` signs and uploads with the key instead of the Xcode
Apple ID, and `scripts/testflight-auto.sh` then runs `scripts/asc.py distribute`: it waits
for processing, sets What to Test from the newest changelog entry, gives the build the
previous build's testers and submits it for Beta App Review.

```bash
python3 scripts/asc.py check            # key works; app and beta groups
python3 scripts/asc.py builds 5         # newest builds and review state
python3 scripts/asc.py expire 202610090932
```

### Step 6B: Sideload to your own iPhone (no Apple Developer account needed)
This is the free path — install Chirp directly on your own phone without
publishing anywhere. The only catch: Apple requires apps signed with a free
account to be re-signed every 7 days, so you'll repeat the last step weekly
(takes under a minute).

1. **Plug your iPhone into your Mac** with a cable, and unlock it.
2. **Trust the computer** if prompted on the phone.
3. In Xcode, open the project if it isn't already: `npx cap open ios`
4. In the Xcode toolbar's device picker (top, next to the Run/Stop buttons),
   select your physical iPhone instead of a simulator.
5. Under the **App** target → **Signing & Capabilities**, make sure
   **Automatically manage signing** is checked, and sign in with your regular
   Apple ID (Xcode → Settings → Accounts) if you haven't already — a free
   Apple ID works fine here, no paid account required.
6. Click the **▶ Run** button. Xcode builds, installs, and launches Chirp
   directly on your phone.
7. The first time, iOS will refuse to open the app with an "Untrusted
   Developer" message. Go to **Settings → General → VPN & Device Management**
   on the phone, tap your Apple ID under "Developer App", and tap **Trust**.
8. Open Chirp from the home screen — it's installed.

**To renew after 7 days:** plug the phone back in and click ▶ Run again in
Xcode. You don't need to repeat the Trust step unless you used a different
Apple ID. **Limits on a free account:** up to 3 apps installed this way at
once, and the app's provisioning profile (not your data) expires weekly —
nothing on the phone gets deleted, the app just stops opening until you re-run
the install.

---

## Step 7: Update the app after web changes

Whenever you update the web app:
```bash
cd chirp-server/frontend
npm run build
npx cap sync ios       # syncs updated dist/ to Xcode project
# Then build/run from Xcode or npx cap run ios
```

---

## Apple Watch app (in testing)

Live Detect from the wrist. Code is in `ios-watch/`; nothing else uses it yet.

```bash
sudo gem install xcodeproj        # once
WATCH=1 PICKER=1 TEAM_ID=F7N9ZF7U57 ./build-ios.sh --testflight
```

- `WATCH=1` adds a watchOS target (`ChirpWatch`, bundle ID `<app>.watchkitapp`, watchOS 10+) to Capacitor's Xcode project and embeds it in the iPhone app. A build without it takes the target back out, so production builds are unchanged.
- Sign-in: the web app asks `POST /api/v1/auth/watch-token` for a 30-day token that only works for Live Detect, and the `ChirpWatch` plugin (`ios-watch/phone/`) passes it to the watch with WatchConnectivity. The watch then talks to the server directly.
- The watch records 4-second clips every 3 seconds (32 kHz mono WAV) and sends them to `/api/v1/live-detect/analyze`, the same endpoint the phone uses. Clips with a bird become recordings.
- To check on a watch: listening with the wrist down, the microphone sample rate, and upload speed when the watch only has the iPhone's connection.
- Shipping it in the App Store version needs Apple Watch screenshots in App Store Connect.

## Native Features Implemented

| Feature | Implementation |
|---------|---------------|
| Haptic feedback | `native.haptic.light/medium/heavy/success/error()` |
| Status bar | Dark style matching #08090d background |
| Splash screen | Green on dark, 1.2s fade |
| Push notifications | Real APNs delivery (see Step 4c) + Web Push for the browser/PWA — both, from one server-side call |
| Network detection | Online/offline state monitoring |
| Audio playback | WKWebView supports HTML5 audio natively |
| Safe areas | `env(safe-area-inset-*)` CSS already applied |

---

## App Store Submission Checklist

- [ ] Apple Developer account ($99/year) at developer.apple.com
- [ ] App ID registered: `com.yourname.chirp`
- [ ] Provisioning profile created (Xcode handles this automatically)
- [ ] App icon 1024×1024 (included in ios-icons/)
- [ ] Screenshots for App Store (iPhone 6.7", 6.5", 5.5"; iPad 12.9")
- [ ] App Store description written
- [ ] Privacy Policy URL (required — app accesses network, microphone via server)
- [ ] Age rating: 4+ (nature/bird monitoring, no objectionable content)

---

## Troubleshooting

**"Untrusted Developer" on device:**
Settings → General → VPN & Device Management → Trust your developer certificate

**White screen on launch:**
- Check server URL in capacitor.config.json is reachable
- Check Info.plist has NSAppTransportSecurity settings (Capacitor adds these)

**"Unable to load" error:**
- Make sure `npm run build` completed successfully
- Run `npx cap sync ios` after every build

**CocoaPods install fails:**
```bash
cd ios/App && pod install --repo-update
```
