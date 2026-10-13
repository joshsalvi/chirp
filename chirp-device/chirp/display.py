"""
Chirp Device — OLED Display Driver
Argon ONE v5 "Industria" Case — 128×32 SSD1306 OLED

Hardware:
  Display:   128×32 monochrome OLED, SSD1306 controller
  Interface: I²C, address 0x3C, bus 1 (/dev/i2c-1)
  Case:      Argon ONE v5 with Industria top panel

Requirements:
  pip install luma.oled pillow smbus2
  sudo usermod -aG i2c $USER   (then reboot / restart service)
  dtparam=i2c_arm=on in /boot/firmware/config.txt

Display pages (auto-cycle every PAGE_INTERVAL_SEC, flash to detection on trigger):

  Page 0 — LOGO        Pixel-art bird + "CHIRP" centered
  Page 1 — STATUS      ●/○  ONLINE/LOCAL  |  42  detections
  Page 2 — LAST BIRD   Robin (big) · 89% (big) · 2m ago (small)
  Page 3 — SYSTEM      41° (big left) · 3d 4h (big right)
  Page 4 — UPLOADS     23 (big) · queue 0 · 4.2 MB sent

Design principles:
  - Max 2 pieces of data per page — readability on 128×32
  - Large fonts (16–20pt) for primary values, 9pt for labels
  - No divider lines, no page dots (waste precious pixels)
  - PIL load_default(size=N) for font — no file path dependency
"""

import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

OLED_WIDTH        = 128
OLED_HEIGHT       = 32
OLED_I2C_ADDRESS  = 0x3C
OLED_I2C_BUS      = 1

PAGE_COUNT        = 6          # 0=Logo 1=Status 2=LastBird 3=System 4=Uploads 5=Disk
PAGE_INTERVAL_SEC = 6          # seconds per page in auto-cycle
FLASH_SECS        = 6          # how long to show detection page on new trigger

# Font sizes — load_default(size) (Pillow 10+). Bumped up for better readability.
# On 128×32 the bitmap renderer naturally makes larger fonts appear bolder.
SZ_LARGE  = 19    # primary values — was 16, now chunkier
SZ_MEDIUM = 13    # secondary values — was 11
SZ_SMALL  = 10    # labels/timestamps — was 9

# Splash logo: pixel-art bird drawn with PIL primitives
# Fits in a 28×20 bounding box, placed left-centre, "CHIRP" text right
LOGO_X = 4        # left margin for bird art
LOGO_Y = 4        # top margin


