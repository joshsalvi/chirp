"""
Look of Chirp's emails: a light card (which mail apps' dark modes invert
cleanly, where a dark design came out grey and washed out in Gmail and
Outlook) with the app's dark header band, the current logo and real bird
photos, both attached inline (cid:) so they show without loading remote
images and without a public photo URL.

    imgs = InlineImages()
    src = imgs.add_photo("/data/media/robin.jpg")      # "cid:..."
    html = wrap_html(..., body)
    _send(..., html, inline_images=imgs.parts)

The logo is attached automatically by email_service._send whenever the
HTML references LOGO_CID.
"""
import base64
import hashlib
import io
import os
from pathlib import Path
from typing import Optional

# Palette (contrast against white checked: TEXT 10.9:1, MUTED 5.4:1,
# ACCENT_TEXT 5.2:1).
BG = "#eef2ec"
CARD = "#ffffff"
PANEL = "#f4f7f2"
BORDER = "#dfe6dc"
INK = "#14231a"
TEXT = "#33443a"
MUTED = "#5f6f64"
HEADER = "#0a160c"
HEADER_TEXT = "#f5efe6"
HEADER_MUTED = "#a9c4ad"
ACCENT = "#ea580c"
ACCENT_TEXT = "#c2410c"
ACCENT_SOFT = "#fff1e6"
GREEN = "#15803d"
GREEN_SOFT = "#e9f6ec"
TEAL = "#0e7490"
TEAL_SOFT = "#e6f4f7"
VIOLET = "#6d28d9"
VIOLET_SOFT = "#f1ecfb"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

