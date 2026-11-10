// Fails the build when a first page load gets heavier than its budget
// (npm postbuild hook). Counts what each page loads before it can draw:
// its scripts, modulepreloads and stylesheets, gzipped.
// Raise a budget on purpose, in the same change that needs it.
import fs from 'fs'
import path from 'path'
import zlib from 'zlib'

const BUDGETS = {
  'index.html': { js: 130, css: 25 },   // Chirp. 0.5.18.a: 112.6 and 21.3
  'lite.html': { js: 75, css: 10 },     // Chirp Lite. 0.5.19.a: see the build log
}
const dist = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../dist')
let over = false
for (const [page, budget] of Object.entries(BUDGETS)) {
  const file = path.join(dist, page)
  if (!fs.existsSync(file)) { console.error(`[bundle-budget] ${page} missing`); over = true; continue }
  const html = fs.readFileSync(file, 'utf8')
  const files = new Set([...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.(?:js|css))"/g)].map(m => m[1]))
  const totals = { js: 0, css: 0 }
  const rows = []
  for (const f of files) {
    const gz = zlib.gzipSync(fs.readFileSync(path.join(dist, f)), { level: 9 }).length / 1024
    totals[f.endsWith('.css') ? 'css' : 'js'] += gz
    rows.push(`${gz.toFixed(1).padStart(7)} kB  ${f}`)
  }
  console.log(`[bundle-budget] ${page} first load (gzip):\n` + rows.join('\n'))
  for (const k of Object.keys(budget)) {
    const line = `[bundle-budget] ${page} ${k}: ${totals[k].toFixed(1)} kB of ${budget[k]} kB`
    if (totals[k] > budget[k]) { over = true; console.error(line + ' — over budget') } else console.log(line)
  }
}
if (over && process.env.BUNDLE_BUDGET !== 'warn') process.exit(1)
