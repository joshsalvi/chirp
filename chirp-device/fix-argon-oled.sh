#!/usr/bin/env bash
# =============================================================================
# Fix: Hand the OLED over from the Argon ONE's own software to Chirp
#
# Run this on an ALREADY-INSTALLED Chirp device if the OLED is still showing
# the Argon ONE's default screens (IP address / CPU temp / etc.) instead of
# Chirp's own pages. This is the same fix install.sh now applies automatically
# on fresh installs (as of this version) — this script is for devices set up
# before that, so a full reinstall isn't needed.
#
# What this does and why it's safe:
#   The Argon ONE v5 Industria case's own setup script installs
#   "argononed.service", a daemon that controls both the OLED and the case's
#   physical power button. It fights Chirp's display.py for control of the
#   same screen and tends to win, so Chirp's custom pages never actually show.
#
#   For the Argon ONE v5 specifically, the fan is controlled by the Pi's own
#   kernel thermal governor, NOT by argononed over I2C (that's only true of
#   the older v1-v3 Argon ONE cases) — so stopping this service does NOT
#   affect cooling.
#
#   Trade-off: the case's physical power button (press to reboot/shutdown)
#   will stop working, since that's also handled by this daemon. You can
#   still shut down safely via SSH ("sudo shutdown now") or the systemd
#   service. Chirp's own GPIO 27 OLED page-button is unaffected either way
#   (a separate pin, handled entirely by display.py, nothing to do with
#   argononed).
#
# Usage:
#   chmod +x fix-argon-oled.sh
#   ./fix-argon-oled.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Hand the OLED over to Chirp from Argon ONE's daemon    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

ARGON_SERVICE=""
for candidate in argononed argoneon; do
    if systemctl list-unit-files 2>/dev/null | grep -q "^${candidate}\.service"; then
        ARGON_SERVICE="${candidate}"
        break
    fi
done

if [ -z "${ARGON_SERVICE}" ]; then
    info "No Argon ONE OLED service (argononed/argoneon) found on this system."
    info "If the OLED is still showing the wrong content, it's not this — check:"
    info "  sudo systemctl status chirp"
    info "  journalctl -u chirp -f"
    exit 0
fi

info "Found ${ARGON_SERVICE}.service — currently $(systemctl is-active "${ARGON_SERVICE}" 2>/dev/null || echo unknown)."
warn "About to stop and disable it. Trade-off: the case's physical power"
warn "button (press to reboot/shutdown) will stop working. Cooling is NOT"
warn "affected — the Argon ONE v5's fan is controlled by the Pi's kernel"
warn "thermal governor, not by this daemon."
echo ""
read -p "Continue? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    info "Cancelled — no changes made."
    exit 0
fi

sudo systemctl stop "${ARGON_SERVICE}"
sudo systemctl disable "${ARGON_SERVICE}"
success "${ARGON_SERVICE}.service stopped and disabled."

info "Restarting Chirp's own display so it takes the OLED immediately..."
if systemctl list-unit-files 2>/dev/null | grep -q "^chirp-device\.service"; then
    sudo systemctl restart chirp-device
    success "chirp-device.service restarted — the OLED should now show Chirp's pages."
else
    warn "chirp-device.service not found — restart however you normally run Chirp"
    warn "(e.g. 'python main.py') for the display change to take effect."
fi

echo ""
success "Done. The OLED is now under Chirp's sole control."
