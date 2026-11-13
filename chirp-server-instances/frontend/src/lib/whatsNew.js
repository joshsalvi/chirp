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
  version: '0.5.19.am',
  // The release whose `latest` text this is. The popup shows once per value,
  // so small fixes that don't change `latest` don't bring it back.
  popup: '0.5.19.l',
  title: "What's new in Chirp",
  latest: {
    intro: 'A new, simpler dashboard.',
    sections: [
      {
        heading: '🐦 Standard dashboard',
        body: "The latest bird and its song, today's birds as photos, three facts and a line from the journal. It's the new default.",
      },
      {
        heading: '📊 Advanced is one tap away',
        body: 'The full dashboard is now called Advanced. Switch with the button at the top of the Dashboard or in Settings → Appearance.',
      },
    ],
  },
  recent: [
    { version: '0.5.19.am', summary: 'Photos from other sites no longer carry your sign-in.' },
    { version: '0.5.19.al', summary: 'Bird profiles show their header photo again.' },
    { version: '0.5.19.ak', summary: 'The next photo no longer peeks in on the dashboard.' },
    { version: '0.5.19.aj', summary: 'Tighter website header on phones; bird photos load together.' },
    { version: '0.5.19.ai', summary: 'Swipe through bird photos, pinch to zoom spectrograms, and stay signed in.' },
    { version: '0.5.19.ah', summary: 'Enhanced audio: much less hiss, especially with Rumble removed.' },
    { version: '0.5.19.ag', summary: 'iPhone app: Account → Haptics turns vibration on or off.' },
    { version: '0.5.19.af', summary: 'Demo: Live Detect through the station plays back a recording from the yard.' },
    { version: '0.5.19.ae', summary: 'The demo shows its daily and weekly journals.' },
    { version: '0.5.19.ad', summary: 'Try the demo: a read-only look at a real yard, no account needed.' },
    { version: '0.5.19.ac', summary: 'Standard dashboard: a Show all / Show fewer button under the bird grid.' },
    { version: '0.5.19.ab', summary: 'A new Apps page describes Chirp, Chirp Lite and Chirp Live, with fresh screenshots across the website.' },
    { version: '0.5.19.aa', summary: 'Song line: only the bars light up where the bird was heard.' },
    { version: '0.5.19.z', summary: 'Press and drag along the tab bar: the glass lens follows your finger and opens the tab you let go on.' },
    { version: '0.5.19.y', summary: 'Liquid Glass tab bar on phones, a tap of haptics when pulling to refresh, and song lines that highlight where the bird sang.' },
    { version: '0.5.19.x', summary: 'Multi-location servers share one species library, so a location\'s new birds load without fetching from the web.' },
    { version: '0.5.19.w', summary: 'Global Admin: usage for each location. ourchirp.com: new locations wait for approval.' },
    { version: '0.5.19.v', summary: 'Song line: the latest bird\'s player shows the recording\'s sound, where the bird is, and a mark per call to tap.' },
    { version: '0.5.19.u', summary: 'Chirp Live 1.3: level bars, running spectrogram, waveform or live spectrum while listening.' },
    { version: '0.5.19.t', summary: 'Pull to refresh: the indicator sits in the space above the page; long bird names no longer break mid-word.' },
    { version: '0.5.19.s', summary: 'iPhone and iPad app: swipe from the edge to go back or forward, pull down to refresh, tap the status bar to scroll up.' },
    { version: '0.5.19.r', summary: 'The latest-bird photo takes the photo\'s shape, so tall birds are shown head to toe.' },
    { version: '0.5.19.q', summary: 'The dashboard view button reads "View: Standard" or "View: Advanced".' },
    { version: '0.5.19.p', summary: 'Standard dashboard: tall photos of the latest bird are shown whole.' },
    { version: '0.5.19.o', summary: 'Standard dashboard photos keep the bird\'s head in view.' },
    { version: '0.5.19.n', summary: 'Website, user guide and App Store show the Standard dashboard.' },
    { version: '0.5.19.m', summary: 'Standard dashboard: all of today\'s birds in one tap, a by-hour chart, a picker that fits on phones.' },
    { version: '0.5.19.l', summary: 'New Standard dashboard; the full one is now Advanced.' },
    { version: '0.5.19.k', summary: 'Hosted site media moved to NVMe for faster pages and audio.' },
    { version: '0.5.19.j', summary: 'Chirp for iPhone and iPad is on the App Store; Chirp Lite in the iPhone app.' },
    { version: '0.5.19.i', summary: 'A local range map for every bird and bat, including the Bat profile.' },
    { version: '0.5.19.h', summary: 'Chirp Lite Today shows the first song of the day; swipe back on iPhone.' },
    { version: '0.5.19.g', summary: 'Range map pictures for maps hosted on Wikimedia.' },
    { version: '0.5.19.f', summary: 'Chirp Lite iPhone shows Wikipedia range maps.' },
    { version: '0.5.19.e', summary: 'Chirp Lite range maps (eBird Status & Trends first); the BirdLife map tab works again.' },
    { version: '0.5.19.d', summary: 'Chirp Lite iPhone: the sign-in screen fits the screen.' },
    { version: '0.5.19.c', summary: 'Chirp Lite photo credits; the Chirp Lite iPhone app (source, icon set, listing).' },
    { version: '0.5.19.b', summary: 'Chirp Lite: the playing bar stays small; sign-ins for the Chirp Lite iPhone app.' },
    { version: '0.5.19.a', summary: 'Chirp Lite: a simple, picture-first view at /lite.' },
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
  '0.5.19': 'Chirp Lite, a simple picture-first view, and Chirp for iPhone and iPad on the App Store.',
  '0.5.18': 'Security headers and sign-in limits, Apple TV listen-back, backups fixed, faster pages and Chirp Live on the App Store.',
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
