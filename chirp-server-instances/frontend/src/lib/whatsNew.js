// What's New popup content.
//
// Structure: `latest` is the ONLY thing shown in full detail — the
// popup exists to announce what's new *right now*, not to be a running
// archive (that's what the Changelog page, linked from the popup, is
// for).
//
// `previousHighlights` and `olderHistory` are TWO tiers, both shown
// collapsed by default:
//   - previousHighlights: individual entries, one sentence each, for
//     the CURRENT minor version ONLY (the X.Y in X.Y.Z — everything
//     sharing WHATS_NEW.version's first two numbers). This is the part
//     someone reads to catch up after being away a little while, and
//     it's naturally self-limiting in length since a minor version's
//     patch letters reset every time Y increments.
//   - olderHistory: every PRIOR minor version, one entry per minor
//     version — "0.5.2", not eighteen separate 0.5.2.a../0.5.2.n
//     lines. Older entries may span a wider range (a whole major
//     version's era, or several minors that were small/related enough
//     to fold together) once they're old enough that per-minor detail
//     stops being useful — see the pre-0.5.0 entries below for the
//     pattern. Not meant to replace CHANGELOG.md (the complete
//     record); this is here so the popup's own history doesn't just
//     cut off into nothing once a minor version ages out of
//     previousHighlights.
//
// MAINTENANCE RULE, moving forward: every version bump prepends to
// previousHighlights as before. But the MOMENT a version bump
// increments the minor number (Y in X.Y.Z changes — e.g. 0.5.3.j to
// 0.5.4.a), previousHighlights' entire current content (all of the
// outgoing minor version's patches) collapses into ONE new entry
// prepended to olderHistory — written as a single sentence or two
// covering the general arc of that minor version, not a list of every
// individual patch — and previousHighlights starts fresh, empty, for
// the new minor version. A minor version should never have more than
// one entry sitting in olderHistory; if it does, that's the same
// unbounded-growth bug this structure exists to prevent, just moved
// down a tier instead of fixed.
//
// WHATS_NEW.version must match the VERSION file exactly (the
// build-time check in stamp-sw-version.mjs enforces this), or the popup
// won't trigger for anyone since it'll look identical to whatever they
// already last saw.
export const WHATS_NEW = {
  version: '0.5.12.r',
  title: "What's new in Chirp",
  latest: {
    intro: "Fewer false owls, an evening digest for the day you just had, a tidier Settings page, and working test emails.",
    sections: [
      {
        heading: '🦉 Fewer false owls',
        body: "Pigeon coos, engines and voices were being called Great Horned, Long-eared or Saw-whet Owls, mostly in the daytime. An owl now needs support across the whole sound, not just the low band, and a device's owl stays only when the server hears it too. Tested on Natick's recordings: false owls on midday recordings fell from 20 in 231 to 1, with every Barred Owl still found.",
      },
      {
        heading: '📰 Digest on the day itself',
        body: "The daily digest push and email each have a separate send time in your site's time zone (Settings → Alerts & Email → Daily Digest). A time from noon on covers that day so far, so a 9 PM push sums up today; an earlier time covers yesterday. The digest page keeps counting until midnight, and each bird's play button opens Recordings filtered to that bird.",
      },
      {
        heading: '⚙️ Settings, reorganized',
        body: "New General tab for location, time zone, web address and what everyone sees. Alerts & Email holds the digest times, email server and iPhone push keys; eBird keys moved to Integrations; Access & Security gathers sign-in, device keys, the activity log and network; card layout and app install moved to Appearance.",
      },
      {
        heading: '✉️ Test emails',
        body: "Send Test, Test New Bird and Test Digest work again and use the same designs as the emails people receive, with your site's latest bird and latest day.",
      },
    ],
  },
  previousHighlights: [
    { version: '0.5.12.r', summary: 'Live Detect explains when a server address needs https://.' },
    { version: '0.5.12.q', summary: 'Groundwork for connecting the iPhone app to any Chirp server.' },
    { version: '0.5.12.p', summary: 'Request a hosted site or a push relay token at ourchirp.com/about.' },
    { version: '0.5.12.o', summary: 'A public About page at ourchirp.com/about, linked from the sign-in screen.' },
    { version: '0.5.12.n', summary: 'Global Admin\'s Headscale panel works again, and Headscale restarts itself if its admin socket stops answering.' },
    { version: '0.5.12.m', summary: 'Far fewer false owls from noise; every Barred Owl in testing still found.' },
    { version: '0.5.12.l', summary: 'Evening digest for the same day, separate push and email times, reorganized Settings and working test emails.' },
    { version: '0.5.12.k', summary: 'Faster Live Detect session saves, and each daily digest goes out once.' },
    { version: '0.5.12.j', summary: 'Delete one notification at a time, a dependable morning digest, and My Notifications without stray Dashboard cards.' },
    { version: '0.5.12.e', summary: 'Haptic feedback across the iPhone app.' },
    { version: '0.5.12.c', summary: 'Faster app start and page switching, and Settings as a simple list with live search and a Save bar that appears only when needed.' },
    { version: '0.5.12.b', summary: 'Live Detect through a Chirp device uses that device\'s location.' },
    { version: '0.5.12.a', summary: 'My Notifications in Settings, watched birds, journal pushes that open the journal, Live Detect location, and in-app account deletion.' },
  ],
  olderHistory: [
    { range: '0.5.11', summary: 'A Notifications tab with unread badge, push alerts in the iPhone app with permission prompts on first launch, view-only accounts made read-only on the server, a privacy page, account deletion in the app, and the first TestFlight builds.' },
    { range: '0.5.10', summary: 'Deletes and auto-purge stopped locking the database, Unknown recordings were hidden, spectrogram storage shrank, and night callers got their own threshold choices (own floors, global, or per species). AI Second Opinion answered faster, the daily email got bird photos and a new layout, the server learned to re-sign the iOS app, server BirdNET was protected against broken builds, the iPhone Home Screen app was fitted to iOS 26.1+ and 27, and signing in from an iPhone stopped failing on capital letters.' },
    { range: '0.5.9', summary: 'A refined Songbird logo with motion, then the iOS app grew up: microphone and notification prompts, iOS 27 support, theme-following status bar, offline page, and no zoom when typing. Owls stopped being dropped by the location filter and were scored on a low-frequency copy of the audio with a hoot check, re-analysis kept detections found on the original audio and logged every species it removed with the reason, and new installs store recordings as FLAC.' },
    { range: '0.5.8', summary: 'A new Songbird logo across every theme, with icons that refresh after updates and a one-time re-add prompt for iPhone home-screen installs. AI Second Opinion gained measured checks per species and started catching dog barks and high-frequency buzzing. Tailscale connections to devices got steadier, the iOS app moved to ourchirp.com, and the iPhone layout stopped dragging and blurring under Liquid Glass.' },
    { range: '0.5.7', summary: 'AI Enhance (Experimental) arrived, then Rumble Removed got its own three-mode setting, AI Second Opinion was rebuilt (species grouping, measured frequency bands, insect-chirp detection, mel-scaled image, no more truncation), and Headscale remote access was hardened. The late 0.5.7 releases fixed overnight owl detection (device gate and gain defaults, night-caller confidence floors, owl recordings kept through re-analysis and auto-purge), added the XVF3800 raw-mic switch, a Coral check, Enhanced cache cleanup, night reports, and Server Connects Via for reaching devices over Tailscale.' },
    { range: '0.5.6', summary: 'Fixed several instances-only issues found along the way — bird photos never displaying once locally downloaded (profile pages, Dashboard, Life List, and more), the Seasonal Range Map 401ing on every source because image/legend requests couldn\'t carry this multi-tenant deployment\'s auth token, and Range Map tabs disappearing entirely when nothing was cached yet. Also: the AI Journal (and two other schedulers) never running for any real location, Live Detect\'s capture-gap fix and sensitivity slider, Mic Frequency Response as a full mic-comparison tool, a species-aware high-pass filter that became its own "Rumble removed" toggle, and the underlying filter bug (a bandpass, not a high-pass, ringing audibly at the band edges) that whole thread traced back to. Same Safari upload and Changelog tab fixes as chirp-server throughout.' },
    { range: '0.5.5', summary: 'The biggest arc: this location\'s own database import feature, a membership-count mismatch fix, per-instance sync fixes for Bird Buddy/Haikubox/iNaturalist and the dashboard cache warmer, then a long push to get remote access working — server-side Tailscale, a bundled self-hosted Headscale (through several build/restart/networking fixes), Global Admin diagnostics per-location, register-with-invite-code in one step, and finally replacing Cloudflare Tunnel entirely with a dedicated Caddy reverse proxy plus automatic Dynamic DNS once Cloudflare\'s own proxying turned out unable to carry Tailscale\'s protocol at all. A new Tech Docs page covers the whole setup. Also: a full parity audit against chirp-server, and a Devices-page mobile layout fix.' },
    { range: '0.5.4', summary: 'Live Detect gained the ability to save a full session as one continuous recording, admins can now choose which Dashboard cards load at all (not just show/hide), and several rounds of diagnostics tooling arrived — automatic SQLite maintenance, a VACUUM button, and a query-plan checker to verify database health directly. Also: Settings tab alignment, log/report downloads that could silently fail in some browsers, a Tutorial section for Live Detect, and assorted smaller fixes.' },
    { range: '0.5.3', summary: 'Added a Life History card (full AAB paragraphs) and expanded Tech Docs from every project README. AI Second Opinion extended to bat calls, then to multiple species per recording, then reworked to group by species instead of listing every detection. Added a Listen button to mic check (later extended to the AudioMoth, downshifted into hearing range) using a new device-side status endpoint. Dashboard got a loading skeleton, a rolling 30-day diversity window, count-up stat cards, and a time-of-day greeting; Statistics gained a 12/24-month/all-time diversity window with server-side caching. Found and fixed a bug where every skeleton loader in the app was silently static instead of animating.' },
    { range: '0.5.2', summary: 'Added a bird size-comparison ruler (heavily refined across many follow-ups — licensed silhouettes, log scale, measured-range display), a bats-exclusion toggle for Statistics, an admin-only Tech Docs page, and a Settings sidebar redesign.' },
    { range: '0.5.1', summary: 'Added the At a Glance card (habitat/food/nesting/behavior, later redesigned into four symbol cards), found and fixed why Cool Facts were missing for many species (a Cloudflare block silently disabling retries), and several smaller bird-profile and iNaturalist fixes.' },
    { range: '0.5.0', summary: 'AudioMoth crash recovery, iNaturalist comment posting for AI second opinions, and the dedicated Cloudflare Tunnel container removed, plus fixes for 11 secretly-single-hue themes, a dozen hardcoded-white-text bugs on light themes, a heatmap species selector unreachable on narrow phones, and vague diagnostic-panel error messages.' },
    { range: '0.4.0.c0 – 0.4.0.c4', summary: 'Cornell Lab of Ornithology content added to bird profiles and AI journals, a fifth AI personality slider (Curiosity), and a daily digest email rework (journal excerpt + logo).' },
    { range: '0.4.0.ba – 0.4.0.be', summary: 'The original chirp-multi (a separate multi-tenant app) reached production-readiness — safe backups, upload limits, login lockout — then was deliberately deprecated in favor of the multi-instance model above, after repeated gaps showed up versus this app\'s own more mature code.' },
    { range: '0.4.0.a – 0.4.0.az', summary: 'Bluetooth-based first-time WiFi setup, bat echolocation detection end-to-end, native iOS push notifications, and the original build-out of chirp-multi and its React frontend.' },
    { range: '0.1.x – 0.3.x', summary: 'The original foundation (the Raspberry Pi edge sensor, two-stage BirdNET pipeline, Docker server, and first web dashboard, plus hundreds of early refinements) through the introduction of AI features — the Daily Journal and multi-provider AI key management (Anthropic/OpenAI/Gemini).' },
  ],
}