LOGO_CID = "chirp-logo"
# The app icon (frontend/public/icon-192.png) as of 0.5.10.c, used when the
# built icon isn't on disk. Regenerate when the logo changes.
_LOGO_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAIAAADdvvtQAAAT8ElEQVR4nO3dd1QUV/sH8DvLLgu7oDSpohhU1EgEAigWLChWBBVrNBYIRENEUaMvGn0Nii2xYCyosWAsGIxdLCAKWEEQFGxYEKR3BFa2zO+PzUv4weyyzGWXXXg+x8OBO3fujGe/Z+ozswTHUAsBQBejtVcAqDYIEMACAQJYIEAACwQIYIEAASwQIIAFAgSwQIAAFggQwAIBAlggQAALBAhggQABLBAggAUCBLBAgAAWCBDAAgECWCBAAAsECGCBAAEsECCABQIEsECAABYIEMACAQJYIEAACwQIYIEAASwQIIAFAgSwQIAAFggQwAIBAlggQAALBAhggQABLBAggAUCBLBAgAAWCBDAAgECWCBAAAsECGCBAAEsECCABQIEsECAABYIEMACAQJYIEAACwQIYIEAASzM1l4B0GwkSYp/IQiiddcEwRZI5QhFpJBETAZBEARfKBL9L0ytBbZAqkREkkZaTFNtVnd9dgVPlFHCy60U8ARkK26JIECqRFtd7ZBH11HWeuI/yWrBD5cyjyaXIPRPguq2RwqLFOzCVMk0a91RVjqCKoH4H4lQ0EgzTRaBECIREpJIhEgmQRIEyReRIoXs3GALpEoGm3MEfFHdnyIS6WkyrQw0UvJ4JEkaqSNDNmnJIcr56H01mVeLPst/5wYBUiUmHdgNWoQk6qKjnpLH68gk91gTEzoRIkQwCFRSi1akk6dy5b4zg12YKimt4TdurOAJEUJTjNEwPaKQTxTzUWEtIhGxugfBZsh9NwYBUiUMqs2JuNGmA1Hz784NiRDSUSe6aMr9WBoCpIxEIlIgFPEFIr5QJBCKSBku9phqNGwRkqhLo8YWB8dASockSS0Nlp6WBpvFEIrI6lpBUQWvyQuGFQKy7mS+Tv1tkpy06wD16dlzgL2DmYmJlhaXy+Vqc7hcLvfzZ15RSUlBUVFpeXlxcUlBUWFy6tOyinKFrRWLyVg8vp/XiD6mZjqiqtpHGQVBEY9inmVLv3FBuXdTwNWgdhegXj26O9n3H+jo4OToaGRgIMssfD7/VlxsxKVLkdHRnz9/lvcaDuhh9PO3gxGPT1bzGWqMAV+aHuw0otfi40L5b05oaC8BmjJhwoTRowfYOxjo6TV3XhaLNXqEy+gRLlXV1ZdvXA8/dy7uwQN5rKSYp1MPUdU/MSVFJKoVmuprf2HU8XWu4raCsmvjAWIymbM8PX/09rYw74I/GpfDme4xabrHpNj79wI3bHiZkYE/ZmOmutwGLSKhqLO+NgRIoTQ02PNmzPTz8jYyNGzxwZ2dBsZfuXr8zJn1W7eWV1a07OC1ImHjRhaj9Ss3KLXBAHXQ0vaZO9d7zmx93WbvrZplzrRpwwYNmrNwYdrLFy04LNHoZEqZtbXrQA62tg9v3ly5eLG80yNmbmZ2PSJi6kR3BSxLObWpAC1asODinydoHCbjYKur7922bdYUT0UuVHm0kV2YhgZ796YtHuPGNWuutBcvHyYlPkhMyMz+WFFRUV5RXlhcoq+ra2psbGRoaG7a2bKbhZurq6mJSZND7QoOrvz06dL1a3T/B6qqLQTIwrzLn/v3W3XvLkvnB4mJ8Q8fPHz8OPHJk09VVY07FJeWFpeWPn3+XPznmuCNfXv1dh0+3H3suD5WPaWMfDgkxGPOnLuPHjaexOVwLC0sHGy/njpxoq5Ox9T09P8EBRWVFMuywkpO5QPkMsT50M6dWlpaTfaMiY/fsjvk8ZMnzV3EsxfPn714vn3fXvexY/+zZImlRTdJPf8I2eUxe46+nl5X885dOnfu1qWrhbl51y7mDQ7IvrCwcBs9xu2bGQnJzV4ZZaPaARo6cOCpgwebfDgh5u7dLSG7mhUdBzu7wY79yysqHjxOTH/5Utx4ITIyMipq77Zf3ceOpZxLX1cv7soVWcZXU2OEbt9hN3y47KuknFQ4QFbdux/bs1d6emLu3t26OyQxOVn2YZlM5rHf97gOH44QSklLMzMx8ffxXfrz6urqGoRQLZ/vvcQ/62O2n/d3Mg5IcZMTIYSQuanZFxYWb9+/l33dlJCqBkhfV/f0gUNcDkdKH7+VK8PPn2vuyBsCA8Xp4fP5rp5TRCKR+9ixuzdt9vL3r+uzfts2kYhc7OMjy4BSAj7YsX9LBUjQ6E4ZgRBfJCm9LUZVT+P/3Le/s5mppKlFJSXjZs6gkR4jQ8Nvp00X//65tlZNTQ0hRBDE+FGuOh061u8Z9Nuvp8/9jRBWyV9qWhrO7PU9qyQZiKwLC4FQjZB8Vw0FZVQOh+y2t7WVNPX5q1cukzwSkpJojGxlacliscS/a3G5Z/44vH7lqs1r16qpqfXr26dB51VBQTVSbs43Fa38goInac8o5qMq/WmyHuhsHpFZTdaKSAYiSZKsFJCncsi8WghQI/4+vm6jR0uaei06asz0qTl5efQGLyv/fzcsB/fvv2jBAvE5VFUNr0HnqqqqU2fPShxL6meXk5c3YpIH5aSi8poGsxII5ZVXSxsOofc1hGcycT4fpVSguBK0+x1a9YJgyv+miIoFyHX4iDXLlkmaeiPm1pxFi8RHu/Skpqe/eE1xj/1jTs7T9PTG7eu2bK789Km5S7l844bNsKEFRUWUU6PTPtbUChgMgkEQ4p9vC8pfZJdKH5PFQFk1xA8phMtdwvMRseMtoaGQ+6+qFCAuh7M9KEjS1BevM3wCAvCX4rdyhUAgqN/C4/G+WxZAWUrG430e6u6WmZUlfkg9r6Ag4+1b6eP/dfHi/B/9pJQ5n4l/dfhWenZRZWFFdX5p1fOsYt/QmFoZysnUGYijjjhsxGEjDktBD6eq0lnYcj8/o06dKCeVlZd/4+tTVd3Edl4WKWlpsxd+vyNog4mxsUAgiHvwYNue36UcUWVlf7Qf6YIQYjKZ+3/9TdIlIrEjJ0/8tH699BXQUGf9uC/6UFRar866lTW1cc9zK2tqOWwWvf+OvKlMgCzMu/h5eUuaOv9Hvw8fs1tqWdGxsV8NdW7WLBoa7DN/HHayd5DSZ//Roz9vCm5yKIJAHG3Np1nFKe8KEUGos9Tq0sMXNtxuEQh9bnwGr0Aqswvbsm6dpEnL/7su/iHFHSiFsexmkR5/T3p6tu7eLUt66miwmBxNdY4Gi6n272d0L+sTSZIMAhEIEQipEaiomv80n/4xHz7V2AK5Dh8xYsgQyknnr149duqUgtenPoIgIsP/0tbWltJnTfDG0GPH8Jd1MLF4XI+O/Uw5GkyGUER+qhUFxeSU8URqrVevSHAMm74N2brUWaxHN6PMqGoqqmtqHEaNLCgsVPxa1Zk0fvyB7TskTSVJ8qf/rj96+mSLLEtEkjy+yNfBoI+hZkmN4M67T7ffVHI01FpkcHpUYAv0g5c3ZXoQQjv27Wvd9CCEBjk6SpnqHxh46m/J14qaiUEQGixG6MMiJCIRgRCT0brpQcofICaT6edNfez8MTd37+E/FLw+jUk69SNJ8vvlAX9flunmvOwYBNHqoalP2Q+iJ7i6dpBweLEq6JdaPsXbKhRMUoC27t7V4ulRQsq+BZo5eQple+z9e9eio+mNqcXlfuPpObh///RXr05ERHzIxjr/l7R7vRDZLspblfog2rBTp2dx8Y0rfoRCYX/XUZl0P/gT+0Nd/1fJJRQKt4SE7AzdL8sbMChFHDk6dOBA9E/dz78/zL+y5sn/OehWp9S7sJmTJlPWi12+cYN2evy8vV3r1QGqqakFLl3qPXs2zVVEyMzEWPwLUe9HWUV5e0gPUvIAzZ0xg7I94tJFegN+adXrP/5LGrfPnzWL3oA6HTtSlkh/zKFZDqBy5BsgI0PDL7pa0JvXwc7O3MyscXtZeXnUnTs0BlRXV9//23Z1dfXGkzTYNN/ENMHVlXIbmZOXS29AlSOvAHXQ0j514OCzuPiHN24kRkX7zp3b3BFmTppM2X4xMrLB3XIZrQlY1qsH9aM/MXFxNAZECLmNHkPZ/jglhd6AKkcuB9FsNvtmxN+9e/ao3xh7//73ywMKi2R9GCr1TqyJsXHjdvfZs+8lPGruKg1y7H/++HHKSUKhcPD4cRnv3jV3TC6X+yYhUVz22oDjqJHvPnxo7oCqSC5boIXz5jdID0LI2ckp7vKVYYMGyTKCtpYWZXpy8vJopKePldXRPb9Lmhpy8ACN9CCExo8cRZme569et5P0IDkFaKyLC2W7vq7eX4ePbFy9hsls4vqTXb+vKNtv341v7sp8bWNz6cTJBiXxdTKzsn7ds6e5Y4q5jXalbL98o11cARKTS4AYDGnD+nz77Y2ICOlvfLLu3bCCXay5jzE4OzmdO3pM0rVshJB/YGBtbW2zxhSz7NZt1DDqxwIvXoukMaCKkkuAjkf8Jb2Dde8+sZcuzZk2TVKHvr2oA1T3yLosXJydTx88pKmpKanDgbAwykfZZRESvIly//U2M5OyqrqtkkuAwk6fPnKyiQIGTU3N7UEbju3Zo031WLt1n96Uc8m4BTLQ09setOFk6IG6Z3Qau5fwqFkVXvVNmTDB0c6OctK5K5fpjami5HgrY96MWb+sWillAyD2MTfXy39x/fNeDTY780lK4/1gxru3TmOoT5vrsNnsRfMXLPbx0eI2fNNgfXn5+c5ubqXlZdJHo6TBZidG36KszlaG+iQFk+OFxKOnTw51n1j3ZgJJzExMLp88tcT3+7orcn379KE8inqa3sT+y9PN7eG164FLl0pPT2FxyeR5c+mlByG0yn+JpNp+ZahPUjD53o1/l5npMnnS2uUrvp83T8pbEJhM5uqAAJehzl7+/gWFhX2tqPdfT583fDKLxWLZWFs72to52tra29oZGug3uUqFxSXus2e9burhG0mcnZwWzp9POUlJ6pMUTO7lHAKBYO3mTTdv3w7dvr2TvrQPeMDX9nevXF24YrmJMfV7VVPT/zkAMjYymu7uMcJ5iH0/G8pbE5K8evNmps93tOs3evfsGbZ3n6RzzMCNG5ShPknBFFfOoaujs2/bry7OTT8uk/LsWb++fRu3D5kw7sXrjAFf24cf+oPDaeLQqrHo2Fgv/8W0nx0zNjSMPnfeUMLL7R8+fjxh1kx6I6s0xd2NLy0rm/Gd98r163m8hg+ZN0CZHoQQny9ECC1asIBGevYdOTLT5zva6dHicv8+dkxSeoRC4ZLVq+mNrOoUXc5x+OQJ54lur968kdqLuraLL+AjhL7s1atZS3z6PH38zBlrN2+iXTLG5XDC9u7r8YWlpA5rN2/KeEfzoErVtUI90LvMzGHuE0OPHZP8iVIfbguEAoRQdaO3ZEjyITvbd9nSER4ej2i96kXM1Nj45tmzQwYMkNQhLDz8QFgY7fFVXesUlPH5/DXBG6d6zc+X8IYKSgK+ACGUkNx0GnLz8pat/dnRdRRmWbtNX+uY8xekbHui7txevm4tziJUXSvXROvq6BzaudPZaaAsna36O5aUlXXv1u32hYtsdsOvn0UIlZSVXouOvn03/srNKHp3uOqb4uYWErxJyllealra+Jkz2knpqiRKUVTvPXv2uhU/aWjUlQVSv9nP2nlIXn4+QsjG2npjYKBNX2uCINJfvkxNT09NS09KfZJK9QofetYELPP39ZXSITMra8y0qUUlJS21RBWlFAFCCPXq0T30t53S3+Sd/PSpqyf1Uz4tyMHObtPqNZLOBMVKy8vGTJ32NvO9vFdG+SlLUf2L1xlDJ07452hUwrG1rbW1lHd04DM1MT60c9fVU6elpye/oMBjzhxIj5iybIHqDBngdHzvHi5X4lotW/tzWHh4yy5UW0tr2aIffvDyarJnUkrK7IW+hcXtfc9VR+kChBDqpK935+LlThKu2olEojMXzm/Yvj2/oAB/WY52djMmTXYfO1ZK0VmdC5GRC1cs57e/+xVSKGOAEEI6HTsm3YqhLBUS4/F4B8LCdobup/GOS4SQoYHBN55Tp0/ykPLFF/WRJLlp584d+/fRWFbbpqQBQgi5DHE+feiQ9D7V1TW34mOv3rx5/VZMxadK6Z17Wlra29g42No52Nr2tLRs8hs2/l1KTY1vQMC1WzQfxW/blDdACKFFCxasX7lKxs73ExM+ZGd/yM7OKyj4kJ3N5wsIApkYG1uYd7G1tnaws5VUVy9dZFTUmk3BmC9gaMOUOkAIIZ9v525spfuUb9+/X75uXdyD+62ydFWh7AFCCLmNHr178xbp36vSsioqK3/btzf06FGhkOILlEF9KhAghFC3rl2P7v69j5WVvBdEkmT4+XO/bNsKJ+oyUo0AIYRYLJa/j6+/j0+9Ox4t6UN2dvj5cyfPns3OyZHH+G2VygRIzNzMbFdw8JABTi014KeqqkvXr4WfO0/7AbF2TsUCJDZ88OCJY8aOdx2l21GHxuz5RUWJyUmPkpISnjyh961QoI5KBkiMwWAM+Np+vKvr+JEjzUwlfvkcQkgoFKa/epmQnJyQlPQoORnOyVuQCgeovg5a2vp6egYG+gZ6ep309fV19So/VebmF+QVFuTl53/MbS+ve1K8NhIg0FqUpZwDqCgIEMACAQJYIEAACwQIYIEAASwQIIAFAgSwQIAAFggQwAIBAlggQAALBAhggQABLBAggAUCBLBAgAAWCBDAAgECWCBAAAsECGCBAAEsECCABQIEsECAABYIEMACAQJYIEAACwQIYIEAASwQIIAFAgSwQIAAFggQwAIBAlggQAALBAhggQABLBAggAUCBLBAgAAWCBDAAgECWCBAAAsECGCBAAEsECCABQIEsECAABYIEMACAQJYIEAACwQIYIEAASwQIIAFAgSwQIAAFggQwAIBAlggQADL/wFlwrgndbdhMgAAAABJRU5ErkJggg=="


