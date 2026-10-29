import { chromium } from '/opt/node-tools/node_modules/playwright/index.mjs'
import fs from 'fs'
const V = JSON.parse(fs.readFileSync('vars.json','utf8'))
const L = JSON.parse(fs.readFileSync('logos.json','utf8'))
const k = 9.209, cx = 58.45, cy = 49.53
const inner = s => s.replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, '')
const lum = h => { const n = parseInt(h.slice(1),16); const c=[n>>16,(n>>8)&255,n&255].map(v=>{v/=255;return v<=0.03928?v/12.92:((v+0.055)/1.055)**2.4}); return 0.2126*c[0]+0.7152*c[1]+0.0722*c[2] }
function icon(id) {
  const v = V[id]
  let body
  if (id === 'forest') body = inner(L.__default).replaceAll('INK', '#f5efe6').replaceAll('"BG"', '"#0a160c"').replaceAll('B0', '#fdba74').replaceAll('B1', '#fb923c').replaceAll('B2', '#ea580c')
  else if (L[id]) body = inner(L[id])
  else {
    const light = lum(v.bg) > 0.4
    body = inner(L.__default).replaceAll('INK', v.text).replaceAll('"BG"', `"${v.bg}"`)
      .replaceAll('B0', light ? v.a500 : v.a300).replaceAll('B1', light ? v.a600 : v.a500).replaceAll('B2', v.a700)
  }
  const bg = id === 'forest' ? '#0a160c' : v.bg
  // var(--bg-panel) etc. inside themed logos resolve against this theme's colors
  const style = `--bg-panel:${v.bg};--bg-base:${v.base};--text-primary:${v.text};--accent-300:${v.a300};--accent-400:${v.a400};--accent-500:${v.a500};--accent-600:${v.a600}`
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024" style="${style}"><rect width="1024" height="1024" fill="${bg}"/><g transform="translate(${512 - cx*k} ${512 - cy*k}) scale(${k})">${body}</g></svg>`
}
fs.mkdirSync('out2', { recursive: true })
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' })
const p = await b.newPage({ viewport: { width: 1024, height: 1024 } })
for (const id of Object.keys(V)) {
  const s = icon(id)
  fs.writeFileSync(`out2/${id}.svg`, s)
  await p.setContent(`<html><body style="margin:0;background:#000">${s}</body></html>`)
  await p.screenshot({ path: `out2/${id}.png`, clip: { x: 0, y: 0, width: 1024, height: 1024 } })
}
await b.close()
console.log('done', Object.keys(V).length)
