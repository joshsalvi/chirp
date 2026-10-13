# Chirp — App Store and TestFlight listing

Everything App Store Connect asks for, ready to paste. Character limits are Apple's; every field here fits.

## App Information (App Store Connect → General → App Information)

| Field | Value |
|---|---|
| Name (30) | Chirp: Bird Call Detector |
| Subtitle (30) | Know every bird in your yard |
| Bundle ID | com.joshuasalvimd.chirp |
| SKU | chirp-ios-001 |
| Primary category | Reference |
| Secondary category | Education |
| Content rights | Does not contain, show or access third-party content it doesn't have rights to (bird photos come from licensed sources with credits shown) |
| Age rating | 4+ (answer "None" to every question; no unrestricted web access, no user-generated content visible to strangers) |

## Pricing and Availability

- Price: Free (USD 0)
- Availability: all countries, or United States only to start
- iPad: not offered (the build is iPhone only)

## Version page (Distribution → iOS App → 0.5.11)

**Promotional text (170)**
```
Hear who's singing. Chirp listens around the clock, names each bird with BirdNET and builds your life list, with an alert the moment a new species turns up.
```

**Description (4000)**
```
Chirp turns your backyard into a bird observatory. A small listening station records bird calls day and night, identifies each species with the BirdNET model, and sends everything to your Chirp server. This app is your window into it.

WHAT YOU CAN DO
• See today's birds at a glance, with photos, the latest detection and how confident the identification was.
• Open any recording to hear the call and see its spectrogram, with each species marked where it sings.
• Build your life list automatically, with first-heard dates, counts and streaks for every species.
• Read species profiles with photos, sounds, range maps and how often the bird is seen in your area this month.
• Use the Field Guide to see which birds are likely near you right now, from eBird data.
• Run Live Detect to identify birds with your iPhone's microphone wherever you are, with the location saved alongside if you choose.
• Get push alerts for new species, for birds you choose to watch (every time or a daily summary), and for the evening Daily Journal and Sunday Weekly Journal. Every alert is also kept in the Notifications tab, and tapping one opens the recording or journal entry.
• Ask for an AI second opinion on a tricky recording, add notes, and submit observations to iNaturalist.

YOUR DATA STAYS YOURS
Chirp runs on its operator's server. No ads, no tracking, no selling of data. You can delete your account in the app at any time.

Chirp needs a Chirp site account. Ask the person who runs your Chirp site for an invite code.
```

**Keywords (100)**
```
birds,birding,bird song,bird call,birdnet,identify,life list,ebird,owl,backyard,nature,sound
```

**Support URL:** `https://ourchirp.com/support.html`
**Marketing URL:** `https://ourchirp.com/`
**Copyright:** `2026 Joshua Salvi`
**What's New** (from the second version on; the first version has no such field):
```
First App Store release: live bird detections from your Chirp site, recordings with spectrograms, life list, species profiles, Field Guide, Live Detect, and push alerts for new species.
```

## Screenshots

6.9-inch iPhone, 1320 × 2868 (Apple scales them for smaller iPhones). Upload in this order:

| # | File | Headline |
|---|---|---|
| 1 | 1-dashboard.png | Know who's singing |
| 2 | 2-recording.png | See every call |
| 3 | 3-life-list.png | Your life list builds itself |
| 4 | 4-bird-profile.png | Meet each bird |
| 5 | 5-field-guide.png | What's around right now |
| 6 | 6-notifications.png | Never miss a newcomer |
| 7 | 7-my-notifications.png | Alerts your way |

In `~/Developer/Chirp/app-store/`: `marketing/` has the captioned versions for the store, `raw/` the plain app screenshots, `icon-1024.png` the icon (already in the build).

## App icon

Comes from the build (1024 × 1024, no transparency): `ios-icons/icon-1024.png`. Nothing to upload separately.

## App Review Information

| Field | Value |
|---|---|
| Sign-in required | Yes |
| User name | appreview |
| Password | not stored here (in the chat where the account was made; reset it with the admin tools if lost) |
| Contact | Joshua Salvi, josh.salvi@gmail.com, plus a phone number |

**Notes**
```
Chirp is the companion app for a self-hosted bird call detection system. The demo account is a read-only member of a site in Natick, Massachusetts, where a listening station records birds all day, so new recordings and detections appear throughout the day.

Try: Dashboard; open any recording to play it and see its spectrogram; Life List; species profiles; Field Guide; the Notifications tab. Live Detect works anywhere: tap the sound-wave tab, then Start, near bird song.

Permissions: notifications and microphone are requested right after sign-in. The microphone is used only while Live Detect runs; location is requested when Live Detect starts (optional, saved with its recordings).

Account deletion: ⋮ → My Profile → Delete account (password required). If you delete the demo account, email us and we'll recreate it.

Native features: push notifications (APNs), microphone capture, Bluetooth setup of listening stations, haptics, share sheet and file export.
```

## App Privacy (App Store Connect → App Privacy)

Tracking: **No** (Chirp doesn't track people across apps or websites).

| Data type | Collected | Linked to the person | Used for tracking | Purpose |
|---|---|---|---|---|
| Contact Info → Email address | Yes (optional) | Yes | No | App Functionality |
| Contact Info → Name | Yes (optional display name) | Yes | No | App Functionality |
| User Content → Audio data | Yes (Live Detect clips, uploads) | Yes | No | App Functionality |
| User Content → Other user content (notes) | Yes | Yes | No | App Functionality |
| User Content → Photos | Yes (optional profile photo) | Yes | No | App Functionality |
| Identifiers → User ID | Yes (username) | Yes | No | App Functionality |
| Identifiers → Device ID | Yes (push token) | Yes | No | App Functionality |
| Location → Precise location | Yes (optional; only while Live Detect runs, saved with its recordings) | Yes | No | App Functionality |
| Usage data, diagnostics, contacts, health, financial | No | | | |

Privacy policy URL: `https://ourchirp.com/privacy.html`

## Export compliance

The build declares `ITSAppUsesNonExemptEncryption = NO` (only standard HTTPS), so App Store Connect doesn't ask.

## TestFlight → Test Information

**Beta App Description**
```
Chirp shows what your Chirp listening station has heard: today's birds, recordings with spectrograms, your life list, species profiles and a local field guide. Live Detect identifies birds with the iPhone microphone, and push notifications announce new species.
```
Feedback email: `josh.salvi@gmail.com` · Marketing URL: `https://ourchirp.com/` · Privacy Policy URL: `https://ourchirp.com/privacy.html`

**What to Test** (per build)
```
- Sign in, then allow notifications and the microphone when asked.
- Check the Notifications tab and its badge when a new bird is announced.
- Open a recording, play it and scroll the spectrogram.
- Try Live Detect outdoors for a minute.
- Tell us about anything that looks wrong on your iPhone model.
```

Beta App Review uses the same sign-in and notes as App Review above.

## Keeping builds current

- Testers are never re-added; they stay in their group across builds.
- Internal group: no review; turn on "Automatically distribute builds" and every upload reaches testers about 10–30 minutes after processing. Internal testers must be App Store Connect users (Users and Access, any role).
- External group "CH": each build is added to the group by hand and goes through Beta App Review (first build about 24–48 h; later versions usually hours). A build with the same version number and a new build number usually skips review.

- Every app update is uploaded to TestFlight (`TEAM_ID=F7N9ZF7U57 ./build-ios.sh --testflight`).
- The Mac also uploads by itself when the last upload is 40 days old (`scripts/testflight-auto.sh`, LaunchAgent `com.joshuasalvimd.chirp.testflight`, Mondays 9:07).
