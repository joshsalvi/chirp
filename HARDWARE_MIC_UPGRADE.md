# Chirp Listening Station — Combined Bird + Bat, Weatherproof, AC-Powered
### Rated for year-round outdoor use, Maine to Florida

> **Revised after real interference evidence.** A controlled test on an
> actual deployment (Pi and each microphone physically separated onto
> separate chairs) made a persistent ~25.8kHz interference tone disappear
> entirely — and raising the sample rate to 384kHz, which an earlier
> version of this investigation had recommended, did **not** fix it. That
> points at near-field EMI from the Pi itself, not microphone self-noise.
> Full details in `BAT_WOBBLE_INVESTIGATION.md`. This means the original
> version of this guide — which put the bird mic, AudioMoth, and Pi all
> in **one shared enclosure** — was recommending close to the wrong
> arrangement for this specific interference. **Revised below to
> physically separate the microphones from the Pi via a real cable run,
> in two enclosures instead of one.** If you already built the
> single-enclosure version and it's had this same wobble, this is
> almost certainly why, and worth fixing before anything else.

A permanent, wall/pole-mounted outdoor listening station: a genuinely low-noise
dedicated bird microphone *and* an ultrasonic bat microphone, wired to
permanent AC power, physically separated from the Pi's own electronics to
avoid the near-field interference confirmed above. This is a step up from
the original ChirpPi build toward two purpose-built, genuinely high-quality
microphones in one clean, professional-looking installation — verified
against real component specs for the full US East Coast climate range, not
just assumed to work.

**Difficulty: moderate-to-involved.** Real soldering (a handful of joints,
not surface-mount work), real electrical work (mains AC to low-voltage DC),
and — new in this revision — a genuine cable run between two enclosures
rather than one simple box. See the safety note in Part 5 before touching
anything with a plug on it.

**Total cost: roughly $210-250** (a small increase from the original
single-enclosure estimate — a second, smaller enclosure and a longer
shielded cable run cost a little more than one box, and that's a real,
worthwhile trade for actually solving the interference rather than
building a nicer-looking version of the same problem).

---

## Why this range needed real verification, not assumption

Maine winters and Florida summers are genuinely different engineering
problems, and it would have been dishonest to just repeat generic "weatherproof"
advice without checking real component specs against both ends. Two findings
actually changed the design:

- **The Primo EM272 capsule is rated -20°C to +60°C (-4°F to +140°F)** —
  confirmed from Primo's own datasheet. Fine for Maine cold. Tight for Florida
  summer, but not because of ambient air temperature (Florida air rarely tops
  100°F) — the real risk is **a sealed, dark enclosure baking in direct sun**,
  which can run 40-60°F above ambient internally. A black box in Florida sun
  can plausibly hit 140°F+ inside even at 95°F ambient. That's a real,
  physically-grounded failure mode.
