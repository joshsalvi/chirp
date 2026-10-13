# Bat Wobble Interference — Investigation Log

A persistent ~25.8kHz tone with ~28.8Hz modulation, overlapping bat
echolocation frequencies, in AudioMoth recordings. This consolidates
everything learned across sessions into one place, including a real,
decisive finding that overturns an earlier recommendation — documented
here plainly rather than left as a stale, now-wrong suggestion sitting in
an old changelog entry.

## The decisive finding (real, controlled, from this deployment)

**Physically separating the Raspberry Pi and each microphone — Pi on its
own chair, each mic on its own chair, three separate physical
locations — made the wobble disappear entirely.**

**Increasing the AudioMoth's sample rate to 384kHz did NOT fix it.**

This is the most important data point in the whole investigation, and it
changes the diagnosis:

- It rules out AudioMoth self-noise / anti-aliasing artifacts as the
  cause **for this specific deployment** — a real, physically-grounded
  theory earlier in this investigation (see "Ruled out" below), but the
  384kHz test was the direct way to confirm or deny it, and it came back
  negative. Self-noise intrinsic to the AudioMoth itself wouldn't
  disappear just because the device moved a few feet away from the Pi.
- It points squarely at **near-field EMI/RF coupling from the Raspberry
  Pi itself** — its switching power supply, SoC, wifi radio, or USB bus
  all radiate some electrical noise in normal operation, and an
  unshielded microphone (or its cable) sitting close to that source can
  pick it up as an audible-range artifact, especially if the
  interference has any low-frequency amplitude-modulation component. The
  ~28.8Hz modulation rate observed from the start is actually consistent
  with this: that kind of slow modulation riding on a higher-frequency
  tone is a common signature of switching-regulator ripple or a
  periodic digital process (e.g. a display refresh, a polling loop),
  not of a microphone's own intrinsic self-noise.

## What this means practically

**The fix is physical distance between the Pi and the microphone(s), not
a sample-rate or firmware change.** Confirmed directly, not theorized.

This has an immediate, real consequence for `HARDWARE_MIC_UPGRADE.md`
(the combined bird+bat weatherproof enclosure guide written earlier this
session) — that guide's design put the bird mic, the AudioMoth, and the
Pi all in **one shared enclosure**, which is now known to be close to
exactly the wrong arrangement for this specific interference. That guide
has been revised (see its own changelog note) to physically separate the
microphone capsules from the Pi/electronics compartment via a real cable
run, rather than co-locating everything for convenience.

## What was tried and ruled out, or not yet confirmed

- **AudioMoth self-noise / anti-aliasing artifacts at lower sample
  rates** — a real theory from an earlier session, based on genuine
  evidence: AudioMoth's own official support forum has a report of
  nearly identical symptoms, and BTO (British Trust for Ornithology)'s
  own Acoustic Pipeline documentation explicitly warns about AudioMoth
  self-noise and recommends 384kHz specifically to avoid it. That
  evidence wasn't wrong in general — self-noise is a real, documented
  AudioMoth phenomenon — but the 384kHz test on this specific unit, in
  this specific deployment, came back negative, and the chair-separation
  test point squarely at an external, proximity-dependent cause instead.
  Worth remembering both things can be true in general (self-noise is
  real for some AudioMoth units/deployments) while this deployment's
  actual cause is something else.
- **Fan/PWM noise from the Argon ONE v5 case** — an earlier A/B test
  (stopping `argononed`) was inconclusive, possibly because stopping the
  daemon doesn't guarantee the fan's PWM signal actually stopped at the
  hardware level. Given the new finding, this remains a plausible
  *contributor* specifically because a case fan is physically part of
  the same enclosure as the Pi — worth revisiting with a real, confirmed
  physical fan stop (unplug it, not just stop the daemon) now that
  proximity is confirmed to matter.
- **USB bus / shared power rail noise** — not yet isolated as its own
  variable. Given the chair-separation test also increased *cable*
  length between the Pi and each mic, it's not yet confirmed whether the
  fix is specifically "further from the Pi's own radiated EMI" versus
  "longer USB/audio cable run changes cable-borne noise coupling" —
  these point to related but distinguishable causes and would call for
  different follow-up (physical shielding/positioning vs. cable
  quality/ferrites). Worth a follow-up test: same distance, but a
  shorter high-quality shielded cable instead of the longer one likely
  used for the chair-separation test, to isolate which factor is doing
  the actual work.

## Recommended next steps

1. **Confirm the fan variable properly** — physically unplug the Argon
   ONE's fan (not just stop the daemon) with the Pi and mics back in
   their normal close arrangement, to see whether that alone resolves it
   without needing physical separation at all. If it does, the fan was
   the primary contributor, and proximity to the Pi's other electronics
   (SoC, wifi, power supply) wasn't actually the driver.
2. **If the fan isn't the whole story**, try shielded cable + ferrite
   chokes at both ends of the mic cable, with the Pi and mics back in
   their normal close positions — tests whether cable shielding alone
   (without physical distance) is sufficient, which would be a much more
   practical permanent fix than requiring several feet of separation.
3. **Keep 384kHz or not** — since it didn't fix the actual problem, this
   comes down to whether the higher sample rate has other independent
   benefits (per BTO's own general guidance) worth the extra storage/
   processing cost on its own merits, not as an interference fix.
