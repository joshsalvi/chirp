#!/usr/bin/env python3
"""Chirp Lite App Store images: each simulator screenshot (1320x2868) under a
caption, on Lite's sky-to-meadow colors.

    python3 scripts/lite-promo.py RAW_DIR OUT_DIR

RAW_DIR is from ./build-lite.sh --shots (0-signin.png ... 5-bird.png).
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1320, 2868
TOP, BOTTOM = (214, 238, 250), (226, 244, 224)
INK = (20, 61, 38)
SUB = (52, 96, 70)
PILL, PILL_INK = (242, 194, 48), (40, 34, 8)
SHOTS = [
    ("1-today", "1-today.png", "Your yard, today", "The latest visitor and its song, one tap away", "Try the demo · no account needed"),
    ("2-birds", "2-birds.png", "Every bird, by photo", "Your yard's collection, sorted your way", None),
    ("5-bird", "3-bird.png", "Meet each bird", "Its song, size, season and a fun fact", None),
    ("4-guide", "4-guide.png", "Who to listen for", "Birds near you this month, and which have visited", None),
    ("3-listen", "5-listen.png", "Hear every visit", "Recordings as cards: tap to play", None),
    ("0-signin", "6-demo.png", "Look around first", "Try the demo yard, no account needed", None),
]
FONT_DIRS = ["/usr/share/fonts/opentype/inter", "/System/Library/Fonts", "/Library/Fonts"]


def font(names, size):
    for d in FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def background():
    c = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(c)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    return c


def main(raw, out):
    os.makedirs(out, exist_ok=True)
    title_f = font(["Inter-Black.otf", "Helvetica.ttc"], 116)
    sub_f = font(["Inter-SemiBold.otf", "Inter-Medium.otf", "Helvetica.ttc"], 50)
    pill_f = font(["Inter-Bold.otf", "Helvetica.ttc"], 44)
    for scene, name, title, sub, pill in SHOTS:
        shot = Image.open(os.path.join(raw, scene + ".png")).convert("RGB")
        c = background()
        d = ImageDraw.Draw(c)
        size = 116
        while d.textlength(title, font=title_f) > W - 120 and size > 80:
            size -= 4
            title_f = font(["Inter-Black.otf", "Helvetica.ttc"], size)
        y = 170
        d.text(((W - d.textlength(title, font=title_f)) / 2, y), title, font=title_f, fill=INK)
        y += 150
        d.text(((W - d.textlength(sub, font=sub_f)) / 2, y), sub, font=sub_f, fill=SUB)
        y += 80
        if pill:
            pw = d.textlength(pill, font=pill_f) + 88
            d.rounded_rectangle(((W - pw) / 2, y + 10, (W + pw) / 2, y + 96), radius=43, fill=PILL)
            d.text(((W - d.textlength(pill, font=pill_f)) / 2, y + 28), pill, font=pill_f, fill=PILL_INK)
            y += 120
        top = y + 50
        sh = H - top - 110
        sw = int(shot.width * sh / shot.height)
        shot = shot.resize((sw, sh), Image.LANCZOS)
        mask = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, sw - 1, sh - 1), radius=96, fill=255)
        x = (W - sw) // 2
        d.rounded_rectangle((x - 8, top - 8, x + sw + 7, top + sh + 7), radius=104, fill=(255, 255, 255))
        d.rounded_rectangle((x - 9, top - 9, x + sw + 8, top + sh + 8), radius=105, outline=(190, 212, 196), width=2)
        c.paste(shot, (x, top), mask)
        c.save(os.path.join(out, name), optimize=True)
        print(name)
        title_f = font(["Inter-Black.otf", "Helvetica.ttc"], 116)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
