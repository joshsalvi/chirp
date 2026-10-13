# iOS re-sign on the server

Chirp's iOS app is signed with a free Apple ID, so iOS stops opening it after
7 days. This optional part of the stack re-signs it from Unraid, so the Mac
doesn't have to.

## How it works

- **ios-resign** checks every 5 minutes which iPhones are on the network, using
  [netmuxd](https://github.com/jkcoxson/netmuxd).
- For any phone that is due, it re-signs `App.ipa` and installs it, using
  [AltServer-Linux NG](https://github.com/jaakkopalvaila/AltServer-Linux). That
  fork handles iOS 26.4+/27 and the September 2026 Apple sign-in change.
- A phone is due when it was last signed 5 or more days ago (`RESIGN_EVERY_DAYS`).
- **anisette** (`dadoum/anisette-v3-server`) supplies the data Apple's sign-in
  needs. It runs on this server, so nothing goes to a third party.

When Apple asks for a two-factor code, Chirp emails the admin a link to
`https://iosresign.ourchirp.com/`. Open the page and type in the code within 15 minutes.
The same page shows each phone's last and next re-sign and has a **Re-sign now**
button. A failed re-sign also sends an email.

The app loads Chirp from ourchirp.com, so server updates reach the phones
without a new IPA. Rebuild the IPA on the Mac only when native code changes,
such as a new Capacitor plugin.

## Setup

### 1. Settings

Add these lines to the stack's `.env` (Compose Manager → chirp-server-instances → Edit Stack → Env):

```
COMPOSE_PROFILES=ios-resign
APPLE_ID=you@example.com
APPLE_PASSWORD=your-apple-id-password
RESIGN_EVERY_DAYS=5            # optional: re-sign when this many days have passed (max 6)
RESIGN_POLL_MINUTES=5          # optional: how often to look for phones
RESIGN_DEVICES=                # optional: comma list of phone names or UDIDs; empty = all paired
RESIGN_EXTRA_DEVICES=          # optional: UDID=IP pairs for phones away from home (Tailscale)
RESIGN_WEB_TOKEN=              # optional: the page then needs ?token=...
RESIGN_PUBLIC_URL=https://iosresign.ourchirp.com/
RESIGN_TUNNEL_TOKEN=          # printed by cloudflare_setup.py (step 4)
```

- Use the Apple ID that Xcode signs with. App-specific passwords don't work
  for developer signing.
- Chirp sends its emails to the admin email set in Settings → Alerts & Email.

### 2. The app

On the Mac, build it and copy it here in one step:

```bash
RESIGN_HOST=root@192.168.1.224 ./build-ios.sh --archive
```

You can also build first and copy `build/App.ipa` to
`/mnt/user/appdata/chirp-ios-resign/ipa/App.ipa` yourself.

### 3. Pairing (once per iPhone)

netmuxd needs each phone's pairing record. There are two ways to get one.

**Option A: copy the Mac's records.** The Mac is already paired with both phones.

```bash
sudo scp /var/db/lockdown/*.plist root@192.168.1.224:/mnt/user/appdata/chirp-ios-resign/lockdown/
```

This copies `SystemConfiguration.plist` together with one `<UDID>.plist` per
phone. Keep the two together.

**Option B: pair over Unraid's USB port.**

1. Plug the iPhone in and unlock it.
2. Run:

   ```bash
   cd /boot/config/plugins/compose.manager/projects/chirp-server-instances
   docker compose run --rm --privileged -v /dev/bus/usb:/dev/bus/usb ios-resign pair
   ```

3. Tap **Trust** on the phone.

Either way, the phone must have **Wi-Fi sync** turned on. In Finder or Xcode,
that's "Show this iPhone when on Wi-Fi". It is already on if `build-ios.sh
--install` reaches the phone over Wi-Fi.

### 4. Public link (Cloudflare)

The two-factor link in the email works anywhere through a Cloudflare Tunnel
to `iosresign.ourchirp.com`. Cloudflare Access sits in front of it, so only
the listed emails get in, after a one-time code sent to that address.

`cloudflare_setup.py` creates the tunnel, the DNS record and the Access app,
and prints the tunnel token. It needs an API token with three permissions:
Account → Cloudflare Tunnel: Edit; Account → Access: Apps and Policies: Edit;
Zone ourchirp.com → DNS: Edit.

```bash
CF_API_TOKEN=... python3 ios-resign/cloudflare_setup.py \
  --account 17f7812beec0c527583ac428818fa5fa --zone e985b279e2ea714fc9ecccce7b9c8c20 \
  --hostname iosresign.ourchirp.com --email josh.salvi@gmail.com
```

Put the printed `RESIGN_TUNNEL_TOKEN` in `.env`. The `resign-tunnel`
container runs it.

### 5. Start

Rebuild the stack. The three new containers are `chirp-anisette`,
`chirp-ios-resign` and `chirp-resign-tunnel`. Open
`https://iosresign.ourchirp.com/` (or `http://UNRAID:8099/` at home) to check
that both phones are listed.

## Things to know

- **The Mac and the server renew the same app.** On a free Apple ID, AltServer
  always installs the app as `com.joshuasalvimd.chirp.<team ID>`. Since
  0.5.10.m, `build-ios.sh` builds under that same ID, so either one renewing
  resets the 7 days, and the Mac's scheduled re-sign can stay on as a backup.
  The first build after this change installs it as a new app. Delete the old
  Chirp icon once and sign in again in the new one.
  `SHARED_SIGNING=0 ./build-ios.sh` goes back to the plain ID.
- **Copying the IPA:** `RESIGN_HOST=root@192.168.1.224 ./build-ios.sh --archive`
  copies the new IPA here after each build. The service sets the bundle ID back
  to the plain one before AltServer adds the team ID.
- **Free-account limits:** 3 sideloaded apps per phone, and 10 app IDs a week.
  Re-signing the same app doesn't use a new ID.
- **How often Apple asks for a code** depends on Apple. If the sign-in session
  persists, it asks rarely. If not, it asks at most once per re-sign, so about
  once every 5 days.
- **Phones on the network:** a phone shows up when it's on the same Wi-Fi and
  awake or charging. iOS keeps Wi-Fi sync alive best while charging. A phone
  that isn't seen for 7 days stops opening Chirp until it's re-signed.
- **Away from home (Tailscale):** a phone outside the LAN can't be found by
  name, but it can be reached by IP. Since 0.5.10.n, `RESIGN_EXTRA_DEVICES=
  <UDID>=<IP>[,<UDID>=<IP>]` adds each one to netmuxd before every check.
  Use the phone's Tailscale address. Requirements:
  - Unraid on the same tailnet (it is: `tower`, 100.87.218.118).
  - Tailscale running on the phone (On Demand helps; iOS stops it in the
    background otherwise).
  - The phone paired and Wi-Fi sync on, as above.
  Plain internet access without a VPN can't work, because iOS only accepts
  installs from a paired computer it can reach directly. UDIDs:
  `xcrun devicectl list devices` on the Mac.
- **Logs:** `docker logs chirp-ios-resign`, or the Log section of the page.
- **Download URLs:** to pin a different AltServer or netmuxd build, set
  `ALTSERVER_URL` or `NETMUXD_URL` in `.env` and rebuild.
- **Status:**
  - Built and tested with a simulated AltServer: the two-factor prompt, the
    code page, the success/failure state and the emails.
  - The real AltServer binary was checked for its options and prompts.
  - Not yet tried against Apple and a real phone: the first run is that test.
