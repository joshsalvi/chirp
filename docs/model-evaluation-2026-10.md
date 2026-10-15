# Model evaluation, October 2026

BirdNET 2.4 (what Chirp runs today) against three candidates from Chirpity's model list, on public, expert-labeled audio. CPU only (2 cores).

## Test data

| Set | What | Size |
|---|---|---|
| Yard soundscapes | Sapsucker Woods, Ithaca NY (BirdSet SSW test, CC BY 4.0). Densest 10 min of each hour-long file, Feb–Jul 2017, day and night | 56 recordings, 9.3 h, 4,396 labeled calls, 51 species (41 with enough calls to score) |
| Night flight calls | CLO-43SD: warbler flight calls, 15 per species where available | 621 calls, 43 species |
| Non-bird noise | ESC-50 minus its 4 bird classes: rain, wind, engines, sirens, dogs, insects, people… | 1,840 clips of 5 s, 46 classes |
| Night audio | The 14 night/pre-dawn SSW recordings | 2.3 h |

Settings matched Chirp's server: BirdNET 2.4 sensitivity 1.5, location filter (BirdNET's species list for the site and week), applied to every model. BirdNET 2.4 used a 1.5-s hop (Chirp uses 0.5 s).

## Yard soundscapes

| | BirdNET 2.4 | BirdNET v3 (preview 3.1) | Perch v2 |
|---|---|---|---|
| Mean per-species AP (5-s cells) | 0.57 | **0.81** | 0.68 |
| Best model, species count (of 41) | 2 | **36** | 3 |
| Species found per 10-min recording at 90% precision | 36% | **74%** | 57% |
| Species found per minute at 90% precision | 29% | **72%** | 53% |
| Threshold for 90% precision | 0.60 | 0.53 | logit 10 |

Chirp today shows BirdNET 2.4 detections at ≥ 0.15. On this data, raw and before Chirp's second-opinion steps, that finds 95% of species per recording, but only 16% of what it reports matches a labeled call (149 unlabeled species reports per hour). BirdNET v3 at 0.5: 76% found, 86% correct.

Largest gains with BirdNET v3: Yellow Warbler, Blue-winged Warbler, Song Sparrow, American Goldfinch, American Robin, Great Crested Flycatcher (AP +0.35 to +0.62).

## False alarms

| | Noise clips with any bird | Noise clips with an owl | Night: unlabeled reports/hour | Night: false owl reports |
|---|---|---|---|---|
| BirdNET 2.4 at 0.15 (Chirp today) | 94.5% | 6.7% (dogs, snoring, crickets, dripping water) | 139 | 5 (Barred Owl) |
| BirdNET 2.4 at 0.63 | 17.3% | 0.1% | 1.7 (at 0.60) | 0 |
| BirdNET v3 at 0.53 | 1.6% | 0.1% | 1.7 (at 0.50) | 2 (Barred Owl; may be unlabeled real owls) |
| Perch v2 at logit 10 | 0.5% | 0% | 2.1 | 0 |
| Nighthawk (default) | 2.0% (460-clip subset) | n/a | 14.6 detections/h, 23 of 34 on labeled calls | n/a |

## Night flight calls (621 warbler calls)

| | Detected | Right family (warbler) | Right species |
|---|---|---|---|
| Nighthawk | 97% | 98% | Names a species for 26% of calls, 70% of those right; otherwise a sound group (87% right). Right species or group: 59% |
| BirdNET v3 | top guess | 47% | 15% (top 5: 34%) |
| BirdNET 2.4 | top guess | 14% | 2% |
| Perch v2 | top guess | 18% | 2% |

## Speed and size (2 CPU cores)

| | CPU time per hour of audio | Model size | License |
|---|---|---|---|
| BirdNET 2.4 | 2.6 min (1.5-s hop) | 52 MB | CC BY-NC-SA 4.0 (non-commercial) |
| BirdNET v3 | 2.0 min | 557 MB (279 MB FP16; regional files smaller) | CC BY-SA 4.0, commercial use allowed; "developer preview for research and evaluation"; no poaching or military use |
| Perch v2 | 1.8 min | 409 MB (131 MB INT8) | Apache-2.0 |
| Nighthawk | 19 min | small | CC BY-NC 4.0 (non-commercial) |

## Not tested

- FrogNET: European frogs and toads only.
- Chirpity's own night model: bundled in the Chirpity app on GitHub (not reachable from the test machine); trained in the UK.
- Raspberry Pi speed, and BirdNET v3's regional files (North America East).

## Caveats

- Ithaca, not Natick. Labels can miss faint or distant calls, which count against every model as "unlabeled reports".
- Some test audio may overlap the models' training data (Cornell recordings), most likely for Nighthawk and the flight calls.
- Chirp's own extra steps (AI second opinion, night-caller floors, owl checks) weren't applied.

## Recommendation

1. BirdNET v3 for server re-analysis: about twice the species found at the same precision, and far fewer false alarms in noise. Add as an opt-in now; make it the default when it leaves preview.
2. Nighthawk as a night-only flight-call pass, kept separate from the main species list. Non-commercial license: needs the authors' permission before a paid launch.
3. Perch v2 for embeddings (similar-call search, training on confirmed detections) and as a noise check. Not the main identifier.
4. Revisit the 0.15 display floor with sensitivity 1.5 for BirdNET 2.4 while it stays in use.
5. Repeat on a week of the Chirp station's own recordings, using detections already confirmed or rejected in the app.
