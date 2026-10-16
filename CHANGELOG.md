## 1.4.2 (chirp-device) — 2026-10-16 — FEATURE — Mains hum filter

- Notches mains hum (60 or 50 Hz and harmonics to 1 kHz, 3 Hz wide) on each mic before detection, recordings and night audio.
- audio.hum_filter: auto (default; on only when hum stands 10 dB out, rechecked every 5 minutes), 60, 50 or off.

