# Chirp Lite on the App Store

App record: "Chirp Lite: Backyard Birds", bundle ID `com.joshuasalvimd.chirp.lite`, SKU `chirp-lite`.

Pushed by script:
- `BUNDLE_ID=com.joshuasalvimd.chirp.lite python3 scripts/asc.py listing docs/app-store-metadata-lite.json docs/screenshots/lite`
- `BUNDLE_ID=com.joshuasalvimd.chirp.lite python3 scripts/asc.py store-setup --apply` (age rating, content rights, free, availability, review contact)
- `./build-lite.sh --testflight` (build), `LITE_USER=<account> ./build-lite.sh --shots` (screenshots)

Set by hand in App Store Connect: App Privacy and the demo account password (`appreview`).

## App Privacy

The app only reads from the Chirp site someone signs in to; ourchirp.com is run by us, so the sign-in counts.

| Data type | Collected | Use | Linked to the person | Tracking |
|---|---|---|---|---|
| Identifiers → User ID | Yes | App Functionality | Yes | No |
| Everything else | No | | | |

No location, audio, contacts, usage data or diagnostics leave the phone; the app has no analytics.