def logo_png() -> bytes:
    here = Path(__file__).resolve().parent.parent           # app/
    for p in (here / "static" / "icon-192.png",
              here.parent / "frontend" / "public" / "icon-192.png",
              here.parent / "frontend" / "dist" / "icon-192.png"):
        try:
            if p.is_file():
                return p.read_bytes()
        except OSError:
            pass
    return base64.b64decode(_LOGO_PNG_B64)


class InlineImages:
    """Images to attach to one email, referenced from its HTML as cid:."""

    def __init__(self):
        self.parts = []          # [{"cid", "content", "mimetype"}]
        self._by_key = {}

    def add(self, content: bytes, mimetype: str, key: Optional[str] = None) -> str:
        key = key or hashlib.sha1(content).hexdigest()[:16]
        if key not in self._by_key:
            cid = f"img-{len(self.parts) + 1}-{key}"
            self.parts.append({"cid": cid, "content": content, "mimetype": mimetype})
            self._by_key[key] = cid
        return f"cid:{self._by_key[key]}"

    def add_photo(self, path: str, width: int = 480, height: int = 320) -> Optional[str]:
        """A bird photo cropped to width x height (3:2) as JPEG; None when
        the file is missing or unreadable."""
        if not path or not os.path.isfile(path):
            return None
        try:
            from PIL import Image, ImageOps
            im = Image.open(path)
            im = ImageOps.exif_transpose(im).convert("RGB")
            im = ImageOps.fit(im, (width, height), Image.LANCZOS, centering=(0.5, 0.4))
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=82, optimize=True, progressive=True)
            return self.add(out.getvalue(), "image/jpeg", key=hashlib.sha1(path.encode()).hexdigest()[:16])
        except Exception:
            return None


