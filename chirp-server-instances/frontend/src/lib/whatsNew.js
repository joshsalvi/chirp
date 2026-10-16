// What's New popup and Changelog summaries. Same file in both forks.
//
// Keep it short:
// - latest: what changed for people since the last popup. An intro of one
//   sentence and at most three items, each one or two sentences.
// - recent: the current minor version (X.Y.Z), one short line per release
//   people would notice. Server-only and developer releases are left out.
// - GROUP_SUMMARIES: one line per minor version (0.5.12, 1.3…), shown on
//   the collapsed Changelog card. Add the new minor's line when it starts;
//   when it ends, rewrite it to cover the whole minor and empty `recent`.
// - ERA_SUMMARIES: one line per major version (0.5, 0.4…), shown on the
//   collapsed era card.
//
// WHATS_NEW.version must match the VERSION file (stamp-sw-version.mjs
// checks it). Set `popup` to the new version when `latest` changes.
export const WHATS_NEW = {
  version: '0.5.13.e',
  // The release whose `latest` text this is. The popup shows once per value,
  // so small fixes that don't change `latest` don't bring it back.
  popup: '0.5.13.a',
  title: "What's new in Chirp",
  latest: {
    intro: 'Newer bird-ID models to try, night flight calls, and safer deletes.',
    sections: [
      {
        heading: '🧪 BirdNET v3',
        body: 'Admins can turn it on in Settings → Experimental → Detection Models, to compare on each recording or as the main model. In testing it found about twice as many species at the same accuracy.',
      },
      {
        heading: '🌙 Night flight calls',
        body: 'With Nighthawk on, stations send their night audio and the new Night Calls page lists the calls of migrating birds overhead.',
      },
      {
        heading: '🗑️ Confirm before deleting',
        body: 'Clearing all notifications asks first, and deleting your account needs the word delete typed.',
      },
    ],
  },
  recent: [
    { version: '0.5.13.e', summary: 'Night Calls: playback fixed and plainer names for each call.' },
    { version: '0.5.13.d', summary: 'Clearer Settings descriptions, including Empty Recordings.' },
    { version: '0.5.13.b', summary: 'Station offline alerts wait 15 minutes by default; the delay is in Settings.' },
    { version: '0.5.13.a', summary: 'BirdNET v3 and night flight calls in Settings → Experimental; delete confirmations.' },
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
  '0.5.13': 'BirdNET v3 and Nighthawk night flight calls (experimental).',
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
