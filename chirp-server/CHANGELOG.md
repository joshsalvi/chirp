## 0.5.14.g — 2026-10-17 — BUGFIX — Audio check hears short calls

- AI Second Opinion's audio check now measures short calls (chips, "pik"s, 20–50 ms) too; faint Downy Woodpecker and chickadee calls at 6–8 kHz read as "nothing above the background" before.
- The AI gets those measured frequencies, so it no longer guesses them from the image.