def esc(s) -> str:
    import html
    return html.escape(str(s or ""), quote=True)


def section_label(text: str) -> str:
    return (f'<div class="em-muted" style="font-size:11px;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:.1em;color:{MUTED};margin:0 0 12px;">{text}</div>')


def info_box(html: str, accent: str = ACCENT) -> str:
    return (f'<div class="em-panel em-text" style="background:{PANEL};border-left:3px solid {accent};'
            f'border-radius:0 10px 10px 0;padding:14px 16px;margin:16px 0;font-size:14px;'
            f'color:{TEXT};line-height:1.6;">{html}</div>')


def stat_tile(value: str, label: str, color: str, soft: str) -> str:
    return (f'<td class="em-tile" width="33%" style="text-align:center;padding:16px 8px;background:{soft};'
            f'border-radius:12px;">'
            f'<div style="font-size:30px;font-weight:800;color:{color};line-height:1;">{value}</div>'
            f'<div style="font-size:11px;font-weight:600;color:{color};margin-top:6px;text-transform:uppercase;'
            f'letter-spacing:.08em;">{label}</div></td>')


def stat_row(tiles: list) -> str:
    cells = '<td width="10" style="font-size:0;">&nbsp;</td>'.join(tiles)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:0 0 26px;"><tr>{cells}</tr></table>')


