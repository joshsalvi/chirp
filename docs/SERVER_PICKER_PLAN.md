# Connect the iPhone app to any Chirp server (plan, not shipped)

Goal: the app opens ourchirp.com by default, and a person can switch it to any
Chirp server by URL (`https://chirp.example.com`) or on the home network
(`http://192.168.1.50:8768`). Nothing here is in the current build; the
App Store version under review keeps `server.url = https://ourchirp.com`.

Draft files, not wired in yet:

- `ios-launcher/index.html` — the bundled start page (below).

## How it would work

Today Capacitor loads `server.url` directly. With a picker:

1. `capacitor.config.json` drops `server.url`; the app starts on a small
   bundled page (`ios-launcher/index.html`, copied into the iOS build's web
   folder by `build-ios.sh`).
2. The launcher reads the saved server (default `https://ourchirp.com`),
   checks `GET <server>/api/v1/health` (2 s timeout) and, if it answers with
   a Chirp `version`, replaces itself with the server
   (`location.replace(server)`). A cold start costs one extra request.
3. If the check fails, or the person long-presses the logo on launch, the
   launcher shows the picker: ourchirp.com, recent servers, or a typed URL /
   IP and port. "Test" runs the health check before saving.
4. Inside the web app, Settings → My Profile gets "Server: ourchirp.com ·
   Change" (iPhone app only), which clears the saved server and reloads the
   launcher.

## Native settings that have to change

| Setting | Now | With the picker | Why |
|---|---|---|---|
| `server.url` | `https://ourchirp.com` | removed | start on the bundled launcher |
| `server.allowNavigation` | ourchirp.com | `["*"]` | any server stays inside the app |
| `ios.limitsNavigationsToAppBoundDomains` | true | false | app-bound domains are a fixed list of at most 10 |
| `WKAppBoundDomains` (build-ios.sh) | from the config | removed | same |
| `NSAppTransportSecurity` → `NSAllowsLocalNetworking` | — | true | plain `http://` to IP addresses and `.local` names |
| `NSLocalNetworkUsageDescription` | — | "Chirp connects to a Chirp server on your home network." | iOS asks before reaching LAN addresses |

## Things to verify before building

1. **Plugins on other servers.** Push, haptics, microphone and the splash
   screen come from the Capacitor bridge. Check on a device that the bridge
   is injected after `location.replace` to a server other than the start
   page (it is injected as a user script for every page in the web view, but
   confirm with the haptics test button and push registration).
2. **Service worker.** Without app-bound domains, WKWebView doesn't run
   service workers. ourchirp.com loses its cached app shell inside the app
   (slower cold start, no offline page). Option: keep ourchirp.com in
   `WKAppBoundDomains` and turn `limitsNavigationsToAppBoundDomains` off, then
   test whether the worker still registers there.
3. **Push on self-hosted servers.** APNs only accepts pushes signed with our
   key (team NM8V6J5ZMF). A server someone else runs can't sign them.
   Built in 0.5.12.p: the push relay on ourchirp.com. A self-hosted server
   gets a relay token (request at /about, approved in Global Admin →
   Requests), pastes it in Settings → Alerts & Email → iPhone Push, and
   posts `{device_token, payload, server}` to `/api/v1/push-relay/send`;
   ourchirp.com signs with CHIRP_APNS_* and forwards. 600 pushes an hour
   per token; tokens can be revoked. The payload carries `server` so the
   app can open the right server when a notification is tapped.
4. **Login state per server.** Tokens live in each server's localStorage
   (different origin), so switching servers keeps each one signed in. The
   launcher should keep a list of recent servers with their names (from
   `/api/v1/health` or `/api/v1/settings/public`).
5. **CORS for the health check.** The launcher runs from `capacitor://localhost`, so `/api/v1/health` needs `Access-Control-Allow-Origin` for that origin (or `*` on that one endpoint) on every Chirp server.
6. **App Review.** A server field is fine, but the review build must still
   open ourchirp.com with the demo account by default. Say so in the notes.

## Effort

| Part | Estimate |
|---|---|
| Launcher page and picker | half a day |
| Config, Info.plist and build-ios.sh changes | 1–2 hours |
| "Change server" in Settings (web app, app only) | 1–2 hours |
| Device testing: plugins, LAN http, push, service worker | half a day |
| Push relay on ourchirp.com | done (0.5.12.p) |

Without the relay it is a contained change, roughly a day including device
testing. The relay is what decides whether other servers get push alerts.
