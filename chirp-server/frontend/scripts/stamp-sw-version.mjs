#!/usr/bin/env node
/**
 * Stamps the project's canonical version (from the VERSION file in
 * chirp-server/ — the same file the Python backend reads via
 * Settings._read_version() in app/config.py) into BOTH public/sw.js's
 * CACHE constant and this package's own package.json version field, so
 * every place a version number is displayed or used for cache-busting
 * traces back to the exact same single file, with zero manual
 * keep-multiple-copies-in-sync editing required.
 *
 * History of why this matters: there were originally three independent
 * copies of "the version" — package.json's own version field, a
 * hardcoded literal string in main.py's FastAPI(version=...) constructor
 * (despite a comment claiming it was "updated by VERSION file at
 * runtime," which was never actually true), and this script reading
 * package.json. The FastAPI literal is what /health actually returns,
 * which is what Settings.jsx's VersionBadge displays — so bumping
 * package.json alone never actually updated what a real person saw in
 * the UI. VERSION was first moved to the repo root to fix that, which
 * broke `docker build` (the backend stage's `COPY VERSION ./VERSION`
 * resolves against the build context, which is chirp-server/, not the
 * repo root — a file one level above is invisible to it). VERSION was
 * then moved into chirp-server/ to fix THAT, which still broke the
 * separate frontend-builder stage, since that stage only ever receives
 * `COPY frontend/ .` and never had a VERSION file copied into it at all
 * until the Dockerfile gained its own explicit `COPY VERSION
 * ./VERSION` for this stage too. This script now searches multiple
 * candidate paths (see versionCandidates below) rather than assuming a
 * single fixed depth, specifically because guessing one depth has
 * already been wrong twice for two different real reasons.
 */
import { readFileSync, writeFileSync, existsSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))
// Two real layouts this needs to handle, not one — a single hardcoded
// relative-path depth was tried twice already and was wrong both times
// for exactly this reason:
//   1. Inside the Docker frontend-builder stage: VERSION is explicitly
//      copied to /frontend/VERSION by the Dockerfile (one level up from
//      this script, at frontend/scripts/../VERSION).
//   2. A developer running `npm run build` directly from a local
//      chirp-server/frontend/ checkout: VERSION lives at
//      chirp-server/VERSION (two levels up from this script).
// Mirrors the same multi-candidate, first-match-wins pattern
// app/config.py's _read_version() already uses for the identical reason
// — the canonical file's real location relative to "here" genuinely
// differs between a built container and a dev checkout, and trying to
// guess a single "correct" depth has now broken two builds in a row.
const versionCandidates = [
  join(__dirname, '..', 'VERSION'),       // frontend/scripts/ -> frontend/  (Docker stage)
  join(__dirname, '..', '..', 'VERSION'), // frontend/scripts/ -> frontend/ -> chirp-server/  (local dev)
]
const pkgPath = join(__dirname, '..', 'package.json')
const swPath = join(__dirname, '..', 'public', 'sw.js')

const versionPath = versionCandidates.find(p => existsSync(p))
if (!versionPath) {
  console.error(`stamp-sw-version: could not find VERSION at any of: ${versionCandidates.join(', ')}`)
  process.exit(1)
}

let version
try {
  version = readFileSync(versionPath, 'utf-8').trim()
} catch (e) {
  console.error(`stamp-sw-version: could not read canonical VERSION file at ${versionPath}: ${e.message}`)
  process.exit(1)
}
if (!version) {
  console.error(`stamp-sw-version: VERSION file at ${versionPath} is empty`)
  process.exit(1)
}

// 1. Stamp sw.js's cache name
let sw = readFileSync(swPath, 'utf-8')
const CACHE_PATTERN = /const CACHE = '[^']*'/
if (!CACHE_PATTERN.test(sw)) {
  console.error(`stamp-sw-version: could not find "const CACHE = '...'" in ${swPath} — sw.js may have been restructured; update this script's regex to match.`)
  process.exit(1)
}
sw = sw.replace(CACHE_PATTERN, `const CACHE = 'chirp-v${version}'`)
writeFileSync(swPath, sw)
console.log(`stamp-sw-version: sw.js CACHE set to 'chirp-v${version}'`)

// 1b. Version the icon URLs (?v=VERSION) in index.html and manifest.json.
// Browsers and home-screen installs key icons by URL, so same-named files
// keep showing an old logo; a new URL per release is what makes Chrome
// and Android pick up a changed icon. The manifest's own URL stays fixed:
// Android has tied installed apps to it, and the server sends it no-cache.
const ICON_URL = /(\/(?:favicon\.ico|favicon\.svg|icon-192\.png|icon-512\.png|apple-touch-icon\.png|logo\.svg))(\?v=[^"']*)?(["'])/g
for (const rel of ['index.html', join('public', 'manifest.json')]) {
  const path = join(__dirname, '..', rel)
  if (!existsSync(path)) continue
  const before = readFileSync(path, 'utf-8')
  const after = before.replace(ICON_URL, `$1?v=${version}$3`)
  if (after !== before) writeFileSync(path, after)
  console.log(`stamp-sw-version: ${rel} icon URLs set to ?v=${version}`)
}

// 2. Keep package.json's version field in sync too, so anything that
// reads it directly (npm tooling, this script's own next run) doesn't
// become a fourth stale copy.
const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'))
if (pkg.version !== version) {
  pkg.version = version
  writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n')
  console.log(`stamp-sw-version: package.json version set to '${version}'`)
}

// 3. Verify the What's New popup's version matches — this is content a
// person actually reads (see lib/whatsNew.js), so it can't be auto-
// stamped the way sw.js/package.json are above; someone has to write
// what's actually new. But a version bump shipping with a stale popup
// version means either the popup silently never shows for this release,
// or it shows describing an OLDER release's content — both wrong, and
// both easy to forget by hand across many small releases. Failing the
// build here forces updating whatsNew.js's content alongside the version
// bump, not just remembering to eventually get around to it.
const whatsNewPath = join(__dirname, '..', 'src', 'lib', 'whatsNew.js')
if (existsSync(whatsNewPath)) {
  const whatsNewSrc = readFileSync(whatsNewPath, 'utf-8')
  const versionMatch = whatsNewSrc.match(/version:\s*'([^']*)'/)
  const whatsNewVersion = versionMatch ? versionMatch[1] : null
  if (whatsNewVersion !== version) {
    console.error(
      `stamp-sw-version: lib/whatsNew.js's version ('${whatsNewVersion}') does not match ` +
      `the canonical VERSION ('${version}'). Update whatsNew.js's content for this release ` +
      `(not just its version field) before building — see the file's own comments for what ` +
      `belongs there.`
    )
    process.exit(1)
  }
  console.log(`stamp-sw-version: whatsNew.js version confirmed in sync ('${version}')`)
} else {
  console.warn(`stamp-sw-version: could not find whatsNew.js at ${whatsNewPath} — skipping its version check`)
}