def badge(text: str, color: str, soft: str) -> str:
    return (f'<span style="display:inline-block;padding:3px 9px;border-radius:99px;font-size:11px;'
            f'font-weight:700;background:{soft};color:{color};">{text}</span>')


def species_card(name: str, photo_src: Optional[str], lines: list, badges: str = "",
                 bar_pct: Optional[float] = None, link: str = "") -> str:
    """One species: photo (or a lettered tile), name, detail lines."""
    if photo_src:
        pic = (f'<img src="{photo_src}" width="256" alt="{esc(name)}" '
               f'style="display:block;width:100%;max-width:100%;height:auto;border-radius:10px 10px 0 0;"/>')
    else:
        initials = "".join(w[0] for w in str(name).split()[:2]).upper() or "?"
        pic = (f'<div style="height:120px;line-height:120px;text-align:center;border-radius:10px 10px 0 0;'
               f'background:{GREEN_SOFT};color:{GREEN};font-size:34px;font-weight:800;">{esc(initials)}</div>')
    if link:
        pic = f'<a href="{link}" style="text-decoration:none;">{pic}</a>'
    bar = ""
    if bar_pct is not None:
        w = max(4, min(100, round(bar_pct)))
        bar = (f'<div class="em-track" style="height:6px;background:{BORDER};border-radius:3px;margin-top:10px;">'
               f'<div style="height:6px;width:{w}%;background:{ACCENT};border-radius:3px;"></div></div>')
    detail = "".join(f'<div class="em-muted" style="font-size:12px;color:{MUTED};margin-top:3px;">{l}</div>'
                     for l in lines if l)
    title = esc(name)
    if link:
        title = f'<a href="{link}" class="em-ink" style="color:{INK};text-decoration:none;">{title}</a>'
    badge_html = f'<div style="margin-top:8px;">{badges}</div>' if badges else ""
    return (f'<div class="em-card2" style="background:{CARD};border:1px solid {BORDER};border-radius:12px;">'
            f'{pic}<div style="padding:12px 14px 14px;">'
            f'<div class="em-ink" style="font-size:15px;font-weight:700;color:{INK};line-height:1.25;">{title}</div>'
            f'{detail}{badge_html}{bar}</div></div>')


