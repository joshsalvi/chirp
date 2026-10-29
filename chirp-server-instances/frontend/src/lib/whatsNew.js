// What's New popup and Changelog summaries. Same file in both forks.
//
// Keep it short:
// - latest: what changed for people since the last popup. An intro of one
//   sentence and at most three items, each one or two sentences.
// - recent: the current minor version (X.Y.Z), one short line per release.
//   Every server release gets a line, developer and server-only ones too.
// - GROUP_SUMMARIES: one line per minor version (0.5.12, 1.3…), shown on
//   the collapsed Changelog card. Add the new minor's line when it starts;
//   when it ends, rewrite it to cover the whole minor and empty `recent`.
// - ERA_SUMMARIES: one line per major version (0.5, 0.4…), shown on the
//   collapsed era card.
//
// WHATS_NEW.version must match the VERSION file (stamp-sw-version.mjs
// checks it). Every server release adds its `recent` line. `popup` changes
// only when `latest` does (set it to that release's version): the popup
// shows once per `popup`, so a fix that leaves `latest` alone doesn't bring
// it back with the same text. WhatsNewModal shows it only when `popup` is
// newer than the version last dismissed.
export const WHATS_NEW = {
  version: '0.5.18.b',
  // The release whose `latest` text this is. The popup shows once per value,
  // so small fixes that don't change `latest` don't bring it back.
  popup: '0.5.17.a',
  title: "What's new in Chirp",
  latest: {
    intro: 'BirdWeather stations, an app diagnostics file for problem reports, and a page for testing the apps early.',
    sections: [
      {
        heading: '🌦️ BirdWeather',
        body: 'Admins can bring in the sound from a BirdWeather station (PUC, BirdNET-Pi or BirdNET-Go) in Settings → Integrations. Chirp runs it through BirdNET like an upload, with spectrograms and playback.',
      },
      {
        heading: '🩺 App diagnostics',
        body: 'Account → Help & Feedback can export a text file about this app and device, or add it to your message, to help sort out problems.',
      },
      {
        heading: '📱 Test the apps early',
        body: 'Request a TestFlight invite for the iPhone, iPad, Apple TV or Chirp Live app at ourchirp.com/testflight.html.',
      },
    ],
  },
  recent: [
    { version: '0.5.18.b', summary: 'Web framework pinned to the tested versions.' },
    { version: '0.5.18.a', summary: 'Security headers, sign-in limits and faster builds; ourchirp.com admins get reachability and security events.' },
  ],
}

export const ERA_SUMMARIES = {
  '0.5': 'Hosted sites at ourchirp.com, the iPhone app, Live Detect, AI second opinions and a tuned night pipeline.',
  '0.4': 'Bluetooth device setup, bat echolocation and native iPhone push.',
  '0.3': 'AI arrives: Daily Journal, profile summaries and call re-analysis.',
  '0.2': 'Versioning scheme adopted; cache and Field Guide fixes.',
  '0.1': 'The foundation: Pi station, two-stage BirdNET, Docker server and web dashboard.',
  '1': 'The Raspberry Pi station software (chirp-device).',
}

export const GROUP_SUMMARIES = {
  '0.5.18': 'Security headers and sign-in limits, reachability and security events, faster builds.',
  '0.5.17': 'BirdWeather stations, app diagnostics, Chirp Live picture packs, smoother ChirpPi Live Detect and an optional Ollama key.',
  '0.5.16': 'Apple TV app, iPad support, theme-matched app icon, night flight call filters, TestFlight sign-up, site traffic, safer hosted sites and the website moved to ourchirp.com only.',
  '0.5.15': 'Troubleshooting page and recent recordings on Apple Watch.',
  '0.5.14': 'BirdNET v3 by default, per-bird AI ratings, Low pitch view, Back and Forward, station hum filter, saved recordings and a tidier Recordings list.',
  '0.5.13': 'BirdNET v3 and Nighthawk night flight calls, station offline alerts, clearer Settings text.',
  '0.5.12': 'Notifications tools, same-day digest, reorganized Settings, fewer false owls, hosted sites, invite codes and station-offline alerts.',
  '0.5.11': 'Notifications tab, iPhone push alerts, read-only viewers, privacy page, first TestFlight builds.',
  '0.5.10': 'Faster deletes, smaller spectrograms, night-caller thresholds, new daily email, iOS 26–27 fixes.',
  '0.5.9': 'Animated Songbird logo, iPhone app permissions and offline page, better owl scoring, FLAC storage.',
  '0.5.8': 'New Songbird logo, sharper AI Second Opinion, steadier Tailscale, app moved to ourchirp.com.',
  '0.5.7': 'AI Enhance, rebuilt AI Second Opinion, Rumble Removed, overnight owl fixes, XVF3800 support.',
  '0.5.6': 'Live Detect overlap and sensitivity, Mic Frequency Response, high-pass filter fix.',
  '0.5.5': 'Remote access via Tailscale and Headscale, site import, Tech Docs page.',
  '0.5.4': 'Saved Live Detect sessions, choose Dashboard cards, database health tools.',
  '0.5.3': 'Life History card, AI Second Opinion for bats and multiple species, mic Listen button.',
  '0.5.2': 'Bird size ruler, bats toggle in Statistics, Tech Docs page.',
  '0.5.1': 'At a Glance card and the missing Cool Facts fixed.',
  '0.5.0': 'AudioMoth recovery, iNaturalist comments, light-theme fixes.',
  '0.4.0': 'Bluetooth WiFi setup, bat detection end to end, native iPhone push.',
  '0.3.0': 'Daily Journal, profile summaries and call re-analysis across four AI providers.',
  '0.2.0': 'Versioning scheme adopted; stale-cache and Field Guide fixes.',
  '0.1.17': 'Bird Buddy and Haikubox integrations; a purge bug that deleted bat recordings fixed.',
  '0.1.16': 'Bat detection wired into recordings.',
  '0.1.15': 'Bat species classifier; a deploy caching bug fixed.',
  '0.1.14': 'Mic-level and changelog display fixes.',
  '0.1.13': 'Photo gallery layout fixes.',
  '0.1.12': 'Range map tabs stop re-fetching.',
  '0.1.11': 'Breeding-season bands on eBird range maps.',
  '0.1.10': 'Range map legends fixed.',
  '0.1.9': 'Three new themes, OLED fix, Dashboard date fix.',
  '0.1.8': 'Haikubox support; Field Guide and Settings fixes.',
  '0.1.7': 'Recordings cleanup, device location defaults.',
  '0.1.6': 'Device audio-test crashes fixed.',
  '0.1.5': 'European species no longer slip through the location filter.',
  '0.1.4': 'eBird export; notification fixes.',
  '0.1.3': 'SSH terminal fixes.',
  '0.1.2': 'iNaturalist and audio pipeline fixes.',
  '0.1.1': 'Settings rework and early fixes.',
  '0.1.0': 'First release: detection, recordings and the life list.',
  '1.3': 'XVF3800 raw mics, owls kept by the location filter, Coral scoring like CPU, night-caller thresholds.',
  '1.2': 'Uploads to several servers, Tailscale, Bluetooth setup install fixes.',
}
