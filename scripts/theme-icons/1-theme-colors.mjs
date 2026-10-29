import { chromium } from '/opt/node-tools/node_modules/playwright/index.mjs'
import fs from 'fs'
const css = fs.readFileSync('/home/claude/w/chirp-server-instances/frontend/dist/assets/index-MPEIKAWK.css','utf8')
const ids = ['forest','midnight','dawn','ocean','ember','slate','sage','dusk','sand','arctic','contrast','paper','mono','terminal','plate','oscilloscope','aviary','cornell','fieldnotebook','dracula','nexrad','mothtrap','migration','roost','echocave','spectrogram']
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' })
const p = await b.newPage()
await p.setContent('<html><head><style>'+css+'</style></head><body></body></html>')
const out = {}
for (const id of ids) {
  out[id] = await p.evaluate(id => { document.documentElement.setAttribute('data-theme', id); const cs = getComputedStyle(document.documentElement); const g = k => cs.getPropertyValue(k).trim(); return { bg: g('--bg-panel'), base: g('--bg-base'), text: g('--text-primary'), a300: g('--accent-300'), a400: g('--accent-400'), a500: g('--accent-500'), a600: g('--accent-600'), a700: g('--accent-700') } }, id)
}
fs.writeFileSync('vars.json', JSON.stringify(out, null, 1))
console.log(Object.entries(out).map(([k,v])=>k+' '+JSON.stringify(v)).join('\n'))
await b.close()