def species_grid(cards: list) -> str:
    """Two cards per row; stacks on narrow screens."""
    rows = []
    for i in range(0, len(cards), 2):
        a = cards[i]
        b = cards[i + 1] if i + 1 < len(cards) else ""
        rows.append(
            '<tr>'
            f'<td class="em-col" width="50%" valign="top" style="padding:0 6px 12px 0;">{a}</td>'
            f'<td class="em-col" width="50%" valign="top" style="padding:0 0 12px 6px;">{b}</td>'
            '</tr>')
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(rows)}</table>')


def journal_box(text: str) -> str:
    paragraphs = [p.strip() for p in str(text).strip().split("\n\n") if p.strip()]
    inner = "".join(f'<p class="em-text" style="margin:0 0 10px;font-size:14px;line-height:1.7;color:{TEXT};">{esc(p)}</p>'
                    for p in paragraphs)
    return (f'<div class="em-panel" style="background:{PANEL};border:1px solid {BORDER};border-radius:12px;'
            f'padding:18px 20px 8px;margin:0 0 8px;">{inner}</div>')


def wrap_html(title: str, preheader: str, body_html: str, *, subtitle: str = "",
              accent: str = ACCENT, cta_url: str = "#", cta_label: str = "",
              server_url: str = "", logo_src: str = f"cid:{LOGO_CID}") -> str:
    cta = ""
    if cta_label:
        cta = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:26px 0 4px;">'
               f'<tr><td align="center"><a href="{cta_url}" style="display:inline-block;padding:13px 28px;'
               f'background:{ACCENT_TEXT};color:#ffffff;font-weight:700;font-size:15px;border-radius:10px;'
               f'text-decoration:none;">{cta_label} &rarr;</a></td></tr></table>')
    manage_url = f"{server_url}/profile" if server_url else "#"
    sub = (f'<div style="font-size:14px;color:{HEADER_MUTED};margin-top:6px;">{subtitle}</div>' if subtitle else "")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="color-scheme" content="light dark"/>
