// Fails the build when the first page load gets heavier than the budget
// (npm postbuild hook). Counts what dist/index.html loads before the app
// can draw: its scripts, modulepreloads and stylesheets, gzipped.
// Raise BUDGET_KB on purpose, in the same change that needs it.
import fs from 'fs'
import path from 'path'
import zlib from 'zlib'

const BUDGET_KB = { js: 130, css: 25 }   // 0.5.18.a: 112.6 and 21.3
const dist = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../dist')
const html = fs.readFileSync(path.join(dist, 'index.html'), 'utf8')
const files = [...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.(js|css))"/g)].map(m => [m[1], m[2]])
const totals = { js: 0, css: 0 }
const rows = []
const unique = [...new Map(files.map(([f, kind]) => [f, kind])).entries()]
for (const [f, kind] of unique) {
  const gz = zlib.gzipSync(fs.readFileSync(path.join(dist, f)), { level: 9 }).length / 1024
  totals[kind] += gz
  rows.push(`${gz.toFixed(1).padStart(7)} kB  ${f}`)
}
console.log('[bundle-budget] first load (gzip):\n' + rows.join('\n'))
let over = false
for (const k of Object.keys(BUDGET_KB)) {
  const line = `[bundle-budget] ${k}: ${totals[k].toFixed(1)} kB of ${BUDGET_KB[k]} kB`
  if (totals[k] > BUDGET_KB[k]) { over = true; console.error(line + ' — over budget') } else console.log(line)
}
if (over && process.env.BUNDLE_BUDGET !== 'warn') process.exit(1)