- **The Raspberry Pi's real risk is the same direction** — its recommended
  safe ambient ceiling is ~50°C (122°F), and it generates its own heat on top
  of that. In Maine cold, this actually helps: Chirp listens continuously, so
  the Pi is rarely fully idle and self-heats almost constantly — real-world
  reports (including Raspberry Pi's own forum) confirm boards run fine well
  below freezing despite no official cold-rated spec. **Heat, not cold, is
  the harder problem for this specific build.**

This means the single biggest design lever for a Maine-to-Florida build isn't
a different microphone — **it's the enclosure's color and thermal path.**

## Design decisions this drove

1. **Enclosure: light color, not black.** The single biggest lever on internal
   peak temperature. A light/reflective surface can run 20-30°F+ cooler
   internally than black in direct sun — zero added cost or complexity.
2. **Mount it shaded** — under an eave, north-facing (northern hemisphere), or
   under natural tree cover. Avoiding all-day direct southern sun beats
   engineering around it.
3. **Thermal-bridge the Pi to the aluminum housing itself** via a small
   thermal pad between the SoC and the aluminum wall — turns the whole
   enclosure into a heatsink. A second real reason (beyond looks and
   cold-brittleness below) to pick aluminum over plastic for this climate.
4. **Aluminum over ABS plastic for the cold end too.** ABS becomes measurably
   brittle below roughly -20°C to -40°C depending on formulation — real Maine
   cold snaps can reach that. Aluminum has no such failure mode.
5. **Condensation control — a real, documented risk.** Open Acoustic Devices
   (AudioMoth's own team) explicitly warns that condensation inside a sealed
   housing, not the electronics failing from cold, is the primary real-world
   cold-weather failure mode. A sealed box cycling through daily/seasonal
   swings pulls moist air in and out at every seam, and it condenses on the
   coldest surface inside — usually the electronics. Fix: silica gel
   desiccant packs (cheap, re-dry every few months) plus acoustic vents that
   double as passive pressure-equalization points.
6. **Gaskets/seals: silicone or EPDM, not generic PVC.** Silicone/EPDM stay
   flexible to roughly -40°F to -60°F; cheap PVC can stiffen and lose its
   seal in real Maine cold, right when it matters most.

---

## Why two separate microphones, not one

Bird calls (~1-10kHz) and bat echolocation (~15-120kHz) have completely
different requirements — one mic covering both well isn't really a thing.
Two purpose-built mics sharing one enclosure and one Pi is the actually-good
version of "one listening station."

---

## Part 1 — The bird microphone

**Primo EM272** electret condenser capsule — not the older EM172. The EM272
has real, improved RF-interference immunity over the EM172, which matters
specifically here: Chirp's own AudioMoth has an ongoing, partially-unresolved
interference investigation, and the EM172's documented weakness is
specifically wifi/RF susceptibility. Building a second RF-sensitive mic next
to a Pi's wifi radio and a bat detector with its own real interference
history invites a second, unrelated noise problem for no reason.

**Get the 3.5mm plug-in-power version, not XLR.** Not a minor preference —
XLR versions need real 48V phantom power; feeding that into a capsule built
for a few volts of bias can destroy it. This has happened to people doing
exactly this kind of build.

**Two ways to get one:**
- **No soldering:** [FEL Communications / MicBooster "Clippy" EM272](https://www.micbooster.com/) — pre-wired to a 3.5mm TRS plug, ~$45-58.
- **Solder it yourself (cheaper):** bare **Primo EM272Z1** capsule (~$25-33 from [MicBooster](https://micbooster.com/microphone-capsules/199-primo-em272.html) — the **Z1** suffix specifically means the 2-wire plug-in-power version, not the 3-wire EM273) + a 3.5mm TRS plug + shielded 2-conductor cable (Mogami 2549, from [Redco Audio](https://www.redco.com/)).

**Real precedent for this exact build:** [BirdNET-Pi GitHub Discussion #39](https://github.com/mcguirepr89/BirdNET-Pi/discussions/39) — someone built almost exactly this (EM272 pair + cheap USB audio interface + Pi running BirdNET), described as producing genuinely high-quality recordings. [WILDLABS forum thread](https://wildlabs.net/en/discussion/microphone-bird-monitoring-raspberry-pi) independently confirms a Sound Blaster Play! 3 provides correct bias voltage for this capsule family.

### USB audio interface (mandatory, not optional)

**The Raspberry Pi's own audio jack cannot record at all** — confirmed
directly from real Pi/BirdNET-Pi user reports; output-only, no mic input
circuitry, no bias voltage. You need one of:
- **Creative Sound Blaster Play! 3** (~$30) — most commonly recommended for this capsule family.
- **UGREEN USB Audio Adapter** (~$12-15) — cheaper, confirmed working in a real documented build.

### Building the mic (solder-it-yourself route)

| Part | Source | Cost |
|---|---|---|
| Primo EM272Z1 capsule | MicBooster | $25-33 |
| 3.5mm TRS male plug | Any electronics supplier | $3-5 |
| Shielded 2-conductor cable, ~6ft (Mogami 2549) | Redco Audio | $8-15 |
| Heat-shrink tubing | Any electronics kit | ~$2 |

**Steps:**
1. Check the capsule's datasheet pinout (linked from MicBooster's product page) — signal+bias on one pad, ground on the other.
2. Strip ~1cm of outer jacket from the cable, exposing shield braid and inner conductor.
3. Tin both the capsule's contacts and the cable's conductors before joining — faster, cleaner joint, less heat exposure.
4. Solder center conductor to signal/bias pad, shield braid to ground pad. Keep the iron on each joint as briefly as possible — electret capsules are heat-sensitive. **Use a low-power (~18W), temperature-controlled iron** if you have one — MicBooster's own soldering guide specifically recommends this.
5. Slide heat-shrink tubing onto the cable *before* soldering (easy to forget), shrink once cooled.
6. Wire the other end to the 3.5mm TRS plug: tip = signal, ring = bias (from the sound card), sleeve = ground.
7. Test before final assembly — record a few seconds with `arecord`, listen for a clean signal. Faint hiss is normal; hum or crackle means a bad joint.

---

## Part 2 — The bat (ultrasonic) microphone

**Keep using AudioMoth**, run continuously via **USB Microphone mode** rather
than battery — no battery to run down on a permanent AC installation, and
it's already what `bat_detector.py` knows how to detect and use at 192kHz+.

**Real, climate-relevant note:** Open Acoustic Devices' own team explicitly
warns that condensation inside a sealed housing — not electronics failing
from cold — is the real risk for cold-weather deployments. This is exactly
why the condensation-control steps above (desiccant, pressure-equalizing
vents) matter for this build, more than any specific temperature rating.

If you don't already have one: [AudioMoth from Open Acoustic Devices](https://www.openacousticdevices.info/audiomoth) (~$70-90). No soldering — connects via its own USB port.

---

## Part 3 — Weatherproofing the microphones

Goal: water out, sound in — genuinely both.

### Tier A — Budget, DIY, proven
1. Open-cell reticulated foam disc (a lav-mic windscreen, ~$5-8/pack) over the capsule.
2. Fine stainless steel mesh over that (a cut section of kitchen sink strainer works).
3. Nylon stocking material stretched over both, sealed at the edges.
4. Mount the capsule pointing downward at a slight angle inside a small overhanging lip — keeps rain from hitting the vent directly.

Cost: under $15 total.

### Tier B — Premium (recommended for this climate range)
**GORE Acoustic Vents** — real, purpose-built ePTFE membranes, genuinely
IP67/68-rated, under 1dB acoustic loss. Available via
[Mouser Electronics](https://www.mouser.com/manufacturer/gore/) (search "Gore
acoustic vent," GAW200-series) in small hobbyist quantities. ~$5-15. These
also double as pressure-equalization points.

**For this climate range specifically, Tier B is worth the extra cost.**
Given real freeze-thaw cycling in Maine and real heat-cycling in Florida, the
better pressure-equalization behavior does real work reducing how much the
enclosure "breathes" moisture through its seams across a genuinely wide swing.

---

## Part 4 — Two enclosures, not one: the mic head and the electronics box

This is the real structural change from the original single-enclosure
design. **The bird mic capsule and the AudioMoth live in a small
enclosure of their own — no Pi, no USB sound card's own circuitry, no
switching power supply anywhere near them — connected by a real cable run
to a separate enclosure holding the Pi and its electronics.**

### The mic head (small, mic capsules only)

A small weatherproof box — the [TICONN IP67 ABS Waterproof Junction Box, 8.7"×6.7"×4.3"](https://www.amazon.com/TICONN-Waterproof-Electrical-Junction-Enclosure/dp/B0B87V7QTH)
(~$25-30) from the original design is actually the right size for this
now — it only needs to hold two small mic capsules and their vent/foam
assemblies, not a Pi and a sound card too. (Its plastic-in-cold caveat
from earlier still applies if it's somewhere that sees real hard freezes
unshaded — consider a small light-colored aluminum box instead if that's
a concern for your specific mounting spot.)

- Mount the EM272 bird mic capsule and the AudioMoth's own capsule inside, each behind its own acoustic vent (Part 3, Tier A or B).
- The USB sound card (for the bird mic) — **mount it in this box too, not the Pi's box.** It's a much smaller, simpler circuit than a full Raspberry Pi (no SoC, no wifi radio, no switching regulator of its own beyond a small linear one), and the whole point is keeping the actual radiating sources away from the mics — but if the wobble investigation's follow-up testing (see `BAT_WOBBLE_INVESTIGATION.md`) finds the sound card itself contributes too, moving it to the Pi's box instead is a reasonable fallback.
- One cable exits this box: a USB cable (carrying both the sound card's audio and the AudioMoth's own USB connection — use a small **powered/active USB hub** inside this box if you'd rather run one cable back rather than two, or just run two separate USB cables if that's simpler for your specific layout).

### The electronics box (Pi, AC power)

**[GledeYeTec 14.5" Heavy-Duty Aluminum Outdoor Camera Housing](https://www.amazon.com/dp/B0D49FF6GB)**
(~$45-55), white or light gray per the thermal reasoning above — now
holding just the Pi and its power connections, with more free room than
the original design needed for this alone.

### The cable run between them

**How far apart:** `BAT_WOBBLE_INVESTIGATION.md` hasn't pinned down the
exact minimum distance yet (the chair-separation test that confirmed this
worked was several feet, not a precisely measured minimum) — start with
**at least 6-10 feet** of real separation as a reasonable, evidence-based
starting point, and treat closer-but-still-working as a possible future
optimization once more testing narrows it down, not an assumption to
build around now.

**Cable:** a genuine **shielded, active USB extension cable** rated for
outdoor/direct-burial use if the run is longer than about 5 meters
(16 feet) — passive USB runs beyond that length risk signal degradation
regardless of the interference question. For shorter runs within that
limit, a good shielded USB extension (not a bargain unshielded one) is
sufficient. Route it through weatherproof cable glands on both
enclosures, with a drip loop at each end per Part 5's own guidance below.

### Mounting the mics through the mic-head enclosure wall
1. Mark two positions — one for the bird mic, one where the AudioMoth's own capsule has a clear path.
2. Drill pilot holes, step up to the correct vent/foam size with a step drill bit (prevents cracking, especially on aluminum).
3. Tier A: hot-glue/silicone-seal the mesh to the inside wall over the hole, foam disc on top, nylon layer stretched over the outside with a clear silicone bead around its edge.
4. Tier B: peel-and-stick per the vent's own instructions.
5. Position each capsule close but not touching its vent/foam (a few mm air gap is normal), mounted to a small internal bracket or standoff.

---

## Part 5 — AC power, done safely

**Real safety note:** if you're not comfortable with mains AC wiring, this is
the part worth having an electrician check, or do outright. Getting it wrong
risks fire or shock in a way a bad solder joint doesn't.

1. **Outdoor-rated AC-to-DC power supply** (5V, 4A minimum, IP65+ rated — the
   kind sold for outdoor LED strip lighting works well, ~$12-18), mounted in
   its own small separate weatherproof box, *not* inside the main enclosure.
2. Only the **low-voltage DC output** enters the main enclosure, through a proper cable gland.
3. That DC line feeds the Pi's power input directly — no mains voltage ever present with the mics and electronics.
4. Plug the outdoor supply into a genuinely **outdoor-rated, GFCI-protected** outlet.
5. Leave a **drip loop** in any outdoor cable run before it enters a gland.
6. **For this temperature range specifically:** confirm the power supply's
   own rated range covers both ends — most outdoor LED-strip supplies run
   roughly -20°C to +60°C (-4°F to +140°F), matching the EM272's own range
   closely, but check the specific unit's datasheet before buying since
   cheap units vary.

---

## Part 6 — Final assembly

1. **Mic head box:** mount the bird mic capsule and AudioMoth behind their vents, and the USB sound card (or USB hub, if combining both mics onto one cable run) on standoffs. Drop in 1-2 silica gel packs here too — it's a sealed box like the other one.
2. **Electronics box:** mount the Pi on standoffs, thermal pad connecting it to the aluminum wall. Drop in 2-3 silica gel packs.
3. Run the USB extension cable between the two boxes, through cable glands on both, with a drip loop at each end.
4. Route the AC-derived DC power line into the electronics box the same way (Part 5), also with its own drip loop.
5. Connect everything inside the electronics box: USB extension (from the mic head) → Pi, DC power → Pi.
6. Seal both enclosures per their own instructions.
7. Confirm both audio devices from the Pi: `arecord -l` should show the USB sound card; `chirp-device` already knows how to find the AudioMoth — both now reachable over the extension cable exactly as if they were plugged in directly.
8. **Test for at least a week somewhere accessible** before final permanent mounting — check for condensation in both boxes on a cold morning, signal degradation on a hot afternoon, and **specifically re-check for the wobble tone now that the mics are physically separated from the Pi** — the actual thing this revision exists to fix. If it's still present at the distance you used, that's real, valuable data for `BAT_WOBBLE_INVESTIGATION.md` — worth reporting back rather than assuming the guide got it right.

---

## Full parts list

| Part | Cost |
|---|---|
| Primo EM272Z1 capsule | $25-33 (or $45-58 pre-made) |
| 3.5mm TRS plug + shielded cable + heat-shrink | $13-22 |
| USB audio interface | $12-30 |
| AudioMoth (if needed) | $70-90 |
| Acoustic weatherproofing (Tier B recommended) | $5-15 |
| Aluminum enclosure (electronics box), light color | $45-55 |
| Small mic-head enclosure (TICONN or similar) | $25-30 |
| Shielded active USB extension cable, 10ft+ | $15-25 |
| Small USB hub (if combining both mics onto one cable run) | $8-12 |
| Outdoor AC-DC power supply, 5V 4A, IP65+ | $12-18 |
| Thermal pad, silica gel packs (both boxes), cable glands, sealant | ~$20 |

**Total: ~$210-250** (excluding Pi and AudioMoth if you already have them) —
a modest increase from the original single-enclosure estimate, for an
enclosure arrangement that's actually confirmed to avoid the interference
this whole build exists to get right.
