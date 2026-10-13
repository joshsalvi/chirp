# Bat species classification models

## Files

- BirdNET v2.4 base model — not shipped here. `bat_species_classifier.py`
  uses birdnetlib's bundled `BirdNET_GLOBAL_6K_V2.4_Model_FP32.tflite`; a
  `BirdNET_GLOBAL_6K_V2.4_Model_FP16.tflite` dropped into this folder takes
  priority. It is the standard BirdNET v2.4 base
  model (same architecture chirp-device uses for bird detection), used here
  in **embeddings mode** — not for its own 6522-species bird output, but to
  extract a 1024-dimensional feature vector from a 256kHz audio window. This
  is the exact "transfer learning on top of BirdNET" approach documented by
  BattyBirdNET-Analyzer: https://github.com/rdz-oss/BattyBirdNET-Analyzer

- `BattyBirdNET-USA-EAST-256kHz.tflite` — a small (~95KB) linear classifier
  trained on top of those embeddings, using the NABat (North American Bat
  Monitoring Program) training dataset, region-restricted to eastern North
  American species (relevant to Massachusetts). Source:
  https://github.com/rdz-oss/BattyBirdNET-Analyzer/tree/main/checkpoints/bats/v1.0

- `BattyBirdNET-USA-EAST-256kHz_Labels.txt` — the 23 output classes: 16 real
  bat species plus 7 non-species rejection classes (cricket, background,
  noise, silence, etc.) the classifier was explicitly trained to distinguish
  from real echolocation calls.

## License — IMPORTANT

The BattyBirdNET-USA-EAST classifier (and its labels file) is licensed
**CC BY-NC-SA 4.0 — non-commercial only** (see `LICENSE-BattyBirdNET-classifier.txt`).
Fine for personal/hobby use; flagged explicitly here since Chirp has a
pending patent application, in case that context ever matters for how this
specific bundled model is used or distributed.

The base BirdNET model file is unrelated to this license and already
bundled elsewhere in this project under its own terms.

## Real-world accuracy caveats (from the classifier's own maintainer)

The maintainer's own testing found roughly 1-in-20 misclassifications across
the full training set, likely higher in real-world noisy conditions — and
peer-reviewed literature on automated bat classifiers generally (Solick et
al. 2024, PLOS ONE) found low positive-predictive-value and sensitivity
particularly for *Myotis* species, recommending expert review before using
automated results for any regulatory or conservation decision. This is
reflected in how the classifier module surfaces results: raw per-class
confidences, including the explicit noise/cricket/silence classes, not just
a single asserted "best guess" species.

## Not yet wired into the live detection pipeline

This is currently a standalone, tested module — see
`app/services/bat_species_classifier.py`'s own module docstring, and
`tests`/functional test scripts, for what's actually been verified.
