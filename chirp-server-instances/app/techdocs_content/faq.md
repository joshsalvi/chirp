# FAQ / Troubleshooting

Issues that came up during development, with the root cause
and fix — not hypothetical scenarios.

## "Input overflow" warnings from a USB microphone

**Cause:** the audio callback chunk size is too small for that
particular USB device to keep up with reliably — some USB audio
hardware can't service very frequent, very small callbacks without
occasionally missing one.

**Fix:** increase `audio.chunk_size` in `config.yaml` (default 8192;
try 16384 if warnings persist).

## A microphone isn't being detected at all

Two independent lists control this, and it's worth checking both:

- `device_name_hints` — the device's name needs to match one of these
  substrings *or* be picked up by the broader fallback scan over all
  connected input devices. If it's a genuinely unusual device name, it should
  still be caught by the fallback scan rather than silently ignored.
- `device_name_excludes` — checked independently, and takes priority.
  If a device's name matches something in this list, it's excluded from
  bird detection regardless of what's in the hints list. Nothing is
  excluded by default.

## Cool Facts / species enrichment missing for some species

The Cornell Lab / All About Birds source sits behind Cloudflare, which
has occasionally challenged automated requests during a fetch. The
system distinguishes a genuine Cloudflare block from AAB simply having
no page for a given species — a block doesn't get permanently cached as
"no data," so it retries on a future enrichment pass rather than being
stuck empty forever. If a specific bird's profile seems to be missing
data that other birds have, a manual re-enrichment (via Settings) will
usually resolve it.

## BirdNET is reporting species that clearly aren't local

This almost always means location filtering isn't configured — without
a latitude/longitude, BirdNET evaluates against its full global species
list rather than what's realistic for the deployment's own location.
Set the location in the server's Settings page; it propagates to
connected edge devices automatically.

## The home-screen icon still shows the old logo

Icon links carry the release version (`/icon-192.png?v=0.5.8.d`), and the
server sends the manifest and icons with `Cache-Control: no-cache`, so a
new release always looks like a new icon to the browser.

- **Android (Chrome):** the installed app checks the manifest when it
  launches, at most once a day, and swaps the icon in. Chrome may ask to
  confirm the change.
- **Desktop Chrome/Edge:** same daily check; icon changes may ask for
  confirmation or need a reinstall on older versions.
- **iPhone/iPad:** iOS saves the icon when the app is added and never
  updates it. Chirp shows a one-time card with the steps: remove Chirp
  from the Home Screen, then in Safari tap Share → Add to Home Screen.
- **Browser tab:** reload the page once.
