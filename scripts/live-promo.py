#!/usr/bin/env python3
"""Chirp Live App Store images: each simulator screenshot (1320×2868) under a
caption, on the app's dark green.

    python3 scripts/live-promo.py RAW_DIR OUT_DIR

RAW_DIR has welcome/listen/station/summary/sessions.png from the simulator
(-ChirpShots <scene>); OUT_DIR gets 1-listen.png … 5-welcome.png.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1320, 2868
BG = (10, 22, 12)
INK = (245, 239, 230)
AMBER = (251, 191, 36)
SHOTS = [
    ("listen", "1-listen.png", "See who's\nsinging", "Names birds as they sing, on your iPhone"),
    ("summary", "2-summary.png", "Every walk,\nsummed up", "Species, calls and the best clip of each bird"),
    ("sessions", "3-sessions.png", "Keeps every\nsession", "With the sound, the place and GPS"),
    ("station", "4-station.png", "Listen to\nyour yard", "Signed in to a Chirp site, hear your stations"),
    ("welcome", "5-welcome.png", "No account.\nNo signal needed.", "Over 6,000 species, all on your iPhone"),
]

FONT_DIRS = ["/usr/share/fonts/opentype/inter", "/System/Library/Fonts", "/Library/Fonts"]


def font(names, size):
    for d in FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def main(raw, out):
    os.makedirs(out, exist_ok=True)
    title_f = font(["InterDisplay-Bold.otf", "SFNSDisplay-Bold.otf", "Helvetica.ttc"], 118)
    sub_f = font(["Inter-Medium.otf", "SFNSText.ttf", "Helvetica.ttc"], 50)
    for scene, name, title, sub in SHOTS:
        shot = Image.open(os.path.join(raw, scene + ".png")).convert("RGB")
        c = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(c)
        y = 170
        for line in title.split("\n"):
            w = d.textlength(line, font=title_f)
            d.text(((W - w) / 2, y), line, font=title_f, fill=INK)
            y += 138
        w = d.textlength(sub, font=sub_f)
        d.text(((W - w) / 2, y + 26), sub, font=sub_f, fill=AMBER)
        # The screen, scaled into the space below, rounded like the phone.
        top = y + 150
        sh = H - top - 110                      # fit below the caption
        sw = int(shot.width * sh / shot.height)
        shot = shot.resize((sw, sh), Image.LANCZOS)
        mask = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, sw - 1, sh - 1), radius=96, fill=255)
        x = (W - sw) // 2
        d.rounded_rectangle((x - 6, top - 6, x + sw + 5, top + sh + 5), radius=102, fill=(40, 58, 44))
        c.paste(shot, (x, top), mask)
        c.save(os.path.join(out, name), optimize=True)
        print(name)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