class OledDisplay:
    """128×32 SSD1306 OLED on the Argon ONE v5 Industria panel."""

    def __init__(self, config: Dict):
        self._config   = config
        self._device   = None
        self._fl           = {}     # font cache: {size: ImageFont}
        self._font_cursive = None   # italic/script font for logo page
        self._page     = 0
        self._stats: Dict[str, Any] = {}
        self._last_detection: Optional[Dict] = None
        self._last_detect_time: Optional[datetime] = None
        self._flash_until: Optional[float] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> bool:
        last_err: Optional[Exception] = None
        for attempt in range(3):
            if attempt > 0:
                time.sleep(2.0)
            try:
                if self._init_hardware():
                    self._thread = threading.Thread(
                        target=self._loop, name="OledDisplay", daemon=True
                    )
                    self._thread.start()
                    logger.info("OLED display active (128×32 SSD1306 I2C bus=%d addr=0x%02X)",
                                OLED_I2C_BUS, OLED_I2C_ADDRESS)
                    return True
            except ImportError as e:
                logger.info("OLED disabled — luma.oled not installed: %s", e)
                return False
            except PermissionError as e:
                last_err = e
            except Exception as e:
                last_err = e
                logger.debug("OLED init attempt %d: %s", attempt + 1, e)

        if last_err:
            if "Permission" in str(last_err) or "13" in str(last_err):
                logger.warning(
                    "OLED: permission denied on /dev/i2c-%d. "
                    "Fix: sudo usermod -aG i2c %s  then restart service.",
                    OLED_I2C_BUS, os.environ.get("USER", "$USER"))
            elif "No such file" in str(last_err):
                logger.warning(
                    "OLED: /dev/i2c-%d not found. "
                    "Add dtparam=i2c_arm=on to /boot/firmware/config.txt", OLED_I2C_BUS)
            else:
                logger.warning("OLED init failed: %s", last_err)
        return False

    def _init_hardware(self) -> bool:
        from luma.core.interface.serial import i2c
        from luma.oled.device import ssd1306
        from PIL import ImageFont

        # Read bus/address from config, falling back to Argon ONE v5 defaults
        disp_cfg = self._config.get("display", {})
        cfg_bus  = int(disp_cfg.get("i2c_bus", OLED_I2C_BUS))
        addr_raw = disp_cfg.get("i2c_address", hex(OLED_I2C_ADDRESS))
        addr     = int(addr_raw, 16) if isinstance(addr_raw, str) else int(addr_raw)
        brightness = int(disp_cfg.get("brightness", 220))

        # Try the configured bus first; if it fails, scan buses 0-7 for the display.
        # The Argon ONE v5 Industria OLED is on bus 1 (Pi 4) or bus 1 (Pi 5 with
        # i2c_arm=on).  Some carrier boards remap to bus 4.  Auto-scan finds it.
        errors = {}
        buses_to_try = [cfg_bus] + [b for b in range(8) if b != cfg_bus]
        for bus in buses_to_try:
            try:
                serial = i2c(port=bus, address=addr)
                dev = ssd1306(serial, width=OLED_WIDTH, height=OLED_HEIGHT)
                dev.contrast(brightness)
                self._device = dev
                if bus != cfg_bus:
                    logger.info(
                        "OLED found on I2C bus %d (config said %d) — "
                        "update display.i2c_bus in config.yaml to suppress this scan",
                        bus, cfg_bus
                    )
                # Pre-load font cache — must happen after device is set
                for sz in (SZ_LARGE, SZ_MEDIUM, SZ_SMALL):
                    try:
                        self._fl[sz] = ImageFont.load_default(size=sz)
                    except TypeError:
                        self._fl[sz] = ImageFont.load_default()
                # Cursive/script font for the logo page
                self._font_cursive = None
                CURSIVE_CANDIDATES = [
                    "/usr/share/fonts/truetype/google-fonts/Lora-Italic-Variable.ttf",
                    "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
                    "/usr/share/fonts/truetype/crosextra/Caladea-Italic.ttf",
                ]
                for path in CURSIVE_CANDIDATES:
                    if os.path.exists(path):
                        try:
                            self._font_cursive = ImageFont.truetype(path, 22)
                            logger.debug("OLED cursive font: %s", path.split("/")[-1])
                            break
                        except Exception:
                            continue
                if self._font_cursive is None:
                    try:
                        self._font_cursive = ImageFont.load_default(size=22)
                    except TypeError:
                        self._font_cursive = ImageFont.load_default()
                # Start GPIO button watcher for page cycling
                self._start_button_watcher()
                return True
            except Exception as e:
                errors[bus] = str(e)
                continue

        # Nothing worked — raise so the caller gets a meaningful message
        raise OSError(
            f"SSD1306 OLED not found at address 0x{addr:02X} on any I2C bus. "
            f"Tried buses {list(errors.keys())}. "
            f"Errors: {errors}. "
            f"Check: sudo i2cdetect -y 1   (or -y 4 for Argon ONE v5). "
            f"Ensure dtparam=i2c_arm=on is in /boot/firmware/config.txt."
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        if self._device:
            try:
                self._device.clear()
            except Exception:
                pass

    # ── Public API ─────────────────────────────────────────────────────────────

    def update_stats(self, stats: Dict[str, Any]) -> None:
        with self._lock:
            self._stats = dict(stats)

    def notify_detection(self, species: str, confidence: float,
                         ago_seconds: float = 0) -> None:
        with self._lock:
            self._last_detection = {"species": species, "confidence": confidence}
            self._last_detect_time = datetime.now()
        self._flash_until = time.monotonic() + FLASH_SECS

    # ── Background loop ────────────────────────────────────────────────────────

    def _loop(self) -> None:
        last_advance = time.monotonic()
        while not self._stop_event.is_set():
            now = time.monotonic()
            if self._flash_until and now < self._flash_until:
                self._render_page(2)    # last-bird page
            else:
                self._flash_until = None
                if now - last_advance >= PAGE_INTERVAL_SEC:
                    self._page = (self._page + 1) % PAGE_COUNT
                    last_advance = now
                self._render_page(self._page)
            self._stop_event.wait(1.0)

        if self._device:
            try:
                self._device.clear()
            except Exception:
                pass

    # ── Render dispatcher ──────────────────────────────────────────────────────

    def _render_page(self, page: int) -> None:
        if not self._device:
            return
        try:
            from luma.core.render import canvas
            with canvas(self._device) as draw:
                if   page == 0: self._draw_logo(draw)
                elif page == 1: self._draw_status(draw)
                elif page == 2: self._draw_last_bird(draw)
                elif page == 3: self._draw_system(draw)
                elif page == 4: self._draw_uploads(draw)
                elif page == 5: self._draw_disk(draw)
        except Exception as e:
            import traceback
            logger.warning("OLED render error page %d: %s\n%s",
                           page, e, traceback.format_exc(limit=4))

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _f(self, size: int):
        """Return cached font for given size. Never returns None."""
        f = self._fl.get(size) or self._fl.get(SZ_SMALL)
        if f is None:
            # Absolute fallback — should never happen but prevents AttributeError
            from PIL import ImageFont
            try:
                f = ImageFont.load_default(size=size)
                self._fl[size] = f
            except Exception:
                f = ImageFont.load_default()
                self._fl[size] = f
        return f

    def _txt(self, draw, x: int, y: int, text: str, size: int = SZ_MEDIUM) -> int:
        """Draw text, return pixel width."""
        f = self._f(size)
        draw.text((x, y), text, font=f, fill="white")
        try:
            return int(draw.textlength(text, font=f))
        except Exception:
            return len(text) * max(6, size // 2)

    def _txt_r(self, draw, y: int, text: str, size: int = SZ_MEDIUM) -> None:
        """Draw text right-aligned."""
        f = self._f(size)
        try:
            w = int(draw.textlength(text, font=f))
        except Exception:
            w = len(text) * max(6, size // 2)
        draw.text((OLED_WIDTH - w - 1, y), text, font=f, fill="white")

    def _txt_c(self, draw, y: int, text: str, size: int = SZ_MEDIUM) -> None:
        """Draw text horizontally centred."""
        f = self._f(size)
        try:
            w = int(draw.textlength(text, font=f))
        except Exception:
            w = len(text) * max(6, size // 2)
        draw.text(((OLED_WIDTH - w) // 2, y), text, font=f, fill="white")

    def _txt_cursive(self, draw, x: int, y: int, text: str) -> None:
        """Draw text using the cursive/italic font, centred in the right half."""
        f = self._font_cursive or self._f(SZ_LARGE)
        try:
            w = int(draw.textlength(text, font=f))
        except Exception:
            w = len(text) * 9
        # Centre within the right portion of the display (x to right edge)
        avail = OLED_WIDTH - x
        cx = x + max(0, (avail - w) // 2)
        draw.text((cx, y), text, font=f, fill="white")

    def _start_button_watcher(self) -> None:
        """
        Watch the Argon ONE v5 Industria OLED button (GPIO 27, BCM) and advance
        the display page on each press.

        Tries three methods in order:
          1. python-gpiod (libgpiod — modern Pi OS)
          2. sysfs /sys/class/gpio  (works without any library)
          3. Silently disabled if neither is available
        """
        GPIO_PIN = 27          # BCM pin for Argon ONE Industria screen button
        DEBOUNCE_MS = 250      # ignore bounces within this window

        def _open_gpiod_request():
            """
            Open the gpiod line request synchronously, on the calling thread.
            Raises on any real failure (missing chip path, no permissions,
            line already held, wrong API for the installed gpiod version,
            etc.) so the caller can catch it and fall back to sysfs — this is
            the part that silently died inside a daemon thread before.
            """
            import gpiod
            from gpiod.line import Edge, Bias
            return gpiod.request_lines(
                "/dev/gpiochip0",
                consumer="chirp-display",
                config={GPIO_PIN: gpiod.LineSettings(
                    edge_detection=Edge.FALLING,
                    bias=Bias.PULL_UP,
                )},
            )

        def _button_loop_gpiod(request):
            import time
            last_press = 0.0
            logger.info("OLED button watcher active (gpiod, GPIO %d)", GPIO_PIN)
            try:
                while not self._stop_event.is_set():
                    if request.wait_edge_events(timeout=0.5):
                        request.read_edge_events()
                        now = time.monotonic()
                        if now - last_press > DEBOUNCE_MS / 1000:
                            last_press = now
                            self._advance_page()
            finally:
                request.release()

        def _button_loop_sysfs():
            import time
            export_path = "/sys/class/gpio/export"
            gpio_dir    = f"/sys/class/gpio/gpio{GPIO_PIN}"
            val_path    = f"{gpio_dir}/value"
            dir_path    = f"{gpio_dir}/direction"
            edge_path   = f"{gpio_dir}/edge"

            try:
                if not os.path.exists(gpio_dir):
                    with open(export_path, "w") as f:
                        f.write(str(GPIO_PIN))
                    time.sleep(0.1)
                with open(dir_path, "w") as f:
                    f.write("in")
                with open(edge_path, "w") as f:
                    f.write("falling")
            except Exception as e:
                logger.debug("OLED button sysfs setup failed: %s", e)
                return

            import select
            last_press = 0.0
            logger.info("OLED button watcher active (sysfs, GPIO %d)", GPIO_PIN)
            try:
                with open(val_path, "r") as val_file:
                    # Read once to clear initial state
                    val_file.read()
                    val_file.seek(0)
                    while not self._stop_event.is_set():
                        r, _, _ = select.select([val_file], [], [], 0.5)
                        if r:
                            val_file.seek(0)
                            val = val_file.read().strip()
                            if val == "0":   # active low
                                now = time.monotonic()
                                if now - last_press > DEBOUNCE_MS / 1000:
                                    last_press = now
                                    self._advance_page()
            except Exception as e:
                logger.debug("OLED button sysfs read error: %s", e)
            finally:
                # Unexport on exit
                try:
                    with open("/sys/class/gpio/unexport", "w") as f:
                        f.write(str(GPIO_PIN))
                except Exception:
                    pass

        # Try gpiod first, then sysfs
        def _try_start():
            try:
                gpiod_request = _open_gpiod_request()
            except ImportError:
                gpiod_request = None
            except Exception as e:
                # Real runtime failure (wrong/missing chip path, no permissions,
                # line busy, gpiod API mismatch, etc.) — this used to escape
                # uncaught inside the daemon thread and silently kill the
                # button watcher with no fallback. Caught here instead, so we
                # fall through to sysfs below.
                logger.warning("OLED button: gpiod unavailable (%s) — falling back to sysfs", e)
                gpiod_request = None

            if gpiod_request is not None:
                t = threading.Thread(target=_button_loop_gpiod, args=(gpiod_request,),
                                     name="OledButton", daemon=True)
                t.start()
                return

            if os.path.exists("/sys/class/gpio"):
                t = threading.Thread(target=_button_loop_sysfs,
                                     name="OledButton", daemon=True)
                t.start()
                return

            logger.debug("OLED button: no GPIO access (install python-gpiod for button support)")

        _try_start()

    def _advance_page(self) -> None:
        """Manually advance to the next page (called on button press)."""
        self._page = (self._page + 1) % PAGE_COUNT
        # Cancel any active flash so button overrides it
        self._flash_until = None
        self._render_page(self._page)
        logger.debug("OLED button: advanced to page %d", self._page)

    # ── Page 0: Logo splash ────────────────────────────────────────────────────
    # Wider pixel-art bird across the left 52px, "chirp" cursive on the right.
    # Bird is drawn at 2× scale so it reads clearly at arm's length.
    #
    #  Display: 128×32
    #  Bird zone: x=0..51  (52px wide)
    #  Text zone: x=54..127 (74px wide)
    #
    def _draw_logo(self, draw) -> None:
        # Bird origin — shifted left and slightly taller scale factor
        bx, by = 2, 0

        # ── Head (larger circle) ──────────────────────────────────────────────
        draw.ellipse([bx+8,  by+1,  bx+20, by+12], fill="white")

        # ── Body (wide ellipse) ───────────────────────────────────────────────
        draw.ellipse([bx+2,  by+8,  bx+24, by+26], fill="white")

        # ── Tail feathers (pointing left) ─────────────────────────────────────
        draw.polygon([
            (bx+2,  by+18),
            (bx-4,  by+26),
            (bx+0,  by+27),
            (bx+4,  by+21),
            (bx+7,  by+27),
            (bx+11, by+27),
            (bx+10, by+19),
        ], fill="white")

        # ── Eye ───────────────────────────────────────────────────────────────
        draw.ellipse([bx+15, by+3, bx+19, by+7], fill="black")
        # Eye highlight
        draw.ellipse([bx+16, by+3, bx+17, by+4], fill="white")

        # ── Beak (wider triangle pointing right) ──────────────────────────────
        draw.polygon([
            (bx+20, by+6),
            (bx+32, by+8),
            (bx+20, by+11),
        ], fill="white")

        # ── Wing (dark cutout on body, white highlight) ────────────────────────
        draw.ellipse([bx+4,  by+12, bx+16, by+22], fill="black")
        draw.ellipse([bx+6,  by+13, bx+14, by+20], fill="white")

        # ── Legs (thicker — 2 lines each) ─────────────────────────────────────
        for lx in (bx+9, bx+10):
            draw.line([(lx, by+25), (lx-1, by+31)], fill="white")
            draw.line([(lx-1, by+31), (lx-4, by+32)], fill="white")
        for lx in (bx+15, bx+16):
            draw.line([(lx, by+25), (lx-1, by+31)], fill="white")
            draw.line([(lx-1, by+31), (lx-4, by+32)], fill="white")

        # ── Sound waves (right of beak, 3 arcs getting larger) ────────────────
        sx = bx + 34
        for i, r in enumerate([4, 7, 10]):
            draw.arc([sx+i*4, by+4, sx+i*4+r, by+13],
                     start=310, end=50, fill="white")

        # ── "chirp" in cursive/italic — right half, vertically centred ────────
        # Text zone starts at x=55, centred vertically in 32px
        f = self._font_cursive or self._f(SZ_LARGE)
        try:
            tw = int(draw.textlength("chirp", font=f))
        except Exception:
            tw = 40
        tx = 55 + max(0, (73 - tw) // 2)   # centre in 55..127 zone
        # Vertical: font bbox top offset is typically 4-6px, aim for visual centre
        draw.text((tx, 5), "chirp", font=f, fill="white")

    # ── Page 1: Status ─────────────────────────────────────────────────────────
    # Shows: paired status (large dot + label) + total detections (large number)
    #
    #  ●  ONLINE        42
    #      detections
    def _draw_status(self, draw) -> None:
        with self._lock:
            s = self._stats
        paired   = s.get("paired", False)
        triggers = s.get("triggers", 0)
        uploads  = s.get("uploads_succeeded", 0)

        # Left: connection status
        dot = "●" if paired else "○"
        label = "ONLINE" if paired else "LOCAL"
        draw.text((2, 0), dot, font=self._f(SZ_LARGE), fill="white")
        self._txt(draw, 18, 3, label, SZ_SMALL)
        self._txt(draw, 2, 19, f"{uploads} up", SZ_SMALL)

        # Vertical separator
        draw.line([(63, 0), (63, OLED_HEIGHT - 1)], fill="white")

        # Right: detection count (dominant)
        val = str(triggers)
        self._txt_r(draw, 0, val, SZ_LARGE)
        self._txt_r(draw, 19, "detections", SZ_SMALL)

    # ── Page 2: Last bird ──────────────────────────────────────────────────────
    # Shows: species name (large, truncated) + confidence (large right) + time ago
    #
    #  Robin                89%
    #  American              2m ago
    def _draw_last_bird(self, draw) -> None:
        with self._lock:
            det = self._last_detection
            dt  = self._last_detect_time

        if not det:
            self._txt_c(draw, 5, "No detections", SZ_MEDIUM)
            self._txt_c(draw, 20, "yet", SZ_SMALL)
            return

        species = det["species"]
        conf    = f"{det['confidence']*100:.0f}%"

        # Split long names: "American Robin" → ["American", "Robin"]
        parts = species.split()
        if len(parts) >= 2 and len(species) > 14:
            line1 = parts[-1][:12]       # last word (usually shortest — "Robin")
            line2 = " ".join(parts[:-1])[:14]  # rest — "American"
        else:
            line1 = species[:12]
            line2 = ""

        # Time ago
        ago = ""
        if dt:
            secs = int((datetime.now() - dt).total_seconds())
            if secs < 60:
                ago = f"{secs}s ago"
            elif secs < 3600:
                ago = f"{secs // 60}m ago"
            else:
                ago = f"{secs // 3600}h ago"

        # Draw: species name left (large), confidence right (large)
        self._txt(draw, 1, 0, line1, SZ_LARGE)
        self._txt_r(draw, 0, conf, SZ_LARGE)
        if line2:
            self._txt(draw, 1, 18, line2, SZ_SMALL)
        if ago:
            self._txt_r(draw, 20, ago, SZ_SMALL)

    # ── Page 3: System ─────────────────────────────────────────────────────────
    # Shows: CPU temp (large left) + uptime (large right)
    #
    #  41°          3d 4h
    #  CPU          uptime
    def _draw_system(self, draw) -> None:
        with self._lock:
            s = self._stats
        cpu  = s.get("cpu_temp_c")
        up   = s.get("uptime_seconds", 0)

        temp_str = f"{cpu:.0f}\u00b0" if cpu is not None else "--\u00b0"
        up_str   = _fmt_uptime(up)

        # Left column: CPU temp
        self._txt(draw, 1, 0, temp_str, SZ_LARGE)
        self._txt(draw, 1, 19, "CPU", SZ_SMALL)

        # Middle separator
        draw.line([(63, 0), (63, OLED_HEIGHT - 1)], fill="white")

        # Right column: uptime
        self._txt_r(draw, 0, up_str, SZ_LARGE)
        self._txt_r(draw, 19, "uptime", SZ_SMALL)

    # ── Page 4: Uploads ────────────────────────────────────────────────────────
    # Shows: uploaded count (large) + queue + MB sent
    #
    #  23             Q: 0
    #  uploaded    4.2 MB
    def _draw_uploads(self, draw) -> None:
        with self._lock:
            s = self._stats
        ok    = s.get("uploads_succeeded", 0)
        fail  = s.get("uploads_failed_permanent", 0)
        queue = s.get("upload_queue_size", 0)
        mb    = s.get("bytes_uploaded", 0) / (1024 * 1024)

        # Left: uploaded count
        self._txt(draw, 1, 0, str(ok), SZ_LARGE)
        self._txt(draw, 1, 19, f"up  {fail}fail", SZ_SMALL)

        # Separator
        draw.line([(63, 0), (63, OLED_HEIGHT - 1)], fill="white")

        # Right: queue + MB
        self._txt_r(draw, 0,  f"Q:{queue}", SZ_MEDIUM)
        self._txt_r(draw, 19, f"{mb:.1f}MB", SZ_SMALL)

    # ── Page 5: Disk ───────────────────────────────────────────────────────────
    # Shows: free space (large left) + used % (large right)
    #
    #  117G          62%
    #  free          used
    #
    # disk_free_gb/disk_used_pct were already being computed in _collect_stats()
    # but were never actually wired into any page — this was the gap.
    def _draw_disk(self, draw) -> None:
        with self._lock:
            s = self._stats
        free_gb  = s.get("disk_free_gb")
        used_pct = s.get("disk_used_pct")

        free_str = f"{free_gb:.0f}G" if free_gb is not None else "--"
        pct_str  = f"{used_pct:.0f}%" if used_pct is not None else "--"

        # Left column: free space
        self._txt(draw, 1, 0, free_str, SZ_LARGE)
        self._txt(draw, 1, 19, "free", SZ_SMALL)

        # Middle separator
        draw.line([(63, 0), (63, OLED_HEIGHT - 1)], fill="white")

        # Right column: percent used
        self._txt_r(draw, 0, pct_str, SZ_LARGE)
        self._txt_r(draw, 19, "used", SZ_SMALL)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    if s < 60:    return f"{s}s"
    if s < 3600:  return f"{s // 60}m"
    if s < 86400:
        h, m = divmod(s // 60, 60)
        return f"{h}h{m:02d}"
    d, rem = divmod(s, 86400)
    return f"{d}d{rem // 3600}h"


def _get_mem_used_mb() -> Optional[float]:
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    info[parts[0].rstrip(":")] = int(parts[1])
        return round((info.get("MemTotal", 0) - info.get("MemAvailable", 0)) / 1024, 1)
    except Exception:
        return None


def _get_cpu_temp() -> Optional[float]:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except Exception:
        return None


def build_stats_for_display(watcher) -> Dict[str, Any]:
    """Collect flat stats dict from all BirdWatcher components."""
    import shutil
    stats: Dict[str, Any] = {}
    try:
        ds = watcher._detector.stats
        stats["triggers"]          = ds.get("triggers", 0)
        stats["windows_analyzed"]  = ds.get("windows_analyzed", 0)
    except Exception:
        pass
    try:
        rs = watcher._recorder.stats
        stats["recordings_completed"]   = rs.get("recordings_completed", 0)
        stats["total_seconds_recorded"] = rs.get("total_seconds_recorded", 0.0)
    except Exception:
        pass
    try:
        us = watcher._uploader.stats
        stats["uploads_succeeded"]        = us.get("uploads_succeeded", 0)
        stats["uploads_failed_permanent"] = us.get("uploads_failed_permanent", 0)
        stats["bytes_uploaded"]           = us.get("bytes_uploaded", 0)
        stats["upload_queue_size"] = (
            watcher._upload_queue.qsize() if hasattr(watcher, "_upload_queue") else 0
        )
    except Exception:
        pass
    try:
        sync = watcher._sync
        stats["paired"]                 = sync.is_paired()
        stats["config_version"]         = sync._server_config_version
        stats["config_applied_version"] = sync._applied_version
        stats["backend"]                = sync._backend
        stats["coral_form"]             = sync._coral_form
        stats["mic_count"]              = sync._mic_count
    except Exception:
        pass
    try:
        if watcher._start_time:
            stats["uptime_seconds"] = (
                datetime.utcnow() - watcher._start_time
            ).total_seconds()
    except Exception:
        pass
    stats["cpu_temp_c"]  = _get_cpu_temp()
    stats["mem_used_mb"] = _get_mem_used_mb()
    try:
        rec_dir = watcher.config.get("recording", {}).get("output_dir", "/")
        usage = shutil.disk_usage(rec_dir)
        stats["disk_free_gb"] = round(usage.free / (1024 ** 3), 2)
        stats["disk_used_pct"] = round(usage.used / usage.total * 100, 1) if usage.total else None
    except Exception:
        pass
    return stats