<meta name="supported-color-schemes" content="light dark"/>
<title>{esc(title)}</title>
<style>
  :root {{ color-scheme: light dark; supported-color-schemes: light dark; }}
  @media (max-width: 520px) {{
    .em-pad {{ padding-left: 16px !important; padding-right: 16px !important; }}
  }}
  @media (max-width: 340px) {{
    .em-col {{ display: block !important; width: 100% !important; padding: 0 0 12px 0 !important; }}
  }}
  /* Apple Mail and iOS Mail in dark mode: our own dark version instead of
     an automatic inversion. */
  @media (prefers-color-scheme: dark) {{
    .em-bg {{ background: #071009 !important; }}
    .em-card, .em-card2 {{ background: #0f1d12 !important; border-color: #1f3324 !important; }}
    .em-panel {{ background: #142618 !important; border-color: #1f3324 !important; }}
    .em-ink {{ color: #f3efe7 !important; }}
    .em-text {{ color: #d3ddd4 !important; }}
    .em-muted {{ color: #9db5a2 !important; }}
    .em-track {{ background: #1f3324 !important; }}
  }}
</style>
</head>
<body class="em-bg" style="margin:0;padding:0;background:{BG};font-family:{FONT};color:{TEXT};">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{esc(preheader)}&nbsp;&#8204;&#8204;&#8204;&#8204;&#8204;&#8204;</div>
<table role="presentation" class="em-bg" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};">
<tr><td align="center" style="padding:28px 12px;">
<table role="presentation" class="em-card" width="600" cellpadding="0" cellspacing="0"
       style="width:100%;max-width:600px;background:{CARD};border:1px solid {BORDER};border-radius:18px;overflow:hidden;">
  <tr><td class="em-pad" style="background:{HEADER};padding:24px 32px 26px;">
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:middle;padding-right:10px;">
        <img src="{logo_src}" width="52" height="52" alt="Chirp" style="display:block;width:52px;height:52px;border-radius:12px;"/>
      </td>
      <td style="vertical-align:middle;font-size:21px;font-weight:800;color:{HEADER_TEXT};letter-spacing:-.4px;">Chirp</td>
    </tr></table>
    <h1 style="margin:22px 0 0;font-size:26px;line-height:1.25;font-weight:800;color:{HEADER_TEXT};letter-spacing:-.4px;">{title}</h1>
    {sub}
  </td></tr>
  <tr><td class="em-pad" style="padding:28px 32px 8px;">
    {body_html}
    {cta}
  </td></tr>
  <tr><td class="em-pad" style="padding:18px 32px 26px;text-align:center;border-top:1px solid {BORDER};">
    <p class="em-muted" style="margin:0;font-size:12px;color:{MUTED};line-height:1.6;">
      Chirp &middot; your own bird monitoring station<br/>
      <a href="{manage_url}" style="color:{ACCENT_TEXT};">Email preferences</a>
      &nbsp;&middot;&nbsp;
      <a href="{server_url or '#'}" style="color:{ACCENT_TEXT};">Open Chirp</a>
    </p>
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""
