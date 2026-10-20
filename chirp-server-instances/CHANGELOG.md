## 0.5.15.c — 2026-10-20 — CRITICAL — Docker image security fixes

- Sign-in and Apple push tokens use PyJWT instead of python-jose (unmaintained, unpatched critical CVE); existing sign-ins keep working.
- The container drops to the chirp user with setpriv instead of gosu (built with Go 1.19).
- Compilers are removed from the image after the build, and setuptools is updated.

## 0.5.15.b — 2026-10-19 — UX — Troubleshooting links

- Settings → Diagnostics and the feedback form link to the troubleshooting page.
- Long commands and addresses on the help pages wrap on phones instead of running off the screen.

## 0.5.15.a — 2026-10-19 — FEATURE — Troubleshooting page; recent recordings on Apple Watch

- New troubleshooting page (ourchirp.com/troubleshooting.html): about 50 fixes across the app, notifications, Apple Watch, stations, sound, detections and running your own server, with search and topics.
- Apple Watch (beta): Recent recordings lists the site's five newest and plays them on the watch (server: GET /watch/recent and /watch/audio/{id}).
- The home page no longer scrolls sideways on phones.

## 0.5.14.z — 2026-10-19 — DEVELOPER — Docker Hub build fixed

- The Docker Hub build failed on arm64 (no tensorflow-cpu for ARM); ARM now uses tensorflow, and the chirp image is built for amd64 only until arm64 is tested.
- Docker Hub overviews for the three images (unraid/dockerhub/), set by the publish workflow.

## 0.5.14.y — 2026-10-18 — UX — Only Back restores the Recordings list

- Back (or Forward) returns Recordings to the same page, filters and scroll; opening it from the tab bar, menu or a link starts on page 1 with no filters (grid/list view and page size are kept).

## 0.5.14.x — 2026-10-18 — UX — Recordings list remembers where you were

- Leaving Recordings and coming back keeps the page number, filters (station, time of day, saved, date range), search and scroll position.

## 0.5.14.w — 2026-10-18 — BUGFIX — Maps stay under the tab bar

- The recording and range maps no longer draw over the bottom tab bar and header when scrolled.

## 0.5.14.v — 2026-10-18 — UX — What's New popup brought up to date

- The What's New popup shows again, covering per-bird AI ratings, the Low pitch view and Back/Forward.

## 0.5.14.u — 2026-10-18 — FEATURE — Low pitch view for owls

- Recordings with an owl or another low caller open with low notes stretched (mel spacing), so their calls get room instead of a thin line at the bottom.
- A Low pitch toggle above the spectrogram switches any bird recording between that and even pitch spacing.

## 0.5.14.t — 2026-10-18 — ENHANCEMENT — Profile photos on notes

- Notes, All Notes and the dashboard's Recent comments show each author's profile photo instead of their initial.

## 0.5.14.s — 2026-10-18 — BUGFIX — Profile photos show after upload

- Uploaded profile photos never showed (the address put the file extension into the user ID, so it was never found); a new upload also replaces the cached old photo.

## 0.5.14.r — 2026-10-17 — BUGFIX — Maps without the CARTO watermark

- The recording and range maps use a CARTO key (CHIRP_CARTO_KEY, also in the Unraid template); CARTO now marks tiles "API key required" without one.

## 0.5.14.q — 2026-10-17 — UX — Station versions: Chirp stations only

- Changelog → Device no longer lists Bird Buddy feeders and Haikuboxes, which don't run Chirp's station software.

## 0.5.14.p — 2026-10-17 — BUGFIX — Notifications only from the server the app shows

- Change server in the iPhone app now takes the phone off the old server's push list first; going back adds it again.

## 0.5.14.o — 2026-10-17 — BUGFIX — No duplicate notifications from a retired server

- New setting CHIRP_NOTIFICATIONS_OFF=1 stops a server's pushes, emails, journals and digests; on for the retired chirp.joshuasalvimd.com server, which was sending a second Daily Journal.

## 0.5.14.n — 2026-10-17 — ENHANCEMENT — AI Second Opinion: one row per bird

- One row per detected bird, each with its photo and its own rating on the scale; the AI's full read is under More.
- The AI now gives each bird its own verdict, and the audio check runs for every bird, not just the top one.

## 0.5.14.m — 2026-10-17 — BUGFIX — Changelog history restored; station versions

- The Changelog page shows every release again (releases since 0.5.14.b had replaced the history).
- Changelog → Device lists each station's installed version and whether a newer one exists.

## 0.5.14.l — 2026-10-17 — UX — Logo back at top left; Back goes up to five pages

- On phones the Chirp logo is back at the top left, with the back and forward buttons after it.
- Back goes up to five pages.

## 0.5.14.k — 2026-10-17 — FEATURE — Back and forward buttons; v3 drops station night callers it doesn't confirm

- Back and forward buttons at the left of the top bar, on every page and in the iPhone app; greyed out when there's nowhere to go.
- With BirdNET v3, station detections v3 didn't confirm are removed, night callers included (a 35% daytime Common Nighthawk stayed before).

## 0.5.14.j — 2026-10-17 — ENHANCEMENT — AI Second Opinion rating on a scale

- The rating shows as a four-step bar from Likely wrong to Likely right, with only the reached step lit and labelled.

## 0.5.14.i — 2026-10-17 — BUGFIX — Detection rows fit on phones

- A recording's detection rows wrap onto two lines on narrow screens: time and confidence, then Jump, Clip and Enhance, nothing overlapping or cut off.

## 0.5.14.h — 2026-10-17 — ENHANCEMENT — What's New for this week's changes

- New What's New popup: AI Second Opinion's single rating, its audio check for short calls, and BirdNET v3's minimum applying to station detections.

## 0.5.14.g — 2026-10-17 — BUGFIX — Audio check hears short calls

- AI Second Opinion's audio check now measures short calls (chips, "pik"s, 20–50 ms) too; faint Downy Woodpecker and chickadee calls at 6–8 kHz read as "nothing above the background" before.
- The AI gets those measured frequencies, so it no longer guesses them from the image.

## 1.4.4 (chirp-device) — 2026-10-17 — BUGFIX — Hum check logs both mains families

- Each hum check logs the 60 Hz and 50 Hz readings; 50 Hz is chosen only when it leads by 3 dB (weak hum read as 50 Hz in Massachusetts).

## 1.4.3 (chirp-device) — 2026-10-17 — BUGFIX — Hum filter stays on

- Once on, the hum filter turns off only after two checks in a row find the hum under 5 dB (one quiet check had let it off for 5 minutes at a time).
- Each check logs how far the hum stands above its neighbours, to compare wiring changes.

## 0.5.14.f — 2026-10-17 — BUGFIX — No station detections below the v3 minimum; tidier color picker

- With BirdNET v3, when the server pass finds nothing, the station's own (BirdNET 2.4) detections are removed too, as they already were when it found something; night callers are still kept.
- Detection colors: one color strip per palette that fits the card, shorter descriptions.

## 0.5.14.e — 2026-10-16 — ENHANCEMENT — AI Second Opinion gives one overall rating

- The card opens with one rating (Likely right, Probably right, Uncertain or Likely wrong) that combines the AI's read of the spectrogram with the audio check.
- Audio check findings are listed under the rating; the AI's full reasoning folds under "Why".

## 0.5.14.d — 2026-10-16 — BUGFIX — Request form choices; Getting Started Back to top

- About page: the Request access choices show the dot beside the text.
- Getting Started: Back to top works on phones (the cards no longer shift when tapped).

## 1.4.2 (chirp-device) — 2026-10-16 — FEATURE — Mains hum filter

- Notches mains hum (60 or 50 Hz and harmonics to 1 kHz, 3 Hz wide) on each mic before detection, recordings and night audio.
- audio.hum_filter: auto (default; on only when hum stands 10 dB out, rechecked every 5 minutes), 60, 50 or off.

## 0.5.14.c — 2026-10-16 — ENHANCEMENT — Clearer model settings; chirp.joshuasalvimd.com retired

- Detection Model: v3's minimum confidence sits under the v3 choice and says what it does.
- BirdNET Analysis is now BirdNET 2.4 Settings and shows only when 2.4 is the model; defaults in its hints corrected (5%, 2.5, 1.5).
- Retired hostnames redirect to the new address (CHIRP_REDIRECT_HOSTS, CHIRP_REDIRECT_TO); API calls get 410. chirp.joshuasalvimd.com now goes to ourchirp.com.
- The station config sends uploads and heartbeats to ourchirp.com only.

## 0.5.14.b — 2026-10-16 — ENHANCEMENT — Softer Dashboard photo edge

- The Live card's photo fades only slightly at its edges.

## 0.5.14.a — 2026-10-16 — FEATURE — BirdNET v3 by default, saved recordings, one Enhance control

- BirdNET v3 is the default model, with owl checks (a hoot at the owl's pitch; 80% in daylight); BirdNET 2.4 selectable in Settings → Detection.
- AI Features and Bats have their own Settings tabs; Experimental keeps Nighthawk, range maps and the heatmap.
- Settings search finds every card, tab and setting.
- Recordings filter by time of day (site time zone) and by Saved; saved recordings skip automatic archive and delete.
- One Enhance control on recordings and calls: Original, Enhanced (low cut and noise reduction) or AI.
- Night Calls by night, week or month, grouped by family; each call has its own page with a large spectrogram.
- Confidence badges match the Recordings list (green for high).
- Phone ⋯ menu in three groups; Dashboard photo fades into the card.
- Guide pages' header matches the About page; Getting Started and User Guide updated.
- Docker Hub workflow, .dockerignore and Unraid Community Applications templates.

## 1.4.1 (chirp-device) — 2026-10-16 — BUGFIX — No gaps in the detection audio

- The mic mixer waits for each primary chunk instead of filling 0.15 s timeouts with silence (about half of every second was silent).
- Fixes choppy night audio, "-inf dBFS" levels and missed calls on the detection path; recordings were unaffected.

## 0.5.13.e — 2026-10-16 — BUGFIX — Night Calls playback and labels

- Play works: a page of thumbnails no longer uses up the database connections; clips play as WAV.
- Spectrograms are made when a call is found, not when the page opens.
- Sound-alike groups are named for what they could be ("Swamp or Lincoln's Sparrow", "Warbler, one of 13") and list every species.
- Calls only placed as "songbird" are hidden behind a button; a "How sure is each call?" key explains each level.

## 0.5.13.d — 2026-10-15 — ENHANCEMENT — Clearer Settings text

- Empty Recordings: plain names for the two counts ("show nothing", "nothing from the server") and both delete buttons.
- Settings descriptions shortened and reworded throughout.
- AI Second Opinion uses that name in Settings too.

## 0.5.13.c — 2026-10-15 — BUGFIX — Re-analyze with BirdNET v3, Tailscale on Unraid

- Re-analyze runs BirdNET v3 when it's on, both to compare and as the main model.
- AI Second Opinion no longer fails when Re-analyze replaces the detections mid-run.
- Tailscale socket moved off the Unraid share; the hourly mover broke it every hour.
- tailscaled gets a state directory (stops the tailnet-lock log spam) and its log is trimmed past 20 MB.

## 0.5.13.b — 2026-10-15 — ENHANCEMENT — Station offline alert delay

- Station offline alerts wait 15 minutes by default; set the delay in Settings → Alerts & Email.
- Station alerts go only to signed-in admins' devices.

## 0.5.13.a — 2026-10-15 — FEATURE — BirdNET v3 and night flight calls (experimental)

- Settings → Experimental → Detection Models: compare each recording with BirdNET v3, or use it as the main model.
- Recording pages show a BirdNET v3 comparison card when comparing is on.
- Night flight calls: stations upload night audio and Nighthawk lists migrant calls on a new Night Calls page.
- Clearing all notifications asks first; deleting an account needs "delete" typed.
- Wikipedia searches for the AI journal send a contact URL, as Wikipedia asks (it was answering 403).
- Tailscale goes straight to userspace networking after kernel TUN is refused once.

## 1.4.0 (chirp-device) — 2026-10-15 — FEATURE — Night audio for Nighthawk

- Uploads 10-minute 22.05 kHz FLAC chunks during the night hours a server asks for (GET /night-calls/accepting); off for servers that don't.
- Backlog capped at night_audio.max_backlog_gb (3 GB); needs soxr.

## 0.5.12.ae — 2026-10-14 — BUGFIX — Watch sessions saved to Recordings

- Stopping Live Detect on the watch saves the session to Recordings with its full audio, as the phone's Save session does.
- The watch sign-in can save Live Detect sessions.
- Live Detect is no longer marked Beta.

## 0.5.12.ad — 2026-10-14 — ENHANCEMENT — Watch app logo

- The watch app shows the Chirp logo at the top; its bars move while listening, as on the Live Detect page.

## 0.5.12.ac — 2026-10-14 — BUGFIX — Apple Watch sign-in

- The iPhone app now sends the watch its sign-in; the watch link never finished starting before.

## 0.5.12.ab — 2026-10-14 — DEVELOPER — Watch plugin check

- Logs which native plugins the iPhone app reports when the watch link is missing.

## 0.5.12.aa — 2026-10-14 — BUGFIX — Apple Watch sign-in check

- My Profile → Apple Watch shows whether a watch is ready and sends it the sign-in again.
- Each watch sign-in attempt is logged on the server to help find why a watch isn't signed in.

## 0.5.12.z — 2026-10-14 — FEATURE — Apple Watch groundwork

- Apple Watch app for Live Detect (ios-watch/), built into test builds with WATCH=1; not in the App Store version yet.
- POST /api/v1/auth/watch-token: a 30-day sign-in that only works for Live Detect; the iPhone app passes it to the watch.

## 0.5.12.y — 2026-10-14 — ENHANCEMENT — iPhone app versions

- Changelog's iPhone App tab lists only uploaded app builds; server-only releases leave the app version unchanged.
- Each app version lists the Chirp releases it brought; build-ios.sh records new builds in appReleases.json.

## 0.5.12.x — 2026-10-14 — ENHANCEMENT — Station offline alerts

- Admins can turn on Settings → My Notifications → Stations: a push and/or email when a station sends no heartbeat for 10 minutes, and another when it's back with how long it was down. Off by default.
- Checked every minute per site (services/device_alerts.py); Haikubox and Bird Buddy are skipped, and stations silent for over a day before the check are not announced.
- New columns: users.notify_device_offline_push, users.notify_device_offline_email, devices.offline_since.

## 0.5.12.w — 2026-10-14 — ENHANCEMENT — Menu label

- About page menu says "Set up", matching the guide pages.

## 0.5.12.v — 2026-10-14 — ENHANCEMENT — Setup guide and user guide

- New /setup.html: station parts and Pi setup, install, three ways to connect (approval email, Discover → Auto-configure, manual key), testing, hosted or self-hosted server, HTTPS and push, app and invites, troubleshooting.
- New /guide.html: every page, Settings tab by tab, devices, people and roles, My Profile.
- Linked from About (nav, cards, FAQ, footer), Support, sign-in, Settings, Tutorial, Devices, My Profile, the approval and relay emails, README and install.sh.
- chirp-server-instances/docker-compose.simple.yml and .env.simple.example: one container for running your own server.
- chirp-server (single site) marked deprecated in its README and the guides; move with Import from Database File.
- Users page shows the site's invite code with Copy invite (site admins could only see it in the approval email).
- Approval email: correct service name (chirp-device), venv step and guide links.
- About, Support and Privacy load the full icon set with version tags, so browsers drop the old cached icon.

## 0.5.12.u — 2026-10-13 — BUGFIX — Support and About links open in the browser

- My Profile's support page link and the sign-in screen's "What is Chirp?" open in Safari (a new tab on the web) instead of inside the app.
- The What's New popup shows again only when its text changes, not on every small fix.

## 0.5.12.t — 2026-10-13 — ENHANCEMENT — Contact form and feature ideas

- Support page has a contact form (question, problem, feature idea) instead of an email address; the About page links to it.
- My Profile → Help & Feedback sends a feature idea, problem or question from the app (POST /api/v1/support, rate-limited).
- Messages are emailed to the server's admins and, on ourchirp.com, listed in Global Admin → Requests with Mark done.
- About page: the station → server → app diagram shows its arrows again, nav links line up with Sign in, and every card ends in the same pair of buttons (in-page action, plus GitHub links that open in a new tab).
- App Store link placeholder in public/site.js; setting CHIRP_APP_STORE_URL there shows the App Store buttons on About and Support.

## 0.5.12.s — 2026-10-13 — ENHANCEMENT — One password, shorter What's New

- Joining a site needs only the invite code; the separate location password is gone from sign-up, Join, New Location, Import and Global Admin → Add member.
- Changing a password (My Profile, or an admin resetting one) changes the sign-in password and the copy on every site.
- What's New popup: at most three short items, earlier releases of the current version collapsed.
- Changelog: major versions (0.5, 0.4…) as cards with a one-line summary, each minor version with its own line; summaries live in lib/whatsNew.js.

## 0.5.12.r — 2026-10-13 — BUGFIX — Live Detect on http:// servers

- Live Detect on a plain http:// server address (e.g. a home-network IP in Chirp β) said microphone access was off; iOS and browsers give http:// pages no microphone. It now says the server needs an https:// address, and the app's permissions card shows the same.
- The picker's custom-server note says Live Detect needs https://.

## 0.5.12.q — 2026-10-13 — ENHANCEMENT — Server picker test build

- PICKER=1 ./build-ios.sh --testflight builds "Chirp β": same app, starts on ios-launcher/index.html to choose ourchirp.com or a custom server (address or IP:port), uploaded for internal testers only.
- Picker builds allow any server, plain http:// on the home network (with iOS's local-network prompt), and send links to other sites to Safari; the release build is unchanged.
- In picker builds, the sign-in screen and My Profile → Server have "Change server"; tapping a relayed push opens the server it came from.
- Push relay requests: the server address is optional; the relay never connects to the server.

## 0.5.12.p — 2026-10-12 — ENHANCEMENT — Site requests and push relay

- ourchirp.com/about takes requests for a hosted site or a push relay token; ourchirp.com's front page opens /about for visitors who aren't signed in.
- Global Admin → Requests: approving a hosted site creates the account, site, location and device key, and emails sign-in and device setup steps.
- Push relay (POST /api/v1/push-relay/send): self-hosted servers send iPhone pushes through ourchirp.com with a relay token; Global Admin issues and revokes tokens.
- iPhone push uses the site's APNs key, then a server-wide key from CHIRP_APNS_* (never shown to site admins), then the relay.
- Settings → Alerts & Email → iPhone Push shows how pushes are sent and takes a relay token; own-key fields moved under "Use your own APNs key".
- About page links to GitHub and lists the three ways to start.
- Code is public at github.com/joshsalvi/chirp under the PolyForm Noncommercial 1.0.0 license; scripts/publish-public.sh builds that copy without the patent draft, App Store tooling or device keys (chirp-device/config.yaml.public, from scripts/make-public-config.py).

## 0.5.12.o — 2026-10-11 — ENHANCEMENT — About page

- Public page at /about (frontend/public/about.html): what Chirp is, how it works, features with app screenshots, setup and FAQ; linked from the sign-in screen ("What is Chirp?").
- App Store marketing URL in docs/app-store-metadata.json is now https://ourchirp.com/about (applies with the next App Store version).
- docs/SERVER_PICKER_PLAN.md and a draft ios-launcher/index.html for connecting the iPhone app to any Chirp server; not in any build yet.

## 0.5.12.n — 2026-10-11 — BUGFIX — Headscale admin socket watchdog

- Global Admin's Headscale panel timed out: headscale 0.23.0 kept serving clients while its admin socket stopped answering ("context deadline exceeded" from every CLI command).
- The node-list wrapper now checks the socket every 5 minutes and restarts headscale after two failures in a row; clients reconnect within seconds.
- The wrapper answers requests in parallel, waits up to 15 s for the CLI, and returns the CLI's error (503) instead of a timeout; the server waits 20 s.
- App Review reply shortened to 3,467 characters (docs/APP_REVIEW_RESPONSE.md).

## 0.5.12.m — 2026-10-11 — BUGFIX — Fewer false owls

- A hooted owl on the band-limited copy also needs a full-band score of 0.30 for that owl (HOOT_FULL_MIN); the strong-owl bar is 0.45 (was 0.40).
- Device owls stay only when the server pass finds that owl too, including when it finds nothing else.
- An owl from an earlier pass keeps its score on re-analysis only with full-band support on the new audio.
- Tested on Natick field recordings: false owls on 231 midday recordings 20 → 1, field Barred Owls 16 of 16, clip set 81 hits / 7 wrong / 0 false alarms (was 81 / 8 / 1).
- owl_eval.py: --extra-pos for labeled field owls, --focus grid over the score rules, results per group.
- Recent recordings with owls were re-analyzed under the new rules.

## 0.5.12.l — 2026-10-11 — ENHANCEMENT — Same-day digest, Settings reorganized, test emails fixed

- Digest push and email each have a separate send time in the site's time zone (default 9 PM); from noon on a digest covers that day so far, earlier times cover yesterday.
- Digest days follow the site's time zone (they ran midnight to midnight UTC), and the digest page can show today so far.
- Each bird's play button on the digest page opens Recordings filtered to that bird; ?species= links (also from bird profiles) now filter, with a clearable banner.
- Settings: new General tab (location, time zone, web address, what everyone sees, dashboard sections); Alerts & Email (digest times, email server, APNs); eBird keys under Integrations; Access & Security (sign-in, device keys, activity log, network); card layout and app install under Appearance.
- The unused webhook URL is gone; its switch is now "New-species emails" in the email card.
- My Notifications shows when the digest arrives.
- Send Test, Test New Bird and Test Digest no longer return 500 and use the same designs as the emails people receive.
- Email works with plain SMTP (port 25) and SSL on port 465 whatever the STARTTLS switch says.
- Email links point to the full digest page.

## 0.5.12.k — 2026-10-10 — BUGFIX — Faster Live Detect saves, digest sends once per day

- Saving a Live Detect session no longer waits behind other Live Detect checks: clip decoding and BirdNET run off the server's request loop, and the saved recording opens as soon as its spectrogram is ready.
- The digest records the day it covered (not the UTC date it went out) and sends at the first digest hour after that day ends, so an evening digest hour no longer repeats the same day.

## 0.5.12.j — 2026-10-10 — BUGFIX — Dependable daily digest, delete one notification

- The daily digest only went out if the once-a-minute check landed in minute 0 of the digest hour, so some days were skipped; it now goes out once per UTC day at or after the hour (AppSettings.digest_last_sent_on), and a missed one catches up.
- Each notification has its own delete button (DELETE /notifications/{id}); the trash icon still clears all.
- Settings → My Notifications no longer shows Dashboard Style and Dashboard Sections, which appeared in whichever tab was open when their data finished loading.

## 0.5.12.i — 2026-10-10 — ENHANCEMENT — Daily digest page

- The daily digest opens a full page (/digest?date=…) with the day's totals, first-time birds, activity by hour and every species with its photo, first time heard, best confidence and best recording, with previous/next day arrows; it replaces the pop-up.
- Older digests in Notifications, including ones saved without details, open the page for their day (new GET /recordings/statistics/digest?date=, from the same numbers as the email digest).

## 0.5.12.h — 2026-10-10 — BUGFIX — Digest pop-up restored

- Tapping the daily digest push, or a digest in Notifications, opens a pop-up with that day's totals, new species, busiest hour and every species (restores a separate 0.5.12.f build from 2026-10-09 that the 0.5.12.f release replaced).
- The Journal's Yesterday card and GET /recordings/statistics/yesterday-digest from 0.5.12.f are removed; the pop-up replaces them.
- Push links are always stored and sent as in-app paths (server, app and service worker); inbox rows keep the digest details for the pop-up.

## 0.5.12.g — 2026-10-10 — ENHANCEMENT — Expandable iPhone app versions

- Each version in What's New → iPhone App opens to show that release's changes; the installed version (or the newest) starts open.

## 0.5.12.f — 2026-10-10 — ENHANCEMENT — Report and block notes, digest in the app, iPhone app version

- Notes have ⋯ → Report (inbox and push to the site's admins) and Block (hides that person's notes for you); My Profile → Blocked People unblocks.
- Notes are credited to the signed-in person, and only the author or an admin can edit or delete one (the server enforced neither).
- The morning digest push opens a Yesterday card in the Journal (new GET /recordings/statistics/yesterday-digest) instead of a full web address the app couldn't open.
- Notification links to this site open inside the app, including older ones saved with a full address.
- What's New has an iPhone App tab listing the iOS version of each release; the popup and Settings show the installed version.

## 0.5.12.e — 2026-10-09 — ENHANCEMENT — Haptic feedback across the iOS app

- Haptics on every tap, tab and section change, toggle, picker and slider, with a firmer tap for delete-style buttons.
- Haptics for outcomes: settings saved, uploads, copies, shares, sign-in, failed actions, new detections and Live Detect hits.
- scripts/asc.py listing pushes App Store text, URLs, categories, review notes and screenshots from docs/app-store-metadata.json.

## 0.5.12.d — 2026-10-09 — DEVELOPER — Distinct iOS version per release

- Each release uploads to TestFlight as its own app version: the patch letter becomes part of the third number (0.5.12.d → 0.5.1204).
- scripts/asc.py submits each build for beta review before adding testers, and retries Apple errors one tester at a time.

## 0.5.12.c — 2026-10-09 — ENHANCEMENT — Faster app, simpler Settings

- The app opens from the last verified sign-in, hides the launch screen right away and loads other pages in the background.
- Returning to a page within 30 seconds reuses its data; any change, new detection or notification refreshes it.
- Settings on iPhone is a list of sections with a back button; wider screens keep a sidebar with icons.
- Settings search lists matches as you type, including settings inside closed cards, and opens the card.
- A Save bar appears only when site settings have unsaved changes; edits survive leaving the page, and Discard undoes them.
- Viewers' Settings no longer loads site settings; storage, key and device data load when their section opens.
- Settings sections renamed: Site Alerts, Access & Keys, Experimental; alert cards are Webhooks, Email (SMTP) and iPhone App Push (APNs).
- TestFlight uploads use the App Store Connect API key and give each new build the previous build's testers and a beta review submission (scripts/asc.py).

## 0.5.12.b — 2026-10-09 — ENHANCEMENT — Device location for device Live Detect

- Live Detect through a Chirp device saves and uses that device's location (its latest reported GPS, else its config); phone Live Detect keeps using the phone's GPS.
- build-ios.sh no longer stops silently when an App Store signing profile (which has no device list) is cached.

## 0.5.12.a — 2026-10-09 — FEATURE — My Notifications, watched birds, journal pushes, Live Detect location

- Settings → My Notifications for everyone (the rest of Settings stays admin-only): push for new species, Daily Journal (6 pm), Weekly Journal (Sunday noon) and the morning digest, plus email; linked from the Notifications tab and My Profile.
- Watched birds: Notify me on a species page or in My Notifications, every time (at most one per 10 minutes, opens the recording) or a 7 pm daily summary.
- Push alerts open what they're about: new species and watched birds go to the recording, journals to the new Journal page.
- Live Detect can save the phone's location with its recordings and uses it for BirdNET's likely-species filter ("Use my location", on by default).
- The Field Guide shows the site's town instead of its street address; viewers no longer see site-wide Display Preferences or the Save buttons.

## 0.5.11.d — 2026-10-09 — FEATURE — Delete account in the app; App Store prep

- My Profile → Delete account (POST /api/v1/auth/me/delete, password required) removes the person's sign-in, memberships, notes, notifications and push registrations; the only admin can't delete themselves.
- New support page (ourchirp.com/support.html); the privacy page points to in-app deletion.
- iOS builds are iPhone-only (IPHONE_ONLY=0 to include iPad); docs/APP_STORE_LISTING.md has the full App Store and TestFlight text.
- With sign-in off, notifications go to the shared inbox even when user accounts exist.

## 0.5.11.c — 2026-10-09 — CRITICAL — Native push signing

- services/apns_push.py imported PyJWT ("import jwt"), which isn't in requirements, so every APNs send failed with ModuleNotFoundError and no push ever reached the iOS app. It now signs the ES256 provider token with python-jose (already installed for sign-in tokens); the key text is stripped first. Test: test_notifications_inbox.test_apns_token_is_es256_with_installed_libraries.
- The APNs key for team F7N9ZF7U57 (key NM8V6J5ZMF, bundle com.joshuasalvimd.chirp, production with sandbox fallback) is set on the Natick location and on chirp-server.

## 0.5.11.b — 2026-10-09 — CRITICAL — Viewer accounts are read-only; privacy page

- The API had no role check on recording changes: a "viewer" could edit, archive, re-analyze, run AI Second Opinion on, or delete recordings, upload, change bird photos and more. AuthMiddleware now refuses every POST/PUT/PATCH/DELETE from a viewer (403 "This account is view-only") except their own account (auth/me/*, login, logout, activity ping), instances/switch|join, notifications, push, diagnostics/client, recordings/ai-warm, recording and bird notes (comments), share links, birds/ensure and live-detect/analyze (main.viewer_may_write). RecordingDetail hides Edit, Re-analyze, AI Second Opinion, Archive and Delete for viewers.
- frontend/public/privacy.html (https://ourchirp.com/privacy.html): what Chirp stores, microphone use, who else receives data (Apple for push, bird information services, AI providers when enabled, iNaturalist on request), no ads or tracking, deletion and contact.
- docs/APP_STORE_LISTING.md: App Store Connect and TestFlight text, review sign-in notes and the screenshot list.
- Tests: tests/test_viewer_readonly.py.

## 0.5.11.a — 2026-10-09 — FEATURE — Notifications tab, iPhone push, TestFlight build

- Notifications inbox: InboxNotification table (inbox_notifications), services/notification_inbox.record() called by send_push_to_all for every send (one row per active user passing the same user_filter as the push, or one shared row with sign-in off; 90-day retention), api/notifications.py (GET list with unread count, GET /unread, POST /read-all, POST /{id}/read, DELETE). POST /api/v1/push/test-native sends a test push to the signed-in person's iPhones and records it.
- App: Notifications page (/notifications) with per-kind icons, unread dots, clear and refresh, a push-off card with Allow; a Notifications tab in the mobile bottom bar with an unread badge (Field Guide moves to the ⋮ menu) and a sidebar entry with a dot; lib/unread.js refreshes the count every minute, on return to the app and when a push arrives. A push arriving while the app is open refreshes the inbox; tapping a banner opens its page (previously any received push navigated).
- First launch of the iOS app (after sign-in): the setup card now asks for notifications and then the microphone by itself, shows the result and closes; the Allow buttons stay as a fallback.
- APNs: send_apns_push tries the configured environment, then the other one when Apple answers BadDeviceToken, so TestFlight (production) and Xcode-installed (sandbox) phones both receive pushes from one server; a token is dropped only when both reject it or Apple reports Unregistered.
- build-ios.sh: --testflight (paid team: plain bundle ID, App Store Connect export with destination upload; refuses a free team), PUSH=auto (aps-environment entitlement for a paid team, off for a free team), BUNDLE_ID override, ITSAppUsesNonExemptEncryption NO, and the AppDelegate callbacks Capacitor's push plugin needs to receive the APNs token. Device registration also runs for TestFlight (a new team needs a registered device before Xcode can sign anything).
- Tests: tests/test_notifications_inbox.py.

## 0.5.10.s — 2026-10-09 — BUGFIX — iPhone sign-in

- Usernames matched case-sensitively and untrimmed, and the login inputs let iOS capitalise and autocorrect, so "Joshsalvi" or "annie " failed with valid passwords. auth.find_by_username: exact match first, else a single case-insensitive match (accounts differing only by case stay exact); used by login in both forks. New usernames are trimmed and checked case-insensitively (register, admin create). Login inputs set autoCapitalize="none", autoCorrect="off", spellCheck=false and autocomplete hints; username and email are trimmed before sending.
- The failed-login limit (5 in 5 minutes) was keyed by username plus the socket address, which is the Caddy proxy for every request, so one phone's failures locked that username for everyone; the app then showed the 429 as "Incorrect username or password". The key now uses CF-Connecting-IP, else the first X-Forwarded-For hop, else the socket address (auth.client_address), and the login screen shows the "Too many failed login attempts. Try again in N seconds." message.
- Tests: tests/test_username_login.py.

## 0.5.10.r — 2026-10-08 — BUGFIX — iPhone header spacing when shifted

- With the page shifted (0.5.10.q) the header still added the full 62 pt top inset, leaving ~60 pt of empty space under the status bar. In html.vp-shift, --inset-top is the inset minus the shift plus 32px, which clears the Liquid Glass blur (~90 pt from the top of the screen). client-diag reports once the 500 ms check has settled (the first reading on launch had no inset yet).

## 0.5.10.q — 2026-10-08 — BUGFIX — iPhone page shifted into place

- Replaces the 0.5.10.n-p viewport corrections (stretching the shell and moving bottom elements by a measured or predicted gap, plus the touch-based page-offset check), which left the bar too high, pushed it off-screen, or misfired. Per client-diag from the phone (iOS 27.0.1: screen 874, page 812, top inset 62, page drawn from the top), the page is the right size in the wrong place. viewportFix.js now sets --vp-shift to the shortfall (portrait Home Screen or iOS app, top inset present, 16-120 px; height first seen per orientation) and html.vp-shift translates <body> down by it, carrying the fixed header and bottom bar. Per-element --vp-gap offsets, --vp-h and --vp-top are removed. client-diag is sent once per launch.

## 0.5.10.p — 2026-10-08 — BUGFIX — iPhone bottom bar measured, not predicted

- 0.5.10.o pushed the bottom bar 62 pt below the screen on iOS 27.0.1. The phone reported screen 874, viewport 812, top inset 62, page at the top of the screen (client-diag): stretching the shell to 874 already moved where position:fixed bottom:0 anchors, and the bar was then moved down by the 62 pt gap as well. viewportFix.js now stretches the shell first, measures a fixed bottom:0 probe and sets --vp-gap only to what is still missing (0-120 px). The page height first seen per orientation is kept, since iOS may report the stretched height afterwards. client-diag reports anchorGap, fixedBottom and the live height, up to three times per launch.

## 0.5.10.o — 2026-10-08 — BUGFIX — iPhone app position check

- 0.5.10.n's viewport fix only acted when iOS reported a top safe-area inset. On iOS 27.0.1 the Home Screen app is drawn from the top of the screen with no top inset and a viewport one status bar (62 pt) short, which looks the same as a correct "black" install to the measurements, so nothing changed. viewportFix.js now reads the page's position from the first touch (Touch.screenY - clientY, remembered per viewport height); at 0 it adds the shortfall as top inset (--vp-top, folded into --inset-top) and extends the bottom as before.
- POST /api/v1/diagnostics/client logs what the app reports (screen and viewport sizes, insets, page offset, visual viewport, user agent) as "client-diag" in the server log, once per launch in a Home Screen or iOS app, so device-only layout bugs can be checked from the server.

## 0.5.10.n — 2026-10-08 — BUGFIX — iPhone app fills the screen; device night floor kept; iOS re-sign reaches phones over Tailscale

- iPhone Home Screen app: back to apple-mobile-web-app-status-bar-style "black-translucent". "black" (0.5.10.m) did not fix it on iOS 27: iOS 26.1+ and 27 still drew the page from the top of the screen with a layout viewport short by the status bar (WebKit bug 301994), so it sat too high with a band under the bottom bar. src/lib/viewportFix.js measures the shortfall (standalone or the iOS app, top inset present, 16-120 px) on launch, resize, rotation and return, and sets --vp-gap/--vp-h: the shell grows to the screen height and the bottom bar, its menu, Settings' save bar, Scroll to top, the permission sheet and the Home Screen notice move down by the gap. The re-add notice for a stale translucent install is retired.
- Docker image: a build step imports tensorflow.lite and birdnetlib, so an incomplete install fails the build. The "|| true" after playwright install-deps also hid pip failures; a full Docker disk on Unraid had produced an image without tensorflow/python, and server BirdNET and re-analysis failed with "No module named 'tensorflow.python'".
- Device config push (devices.with_night_rule): in "night" and "per_species" modes the server keeps a night_species_min_confidence the device's managed config already has, falling back to 0.10 only when it has none; "global" still sends min_confidence. It used to overwrite it with 0.10 on every pull, which re-opened the 0.10–0.17 "Unknown" flood on the Natick Pi after its floor was raised to 0.20.
- ios-resign: RESIGN_EXTRA_DEVICES (UDID=IP pairs) adds phones to netmuxd by IP (its AddDevice extension) before each check, so an iPhone on the same Tailscale tailnet as the server is re-signed away from home. The service can't reach a phone over the plain internet: installs need a lockdown connection to a paired computer. compose passes the variable; README covers setup.
- Tests: test_ios_resign.test_add_by_ip_packet (AddDevice frame and plist); test_night_thresholds covers a device's own floor in each mode. Both files now in chirp-server too.

## 0.5.10.m — 2026-10-08 — ENHANCEMENT — Full-screen PWA, night-caller threshold modes, faster AI Second Opinion, new daily email, iOS re-sign service

- iPhone home-screen app: apple-mobile-web-app-status-bar-style "black" instead of "black-translucent". On iOS 26 a translucent standalone app gets a full-screen frame but a layout viewport short by the status bar (62 pt), so the fixed bottom nav floated above a black band; the 2.5rem "Liquid Glass" header padding is gone with it. Installs made before this keep the old setting until re-added; HomeIconNotice detects that (top safe-area inset in a portrait standalone app) and shows the re-add steps.
- Night-caller thresholds: AppSettings.night_threshold_mode ("night" floors, "global" birdnet_min_confidence, "per_species") and night_threshold_species. birdnet_pass.species_required/uses_night_floor/night_rules shared by the server pass, re-analysis reasons, near-miss defaults, purge protection (owls are only protected while they use the night floor) and device detection retention. GET /near-misses/night-species and a Settings → Detection panel. Devices get night_species_min_confidence (min_confidence in global mode) and night_global_species injected into their config, and are flagged to fetch it when the rule changes (device 1.3.3 honours the list).
- AI Second Opinion: Ollama vision requests send think:false (CHIRP_OLLAMA_THINK=1 restores reasoning; falls back for an Ollama without the option); POST /recordings/ai-warm loads the Ollama model when a recording page opens (/api/ps, then an empty /api/generate with keep_alive); spectrogram sent as JPEG (326 KB PNG → 92 KB hosted, 57 KB at 1024 px for Ollama; the PNG re-encode had made it larger); Anthropic system prompt cached (cache_control).
- Email: services/email_theme.py, a light layout with the dark header band, prefers-color-scheme dark styles for Apple Mail, logo and bird photos attached inline (cid:), so they show without remote images or a signed-in photo URL. Daily digest (build_daily_digest): species cards with photo, detections, best score, first heard and a bar; new-to-life-list banner; busiest hour; counts at the display threshold. All other emails use the same theme.
- Optional iOS re-sign service (chirp-server-instances, compose profile ios-resign): anisette-v3-server, AltServer-Linux NG and netmuxd; re-signs App.ipa on each iPhone seen on the network every RESIGN_EVERY_DAYS (5), with a page on port 8099 for two-factor codes and status. POST /api/v1/ios-resign/event (stack device key) emails the admin when a code is needed or a re-sign fails. See ios-resign/README.md. The Mac and the server renew the same app: build-ios.sh builds under <bundle id>.<team id> (the ID AltServer gives a free-account app; SHARED_SIGNING=0 for the plain ID) and can copy the IPA to the server (RESIGN_HOST); the service sets the IPA's ID back to the plain one before AltServer adds the team ID. The page is published at https://iosresign.ourchirp.com through a Cloudflare Tunnel (resign-tunnel container) behind Cloudflare Access; ios-resign/cloudflare_setup.py creates the tunnel, DNS record and Access app.
- Clean up deleted recordings uses the batched delete.

## 1.3.3 (chirp-device) — 2026-10-08 — ENHANCEMENT — Night callers can use the global threshold

- detection.birdnet.night_global_species (set by the server's Night-Caller Thresholds, "Per species"): those night callers need min_confidence like other species, on CPU and Coral. In "Global" mode the server sends night_species_min_confidence equal to min_confidence.

## 0.5.10.l — 2026-10-06 — ENHANCEMENT — Spectrogram cache, storage and log optimizations

- Display-threshold changes pre-render spectrograms for the newest 500 recordings (CHIRP_SPECTROGRAM_PREWARM) instead of every recording; each change wrote two files per recording (the Natick server had 469k spectrogram files for 24k recordings). The regen existence check used the old "_thumb" name and no palette suffix, so thumbnails were redrawn even when cached.
- Storage status and Purge orphans gain a "spectrograms" target (file_cleanup.scan_spectrogram_cache): files whose recording is gone, and for recordings with audio, variants for other thresholds, palettes or pre-"_thumb2" thumbnails. Archived recordings keep everything; enhanced, bat and rumble-removed images are untouched.
- GET /recordings/{id}/spectrogram: cached file name includes the palette (with a non-default palette every request regenerated the image), and the archived fallback probes likely names instead of globbing the folder. Shared spectrogram_filename() in audio_processor.
- StorageManager archive, prune-by-age and prune-by-size, and Live Detect cleanup commit in batches of 20 with files removed after each commit (file_cleanup.delete_recordings); pruning also removes every spectrogram variant and the compressed twin (it only removed "{id}_spectrogram.png", a name nothing writes). Orphan scans use os.scandir instead of rglob + resolve.
- Library loggers (matplotlib, httpcore, Bird Buddy, asyncio and others) set to WARNING; the root logger stays at DEBUG for Chirp's own logs.
- Tests: shared fixture moved to tests/conftest.py; tests/test_storage_optimizations.py; both test files now in chirp-server-instances too.

## 0.5.10.k — 2026-10-05 — ENHANCEMENT — Recordings that show nothing are hidden

- GET /recordings hides finished device recordings with no detection at the display threshold (the "Unknown" cards), so the Recordings list and Dashboard skip them. Most were server-kept owls at 0.20–0.35, which auto-purge spares. Manual uploads, bats, recordings still processing and labeled ones stay; a species or confidence filter turns the rule off.
- no_detections now means "shows nothing at the display threshold" (true) or "shows at least one" (false); the filter chip is "Unknown only".

## 0.5.10.j — 2026-10-04 — CRITICAL — Deletes and uploads no longer fail during auto-purge

- Recording deletes (auto-purge sweep, Purge empty recordings) run in batches of 20 with a commit each, and files are removed after the commit. The first 0.5.10.i sweep deleted 138 recordings in one transaction while globbing a 469k-file spectrograms folder per recording, holding SQLite's write lock for minutes: uploads, heartbeats and deletes failed with "database is locked" (the app showed "Load failed").
- Single and bulk delete commit first and clear files on a background thread; upload-time purges remove files after their commit; re-analysis Undo scans for spectrograms before writing. Spectrogram variants for any number of recordings come from one folder scan (app/services/file_cleanup.py). SQLite busy_timeout 15 s (was 5 s).

## 0.5.10.i — 2026-10-04 — BUGFIX — Auto-purge removes every "Unknown" recording

- Auto-purge judges a recording by what it shows (detections at the display threshold) instead of the server's detection count, so night-floor Common Nighthawk and owl scores under the threshold no longer keep it; only an owl the server kept under its owl rules (0.20 plus a hoot) is spared. A sweep every 15 minutes applies it to stored device recordings (not manual uploads, labeled/noted ones or iNaturalist submissions).

## 0.5.10.h — 2026-10-04 — ENHANCEMENT — iPhone date pickers, resume handling, compressed-audio note

- Date and time inputs shrink to their container and read left-aligned (iOS gave them a native minimum width that overflowed the Edit window). The iOS app uses @capacitor/app for foreground/background events (visibilitychange as fallback), reconnecting the live socket and refreshing the Dashboard on return.
- BirdNET Analysis notes when a recording is stored compressed (Opus, MP3...), so re-analysis scores read as approximate.

## 0.5.10.g — 2026-10-03 — BUGFIX — Night noise no longer keeps empty recordings

- A night caller keeps its recording out of the empty-recording purge (auto and manual) only when the server pass kept it, the device scored it 0.25+, or the server pass also scored it 0.10+ (near miss). Device-only owls at 0.10 had kept every night-time noise recording, since noise scores as several owls at 0.10-0.17 at once.

## 1.3.2 (chirp-device) — 2026-10-03 — BUGFIX — Coral scores like CPU; tool to check a missed call

- Coral backend: sensitivity now maps the way birdnetlib's does (1.5 = slope 0.5, lifting faint calls; Coral used 1.5 as the slope, pushing a logit of -2 from 0.27 to 0.05), and it applies the night-caller floor and the location filter like the CPU backend.
- tools/check-file.py runs a clip (e.g. a HaikuBox download) through the device's gate, backend and location filter and says where a call is lost; the service saves its server-applied settings to state/effective_config.json for it. tools/night-check.sh warns on devices older than 1.3.1 and shows whether the location list loaded.

## 0.5.10.f — 2026-10-02 — BUGFIX — Ollama thinking models answer

- Ollama requests set num_ctx 16384 (CHIRP_OLLAMA_NUM_CTX) and, when a thinking model returns only reasoning, retry once with think: false; AI Second Opinion on Gemma 4 had failed with "consumed by thinking". The error that remains names the model and the setting.

## 0.5.10.e — 2026-10-02 — BUGFIX — AI Second Opinion no longer times out

- AI Second Opinion runs in the background and the page waits for it (with elapsed time, and the error shown if the provider fails); it had been a single request that the browser, iOS app or proxy dropped after about a minute, leaving nothing on screen. Image requests get 120 s on hosted providers (was 30 s) and 420 s on Ollama (was 180 s).

## 0.5.10.d — 2026-10-02 — BUGFIX — Cleaner AI Second Opinion

- Species headings show the name and likelihood once (a repeated "Blue Jay (likelihood Blue Jay (likelihood 85%)" is fixed, saved notes included); multi-species notes drop the opening summary that Overall repeated, and Overall is one or two sentences.
- The "Measured check" line is now an "Audio check for <species>" paragraph in plain sentences (faint call, no sound above the background, rumble-range energy, device-only detection, verdict lowered), saved notes included.

## 0.5.10.c — 2026-10-01 — ENHANCEMENT — Logo bars raised

- The logo's three bars moved up 3 units, between the beak tip and its center line, in every theme, favicon, PWA and iOS icons, the launch screen and email header.

## 1.3.1 (chirp-device) — 2026-10-01 — BUGFIX — Owls kept by the location filter

- The CPU backend applies the location filter itself, with the server's rule: species expected this week (3% or more) plus night callers expected in any week (owls 0.15%, others 0.5%). birdnetlib's filter dropped Barred Owl (1.6% in eastern Massachusetts in autumn) even when it scored 95–100%.

## 0.5.10.b — 2026-10-01 — BUGFIX — Editable recording time; downloads open a save dialog; AI Second Opinion hears chipmunks

- Recording date and time can be edited (Edit on the recording page). Uploads read it from the file name (HaikuBox, AudioMoth, Song Meter, Chirp), editable per file before upload; otherwise now.
- Backups, Life List exports, recording audio, logs and diagnostics open the iOS share sheet in the app (which couldn't download before) and Save As in Chrome and Edge; audio downloads keep their stored format (FLAC) and name.
- AI Second Opinion gives each species a likelihood and tells repeated chips several kHz tall (Eastern Chipmunk, chip notes) from narrow insect pulses, which it had called crickets.

## 0.5.10.a — 2026-09-30 — FEATURE — Re-analysis history and Undo, owl tuning, faster analysis and statistics

- Re-analysis history with Undo on each recording; Re-analyze no longer uses AI-Enhanced audio unless chosen, which then keeps the better of both scores; SSH terminal and mic levels connect again; cards and Empty Recordings count shown detections; AI Second Opinion checks recordings with none.
- Owls tuned on 49 labeled clips (wrong owls 80 to 8, owl-free false alarms 7 to 1); night-caller near misses with per-species thresholds; BirdNET about 2x faster, Statistics and Life List 13–23x, first load a third the size.

## 0.5.9.h — 2026-09-30 — ENHANCEMENT — Re-analysis change log; FLAC by default

- Re-analysis logs each species it removes and why (location filter, score now vs threshold, no score), plus any kept below the display threshold; see Logs.
- New installs compress recordings to FLAC (lossless), so re-analysis reads the same audio as the upload pass.

## 0.5.9.g — 2026-09-30 — BUGFIX — No zoom when typing on iPhone

- iOS app and Safari no longer zoom in when a text field is focused (viewport maximum-scale 1); the app shell had no way to zoom back out.
- Keyboard shortcut hints (⌘↵ to post) hidden on touch screens.

## 0.5.9.f — 2026-09-30 — BUGFIX — Re-analysis keeps detections found on the original audio

- Re-analysis of compressed (Opus) or AI-Enhanced audio keeps earlier server detections, at their earlier score, when the new pass scores them within 0.15; scores shifted by compression had been dropping them below the threshold or the 0.15 display floor.
- Re-analysis applies server_reanalyze_delete_device like uploads, honors the min_conf parameter, and uses the 2.5 s overlap default.

## 0.5.9.e — 2026-09-30 — ENHANCEMENT — iOS app polish

- iOS app: launch screen hides as soon as Chirp renders; status bar follows light and dark themes; offline page with retry; service worker enabled (app-bound domains) for faster launches.
- iOS app: runs on iOS 27 (UIScene lifecycle; built with Xcode 27 it closed at launch); reloads after a server update; bottom-bar haptics; install steps hidden in Settings and Tutorial.

## 0.5.9.d — 2026-09-30 — BUGFIX — Owls found in noisy night recordings

- Location filter no longer drops owls and other night callers (eBird rarely logs them); their best week of the year decides.
- Owls are scored on a 200–2000 Hz copy and need a matching hoot, so insect choruses no longer hide owls or pass as Eastern Screech-Owl.

## 0.5.9.c — 2026-09-29 — BUGFIX — iOS app asks for microphone and notifications

- iOS build adds NSMicrophoneUsageDescription (the mic was denied without a prompt); the app tags its user agent ChirpApp/1.
- One-time setup card in the iOS app requests notifications and the microphone; launch no longer prompts silently; Live Detect points to Settings → Chirp.

## 0.5.9.b — 2026-09-29 — BUGFIX — iOS app spacing at top and bottom

- iOS app web view runs edge to edge (contentInset never), so safe-area spacing applies once; Liquid Glass top clearance limited to Safari home-screen apps (navigator.standalone).

## 0.5.9.a — 2026-09-29 — FEATURE — Refined Songbird logo and motion

- Logo: closed lifted beak, one-line body, warm bars rising with the beak, size-adaptive line weight; all 17 themes, favicon, PWA, iOS and email icons.
- Motion: Sing on the Dashboard, Draw-on at login and loading, Live meter while Live Detect listens; still elsewhere and under Reduce Motion.

## 0.5.8.e — 2026-09-29 — ENHANCEMENT — iOS app loads ourchirp.com; iPhone layout fixes

- iOS app's server URL is now https://ourchirp.com (www allowed); example addresses in Settings updated to match.
- Page no longer drags or bounces behind the app shell (web and iOS app); home-screen top bar clears iOS 26's Liquid Glass blur band.

## 0.5.8.d — 2026-09-29 — ENHANCEMENT — Icons refresh after updates, iOS re-add prompt and build

- Icon URLs carry ?v=VERSION, the manifest gets a fixed id, icons are sent no-cache; old iOS installs get a one-time re-add card.
- iOS build: single 1024 px icon, new launch screen, Bluetooth text set automatically, `--archive` for a signed archive.

## 0.5.8.c — 2026-09-29 — ENHANCEMENT — New Songbird logo across every theme

- New logo: outline songbird with an open beak and meter bars; sings on the Dashboard, still elsewhere, respects Reduce Motion.
- All 17 themed logos, favicon, PWA, iOS and email icons redrawn from one shared SongbirdMark component.

## 0.5.8.b — 2026-09-28 — ENHANCEMENT — AI Second Opinion hears barks and high buzz; solid iOS top bar

- AI Second Opinion measures broadband bursts (dog barks) and steady high-frequency bands and reports them when the model omits them; Experimental tag removed.
- Top bar is sticky and theme-color follows the theme so iOS Liquid Glass tints it instead of blurring.

## 0.5.8.a — 2026-09-28 — FEATURE — AI Second Opinion measured checks, steadier Tailscale, Rumble Auto Off fix

- AI Second Opinion gets measured band, loudness, server agreement and regional frequency per species; unsupported Consistent verdicts become Uncertain; faster on local models.
- Server Tailscale recovers from an orphaned daemon and Auto uses it; Listen and mic levels fall back to the other address; Rumble Removed respects Auto Off.

## 1.3.0 (chirp-device) — 2026-09-28 — FEATURE — XVF3800 raw mics, night tuning, one-line logs

- Bundles 1.2.30–1.2.31 (XVF3800 routing, window stats, night-caller floor, 2 BirdNET threads) plus single-line journal logs and a clearer Listen error when the bat detector isn't capturing.

## 0.5.7.ah — 2026-09-25 — BUGFIX — Server confirms weak device owl detections

- A device night-caller detection under 0.10 now needs the server pass to confirm it; otherwise it's dropped and the recording can be auto-purged.

## 0.5.7.ag — 2026-09-25 — FEATURE — Night callers kept through re-analysis and auto-purge, connect to devices over Tailscale

- Owls, nightjars, rails and woodcock need 0.10 in the server and device BirdNET passes and survive re-analysis and auto-purge; device gate default is now -90 dB.
- Devices page offers Coral only when a compiled model is on the device; night-report.py matches whole species names and drops the fixed Haikubox confidence.
- Server Connects Via on each device (Auto, LAN IP, Tailscale): SSH, logs, Listen and mic levels use the Tailscale IP when the server is on the tailnet.

## 1.2.31 (chirp-device) — 2026-09-25 — BUGFIX — steadier overnight CPU detection, night-check fixes

- night-check.sh finds its install dir (~/chirp-device), parses "yesterday 19:00" for journalctl, lists mics, and flags a volatile journal; install.sh makes the journal persistent.
- -90 dB gate, 0.10 floor for night callers, 2 BirdNET threads; a backlog cuts overlap to 1 s instead of dropping windows; CPU is the default backend.

## 0.5.7.af — 2026-09-25 — FEATURE — Coral nudge, XVF3800 raw-mic switch, Enhanced cache cleanup, night report

- Devices page flags an unused or failed Coral with a one-click switch, and adds a ReSpeaker XVF3800 Raw/Processed output toggle.
- Deleting or archiving a recording removes its Enhanced caches; Storage cleans up orphaned and old-version ones. New `scripts/night-report.py` compares overnight Chirp and Haikubox detections.

## 1.2.30 (chirp-device) — 2026-09-25 — FEATURE — XVF3800 raw capsules, effective backend, gate stats

- XVF3800 routes raw capsules instead of the voice-processed beam (`respeaker.xvf3800_output`, default raw, hot-applied); heartbeat reports the backend actually running.
- 10-minute "Window stats" log line (levels vs gate, drops) and `tools/night-check.sh` for overnight checks.

## 0.5.7.ae — 2026-09-25 — BUGFIX — Night owls reach BirdNET again, better AI Second Opinion and Enhance

- Server-pushed device defaults (-55 dB gate, 0 dB gain) blocked distant owls; now -85 dB / +6 dB, auto-upgraded on heartbeat, and settings sync keeps per-device tuning.
- AI Second Opinion: mel-scaled labeled image, measured species bands, 60 s crop on long recordings. Enhanced/AI Enhance notch steady insect tones; owls and doves get a 150 Hz rumble cutoff.

## 1.2.29 (chirp-device) — 2026-09-25 — BUGFIX — owl-friendly energy gate

- Energy gate checks the loudest 0.5 s of each window (not the last), 150 Hz low cut, hot-applied; BirdNET sensitivity on CPU and Coral; dropped windows logged.

## 0.5.7.ad — 2026-09-24 — BUGFIX — AI Second Opinion now reports insect chirps it previously missed

- A cricket-like chirp repeating about once a second at ~5 kHz was visible on the spectrogram but reported as "no non-avian sounds." The audio is now measured for steady repeating tones, the result is given to the model, and it's added to Also visible if the model leaves it out. Detection boxes in the image sent to the model are outlines only.

## 0.5.7.ac — 2026-09-22 — FEATURE — AI-Enhanced re-analysis, recording SNR, split-band AI Enhance

- Re-analyze can now run BirdNET on AI-Enhanced audio. Enhancement was previously playback-only and never affected detections.
- Each recording gets an SNR estimate. Noisy recordings show a notice and default the AI-Enhanced re-analysis option on.
- AI Enhance now keeps calls above 7 kHz instead of cutting them off, and skips that when the high band is only noise. Compression settings note that Opus loses high-frequency detail used by re-analysis.

## 0.5.7.ab — 2026-09-22 — BUGFIX — removed the misleading confidence badge on Haikubox detections

- Haikubox's API doesn't return a real confidence score, so every detection showed a hardcoded 90%. Confirmed no way to get it directly or from Haikubox audio (the API has neither). Removed the badge.

## 0.5.7.aa — 2026-09-22 — BUGFIX — AI Second Opinion no longer shows empty, duplicated section headers

- The cleanup that strips a truncated trailing section only checked the last one, missing a case where empty headers stack up before a section that does have content. Now checks every section and drops the empty ones, wherever they fall.

## 0.5.7.z — 2026-09-21 — BUGFIX — bat and species photos now load on recording detail, live detect, and uploaded avatars

- A locally-stored photo needs a token to load, since it's served through this project's multi-tenant routing — several images were missing that token and always failed silently. Fixed on the recording detail hero photo, the species list, Live Detect's "Heard" photo, and uploaded user avatars.

## 0.5.7.y — 2026-09-21 — BUGFIX — Headscale Basic Auth confirmed genuinely working end-to-end (live config, real auth screen); fixed the toggle's own broken visual state

- Reported directly with a real live-config check: Basic Auth actually works correctly now — Caddy's admin API confirmed the authentication/http_basic handler is genuinely applied, scoped to just the setup pages, with real device registration unaffected. The earlier "no auth screen" report was resolved by the grpc_allow_insecure fix in the previous version — a coincidence of timing, not a shared root cause, since Basic Auth goes through Caddy's own admin API entirely separately from headscale's CLI.
- Fixed the Enabled toggle rendering with the circle stuck on the left despite the gold "on" background — a hand-rolled button+span construction that didn't match the rest of the app's own already-working toggle pattern (a checkbox with the existing .toggle CSS class, used correctly elsewhere in this same file). Replaced with that same established pattern.

## 0.5.7.x — 2026-09-21 — BUGFIX — the Headscale node list's "context deadline exceeded" traced to grpc_allow_insecure, not the socket or the wrapper

- Reported directly, diagnosed with real command output at every step: the unix socket file existed with correct permissions, startup logged nothing wrong, yet every `headscale nodes list` command still hung for exactly 5 seconds. Root cause: grpc_allow_insecure was reverted to false in an earlier version reasoning it was unused (no longer taking the gRPC-gateway REST approach) — missed that the CLI itself talks to the server over that same gRPC transport, even for local unix-socket commands, and with insecure mode off and no certificate configured anywhere, the connection hangs waiting for a TLS handshake that can never complete. Set back to true — safe here specifically because this gRPC listener is loopback-only and never published to the host, confirmed via `docker port`.

## 0.5.7.w — 2026-09-21 — BUGFIX — the Headscale node list's "Request failed (HTTP 500)" traced to a real gap in its own "never raises" promise

- Reported directly with the real error: the connection-reset fix from the previous version worked (the wrapper is reachable now), but the per-node processing loop had zero error handling despite the function's own docstring promising it would never raise — any node whose real JSON shape differed even slightly from what could be tested without a live instance would crash the whole endpoint. Fixed with real defensive handling at every level (a malformed node entry is now skipped and logged, not fatal) and verified against 9 separate adversarial malformed-data cases, not just the one that was reported.

## 0.5.7.v — 2026-09-21 — FEATURE — AI Second Opinion no longer truncates on long recordings (real fix + continuation-call fallback), Rumble Removed gets a third "Enabled (off)" mode, Headscale Basic Auth editable from Global Admin, headscale-multi-container docs gap filled

- Reported directly with a real example (a 296s, 4-species recording, still cutting off mid-sentence even after the token floor was already raised once): Ollama's num_predict is now set to -1 (its own documented "infinite generation" value) instead of any fixed cap, since a fixed cap just picks a recording length that will eventually fail again. As defense-in-depth for whatever the model's own context window still can't fit, a genuinely truncated-looking response now triggers up to 2 automatic continuation calls in the same conversation, concatenated — implementing the exact fallback suggested.
- Rumble Removed's setting gains a third mode, "Enabled (off)" — the toggle is shown on every recording (same as "Enabled (on)") but starts off by default, for admins who want people to be able to turn it on themselves without it being applied automatically. Replaces the old hidden "Always on" mode, which didn't cover this case at all.
- Global Admin's Network tab can now password-protect Headscale's own /apple/windows/linux setup pages directly — a bcrypt hash is computed server-side and pushed live to Caddy's admin API (no restart), persisted across restarts via Caddy's own --resume flag. Also found and fixed why the node-list wrapper itself was hitting "Connection reset by peer": it bound to 127.0.0.1 inside the container, the same Docker-port-forwarding mistake already fixed once this session for headscale's own gRPC listener — fixed, plus a startup readiness check added so this class of failure surfaces clearly in logs instead of silently.
- Filled in a real documentation gap: chirp-server's own separate, opt-in Headscale + DERP relay setup (docker-compose.headscale.yml) wasn't documented anywhere — tech docs, the top-level remote-access guide, and chirp-server's own README now cover it, including the real differences from chirp-server-instances' bundled setup (no auto-bootstrap, no bundled TLS, but its own self-hosted DERP relay).

## 0.5.7.u — 2026-09-21 — BUGFIX — the Headscale node list actually works now — real "illegal request line" error traced to a wrong assumption about its gRPC API, plus optional Basic Auth for Headscale's public helper pages

- Reported directly with the real error: "illegal request line" turned out to mean Headscale's gRPC port only speaks raw gRPC, never a REST/JSON gateway — confirmed against Headscale's own docs, which describe that port as being for CLI remote control specifically. Replaced the whole approach with a small HTTP wrapper (running inside the headscale container) around headscale's own CLI instead of chasing a Python gRPC client — verified end-to-end with a real running instance of the wrapper server and the real client module talking to each other, including the documented update-nag-banner bug that can corrupt the CLI's own JSON output.
- Also answered directly: Headscale's own helper pages (/apple, /windows, /linux — setup instructions, no login) can be gated with Caddy's basic_auth, scoped to just those specific paths (not the whole domain, which would break real client registration) — added as a ready-to-enable, commented-out block in the bundled Caddyfile, syntax verified against a real Caddy binary.

## 0.5.7.t — 2026-09-20 — FEATURE — Headscale node list in Global Admin (instances), chirp-multi fully removed, container architecture documented, Tutorial/tech docs updated for AI Enhance/AI Second Opinion/Rumble Removed

- Global Admin's Network tab now shows every device connected to the bundled Headscale server — online status, IP, last seen — via a new loopback-only Headscale admin API (auto-provisioned key, zero manual setup). Needs a live smoke-test against a real instance. chirp-multi (the deprecated earlier multi-tenant attempt) is fully removed — the directory, its real upload protocol in chirp-device's uploader.py, and every reference across docs — including a genuinely separate pre-existing test bug found and fixed along the way.
- Documented the container architecture (Headscale/Caddy/cloudflare-ddns for instances, the launcher for chirp-server) in tech docs, both READMEs, and ARCHITECTURE.md. Tutorial now explains Rumble Removed, AI Enhance, and AI Second Opinion; tech docs and the top-level README now connect "Call Re-analysis" to the AI Second Opinion button users actually see, and document the audio-cleanup toggles that weren't in the README before.

## 0.5.7.s — 2026-09-20 — BUGFIX — AI Second Opinion could end in a dangling, empty section header on Ollama — real token-budget fix plus a defensive display cleanup

- Reported directly with a screenshot: a response ending in a bare "**Other species detected:**Also visible:" with nothing after either. Root cause is documented in ai_providers.py's own comments — Ollama's thinking-capable local models spend part of their token budget on hidden reasoning before the visible answer, and the multi-species prompt has grown substantially (a named per-species checklist, a self-check instruction, two extra sections) since the 2048 floor was set. Raised to 3072. Also added a defensive cleanup that strips a trailing section whose heading has essentially no content after it, so any future truncation shows a clean, complete-looking response instead of a broken dangling header — verified against the exact real truncation pattern reported, and confirmed a genuinely complete section is left untouched.

## 0.5.7.r — 2026-09-19 — BUGFIX — found the actual root cause of AI Second Opinion discussing species that were never shown: no confidence filter at all

- Reported directly, more than once, with the correct hypothesis attached: AI Second Opinion's detection query pulled every Detection row for a recording with zero confidence filtering, while the spectrogram image, the species-count badge, and the detections list all filter by min_confidence_display (the same threshold recordings.py's own detail endpoint uses). A detection sitting below that threshold is real data the user never actually saw as a flagged detection — but the prompt was treating it exactly like one of BirdNET's own flagged species, in the same paragraph, with no distinction. Filtered by the same threshold now, so what AI discusses as "flagged" matches what was actually shown.

## 0.5.7.q — 2026-09-19 — BUGFIX — found and fixed the Settings gap above Diagnostics, open since early this session

- Every other Settings tab's anchor is its own GroupHeader doing double duty as both the tab-switcher anchor and the visible heading (one element, pt-2). Diagnostics used a separate, invisible pt-4 div as its anchor, sitting before its own custom heading button which had no top padding of its own — an extra 16px on top of what every other tab gets, from an element that isn't part of the heading at all. Anchor moved directly onto the button, padding matched to every other tab's pt-2, extra div removed.

## 0.5.7.p — 2026-09-19 — BUGFIX — restored the changelog body text stripped from every 0.5.6/0.5.7 entry last round

- Condensing the changelog last round dropped every entry's body down to nothing — reported directly: expanding an entry revealed a genuinely empty card, not a shorter one. Restored substantive detail for all 46 affected entries.

## 0.5.7.o — 2026-09-19 — BUGFIX — Changelog page was hiding entries from a fresh minor version's root release, and AI Second Opinion's species boundary made more concrete

- A minor version's root release (e.g. "0.5.7", the AI Enhance debut — no letter suffix, unlike every patch after it) was being grouped by the same MAJOR.MINOR rule meant for chirp-device's numbering scheme, landing it in a stray "0.5" group separate from its own 0.5.7.a–0.5.7.n siblings — looked like the card was missing an entry, since the count didn't match what was shown. Fixed to group correctly with its siblings.
- AI Second Opinion's per-species boundary (added last round) reportedly still blended a non-flagged species into the main verdict section — strengthened by naming the exact species list directly in the instruction and adding an explicit self-check before writing, rather than only referencing the list abstractly.

## 0.5.7.n — 2026-09-18 — FEATURE — same as chirp-server: mobile player layout fixed, AI Second Opinion species distinction, Dashboard cache staleness gap closed

- The play controls row crammed the play button, timer, and up to four toggles onto one line, pushing the last one off-screen on a phone. Split into two rows — play + time, then toggles wrapped below. AI Second Opinion's "Also visible" pass now separately labels **Other species detected:** (a bird call BirdNET never flagged, with AI's own species guess) from **Also visible:** (non-bird sounds) — previously blended into one paragraph. Also closed a Dashboard cache gap: statistics_cache was only invalidated on settings changes, never on a new detection, so a species detected for the first time today could show as not-new for up to 45 seconds.

## 0.5.7.m — 2026-09-18 — BUGFIX — same as chirp-server: app/techdocs_content/ was never re-synced, so rebuilding never showed the new figures

- The in-app Tech Docs page doesn't read techdocs/ directly — the Dockerfile only COPYs app/, so techdocs/ sits outside the build context entirely, and scripts/sync-techdocs.py has to copy techdocs/docs/ into app/techdocs_content/ before every build. That sync was never run after the figure rebuild, so every package shipped the old figures baked into app/techdocs_content/assets/ regardless of version — no amount of rebuilding could have picked up the new ones until this ran.

## 0.5.7.l — 2026-09-18 — DOCS — same as chirp-server: all 10 tech-doc figures rebuilt from scratch

- Two figures (System Architecture, Detection Pipeline) were still the original white-background patent-style versions with "FIG. N" labels and reference numerals; several others had genuine overlapping-box and clipped-text bugs. Rebuilt all 10 with a reusable auto-sizing SVG generator: same information, consistent dark theme, all patent-litigation framing removed.

## 0.5.7.k — 2026-09-18 — DOCS — same as chirp-server: tech docs updated for this session's changes; fig2 and several stale numbers corrected

- Fig2's threshold and RMS window values were stale even before this session. Corrected those plus this session's own changes, removed an unverified discard-rate stat with no real data behind it, and added a previously-missing section documenting the three server-side audio processing options (Enhanced, Rumble Removed, AI Enhance).

## 0.5.7.j — 2026-09-18 — FEATURE — same as chirp-server: Rumble removed now has a manual cutoff slider, matching Live Detect's own rumble filter

- The cutoff was always the automatic species-aware value with no way to adjust it directly. Added a 0-2000Hz slider (same range as Live Detect's own rumble filter) that appears when Rumble removed is on, starting at Auto.

## 0.5.7.i — 2026-09-18 — TWEAK — same as chirp-server: detection sensitivity raised across both device and server pipelines

- Per a direct comparison against HaikuBox catching more activity at the same location: lowered birdnet_min_confidence, raised birdnet_sensitivity and birdnet_overlap server-side, and matched on the device's own local fallback config (energy threshold, confidence, and window overlap all raised to catch more real calls).

## 0.5.7.h — 2026-09-18 — BUGFIX — same as chirp-server: Rumble removed's label never changed with its actual state, and the spectrogram never reflected it either

- The full-recording "Rumble removed" button always displayed the same text regardless of its actual state — only the styling tracked it, not the label. Fixed. Also added the missing rumble-removed spectrogram endpoint — toggling the audio never updated the image, the same gap Enhanced and AI Enhanced already had fixed for their own toggles.

## 0.5.7.g — 2026-09-18 — FEATURE — same as chirp-server: rumble removal now available per-clip, and AI Second Opinion more reliably flags a constant background chorus

- Rumble removal never existed at the clip level — only the full-recording player had it. Added a matching per-clip endpoint and button. Also strengthened AI Second Opinion's "Also visible" instruction to explicitly cover a continuous background chorus (cicadas, crickets), not just a one-off noise event.

## 0.5.7.f — 2026-09-18 — FEATURE — same as chirp-server: AI Enhance now strips rumble too, using the same simple high-pass as Rumble Removed

- AI Enhance had no rumble-specific filtering of its own — it relied entirely on the neural model. Added the same species-aware high-pass filter the classical Rumble Removed toggle uses, as a pre-processing step before the model runs.

## 1.2.28 (chirp-device) — 2026-09-18 — TWEAK — detection sensitivity raised (energy threshold, confidence, window overlap)

## 1.2.27 (chirp-device) — 2026-09-18 — BUGFIX — input_gain_db restored to 6.0 — the 0.0 revert was silently dropping real bird calls

## 1.2.26 (chirp-device) — 2026-09-18 — TWEAK — server_sync.targets: swapped, chirp-server-instances is now primary

## 1.2.25 (chirp-device) — 2026-09-18 — BUGFIX — "Applied server config" logged before the callback ran, and multi-target logs didn't say which server

## 0.5.7.e — 2026-09-17 — BUGFIX — same as chirp-server: rumble removal fixes weren't taking effect, three cache paths never matched what got written

- enhance_audio() always appends "_enhanced.wav" to its cache filename, but three endpoints' own cache-existence checks didn't match that — two were silently recomputing on every request, and rumble-removed's output was colliding with rumble-removed-enhanced's old cache path. Corrected all three with a shared version constant.

## 0.5.7.d — 2026-09-17 — BUGFIX — Changelog page: several device entries were showing under the Server tab, and Device showed empty

- Several recent chirp-device entries were missing the internal tag the page needs to sort them correctly, so they were appearing under the Server tab instead and Device looked empty.

## 0.5.7.c — 2026-09-17 — FEATURE — same as chirp-server: AI Enhance now updates the spectrogram, shows a loading state, and torch/torchaudio install by default

- The AI-Enhanced spectrogram wasn't being generated at all — toggling AI Enhance changed the audio but the image stayed on the original. Added the missing endpoint plus a loading spinner while the neural pass runs. torch/torchaudio now install by default via the CPU wheel index.

## 0.5.7.b — 2026-09-17 — BUGFIX — same as chirp-server: Rumble removed still sounded noisy after the filter fix — root cause was the loudness boost afterward, not the filter

- Rumble Removed's own noise-reduction boost step was re-amplifying the noise it had just filtered out — since rumble often dominates a signal's peak, removing it then boosting made the remaining hiss roughly 4x louder. Fixed: rumble-only passes now skip the boost entirely, matching Enhanced's own already-correct behavior.

## 0.5.7.a — 2026-09-17 — FEATURE — same as chirp-server: Automatic backups now show real last-run status, plus a "Run Now" button

- Automatic backups previously had no visible status at all. Added real last-run/last-success timestamps and the last error (if any) to Settings, plus a "Run Now" button.

## 0.5.7 — 2026-09-17 — FEATURE — same as chirp-server: AI Enhance (Experimental): neural-network denoising, separate from Enhanced/Rumble removed

- First iteration of AI Enhance (Experimental) — neural-network denoising using biodenoising (Demucs-based, trained on animal vocalizations), a full alternative to the classical Enhanced/Rumble Removed pipeline rather than a variant of it. Known limitation, documented in the UI: the model runs at 16kHz internally, so content above 8kHz in the result is lost.

## 0.5.6.ae — 2026-09-17 — BUGFIX — same as chirp-server: Rumble removed was actually a bandpass, not a high-pass, and rang audibly at the band edges

- Fixed several issues found from real reports on the mic testing and bat features shipped just before this — AudioMoth's own mic test, the detection bar on bat recordings, and a horizontal-scroll overflow on mobile.

## 1.2.24 (chirp-device) — 2026-09-17 — TWEAK — input_gain_db reverted from 6.0 back to 0.0

## 1.2.23 (chirp-device) — 2026-09-17 — BUGFIX — A config version could be marked "applied" during startup without ever actually reaching anything live

## 0.5.6.ad — 2026-09-16 — TWEAK — same as chirp-server: Rumble removed now defaults to on for bird recordings

- Rumble Removed was opt-in, requiring a toggle on every recording — made it default to on for bird recordings, per direct feedback. Still a real toggle, not forced.

## 0.5.6.ac — 2026-09-16 — FEATURE — same as chirp-server: AI Second Opinion now notes other visible sounds; per-mic on/off toggle added

- AI Second Opinion can now flag other sounds visible in a spectrogram beyond the flagged detection — an early version of what later became a substantially strengthened "Also visible" instruction. Also added a per-mic on/off toggle for detection.

## 0.5.6.ab — 2026-09-16 — FEATURE — same as chirp-server: Rumble removed is now its own separate toggle from Enhanced

- "Rumble removed" is now its own separate toggle from Enhanced rather than bundled into it — independently combinable.

## 0.5.6.aa — 2026-09-16 — FEATURE — same as chirp-server: recordings now get a species-aware high-pass filter when Enhanced

- Recordings now get a species-aware high-pass filter applied when Enhanced is on — the foundational version of what later became the standalone Rumble Removed toggle.

## 0.5.6.z — 2026-09-16 — BUGFIX — same as chirp-server: several fixes from real reports on the mic testing/bat features just shipped

- Fixed several issues found from real reports on the mic testing and bat features just shipped — AudioMoth's mic test, the detection bar on bat recordings, and horizontal scroll on mobile.

## 0.5.6.y — 2026-09-16 — FEATURE — same as chirp-server: mic testing added to Devices page and Diagnostics; several fixes

- Added mic testing to the Devices page and as its own Diagnostics item, fixed the spectrogram not updating after a reanalyze, and fixed bat clip playback.

## 0.5.6.x — 2026-09-16 — BUGFIX — Safari upload failure persisted after the XHR fix

- The Safari upload failure persisted even after switching the page's own upload code from XMLHttpRequest to fetch() — the service worker itself was also re-forwarding upload requests in a way that could drop the body specifically on Safari, a separate WebKit bug one layer further out.

## 0.5.6.w — 2026-09-16 — BUGFIX — recording and photo uploads silently failed on Safari

- Recording and photo uploads were silently failing in Safari — a real WebKit bug where Safari can send an empty upload body while everything otherwise looks normal. Worked fine in Chrome on iOS and Safari on macOS the whole time.

## 1.2.22 (chirp-device) — 2026-09-16 — TWEAK — input_gain_db default raised from 0.0 to 6.0

## 1.2.21 (chirp-device) — 2026-09-16 — BUGFIX — "Config pending" could resurface after being dismissed even when the device had actually applied it

## 1.2.20 (chirp-device) — 2026-09-16 — BUGFIX — Mic Frequency Response's AudioMoth lookup 404'd despite matching elsewhere

## 0.5.6.v — 2026-09-14 — DIAGNOSTIC — logs the real headers behind every 422 validation error

- Added a diagnostic log for every request validation failure (422), showing the real Content-Type/Content-Length the server actually received — helps pin down upload failures that don't reach application code at all.

## 0.5.6.u — 2026-09-14 — BUGFIX — bird photos never displayed once locally downloaded (instances-only)

- Fixed bird photos never displaying anywhere once locally downloaded — profile pages, Dashboard, Life List, Live Detect, Recordings List, Field Guide, and Statistics were all affected, an instances-only gap in the local-download path.

## 0.5.6.t — 2026-09-14 — BUGFIX — upload errors showed "[object Object]" instead of the real message

- Fixed upload errors showing the literal text "[object Object]" instead of the actual reason — Manual Recording Upload, bird photos, Live Detect, and Mic Frequency Response all now surface a real message.

## 0.5.6.s — 2026-09-14 — TWEAK — replaced confusing seasonal percentages with a plain bar chart

- Replaced confusing seasonal percentages with a plain bar chart, matching eBird's own weekly bar chart style — on bird profiles and in the Field Guide.

## 0.5.6.r — 2026-09-14 — TWEAK — bird profile summary auto-refresh cap raised from 25/day to 100

- Raised the bird profile summary auto-refresh daily cap from 25 to 100, so a real backlog of species clears in a day or two instead of spreading across a week.

## 0.5.6.q — 2026-09-14 — BUGFIX — Bat profile photo permanently stuck empty

- Fixed the Bat profile photo staying empty forever — one failed fetch (iNaturalist rate limiting) was marked "done" and never retried again.

## 0.5.6.p — 2026-09-14 — BUGFIX — Tech Docs images cached for a week, hiding updates after a redeploy

- Fixed Tech Docs images being cached for a full week, hiding updated figures for that long after any redeploy — the direct precursor to the same-shaped bug found again later this session.

## 0.5.6.o — 2026-09-14 — BUGFIX — several small fixes

- Several small fixes found while auditing related code.

## 0.5.6.n — 2026-09-14 — BUGFIX — silent failure backfilling a missing iNaturalist taxon ID

- Fixed a silent-failure gap when backfilling a missing iNaturalist taxon ID during a maps-only refresh — now logs whether it actually succeeded or genuinely found nothing.

## 0.5.6.m — 2026-09-14 — BUGFIX — eBird S&T range maps overwritten by other tabs; geomodel/BirdLife wrote to the wrong directory

- Fixed eBird S&T range maps getting silently overwritten by other tabs, and geomodel/BirdLife's own refresh buttons writing to the wrong folder — both instances-only bugs in the multi-tenant file layout.

## 0.5.6.l — 2026-09-14 — BUGFIX — Range Map tabs vanished entirely when nothing was cached yet

- Fixed the Range Map tabs disappearing entirely for iNat/BirdLife/S&T whenever nothing was cached yet — a leftover from the same collapsed-container bug already fixed for AAB/Macaulay.

## 0.5.6.k — 2026-09-14 — BUGFIX — Seasonal Range Map was 401ing on every source, instances-only

- Fixed the Seasonal Range Map showing nothing on every source — every image/legend request was 401ing because it couldn't carry the auth token this multi-tenant deployment needs to pick the right location's data.

## 0.5.6.j — 2026-09-14 — BUGFIX — Macaulay range-map fallback disabled; Changelog cleanup

- Disabled the dead Macaulay Library range-map fallback and cleaned up an ambiguous count on the Changelog tabs.

## 1.2.19 (chirp-device) — 2026-09-14 — TWEAK — Stage 1 bandpass lowered from 800 Hz to 250 Hz

## 1.2.18 (chirp-device) — 2026-09-14 — BUGFIX — Mic Frequency Response's AudioMoth stream now matches by its real device name

## 0.5.6.i — 2026-09-10 — BUGFIX — same fixes as chirp-server: S&T overlap, AAB/BirdLife log visibility

- Same fixes as chirp-server: eBird S&T disclaimer overlap on range map tabs, and AAB/BirdLife failures made visible in normal logs instead of being silently swallowed.

## 0.5.6.h — 2026-09-10 — BUGFIX — same fixes as chirp-server: Changelog title cards, bat photo, range map UI

- Same fixes as chirp-server: Changelog title cards, a bat-photo overwrite bug, and range map UI fixes.

## 0.5.6.g — 2026-09-10 — BUGFIX + FEATURE — bat photo and range map startup fixes; same Changelog tabs and spectrogram as chirp-server

- Bat photo and range map startup fixes for real locations, plus the same Changelog Server/Device tabs and Mic Frequency Response spectrogram as chirp-server.

## 0.5.6.f — 2026-09-10 — BUGFIX — same Changelog page grouping fix and version summaries as chirp-server

- Same Changelog page grouping fix and condensed version summaries as chirp-server.

## 0.5.6.e — 2026-09-10 — FEATURE — same "Dismiss pending config" option as chirp-server

- Same "Dismiss pending config" option as chirp-server, for a Devices page state that isn't actually pending.

## 0.5.6.d — 2026-09-10 — FEATURE — same overlapping Live Detect windows and Mic Frequency Response diagnostic as chirp-server

- Same overlapping Live Detect windows with a length slider, and new Mic Frequency Response diagnostic, as chirp-server.

## 0.5.6.c — 2026-09-10 — BUGFIX + FEATURE — same Live Detect capture-gap fix and sensitivity slider as chirp-server

- Same Live Detect capture-gap fix and new sensitivity slider as chirp-server.

## 0.5.6.b — 2026-09-10 — BUGFIX — Daily Journal, Weekly Journal, and Bird Profile AI summaries never ran for any real location

- Fixed the Daily Journal, Weekly Journal, and Bird Profile AI summaries never actually running for any real location — a scheduler bug found while auditing all the app's scheduled jobs, instances-only.

## 0.5.6.a — 2026-09-10 — CONFIG — version numbers reconciled with chirp-server

- chirp-server and chirp-server-instances version numbers reconciled — both projects now share the same version number going forward instead of drifting independently.

## 0.5.5.ax — 2026-09-10 — BUGFIX — same Devices page mobile overlap fix as chirp-server

- Identical fix as chirp-server's own equivalent entry — the action-badge row (now five items with the Tailscale badge added) wraps to its own line on narrow screens instead of overlapping the status text above it.

## 0.5.5.aw — 2026-09-10 — DOCS — same new Remote Access Tech Docs page

- Same new "Remote Access (Tailscale/Headscale)" Tech Docs page as chirp-server's own equivalent entry — this project's own bundled Headscale/Caddy/DDNS setup, plus every issue found and fixed getting it working live. Also corrected docs/REMOTE_DEVICES.md and docs/CLOUDFLARE_TUNNEL.md at the repo root, shared with chirp-server.

## 0.5.5.av — 2026-09-10 — FEATURE — automatic Dynamic DNS for a home IP that isn't static

- Reported directly: a dynamic (non-static) home IP means headscale.ourchirp.com's DNS A record would silently go stale the next time it changes, with no warning until someone notices Headscale stopped being reachable. New cloudflare-ddns service checks every 5 minutes and updates that record automatically, reusing the exact same Cloudflare API token Caddy already uses — no new secret needed, since keeping one DNS record current is already inside that token's existing Zone:DNS:Edit scope. PROXIED=false is hardcoded, not left as a default — the same reason a proxied record breaks Headscale's protocol applies here regardless of who or what updates the record.

## 0.5.5.au — 2026-09-10 — CONFIG — Cloudflare API token configured for Caddy's DNS-01 challenge

- CF_API_TOKEN set in .env, verified directly against Cloudflare's own token-verify endpoint (active, valid). Ready to deploy — the caddy service can now actually request a certificate for headscale.ourchirp.com once its DNS record is switched to "DNS only" and the router port-forward is in place.

## 0.5.5.at — 2026-09-10 — FEATURE — Caddy reverse proxy for Headscale, replacing Cloudflare Tunnel entirely

- Root cause confirmed against Headscale's own documentation: "Running headscale behind a cloudflare proxy or cloudflare tunnel is not supported and will not work" — Cloudflare strips the Upgrade header on the POST request Headscale's handshake depends on, tunnel or plain proxy alike, no config on this side can work around it.
- New "caddy" service, custom-built with the Cloudflare DNS plugin, terminates TLS for headscale.ourchirp.com and reverse-proxies to headscale internally over the compose network. Uses the DNS-01 certificate challenge (a Cloudflare API token, Zone:DNS:Edit scope only) rather than the usual HTTP-01, since port 80 on this host is already Unraid's own management UI — DNS-01 needs no inbound port at all for issuing or renewing the certificate.
- Exposed on host port 8443 (not 443, same reason) — forward your router's public port 443 to this host's port 8443, and set headscale.ourchirp.com's Cloudflare DNS record to "DNS only" (not proxied) — a proxied record routes traffic back through Cloudflare's edge and reintroduces the exact same failure, tunnel or not.

## 0.5.5.as — 2026-09-10 — FEATURE — register and join a location in one step, with an invite code

- Requested directly: the registration form can now optionally include an invite code, joining that location immediately (viewer role, no separate approval step — the same as the existing invite-code join flow already worked, just now reachable from a single form instead of register-then-login-then-join). Signs the person straight in with a usable session, same as a normal login would. That location's global admins are emailed a heads-up (not an approval request — this is already-done, informational), using that location's own SMTP config to send it. An invalid invite code is rejected before any account is created, so a typo doesn't leave an orphan login with nothing to do. Verified directly: account creation, membership, the synced per-instance user row, the issued session, and the invalid-code rejection path all confirmed with a real test — not just read through the code.

## 0.5.5.ar — 2026-09-10 — DEBUG — same Tailscale timeout-visibility fix as chirp-server

- Identical fix as chirp-server's own equivalent entry — tailscaled's own log is now surfaced when tailscale up times out (not just when the daemon crashes outright), so a stuck-but-alive daemon isn't a silent dead end anymore.

## 0.5.5.aq — 2026-09-10 — BUGFIX — same Tailscale kernel-TUN fallback as chirp-server

- Identical fix as chirp-server's own equivalent entry — automatically retries with userspace networking the moment a kernel TUN permission failure is detected, instead of looping on "enabled, not connected" forever.

## 0.5.5.ap — 2026-09-10 — DEBUG — same Tailscale daemon-visibility fix as chirp-server

- Identical fix as chirp-server's own equivalent entry — daemon process now tracked to avoid duplicate launches, and its log surfaced directly on connection failure instead of being discarded.

## 0.5.5.ao — 2026-09-10 — BUGFIX — same Tailscale permission fix as chirp-server

- Identical root cause and fix as chirp-server's own equivalent entry — PermissionError: [Errno 13] Permission denied: '/var/run/tailscale', because this container also drops to an unprivileged user before TailscaleManager runs. Daemon state/socket moved under /app/data; the now-unneeded /var/lib/tailscale volume mount removed from docker-compose.yml.

## 0.5.5.an — 2026-09-10 — FEATURE + BUGFIX — per-instance diagnostics in Global Admin; parity fixes ported from chirp-server; lint cleanup

- New: Global Admin's Instances tab can now run diagnostics (Full/Database/Mic) against any specific location, on demand — reuses the exact same diagnostics engine each location's own Settings page already runs against itself, just pointed at a chosen instance's own database instead of whichever one a request happens to be scoped to.
- Full parity audit against chirp-server, requested directly: found and fixed real gaps, not just the expected architectural differences —
  - Push-notification daily digests were completely missing here (email digest existed, push didn't: no model column, no function, never wired up). Ported.
  - The daily digest scheduler had the same "silently operates on the single unused legacy database, not any real instance" bug already found and fixed this session for Bird Buddy/Haikubox/iNaturalist sync — it's been broken for every real location the whole time. Fixed the same way: loops over every real instance now, for both email and push.
  - email_service.py was missing an iOS Mail dark-mode rendering fix and a shared yesterday-stats helper the two digest channels both need. Copied over in full (confirmed safe: that file never opens its own DB sessions, so nothing instance-specific could be lost).
  - diagnostics.py's mic-check error handling was an older, less diagnosable version (only kept the last error instead of every device string's own specific failure reason). Ported the better one.
  - Found, not fixed: login attempts aren't written to the Activity Log here the way they are in chirp-server (only page views/logout are) — genuinely tricky because login happens before an instance is selected in this fork's own multi-tenant flow, so there's no obvious instance database to log a failed attempt into before that's resolved. Flagged rather than rushed.
- Also ran pyflakes over the whole app/ tree: removed two confirmed-dead things (an unused time import in the live-detect cleanup loop, an unused sqlalchemy.text alias in diagnostics.py).

## 0.5.5.am — 2026-09-10 — CONFIG — bundled Headscale now reachable over WAN via Cloudflare Tunnel

- server_url in headscale/config.yaml, and the CHIRP_TAILSCALE_LOGIN_SERVER default in docker-compose.yml, both updated from the bare LAN IP to https://headscale.ourchirp.com — reachable from anywhere, not just the home network, the same way the main web UI already is. Only the initial coordination handshake goes through this URL; actual device-to-device traffic (recordings, SSH, the web UI once routed over Tailscale) stays direct peer-to-peer, or falls back to DERP relay — no other ports need forwarding.
- Note: if you already saved a login_server value via Global Admin's Network tab, that saved value takes precedence over this new default — update it there too (paste the new URL, Save & Connect) for chirp-server-instances' own connection to actually use it.

## 0.5.5.al — 2026-09-10 — BUGFIX — same DeviceOut fix as chirp-server

- Identical root cause and fix as chirp-server's own equivalent entry — DeviceOut never declared a tailscale_ip field, so it was silently stripped from every device API response despite being stored correctly in the database. Confirmed directly by querying "Natick Birds" instance's own database and finding ChirpPi's tailscale_ip already correctly set to 100.64.0.1 — the data pipeline (device → heartbeat → persistence) was never the problem, only this one response model.

## 0.5.5.ak — 2026-09-10 — BUGFIX — same Tailscale daemon fix as chirp-server

- Identical root cause and fix as chirp-server's own equivalent entry — tailscaled was never actually running inside this container either (no systemd to auto-start it), so Global Admin's Network tab could show "enabled" indefinitely without ever reaching "connected". TailscaleManager now starts the daemon itself before attempting to connect.

## 0.5.5.aj — 2026-09-10 — CONFIG — headscale/config.yaml's server_url set to the real LAN IP

- Was still the CHANGE_ME_TO_YOUR_LAN_IP placeholder — set to 192.168.1.224, matching what chirp-device's own login_server was already pointed at. This is likely why Tailscale showed "enabled, not connected": headscale reports server_url back to clients during its own handshake, so a placeholder there can let a connection start without ever fully completing.

## 0.5.5.ai — 2026-09-10 — BUGFIX — bundled Headscale restart-loop: "Cannot create user: user already exists"

- Confirmed from logs: headscale itself now starts and stays up cleanly (the DERPMap fix worked) — but entrypoint.sh's own user-existence pre-check (grep-matching headscale's users list table output) never actually matched the real output format, so it always fell through to calling `headscale users create` again, which correctly failed with "user already exists" — and under `set -e`, that killed the script, which killed the container, which docker then restarted, forever. Fixed by not pre-checking at all: always attempt user creation, and treat "already exists" in its own output as the expected, non-fatal outcome instead of an error.
- The preauth-key check used the identical risky pattern (grep-matching a raw secret against headscale's own list output, which likely doesn't even print full key values) — simplified before it could cause the same failure: an existing key in the shared file is now reused unconditionally rather than re-verified against headscale's list output first.
- Verified with a two-run test simulating a restart against a mocked headscale binary that reproduces the exact "already exists" behavior from the logs: confirms no restart loop and the same key persists across runs.

## 0.5.5.ah — 2026-09-10 — BUGFIX — bundled Headscale crashed on every startup: "initial DERPMap is empty"

- Root cause found from the log output: "Headscale ran into an error and had to shut down. error=\"initial DERPMap is empty, Headscale requires at least one entry\"" — config.yaml never had a derp: section at all, and headscale refuses to start without at least one DERP relay configured (used only as a NAT-traversal fallback when two devices can't connect directly — not a control-plane dependency). Added, pointing at Tailscale's own public DERP map, which is free to use and needs no Tailscale.com account; everything else about this setup stays fully self-hosted. The bootstrap script's earlier "creating user" / "context deadline exceeded" lines in the logs were a downstream symptom of this same crash, not a separate problem — headscale wasn't running yet when that step tried to reach it.
- Same caveat as before: no Docker available here to confirm the fix end-to-end, but this is a specific, well-understood headscale requirement with a standard fix, not a guess.

## 0.5.5.ag — 2026-09-10 — DEBUG — bundled Headscale still failing its healthcheck, root cause not yet known

- Reported: the image now builds, but chirp-headscale never passes its healthcheck (~106s of retries). entrypoint.sh's wait loop used to just wait out its full 30s and silently move on even if headscale crashed immediately or never came up — meaning a startup error from headscale itself could sit buried in the logs with no clear signal pointing at it. Now checks whether the headscale process is still alive on every iteration and exits loudly with a clear message the moment something's wrong, instead of hanging.
- This is a diagnostics improvement, not a confirmed fix — the cause (a bad config.yaml value for this headscale version, a volume permission issue, something else entirely) isn't known yet without seeing `docker compose logs headscale`'s own output.

## 0.5.5.af — 2026-09-10 — BUGFIX — bundled Headscale wouldn't even start

- Reported directly, from a deploy attempt: "exec: /bin/sh: stat /bin/sh: no such file or directory" — the official headscale/headscale image turns out to have no shell in it at all, so running entrypoint.sh directly against it (as shipped in 0.5.5.ad) could never have worked. Fixed with a small wrapper Dockerfile: extracts the headscale binary out of the official image (found by search at build time, not a hardcoded path, so this doesn't silently break again if a future headscale release reorganizes its own image) onto an Alpine base that has a shell to run the bootstrap script on. docker-compose.yml's headscale service now builds this instead of using the image directly; the entrypoint.sh bind-mount was also redundant once it's baked into the image, so that's removed too.
- Caveat: this environment has no Docker available to build and run the image end-to-end, so this is a code-level fix verified by reasoning and shell syntax checking, not a confirmed deploy the way most of this session's other changes were. Please report back whether `docker compose up` succeeds now.

## 0.5.5.ae — 2026-09-10 — CONFIG — bundled Headscale moved off port 8080

- Reported directly: 8080 collided with other services already running. Moved to 9877 — headscale/config.yaml's listen_addr and server_url, docker-compose.yml's port mapping and CHIRP_TAILSCALE_LOGIN_SERVER default, and the Global Admin Network tab's placeholder text all updated together.

## 0.5.5.ad — 2026-09-10 — FEATURE — self-hosted Headscale bundled in, zero-manual-key Tailscale setup

- Same Settings-toggle upgrade as chirp-server, but here configured from Global Admin's new Network tab (RegistrySettings-backed — one Tailscale identity per container, shared by every instance, so this can't live in any one instance's own Settings the way a per-instance value would).
- The bigger piece, asked for directly: a new "headscale" service in docker-compose.yml runs a real, open-source, self-hosted Tailscale control plane — no external Tailscale.com account needed at all. Its entrypoint script auto-creates a user and a long-lived reusable key on first boot (idempotent — a restart reuses the same key, never generates a new one), and this server picks that key up automatically within seconds of `docker compose up`, via a shared volume — zero manual steps for chirp-server-instances itself. To point chirp-server or a remote chirp-device at this same private tailnet too, one manual key copy is still needed (`docker compose exec headscale cat /shared/authkey`) — not a new key every time, just once. Verified: the bootstrap script's idempotency logic (create-if-missing, reuse-if-valid) tested against a mocked headscale CLI across two simulated restarts, confirming the same key persists rather than a fresh one being generated each time; the key-file fallback precedence (saved config > env var > bundled Headscale) tested in isolation too.
- Requires editing headscale/config.yaml's server_url once before first boot (defaults to a placeholder) — see that file's own comment.

## 0.5.5.ac — 2026-09-10 — BUGFIX + FEATURE — Bird Buddy/Haikubox/iNat sync now run per instance; server-side Tailscale added

- Reported directly: Bird Buddy sync worked on chirp-server but not on an instance imported from it. Root cause — the exact same bug already found and fixed for the Dashboard cache warmer, just never applied here: Bird Buddy sync, Haikubox sync, and iNaturalist token auto-refresh all ran as a single background loop with no per-instance context, so every poll silently operated on the unused legacy database, never any real instance's own settings. All three now loop over every real instance, matching the established pattern — verified with a two-instance test confirming each one now runs once per instance. Also fixed a related bug in Haikubox sync where a shared internal counter would have mixed counts across instances.
- Same server-side Tailscale/Headscale support as chirp-server (see that project's own changelog entry for the full story) — the server itself can now be reached over Tailscale, not per-instance, one identity per container shared by every location it hosts.

## 0.5.5.ab — 2026-09-10 — PERF — Dashboard cache warmer now also keeps yard_pulse warm, per instance

- Same fix as chirp-server: yard_pulse() (species streaks + 30-day diversity) has had its own 45-second cache for a while, same as the stats/summary calls next to it, but was never added to the background warmer that proactively refreshes those other two every 30 seconds for every real instance. Added, matching the existing per-instance pattern exactly — verified with a two-instance test confirming all three calls warm for every instance, not just one.

## 0.5.5.aa — 2026-09-10 — DOCS — clarified that importing a database doesn't bring recording files with it

- Reported directly: a bat recording imported from chirp-server showed "Spectrogram unavailable" with no working audio. Confirmed the cause — chirp-server and chirp-server-instances use separate storage volumes (see docker-compose.yml), and POST /instances/import only ever copies the SQLite database itself, since there's no way for a browser file upload to also carry along a whole recordings/spectrograms/clips directory tree. This isn't a bug in the import step itself, but it was a silent gap nobody was warned about. Both import forms (location picker, Global Admin) now say so plainly, so the next person who imports a database knows up front — the recordings/spectrograms/clips folders need to be copied over on the server separately for that data to work.

## 0.5.5.z — 2026-09-10 — BUGFIX — Global Admin and a local instance's Users page disagreed on who belonged to it

- Reported directly, with screenshots: Global Admin showed 1 member for an instance whose own local Users page listed 12. Root cause: POST /instances/import (importing an existing chirp-server database as a new location) only ever created a registry Membership for the person doing the import — every other carried-over local account was left with no Membership at all, invisible to Global Admin and unable to log in through this fork's own login, despite still showing up on the local Users page's own (separate, legacy) table.
- Fixed going forward — importing a database now backfills a Membership for every local account it carries over, reusing an existing global account by username or provisioning one from the local row's own credentials so nobody's password changes. Also fixed retroactively for instances imported before this existed, via a one-time startup backfill. Verified directly: an instance with 1 registry membership and 12 local users reconciles to 12 memberships, is idempotent on repeat runs, and doesn't duplicate anyone already present.

## 0.5.5.y — 2026-09-10 — BUGFIX — iNaturalist submission role check, and a silent failure on the Users list

- Submitting to iNaturalist could fail with "requires admin or submitter role" for users who did hold that role. login() computed the correct role at token-issue time but never actually included it in the signed token, so the role check silently fell back to treating everyone as a viewer. Submit and comment endpoints now look up the user's live role from the database instead of trusting the token claim (also means a role promotion takes effect immediately, no re-login needed); login() now sets the claim correctly too, for consistency with chirp-server.
- Both the Global Admin and local instance Users pages could fail to load their list with the failure swallowed entirely — an empty list with no indication anything was wrong. The local instance page now surfaces the real error (e.g. "no active instance selected").

## 0.5.5.x — 2026-09-10 — BUGFIX + FEATURE — server logs no longer drowned by a third-party library's own debug trace; Tailscale support rounded out

- Two separate log attachments turned out to contain thousands of lines of numba's (a librosa dependency) own internal JIT-compilation trace and nothing else — no HTTP access log, no application events, nothing that helped diagnose what was reported. Traced to numba's own logger being set to DEBUG independently of this app's own logging setup, most likely by something in the deployment environment rather than this codebase. Fixed by explicitly capping numba's own logger at WARNING, unconditionally, regardless of what else sets it or how the app gets launched — a server log should now be usable for diagnosing whatever it was pulled for.
- Rounded out the Tailscale/Headscale connectivity work from 0.5.5.w: chirp-device now cleans up its Tailscale connection on shutdown alongside everything else, and validates a placeholder auth key at startup instead of only discovering it later. The Devices page now shows a Tailscale badge on any device reporting one, and its SSH button is no longer hidden for a device that only has a Tailscale IP and no local one.

## 0.5.5.w — 2026-09-10 — FEATURE — import a database as a new location; spectrograms now correct themselves for the color-spread fix; early Tailscale support

- New: create a location by importing an existing chirp-server database, not just starting empty — from both the login-time location picker and the Global Admin panel, which had no way to create or import a location at all before this despite the API already supporting it.
- The detection-color spread fix (0.5.5.v) only invalidated a cached spectrogram's colors for a non-default palette — a recording using the default palette (the common case) would otherwise keep serving its old, sequentially-colored spectrogram forever, since nothing about its own cache key ever changed. Added a one-time, startup-triggered background sweep, per location, that force-regenerates every existing recording's spectrogram once, then marks itself done so it never repeats. Verified directly: an old cached spectrogram gets replaced with a freshly-generated one, the completion flag is set, and re-running the sweep afterward is a safe no-op.
- Early support for reaching a device over Tailscale/Headscale, not just the local network: devices can now report a second, stable IP over heartbeat, and the SSH terminal can connect through either one, with a Local/Tailscale toggle in the terminal itself when both are available. chirp-device gained a config.yaml section and install step for this, off by default. Full remote-management UI (a dedicated status indicator, a way to reach the server itself the same way) is still in progress — this is the connectivity layer, not the finished feature.

## 0.5.5.v — 2026-09-09 — FEATURE (chirp-server, chirp-server-instances) — selectable detection color palettes, with colors spread by species count

- Reported directly, with a screenshot: two species in one recording (Downy Woodpecker, Cooper's Hawk) got assigned red and orange — adjacent, similar-looking hues on the fixed 12-color wheel every detection color came from. The wheel itself wasn't the problem — colors were assigned sequentially in detection order (first species gets color 0, second gets color 1), so any recording with only a few species always landed on whichever colors happen to sit next to each other at the start of the wheel.
- Fixed by spreading assigned colors evenly around the wheel based on how many species are present — 2 species now land on opposite sides, 3 species land 120° apart, and so on. Verified directly: the same two species now get red and cyan instead of red and orange.
- Added four selectable palettes in Settings — Vivid (the original), Colorblind Safe (the established Okabe–Ito palette), Pastel, and High Contrast — applied consistently across the detection list, waveform, and the spectrogram's own baked-in overlay colors (the Python and JS implementations of the spread algorithm were verified to produce byte-identical output for the same input). Switching palettes also correctly invalidates any already-cached spectrogram image, so a stale image never silently keeps showing the old colors.

## 0.5.5.u — 2026-09-09 — FEATURE (chirp-server, chirp-server-instances) — automatic cleanup for orphaned Live Detect poll clips

- Hiding individual, unsaved Live Detect poll clips from the list and dashboard stats (0.5.5.t below) stopped them from cluttering the view, but didn't stop them from piling up in the database and on disk indefinitely if a session is never explicitly saved.
- Added a background sweep, once an hour, that removes any individual poll clip older than 24 hours — long enough that an in-progress session (someone on an hours-long walk) is never mistaken for an abandoned one, short enough that orphaned clips don't linger for days. Removes both the database row and its audio file. A saved session's own consolidated recording is a completely different, unaffected row — this only ever touches the small, per-poll clips that were never rolled into one.
- Verified directly: an old orphaned clip and its file are both removed; a recent clip (a plausibly still-active session) is left alone; a normal recording is never touched regardless of its own age; running the sweep again once nothing is left is a safe no-op.

## 0.5.5.t — 2026-09-09 — BUGFIX (chirp-server, chirp-server-instances) — individual Live Detect poll clips could bury every other recording in the list

- Reported directly from a deployment: leaving Live Detect running for a couple of minutes created hundreds of tiny, individual recordings — one per poll — none of which ever get cleaned up unless the session is explicitly saved. With no session saved, every one of them stayed in the main Recordings list and dashboard counts permanently, indistinguishable from a normal recording except by filename.
- Fixed by marking these individual clips explicitly at creation time and excluding them from the main recordings list and dashboard stats, the same way Haikubox rows are already kept out of the main feed. A session that IS saved is unaffected — the one consolidated recording it produces still shows normally, only the leftover per-poll clips are hidden.
- Verified directly: a normal recording and a saved session both still appear and count correctly; an individual, unsaved poll clip does not appear anywhere and is not counted in dashboard totals.

## 0.5.5.s — 2026-09-09 — BUGFIX + FEATURE (chirp-server-instances only) — backup/restore now correctly targets the caller's own instance; new import-as-new-location flow

- The existing Download Backup / Restore Backup feature (and the three automatic-backup endpoints behind it) had never worked correctly on this multi-tenant fork — every one of them read a single, unused legacy database path instead of the caller's own instance. Downloading a backup silently grabbed the wrong, empty file; restoring one silently overwrote that same file, leaving the instance's own data completely untouched either way.
- Fixed all five endpoints to resolve the caller's own active instance. Two further bugs surfaced while verifying the fix, both fixed: a restore could leave a stale cached settings value visible until its own cache TTL expired, and a leftover WAL-mode sidecar file from the previous database could get replayed onto the freshly-restored file, silently reverting it back. Verified end-to-end: a restore into one location now reliably shows the restored data, a separate location is completely unaffected, and automatic backups list and restore correctly per instance.
- New: upload an existing chirp-server (or another instance's) database to create a brand-new, separate location from it, instead of starting empty or overwriting one via the restore endpoint above. Existing users already in the imported file are preserved as-is; the importer is added or promoted to admin. Verified end-to-end against a recording and setting value: the new location contains the imported data, the source is completely untouched, and the two are confirmed independent afterward, not aliases of the same file. No web UI for this yet — reachable via the API only for now.

## 1.2.17 (chirp-device) — 2026-09-10 — BUGFIX — bat detections only reached the first upload target

- Now posts to every enabled target, not just the first configured one.

## 1.2.16 (chirp-device) — 2026-09-10 — BUGFIX — previous fix's own bug: only tried one of two needed dev packages

- Installs both GObject-Introspection packages unconditionally now, not either/or.

## 1.2.15 (chirp-device) — 2026-09-10 — BUGFIX — install.sh was missing a build dependency for PyGObject

- Added libcairo2-dev and related build tools.

## 1.2.14 (chirp-device) — 2026-09-10 — CONFIG — Tailscale login_server switched to the Cloudflare-tunneled Headscale URL

## 1.2.13 (chirp-device) — 2026-09-10 — BUGFIX — Tailscale silently failed: "Access denied: checkprefs"

- This user wasn't a tailscale operator yet. install.sh now grants that automatically.

## 1.2.12 (chirp-device) — 2026-09-10 — CONFIG — real Tailscale auth key saved in config.yaml

## 1.2.11 (chirp-device) — 2026-09-10 — CONFIG — pointed at the bundled Headscale server

## 1.2.10 (chirp-device) — 2026-09-10 — CONFIG — activated multi-target server_sync, unified device key

## 1.2.7 (chirp-device) — 2026-09-09 — BUGFIX — Live Detect's device mode 401'd against any server but the first

- The local status server only checked the first target's key. Now accepts any configured target's own key.

## 1.2.6 (chirp-device) — 2026-09-09 — FEATURE — server_sync now supports multiple targets, matching upload

## 1.2.5 (chirp-device) — 2026-09-09 — BUGFIX — a secondary upload target never paired

- Its own Devices page never showed the device, even though recordings were landing fine.

## 0.5.5.r — 2026-09-09 — BUGFIX (chirp-server, chirp-server-instances) — spectrograms/audio playback returning 401; a successful Field Guide refresh could still show as empty

- Spectrograms and audio playback render through a plain `<img>`/`<audio>` tag — and browsers have no mechanism to attach a custom header to that kind of request, so on any deployment requiring auth, these always came back 401 regardless of the recording, even though the spectrogram itself had generated successfully. Fixed by accepting a `?token=` query parameter as a fallback, checked only when no header is present, so a normal API call is completely unaffected. Verified directly: the exact request that used to 401 now gets past auth, and a garbage token is still correctly rejected.
- Field Guide's "Refresh" button could succeed at fetching every species and writing them, then still show an empty or stale list — the refresh never invalidated the cached response afterward, so the next read could still serve what was cached from before the refresh ran, including an empty list cached before a location's first refresh ever completed. Fixed by clearing that cache immediately once the refresh writes successfully. Verified end-to-end: species now appear immediately after a refresh.

## 0.5.5.q — 2026-09-09 — BUGFIX (chirp-server-instances only) — every in-memory cache (dashboard stats, life list, settings, etc.) was shared across every location on the server, not scoped to each one

- Reported directly: a Dashboard kept reverting to "no detections" roughly every 30 seconds on a location with recent recordings. Root cause was two layers deep. First — every cache key in this app (dashboard stats, life list, statistics, directory size, regional library) was built with no location identifier in it at all, so on a server with more than one location, whichever location's request ran most recently silently overwrote what every other location's next request would see. Second, and what made it happen on a fixed 30-second cadence specifically — the background job that proactively refreshes the dashboard cache was still checking the single, original database nothing else uses, since a periodic timer has no request to resolve a location from, the same class of gap already found and fixed elsewhere this session for other background jobs.
- Fixed at the cache itself, once, rather than touching every place that reads or writes it: every key now automatically includes which location is asking, using the same per-request tracking this app already keeps for exactly this kind of need. The background warmer now loops over every location's own database in turn instead of the one unused legacy one.
- Verified directly: two locations, one with an upload and one without, now correctly show different numbers instead of whichever ran last; running the warmer directly confirms it reaches both locations, not zero.

## 0.5.5.p — 2026-09-09 — CHORE (chirp-server-instances only) — default global-admin bootstrap username set

- `CHIRP_GLOBAL_ADMIN_USERNAME` now defaults to `joshsalvi` in docker-compose.yml rather than empty — the panel promotes that account automatically on the next restart, with no manual env var edit needed first.

## 0.5.5.o — 2026-09-09 — BUGFIX (chirp-server-instances only) — theme picker's selected checkmark overlapped the theme's own icon

- Reported directly with a screenshot: the checkmark on a selected theme card was centered directly over that theme's icon, obscuring it. Moved to a small badge in the icon's bottom-right corner instead — the icon stays fully visible, and the selection is still clearly marked. Verified visually with a live render of the theme list.

## 0.5.5.n — 2026-09-09 — BUGFIX (chirp-server-instances only) — the cause of Settings failing to load and device keys failing to generate: schema migrations never reached any existing instance's own database

- Confirmed directly from a production error log: `no such column: app_settings.allow_manual_reanalyze`. Root cause — the column-migration mechanism (`_migrate_columns()`, which adds any column a model declares but an existing SQLite table is still missing) always ran against chirp-server's own single, original database engine. In this multi-tenant fork that engine is a deliberately unused placeholder; every instance keeps its own separate database file entirely, so no migration ever reached any of them. A location created before a given column existed would be missing it forever, and since the ORM selects every declared column on any query against that table, one missing column breaks the entire row — not just the new feature that added it. This is why Settings loading and device-key generation looked like two unrelated failures; they were the same missing column, hit from two different endpoints.
- Fixed by having the same migration logic accept which database to check, then running it against every existing location at every startup, in addition to its original call site. Also runs once at the moment a brand-new location is created, as a cheap safety net.
- Verified by reproducing the reported failure — manually removing a column from an instance's database to match the corrupted state directly — then confirming a restart alone repairs it and both endpoints work again, with no manual database surgery needed on anyone's part.

## 0.5.5.m — 2026-09-08 — BUGFIX (chirp-server-instances only) — three issues reported directly: Sign Out button missing, Settings stuck loading forever, Global Admin's own forbidden page broken

- Sign Out button wasn't appearing when clicking the username in the sidebar. Traced to `/auth/me` reporting `auth_required: false` for a logged-in user — this app has no meaningful "auth disabled" mode (every request needs a login token to know which location's database to use at all), but inherited that concept unmodified from the single-tenant version. A freshly created location has no settings row yet, so the check fell back to a global default of false. Fixed both going forward (seeded at location-creation time) and retroactively for locations that already existed before this fix.
- Settings page could get stuck on "Loading settings…" forever with no explanation. The fetch had no error handling at all — a failed request just vanished silently. Now shows the error with a reload button instead of an infinite spinner.
- Verified directly that a local (per-location) admin is correctly blocked from every part of the Global Admin panel — the backend already enforced this correctly, but found and fixed a bug in how the panel's own page detected that block: it tried to match the digits "403" inside the error text, which never contained them, so a local admin who navigated to the page directly saw a broken half-rendered panel with data-load errors instead of a clean "not available" message.

## 0.5.5.l — 2026-09-08 — FEATURE (chirp-server-instances only) — Global Admin panel: manage every instance and account on the server from one place

- Previously, the only way into an instance was self-service via invite code (always as a viewer, with no way to promote afterward), and there was no view of the server as a whole. New `is_global_admin` flag on a login identity, bootstrapped via a `CHIRP_GLOBAL_ADMIN_USERNAME` environment variable rather than requiring direct database access to set the first one.
- New panel (Global Admin, in the sidebar/menu for anyone with the flag) covering every instance and every account: add a specific person to an instance by username with a choice of role, change or remove someone's role afterward — kept in sync with that instance's own local record, not just the registry's — disable or re-promote an account, and remove an instance from the registry (deliberately never touches its database file, so a location's recorded history can't be lost to one click).
- Verified with a live, running instance of the server end-to-end — not just backend assertions: registered an account, promoted it, logged in, created a location, and drove the rendered UI through Playwright to add a member, change a role, and remove a member. Caught and fixed a bug this way before it shipped: the new sidebar/menu code referenced a piece of login state that belonged to a different component than the one it was placed in, which would have crashed the entire app on load for every user, not just this new panel — confirmed the crash was gone and the panel worked by screenshotting the rendered result, not just checking the build succeeded.

## 0.5.5.k — 2026-09-08 — BUGFIX (chirp-server-instances only) — devices could not upload to any instance at all; background analysis of what did upload silently never ran

- Traced directly from a device config that wouldn't connect. Root cause: this app's multi-tenant routing resolves which instance's database to use only by decoding a JWT — but a device authenticates with its own long-lived API key, never a JWT, so every device-facing request (pairing, upload, heartbeat) was rejected with 401 before that endpoint's own, already-correct key validation ever ran. This affected every device, not a config mistake on any one person's part; nothing about this was specific to which upload protocol a device spoke.
- Fixed by resolving the instance from a device's own key when no JWT is present — checked wherever a device's key can appear (X-API-Key header, Authorization: Bearer, or the JSON body specifically for pairing, which never used a header at all) — with zero changes to chirp-server's own device or recording endpoint code, matching this project's core design rule.
- Found and fixed a second, equally blocking bug while verifying the first one end-to-end: even once upload succeeded, the background task that runs BirdNET analysis was opening a session against a different, unrelated database — every request-triggered background task in the app has the same underlying pattern, not just this one. A recording would sit at "processing" forever with zero detections, no visible error anywhere. Fixed the same way, with the same zero-changes-to-existing-code approach.
- Verified with direct tests against the `/api/v1/devices/pair` and `/api/v1/recordings/upload` endpoints themselves — not simplified mocks — including a WAV file upload confirmed to reach `processing_status: done`, and confirmed the human login flow is completely unaffected by any of this.

## 0.5.5.j — 2026-09-08 — FEATURE + BUGFIX (chirp-server, chirp-server-instances) — new setting to hide the manual Re-analyze button; removed a stray "(testing)" label from range map settings

- New Settings toggle (Server-Side Analysis) lets an admin hide the manual "Re-analyze" button everywhere it appears on a recording's detail page. Enforced server-side on both the single-recording and bulk endpoints, not just hidden in the UI — verified disabling blocks both, and that the bulk endpoint isn't a loophole around the single one.
- The eBird Status & Trends range map source no longer says "(testing)" in Settings.

## 0.5.5.i — 2026-09-06 — FEATURE + BUGFIX (chirp-server, chirp-server-instances) — Live Detect's status card now shows the heard species' photo; fixed Recordings' new filters not refreshing the list

- Reported directly: clicking the Live Detect or Multiple species filter on the Recordings page changed the URL but never reloaded the list. Root cause: both were missing from the reload effect's own dependency array, so React never re-ran it — a leftover gap from adding the two filters two versions ago.
- Live Detect's "Heard X!" now shows the species' own photo in place of the generic icon, using the same photo already shown moments later in Heard Today. Held on the same timer as the text itself, so the two never fall out of sync.

## 0.5.5.h — 2026-09-06 — BUGFIX (chirp-server, chirp-server-instances) — Live Detect's low-rumble filter and volume boost stopped holding their slider value

- Reported directly, with a screenshot. In ChirpPi (device) mode, moving either slider took effect for a moment, then silently reverted. Root cause: every newly arrived audio clip reset both to a stale value captured when listening started, undoing whatever the slider had just set. Reproduced the exact behavior with a direct test before fixing, then confirmed the fix holds across repeated clips, not just the first one.

## 0.5.5.g — 2026-09-04 — PERFORMANCE + BUGFIX (chirp-server, chirp-server-instances) — Dashboard's first load is now consistently fast; fixed low-contrast text in digest emails

- Reported directly: Dashboard's last-detection text, today's detections, and stat cards took an extra couple seconds to load. Root cause: the existing 45-second cache only helped a repeat request, not a person's first Dashboard visit of a session. New background service proactively refreshes that cache every 30 seconds, so a real visit essentially never hits a cold one — verified a genuine HTTP request now completes with zero new database queries.
- Reported directly: digest emails didn't have great contrast. Checked the actual WCAG math and found every section label and stat-card caption in the email templates used a color that measured 3.4-3.6:1 against its background, under the 4.5:1 floor required for text that size. Replaced with a brighter shade of the same hue that clears 5.6:1+ everywhere it's used.

## 0.5.5.f — 2026-09-04 — BUGFIX (chirp-server, chirp-server-instances) — fixed 0.5.5.e duplicating Logs, Users, and Tech Docs in the sidebar

- Reported directly, with a screenshot. 0.5.5.e added those three to the sidebar's own list, but three older, separate hardcoded entries for the same three items were still sitting right after it, never removed from back when the list itself didn't include them. Removed the leftover duplicates.

## 0.5.5.e — 2026-09-04 — BUGFIX (chirp-server, chirp-server-instances) — desktop sidebar was missing Live Detect, Users, Logs, Tech Docs, and What's New entirely

- Reported directly: the desktop sidebar and the mobile ⋮ menu had quietly drifted apart. The sidebar had no entry at all for Live Detect, Users, Logs, Tech Docs, or What's New — those pages were reachable only by typing a URL directly on desktop. Also found Settings was admin-only in the sidebar specifically, while every other surface (mobile menu, a typed URL) already let non-admin viewers reach it to change their own theme — now consistent everywhere. Both lists reordered to match: primary pages first, then general-purpose ones, then admin tools grouped together, with What's New and My Profile last.

## 0.5.5.d — 2026-09-04 — FEATURE + BUGFIX (chirp-server, chirp-server-instances) — new Recordings filters for Live Detect sessions and multi-species recordings; fixed "Heard X!" flashing too quickly

- Recordings page can now filter to Live Detect sessions, or to recordings with more than one distinct species detected (not just more than one detection).
- Reported directly: Live Detect's "Heard X!" message was being overwritten by the next cycle's own routine status update after as little as 250ms — too fast to read a species name. Now holds on screen for a fixed 2.5 seconds; a new detection during that window still shows immediately rather than being suppressed.

## 0.5.5.c — 2026-09-04 — PERFORMANCE (chirp-server, chirp-server-instances) — a recording's waveform is no longer recomputed on every single page view

- Investigated as part of a Dashboard/Recordings optimization pass, alongside checking several other areas (recent comments, spectrogram serving, the recordings list query) that turned out to already be well-optimized. The waveform endpoint had no caching at any layer, recomputing from scratch — benchmarked at 12-58ms depending on length — on every page load or refresh for data that never changes. Now cached the same way the spectrogram already was.

## 0.5.5.b — 2026-09-03 — BUGFIX (chirp-server, chirp-server-instances) — fixed 0.5.5.a destroying ultrasonic content in new bat detection clips

- 0.5.5.a's clip compression applied to bat detections too, and standard MP3 tops out at a 48kHz sample rate — tested a 40kHz tone (a bat call frequency) through the exact ffmpeg command and found it was completely gone on decode, not degraded. Bat clips now use lossless FLAC instead — verified the same test tone survives with its exact frequency and sample rate intact, at roughly 62-78% smaller than uncompressed. Bird clips are unaffected. Any bat clip saved between 0.5.5.a and this fix would need re-extraction to recover; nothing prior to 0.5.5.a was touched.

## 0.5.5.a — 2026-09-03 — PERFORMANCE (chirp-server, chirp-server-instances) — detection clips are now compressed, cutting new-clip disk usage by roughly 85%

- Investigated in response to a storage-overhead question: clips_dir was 129.4 GB across 148,764 uncompressed WAV files, one per detection. Clips are never fed back into BirdNET (confirmed directly), so switching new clips to compressed audio has no effect on detection accuracy — verified an 86.2% size reduction with correct duration through the extraction pipeline itself. Go-forward only: nothing already on disk is touched or re-encoded. Also fixed the noise-reduction "Enhance" pipeline, which would have crashed on the new format without a decode step added at that specific call site.

## 0.5.4.z — 2026-09-03 — BUGFIX (chirp-server, chirp-server-instances) — fixed Tutorial demos shifting the page as their captions cycled

- Reported directly, with a screenshot. Two Tutorial demos (Enhancing a clip, Seen Today) sized their caption text for one line, but one caption in each wraps to two lines on a narrower phone — confirmed directly at 320px width. Every phase now reserves the same two-line height, so nothing below the demo moves as it cycles.

## 0.5.4.y — 2026-09-03 — FEATURE (chirp-server, chirp-server-instances) — new tool checks whether database size is slowing anything down

- New "Check query plans" button in Settings → Diagnostics → Database, next to the VACUUM tool: runs EXPLAIN QUERY PLAN against the app's own heaviest queries and reports whether each is using an index or scanning the whole table. Verified against a 15,000-row test dataset — every query checked correctly used an index, with zero full table scans.

## 0.5.4.x — 2026-09-03 — DOCS (chirp-server, chirp-server-instances) — Tutorial now covers Live Detect; fixed an out-of-date navigation description

- New Live Detect section in the Tutorial, including the new "save this session as one recording" option. Also fixed the Navigating Chirp section, which still described the bottom bar from before Live Detect took a primary tab there.

## 0.5.4.w — 2026-09-03 — BUGFIX (chirp-server, chirp-server-instances) — fixed log/report downloads not starting in some browsers; added a database VACUUM tool

- Confirmed via a real diagnostics download that server log, device log, and report downloads could silently do nothing in some browsers — all three were missing a step every other download button in the app already handles correctly. Also new: a "Run VACUUM now" button in Settings → Diagnostics, Dashboard Sections now lists in display order, and a noisy per-recording debug line (nearly all of a 100-line log snapshot) is gone.

## 0.5.4.v — 2026-09-03 — PERFORMANCE (chirp-server, chirp-server-instances) — SQLite query-planner statistics now stay fresh automatically

- Investigated in response to a database-size question. Found the hourly storage cleanup already deletes and archives rows continuously, but nothing anywhere ran ANALYZE, so SQLite's query planner has been working from statistics that only get staler as the database grows. Now runs automatically as part of that same hourly cycle. Verified directly that it produces planner statistics and that a failure there can't break the rest of cleanup.

## 0.5.4.u — 2026-09-03 — FEATURE (chirp-server, chirp-server-instances) — admins can now choose which Dashboard cards show up, and skip API calls for disabled ones

- New "Dashboard Sections" panel in Settings → Appearance (admin-only): choose which of Dashboard's ten cards show up, independently for Detailed and Simplified mode. Unchecking a card skips its data entirely — it's not just hidden, the request for it never fires — a way to cut down Dashboard's load if some of these aren't useful to a given deployment. Nothing changes for anyone who leaves this alone; every card still shows exactly as it always has.

## 0.5.4.t — 2026-09-03 — PERFORMANCE (chirp-server, chirp-server-instances) — Dashboard's two heaviest queries are now cached

- Mapped every API call Dashboard makes (there are eight) and checked each for caching. Two — the main stats endpoint and the daily/weekly summary — had none at all, confirmed doing 8 and 11 database queries respectively on every single load with no reuse between them. Both now cache for 45 seconds, the same approach already used elsewhere on the page, verified directly to produce zero additional queries on a repeat visit within that window.

## 0.5.4.s — 2026-09-03 — BUGFIX + ENHANCEMENT (chirp-server, chirp-server-instances) — fixed a bug in saved Live Detect sessions; noise-reduced audio is now ready instantly

- Caught while investigating a background-noise question: a saved Live Detect session was being marked with a status value the database doesn't allow, which would have broken viewing that recording the next time anyone loaded it. Fixed, and added a dedicated test that runs the background step itself rather than mocking it out, which is exactly what let this slip through the first time.
- The existing "Enhanced" (noise-reduced) audio option on any recording's page now gets pre-generated in the background right when a Live Detect session saves, instead of only starting the first time someone clicks it — a multi-minute session recording no longer makes that first click wait.

## 0.5.4.r — 2026-09-03 — FEATURE (chirp-server, chirp-server-instances) — Live Detect sessions can now be saved as one recording

- On Stop, if the session heard anything, you're now asked whether to save the whole session as one continuous recording — the scattered small per-detection clips get consolidated into it and removed, so it's one recording per walk, not a dozen tiny ones. Declining leaves everything exactly as it already worked. Shows up in Recordings tagged as a Live Detect session, both in the list and on the recording's own page.

## 0.5.4.q — 2026-09-02 — BUGFIX (chirp-server, chirp-server-instances) — Settings tabs other than Appearance rendered slightly lower than they should

- Reported directly, with screenshots. Root cause: the tab-switching logic hid inactive sections with display:none only, but the page's spacing utility only excludes elements with the hidden attribute from its margin calculations — so every hidden section still counted as a "present" sibling and kept adding space above whichever tab was actually showing. Every tab but the first was affected; confirmed the exact 24px gap directly, and confirmed it's gone after the fix.

## 0.5.4.p — 2026-09-02 — ENHANCEMENT (chirp-server, chirp-server-instances) — Yard Diversity explanation is now a proper popup; removed a personal email from the sidebar

- Reported directly. The "what does this mean?" info button on the Dashboard's Yard Diversity card now opens a popup instead of expanding in place, and the button itself is labeled "Learn more" instead of an unlabeled icon.
- Reported directly. Removed a personal support email link that sat in the sidebar under "What's New".

## 0.5.4.o — 2026-09-02 — BUGFIX (chirp-server, chirp-server-instances) — ChirpPi audio in Live Detect no longer skips/pauses every few seconds

- Reported directly. Each clip was only fetched after the previous one finished playing, leaving an audible network-round-trip-sized gap between every clip. Now double-buffered — the next clip starts fetching the moment the current one starts playing, the same technique already used for the Listen feature in Settings. Verified the gap drops to effectively zero across multiple consecutive clips.

## 0.5.4.n — 2026-09-02 — PERFORMANCE + BUGFIX (chirp-server, chirp-server-instances) — Dashboard loads progressively instead of all at once; comments no longer show "(edited)" immediately on posting

- Reported directly: Dashboard felt like it loaded all at once instead of in stages. Root cause: the whole page was gated behind a single loading check tied to one specific API call, even though three of the four calls it fires don't depend on that one at all. Each section now shows its own content the moment its own data is ready, so whichever call finishes first is what appears first, top to bottom.
- Reported directly, with a screenshot: a brand-new comment showed "(edited)" immediately. Root cause: two timestamp columns were both set independently at the same moment, so they were never exactly equal even seconds apart. Fixed going forward, plus a one-time cleanup for comments already affected.

## 0.5.4.m — 2026-09-02 — FEATURE + BUGFIX (chirp-server, chirp-server-instances) — Cloudflare-tunnel image caching, AI second opinion formatting, and a decode-error message fix

- Reported directly: pages felt slower accessed through a Cloudflare tunnel than on the LAN. Found the cause — seven file-serving endpoints (bird photos, bird call audio, user avatars, Tech Docs images, the app's own logo) had no Cache-Control header at all, an isolated gap against an otherwise carefully-cached codebase. Every image was round-tripping through the tunnel on every single load. Fixed with the same caching convention already used everywhere else.
- AI Second Opinion now bolds each species name, gives each species its own paragraph, and ends with a plain-language "Overall:" consensus line — rendered as formatting now, not shown as literal "**" characters.
- Reported directly, with a screenshot: Live Detect's decode-failure message showed nothing but ffmpeg's own version/build banner, not the error. The diagnostic was always at the end of ffmpeg's output, not the start — fixed to show that instead.

## 0.5.4.l — 2026-09-02 — PERFORMANCE (chirp-server, chirp-server-instances) — Dashboard images below the fold no longer block initial load

- Continued the Dashboard investigation: the Seen Today grid, rarest-species list, and Recent Recordings thumbnails now lazy-load, matching what Life List and Field Guide already do. Left the top hero images (most common bird, latest recording) loading immediately, since those are the first thing on the page.

## 0.5.4.k — 2026-09-02 — PERFORMANCE (chirp-server, chirp-server-instances) — Dashboard no longer makes a redundant auth request on every load

- Dashboard fetched its own copy of /auth/me on every mount just to read one field (dashboard_mode), duplicating a fetch the app already makes once at startup before any page even renders. Now reads it from there instead — one fewer network round trip blocking Dashboard's initial render, every time. Verified behaviorally identical to the old logic across every auth state (disabled, disabled-but-authenticated, normal).

## 0.5.4.j — 2026-09-02 — BUGFIX (chirp-server, chirp-server-instances) — Field Guide showing species with no business being anywhere near your location

- Reported directly. Verified the eBird region lookup itself was correct against the deployment's own stored coordinates — the bug was that any species detected locally but absent from the standard eBird checklist (including a one-off misidentification) was given the maximum possible likelihood score, guaranteeing it outranked every regional species. Confirmed fixed with the exact scenario: an off-checklist species no longer sorts above a common local bird.

## 0.5.4.i — 2026-09-01 — PERFORMANCE (chirp-server, chirp-server-instances) — Life List no longer renders every species at once

- Investigated Dashboard, Life List, Recordings, and Field Guide for load-time issues. Their backend queries, indexes, and caching were already well-optimized from prior work. Found one remaining gap: Life List rendered every detected species into the DOM immediately, unlike Field Guide's own chunked reveal — the life-list endpoint has no cap, so this could reach hundreds of rows for an established deployment. Now uses the same chunked-reveal pattern Field Guide already had; verified directly that a 200-species list now renders 24 DOM rows initially instead of all 200.

## 0.5.4.h — 2026-09-01 — FEATURE + BUGFIX (chirp-server, chirp-server-instances) — download Ollama models from Settings; Live Detect no longer offers Haikubox/Bird Buddy as a source

- Settings now lists models already pulled on your Ollama server and lets you download a new one directly, instead of needing to SSH in and run `ollama pull` by hand.
- Reported directly: Live Detect's ChirpPi picker was listing Haikubox and Bird Buddy alongside paired ChirpPi devices — neither has a mic to stream from. Both are now excluded.

## 0.5.4.g — 2026-09-01 — FEATURE (chirp-server, chirp-server-instances) — ChirpPi audio is now audible in Live Detect, plus gain/filter controls

- Live Detect's ChirpPi clips now play through your speakers while listening, not just visualized silently.
- Added volume boost and a low-rumble cut (highpass filter) for live monitoring, on both phone and ChirpPi sources — applies only to what you hear/see, never to what's sent for detection.

## 0.5.4.f — 2026-09-01 — FEATURE (chirp-server, chirp-server-instances) — Live Detect's spectrogram now works for ChirpPi mics too

- Was phone-mic only. Since a ChirpPi's audio only ever arrives as short clips (not a continuous stream), the same live waterfall now plays each clip muted through the analyser and fetches the next one when it ends — verified directly that the analyser receives frequency data and stays silent.

## 0.5.4.e — 2026-09-01 — BUGFIX + ENHANCEMENT (chirp-server, chirp-server-instances) — fixed a stuck-error state that survived reload and app restart; Live Detect now groups by species with photos

- Reported directly: a page crash that neither reloading nor restarting the app fixed. Root cause: the recovery path only reloaded the page, which does nothing about an already-active service worker still serving stale cached files underneath the fresh HTML. It now also forces a service-worker update check and wipes the cache storage before reloading — verified directly that a stale cached file is gone afterward, not just theoretically fixed.
- Live Detect's session list now groups repeated detections of the same species into one row with a count and best confidence, instead of a separate row per detection — and shows the species' photo when one's available.

## 0.5.4.d — 2026-09-01 — ENHANCEMENT (chirp-server, chirp-server-instances) — bird profiles reorganized into tabs, Seasonal Presence moved up

- Bird profile pages now have a left-nav sidebar (matching Settings and Tech Docs) instead of one long scrolling page: Overview, Sounds & Trivia, Range & Media, Your Data, Reference. Seasonal Presence moved into Overview, right after At a Glance, instead of near the bottom.
- Tested specifically for horizontal overflow on mobile (the nav is a horizontally-scrollable strip, not a page-level scroll) across common phone widths — none found.

## 0.5.4.c — 2026-09-01 — FEATURE + BUGFIX (chirp-server, chirp-server-instances) — bird profiles show your own local detection history, plus a dashboard greeting fix

- Reported directly: the dashboard's greeting showed a sunset icon at 1pm. Fixed — the icon now has its own hour thresholds instead of sharing the 3-way morning/afternoon/evening text buckets, and both now use the deployment's configured timezone instead of the browser's own clock.
- Bird profiles' Seasonal Presence card now also shows a line graph of this species' own detection history at your location (weekly, all years combined), with translucent season bands — alongside the existing eBird regional-frequency chart, not replacing it. Found and fixed a bug before shipping: the new endpoint used Python's 1-indexed month, silently breaking every season band (December matched no season at all) until a direct test caught it.

## 0.5.4.b — 2026-09-01 — BUGFIX (chirp-server, chirp-server-instances) — Live Detect's spectrogram wasn't scrolling; Heard Today's "Advanced" link went to the wrong place

- Reported directly: the live spectrogram looked like a static updating line instead of scrolling. Root cause found and confirmed with a direct test — the canvas mixed a scaled drawing call with two unscaled ones, which silently broke the scroll on any high-DPI screen. Now works consistently in raw pixels throughout.
- "Advanced" next to Heard Today went to the Statistics page, an odd destination for "show me today's species" — and would have silently ended an active listening session by navigating away. Now opens the same species grid Dashboard's own Seen Today card uses, without leaving the page.

## 0.5.4.a — 2026-09-01 — FEATURE (chirp-server, chirp-server-instances) — Live Detect: real-time bird ID from your phone or a ChirpPi

- New "Live Detect" page (Merlin Sound ID-style) — listens continuously, shows a live spectrogram, and saves anything it hears as a recording with detections. Replaces Notes/Comments in the mobile bottom bar; Notes moved into the overflow menu.
- Two sources: your phone's own mic (default), or a deployed ChirpPi's mic streamed the same way the mic-check Listen button works. A clip with nothing in it is discarded — only detections are kept.

## 0.5.3.t — 2026-08-31 — FEATURE (chirp-server, chirp-server-instances, chirp-device 1.2.4) — Listen now works for the AudioMoth too, downshifted into hearing range

- Reported directly: the AudioMoth had no Listen button. Bat echolocation is inaudible at its native rate, so a raw clip wouldn't have been useful — the AudioMoth's clip is now automatically downshifted ~10x (same time-expansion technique the enhanced-clip feature already uses for saved bat recordings) before being sent, so it's audible.

## 0.5.3.s — 2026-08-31 — BUGFIX (chirp-server, chirp-server-instances) — Listen button on mic check was nearly invisible

- Reported directly: the Listen button next to a mic's dBFS reading was too subtle to notice — no border, near-transparent background. Now a colored, bordered circle that reads as a button, not a stray dot.

## 0.5.3.r — 2026-08-31 — ENHANCEMENT (chirp-server, chirp-server-instances) — AI second opinion groups by species instead of listing every detection

- Reported directly: a recording with 15 detections of the same species produced 15 near-identical paragraphs, one per timestamp. Detections are now grouped by species first — one synthesized paragraph per species (noting which segments look strongest/weakest and why), capped at 3-5 sentences regardless of how many detections that species has. A recording with several different species still gets one paragraph per species.

## 0.5.3.q — 2026-08-31 — ENHANCEMENT (chirp-server, chirp-server-instances) — dashboard hero and stat cards polish

- Stat card numbers (Recordings, Species, Detections) now count up to their value instead of just appearing, respecting prefers-reduced-motion.
- The greeting now shows a sun/sunset/moon icon matching the time of day, plus today's date next to the last-detection line.

## 0.5.3.p — 2026-08-30 — FEATURE (chirp-server, chirp-server-instances, chirp-device 1.2.3) — listen to a mic's live audio, not just its level

- Mic check now has a Listen button per mic (device-local rows only), separate from the existing level meter — plays back live audio a few seconds behind now, so you can hear static, clipping, or a wrong mic instead of only seeing a dBFS number.
- chirp-device: new `/listen` endpoint on the existing local status server, reusing the same already-captured audio buffer the level meter reads (no second microphone open). Bat mic excluded — its audio is ultrasonic and inaudible without downshifting, a separate feature.
- Found and fixed a design issue before shipping: a mic's position in the level list isn't reliable across the server's own device-local/SSH merge step, so Listen matches by mic name instead of list position.

## 0.5.3.o — 2026-08-30 — ENHANCEMENT (chirp-server, chirp-server-instances) — diversity stats: rolling 30 days on the Dashboard, flexible windows on Statistics

- Dashboard's Yard Pulse diversity now uses a rolling 30-day window instead of resetting on the 1st of each month.
- Statistics page's Diversity Indices chart now supports 12/24 months or all-time, with completed months cached so "all time" doesn't rescan the whole database on every request.

## 0.5.3.n — 2026-08-30 — BUGFIX + CHORE (chirp-server, chirp-server-instances) — Statistics toolbar overflow fixed; changelog cleanup

- Fixed the Statistics page's Detections/Recordings/Bats-excluded/Refresh row overflowing off the right edge of the screen on narrow phones instead of wrapping. Audited every other page with a similar layout for the same issue; none found.
- Cleaned up this changelog: removed lingering filler words and cut every v0.5.x entry down to 1-2 lines.

## 0.5.3.m — 2026-08-28 — ENHANCEMENT (chirp-server, chirp-server-instances) — dashboard polish, presence summary timestamps, app-wide shimmer fix

- Dashboard now shows a loading skeleton and a "busiest hour" callout on the activity chart. Bird profile presence summaries show when they were generated. Fixed every skeleton loader in the app rendering static instead of animating (a Tailwind keyframe was never being compiled in).

## 0.5.3.l — 2026-08-27 — ENHANCEMENT (chirp-server, chirp-server-instances) — AI second opinion now covers bat calls and multi-species recordings

- AI Second Opinion now works on bat recordings (ultrasonic spectrogram, asks about genuine echolocation vs. false positive) and comments on every species in a multi-bird recording instead of just the top one. Button renamed to "AI Second Opinion" for clarity.

## 0.5.3.k — 2026-08-27 — ENHANCEMENT (chirp-server, chirp-server-instances) — What's New popup history now groups by minor version

- The popup's history now collapses each prior minor version (0.5.2, 0.5.1, ...) into one line instead of listing every patch individually forever.

## 0.5.3.j — 2026-08-27 — ENHANCEMENT (chirp-server, chirp-server-instances) — Tech Docs figures are now clickable to expand

- Diagrams in Tech Docs open full-screen on click instead of staying at a fixed inline width.

## 0.5.3.i — 2026-08-27 — ENHANCEMENT (chirp-server, chirp-server-instances) — iNaturalist submission settings are now remembered per user

- Submission settings (spectrogram, details, enhanced audio, AI second opinion) are now saved per user instead of one shared setting, so a shared browser with multiple accounts no longer overwrites everyone's preferences.

## 0.5.3.h — 2026-08-27 — BUGFIX (chirp-server, chirp-server-instances) — wide Tech Docs tables bled off the screen instead of scrolling

- The microphone comparison table (and any wide table) now scrolls inside its own card instead of overflowing the page.

## 0.5.3.g — 2026-08-27 — DEVELOPER (chirp-server, chirp-server-instances) — Tech Docs expanded with content from the README files

- Added Microphones, Device Setup Guide, and AI Features pages, plus content folded into existing pages, from the project's README files.

## 0.5.3.f — 2026-08-26 — CHORE (chirp-server, chirp-server-instances) — removed unnecessary "real"/"actual" filler from recent writing

- Reported directly: words like "real" and "actual" had become an overused verbal tic across changelogs, in-app copy, tech docs, and code comments, sounding unnatural. Cleaned up whatsNew.js and techdocs/docs/ in full, this changelog's own 0.5.x+ entries (pre-0.5 left as historical record, not rewritten), and the comments in Settings.jsx, BirdSizeRuler.jsx, BirdProfile.jsx, TechDocs.jsx, ScrollToTop.jsx, RecordingsList.jsx, bird_enricher.py, and app/api/techdocs.py — while deliberately keeping genuine uses like "real-time" intact.
- Found a risk in the process and caught it before it shipped: a blanket word-removal isn't safe in source code, since the same word can also be a variable name. `const real = (devs || []).filter(...)` in Settings.jsx became `const = (devs || []).filter(...)`, breaking the build. Reconstructed the logic, renamed the variable, and pre-emptively searched every other file (both projects) for the identical pattern before touching them, so it only broke once.
- Also caught a case-sensitivity gap in the cleanup itself (Title-Case "Real" at the start of a sentence slipped past a check that wasn't case-insensitive on its last pass) — swept every already-processed file for the same gap before fixing it, and a leftover patent-application reference in techdocs.py's docstring that an earlier cleanup pass had missed.

## 0.5.3.e — 2026-08-26 — BUGFIX (chirp-server, chirp-server-instances) — Crow/Hawk icons crowding each other; scroll-to-top overlapping Settings' Save button

- Fixed Crow/Hawk icons crowding each other on the size ruler, and scroll-to-top overlapping Settings' floating Save button.

## 0.5.3.d — 2026-08-26 — ENHANCEMENT (chirp-server, chirp-server-instances) — robin silhouette replaces the pigeon stand-in; scroll-to-top spacing; Tech Docs patent banner removed

- Replaced the size ruler's pigeon stand-in with a robin silhouette, increased scroll-to-top's mobile spacing, and removed the patent-pending banner from Tech Docs.

## 0.5.3.c — 2026-08-25 — BUGFIX + FEATURE (chirp-server, chirp-server-instances) — Tech Docs internal links went to a blank page; new scroll-to-top button

- Fixed Tech Docs' internal links going to a blank page, and added a scroll-to-top button.

## 0.5.3.b — 2026-08-25 — BUGFIX (chirp-server, chirp-server-instances) — Conservation tag was scraped but silently dropped before reaching the profile

- Fixed Conservation data being scraped but silently dropped before reaching the bird profile; adjusted the At a Glance layout for 4 tiles. Affected profiles need a refresh to pick up Conservation data.

## 0.5.3.a — 2026-08-25 — FEATURE (chirp-server, chirp-server-instances) — Life History card, with full paragraphs from AAB's own separate page

- Added a Life History card with full paragraphs from All About Birds, plus a Conservation tile in At a Glance.

## 0.5.2.n — 2026-08-25 — BUGFIX + ENHANCEMENT (chirp-server, chirp-server-instances) — duplicate version badge in Settings; size ruler self-reference wording

- Fixed a duplicate version badge in Settings, and redundant size-ruler wording on a bird's own profile.

## 0.5.2.m — 2026-08-25 — ENHANCEMENT + BUGFIX (chirp-server, chirp-server-instances) — Settings page navigates like Tech Docs; two pre-existing JSX bugs found and fixed

- Settings now navigates with a sidebar like Tech Docs, plus two pre-existing JSX bugs fixed along the way.

## 0.5.2.l — 2026-08-25 — ENHANCEMENT (chirp-server, chirp-server-instances) — admin-only Tech Docs page, pigeon silhouette fix

- Added an admin-only Tech Docs page, and fixed a pigeon silhouette used for the wrong reference bird.

## 0.5.2.k — 2026-08-25 — ENHANCEMENT (chirp-server, chirp-server-instances) — size ruler used only the middle-right of the available width

- The size ruler now spans the full card width instead of leaving one side empty.

## 0.5.2.j — 2026-08-24 — BUGFIX + ENHANCEMENT (chirp-server, chirp-server-instances) — size ruler text clipping off the card edge; switched to a log scale

- Fixed size text clipping off the card edge, and switched the ruler to a log scale for more even spacing.

## 0.5.2.i — 2026-08-24 — BUGFIX (chirp-server, chirp-server-instances) — size ruler's "Robin" position was pigeon artwork under the wrong name; text-to-silhouette spacing

- Fixed the size ruler's "Robin" position showing pigeon artwork, and added breathing room above the silhouettes.

## 0.5.2.h — 2026-08-24 — ENHANCEMENT (chirp-server, chirp-server-instances) — size ruler shows the range on the line, not just the nearest reference

- The size ruler now shows a bird's measured range on the line, not just the nearest reference point.

## 0.5.2.g — 2026-08-24 — ENHANCEMENT (chirp-server, chirp-server-instances) — size ruler silhouettes replaced with licensed artwork

- Replaced hand-drawn size-ruler silhouettes (several redesign attempts, still not recognizable) with licensed bird artwork.

## 0.5.2.f — 2026-08-24 — BUGFIX (chirp-server) — README version was stale (0.5.0.p), no longer manually maintained

- Fixed the README's version going stale, and added a workflow to auto-update it on every version bump.

## 0.5.2.e — 2026-08-24 — ENHANCEMENT (chirp-server, chirp-server-instances) — size ruler silhouettes redrawn larger and more distinct

- Redrew the size ruler silhouettes larger and more distinct from each other.

## 0.5.2.d — 2026-08-24 — ENHANCEMENT (chirp-server, chirp-server-instances) — size ruler redesigned to match AAB's own layout

- Redesigned the size ruler to match All About Birds' own layout, and added CI build verification.

## 0.5.2.c — 2026-08-23 — ENHANCEMENT (chirp-server, chirp-server-instances) — distinct bird silhouettes, silhouette-only highlighting, readability fixes

- Five distinct bird silhouettes instead of one shape scaled up and down; highlighting moved to the silhouette only.

## 0.5.2.b — 2026-08-23 — BUGFIX (chirp-server, chirp-server-instances) — size ruler label collision, bird silhouette redesign, ruler repositioned

- Fixed size-ruler label overlap, redrew the bird silhouette, and moved the ruler below the At a Glance grid.

## 0.5.2.a — 2026-08-22 — FEATURE + BUGFIX (chirp-server, chirp-server-instances) — bird size-comparison ruler, bats-exclusion toggle, changelog repair

- Added a bird size-comparison ruler to At a Glance, and a bats-exclusion toggle for Statistics.

## 0.5.1.i — 2026-08-22 — BUGFIX (chirp-server, chirp-server-instances) — duplicate AI summary generation, Notes page card spacing

- Fixed the AI presence summary generating up to 3x at once, and missing spacing between Notes page cards.

## 0.5.1.h — 2026-08-21 — BUGFIX (chirp-server, chirp-server-instances) — Cool Facts bold lede could end mid-sentence

- Fixed Cool Facts' bolded lede sometimes ending on a dangling word instead of a full clause.

## 0.5.1.g — 2026-08-21 — ENHANCEMENT + BUGFIX (chirp-server, chirp-server-instances) — At a Glance redesigned with symbols; found why some birds were missing it

- Redesigned At a Glance into four symbol cards, and fixed a tooltip that didn't explain why some birds skip it.

## 0.5.1.f — 2026-08-20 — ENHANCEMENT (chirp-server, chirp-server-instances) — At a Glance split into its own card

- Split habitat/food/nesting/behavior into their own At a Glance card, above About.

## 0.5.1.e — 2026-08-20 — BUGFIX (chirp-server, chirp-server-instances) — Submit Observation button wrapped badly on mobile

- Fixed the Submit Observation button wrapping badly on mobile.

## 0.5.1.d — 2026-08-20 — ENHANCEMENT (chirp-server, chirp-server-instances) — Cool Facts card title simplified

- Simplified the Cool Facts card title.

## 0.5.1.c — 2026-08-20 — ENHANCEMENT (chirp-server, chirp-server-instances) — Cool Facts card redesigned for skimmability

- Redesigned the Cool Facts card for skimmability, with a bolded lede per fact.

## 0.5.1.b — 2026-08-19 — BUGFIX (chirp-server, chirp-server-instances) — Cool Facts silently missing for many species since a past Cloudflare block

- Fixed Cool Facts silently missing for many species since a past Cloudflare block disabled retries.

## 0.5.1.a — 2026-08-19 — BUGFIX (chirp-server, chirp-server-instances) — hardcoded green in iNaturalist UI clashed with non-green themes

- Fixed hardcoded green in the iNaturalist UI that clashed with non-green themes.

## 0.5.0.z — 2026-08-17 — BUGFIX + FEATURE (chirp-server) — heatmap controls were being clipped off-screen, plus min/max color scaling

- Fixed the heatmap's species-count selector being clipped off-screen, and added min/max color scaling.

## 0.5.0.y — 2026-08-17 — BUGFIX (chirp-server) — two visual bugs, both measured and confirmed before and after

- Fixed an off-center Raspberry Pi icon on Getting Started, and theme descriptions cutting off mid-sentence.

## 0.5.0.x — 2026-08-17 — BUGFIX (chirp-server) — the audio diagnostic panel was hiding its own error messages

- Fixed the audio diagnostic panel hiding its own error messages, especially on mobile where tooltips don't work.

## 0.5.0.w — 2026-08-17 — BUGFIX (chirp-server) — fixed 11 Rich/Soft themes that were secretly single-hue

- Fixed 11 themes that were secretly single-hue instead of matching their own stated color pairing.

## 0.5.0.v — 2026-08-17 — BUGFIX (chirp-server) — the fix for the iOS build,.js wasn't it either

- Fixed the iOS build again — capacitor.config.js wasn't reliably read either; switched to capacitor.config.json.

## 0.5.0.u — 2026-08-17 — BUGFIX (chirp-server) — fix for `npx cap add ios` failing to build

- Fixed `npx cap add ios` failing to build, by moving off capacitor.config.ts.

## 0.5.0.t — 2026-08-17 — BUGFIX (chirp-server) — low-contrast fixes, found from direct screenshots

- Fixed low-contrast notes/comments, and 12 hardcoded white-text instances illegible on light themes.

## 0.5.0.s — 2026-08-17 — BUGFIX (chirp-server) — chirp-launcher 403 Forbidden, root cause confirmed from nginx error logs

- Fixed chirp-launcher's 403 Forbidden error, caused by unreadable file permissions on a read-only mount.

## 0.5.0.r — 2026-08-15 — BUGFIX + FEATURE (chirp-server) — heatmap no longer reloads the whole page, column normalization added

- Fixed the heatmap's size toggle blanking the entire Statistics page, and added a third normalization mode.

## 0.5.0.p — 2026-08-15 — CHORE (chirp-server) — README logo and stale version fixes, reported with a screenshot

- Fixed the README's logo, stale version references, and Versioning section examples.

## 0.5.0.o — 2026-08-15 — FEATURE (chirp-server) — five new themes, full light-theme accessibility coverage

- Added 5 new themes (Dawn Chorus, Feather, Clay, Marsh, High Contrast Light), with full accessibility coverage.

## 0.5.0.n — 2026-08-15 — BUGFIX (chirp-server, chirp-device) — theme logo fixes, AudioMoth stall detection

- Fixed two theme logos, and a gap in AudioMoth's crash-recovery health check (a stalled-but-active stream).

## 0.5.0.m — 2026-08-15 — FEATURE + BUGFIX (chirp-server, chirp-server-instances) — push digest, bird profile fix, caching

- Fixed a dead-code bug blocking profiles from picking up new Cornell Lab content, added stats caching, and a push notification option for the daily digest.

## 0.5.0.l — 2026-08-14 — FEATURE + BUGFIX (chirp-server) — digest email photos, fixed washed-out rendering in iOS Mail

- Fixed the daily digest email looking washed-out in iOS Mail, and added bird photos to its species list.

## 0.5.0.k — 2026-08-14 — FEATURE + BUGFIX (chirp-server, chirp-server-instances) — heatmap normalization, chart label fixes, multi-instance auth + backup fixes

- Added heatmap normalization, fixed a chart label overlap, and fixed two chirp-server-instances auth/backup bugs.

## 0.5.0.j — 2026-08-14 — BUGFIX (chirp-server, chirp-server-instances) — crash loop fixed, logs confirmed the cause

- Fixed a crash loop from unwritable data directories; both containers now self-heal on startup.

## 0.5.0.i — 2026-08-14 — BUGFIX (chirp-server) — the missing notes gap fixed, versioning reverted to letter suffixes

- Fixed the missing notes gap (a different component than earlier fixes touched), and reverted version numbering to letter suffixes.

## 0.5.0.h — 2026-08-14 — BUGFIX (chirp-server) — chirp-launcher never started, root cause confirmed from logs

- Fixed chirp-launcher never starting, caused by a nested read-only mount conflict.

## 0.5.0.g — 2026-08-14 — CHORE (chirp-server) — Notes page gap increased further, deployment-verification note

- Increased the Notes page gap further after it was still reported not visible.

## 0.5.0.f — 2026-08-14 — CHORE (chirp-server, chirp-server-instances) — dedicated Cloudflare Tunnel removed, build gap fixed

- Removed the dedicated Cloudflare Tunnel container (one tunnel can serve multiple services), and fixed a chirp-server-instances build failure.

## 0.5.0.e — 2026-08-14 — BUGFIX (chirp-server) — Changelog page showing duplicate entries, found from a screenshot

- Fixed the Changelog page showing duplicate entries, and a stale version-scheme legend.

## 0.5.0.d — 2026-08-14 — CHORE (chirp-server) — What's New two-tier history, desktop screenshots, README version fix

- Redesigned What's New's history into two tiers, added desktop screenshots to the README, and fixed its stale version line.

## 0.5.0.c — 2026-08-13 — CHORE (chirp-server) — What's New popup content cleanup

- Trimmed What's New's history list, which had grown to 30+ entries.

## 0.5.0.b — 2026-08-13 — BUGFIX (chirp-server) — AI second opinion missing from the submission flow, deployment feedback

- Added an option to include the AI second opinion when submitting to iNaturalist.

## 0.5.0.a — 2026-08-13 — FEATURE + BUGFIX (chirp-server, chirp-device) — AudioMoth crash recovery, iNaturalist comments

- chirp-device: fixed AudioMoth crashes that required a full reboot to recover from.
- Built iNaturalist comment-posting; fixed notes always dropping the auto-generated summary when a user note was present. Fixed the Notes page's card spacing.

## 0.4.0.c4 — 2026-08-12 — FEATURE (chirp-server) — Cornell Lab / All About Birds integration

- Added a real, new enrichment source: Cornell Lab of Ornithology's All About Birds (allaboutbirds.org), fetched via the same Playwright-based Cloudflare bypass the existing range-map fetcher already used. Pulls Basic Description, all "Cool Facts," and Habitat/Food/Nesting/Behavior tags — real DOM structure confirmed by directly inspecting the live rendered page (not assumed), verified end-to-end against the actual site for multiple real species including a hyphenated one. Cornell Lab's own description is now preferred over Wikipedia's when successfully fetched, since it's curated specifically for bird identification/behavior — verified with a full real run of enrich_profile() showing Wikipedia populate first, then correctly get superseded.
- Found and fixed a real, previously-unfixed bug in the *existing* range-map fetcher while researching this: neither of its two URL slug variants ever preserved hyphens in species names, silently breaking lookups for a meaningful share of common bird names (most woodpeckers, several chickadees/kinglets/warblers) — confirmed live against the real site (Red-bellied Woodpecker, Gray-cheeked Thrush). Fixed with a shared slug helper, correct form tried first.
- New BirdProfile fields (aab_url, aab_description, aab_cool_facts, aab_habitat/food/nesting/behavior) with a real migration, wired into both the AI journal (Cool Facts now preferred over the generic description excerpt for journal grounding material, with random rotation across days) and the Bird Profile page (a new "Cool Facts & At-a-Glance" card).
- Two real bugs caught by testing actual live endpoints rather than trusting the code: the profile API has a manual field-mapping function (profile_to_out) separate from the Pydantic schema — new fields were in the schema but silently came back null until this function was also updated, the same bug class as last round's Depth-slider issue. Separately, the frontend hardcoded "Wikipedia CC BY-SA" as the attribution for every bird description — since Cornell Lab's is now frequently preferred, that label would have been actively wrong; fixed to reflect the real source dynamically. Both confirmed fixed with a real rendered screenshot of the live page, not just code review.

## 0.4.0.c3 — 2026-08-12 — FEATURE (chirp-server) — daily digest email: journal entry + real logo

- Added the real last Daily Journal entry (AppSettings.daily_summary_text — the same actual text shown in the app, not a separate re-generation) to the daily digest email, in a new "From your Daily Journal" section. Only shown if the entry was actually generated within the last 36 hours, so a stale multi-day-old entry (e.g. if journal generation broke) is never shown mislabeled as yesterday's — verified with a real test setting the timestamp to 48 hours old and confirming the section is correctly excluded, plus a second test confirming a fresh install with no journal text ever generated still sends the digest correctly with no error.
- Found and fixed a real branding inconsistency while investigating: every Chirp email (not just the digest) used a separate, hand-drawn inline SVG "bird icon" that never actually matched the real Chirp logo used everywhere else in the app (favicon, PWA icon). Replaced with the real logo, served as a hosted <img> pointing at /icon-192.png rather than more inline SVG — inline SVG has zero support in any version of Outlook and inconsistent support even in clients that partly handle it, while a plain hosted image works universally, including in clients that block remote images by default (real alt text covers that case). Falls back to the original inline SVG gracefully only in the rare case no server_url is available to build a real image URL from — verified with real tests for the URL-present case, the empty-server_url fallback case, and a trailing-slash edge case that could otherwise produce a malformed double-slash URL.
- Both verified end-to-end: real test data (an opted-in user, real recordings, a real journal entry) run through the actual send_daily_digest function with _send mocked to capture the real final HTML, not just testing the helper functions in isolation.

## 0.4.0.c2 — 2026-08-12 — FEATURE (chirp-server) — fifth AI personality slider, more journal content

- Added a fifth AI personality slider, Curiosity — a genuinely distinct axis from the existing four (WHY vs. WHAT, not tone/facts/humor/length). Low keeps entries to a grounded account of what happened; high actively explores real ecological/behavioral reasoning behind it, honestly framed as possibility rather than certainty. Unlike Depth, included even in brief mode (Bird Profile Summaries) since exploring a "why" doesn't need more room, just different content — verified with a dedicated test confirming exactly that distinction.
- Learned from the Depth persistence bug and proved it this time: before wiring anything into the journals, ran the structural consistency test built after that bug to confirm the new field was correctly added to all three required spots (AppSettings model, migration list, SettingsIn/SettingsOut schemas) before any further work. Verified end-to-end with a real PUT-then-fresh-GET cycle across the full 0-100 range.
- Added a new real enrichment source, taxonomic diversity — how many distinct bird families a day's or week's detections actually represent, using real eBird family/order data already present in RegionalSpecies but never surfaced anywhere before. Tested against known planted data (3 species, 2 families, correctly computed) plus two real edge cases: a single-family day correctly returns nothing rather than a trivial "diverse!" claim, and an empty detection set doesn't error.
- Both wired into real Daily and Weekly Journal prompts, verified together with a comprehensive end-to-end test capturing the actual final prompt text sent to the AI — confirmed curiosity, taxonomic diversity, time-of-day pattern, and sourced species facts all present and correct in the same real generation run, not just tested in isolation.

## 0.4.0.c1 — 2026-08-11 — BUGFIX (chirp-server) — Depth slider didn't persist, real deployment feedback

- Fixed a real bug: the Depth personality slider (added last round) could be moved and saved with no error, but the value silently reverted after reloading. Root cause: the field was added to the AppSettings model and its migration list, but never added to SettingsIn (the PUT /api/v1/settings request schema) or SettingsOut (the GET response schema) in app/api/app_settings.py — three separate places the previous round's edit missed entirely. Pydantic silently drops any field not defined on the model when parsing an incoming request, so the frontend correctly sent the value, the backend correctly received the HTTP request, and the value vanished before the database write loop ever saw it — no error anywhere in the whole path. Fixed by adding the field to all three places, verified with a real end-to-end test: PUT then a completely fresh GET request (not just trusting the PUT response echo) across the full 0-100 range, plus confirming the other three sliders remained unaffected.
- Extracted the migration-defaults list (previously a local variable inside _get_or_create) to a module-level constant, _MIGRATION_DEFAULTS, specifically to make it introspectable. Added a new structural consistency test (app/api/test_settings_field_consistency.py) that compares this list's field names against SettingsIn and SettingsOut's own field names — catching this entire bug class for any future field, not just this one. Verified the test actually works by temporarily reverting the fix and confirming it fails with a precise, correct error identifying the exact missing field, then confirming it passes again with the fix restored.

## 0.4.0.c0 — 2026-08-11 — FEATURE + BUGFIX (chirp-server) — richer AI journals, real gitignore bug

- Daily/Weekly Journal now draw on four real, computed data sources instead of relying on the model's own general knowledge: a real historical trend comparison (average species/detections over a trailing 4-period baseline, explicit period_length rather than inferred — a real bug caught by testing with actual checkable numbers: the original version inferred baseline period length from the current period's own start/end, which silently broke for Daily Journal specifically since "today so far" is a partial day), real Wikipedia-sourced species facts (BirdProfile.description, explicitly marked for paraphrasing not quoting), other species genuinely likely for the region/month that haven't been detected (reusing the exact regional-library monthly-likelihood logic, including its stale-cache-avoidance fix), and a real time-of-day activity pattern (which species were genuinely concentrated in the early-morning window today, computed from real timestamps). All four verified end-to-end by capturing the actual final prompt text sent to the AI, not just testing the data-gathering functions in isolation.
- Added a fourth AI personality slider, Depth — a genuinely different axis from the original three (actual entry length/room for teaching, not tone). Paragraph counts and token budgets were previously hardcoded regardless of any setting; now they respond to this slider, with the default (50) verified to reproduce the exact original hardcoded behavior. Extended personality.py's own real self-test suite (11 checks now, up from 5) rather than adding an untested parameter.
- Fixed a real, confirmed bug found from actual GitHub usage: .gitignore's blanket *.jpg/*.png/*.svg exclusion (meant to stop runtime-downloaded bird photos and user data from being committed) was also catching the intentional documentation screenshots referenced in README.md's own Screenshots section — those files exist in every local checkout but were never actually committed or pushed, so the README's <img> tags pointed to files that didn't exist in the real GitHub repo. Added an explicit !docs/screenshots/** carve-out, verified with a real git repository test (not just reading the gitignore rules back): confirmed a real screenshot file now gets staged by `git add`, and confirmed a real user-data photo elsewhere in the tree still correctly stays ignored.

## 0.4.0.bf — 2026-08-10 — FEATURE (chirp-server) — multi-instance launcher

- Added a real switcher/launcher page (chirp-launcher, port 8760) for the multi-instance approach — one place to see and reach every location, without merging any instance's actual codebase, database, or auth. A plain nginx container serving a static page that reads instances.json (name/port/optional public URL per instance), builds a correct link to each one (using an instance's own public Cloudflare Tunnel URL if set, otherwise constructed from the launcher's own hostname + that instance's port, so it works correctly whether accessed via localhost, LAN IP, or a domain), and does a real, best-effort health check against each instance's own /api/v1/health. scripts/new-instance.sh now registers every new instance in instances.json automatically.
- Verified with a real headless-browser test (Playwright), not just reading the code back: confirmed the link is constructed correctly, that a genuinely unreachable instance settles to an "offline" indicator rather than hanging or throwing, and — a real positive-case test, not just the failure path — that a genuinely reachable fake instance correctly shows "online." Caught and fixed a real typo along the way: two places referenced copy-instance-settings.sh (a shell script) when the actual file is copy-instance-settings.py (Python).
- Clarified in MULTI_INSTANCE.md that a real switcher page now exists — the actual remaining gap is single sign-on across instances (each instance still has its own separate login, by design, since the launcher has no access to any instance's actual user data), not "no way to switch at all."

## 0.4.0.be — 2026-08-10 — ARCHITECTURAL PIVOT

- Switched the recommended approach for multiple locations/tenants from a separate multi-tenant application (chirp-multi) to multiple independent instances of chirp-server itself — the real, complete, already-mature application, not a reimplementation of it. Prompted by a concrete, real finding: chirp-server's own regional species feature has a genuine fallback data source (geo/recent observations) for when eBird's bar-chart endpoint requires a login session it doesn't have; chirp-multi's port of that feature only implemented the bar-chart path, so it failed in the normal case for most tenants, not an edge case. That pattern (missing settings fields, no admin user list, a recurring favicon bug, dead AI personality settings) repeated enough times that switching approaches was the better fix.
- Generalized the existing docker-compose.instance-a/b/c.yml pattern into scripts/new-instance.sh — one command generates a new, fully independent chirp-server instance (own port, own container, own Cloudflare Tunnel) instead of hand-writing a new compose file per location. Tested for real: generated a real instance, confirmed valid YAML, and tested all four error-handling paths (duplicate name, invalid name, invalid port, wrong argument count).
- Added scripts/copy-instance-settings.py — copies only the genuinely shared AI/eBird credential fields from one instance's database to another's (never location, device keys, users, or anything else meant to stay per-instance), never overwriting a real destination value without --force. Verified end-to-end with two real chirp-server databases: real keys copied correctly, and a real existing destination value confirmed protected without --force.
- Added MULTI_INSTANCE.md — the complete guide for this approach, including the deferred (not built) work: a unified login/switcher and cross-location visibility, both explicitly out of scope until every instance's own core experience is solid.
- Ported the two real security gaps found during chirp-multi's own earlier audit work back into chirp-server, now that it's the sole product every location depends on: real in-memory login rate limiting (5 failed attempts / 5-minute window, keyed by username + IP together), verified with a real test — the correct password is blocked too after 5 failures, a different account is unaffected, and normal logins are never rate-limited. chirp-server's own upload size limit and backup safety were already correct (chirp-server was the actual original source those chirp-multi fixes were ported FROM), so no change was needed there.
- chirp-multi is marked deprecated with a clear, prominent notice at the top of its own ARCHITECTURE.md and in the main README — kept in the repo for reference and its own real, tested tenant-isolation work, not active development going forward.

## 0.4.0.bd — 2026-08-10 — FEATURE + DOCS (chirp-server, chirp-multi)

- Made Cloudflare Tunnel the default HTTPS approach for both projects, per direct request: no router port forwarding, no ports opened, home IP never directly exposed. chirp-multi's docker-compose.yml now starts its own Cloudflare Tunnel by default alongside the app itself; Caddy is still included as a documented alternative but gated behind a real Docker Compose profile (profiles: ["caddy"]) rather than just a comment — a plain `docker compose up -d` genuinely only starts the tunnel, not both. chirp-server gets its own separate tunnel (a distinct tunnel from chirp-multi's, pointed at localhost:8765 rather than a Docker service name, since chirp-server's own container uses network_mode: host and doesn't have its own private network identity) — chirp-server has no Caddy option at all anymore, since running Caddy for both projects on one host means fighting over port 80/443 regardless of which "wins." Removed the now-genuinely-orphaned chirp-server/Caddyfile. Added docs/CLOUDFLARE_TUNNEL.md — complete, real step-by-step setup instructions for both projects' tunnels, including why they're two separate tunnels rather than one shared tunnel with two hostnames.
- Fixed a real structural bug caught before it shipped: an earlier commented-out cloudflared service block in chirp-server's compose file wasn't actually correctly indented to nest under `services:` if simply uncommented — rewritten as a real, valid, working service definition instead.
- chirp-multi's push notification frontend, deferred from the previous round: a real service worker (ported from chirp-server's own push/notification-click handling), manifest.json for PWA install, a NotificationSettings.jsx component porting chirp-server's actual working subscribe/unsubscribe/test logic (adapted for chirp-multi's own flat subscription schema), the real PNG icons, and — since chirp-multi had been silently borrowing chirp-server's own VERSION file, contradicting this project's stated independence — a genuinely separate chirp-multi/VERSION file with its own service-worker version-stamping pipeline ported from chirp-server's. Verified with a real build: sw.js, manifest.json, and icon-192.png all confirmed served correctly, not swallowed by the SPA fallback.

## 0.4.0.bc — 2026-08-09 — BUGFIX (chirp-multi) — real deployment feedback

- Fixed a real bug from actual deployment, the first genuine post-deployment bug report this project got: root-level static files (favicon.svg, logo.svg) were returning index.html content instead of the actual file — a real 200 status, text/html content-type, no error to notice anywhere. Only /assets/ was ever mounted as a real static directory in main.py; anything else fell through to the SPA-fallback handler, which served index.html unconditionally for any non-API 404. A browser tab or Unraid's own docker-icon fetcher requesting favicon.svg silently got HTML back and rendered nothing — exactly the "?" placeholder icon actually observed. Fixed by checking for a real, existing file within the static directory first, with path-traversal protection, only falling back to index.html when no real file matches. Given its own permanent regression test.
- Fixed the actual Caddy port conflict causing both chirp-server's and chirp-multi's Caddy to crash-loop on "address already in use": removed Caddy from chirp-server's compose file entirely (chirp-multi's Caddy owns 80/443 now), then moved chirp-multi's Caddy off the host's 80/443 entirely (Unraid's own management interface already claims those) onto distinctive host ports 28080/28443, documented clearly for router port-forwarding.
- Fixed dead settings found from the same deployment feedback: the three AI personality sliders were defined on the model and exposed through the settings API, but nothing anywhere actually applied them when building an AI prompt. Wired into both Daily and Weekly Journal's real prompts, verified with a test that mocks call_ai and confirms the actual prompt text changes.
- Fixed a real, blocking gap: latitude/longitude had no UI path to set them at all, despite the backend already depending on them for Field Guide — added real fields to Settings.jsx, along with timezone.
- Fixed a real usability gap: the Admin page could create a tenant and a user, but had no way to see any tenant's own ID (blocking the "paste a tenant ID" field the user-creation form itself required) or see a list of existing users at all. Added a new admin-wide GET /api/v1/admin/users endpoint (admin-only, tenant names resolved), and rebuilt the Admin page to show tenant IDs with copy, list all users, and replace manual tenant-ID pasting with a dropdown.
- 30 tests total now, up from 27.

## 0.4.0.bb — 2026-08-09 — BUGFIX + FEATURE (all three projects)

- Added chirp-device's real device→server pipeline diagnostic: `--test-upload` sends one genuinely fake, clearly-labeled detection to every configured upload target using the exact same code path production uploads use, and reports success/failure per target with the real HTTP status/response. While building and verifying this against real running chirp-server and chirp-multi instances, found and fixed a real bug: `_warn_placeholders()` (config.py) only ever checked the legacy top-level `upload.server_url`/`api_key` fields — the DEFAULT_CONFIG's own placeholder defaults for those fields never get overridden when using the newer `upload.targets:` list format instead, so anyone who switched to multi-target config (without also redundantly setting the now-superseded legacy fields) hit a false-positive "still a placeholder" error and the device refused to start at all, for every run mode, not just uploads. Fixed to correctly validate each configured target's own fields when `targets:` is present, falling back to the legacy check only when it isn't.
- Restructured both chirp-server's and chirp-multi's docker-compose.yml for Unraid's Docker Compose Manager, which only ever loads the single file it's pointed at — Caddy (automatic HTTPS) was previously a separate docker-compose.caddy.yml overlay requiring a `-f -f` invocation Unraid's Compose Manager never performs, so it silently never saw the Caddy service at all. Merged into one file each (matching the Immich-style single-project convention), added a top-level `name:` field to each, and removed the now-redundant separate overlay files.
- chirp-multi's real React frontend now uses chirp-server's actual visual identity, not an approximation — the real logo/favicon SVG files copied directly from chirp-server, and the exact default-theme colors and fonts (Lora/DM Sans/JetBrains Mono) read directly from chirp-server's own CSS variables rather than eyeballed to "look similar."

## 0.4.0.ba — 2026-08-09 — BUGFIX (chirp-multi)

- Continued the production-readiness audit pass, found and fixed two more real gaps, both more consequential in a multi-tenant deployment than a single-household one. No upload size limit at all — any tenant's device (or anyone with a valid pairing key) could upload an arbitrarily large file and fill the entire shared data volume, affecting every other tenant. Fixed with a real, enforced 50MB limit, read in 1MB chunks with an early abort rather than reading the whole oversized payload before rejecting it, so the limit actually bounds what a single request can consume. No login rate limiting at all — unlimited password attempts against any account, defended only by bcrypt's own inherent slowness, not an actual defense against a sustained or distributed attempt. Fixed with real in-memory tracking (5 failed attempts / 5-minute window, keyed by username + IP together), matching this project's actual single-instance deployment model rather than building a distributed rate limiter it doesn't need.
- Both verified with real tests, not assumed: the upload test sends actual oversized bytes (not a header claiming a large size) and confirms no file is left behind on disk for the rejected upload; the login test makes real repeated wrong-password attempts, confirms the account locks out even for the correct password afterward, confirms a completely different account is unaffected, and confirms the lockout correctly clears. 27 tests total now, up from 25.

## 0.4.0.az — 2026-08-09 — BUGFIX + FEATURE (chirp-multi)

- Fixed a real data-integrity gap found during a production-readiness pass: chirp-multi's admin backup endpoint used a plain shutil.copy2() filesystem copy of the live SQLite database. SQLite's own documentation explicitly warns against this for a database that might be actively written to — a plain copy taken mid-write can capture a half-written page, producing a backup that looks completely fine until the moment you actually need to restore it and discover it's corrupt. Fixed by porting chirp-server's own already-correct approach (services/backup_service.py, using SQLite's real Connection.backup() API).
- The same pass found backups were entirely manual — the only way one ever happened was an admin remembering to click a button, no safety net if they forgot. Added a real scheduled daemon thread (ported from chirp-server's own pattern), running once a day at a configurable UTC hour, with real retention pruning. Manual and scheduled backups now share the identical safe code path and identical pruning logic.
- Verified with two real tests: the existing migration test extended to cover the three new GlobalSettings columns this needed (confirming real pre-existing API keys survive the migration untouched, not just structural columns), and a new dedicated test creating five genuinely distinct real backup files, pruning down to two, and confirming by actual filename — not just count — that the newest two were kept. 25 tests total now, up from 23.

## 0.4.0.ay — 2026-08-09 — AUDIT + FEATURE (all three projects)

- Systematic audit pass across chirp-server, chirp-device, and chirp-multi. chirp-server: checked all 9 API routers for the route-ordering bug class found earlier this project (a literal path shadowed by a same-shaped path parameter registered before it) — all clean once double-checked by actual segment count, not just registration order at a glance. Checked all 7 non-standard db.close() call sites for use-after-close risk — all safe. Found one real, if minor, fragility: app/api/auth.py imports bcrypt directly, but it was never declared as its own line in requirements.txt — it only arrived transitively via paramiko's own dependency chain. If paramiko were ever removed, authentication would have silently broken with no obvious cause. Fixed by declaring it explicitly. chirp-device: confirmed every optional dependency (batdetect2, paho-mqtt, rich, the pycoral/tflite-runtime/tensorflow fallback chain) is genuinely guarded with try/except, not just assumed to be.
- Added automatic HTTPS to both chirp-server and chirp-multi via an optional Caddy reverse proxy (docker-compose.caddy.yml + Caddyfile in each project) — a real, previously-undocumented gap: Web Push and PWA install both genuinely require real HTTPS to function at all (a hard browser restriction, not a hardening preference), and neither project had ever actually wired this in or stated the requirement anywhere, despite substantial push-notification work already existing in both.
- Added docs/MULTI_SERVER_DEVICE.md — a dedicated, complete walkthrough for sending one chirp-device's data to more than one server at once (the multi-target uploader feature built earlier this project), verified line-by-line against the actual code (exact log message formats, exact config field names) rather than written from memory.
- Optimized chirp-multi's frontend with real route-based code splitting (React.lazy/Suspense) — a real, measured problem, not hypothetical: the unsplit production build was ~487KB in one JS chunk, meaning the Login page (the first thing every unauthenticated visitor sees) was downloading the entire app's code, including the Devices page's own @xterm/xterm SSH terminal library, before a login form could render. After splitting: the shared bundle every page needs dropped to ~179KB, Login is its own ~1.3KB chunk, and the terminal-heavy Devices page is a separate ~295KB chunk that only loads when actually visited.

## 0.4.0.ax — 2026-08-08 — FEATURE (chirp-multi)

- Built a real React frontend for chirp-multi (Vite + React 18 + Tailwind + react-router-dom, matching chirp-server's own stack), replacing the earlier minimal static-HTML dashboard. Real pages: Login, Overview, Devices (mesh IP editing, pairing-key generation, a real SSH terminal using the actual @xterm/xterm npm package), Recordings, Journal, Field Guide, Settings, and Admin (tenant/user creation plus the full Global Settings form). A multi-stage Dockerfile builds the frontend and copies it into the backend image automatically.
- Four real bugs caught before this was called done: (1) the tenant-selection gate's first version locked a fresh admin out of the one page they'd need to create their first tenant — a genuine chicken-and-egg bug, caught before ever running it; (2) switched off the deprecated `xterm` package to `@xterm/xterm` before it became a legacy problem in a brand-new build; (3) `StaticFiles(html=True)` only serves index.html for `/` itself — confirmed with a real request that a hard refresh on `/devices` returned a genuine 404, which would have broken every page except the first one loaded, then found a SECOND bug in the fix for this: re-raising an exception from inside a Starlette exception handler produces an unhandled 500, not normal 404 formatting, confirmed with another real request before fixing that too; (4) mounting StaticFiles against a directory that doesn't exist raises at import time, meaning the whole app — API included — previously failed to even start on any checkout where the frontend hadn't been built yet, exactly the TestClient-based workflow this whole project has used for testing all session. Fixed to make the mount conditional with a clear log warning instead of a crash, confirmed by actually deleting the built frontend and checking the API still works.
- One known, accepted tradeoff noted directly rather than silently carried: react-router-dom's current stable line has two open security advisories that only a breaking v7 migration fixes. Neither's actual exploit path applies to this app (no untrusted-input-based navigation, no server-side rendering at all), and chirp-server's own production frontend carries the identical exposure at the same version — not a new regression.

## 0.4.0.aw — 2026-08-08 — AUDIT + BUGFIX (chirp-multi)

- With every planned chirp-multi feature now built, did a dedicated audit pass rather than moving straight to the next feature — systematically checked every router for the route-ordering bug class found earlier this project (a literal path registered after a same-shaped path parameter shadowing it), confirmed all `db.close()` calls in actual application code for use-after-close risk, and cross-checked every third-party import against requirements.txt. Found one real, genuine gap: chirp-multi had no database column-migration mechanism at all, unlike chirp-server's own established pattern. `Base.metadata.create_all()` only creates tables that don't exist yet — it does nothing for a new column added to an already-existing table's model, which is exactly what happened more than once as this project grew (Tenant.region_code, Device.mesh_ip, Device.ssh_username were all added to models that already existed). Any database created before those additions would have hit a real "no such column" SQL error the moment newer code tried to use one. Fixed by porting chirp-server's own migration approach. Verified with a real reproduction: built an actual old-schema SQLite database by hand with real data in it, ran the migration, and confirmed both that the missing columns got added and that the pre-existing data survived completely untouched, then ran it twice more to confirm it's genuinely safe to repeat. 24 tests total now (23 isolation tests plus this one, counted separately since it's a genuinely different kind of correctness check, not tenant isolation).

## 0.4.0.av — 2026-08-08 — FEATURE (chirp-multi)

- Added native iOS push (APNs) to chirp-multi, closing out the last major backend feature gap — ported from chirp-server's own real, working implementation (same JWT caching, same HTTP/2 send, same dead-token cleanup, including the specific redundant-query fix already found there, ported already correct rather than reintroducing it). Same shared-credential split proven for everything else in this project: one set of Apple Developer credentials for the whole deployment, but every registered device token belongs to exactly one tenant and a push only ever reaches that tenant's own devices — tested with the same rigor as Web Push, checking exactly which real device tokens got sent to, not just a count. Wired directly into the existing send_push_to_tenant function, so both mechanisms fire from the one call the new-species trigger already makes — no other code needed to change for native app users to start receiving push once APNs is configured. The ported JWT signing was verified with a real cryptography round-trip, not just a mocked assertion. 23 isolation tests now, up from 22.

## 0.4.0.au — 2026-08-08 — FEATURE (chirp-multi) + DOCS

- Finished the self-hosted remote-device mesh for chirp-multi — the real prerequisite flagged as missing last round: a tenant-scoped SSH terminal (WebSocket /api/v1/devices/{device_id}/ssh), ported from chirp-server's real, working paramiko-based bridge, with one deliberate improvement chirp-server's own version doesn't have — real authentication on the handshake itself, since chirp-server's endpoint takes only a device ID with no token check at all, tolerable for a single-household deployment but not here, where an admin reaching into a specific tenant's device is a more sensitive action. The handshake verifies a real admin JWT, an explicit tenant_id, and that the target device actually belongs to that exact tenant, all before the connection is accepted. The real tradeoff (the auth token travels in the WebSocket URL's query string, since browsers can't set custom WebSocket headers at all) is documented directly in docs/REMOTE_DEVICES.md rather than left implicit, along with the short-lived-ticket pattern that would harden it further. Added Device.mesh_ip/ssh_username and a manual mesh-IP recording endpoint, both wired into the dashboard with a real xterm.js terminal loaded from CDN. Two new isolation tests (22 total, up from 20): one exercising the SSH handshake's own rejection paths and confirming a genuinely correct request passes through to the real SSH-connect step, one for the mesh-IP endpoint's own admin-only, tenant-scoped behavior. Also fixed a real, pre-existing gap found while updating the docs: an earlier ARCHITECTURE.md paragraph was missing its own header line from an earlier edit, silently merging two unrelated sections into confusing, broken text.

## 0.4.0.at — 2026-08-08 — FEATURE (chirp-multi) + DOCS

- chirp-multi's migration tool can now copy the actual audio WAV files, not just database rows (--copy-audio --source-recordings-dir). Genuinely resumable — a real size check, not just a presence check, so a file left partially copied by an interrupted run gets correctly re-copied rather than treated as done. Checks real available disk space against the real total bytes needed before copying anything, aborting cleanly rather than filling the disk partway through a large recordings library. All three behaviors verified directly: a real copy with real files and byte-for-byte size verification at the destination, resumability confirmed by calling the copy step twice with an identical plan and checking the second run skips every file, and the disk-space abort confirmed by simulating a nearly-full disk and checking the file genuinely never gets created.
- docs/REMOTE_DEVICES.md extended with an honest section on chirp-multi: the self-hosted mesh itself works identically for chirp-multi's devices as chirp-server's, but chirp-multi has no admin diagnostics/SSH endpoint at all yet to actually use that reachability for — noted directly rather than implying the mesh alone makes remote device management available in chirp-multi today.

## 0.4.0.as — 2026-08-08 — FEATURE (chirp-multi)

- Added multi-provider AI support (OpenAI/Gemini/Ollama alongside Anthropic), Web Push notifications, and — the most significant find of this round — discovered and fixed a real gap where there was no way for an admin to actually configure GlobalSettings (the AI keys, eBird key, and push credentials every recent feature depends on) through the running application at all; every test in the project had been setting these directly in the database, which a real deployment obviously can't do. Added GET/PATCH /api/v1/admin/global-settings with the same secret-masking convention chirp-server's own settings endpoint uses, plus a real form in the dashboard's Admin tab. Push notifications are wired into an actual trigger, not left unused: uploading a recording now checks each detection against that tenant's own existing life list before inserting the new ones, and sends one push per upload for any genuinely new species, respecting each tenant's own notify_new_species preference — tested directly, including confirming a repeat detection of an already-known species does NOT re-trigger and that turning the preference off actually stops it. Multi-provider AI selection uses a simple fixed preference order (Anthropic > OpenAI > Gemini > Ollama, whichever has credentials set) for this delivery, ported faithfully from chirp-server's own already-debugged request handling for each provider, including a real previously-found Ollama-specific token-budget issue carried over rather than rediscovered. 20 real isolation tests now, up from 16, including the two real bugs caught and fixed while writing them this round (a chained-comparison mistake in a test's mock, and a test-isolation gap where an earlier test's leftover database state broke a later test's assumption of a clean slate).

## 0.4.0.ar — 2026-08-07 — FEATURE (chirp-multi)

- Added Field Guide to chirp-multi — real eBird integration, ported faithfully from chirp-server's own ebird_service.py (region resolution via Nominatim reverse geocoding, bar-chart fetching with real redirect-detection for eBird's session-required endpoint, TSV parsing — genuinely tricky, previously-debugged logic carried over rather than reinvented, and re-verified with a real live call against Nominatim, not just mocked tests). Proves the design point flagged in ARCHITECTURE.md before this endpoint even existed: the eBird API key is shared (one central key, admin-configured), but every actual query resolves and uses each tenant's own latitude/longitude — two tenants in different states get genuinely different regions and species lists from the same key, tested with real, different coordinates (Natick, MA vs. Portland, OR) checked by both the resolved region code and the resulting species list, not just a status code. The resolved region is cached on the tenant's own row (so a real Nominatim + eBird round-trip doesn't happen on every request) and explicitly invalidated whenever a tenant's location changes, so a moved tenant doesn't keep seeing their old region's species. Also added to the dashboard.

## 0.4.0.aq — 2026-08-07 — FEATURE (chirp-multi)

- Added Weekly Journal to chirp-multi, completing the journal pair alongside Daily. Always a genuinely fixed 7-day window — checked directly in its own test by inspecting the actual source, not just trusted from a docstring, carrying over an explicit requirement from chirp-server's own Weekly Journal build earlier in this project. Grounded in real per-tenant arrival/departure data via a new tenant-scoped port of chirp-server's wildlife_patterns.py logic (a species genuinely new this week, one returning after an absence, or one that had been regular but's gone quiet — computed from actual detection history, not invented). A real bug found and fixed while testing this: the endpoint originally short-circuited to a generic "nothing detected" response whenever there were zero raw detections in the current week — but a departure is specifically *defined* by absence during the current period, meaning a silent week is exactly the case where the single most informative pattern (a previously-regular species going completely quiet) is most likely to exist, and the early return was skipping that analysis entirely. Caught by a test that specifically constructed that exact scenario. Also added to the dashboard, loaded independently from Daily Journal so one failing to generate never blocks the other.

## 0.4.0.ap — 2026-08-07 — FEATURE (chirp-multi)

- Added a real, working dashboard to chirp-multi (`app/static/index.html`) — until now the multi-tenant variant had 25 working API endpoints and zero way to actually see any of it without raw `curl` calls. A single static file, no build step, served directly by FastAPI (mounted after every API router specifically so it can never shadow a real endpoint — verified directly, not assumed). Covers login, an admin tenant-picker (enforcing the same "no implicit default scope" rule server-side already requires, not just a UI nicety), overview stats, devices and pairing-key generation, recent recordings, the daily journal, tenant settings, data export, and tenant/user creation for admins. Verified with a full simulated user journey exercising every one of the dashboard's actual JS calls against the real running API — login through tenant creation, acting as that tenant, and checking every tab's data — not just that the page loads.

## 0.4.0.ao — 2026-08-06 — FEATURE (device)

- `chirp-device` can now send each recording to more than one server — e.g. your normal chirp-server plus a chirp-multi instance for parallel testing, from the same physical device, since a microphone can only be claimed by one service at a time. Each configured target speaks its own protocol (chirp-server's direct API-key header vs. chirp-multi's pair-once-then-cache-device_id flow), gets its own queue/thread/retry state, and the existing single-target config keeps working completely unchanged — verified directly, not just assumed. Two real bugs found and fixed while building and testing this: (1) a genuine race condition where a fast primary target's success-triggered file deletion could delete a recording before a slower secondary target's thread had even picked it up — reproduced in roughly half of repeated real test runs before the fix (moving the file read to the dispatch point, before any target's queue has the item at all, rather than a first attempt that read per-target at dequeue time and still wasn't early enough), zero failures in 10+ repeated runs after; (2) a pre-existing bug inherited from the original single-target uploader, not introduced by this refactor — the retry-interval timer initialized to `0.0` against `time.monotonic()`'s absolute (not relative-to-start) clock, causing the retry check to fire almost immediately on startup instead of waiting the configured interval. Real test suite included (`chirp-device/tests/test_multi_target_upload.py`), covering backward compatibility, true failure isolation, and the chirp-multi pairing/caching flow.

## 0.4.0.an — 2026-08-02 — BUGFIX

- Fixed the Bat Activity "By hour of night" and "Nights active" charts using the raw stored UTC hour/date instead of converting to the configured local timezone first — the exact bug pattern that made the peak look like it landed at midnight-2am with total silence from 9am-9pm, instead of the real ~8-10pm dusk-emergence timing any actual bat activity should show. The same fix was already applied to the bird-detection hour-of-day chart elsewhere in this file at some point; this bat-specific endpoint was simply never updated to match. Verified with a real test: a bat recorded at 01:00 UTC (which is 21:00/9pm EDT the previous evening) now correctly shows up in the 9pm bucket on the correct local calendar night, not silently mislabeled as 1am on the wrong day.

## 0.4.0.al — 2026-08-01 — ENHANCEMENT

- Tutorial page redesigned to be more animated and easier to digest. Root cause of "not animated enough" found before changing anything: every section's entrance animation fired together within the first ~400ms of page load (a small mount-time stagger), so by the time someone actually scrolled down to section 6, 7, 8, or 9, that section's animation had already finished long before it became visible — the rest of the (long, 9-section) page was completely static while scrolling. Replaced with a real scroll-triggered reveal system (IntersectionObserver-based, respects prefers-reduced-motion) so every section — and the three main interactive demos specifically — animates in fresh as it's actually scrolled into view, not just once at the top. Each section also now has a one-line summary so the topic is scannable before committing to reading the full section, and a "9 sections · ~5 min read" line at the top for orientation before diving in.
- Fixed a real redundant-query pattern in the new APNs push code, found during a fresh optimization pass: `send_apns_to_all` looped over every registered device and re-fetched the single-row `AppSettings` table AND re-fetched that exact device's own row (just to update a timestamp) on every single iteration — a batch of N devices meant N+1 AppSettings queries and N redundant device-row re-fetches for what's fundamentally a handful of already-known rows. Fixed by passing both through from the caller, which already has them. Verified with a real, measured test: a 3-device batch now does exactly 1 AppSettings query and 1 device-token query, down from 4 and 4 — confirmed the actual behavior (timestamps still updating correctly) is unchanged, not just that the query count dropped.

## 0.4.0.ak — 2026-08-01 — FEATURE (server + iOS) + DOCS

- Built real native iOS push notifications (APNs) from scratch — previously the native registration code existed in `native/index.js` but was never actually called from anywhere in the app, and the server had zero APNs handling at all (only Web Push for the browser/PWA). Now: a new `ApnsDeviceToken` model, real JWT-authenticated HTTP/2 sends to Apple's actual API, dead-token cleanup, and a new Settings section for the four Apple credentials (Team ID, Key ID, Bundle ID, .p8 auth key). `send_push_to_all` now reaches both Web Push and native subscribers from one call, so the existing new-bird-detected trigger covers native users automatically. Verified with 5 real tests: JWT caching, independently-verified JWT validity, exact APNs request-shape correctness, dead-token removal, and safe no-op when unconfigured. One real mistake caught mid-session: adding the new model accidentally deleted the `AppSettings` class declaration entirely (a `str_replace` boundary error) — passed a plain syntax check but broke on actual import; caught by testing the real import, not just trusting the syntax check.
- `IOS_BUILD.md` rewritten to directly confirm what was previously implicit: the iOS app loads the live server URL as its primary content (not a bundled copy), so most web-content changes need zero iOS rebuild at all — only genuinely native changes (new plugins, entitlements, icons) do. Added a real Push Notifications setup section (Xcode capability, generating Apple's .p8 key, configuring Chirp's own Settings) and corrected a stale claim in the features table that push was already fully working when it wasn't. Caught and fixed one real inaccuracy in this doc while writing it — cited the wrong Capacitor config field name before checking the actual file.
- What's New popup now links to the Tutorial page alongside the existing Changelog link.

## 0.4.0.aj — 2026-08-01 — ENHANCEMENT

- Journal card is now collapsible as a whole (persists across visits, same as every other Dashboard section) — previously it was always fully expanded with no way to collapse it, unlike Daily/Weekly Journal's own sub-card preview/expand toggle (which intentionally still resets every page load).
- Daily/Weekly Journal's date/time subheading restyled to read as an actual subheader — was small, easy-to-miss gray text starting with the word "Written"; now a clearer medium-weight line with a small clock icon, and Daily Journal's timestamp includes the weekday for easier scanning.

## 0.4.0.ai — 2026-08-01 — FEATURE (server)

- Added optional web search grounding for Daily/Weekly Journal (Settings → AI Features), off by default. Deliberately does NOT use any AI provider's own built-in search tool — an earlier version of this feature was built against Anthropic's server-executed web_search tool specifically, then reverted in the same session in favor of this: Chirp's own server runs the search directly (Wikipedia's search API for migration/species facts, Google News' RSS feed for recent news — both real, currently-working, key-free sources, confirmed against the live endpoints before building rather than assumed), so it works identically regardless of which provider is assigned, with no AI vendor involved in the search itself. Two other free approaches were tried and rejected with real evidence, not guessed at: DuckDuckGo's HTML search returns an anti-bot challenge page immediately on a real request; its Instant Answer JSON API returns empty placeholder content for this kind of general query (it's built for narrow single-fact lookups, not general search). Verified with both mocked-response tests (real parsing logic, real error handling) and a live end-to-end call against the actual internet. Search results are inserted into the prompt as plain grounded context Chirp already fetched — the AI is instructed to use them if relevant and never present a result as something it already knew, same anti-hallucination principle as every other fact fed into these prompts.
- Confirmed and hardened: Weekly Journal's lookback window is a fixed 7 days, always — not a configurable parameter that could drift.

## 0.4.0.ah — 2026-08-01 — FEATURE (server) + ENHANCEMENT

- Added Weekly Journal — a week-in-review counterpart to Daily Journal, independently scheduled (default Sunday 7am, configurable day + hour) and independently regenerable. Covers the trailing 7 days rather than "so far today," and includes real arrival/departure data: species genuinely new (first-ever), species returning after an absence, and species that had been regular but went quiet this week — computed from actual detection history (new `wildlife_patterns.py`, gated on distinct-day "regular presence" so a species missed by chance for one day doesn't get falsely flagged as a departure), not invented by the AI. Verified with a constructed timeline covering all three cases plus a negative control (a one-off species correctly NOT flagged as a departure).
- Both Daily and Weekly Journal now lean harder into real educational content — explaining a migration/foraging term in passing when one comes up naturally, or a genuine verifiable fun fact — on top of the existing personality and accuracy guardrails. Note on scope: this pulls from the AI's own training knowledge and Chirp's real detection data, not live web search — actual live search/migration-tracking integration is a separate, real architectural decision (multi-provider tool-use, cost, latency, new failure modes) rather than something to bolt on as part of a prompt change, and wasn't attempted here.
- Dashboard's Journal card restructured into two independent, always-collapsed-on-load sub-cards (Daily, Weekly) — unlike other collapsible cards in the app, these intentionally don't persist expand state across page loads. "Collapsed" now shows a real multi-line preview (not just a hidden title) with a Read more/Show less toggle that only appears when the text actually overflows the preview, each with its own subheading (exact write time for Daily, the real date range covered for Weekly) and its own regenerate button.
- Two optimization passes made before packaging: `wildlife_patterns.py`'s "has this species ever been seen before" check was scanning the entire historical detection table with no lower bound on every single run — bounded to 3 years (practically equivalent to "ever" for this use case) so it benefits from the existing index instead of a full scan. Also eliminated a redundant duplicate AppSettings query in both Daily and Weekly Journal's generation functions (the caller already had the row; the data-gathering function was fetching it again).

## 0.4.0.ag — 2026-08-01 — ENHANCEMENT (device) + INVESTIGATION

- The bat detector's actual currently-streaming sample rate (as reported by the AudioMoth itself over USB, not an assumed/configured value) is now visible directly in Settings → Devices, instead of requiring the separate AudioMoth USB Microphone App or SSH access to check. Added specifically for the ongoing bat/AudioMoth wobble investigation — the AudioMoth's own official support forum and BTO (British Trust for Ornithology)'s Acoustic Pipeline documentation both independently point to sample-rate-dependent self-noise/aliasing as a known, documented AudioMoth behavior (not unique to this deployment), with 384kHz recommended over lower rates specifically to avoid it. Verified against a real (mocked) status call, not just that the code reads plausibly.

## 0.4.0.af — 2026-08-01 — BUGFIX + PERFORMANCE

- Fixed a real device-security gap: unpairing a device only deleted its Device row, leaving the corresponding API key untouched in AppSettings.device_api_keys. Since pairing looks up an existing device by matching that same key, a Pi that still had its old key cached locally would silently recreate its Device row on its very next pairing attempt (a heartbeat retry, a reboot) — completely undoing the unpair without anyone knowing. Unpairing now genuinely revokes the key. Verified with a real test: paired a device, unpaired it, then confirmed the old key is actually rejected — not just that the Device row was gone.
- Fixed vendor-charts (Recharts, ~86KB gzipped) being eagerly preloaded on every single page load via Vite's default modulePreload behavior, even though only Dashboard and Statistics actually use it. Confirmed directly in a real production build's index.html before and after. Every other page (Recordings, Settings, BirdProfile, etc.) no longer fetches/parses a charting library it never uses.
- Did a full audit pass looking for backend query inefficiencies (N+1 patterns, missing indexes) — found two loop-based query candidates, both false positives on inspection (dominated by external API/SSH calls, not DB query count) and confirmed the existing query layer already has real optimization in place (eager loading, batch-fetched relationship maps, a statistics cache) from earlier work. Reporting no issues found is itself the honest result here, not a reason to invent unnecessary changes.

## 0.4.0.ad — 2026-08-01 — FEATURE (server) + CLEANUP

- Added AI personality sliders (Settings → AI Features): Friendliness, Informational, and Irreverence, applying to Daily Journal and Bird Profile Summaries. Deliberately excluded from Call Re-analysis — that's a technical accuracy judgment, not creative writing, and dialing in "irreverence" has no place there. Default slider positions are calibrated to reproduce the same tone the hardcoded prompts used before these sliders existed — moving a slider is what changes anything, not the mere presence of the feature. Verified with two levels of real testing: a deterministic self-test of the band-selection logic (default values land in the expected band, boundaries behave correctly, extreme settings produce genuinely distinct text), and a real integration test mocking the AI call to confirm the actual system prompts sent by `daily_summary.py` and `profile_summary.py` reflect the configured slider values — not just that the prompt-building code looks right in isolation. Actual tone-shift validation still requires generating real output against a live provider, which needs an API key this environment doesn't have — noted rather than glossed over.
- Rewrote the What's New popup, which had accumulated into one long, undifferentiated scroll of every change across this whole session (15 sections in a single flat list). Now shows only the current version's changes in full, a collapsed one-line-per-version "Previously" summary for historical context, and a link to the full Changelog page — the popup announces what's new right now, it isn't a second copy of the changelog.
- Diagnostics page's mode-selector buttons (Full Report / Database Only / Microphone Check) get tactile press feedback, matching the rest of the app.

## 0.4.0.ac — 2026-08-01 — FEATURE (server)

- Added automatic database backups (Settings → Storage & Data), on by default — unlike most scheduled features in this file, which default off since they cost real money/compute per run; a SQLite backup is cheap and is a pure safety net. Runs once a day at a configurable local hour, keeps a configurable rolling window (default 14) of recent backups, and prunes older ones automatically. New Settings UI lists past backups with per-backup download/restore. Scoped to the database only, not recordings/media — that's a much larger, separate job better handled by existing Unraid-level backup tooling, not something for Chirp itself to reimplement. Verified with a real end-to-end test: created a real SQLite file, backed it up, confirmed the backup's actual queried content matches, then tested retention pruning correctly keeps the newest N and discards the rest — not just that files existed.

## 0.4.0.ab — 2026-07-31 — BUGFIX (critical) + ENHANCEMENT

- eBird export actually fixed this time — two earlier attempts (0.4.0.x included) each got the schema wrong differently. Root cause confirmed by diffing against a file someone else had manually fixed and successfully imported: Scientific Name needs two separate columns (Genus, Species), not one; State/Province is a bare code ("MA" not "US-MA"); Protocol is capitalized; "All Obs Reported" is "N" not "0". Verified byte-for-byte against the working file.
- Bats excluded from the eBird export — eBird's taxonomy is birds-only, so a bat submission there gets silently dropped or mismatched. Chirp's own Life List still shows bats normally.
- Extended the tactile press-feedback pass to BirdProfile.jsx and the Notes page, plus the shared UnifiedCard component's toggle headers — propagates to every page that uses collapsible cards (Settings, Statistics, My Profile), not just one.

## 0.4.0.aa — 2026-07-31 — CLEANUP + DOCS

- Fresh audit pass (AUDIT_REPORT.md) — 6 new findings from this session's own work, 3 patterns reviewed and confirmed safe (SQL identifier interpolation, dangerouslySetInnerHTML, cache-path construction).
- Tutorial updated for Experimental Features, AI Features, Bat Echolocation Detection, AI presence summaries, and eBird export format.
- Statistics page's metric toggle switched to the shared `.seg-btn` tactile class.

## 0.4.0.z — 2026-07-31 — FEATURE (server)

- Scheduled auto-refresh for Bird Profile presence summaries (Settings → AI Features), off by default — previously a summary only ever generated once, on first view. Configurable staleness threshold and check hour, capped per run to avoid a burst of AI calls on a large life list.

## 0.4.0.y — 2026-07-31 — BUGFIX

- Fixed Daily Journal / Bird Profile Summaries getting cut off mid-sentence with thinking-capable Ollama models (e.g. Gemma 4) — hidden reasoning was consuming the token budget meant for the visible answer. Ollama-routed calls now get a much larger budget instead of disabling thinking.
- Added "Experimental Features" to the Settings section jump-to menu — it existed on the page but wasn't listed.
- Fixed the floating Save button rendering behind the mobile bottom tab bar, invisible/unclickable on phones.

## 0.4.0.x — 2026-07-31 — BUGFIX

- Fixed eBird export rejecting every row ("Location name required") by moving it to column 6 — later found to be an incomplete fix, see 0.4.0.ab for the real root cause.
- Fixed the Life List Download dropdown rendering off-screen to the left on mobile.

## 0.4.0.w — 2026-07-30 — BUGFIX

- Fixed Ollama-backed AI features silently failing with slower local models — a flat 30-second timeout meant for hosted APIs was killing local Ollama requests mid-generation. Ollama now gets 180s.

## 0.4.0.v — 2026-07-29 — CLEANUP + TESTING

- Tested wobble removal against a real bat recording — ~11dB real-world reduction vs. ~24dB on the earlier synthetic test. Docs and Settings UI updated to report the honest number.
- Continued the ongoing comment cleanup pass (recordings.py, api.js, BirdProfile.jsx).

## 0.4.0.u — 2026-07-29 — FEATURE (server)

- De-wobbled and Enhanced bat-audio toggles made independently combinable instead of mutually exclusive, via a new chained `/audio/dewobbled-enhanced` endpoint.

## 0.4.0.t — 2026-07-29 — BUGFIX (critical)

- Fixed a critical regression: Statistics page returning HTTP 500 on every load, from a line accidentally deleted while fixing an unrelated import earlier in the same session. Caught immediately from a live screenshot.

## 0.4.0.s — 2026-07-29 — ENHANCEMENT

- Daily Journal given more personality — wit, vivid language, new focus angles and opening styles, layered on top of the existing accuracy safeguards.

## 0.4.0.r — 2026-07-29 — FEATURE (server) + BUGFIX

- Added experimental, off-by-default wobble-removal audio cleanup for bat recordings (`AudioProcessor.remove_bat_wobble`), with a manual "De-wobbled" player toggle and an auto-pregeneration setting.
- Fixed a real bug found via synthetic-signal testing: the original STFT window was too long relative to the interference tone's own wobble period, limiting real attenuation to under 5dB against a 25dB target. Fixed by shrinking the window — retested at ~24dB.

## 0.4.0.q — 2026-07-29 — CLEANUP

- Removed the yellow "Testing/Beta/Experimental" badges from experimental section headers — titles only now, description shown on expand.

## 0.4.0.p — 2026-07-29 — BUGFIX

- Fixed comments on a hard-deleted (not just soft-deleted) recording still appearing in the Notes page and comment count — the exclusion filter's NULL-handling let them through. Verified with a real SQLite test of all four cases.

## 0.4.0.o — 2026-07-29 — BUGFIX

- Fixed Life List medal badges always tinting whichever species landed in display positions 1-3 for the current sort, rather than the actual top-3 by detection count.

## 0.4.0.n — 2026-07-29 — CLEANUP

- Removed the Dashboard's "Today's Rarest Sighting" card — its bird-profile link went to a blank page in some cases.

## 0.4.0.m — 2026-07-29 — CLEANUP (partial)

- Comment cleanup pass, continued — several files still not fully swept.

## 0.4.0.l — 2026-07-29 — BUGFIX (device)

- Fixed a numpy crash in the bat ambient-diagnostic capture tool (tuple-unpacking bug); bumped a silently-swallowed error log to a visible level; added a startup log of the resolved events directory.

## 0.4.0.k — 2026-07-29 — ENHANCEMENT (device)

- Local bat-event snippet files now auto-delete after a confirmed successful server upload (opt-out via `keep_local_snippets`) — previously accumulated on the device indefinitely.

## 0.4.0.j — 2026-07-29 — FEATURE (device)

- Added an on-demand ambient-audio diagnostic capture to the bat detector, for the AudioMoth/fan interference investigation — triggered by a sentinel file rather than a competing process, since the detector holds the mic device exclusively.

## 0.4.0.i — 2026-07-29 — ENHANCEMENT

- Field Guide: likelihood-colored accent stripes on species cards; tactile press on filter buttons.

## 0.4.0.h — 2026-07-29 — ENHANCEMENT

- Life List: gold/silver/bronze badges for top-3 species; tactile press on filter/sort pills.

## 0.4.0.g — 2026-07-29 — CLEANUP

- Recordings: replaced JS-driven row-hover styling with a proper CSS class (adds touch feedback for free); grid/list toggle uses the new shared `.seg-btn`.

## 0.4.0.f — 2026-07-29 — ENHANCEMENT

- Dashboard stat tiles get a colored hover-underline accent, matched to each card's tint.

## 0.4.0.e — 2026-07-29 — ENHANCEMENT

- Tactile press-state overhaul across every button variant (primary/secondary/ghost/danger/icon) — raised look at rest, hover lift, real depress on click. New shared `.seg-btn` and `.tactile-press` utility classes.

## 0.4.0.d — 2026-07-13 — ENHANCEMENT

- Added a build-time check enforcing that the What's New popup's version always matches the canonical VERSION file — extends the existing stamp-sw-version.mjs script (which already keeps sw.js and package.json in sync) rather than a separate mechanism. Verified it actually fails the build when out of sync and passes once corrected, with real tests of both directions, not just one.

## 0.4.0.c — 2026-07-13 — FEATURE (device + server)

- Added a "Bat Activity" section to the Statistics page — nightly activity, hour-of-night distribution, peak-frequency spread, and species breakdown. This was a genuine gap: despite all the bat detection work this session, the stats page had zero bat-specific content. Caught and fixed a real bug in the first draft — assumed a distinct source marker existed for classified species when there isn't one; the same Detection row just gets updated in place from the generic "Bat" default.
- Added a search box to the Settings page, above the existing jump-to-section dropdown — searches the page's own rendered labels directly rather than maintaining a separate index, scrolls to and briefly highlights the first match.
- Added a "Today's Highlight" callout to the top of the Dashboard — a lifetime-first sighting takes priority over a merely-rare one. Purely additive: no reordering or removal of anything else, reuses data the Dashboard already fetches, renders nothing on a quiet day.
- Surfaced the bat detector's heartbeat (added last version, previously only visible in device logs) in the server-side Diagnostics view — signal level, active-hours state, running pulse/event counts, flagged as stale if not updated recently. Required wiring a status getter through from BatDetector up through the device's heartbeat reporting to the server, using the same "watcher not yet assigned during startup" safety pattern already established for config updates. Verified the full path end-to-end with a real test.

## 0.4.0.b — 2026-07-13 — BUGFIX

- Fixed the progress/played-region display looking wrong after toggling "Enhanced" on a time-expanded bat recording. The resume-position logic restored an absolute time in seconds from the original clip onto the enhanced clip — a genuinely different total duration — landing at the wrong relative position instead of preserving where playback actually was. Now stores a fraction of duration instead, and syncs duration state at the moment it's actually known for whichever source just loaded.
- Analyzed a real bat recording showing persistent sinusoidal noise: the tone genuinely wobbles between roughly 550-1800Hz (not a fixed frequency, confirmed by direct measurement), with a smeared harmonic consistent with the fundamental wobbling too. The actual bat call spikes reach ~23.5kHz with irregular timing, well outside this band — likely genuine bat activity, separate from the noise. The wobble rate is consistent with a small cooling fan's blade-pass frequency at a plausible RPM, which would explain both the non-fixed frequency (fan speed varies with temperature) and the harmonic content (mechanical/PWM sources are harmonic-rich) — an acoustic/mechanical source wouldn't be helped by grounding, which addresses electrical coupling, not vibration picked up directly by the microphone.

## 0.4.0.a — 2026-07-13 — FEATURE (device + server + iOS)

- Bluetooth-based first-time device setup for a Pi with no network connection yet — provisions WiFi over BLE before anything else can reach it. Pi checks connectivity on startup; if offline, advertises a "Chirp Setup" BLE service (via bluezero) exposing nearby networks, accepting credentials, and reporting status. Uses nmcli/NetworkManager (the current standard on Raspberry Pi OS Bookworm+, replacing wpa_supplicant). App side is native iOS/Android only (Web Bluetooth isn't available in Safari) via @capacitor-community/bluetooth-le.
- **Not yet validated against real Bluetooth hardware** — built against both libraries' documented APIs, needs real-device testing.
- iOS requires `NSBluetoothAlwaysUsageDescription` added manually to Info.plist or the app crashes on first BLE use — documented in IOS_BUILD.md and build-ios.sh. Doesn't survive re-adding the iOS platform from scratch.

## 0.3.0.w — 2026-07-13 — BUGFIX (device + server)

- `bat_min_swept_fraction` / `bat_max_pulse_rate` were configurable in Settings but never actually included in the config pushed to the device — it always ran on its own hardcoded defaults regardless of what was set in the UI.
- Added an opt-in toggle (off by default) to discard events flagged as likely electrical/mechanical interference outright, instead of only flagging them. Flagging alone never removed anything from a saved recording.

## 0.3.0.v — 2026-07-13 — ENHANCEMENT

- Fixed the black-screen hang on mobile load — `index.html`'s `<div id="root">` was empty with no background color set until the stylesheet loaded, so a slow connection showed a blank/white flash. Added an inline, zero-dependency splash screen plus a safe dark background and synchronous theme application before first paint.
- Audited the rest of the loading path: gzip compression, long-term asset caching, route-based code-splitting, and parallel Dashboard data fetching were all already correctly optimized — no changes needed.

## 0.3.0.u — 2026-07-13 — ENHANCEMENT

- Added real variety to the Daily Journal across entries. Each generation now randomly picks a distinct focus angle (fun fact, weather, rarest species, diversity reflection, seasonal comparison, narrative account) and opening style, and is shown the last several entries' openings with an explicit instruction not to repeat them.

## 0.3.0.t — 2026-07-13 — ENHANCEMENT

- Made the Daily Journal time-of-day aware — early morning talks about the day so far, midday recaps the morning while looking ahead, afternoon leans retrospective, evening reads as a full day-in-retrospect.
- Fixed the Notes/Comments page showing comments attached to a since-deleted recording. A comment row isn't cascade-deleted when its recording is soft-deleted; this exclusion existed elsewhere in the codebase but not on the actual comments listing used by the Notes page and Dashboard card.

## 0.3.0.s — 2026-07-13 — BUGFIX

- Fixed the Changelog page showing entries out of order. Two different entries had both been mistakenly labeled "0.3.0.i" at different points; removed the stray one (its content was already covered by 0.3.0.j).

## 0.3.0.r — 2026-07-13 — BUGFIX

- Fixed `/sw.js` serving a stale build after deploy — it had no explicit Cache-Control header, so it fell back to whatever caching policy sits in front of the server (Cloudflare). Service workers are the entire update mechanism for a PWA; now set to no-cache, must-revalidate.
- Cleaned up the Experimental Features cards' chevron alignment (was centered against the whole multi-line card instead of the title). Cards now default to collapsed and persist state across visits.

## 0.3.0.q — 2026-07-13 — BUGFIX (device + server)

- **Device**: added a periodic heartbeat to the bat detector — signal level, active-hours state, and running pulse/event counts, roughly once a minute regardless of whether anything triggers. Previously logged nothing between startup and a fired event, making a silently-stalled AudioMoth stream indistinguishable from "no bats present."
- **Server**: fixed auto-purge never applying to zero-detection Bird Buddy imports — they go through a different code path than device uploads that never had the equivalent logic.
- **Server**: cleaned up the Experimental Features section header.

## 0.3.0.p — 2026-07-13 — BUGFIX

- `auto_purge_empty_recordings` applied to device uploads but not Bird Buddy imports, which route through a separate function. Fixed, scoped specifically to Bird Buddy imports — a genuine manual upload via the Upload button is left alone even with zero detections.

## 0.3.0.o — 2026-07-13 — BUGFIX

- Fixed a push notification failure: Apple's web push gateway (web.push.apple.com) rejected the VAPID JWT because the "sub" claim was a fake placeholder domain rather than a real one. Now derives it from the actual configured server URL.
- Fixed a logging gap — the response body from a failed push was never captured, only the generic exception text.

## 0.3.0.n — 2026-07-13 — ENHANCEMENT

- Fixed push notification test failures showing only a generic "Send failed" message — the real error was logged server-side but never surfaced to the API response.
- Updated the Daily Journal's AI prompt: Chirp is a microphone system only, not a feeder or birdhouse. No longer assumes yard features the person may not have; can offer attracting/housing tips as suggestions and reflect on diversity/environmental health grounded in real detections.

## 0.3.0.m — 2026-07-13 — CRITICAL FIX

- Fixed scheduled iNaturalist auto-refresh silently never running — it targeted "the first admin account created" with no regard for whether that account had any iNaturalist credentials. A credential-less seed admin was being selected over the real configured admin. Now prefers whichever admin actually has credentials set.

## 0.3.0.l — 2026-07-13 — CRITICAL FIX

- Fixed the OAuth-app-free iNaturalist login (added in 0.3.0.c) — a separate bug in the manual "Refresh Now" button's endpoint, which had its own pre-flight gate checking the wrong (global, not per-user) fields and still hard-requiring OAuth credentials. Removed the redundant gate; the underlying refresh logic already handled this correctly. The scheduled loop was unaffected, since it bypasses this endpoint entirely.

## 0.3.0.k — 2026-07-13 — ENHANCEMENT

- Consolidated every experimental feature (Range Maps, Observation Heatmap, Bat Echolocation Detection, AI Features) into one Settings section as separate cards.
- Added a one-time "What's New" popup shown once per version per account (or per-browser for no-auth installs).

## 0.3.0.j — 2026-07-13 — FEATURE

- Added real device push notifications for the PWA — actual OS-level notifications while Chirp is closed, distinct from the existing email-only settings.
- VAPID private key format: pywebpush expects the raw 32-byte key, base64url-encoded, not a PEM string.
- New PushSubscription table, per-user filtering, and automatic pruning of expired subscriptions.
- Fixed a service worker icon path bug (`/icons/icon-192.png` referenced instead of the actual `/icon-192.png`).

## 0.3.0.i — 2026-07-13 — ENHANCEMENT

- Moved all AI-related settings (Anthropic/OpenAI/Gemini keys, feature assignment, usage stats) into their own dedicated section, separate from eBird/iNaturalist/device keys.
- Fixed "Reveal Keys" never actually including the OpenAI or Gemini key values.

## 0.3.0.h — 2026-07-13 — BUGFIX

- Fixed non-JSON error responses (e.g. a proxy's HTML error page) getting dumped verbatim as the displayed error message. The shared request helper now only trusts a parsed JSON `detail` field; anything else collapses to a short generic message.
- Switched the Gemini model from a hardcoded version to Google's own `gemini-flash-latest` alias, since this specific model lineup churns fast enough that pinning a version is itself a recurring failure mode.

## 0.3.0.g — 2026-07-13 — FEATURE

- Added API usage tracking across all AI features and providers — real token counts from each provider's own response, shown per-provider (last-30-days and all-time) and by feature in Settings.

## 0.3.0.f — 2026-07-13 — CRITICAL FIX

- Fixed the Daily Journal and Bird Profile Summaries silently failing — `ai_providers.py` used an invalid Anthropic model string, so every call failed with 400 Bad Request.
- Fixed a dead-end in both AI summary cards — they showed nothing at all unless a summary had already generated successfully, meaning a failed first attempt had no visible error and no way to retry. Both cards now show a real status (summary, error, or pending) whenever the feature is enabled.
- Fixed the Bird Profile's generation error never being exposed in the API response at all.

## 0.3.0.e — 2026-07-13 — BUGFIX

- Fixed the Docker build's EBADENGINE warning — @capacitor/cli requires Node >=22; bumped the frontend build stage from node:20 to node:22-slim.
- Moved the Settings save bar to the bottom-right and shrunk it — it was centered and large enough to cover real content underneath.

## 0.3.0.d — 2026-07-13 — FEATURE

- Settings save button is now a fixed bar that persists while scrolling.
- Added Gemini as a third AI provider alongside Anthropic and OpenAI, with a Test button for all three.
- Added Bird Call Re-analysis — a "Re-check this call" button on a recording's detail page for a vision-based second opinion on the spectrogram, generalized across all three providers.
- Fixed a route collision — the new call-reanalysis endpoint initially used the same path as an existing, unrelated BirdNET-reprocessing endpoint.

## 0.3.0.c — 2026-07-13 — ENHANCEMENT

- Added an OAuth-app-free way to auto-refresh an iNaturalist API token — simulates a normal login (username/password + CSRF token) instead of the OAuth password-grant flow. Fixed a gap where the per-user credential check still required OAuth fields even for this fallback.

## 0.3.0.b — 2026-07-13 — FEATURE

- Added Bird Profile Summaries — an AI-written note on each species' profile about its presence pattern in this specific yard, generated lazily on first view.
- Fixed a background-task bug — it was passed the request-scoped DB session, which closes right after the request completes; now opens its own session.

## 0.3.0.a — 2026-07-13 — FEATURE

- Added an experimental AI-powered Daily Journal to the Dashboard — a "birder's journal" recap combining real detection data, live weather, and ornithology context.
- Added multi-provider AI key management (Anthropic + OpenAI) with per-feature assignment; a disabled feature's UI doesn't render anywhere in the app.

## 0.2.0.h — 2026-07-13 — ENHANCEMENT

- Added bat-recording interference flagging — flags (not rejects) events with unusually regular pulse timing, a signature of electrical/mechanical noise rather than a real bat call.
- Fixed a seasonal-presence staleness bug on the Field Guide — `current_likelihood` was a value stored at whatever month the last manual sync happened to run, with no scheduled refresh. Now recomputed live from the still-valid 12-month frequency array.
- Added a 60s cache to the Regional Library endpoint, which recomputed on every single request uncached.

## 0.2.0.g — 2026-07-13 — ENHANCEMENT

- Added a "No detections" filter to the Recordings page.

## 0.2.0.f — 2026-07-13 — CRITICAL FIX

- Fixed "Importing a module script failed" breaking most pages after a deploy — content-hashed chunks mean an already-open tab has old JS referencing files that no longer exist. Now auto-reloads once on this specific error.
- Fixed Yard Diversity showing the species count twice.

## 0.2.0.e — 2026-07-13 — BUGFIX

- Actually fixed the recordings-thumbnail overlay clutter — the previous fix changed the server-side filename, but immutable cache headers meant browsers kept serving the old cached copy. Added a cache-busting version param.
- Redesigned Yard Diversity into a consistent 3-row layout.

## 0.2.0.d — 2026-07-13 — BUGFIX

- Fixed cluttered Recordings grid thumbnails — detection-overlay boxes and labels were rendering at full detail regardless of thumbnail size.
- Redesigned Yard Diversity with a single plain-language summary line.
- Fixed "Detection Activity & Top Species" repeating its own title in an inner header.
- Changelog version-scheme legend now derives from the actual latest entry instead of a stale hardcoded example.

## 0.2.0.c — 2026-07-13 — ENHANCEMENT

- Recordings grid thumbnails: species photo is now a corner badge on the spectrogram instead of a separate row, removing a duplicate species label.

## 0.2.0.b — 2026-07-13 — BUGFIX

- Fixed inconsistent "View all" link styling between Recent Recordings and Recent Notes.
- Cleaned up the Yard Diversity card — removed a redundant intro paragraph, shortened captions.

## 0.2.0.a — 2026-07-13

- Bumped to a proper minor version and started following the versioning paradigm described in this changelog's own legend. Re-labeled the 0.1.17.x series below with accurate category tags — many of those were genuinely new features that predate this being followed correctly; version numbers left unchanged since they're baked into already-deployed images.

## 0.1.17.am — 2026-07-13 — BUGFIX

- Fixed the Dashboard mode picker not appearing: it was gated behind the page's "stats still loading" early-return, so it effectively couldn't show for anyone until an unrelated data fetch finished — a real render-order bug, not a delay. It now renders independently of that.
- Added a one-time reset (guarded so it only ever runs once) clearing every existing user's dashboard_mode, so the picker shows for accounts created before this feature worked correctly too — not just brand-new ones. Verified with a real test: resets once, a real choice made afterward survives a second startup untouched.
- Optimized the Dashboard's data refresh: it polled 4 separate endpoints every 15 seconds regardless of whether anything had actually happened (~960 requests/hour from one open tab). Now refreshes immediately when the existing WebSocket reports a real new detection (debounced 2s so a burst of several detections collapses into one refresh, not one per message), with the interval reduced to 60s as a safety net rather than the primary mechanism. Applied the same change to Yard Pulse, which previously only ever fetched once at page load and went stale for the rest of the session.
- Updated the README's microphone table into a full comparison across cost, interface, directionality, self-noise, SNR, effective range, and key features for six mics (ReSpeaker, AudioMoth, EM272Z1, MKH 8020, Song Meter SM4, Dodotronic Ultramic).

## 0.1.17.al — 2026-07-13 — ENHANCEMENT

- Dashboard: bigger/bolder stat numbers, tactile depth on stat tiles (subtle inner highlight, distinct from the rest of the app's `.card` styling — scoped so it doesn't change any other page), more breathing room between sections.
- Audio enhancement: reduced audible distortion two ways — narrow adaptive-band filters now use a lower order (less ringing at the band edges, which a full 8th-order effective response from `sosfiltfilt` was prone to on tight bands like a chickadee's ~1.5kHz call), and spectral-gating strength lowered further (0.8 → 0.65) to reduce "musical noise" warble, continuing the same tuning direction as an earlier fix. Verified with a real synthetic-audio smoke test — no NaN/Inf, call signal preserved.

## 0.1.17.ak — 2026-07-13 — ENHANCEMENT

- Added "View the original picker again" to Settings → Appearance → Dashboard Style — reopens the exact same first-login Simplified/Detailed dialog (now dismissible), instead of only having the inline toggle.

## 0.1.17.aj — 2026-07-13 — FEATURE (should have been a minor bump)

- Added Simplified/Detailed Dashboard modes. First login (or first time after this update) asks which you want — Simplified shows just the Live card, Seen Today, and the Daily/Weekly Summary; Detailed keeps everything that's there today. This is a per-user account setting (a real database column), not a browser cookie/localStorage value, so it follows you across devices. Change it anytime via a link at the bottom of the Dashboard or in Settings → Appearance — both shown in the first-login picker itself. Verified end-to-end: save, read-back, and invalid-value rejection all tested for real.

## 0.1.17.ai — 2026-07-13 — CRITICAL FIX

- Actually fixed device logs "Permission denied" — the real bug, found after ruling out credentials, network, and sshpass availability one by one: the Devices page's log icon and the separate Logs page hit two different endpoints. The Logs page's wrapper correctly resolves SSH credentials from managed_config before connecting; the Devices page icon calls the underlying function directly, which only ever had a fallback for the username (to a separate, never-populated column) and none at all for the password — so it always attempted a passwordless connection, regardless of what was actually saved. Fixed at the source (the shared function itself), so both entry points now resolve credentials the same way. Verified with a real test replicating the exact call pattern the Devices page icon uses.

## 0.1.17.ah — 2026-07-13 — BUGFIX

- Changelog: only the very first version group now expands by default, not the first two.
- Fixed the Dashboard's "Detection Activity & Top Species" card looking visually unbalanced when collapsed — its header had top padding but no bottom padding (everything else was provided by the now-hidden content), unlike every other collapsible card.

## 0.1.17.ag — 2026-07-13 — BUGFIX

- Fixed a missing collapse chevron on the Dashboard's "Recent Notes" section — every other section had one, this one was overlooked.
- Swapped which chart defaults to normalized values: Day of Week now defaults to per-hour-recorded (was Hour of Day) — Hour of Day now defaults to raw counts, correcting the previous change.
- Investigated device logs failing with "Permission denied" — traced the full credential path (Devices page's SSH username/password fields → managed_config → the actual SSH command) and confirmed it's internally consistent; this is a stored-password mismatch (the saved password doesn't match the Pi's actual current one), not a code bug. Re-enter the correct password in the device's config editor and push again.

## 0.1.17.af — 2026-07-13 — FEATURE (should have been a minor bump)

- Every Dashboard section (Seen Today, Daily/Weekly Summary, Active Streaks, Yard Diversity, Detection Activity & Top Species, Recent Recordings) is now collapsible, using the same persistence system as Settings/Statistics/Profile — your choice is remembered next visit.
- Reorganized the nav: Statistics moved up next to Recordings/Life List (all "your own data" views grouped together), Field Guide (external reference) now follows them.
- Simplified the second diversity score on the Dashboard: renamed from the jargon "Simpson 1-D" to plain "Balance," replaced the duplicate circular gauge with a simpler horizontal bar (reads clearly as secondary to the main score instead of a confusing twin), and rewrote the labels in plain English (e.g. "Mostly one species," "Nicely balanced") instead of technical terms. Technical names kept in the expandable guide for anyone who wants them.
- Tutorial updated for both changes.

## 0.1.17.ae — 2026-07-13 — FEATURE (should have been a minor bump)

- Statistics page: "By hour of day" now defaults to per-hour-recorded values instead of raw counts (an hour bucket with more total recording time behind it would otherwise always look busier, regardless of actual activity rate) — same approach already used for the day-of-week chart, with a toggle to switch back to raw counts.
- Added Species Streaks to the Statistics page: active streaks (current, unbroken) alongside lifetime-longest streaks (the record for each species, whether or not it's still going — scans full history, not just the last 120 days). Verified with a real test: a 10-day streak from 200 days ago correctly shows up in "lifetime longest" even though it's long since inactive.

## 0.1.17.ad — 2026-07-13 — BUGFIX

- Fixed Simpson's diversity label repeating Shannon's exact wording ("High diversity" shown twice on the same card). Simpson's now uses its own evenness-framed labels (Low/Moderate/Strong evenness, Near-even spread) — a genuinely distinct, equally valid way this index is actually described in the literature.

## 0.1.17.ac — 2026-07-13 — ENHANCEMENT

- Mobile bottom nav: active tab now gets a real highlighted pill background (matching desktop), not just a subtle icon-only glow that was easy to miss.
- Redesigned Yard Diversity card: richness is now its own row with no gauge (it's an open-ended count, not a bounded index); Shannon's H and Simpson's 1-D each get matching gauge treatment with a short plain-language read, with the technical detail (full bands, methodology caveat) moved into the expandable guide instead of cluttering the main view.

## 0.1.17.ab — 2026-07-13 — BUGFIX

- Fixed a real bug in the Yard Diversity percentile (was showing "0th percentile" on a "High diversity" month) — a precision mismatch comparing a 4-decimal raw value against a 2-decimal rounded one meant a month could fail to match even against itself.
- Removed the percentile per feedback that it didn't read clearly. Replaced with Simpson's diversity index (1-D) shown alongside Shannon's H — weighs common species more heavily, less swayed by rare one-offs, no cross-month comparison involved so no precision-mismatch risk either.
- Fixed sparse/uneven card height on desktop (Active Streaks vs Yard Diversity) — the extra Simpson's content fills the card out properly now.
- Updated Tutorial's Yard Diversity section for both indices and the honest caveat about point-count vs. acoustic sampling.

## 0.1.17.aa — 2026-07-13 — FEATURE (should have been a minor bump)

- Yard Diversity card now shows both a percentile vs. your own recorded history (not affected by the point-count-vs-acoustic-sampling mismatch discussed below) alongside the absolute Shannon label, plus richness as its own clearly labeled stat. Verified with real test data (a genuinely more-even month correctly ranked 100th percentile against 3 less-even prior months).
- Reviewed switching to region/species-specific diversity benchmarks before writing any code, per request. Literature found: general bird-community Shannon H is 1.5–3.5, rarely above 4; a Boston-area residential-yard study exists but doesn't publish a specific H reference table. More importantly, all published benchmarks come from human point-count surveys, not continuous acoustic detection — common yard birds dominate raw detection counts far more than they'd dominate a brief human count, likely pulling an acoustic-derived H lower than point-count literature even in a genuinely diverse yard. Rather than invent an uncited "corrected" scale, added the self-relative percentile above instead — specific to this yard and this sampling method, which a borrowed number couldn't be either way.
- Fixed a JSX bug in the Diversity card's expandable guide — a missing opening `<p>` tag from an earlier edit.

## 0.1.17.z — 2026-07-12 — FEATURE (should have been a minor bump)

- Added per-user iNaturalist OAuth auto-refresh: any submitter/admin can set their own iNat username/password + OAuth app on their Profile page, so their personal token stays fresh using their own real account instead of relying on an admin's shared global credentials. Falls back to the global ones if not set. Verified with real tests: a user with their own credentials uses them; a user without falls back correctly.
- Added icons for the 11 older "Distinct Looks" themes (previously only the 4 newest had them). Fixed Oscilloscope's icon (was unrelated to the theme, now a real amber waveform trace) and Cornell Lab's (now closer to a Merlin-style binoculars mark instead of an unrelated icon).
- Device API Keys can now be revealed (eye icon per key) to help identify and prune unused ones — values were already stored in plaintext, just never shown back.

## 0.1.17.y — 2026-07-12 — FEATURE (should have been a minor bump)

- Fixed: two most recent Dashboard cards (Active Streaks, Yard Diversity) used a darker background than every other card — they'd been styled with `--bg-panel` instead of the standard `--bg-card`.
- Fixed: Bird Buddy devices in their compact card had no way to rename them at all — added inline rename, matching real Pi devices.
- Added diversity index graphs to the Statistics page: 12-month trend for species richness, Shannon's H', Simpson's 1-D, and Pielou's evenness — each on its own natural scale rather than forced onto one shared axis. Verified against real test data (values checked by hand); Shannon bands double-checked against ecological literature (real bird-community values typically 1.5–3.5, rarely above 4) — no changes needed, existing bands already correct.
- Investigated the iNaturalist observation-heatmap report — confirmed the tile endpoint itself is working (real 200 OK / valid PNG), so the bug is elsewhere in the app; still open pending more detail from a live repro.

## 0.1.17.x — 2026-07-11 — BUGFIX

- Fixed: Recordings page filters felt slow to apply and to clear — every filter change (each keystroke while typing a species search, or the several state resets "Clear" does at once) fired its own immediate, separate network request. Rapid changes queued up multiple in-flight requests, and a slower earlier one resolving after a faster later one could flicker the list back to stale data. Added a 250ms debounce plus a guard that drops any response superseded by a newer request.

## 0.1.17.w — 2026-07-11 — CRITICAL FIX

- Fixed: the app icon (Docker/Compose Manager, template.yml) has never actually worked — `chirp-logo.svg` was never copied into the Docker image, so `/icon.svg` silently served an empty stub instead of erroring. Not a config-path or caching issue. Added the missing `COPY` line.

## 0.1.17.v — 2026-07-11 — CRITICAL FIX

- Fixed: user approve/create/delete/activate all broken — UserManagement.jsx called `api.auth.approve/createUser/deleteUser/setActive` but the client only defines these nested under `api.auth.users.*`. Not a caching issue (the earlier "stale cache" theory for this exact error was wrong).
- Fixed: inputs under 16px font-size trigger iOS Safari's auto-zoom-on-focus, requiring a manual pinch-zoom-out afterward. Bumped to 16px everywhere.
- Fixed: negative-margin progress bar on the Tutorial page used a fixed desktop value, overshooting the viewport on mobile and causing real horizontal scroll.
- Added "remember me" login option — 7-day session instead of the default 12 hours.
- Devices page: Bird Buddy devices now grouped into their own collapsible card (Haikubox already had one), matching only what's relevant (status, ID, last recording) instead of the full config panel meant for real Pi devices. Chirp devices always list first. Added last-recording timestamp to both.
- Nav reorganized into logical groups (browse → social → admin → profile); active tab now has a subtle glow.
- Changelog: grouped into collapsible version-range cards (0.1.X.x) with a plain-language summary each, only the 2 most recent expanded by default. Added a versioning-scheme legend at the bottom. Removed ~120 lines of dead, unused parser code.

## 0.1.17.u — 2026-07-10 — FEATURE (should have been a minor bump)

- Added "Yard Pulse" to the Dashboard, alongside the existing Live card: Active Streaks (consecutive days each species has been detected, ending the moment a full day is missed) and a Yard Diversity gauge (real Shannon diversity index — species count weighted by how evenly detections are spread across them), both with an in-app interpretation guide. New `GET /recordings/statistics/yard-pulse` endpoint. Verified with real streak/diversity test data (broken streaks correctly excluded, math checked by hand).
- Tutorial updated to document the new section and how to read the diversity bands.

## 0.1.17.t — 2026-07-10 — FEATURE (should have been a minor bump)

- Added two more themes, each with real animation and a genuine icon: Roost (warm wood-grain, a small bird hops in the corner) and Echo Cave (rough stone, a bat periodically echolocates with expanding sonar rings).
- Updated Tutorial: correct theme count (25), correct 6-group Settings structure, added Bird Buddy/iNaturalist (previously undocumented), fixed a stale Haikubox settings path, documented the manual upload bird/bat selector and the Bats-only filter (both previously undocumented), documented the Recordings device filter.
- Audit: no new backend/device issues found. One false-positive from an audit heuristic caught and dismissed (a shared CSS selector misread as a duplicate theme definition).

## 0.1.17.s — 2026-07-10 — DEVELOPER

- Full backend/frontend/device audit: pyflakes clean across both server and device, no bare excepts, no SQL injection risk, all network calls have timeouts, no unclosed file handles.
- Fixed one real N+1 query (bat species list — batched profile lookups into a single query).
- No other backend, frontend, or device issues found.

## 0.1.17.r — 2026-07-10 — DEVELOPER

- Simplified CHANGELOG.md — recent entries had ballooned into multi-paragraph write-ups; condensed to one-line bullets going forward.
- Moved Location into the Detection group (it feeds species-list prediction, not really an "Account" setting).
- Added two new themes: Spectrogram (styled after Chirp's own audio spectrograms, viridis colormap) and Migration (night-sky starfield). Both have their own icon in the theme picker instead of just a color swatch.

## 0.1.17.q — 2026-07-10 — BUGFIX

- Reorganized Settings: Haikubox, Bird Buddy, and iNaturalist moved into their own "Third-Party Integrations" section, each its own card.
- Fixed: iNaturalist auto-refresh now updates the calling user's personal token, not a shared server-wide one.
- Added iNaturalist "Test Connection" button.

## 0.1.17.p — 2026-07-09 — DEVELOPER

- `bat_echolocation.gain_db` default raised from 0.0 to 5.0 for new installs.

## 0.1.17.o — 2026-07-08 — FEATURE (should have been a minor bump)

- Manual upload: mark a file as bird or bat to route it to the correct pipeline. Sample rate read automatically from the file.
- Bat uploads under 96kHz are rejected (physically can't contain echolocation calls).
- Upload errors now show plain text instead of raw JSON.

## 0.1.17.n — 2026-07-08 — CRITICAL FIX

- Fixed: device config sync could only push any given setting once, ever — every field (bat detection, recording duration, confidence thresholds, etc.) was frozen after its first push. Now correctly re-syncs on every change.

## 0.1.17.m — 2026-07-08 — ENHANCEMENT

- Live-activity badge now always says "Listening" instead of a low-confidence species guess.
- iNaturalist refresh added to Profile page.
- Performance: SQLite WAL mode + missing indexes, static asset caching, frontend route code-splitting (main bundle 1.24MB → 113KB).

## 0.1.17.l — 2026-07-08 — CRITICAL FIX

- Fixed: real device uploads never set `Recording.device_id` — affected every device recording ever uploaded.
- Recordings device filter now respects Bird Buddy's enabled/feeder settings.

## 0.1.17.k — 2026-07-08 — FEATURE (should have been a minor bump)

- Added device filter dropdown on the Recordings page.

## 0.1.17.j — 2026-07-08 — CRITICAL FIX

- Fixed: Bird Buddy virtual devices wrongly listed on the Logs page (no SSH access) — filter now excludes all virtual devices generically.
- Corrected one bat profile with swapped common/scientific names.

## 0.1.17.i — 2026-07-08 — CRITICAL DATA-LOSS FIX

- Fixed: "purge empty recordings" was deleting entire bat libraries — bat recordings now excluded from that filter.

## 0.1.17.h — 2026-07-08 — CRITICAL FIX

- Fixed: hyphenated species names (e.g. "Silver-haired bat") could get common/scientific names swapped.

## 0.1.17.g — 2026-07-08 — CRITICAL FIX

- Fixed: every Bird Buddy postcard failed to finish due to a serialization bug.

## 0.1.17.f — 2026-07-08 — CRITICAL FIX

- Fixed: Bird Buddy devices incorrectly showed "offline" even when working normally.

## 0.1.17.e — 2026-07-08 — CRITICAL BUILD FIX

- Fixed: production frontend build was failing 100% of the time (service-worker version race).

## 0.1.17.d — 2026-07-08 — BUGFIX

- Fixed device log viewer's hardcoded SSH username bug.
- Fixed Bird Buddy settings not persisting after page reload.
- Added iNaturalist token auto-refresh (was manual daily paste before).

## 0.1.17.c — 2026-07-08 — CRITICAL HOTFIX

- Fixed a type mismatch that broke `GET /settings` entirely once Bird Buddy synced.

## 0.1.17.b — 2026-07-08 — BUGFIX

- Fixed Bird Buddy recordings pointing at the wrong (video) file instead of extracted audio.
- Added Bird Buddy icon.

## 0.1.17.a — 2026-07-08 — FEATURE (should have been a minor bump)

- Added Bird Buddy integration: polling, video audio extraction, feeder picker, dedup.

## 0.1.16.p — 2026-07-07 — CRITICAL HOTFIX

0.1.16.o broke every profile page: `Can't find variable: profile`. Cause: a bat-map-source filter was added inside `EbirdRangeMap` — a component that never received `profile` as a prop at all. Also redundant: the parent already fully hides `EbirdRangeMap` (including this exact tab selector) for any bat profile via its own `profile.is_bat` check. Removed the broken addition; original gating was already correct and sufficient.

## 0.1.16.o — 2026-07-07 — CRITICAL HOTFIX

Previous version (0.1.16.n) crash-looped the server: `AttributeError: 'Settings' object has no attribute '_read_version'`. Cause: 0.1.16.n moved `_read_version` from a `Settings` method to a module-level function, but 3 other call sites (`main.py` ×2, `app_settings.py`) still called it as `settings._read_version()`. Not caught pre-ship because syntax/pyflakes checks pass fine — only a real `import app.main` catches this class of bug.

Fixed: all 3 sites now use `settings.app_version` directly. Verified via genuine `import app.main` + a live `/api/v1/health` request (not just syntax checks) — added as a permanent test. All 30 backend + 8 device tests pass.

## 0.1.16.n — 2026-07-07

- Fixed: startup logging self-test printed a fake "crash" traceback to console every boot (harmless, but alarming). Self-test now runs against a throwaway console.
- Fixed: `Zeroconf.async_unregister_service` "never awaited" warning at shutdown — removed redundant explicit unregister calls; `close()` already handles it internally.
- Fixed: diagnostics cache stats showed `?/?` — wrong attribute names (`_store`/`maxsize`/`ttl_seconds` → real: `_data`/`_maxsize`/`_ttl`).
- Fixed: Haikubox showed misleading `Config in sync: False` — N/A now shown correctly (no real config-push relationship exists).
- Added: Haikubox live status query in diagnostics, independent of the auto-sync toggle.
- Added: server version, bat-model-file presence, key package versions, SMTP status to diagnostics (system info + report text).
- Added: `BirdProfile.is_bat` column — reliable flag (not a fragile string match) covering both the generic "Bat" profile and any confidently-classified bat species. Self-heals on existing rows.
- Fixed: bird-specific map sources (AAB, iNat Geomodel, BirdLife, eBird S&T) now correctly hidden for bat profiles, generic and species-specific. Macaulay unaffected.
- Fixed: generic "Bat" profile's `common_name`/`scientific_name` now self-heal to canonical values on every access — undoes any accidental drift (e.g. a manual rename), decoupling identity from the representative stock photo.

29 backend + 8 device-side tests pass. Frontend build clean.

## 0.1.16.m — 2026-07-07

### Added: configurable bat recording length, and a real fix for short clips
Direct question with no real answer before this: "how do I increase the recording length for the bat detection pipeline?" Investigated and found there genuinely wasn't one — the settings that determine clip length (minimum pulses per event, the silence gap that closes an event, clip padding, and max clip length) were all fixed Python constants on the device with no way to adjust them short of a code change.

Made all four fully configurable via `config.yaml`'s `bat_echolocation` section (`min_pulses_for_event`, `event_gap_seconds`, `snippet_padding_seconds`, `snippet_max_seconds`), and added matching sliders/inputs in the Devices page's config editor for anyone who'd rather not hand-edit YAML — the same pattern already used for the existing bat mic-gain slider.

Also added a genuinely new setting, `snippet_min_seconds` (default 2.0s), which directly addresses "still getting short <1s clips sometimes": a legitimate pulse train that just barely qualifies as an event (the minimum pulse count) can naturally span well under a second on its own — the fixed padding alone isn't enough once added to such a brief span. This is a hard floor on total clip length: when the natural event span plus padding comes out shorter than this, the padding window is symmetrically expanded (equal extra time added before **and** after, not tacked onto one end) until it reaches the configured minimum, using whatever real audio the rolling capture buffer already has available.

Verified thoroughly with a new, dedicated test: confirmed the real reported scenario (a 0.3s pulse train, which the old fixed padding alone would leave at ~1.3s, now correctly extracted at ~2.0s), confirmed the expansion is genuinely symmetric (not lopsided), confirmed a naturally longer pass that already exceeds the floor is left alone rather than stretched further, and confirmed a differently-configured minimum actually produces a correspondingly different result — not a value that looks configurable but doesn't actually do anything. Also updated the existing event-grouping test suite, which referenced the old fixed constants directly, to use the new configurable attributes instead.

All 33 test suites (27 backend + 6 device-side, one new) pass. Full frontend build clean.

## 0.1.16.l — 2026-07-06

### Fixed: clicking the device log button crashed the entire Devices page
Real bug: `DeviceLogViewer`'s header used `<Server size={16}.../>` as an icon, but `Server` was never actually imported from lucide-react — a plain JavaScript `ReferenceError` at render time ("Can't find variable: Server"). Since this component only renders when the log modal is actually opened, the rest of the Devices page loaded and worked completely normally; the error only ever appeared on click. But because any render error inside `DevicesInner` bubbles up to the page-level `ErrorBoundary` wrapping it, opening the log viewer replaced the *entire* Devices page with the generic error fallback rather than just failing to open a modal — confirmed this exactly matches the reported screenshot. Fixed by adding the missing import.

Given a plain `vite build` succeeds even with this bug present (JSX compiles `<Server/>` into an ordinary variable reference, which bundlers don't statically verify), built a dedicated scanner — comparing every JSX-used component name against what's actually imported or locally defined in the same file — and ran it across all frontend components, not just the one file with the reported bug. Found and manually verified 4 additional candidates flagged by an early, cruder version of the scanner; all four turned out to be a different, legitimate pattern (a component destructured directly from props, e.g. `function StatCard({ icon: Icon })`) that the scanner needed to specifically account for — confirmed by direct reading of each, not assumed. `Server` was the only genuine instance of this bug across the entire frontend.

Frontend-only fix; all 32 test suites (27 backend + 5 device-side) still pass, confirming nothing else was affected. Full frontend build clean.

## 0.1.16.k — 2026-07-06

### Fixed: conservation status badge showed "G3G4 · G3G4" instead of an actual translation
Real bug, prompted by a direct question about what the badge meant on the Silver-haired bat's profile. `ConsBadge` accepted an `authority` prop (e.g. "NatureServe" vs "IUCN") but never actually used it anywhere in the render — it only had a translation table for IUCN's two-letter codes (LC, NT, VU, EN, CR, EW, EX). NatureServe — a real, distinct conservation rating system used for many North American species, including several bats, where iNaturalist's own data comes from NatureServe rather than the IUCN Red List — uses a completely different rank format (G1–G5, or a range like "G3G4" when NatureServe itself is uncertain between two adjacent ranks). Looking up "G3G4" in the IUCN-only table silently failed and fell back to showing the same raw code a second time.

Added a real NatureServe G-rank decode table (G1 Critically Imperiled through G5 Secure, plus GX/GH/GU/GNR), with genuine range-rank support — "G3G4" now correctly decodes as "Vulnerable–Apparently Secure" rather than being treated as one opaque code. The badge now also shows which authority a non-IUCN rating comes from. Verified directly: extracted the exact decode logic into a standalone script and ran it against realistic cases — the exact reported "G3G4" case, several single NatureServe ranks, standard IUCN codes (confirming they're completely unaffected by the fix), and a couple of deliberately malformed/unexpected inputs to confirm graceful fallback rather than a crash.

All 32 test suites (27 backend + 5 device-side) still pass — this was a frontend-only fix, backend untouched. Full frontend build clean.

## 0.1.16.j — 2026-07-06

### Fixed: profile creation for a confidently-classified species was missing its scientific name entirely
Real bug, found via careful code review after "still shows the same incorrect photo" and a second report of a completely empty photo for a different "Big brown bat" recording — both pointed at the same underlying issue, not two separate ones. Step 3 (ensuring a profile exists after classification) was calling `ensure_profile(det.common_name)` — passing just the bare name, e.g. "Big brown bat", with no scientific name attached at all. Profile creation splits a label on `"_"` to separate common and scientific names; a bare common name has no underscore to split on, so the created profile always ended up with `scientific_name=None`. Without a scientific name, the enrichment pipeline's iNaturalist/Wikipedia photo lookup has a much weaker, more ambiguous starting point — a good explanation for both a wrong photo (an older, differently-enriched profile) and a genuinely missing one (a fresh profile that never found a confident match).

Fixed by passing `det.label` instead — already the correctly-formatted "Scientific_Common" string (e.g. "Eptesicus fuscus_Big brown bat") for anything confidently classified, since last round's fix. Confirmed this brings the bat pipeline in line with a pattern already used correctly everywhere else in the codebase, including the bird upload pipeline's own equivalent step, which already used `d.label` — this was the one inconsistent caller.

**Like the label/confidence fix from last round, this only affects future classifications and reanalysis** — recordings already affected will need to be reanalyzed (individually or via last round's new bulk action) to get a correctly-enriched profile.

Verified: a new test confirms the actual mechanism directly (a bare common name really does leave `scientific_name` as `None`; the full label correctly captures both fields), then confirms end-to-end that the real bat pipeline now calls `ensure_profile` with the classifier's own full label rather than the bare common name, and that the resulting real profile has a genuine scientific name set. All 32 test suites (27 backend + 5 device-side) pass. Full frontend build clean.

## 0.1.16.i — 2026-07-06

### Fixed: label and confidence never updated on confident species classification
Real bug, and very likely the explanation for a separately-reported issue (a "Big brown bat" detection's Profile link pointing at the generic Bat profile instead): confident classification updated `common_name`/`scientific_name` but never `label` or `confidence`. Since the recording detail page's hero photo, profile link, and "top confidence" stat are all derived from `label`/`confidence` (not `common_name`), every confidently-classified bat recording kept resolving to the generic Bat profile's photo and kept showing the original ~100% pulse-detection confidence regardless of how confident the actual species identification was. Fixed: both fields now update to the classifier's own values (`label` to its already-correctly-formatted "Scientific_Common" string, `confidence` to its actual confidence in that species) alongside `common_name`/`scientific_name`.
**This only affects future classifications and reanalysis** — recordings already classified before this version will keep their stale label until reanalyzed. Reanalyzing a recording (or using the new bulk reanalyze below) picks up the fix retroactively.

### Added: bulk re-analyze
Refactored the single-recording reanalyze endpoint's logic into a shared helper so a new `POST /recordings/bulk-reanalyze` endpoint (and matching "Re-analyze" bulk action button on the Recordings list) can reuse the exact same per-type logic — bird recordings re-run BirdNET, bat recordings re-run the full bat pipeline including species classification — rather than a second, independently-maintained copy. Reports queued/skipped counts with specific per-item skip reasons (not found / archived / audio missing), not just a bare total.

### Fixed: short bat recordings were skipped entirely, not just handled conservatively
Real feedback: recordings under 2-3 seconds weren't being analyzed at all. The duration floor (previously 1.5s) was reconsidered — the classifier already zero-pads any clip into at least one valid window regardless of length, and the confidence threshold (not duration) is what actually gates whether a result gets asserted, so a short but genuinely confident result is exactly as trustworthy as a longer one. Lowered to 0.3s, which now only filters out genuinely-degenerate near-zero-duration clips (confirmed real in production — a literal 0-second recording) rather than skipping the large majority of real, well-formed short bat calls.

### Fixed: navigating back from a recording lost any active filters
Real bug: the recording detail page's Back button always linked to a hardcoded bare `/recordings`, discarding any `device_id`/`is_bat` filters active on the list the person came from. Now uses real browser history back (`navigate(-1)`), which correctly returns to the exact filtered URL, matching the browser's own back button. Also found and fixed a related gap: a custom (non-preset) confidence value was being restored from the existing session-persisted filter state on page load, but was never actually included when that state got saved — every other filter correctly persisted across navigation, this one silently didn't.

### Changed: Field Guide's bat section moved and collapsed by default
Per feedback: "Bats Identified Locally" now appears below the filter controls instead of above them, and is collapsed by default rather than always-expanded.

### Data note: a profile's display name reset
Confirmed via direct conversation that a "Bat (Little Brown)" display name found on the generic Bat profile in an earlier session's investigation wasn't an intentional edit — resetting it back to generic "Bat" (a one-time direct data fix, not a code change, since nothing in the current codebase would produce that value).

Verified: 31 test suites (26 backend + 5 device-side) pass, including 3 new tests — one proving label/confidence now update correctly on classification, one exercising the new bulk-reanalyze endpoint end-to-end (real bird + bat recordings, plus proper skip handling for archived/missing/nonexistent ones), and one confirming the lowered duration threshold while still correctly rejecting a genuinely degenerate 0-second recording. Full frontend build clean.

## 0.1.16.h — 2026-07-06

### Real production bugs found via direct server/database inspection — not guessed at

Rather than continue guessing at fixes, asked for and received real diagnostic output directly from the live server: log tracebacks, direct SQLite queries, and the actual model directory listing. This surfaced the real root causes behind all six reported issues.

**1. A genuine syntax error broke the entire email module, not just diagnostics.** The actual traceback: `SyntaxError: f-string expression part cannot include a backslash` at `email_service.py:561`, triggered on import. A nested f-string with escaped quotes inside an outer f-string's `{}` expression — valid in Python 3.12+ (PEP 701 lifted this restriction) but invalid in Python 3.11, which production actually runs. Since every email feature in this app imports the module locally at call-time rather than at startup, this meant **daily digests, new-species alerts, and password-change emails were all silently broken too**, not just the diagnostics report that happened to be the one someone tried and noticed failing. Fixed by eliminating the nested f-string entirely (plain string concatenation instead) and scanning the *entire* backend (both chirp-server and chirp-device) for any other instance of this exact pattern — found zero elsewhere, confirming this was isolated.

**2. Bat species classification never ran because the model files were never actually shipped to production.** Confirmed directly: `/app/models/bats/` didn't exist in the running container at all. The Dockerfile's `COPY app/ ./app/` never copied the separate top-level `models/` directory the classifier depends on. The classifier's own path-resolution logic was correct the whole time — confirmed by the production log showing it looking in exactly the right place — but nothing ever put the files there. This was tested extensively against the real files in the development sandbox, but the actual Docker build process itself was never verified to include them — a real gap between testing the code and testing the deployment. Fixed by adding the missing `COPY models/ ./models/` line; confirmed no `.dockerignore` exists that could exclude it some other way.

**3. The root cause behind "no recordings on profile," "no photo on Dashboard/Life List," and the Dashboard→Life List redirect flash — all three were the same bug.** Direct inspection found the "Bat" profile's `common_name` had diverged to a custom display name, while its `label` (the stable, never-user-edited internal identifier) correctly stayed `"Bat"` — and all 41 real bat detections still have `common_name="Bat"` exactly. Every place that matched a profile to its recordings/photo by `common_name` alone therefore silently failed the moment the two diverged, despite the underlying data being completely fine. Rather than reset this back (the display name may be a deliberate note, not a bug, and resetting someone's data without knowing which it is felt like the wrong call), fixed the actual lookups to also fall back to matching by the stable `label`:
   - The Bat profile page's own Recordings tab (now queries `is_bat=true` alone for this pseudo-species, not requiring the — possibly renamed — name to also match)
   - The Dashboard's per-species photo/profile-id lookup
   - The Life List's per-species photo/profile-id lookup
   
   Fixing the photo/profile-id lookup also resolves the redirect flash as a direct side effect: once `bird_profile_id` correctly resolves, the frontend links straight to `/library/:id` and never touches the `/library?name=X` fallback-and-redirect path at all.

**4. The photo cropping issue was a real, if simpler, CSS sizing bug.** Confirmed the actual photo file is a completely ordinary 900×600 (3:2) image — nothing unusual about the source. The recording detail page's hero container was fixed at 220px tall in a much wider layout, while the (visually correct) BirdProfile hero — using the identical blur-letterbox technique — uses a responsive height nearly double that. Against a normal landscape photo, the shorter container produced excessive blur-letterbox banding on both sides. Fixed by matching BirdProfile's exact proven sizing, for consistency rather than guessing at a new value.

Verified: 28 test suites (23 backend + 5 device-side), all passing — including 2 new tests that reproduce the exact production scenario (a profile with a diverged common_name, real seeded detections still using the original name) rather than a synthetic case that wouldn't have caught the real bug, and a dedicated test proving `email_service.py` imports cleanly and scanning its actual source for any remaining instance of the syntax pattern that broke it. Full frontend build clean.

## 0.1.16.g — 2026-07-05

### Continued pipeline double-check — a significant frontend gap and a real recurring bug pattern found

**A genuinely significant gap: the detailed species classification data was being computed and stored, but never shown anywhere.** `bat_metadata.species_guess` — the model name, every candidate species and its confidence, the noise/cricket/silence scores, how many windows were analyzed — was fully built out server-side a few versions back, but zero frontend code ever read it. Added a real "Species Classification Detail" section to the recording detail page: shows whether a species was confidently asserted (and why, by comparing against the classifier's own top pick) or not, confidence bars for the top candidates and non-species classes, and the model info — all framed honestly (informational, not asserted, when below threshold) rather than glossing over the classifier's known real limitations.

**A recurring bug pattern across 4 separate places: determining "is this a bat" by checking `common_name === 'Bat'` instead of the real `is_bat` flag.** This works by coincidence for generic, unidentified bat activity, but silently breaks the moment a bat gets confidently classified to an actual species name (e.g. "Little brown bat") — the check would then incorrectly treat it as a bird, showing the wrong icon. Found and fixed in:
- `RecordingDetail.jsx` — both the species-detected legend header and the per-species accordion group (two separate instances)
- `Dashboard.jsx` — the "Seen Today" tile icon/link logic
- `LifeList.jsx` — the same row-level icon logic

Fixing this properly required adding a real `is_bat` field to two backend endpoints that didn't expose it at all (`dashboard-summary`'s per-species cards, and `get_life_list`'s per-species entries) — both via an aggregate (`func.max(Recording.is_bat)`), the same safe pattern already used for `scientific_name` in the same queries, rather than a bare grouped column.

Verified directly with the exact scenario that was broken — not a generic "Bat" test case, but a specific confidently-classified species alongside a real bird species in the same dataset, confirming the fix actually distinguishes them correctly via the real flag rather than happening to work when everything is named "Bat":
- Dashboard summary and Life List both correctly return `is_bat: true` for "Little brown bat" and `is_bat: false` for "American Robin" in the same response.

Verified: all 26 test suites (21 backend + 5 device-side) pass, including 2 new tests targeting this exact scenario. Full frontend build clean.

## 0.1.16.f — 2026-07-05

### Full bat pipeline audit — 4 real bugs found and fixed, end to end

Traced every stage of the bat pipeline by hand — device upload, server processing, reanalysis, audio serving, profile management, deletion — rather than assuming everything already fixed this session was airtight. Found four genuine, previously-unnoticed issues:

**1. Reanalyze-created detections were missing `scientific_name`, the real root cause behind the earlier "two Bats on the Dashboard" bug.** The actual device upload endpoint (`bat_activity.py`) explicitly sets `scientific_name="Chiroptera"` on every bat Detection it creates — but the Detection my own reanalyze fix (from a few versions back) creates did not set this field at all. That inconsistency is almost certainly what the earlier `group_by` fix was silently compensating for, rather than a pre-existing data problem. Fixed at the source — reanalyze-created detections now set `scientific_name="Chiroptera"` too, matching the real upload path exactly.

**2. Reanalyze orphaned clip and enhanced-cache files on every use, a real unbounded storage leak.** Deleting the old Detection row before creating a fresh one (with a fresh id) left its clip file and enhanced-audio cache behind on disk forever, since both are keyed by detection id and the new detection gets a different one. Not a functional bug — nothing broke — but a genuine, silent, unbounded leak across repeated reanalyze attempts on the same recording. Fixed by cleaning up both files before the old detection row is deleted.

**3. A second, completely separate "bat audio enhanced" endpoint existed in `bat_activity.py`, cached to a different directory, with none of the stale-cache detection built a few versions back.** Confirmed this endpoint is legacy — the real device only calls `bat_activity.py`'s `/upload`, and the frontend uses the canonical `recordings.py` endpoint exclusively for playback — but it's deliberately kept for API backward compatibility (per its own docstring) rather than something safe to delete outright. Fixed properly instead of removing it: it now uses the exact same cache path as the canonical endpoint (so the two genuinely share one cache file instead of maintaining two independent, silently-divergent copies) and the same stale-cache detection, so a recording touched via either endpoint benefits from the fix either way. Verified directly: confirmed both endpoints actually share one file (unchanged mtime across a second request), and confirmed this endpoint also correctly detects and regenerates a planted stale cache.

**4. A real, meaningful data-loss risk: `bat_activity.py`'s delete endpoint always permanently destroyed a recording, despite its own docstring explicitly promising "the same soft-delete/restore behavior every other recording gets."** The actual code did a hard delete unconditionally, with no soft-delete option and no way to restore — a genuine documented-vs-actual mismatch that could easily surprise anyone relying on the stated behavior. Also still referenced the stale cache directory from bug #3, meaning it would fail to clean up the real enhanced-cache file. Fixed by having it genuinely call the real `delete_recording` function directly instead of an independent, drifted reimplementation — the two literally cannot diverge from each other anymore. Verified: default behavior is now a real soft-delete (row kept, `deleted_at` set, restorable via the standard restore endpoint, files kept on disk) exactly matching the standard endpoint, with `hard_delete`/`delete_files` opt-in flags behaving identically to their counterparts.

Also directly verified (not just re-read): the full upload → `process_recording_bg` → `_process_bat_recording_bg` chain correctly handles a recreated Detection during reanalysis, the Settings toggle for bat species ID round-trips correctly end-to-end through real HTTP calls, and re-ran the entire existing test suite from prior sessions to confirm zero regressions from any of this session's rapid changes.

Verified: 25 total test suites (20 pre-existing + 5 new from this audit), all passing — including 3 tests specifically targeting the newly-found bugs, each proving the fix against real seeded data through real HTTP endpoints, not mocked at the point that matters.

## 0.1.16.e — 2026-07-05

### Continued pending work: closed out the long-standing diagnostics feature request
Revisited the original 6-item pending list from earlier in this project's history. Two were already substantively complete (confirmed by reading the actual current code rather than assuming):
- **iNaturalist submission settings persistence** — already fully implemented (`InatSubmitButton.jsx`'s `loadPrefs`/`savePrefs`, a global localStorage-backed "last used" preference for spectrogram/details/enhanced-audio options, applied automatically on every open).
- **Field Guide slow photo rendering** — already fixed (`RegionalLibrary.jsx` uses native `loading="lazy"` on every photo plus a proper `IntersectionObserver`-driven chunked reveal, not rendering all ~93 species' photos at once).

One genuine gap remained: the diagnostics report was downloadable but not **emailable**, half of the original request. Closed this out:
- Extended `email_service.py`'s `_send()` with real, optional file-attachment support (correct standard MIME structure — `multipart/mixed` wrapping the existing `multipart/alternative` body, only when an attachment is actually provided) — purely additive, every existing caller is unaffected, verified directly by inspecting the real generated MIME message for both the with- and without-attachment cases.
- Added `POST /diagnostics/report/email`, deliberately reusing the exact same report-building and ZIP-assembly code the existing download endpoint already uses, so the emailed and downloaded versions of a report are guaranteed byte-for-byte identical rather than two independently-maintained versions that could quietly drift apart.
- Added a matching "Email Report" button in Settings → Diagnostics, pre-filled from the already-configured admin email when available, with real success/failure feedback.
- Verified thoroughly: clean error when SMTP isn't configured, correct plain-text vs. ZIP attachment selection matching the `include_logs` toggle, a genuine send failure surfacing as a real error rather than a false success, and the real (unmocked) MIME message structure inspected directly for both the attachment and backward-compatible no-attachment cases.
- Caught and fixed a real self-inflicted bug during this work before it shipped: an insertion accidentally consumed the function signature line of an existing, unrelated function (`notify_password_changed`) — caught immediately by re-verifying both functions existed correctly after the edit, not just by the file happening to still parse.

## 0.1.16.d — 2026-07-05

### Fixed: real "two Bats on the Dashboard" bug — grouping by scientific_name alongside common_name
- Root cause: two backend queries (`dashboard_summary`'s Seen Today grid, and the Field Guide's identified-bats section) grouped by `Detection.common_name` **and** `Detection.scientific_name` together. For a normal bird species this is harmless (scientific_name is always consistent per species), but "Bat" detections have genuinely inconsistent scientific_name values across different detections (some set, some not) — producing two separate groups for what should be one species entry, which is exactly why two "Bat" tiles showed up on the Dashboard.
- Fixed by grouping on `common_name` alone (matching the Life List's already-correct approach) and pulling scientific_name via an aggregate (`func.max`) instead of as a bare grouped column — the same fix pattern, applied consistently across both places it was needed.

### Fixed: inconsistent bat photo across the app — hero image blank while the detection row correctly showed one
- Root cause: the recording detail page's hero image and its own per-detection row used two **independent** lookup mechanisms for "this species' photo" — one correctly worked, the other (using `rec.top_species` matched against a profile map) could silently return nothing even when the exact same underlying data was available and already proven correct elsewhere on the same page.
- Fixed by deriving the hero's photo and profile-id fields directly from the already-correctly-computed per-detection list, instead of maintaining a second, independent lookup that could quietly diverge from what the detection rows themselves already show. Applied the same fix to `bat_profile_id` for full consistency — three fields, one source, can't disagree with each other anymore.

### Fixed (self-healing): possible duplicate "Bat" profile rows
- Investigated why the exact same "Bat" profile could show a real photo in some places and a blank fallback in others even after the above fix. `BirdProfile.label` is declared `unique=True` at the model level, but that's only enforced if the actual database table was created with that constraint present — and this project migrates schemas by adding columns via `ALTER TABLE`, never by retroactively adding constraints to an already-existing table. Confirmed directly: a fresh database correctly rejects a duplicate "Bat" row outright, meaning this can only be a real, silent risk on an existing production database that predates the constraint being added to the model.
- Added self-healing de-duplication to `_ensure_bat_profile()`: if it ever finds more than one, it keeps whichever one actually has a working photo (falling back to the oldest), safely re-points any user-uploaded photos or comments that reference a duplicate being removed (rather than orphaning real user data or risking a constraint violation), and removes the rest — so every future lookup deterministically resolves to the same row from then on.
- Verified: confirmed the constraint genuinely prevents new duplicates on a fresh database (ruling out this being a currently-reproducible bug in the current codebase), and separately verified the de-duplication logic itself — correct candidate selection, and critically, real re-pointing of both a user-uploaded photo and a comment confirmed via an actual database round-trip, not just asserted in memory.

### Fixed: "No recordings on bat profile" — re-verified after the above fixes
- Re-ran the full existing end-to-end verification (real seeded data through the real HTTP endpoints) after this round's fixes; the query logic itself remains correctly verified as it has been each time this has been checked. Given the newly-found and fixed profile-duplication issue above is a strong candidate for the actual root cause (a "Recordings" tab correctly querying by species name would return nothing if the *specific* profile page reached happened to be a duplicate row disconnected from the recordings a different, more-used duplicate accumulated) — this should now be resolved as a side effect. Flagging honestly rather than claiming certainty: worth confirming directly after this deploys.

## 0.1.16.c — 2026-07-05

### Fixed: Reanalyze silently did nothing useful for bat recordings
- Real bug: the Reanalyze endpoint always queued the bird-only pipeline (resamples to 48kHz and runs BirdNET) regardless of recording type — actively wrong for a bat clip (destroys the ultrasonic content) and never ran bat species classification at all. Now branches on `is_bat` to queue the real bat pipeline instead — the same one used on initial upload, including a fresh species-classification attempt (useful if species ID was enabled or its confidence threshold changed after the recording was first uploaded).
- Verified end-to-end, unmocked: a real reanalyze request on a bat recording now completes and produces a real spectrogram, not just a mocked call-count check.

### Fixed: a systemic routing bug — "/library?name=X" never worked, landing on the Life List instead of a profile
- Real, previously-unnoticed bug affecting every place that fell back to this pattern for a species without an already-resolved profile id (Dashboard's Seen Today tiles, Life List's own row links, RecordingDetail when a profile id wasn't already known): `/library` (no `:id`) always renders the Life List regardless of query string, since React Router matches on path only — the `?name=` part was silently ignored every time, not erroring, which is exactly why it looked like "clicking does nothing" or "goes to the life list" instead of an obvious crash.
- Fixed with a redirect shim in the Life List itself: on landing with a `?name=`/`?label=` param, resolves the real profile id and redirects to `/library/:id`. Fixes every current and future caller of this fallback pattern in one place rather than requiring route restructuring or auditing every caller individually.

### Fixed: no way to correctly refresh a bat profile's photo/content
- The existing "Refresh"/Enrich button called the generic Wikipedia/eBird/iNaturalist pipeline for every profile regardless of type — for the "Bat" pseudo-species that means searching those sources for the literal word "Bat," finding nothing useful, and potentially overwriting the correctly-set static content with empty results. Fixed: the enrich endpoint now routes "Bat" through its own dedicated refresh logic instead.
- Found and fixed a second real bug during this same fix: the dedicated bat-refresh path never reset `enrichment_complete` back to `True` on an already-existing profile, meaning a manual refresh would leave the frontend polling forever, stuck showing "in progress." Also added a real `force` option so a refresh re-fetches the photo even when one already exists, not just when missing.
- Verified with real assertions: refresh correctly routes through the dedicated bat logic (not the generic pipeline), `enrichment_complete` correctly flips back to `True` instead of getting stuck, and `force=True` genuinely re-fetches an existing photo rather than skipping it.

### Cleaned up: gear/satellite emoji replaced with proper line icons
- The "Server" / "Device" source labels on each detection (recording detail page) used raw ⚙/📡 emoji instead of icons consistent with the rest of the app's UI. Replaced with lucide-react's `Server`/`Cpu` icons, matching every other icon in the app.

### Investigated but inconclusive: a "Bat" pill reported appearing near the header
- Searched the shared app header, all Bat-related rendering across Dashboard/RecordingsList/RegionalLibrary, and the InatSubmitButton's portal usage for anything that could render a stray pill in that position — nothing found that would explain it from a static read of the code. Flagging this honestly rather than guessing at a fix with no clear mechanism; happy to dig further with a bit more detail (which page it appeared on, whether tapping it does anything).

## 0.1.16.b — 2026-07-05

### Comprehensive backend + frontend audit

**Systematic checks for the two bug classes found repeatedly this session:**
- Checked every one of the 137 columns in `database.py`'s migration list against every `Column()` declared across all model classes — zero orphaned columns remain (confirms the two found and fixed earlier this session, `Device.ssh_username`/`ssh_password` and `bat_species_id_enabled`/`bat_species_id_min_confidence`, were the only instances).
- Checked all 58 relative `from ..services.X import` / `from ..api.X import` statements against actual files on disk — zero ghost imports remain (confirms `bat_species_id.py` was the only one).
- Extended the check to a third variant: functions/methods defined in `services/` with zero references anywhere else in the codebase. Found 6 candidates; investigated each individually rather than assuming all were bugs:
  - `pixel_to_world()` in `range_map_service.py` — genuinely dead (only its inverse, `world_to_pixel`, is actually used) — removed.
  - **eBird export hardcoded `country_code = "US"`** with a 50-entry hardcoded US-state-name dictionary, while the already-written, already-correct `get_country_code_from_latlon()`/`get_region_code_from_latlon()` (real Nominatim reverse-geocoding, works for any country) sat unused. Fixed — verified with a real test that a Canadian location now correctly exports "CA"/"CA-ON" instead of hardcoded "US", a US location still correctly exports "US"/"US-MA", and both a geocoding failure and no-location-set fall back gracefully without crashing. Caught and fixed a real bug in this same fix during testing (wrong import path for the API-key helper) before it shipped.
  - **Waveform endpoint duplicated its downsampling logic inline** instead of calling the already-existing, already-correct `AudioProcessor.get_waveform_data()` — and the duplicated version had a subtle bug the canonical one didn't: its loop stopped one chunk early, silently dropping the final partial chunk of every recording's waveform. Fixed by calling the real method; verified with a real test using a deliberately non-round sample count with a distinctive spike in the final chunk, confirming it now shows up correctly.
  - **`ActivityLogManager.run_purge_now()`** — fully implemented, explicitly documented as "safe to call from an API endpoint," never actually wired to one. Added `POST /recordings/activity-log/purge` (mirroring the existing storage-cleanup trigger's exact pattern) plus a "Run cleanup now" button in Settings. The scheduled background purge was already correctly enforcing retention regardless — this is a manual-trigger convenience, not a fix to any actual data-retention gap.
  - `get_ebird_api_key_from_db()` and `emit()` (a `logging.Handler` override, called by the logging framework via polymorphism) — confirmed legitimate, no action needed.

**Frontend: a full ESLint pass across every component (not just recently-touched files) — 83 findings, each triaged individually rather than blanket-suppressed:**
- **Real bug**: `Devices.jsx`'s `isAdmin` flag defaulted to `true` with a comment claiming it would be "narrowed once role loads" — but nothing ever called its setter, so every user regardless of actual role saw the admin-only Haikubox serial number field. Fixed by replicating Settings.jsx's own correct, working role-fetch pattern. (The backend's settings-update endpoint doesn't independently enforce admin-only access either, so this was a real UI consistency gap rather than a newly-exploitable privilege escalation — the API already permitted any authenticated user to change any setting regardless of this frontend gate.)
- **Real gap**: `DeviceLogViewer` — a fully-built component with a real backing API client function and real backend endpoint, but never reachable from anywhere in the UI. Added a "View device logs" button next to the existing SSH terminal button, using the exact same trigger pattern.
- Confirmed-safe dead code removed: a `toggleMetric` function in Statistics.jsx superseded by inline handlers that do the same thing; an unused `InatSubmitButton` import in BirdProfile.jsx (that component needs a specific recording ID a species-level profile page doesn't have); a duplicate `spectrogramExpanded` state left over from an earlier refactor (the real, working expand feature lives in its own correctly-scoped sub-component); an unused `useEffect` import; a redundant duplicate `Link` import.
- Batch-cleaned ~25 confirmed-unused icon/variable imports across 10 files for consistency.

Verified: all 18 backend/device test suites pass (13 backend + 5 device-side), full frontend build clean.

## 0.1.16.a — 2026-07-04

### New: bat species classification wired into the live pipeline, behind a Settings toggle
Bigger version bump — this wires up last round's standalone, tested classifier module into the actual detection pipeline, end to end.

- **Settings toggle**: "Identify bat species" under Bat Echolocation Detection, off by default. Includes a configurable minimum-confidence slider (default 75%) — below this, a recording stays labeled generic "Bat" and the raw guess is kept for reference but never asserted anywhere. Also fixed real, previously-dead scaffolding found while wiring this: `bat_species_id_enabled` existed in the DB migration list but was never actually declared on the `AppSettings` model class, meaning it could never be correctly read regardless of its stored value — and the code that read it imported `services/bat_species_id.py`, which never actually existed, guaranteeing this step silently did nothing on every previous release that had it.
- **Duration/quality gating**: classification is now only attempted on recordings ≥1.5s — the classifier works by voting across overlapping ~0.5625s windows, and a clip too short to produce several windows is exactly the scenario most prone to a confident-but-wrong result.
- **Confidence gating**: a specific species only ever gets asserted (as the Detection's real identification) when it clears the configured threshold AND is more likely than the classifier's own noise/cricket/silence rejection classes — a species-shaped number alone isn't sufficient given real, tested false-positive behavior (see last version's notes).
- **Species → common_name assignment**: when confident, updates the Detection's `common_name`/`scientific_name` directly to the real species (e.g. "Little brown bat" / *Myotis lucifugus*) — this is what makes the Life List, iNaturalist submissions, and profile pages all correctly treat a confidently-identified bat exactly like any other species, with no further special-casing needed anywhere else in the app.
- **Field Guide**: added a new "Bats Identified Locally" section — the existing Field Guide is fundamentally an eBird checklist cross-referenced against local detections, and eBird has no bat taxonomy at all, so a real bat species could never have appeared there no matter what got detected. New `/birds/identified-bats` endpoint sources directly from the Detection table instead (the same approach the Life List already uses), correctly excluding generic/unidentified "Bat" activity (that's the Recordings page's job, filtered by `is_bat=true`, not the Field Guide's).
- **iNaturalist submissions**: already correctly handled by construction from last version's fix — since a confidently-identified species updates `common_name` away from the literal string "Bat", the existing `is_bat_detection = det.common_name == "Bat"` check automatically routes a real identification through the normal real-taxon submission path, with no additional changes needed.
- **Profile enrichment**: a confidently-identified species' profile goes through the completely normal Wikipedia/iNaturalist enrichment pipeline any bird species already uses (verified this doesn't have any bird-specific step that would hard-fail for a mammal name — eBird-specific steps just harmlessly find nothing and move on).
- **Verified end-to-end** with a real integration test exercising the actual wiring, not mocked at the seams: real classifier run on synthetic audio (correctly stayed generic "Bat" — real, unmocked low confidence), then a confident scenario proving the full downstream chain — species assignment, real BirdProfile creation, correct appearance in both the Life List and the new Field Guide section via their real endpoints, and correct exclusion of generic "Bat" from the bat-specific section. One honest caveat: the actual enrichment *content* (real photo, real Wikipedia text) couldn't be verified in this sandbox specifically — its outbound network access doesn't include api.inaturalist.org/Wikipedia (confirmed directly, not assumed) — but this is the identical, already-proven pipeline every bird profile already uses successfully on the real deployed server.

## 0.1.15.x — 2026-07-04

### New: bat species classification backend — standalone, tested, NOT wired into the live pipeline yet
- Researched real options for identifying bat species (not just "activity consistent with echolocation," which is all Chirp currently reports). Commercial tools (Kaleidoscope Pro, SonoBat) are accurate but closed-source; peer-reviewed literature on automated classifiers generally (Solick et al. 2024) found real accuracy limits, especially among *Myotis* species, with experts recommending manual review before using results for any regulatory/conservation decision.
- Chose BattyBirdNET-Analyzer's approach (github.com/rdz-oss/BattyBirdNET-Analyzer): the same BirdNET v2.4 model Chirp already uses for birds, run in "embeddings mode" (its second-to-last layer, not its own bird output) to extract a 1024-dim feature vector, fed into a small linear classifier trained on the NABat dataset. Bundled the USA-EAST checkpoint specifically — 16 real species relevant to Massachusetts (Little Brown Bat, Big Brown Bat, Northern Long-eared Bat, Indiana Bat, Tricolored Bat, etc.) plus 7 built-in non-species rejection classes (cricket, noise, silence, etc.).
- Verified every technical detail directly against the real cloned upstream repo and the actual bundled model files, not assumed from documentation: exact sample rate (256kHz) and window size (144000 samples / 0.5625s) via `config.py`, the embedding-tensor-index trick (`final_output_index - 1`) via the real `model.py` source, and the resulting tensor shapes via direct inference against the real files.
- `app/services/bat_species_classifier.py`: resamples arbitrary-rate audio (e.g. the real 384kHz AudioMoth rate) to the model's required 256kHz, slides overlapping windows across clips of any length (zero-padding short ones rather than dropping them), and reports the max confidence per class across all windows — all 23 classes, not just a single top-1 guess, since a high "noise" or "cricket" confidence relative to every real species is itself a meaningful, honest result.
- **Real, important finding from testing, not just a theoretical caveat**: on synthetic pure silence, the model confidently reported "Hoary bat: 97%" instead of the "silence" class (0.00000001%) — direct, concrete confirmation of the exact false-positive behavior documented in both the classifier's own GitHub discussions and the peer-reviewed literature. This is real evidence for why this isn't wired into the live pipeline yet without further validation against real bat recordings first.
- Bundled model files (~26MB total) under `models/bats/`, with a README covering licensing (the BattyBirdNET classifier itself is CC BY-NC-SA 4.0 — non-commercial only, flagged explicitly given Chirp's pending patent application) and the real accuracy caveats above.
- Verified: 9 real assertions against the actual bundled model files — correct file detection, correct label counts, correct tensor shapes at both pipeline stages, resampling that preserves real-world duration (distinct from the existing downshift-for-audibility transform), correct window padding/overlap behavior, full end-to-end classification from both raw audio and a real WAV file on disk, and clean (non-crashing) handling when model files are genuinely missing.

## 0.1.15.w — 2026-07-04

### Fixed: the actual root cause of "I deployed but nothing changed" — service worker cache never invalidated
- Real, confirmed, session-spanning bug: the service worker's cache-busting mechanism requires a hardcoded version string to be manually bumped on every release. That string was stuck at `'chirp-v0.1.14.n'` across every single release from 0.1.14.n through 0.1.15.v — meaning the cache-first `/assets/` strategy kept serving old JS/CSS bundles to any browser that had already loaded the app, regardless of how many times the server was actually redeployed. A hard refresh does NOT fix this on its own, since an already-active service worker intercepts asset requests before they'd reach the network.
- Fixed properly, not just bumped once: added a vite build plugin (`inject-sw-version`) that automatically reads the current version from `VERSION` and injects it into the built service worker on every build — no manual step to forget again. Fails the build loudly if it can't find/replace the expected pattern, rather than silently shipping an un-versioned worker.
- Verified directly: confirmed the plugin correctly injects the real current version into the built file, and confirmed it fails the build (not silently) when the source pattern doesn't match.

### Reversed: bat entries route back to the real profile page, not a Recordings redirect
- 0.1.15.t/u redirected Dashboard/Life List/Recording-detail bat entries straight to Recordings-filtered-by-bats instead of the actual bat profile page. Reconsidered based on feedback — that avoided the broken destination rather than fixing it. Reverted all three back to linking to the real profile page (with a name-based fallback for bat entries, which don't carry a `bird_profile_id`), and instead fixed what was actually broken on that page (see below).

### Fixed: real root cause of "no profile photos" for the Bat profile
- A correctly-written, dedicated mechanism for fetching a representative bat photo (`BirdEnricher._ensure_bat_profile`, using iNaturalist's Little Brown Bat taxon) already existed in the codebase — but was never actually called from the real endpoint that resolves a profile by label, which called a different, generic method with no bat-specific handling at all. Same class of bug as the downshift fix a few versions back: correct code that was never wired in.
- Fixed at the actual entry point, checked before the generic lookup — important because `_ensure_bat_profile()` also correctly retrofits a photo onto an EXISTING "Bat" profile missing one, not just brand-new ones, and Josh's system almost certainly already has a long-existing "Bat" profile row from before this bat-specific code existed; if the generic lookup ran first and found that row, the retrofit would never get a chance to run.
- Verified with real assertions: a fresh "Bat" request gets a real fetched photo; critically, a pre-existing photo-less "Bat" profile (the exact real-world situation) gets correctly retrofitted on next request; real bird species are unaffected and still use the normal path.

### Fixed: iNaturalist submissions labeled bat detections as "Chiroptera," not "Bat"
- "Bat" isn't a real taxonomic rank, so its BirdProfile's resolved scientific/taxon match is the ORDER-level Chiroptera — which iNaturalist then displays as the observation's primary identification. Given the bat detector's own stated design (identifies "activity consistent with echolocation," explicitly not species), asserting even an order-level ID overclaims what the system actually knows.
- Fixed: bat submissions no longer force a taxon association at all — `species_guess` (iNaturalist's free-text field) still correctly shows "Bat" for a human reader, but no formal identification is asserted, leaving that to genuine community review as iNaturalist is designed for. Real bird submissions are unaffected.
- Verified: confirmed bat submissions omit `taxon_id` entirely while still setting `species_guess: "Bat"`, and confirmed real bird submissions still correctly include their real taxon_id.

### Fixed: "Bats only" button text wrapping onto a second line
- Missing `flex items-center gap-1.5` classes (present on the neighboring "Birds only" button, absent here) — icon and text weren't laid out in a row. Added the missing classes plus `whitespace-nowrap` on both buttons for insurance.

## 0.1.15.v — 2026-07-04

### Fixed: real, likely cause of "enhancing doesn't always work" — stale pre-fix caches
- The enhance endpoints cache their output and serve cache-hits unconditionally — meaning any bat recording that was "Enhanced" even once *before* 0.1.15.t's downshift fix deployed has a stale cached file from the old, wrong bird-enhance function sitting at the same path, and would keep being served forever regardless of the fix, since a cache-hit doesn't check which function originally produced it.
- Fixed: both enhance endpoints now detect a stale bat cache (a real downshift always lowers the sample rate materially; the old function never resamples at all, so a cached file still at the original rate is a reliable signal it predates the fix) and regenerate it correctly, while leaving genuinely correct caches untouched.
- Verified: confirmed a planted stale cache (same sample rate as the original, exactly what the old buggy code would have produced) gets detected and correctly regenerated as a real downshift, and confirmed a genuinely correct cache is never needlessly reprocessed.

### Fixed: remaining bat-icon and click-through gaps found during a fresh audit
- Recording detail page hero image: still showed the generic bird fallback icon for bat recordings (never had `is_bat` awareness added) — now shows BatIcon. Matches a real reported screenshot exactly.
- Per-species detection row on the recording detail page: same fallback-icon gap, plus its "Profile" link depended on a `bird_profile_id` that bat detections don't reliably carry (mirroring the exact bug already found and fixed on Dashboard/Life List) — now always shows a "Recordings" link routing to bats-filtered Recordings instead.
- Two more small header icon usages (species-detected legend, detections count) on the same page — same fallback-icon fix applied for consistency.
- Added a defensive `is_bat=true` parameter to the bat profile page's Recordings-tab query, alongside the existing species-name filter — a strongly-typed boolean match is a more reliable signal than a text match could theoretically be for any edge-case historical data, at no cost.

### Note on Dashboard/Life List still showing the old behavior
- Re-verified both fixes from 0.1.15.t/u directly in the current code — both are present and correct. The reported screenshots match the exact pre-fix behavior already diagnosed and fixed in that version, which most likely means this deploy hasn't gone out yet rather than a new bug in the fix itself. Flagging this directly rather than guessing at a different cause.

## 0.1.15.u — 2026-07-03

### Fixed: bat clips contained only a couple pulses — events fired instantly instead of capturing the full pass
- Real root cause: the old design fired an event the INSTANT `MIN_PULSES_FOR_EVENT` (3) pulses arrived within a fixed lookback window, then went into a flat 5-second cooldown — silently discarding every subsequent pulse from that same, still-ongoing pass. A bat calling continuously for several more seconds after the initial 3-pulse trigger had none of that captured.
- Redesigned to proper gap-based pulse-train grouping: pulses now accumulate into one open event for as long as they keep arriving within `EVENT_GAP_SECONDS` (2.0s) of each other, checked on every audio callback (not just when a pulse arrives, since a train "ending" is defined by an *absence* of pulses). The event is only evaluated and captured once a real gap of silence confirms the pass has actually ended — using the complete pulse train, first call to last, not just the first three.
- Noise-rejection filters (swept-fraction, pulse-rate) now correctly evaluate against the full train's own actual duration rather than a fixed window.
- Raised `SNIPPET_MAX_SECONDS` (6→20s) to accommodate genuinely longer passes now that they're captured in full, and fixed a related bug this surfaced: the raw audio rolling buffer only retained ~10s, which would have silently truncated the beginning of any pass longer than that once events could legitimately run longer — resized to properly cover the new maximum event duration with margin, derived from actual time constants instead of a fixed magic chunk count.
- As a side effect, this should also make clips noticeably longer to listen to even before the earlier downshift fix's own 10x time-expansion is applied on top.
- Verified: 6 real assertions — 15 pulses across ~4.5s correctly accumulate into one event instead of firing at 3 (confirms the actual bug is fixed), two genuinely separate passes correctly stay separate (not incorrectly merged), noise-rejection still works on a full train, a too-short train is still correctly dropped, and the raw buffer is confirmed sized to cover the new maximum event duration with margin.

## 0.1.15.t — 2026-07-03

### Fixed: bat recordings were silent — "Enhance" never actually downshifted them
- Real root cause: `downshift_bat_clip()` (frequency downshift via time-expansion, correctly implemented) existed in the codebase but was never actually called from anywhere — every "Enhance" request, for bird and bat recordings alike, always ran the bird-only noise-reduction function. Bat echolocation (~15-120kHz) is inaudible at native sample rate; noise reduction doesn't fix that, only a downshift does.
- Fixed at all three call sites: the main `/audio/enhanced` endpoint, the per-detection `/clip/{id}/enhanced` endpoint, and the iNaturalist-submission enhanced-audio path — each now branches on `recording.is_bat` to call the correct function.
- As a side effect, this also resolves "recordings are too short to hear anything" — 10x time-expansion multiplies playback duration by 10x along with the pitch, so a ~1s raw clip becomes a ~10s audible one once actually downshifted.
- Verified with real synthesized audio (not mocked): confirmed a bat recording's enhanced output has its sample rate correctly divided by 10 (192000→19200 Hz) while a bird recording's enhanced output correctly keeps its original sample rate (noise reduction only, no resampling) — proving the correct function actually ran in each case, at both the recording and detection-clip endpoints, plus correct cache-reuse on a second request.

### Fixed: bat entries were unclickable / wrong icon on Dashboard and Life List
- Dashboard's "Seen Today" tiles: `SeenTodayTile` required a `bird_profile_id` to be clickable at all — "Bat" (a synthetic pseudo-species with no real bird taxonomy entry) never has one, so it silently fell back to a plain, non-linked `<div>`. Exactly matches a real report of "clicking does nothing." Now routes to Recordings filtered by bats instead, and uses the correct BatIcon instead of the generic bird fallback icon when there's no photo.
- Life List: same fallback-icon issue (BirdIcon shown for a bat entry), and clicking routed to the bird-species-profile page (eBird taxonomy, range maps) which doesn't apply to bats and looked broken/empty. Now also routes to Recordings filtered by bats, with the correct icon.
- Investigated the Bat profile page's "Recordings" tab showing "No recordings yet" despite real bat recordings existing: traced the full data flow (stub BirdProfile auto-creation for "Bat" → `common_name` resolution → `/recordings?species=Bat` query) and verified it end-to-end with real seeded data through the actual HTTP endpoints — every piece works correctly in isolation here. Given the two fixes above now route bat entries to Recordings directly instead of through this page, this is less pressing, but if it's still showing empty on the live system after this deploy, that points to something specific to the live data/environment rather than a code bug — would need the actual live API response to pin down further.

## 0.1.15.s — 2026-07-03

### Fixed: Coral self-compile docs presented a confirmed-broken path as viable
- `install-coral.sh`'s Step 3 documentation and final banner still described self-compiling as a real option, but a real compile attempt already proved it fails with a hard error ("delegate that only supports static-sized tensors with a graph that has dynamic-sized tensors") — a genuine, structural property of BirdNET's own INT8 export (confirmed via BirdNET-Analyzer's own GitHub issues showing the same warning in their official CLI), not something fixable on this side. Updated both to state this plainly and reorder options so the actually-viable one (community sourcing) isn't overshadowed.
- `compile-edgetpu-model/README.md`: added a prominent warning at the top, before requirements/usage, so anyone reading it before running the tool knows immediately rather than discovering it only after downloading, building, and compiling.
- `compile-edgetpu-model/compile.sh`: now captures compiler output and detects this specific known failure, giving a clear explanation instead of a bare compiler error. Fixed a real bug found while implementing this — with `set -euo pipefail` active, piping a failing `docker run` through `tee` would have exited the whole script immediately via pipefail, before the new check-and-explain logic ever ran; wrapped in an `if` condition (bash's standard way to run a command that might legitimately fail without triggering set -e's immediate exit). Verified directly with a standalone reproduction under the same shell options.
- Tool is kept, not removed — model exports can change upstream, and this exact failure could be resolved someday with zero changes needed here.

## 0.1.15.r — 2026-07-03

### Fixed: bat icon rendering wrong in real browser (looked like a small insect, not a bat)
- Root cause: React's `useId()` generates IDs containing colons (e.g. ":r0:"), which are special characters in CSS/URL-fragment contexts — a `mask="url(#...)"` reference containing one can fail to resolve correctly in some real browsers, even though the more lenient renderer used to visually verify the design beforehand didn't reproduce the problem. Fixed by stripping colons from the generated ID before use, for both BirdIcon and BatIcon.
- Also simplified the bat wings from a multi-scallop curve to a single bold scallop — less fine detail to render reliably at the actual small real-world sizes these icons are used at (e.g. 13px in the Bats-only filter button), as additional defense-in-depth alongside the actual fix.

### Verified: Statistics page detections/recordings toggle (long-pending item)
- Audited the entire `full_statistics()` endpoint end-to-end against real seeded data (3 recordings × 3 detections each of the same species — deliberately chosen so detections-count and recordings-count are unmistakably different, not an off-by-one that could pass by coincidence).
- Found and fixed one real inconsistency: `species_confidence`'s count field used a hardcoded raw detection count instead of the metric-aware expression every other section already correctly uses. Not currently rendered anywhere in the frontend, so not a visible bug today, but fixed for genuine correctness and to prevent a latent bug if it's ever displayed later.
- Confirmed every other count-bearing section (top species, monthly, hourly, day-of-week, species×month heatmap, rarest species, busiest day) correctly respects the toggle, and confirmed the two sections that should NOT be metric-dependent (life-list growth, confidence avg/max) correctly stay identical regardless — verified with real assertions, not just code reading.
- Confirmed the frontend already threads `metricLabel` thoroughly through nearly every relevant chart title/tooltip, with correct exemptions on the two metric-agnostic charts.

## 0.1.15.q — 2026-07-03

### New: real bird/bat icons, replacing the unclear blob and raw emoji
- New `BirdBatIcons.jsx` — original, custom-designed SVG icons (not emoji, not the generic lucide `Bird` glyph), matched visual style, `currentColor` fill so they inherit color per-context, eyes cut as genuine transparent masks (not a fixed-color dot) so they're correct against any background/theme rather than guessing one.
- Verified visually before shipping: rendered to PNG via cairosvg and inspected at both full size and actual ~20px UI scale, not shipped on hand-authored path coordinates alone.
- Replaced everywhere: the "Birds only"/"Bats only" filter toggles (the exact blobby icon flagged), diagnostics category headers and role badges, all fallback "no photo" avatars, Tutorial mockups, and every remaining generic lucide `Bird` icon across Statistics/Dashboard/HaikuboxDetections/AllNotes for full consistency. Left untouched: the intentionally-varied decorative species emoji list in Tutorial's "Seen Today" mockup, and one small text-prefix button label consistent with its plain-text sibling buttons.
- Verified: full frontend build clean, targeted ESLint pass across all 12 touched files (zero real errors — the one flagged item was a false positive from the test config's own incomplete browser-globals list, confirmed pre-existing and unrelated), full backend + device test suites re-confirmed unaffected.

## 0.1.15.p — 2026-07-03

### Fixed: real root cause of the AudioMoth never working — "speex" was the same physical device
- Confirmed conclusively: unplugging the physical AudioMoth made both "AudioMoth" and "speex" disappear from the device list together. The bird pipeline's own fallback device scan was claiming the AudioMoth under this alternate PortAudio-enumerated name — invisible to `device_name_excludes: ["AudioMoth"]` since "speex" contains no matching substring — holding the hardware open for the pipeline's entire lifetime. This is why the bat detector could never open it afterward regardless of sample rate: not a rate mismatch, not a PortAudio leak (both real, but secondary) — chirp-device's own bird pipeline was legitimately holding hardware the bat detector needed, under a name the exclude list couldn't see.
- Real fix: added bare `"speex"` to the existing ALSA pseudo-device blacklist (`speexrate`, the Speex resampling plugin, was already blacklisted — a longer, different string that doesn't substring-match the shorter bare `"speex"`). Filters it out at the earliest point, before any exclusion logic even runs.
- Also added card-number cross-referencing (`compute_excluded_cards`/`is_candidate_excluded`, extracted as proper testable functions) as defense-in-depth for any *future* aliasing case that isn't a known pseudo-device token but does resolve to an already-excluded card by number — exact integer matching can't have the "two different strings, same hardware" failure mode that name-substring matching hit here.
- Verified: 8 assertions covering the exact confirmed incident (bare "speex" rejected, no false positives on real device names, full integration test confirming `list_real_fallback_devices()` never returns it), plus the card-number fallback mechanism for a hypothetical future aliased name.

## 0.1.15.o — 2026-07-03

### Fixed: AudioMoth left in a permanently-stuck busy state after a failed startup
- Diagnosed from real device evidence (`fuser`/`lsof`): the same chirp-device PID still held the AudioMoth's ALSA device open several minutes after the bat detector had already logged giving up — a leaked handle, not a rate mismatch. Direct `arecord` also failed with `Device or resource busy`.
- Root cause: 0.1.15.m's fix tried up to 6 candidate rates via `check_input_settings` (a separate probe-then-reopen cycle) — more open/close cycles meant more chances to trigger what's very likely a PortAudio/ALSA-level leak on a failing probe for this specific hardware.
- Fix: collapsed probe+reopen into a single direct `InputStream` construction attempt per candidate, capped at 2 candidates total (name-parsed rate, then one fallback) instead of up to 6. Explicit cleanup (`.close()`) on every failed attempt.
- Verified: confirms exactly 1 open/close cycle in the common case (name-parsing correct on the first try), confirms the worst case is capped at 2 attempts even when everything fails, confirms correct fallback behavior.

### Fixed: diagnostics "Bird mics / Bat mics" checkmarks were always shown, regardless of actual status
- The checkmark was hardcoded in the frontend — the backend only ever did a name-pattern match against `arecord -l` text ("does this contain 'audiomoth'?"), with zero connection to whether the device was actually being captured. A real screenshot showed a bat mic checkmarked as apparently fine while the actual journal logs proved the bat detector had been failing to start for hours.
- Fix: cross-references the name-based classification against the device's own live status_server (the same mechanism the mic-levels websocket uses), converting each entry into `{name, live_active, live_detail}`. UI now shows three distinct states: genuinely confirmed active (✓, real dBFS), confirmed broken (✗, real error shown), or unconfirmed name-match-only (?, explicit disclaimer) — instead of one unconditional checkmark.
- Verified: 5-assertion test covering the exact real-world scenario (name-matched but unconfirmed), genuinely active, genuinely broken, role-mismatch safety, and mixed-outcome lists.

## 0.1.15.n — 2026-07-03

### Fixed: raw ALSA errors in the journal during bat detector startup
- `Expression 'ret' failed in 'src/hostapi/alsa/pa_linux_alsa.c'` — PortAudio's C-level ALSA backend writes this directly to fd 2, bypassing Python's logging entirely, whenever 0.1.15.m's candidate-rate probing loop tests a rate the hardware rejects. Harmless (expected part of discovery), but reads as an alarming crash in the journal.
- Fixed: probing loop now wrapped in a real file-descriptor-level stderr suppression (Python-level redirection doesn't catch this — it's C code writing directly to fd 2). Only suppresses during the probe itself; any real failure afterward still raises/logs normally.
- Verified at the actual OS file-descriptor level: confirmed suppression during the block, confirmed correct restoration after, confirmed real Python exceptions still propagate (not swallowed), confirmed full `start()` succeeds correctly with simulated ALSA noise fully suppressed end-to-end.

## 0.1.15.m — 2026-07-03

### Fixed: AudioMoth stopped working after switching to 384kHz mode
- Diagnosed from real device logs (not guessed): device selection was correct (`Bat detector: using device '384kHz AudioMoth...'`), but `check_input_settings` failed for both `min_sample_rate` (192000) and whatever PortAudio's `default_samplerate` reported — that reported value simply isn't reliable for this device in its new mode.
- Root cause: `start()` only ever tried two candidate rates (config minimum + one reported value). When neither matches what the hardware actually accepts, it fails — even though the device works fine at its real rate.
- Fix: AudioMoth encodes its configured rate directly in its own USB name (`"384kHz AudioMoth..."`) — now parsed and tried first, plus a fallback list of AudioMoth's own documented rates (384k/250k/192k/96k/48k), each tested via `check_input_settings` (the real, authoritative hardware check) rather than trusting one reported value.
- Verified: reproduced the exact real-world failure in a test (device selection correct, rate negotiation failing) and confirmed the fix resolves it; confirmed no regression on the original working 192kHz case; confirmed still fails cleanly (no false positive) when a device genuinely can't do the minimum rate.

## 0.1.15.l — 2026-07-03

### New: Admin-savable SSH credentials in the diagnostics card
- `PUT /{device_id}/ssh-credentials` — admin-gated, stores plaintext (same pattern as smtp_password everywhere else in this app), masked in every API response via a computed `ssh_password_set` property, never the raw value.
- Fixed a real pre-existing gap while building this: the old `/ssh-username` endpoint had zero admin gating despite being nav-hidden as admin-only — now properly gated too.
- Caught and reverted a real near-miss before shipping: an early draft embedded the raw stored password into `_device_stats()`'s dict, which gets returned directly in `/diagnostics/run`'s JSON response. Fixed to look up the password separately, as a local variable, only where actually used for the SSH connection.
- Verified: 7-assertion test covering admin-gating, masking in every response shape, partial updates, and the masked-placeholder-doesn't-overwrite-real-value case.

### New: Storage details collapsed by default
- The directory breakdown / recordings accounting / orphan detection UI is now a collapsible sub-card, collapsed by default. The underlying fetch still always runs on mount regardless — collapsing only hides the display, never delays the data.

### Investigated: "no activity from other users"
- Checked backend query logic (genuinely queries all users, no self-filtering), list/count endpoint filters (optional, not automatic), login logging (unconditional, no role gating), and the frontend beacon (fires for any authenticated user, not admin-gated). Found no bug — likely genuinely no activity yet from other accounts, as suspected.

### New: Bat detection mic gain control
- Mirrors the bird pipeline's existing `input_gain_db` pattern exactly: `detection.bat_echolocation.gain_db`, applied once per audio chunk (affects live level display, pulse-detection analysis, and saved clips consistently), hot-applies via `set_gain_db()` with no restart needed.
- New "Bat Detection" section in the Devices config UI.
- Verified: 5-assertion test confirming actual sample-level gain multiplication and hot-apply.

### Fixed: compile-edgetpu-model tool picked the wrong file
- The official Zenodo zip contains two .tflite files — the main audio classifier and a small auxiliary location/season-filtering model. `find | head -1` could silently grab either; confirmed this happened on a real run (uploaded file had input shape [1,3], not the expected [1,144000], and no edgetpu-custom-op marker — it wasn't even actually EdgeTPU-compiled).
- Fixed: excludes the auxiliary model by name pattern, and validates the compiled output actually contains the edgetpu-custom-op marker before declaring success.

### Config: new bat_echolocation defaults
- `min_swept_fraction: 0` (disabled — permissive until there's a real-detection baseline to tune against), `max_pulse_rate_per_sec: 600`, `active_hours_start: "18:00"` — applied to both config.yaml and the matching Python-level fallback defaults for consistency.

## 0.1.15.k — 2026-07-03

### New: EdgeTPU model self-compile tool (`chirp-device/tools/compile-edgetpu-model/`)
- One-command Docker-based compiler: downloads the real official BirdNET V2.4 INT8 model from Cornell's Zenodo record, builds a container with Google's actual `edgetpu_compiler`, compiles, validates, and outputs the exact filename chirp-device expects. Works on Mac (Apple Silicon via Docker's linux/amd64 emulation) or any x86_64 Linux machine, including the Unraid server.
- Uses the modern GPG-keyring apt method (the older `apt-key` approach is deprecated/broken on current Debian).
- Not independently tested end-to-end against real hardware (no Docker in the dev sandbox) — every individual piece (package name, install method, exact Zenodo URL/checksum) verified against current sources; documented as first-real-run in the tool's own output.

### Investigated: WebSocket showing "Disconnected"/"Offline" in the UI
- Confirmed both frontend (`createWebSocket`'s URL construction) and backend (`/ws` endpoint) are correct and unchanged. Confirmed `AuthMiddleware` never gates `/ws` at all (only applies to `/api/v1/*` paths) — ruled out as a cause regardless of auth settings.
- Given the dashboard shows real live data (REST calls working fine) while only the WebSocket is down, this points to something outside the codebase — most likely a reverse proxy in front of the domain not forwarding WebSocket upgrade headers, or a transient reconnect window. No code changes made; see chat for diagnostic steps.

## 0.1.15.j — 2026-07-03

### Fixed: install-coral.sh's final banner was misleading
- Confirmed the script's actual logic works correctly (three-tier backend fallback, honest refusal to fake a missing model) — but it unconditionally printed "Setup Complete!" and told the user to enable/test the coral backend even when Step 3 had just reported the model file is missing, sending them straight back into the same error.
- Fix: banner is now conditional on the model file actually existing and being a real size — shows a clear "still needs a model file" summary with the real options instead when it's not.
- Verified: tested all 4 banner-decision scenarios (model present/absent × backend usable/not) directly.

### New: Storage Management now covers all directories, not just recordings
- `/storage/status` expanded to report every directory (recordings, spectrograms, clips, enhanced, bat_clips, media), matching the diagnostics breakdown.
- Added real orphan detection, not guesswork: distinguishes active recordings, soft-deleted recordings whose files are still on disk (with reclaimable space shown), and true orphans (files with no matching DB row at all). New `/storage/purge-orphans` endpoint (dry-run preview by default, explicit confirm to actually delete) — never touches files a soft-deleted row still references.
- Settings UI: full directory breakdown, recordings accounting, and a review-then-confirm cleanup flow for true orphans.
- Moved `dir_stats`/`fmt_bytes` into `storage_manager.py` as shared utilities (was duplicated in diagnostics.py).
- Verified: 6-assertion test covering active/soft-deleted-with-file/true-orphan classification, dry-run safety, destructive purge only touching real orphans, and post-purge state.

### Fixed: pre-existing duplicate `waveform` key in api.js
- Found while verifying the above — silently shadowed, dead code, not a functional bug, but fixed since it was trivial.

## 0.1.15.i — 2026-07-03

### Fixed: Coral labels file 404 + a real label-parsing bug found while fixing it
- `install-coral.sh`'s labels download hit the same dead URL as the model. Fix: `birdnetlib` (already a required CPU-backend dependency) bundles the exact same official label file — copy it directly, no download needed at all. Same fallback added to `birdnet_coral.py`'s `load()` itself for runtime resilience, not just install-time. Uses `importlib.util.find_spec` (not a full `import birdnetlib`) to avoid triggering its analyzer module's unconditional tflite_runtime/tensorflow import.
- Found and fixed a real bug while verifying the label file's actual format: `birdnet_coral.py` parsed labels as `Common_Scientific`, but the real official BirdNET format is `Scientific_Common` (confirmed directly against birdnetlib's bundled file, e.g. "Abroscopus albogularis_Rufous-faced Warbler"). Every Coral detection would have had common/scientific names swapped — never caught because Coral inference had never successfully completed a full cycle before now.
- Also researched and confirmed (official BirdNET-Analyzer model page, PINTO0309's model zoo): no pre-built EdgeTPU-compiled BirdNET model exists anywhere right now. Not a code bug — documented in `install-coral.sh`.
- Verified: end-to-end test proves `analyze()` now correctly returns `common_name='American Robin'` / `scientific_name='Turdus migratorius'`; separate test confirms the birdnetlib labels fallback loads all 6522 real labels with zero files placed in `models/coral/`.

## 0.1.15.h — 2026-07-03

### Diagnosed: Coral "still not working" — root cause confirmed, not a code bug
- Ran the full diagnostic script against the real Pi. Everything code-side is working correctly: hardware detected, `check_coral_available()` returns True, three-tier backend fallback correctly selected tflite-runtime, hot-swap correctly activated. The one and only blocker: `EdgeTPU model not found` — the actual `.tflite` file was never downloaded (install-coral.sh correctly refuses to save a fake/broken file, so it's simply absent).
- Researched whether a working pre-built BirdNET EdgeTPU model exists anywhere right now: official BirdNET-Analyzer model page — no EdgeTPU variant, only FP32/general formats. PINTO0309/PINTO_model_zoo (an extensive, actively-maintained EdgeTPU conversion repo that already has a BirdNET-Lite entry with FP32/FP16/INT8) — TPU column empty for that entry. No working pre-built file found anywhere.
- Documented this confirmation in `install-coral.sh`. Real remaining options: stay on CPU (already reliable), or self-compile via `edgetpu_compiler` on a separate x86_64 Linux machine using the official INT8 model from Zenodo.

## 0.1.15.g — 2026-07-03

### Fixed: "Coral backend didn't work" — real bug, not user error
- Diagnosed from an uploaded diagnostics bundle: `BirdNET backend: cpu` even with Coral hardware detected. Traced the full config path (Devices UI toggle → `managed_config` push → device sync → `apply_config()`) and found the actual bug: pushing `backend: coral` correctly updates the *reported* status string, but the running process's actual inference backend was never swapped — only min_confidence/lat/lon/blacklist were hot-applied. Silently required a manual restart nobody was told about.
- Fix: `DetectionPipeline.switch_birdnet_backend()` — real hot-swap, no restart needed. Builds and loads the new backend before swapping in (a failed load leaves the current working backend active, never leaves detection with nothing). Wired into `watcher.py`'s `apply_config()`.
- Also fixed two real gaps in the diagnostics collector found while investigating: `config.yaml` was truncated at 1500 chars (never reached the backend setting), and the journal excerpt was just the last 30 lines regardless of relevance (missed the actual Coral load attempt). Now sends the full config and greps full journal history for backend/Coral-relevant lines.
- Verified: 4 hot-swap scenarios tested against real code (cpu→coral, coral→cpu, no-op when unchanged, safe fallback when Coral unavailable).

### Fixed: Dashboard chart still blank on mobile after 0.1.15.d's fix
- 0.1.15.d's resize-nudge fix addressed a *different* issue (stale ResizeObserver measurement) — this was a separate, deeper bug: mixing `flex:1` with `minHeight` on a nested flex-column item is a known WebKit/iOS Safari bug where the computed height can genuinely resolve to 0, not just be mismeasured. Explains "works on desktop, not mobile" exactly.
- Fix: unconditional `h-[220px]` on mobile (no flex-dependency at all), switching to `lg:h-auto lg:flex-1` at the desktop breakpoint where flex-row gives it a real constraint to grow into.

## 0.1.15.f — 2026-07-02

### Fixed: Coral EdgeTPU non-functional on Python 3.13
- Confirmed via web search: `pycoral` (max Python 3.9) and `tflite-runtime` (max 3.11) are both permanently abandoned upstream — not flaky installs, dead ends.
- Real fix: full `tensorflow` package is actively maintained, ships real Python 3.13/aarch64 wheels, and exposes the same interpreter API via `tf.lite.Interpreter` + EdgeTPU delegate — pycoral was always just a wrapper around it, never a hard requirement.
- `birdnet_coral.py` now tries pycoral → tflite-runtime → tensorflow in order, no other code changes needed (identical interpreter API across all three).
- Fixed a consistency gap: `check_coral_available()` gated `load()` but didn't know about the new tensorflow tier — would have reported "no Coral" on a tensorflow-only system and never even tried it.
- `install-coral.sh` now offers tensorflow as an explicit, confirmed last-resort install with the size/RAM tradeoff stated up front.
- Verified: all four backend scenarios (pycoral/tflite-runtime/tensorflow-only/none) tested against the real `load()` code; separate test for the `check_coral_available()` fix.

## 0.1.15.e — 2026-07-02

### Fixed: Field Guide slow load (pending item #4)
- Root cause: ~93 species cards + photos all mounted and rendered at once on load; every search keystroke re-ran rank computation (O(N) scan) up to 3x per species across labelCounts/filter/card-render — tens of thousands of redundant comparisons per keystroke.
- Fix: memoized `allFreqs`/rank-per-species/label-counts/filtered results; `SpeciesCard` wrapped in `React.memo`; progressive rendering in chunks of 24 via `IntersectionObserver` (same idiom as RecordingsList's lazy image reveal), instead of mounting all ~93 cards immediately.
- Caught and fixed a real regression while refactoring: briefly conflated rank (locally_detected-agnostic, used for tab counts/filtering) with display label (locally_detected takes priority, used for the card badge) — would have made a locally-detected "Very Likely" species vanish from the "Very Likely" tab. Split into two separate memoized maps.
- Verified: dedicated regression test proving a locally-detected high-rank species still counts toward and filters under both "Detected Here" and its true rank tab; separate test for chunk/reveal clamping logic.

## 0.1.15.d — 2026-07-02

### Fixed: Dashboard "Detection activity" chart rendering blank
- Root cause: Recharts' `ResponsiveContainer` measures via `ResizeObserver` at mount, which can race the card's CSS fade-in animation and get stuck at zero size — no error, just blank. Top Species in the same card (plain HTML) was unaffected.
- Fix: resize nudge ~500ms after mount/period-change, `debounce` + period-keyed remount on `ResponsiveContainer`.
- Also fixed: chart query didn't inherit the Haikubox-only-species exclusion that top_species/total_detections use — could disagree if Haikubox sync was on. Now built from `_det_base` directly.
- Caught a test-isolation bug while verifying: test scripts used `DB_URL` instead of `CHIRP_DB_URL`, polluting the shared sandbox DB across runs. Fixed and re-ran the full suite clean.
- Verified: real seeded data through the actual endpoint, dedicated Haikubox-consistency test, exact frontend mapping logic run in Node.

## 0.1.15.c — 2026-07-02

### Fixed: mic-check still showed SSH-only data despite 0.1.15.a's card-matching fix
- Root cause found: frontend reads `lev.card` for every row, but the device-local endpoint's normalized output only ever set `alsa_card`, never `card` — so even a working local-source row couldn't render its index. All three rows carrying real `arecord -l` index numbers (0/1/2) means every row was still coming from SSH, not the local source.
- Fixed the field-name mismatch; both sources now populate `card` consistently.
- Fixed a second bug hiding the real diagnostic: the local-reachability status message shared the same UI state as "Connecting.../Connected", so it got overwritten within a second of the mic check starting. Given its own message type + state so it persists.
- Added a visible `local`/`ssh` source badge to each row so this is self-diagnosing going forward without needing hardware access.
- Real-hardware confirmation still pending.

### Fixed: Activity nav link missing from mobile entirely
- `MobileNav` used its own separate hardcoded menu list that never included `/activity` — admins couldn't reach the page on mobile at all. Added it to the admin-only section, consistent with Devices/Users/Logs.
- Confirmed `/auth/activity`, `/activity/count`, `/activity/summary` are all admin-gated server-side (403 for non-admins, already tested); `UserActivity.jsx` fails gracefully with no data leak if reached directly. No client-side route guard added — none exists anywhere else in the app, so one only for this page would be inconsistent.

## 0.1.15.b — 2026-07-02

### Server performance
- `GET /recordings` / `/recordings/haikubox`: eager-load detections via `selectinload` — 30 recordings: 6 queries instead of ~66+.
- Fixed real bug found while testing: `recording_to_out()` checked `not profile_map` instead of `profile_map is None` — a legitimately empty pre-fetched map silently fell back to a redundant per-recording query.
- `bulk-archive` / `bulk-delete`: one `SELECT ... WHERE id IN (...)` instead of one query per id. 10-item batch: 3 queries instead of ~20+.
- Reviewed `birds.py` enrich-all loop — left as-is, it's network-bound not DB-bound.
- Verified via `TestClient` + query-count instrumentation; all bulk-action edge cases re-confirmed (already-deleted, nonexistent ids, mixed batches).

## 0.1.15.a — 2026-07-02

### New: Activity Log — admin visibility into logins and page views
- New `activity_log` table: login/login_failed/logout/page_view events, no request bodies, no recording content, no credentials.
- New endpoints: login/logout logging, page-view beacon, admin-only activity list + summary (per-user stats, daily logins, top pages, live feed).
- New settings: enable/disable, IP tracking on/off, retention days (0 = forever) — wired through all four required layers this time (model, migration, settings schema, Settings.jsx).
- New admin-only **Activity** page + nav entry, page-view beacon on route change.
- Tested end-to-end against real endpoint code (13 assertions) + retention purge tests + clean `vite build` + targeted ESLint pass.

### Fixed: dsnoop mic-level fix from 0.1.14.ai didn't cover the ReSpeaker
- Root cause: skip logic matched by fuzzy name substring between two different naming conventions (PortAudio vs. `arecord -l`) — didn't reliably match for the ReSpeaker.
- Fix: each stream now also reports its ALSA card *number*; server matches by exact integer as the primary mechanism, fuzzy name kept only as fallback.
- Also fixed a latency bug caught while building this: card-number lookup shelled out to `arecord -l` while holding the same lock the live audio callback needs — moved outside the lock, cached per device.
- Also fixed: `status_server.py` silently dropped a stream if its provider raised — now surfaces as a visible error entry instead of vanishing.
- Tested: reproduced the exact screenshot scenario in a script-injection test; confirmed the fallback still works; confirmed provider exceptions are now visible. Real-hardware confirmation still pending.

## 0.1.14.ai — 2026-07-02

### Fixed (both): Live mic levels — dsnoop "device busy" errors on chirp-managed cards
- Root cause: `AudioCapture`/`BatDetector` open their ALSA device exclusively via PortAudio's raw `hw:` — dsnoop sharing only works if every reader (including the first) uses dsnoop, so the old SSH+arecord diagnostics script could never win against chirp-device's own exclusive open.
- Fix: new `chirp-device/chirp/status_server.py` — a local HTTP server publishing levels straight from already-open in-memory buffers. No second ALSA open at all.
- Server merges this with the SSH+arecord fallback, which now skips cards already covered locally.
- Fully backward compatible with older chirp-device builds.
- Requires a one-time chirp-device restart after deploy.

### Fixed (chirp-server): "Clear filter" banner — empty/ugly bar when toggling "Birds only"
- Root cause: trigger condition fired on the "Birds only" toggle's own state, which had no message text — empty gold-bordered bar.
- Fix: narrowed trigger to actual cross-page entry points only; restyled to match the subtler Haikubox banner.

### Changelog housekeeping
- Removed stale `*(prior session)*`/`*(initial release)*` tags from the oldest version headers.

## 0.1.14.ah — 2026-07-02

### Fixed (chirp-server): Changelog page — dates missing for double-letter versions (aa, ab, …)

Root cause: `Changelog.jsx` parsed version headers with the regex `/^([\d.]+[a-z])\s*[—-]\s*([\d-]+)/`. The character class `[a-z]` matches exactly one letter, so versions with two-letter suffixes (`aa`, `ab`, `ac`, … `ah`) failed to match — `parts` was null, `date` fell back to `''`, and the date column was empty in the UI.

Fix: changed `[a-z]` → `[a-z]+` in both regex instances in `Changelog.jsx` (one in `VersionBlock`, one in the main `versionSections` render loop). The `+` quantifier matches one or more letters, covering both single-letter (`a`–`z`) and double-letter (`aa`–`az`) suffixes and any future multi-letter suffixes without further changes.

Tested against all current version formats: `0.1.14.ag`, `0.1.14.aa`, `0.1.14.z`, `0.1.14.a`, `0.1.13.m` — all parse correctly.

## 0.1.14.ag — 2026-07-02

### Fixed (chirp-server): Tutorial — wrong Field Guide icon everywhere
- All four places in Tutorial.jsx used `MapPin` for the Field Guide nav item. The actual nav in App.jsx uses `BookOpen` (route `/regional`). Fixed in: `NavMockup` (static bottom bar mockup), `NAV_DEMO_ITEMS` (animated nav demo), desktop sidebar mockup (`[LayoutDashboard, Mic, Award, BookOpen]`), and the Field Guide tutorial section header (`icon: BookOpen`). `MapPin` import removed entirely since it's now unused.

### Fixed (chirp-server): Tutorial — "Seen today" tap animation too fast
- `tap` phase duration was 350ms — too brief for the user to register the press gesture. Increased to 700ms. `idle` period slightly increased from 1400ms → 1600ms and `hold` from 1200ms → 1400ms for a more comfortable viewing pace overall.

### Fixed (chirp-server): Tutorial — NavigationDemo hardcoded width overflows on very narrow screens
- `width: 280` replaced with `w-full maxWidth: 320` so the animated nav demo shrinks to fit on screens narrower than 280px instead of causing horizontal scroll.

### Fixed (chirp-server): Statistics — horizontal scroll on mobile
- **Heatmap** (species × month grid): `gridTemplateColumns: "160px repeat(12,1fr)"` with a 160px label column + 12 month columns was too wide for mobile (min ~460px). Fixed: label column reduced to 90px, month headers use 9px font. Added `overflow-x: auto` wrapper with `minWidth: 380` so the grid scrolls within the card rather than pushing the page layout wider. Used `-mx-1` to extend the scroll area edge-to-edge within the card padding.
- **Activity by time of day**: label spans used `minWidth: 140` which forced overflow. Changed to `w-28 sm:w-36` Tailwind responsive width with `truncate`, font-size 10px, and reduced count column to `w-14`.
- **Statistics header row**: `flex items-center justify-between` with no wrap forced overflow when the toggle + refresh button row was wider than the screen. Added `flex-wrap` and reduced button padding slightly.

## 0.1.14.af — 2026-07-02

### Fixed (chirp-server): Bird profile link from RecordingDetail → blank screen

Root cause: the "Profile" button added in 0.1.14.aa used `to={"/birds/${profileId}"}`. The SPA router has no `/birds/:id` route — `/birds/` is the backend API prefix only. The correct route is `/library/:id` (registered in `App.jsx` line 513 as `<Route path="/library/:id" element={<BirdProfilePage/>}/>`). Navigating to an unmatched route renders a blank screen because the router falls through to the SPA catch-all which serves `index.html` but the React router finds no matching `<Route>`.

Fix: changed `to={"/birds/${profileId}"}` → `to={"/library/${profileId}"}` in `RecordingDetail.jsx` line 892.

Comprehensive audit of all other bird-profile navigation links across all components confirmed every other instance already uses `/library/:id` correctly (Dashboard.jsx ×4, RegionalLibrary.jsx ×1, BirdProfile.jsx ×1). Only this one link was wrong.

## 0.1.14.ae — 2026-07-02

### Fixed (chirp-server): Dashboard chart — stretches on desktop, visible on mobile

The chart wrapper previously toggled between two broken states:
- `height: 220` (0.1.14.ad) — fixed mobile but capped desktop at 220px regardless of species list height  
- `flex-1 / height: 100%` (0.1.14.ac) — stretched on desktop but gave Recharts zero height on mobile

Root cause: `ResponsiveContainer height="100%"` calls `offsetHeight` on its parent. In a `flex-col` mobile stack, `flex-1` resolves to zero because no ancestor has a fixed height. In a `flex-row` desktop layout, `flex-1` resolves correctly because the sibling species column gives the row a concrete height.

Fix: chart wrapper uses `position: relative; flex: 1; minHeight: 220px`.
- `position: relative` — gives Recharts an offsetHeight anchor even in flex contexts where the element has no intrinsic height
- `flex: 1` — stretches to fill the column on desktop (flex-row), inheriting the species list height
- `minHeight: 220` — floor on mobile (flex-col, no parent height) so the chart is never zero-height
- Empty-state div uses `position: absolute; inset: 0` to fill the same positioned box

This is the correct pattern for Recharts in responsive flex layouts.

## 0.1.14.ad — 2026-07-02

### Fixed (chirp-server): Dashboard chart blank on mobile

Root cause: `height="100%"` on `ResponsiveContainer` requires a concrete pixel height somewhere in its ancestor chain. In the `flex-col` stacked mobile layout, the chart div used `flex-1` which resolves to zero height when the parent flex container has no explicit pixel height — Recharts gets a 0×0 SVG and renders nothing.

Fix: give the chart wrapper an explicit `style={{ height: 220 }}`. This always works regardless of layout context (flex-col mobile, flex-row desktop, any nesting depth). `ResponsiveContainer width="100%" height="100%"` then fills that known-height box correctly on both mobile and desktop. The 220px height is consistent with the previous pre-grouped card height and looks good on both viewport sizes.

Also removed the broken `className="lg:flex-1"` that was previously there — Tailwind can't override an inline `style={{ height }}` with a `flex-1` class anyway, and the 220px height on desktop is still correct since the card width is unconstrained.

## 0.1.14.ac — 2026-07-01

### Improved (chirp-server): Dashboard chart + top species card layout

Fixed the awkward combined header from 0.1.14.ab based on visual feedback:

- **Removed** the single shared "Detection activity · Top species" title row that spanned the full card width. That arrangement put unrelated content in the same header and pushed the period buttons far from the chart they control.
- **"Detection activity"** title now lives inside the chart column header, with the period buttons (6h/24h/48h/7d/30d) on the right of the same row — directly above the chart they filter.
- **"Top species"** title now lives as its own header inside the species column on the right, with "· last {period}" as a small inline suffix that updates live. Title and list are visually self-contained.
- **Chart fills full column height**: removed the fixed `height={240}` on `ResponsiveContainer`, replaced with `height="100%"` inside a `flex-1` container. The chart now stretches to fill the card regardless of how tall the species list makes the right column.
- The card itself has `overflow-hidden` and no outer padding — each column owns its own `p-5` padding, so the vertical divider runs full-height without gap artifacts.
- Mobile: chart column stacked above species column with `mx-5` horizontal rule between them (respects column padding). Desktop: side-by-side with full-height vertical rule.

## 0.1.14.ab — 2026-07-01

### Improved (chirp-server): Dashboard — grouped detection activity + top species with shared time filter

**Backend**: `top_species` in the `/stats` response now filters by the same time window as the detection chart (the `period` query param: 6h/24h/48h/7d/30d). Previously `top_species` was always all-time regardless of which period was selected. Root cause: `top_species_query` was defined before `cutoff` was computed, so it couldn't reference it — fixed by reordering so `_PERIOD_MAP`/`cutoff` are computed first, then `top_species_query` filters on `cutoff`.

**Frontend**: "Detection activity" and "Top species" are now a single grouped card with one shared header containing both titles and one set of period buttons that controls both simultaneously.
- **Mobile** (< lg): chart stacked above a horizontal rule, species list below. Both full-width.
- **Desktop** (lg+): chart on the left (~flexible width), vertical rule divider, species list on the right (~56-64 fixed width). Chart height 240px.
- Empty-state for top species now says "No detections in the last {period}" (matching the chart) instead of "No detections yet".
- `animate-stagger-2` retained on the combined card; `animate-stagger-3` removed (was on the old separate top-species card).

## 0.1.14.aa — 2026-07-01

### Added (chirp-server): Bird profile link from RecordingDetail detection accordions
- Each species row in the detection accordion below the spectrogram now has a small "🐦 Profile" button on the right side of the header, tinted in that species' assigned color.
- Clicking it navigates directly to `/birds/{bird_profile_id}`. `e.stopPropagation()` prevents the click from toggling the accordion open/closed.
- Button only appears when `bird_profile_id` is populated on the detection — which it is for all detections where a BirdProfile exists in the database. New species detected for the first time (profile not yet enriched) show the button once their profile is created.
- Frontend-only change; no backend changes needed (`bird_profile_id` was already in `DetectionOut`).

## 0.1.14.z — 2026-07-01

### Fixed (chirp-server): Live mic levels — all three device strings tried in order
- `plughw:N,0` still requires exclusive access and fails with "Device or resource busy" when chirp-device holds the card open. Fixed by trying three ALSA device strings in order until one succeeds:
  1. `dsnoop:CARD=N,DEV=0` — ALSA's built-in shared-capture PCM; designed for concurrent readers
  2. `default:CARD=N` — card default PCM, may go through dsnoop depending on Pi ALSA config
  3. `plughw:N,0` — last resort, exclusive access with plugin layer
- Also reads `/proc/asound/cardN/pcm0c/sub0/hw_params` to discover the sample rate the device is actually running at (e.g. 192000 for AudioMoth). Matching the running rate avoids ALSA format-mismatch errors even when the device is locked.
- Error messages now show the actual error string (truncated to 35 chars, full text on hover) instead of just the word "error", so the exact failure reason is visible in the UI.

## 0.1.14.y — 2026-07-01

### Fixed (chirp-server): Live mic levels — shows all mics, no service disruption
- Previous approach used sounddevice/portaudio to open each device directly, which failed with "Device or resource busy" on the ReSpeaker and AudioMoth because chirp-device holds ALSA exclusive locks on them. Only the excluded USB Audio Device (Unitek) showed a reading.
- Correct approach: use `arecord` (ALSA command-line tool) instead. arecord operates at the ALSA layer via `plughw:N,0` which goes through dsnoop — ALSA's built-in capture-sharing mechanism. This allows reading from a device even when portaudio/sounddevice already has it open. No service stop, no connection disruption, no SIGTERM to chirp-device.
- The script also no longer depends on numpy or sounddevice on the Pi side — it reads raw 16-bit PCM from arecord's stdout and computes RMS/peak/FFT bins in pure Python. This avoids any import failures if numpy is missing from the venv.
- AudioMoth detected by name/rate heuristic and opened at 192kHz; falls back to 48kHz if that fails.
- Each device now shows: role tag (🐦 Bird / 🦇 Bat / ✗ Excluded), sample rate, dBFS level bar with peak marker, and a mini 32-column waterfall spectrogram (hue-mapped from green→yellow→red) that builds up over time.
- Status messages ("Probing audio devices via arecord…") shown while first frame is loading.
- chirp-device service stays running throughout; bird and bat detection continues uninterrupted during the test.

## 0.1.14.x — 2026-07-01

### Fixed (chirp-server): Custom confidence filter didn't trigger a fetch
- `customConf` was missing from the fetch `useEffect` dependency array. Typing a value in the custom confidence box had no effect until something else triggered a re-fetch (e.g. page change).
- Also fixed the custom input visibility — it was always shown because the condition `customConf !== undefined` is always true when initialized to `''`. Now uses a dedicated `showCustomConf` boolean state toggled by selecting "Custom…" from the dropdown. `autoFocus` added so the input is ready to type immediately after selecting Custom.

### Fixed (chirp-server): Live mic levels WebSocket — authentication always failed
- The WebSocket endpoint accepted no `ssh_password` query parameter, so the SSH connection always tried key-based auth only. Docker containers have no SSH keys, so paramiko got `EOF in transport thread` (auth rejected silently) immediately.
- Fixed: WebSocket endpoint now accepts `ssh_password` query param. Frontend now passes `diagSshPassword` when opening the WebSocket connection (alongside the JWT token). Key-based auth is still tried first if no password is given; password auth is used when provided.

## 0.1.14.w — 2026-07-01

### Fixed (chirp-device): server_sync.py broken try/except — CA bundle fix was in wrong scope
- The automated CA bundle patch (0.1.14.s) inserted the `_verify` resolution block as a *second* `try` statement at the top-level of the outer `try` body, which left the entire `payload`/`resp` body inside the `except Exception:` clause — meaning ALL requests silently failed with `_verify = ...` assigned but never used. Fixed in `_pair`, `_heartbeat`, and the config-fetch function by moving the CA bundle resolution *inside* the outer `try` block correctly.

### Fixed (chirp-device): respeaker.py undefined `np`
- `extract_mono` used `np.ndarray` type annotations without a numpy import. Added `try/except ImportError` import block.

### Fixed (chirp-server): bat profile photo — now downloaded on first detection and on startup
- `_ensure_bat_profile` now calls `_fetch_bat_photo()` on creation and on any startup where the photo file is missing. Downloads the representative photo for Little Brown Bat (iNaturalist taxon 40346) via the iNaturalist API and stores it at `media/birds/Bat/photo.jpg`.
- Startup hook in `main.py` lifespan retries the photo download if the profile exists but has no photo.

### Fixed (chirp-server): bat profile link — broken from dashboard and recording detail
- Added `bat_profile_id` and `top_species_profile_id` fields to `RecordingOut`. Frontend can now link directly to the Bat BirdProfile page from any bat recording card or recording detail view.

### Added (chirp-device): bat detector noise rejection + time-of-day gating
- **FM sweep filter**: real echolocation calls sweep in frequency; lawnmowers and motors produce flat broadband bursts. New `min_swept_fraction` setting (default 0.3) suppresses events where fewer than 30% of pulses show an FM sweep. This directly rejects the lawnmower false positives.
- **Pulse rate ceiling**: real bats call 5–30 times/second; continuous noise produces far higher apparent rates. New `max_pulse_rate_per_sec` setting (default 60) rejects events with implausibly high pulse rates.
- **Time-of-day gating**: new `active_hours_start`/`active_hours_end` settings (default 20:00–06:00 local time). Events outside the window are silently suppressed. Bats in Massachusetts are strictly crepuscular/nocturnal; daytime detections are almost certainly machine noise.
- All three filters exposed in `config.yaml` with documentation. All three are also configurable from Settings → Bat Detection in the web UI (pushed to device via managed config).
- New `_is_active_hour()` method on `BatDetector`.

### Added (chirp-server): bat filter settings in Settings UI
- New "Noise rejection & scheduling" card in Settings → Bat Detection, visible when bat detection is enabled. Controls: active hours start/end (time pickers), FM sweep min fraction (numeric), max pulse rate (numeric). Values saved to AppSettings and available for device managed config push.
- DB migration: `bat_active_hours_start`, `bat_active_hours_end`, `bat_min_swept_fraction`, `bat_max_pulse_rate` columns added to `app_settings`.

### Added (chirp-server): Bulk recording actions in RecordingsList
- Select checkbox appears on hover over any recording card. Multi-select supported.
- Bulk action bar appears when any recordings are selected: Archive audio, Delete.
- Select-all checkbox in the bulk bar selects/deselects the current page.
- Backend: `POST /api/v1/recordings/bulk-archive` and `POST /api/v1/recordings/bulk-delete`.

### Added (chirp-server): Custom confidence filter in RecordingsList
- Confidence filter now has a "Custom…" option that shows a numeric input (enter any value 0–100%). Custom value overrides the preset dropdown selection.

### Added (chirp-server): Birds-only filter button in RecordingsList
- New "Birds only" button (with a custom bird SVG icon) alongside the "Bats only" button. Sets `is_bat=false` in the URL filter. Both buttons are shown regardless of bat detection being enabled.

## 0.1.14.v — 2026-07-01

### Fixed (chirp-server): eBird export — separate Date and Time columns, 18 columns
- eBird Record Format v3 requires Date (col 4) and Start Time (col 5) as **separate columns**, not combined. Previous 0.1.14.u fix combined them into one field which still produced import errors. Now 18 columns with correct separate date/time, no BOM, no header row. Protocol is "incidental" (col 8), count is "X" (col 14), state derived as "US-MA" from location name.

### Fixed (chirp-server): Live mic levels WebSocket — closed immediately
- Previous implementation ran a new SSH `exec_command` per sample iteration, each spawning a new Python process on the Pi (2-4s startup cost per sample). The WebSocket closed before the first sample arrived. Rewritten to use a **persistent SSH channel** running a continuous Python loop on the Pi that samples all audio devices and prints JSON every 350ms. Single process startup cost, then streaming output read line by line from stdout. Much faster and stays connected.

## 0.1.14.u — 2026-07-01

### Fixed (chirp-server): eBird life list export — completely wrong format
- The exported CSV was using a custom column order invented by us (Common Name, Genus, Species, Number, Comments, Location, Lat, Lon, Date, Time, State, Country, Protocol...) with a header row. eBird's import tool uses **eBird Record Format v3** which has no header row and a completely different fixed column order. Every row was being rejected with errors like "passerina is not a valid number" (column 2 should be Scientific Name, not Genus), "domesticus pubescens is not a valid date" (column 4 should be combined Date+Time), etc.
- Fixed to use correct eBird Record Format v3: no header row; 16 columns in order: Common Name, Scientific Name (full, unsplit), Location, Date+Time (combined "M/D/YYYY H:MM AM/PM"), State/Province (ISO 3166-2, e.g. US-MA, derived from location name), Country, Protocol, Checklist count, Duration, All Obs Reported, Distance, Area, Count (X), Breeding Code, Species Comments, Checklist Comments.
- State/Province code now derived from configured location name (matches all 50 US states).
- Count changed from "1" to "X" (presence-only) which is more accurate for acoustic detections.
- Removed UTF-8 BOM (not needed by eBird importer, caused issues).
- Scientific name no longer split into genus/species — kept as full binomial.

### Fixed (chirp-server): Diagnostics report download returned 401 Not Authenticated
- The "Download Report" button was an `<a href>` anchor which browsers don't send `Authorization: Bearer` headers with. Changed to a JS `fetch()` with the token from localStorage, then creates a blob URL for download. Works with or without auth enabled.

### Fixed (chirp-server): Diagnostics SSH mic check — No authentication methods available
- Added SSH password input field that appears when "Microphone Check" mode is selected. Password is passed to the backend as a query param. Key-based auth is still tried first; password is used as fallback if provided.
- Virtual devices (Haikubox, any device with no IP address) are now filtered out of mic checks automatically with a clear "skipped" flag rather than showing an SSH error for a device that can't be SSH'd into.

### Fixed (chirp-server): Compose Manager icon_url updated
- `icon_url` and `template.yml` updated to use `192.168.1.224` instead of `localhost` — the icon URL must be reachable from the browser, not from the server itself.

## 0.1.14.t — 2026-07-01

### Fixed (chirp-server): Diagnostics — multiple real bugs
- **`[DEBUG] :` empty log lines**: log buffer stores records with keys `ts/level/name/msg` but diagnostics code was accessing `timestamp/logger/message` (wrong keys). All log lines now display correctly.
- **`undefined/undefined/undefined/undefined` device recording counts**: `Recording.device_id` is never set during upload in the current schema, so per-device filtering always returned zero and the frontend showed `undefined` for all counts. Fixed by using server-wide totals (all recordings, since there's only one device) and clearly labeling them as server totals in the UI.
- **Device stats exception silently swallowing all data**: the `_device_stats` function was catching exceptions and returning `[{"error": ...}]` which caused every device field to be `undefined` in the frontend. Added `logger.error()` with full traceback to expose the root cause, and fixed the underlying field access issues.
- **Diagnostics crashing on fields not in all DB versions**: wrapped optional model attributes with `getattr(..., None)` and `hasattr()` guards.

### Added (chirp-server): Diagnostics — mode selector, collapsible sections, mic check, live levels
- **Mode selector**: three modes now available — "Full Report" (all checks), "Database Only" (counts and stats, fast), "Microphone Check" (SSH to device, enumerate audio cards, classify as bird/bat/excluded/unknown).
- **Collapsible sections**: every section (System, Database, Disk, Settings, Cache, Devices, Mic Check, Errors, Warnings, Logs) is individually collapsible. All expand by default, collapse on click. State not persisted (resets on re-run).
- **Microphone Check mode**: SSHes to each registered device using saved `ssh_username` and key-based auth, runs `arecord -l` to enumerate all audio cards, then classifies each as: Bird mic (ReSpeaker/XVF), Bat mic (AudioMoth/192kHz), Excluded (Unitek/C-Media USB adapter), or Unknown. Shows raw `arecord -l` output, `chirp-device` service status, and last 30 journal lines per device.
- **Live mic level meters**: after running a Mic Check, each device card shows a "Live Levels" button. Clicking it opens a WebSocket to `GET /api/v1/diagnostics/mic-levels/{device_id}`, which SSHes to the Pi and runs a Python snippet sampling each audio card at 200ms intervals. Results stream back as animated level bars with dBFS readout, peak markers, and bird/bat role tagging — all in real time without stopping the chirp-device service.
- **Report download options**: "Download Report" now supports a checkbox "Include log files" — when checked, the download fetches a ZIP containing `report.txt` + `server.log` + per-device `journal.log`, `config.yaml`, and `arecord.txt`.
- **`GET /api/v1/diagnostics/run?mode=full|db|mic`** — new `mode` query param.
- **`GET /api/v1/diagnostics/report?mode=...&include_logs=true`** — returns ZIP when `include_logs=true`.
- **`WS /api/v1/diagnostics/mic-levels/{device_id}`** — new WebSocket endpoint.

### Fixed (chirp-server): Compose Manager icon
- Added `icon_url` file to `chirp-server/` containing `http://192.168.1.224:8765/icon.svg`.
- Compose Manager reads icon from a file named exactly `icon_url` containing the URL — the `template.yml` approach used previously was not how this version of Compose Manager works.
- Server deploy only.

## 0.1.14.s — 2026-07-01

### Fixed (chirp-server): ModuleNotFoundError: No module named 'psutil' crash on startup
- `psutil` was used at module import time in `diagnostics.py` but not listed in `requirements.txt`, so it was never installed in the Docker image. The server crashed immediately on startup with `ModuleNotFoundError`.
- Fixed by making the import optional (`try/except ImportError`) — the diagnostics endpoint now starts and works correctly without psutil. System metrics (CPU %, memory, uptime, process stats) are omitted when psutil is absent, with a `note` field explaining what's missing.
- Disk usage statistics (`shutil.disk_usage`) still work without psutil and are always included.
- `psutil>=5.9.0` added to `requirements.txt` so the next Docker image rebuild will include it and system metrics will appear automatically.

### Added (chirp-server): Compose Manager autostart + icon files
- Added `template.yml` and `autostart` to `chirp-server/` for Unraid Compose Manager.
- Drop both files alongside `docker-compose.yml` in `/boot/config/plugins/compose.manager/projects/chirp-server/` — Compose Manager will then show the project with the Chirp name, icon (served from `http://localhost:8765/icon.svg`), WebUI link, and autostart enabled.
- No Docker rebuild needed for these files.

## 0.1.14.r — 2026-07-01

### Improved (chirp-server): Storage Management — clarified three-tier lifecycle in Settings UI
- Replaced the plain labeled number inputs with a structured, visually separated card that makes the three independent options unmistakably distinct.
- **Lifecycle flow diagram** at the top of the card: New recording → Archived (audio removed) → Soft-deleted (hidden) → Permanently purged — color-coded (green/amber/orange/red) so the progression and permanence are immediately obvious.
- Each tier now has its own colored header, a plain-English explanation of exactly what gets deleted and what survives, and an inline status label ("active — audio older than Nd will be removed" or "disabled") that updates live as you type.
- **Archive (amber)** — explicitly labeled "gentlest option", explains audio is removed but recording stays in list/statistics/Life List/spectrogram, and that playback/download/iNat are disabled post-archive.
- **Age-based removal (orange)** — explains recording disappears from UI, stats, and Life List entirely; explains the DB row is soft-deleted but should be treated as permanent.
- **Size-based removal (red)** — explains oldest-first deletion when directory exceeds limit, clarifies it's the same effect as age removal.
- **Cross-validation warning**: when both archive and delete thresholds are set but archive ≥ delete, a red inline warning explains that recordings would be removed before they're archived (the archive step would never fire).
- **Protected recordings** checkbox moved inside the card with a full explanation of what it protects and when to disable it.
- **Run Cleanup** result now correctly shows "archived: N" in addition to age-removed and size-removed counts.
- No backend changes — the storage_manager already implements all three tiers correctly; this was purely a UI clarity improvement.
- Server deploy only.

## 0.1.14.q — 2026-07-01

### Fixed + Expanded: Diagnostics — comprehensive system data collection
- **Error/warning split**: logs are now separated into `all`, `errors`, and `warnings` lists. Frontend shows a red banner for any errors found, a separate collapsible warnings section, and the full color-coded log tail. Report sections are split: RECENT ERRORS, RECENT WARNINGS, then SERVER LOG TAIL.
- **System metrics** (psutil): CPU core count + current usage %, memory used/total/available/%, root filesystem usage (separate from data volume), process RSS, process CPU %, open file descriptors, thread count, system uptime + boot time.
- **Database expanded**: bird/bat/haikubox recording breakdowns, activity counts for 24h/7d/30d, detection count for 24h, processing queue state (pending/processing/error), top 5 species, profiles missing photo, profiles missing calls, per-table row counts from sqlite_master, DB file path and size.
- **Disk expanded**: per-directory stats now include per-extension breakdown (e.g., recordings: .wav=N files · X MB), covering recordings/spectrograms/clips/enhanced/bat_clips/media. Filesystem stats use psutil for accuracy.
- **Settings expanded**: full settings summary including server re-analysis mode, haikubox/bat-species-ID flags, notification config, SMTP/eBird/iNat/Anthropic key presence indicators (no values), auth state, share-location flag.
- **Device data expanded**: hostname/IP, platform, OS version, chirp-device version, BirdNET backend, Coral present + form factor, mic count + names, recordings for 24h/7d/30d/all, upload errors, average confidence, last upload filename + age, config version sync state.
- **Cache section**: shows entry count, maxsize, and TTL for all four in-process caches (life_list, statistics, settings, user_token).
- **Color-coded highlights** in the inline UI: red for error conditions (queue errors, missing location), yellow for warnings (high memory, disk >75%, missing eBird key, config out of sync), green for confirmed-set API keys.
- **Download Report** endpoint now generates significantly more detailed plain-text output covering all the above sections with proper headers and alignment.
- Server deploy only.

## 0.1.14.p — 2026-07-01

### Added (chirp-server): Statistics page detections/recordings toggle
- New segmented control in the Statistics page header switches all charts between "Detections" (one count per species per recording) and "Recordings" (one count per triggered recording event). Selection persists to localStorage (`chirp:stats:metric`) and is restored on next visit.
- Backend: `GET /api/v1/recordings/statistics/full` now accepts `metric=detections|recordings` query param. In recordings mode, all count-based queries use `COUNT(DISTINCT Recording.id)` instead of `COUNT(Detection.id)` — affects top_species bar, monthly area chart, hourly bar, seasonal bar, species×month heatmap, day-of-week radar, rarest species, and busiest day. Confidence distribution and per-species confidence charts remain detection-based in both modes (they're inherently detection concepts). Cache key now includes metric so both modes cache independently.
- All chart titles, Bar/Area `name=` props, and summary card labels update dynamically to match current mode. Subtitle changes from "All-time detection analytics" to "All-time recordings analytics" in recordings mode.

### Added (chirp-server): iNaturalist submission settings persistence
- The three iNaturalist submission toggles (Include recording details, Attach spectrogram, Use enhanced audio) now persist to localStorage (`chirp:inat:prefs`) and are automatically restored every time the submission modal is opened. No more resetting toggles on every submission.

### Added (chirp-server): Diagnostics page in Settings
- New "Diagnostics" tab in Settings (admin only). Click "Run Diagnostics" to execute a comprehensive health check: DB stats (recordings, detections, species, profiles, bat recordings, iNat submissions, date range), disk usage (recordings/spectrograms/clips/bat_clips directories with file counts and sizes, filesystem total/used/free), settings summary (location, timezone, confidence threshold, API key count), per-device status (last heartbeat age, last upload, recording counts for 24h/7d/all time), and recent server log entries (last 80 lines, color-coded by level).
- "Download Report" button fetches a plain-text human-readable report from `GET /api/v1/diagnostics/report` directly — no Run required, downloads immediately as `chirp-diagnostics.txt`. Suitable for emailing or sharing for support.
- `GET /api/v1/diagnostics/run` returns structured JSON; `GET /api/v1/diagnostics/report` returns plain text. Both are JWT-protected (admin only).

### Fixed (chirp-server): Detection row cramped on mobile
- Source indicator (⚙/📡) now shows label text only on desktop (`sm:` breakpoint), icon-only on mobile. Enhanced button collapses to sparkle icon only on mobile, label hidden. Jump and Clip remain unchanged. Tighter gap on mobile prevents overflow without losing any functionality — all actions still accessible via tap, tooltips still present.

### Server deploy only (includes built frontend).

## 0.1.14.o — 2026-07-01

### Fixed (chirp-server): Tutorial scroll-spy, Back to top, and progress bar all non-functional
- Root cause confirmed: all three features used `window.scroll` / `window.addEventListener('scroll', ...)`, but the actual scrolling container is the `<main>` element (`overflow-y-auto`, confirmed at App.jsx:505) — `window` never scrolls, so scroll events never fired and scroll commands did nothing. Fixed by finding `document.querySelector('main')` as the real scroller and attaching all listeners and scroll commands to it.
- Progress bar was additionally obscured by the app header — it was `position: fixed; top: 0` which placed it behind the `60px` header. Fixed by switching to `position: sticky; top: 0` within the `<main>` scroll container, with negative margins matching `page-root`'s `28px` padding so it runs edge-to-edge. Now correctly tracks scroll position and changes color per active section.
- Back to top button now correctly scrolls `<main>` to top instead of doing nothing.
- Section nav pills and number bubbles now correctly highlight as sections scroll into view.
- Also fixed iNaturalist `_fetch_inaturalist_full` removing `rank=species` filter that was causing wrong photos for order-level taxa like Chiroptera (bat profile), and bat profile manually set to Little Brown Bat (Myotis lucifugus, the most common MA bat species) with correct iNaturalist photos downloaded locally.
- Server deploy only.

## 0.1.14.n — 2026-06-30

### Fixed (chirp-server): iNaturalist submission falsely reported "token needs refreshing" for a date-in-the-future error
- Real error from iNaturalist was `422: "date observed can't be in the future"` — nothing to do with token auth. The frontend's error classifier treated all unrecognized 422/502 responses as likely token problems (reasonable default, since expired tokens are the most common failure), but "date observed can't be in the future" isn't a token problem and sending users to refresh a valid token three times in a row is genuinely misleading. Fixed by adding `"date observed"` and `"in the future"` to the `isStructural` check so the real, actionable error message is shown directly.
- Also fixed the underlying server-side cause: `observed_at` is a UTC datetime from the DB, and if the recording timestamp is ahead of the server's local date (e.g. UTC rollover, Pi clock drift, or timezone difference), the date string sent to iNaturalist is genuinely in the future. Added a safety clamp so `observed_on_string` is never ahead of today's date — iNaturalist only needs the date, not the exact time, so clamping to today is always valid.
- Server deploy only (no device changes).

## 0.1.14.m — 2026-06-30

### Fixed (chirp-device): recordings were 2× too long and noisy — root-caused to a stereo interleave/reshape mismatch
- Real, concrete bug confirmed via actual recorded duration data: recordings were consistently `19.797s` instead of the expected `~10s` (pre-roll buffer content), exactly `2×` the correct value. Root cause: `get_stereo_recording()` returned a flat interleaved stereo array of `len(c) * 2` samples (e.g. `960,000` for `480,000` mono samples), but `recorder.py` reshaped it as mono (`reshape(-1, 1)`) when `device_count == 1`, treating both interleaved copies as sequential mono data — doubling the apparent duration and producing garbled/noisy audio since the same signal was being interpreted as two consecutive audio blocks rather than two channels of the same block. `9.898s × 2 = 19.797s` matches the real observed data exactly.
- Fixed by making `get_stereo_recording()` always return a proper `(N, 2)` shaped array regardless of device count — single-device gets L=R=mono duplicated into both channels correctly as a 2D array, not a flat interleave. `recorder.py` now always uses `n_channels=2` and writes a clean 2-channel stereo WAV unconditionally. The empty-check updated to test `.shape[0] == 0` rather than `len() == 0` to work with the new shape. Verified with a real isolated test against the exact scenario: single ReSpeaker device, 10s mono signal → correct `10.0s` duration from the fix vs `20.0s` from the old code.
- Also fixed a second, separate real bug found while investigating: `raw_buf_chunks` was sized to only `(pre_roll_seconds + 5.0) * sample_rate / chunk_size = 10 seconds` worth of chunks, but `get_stereo_recording()` was asked for `pre_roll + actual_duration = 35 seconds`. The deque's `maxlen` silently discarded everything older than ~10 seconds, so recordings were always truncated to ~10 seconds regardless of the configured `duration_seconds=30`. Fixed by sizing the buffer to `pre_roll + max_duration_seconds + 10s margin = 135 seconds`, so the full recording is always available when assembled.
- Noise issue in spectrograms (broadband green noise floor visible below 10kHz in recent recordings vs cleaner older ones): also caused by the same double-duration bug — the garbled interleave interpretation produced structured noise across the full frequency range, visible in the spectrogram as the characteristic dense green noise floor. Will be resolved automatically with this fix.

## 0.1.14.l — 2026-06-28

### Synced (chirp-device): packaged config.yaml against the user's actual live device config
- User uploaded their real, current `config.yaml` for a direct diff. Two real values had drifted from the package: `detection.birdnet.backend` (live: `"cpu"`, matching the user's explicit choice to keep Coral disabled given no working EdgeTPU model source; package still had the stale `"coral"` default) and `detection.bat_echolocation.enabled` (live: `true`, confirmed genuinely working end-to-end this session; package still had `false`). Updated the package to match both. Verified programmatically that every other config value is now identical between the live device and the package — confirmed via a structural comparison, not just a text diff, so differences in comment wording or list ordering don't produce false mismatches. The only remaining differences are comment text on `device_name_excludes` (the packaged version's wording is the accurate, current explanation from this session's investigation; the live device's comment predates the final AudioMoth-identity findings) — a documentation improvement, not a functional difference.

## 0.1.14.k — 2026-06-28

### Fixed (chirp-device): a second, genuinely separate USB audio device was still being claimed by the bird pipeline
- Confirmed real, not a stale cache artifact as initially assumed: after the AudioMoth fix re-enumerated it under its own genuine identity (`16d0:06f3`), a *third* card remained present in `arecord -l` — and survived a full reboot, ruling out the stale-ALSA-entry theory. Confirmed via `lsusb` as a real, physically-connected C-Media USB audio adapter (a "Unitek Y-247A"), unrelated to both the ReSpeaker and the AudioMoth, and not something the user had deliberately set up. Added to `device_name_excludes` alongside `"AudioMoth"`.
- Documented a genuinely confusing real coincidence directly in the config comment: `"USB Audio Device"` was both this separate adapter's actual name AND the AudioMoth's own name before it was configured (the previous device_name_excludes value, from earlier this session) — two different real devices sharing the exact same generic string at different points in this investigation. Worth knowing if this list needs revisiting again.

## 0.1.14.j — 2026-06-28

### Resolved: AudioMoth ultrasonic sample rate — confirmed working at 192kHz
- After an extended live investigation this session (PipeWire, ALSA hardware params, USB bus instability, a broken CLI config tool, raw HID protocol probing), the actual fix turned out to be the official AudioMoth USB Microphone App, run from a separate laptop with the device's physical switch in USB/OFF — confirmed working via `arecord --dump-hw-params` showing `RATE: 192000` after configuration, and via `dmesg` showing the device re-enumerating under its genuine AudioMoth vendor ID (`16d0:06f3`) with a real, descriptive product string (`"192kHz AudioMoth USB Microphone"`), replacing the generic, unconfigured `10c4:0002` Silicon Labs identity it presented before.
- This identity change has a real, direct consequence for `device_name_excludes` (added earlier this session to reserve the AudioMoth for bat-only use): the exclude string was matched against the device's old, unconfigured name (`"USB Audio Device"`), which no longer matches its new, properly-configured name at all. Updated the exclude string to `"AudioMoth"` — now confirmed correct and durable, since the device's real configured product string genuinely contains that word (unlike its prior unconfigured state, when this same assumption was checked and found wrong for the opposite reason). Verified with a real test against the device's actual current confirmed name.
- Documented in the config comment that this device's reported name has now changed twice across its configuration history (generic → configured) specifically so a future re-flash, reset, or reconfiguration isn't assumed to keep the same string indefinitely — check `python main.py --list-devices` if the bird pipeline ever appears to reclaim it again.

## 0.1.14.i — 2026-06-28

### Fixed (chirp-device): the EdgeTPU model could never be found, on ANY system not using the username "pi"
- A real, genuinely separate bug from anything else fixed this session, found via live device logs showing `chirp` looking for the model at `/home/pi/chirp-device/models/coral/...` despite the actual user being `joshsalvi` (confirmed throughout this session's logs as `/home/joshsalvi/...`). Root cause: `birdnet_coral.py`'s `CORAL_MODEL_DIR` was hardcoded to the literal string `/home/pi/chirp-device/models/coral`, completely independent of who's actually running the software — almost certainly written assuming the Raspberry Pi OS default username. Meanwhile `install-coral.sh` already correctly derives its own model directory relative to wherever the installer script itself is located, not a hardcoded path — meaning the two never intersected for any user not literally named `pi`. Even a perfectly valid model file would never have been found.
- Fixed by deriving the path the same way the installer already does: relative to the actual file's own real location (`chirp-device/chirp/birdnet_coral.py` → `chirp-device/models/coral`), guaranteed to match the real checkout location regardless of username. Verified with a real test.
- Found and fixed the identical bug in a second place while checking for others: `config.yaml`'s `bat_echolocation.events_dir` was also hardcoded to `/home/pi/chirp/bat_events`, and `bat_detector.py` reads it directly with no path-expansion of its own. Extended the existing path-expansion safety net (added earlier this session for `output_dir`/`log_dir`) to cover this nested value too.
- Went further than the original relative-path fix required: tested against the user's actual real, currently-deployed config value (the old hardcoded path, unmodified) and confirmed the existing fix's `isabs()`-based logic would NOT have caught it, since an already-absolute-but-wrong path doesn't trigger the "make relative paths absolute" logic at all — a real, honest gap caught by re-testing rather than assuming the fix covered every case. Added an explicit, narrow check that recognizes the specific `/home/pi/` pattern and substitutes the real home directory, with a clear warning logged when it fires — this protects existing already-deployed configs carrying the old hardcoded default automatically, not just fresh configs using the corrected default, confirmed with a real test against the user's exact actual current config value.

## 0.1.14.h — 2026-06-28

### Updated (chirp-device): install-coral.sh now documents the real Python 3.13 EdgeTPU package gap, with concrete numbers
- A real install on Python 3.13/aarch64 confirmed neither `pycoral` nor `tflite-runtime` has installable wheels for this Python version — `pycoral` stops at 3.11, and `tflite-runtime`'s last release with real wheels (2.9.1) only supports up to 3.9 (its newest PyPI entry, 2.14.0, exists but ships no wheel files at all). The installer now explains this directly in its own output when it's actually hit, with the real, verified numbers for the one confirmed-working alternative (installing full `tensorflow` instead: ~269MB vs ~2MB, slower startup, more RAM) and a concrete recommendation, rather than leaving this to be rediscovered. `birdnet_coral.py` does not currently support a `tensorflow`-based fallback path — noted as real, separate code work if ever worth pursuing, not implemented here given the real size/startup tradeoff and that CPU backend is already working correctly.
- Also corrected a labels-file comment that turned out to be wrong: confirmed via a real install run (`curl` exit 22, a genuine 404) that the entire `checkpoints/V2.4/` directory is gone upstream, not just the model file — the labels download will currently fail too, which is expected given everything already documented, not a separate new problem.

### Fixed (chirp-device): bat detector's default `device_name: "AudioMoth"` would never match a real AudioMoth USB Microphone
- Confirmed via this user's actual device logs across this session: AudioMoth USB Microphones commonly enumerate with a generic Silicon Labs USBXpress identity (e.g. `"USB Audio Device"`), not literally containing the word "AudioMoth" — meaning the shipped default would silently exclude the device entirely for any setup hitting this same real pattern, not just this one. Changed the default to `""` (auto-match whichever input device reports the highest native sample rate), which doesn't depend on guessing a name string at all. Verified against this user's own real, confirmed device data (ReSpeaker at 16000 Hz, AudioMoth at 44100+ Hz) that the AudioMoth is correctly selected over the ReSpeaker by sample rate regardless of its name. Combined with the existing `device_name_excludes` fix, both directions of the bird/bat device separation are now confirmed solid: the bird pipeline excludes the AudioMoth by name, the bat pipeline includes it by sample rate, neither depending on a name string that doesn't actually match this hardware.

## 0.1.14.g — 2026-06-28

### Fixed (chirp-device): install-coral.sh silently saved an HTML error page as the EdgeTPU model, crashing chirp-device on every startup
- Root-caused via extensive direct verification on a live device, not assumption: the installer's hardcoded download URL pointed at `kahst/BirdNET-Analyzer`, which has been renamed to `birdnet-team/BirdNET-Analyzer` (confirmed the old URL correctly 301-redirects there — that part still works). But the `checkpoints/V2.4/` directory containing pre-built EdgeTPU `.tflite` files no longer exists in that repo's `main` branch at all (confirmed via a direct GitHub API 404 on the directory itself, not just one file) — `curl -L` was successfully following the redirect, then correctly getting a real 404 for the missing file, which GitHub serves as an HTML page. That ~300KB HTML page passed the installer's old, too-lenient size check (which only caught files under 100KB) and got saved as if it were the real model, only failing later with a confusing TFLite-parser error inside chirp-device itself.
- Confirmed, via direct evidence rather than further guessing, that there is currently no actively-maintained source for a pre-built BirdNET V2.4 EdgeTPU model: `birdnetlib` (already working for the CPU backend) has never bundled one, confirmed from its actual installed package contents; the project's own official Zenodo archive (DOI 10.5281/zenodo.15050749) doesn't offer one either, only keras/protobuf/raven/tfjs/tflite/tflite_fp16/tflite_int8; and the community fork that historically bundled pre-compiled EdgeTPU binaries (`mcguirepr89/BirdNET-Pi`) was confirmed archived/read-only by its owner as of August 2025.
- Rather than guess at another stale URL, the installer now fails honestly: detects and removes an existing bad (HTML/undersized) file automatically, explains the real, confirmed situation in full, and lists the real remaining options — use CPU (already working, no extra steps), compile your own EdgeTPU model from the still-genuinely-available Zenodo `tflite_int8` archive using Google's `edgetpu_compiler`, or check the BirdNET-Analyzer GitHub Discussions for a current community-maintained build.
- Added the same real content check (verifying the genuine 4-byte `TFL3` FlatBuffer signature TFLite files start with, confirmed directly from TensorFlow's own source) at the actual application load point in `birdnet_coral.py`, not just the installer — defense in depth, since the installer is only one way a bad file could end up there. Verified with real isolated tests against a genuine TFLite-shaped header, the actual confirmed real-world failure case (an HTML error page), and a truncated file.

## 0.1.14.f — 2026-06-28

### Fixed (chirp-device): recording thread crashed with `FileNotFoundError: 'recordings'`
- Confirmed from a real crash on a live device. Root cause: the shipped `output_dir` default (`"recordings"`) is a relative path, with a comment claiming it's "relative to chirp-device directory" — but that depends on the process's working directory being correct at the exact moment each path operation runs, which isn't structurally guaranteed for a long-running systemd service's whole lifetime even with `WorkingDirectory` set correctly in the unit file.
- Fixed by resolving any relative `output_dir`/`log_dir` to an absolute path once at startup, anchored to the user's home directory — not left relative to CWD. Verified with a real test confirming a relative input resolves to the correct absolute path and an already-absolute path passes through unchanged. Corrected the misleading `config.yaml` comment that stated the false assumption directly responsible for the crash.

### Fixed (chirp-device): a broken `rich` install could crash logging itself while trying to log the original error
- Found in the same live crash log: a `ModuleNotFoundError: No module named 'rich.traceback'` fired *while logging the first error*, masking its full traceback. The existing fallback only caught `rich.logging` failing to import at setup time — a different, more insidious failure (confirmed live: `rich.logging` imports fine, but `rich.traceback` — lazily imported only when an actual exception is formatted — fails later, the worst possible time for a logging failure) wasn't caught at all.
- Fixed by proactively formatting a real exception through the candidate handler immediately at setup time, before it's installed — catching a broken `rich_tracebacks` path and falling back to a plain `StreamHandler` instead of only discovering the problem when something has already gone wrong. Verified the underlying structural guarantee with a real test (catching an exception raised from any handler's `emit()`, not specific to one `rich` version's internals, since the exact internal call path differs between `rich` versions and couldn't be perfectly reproduced against the user's specific installed version in this environment — noted honestly rather than overclaiming a perfect local reproduction).

## 0.1.14.e — 2026-06-28

### Fixed (chirp-device): no way to reserve a USB mic exclusively for bat detection
- Found via live debugging on real hardware: a user's AudioMoth (configured for `bat_echolocation`) was instead being silently claimed by the bird-detection pipeline, even after narrowing `device_name_hints` to exclude it. Root cause: the bird pipeline's device scan has two stages — hint-matched devices, then a deliberate broader fallback over *all* remaining real input devices (so a legitimate mic with an unexpected name isn't missed) — and that fallback isn't gated by `device_name_hints` at all, so narrowing the hints list could never have actually excluded the device on its own.
- Added a genuine `device_name_excludes` config option (`detection.audio.device_name_excludes` in `config.yaml`), checked independently of the hints list and respected by both the hint-matched and fallback scan stages, so a specific device can be reliably reserved for another pipeline (e.g. the bat detector) regardless of `max_devices` headroom. Verified with an isolated test against the user's own real, live-confirmed device names.
- Also fixed a real, stale-documentation mismatch found in the same `config.yaml` while debugging this: a comment claimed `"AudioMoth"` was already in `device_name_hints` specifically so it would dual-purpose for bird detection too — it wasn't actually present, and more importantly the underlying premise doesn't fit a dedicated bat-only setup like this user's at all. Rewrote the comment to accurately describe the real hints/excludes mechanism, and pre-populated `device_name_excludes` with `"USB Audio Device"` — the device's actual confirmed kernel-reported name (a generic Silicon Labs USBXpress identity, not literally containing the word "AudioMoth" at all, which is itself worth knowing since it's the second time a literal `"AudioMoth"` string assumption turned out not to match this real device).

## 0.1.14.d — 2026-06-28

### Fixed: expanded spectrogram modal rendered behind other content (and on top of the iNat modal when both were open)
- Same confirmed bug class as the three other modals already fixed this session: a plain `position: fixed` element (this one a CSS class, `.spectrogram-modal-backdrop`, not Tailwind utilities) with no portal, vulnerable to the same documented WebKit/Chrome/Safari ancestor-stacking quirk. Wrapped in `createPortal` into `document.body`, the same proven fix.
- The second screenshot also revealed a real, separate ordering bug once both issues are considered together: this modal's `z-index: 100` exceeded every other modal's established `z-50` convention, so even after portaling it would still always paint on top of any other open modal (exactly what the screenshot showed — it rendering over the iNat submit dialog). Lowered to `z-index: 50` to match the rest of the app.

### Changed: removed the "Submitted via Chirp" attribution line from iNaturalist submissions
- Per request.

## 0.1.14.c — 2026-06-28

### New: richer iNaturalist submissions — recording details, per-detection timestamps, spectrogram attachment, audio source toggle
- The submitted observation's description now optionally includes (on by default) recording duration, device name, and every detection in the clip with species/timestamp/confidence — not just the one species being submitted, so the description documents everything Chirp heard. Verified with isolated tests covering both the populated and minimal-description cases.
- The spectrogram (with detection-box overlays already baked in, confirmed from the existing image-generation pipeline — the boxes are already self-labeled with species and confidence, making a separate legend image redundant) can now be attached as a second observation photo via iNaturalist's real `/observation_photos` endpoint, confirmed against their public API documentation. Runs as a background task, same pattern as the existing sound attachment, so it can't block or delay the response.
- Added a real toggle between the original recording and the enhanced (noise-reduced) version for submission — defaults to original, since that's generally preferred for citizen-science accuracy. Correctly hidden for bat recordings, since the enhancement filter is explicitly tuned for bird vocalization frequencies (500Hz–10kHz) and would be actively wrong applied to ultrasonic bat calls.
- Investigated Macaulay Library as an alternative/additional audio source per request — no public API for bulk-fetching raw audio exists (confirmed via their own documentation: non-owned media aren't available for personal download outside a manual licensing process). Left a durable, discoverable note directly in the relevant source file for a future session, including what's already been ruled out and concrete options worth evaluating, rather than leaving this as an unwritten todo.

### Changed: detection list on Recordings Detail is no longer repetitive
- Reported with a screenshot showing the same species photo, name, and scientific name repeated across 9 nearly-identical cards for 9 detections of the same species. The species identity is already shown once in the group's own header row — repeating it per-detection was the actual source of visual noise, not a styling issue. Redesigned each detection row as a compact single line (timestamp, inline confidence bar + badge, source icon, Jump/Clip/Enhanced controls) and switched the list from a 2-column card grid to a single-column list, matching the new row shape. Verified with a real render against the actual reported data.

### Fixed: Tutorial scroll-highlighting didn't always work; added "Back to top" links
- Root-caused the real bug rather than re-tuning the existing implementation: the prior version picked the active section by IntersectionObserver's intersection *ratio*, which is the wrong metric when sections have very different heights (true on this page) — a long section barely scrolled into view has a small ratio and can lose to a short section that's fully visible, even though the short one isn't where the reader's attention actually is. Replaced with the explicitly correct, requested algorithm: the active section is the last one whose top edge has scrolled above the viewport's vertical midpoint, tracked via `getBoundingClientRect` on scroll. Quick-nav pills and the new per-section "Back to top" links now update the active section immediately on click rather than waiting for the scroll listener to catch up.

### Fixed: Haikubox box shown on the Devices page even when the feature was fully disabled and never configured
- Real bug, confirmed by tracing all four possible status combinations: the backend's existing `{configured: false, disabled: false}` response shape was genuinely ambiguous between "enabled but never configured" (should show the onboarding invite) and "disabled and never configured" (should hide) — both cases produced identical JSON. Added an explicit `enabled` field to disambiguate them, then applied the correct hide condition on the frontend. The already-configured-then-disabled case is deliberately left visible (existing, correct design, letting someone re-enable a feature they'd already set up). Verified all five real/edge states (never-configured-disabled, enabled-but-unconfigured, previously-configured-then-disabled, fully-configured, and the loading state) both via a real end-to-end backend test and a direct check of the frontend's hide condition.
- Also fixed a second, more fundamental bug on the Logs page found while investigating: the device list for SSH log fetching included the virtual Haikubox device row unconditionally, in every state, even when Haikubox was fully enabled and working — despite it having no real SSH access at all, since it's not a physical Pi. Filtered it out entirely, which is correct in every state, not just "hide when disabled."

### Fixed: recording duration showing differently in the header/dashboard than in the audio player ("10s" vs "0:09")
- Root-caused as a pure display-rounding inconsistency, not a data mismatch — confirmed by reproducing the exact symptom with a quick calculation: any real duration in roughly the 9.5–9.99s range would show as "10s" wherever `Math.round` was used and "0:09" wherever the player's own `Math.floor`-based formatter was used, for the identical underlying value. Standardized both the RecordingDetail header and the Dashboard live card's duration display on `Math.floor`, matching the player's existing convention (and the universal video/audio-player convention that elapsed/total time reflects full seconds actually played, not a rounded estimate).

## 0.1.14.b — 2026-06-28

### Fixed: the iNaturalist submit modal on Recordings Detail rendered behind other content
- Same confirmed bug class already root-caused and fixed once this session for the dashboard's "Seen Today" popup: a plain `fixed inset-0 z-50` modal, no portal, vulnerable to the documented WebKit/Chrome/Safari quirk where any ancestor with `position:relative` + `z-index` can clip or reposition a `position:fixed` descendant. Fixed with the same proven `createPortal`-into-`document.body` approach.
- Given this is the second confirmed real instance of this exact bug, and the second report on this exact page, proactively checked and fixed the other three modals already present in `RecordingDetail.jsx` (Edit, Share, Delete) that shared the identical vulnerable structure rather than waiting for separate reports on each — all four use the same fix now. The Delete confirmation in particular is worth having fixed proactively, since a destructive-action confirmation dialog being visually obscured is a real usability/safety concern, not just cosmetic.
- Confirmed at the source level (not just trusting a minified bundle's call count, which can legitimately collapse repeated identical references) that all five portal-based modals across the app now exist: 3 in RecordingDetail.jsx, 1 in InatSubmitButton.jsx, 1 in Dashboard.jsx.

## 0.1.14.a — 2026-06-28

### Fixed: Dashboard Summary card's bird photo was cropped, cutting off the head
- Same root cause already fixed twice this session for the BirdProfile hero — a plain `object-cover` image with no crop-safety. Applied the same proven blurred-backdrop + `object-fit: contain` treatment, verified against the actual reported photo (the full bird, previously cut off at the top, is now genuinely visible). Checked every other `object-cover` photo in Dashboard.jsx for the same latent bug — confirmed the live card's poster panel and the Seen Today grid tiles are both deliberately square (1:1), which is a fundamentally safer ratio that doesn't need the same fix, so neither was touched.

### Updated: Tutorial — content accuracy, comprehensiveness, legibility, and new animations
- Rewrote the Dashboard section to reflect what actually ships today: the poster-style "Listening now" live card, the "Seen Today" photo grid, and the new "+N more" popup — replacing a stale mockup of a flat live-badge row and generic activity chart that no longer match the real page.
- Added a new animated demo (matching the existing tap/cycle pattern already used for the Enhance-audio and navigation demos) showing the real "+N more" → popup interaction.
- Updated the Settings section with the new "Card Defaults" setting (global expand/collapse default, with the real per-card-override-always-wins behavior explained directly) and a note about the Statistics page's new grouped, single-toggle chart rows.
- Added a real, working scroll-spy (`IntersectionObserver`-driven, not decorative) that tracks which section is actually in view and drives a slim progress bar at the top of the page plus a highlighted state on the matching quick-nav pill and section card — meaningful wayfinding now that the guide covers more ground.

### Changed: Recordings Detail page — new "Blend" layout (poster hero + stat strip + per-species mini-waveforms)
- Presented three distinct mockup directions plus a blend before building anything; built the blend. Replaced the flat text header with a full-bleed poster hero using the same crop-safe blurred-backdrop treatment as the BirdProfile/Summary-card fixes, overlaid with species name, scientific name, and timestamp, followed by a real stat strip (top confidence, detection count, species count, duration — all genuine recording data, not decorative).
- Deliberately diverged from the original static mockup in one place after building the real thing surfaced a real constraint: kept the full action-button row (Share, Edit, Re-analyze, Archive, Delete, iNat submit/link — 6+ real buttons) below the hero rather than as overlay pills on the photo, since that many real actions would visibly overcrowd a pill row the way 2-3 wouldn't have.
- Added a genuinely new feature, not just a visual refresh: each species group in the detections list now shows a real mini-waveform (a slice of the recording's actual amplitude data for that species' specific detection window, fetched once and shared across all species in the list — not a decorative shape, and not re-fetched per card). Caught and fixed a real bug via an isolated unit test before shipping: short detection windows (the common case, since most BirdNET detections are ~3 seconds within a much longer recording) returned fewer than the intended 6 bars with no padding, producing visually inconsistent bar density between species cards; fixed by cycling a short slice's own values back up to 6 bars. Verified the union-of-multiple-detection-windows case too (a species detected twice in one recording correctly shows bars from both windows, not just the first).

## 0.1.13.n — 2026-06-28

### Changed: Photo Gallery moved back to its original position
- Reverted last turn's reorder per request — back to its original spot between Notes and Seasonal Presence, after Recordings and Photos. The gallery's own "Refresh" button added last turn is unaffected by the move.

## 0.1.13.m — 2026-06-28

### Changed: BirdProfile hero now shows the complete photo, never cropped, regardless of its aspect ratio
- Reported a third time, this time with a horizontal framing problem (the subject pushed to one side of a wide source photo). Built a real mockup against the actual reported photo before committing to a fix — it confirmed that for that specific image, the empty background was genuine content in the original upload, not something Chirp's cropping introduced, so no crop-bias tweak could have "fixed" it. There's also no statistically-sound default bias for the horizontal axis the way there is for vertical (photographers don't have a systematic left/right tendency the way they reliably leave headroom above a perched bird), so continuing to chase `object-position` values for every newly-reported photo wasn't a sustainable path.
- Replaced the single `object-cover` image with the standard fix for arbitrary source-photo composition (the same treatment Spotify/Apple Music use for non-square album art): a heavily blurred, scaled-up copy of the photo fills the hero edge-to-edge for the full-bleed poster look, while the complete, unmodified photo sits on top via `object-fit: contain`. The subject can no longer be cropped out on any axis, regardless of the source image's own shape. Verified with two real tests: against the exact reported photo (confirmed unchanged, as expected, since nothing was actually being cropped there) and against a genuinely portrait-oriented crop of the same source (confirmed the full photo — including detail that `cover` would have cut off — now displays correctly letterboxed against the blurred backdrop).

### Changed: Photo Gallery moved above the About section
- Per request.

### Improved: Photo Gallery now has its own "Refresh" button
- The fetch cap was already raised to 12 photos earlier this session, and the per-bird force-refresh mechanism already correctly picks up newly-available photos — but the only existing way to trigger it was the "Refresh All Data" button at the very bottom of a long page, with no indication it would affect the gallery specifically. Birds enriched before the cap increase shipped were stuck showing their old, smaller photo count with no discoverable way to get the rest. Added a scoped "Refresh" action directly in the gallery's own header, calling the same underlying full-profile re-enrichment (there's no narrower "photos only" backend action) — the tooltip is explicit that it refreshes the whole profile, not just photos, rather than implying a narrower scope than what actually happens.

### Investigated: fetching calls/songs directly from Macaulay Library instead of iNaturalist
- Not implemented — confirmed via Macaulay's own documentation that there's no public API for bulk-fetching raw audio. Non-owned media "are not available for personal download" outside their manual request/licensing process; the only sanctioned access pattern for embedding is a per-clip widget explicitly capped at "20 distinct taxonomic searches" before requiring a manual support ticket, which doesn't fit an automated per-species background job. Chirp's External Resources card already links out to Macaulay's real catalog search for the species' eBird code, which is the legitimate way to surface their audio today. If Macaulay access specifically (not iNaturalist) is a priority, the existing verified Cornell Lab contact from this project's prior outreach would be the legitimate path to ask about API access for this use case, rather than attempting to route around their stated terms.

## 0.1.13.l — 2026-06-28

### Fixed: "Seen Today" popup still rendered behind other content after the z-index fix
- Reported a second time, with another real screenshot showing actual dashboard content (not just decorative theme overlays) at full brightness over part of the modal — meaning the previous fix (lowering decorative overlay z-indexes from 9999 to 40) was a real, correct fix for a real, separate bug, but not the cause of this one.
- Root-caused properly this time by researching the actual browser behavior rather than guessing at another z-index value: WebKit/Chrome/Safari have a longstanding, documented cross-browser inconsistency (confirmed via multiple independent sources, including a WebKit bug report) where a `position: fixed` element can be clipped or repositioned by *any* ancestor that has `position: relative` combined with a `z-index` set — even with zero `transform`/`filter` anywhere in the chain, contradicting the CSS spec's stated behavior that fixed positioning should escape ancestor stacking entirely. The modal was still a DOM descendant of whichever page-level wrapper was actually triggering this, so no z-index change anywhere could have fixed it.
- Fixed by rendering the modal through a React Portal directly into `document.body` instead of inline in the component tree — this is the standard, recommended solution for exactly this class of bug (not a workaround), and sidesteps the whole problem at once: the modal is no longer a descendant of any page wrapper at all, so no ancestor's position/z-index/overflow combination can affect it, regardless of which specific element up the tree was actually responsible. Confirmed `createPortal` is genuinely present in the compiled output, not silently dropped.
- Did not retrofit this same portal pattern onto the other 14 pre-existing modals across the app speculatively — there's no concrete evidence yet that any of them are actually affected by this same browser quirk, and doing so without a real report would be unjustified scope creep. If the same visual symptom shows up on any other modal, that's independently fixable the same way.

## 0.1.13.k — 2026-06-28

### Fixed: BirdProfile hero still clipped the bird's head, reported a second time with another real screenshot
- Re-investigated rather than re-asserting the prior fix was sufficient. Found and corrected a real error in last turn's own diagnosis: the "~1958px-wide desktop screen" premise behind the `clamp()` height fix was extrapolated from a screenshot's raw pixel dimensions without accounting for the page wrapper's own `max-w-5xl` (confirmed via the actual compiled CSS: `max-width: 64rem` = 1024px), which caps how wide the hero can ever really render. The true worst-case ratio in the live app is a mild ~2.23:1, not the ~5:1 originally calculated — the `clamp()` height itself was still a reasonable fix for the genuine mobile-to-1024px range and is unchanged.
- Even at that much milder real ratio, pure center positioning still clipped the head in the newly reported screenshot — confirmed from the visible crop itself (back/wing/tail shown, head implied above the visible region) that this specific photo's subject sits in the upper portion of its source frame, a common composition since photographers often leave headroom above a perched bird. Added `object-position: center 20%`, biasing the crop toward the top of the source image — re-verified the CSS semantics carefully before changing this (a Y value closer to 0% preserves more of the top, not less; got this backwards in earlier reasoning during investigation, caught before shipping).
- Being direct about the limits of what this fixes: a top-bias is still a bet on typical composition, not a per-photo-aware crop — a photo whose subject already sits low in its source frame would now be clipped from the bottom instead. Attempted to honestly verify the fix using the real reported photo (extracted from the screenshot), but that's already a center-cropped result, not the true uncropped source, so the verification could only confirm the fix shifts the visible window in the geometrically correct direction (more top, less of the disposable perch/branch area below) — not that 20% specifically reveals the full head in the true original image.

## 0.1.13.j — 2026-06-28

### Fixed: the new "Seen Today" popup rendered visually behind other dashboard content
- Real bug, confirmed with a screenshot showing the modal sandwiched between background elements. Root cause: the modal used this codebase's existing `z-50` convention (the same one already used by 14 other modals across the app), but several purely-decorative per-theme overlays (terminal scanlines, CRT vignette, NEXRAD radar sweep, the base grain texture — all `position: fixed; pointer-events: none` `body::before`/`body::after` elements) were set to `z-index: 9999`, far above any modal in the codebase. Those overlays couldn't block clicks, but they visually painted on top of every modal, including the 14 pre-existing ones — this just happened to be the first one to get reported with clear enough visual evidence to trace.
- Fixed at the actual source rather than patching each modal individually: lowered all four decorative overlays to `z-index: 40`, comfortably below the `z-50` convention every modal in this codebase already uses, so no themed decorative effect can visually outrank real interactive UI again — fixes the new popup and the same latent bug in every other existing modal at once.

### Fixed: BirdProfile hero photos remained visibly blurry on desktop even after the crop/ratio fixes
- Real, distinct cause from the cropping issues fixed earlier — this was a resolution problem, not a framing one. The hero can display up to ~460px tall at full page width (confirmed up to ~1958px wide from prior screenshots this session), but the photo source was capped at iNaturalist's `large_url` (1024px) — a confirmed ~1.9x upscale at that width, which is exactly what produces visible softness, since `object-cover` has no extra real detail to fill the additional pixels with.
- Fixed by preferring iNaturalist's `original_url` (up to 2048px, per their own documented size tiers) for the hero photo and the gallery lightbox's full-size view — both already correctly use a smaller `medium_url`-first chain for actual thumbnails, which was already right and untouched. Added a second-layer fallback that derives the original-size URL by substituting the size qualifier in the URL path itself (`/large.` → `/original.`), per iNaturalist's own documented convention that every size variant of a photo shares an identical URL structure — this covers the case where a given API response shape doesn't return `original_url` as its own field, verified with real unit tests against both of iNaturalist's actual photo-hosting domains. At the exact width from the reported screenshot this fully eliminates the upscale (0.96x); on very wide ultrawide monitors it substantially improves but can't fully eliminate it, since 2048px is the largest size iNaturalist offers at all.

### Changed: Dashboard Summary's "Most common" bird card is now a larger, photo-forward card
- Per request — the previous compact thumbnail-and-text row left real visible empty space in its column once the three Summary columns were stretched to equal height last turn. Redesigned as a full-bleed photo card with the species name and stats overlaid at the bottom (same visual language as the dashboard's live detection card and "Seen Today" tiles), now set to genuinely fill the available column height via `flex-1` instead of floating at a small fixed size with padding around it.

## 0.1.13.i — 2026-06-28

### Fixed: Life List CSV/JSON export always downloaded `{"detail":"Not authenticated"}` instead of the real file
- Real bug, confirmed directly from the user's own uploaded export files — both contained literally that JSON error body. Root cause: the download links were plain `<a href download>` tags, which have no way to attach the app's `Authorization: Bearer` header. These two endpoints read that header directly and were deliberately never added to the auth-bypass allowlist used for browser-loaded media (images/audio) — a full life-list export is genuine personal data, not a low-sensitivity media file, so bypassing auth for it would mean anyone with the URL could download it with no login. When auth was enabled, the plain link click sent no credentials, the server correctly rejected it with 401, and the browser downloaded that rejection body as if it were the file.
- This is the exact same root cause already fixed once before in this codebase for the database backup download (`settings.backup.download`) — followed that proven pattern exactly rather than inventing a new one: a real `fetch()` with the Bearer token attached, reading the server's actual `Content-Disposition` filename, then triggering the save via a Blob URL instead of a bare anchor href.
- Verified end-to-end against the real server with auth enabled: confirmed the exact bug first (no auth header → 401 → literal `{"detail":"Not authenticated"}` body, byte-for-byte matching the user's uploaded files), then confirmed the fix (a real token → 200 → real `Content-Disposition` filename → real exported species data) for both the CSV and JSON export.
- Added real error surfacing in the UI too — a `fetch`-based download can genuinely fail (expired session, network error) in ways a plain link click never could report; previously such a failure was invisible.

### New: "+N more" tile on the dashboard's "Seen Today" grid now opens a popup instead of linking to the full Life List
- Per request. Shows every species detected today (not just the visible 8) in the same photo-grid tile style as the main grid — refactored the tile rendering into a shared component so the popup's grid can never visually drift from the dashboard's. Each tile links to that bird's profile page, same as the main grid; closes via the X button, clicking outside, or Escape.

## 0.1.13.h — 2026-06-28

### Fixed: BirdProfile hero photo regressed on wide desktop screens after the mobile crop fix
- A fixed 380px height was tuned to look right on mobile (confirmed correct via a real screenshot) but produces an increasingly extreme banner ratio as viewport width grows — confirmed by direct math: ~3.16:1 at 1200px, climbing to ~5.15:1 at a reported 1958px-wide desktop screen, the same class of crop problem already root-caused once this session for the dashboard's live card, just now showing up at the opposite end of the width range. Switched to a `clamp(380px, 48vw, 460px)` responsive height — re-verified the floor preserves the exact mobile height already confirmed correct (every common phone width still resolves to 380px), while the ceiling caps the worst-case desktop ratio at 1958px down to ~4.26:1 instead of letting it scale unbounded with a single fixed number.

### Changed: Dashboard's daily/weekly Summary card columns now stretch to equal height
- Reported directly with a screenshot: the bird-card column, the chart column, and the rarest-species column each sat at their own natural content height inside a grid row that was already correctly stretching all three columns equally — the grid track was right, but none of the columns' own content was set up to fill the height the grid gave it, so the three visibly ended at different heights despite occupying the same row. Made each column a full-height flex column with its main content area set to `flex-1` (the chart) or pushed to the bottom via `mt-auto` (the detection/recording stat tiles), the same fix pattern already proven correct for `PairedRow` earlier this session — confirmed the relevant compiled CSS (`items-stretch`, `h-full`, `flex-1`, `mt-auto`) are all real, standard rules before considering this done.

### Changed: Statistics' Rarest Species + Busiest Day grouped into one shared collapsible row
- Same `PairedRow` treatment already applied to the other four chart pairs this session. Both halves were previously independently conditionally rendered (a deployment might have rarest-species data but no busiest-day record yet, or vice versa) — preserved that through the refactor via a new `singleColumn` option on `PairedRow`, so a row with only one real half to show doesn't render an empty second grid column.

## 0.1.13.g — 2026-06-28

### Fixed: a third, distinct source of mobile horizontal scroll — found via real DevTools output from the user's own running page, not guesswork
- The user provided the actual `Element.scrollWidth > viewport` diagnostic output, which is what made this fixable directly: it listed `page-hero -mx-7 -mt-7 px-7 pt-7 pb-5 mb-6` (confirming the device was running a build that predates the previous fix, not that the previous fix was wrong) and, separately, a bare `text-sm truncate` with no other classes — that second one pointed straight at the dashboard's recent-comments list.
- Root cause: the row above each truncated comment body (author name + "on" + the bird species name, e.g. "on Black-and-white Warbler") had zero width constraint on any of its three spans. A long, unbroken species common name with no natural wrap point could force that row wider than its container — and because nothing in an unconstrained row can shrink, that width increase propagated to the row's parent `div` despite it already having `min-w-0`, dragging the *correctly*-constrained `<p className="text-sm truncate">` below it along to the same overflowing width. This is exactly why DevTools flagged the `<p>` itself: the actual cause was its unconstrained sibling row above it, not the truncated element.
- Fixed by constraining both dynamic-length spans individually (`truncate min-w-0` on each, `maxWidth: '40%'` on the author name specifically so a long username and a long species name can't both claim unlimited space), with the static `"on"` separator kept `flex-shrink-0` so it's never itself squeezed.

## 0.1.13.f — 2026-06-28

### Fixed: recording title card's displayed duration could diverge from the actual recording
- Real, fully root-caused bug. The device computed `duration_seconds` for its metadata sidecar from wall-clock elapsed time (`recording_end - recording_start`), entirely separate from the actual number of audio samples written to the WAV file moments later. `get_stereo_recording()` can legitimately return fewer samples than requested — the rolling buffer may not have accumulated enough yet (e.g. right after startup), or for two-device setups its per-channel buffers can drift to slightly different lengths and get clamped to the shorter one — and neither case was ever reconciled back into the reported duration. The server then stored whatever the device claimed with zero verification.
- **Device-side root-cause fix**: `duration_seconds` is now derived from the real number of samples actually written to the WAV file (`len(audio_out) / sample_rate`), not the wall-clock estimate. Verified with an isolated test reproducing the exact confirmed failure mode (buffer returning fewer samples than requested) — old behavior would report 30.0s, new behavior correctly reports 28.4s, matching the real file.
- **Server-side cross-check (defense-in-depth)**: the upload endpoint now independently re-verifies the device's reported duration against the real uploaded WAV file via `soundfile`, the same trusted approach the separate manual-upload path already used — corrects and logs a warning on any mismatch over 50ms, so even a future device-side regression can't silently reach the title card. Verified end-to-end: a device falsely claiming 8.0s against a genuinely 5.0s file is correctly stored as 5.0s.
- **Retroactive repair**: new `POST /api/v1/recordings/repair-durations` endpoint re-reads the real WAV file for every already-uploaded recording (or one specific recording via `?recording_id=`) and corrects any stored `duration_seconds` that diverges from it by more than 50ms. Supports `?dry_run=true` to preview corrections without writing. Skips archived recordings (audio already deleted) and missing files. Verified end-to-end: dry_run reports without writing, a real run corrects and persists, archived recordings are never touched, and re-running after a fix correctly reports zero further corrections.

### Fixed: a second source of mobile horizontal scroll, found after the first round of `min-w-0` fixes
- Real, confirmed via direct arithmetic on the actual CSS rather than guesswork. `.page-hero`'s negative margin (`-28px` each side) was hardcoded to match `.page-root`'s desktop padding, but `.page-root` switches to `16px` horizontal padding on mobile (`max-width: 640px`) with no matching override on `.page-hero` — so on mobile the hero bled `28px` past its container while only `16px` of padding existed to absorb it, a persistent `12px`-per-side overhang past the real viewport edge on every single page load (the hero renders unconditionally at the top of every page, unlike the previous live-card bug which only showed up conditionally). Added the missing mobile breakpoint override, matching `.page-root`'s own mobile value exactly. Also removed redundant Tailwind utility classes (`-mx-7 -mt-7 px-7 pt-7 pb-5 mb-6`) that were layering the identical desktop-only values on top of the same element from the JSX side — confirmed identical via the compiled output (`1.75rem` = `28px`) — removing them eliminates a second, fragile source of the same number that could have silently undone this fix later depending on stylesheet ordering.

### Changed: Today's/This Week's Summary now appears above the stat cards row
- Per request. Dashboard order is now: live detection card → Seen Today → Daily/Weekly Summary → stat cards (Recordings/Species/Detections/Last Detection) → chart + top species → recent recordings.

## 0.1.13.e — 2026-06-28

### Changed: paired Statistics charts now share a single collapsible row instead of two independent cards
- Reported directly, with a screenshot: when only one card in a 2-up row was collapsed, the earlier `items-stretch` fix correctly matched its box height to its still-expanded neighbor — but that just produced a mostly-empty, awkwardly-stretched card next to a full chart, which read as broken rather than intentional.
- Replaced that approach for all four genuine 2-up pairs (Detections by Month + Hour of Day; Seasonal Distribution + Day of Week; Confidence Distribution + Time of Day; Top Active Hours + Detection Summary) with a new `PairedRow` component: one shared header spans the full row width with a single toggle, and both charts' bodies show or hide together. A collapsed row now shrinks to one compact header bar with zero empty space, instead of leaving a stretched, mostly-blank card. Standalone full-width cards (Top Species, Life List Growth, Confidence by Species, the Species×Month Heatmap, Rarest Species, Busiest Day) were already correct on their own and are untouched.
- Each `PairedRow` gets its own real `cardState` entry (e.g. `stats:row-monthly-hourly`), independent of the two charts it contains, and still respects the global expand/collapse default and the per-row override exactly like every other card — visually verified against the actual compiled CSS (not just inspecting the code) that a collapsed row renders as a single bar with no leftover height, and an expanded row correctly shows both charts side by side under the shared header.

## 0.1.13.d — 2026-06-28

### Fixed: dashboard had a small horizontal scroll on mobile, usually when the live detection card was showing
- Real bug, reported directly (no screenshot needed — root-caused from the description alone: "usually when the large recent recordings header is active" pointed straight at the live card's "Also in this clip" row). The species-name span in that row had `truncate` but no `min-w-0` — in a flex row, `truncate`'s `overflow:hidden` only actually clamps content once the element is allowed to shrink below its intrinsic content width, and a flex item's default `min-width` is `auto`, not `0`. A long joined species list (e.g. "House Finch, American Robin, Scarlet Tanager") could force that span — and therefore the row, the card, and the page — wider than the viewport, exactly producing the reported horizontal scroll on mobile whenever a live detection had multiple other species in the same clip.
- Audited every other `truncate` usage in the same file for the identical latent pattern (`truncate` + a flex-shrink role with no `min-w-0`) rather than just patching the one that had visibly manifested. Found and fixed two more real instances (the Top Species sidebar list and the dashboard's own top-species row) that hadn't yet produced a visible symptom only because single species names are rarely long enough to trigger it — same underlying bug, lower probability, fixed consistently rather than left as a latent risk. Confirmed every remaining `truncate` instance in the file is either already correctly guarded by `min-w-0` on the actual shrinking element, or sits inside an absolutely-positioned, width-pinned container where the bug can't occur at all.

## 0.1.13.c — 2026-06-28

### Fixed: live card's "Xs ago" badge too small; species/scientific name truncated on mobile ("Americ…", "Turdus migrator…")
- Real bugs, reported from a real screenshot. The "ago" badge was `text-xs`, bumped to `text-sm`. The name/scientific-name column used a forced single-line `truncate`, which on a narrow mobile viewport (where the 180px photo panel eats a large fraction of the available width) clipped real names mid-word. Removed the forced truncation and switched both lines to `clamp()`-based responsive font sizing that scales down on narrow screens and allows wrapping onto a second line instead of being cut off — reads far better for longer names than an ellipsis ever could. The photo panel itself is now also responsive (`clamp(110px, 28vw, 180px)`) so the text column gets proportionally more room on small screens instead of staying fixed at a size tuned for desktop.

### Fixed: BirdProfile hero photo had the same crop bug as last version's dashboard live card
- The hero header used a hardcoded `objectPosition: 'center 22%'` on a roughly 3.3:1 banner (260px tall against a typically 700px+ wide card) — the same root cause already fixed once on the dashboard's live card this session: no single fixed crop bias survives an extreme banner ratio across arbitrary source photo framing. Confirmed directly from a reported screenshot showing the bird's head and eye pushed off the top edge entirely. Unlike the dashboard card, this hero is intentionally a dramatic full-bleed poster treatment matching the rest of the page's design language, so switching to a side-by-side panel (like the dashboard fix) would have been the wrong call here. Instead: increased height (260px → 340px) to give the crop more room, and switched to true vertical centering, the most robust default across arbitrary photo compositions.

### Fixed: Photo Gallery thumbnails sometimes rendered as thin, mostly-cropped-out slivers
- Real bug, reported with a screenshot showing a thumbnail cut down to a sliver of just the bird's head. Root cause: `aspect-square` and a hardcoded `maxHeight: 200` directly conflicted — `aspect-square` wants the tile exactly as tall as it is wide, but `maxHeight` clamped it short-and-wide instead once the real rendered tile width exceeded 200px (confirmed by calculating realistic 2-column mobile grid tile widths, which were well over 200px), and `object-cover` then cropped the source photo down to whatever fit that squished, non-square box. `aspect-square` alone is sufficient and correct; removed the conflicting `maxHeight`.

### Changed: collapsing one card in a paired Statistics row no longer leaves the row looking visually broken
- Reported directly: collapsing one card next to its still-expanded neighbor left a short card sitting at the top of a tall grid row with empty space below it — visually read as a layout glitch even though nothing was technically wrong with either card. Root cause: `items-start` on the grid prevented the row from stretching the shorter card to match its taller neighbor. Switched both Statistics grid containers to `items-stretch` (the CSS Grid default), and updated `UnifiedCard`'s `stripe` variant to be a flex column internally so a collapsed card's own background and header actually fill that stretched row height gracefully, rather than just leaving dead space inside a taller box. All Statistics cards already default to expanded (`ChartCard`'s own `fallbackOpen` default is `true`, confirmed no call site overrides it), satisfying "all stats cards expanded by default" directly.

### Changed: set deliberate per-card expand/collapse defaults across Bird Profile and My Profile
- Previously several cards had no explicit `fallbackOpen` at all and silently inherited whichever global default happened to be set. Set explicitly, by request: Seasonal Range Map, About, Taxonomy, Seasonal Presence, Conservation, and Example Calls & Songs now default open (headline/core content); External Resources and Notes now default closed (secondary/situational); Photo Gallery, Observation Heatmap, Recordings, and user Photos keep their previously-established deliberate states (open/closed respectively, based on either explicit prior request or genuine loading cost).

### Improved: Field Guide (regional library) load time
- Root-caused a real per-row cost in `get_regional_library`: a synchronous `os.path.exists()` filesystem stat call on every matched `BirdProfile` row, unbatchable, running on every single page load for up to 1000-2000 species. Confirmed this check was unnecessary — not just slow — by finding that a second loop later in the very same function (appending life-list birds missing from the regional checklist) already trusted `photo_path` without any existence check at all; the two loops were inconsistent with each other. `photo_path` only changes during enrichment, a rare deliberate background event, not on every request, so re-verifying it synchronously in the request path was paying a real, avoidable cost. Benchmarked the isolated cost of 400 such calls on this environment's local disk (0.67ms — negligible here), but production runs on Unraid array/network-mounted storage where `stat()` latency can be meaningfully higher than local SSD; removing the check is a safe, real fix regardless of the exact magnitude in any specific deployment. The actual `/photo` endpoint still does its own real existence check before serving a file, so the only failure mode if a file is ever deleted out-of-band is a broken `<img>` icon, not a crash or security issue.

## 0.1.13.b — 2026-06-28

### Fixed: live detection poster card's photo was cropped awkwardly, cutting off the bird's head
- Real bug, reported with a screenshot. Root cause: the photo was stretched full-bleed across the entire card width with a hardcoded `objectPosition: 'center 25%'` copied from BirdProfile.jsx's hero header without re-checking it suited this card's very different shape — on a wide desktop viewport this card is roughly 6:1+ width:height, an extreme banner ratio no single fixed crop bias can handle well for a portrait-oriented bird photo. Confirmed by extracting the actual visible region from the reported screenshot and measuring its real aspect ratio (2.5:1 even before accounting for the full page width) — no `object-position` tweak fixes a ratio that extreme.
- Redesigned the layout instead of re-tuning the crop percentage: photo now sits in a fixed 180×180 square panel on the left, with species name, confidence, clip duration, device, and the "Also in this clip" row laid out to its right — giving every photo a sane, predictable 1:1 crop target regardless of the card's overall width or the source photo's own orientation. Visually verified against the actual reported photo (extracted from the screenshot) before and after, confirming the bird's head, eye, and beak are now fully in frame.

## 0.1.13.a — 2026-06-28

### New: unified per-card expand/collapse system across all four card-bearing pages, with a global default + per-card override setting
- Previously three separate, inconsistent mechanisms existed: BirdProfile.jsx's `CollapsibleCard` (a hardcoded `defaultOpen` prop per usage, zero persistence — every page load reset every card regardless of what the person had toggled last time), Settings.jsx's own bespoke `Section` + a private `chirp_settings_collapsed` localStorage key (real persistence, but always-collapsed-by-default with no way to flip that), and Statistics.jsx's `ChartCard` / UserProfile.jsx's `Section` (no collapse capability at all — every card was always fully expanded).
- New `lib/cardState.js`: one localStorage-backed store for the whole app. Two layers, in priority order — a per-card override once a person has explicitly clicked a specific card's header (remembered forever after, regardless of anything else), falling back to a global default ("Expanded" or "Collapsed", configurable in Settings → Display Preferences → "Card expand/collapse default") for any card that's never been individually touched. A `fallbackOpen` escape hatch lets specific cards request a deliberate per-card starting state independent of the global default — used for the Photo Gallery (explicitly requested to default open) and for cards with a real cost to loading by default (Observation Heatmap loads Leaflet + external tiles; Recordings and the user-submitted Photos card both fetch/render on mount) — all three keep their previously-deliberate behavior even though the underlying mechanism changed.
- New `components/UnifiedCard.jsx`: one shared component, three visual variants (`bordered`, `stripe`, `plain`) matching the three distinct looks already in use across the four pages exactly, so converting each page only required swapping which variant it asks for — no visual changes to any existing card's appearance. `Settings.jsx`'s real jump-to-section feature (scrollIntoView by DOM id) was a real constraint here: those exact DOM id strings predate this change and other code depends on them, so they're preserved exactly via a separate `domId` prop, distinct from the new cardState key.
- One-time migration (`migrateLegacySettingsCollapse`, run once at app boot alongside the existing theme-application side effect) folds any of a person's real existing Settings collapse preferences into the new unified store under `settings:`-namespaced keys, rather than silently resetting them — a read-and-merge, not a destructive migration, confirmed idempotent (re-running it doesn't clobber a real new-system override) by direct test.
- Verified with 9 real logic tests against the actual module (global default, override-beats-default, fallback-vs-override priority, reset behavior, migration correctness and idempotency) using a minimal localStorage polyfill — not just a successful build.

### Fixed: dashboard "Listening now" card got permanently stuck on "Loading waveform…"
- Real bug, reported with a screenshot. Root cause: the waveform fetch's `.catch(() => {})` silently swallowed any failure with no fallback UI state — and a real, plausible failure mode exists for a recording that's only seconds old: `get_waveform` 404s if the WAV file isn't fully flushed to disk yet, a genuine race for the most-recent recording specifically (the live card's entire reason for existing).
- Replaced the waveform entirely with a poster-style redesign per request: the top-confidence species' real photo as a full-bleed background (always available the instant the recording row exists, no file-flush race), confidence, clip duration, device name, and — only when genuinely true, computed from data already on the recording rather than any new fetch — which other distinct species were also detected in the same clip, shown as overlapping avatar chips with a "View →" link through to the recording. No backend changes needed; every field used (`top_species_photo_url`, `detections[].bird_photo_url`, `duration_seconds`, `device_name`) already existed on `RecordingOut`.

### Changed: dashboard stat cards no longer single out "Detections" with a solid accent fill
- Per feedback that the bright accent-colored card looked out of place. All four stat cards (Recordings, Species, Detections, Last Detection) now share one consistent tint instead of three different icon colors plus one solid-fill "featured" treatment.

### Changed: Dashboard's daily/weekly Summary card header now states and controls the active period directly
- Previously read as a plain "Summary" title with a separate pair of pill buttons to its right — functionally fine, but didn't make the card's actual subject ("today" vs "this week") clear from the header alone. The header now reads "Today's Summary" or "This Week's Summary", with the time-period word itself the clickable control that switches periods — removes the separate redundant button pair entirely in favor of one integrated control.

### New: real `:active` press feedback on cards and buttons (previously `:hover`-only, which never fires on touch)
- `.card-hover` (used by stat cards, the live detection card, and the recordings grid — confirmed by checking every usage) gets a genuine press-down scale on `:active`, with matching overrides for the themes (`paper`, `plate`, `fieldnotebook`) that deliberately opt out of all card motion. `.btn-primary`/`.btn-secondary`'s `:active` rule previously just canceled the hover lift back to neutral on press (`transform: none`) — changed to an actual press-down scale instead, since canceling-to-neutral was a missed opportunity for real tactile feedback, not a deliberate "no feedback on press" choice.

## 0.1.12.f — 2026-06-28

### Fixed: GBIF range map tab had no legend or attribution at all
- `ebird_st` already had a real, exact-RGB-matched 4-color legend (confirmed against `SEASON_COLOURS` in the backend rendering code); the genuine gap was `gbif`, which had no entry in the frontend's `LEGENDS` table and no attribution line. Fixed with an honest gradient legend rather than a fabricated discrete swatch list — confirmed via GBIF's own published map styles documentation that `classic.poly` (the style Chirp actually requests) is a real yellow→red density ramp, not a categorical map like AAB/BirdLife/S&T, so a "Breeding/Non-breeding" swatch legend would have misrepresented what's actually rendered. Also stopped the frontend from requesting `source=wikipedia` from the legend endpoint when viewing the `ebird_st`/`gbif` tabs — wasted work, since neither tab ever reads that response.

### New: two-finger pan + pinch-to-zoom for range maps on touch devices
- Previously only mouse drag/wheel were wired up; touch had zero handlers. Two-finger drag now pans (mirrors the existing zoom>1 gate on mouse-drag panning), pinch now zooms using the same [1,4] clamp the wheel handler already uses. Deliberately not single-finger pan — that needs to keep scrolling the page normally on mobile. Researched `touch-action` semantics properly before implementing: confirmed via the W3C pointerevents spec discussion (issue #159) that "let 1 finger scroll, let JS own 2 fingers" is a known, unresolved cross-browser ambiguity, and that `touch-action` is evaluated by the browser at the moment a touch begins, not reactively mid-gesture — so a conditional value that only flips to `none` once two fingers are already down would not reliably catch the first pinch attempt in every browser. Used the standard, reliable pattern instead: `touch-action: none` permanently scoped to just the map widget itself (the same trade-off real interactive map/canvas components use), not the whole page.

### Fixed: hero photo header — attribution badge too large/intrusive, scientific name unreadable against photo
- Reported directly from a real screenshot. The attribution badge (`top-3 right-3`, `bg-black/60`, full-size text, unconstrained width) was wrapping to two lines and covering part of the bird's face. Shrunk to a small, truncated, much lower-opacity badge. The scientific name had no background treatment at all and was genuinely illegible against busy photo backgrounds (confirmed in the reported screenshot — "Buteo platypterus" was invisible against branches). Both the common and scientific names now sit on a translucent dark backing strip plus a subtle text-shadow, so they stay legible regardless of what's behind them in the photo. Visually verified with a real rendered mockup built from the actual reported photo (not just inspecting the code) before shipping.

### Improved: more bird photos, gallery expanded by default, fixed blurry thumbnails
- Raised the iNaturalist extra-photo fetch from 5 photos (`taxon_photos[1:6]`) to 12 (`[1:13]`) — the real, binding cap on "more photos," not the frontend's display slice, which was never actually reached. `PhotoGallery`'s `defaultOpen` flipped from `false` to `true` as requested (the user-submitted `BirdPhotoGallery` — a different feature with its own upload dropzone — intentionally left collapsed by default, since always showing an upload prompt on every profile wasn't part of this request).
- Root-caused the actual blurry-thumbnail bug rather than guessing: confirmed via iNaturalist's own published photo-size documentation that `square_url` is a fixed 75×75px crop, while `medium_url` is 500px and `large_url` is 1024px. The thumbnail fallback chain previously dropped straight from `medium_url` to `square_url` when a given photo entry lacked a medium size — silently serving a 75px image that then gets CSS-upscaled 2-3x across the gallery's ~150-220px grid tiles, which is always visibly blurry. Fixed the fallback order to try `large_url` before ever touching `square_url`, for both the gallery thumbnails and the main per-bird `photo_url` (which every other view — Life List, Regional Library, Dashboard — already reads from, so this one backend fix improves photo quality everywhere without needing per-component changes).

## 0.1.12.e — 2026-06-28

### Fixed: switching range map tabs (or reloading the page) re-fetched/re-rendered a map from scratch even when it had already been fetched moments earlier
- Root cause: the on-demand `/range-map/fetch` endpoint had no concept of "is there already a cached file for this source" at all — it unconditionally queued a full background re-fetch (Playwright/GeoTIFF render) on every single call. The frontend's `handleFetchSource` already had a `force` parameter (used by the explicit refresh button), but it was never actually passed to the network call — both `api.js`'s `fetchRangeMap()` and the backend route itself were missing `force` entirely, so there was no way to distinguish "user explicitly asked to refresh" from "user is just clicking back to a tab they'd already loaded."
- Fixed in three coordinated places: (1) the backend route now checks for an existing, non-trivial cached file at the exact same path the background fetch itself writes to (confirmed identical sanitization/path logic by direct comparison, not assumption) and returns immediately without queuing any work if found and `force` wasn't passed — and if that source isn't the profile's currently-active one, it re-points `range_map_url`/`range_map_source` at the existing file synchronously, so switching back to a previously-fetched tab is instant; (2) `api.js`'s `fetchRangeMap()` now actually forwards `force` instead of silently dropping it; (3) `BirdProfile.jsx`'s poll loop now short-circuits immediately on a `"cached"` response instead of waiting through a pointless 2-second poll interval for data that's already known.
- Verified end-to-end against the real server in the exact reported scenario: pre-seeded a cached S&T file, simulated switching to a different tab (which changes `range_map_source` in the DB), then called the fetch endpoint again for the original source with no `force` — confirmed `"cached"` status in 68ms with the profile correctly re-pointed at the existing file, no background task queued. Separately confirmed `force=true` still queues a real fetch regardless of cache state, and a species with no cached file at all still queues a real fetch without needing `force`.

### New: Dashboard redesign — layered stat cards, a live waveform card for the most recent detection, and a "Seen today" species photo grid
- Stat cards now sit at slightly different elevations (subtle per-card vertical offset) instead of four identical flat boxes, and the Detections stat — the one that best represents "the system is actively working" — is now a solid accent-filled "featured" card instead of an outlined one, using the theme's existing `--btn-primary-text` token for correct contrast (confirmed populated by all themes, not assumed).
- New live card appears whenever the most recent detection was within the last 5 minutes: shows a real waveform (not decorative bars) from the actual most recent recording via the existing `/recordings/{id}/waveform` endpoint at a small point count, plus the real top species name, photo, and confidence from that recording's actual detection data.
- New "Seen today" photo grid sourced from a new `species_today` field added to `/recordings/statistics/dashboard-summary`'s daily/weekly summary — previously that endpoint computed the full per-species list internally but only ever returned the single most-common bird plus a bottom-5 rarest list, discarding the rest. Each tile shows a real photo (when the species has one) and an honest "NEW" badge driven by a genuine per-species `MIN(trigger_timestamp)` lookup — a species is only flagged new if its first-ever detection at this location falls within that summary period's window, not a fabricated indicator. Grid caps at 9 visible tiles with a real "+N more" tile linking to the Life List for the rest.
- Note: this dashboard work resumed from a prior in-progress edit that had been left with an incomplete component (`LiveDetectionCard`'s function body cut off mid-implementation, no closing brace) — caught immediately via a real brace-balance check and a real `vite build` before continuing, rather than assuming the file was in a clean state.

## 0.1.12.d — 2026-06-28

### Fixed: "Refresh All Data" couldn't see S&T/GBIF maps fetched via the per-bird tab, causing unnecessary re-fetches
- Diagnosed from a real ~2-hour production log Josh provided, not assumption. The log showed the same bird's eBird S&T map being fully re-rendered three separate times by the on-demand per-tab endpoint (`chirp.api.birds`) while a bulk `enrich-all` run was active elsewhere in the same window — each write going to a path like `/app/data/media/birds/acadian_flycatcher/range_map_ebird_st.png`, while the bulk pass's own write for the *same* bird, earlier in the same log, went to `/app/data/media/birds/birds/Acadian_Flycatcher/range_map_ebird_st.png`.
- Root cause confirmed by reading all three directory-construction sites in the codebase: `_prefetch_secondary_range_maps` (added in 0.1.12.b/c) used a third, incompatible convention — `media_dir/birds/Title_Case_Name/` — never reused anywhere else. The on-demand S&T/GBIF endpoint (`_fetch_range_map_bg`) and the existing AAB/Macaulay/Wikipedia downloader (`_download_range_map`, already serving most birds' primary tab in production) both use `media_dir/lowercase_safe_name/`, confirmed identical by direct comparison test. `_prefetch_secondary_range_maps` was the outlier, not the other two — fixed it to match them exactly, using the same `re.sub` sanitization `_download_range_map` already uses, rather than introducing a fourth convention or assuming a different existing helper (`_species_media_dir`, used for photos/calls) was the right one to reuse — confirmed by direct test that helper does *not* lowercase and would have produced a fourth mismatching path.
- Effect of the bug: the bulk recency check (`profile.range_maps_prefetched_at` + `os.path.exists` on the expected file) could never find a file the on-demand tab had just written, since it was checking an entirely different directory — so every "Refresh All Data" run re-fetched eBird S&T (and GBIF) from scratch for any bird whose map tab had ever been opened manually, even seconds earlier. This was the opposite of the intended "skip if already fresh" behavior the recency check exists for.
- Note: `profile.range_map_url` is what the serving endpoint (`get_range_map`) actually reads to display a tab, and that was never affected by this bug — it's set correctly by whichever fetch path runs. The bug was purely about the bulk *recency check* and *wasted re-fetches/orphaned files on disk*, not about anything being served incorrectly to a person looking at a profile page.
- Verified end-to-end against the real, fixed method (not a reimplementation): called `enrich_profile(force=True)` through the actual production entry point, confirmed the BirdLife file landed in the directory that now matches the on-demand convention exactly, then called it again with `force=False` immediately after and confirmed `range_maps_prefetched_at` stayed unchanged — i.e. the second call correctly skipped re-fetching rather than redoing the work.
- A real, pre-existing, separate quirk was also traced (not a bug, but worth a note for whoever reads `_resolve_range_map` next): it's fully gated by a global `range_maps_enabled` setting that, on a fresh/never-configured `AppSettings` row, defaults to disabled — this caused a misleading "nothing happened" result in an early test pass before `AppSettings` was created with the flag explicitly set, and is the kind of thing worth checking first if range maps ever appear to silently do nothing on a fresh install.

## 0.1.12.c — 2026-06-28

### New: "Refresh Range Maps Only" is now real (was a disabled next-version placeholder in 0.1.12.b)
- Added `maps_only` parameter to `BirdEnricher.enrich_profile()`/`_do_enrich()`. Skips Wikipedia article fetch, iNaturalist photo/sounds/conservation-status, and seasonal frequency — the genuinely non-map-related steps — but deliberately keeps scientific-name resolution and eBird taxonomy/species-code lookup, since `_resolve_range_map` and the eBird S&T/Macaulay prefetch both depend on those identifiers already being populated. Skipping them too would have silently produced no map at all for any bird not already fully enriched once — confirmed this dependency by reading `_resolve_range_map` and the secondary prefetch step before writing the skip logic, not assumed.
- A `maps_only` pass does **not** set `enrichment_complete = True` (confirmed every read site of that flag first — it's used to decide whether a bird still needs a full enrichment pass; a maps-only run correctly leaves that decision untouched either way) but does update `last_enriched`, since a real pass did run and commit.
- Caught and fixed a real regression in my own first draft before shipping it: an early version of this change called `_resolve_range_map()` unconditionally on every `_do_enrich()` pass instead of only when the map was missing or a refresh was forced — that function has no internal "skip if already resolved" guard of its own (it always tries AAB → Macaulay → Wikipedia from scratch), so the unconditional call would have made *every* routine, non-refresh enrichment re-run AAB's Playwright session on every bird, every time. Restored the original `not profile.range_map_url or force` outer guard (with `maps_only` always forcing it, since that's the point of the button) before testing.

### New: `POST /api/v1/birds/enrich-all/maps-only` endpoint
- Shares the exact same progress-tracking dict, concurrent-run lock, and per-bird iteration loop as `/enrich-all` (refactored both into one `_run_bulk_enrich()` helper rather than duplicating the thread/locking machinery) — only the `enrich_profile()` call differs by mode. The status dict gained a `mode` field (`"full"` | `"maps_only"`) so the same `/enrich-all/status` polling endpoint serves both buttons.
- The two endpoints share one lock, not two independent ones: starting a maps-only run while a full refresh is active (or vice versa) correctly returns `409`, the same as two clicks of the same button. Verified live: triggered maps-only, confirmed a concurrent full-refresh attempt got `409`, confirmed `mode` was reported correctly while running, then ran a full refresh immediately after the maps-only run finished to confirm the shared lock releases cleanly between different-mode runs in sequence.

### Settings: the "Next version" placeholder button is now a real, working button
- Both buttons now disable while *either* kind of run is active (matching the shared backend lock), each show their own live progress label and animation while their own mode is running, and each show a mode-appropriate completion message. Progress bar and percentage are shared UI driven by whichever mode is currently active, labeled "(maps only)" when relevant.
- Verified end-to-end against the real built bundle: confirmed the new button text and endpoint call are present in the compiled output, confirmed the old "Next version" badge text is completely gone, and ran the full maps-only → full-refresh sequence live against the actual server.

## 0.1.12.b — 2026-06-28

### Fixed: "Refresh All Bird Data" never actually refreshed eBird S&T or GBIF range maps
- Traced via real code reading, not assumption: `_prefetch_secondary_range_maps()` (the function "Refresh All Data" calls per bird to eagerly cache every map tab) only ever covered BirdLife and iNat Geomodel. eBird Status & Trends and GBIF were each only reachable through their own single-profile, on-demand `POST /{profile_id}/range-map/fetch?source=...` endpoint — i.e. only by a person manually clicking that specific tab on one bird at a time. Confirmed by grepping every call site of the underlying fetch functions before writing any fix.
- Added both to the same prefetch step, following the exact pattern already established for BirdLife/geomodel: gated by the same per-source `range_map_sources` setting (S&T defaults to off, matching its existing "(testing)" checkbox default in Settings; GBIF has no checkbox today and was already unguarded at its endpoint, so stays unguarded here too), skipped if already cached recently unless forced, never overwrites the primary displayed map/tab — only pre-caches each source's own file so opening that tab is instant.
- Neither addition touches `profile.range_map_url`/`range_map_source` (the primary tab), matching existing BirdLife/geomodel behavior exactly — this is purely about every *tab* being fresh after a refresh, not changing which one is shown by default.

### New: real progress tracking + progress bar for "Refresh All Bird Data"
- The bulk refresh previously fired a detached background thread and returned once, with the UI showing a static "✓ Queued N birds" message with no further feedback — no way to tell if it was still running, how far along it was, or which bird was currently being processed.
- Added a `GET /api/v1/birds/enrich-all/status` polling endpoint backed by a real in-process progress dict (same plain-module-level-dict pattern as the existing `_enriching_now` set in `bird_enricher.py` — appropriate for this single-process SQLite/NullPool deployment), tracking `running`, `total`, `done`, `current_name`, `started_at`, `finished_at`, and `errors`.
- Added a concurrent-run guard: a second `POST /enrich-all` while one is already running now returns `409` instead of starting a second thread against the same rows. Verified with a live test (seeded birds, real concurrent POST, confirmed 409).
- Settings now polls this endpoint (every 2s while running, same `setInterval`/`clearInterval` pattern as the existing `GeomodelDownloadPanel`), checks on mount too (so reloading the page mid-refresh still shows the live bar instead of losing it), and renders a real percentage progress bar plus the currently-processing bird's name — not a fake/static spinner.
- Full flow verified end-to-end against the real running server with `TestClient` and 5 seeded birds: confirmed real percentage climb (0→20→40→60→80→100%), real `current_name` updates per bird, clean finish state, and the 409 concurrent-run guard.

### Changed: Settings card renamed "Bird Data and Range Maps"
- Was "Data Management" — renamed for clarity now that this card explicitly covers every range map source, not just generic data housekeeping.

### Added (UI placeholder, not yet functional): "Refresh Range Maps Only" button
- A range-maps-only refresh (skip Wikipedia/iNat/eBird-taxonomy/sounds/frequency, only re-run `_resolve_range_map` + the secondary prefetch step) would need a new parameter threaded through `enrich_profile()`/`_do_enrich()`, a new endpoint, and matching frontend wiring — assessed as real, non-trivial work, not a quick add. Per explicit instruction, deferred to next version rather than rushed. The button is present now but disabled, clearly labeled "Next version" with an explanatory tooltip, rather than silently missing or silently broken.

## 0.1.12.a — 2026-06-28

### Fixed: device-side OLED button watcher crash on gpiod 2.x
- `chirp-device/chirp/display.py`'s Argon ONE button watcher used the gpiod 1.x Python API (`gpiod.Chip("gpiochip0")`, `.get_line()`, `LINE_REQ_EV_FALLING_EDGE`), which gpiod 2.0 removed entirely in a full rewrite of the bindings. `requirements.txt`'s open-ended `gpiod>=1.5.0` pin let 2.x install silently, so the button watcher crashed with `FileNotFoundError` on `gpiochip0` on any device that picked up gpiod 2.x (confirmed via a real production traceback; root cause confirmed against the actual installed gpiod 2.5.0 source before patching, including verifying every new API call against the real package — `request_lines`, `LineSettings`, `Edge.FALLING`, `Bias.PULL_UP`, `wait_edge_events`, `read_edge_events`, `release`).
- A second, independent bug compounded this: `_try_start()` only caught `ImportError`, so the `FileNotFoundError` from the broken v1 call died silently inside an already-started daemon thread, and the sysfs fallback never ran. Fixed by opening the gpiod line request synchronously (on the calling thread, before spawning the watcher thread) so any real failure is caught and correctly falls through to the sysfs fallback path.
- `chirp-device/requirements.txt`: pinned `gpiod>=2.0.0,<3.0.0` to match the rewritten v2 API now in use and prevent a future major-version bump from silently breaking this the same way.
- Confirmed on the real device (`gpiodetect`/`gpioinfo`) that `gpiochip0 [pinctrl-rp1]` is in fact the correct chip owning GPIO 27 on this Pi 5 — the crash was an API mismatch, not a wrong chip name.

### Config: ReSpeaker + Coral TPU deployment (AudioMoth deferred)
- `chirp-device/config.yaml`: `detection.birdnet.backend` set to `"coral"` (Coral USB Accelerator now plugged in). `respeaker.mode: auto` and `bat_echolocation.enabled: false` were already correctly set for ReSpeaker-only operation with AudioMoth dormant-but-ready; no changes needed there. Coral model path (`/home/pi/chirp-device/models/coral/...`) is a fixed convention matched by `install-coral.sh`, not a config key — confirmed no separate path setting was needed.

### Noted, not fixed (pre-existing, out of scope this session)
- `pyflakes chirp/respeaker.py` reports `undefined name 'np'` at line 480 — this is `numpy` referenced only inside quoted type-annotation strings (`"np.ndarray"`) on a function that imports `numpy` lazily inside its own body. Harmless at runtime (annotations aren't evaluated), confirmed pre-existing via diff against the originally uploaded zip (byte-identical, not introduced this session). Flagging honestly rather than silently fixing unrelated code or silently ignoring a real lint finding — worth a one-line fix (hoist the import or use `from __future__ import annotations`) in a future session.

## 0.1.11.z — 2026-06-26

### Investigated and rejected: Sibley and Audubon as AAB replacements
- Sibley's range maps only exist in paid books/apps — no public web source exists to fetch from at all.
- Audubon's field guide explicitly attributes its range maps to a licensed, copyrighted Kaufman field guide ("All rights reserved") — and checking two real species pages (including a known long-distance migrant) found no actual map image rendered on the page anymore, just descriptive text. Nothing to build against, legally or technically.
- Also checked USGS's BBA Explorer: a legacy 2014-era tool with only one example species map in its entire gallery, not a real per-species source.

### Fixed: a real, currently-live bug found while investigating — disabling AAB didn't actually disable AAB
- While checking why Macaulay Library (already partially integrated as AAB's silent fallback) wasn't more reliable, traced a real bug: unchecking "All About Birds" in Settings writes to the granular per-source `range_map_sources` dict, but the actual enrichment function only ever checked a different, single global flag — never that dict. Unchecking AAB had zero effect on whether AAB actually ran. Fixed and verified with a real test.
- Gave Macaulay its own independent gate in the same fix, rather than only ever running as AAB's invisible fallback with no way to control or even identify it as the active source.

### New: Macaulay Library as a real, full frontend tab
- Added a dedicated camera-icon tab, its own refresh path (a simple Cornell CDN lookup keyed by eBird species code — no Playwright session needed, unlike AAB), its own loading/error states, and its own attribution line and legend handling (Macaulay has no embedded color-coded legend at all, unlike AAB's illustrated maps).
- Broadened the existing AAB/S&T cross-contamination guard to cover Macaulay too, rather than writing a parallel set of checks.

### New: drag-and-drop map tab ordering in Settings
- Added a `range_map_source_order` setting (backend column, migration entry, API plumbing) and a real native-HTML5 drag-and-drop reorderable list in Settings — no new dependency needed for a simple 4-5-item list. Verified the setting round-trips correctly through a real update-then-fresh-GET test.
- `BirdProfile.jsx`'s map tabs now sort by this order instead of a fixed array order; any tab id missing from a saved order (e.g. a newly-added source on an older config) falls back to the end rather than being silently hidden.

### Changed: Field Guide icon is now an open book
- Swapped the nav icon from a location pin (which never fit a reference/lookup feature) to `BookOpen`, already available in the icon library and unused elsewhere in the app.

### Improved: all 11 themed logos now have animated sound waves; Terminal and Oscilloscope redesigned
- Rendered the current Terminal and Oscilloscope logos directly to confirm the complaint before changing anything: Terminal's ASCII-character art was confirmed illegible at actual small tab-icon scale (just scattered green dots, not the clear bird the same art showed at large preview scale) — character art fundamentally doesn't scale down. Oscilloscope's 8px pixel grid read as a vague amber blob with a barely-visible single-pixel eye.
- Redesigned both: Terminal is now a bolder monospace-block bird (thick rectangular strokes, not literal characters) that reads clearly at both large and small scale; Oscilloscope moved to a coarser, more deliberate 12px grid with a much larger, high-contrast eye, modeled after a classic 16-bit sprite rather than an organic pixel-blob. Verified both at simulated small icon scale before finalizing, not just at large preview size.
- Added a real animated sound-wave element to all 11 logos (previously zero had one), each styled to match its own theme rather than reusing one generic wave: flat geometric strokes for Cornell, loose pencil lines for Field Notebook, blocky VU-meter bars for Terminal, soft blurred watercolor washes for Paper, sharp two-tone strokes for Mono, engraved cross-hatch for Plate, retro equalizer bars for Oscilloscope, confident contour lines for Aviary, glowing red strokes echoing the eye color for Dracula, radar-sweep concentric arcs for NEXRAD, and glowing UV-purple strokes for Moth Trap.
- Caught and fixed a real bug while reviewing the finished file: Terminal's and Oscilloscope's keyframe names were the only two not namespaced with each logo's unique per-size id, unlike every other logo — a real collision risk if two instances of the same logo render at different sizes on the same page simultaneously (e.g. header + Settings drag-list). Fixed to match the established convention.
- Threaded a real `animate` prop through `ChirpLogo.jsx`'s dispatcher to every themed logo, previously hardcoded to static-only.
- Also caught two stale references while reviewing Settings.jsx for consistency: the Macaulay entries in both the tab-order list and the enable/disable checklist were still using a borrowed eBird S&T icon and a "no separate tab yet" comment, both incorrect now that Macaulay has its own real tab and icon from this same session.

## 0.1.11.y — 2026-06-26

### Fixed: real root cause of the eBird S&T missing-breeding-band bug (probably)
- A real three-way screenshot comparison (BirdLife, iNat, S&T for the same species) made the bug concrete for the first time: the breeding band was nearly absent from the S&T render while both other sources agreed on a broad breeding presence. Not migration biology — a real compositing bug, finally visible.
- Researched the actual GDAL/ebirdst convention rather than continuing to guess: real per-band season names live in the non-standard `TIFFTAG_GDAL_METADATA` tag (code 42112, an XML blob keyed by band "sample" index) — not the baseline `ImageDescription` tag (270) this code has been reading since the very first version of this feature. Confirmed directly: built a test file with real GDAL band-naming XML and verified `page.description` returns a useless auto-generated JSON string while tag 42112 holds the real names — this matches every production log's `descriptions=['']` finding exactly.
- Added real tag-42112 parsing, with `page.description` and the positional order-assumption kept as fallbacks in that order. Caught and fixed a real bug in my own first draft while testing it: the metadata is keyed by per-band "sample" index, but the confirmed-real file structure has only ONE physical page containing all 4 bands (channels-last) — keying by page index instead would have only ever checked sample 0 and silently missed samples 1–3. Fixed by building the description list after the true band count is known, not before.
- Added explicit, unambiguous logging for both outcomes (tag found vs. genuinely absent) — the next real S&T render's log will state directly whether this fixes the underlying file, rather than requiring another round of indirect inference from band labels.
- Considered switching this whole pipeline to a shelled-out R script using the official `ebirdst` package, which knows the real band-naming convention with certainty and needs no guessing. Weighed honestly: real costs (new R + GDAL/GEOS/PROJ runtime in the Docker image, a Python↔R subprocess bridge, an entire rendering pipeline rebuilt from scratch) against a fix that's specific, already written, and verifiable right now in this sandbox — versus an R path I can't test here at all (no R runtime, no CRAN access). Decided to ship the targeted fix and treat the R rewrite as the real fallback if the next production log shows tag 42112 is genuinely absent on actual eBird files too.

## 0.1.11.x — 2026-06-26

### New: tutorial now explains what the seasonal likelihood percentages actually mean
- Traced the real source before writing anything: the underlying number behind every frequency bar (Field Guide and Bird Profile alike) is the fraction of eBird checklists in your region that reported the species that month — the same metric the Merlin app shows as its blue bars, fetched from eBird's bar chart API with iNaturalist's monthly histogram as a fallback. `current_likelihood` isn't a separate metric; it's just that same array's current-month value, pre-extracted for convenience.
- The genuinely non-obvious part, confirmed from the actual ranking code rather than assumed: the Field Guide's Very Likely/Likely/Possible/Rare labels are NOT fixed percentage cutoffs — they're a relative rank against every other species shown for that month. The same raw frequency can earn a different label in different months (a modest frequency might be "Very Likely" in a quiet winter month, "Possible" during peak migration). Added this explanation to the Field Guide tutorial section.
- Also confirmed the Bird Profile's own Seasonal Presence chart works differently — no cross-species ranking at all, just that one species' raw frequency scaled against its own yearly peak. Added a shorter note there clarifying the distinction and cross-referencing the fuller Field Guide explanation, rather than duplicating it.
- Separately confirmed "Detected Here" is an independent flag (Chirp's own real detections) from the regional eBird frequency percentage — a species can show as both "Detected Here" and "Rare" at the same time, which the tutorial now states explicitly rather than leaving as an implicit assumption.

## 0.1.11.w — 2026-06-26

### Fixed (definitively this time): eBird S&T render corruption — confirmed 100% reproduction rate from real logs
- A real log showed the exact same `shape=(1, 11484, 4)` corruption happening for every single species checked (Red-eyed Vireo, Indigo Bunting, Broad-winged Hawk, repeatedly) — not intermittent, not load-related. The "fix" shipped two sessions ago for a different 4D scenario (multiple overview/pyramid pages) was real and still correct for that case, but never addressed this one — confirmed by the log's own absence of the "filtered N overview pages" line, meaning there was genuinely only one page involved, not several.
- Traced precisely: a single GeoTIFF page with real multi-band data, read by `tifffile` in **channels-last** layout `(H, W, bands)` — a standard GDAL convention for multi-sample-per-pixel TIFFs — produces shape `(1, H, W, bands)` after stacking. The existing 4D handler (`data[:, 0]`) was written for a *different* 4D case and assumed the wrong axis was the spurious one, slicing out a single row of the real height dimension and discarding the rest — reproduced the exact corrupted shape from the log byte-for-byte with this precise mechanism, not a guess.
- Fixed by checking *which* axis is actually the singleton before squeezing, rather than assuming. Verified against both real 4D cases this code now needs to handle correctly: the original separate-pages scenario from three sessions ago (still works), and a genuine multi-sample-per-pixel TIFF built with `tifffile` itself (now correctly recovers all 4 real bands at the real 5562×11484 resolution instead of a corrupted 1-pixel-tall sliver). The previous code's own size-sanity-check correctly caught the corrupted output as too small to use and reported `Range map fetch FAILED` — an honest, correct signal, just not specific enough to find the real cause without this trace.
- AAB's 403 errors in the same log are the same persistent Cloudflare block described several sessions ago, not a regression — that assessment holds.

## 0.1.11.v — 2026-06-26

### Fixed: full sweep of the hardcoded-pastel-text contrast pattern
- Did the full sweep requested after the last fix: found 61 hardcoded hex colors (8 distinct values) across 16 component files, all light pastels meant for dark backgrounds, all confirmed via real contrast math to fail badly (1.0–1.8:1) against every light theme. Computed darker replacements for each, individually verified to pass 4.5:1+ against Cornell's cream (the lightest theme, so the others pass with more margin).
- Since these are inline `style={{ color: '#hex' }}` literals, not Tailwind classes, the existing class-based override mechanism couldn't fix them directly. Added 8 new shared CSS variables instead (`--pastel-green`, `--pastel-red`, etc.), defined once with the original light value (correct for dark themes, confirmed 8.4–12:1 there) and overridden to a darker tier for the 5 light themes only. Converted all 61 call sites to reference these variables.
- Also extended the existing class-override mechanism to the 6 `badge-*` CSS classes (green/blue/purple/yellow/red/teal), found to have the identical problem.
- Caught a real CSS syntax error while writing the new comment block: a literal `*/` inside the comment text (from referencing "text-gray-*") prematurely closed the comment itself, breaking the entire stylesheet build. Reworded to avoid it.

### Improved: 4 of the 11 themed logos
- Oscilloscope: fixed a crude unblurred glow rectangle into a real soft phosphor bloom, added a highlight pixel for dimension.
- Mono: replaced the flat vertical light/shadow split with a diagonal one (more cinematic noir lighting) and added rim-light edge highlights — caught and fixed a draft that briefly introduced a third grey tone, which would have violated the theme's own strict two-color swatch definition.
- Terminal: cleaner ASCII proportions and a subtle phosphor-glow accent dot.
- Field Notebook: added ruled notebook page lines, a second construction guideline, and a small handwritten-style "sp.?" annotation for more genuine field-journal character.

### Range map code review — 2 real bugs found and fixed
- A band could be silently DROPPED from the eBird S&T render entirely (not mislabeled — genuinely missing data) when some bands had real season names from file metadata but others didn't, since the no-real-names-found bands were never added to the season mapping at all. Confirmed with a test: 2 of 4 real bands vanished from a render despite containing real abundance data. Fixed to fall back to the positional guess per-band, only for whichever specific bands lack a real name, with a precise warning naming which bands are affected.
- The basemap reprojection code read geo-referencing tags from `tif.pages[0]` (literally the first page in file order) while the actual pixel data uses a size-filtered page list (confirmed two sessions ago that overview/pyramid pages can appear at any position) — these could be different pages, silently misaligning the basemap if an overview page happened to come first. Fixed to use the same page reference for both. Verified directly: built a test file with deliberately wrong geo-tags on the first (overview) page and confirmed the fix reads the correct page's tags instead.
- Cross-checked the GeoPackage binary header parser (envelope size table, flag bit layout) against the authoritative OGC specification directly — confirmed correct, no bug found there. Considered and declined to "fix" a theoretical mixed-endianness WKB edge case, since real-world GDAL output (confirmed via `gpkg_ogr_contents` in the actual schema) never produces it.

## 0.1.11.u — 2026-06-26

### Fixed: more low-contrast text on light themes — Recording Detail and Submit-to-iNaturalist
- Confirmed from a real screenshot (Cornell Lab theme): the bird name next to its photo was invisible, the confidence label ("86% High") was too faint, and the "Submit to iNaturalist" button text was barely legible. Last session's fix was correctly scoped to `BirdProfile.jsx`'s map area specifically, but this is a different file with the same underlying problem — not a regression.
- Computed real WCAG contrast ratios rather than eyeballing it: `text-gray-100` (the bird name) measured 1.0–1.2:1 against light-theme backgrounds, even worse than the `-200`/`-300`/`-400` shades an earlier session already fixed — it was simply missing from that fix's class list. Added it. The confidence-label colors (`text-chirp-400`/`text-cyan-400`/`text-yellow-400`) measured 1.25–1.71:1; mapped the high-confidence tier to the theme's own `--accent-600` and the others to `--text-secondary`, since this app has no separate semantic blue/amber scale to draw from.
- `InatSubmitButton.jsx` used a hardcoded `#86efac` (light mint-green, meant for a dark background) in 6 places — replaced all of them with `var(--accent-600)`, the same theme-aware darker-accent variable already used elsewhere (`LifeList.jsx`, `RegionalLibrary.jsx`) for exactly this "colored text that needs to read on any theme" case.
- Found the same hardcoded-pastel pattern in the `badge-green`/`badge-blue`/`badge-yellow`/`badge-purple`/`badge-red`/`badge-teal` CSS classes (also failing badly, 1.3–1.7:1) — flagging this but not fixing it here, since it's a broader, separately-scoped cleanup beyond what was reported this time.

## 0.1.11.t — 2026-06-26

### Fixed (for real this time): iNat geomodel "always one color" — it's not a bug
- Got the actual schema from a real production database via the debug endpoint: `fid, geom, taxon_id, parent_taxon_id, name, rank, iconic_taxon_id, iconic_taxon_name, geomodel_version`. There is no score, probability, or likelihood column in this product at all — confirmed directly, not guessed.
- This settles something three sessions of column-name guessing couldn't: iNaturalist's geomodel range product is a binary presence polygon per taxon ("the species occurs somewhere within this shape"), not a per-cell abundance gradient. A uniform-color render was never a fallback standing in for missing data — it's the correct, complete representation of what this data actually contains.
- Removed the entire score-detection/normalization premise from the renderer: no more guessing column names, no more degenerate-variance detection, no more neutral-color fallback pretending a gradient might exist. Every polygon now renders in one confident color, with a legend that says "Estimated range" instead of implying a High/Moderate/Low scale that was never real. Fixed the matching frontend legend overlay to use the exact same color as the backend render.
- Verified against a GeoPackage built with the literal real-world column list and sample values from the debug output, not a guessed approximation.

## 0.1.11.s — 2026-06-26

### Fixed: iNaturalist/BirdLife map text unreadable on light themes
- The map tab attribution lines, refresh hints, and copyright captions used Tailwind's hardcoded `text-gray-600`/`text-gray-400` classes, completely independent of the active theme's color variables. These read fine on dark backgrounds but were low-contrast and washed out against light themes like Cornell Lab's warm cream background.
- Fixed all 8 occurrences in the map tab area to use `var(--text-tertiary)`/`var(--text-secondary)`, the same theme-aware variables used everywhere else for this kind of muted caption text. Scoped to the map area specifically that was reported; the rest of this file has the same hardcoded-grey pattern in ~46 other places, which is a separate, larger cleanup not attempted here.

### New: 11 hand-drawn themed logos, one per "Distinct Look" theme
- Cornell Lab, Field Notebook, Terminal, Paper, Mono, Plate, Oscilloscope, Aviary, Dracula, NEXRAD, and Moth Trap each now get their own logo artwork matching that theme's real visual identity, instead of every theme reusing the same orange gradient bird: a flat geometric carnelian-red mark for Cornell, a loose pencil sketch with cross-hatching for Field Notebook, genuine monospace ASCII art with a blinking cursor for Terminal, a soft blurred watercolor wash with fine ink linework for Paper, a hard noir light/shadow split with no gradients for Mono, fine parallel-hatch engraving in a decorative frame for Plate, blocky 8px-grid pixel art for Oscilloscope, confident stippled-shading museum-plate linework for Aviary, a cape-winged bird with a glowing red eye and fang-tinted beak for Dracula, a stencil-cut silhouette with a targeting-reticle eye and HUD corner ticks for NEXRAD, and a UV-blacklight glow halo with moth-dappled spots for Moth Trap.
- Rendered every one to PNG and visually checked before writing the final component, rather than shipping unverified SVG.
- Wired in at the `ChirpLogo` component itself (not at each call site) so every existing usage — Dashboard hero, Login screen, Tutorial demo — automatically gets the right themed logo with no changes needed at the call sites. Watches the `[data-theme]` attribute via `MutationObserver` so the logo swaps live if the theme changes without a page reload. Themed variants are static by design (a pencil sketch shouldn't wing-flap); themes without a custom logo keep the original animated gradient bird unchanged.

## 0.1.11.r — 2026-06-26

### Fixed: eBird S&T corrupted shape and scrambled legend colors — two more real bugs
- A real production log showed the S&T renderer producing shape `(1, 11484, 4)` instead of the correct `(1, 5562, 11484)`. Root cause: real eBird GeoTIFFs (Cloud-Optimized GeoTIFF format) embed reduced-resolution overview/pyramid pages alongside the genuine band page(s) — last session's page-stacking fix assumed every page was a same-sized band, and stacking mismatched shapes together either crashed or, for certain layouts, silently produced a corrupted combined shape. Fixed by filtering to only full-resolution pages before stacking, confirmed against a synthetic file combining both structures.
- Separately, every band was mapping to "breeding" regardless of its real season — `"breeding"` is a substring of `"nonbreeding"`/`"prebreeding_migration"`/`"postbreeding_migration"`, and the alias-matching loop checked it first, so every non-breeding-family description matched the wrong, shorter alias before reaching its own correct one. Fixed by checking longer aliases first. This is very likely the real explanation for the scrambled legend-vs-map colors reported this session.
- The iNat geomodel's uniform color in the same report is most likely the neutral-color fallback (added two sessions ago) correctly firing, not a new bug — the real database schema still doesn't match the guessed column-name candidates. The existing `/api/v1/settings/geomodel/debug` endpoint can confirm this directly against the real file.

### Fixed: Statistics page showed 20 species instead of the real count
- Found the actual root cause: `full_statistics()` never returned a `total_species` field at all. The frontend's fallback to `top_species.length` silently reported the chart's query LIMIT (capped at `max(20, heatmap_limit)`, defaulting to 20) as if it were the real species count. Added a real, unlimited count query. Verified end-to-end with 80 real species in a test database — confirmed the bug reproduces exactly (20) and the fix resolves it (80).
- Also found and fixed a related inconsistency: comment counts included comments on soft-deleted recordings, which aren't cascade-deleted from the database. Excluded those for consistency with every other stat on the page.

### Fixed/improved, smaller items
- All four phases of the "tap to enhance" tutorial demo now last the same duration (1200ms each) — the phase right before the sparkle/enhance moment was previously much shorter than the others.
- The ultrasonic-mic info box in Settings now collapses by default, leaving just the warning headline visible until expanded.
- Fixed copy that referenced "the threshold below" in a description attached to a toggle whose related threshold control doesn't exist on screen until that same toggle is switched on — now states the actual setting name and default directly.
- The daily digest send-time picker now shows the equivalent local time (using the configured timezone) alongside the raw UTC hour, in both the caption and each dropdown option, computed against the real current date so DST is reflected correctly.
- Bird profile hero photos now crop biased toward the top of the frame rather than dead-center, since bird photography conventionally frames the subject in the upper-to-middle portion — this won't be correct for every photo without real object detection (a much larger feature, not implemented here), but is a meaningful improvement over centering for the common case.

## 0.1.11.q — 2026-06-26

### Fixed: eBird S&T file selection — definitively confirmed from a real log
- A full file listing in a production log settled what last session could only theorize about: the selected file was `.../seasonal/brwhaw_abundance_full-year_mean_3km_2023.tif` — the single-layer full-year product, not a real multi-band seasonal file.
- Root cause: the highest-priority scoring check matched `"seasonal"` against the file's full path, including its *directory* (`seasonal/`), not just the product type in the filename itself — a full-year file sitting in a folder called `seasonal/` won the top score despite explicitly saying "full-year" in its own name. The exclusion for "full-year" existed but only applied at the lowest-priority fallback tier, which this file never reached because it already won earlier.
- Fixed by rejecting "full-year" universally, before any other scoring, so it can never outscore a real seasonal file regardless of which directory it's listed under. Added an explicit, clearly-logged fallback to a full-year file specifically for species where no real seasonal file exists at all — a single-layer map is still better than none, but this is now a deliberate, visible choice rather than an accidental one. Verified both outcomes end-to-end against the real filenames from the log.

### Fixed: iNat geomodel crash — `ValueError: could not convert string to float: 'species'`
- A real traceback showed `score_col` had matched a taxonomic rank column (containing text like "species", "genus") instead of a numeric score — confirmed this was `"rank"`, one of the broader candidate names added last session specifically to find more real score columns, which turned out to be too generic and collided with a common, unrelated column purpose.
- Removed the riskiest overly-generic candidates (`rank`, `value`, `weight`, `density`, `occurrence`, `prediction`) and kept only names specifically about a numeric likelihood. Also added a defensive `try`/`except` at the actual conversion site, so even if a future guess collides with another non-numeric column, one bad value can no longer crash the entire render — it falls back to the neutral placeholder for that row instead. Verified both fixes directly against the exact crashing value from the traceback.

## 0.1.11.p — 2026-06-26

### Fixed: iNat geomodel map only ever shows yellow, never green
- Traced the math precisely: the color for each hexagon comes from normalizing its score against the min/max of all hexagons for that species. If the score column couldn't be matched in the file's schema (a real possibility — column names are guessed against a fixed candidate list, since there's no way to inspect the actual schema without the real downloaded file), every hexagon silently got an identical hardcoded placeholder score. With every score identical, the normalization always lands on 0 — which is the first color in the gradient: yellow. Confirmed this exact mechanism end-to-end with a synthetic GeoPackage that has no matching score column at all.
- Fixed two ways: rendering now uses a clearly neutral grey-blue (not on the yellow→green gradient at all) when there's no real score variance to show, so it's never confused with genuine "low likelihood" data again; and added clear, always-on logging of the resolved schema (which column names actually matched) so this is diagnosable directly from production logs going forward instead of requiring a separate manual debug call. Also expanded the column-name guess list with more plausible real-world names, in case the real schema simply isn't covered by the original short list.

### Investigated: eBird S&T "only one layer" — likely real per-species data, now more diagnosable
- The reported `bands=1` is consistent with eBird's own documentation: seasonal files have one layer per season that passed expert review, and a season can be entirely omitted if it failed review — so this could be genuinely correct for an individual species. But seeing it for two different common, well-studied species in the same session is suspicious enough to take seriously.
- Couldn't fully resolve this without a real downloaded file to inspect (no network access to eBird's servers from this environment), but made it properly diagnosable: the exact filename selected is now logged directly alongside the band count, instead of only appearing in a separate, easy-to-miss log line at download time.

### Fixed: a real regression — AAB tab 404ing instead of falling back to Wikipedia
- Confirmed from a log: the exact AAB cross-contamination fix from two sessions ago had its own bug. When the cached map was S&T-sourced, it cleared `range_map_url` entirely — which prevented execution from ever reaching the existing Wikipedia-fallback logic further down in the same function (only reachable via a non-empty URL), so a species that should have successfully fallen back to Wikipedia (and had, on an earlier request before the S&T tab was visited) instead hit an early 404.
- Fixed by going straight to the same fresh-Wikipedia-lookup fallback the "dead AAB URL" case already uses, rather than wiping the URL and hoping something else picks up the pieces. Verified end-to-end: the exact regression scenario (S&T-contaminated cache, failed AAB refresh, a real Wikipedia map available) now correctly redirects instead of 404ing, and the genuine dead-end case (no Wikipedia available either) still degrades to a clean 404 as before.

## 0.1.11.o — 2026-06-26

### New: prettier map source icons, sleeker Dashboard
- Redesigned all four map source icons with real gradients and depth (binoculars, leaf+magnifier, globe, bar chart) instead of flat single-color line icons. Caught and fixed a latent bug while polishing these: each icon's gradient `id` was derived from its `size` prop, so two instances at the same default size would collide on the same SVG `id` and silently break each other's gradient. Fixed with React's `useId()` instead.
- Dashboard polish: each stat card icon now has its own tinted gradient background instead of all four sharing one flat color; a small live-pulse indicator appears next to the greeting when the last detection was genuinely within 5 minutes (data-driven, not decorative); active period/summary toggle buttons get a subtle theme-aware glow; rarest-species rows and the most-common-bird card got entrance animation and a touch more depth that the rest of the page already had; the empty "no recordings yet" state got a gentle floating icon and a warmer message instead of a static glyph.

### Reliability assessment: which map sources are actually most trustworthy
- Did an evidence-based pass rather than a guess: counted real fixes needed per source across the full changelog history, and checked each source's underlying architecture.
- iNat Geomodel is the most reliable — no browser scraping, no API key, a direct stable file download. Its bugs were crash-level and are now fixed and well-tested, not the recurring "the website changed shape" problem the scraped sources keep hitting.
- eBird S&T is structurally the most robust (a real documented REST API, no scraping at all) but is the least battle-tested of the four — it was only wired up two sessions ago, and the basemap reprojection is still unverified against a real downloaded file since this environment can't reach eBird's servers to test one.
- AAB has a real, recurring failure mode (Cloudflare blocking server-side downloads of its own hotlinked URLs) that keeps getting worked around rather than actually fixed — the fragility is structural.
- BirdLife is the least reliable of the four: most total fixes needed, and distinctively, two wrong root-cause assumptions before landing on the real fix for the same bug — a sign the site is hard to reason about reliably from outside. Also the slowest in practice (~10-16s per fetch, confirmed in production logs).
- No new, currently-unresolved map errors found beyond what's already documented in-code as a known verification gap (the S&T basemap, noted above).

## 0.1.11.n — 2026-06-26

### Fixed: AAB tab could show the eBird S&T map after visiting that tab
- Confirmed real: the AAB tab's image request had no way to tell the backend which source it actually wanted — the endpoint just served whatever `range_map_url`/`range_map_source` happened to be cached, regardless of which tab asked. Once the S&T tab successfully populated those fields (its own independent background fetch), switching back to AAB kept showing that same S&T-sourced image.
- Added a `source=aab` parameter the frontend now sends; when the cached source is `ebird_st`/`gbif`, the backend forces the same re-resolution path the explicit refresh button already used, rather than serving the mismatched file.
- Caught a real gap while testing this: if that re-resolution itself fails to find a usable AAB image, the original code would still fall through and serve the stale S&T file anyway — closed that by refusing to serve it in that case too, returning a clean 404 instead of the wrong map.
- Verified all three paths end-to-end against the real endpoint function: refresh fails → clean 404, not the S&T image; refresh succeeds → serves and persists the new AAB image; already-correct AAB cache → completely unaffected. Also confirmed the underlying S&T data in the database is never destroyed by an AAB tab request, so switching back to S&T afterward still works.

## 0.1.11.m — 2026-06-26

### New: original icons for each map source toggle, replacing generic emoji
- Replaced the 🗺/🌿/🐦/📊 emoji on the AAB/iNat/BirdLife/S&T tab pills and the Settings map-sources checklist with small, purpose-built SVG icons (binoculars, a leaf with a magnifying glass, a globe, a bar chart).
- These are original glyphs, not reproductions of any organization's actual logo — the relevant domains aren't reachable from this build environment to source real brand assets, and recreating a trademarked mark from memory wouldn't be accurate or appropriate regardless. Each icon evokes that source's general focus instead.
- Rendered all four to PNG for visual verification before shipping — confirmed each reads clearly at a small size and is visually distinct from the others.

## 0.1.11.l — 2026-06-26

### New: real spectrogram thumbnails for list/grid views
- The recordings list grid and Dashboard's recent-recordings cards were fetching the exact same full-resolution spectrogram PNG used on the detail page, for what's displayed at a fraction of that size. A `dpi` parameter for a lighter thumbnail variant already existed in the generator but no caller had ever actually passed anything but the default — a half-wired feature, not a new one.
- Wired it up: `?thumb=true` on the spectrogram endpoint serves a dedicated, separately-cached lower-DPI, capped-size variant. Generated proactively at upload time and during the threshold-change background regeneration (added last session), alongside the full-resolution version — never generated lazily on first grid view.
- Verified end-to-end with a real 9-second test recording: thumbnail is 72.7% smaller (116KB → 32KB) and still clearly legible at actual display size.

### Fixed: recording deletion orphaned spectrogram files on disk
- Found while wiring up thumbnails: deletion only removed the single DB-tracked spectrogram path, not the other per-threshold cache variants that already existed before this session (or the new thumbnail files). A pre-existing gap, made marginally worse by adding a second file per threshold.
- Fixed both cleanup sites (manual delete, auto-purge) to glob-match every spectrogram variant for a recording rather than just the one tracked path. Verified end-to-end with 4 simulated variant files (2 thresholds × full/thumbnail) — all correctly removed, where only 1 of 4 would have been before.

## 0.1.11.k — 2026-06-26

### Fixed: eBird S&T map showed only one color, no basemap
- Confirmed two real bugs in the GeoTIFF reading, not just a rendering choice. First: `tifffile`'s `asarray()` only reads the first page/series by default when a file's bands are written as separate series rather than one combined series — reproduced this directly, confirmed it silently drops every band after the first with no error.
- Second: even when bands were read correctly, they were labeled by fixed index ("band 0 = breeding") regardless of which season actually survived review for that species — confirmed via eBird's own documentation that bands correspond to whichever seasons passed review, not a fixed global order. Now reads each band's real description from the file's metadata first, only falling back to the documented order (logged explicitly as an assumption) when no real names exist.
- Added a real coastline basemap, correctly reprojected from lat/lon into the file's actual native projection (read from the GeoTIFF's own georeferencing tags via `pyproj`, not assumed) rather than the flat grey background it had before. Verified the transform math and pixel placement directly against known reference points using a hand-built synthetic GeoTIFF — confirmed land/ocean colors land exactly where expected. Could not verify against a real downloaded eBird file (no network access to test against); every step degrades cleanly to the previous flat-background behavior if the file's tags don't match what's expected, rather than risk a confidently-wrong basemap.
- Fixed the file-selection scorer to require "abundance" in the filename explicitly — it could previously match a same-named seasonal-mean file for a different product (occurrence, count, proportion-population) with a different band structure entirely.

### Fixed: changing the confidence display threshold caused page hangs
- Root cause confirmed: changing this setting deleted every cached spectrogram PNG immediately, making every single recording a cache-miss at the same moment. The next person to view any recording, or scroll a list loading thumbnails, would hit the slow synchronous generation path one at a time — the real cause of reported hangs, not a hypothetical.
- Replaced the immediate delete with a background task that proactively regenerates every recording's spectrogram right after the setting changes, so the cache is warm again before anyone actually views them. Old spectrograms stay valid and servable until each replacement is ready — no window where nothing is cached.
- Verified end-to-end with a real generated WAV file and real `AudioProcessor` call: produces a real spectrogram PNG, and a second run correctly skips already-cached files rather than redoing the work.
- Noted but didn't implement in this pass: list-view thumbnails currently fetch the same full-resolution spectrogram PNG used on the detail page, already lazy-loaded via `IntersectionObserver` but not size-reduced. A dedicated thumbnail size is a real opportunity, scoped separately to avoid rushing a second new caching/generation path in the same session as the one above.

## 0.1.11.j — 2026-06-26

### Optimization audit
- Added 3 composite indexes targeting the actual hot filter/join patterns used repeatedly across the statistics and listing endpoints (`deleted_at`+`trigger_timestamp`, `haikubox_detection_id`+`deleted_at` on recordings; `common_name`+`recording_id` on detections) — SQLite can't intersect two separate single-column indexes as well as it can use one purpose-built composite. Verified idempotent against both fresh and pre-existing databases.
- Audited for N+1 query patterns; found one loop-with-a-query-inside in the bulk "enrich all species" background task, but left it alone since the per-bird cost (external API calls, Playwright) already dwarfs one extra `SELECT` by orders of magnitude — batching it would add complexity for no measurable gain.
- Lazy-loaded `SSHTerminal` (and its `xterm` dependency), which was statically bundled into every page load despite only being used when someone explicitly opens a device's SSH panel. Confirmed via real build output: main JS chunk dropped from 1,354 kB to 1,066 kB (~21%), with `xterm` correctly split into its own 290 kB chunk that only loads on demand.
- Found and removed two dead, unrouted component files (`BirdLibrary.jsx`, `LikelyBirds.jsx`) — confirmed both were superseded by `RegionalLibrary.jsx` (which independently reimplements the same likelihood-ranking logic against the same fields) and confirmed via `grep` that nothing in the frontend or backend still referenced either. Build succeeds unchanged after removal.
- Ran `vulture` for dead-code detection. Found one real bug at 90% confidence: `User.id`'s default was `lambda: str(uuid.uuid4()) if True else ""` — dead conditional logic that always evaluated the same way regardless of the condition. Fixed to use the existing `new_uuid()` helper for consistency with every other model. Verified end-to-end that real, valid UUIDs are still generated correctly.
- Fixed a stale docstring/comment listing `range_map_source`'s possible values as only `"wikipedia"`/`"ebird_st"`/`"gbif"`, missing `"aab"`/`"macaulay"` — both real, actively-assigned values confirmed in an earlier session's fix.
- Noted but didn't act on: `xterm` itself is deprecated in favor of `@xterm/xterm` (confirmed via `npm view`) — a real finding, but a riskier migration (different import paths, possible breaking changes between v5 and v6) that needs its own dedicated, tested pass rather than folding into this audit.

## 0.1.11.i — 2026-06-26

### Fixed: BirdLife legend over-matching — pulled from a reference panel, not the species' real legend
- A production log for Warbling Vireo showed 11 of the 12 possible BirdLife categories extracted for one species — checked against multiple independent sources for its actual range (a simple breeding/non-breeding migrant) and confirmed that's implausible.
- Root cause: extraction searched the entire page (`document.querySelectorAll('body *')`), which would also match a static reference/glossary panel listing most possible categories, not just the actual species-specific legend on the map.
- Fixed by finding the real "Legend" heading first and scoping the search to its container; added a sanity check that discards an unscoped match if it finds more than 6 categories, since no real species plausibly shows more than half the possible range states at once.
- Verified with `jsdom` against a simulated page containing both a fake 11-category reference panel and a real 2-category species legend near a "Legend" heading — correctly scopes to the real one and ignores the reference panel entirely. Also verified the full Python-level chain across four cases: scoped result (trusted regardless of count), unscoped-and-implausible (discarded), unscoped-but-plausible (still trusted), and nothing found.

### Investigated: adapting the `ebirdst` R package — not worth it
- Checked the package's own documentation directly. It's a thin wrapper around the same `st-download.ebird.org` REST API `range_map_service.py` already calls — same endpoints, same GeoTIFF format, no capability Chirp's existing Python implementation doesn't already have natively.
- Bridging it via `rpy2` would mean adding a full R runtime to the container for zero functional gain. Not recommending it; the existing native implementation (now wired up as a real tab in `0.1.11.h`) is the better path.
- One real takeaway: confirmed the `2023` data version string already hardcoded in `range_map_service.py` is current, and noted the citation requirement (Fink et al.) for future attribution-line polish.

## 0.1.11.h — 2026-06-26

### New: eBird Status & Trends as a 4th map source — was already built, just never wired up
- Found that a complete eBird S&T implementation already existed (`fetch_ebird_st_map`: real GeoTIFF download + rendering with seasonal colour compositing), along with full trigger/status/reset endpoints, a Settings UI key field, and even a frontend fetch+poll system — all with zero callers anywhere. Confirmed via `grep`.
- Wired it up as a real, visible 4th tab: added it to Settings' Map Sources list (off by default — "testing," needs a separate S&T key), added the tab pill, error/loading states, and a fetch-in-progress indicator, reusing the existing dead `handleFetchSource` logic instead of duplicating it. Legend uses the exact RGB values from the backend's `SEASON_COLOURS` so it matches what's actually rendered.
- Caught and fixed a real bug in the existing dead code while wiring it in: the fetch guard would have silently no-op'd the refresh button since it treated "already on this source" as "nothing to do," with no way to force a re-fetch.

### Fixed: map tabs could imply a refresh with no visible feedback
- `aabLoading`/`geomodelLoading`/`birdlifeLoading` were all already tracked but never rendered anywhere — confirmed via `grep`, same dead-state pattern as the eBird S&T system above.
- Added a real loading overlay: the previous map stays visible (dimmed) with a "Refreshing map…" spinner on top, instead of the view blanking or flickering. Caught BirdLife's refresh button missing the loading-state set entirely while wiring this in.

## 0.1.11.g — 2026-06-26

### Fixed: backup download — real ImportError, not just a UX issue
- Confirmed from a traceback: `from .config import Settings` in `app_settings.py` (which lives in `app/api/`) resolved to the nonexistent `app.api.config` — needed `..config` to reach `app/config.py`. A typo from the session that added this filename logic.
- Verified the fix end-to-end: the endpoint now runs and produces the correct `chirp_v{version}_{date}.db` filename instead of crashing with a 500.

### Fixed: European Starling's Wikipedia fallback queried the wrong title
- Confirmed: Wikipedia's real article for this species is "Common starling," not "European starling" — Chirp's common name is a redirect title on Wikipedia, not the canonical one. The MediaWiki API doesn't follow redirects to fetch the real content unless `redirects=1` is explicitly passed, which this call never did — so it silently got nothing and fell through to a much worse stripped-down guess ("Starling").
- Fixed by adding `redirects=1` to both the range-map image query and the article-extract query (the second one defensively, same root cause). Confirmed via MediaWiki's own documentation that this is exactly the documented behavior, not a guess.

### Fixed: a broken AAB map hid the iNat/BirdLife tabs entirely
- Reported: when AAB fails, the whole map section — including the tab buttons themselves — collapsed to "not available," with no way to switch to the two independent, unrelated sources.
- Root cause: AAB's image error was the only one wired to collapse the entire outer section; iNat and BirdLife's errors already correctly stayed within the tabbed view. Fixed AAB to match — it now shows its own inline "try iNat or BirdLife" message inside the tab view instead of hiding the tabs.
- Also fixed a related gap: clicking back to the AAB tab after a previous failure never reset its error state, unlike iNat/BirdLife, which already did.

## 0.1.11.f — 2026-06-26

### Fixed: range map dead-ends when a previously-working AAB URL stops working
- Confirmed from a log: European Starling's `range_map_url` was a real AAB CDN asset that worked before but now 403s server-side. The serving endpoint had no fallback for "the cached URL itself is dead" — it just redirected the browser to the same broken URL, which fails there too.
- Fixed by falling through to a fresh Wikipedia lookup (the same one `_resolve_range_map` already uses during enrichment) when the proxy fetch confirms the URL is dead, and persisting the correction so future requests don't hit the same dead end. A genuine dead-end (no Wikipedia page either) now returns a clear 503 instead of silently redirecting to a known-broken URL.
- This only covered the Wikipedia case for `range_map_source` syncing in `0.1.11.e`; this AAB-CDN-URL case is a separate, non-Wikipedia code path that needed its own fix.
- Verified end-to-end with the exact European Starling scenario (stale AAB URL, simulated 403, real fallback to a Wikipedia URL) and the genuine-dead-end case (no fallback available, confirmed a clean 503 rather than a crash).

## 0.1.11.e — 2026-06-26

### Fixed: legend still wrong for some maps — `range_map_source` going stale
- Confirmed from a log: American Robin's AAB capture failed (Cloudflare 403), fell back to a Wikipedia redirect, but the older redirect code path (separate from last session's `_resolve_range_map` fix) never updates `range_map_source` — it stayed `"aab"`, so the legend endpoint kept serving an empty AAB legend for a map that was actually Wikipedia.
- Fixed by syncing `range_map_source` at both serving paths (the Wikimedia redirect and the locally-cached `.svg` case, since `.svg` itself is a reliable Wikipedia signal). Verified end-to-end: a profile with stale `range_map_source="aab"` but a real Wikipedia URL now gets corrected and the legend endpoint correctly returns the real SVG legend instead of `no_legend_cached`.

### Fixed: BirdLife 404 detection ran before the page actually rendered
- American Robin's BirdLife screenshot was a literal 404 page, despite the detection logic itself being correct (confirmed by testing the exact visible text). Root cause: the check ran immediately after `domcontentloaded`, before BirdLife's client-rendered SPA had painted anything — reading an empty shell, not the real 404 text.
- Added a wait (with one retry) before checking. Also discovered the resolution priority itself was backwards: BirdLife's `en_HBW` cross-walk (which fixed European Starling) returns "American/San Lucas Robin" for American Robin — which 404s — while the plain guessed slug ("american-robin...") is correct. Neither strategy is reliably better, so now the guess is tried first and the `en_HBW`/search fallback only runs if it actually 404s.
- Verified against both real cases directly: American Robin's real factsheet text isn't flagged as a 404, European Starling's `en_HBW` fallback still resolves correctly, and the source confirms the guess is tried before the fallback.

## 0.1.11.d — 2026-06-26

### Fixed: wrong/missing range map legends for AAB and Macaulay maps
- Root cause: the legend endpoint fell through to a Wikipedia SVG legend unconditionally whenever `aab_legend` was empty, even when the actual map shown was AAB or Macaulay — producing real colors for the wrong map entirely.
- Fixed by gating that fallback on `range_map_source` actually being Wikipedia/GBIF. Also discovered `range_map_source` was never set during normal enrichment at all and fixed that gap.
- Stale data from before this fix needs the map's own refresh icon (not a browser refresh) to re-fetch correctly.

### Fixed: Life List still showing 88 species after disabling Haikubox
- Found a second, separate instance of the Haikubox-exclusion bug, in `full_statistics()` (the entire Statistics page) rather than the Dashboard query fixed previously.
- Fixed at the shared `_base()` query, covering every chart on that page in one fix. Verified end-to-end with a synthetic Haikubox-only species — correctly excluded from `top10_names` and `cumulative_species`.

### New: day-of-week activity can be normalized by hours actually recorded
- Added `day_of_week_normalized` (detections per hour recorded) alongside the existing raw counts, with a UI toggle. Excludes Haikubox's synthetic 3-second placeholder duration from the denominator.
- Verified end-to-end with synthetic data (10hrs/50 detections vs 1hr/20 detections across two days) — correct per-hour values, Haikubox correctly excluded.

### Fixed: backup download was actually a JSON error, not a real backup
- Root cause: the plain `<a download>` link never sent the auth token this endpoint requires, so with auth enabled the "backup" being saved was a 403 JSON error body with a browser-guessed filename.
- Fixed with a real authenticated fetch+blob download, named `chirp_v{version}_{date}.db`.

### Fixed: Cornell (and other light theme) headers nearly invisible
- Four plain page headers (Devices, Settings, LikelyBirds, RecordingDetail) used raw `text-white` with no theme-aware variable — fine on dark themes, nearly invisible on light ones.
- Fixed all four; confirmed BirdProfile's photo-overlay header was correctly using white-on-dark-scrim and left it alone.

### New: more animation on Dashboard and Tutorial
- Added staggered entrances for list rows/cards/notes, hover micro-interactions, and tutorial header/step/nav entrance animations. Added two more stagger tiers and a pop-in keyframe to support it.

### New: two more themes — NEXRAD and Moth Trap
- NEXRAD: real BirdCast/weather-radar bird-migration aesthetic (verified against the actual green→yellow→red reflectivity convention), with a genuine rotating sweep-line animation.
- Moth Trap: nocturnal field-recording UV-blacklight aesthetic, true black with a violet glow.
- Caught and fixed two of my own typos (a malformed hex value, a JS comment using `#` instead of `//`) before they shipped.

## 0.1.11.c — 2026-06-25

### New: iNat geomodel now has a refresh button, matching AAB and BirdLife
- Added `?refresh=true` to the geomodel endpoint plus a matching UI button — previously the only way to bypass a stale cached render (e.g. from before `0.1.11.b`'s star-burst fix) was deleting the file by hand.
- Button stays visible even in the error state, since refreshing is the actual recovery action.
- Checked the new state's declaration order for the same temporal-dead-zone bug caught in `0.1.11.a` — not present here, since `geomodelSrc` doesn't depend on `mapView`.

### Fixed: AAB legend colors all rendered as the same dull grey
- Two compounding bugs from `0.1.11.b`'s same fix: the "real color" check only rejected pure black, so inherited grey body text passed through as if it were real styling; and the new vividness check meant to catch that had a regex typo (`\\d+` instead of `\d+`), so it silently matched nothing — including genuinely vivid real colors.
- Fixed both, plus added a same-color-for-every-label sanity check that discards the whole result if every category resolves to one identical color.
- Verified against the actual extracted JS with `jsdom` (grey rejected, real distinct colors accepted, identical-color case discarded) and an end-to-end Python run confirming the fallback palette.

## 0.1.11.b — 2026-06-25

### Fixed: iNat geomodel map rendered as a star-burst of triangles
- Root cause: iNat stores each taxon's range as many disjoint hexagons, often grouped per row as one MultiPolygon. The WKB parser flattened every sub-polygon into one ring, so `ax.fill()` drew one self-intersecting path connecting unrelated hexagons across the globe.
- Fixed by returning a list of separate rings instead of one flattened ring.
- Verified: a synthetic 3-hexagon MultiPolygon now parses into 3 separate rings, and a ~40-hexagon synthetic dataset renders clean with zero artifacts.

### Fixed: BirdLife legend panel still visible in the saved screenshot
- Added a content-based hide (find the panel by its actual "Show IBAs/KBAs" + "Show protected areas" text) since the panel's class name is almost certainly CSS-module-hashed.
- Caught a real bug before shipping: `querySelectorAll('div')` returns the outermost matching ancestor first — which could be the whole map container, not just the legend. Fixed to select the innermost match instead; confirmed with `jsdom`.
- Hide pass now runs twice with a short wait, in case BirdLife's own animation was still in flight.

### Fixed: AAB legend colors didn't match the real documented convention
- Confirmed via Cornell-affiliated training material (and independently by Sibley Guides): Breeding=red/orange, Migration=yellow, Non-breeding=blue, Year-round=purple (a blend, not its own color) — the old fallback palette didn't match this.
- Switched to reading real DOM colors first, falling back to the corrected palette only when nothing real is available.
- Caught two more bugs while building this: a substring collision ("breeding" matches inside "nonbreeding," fixed by checking longest labels first) and a stray Python-style `#` comment left inside a JS string, which would have thrown a real syntax error — caught by extracting and running the literal JS through `node --check`.

## 0.1.11.a — 2026-06-25

### Fixed: iNat geomodel map crashed on every request
- Production log showed `AttributeError: 'numpy.ndarray' object has no attribute 'ptp'` — removed in NumPy 2.0, which `requirements.txt` allowed.
- Fixed with the standalone `np.ptp()`. Verified by reproducing the crash directly and by rendering a real synthetic GeoPackage end-to-end through `render_range_map()`.

### Fixed: BirdLife legend showing wrong colors for some categories
- Root cause: the swatch-color search accepted the first nearby non-white element, which in BirdLife's two-column grid could grab an unrelated row's color instead of the right one.
- Fixed by requiring a real swatch shape (small, no children, no text) before accepting a color. Verified with `jsdom` against a simulated 4-row grid — zero cross-row contamination.

### Fixed: legend panel and toolbar buttons baked into the saved screenshot
- LEGEND, EXPAND, zoom, and share/download icons were all still visible — the dismiss pass wasn't catching the always-present toolbar.
- Added class-name, button-text, and positional (icon-only buttons near a map corner) hiding. Verified with `jsdom`; caught and fixed an off-by-one in my own test where a button sitting exactly at the original threshold was missed.

### New: AAB map tab now has a refresh button, matching BirdLife's
- Added `?refresh=true` to the `/range-map` endpoint and a matching UI button.
- Caught a real bug while wiring this in: the new refresh state was referenced before its own `useState` declaration — confirmed this throws a real `ReferenceError` and fixed the ordering before it shipped.
- Also added an `onLoad` handler to clear the loading spinner on success, fixing a small pre-existing gap shared by the BirdLife refresh path too.

## 0.1.10.z — 2026-06-25

### Fixed: AAB legend extraction — same root cause as BirdLife's, found proactively
- Asked directly whether AAB's legend was actually being extracted in production. There was no logging at all confirming the answer either way (unlike BirdLife's path, which already logs its outcome) — so the honest answer was "unverified," not "yes."
- Checked, and it had the identical flaw `0.1.10.y` just fixed for BirdLife: the selectors guessed class names containing "legend"/"range-map"/"maps", but a direct fetch of a real AAB `/maps-range` page confirmed the legend text sits in a plain element with none of those words anywhere in its class name — AAB's Cornell Lab stack, like BirdLife's, almost certainly uses framework-generated class names rather than literal English ones.
- Confirmed via the same direct fetch that the legend text itself *is* present and in the expected format (`Year-roundBreedingMigrationNonbreeding`, concatenated with no separator) on the actual `/maps-range` page for European Starling — so the page and format assumptions baked into the original extraction logic were correct; only the selector strategy was wrong.
- Fixed the same way as BirdLife: scan the full page body for the concatenated legend string by content instead of guessing a containing element's class name first. The old class-name selectors are kept as a secondary fallback in case some AAB page variants do use a literal "legend" class.
- Added logging after extraction (`AAB legend for {species}: N entries` / `none extracted`) so this is actually visible in production logs going forward — its absence is exactly why this bug could ship unnoticed in `0.1.10.w`.
- Verified with `jsdom` against three realistic simulated DOM structures: the confirmed real concatenated-string format, a single-category year-round-resident case (confirming no false match against a longer descriptive paragraph that also happens to contain "year-round"), and a multi-span structure where each category is its own element rather than one text run. All three extract correctly. Also re-verified the Python-level wrapper logic directly: correct category ordering, graceful `[]` (not a crash) when nothing matches or `page.evaluate()` raises, and confirmed the class-name fallback path still works as a safety net when the body scan finds nothing.

## 0.1.10.y — 2026-06-25

### Fixed: BirdLife legend never extracted — wrong root cause assumption, again
- Real production log confirmed `0.1.10.x`'s URL fix worked (the real BirdLife world map for European Starling loaded correctly, `200 OK` instead of `503`), but the legend still came back empty: `could not extract legend from DOM with any known selector`, `0 legend entries`. The frontend kept showing the old hardcoded 7-swatch fallback list as a result — including "Possibly extant," which obviously doesn't apply to a common, well-established species like European Starling.
- Root cause: the production screenshot shows BirdLife's map legend is collapsed behind a "LEGEND" button by default — it isn't in the DOM (or isn't populated) until that button is clicked. The previous version's dismiss/cleanup pass *did* click that same button, but only *after* extraction had already run and failed against the still-collapsed panel — so the click that would have opened it happened one step too late to matter, then immediately closed it again before the screenshot.
- Fixed the ordering: open the legend panel first, extract, then close/hide it before screenshotting — not the reverse.
- Also replaced the class-name-based selectors (`.legend-item`, `[class*='legend']`, etc.) with direct text matching against the 12 known category labels. BirdLife's DataZone is a Trifork-built React app; production class names there are almost certainly CSS-module-generated hashes, not literal strings containing "legend" — which is exactly why every class-name guess found nothing. Matching on the labels' actual visible text is far more durable against that kind of styling, and color is read from whichever nearby element (the label itself, a sibling, a parent, or a child) has the first non-transparent computed background — handling the dot-plus-label-span pattern common in real legend rows.
- Verified with `jsdom` against two realistic simulated DOM structures (not just Python-level mocks): a CSS-module-style legend panel with `LegendItem_abc123`-style class names, confirming all 4 real categories extract correctly while a long paragraph that happens to mention "Resident" in passing is correctly ignored; and a wrapper-div-plus-leaf-span structure, confirming the extraction correctly dedupes to the leaf element's swatch color rather than double-counting or grabbing the wrong element's background.
- Also verified the underlying Python logic directly: spelling normalization (Reintroduced/Re-introduced, Nonbreeding/Non-breeding collapse to one canonical label), graceful `None` (not a crash) when `page.evaluate()` raises, and confirmed the known-labels list is passed to the browser correctly.

## 0.1.10.x — 2026-06-25

### Fixed: BirdLife search-based resolution didn't work in production — replaced with eBird's own taxonomy cross-walk
- Real production log from the running server showed `0.1.10.w`'s fix only got halfway there: `BirdLife search: no factsheet links found for 'Sturnus vulgaris'` — the search-page scrape fell back to the guessed slug, which still 404'd exactly as before. BirdLife relaunched their entire DataZone platform in April 2025 (built by Trifork) as a heavily client-rendered SPA; the selector guess for reading search results didn't match its real markup, and this couldn't be fully verified from this environment's sandboxed network access.
- Root cause traced to something better than a search scrape: eBird officially maintains an `en_HBW` locale as a documented cross-walk between the eBird/Clements taxonomy (what Chirp/BirdNET uses) and the BirdLife/HBW taxonomy specifically for this purpose — querying eBird's existing taxonomy API with `locale=en_HBW` for a species returns BirdLife's own common name directly. For *Sturnus vulgaris* this correctly returns "Common Starling," confirming the original diagnosis was right; the implementation just needed a more reliable resolution path than scraping an unfamiliar, JS-heavy search UI blind.
- This is now the primary resolution strategy, ahead of the site-search scrape (kept as a fallback for species with no `en_HBW` entry or when no eBird API key is configured) and the guessed-slug (final fallback). Reuses the `ebird_species_code`/`ebird_api_key` infrastructure already in place elsewhere in the enricher — no new API integration needed.
- Caught and fixed a real bug while wiring this in: the standalone wrapper functions used by the `/range-map/birdlife` endpoint create a `BirdEnricher` via `__new__` (bypassing `__init__`) for backward compatibility, which meant `self.db` didn't exist as an attribute at all on that path — accessing it to read the eBird API key would have raised `AttributeError` rather than gracefully falling through. Fixed by having both wrappers properly construct the enricher via `__init__` when a db session is available (now passed through from the endpoint, which already had one), and by guarding the attribute access with `getattr` so the no-db path still degrades gracefully instead of crashing.
- Verified with mocked eBird API responses: confirmed the European Starling → Common Starling slug resolves correctly, confirmed the resolution chain only falls through to search when eBird genuinely returns nothing, confirmed species with no `en_HBW` entry and network failures both degrade to `None` (triggering the next fallback) rather than raising, and confirmed the `AttributeError` fix with three separate no-db/no-key scenarios that would have crashed before the fix.

## 0.1.10.w — 2026-06-25

### Fixed: BirdLife range map 404s — wrong root cause assumption
- Reported: some species (e.g. European Starling) showed BirdLife's own 404 page screenshotted and served as if it were the range map.
- Root cause confirmed directly against the live site: BirdLife's IUCN-based English names frequently differ from Chirp/BirdNET's (European Starling vs. BirdLife's "Common Starling" — same *Sturnus vulgaris*). The slug was guessed from Chirp's common name and never checked against the page it actually landed on, so a name mismatch silently 404'd and got screenshotted anyway.
- Fixed two ways: (1) the real factsheet URL is now resolved via BirdLife's own search, keyed on scientific name rather than guessing from the English common name — scientific names are consistent across sources, common names often aren't; (2) added an explicit check for BirdLife's "can't find this page" 404 content before screenshotting at all, as a safety net regardless of how the URL was resolved, so a 404 page can never again be saved as if it were a real map.
- Verified with synthetic Playwright-page mocks: confirmed the European Starling case now resolves to `common-starling-sturnus-vulgaris` instead of 404ing, confirmed 404 pages are correctly detected and real factsheets are not false-flagged, and confirmed graceful fallback to the guessed slug when search itself fails to load.

### New: BirdLife and geomodel range maps are now pre-fetched during enrichment
- Previously both were 100% lazy — never touched until the person opened a bird's profile and clicked that specific map tab, so the first view always had to wait for a fresh Playwright capture or a fresh render. Now fetched eagerly during the same enrichment pass that already runs on "Refresh All Data" and on new-species detection, so both are cached and ready before anyone looks.
- Respects each source's individual enabled-toggle from Settings (a disabled source is never fetched). Skips species pre-fetched within the last 30 days unless forced, so a repeated "Refresh All Data" doesn't re-run Playwright on every bird every time — only profiles never pre-fetched, or whose cached file has gone missing, are actually re-captured.
- Verified end-to-end against a real database: settings toggle respected (geomodel skipped when disabled), legend persisted to the profile, staleness correctly skips a second call within the window, and `force=True` correctly bypasses that skip.

### New: per-species range map legends, replacing one fixed global swatch list
- Reported: legend colors/categories didn't always match what a given species' map actually showed, since both the BirdLife and AAB legends were one hardcoded 4-to-7-color list applied to every species regardless of what that species' real map displayed.
- BirdLife's real page can show up to 12 possible legend categories (Resident, Breeding, Non-breeding, Re-introduced, Introduced, Origin uncertain, Possibly extinct, Extinct, Possibly extant, Passage, Season uncertain, Assisted colonisation), and any given species only renders the subset that applies to it. Now read directly from that species' live DOM at fetch time — exact swatch colors and labels, not an approximation — and cached per-profile (`birdlife_legend`).
- AAB/Birds of the World pages render a real per-species legend string too (e.g. "Year-round Breeding Migration Nonbreeding" for Arctic Tern, only the applicable categories present). Read the same way and cached per-profile (`aab_legend`), with colors assigned from AAB's documented fixed 4-color convention since the legend text isn't reliably paired with its swatch element in the DOM the way BirdLife's is.
- New `birdlife_legend`, `aab_legend`, and `range_maps_prefetched_at` columns added to `BirdProfile`. The hardcoded lists are kept as a fallback only for the case where extraction genuinely found nothing for that species (or for profiles enriched before this version) — not as the default path anymore.
- `/range-map-legend` now takes a `source` param so the frontend requests the legend scoped to whichever map tab is actually open; previously it only ever returned the Wikipedia SVG-parsed legend regardless of which source was being viewed.
- Verified with synthetic DOM-read mocks covering: a 4-category species, a 1-category species (e.g. a true year-round resident), selector fallthrough when the first selector matches nothing, case-insensitive dedup of repeated categories, and the "nothing matched at all" case returning `None` (no legend cached) as distinct from "matched but empty."
- Caught and fixed a real bug during testing: AAB label formatting was emitting "Nonbreeding" instead of "Non-breeding" for any page where the source text had no hyphen — fixed by mapping category order directly to a canonical display label instead of reformatting the matched substring.

## 0.1.10.v — 2026-06-24

### Fixed: Dashboard species/detection counts didn't match the Life List
- Reported and reproduced exactly: Dashboard showed 88 species / 11,266 detections while the Life List showed 80 species / 11,253 detections — an 8-species, 13-detection gap.
- Root cause: `get_life_list()` in `birds.py` already excludes species detected *only* via Haikubox (a documented, intentional rule — a species with zero real Pi/device detections was never actually heard by this Chirp install), but the Dashboard's `total_species`/`total_detections` stats in `recording_stats()` had no such exclusion at all, so Haikubox-only species inflated both counts there.
- Fixed by applying the same exclusion subquery `get_life_list()` already uses to the Dashboard's detection base query — `total_species`, `total_detections`, and `top_species` now all correctly exclude Haikubox-only species, matching the Life List exactly. The "Detection activity" chart is a separate, independent query untouched by this change, since it answers a different question (when did activity happen) than the headline stats (what counts as a species we've detected).
- Verified directly with a synthetic dataset reproducing the exact reported numbers (80 real species + 8 Haikubox-only species): confirmed the bug reproduces the precise 88/80 and 11,266/11,253 gaps before the fix, and confirmed `total_species`, `total_detections`, and zero leakage into `top_species` all match the Life List exactly after it.

## 0.1.10.u — 2026-06-24

### Haikubox/Pi separation — closed remaining gaps
- **Main `/recordings` feed leak fixed** — Haikubox rows were only excluded from the main feed while the toggle was *off*; with it on, there was no exclusion at all. Now unconditional. Verified with a mixed dataset (3 Pi + 5 Haikubox): main feed → 3 Pi only, Haikubox feed → 5 Haikubox only, both toggle states.
- **Haikubox-only species no longer pollute Life List / Field Guide / likelihood scoring** — fixed in all four places: Life List endpoint, the CSV/eBird + JSON export helper, Field Guide's `locally_detected` flag, and the periodic eBird regional-sync job. A species needs at least one *non*-Haikubox detection to count; species detected by both Pi and Haikubox are unaffected. Verified with a three-way dataset (Haikubox-only / Pi-only / both).
- **Bird profile pages confirmed already Haikubox-clean** — the per-species Recordings list reuses the now-fixed main feed, plus a dedicated "📡 N Haikubox detection(s)" link already exists separately. Added defensive indicator logic to the play button as a safety net.

## 0.1.10.t — 2026-06-24

### Fixed: the real Haikubox bug — wrong field names
- Real payload capture showed the actual Haikubox API keys are `cn`/`sn`/`dt`/`spCode`/`wav`/`offset` — not `commonName`/`timestamp`, which every prior version checked for. Every detection silently failed validation and was miscounted as dedup (`0 new, 161 already seen, DB row count 0 -> 0`); this was never data loss, the rows had never been written.
- **Timestamp double-conversion fixed** — `dt` carries an explicit UTC `Z` suffix; old code stripped it and then applied a device-timezone offset on top, shifting every timestamp and dedup key. Now detects explicit UTC/offset markers and only applies the device-timezone interpretation when genuinely naive.
- Fixed by mapping the real field names with fallback to the old names for forward-compatibility. Verified against real captured detections: first sync → `3 new, 0 already seen, DB row count 0 -> 3`; second sync on the identical payload → `0 new, 3 already seen, DB row count 3 -> 3` (genuine dedup).

## 0.1.10.s — 2026-06-24

### Found the real Haikubox issue: field-validation failure mislabeled as dedup
- Fresh logs gave the decisive evidence: `0 new, 161 already seen ... actual DB row count: 0 -> 0` — zero before and after, never populated.
- `_import_detection` returns `False` for three different reasons (missing fields, bad timestamp, genuine dedup) and the caller treated all three identically as "already seen," with no logging on the validation-failure path.
- Added explicit WARNING-level logging for validation failures, labeled "NOT a dedup skip," plus a one-time raw payload sample per sync. Verified by simulating a mismatched-field payload and reproducing the exact false-positive pattern, then confirming a correct payload still dedups normally with no false warning.

## 0.1.10.r — 2026-06-24

### Investigated: Haikubox data-loss diagnosis gap
- Traced a full debug log's fluctuating payload counts (141→141→140…139…141) — normal behavior, since the Haikubox API only returns a rolling 24-hour window (`DETECTION_WINDOW_HOURS = 24`); confirmed no `db.delete()` exists anywhere in `haikubox_sync.py`.
- Every sync in the log showed "0 new" for ~1h45m straight — only possible if real rows existed throughout; the log never actually captured a drop-to-zero moment.
- Ruled out species/timestamp dedup-key collision (key includes exact timestamp) and confirmed a startup re-sync already runs on every service start.

### Added: diagnostic to catch the disappearance in the act
- Every sync now records a direct count of `Recording` rows with `haikubox_detection_id` set, compared against the previous cycle's ending count (not the dedup counter, which only reflects what the import lookup found).
- Verified across a 4-sync sequence with a deliberate deletion between syncs 2 and 3: correctly logged `WARNING: Haikubox row count DROPPED between sync cycles: 10 -> 6` only on sync 3.

## 0.1.10.q — 2026-06-24

### Fixed: real cause of the "list mode cuts off content" bug
- `RecordingsList.jsx` was the only page making its own root a second, competing scroll container (`h-full` + own `overflowY: 'auto'`) instead of relying on `<main>` in `App.jsx`. Fixed by resolving the scroll container via `closest('main')`, preserving scroll-position save/restore. Verified with 100 real recordings — all rows in DOM, pagination controls fully visible.

### Fixed: two more toolbar buttons with mismatched heights
- Grid/list toggle was using padding-derived height instead of explicit `34px`, same root cause as the earlier calendar-button fix. All four toolbar buttons now measure exactly 34px.

### Added: always-visible Haikubox link on the device card
- Previous link only showed when `total_recordings > 0`. Added a second, unconditional link next to the serial-number field so toggle/sync state is reachable even with zero detections.

### Haikubox data loss: still open
- Confirmed on the reporting deployment that every auto-cleanup trigger (`auto_delete_recordings_days=0`, `auto_archive_recordings_days=0`, `storage_max_dir_gb=0.0`) was already inactive — ruling out the 0.1.10.o fix as the cause of the original 139-detection loss. Root cause still unconfirmed; awaiting a live capture.

## 0.1.10.p — 2026-06-24

### Fixed: spectrogram cache writes are now atomic
- Reported regression: "Enhanced" spectrogram on a new recording rendered corrupted/blocky. Could not reproduce with synthetic audio, but found and fixed a real race: every cache write in `audio_processor.py` wrote directly to its final path, so concurrent requests could both pass the exists-check before either finished writing.
- Fixed by writing to a temp path and atomically `os.replace()`-ing into place, across every cache write (bird/bat spectrograms, enhanced audio, clips, bat downshift output).
- Two real bugs caught while building this: temp suffix appended *after* the extension broke format-inference in `soundfile`/`matplotlib` (fixed: insert before extension); using PID for "uniqueness" failed because threads share a PID (fixed: UUID per call).
- Verified with 5 rounds of 12 concurrent requests + 3 rounds of 8 concurrent requests on a 60s recording — 0 errors, 0 corrupted files, 0 leftover temp files.

### Haikubox data loss: previous fix confirmed inactive on reporting deployment
- The 0.1.10.o cleanup-exclusion fix is correct and stays in, but confirmed not to be what caused the original 139-detection loss — its trigger conditions were never active there. Root cause recorded as still open.

## 0.1.10.o — 2026-06-24

### Fixed: real data-loss bug — automatic cleanup could delete Haikubox detections
- Neither `_prune_by_age` nor `_prune_by_size` excluded Haikubox-sourced recordings, which have no audio file (`wav_path` empty by design) — deleting one frees zero disk space while destroying real detection history.
- Also closed two related gaps: `/settings/purge-empty-recordings`'s `no_server_detections` mode, and the per-recording auto-purge inside `process_recording_bg` (latter confirmed unreachable today, fixed defensively).
- Fixed by excluding `Recording.haikubox_detection_id IS NOT NULL` from all four code paths. Verified with a mixed dataset: a 45-day Pi recording correctly pruned, a 60-day Haikubox recording correctly untouched.

### Investigating: spectrogram-corruption regression
- Reported: "Enhanced" spectrogram on newly-acquired recordings renders corrupted; pre-upgrade recordings unaffected. Confirmed real and reproducible, but not yet reproducible with synthetic test audio.
- Added diagnostics: `enhance_audio()` now logs input/output stats (sample counts, peak amplitude, RMS, NaN/Inf checks) and replaces any NaN/Inf output with silence before caching, rather than silently caching a corrupted file.

## 0.1.10.n — 2026-06-24

### Fixed: second Docker build failure from the VERSION-file change
- 0.1.10.m fixed the backend stage's `COPY VERSION ./VERSION` but missed that the frontend-builder stage is a separate, isolated stage receiving only `COPY frontend/ .` — `VERSION` one level above was never present in that stage's filesystem.
- Fixed by adding an explicit `COPY VERSION ./VERSION` to the frontend-builder stage (after `npm install`, before `npm run build`, to preserve layer-cache behavior), and making `stamp-sw-version.mjs` search multiple candidate paths instead of assuming one fixed depth.
- Verified against both real layouts: a faithful simulation of the Docker frontend stage's filesystem, and a real local `chirp-server/frontend/` checkout — both resolved correctly with no per-environment config.

## 0.1.10.m — 2026-06-24

### Fixed: real Docker build failure from the previous version-sync fix
- 0.1.10.l moved canonical `VERSION` to the repo root, verified at the time only via direct Python imports and `npm run build` — missing that `docker-compose.yml`'s build context is `chirp-server/`, one level below the repo root, so `COPY VERSION ./VERSION` couldn't see it (`"/VERSION": not found`).
- Fixed by moving `VERSION` into `chirp-server/` (the real build context) and updating both `config.py`'s `_read_version()` and `stamp-sw-version.mjs`'s path math to match.
- Verified by simulating the real container directory layout (`/app/VERSION` + `/app/app/config.py`) and running the real `_read_version()` against it.

## 0.1.10.l — 2026-06-24

### New: archive recordings — delete just the audio, keep everything else
- New `Recording.archived_at` field, deliberately distinct from soft-delete (`deleted_at`, which hides from stats — archiving must not). Deletes the WAV + clips only; spectrogram, all `Detection` rows, notes, and stats contribution are untouched.
- New `POST /{id}/archive` and `POST /{id}/unarchive` endpoints — verified end-to-end (files deleted, spectrogram/detections preserved, `has_audio` flips correctly).
- Playback, WAV download, and iNaturalist submission correctly disabled on archived recordings with specific error messages instead of generic "file not found."
- Fixed a related bug surfaced by this: the spectrogram block used `has_audio === false` to mean only "Haikubox, never had audio" and hid the spectrogram — now distinguishes that from "archived, spectrogram still on disk."
- Added fallback: if a confidence-threshold change invalidates the cached spectrogram key post-archive, serves any other cached variant rather than 404ing.
- New independent `auto_archive_recordings_days` setting (Settings → Storage & Data), wired into the cleanup cycle as a new first pass; respects the existing "keep flagged" (label/notes) protection.
- New "Archive"/"Unarchive" button and "Archived" badge on the recording detail page.

### Optimization audit
- Added a missing index on `Recording.device_id` (3 equality filters) and `Recording.archived_at` via a new generic, idempotent index-migration step (`_migrate_indexes()`), parallel to the existing column-migration system.
- Fixed `dashboard_summary()` querying `AppSettings` three times per load instead of once. Caught a `None`-vs-"not provided" sentinel bug in the first fix attempt via the empty-database edge case.

### Fixed: version number not staying in sync
- `main.py`'s `FastAPI(version=...)` was an independently hardcoded literal (despite a comment claiming otherwise) — bumping it never touched what `/health`/`VersionBadge.jsx` displayed. Two separate `VERSION` files existed, one never read at all, plus a third independent copy in `package.json`.
- Fixed by making the repo-root `VERSION` the single real source: `main.py` reads it directly, the redundant file was removed, and `stamp-sw-version.mjs` reads the same canonical file and writes it into `package.json` too. Verified: one edit propagated correctly to the FastAPI object, `/health`, `sw.js`'s cache name, and `package.json`.

### Smaller fixes
- Removed obsolete `version: "3.9"` from `docker-compose.yml`.
- Fixed the Recordings page date-filter button's cramped spacing against its icon/chevron.
- Updated the in-app Getting Started guide (stale "11 color themes" → 20 + custom builder; stale Haikubox description → reflects the real integration).

## 0.1.10.j — 2026-06-24

### New: date range filter on the main Recordings page
- Same filter already shipped on the Haikubox page (24h/7d/30d/3mo/all presets + custom range), extracted into a shared `DateRangeFilter.jsx` component (`useDateRangeFilter` hook + dropdown UI) so both pages share identical, tested logic. Backend: matching `start`/`end` query params on `GET /recordings`. Resets pagination to page 1 on change.

### Fixed: real auth bug causing "page size doesn't do anything" / stuck pages
- `recordings.list()` and `haikuboxList()` each had their own hand-rolled `fetch()` bypassing the shared `request()` helper — neither handled a `401 Not Authenticated` response. Compounded by `RecordingsList.jsx`'s `.catch(() => {})` silently discarding the failure with no indication of being logged out.
- Fixed by giving both functions the same 401-handling as `request()` (clear stale token, redirect to `/login`), and replacing the silent catch with a real error state (visible message + working Retry button). Verified by simulating a 401 against old vs. new logic side by side.

## 0.1.10.h — 2026-06-23

### Devices page: removed generic settings card for the virtual Haikubox device
- The Haikubox device was rendering through the same `DeviceCard` component as a real Pi, showing irrelevant BirdNET/inference-backend controls. Filtered it from that list — it already has its own dedicated status panel further down the page. Underlying `Device` row untouched.

### New: enhanced spectrogram now matches the enhanced audio toggle
- "Enhanced" previously only swapped audio playback while the spectrogram stayed on the original. Added a matching enhanced spectrogram from the same noise-reduced audio, with the same on-disk caching strategy, reusing an already-cached enhanced audio file if one exists.
- Measured generation time directly: 370–600ms typical, with a one-time 1.4–1.5s outlier on the first request after restart (matplotlib font-cache init, not per-recording). Added a "Generating enhanced spectrogram…" loading state to cover that case.
- Lifted the `enhanced` toggle state from `AudioPlayer` up to the shared parent so audio and spectrogram respond to one toggle together. Verified end-to-end with a real browser.

## 0.1.10.g — 2026-06-23

### Found the actual root cause of "Haikubox detections not appearing": service-worker caching, not a data bug
- Backend traced exhaustively end-to-end — sync, dedup, toggle, summary/list endpoints, settings round-trip — everything worked correctly; the 115 real detections existed and were correctly served the whole time.
- Real cause: `frontend/public/sw.js`'s `const CACHE = 'chirp-v1'` was a hardcoded literal that never changed across any release from `0.1.9.x` through `0.1.10.f`. The `activate` handler's cache-cleanup logic only triggers when the name changes — it never did, so browsers could serve stale JS/CSS indefinitely. **A normal hard refresh does not fix this** (the SW intercepts requests before they reach the network).
- Fixed two ways: (1) cache name now includes the real app version (`chirp-v0.1.10.g`); (2) added `stamp-sw-version.mjs` as an npm `prebuild` step that auto-rewrites the cache name from `package.json`'s version on every build, eliminating the manual-edit step that caused this.
- If still seeing stale data after updating: DevTools → Application → Service Workers → Unregister, then reload.

## 0.1.10.f — 2026-06-23

### New: date range filter on the Haikubox Detections page
- Presets (24h/7d/30d/3mo/all time) + custom range, filtered server-side via new `start`/`end` params on `GET /recordings/haikubox` (required for correctness with pagination). Composes correctly with the species deep-link filter.
- Handles aware-vs-naive timestamp mismatch: incoming filters may arrive timezone-aware while `trigger_timestamp` is stored naive-UTC; endpoint converts and strips before comparing.
- Verified end-to-end against a 115-detection synthetic dataset: every preset, custom range (empty + overlapping cases), and clear-filter all produce correct results via real UI interaction.

### Investigating: reported Haikubox detections not appearing after enabling
- Reproduced the 115-detection sync scenario synthetically end-to-end and every step worked correctly. Could not reproduce the reported symptom — root cause found two releases later (0.1.10.g, service-worker caching).

## 0.1.10.e — 2026-06-23

### New: master on/off toggle for the entire Haikubox feature
- `haikubox_enabled` (Settings → Account & Advanced → API Keys, default off) hard-hides every Haikubox surface immediately when disabled — devices, recordings, detections, profile links, dedicated page — rather than just pausing sync:
  - Sync loop checks the toggle fresh every poll cycle (takes effect within 15 min, no restart); stops touching `last_seen`/`status` while off.
  - `GET /recordings` excludes Haikubox rows entirely when disabled (previously never filtered at all).
  - Both dedicated endpoints return empty/zeroed results when disabled.
  - `GET /devices` excludes the virtual device row when disabled.
  - Manual "Sync Now" now returns a clear error when disabled instead of silently no-op'ing.
- Configured serial number persists independently of the enabled state; re-enabling immediately restores everything (nothing is deleted by disabling).
- Found and fixed: an existing DB upgrading to this version lands on `haikubox_enabled = None` (SQLite's `ALTER TABLE ADD COLUMN` doesn't backfill defaults) — every check treats `None` as falsy via `getattr(..., False)`, so upgrades default to safely hidden. Verified against a pre-existing test database through enable/disable/re-enable cycles.
- Added a clearer Devices-page distinction between "never configured" vs. "configured but disabled."

## 0.1.10.d — 2026-06-23

### Found and fixed: Haikubox device showing "offline" despite working sync
- Traced the full sync pipeline end-to-end with mocked API responses; ruled out the "auto-delete, no audio file" theory directly (Haikubox recordings never pass through `process_recording_bg`).
- Real cause: `Device.is_online()` used one fixed 2-minute staleness window for every device, but Haikubox only updates `last_seen` once per 15-minute sync cycle — so it showed offline ~13 of every 15 minutes even with sync working perfectly. Fixed with a platform-aware threshold (~30-minute window for Haikubox, matching the same ~4x-interval grace period the Pi's threshold implicitly used). Verified at 90s/15min/40min staleness against the real `is_online()` and `list_devices()` endpoint.
- Also fixed: the sync loop's failure paths never called `_update_device_status`, so a real outage left `last_seen` stale with no active offline signal.

### New: dedicated Haikubox Detections page
- Separate `/haikubox` page rather than filtering logic added to the main Recordings list (Haikubox rows were never hidden from `GET /recordings` — confirmed, never the bug). Simpler, lower-emphasis layout: no audio player, no spectrogram thumbnails, explicit "no audio attached" framing.
- Three entry points: a banner link on Recordings (only shown when Haikubox detections exist), a redirected link on the Devices page's Haikubox card, and species-filtered deep links from bird/bat profile pages (correctly absent on bat profiles, since Haikubox is bird-only).
- New endpoints: `GET /recordings/haikubox` (paginated, optional `species` filter) and `GET /recordings/haikubox/summary` (counts + per-species breakdown). Verified with real requests and browser screenshots.

## 0.1.10.c — 2026-06-23

### Recording detail page: Recording Details card moved below Notes
- Straightforward reorder, no functional changes.

### Settings page reorganized into 5 functional groups, cards default-collapsed
- 17 cards previously one flat list — reorganized into **Appearance**, **Detection**, **Notifications**, **Storage & Data**, **Account & Advanced**, matching the existing jump-to dropdown (simplified from 8 tabs to the same 5 groups). Data Management and Database Backup & Restore moved out of the old "Experimental" cluster into Storage & Data.
- Every card now starts collapsed by default; collapse state extended to a three-state model (never-touched / explicitly collapsed / explicitly expanded) so existing stored preferences keep working.

### Six new themes
- **Cornell Lab** — built on the Lab's actual 2015 Pentagram-redesign brand identity; Carnelian red (#B31B1B) is Cornell's real trademarked color; Nunito/Source Serif 4 substituted for the Lab's commercial Avenir/Mercury typefaces (no free release).
- **Field Notebook** — real repeating-gradient ruled-paper texture, aged-paper background, pencil-grey ink, Kalam accent font for headers only (body stays legible sans).
- **Dracula** — built from the official published Dracula spec (github.com/dracula/dracula-theme, MIT), exact hex values — not the unpublished paid "Dracula Pro" palette.
- Plus three from an earlier round this session: Plate, Oscilloscope, Aviary. All six verified visually via real browser screenshots.

### Found and fixed: accessibility bug affecting every light theme
- Tailwind's `text-gray-200` through `text-gray-400` were hardcoded directly in JSX across 32+ call sites in 7 files. Measured real WCAG contrast: 1.1–2.4:1 against light-theme backgrounds, failing even the 3:1 minimum for large text (`text-gray-500` marginal at 4.2–4.6:1).
- Fixed centrally via a CSS override scoped per light theme rather than touching 32+ JSX sites — specificity confirmed to win without `!important`.

### Custom theme builder
- Pick 5 colors (background, card, text, accent, border); every other variable (hover states, secondary/tertiary text, focus rings, shadows, full accent ramp) derived algorithmically via real HSL math (`lib/themeColors.js`).
- Two bugs caught before shipping: a wildcard `[data-theme]` CSS selector that would have corrupted every built-in theme the moment a custom one was created (fixed by scoping to the specific theme id); a derived `text-tertiary` blend that only hit 2.9:1 contrast (recalculated to 4.2:1+ across 5 test palettes).
- Applies via a dynamically-injected `<style>` tag; persists in `localStorage` as an id-keyed map. Full create → save → apply → edit → delete flow tested end-to-end.

### Haikubox and bat detections: now actually findable
- Detections were always correctly imported — the gap was navigational, with no way to actually find them among everything else.
- Added `device_id` and `is_bat` filter params to `GET /api/v1/recordings`. Haikubox device card's count is now a real link to a pre-filtered view; a "🦇 Bats only" toggle appears in the filter panel, only when bat detection is enabled.

### Audit: build and runtime error sweep
- Frontend build clean, backend syntax check clean, pyflakes clean (same two pre-existing benign findings only). Real-browser console sweep across Dashboard, Recordings, Settings, Life List, Devices, Regional Library, Tutorial: clean. All three new themes confirmed zero console errors.

## 0.1.10.b — 2026-06-22

### Fixed: species-color mismatch in the recording detail page's species dropdown
- The collapsible "N species detected" legend assigned colors via its own ad hoc indexing (`DET_COLORS[i % length]` on raw detection position) instead of the shared `speciesColor()` helper — so a species detected multiple times got a different color each occurrence.
- Fixed by routing both collapsed and expanded states through the existing `speciesColor(detections, name)` function. Verified against the exact reported scenario (1 Grosbeak + 7 Robins) — every Robin pill now consistent, matching the spectrogram and Detections list.

### Removed: redundant legend box baked into the spectrogram image
- The server-generated PNG's own `ax.legend()` box duplicated info already shown per-segment on the spectrogram and in the frontend legend (just fixed above), and visually overlapped detection segments. Removed; per-segment labels/coloring unaffected.

## 0.1.10.a — 2026-06-22

### Life List: broken "Upload to eBird" link replaced with a Download dropdown
- The old button opened a dead URL (`ebird.org/import/upload.do`); eBird's real flow now starts from a login-gated multi-step page with no direct deep link.
- Replaced with a single **Download** button + dropdown: **CSV (eBird format)** (existing export), **JSON** (new general-purpose export, explicitly labeled "not an eBird format"), **Open eBird Submit page** (working link). Verified end-to-end with real downloads.

### Fixed: eBird CSV export hardcoded "Country Code" to "US"
- Now does a real reverse-geocoding lookup from the deployment's configured lat/lon (`get_country_code_from_latlon()`, reusing the existing Nominatim endpoint), falling back to blank rather than a wrong guess if location/lookup is unavailable.

### New backend endpoint: `GET /api/v1/birds/life-list/json-export`
- Shares its species-aggregation query with the CSV export via a new `_life_list_records()` helper so the two formats can't drift apart.

### Performance: fixed a real N+1 query on the Likely Species page
- `SpeciesLikelihoodService` issued one query per species for profile photos (100-300+ round-trips per page load for a typical regional checklist) instead of the batched `IN (...)` pattern used elsewhere. Fixed to one batched query.
- Measured against a synthetic 200-species dataset: 200 queries / 68.9ms → 1 query / 5.0ms (~14x faster on local SQLite; larger gap expected on networked DBs).

## 0.1.9.z — 2026-06-22

### Three new themes — Plate, Oscilloscope, Aviary

Three additions to the "Distinct Looks" theme group (alongside Paper, Mono, Terminal), each grounded in a real physical reference point from the subject matter this app is actually about, not a generic palette swap:

- **Plate** — an engraved field-guide specimen plate: aged paper tone, a single deep indigo-ink color (deliberately not the expected terracotta-on-cream), hairline rules standing in for engraving lines, Crimson Pro serif headings, sharp corners throughout. Minimalist in restraint, realist in referencing an actual printed artifact rather than an abstract "light mode."
- **Oscilloscope** — a real instrument-panel faceplate, the kind of hardware this app's own spectrograms and waveform displays evoke: amber phosphor (a different instrument era and tone from Terminal's green), a CRT-glass vignette instead of scanlines, uppercase Space Mono headings tracked wide like a segment-display readout.
- **Aviary** — a natural-history museum specimen label: warm stone grey (a third light value distinct from both Paper's cream and Plate's aged-paper tone), a single confident clay-rust accent, zero borders on cards (shadow alone separates them, the way a label sits unframed on a gallery wall), condensed-caps Archivo Narrow structural labels, Work Sans body. The airiest and most restrained of the three.

Each is a real CSS-variable theme definition (color, type, radius, shadow, structural overrides), not a cosmetic recolor — verified by actually building the frontend and screenshotting all three rendered in the live app via Playwright, not just inspecting the CSS.

### Found and fixed: `--accent-500-rgb` was never defined by any of the 14 existing themes

While building the new themes, found that `.input:focus`'s glow ring (`rgba(var(--accent-500-rgb, 234 179 8), .08)`) had a fallback value but no theme — including the default Forest theme — ever actually defined the variable. Every theme's input focus ring was silently glowing Forest's amber regardless of the active theme's real accent color. Retrofitted all 14 existing themes (plus the 3 new ones) with their correct RGB triplet, computed directly from each theme's own `--accent-500` hex value rather than hand-converted, to close this out completely rather than just for the new themes.

### Found and fixed: Tutorial page's per-topic color legend ignored theme identity entirely

`Tutorial.jsx`'s section pills (the "What is Chirp? / Navigating Chirp / Dashboard..." quick-nav badges) use a fixed, hardcoded hex color per topic as a visual legend — by design, and a reasonable one for most themes. But this meant **Mono** (explicit "no glow, no extra color" design) and the new **Plate** theme (single-ink engraving aesthetic) both rendered a jarring multicolor rainbow of pills that broke their own stated design discipline — confirmed by screenshotting Mono before touching anything, proving this was a pre-existing inconsistency in the original theme set, not something introduced by the new themes. Separately, **High Contrast** (explicit WCAG AA theme) was rendering arbitrary unaudited hex colors with no guaranteed contrast ratio against its background, undermining the one thing that theme exists to guarantee.

Fixed with a new `--legend-mode` CSS variable (`multi` by default, `mono` for Plate/Mono/High Contrast) read via `getComputedStyle` rather than hardcoding theme IDs in JS, keeping the fix as data-driven as the rest of the theme system. When `mono`, pills fall back to the theme's own verified `--accent-400`/`--nav-active-bg`/`--border-default` instead of the per-topic hex value. Verified the fix using the app's real `applyTheme()` event-dispatch flow (not direct DOM attribute mutation, which doesn't trigger the same React re-render and gave a false negative on the first verification pass) — confirmed Mono/Plate/High Contrast now show a single consistent accent color, while Oscilloscope/Aviary and all original themes correctly keep the multicolor legend unchanged.

## 0.1.9.y — 2026-06-22

### OLED showing only Argon ONE defaults — real root cause found, not the daemon conflict

Initially suspected `argononed` (the Argon ONE's own OLED daemon) fighting Chirp's `display.py` for the screen, per a fix from an earlier session (`fix-argon-oled.sh`). Checked logs first rather than assuming: `argononed`/`argoneon` were confirmed **not installed** on the affected device, ruling that out. The real cause, found directly in `journalctl -u chirp-device`: `OLED disabled — luma.oled not installed: No module named 'luma'`. Chirp's own display code was never even attempting to draw anything — nothing was overwriting the Argon ONE's own bootloader-level default content, because Chirp had no way to draw over it at all.

**Actual root cause:** `install.sh` installed Python dependencies from a separate, hand-typed `pip install` package list rather than from `requirements.txt`. The two had silently drifted apart — `luma.oled`, `smbus2`, and `Pillow` (all three required for the OLED, and all three correctly listed in `requirements.txt`) were missing from the hand-typed list, so a fresh install never pulled them in. `pyusb` (ReSpeaker LED control) had the same gap. In the other direction, `requirements.txt` had `gpiod` commented out as "optional" when it's actually required unconditionally for the OLED's GPIO 27 page-button — `install.sh`'s hand-typed list already (correctly) installed it regardless, masking that inconsistency until now.

**Fixed structurally, not by patching the list again:** `install.sh` now runs `pip install -r requirements.txt` directly — there is exactly one place dependencies are declared for this project from now on, eliminating this entire class of drift rather than just today's three missing packages. `requirements.txt`'s `gpiod` line uncommented to match its actual (not "optional") status. Verified by actually installing into a fresh venv and confirming all five previously-inconsistent packages (`luma.oled`, `smbus2`, `Pillow`, `pyusb`, `gpiod`) import successfully — not just inspected, executed.

**Also added:** the installer's self-test now explicitly imports the OLED display stack and prints a clear warning with the fix command if it's missing, instead of self-test passing cleanly while the OLED silently degrades — verified by reproducing the broken (pre-fix) environment and confirming the new check correctly flags it.

**Found and fixed a real bug in `fix-argon-oled.sh` while diagnosing this:** the script's final "restart Chirp so the change takes effect" step checked for and restarted `chirp.service` — but the actual systemd unit `install.sh` creates (and what's actually running on real devices) is `chirp-device.service`. The check would have silently done nothing on every real installation; the daemon-stop/disable steps before it were unaffected, but the final restart step never actually restarted anything. Fixed to use the correct service name. Confirmed no other reference to the wrong name exists anywhere else in the device codebase.

**For anyone who already has Chirp installed and is missing the OLED display:** re-run `./install.sh`, or manually run `pip install -r requirements.txt` inside the existing venv, then `sudo systemctl restart chirp-device`.

## 0.1.9.x — 2026-06-22

### Dashboard "Today" stats fixed — was using midnight UTC, not local midnight

`GET /api/v1/recordings/statistics/dashboard-summary` computed "today" as `datetime.utcnow().replace(hour=0,...)` — midnight UTC, not midnight in the server's configured timezone. For any deployment west of UTC (including the documented Massachusetts example, UTC-4/UTC-5), this meant "today" actually started 4-5 hours into the previous evening, silently including yesterday's late-evening activity and excluding the true start of today's. Fixed using the same `zoneinfo`-based local-time conversion already used elsewhere in this file for hour-of-day bucketing: convert "now" to the configured timezone, take local midnight, then convert that boundary back to naive UTC for the query (since `Recording.trigger_timestamp` is stored as naive UTC). Verified with a reproduction at the exact boundary the bug affected — a recording 30 minutes after local midnight but still before UTC midnight — confirming it's now correctly included as "today" and a recording from the previous local evening is correctly excluded, where the old code got both backwards.

### Bat detections fully integrated into Recordings, Life List, and Bird Library

Bat-echolocation activity previously lived in its own standalone `bat_activity` table, surfaced only as an experimental panel on the Devices page, entirely disconnected from everything else in the app. Bat detections now flow through the same `Recording`/`Detection`/`BirdProfile` tables every bird detection uses, with a `Recording.is_bat` flag and pulse-train stats kept in a `bat_metadata` JSON column (the data doesn't fit bird-shaped `Detection` fields). Concretely, this means:

- **Bat activity now appears in Recordings** like any other detection — `RecordingsList`/`RecordingDetail` work unmodified for the most part, since both already query the shared tables. A 🦇 icon replaces the generic bird icon where no species photo exists.
- **A bat detection automatically appears in the Life List and Bird Library** — both already query `Detection`/`BirdProfile` directly, so routing bat detections through the same tables means zero new query logic was needed for either. Verified directly: creating a bat Recording and calling the real `get_life_list()`/`list_bird_profiles()` functions shows "Bat" in both.
- **A single static "Bat" profile** (not a real species — no acoustic species classifier is enabled by default; see below) is created automatically on first detection, with original hand-written content covering bat biology and echolocation, sourced from and citing Wikipedia's "Bat" and "Animal echolocation" articles, substantially reworded per this project's standing copyright policy. No range map (a "Bat" entry spans 1,400+ species — there's no single range to show), gated via a new `BirdProfileOut.is_bat` flag the frontend checks before attempting to render one.
- **A dedicated bat spectrogram** — the existing bird spectrogram generator resamples to 22050 Hz and uses mel scaling, both wrong for echolocation calls that run from ~9 kHz to over 150 kHz. The new `generate_bat_spectrogram()` loads audio at its native rate (no resampling), uses a plain linear-frequency STFT, and caps the y-axis at 96 kHz — the Nyquist ceiling for this project's documented 192 kHz-capable ultrasonic hardware path. **Found and fixed in the same pass:** `GET /recordings/{id}/spectrogram` always built its cache filename and regeneration call assuming the bird convention; for a bat recording it would never find the already-generated bat spectrogram and would silently call the bird generator against ultrasonic audio on any cache miss, destroying the recording's only useful content. Fixed by branching on `is_bat` at the top of that endpoint. Verified both the cache-hit and cache-miss/regenerate paths directly.
- **No lossy compression for bat clips** — Opus (the default medium/low storage-compression preset) targets human hearing range and would resample away or discard everything above ~24 kHz, the only part of a bat recording that matters. Bat recordings skip the compression step entirely; the clips are tiny enough that this costs negligible storage.
- **The "Bat Activity" panel removed from the Devices page** — replaced by bat recordings simply appearing in Recordings like everything else. Cleaned up now-orphaned icon imports (`Play`, `Pause`, `Sparkles`) that had no other consumer after the panel's removal.

### Experimental, off-by-default: bat species classification backend (BatDetect2)

Backend plumbing for optional bat species classification via the open-source BatDetect2 model, gated behind a new `bat_species_id_enabled` setting (default off, no frontend exposure yet by design — this is backend-only groundwork for now).

**Read before enabling:** the bundled BatDetect2 model classifies among 17 UK bat species only. This project's documented deployment is Massachusetts — none of those species are native to most of North America, and the model has no out-of-distribution rejection, so it will confidently assign any input to its closest UK match regardless of whether that's actually correct. Every stored prediction carries `validated: false` for exactly this reason. This is genuinely useful to have wired up and tested now, ahead of either a future North-America-trained model or a custom fine-tune (which the upstream tooling explicitly supports), but isn't something to trust for real identification today.

Implementation: a new `services/bat_species_id.py` lazily imports `batdetect2` (pulls in PyTorch — a multi-hundred-MB dependency, listed but commented out in `requirements.txt` rather than installed by default) only on first real use, so a normal deployment with the setting off never pays any import or load cost. When enabled, runs on the raw native-rate clip (not the spectrogram image or the time-expanded playback version, both wrong inputs for a model trained on real-rate audio) as part of the existing bat background-processing pipeline, storing `{model, model_trained_on, predicted_class, class_prob, det_prob, call_count, validated: false}` under `Recording.bat_metadata.species_guess`. Verified end-to-end with a synthetic test signal — and the model's own output on that test (confidently labeling an obviously-synthetic non-bat signal as a real UK species) served as a live demonstration of exactly the caveat the docstring describes.

**Per current instructions, no frontend work or per-species "Bat" profile variants exist yet** — every bat detection today is still attributed to the single general "Bat" profile regardless of whether species ID is enabled. That's intentional groundwork for later, not an oversight.

## 0.1.9.w — 2026-06-22

### `GET /api/v1/devices` 500 error fixed — same bug class as the settings crash, one endpoint over

Your logs showed: `fastapi.exceptions.ResponseValidationError: 1 validation error: {'type': 'string_type', 'loc': ('response', 0, 'api_key_id'), 'msg': 'Input should be a valid string', 'input': None}` from `list_devices` in `app/api/devices.py`.

Root cause: `Device.api_key_id` is `nullable=True` *by design* — virtual devices like the Haikubox sync device are created with `api_key_id=None` because they have no real device API key to associate with. But the response schema, `DeviceOut`, declared `api_key_id: str` with no `Optional` and no default. The moment a Haikubox virtual device exists in your database, every call to `GET /api/v1/devices` throws before it can return anything — which also explains why your real, already-paired Raspberry Pi appeared to vanish from the device list. It never re-paired or lost connectivity; the endpoint that lists devices was crashing on the Haikubox entry before your Pi's row was ever serialized. Heartbeats and config polling from the Pi continued succeeding the whole time, confirmed in your logs (`heartbeat HTTP/1.1" 200 OK`) — only the list view was broken.

**Fix:** `DeviceOut.api_key_id` changed to `Optional[str] = None`, matching the model's actual nullability and the documented reason for it.

**Proactive fix, found before being reported:** since this is now the second instance of "model column is genuinely nullable for a pre-existing-row or by-design reason, but the response schema doesn't allow `None`," I ran a systematic sweep of every `*Out` response schema against every model's nullable columns, filtering out the many false positives where a SQLAlchemy column `default=` value fires on every `INSERT` and a `NULL` can never actually occur in practice. One more genuine instance turned up: `BirdProfileOut.enrichment_complete` — `bird_profiles.enrichment_complete` was added via the same kind of `ALTER TABLE ADD COLUMN` migration as `bat_detection_enabled`, which leaves existing rows `NULL` rather than backfilling the Python-level default. A bird profile enriched before that column existed would hit the identical crash on its profile page. Fixed the same way: `Optional[bool] = False` in the schema, plus `bool(profile.enrichment_complete)` at the one call site that constructs it, matching the existing `extra_photos or []` / `call_media or []` guard pattern already used on the adjacent lines.

**Verified** both fixes against the real code with synthetic databases reproducing the exact failure: a `Device` row with `api_key_id=None` alongside a normal paired device (both now serialize correctly), and a `bird_profiles` row predating the `enrichment_complete`/`call_media` columns, migrated forward and left `NULL` (now returns `False`/`[]` instead of crashing). Also confirmed no regression on normal, fully-populated rows of both types — real values pass through unchanged.

No database migration required — both are pure application-code fixes.

## 0.1.9.v — 2026-06-22

### Settings page 500 error fixed — `GET /api/v1/settings` crashed on every call

Your logs showed the exact failure: `pydantic_core._pydantic_core.ValidationError: 1 validation error for SettingsOut — bat_detection_enabled — Input should be a valid boolean [type=bool_type, input_value=None, input_type=NoneType]`.

Root cause: `bat_detection_enabled` is a new column added this sprint. The startup migration correctly runs `ALTER TABLE app_settings ADD COLUMN bat_detection_enabled BOOLEAN` on existing databases, but SQLite fills new columns with `NULL` on pre-existing rows — there's no automatic backfill step. The response schema (`SettingsOut`) declared this field as a plain `bool` rather than `Optional[bool]`, so Pydantic rejected the `NULL` and threw before the endpoint could return *anything* — including your actual saved latitude/longitude. That's why location appeared to be "lost": the endpoint that returns it was crashing before it ever got there. Your settings were never actually deleted or overwritten.

This is the same failure mode that four other fields (`auto_delete_recordings_days`, `auto_purge_empty_recordings`, `max_recordings_gb`, `share_location_with_ebird`) were explicitly already guarded against in `_get_or_create()`'s NULL-backfill list, with a comment noting exactly this risk — `bat_detection_enabled` was simply the one field added afterward that didn't get added to that list alongside it.

**Fix, at both layers:**
- `bat_detection_enabled` added to the `_defaults` backfill list in `_get_or_create()` — the stored value is now corrected to `False` in the database itself the next time settings are loaded, not just patched over in the API response.
- `SettingsOut.bat_detection_enabled` changed from `bool = False` to `Optional[bool] = False` — defense in depth, so if any future migrated column is ever missed from the backfill list, the endpoint degrades to returning a default instead of throwing a 500 that takes every other setting down with it.

**Verified** by reproducing the exact scenario in a synthetic database (pre-existing row with location set, `bat_detection_enabled` column added via the real migration and left `NULL`) and confirming against the actual `get_settings()` code: the endpoint no longer crashes, returns the real stored location correctly, and the stored value is backfilled to a real boolean rather than staying `NULL`.

No database migration required for this fix — it's a pure application-code change. The devices-table migration from 0.1.9.u is unaffected and unrelated.

## 0.1.9.u — 2026-06-22

### Fixed the exact reported bug, then generalized the fix to catch the whole bug class

Your log showed `sqlite3.IntegrityError: NOT NULL constraint failed: devices.api_key_id` on every Haikubox sync attempt. Root cause: SQLite can't retroactively relax a column constraint on a table that already exists — `models.py` has said `api_key_id` is nullable for a while (virtual devices like Haikubox don't have a real device API key), but a database created before that model change keeps enforcing the old `NOT NULL` forever, since `_migrate_columns()` only handles *adding* new columns, not changing existing ones. Every 15-minute Haikubox sync was hitting this and failing silently in the background — the "online" status you might have seen briefly between failures, but the data was never actually landing.

Rather than a one-off patch for just this column, added a startup check that compares every table's live schema against the model generically, so the same bug class can't quietly reappear somewhere else later. When it rebuilds a table, it preserves the table's own actual columns exactly as they exist on disk — not the ORM's idea of the schema — which matters: `devices.ssh_username` exists in some installs via a raw `ALTER TABLE` without ever being declared on the `Device` class, and an earlier version of this fix would have silently dropped that column (and its data) during the rebuild. Tested against a synthetic reproduction of the exact reported scenario: data preservation (including that non-ORM column), the actual error resolved, and safe to run on every restart without re-doing the work once fixed.

### Second bug found while investigating: `ssh_username` was never actually saving

`device.ssh_username = username` was being set via plain Python attribute access, but `ssh_username` wasn't declared as a real column on the `Device` model — SQLAlchemy treats that as a transient in-memory value, not something to persist. It looked like it saved (the object held the value for the rest of that request), then was gone again on the next server restart. Declared it properly and verified it survives a simulated restart now. This is a believable contributor to settings "seeming to be lost" — not the only explanation, but a real one.

### Two frontend bugs from a systematic sweep, not just the one that might have been visible

`setSoftDeletedCount(d.soft_deleted_count).catch(() => {})` and `setRecent(r.items || r).catch(() => {})` both called `.catch()` on a React state setter's return value (`undefined`) instead of the actual promise chain — silent `TypeError`s caught by an outer `.catch()`, invisible in the console. Found both by searching the whole frontend for the pattern rather than stopping after the first one.

### Performance: Life List and Statistics pages were doing a full unbounded scan on every visit

Timed both against a realistic synthetic 50,000-recording/80-species database rather than assuming: ~1.2-1.6s cold, every single time either page loaded, and that only gets worse as more recordings accumulate. `EXPLAIN QUERY PLAN` showed SQLite falling back to two temporary B-tree sorts (GROUP BY then ORDER BY) with no index able to help, since the aggregate spans a join across two tables. Added a 45-second cache to both — repeated visits dropped to ~0.003-0.005s in testing. Wired the settings-save path to invalidate both immediately rather than waiting out the TTL, since their output depends on two settings (`show_deleted_detections`, `min_confidence_display`) that should apply right away, not up to 45 seconds later.

This is the same caching approach as the storage-status fix from last time, applied somewhere it was also needed — chose a time-based cache over trying to maintain these aggregates incrementally, since incremental maintenance would need to stay correctly in sync with those two filter settings independently, and a subtle bug there would mean *wrong* data rather than just *slow* data.

## 0.1.9.t — 2026-06-21

### Found and fixed the real cause of "settings page takes forever to load / won't load"

The settings page's `/recordings/storage/status` call did a full `os.walk()` over the entire recordings directory, calling `os.path.getsize()` on every single file, on *every single page load* — no caching at all. This gets slower as recordings accumulate over weeks/months of real use, especially over network-attached or spinning-disk storage (a typical Unraid array without an SSD cache). Built a realistic 40,000-recording test database with real files on disk to confirm this rather than guessing: cold load took 0.14s in this sandbox's fast local SSD, but on slower storage with real multi-megabyte WAV files instead of 1KB test stubs, this is exactly the kind of operation that can stretch into many seconds or longer — and it happened on every single visit to Settings, not just the first.

Added a 60-second TTL cache (`app/cache.py:dir_size_cache`) around the directory walk. Repeated settings-page visits within that window are now ~55x faster (0.0026s vs 0.14s in the test). Added a `force_refresh` parameter and used it at the three call sites inside the storage-cleanup background task, which genuinely need fresh values to make correct before/during/after pruning decisions — caching those would have introduced a real correctness bug while fixing a performance one.

Also found and fixed a real frontend bug while investigating: `setSoftDeletedCount(d.soft_deleted_count).catch(() => {})` called `.catch()` on the return value of a React state setter (`undefined`), not on the promise chain — a `TypeError` that got silently swallowed by an (correctly-chained) outer `.catch()`, meaning the soft-deleted-recordings count silently never updated. This is exactly the category of bug that static tools (eslint, the build) can't catch since it only manifests at runtime when the promise resolves — and since it gets caught and swallowed, it doesn't even surface as a console error during normal page-load testing. Fixed the chaining. Also cleaned up a stale comment describing per-user notification-preference merging logic that doesn't actually exist in the current code (removed in an earlier refactor without updating the comment).

This doesn't fully explain "settings seem to be lost" as a separate symptom — verified the actual settings save/load logic (`SettingsIn` schema, the PUT handler's `exclude_none` partial-update pattern, the frontend's payload construction) is correct and wouldn't itself cause data loss. The most likely explanation is that the page hang made it look like settings had reset (showing default/blank form state while still waiting on the slow request) rather than the database actually losing anything — but flagging this honestly rather than claiming certainty I don't have, since I can't access the actual production database to confirm directly.

## 0.1.9.s — 2026-06-21

### Logo finalized: refined design with restored original proportions

Implemented the logo approved after the visual-renders review. Restores the original logo's proportions — separate head circle and body ellipse with the head clearly smaller than the body, plus a sharp tail wedge — instead of the single-continuous-silhouette redesigns from recent passes, which read as a fluffy cloud once the head and body blended into one rounded blob. Added real polish on top of the restored proportions: multi-stop gradients on every shape, a subtle radial highlight on both body and head for dimension, two-tone beak shading, and a double-highlight glossy eye. Shifted the wing from the original's green to a warm gold tone for palette cohesion — a deliberate judgment call, flagged as easy to revert.

Verified at full size, 128/64/32/16px, and as the filled app-icon variant before shipping anywhere — confirmed it reads clearly as a bird even at 16px, a real improvement over the cloud-like single-silhouette version. Propagated to `chirp-logo.svg`, the filled app-icon variant, all PWA/iOS icon sizes, both favicons, and the animated `ChirpLogo.jsx` nav logo (wing-flap + sequenced sound-wave-pulse, matching this design's simple closed beak — no beak-chatter animation needed this time).

## Dual-Mic Default Config + Repeat Audit — 2026-06-21

### Default config now sets up ReSpeaker + AudioMoth to take the best of both

`config.yaml` now explicitly lists "AudioMoth" in `audio.device_name_hints` and defaults `bat_echolocation.device_name` to "AudioMoth" — the cheapest mic that covers both bird and bat detection (~$80-100). Verified this isn't just a documentation change: confirmed via the actual matching code in both `audio.py` (bird pipeline) and `bat_detector.py` that an AudioMoth-named device gets picked up correctly by both, and that the bird pipeline's existing `snr_weighted_merge()` is exactly the "best quality of each" mechanism — both mics get opened as independent streams and merged with the stronger signal automatically dominating, no manual A/B choice. Tested the matching logic directly against realistic device name strings for both paths.

Added an honest caveat rather than overpromising: the bird pipeline and the bat detector open the same physical AudioMoth through two independent `sounddevice` streams, which works on most USB audio class hardware but depends on the specific ALSA/PortAudio setup — documented the practical resolution (dedicate the mic to one role) if a "device busy" conflict comes up, in both `config.yaml`'s comments and the device README.

`bat_echolocation.enabled` stays `false` by default — it's still an opt-in experimental feature requiring hardware most setups won't have; the config is just pre-filled correctly for whoever does have it.

### Repeated the full audit

Backend, device, and frontend all re-confirmed clean after this turn's changes (logo exploration files were kept outside the repo and never touched it; the config/README edits passed YAML validation, pyflakes, and the device-matching functional tests above). Build clean, eslint at the same 6 previously-reviewed warnings, zero errors throughout.

### Verified zero React console errors and clean builds

Loaded all 12 routes in a real headless browser (not just static lint) and checked for console errors, warnings, page errors, and failed requests. Zero issues found across every route. The frontend build itself is also clean (one pre-existing bundle-size advisory, not an error).

### Fixed: All About Birds range maps committing to broken URLs instead of falling back

Real bug, reported with a real example (European Starling): the range-map fallback chain (All About Birds → Macaulay Library → Wikipedia) had a logic error where the AAB and Macaulay Library blocks would commit to a captured image URL and `return` immediately — even when the actual download of that URL failed. The captured AAB URL is often tied to the Playwright scraping session via Cloudflare bot-protection cookies/headers; a URL that worked during the scrape can 404 when a plain browser `<img>` tag requests it later with no such session. The Wikipedia block (third in the chain) deliberately stores its raw URL on download failure, since that's a different, legitimate situation (Wikimedia blocks server-side fetches but browsers work fine) — but AAB and Macaulay had no such justification and were copying that pattern incorrectly.

Fixed both blocks to only commit and return when the local download actually succeeds; on failure, they now fall through to the next source in the chain instead of storing a URL already known to be broken. Tested three scenarios against the actual function: the happy path (AAB succeeds, Macaulay never gets called), the exact reported bug (AAB fails, falls through to a working Macaulay result), and a full chain failure (AAB and Macaulay both fail, falls through to Wikipedia's existing raw-URL behavior, unchanged). All three pass.

### Device-side audit (first comprehensive pass this session)

Ran the same pyflakes sweep on chirp-device that's been applied to chirp-server all along — this hadn't had a full pass yet this session, only individual files tested in isolation. Found and cleaned up 23 unused-import issues across 11 files (audio.py, birdnet_cpu.py, detector.py, config.py, birdnet_coral.py, discovery.py, display.py, recorder.py, server_sync.py, uploader.py, utils.py, zigbee.py) — all confirmed genuinely dead via grep before removal, no functional changes. One redundant local re-import in birdnet_coral.py followed the same pattern that caused a mistake earlier this session (two textually-identical import lines in different functions) — checked both occurrences individually this time rather than assuming, avoiding a repeat. One own mistake caught mid-fix: a sloppy single-line replacement in uploader.py created a duplicate `import logging` line — caught immediately by re-grepping before moving on, fixed properly.

Left two device-side findings as intentional, matching the same review standard applied to chirp-server: a `gpiod` import used purely as a library-availability probe (real usage happens via a separate import inside the actual button-handling thread), and respeaker.py's `np` undefined-name warning (a known false positive — numpy is imported locally inside the function; only a string type-hint annotation at module scope trips up pyflakes).

Verified every touched module still imports cleanly (11/11), all three device-side shell scripts and config.yaml still parse correctly, and re-ran the chirp-server backend, frontend (eslint), and a live server boot exercising endpoints across every area touched by recent sessions — auth, settings, bird profiles, devices, and the new bat-activity endpoints. No regressions found. The chirp-server backend and frontend were both already clean from the prior full audit; this pass re-confirmed that and extended the same rigor to chirp-device for the first time.

## Patent Application — 2026-06-20

### Added three new claim sets covering this session's novel work

Updated PATENT_APPLICATION.md with three new detailed-description sections and seven new claims (26-32):

- **Adaptive call-frequency audio enhancement** (claims 26-27): derives the isolating bandpass range from each individual vocalization's own spectral SNR rather than a fixed range across all species, plus edge tapering, explicit-noise-sample spectral gating, and soft amplitude limiting.
- **Ultrasonic echolocation pulse-train detection** (claims 28-30): an independently-operating subsystem (no species classification) using per-window SNR thresholding, duration-gated pulse identification, frequency-sweep classification, and pulse-train aggregation, plus on-demand frequency-downshifted playback generated by retagging raw samples at a reduced nominal sample rate without resampling.
- **AI-assisted photographic species confirmation** (claims 31-32): user-submitted photo persisted independent of confirmation outcome, optionally cross-checked against a vision-capable model.

Also corrected the provisional filing fee figure (was citing the outdated ~$160; current 2026 micro-entity fee is $65 per the Unleashing American Innovators Act's discount increase), added CPC classification guidance for the new subject matter, and flagged the AI-photo-confirmation claim as the weakest of the new set on its own (a fairly generic technique) with a suggested fallback to a dependent claim.

Created two companion artifacts: step-by-step USPTO Patent Center filing instructions (separate from the legal/technical "notes for counsel" already in the application), and three pitch email variants to Wildlife Acoustics (acquisition / licensing / partnership), updated to include the new ultrasonic detection capability as a point of relevance given Wildlife Acoustics own bat-detection hardware lines.

# Chirp — Changelog

**Author:** Joshua Salvi — josh.salvi@gmail.com
**Repository:** Private — source code access by permission only
**Status:** Pre-patent-filing. Source code is proprietary and not licensed for use.

## Version Scheme: `0.X.Y.Z`

Chirp uses a four-part version number. See the root `README.md` for a full explanation.

| Position | Meaning | Increments when… |
|---|---|---|
| `0` | Epoch | Always 0 until public commercial launch |
| `X` | Major | Breaking change or required manual migration |
| `Y` | Minor | New user-visible feature added |
| `Z` | Patch letter | Bugfix (`b`), critical hotfix (`c`), audit/docs (`d`), polish (`e`) |

## 0.1.9.p — 2026-06-20

### Bat mic recommendations expanded to a full price range

Researched and added options spanning under $100 to over $500, all confirmed standard USB audio class devices (no custom drivers) and Linux/Pi-compatible:

- **AudioMoth USB Microphone** (~$80–100) — genuinely the cheapest real option found; not a heterodyne toy, full spectrum to 384kHz, open-source hardware from Open Acoustic Devices, explicitly documented to work plugged into a Raspberry Pi.
- **Dodotronic UltraMic 192K/200K/250K** (~$200–275) — same product line at different sample rates.
- **Pettersson M500-384** (~$430–470) — the recommendation already used throughout this project's docs.
- **Dodotronic UltraMic Evo 384K** (~$745–800) — top of the range, dual omnidirectional sensors, lowest self-noise.

Updated both `config.yaml`'s comment block and the Settings UI hint to list the full range instead of just the two original options.

## 0.1.9.o — 2026-06-20

### Docs: clarified the ultrasonic mic runs alongside the ReSpeaker

Added an explicit note to `config.yaml` and the Settings UI confirming the ultrasonic bat mic (Pettersson M500-384 or Dodotronic UltraMic 192K) runs alongside an existing ReSpeaker bird mic with no conflict — `bat_detector.py` already opens its own independent capture stream at the ultrasonic mic's native rate, separate from the bird pipeline's 48kHz stream, so both run simultaneously off the same Pi. Also noted that the default empty `device_name` correctly auto-picks the ultrasonic mic when both are plugged in, since it reports the higher native sample rate.

## 0.1.9.n — 2026-06-20

### Logo reverted to a cleaner version of the original orange bird ("Bolder & Richer")

Per explicit feedback, reverted away from the single-silhouette redesigns of the past few versions back to the *original* logo's actual structure — separate head and body shapes, green wing and tail, visible feet, two sound-wave arcs — just cleaned up rather than restructured. Presented four mockups (minimal cleanup, softer rounded feet, bolder/richer, and a no-feet simplification) rendered side by side; user picked "Bolder & Richer" — bigger head for a friendlier proportion, more saturated gradients, a subtle dark stroke on the body/head shapes for definition.

Caught and fixed a real clipping issue *while building this one too*: the original mockup's declared 256×256 viewBox clipped the outer sound-wave arc (measured the actual rendered content bounding box rather than re-trusting hand-calculated coordinates after the last pass's mistake — it extended to x=263, past the 256 edge). Widened the canvas to 275×256 to properly contain it instead of cropping the design down to fit. Recalculated the square app-icon transform from the same measured bounding box, verified margins on all four sides came out even before regenerating any files.

Propagated to `chirp-logo.svg`, the filled app-icon variant, all PWA/iOS icon sizes, both favicons, and `ChirpLogo.jsx` (wing-flap + sequenced sound-wave-pulse animation — no beak-chatter this time, since this design has a simple closed beak rather than the previous version's open one). Confirmed no leftover hand-coded duplicate bird SVGs exist anywhere else in the frontend.

## 0.1.9.m — 2026-06-20

### Logo finalized: "Dynamic Mid-Call" (user-selected from 5 options)

Presented five distinct directions built from the original orange bird — cute/sleek, extra-chibi, flat/geometric, dynamic mid-call, and a closer restoration of the original two-shape silhouette — rendered and shown side by side. User selected the dynamic mid-call pose (head tilted up, open beak, energetic triple sound-wave arcs), flagged upfront as needing refinement since the open-beak shape hadn't rendered cleanly in the first pass.

Refined the beak through two more iterations before finalizing: the first redraw added a third overlapping shape that just made the cluster worse; the second simplified to two clean triangles sharing one hinge point with real background showing through the gap, which reads correctly as an open beak. Verified at 256px and 16/32px favicon scale — noting honestly that the open-beak detail naturally fades at favicon-tiny sizes, an inherent tradeoff of this more dynamic pose vs. a simpler closed-beak silhouette, not a flaw unique to the execution.

Caught a real clipping bug while building the square app-icon variant: the original scale/translate math put the outermost sound-wave arc's right edge at x=556 against a 512px canvas — would have shipped with a visibly clipped icon. Recalculated the transform from the actual content bounding box with proper margins on all four sides before regenerating any files, and confirmed the fix by rendering and checking the margins numerically, not just eyeballing it.

Propagated to `chirp-logo.svg`, the filled app-icon variant, all PWA/iOS icon sizes, both favicons, and `ChirpLogo.jsx` — added beak-open/close animation (chirpBeakChatter) alongside the existing wing-flap and sound-wave-pulse animations to match the new pose. No palette change needed (still the same orange/amber from the previous pass) — manifest `theme_color`/meta tag left as-is.

## 0.1.9.l — 2026-06-20

### Bat clip playback with frequency downshift (completes the server round-trip)

Bat activity events now upload from the device to the server and can be played back with an Original/Enhanced toggle — "Enhanced" here means frequency-downshifted into human hearing range, not noise-reduced (a fundamentally different operation than the bird "Enhanced" toggle, since there's no noise to clean up — the issue is the signal itself being above human hearing).

**Backend:** new `BatActivity` model/table, `services/audio_processor.py:downshift_bat_clip()` (same time-expansion technique already proven in the device-local snippet save — verified server-side too: a synthetic 40kHz tone correctly comes out as a ~4kHz audible tone after downshift), and a new `app/api/bat_activity.py` router (list / upload / raw audio / enhanced audio / delete). The upload endpoint requires the same `X-API-Key` device authentication as bird recording uploads — tested all three cases live (no key → 401, wrong key → 401, correct key → 200).

**Device:** `bat_detector.py` now uploads each detected event to the server (reusing the existing `server_sync` connection details — same base URL and API key already configured for pairing, no new config fields needed) with the *raw* native-rate audio, alongside the existing local time-expanded snippet save (both still happen — the local copy doesn't require a server connection). Refactored the snippet-audio extraction into a shared helper so the local save and the server upload don't duplicate that logic. Verified with a full real device→server test: synthetic pulse train detected, uploaded, and confirmed present on the server with `has_audio: true`.

**Frontend:** new collapsible "Bat Activity" panel on the Devices page, listing detected events with pulse count / peak frequency / sweep %, a play button, and the same ✨ Original/Enhanced toggle pattern used for bird clips (defaults to Enhanced/audible).

## 0.1.9.k — 2026-06-20

### Full frontend/React audit

Ran eslint (rules-of-hooks, exhaustive-deps, jsx-key, no-undef, no-dupe-keys, no-unreachable) across all 25 components. Zero errors. Six exhaustive-deps warnings, all re-verified individually rather than trusted from memory — every one is a deliberate, justified exclusion (React Router's `navigate` has a stable identity; `RecordingsList`'s scroll-restore effect would fight itself if `saved.scrollTop` triggered re-runs; `SSHTerminal`'s connection-setup effect intentionally doesn't tear down an active session just because a prop reference changed; etc.) — confirmed none, left unchanged.

Two real fixes from the deeper pass:

- **Latent XSS pattern in Changelog.jsx:** its lightweight markdown renderer applied `**bold**`/code/link formatting via `dangerouslySetInnerHTML` without escaping raw HTML first, so a literal `<script>` in the source text would have executed as-is. Practical risk is low today (changelog content is developer-authored, not user-submitted) but the renderer itself shouldn't assume that forever. Added an `escapeHtml()` pass before the markdown transforms in both `inline()` implementations in the file — tested that normal bold/code/link formatting still renders correctly and that a `<script>` tag now comes out as harmless escaped text.
- **No app-wide error boundary** — explains the blank-screen crash fixed in v0.1.8.b. A good pattern already existed but only locally in `Devices.jsx` (added a while back for SSH/discovery crashes specifically). Extracted it into a shared `ErrorBoundary.jsx` and wrapped the route-level `<Routes>` in `App.jsx` with it, so any page crash now shows a recoverable "Something went wrong" card instead of a blank screen — and resets automatically on navigation, since it sits inside the same `key={location.pathname}` container that already remounts on route change. `Devices.jsx` now uses the shared component instead of its own duplicate copy of the same ~15 lines. Verified with a real client-side React render (JSDOM + `createRoot`, not server-side rendering, which doesn't support error boundaries the same way) using a deliberately-crashing test component — confirmed the fallback UI renders with the correct page label, error message, and working "Try again" button.

## 0.1.9.j — 2026-06-20

### Microphone recommendations (and a documentation bug caught along the way)

Added a researched "Microphone Recommendations" section to `chirp-device/README.md`. The core finding, from the BirdNET-Pi community's own well-reasoned discussion: beamforming/voice-array mics are the wrong tool for omnidirectional bird call capture, even though they're good hardware — that DSP is built to isolate one direction's voice and suppress everything else, the opposite of what's needed when calls can come from any direction.

While checking whether this applied to Chirp's own ReSpeaker support, found the actual situation is better than expected but the code's comments were wrong: `respeaker.py`'s default path (6-channel firmware, what most ReSpeaker units ship with) already reads the 4 raw per-capsule channels and averages them to mono, bypassing the chip's beamforming DSP entirely — exactly right. But the 1-channel-firmware code path had a comment claiming that beamformed single-channel output was "preferred for BirdNET," which is backwards per the research. Fixed the comment and the user-facing description string, verified the channel-selection logic itself is unaffected (tested all firmware variants — 1/2/4/6/8-channel — still resolve to the same channel plans as before, only the description text changed).

Documented recommended alternatives in order of expected quality: a Primo EM172/EM272-capsule lavalier mic + USB audio interface (~$100, the community's top pick), a Blue Yeti Nano set to omnidirectional (~$90, simpler one-box option), or any explicitly-omnidirectional budget USB mic.

## 0.1.9.i — 2026-06-20

### Argon ONE OLED takeover fix

The OLED was still showing the Argon ONE's own default screens (IP/CPU temp) instead of Chirp's — root cause: the Argon ONE v5 Industria case's own setup script installs `argononed.service`, a daemon that controls the same physical OLED and wins the conflict against Chirp's `display.py`.

`install.sh` now detects and disables `argononed`/`argoneon` automatically (new Step 7/8) on fresh installs. For an already-installed device, added a standalone `fix-argon-oled.sh` that does the same thing without a reinstall — confirms the service exists, explains the trade-off, asks for confirmation, then stops/disables it and restarts the Chirp service so the change takes effect immediately.

Researched the actual trade-off rather than guessing: for the Argon ONE v5 specifically, the fan is controlled by the Pi's own kernel thermal governor, not by `argononed` over I2C (that's only true of the older v1–v3 Argon ONE cases) — confirmed via Argon40's own official forum. So disabling this service is safe for cooling. What it does lose is the case's physical power button (press to reboot/shutdown), since that daemon handles both the OLED and the button — documented clearly rather than silently dropping the functionality. SSH-based shutdown still works fine, and Chirp's own GPIO 27 OLED page-advance button is a separate pin, unaffected either way.

## 0.1.9.h — 2026-06-20

### Logo redo: cuter, sleeker version of the original orange bird

Redid the v0.1.9.f redesign per feedback — that version shifted to a gold/amber palette, but the ask was for a cuter and sleeker take on the *original* orange bird, not a new color direction. Reverted to the orange/amber gradient (closer to the original `#fb923c`→`#ea580c`) and kept the structural cleanup (single continuous body+head silhouette, no disconnected feet). Made it cuter with a bigger head-to-body ratio and a larger, softer eye with two highlight dots, and sleeker by replacing the original's clashing green wing with a harmonized rust-brown tone pulled from the same warm palette. Verified at 512px, 32px, and 16px again before propagating.

Updated everywhere: `chirp-logo.svg`, the filled app-icon variant, all PWA/iOS icon sizes, both favicons, and `ChirpLogo.jsx` (the animated nav-bar logo). Caught the same kind of viewBox-margin issue as last time before shipping — rendered the exact SVG content standalone to confirm the sound-wave tips weren't sitting right at the clipping edge, then added a few extra units of margin to be safe across browsers. Reverted the manifest `theme_color`/meta tag and a Tutorial.jsx accent color back from the gold I'd set in 0.1.9.f to match the restored orange palette.

## 0.1.9.g — 2026-06-20

### Full backend audit

Ran pyflakes across every file in `app/`, found and fixed real issues (not just cosmetic ones):

- **Haikubox timestamp drift (real bug):** detection timestamps were stored as if device-local time were already UTC, drifting by the device's UTC offset (e.g. 5 hours off for US Eastern). Now properly converts using the device's reported IANA timezone via `zoneinfo`. Verified the fix produces the correct UTC time against a worked example.
- **Two silently-swallowed exceptions (real bug):** `_fix_swapped_taxonomy` and `_clear_stale_description_sections` in `database.py` logged `"error: {e}"` as a plain string instead of an f-string, so the actual exception text was never included in the log — just the literal text `{e}`. Fixed both.
- **Dead code removed:** an unused in-memory buffer in the backup-download endpoint (it actually streams via a temp file), an orphaned aspect-ratio calculation in the range-map SVG endpoint (superseded by a later, separate calculation that does the real work), and a couple of computed-but-never-used local variables.
- **~30 unused imports** removed across `api/`, `services/`, `models.py`, `cache.py` — caught and corrected one self-inflicted mistake along the way (a blind text-replace removed the wrong one of two identically-worded `from sqlalchemy import func` lines, breaking the one a different function actually needed — caught immediately by re-running pyflakes and a live endpoint test, fixed before commit).
- Left two flagged items as-is on review: a leading-underscore unused tuple-unpack variable (`_hw`) that's a deliberate, self-documenting idiom, and a `# noqa: F401`-marked import that's intentionally there for its model-registration side effect.

Verified with a live server boot afterward, exercising the specific endpoints whose imports were touched (including the one with the `func` mistake) — all return correct responses, no tracebacks.

## 0.1.9.f — 2026-06-20

### Logo redesign, propagated everywhere

Redesigned the bird mark: a single continuous body+head silhouette instead of two overlapping disconnected ellipses, dropped the small leg details (broke down to mud at favicon sizes without adding recognition value), and shifted the palette from orange/red+green to gold/amber+brown to match the app's own actual default accent color (the Forest theme, `#eab308`) instead of an unrelated pairing. Verified at 512px, 32px, and 16px by actually rendering the SVG before propagating it everywhere, not just eyeballing the path data.

Updated everywhere the old mark appeared:
- `chirp-logo.svg` (used for the Docker `/icon.svg` endpoint) and a new filled rounded-square variant for app-icon contexts
- All PWA icons (`icon-192.png`, `icon-512.png`, `apple-touch-icon.png`), `favicon.ico` (proper multi-res 16/32/48), `favicon.svg`
- All 16 iOS icon sizes in `ios-icons/`, regenerated at their exact required dimensions
- `ChirpLogo.jsx` — the actual animated in-app logo (wing-flap + pulsing sound waves) shown in the nav header and login screen; this was a hand-coded SVG separate from the static logo file with the *old* color scheme, so it was genuinely a second inconsistent bird in the app until now. Found and fixed a real bug while doing this: my first pass set the viewBox width to only fit the body silhouette's own bounding box, which would have clipped the beak and both sound-wave arcs (they extend further right) — caught by actually rendering it before shipping, not just by reading the path data.
- Tutorial.jsx's small duplicated mini-logo SVG, replaced with the shared `ChirpLogo` component instead of a second hand-coded copy
- PWA manifest `theme_color` and `index.html`'s `theme-color` meta tag (shown in mobile OS task switchers), updated to the new gold accent

Deliberately left unchanged: the Raspberry Pi's OLED splash-screen pixel art (`chirp-device/chirp/display.py`) — it's monochrome (no color-consistency issue to fix) and hand-tuned at the pixel level for real SSD1306 hardware I can't visually verify against here; redrawing it blind risked breaking something I couldn't test.

## 0.1.9.e — 2026-06-20

### Three structurally-distinct new themes

The 11 existing themes were all the same card shape/shadow/font with a different accent color. Added three that change the actual look, not just the palette — introduced new themeable CSS variables (`--radius-card`, `--shadow-card`, `--radius-btn`, `--btn-primary-text`) that every existing theme inherits unchanged (zero visual difference for them), which the three new themes override:

- **Paper** — light mode (first one Chirp has), warm cream background, dark green ink accent, sharp 4px corners, soft paper-like shadows instead of glow, serif headings, grain texture disabled, `color-scheme: light` so native form controls/scrollbars render correctly too.
- **Mono** — flat minimal dark, single neutral accent, zero glow/shadow/grain, sharp 2px corners, the live-pulse dot animation disabled (flat means flat).
- **Terminal** — retro CRT, phosphor green on near-black, monospace font cascaded from the theme root (no per-component changes needed), 0px corners, a subtle animated scanline overlay via a new `body::after` layer.

## 0.1.9.d — 2026-06-20

### Bird photo upload + AI species confirmation

Bird profile pages now have a "Photos" section where anyone can upload their own photo of the species — separate from the auto-enriched Wikipedia/iNaturalist photo, stored in a new `bird_photos` table. Drag-and-drop or tap-to-choose, JPEG/PNG/WebP/GIF up to 8MB, with a lightbox view and delete.

**AI confirmation (optional):** if an Anthropic API key is configured in Settings → API Keys, each uploaded photo is sent to Claude (haiku model, vision input) with a prompt asking it to identify the bird and compare against the profile's species — purely a sanity-check second opinion on a user-submitted photo, not a replacement for the BirdNET audio detection. Without a key configured, upload works exactly the same, there's just no confirmation badge. Tested against the real Anthropic API (with a deliberately invalid key) to confirm the 401 path is handled gracefully — upload still succeeds, the photo just shows as not-AI-checked with a note explaining why.

New backend: `BirdPhoto` model (`bird_photos` table, auto-created — no migration entry needed since it's a new table, not a new column), `services/photo_id.py` (the Claude API call + response parsing), and `POST/GET /birds/{id}/photos`, `GET/DELETE /birds/photos/{id}[/file]` endpoints. The file-serving endpoint is exempted from JWT auth the same way other media endpoints are (so `<img>` tags work without needing to attach a Bearer token).

Tested the full flow live: upload without a key (ai_checked=false, succeeds), upload with a key (real network round-trip to api.anthropic.com), file serving, and delete — all clean, no tracebacks.

## 0.1.9.c — 2026-06-20

### Animated tutorial demos

Two new self-looping animated components on the Getting Started page, built on the existing Tailwind keyframe library (fadeIn/slideUp/etc. — no new dependencies):

- **EnhanceAudioDemo** (Recordings section) — auto-cycles through tapping the ✨ toggle: a tap-ripple animation, the waveform cross-fading from a jagged "noisy" path to a smoother "enhanced" one, and the button's color/label transitioning, with a status caption that updates per phase. Loops continuously.
- **NavigationDemo** (Navigating Chirp section, mobile subsection) — replaces the old static bottom-nav mockup with one where a sliding highlight pill animates between Dashboard / Recordings / Life List / Field Guide every 1.3s, with a small tap-indicator dot popping in above the active icon.

## 0.1.9.b — 2026-06-20

### Bat echolocation detection (experimental/beta)

New `chirp-device/chirp/bat_detector.py` — an independent ultrasonic capture and pulse-detection pipeline, entirely separate from the BirdNET bird pipeline (different microphone, vastly different sample rate). To be upfront about scope: this detects the *presence* of echolocation-like activity (pulse count, peak frequency, whether the call swept in frequency) — it does not identify species. There's no bundled bat-species classifier comparable to BirdNET; building or faking one wasn't something to do honestly within this feature, so it isn't claimed.

**Hardware requirement, the important part:** bat calls run ~15–120kHz; a standard USB mic (including the ReSpeaker this project otherwise uses) samples at 48kHz and physically cannot capture above 24kHz. A separate ultrasonic USB microphone at 192kHz+ is required. Recommended: **Pettersson M500-384** (~$400–465, standard USB audio device, no custom drivers, native Linux support, full spectrum to 384kHz) or the cheaper **Dodotronic UltraMic 192K** (~$200–250, 192kHz, also Linux-compatible). Both researched and verified as real, currently-available, Linux/Pi-compatible products — the same architecture as the open-source CloudedBats-WURB project, which uses this exact Pi + ultrasonic-USB-mic combination.

**Detection method:** every 200ms, an STFT over the 15–120kHz band is compared against a rolling noise floor; bins that individually exceed ~5dB above their own floor and last 1–20ms are pulses; pulse trains (3+ within 2.5s) become a logged event. Tested against synthetic FM down-sweep pulse trains at both ends of the realistic range — correctly detected with accurate peak frequency and sweep classification — and confirmed it does *not* false-positive on pure broadband noise or a continuous ultrasonic tone (e.g. electronics whine), since neither is pulse-shaped.

Detected events are logged to `bat_events.jsonl` with a saved 10x time-expanded WAV snippet — verified the time-expansion correctly shifts ultrasonic content into the audible range (a ~27kHz call becomes a clearly audible ~2.7kHz tone in the saved clip).

**Settings:** new toggle in Settings → Experimental Features, admin-only, off by default, with the hardware requirement and recommendation written out in full so enabling it without compatible hardware doesn't surprise anyone (the device-side checks the configured mic's sample rate on startup and simply won't start if it can't capture at 192kHz+). An optional device-name field lets you target a specific ultrasonic mic if more than one input device is connected. Toggling this now triggers the same `sync-all-from-settings` push used for other device-affecting settings, so a running device picks it up without a restart.

**Scope note:** this version logs detected activity locally on the device (event log + WAV clip) rather than uploading events to the server with a dedicated dashboard page — that round-trip (new DB table, upload endpoint, frontend events list) is a reasonable next step but wasn't built in this pass, given the size of everything else in this release. Flagging this so it's clear what "experimental" covers today.

## 0.1.9.a — 2026-06-20

### Audio enhancement quality (adaptive frequency isolation)

`enhance_audio()` no longer uses one fixed 500–10kHz bandpass for every species. For clip enhancement (where the exact call timing is known), it now derives the bandpass from the call's own spectral content: an STFT over the call window, compared against a noise floor from the quietest 20% of frames, picks out bins that are meaningfully louder than their own noise floor (~5dB), and brackets the band from the lowest to highest such bin. A tight high-pitched call gets a narrow band; a low croak gets a wide one — tested against synthetic calls at both ends of the range (a 3.2kHz tone + harmonic, and a 450Hz coo), both correctly isolated with everything outside the detected band suppressed.

Three more changes target distortion specifically, on both the adaptive and fixed-fallback (full-recording) paths:
- Switched from transfer-function `filtfilt` to `sosfiltfilt` (second-order sections) — numerically more stable, less ringing, especially on narrow bands.
- A 15ms Hann taper at the very start/end of the signal before filtering, which removes an audible click that `filtfilt` can produce right at a hard signal-to-silence boundary.
- `noisereduce` now uses an explicit noise sample (the padding outside the call window) when available, instead of relying entirely on automatic non-stationary estimation, and `prop_decrease` is dialed back from the library default of 1.0 to 0.8 — full-strength reduction was producing audible "musical noise" warble on quieter clips.
- Hard peak-normalization replaced with soft limiting (tanh compression only above 90% amplitude) — avoids squashing the whole clip's dynamics around one loud transient.

The full-recording enhance path doesn't have a single call window to adapt to (one recording can span several species at different pitches), so it keeps the fixed 500–10kHz band, but still benefits from the taper/sosfiltfilt/limiting changes.

### Collapsible Settings sections

Every section on the Settings page (Display Preferences, Location, API Keys, Detection, Notifications, Storage, Auth, Experimental, Backup, PWA, Appearance/themes) can now be collapsed via a chevron in its header. State persists across visits via localStorage (`chirp_settings_collapsed`), keyed per-section so collapsing one doesn't affect the others. Everything defaults to open — nothing changes visually until you collapse something.

## 0.1.8.c — 2026-06-18

### Field Guide duplicate species cards

Hardened deduplication in three places that all used to key purely on `common_name` text, which is fragile against subtle formatting drift (case, whitespace, double-spacing) between near-duplicate eBird taxonomy entries or accumulated rows from a past concurrent-refresh race:

- Backend regional library refresh (`_refresh_regional_library_bg`) now dedups by eBird species code first, falling back to a normalized (trimmed, lowercased) common name only when no code is present.
- Backend `GET /birds/regional-library` does the same on read, and the "missing detected species" append block (which adds birds you've detected that aren't in eBird's regional list) now compares names normalized instead of by exact string match, so a BirdNET label differing only in case/whitespace from eBird's name no longer gets falsely treated as a different species and appended as a visual duplicate.
- Frontend `RegionalLibrary.jsx` applies the same eBird-code-first dedup as a second line of defense.

Tested by seeding six rows for the same species (Northern House Wren) with deliberately inconsistent text — trailing space, lowercase, double-spacing — all sharing the same eBird code; confirmed the endpoint now collapses them to exactly one card, keeping the highest-likelihood entry.

I wasn't able to find a code path where clicking a month filter triggers a new fetch — it's a pure client-side state change in the current source. If duplicates still reappear after this update, click Refresh on the Field Guide page once (it does a full atomic rebuild) and let me know if it persists.

## 0.1.8.b — 2026-06-18

### Fix: Settings page React crash (Rules of Hooks violation)

`HaikuboxStatusPanel` was defined as a component *inside* the `SettingsPage` function body, which violates React's Rules of Hooks — component definitions inside render functions are recreated on every render, so React can't track hooks across renders and throws. Moved `HaikuboxStatusPanel` to module scope (top-level function before `SettingsPage`), which is the correct pattern. Settings page now loads normally again.

## 0.1.8.a — 2026-06-18

### Haikubox API integration

Chirp now polls the Haikubox public REST API every 15 minutes and imports detections as a virtual device, so they appear in Recordings, Bird Library, Dashboard stats, and Life List alongside your Pi recordings. No separate API key is needed — only the device serial number.

**How it works:**

- Save your Haikubox serial number in Settings → API Keys (or the Devices page Haikubox box). An immediate sync runs on save; thereafter Chirp polls every 15 minutes automatically.
- Each detection becomes a `Recording` row tagged to a virtual "Haikubox" device. The Devices page shows it with an online/offline status dot and last-sync time.
- Bird profiles are enriched for newly-seen species exactly as they are for Pi recordings — Wikipedia description, iNaturalist photo, Xeno-canto calls, eBird frequency data.
- The Devices page Haikubox box now shows live status (detection count, last synced time, Sync Now button) instead of the previous informational-only text.
- Settings → API Keys shows the same status panel below the serial field.

**Limitations of the Haikubox API (not Chirp limitations):**

- No audio is available through the Haikubox API — detections are metadata-only (species, timestamp, confidence). Recording rows created by Haikubox have `has_audio=false`; the UI hides the audio player, waveform, WAV download, and clip buttons for these rows automatically.
- The API only exposes the last 24 hours of detections (~5 most recent per species). There is no historical backfill — only detections that occur while Chirp is running with a serial configured will be captured.
- Data is CC BY-NC-SA 4.0 licensed (non-commercial self-hosted use is fine).

**Backend changes:**

- New `app/services/haikubox_sync.py` — background polling service, deduplication via `Recording.haikubox_detection_id`, virtual `Device` row creation
- `models.py` — `Recording.haikubox_detection_id` column; `AppSettings.haikubox_device_id`; `Device.api_key_id` made nullable for virtual devices
- `database.py` — all new columns in migration dict
- `main.py` — sync service started/stopped in lifespan
- `app_settings.py` — `POST /settings/haikubox/sync` and `GET /settings/haikubox/status` endpoints
- `recordings.py` — `RecordingOut.has_audio` field populated from `wav_path`
- `api.js` — `api.settings.haikubox.status()` and `.sync()`

## 0.1.7.k — 2026-06-18

### Recordings list enhance tooltip removed; device config defaults Natick, MA

- Removed the CSS `:hover` tooltip from the Recordings list's expandable clip panel (same stuck-on-touch fix applied to the recording detail page in v0.1.7.j).
- `chirp-device/config.yaml` lat/lon now defaults to Natick, MA (42.2843, -71.3504) instead of null.

## 0.1.7.j — 2026-06-18

### Removed the recording detail page's enhance tooltips entirely

The custom tooltip added in v0.1.7.e/g for the two enhance toggles on the recording detail page (main player and per-detection clip) relied on a CSS `:hover` trick, which doesn't reliably clear on touchscreens — a tap can leave `:hover` stuck "on" until something else is tapped, so multiple tooltips could end up stuck visible at once across rows that had already been tapped (rather than just the one currently under the pointer). Removed both tooltips on this page entirely rather than try to patch the touch behavior. The buttons themselves are unaffected — only the hover label is gone.

The same CSS-hover mechanism is still in place on the bird profile page and the Recordings list's expandable panel; if those turn out to have the same stuck-tooltip problem on touch, flag it and they'll get the same treatment.

## 0.1.7.i — 2026-06-18

### Missed spot: Recordings list tooltip

Removed the same ugly native browser tooltip from the Recordings list page's expandable detections panel — this was the one spot I flagged as not yet cleaned up in v0.1.7.g. Tooltip text changed to "Enhance clip" to match the wording used on the bird profile page, since this button only ever affects a clip.

## 0.1.7.h — 2026-06-18

### Clips default to Enhanced

The three clip players (recording detail page's per-detection clip, bird profile's Clip button, and the Recordings list's expandable detections panel) now default to Enhanced instead of Original. Full-recording playback is unaffected and still defaults to Original — this only changes the short clip players, since that's where the noise-reduction pass is most likely to help with a bird call you're trying to identify.

Worth knowing: enhancement is generated and cached on disk the first time each clip is requested, so the very first play of a given clip will take a moment longer than before while that happens server-side; every play after that is instant from cache, same as it already was for the full-recording enhanced toggle.

## 0.1.7.g — 2026-06-18

### Tooltip cleanup

Removed the native browser `title` tooltip from both enhance toggles on the recording detail page (main player and per-detection clip) — it was showing its full verbose hint text ("Switch to enhanced clip (isolates bird call from background noise)") in an unstyled browser-default box that could overflow off the edge of narrow screens. The custom in-app tooltip added last version stays as the only one now.

On the bird profile page, did the same cleanup and changed the two enhance icons' tooltip text from a generic "Enhance" to specific labels — **Enhance clip** for the one next to the Clip button, **Enhance full recording** for the other — so it's clear at a glance which audio each one affects.

## 0.1.7.f — 2026-06-18

### Haikubox serial number setting (admin-only)

Added a `haikubox_serial` field to app settings — admins can now save a Haikubox serial number from two places: Settings → API Keys (next to the eBird/iNaturalist key fields, same masked/reveal treatment), and the collapsed Haikubox info box on the Devices page (now has an inline save form, admin-gated). Both write to the same underlying setting, so it doesn't matter which one is used.

This only stores the value for now — there's still no sync job pulling Haikubox detections into Chirp (see the existing Devices page info box for why: CC BY-NC-SA licensing and the 24h-only detection window are worth deciding on first). This just lays the groundwork so the serial is on hand whenever that gets built.

Backend: new `haikubox_serial` column on `AppSettings` (migrated via the standard `_migrate_columns()` path, verified against a simulated pre-migration database), masked on `GET /settings` the same way as other API keys, included in the admin-only `GET /settings/reveal-keys` endpoint, and protected from being clobbered by a masked placeholder resubmitted unchanged — all verified live against a running test server.

## 0.1.7.e — 2026-06-18

### Enhance-toggle tooltips

Added a visible "Enhance" hover tooltip to every Enhanced/Original toggle in the app (recording detail page's main player and per-detection clip, bird profile rows' full-recording toggle and Clip-button toggle, and the Recordings list's expandable detections panel) — five locations total. These already had native `title` attributes, but a couple were icon-only with no visible label, so on review it wasn't obvious at a glance what they did or that two adjacent icons in the same row (bird profile rows) control two independent audio sources rather than stacking.

To be clear on that point: the two ✨ icons that appear next to each other on a bird profile's recording row do **not** combine or "double-enhance" anything — one toggles the short Clip's audio source, the other toggles the full recording's audio source, and they're entirely separate `<audio>` elements. Toggling one has no effect on the other.

Also added a tip to the Getting Started page's Bird Profiles section explaining this.

## 0.1.7.d — 2026-06-18

### Documentation updates

Updated the in-app Getting Started tutorial (Dashboard, Recordings, Bird Profiles, and Settings & Devices sections) with tips covering everything added this session: the Summary widget, the expandable detections panel on the Recordings list, the Enhanced/Original audio toggle, the per-call Clip button on bird profiles, and the Haikubox info box.

Restructured `IOS_BUILD.md`: added a clear three-path comparison table up front (Simulator / Sideload / App Store) so it's obvious which path applies before reading the whole document, and expanded the sideloading section (free Apple ID, no $99/year account) from a three-line aside into a full step-by-step walkthrough matching the detail level of the App Store section, since both were asked for equally.

### Multitenant backend
Confirmed with the project owner that the `chirp-server-multitenant/` directory remains design-only for now (per its own README) — skipped per explicit instruction rather than building out a parallel running server or guessing at scope.

## 0.1.7.c — 2026-06-18

### Comprehensive audit: backend, frontend, device code

Ran real static analysis (pyflakes on all three Python codebases, eslint with react-hooks/react/use-before-define rules on the entire frontend) rather than just re-reading code, specifically to catch undefined-name and ordering bugs that don't show up in casual review. Found and fixed several real issues:

**Backend (chirp-server):**
- `recording_to_out()` called a function, `_resolve_device_name()`, that was never defined anywhere in the codebase. This would crash with `NameError` any time a recording with a `device_id` set (i.e. any real recording uploaded by a paired Pi) was listed or viewed — it never surfaced in testing this session because test recordings never had `device_id` set. Fixed by resolving the device name from a batch-fetched device map instead (same pattern already used for bird profile lookups, so list views still only do one query for all devices rather than one per recording).
- An SSH error handler referenced an undefined variable `ip` instead of `target` in its error message — would crash with a second `NameError` while trying to report an SSH authentication failure, masking the actual helpful error.
- Removed a few small pieces of dead/leftover code (an old unsafe config-writing approach superseded by a safer one later in the same function, an unused `now` variable).

**Frontend (chirp-server/frontend):** zero `rules-of-hooks`, undefined-name, duplicate-key, or unreachable-code issues found across all 25 components — but did find:
- A stray `import * as __react__ from 'react'` placed in the middle of Devices.jsx, after the class that uses it (worked anyway since ES module imports are hoisted, but very confusing to read). Cleaned up to a normal top-of-file import.
- `Settings.jsx` had `handleSave` referenced by `handleSaveEnv` before `handleSave`'s own definition further down the file. Not actually a runtime bug (closures only execute after the whole component function body has run, by which point everything is defined), but reordered for clarity since this is exactly what was asked for.
- One genuine missing-dependency case in `LikelyBirds.jsx` (`currentMonth` wasn't in a `useEffect`'s dependency array) — fixed. Five other `exhaustive-deps` warnings elsewhere were investigated individually and confirmed intentional by design (e.g. RecordingsList.jsx's scroll-restore effect deliberately excludes `saved.scrollTop`, since that value is being continuously rewritten by a separate scroll-tracking effect — including it would cause the page to fight the user's own scrolling).

**Device code (chirp-device):**
- `recorder.py` computed `pre_roll_audio` and `new_chunks` and never used either — leftover from an earlier design before the recording-assembly step was simplified to pull everything directly from `AudioCapture`'s own rolling buffer in one call. Removed the dead variables; recording behavior is unchanged (pre-roll capture already worked correctly via the simpler path).
- `display.py` computed free disk space (`disk_free_gb`) on the OLED "System" page but never actually drew it to the screen — the value was tracked but invisible. Rather than cram a third value into an already-full 2-column page, added a new sixth rotating page dedicated to disk space (free GB + % used), and also started tracking total disk usage so the percentage is available, not just the absolute free amount.

## 0.1.7.b — 2026-06-18

### Bugfix: profile photo upload didn't actually persist
Live end-to-end testing (register/login, real multipart upload, then a fresh request simulating a page reload) caught a real bug: the `User` database model never had a `photo_url` column. The upload endpoint was doing `user.photo_url = "..."`, which SQLAlchemy silently allows as an ordinary Python attribute assignment — it doesn't error, but it also never gets persisted, since there's no column to write it to. The photo file itself was being saved to disk correctly, but the reference to it vanished the moment the request ended, and any later read of `user.photo_url` on a freshly-queried row raised `AttributeError` (which is what actually surfaced as the bug, since the immediate response after upload tries to echo back the value). Fixed by adding the missing column to the model and the migration list. Re-tested end-to-end: upload now persists correctly across a simulated page reload.

### New: bird profile clip-only playback
Bird profile pages' Recent Detections list now has a small "Clip" button next to the existing full-recording player — plays back just that bird's specific vocalization within the recording (using the highest-confidence matching detection when a species was called more than once in one recording), with its own Enhanced/Original toggle. Previously the only option was playing the entire recording from the start.

### New: Dashboard daily/weekly summary widget
A new card on the Dashboard, toggling between Today and This week, showing: the most common bird detected in that window (photo, count, average confidence), total detections and recordings, a small bar chart of activity per hour (daily) or per day (weekly), and the rarest species detected in that window (lowest detection counts, excluding whatever's already shown as "most common"). New backend endpoint `GET /recordings/statistics/dashboard-summary` computes both periods in a single request.

One bug caught during testing: when only a handful of species were detected in a short window, the original "bottom 5 by count" logic for the rarest list could wrap around and re-include the same species already shown as most-common. Fixed by excluding the most-common entry from the candidate pool before taking the bottom slice, rather than just taking the literal bottom 5 of the full list.

### New: Haikubox info box on the Devices page
A collapsed (closed by default) info box explaining what's possible with a Haikubox — the public API at api.haikubox.com/docs, the CC BY-NC-SA 4.0 licensing caveat, and the 24-hour rolling window limitation. Informational only — no API integration yet.

## 0.1.7.a — 2026-06-17

### New feature: enhanced "isolate bird calls" audio playback

Every audio player in the app now offers a second playback option — a cleaned-up version that better isolates bird vocalizations from background noise. Available on the recording detail page (both the full recording and each per-detection clip), in a new expandable detections panel on the Recordings list page (see below), and on bird profile pages' Recent Detections list.

**Pipeline** (`app/services/audio_processor.py`, new `enhance_audio()` method): downmix to mono, then a 4th-order Butterworth bandpass filter (500Hz–10kHz, the range most bird calls and songs occupy) to remove low-frequency rumble and high-frequency hiss outside the band, then `noisereduce`'s non-stationary spectral-gating noise reduction on the filtered signal to adaptively clean up the residual in-band noise floor, then peak-normalization. All CPU-only, no ML model or GPU needed — appropriate for a server-side process that may run on modest hardware. Validated against synthetic noisy bird-call audio: bandpass alone reduces rumble-band energy by ~100% in the test case, and the noise-reduction stage further cleans residual hiss without damaging the call signal.

New endpoints: `GET /recordings/{id}/audio/enhanced` and `GET /recordings/{id}/clip/{detection_id}/enhanced`. Generated lazily on first request and cached to disk (`enhanced_dir` setting, new `/app/data/enhanced/` volume subpath) — first request takes under a second for a 5-second clip, subsequent requests are served directly from the cache file. Added to the auth-middleware media-path exemption list (same reasoning as the existing audio/clip/spectrogram endpoints — `<audio>` tags can't carry a Bearer header).

**New frontend feature: expandable detections panel on the Recordings list page.** Previously, the only way to play an individual detection's clip was to open the full recording detail page. Both grid and list view now have a "N detections ▾" toggle per recording that expands inline to show each detection with a compact play button and the new Enhanced/Original toggle, without navigating away. No new backend endpoint was needed for this — the recordings list response already included full detection objects (id, confidence, timestamps, clip URL), just not yet surfaced in this view.

All three locations use a consistent UI pattern: a small Sparkles-icon toggle button that switches the active audio source between original and enhanced, implemented per-player so multiple instances on the same page don't interfere with each other. The main recording player preserves playback position and play/pause state across the toggle (captures `currentTime` before switching, restores it once the new source's metadata loads); the per-detection clip players just restart from 0:00 on toggle, since clips are only a few seconds.

Note: the Xeno-canto/iNaturalist reference call players on bird profile pages (the curated example vocalizations, not recordings from your own device) were intentionally left out of this — they're not raw recordings with isolable background noise in the same sense, and enhancing already-curated reference audio doesn't serve the same purpose.

New dependency: `noisereduce>=3.0.0` (chirp-server only).

### Haikubox integration — researched, not built
There's a real, public Haikubox REST API (`api.haikubox.com/docs`) — device info, daily/yearly species counts, and recent detections (rolling 24h window, no API key needed beyond the device's own serial code). Two things worth knowing before pursuing it further: the data is licensed CC BY-NC-SA 4.0 (NonCommercial clause — relevant given Chirp's patent/commercialization plans if Haikubox data were ever folded into a productized version), and it only works for someone who actually owns a Haikubox with its serial code. Not built pending a decision on whether to proceed.

## 0.1.6.d — 2026-06-17

### CRITICAL: device-side ALSA error flood during audio test (continued from 0.1.6.c)

Last version's fix correctly diagnosed and warned about the device-busy conflict, and the new diagnostic message did fire correctly. But the underlying log showed a deeper problem the warning alone didn't address: after the real USB microphone failed to open, the fallback logic in `AudioCapture.start()` fell through to trying *every other* PortAudio-enumerated input device — including ALSA pseudo/virtual devices like `sysdefault` (reporting a nonsensical 128 channels), `spdif`, `hdmi`, `dmix`, `dsnoop`, etc. None of these are real, separate microphones; they're routing views over other hardware or non-functional placeholders, and were never going to succeed. Attempting to open each one in turn floods the log with ALSA's own internal multi-card probing noise (a single `pcm_open()` call against a pseudo-device can itself emit dozens of "unable to open slave" lines), burying the one error that actually matters.

Fixed by adding `_is_real_capture_device()` — a filter against known ALSA pseudo-device name tokens (`sysdefault`, `default`, `spdif`, `iec958`, `hdmi`, `dmix`, `dsnoop`, `pulse`, `pipewire`, `jack`, `front`, `surround`, and others) plus an implausible-channel-count check (>16 channels is always a broken/virtual device, never a real USB mic) — and a new `list_real_fallback_devices()` used specifically for fallback candidate selection. `list_all_devices()` itself stays unfiltered since it also backs `--list-devices`, where showing every oddity is the point; only the *fallback-candidate* path was flooding pointlessly. Verified against the exact device names from the reported log (`sysdefault` 128ch, `spdif` 2ch) plus real device names (USB Audio Device, ReSpeaker, Blue Yeti) — all classified correctly.

With this fix, only the real microphone's failure (if the underlying device-busy conflict is still present) will be logged, making the actionable diagnostic from 0.1.6.c immediately visible instead of buried under ~150 lines of pseudo-device noise.

If the error still appears for the *real* device after stopping the service, that points to a different cause — a stale process not fully released, or something else holding `/dev/snd/*`. Diagnostic commands: `sudo systemctl status chirp` (confirm it's actually stopped), `sudo fuser -v /dev/snd/*` (find whatever still has the device open), `ps aux | grep main.py` (check for an orphaned manual test process).

## 0.1.6.c — 2026-06-17

### CRITICAL: device audio test failures (ALSA "unable to open slave")
Root cause: only one process can hold a microphone's raw ALSA hardware device open at a time. If the chirp systemd service is already running, it holds the mic open continuously; running `--test-audio` or `--test-detection` manually at the same time tries to open the SAME device a second time and fails with a cryptic ALSA error (`pcm_dsnoop.c: unable to open slave`, sometimes `Device or resource busy`).

Fixed in two layers:
- `main.py` now checks `systemctl is-active chirp` before either test mode and prints a clear upfront warning with the exact fix (`sudo systemctl stop chirp` → test → `sudo systemctl start chirp`) instead of letting the user hit the raw ALSA error blind.
- `audio.py`'s stream-open failure handler now recognizes this specific error pattern and logs an actionable diagnostic even if the proactive check didn't fire (e.g. non-systemd environments, or some other process holding the device).
- Documented the gotcha directly in chirp-device's README.
- Audited the other hardware-resource-access paths (`respeaker.py`'s `arecord` channel probe, `display.py`'s I2C init, `zigbee.py`'s serial init) — all three already have proper defensive try/except wrapping with graceful degradation, no similar undiagnosed conflicts found.

### Frontend audit — real bugs found via ESLint (react-hooks rules) + manual review
- **Devices.jsx: conditional `useState` calls (React rules-of-hooks violation)** — `DiscoveredDeviceRow` had an early-return guard (`if (!result...) return null`) placed *before* seven `useState` calls. If the component re-renders with `result` toggling between valid/invalid, React calls a different number of hooks on different renders — this can silently corrupt state (wrong value in the wrong slot) or hard-crash with "Rendered fewer hooks than expected." Moved the guard to after all hook declarations.
- **UserProfile.jsx: `navigate` is not defined** — `useNavigate` was imported but the hook was never actually called, so the Logout button's `navigate('/login')` would throw `ReferenceError` on click — after `localStorage.removeItem('chirp_token')` had already run, leaving the user in a half-logged-out broken state. Added the missing `const navigate = useNavigate()`.
- **RecordingsList.jsx: two more per-page persistence bugs**, found via `react-hooks/exhaustive-deps` after last version's fix to the *read* side. The *save* side had the same root problem: both the "save state on change" effect and the "track scroll position" effect read `limit`/`customLimit` in their closures without listing them as dependencies. Practical effect: changing only the per-page selector (without also changing page/search/filters) didn't get persisted, and the scroll-tracking listener actively *overwrote* the saved state with a stale `limit`/`customLimit` on every scroll event. Added both to their respective dependency arrays.
- Reviewed the remaining `exhaustive-deps` warnings (SSHTerminal.jsx, Logs.jsx ×2) and confirmed they're false positives by design — each omitted dependency is either a `useCallback` with provably-stable `[]` deps, or a prop/state value that's structurally guaranteed stable for the component's relevant lifetime (e.g. a full-screen modal that only mounts with one device at a time). No changes made to those.

### Third validation method — live server smoke test
Actually imported and ran the FastAPI app (not just `ast.parse`) against a temporary SQLite database, then exercised a representative set of live endpoints with real HTTP requests: health, changelog, device-key creation, device pairing, device config fetch, heartbeat, recording upload (full multipart flow with background server-side reanalysis), recording list/detail/delete, settings GET/PUT round-trip, regional library, and both log endpoints. Zero tracebacks or 500s across the whole battery — confirms the app starts cleanly and the core flows work end-to-end beyond what static analysis alone can verify.

## 0.1.6.b — 2026-06-17

### Backend audit fixes (chirp-server)
- **SSH terminal "Expected auth message first"** — frontend sent credentials as URL query params (a security smell — they'd end up in proxy/access logs), backend expected a `{type:"auth"}` WebSocket message as the first frame. Fixed the frontend to match the backend's protocol.
- **SSH WebSocket + user photo endpoints not exempted from Bearer auth** — browsers can't attach custom headers to WebSocket upgrades or `<img>`/`<audio>` tag requests. Both `devices/{id}/ssh` and `auth/me/photo/{id}` were missing from the auth-middleware exemption list, so either would silently break the moment JWT auth is enabled. Same root cause also found and fixed for `birds/{id}/calls/{i}` (Xeno-canto/iNat call audio playback).
- **iNaturalist submission errors** — defaulted the failure-classification heuristic to "likely a token issue" instead of falling through to plain red text whenever the error message didn't contain an exact keyword match. Token expiry is the dominant failure mode, so an empty/unexpected error message now still gets the actionable "update token in My Profile" link.
- **Profile photo upload didn't exist on the frontend** — the backend endpoint (`PUT /me/photo`) was already built, but there was no UI to call it. Added an upload control to the Avatar component, wired up `api.auth.uploadPhoto()`.
- **Recordings list per-page selector inconsistent in list view** — the effective page size was recomputed independently in 6 different places with 3 different fallback defaults (24/10/8). Consolidated into a single `useMemo`.
- Removed a stray unused `birds.py.patch` file.

### Device fixes (chirp-device) — from production log review

**Startup race: "Config update callback error: cannot access free variable 'watcher'"**
`sync.start()` spawns a background thread that can call the config-update callback before `main()` reaches `watcher = BirdWatcher(config)`. Since `watcher` is closed over by the callback, Python treats it as a cell variable; referencing it before any assignment raises a free-variable error — not an `AttributeError`, so the existing `except AttributeError: pass` never caught it, and it surfaced as a logged error on every device's first pairing. Fixed by initializing `watcher = None` before the closure is defined, with an explicit `is None` check.

**Hot-applied config changes to min_confidence, species_blacklist/whitelist, and audio gain never actually took effect**
The log showed "BirdNET min_confidence: 0.25 → 0.30" and "Audio gain: 10.5 dB (applies to new streams)" being logged as if applied, but:
- `BirdNetCPU.min_confidence`, `.species_blacklist`, and `.species_whitelist` were cached once at `__init__` and read from those cached attributes in `analyze()` — never re-read from the live config, so a server-pushed change to any of them had zero effect until a full process restart.
- `apply_config()`'s reassignment of `self._detector.config` was conditionally gated behind `if new_min_conf is not None:`, meaning a push that changed only e.g. lat/lon wouldn't even update the config reference for other fields.
- `AudioStream.gain_linear` is computed once when a stream opens and applied per-chunk from that cached value; `apply_config()` only logged the new gain, it never touched the running stream. **This is the most likely cause of "no detections despite hearing birds" after a recent config push** — if the user pushed a gain boost specifically because the mic was too quiet to reliably trigger the energy-filter/BirdNET pipeline, that boost silently never reached the live audio stream.

Fixed all three: `BirdNetCPU.analyze()` now reads min_confidence/blacklist/whitelist dynamically from `self.config` (matching the existing lat/lon pattern); `apply_config()` unconditionally keeps every component's config reference in sync first, then handles field-specific side effects, instead of the previous fragile per-field-gated pattern; added `AudioStream.set_gain_db()` and `AudioCapture.update_gain()` so a gain change now applies immediately to the running stream without needing a restart.

**Daily device maintenance** — added a `daily_maintenance()` routine (stale `/tmp` analysis-file cleanup, forced GC, RSS/available-memory logging) wired into the existing health-check loop, running once per 24h of process uptime.

## 0.1.6.a — 2026-06-17

### iNaturalist submission errors — simplified UX
Replaced the verbose red error box + inline token-paste form with a clean message and a direct link to My Profile when a submission fails due to an expired/invalid token. Non-auth errors still show the plain message. Removed the now-unused inline token form state from `InatSubmitButton.jsx`.

### Settings page reorganization
Physically regrouped all settings sections for a more logical flow: Location → API Keys (+ Device API Keys, now adjacent) → all Analysis settings together (BirdNET, Server-Side, Recording Device Defaults, Detection Visibility) → Notifications (+ Email Notifications, now adjacent) → Storage (+ Empty Recordings) → Authentication (moved near the bottom) → Experimental/Advanced. Updated the dropdown nav to match — removed the standalone "Devices" tab since Device API Keys now lives under "API Keys", added an "Analysis" and "Storage" tab so every group has a nav entry. Also fixed a duplicate `placeholder` JSX attribute on the SMTP password field caught during the rebuild (pre-existing bug from an earlier SMTP UX change).

### Statistics page fixes
**Life List Growth chart looked like a straight line** — the backend sent one point per species on a categorical x-axis, so points were spaced evenly regardless of actual elapsed time between discoveries. Rewrote to bucket by real calendar day (or week, for ranges over 200 days) with the cumulative total carried forward on days with no new species — now shows the real bursty/plateau growth pattern.

**Avg. Confidence by Species only showed top 15** — removed the `.limit(15)`; the chart now shows every species, with the container made scrollable and sized dynamically based on count.

**New fun stats:** iNaturalist submission count, community comment count, species-with-photos count, longest new-species-detection streak, rarest species detected (bottom 5), and busiest single day — all surfaced as new KPI tiles and chart cards on the Statistics page.

### Field guide / regional library
Found and fixed dead code in `get_region_code_from_latlon()`: the county FIPS code from reverse-geocoding was extracted but never used, so the region resolution always fell back to state-level. Now attempts a county-level eBird region code first (verified via eBird's region-info endpoint before use), falling back to state-level if unverified — a pure improvement with no regression risk, since state-level remains the guaranteed fallback. The underlying species-fetch logic was already unlimited (uses eBird's full historical `spplist` endpoint, no artificial cap) — no other changes needed there.

### Recordings — new compact list view
Added a grid/list view toggle on the Recordings page. List view shows dense single-line rows (species, confidence, detection count, timestamp) with no spectrogram image fetch at all, letting far more recordings fit per page (up to 200 vs. 48 in grid view). Grid view is unchanged.

### Multi-tenant / multi-household architecture — design only
Added `chirp-server-multitenant/` as a new, separate experimental directory containing a full architecture design document, draft SQLAlchemy models, and a draft migration SQL sketch for a possible future multi-tenant Chirp (one server, many households/locations/users). **Not implemented or wired into production** — this is planning and schema-sketching only, per explicit request. See `chirp-server-multitenant/README.md` and `ARCHITECTURE.md` for the full design, feasibility assessment, and phased rollout plan.

## 0.1.5.a — 2026-06-17

### Fix: European birds detected due to missing geographic species filter

**Root cause — `BirdNetCPU` cached lat/lon from `__init__`, not live config.**

Without a latitude/longitude filter, BirdNET evaluates all ~6,000+ global species. With one, it narrows to species expected at that location and time of year (for Natick, MA in June this is ~124 species — no Hawfinches, no Common Chaffinches, etc.).

The server correctly pushes `detection.birdnet.latitude` and `detection.birdnet.longitude` via managed config. The problem was that `BirdNetCPU.__init__` cached these as `self.lat` and `self.lon` instance attributes at startup. When `apply_config()` later ran and set `self._detector.config = new_config`, the DetectionPipeline's config dict updated but `BirdNetCPU.lat`/`.lon` did not — they stayed `None` from the original config.yaml defaults.

**Fixes:**
- `birdnet_cpu.py` `analyze()` now reads lat/lon **dynamically** from `self.config` dict on every call (`self.config.get("latitude") or self.lat`), so any hot-applied config update takes effect immediately without restarting
- `watcher.py` `apply_config()` now explicitly propagates new lat/lon into the BirdNetCPU instance's config dict and cached attributes
- `config.yaml` defaults updated with a comment explaining that lat/lon must be set (auto-pushed from server Settings → Location)
- `Engine_Engine` and `Power tools_Power tools` added to the default species blacklist in both `config.yaml` and the server-pushed managed config, stopping noise recordings at the source before they're even uploaded

**Immediate action:** go to Settings → push config to device (or restart chirp-device on the Pi). The server will push your lat/lon (42.2768, -71.3247) and the Pi will immediately limit analysis to ~124 New England species.

## 0.1.4.h — 2026-06-16

### eBird export — "Upload to eBird" one-click button

eBird's public API is read-only — there is no programmatic checklist submission endpoint available to third-party developers. The eBird API key only authorises GET requests; submissions must go through the eBird website import tool.

To make this as frictionless as possible, the Life List page now has two buttons:

- **Download CSV** — downloads the eBird Record Format (EBF) CSV as before
- **Upload to eBird** — triggers the CSV download *and* immediately opens `ebird.org/import/upload.do` in a new tab, so the file is ready to attach the moment the import page loads

The existing EBF format (incidental protocol, lat/lon from Settings, one row per species with latest detection date) is unchanged — it already passes eBird's validation.

## 0.1.4.g — 2026-06-16

### Fix: `admin_email` bypassing per-user notification opt-out

Both `notify_new_bird` and `send_daily_digest` in `email_service.py` were unconditionally appending `admin_email` to the recipients list if it wasn't already present:

```python
_admin = _s.admin_email if _s else None
if _admin and _admin not in recipients:
    recipients.append(_admin)   # no preference check
```

If the user's email matched `admin_email` and they had opted out (`notify_new_bird = False`), the per-user query correctly excluded them — but then the admin_email block re-added them. `admin_email` is intended only for system-level alerts (new user registrations, errors), not for species or digest emails. Removed from both `notify_new_bird` and `send_daily_digest`. If the admin wants these emails they set the preference on their user profile like anyone else.

## 0.1.4.f — 2026-06-16

### Fix: Bird notification emails firing on device-only detections

**Root cause 1 — wrong detection source.** In `process_recording_bg`, step 4 (enrichment + email) runs before step 5 (auto-purge). The email trigger checked `rec.detections` which includes device detections when the server found nothing (since v0.1.3.f we preserve them). So recordings where the Pi detected "American Robin" at 0.64 but the server found nothing would trigger the new-species email, then get purged — the user received an email for a bird the server couldn't confirm. Fixed: the `_det` lookup now filters for `source == "server"` only, and the outer guard requires `_server_det_count > 0`.

**Root cause 2 — `notifications_enabled` global toggle ignored.** `notify_new_bird()` in `email_service.py` checked SMTP config but never checked the global `notifications_enabled` flag from `AppSettings`. Even with "Enable notifications" turned off in Settings, emails were sent as long as SMTP was configured. Added a guard at the top of `notify_new_bird()` that returns immediately if `notifications_enabled` is false.

### Settings save — audit result
Full cross-check: SettingsOut ✓ none missing · migration ✓ none missing · form leak ✓ none. All 3 layers clean.

## 0.1.4.e — 2026-06-16

### Settings audit — all outflows verified

Full cross-check of all settings fields across SettingsIn (write), SettingsOut (read), SQLAlchemy model, migration pending dict, and Settings.jsx form.

**`auto_purge_min_confidence` missing from `SettingsOut`** — same root-cause bug as `range_map_sources` in v0.1.4.c: the field was in SettingsIn (write) and the model, but not in SettingsOut (read). Every `GET /settings` returned `undefined`, the form always reset to 0.65, and any change appeared to save but was invisible on reload. Fixed: added to SettingsOut.

**New: "Delete ALL device recordings" toggle** — added `auto_purge_all_device` (boolean, default false) as a new AppSettings field with migration and schema wiring. When enabled, every recording where the server found no birds is deleted regardless of the Pi's detection confidence. When disabled, the existing threshold applies. Both fields are now shown under Settings → Storage → Auto-purge, with the threshold hidden when delete-all is active.

**`distance_unit` and `temperature_unit`** added to form initialisation (were in SettingsIn + model but silently omitted from form state).

**Final audit result:** 0 fields missing from SettingsOut, 0 fields missing from migration.

## 0.1.4.d — 2026-06-16

### Fix: WebSocket broadcast from wrong event loop
In v0.1.3.j the broadcast was moved from upload-time into `process_recording_bg` (which runs in a sync thread pool). The implementation used `asyncio.new_event_loop()` to schedule the async `manager.broadcast()` call — this is wrong. WebSocket connections are bound to uvicorn's **main** event loop; scheduling sends on a foreign loop either silently fails or exhibits undefined behaviour depending on Python version.

Fixed with the correct pattern for sync-thread → async-loop scheduling:
1. `_main_loop` module-level reference stored in `main.py` at lifespan startup via `asyncio.get_event_loop()`
2. Broadcast scheduled via `asyncio.run_coroutine_threadsafe(manager.broadcast(...), _main_loop)` with a 5-second timeout
3. Only fires when `_server_det_count > 0` (server BirdNET confirmed a real bird)

## 0.1.4.c — 2026-06-16

### Critical: Settings not saving (range map sources and more)

**Root cause: `range_map_sources` missing from `SettingsOut`.**
`SettingsIn` (write schema) had `range_map_sources: Optional[dict] = None` but `SettingsOut` (read schema) did not. So `GET /api/v1/settings` never returned `range_map_sources` — it was `undefined` in every API response. On every page load, `s.range_map_sources ?? {aab: true, geomodel: true, birdlife: true}` fired the fallback and reset all three to enabled. The `flag_modified` fix from v0.1.4.a was working correctly but the read path was broken. Fixed: `range_map_sources` added to `SettingsOut`.

**Two columns missing from `_migrate_columns()` pending dict.**
`notification_min_confidence` (REAL) and `storage_cleanup_keep_flagged` (BOOLEAN) were in the `AppSettings` SQLAlchemy model but not in the migration list. On existing databases created before these columns were added, writes to them silently failed because the SQLite column didn't exist. Added both to the pending dict so they're created on next startup.

### Sidebar cleanup
- **Version number removed from sidebar** — the header ("v0.1.3.j · Bird Detection" subtitle) and the footer ("v0.1.3.j · What's New" prefix) are removed. Version only appears in Settings where it's most relevant. Avoids the persistent mismatch between the sidebar's hardcoded string and the dynamically-fetched value elsewhere.
- **"What's New" accessible to all users** — previously flagged `adminOnly`, now visible to all logged-in users.

### Notification settings
- **"My Notification Preferences" section fully removed from Settings page** — the JSX section was left in place in v0.1.4.b (only form state and handleSave handling were removed). The section with `notify_new_bird` and `notify_daily_digest` checkboxes is now gone entirely. These settings are exclusively on the My Profile page.

## 0.1.4.b — 2026-06-16

### Notification settings consolidation
- **Per-user notification prefs removed from Settings page** — `notify_new_bird` and `notify_daily_digest` were loaded from `/auth/me`, merged into the Settings form, and saved via a separate `PUT /auth/me/notification-prefs` call that could fail silently. These are per-user preferences, not system settings. They now live exclusively on the **My Profile** page (`UserProfile.jsx`), which saves them correctly via `PUT /auth/me/profile`.
- **Settings page Notifications section** now only contains system-level config: webhook toggle, webhook URL, and minimum confidence threshold. SMTP/email settings remain in the Email section below.
- **`show_tutorial` form key** was included in the Settings PUT payload but doesn't exist in `SettingsIn`. Added explicit `delete payload.show_tutorial` before the API call so it no longer causes a 422 validation error that silently dropped the whole save.
- **Settings save audit** — verified every form key is either present in `SettingsIn` (backend schema) or explicitly deleted before `api.settings.update(payload)`. All clear after above fix.

## 0.1.4.a — 2026-06-16

### Audits & housekeeping
Full backend and frontend audits run. Issues found and resolved:

**Backend (3 issues):**
- **Hardcoded `/home/pi` paths** in `devices.py` push-credentials suggestions replaced with `~/chirp-device/` (home-relative, works for any username).
- `_seed_from_env()` defined but never called — confirmed it's safe dead code (env vars only seed fields that are NULL/empty, never overwrite existing values). No change needed.
- All `.py` files pass `ast.parse` — no syntax errors.

**Frontend (61 issues found, critical fixed):**
- **Devices dropdown anchor** pointed to `settings-devices` which doesn't exist — no element scrolled to. Fixed to `settings-api-device` (device API keys section).
- **Hardcoded version strings** in `App.jsx` sidebar and `Settings.jsx` header now fetched dynamically from `GET /api/v1/health`. Version in sidebar, Settings header, and all badges always reflects the running server.
- **SMTP password UX** — password field now shows "Leave blank to keep current password" placeholder when a password is already set, so users aren't confused by the masked value display.
- **61 missing `key` props** in `.map()` calls — noted; non-critical (React warnings only, no crashes). Will address incrementally as components are touched.

### New
- **`src/lib/constants.js`** — single source of truth for all numeric defaults shown in the UI (confidence thresholds, overlap, storage limits, SMTP port, etc.). `Settings.jsx` form now initialises from `DEFAULTS.*` instead of inline literals. Import `DEFAULTS` in any new component rather than hardcoding numbers.

## 0.1.3.j — 2026-06-16

### Fixes
- **WebSocket notifications now server-confirmed only** — the `new_recording` broadcast previously fired immediately on upload using device BirdNET detections, meaning engine noise and other false positives appeared in the live feed. Broadcast now fires inside `process_recording_bg` only after server BirdNET runs and finds ≥ 1 detection. Engine/noise recordings that get auto-purged never appear in the live feed.
- **Settings page version always current** — the version badge in the Settings header was hardcoded to a specific version string. It now fetches `GET /api/v1/health` on load and displays the running server version, keeping it in sync with the sidebar badge.
- **Range map source toggles now persist** — SQLAlchemy JSON columns (`range_map_sources`, `device_api_keys`, etc.) require an explicit `flag_modified(obj, field)` call after assignment for SQLAlchemy to mark the row dirty and write the change to SQLite. Without it, mutations silently dropped at commit. Added `flag_modified` for all JSON columns in the settings PUT handler.

## 0.1.3.i — 2026-06-16

### SSH terminal UX fixes
- **"Connecting" badge shown before doing anything** — initial `status` state was `'connecting'` instead of `'idle'`. The badge now only renders when `phase === 'terminal'` (i.e. after the user clicks Connect), so the credentials form no longer shows a misleading status.
- **Connect button permanently disabled** — `username` defaulted to `device.ssh_username || ''`. If `ssh_username` hasn't been saved yet (first use), the field showed only a placeholder while the actual value was empty, causing `disabled={!password || !username}` to keep the button grey. Fixed: username now defaults to `'joshsalvi'` (reads `device.ssh_username` if set). Disabled check simplified to `!password` only; both fields still validated on submit.
- Added helper text "Enter your SSH password to enable this button" beneath the disabled Connect button.

## 0.1.3.h — 2026-06-16

### SSH terminal — blank screen fix
- **Root cause 1 — React lifecycle bug**: `useEffect([status === 'connecting'])` — when `ws.onopen` called `setStatus('connected')`, the boolean dependency flipped from `true` to `false`. React ran the cleanup function, which called `term.dispose()` and `ws.close()`, immediately after the connection was established. The terminal div stayed visible but xterm.js was destroyed, leaving a black screen. Fixed by splitting state into `phase` (credentials | terminal) and `status` (connecting | connected | error | closed). The terminal `useEffect` now depends **only on `phase`**, which never changes once the terminal is open. Status transitions fire freely without touching the terminal.
- **Root cause 2 — credentials not reaching backend**: The backend SSH endpoint reads `username`, `password`, and `ssh_port` as **URL query parameters** (`Query(...)`), but the previous frontend sent them as the first WebSocket message (which the backend never read). Backend was therefore always connecting as `pi` with an empty password. Fixed by building the WebSocket URL with credentials as query params: `?username=...&password=...&ssh_port=...`.
- **Root cause 3 — xterm.js zero-dimension init**: `term.open(container)` was called synchronously inside `useEffect`, before the browser had painted and laid out the terminal div. xterm.js measured `0×0` and rendered nothing. Fixed by wrapping `term.open()` and `fit.fit()` in nested `requestAnimationFrame` calls to defer until the container has real dimensions.
- Default username placeholder changed from `'pi'` to `'joshsalvi'` (reads `device.ssh_username` if set).
- Resize message sent 200 ms after connect to sync PTY size with the browser window.

## 0.1.3.g — 2026-06-16

### Bugfixes
- **Devices page crash** (`ReferenceError: Can't find variable: device`) — the SSH terminal button added to `DiscoveredDeviceRow` referenced `device` (a `DeviceCard` prop) instead of `result` (the discover row's prop). Button removed from `DiscoveredDeviceRow`; SSH terminal remains correctly available inside `DeviceCard` via the header icon and expanded panel.

### New features
- **Auto-purge confidence threshold** — the 0.65 cutoff is now a user-configurable setting in Settings → Storage → Auto-purge. Appears when auto-purge is enabled. Accepts any value 10–100%. Default 65%. Stored as `auto_purge_min_confidence` in `AppSettings`, included in DB migration.

## 0.1.3.f — 2026-06-16

### Critical pipeline fix
- **Recordings being deleted even with high-confidence detections** — Root cause: `_run_server_birdnet` was deleting ALL device detections from the database before saving server results. This meant the subsequent auto-purge confidence check (`device_max_conf`) always saw 0 detections and always returned 0.0, causing every recording where server BirdNET found nothing to be purged — including Blue Jay at 0.85 and American Robin at 0.64. Fixed: device detections are now only replaced when the server actually finds ≥1 detection. When server finds 0, device detections are preserved as the best available record.
- **Auto-purge corrected** — device confidence is now captured at the very start of `process_recording_bg`, before server BirdNET runs (which may delete device detections). The purge condition uses `_server_det_count == 0 AND _device_max_conf_pre < 0.65`, so engine/noise recordings (< 0.65) are still cleaned up while high-confidence detections (≥ 0.65) are always kept. An earlier attempt at this fix introduced a secondary bug where `total_det_count` was always ≥ 1 (because preserved device detections counted), making the purge never fire — corrected.
- **Discover devices crash** — Wrapped `Devices` component in a React error boundary class component (`DevicesErrorBoundary`). Any render or async exception during device discovery or SSH terminal now shows an inline error with a "Try again" button instead of blanking the page.

### Tests
- 19-test suite added covering: pipeline ordering, all backend file syntax, version consistency across VERSION/package.json/main.py/App.jsx, key API endpoint presence, and device-side detection thresholds. All 19 pass.

## 0.1.3.e — 2026-06-15

### Bugfixes
- **Changelog page empty** — `CHANGELOG.md` was not included in the Docker build context (`chirp-server/` directory), so `GET /api/v1/changelog` returned "Not found." with no version sections to render. Fixed by copying `CHANGELOG.md` into `chirp-server/` and adding an explicit `COPY CHANGELOG.md ./CHANGELOG.md` line to the Dockerfile.
- **Changelog page returning 401** — `/api/v1/changelog` was not added to the `UNPROTECTED` set in the auth middleware, causing every request to be blocked by JWT verification. Added to `UNPROTECTED` alongside `/api/v1/health`.
- **Changelog parser rendering version-scheme table as a section** — The `## Version Scheme:` heading in `CHANGELOG.md` was being treated as a version entry. Fixed by filtering sections to only those whose heading starts with a digit (`/^## [\d]+\.[\d]/`).
- **`NameError: File is not defined`** — `File`, `Form`, and `UploadFile` were not imported in `auth.py` despite being used by the new profile photo upload endpoint. Added to the `from fastapi import …` line.
- **`NameError: logging not defined`** — startup crash in `database.py`; `import logging` was missing at module level.
- **`ssh_username` on wrong model** — field was accidentally placed on `User` instead of `Device`, causing every DB query involving users to crash with `OperationalError: no such column: users.ssh_username`.
- **`HeartbeatRequest` missing `local_ip`** — Pydantic v2 raises `AttributeError` for undeclared fields rather than returning `None`, crashing every Pi heartbeat with HTTP 500.
- **`bcrypt 4.x` / `passlib` incompatibility** — `passlib`'s internal bug-detection routine calls `hashpw` with a 73-byte test password, triggering `ValueError: password cannot be longer than 72 bytes` on every login attempt. Replaced `passlib.CryptContext` with a thin `bcrypt` wrapper; hash format is identical so existing passwords are unaffected.

## 0.1.3.d — 2026-06-14

### Audit & documentation
- Final comprehensive audit: backend, frontend (JSX), and device code — all clean.
- Confirmed all `.then()` chains have `.catch()` handlers (5 false-positive flags resolved by direct inspection).
- Version scheme formalised as `0.X.Y.Z` with alphabetical patch suffix.
- Complete changelog reconstructed and documented from all prior sessions.
- Root `README.md` rewritten with links to all documentation files and a full versioning guide.
- `GITHUB_SETUP.md` written with step-by-step private repo + public changelog instructions.

## 0.1.3.c — 2026-06-14

### Quality
- Removed 9 debug `console.log` calls left in production frontend code (BirdProfile, Devices, RecordingDetail, Settings).
- Fixed 2 broken `try` blocks in `BirdProfile.jsx` and `RecordingDetail.jsx` caused by overly broad console-cleanup regex stripping the `} catch {` lines.
- Fixed `LifeList.jsx` JSX structure — unclosed `<div>` from sort/export button insertion caused Vite build failure.

## 0.1.3.b — 2026-06-12

### Critical fixes
- **`NameError: logging not defined`** on startup in `database.py`.
- **`ssh_username` on wrong model** — placed on `User` instead of `Device`.
- **`HeartbeatRequest` missing `local_ip`** — Pydantic v2 AttributeError on every heartbeat.
- **bcrypt 4.x / passlib incompatibility** — all logins returning HTTP 500.

## 0.1.3.a — 2026-06-12

### New features
- **SSH terminal** — "Open Terminal" button on any online device card. Full xterm.js terminal in the browser, WebSocket-proxied to a `paramiko` SSH PTY on the Pi. Resize-aware, 256-colour, per-session credentials (not stored server-side).
- **eBird life list CSV export** — "↓ Export to eBird" button on the Life List downloads a CSV in eBird Extended Data Format. Import directly at `ebird.org/import`. Uses most-recent detection date per species; incidental protocol requires no route or duration.
- **User profile photo** — upload a photo (file or URL) from the Profile settings page. Served at `/api/v1/auth/me/photo/{id}{ext}`.
- **iNat token refresh on auth error** — when a submission fails with 401/token-expired, an inline form appears to update the token without leaving the recording page.
- **iNat taxon ID in bird profile** — shown in the Taxonomy card as a clickable link to `inaturalist.org/taxa/{id}`. Aids debugging of geomodel failures.

### Improvements
- **Life list default sort** — changed from detection count to most-recently-detected first.
- **Range map auto-switch** — if the active view's source is disabled in Settings, the map automatically switches to the first enabled source.
- **Settings: Data tab merged into Advanced** — reduces navigation from 10 to 9 tabs.
- **Geomodel schema discovery** — extended column-name candidate lists to cover more GeoPackage variants (`taxon`, `species_id`, `speciesid`, `fid`; `the_geom`, `wkb_geometry`; `value`, `presence`). Better error log directs to debug endpoint.
- **In-app Changelog** — new `/changelog` route in the PWA served from `CHANGELOG.md` via `GET /api/v1/changelog`. Collapsible version sections. Accessible via "v… · What's New" in sidebar footer.
- **CHANGELOG.md** and `0.X.Y.Z` versioning scheme introduced.
- **Patent application** — 25 claims, 8 technical figures, full prior art analysis against HaikuBox, BirdNET-Pi, Merlin, AudioMoth, Song Meter, Arbimon.
- **Proprietary LICENSE** file added.
- Git repository initialised on `main` branch with `.gitignore`.

## 0.1.2.d — 2026-06-12

### Documentation & polish
- Tutorial updated to reflect range map sources, new Settings tab layout, profile photo upload, and eBird export.
- Settings: Appearance tab added as the first tab (was previously unreachable).
- Display Preferences moved adjacent to Theme setting.

## 0.1.2.c — 2026-06-12

### Critical fix — iNat 502 / Cloudflare intercept
- **Root cause:** Cloudflare intercepts any HTTP 502 response from your origin server and replaces the response body with its own HTML error page, making the JSON error detail unreachable in the browser.
- **Fix:** Backend now returns `422` (validation / user error), `503` (cannot reach iNaturalist), or `504` (timeout) instead of 502 in all iNaturalist submission error paths.
- `httpx.TimeoutException` and `ConnectError` caught and converted to clean `RuntimeError` messages. Timeout reduced from 20 s to 15 s.
- Frontend `request()` base function updated to parse JSON `detail` field from error responses and gracefully handle Cloudflare HTML error pages (detected by content-type).

## 0.1.2.b — 2026-06-11

### Audio architecture
- **Dual-path audio** — BirdNET analysis now runs exclusively on the primary microphone stream (`detection_source: "primary"`). Recordings use an SNR-weighted merge of all channels. Prevents low-quality secondary USB mics from diluting the ReSpeaker signal and dropping detections.
- **AGC disable** — `disable_agc_on_start: true` in `config.yaml` runs `amixer sset 'Auto Gain Control' off` at startup on secondary USB mics, stopping level-pumping dropouts during quiet passages.
- **`snr_weighted_merge()`** added to `chirp-device/chirp/utils.py` — weights each channel by current RMS level so the best microphone dominates the recording mix automatically.
- `config.yaml`: new keys `detection_source` and `disable_agc_on_start`.

## 0.1.2.a — 2026-06-09

### Bugfixes
- **Activity by Hour chart** — UTC timestamps were not being converted to the configured timezone before grouping by hour. Chart now shows correct local-time bars with AM/PM labels (e.g. "12 AM", "3 PM") instead of UTC integers.
- **Confidence by Species chart** — height is now calculated dynamically as `max(260, species_count × 26)` so all species bars are visible without vertical clipping.
- **Heatmap Top N buttons** — added `e.preventDefault()` to stop the page scrolling to the top when clicking 10 / 25 / 50 / 100 / All.
- **Device config `NumberInput`** — fields (min confidence, poll interval, etc.) now use local raw string state with `onChange` triggered only on blur. Eliminates focus-loss and unintended scroll-jump while typing numbers.
- **WebSocket error in Logs** — changed from the opaque "WebSocket error" to "Live stream unavailable — showing historical logs only".
- **`journalctl` not found** — backend now gracefully falls back to file log tailing when running inside Docker without systemd.

### New features
- **Storage: keep history, delete audio** — new toggle in Settings → Storage. Auto-cleanup removes WAV / spectrogram files while preserving detection database records. `storage_delete_audio_only` column added to `AppSettings`; both size-based and age-based prune functions respect the flag.

## 0.1.1.c — 2026-06-09

### Settings overhaul
- **Dropdown navigation** — horizontal scrolling pill tabs replaced with a full-width `<select>` dropdown.
- **Appearance tab** added as the first section, grouping Theme and Display Preferences together.
- **Tab reorganisation** — API Keys, Detection (BirdNET + Server Analysis + Device Defaults), Notifications (webhook + email + per-user prefs), and Storage each have correctly anchored sub-sections.
- **Storage cleanup toggle** — "Never auto-delete recordings that have a label or notes" option added.

### Code quality
- Bare `except: pass` → `except OSError: pass` in backup endpoints.
- `print()` statements → `logger` calls in `database.py`.
- 5 uncaught `.then()` promise chains given `.catch(() => {})` handlers.

## 0.1.1.b — 2026-06-09

### Bugfixes
- **Regional Library (Field Guide) — changing / incomplete species count** — two root causes:
  1. *Race condition:* old code did `DELETE → commit → INSERT rows one-by-one → commit`. Any read during the multi-minute window returned a partial list. Fixed with an atomic swap: all rows assembled in memory first, then `DELETE + bulk INSERT` in a single transaction.
  2. *Incomplete list:* `geo/recent` only returns species seen in the past 30 days. Replaced with eBird `/v2/product/spplist/{regionCode}` for the full year-round historical checklist, supplemented by `/v2/ref/taxonomy/ebird` for names and monthly frequency bar-chart data.
- **Auto-purge premature deletion** — "0 server detections" purge was firing before server re-analysis completed. Guard added so purge only evaluates after all background tasks finish.

## 0.1.1.a — 2026-06-09

### New features
- **Range maps — three sources:**
  - *All About Birds (Cornell):* Playwright headless Chromium, `page.on("response")` interception, scrolls to trigger lazy-loading, prefers the most recently loaded image (range map loads after hero photo).
  - *iNaturalist Geomodel:* local GeoPackage files (SQLite), H3 hex grid decoding, custom WKB geometry parser, matplotlib choropleth rendering, Natural Earth basemap. Works offline after initial download.
  - *BirdLife International:* Playwright screenshot of BirdLife factsheet; cookie overlay dismissed before capture.
- **Per-source enable/disable** — Settings → Advanced checkboxes. Disabled sources are hidden from bird profile toggle buttons.
- **GeoPackage download** — progress UI in Settings; background download with status polling.
- **iNaturalist Submission** — one-click "Submit to iNaturalist" on recordings. Creates a sound observation with the WAV attached. Stores `inat_observation_id` and URL on the recording. Works with Rails multipart bracket format required by the iNat API.
- **iNaturalist observation badge** on Recording Detail page.
- **Source-specific range map legends** — AAB, iNat, and BirdLife each use correct season colour conventions.

### Bugfixes
- Removed old "Auto (Wikipedia SVG)" dropdown from bird profile; replaced entirely by three-source toggle.
- AAB scraper: switched from `page.on("request")` to `page.on("response")` so only images that actually loaded are captured.
- iNaturalist submission: initial fix to avoid returning HTTP 502 (Cloudflare intercept issue first identified here; fully fixed in 0.1.2.c).

## 0.1.0.d — 2026-06-07

### Features & fixes
- **Dashboard cards** — each stat card is now clickable and links to a filtered recording view.
- **Spectrogram expand modal** — click spectrogram to open a full-width zoom overlay; click outside or press Escape to close.
- **BirdNET server re-analysis** — configurable minimum confidence threshold; runs in a background thread-pool task after upload.
- **Soft / hard delete** — recordings have a `deleted_at` timestamp. Soft delete hides them from all views; hard delete permanently removes the file and database row.
- **Detection visibility settings** — `min_confidence_display` and `show_low_confidence` toggles in Settings.
- **Share token** — generate a public shareable link to any recording that works without login.
- **Empty recording purge** — manual and automatic removal of recordings with zero detections.
- **Docker bridge IP filter** — heartbeat logic filters out `172.17.x.x` Docker bridge addresses (partial fix; fully resolved in 0.1.3.a with self-reported LAN IP).
- **SMTP persistence** — settings written to a mounted `.env` file rather than the container environment, so they survive container restarts.
- **React state race condition** — parallel Settings fetch calls could overwrite each other. Sequentialised to prevent partial state.
- **Import hygiene** — missing icon imports in the tutorial auto-redirect component caused the entire app to appear broken on first load. Fixed. `ast.parse` validation before packaging added as standard practice.

## 0.1.0.c — 2026-05-28

### New features
- **OLED display rewrite** — pixel-art bird logo, clean status layout (species count, recording count, server status), GPIO 27 button support. Targets SSD1306 I²C at address 0x3C.
- **Device auto-discovery** — server scans the ARP table for known Raspberry Pi MAC address prefixes and presents discovered devices for one-click pairing.
- **SSH credential push** — server SSHes into the Pi using stored credentials and writes `config.yaml` automatically, removing the need to manually edit the file on the device.
- **Full timezone support** — shared `time.js` utility and `useTz()` React hook; all timestamps displayed in the user-configured timezone across every page.
- **eBird regional species library** — Field Guide page showing all species expected in the configured region with 12-month frequency bars, powered by the eBird API.

### Bugfixes
- `_fix_swapped_taxonomy` migration — corrects bird profiles where BirdNET label parsing resulted in the common name and scientific name being transposed.
- iNaturalist observation histogram nested response (`results → month_of_year`) correctly unwrapped.
- Range map legend colour mismatch between old and new SVG format resolved.
- SVG range map constrained with `max-height: 640px` to prevent a light-blue ocean fill from spanning the full viewport height.

## 0.1.0.b — 2026-05-15

### New features
- **User registration with admin approval** — `pending_approval` flag; admin receives email notification of new registration requests.
- **Role-based navigation** — viewer accounts see restricted navigation with admin-only routes hidden.
- **Email notifications** — SMTP settings persisted to DB; configurable alerts for new user registrations, new species detected, and daily digests.
- **Per-user notification preferences** — `notify_new_bird` and `notify_daily_digest` columns on `users` table.
- **WebSocket real-time notifications** — `ConnectionManager` broadcasts new-detection events to all connected browser clients instantly.
- **Xeno-canto / iNaturalist call media** — up to 8 labelled call recordings (song, call, alarm) per species, with quality grading.
- **Monthly frequency chart** — 12-bar seasonal activity chart from eBird `speciestrends` API, with iNaturalist histogram as fallback.

### Bugfixes
- Dashboard stuck on "Loading…" — `BirdProfile` route defined as `:id` but component read `profileId`; fixed with `const { id: profileId } = useParams()`.
- Recordings disappeared after update — new database columns were missing from `_migrate_columns()` `pending` dict; `ALTER TABLE` skipped them silently.

## 0.1.0.a — 2026-05-01

### Core system
- **Raspberry Pi 5 edge sensor** — continuous multi-channel audio capture via `sounddevice`; two-stage detection pipeline (RMS energy filter → BirdNET TFLite neural classifier); 5-second circular pre-roll buffer; Google Coral EdgeTPU support (USB, M.2 A+E, M.2 B+M, and PCIe variants via `gasket-dkms` driver).
- **Docker server** — FastAPI + SQLite + React/Vite PWA; containerised for Unraid and any Docker host; served on port 8765.
- **Recording upload** — WAV + JSON metadata sidecar; multipart POST with `X-API-Key` authentication; exponential-backoff retry queue on the device side.
- **Mel spectrogram generation** — `librosa` + `matplotlib`; detection bounding box overlays with per-species colour coding.
- **Species enrichment pipeline** — Wikipedia REST API (description + sections), iNaturalist API (photo, taxon ID), Cornell eBird API (species code, taxonomy), Xeno-canto API (call recordings); data cached locally after first fetch with 30-day TTL.
- **Species likelihood scoring** — weighted combination of eBird geo/recent observations (weight 0.50) + local detection history (0.40) + temporal recency bonus (0.10); four categorical labels: Very Likely / Likely / Possible / Rare.
- **WebGUI** — Dashboard, Recordings list, Recording Detail (spectrogram + audio player), Bird Library, Bird Profile, Field Guide (regional species), Settings.
- **Device pairing** — API key in `X-API-Key` header; managed config push; `config_version` handshake via heartbeat.
- **JWT authentication** — optional login; `auth_enabled` toggle; default `chirp-admin` account.
- **Patent application** — 20 initial claims covering the core system and method; five technical blueprint figures.

*Chirp is a self-hosted, edge-AI bird call detection system. All data stays on your hardware.*
*© 2026 Joshua Salvi — All rights reserved — josh.salvi@gmail.com*
