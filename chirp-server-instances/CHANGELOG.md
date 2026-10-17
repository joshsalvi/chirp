## 1.4.3 (chirp-device) — 2026-10-17 — BUGFIX — Hum filter stays on

- Once on, the hum filter turns off only after two checks in a row find the hum under 5 dB (one quiet check had let it off for 5 minutes at a time).
- Each check logs how far the hum stands above its neighbours, to compare wiring changes.

