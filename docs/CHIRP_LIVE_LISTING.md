# Chirp Live: App Store submission

App: **Chirp Live: Bird Sound ID**, bundle ID `com.joshuasalvimd.chirplive`, version 1.0.

The store text, URLs, categories, review notes and screenshots are in
`app-store-metadata-live.json` and go up with:

    BUNDLE_ID=com.joshuasalvimd.chirplive python3 scripts/asc.py listing docs/app-store-metadata-live.json docs/screenshots/live
    BUNDLE_ID=com.joshuasalvimd.chirplive python3 scripts/asc.py store-setup --apply
    BUNDLE_ID=com.joshuasalvimd.chirplive python3 scripts/asc.py prepare-version 1.0 BUILD

`store-setup --apply` answers the age rating (all None/No), content rights,
free pricing and availability in every territory. Screenshots come from
`scripts/live-promo.py` (simulator shots plus captions).

Set by hand in App Store Connect: App Privacy, the review contact (name,
email, phone; the API wants all four at once) and the demo password.

## App Privacy (App Store Connect → App Privacy)

Data is collected only when someone signs in to a Chirp site; ourchirp.com is
run by us, so it counts.

| Data type | Collected | Use | Linked to the person | Tracking |
|---|---|---|---|---|
| Location → Precise Location | Yes | App Functionality | Yes | No |
| User Content → Audio Data | Yes | App Functionality | Yes | No |
| Identifiers → User ID | Yes | App Functionality | Yes | No |
| Everything else (contact info, health, financial, contacts, browsing, search, usage data, diagnostics, purchases, other) | No | | | |

Not collected by us: the coordinates the app sends to Apple's map service to
name a place (Apple's service, nothing kept by us), and anything from people
who don't sign in (it stays on the phone).

## Age rating

Every content question: **None**. Unrestricted web access, gambling, contests,
user-generated content, messaging, advertising: **No**. Result: **4+**.

## Pricing and availability

Free, all countries and regions. Not for Apple Vision or Mac (iPhone only).

## Other answers

- **Content rights:** contains third-party content, and we have the rights:
  BirdNET models under CC BY-NC-SA 4.0 (credited in the app and the
  description; the app is free).
- **Encryption:** none beyond Apple's HTTPS (set in the build,
  `ITSAppUsesNonExemptEncryption = NO`).
- **Sign-in information for review:** user `appreview` on ourchirp.com; type
  the password into App Review Information. Sign-in isn't required to use the
  app, so "Sign-in required" stays off.
- **Contact:** Joshua Salvi, josh.salvi@gmail.com.

## Screenshots

6.9-inch iPhone, 1320 × 2868, in `docs/screenshots/live/`, made from the
simulator (`-ChirpShots listen|summary|sessions|station|welcome`) with a
caption above each.
