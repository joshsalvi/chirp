# Owl evaluation set

Labeled clips for tuning and regression-testing the server pass's owl rules
(`app/services/birdnet_pass.py`).

## Clips

`manifest.json` lists 49 Xeno-canto recordings. The audio isn't in the repo
because most clips are CC BY-NC-SA; `fetch.py` downloads them.

| Group | Clips |
|---|---|
| Barred Owl | 8 |
| Great Horned Owl | 8 |
| Eastern Screech-Owl | 8 |
| Northern Saw-whet Owl | 8 |
| Owl-free night sounds | 17: Mourning Dove, Rock Pigeon, Common True Katydid, Snowy Tree Cricket, Spring Peeper, Gray Treefrog, American Bullfrog, Eastern Whip-poor-will |

Each owl clip is also mixed with two noise beds (a katydid chorus and tree
crickets) at 1.5x the clip's RMS. That gives 96 owl cases and 18 owl-free
cases. Scoring uses Natick's location filter on 15 March.

## Running it

```bash
python3 scripts/owl-eval/fetch.py                    # ~200 MB into ~/.cache/chirp-owl-eval
python3 scripts/owl-eval/owl_eval.py --show          # current settings, one line per clip
python3 scripts/owl-eval/owl_eval.py --grid          # search; results in grid_results.json
python3 scripts/owl-eval/owl_eval.py --extra-neg DIR # add more owl-free WAVs
python3 scripts/owl-eval/owl_eval.py --extra-pos DIR # add owl WAVs named "<Owl species>__<id>.wav"
python3 scripts/owl-eval/owl_eval.py --grid --focus  # search the score rules only (hoot detector as is)
python3 scripts/owl-eval/owl_eval.py --pitches       # hoot pitches heard per owl
```

The first run scores every clip once: BirdNET on the full band and on the
200–2000 Hz copy for every window, plus the hoot detector's frame data. It
caches those as `.npz` files, and later runs replay the rules in seconds.

## Scoring

- **Hit:** the owl clip's species is reported.
- **Wrong:** another owl species is reported on an owl clip.
- **False alarm:** any owl is reported on an owl-free clip.

The grid ranks settings by hits − wrong − 2 × false alarms.

## Field recordings (0.5.12.m)

The clip set has no daytime audio, and in October Natick's server pass was
reporting Great Horned, Long-eared and Saw-whet Owls on midday recordings.
Two field sets from Natick were added for 0.5.12.m (not in the repo; they're
the site's own recordings):

- 16 recordings with a server Barred Owl at 0.8 or more (`--extra-pos`).
- 231 recordings made 10 AM to 4 PM with a songbird at 0.5 or more and no
  Barred Owl (`--extra-neg`). Any owl reported on one counts as a false alarm.

On those, the band-limited copy scored pigeon coos, engines and voices as
owls at 0.35-0.62 while the full band said 0.02-0.34. `HOOT_FULL_MIN` (the
full-band score a hooted owl needs) was added to the grid:

| Settings | Clip set hits / wrong / false alarms | Field Barred Owls | Midday false owls |
|---|---|---|---|
| 0.5.10.a (strong 0.40, no full-band check) | 81 / 8 / 1 | 16 of 16 | 20 of 231 |
| 0.5.12.m (strong 0.45, `HOOT_FULL_MIN` 0.30) | 81 / 7 / 0 | 16 of 16 | 1 of 231 |

`HOOT_FULL_MIN` 0.45 removes the last midday owl but loses 2 clip-set owls.

## Results (0.5.10.a)

| Settings | Hits (of 96) | Wrong owls | False alarms (of 18) |
|---|---|---|---|
| 0.5.9.h (owl floor 0.10, every owl species kept) | 86 | 80 | 7 |
| 0.5.10.a | 81 | 8 | 1 |

What changed:

- Owls need 0.20.
- A second owl species needs 0.70 by itself.
- A strong full-band owl needs 0.40.
- A hoot must stand 5 dB above the audio just before or after it.

The second-owl rule gave the largest single improvement: wrong owls fell from 27 to 8 at the same floor. The hoot detector's other thresholds made almost no difference.

Still wrong:

- A Gray Treefrog trill scores as Burrowing Owl. Burrowing Owl's location score in Natick is 0.0021, above Long-eared Owl's 0.0018, so the location filter can't separate them.
- Some Eastern Screech-Owl trills score under 0.20. The near-miss log records these, so a per-species threshold can bring them back.

`tests/test_birdnet_pass.py::test_owl_regression` fails if hits drop below
80, wrong owls exceed 10, or false alarms exceed 2 (the `expected` block in
`manifest.json`).
