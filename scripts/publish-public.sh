#!/usr/bin/env bash
# Publish the public copy of a Chirp release (run on the Mac).
#
#   scripts/publish-public.sh [path/to/chirp.zip] [repo-dir]
#
# Defaults: ~/Developer/Chirp/chirp.zip → ~/Documents/Github.nosync/chirp-public
# (a clone of github.com/joshsalvi/chirp, public). The private history lives
# in joshsalvi/chirp-private (publish-github.sh). This copy leaves out the
# patent draft, App Store and TestFlight tooling, and the working device
# config, swaps in chirp-device/config.yaml.public, and refuses to push if
# anything that looks like a key is left.
set -euo pipefail
ZIP="${1:-$HOME/Developer/Chirp/chirp.zip}"
REPO="${2:-$HOME/Documents/Github.nosync/chirp-public}"
[[ -f "$ZIP" ]] || { echo "No zip at $ZIP" >&2; exit 1; }
[[ -d "$REPO/.git" ]] || { echo "No git checkout at $REPO" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
unzip -q "$ZIP" -d "$TMP/src"
VERSION="$(cat "$TMP/src/chirp-server-instances/VERSION")"
S="$TMP/src"

# Private or internal files.
rm -rf "$S"/PATENT_APPLICATION* "$S"/*/PATENT_APPLICATION* "$S"/patent_figures \
       "$S"/*CHIRP_HANDOFF* "$S"/AUDIT_REPORT.md "$S"/GITHUB_SETUP.md \
       "$S"/docs/APP_REVIEW_RESPONSE.md "$S"/docs/app-store-metadata.json \
       "$S"/scripts/asc.py "$S"/scripts/testflight-auto.* "$S"/scripts/publish-github.sh \
       "$S"/scripts/clean-mac-duplicates.sh
find "$S" \( -name '.DS_Store' -o -name '*.p8' -o -name '.env' -o -name '*.db' \) -delete
find "$S" -type f \( -name "* [0-9].*" -o -name "* [0-9][0-9].*" -o -name "* [0-9]" \) -delete
cp "$S/chirp-device/config.yaml.public" "$S/chirp-device/config.yaml"

# Refuse anything that looks like a credential.
if grep -rInE 'chirp-[A-Za-z0-9_-]{40,}|chirprelay_[A-Za-z0-9_-]{20,}|tskey-[a-z]+-[A-Za-z0-9]+|BEGIN (EC |RSA )?PRIVATE KEY-----[A-Za-z0-9+/=[:space:]]{20}|gh[opsu]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|sk-(ant-)?[A-Za-z0-9_-]{30,}|xox[abp]-[0-9A-Za-z-]{20,}|auth_key: "[0-9a-f]{20,}"' \
     --exclude-dir=node_modules "$S"; then
  echo "Possible secret above; nothing published." >&2
  exit 1
fi

cd "$REPO"
# The old name redirects to the private repo, so check where origin lands.
read -r VIS NAME < <(gh repo view "$(git remote get-url origin)" --json visibility,nameWithOwner -q '.visibility+" "+.nameWithOwner')
if [[ "$VIS" != "PUBLIC" || "$NAME" != "joshsalvi/chirp" ]]; then
  echo "origin is $NAME ($VIS), not the public joshsalvi/chirp; nothing published." >&2
  exit 1
fi
git fetch -q origin main 2>/dev/null && git reset -q --soft origin/main 2>/dev/null || true
rsync -a --delete --exclude '.git' "$S"/ "$REPO"/
git add -A
if git diff --cached --quiet; then
  echo "Public repo already at $VERSION."
  exit 0
fi
git commit -q -m "$VERSION"
git push -q origin HEAD:main
echo "Published public $VERSION ($(git rev-parse --short HEAD)) to $(git remote get-url origin)"
