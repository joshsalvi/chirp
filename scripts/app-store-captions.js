// Captioned App Store screenshots (6.9-inch iPhone, 1320 x 2868): headline,
// a line, and the screen in a phone frame.
//   npm i @fontsource/lora@5.1.0 @fontsource/dm-sans@5.1.0   (in the folder you run from)
//   node app-store-captions.js <plain screenshots dir> <out dir>
// Plain screenshots come from monitor/chirp-ss-4.py (app-store/raw-<date>).
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const SRC = process.argv[2];
const OUT = process.argv[3] || 'out';
fs.mkdirSync(OUT, { recursive: true });
const F = 'node_modules/@fontsource';
const font = (fam, file, w) => `@font-face{font-family:'${fam}';font-weight:${w};src:url(data:font/woff2;base64,${fs.readFileSync(path.join(F, file)).toString('base64')}) format('woff2')}`;
const FONTS = font('Lora', 'lora/files/lora-latin-600-normal.woff2', 600) + font('DM Sans', 'dm-sans/files/dm-sans-latin-400-normal.woff2', 400) + font('DM Sans', 'dm-sans/files/dm-sans-latin-500-normal.woff2', 500);
const SHOTS = [
  ['1-standard.png', 'Your yard, today', 'The latest bird and its song, at a glance.', 'Try the demo · no account needed'],
  ['2-standard-birds.png', 'Every bird, by photo', "Today's birds and how often each one sang."],
  ['1-dashboard.png', "Know who's singing", 'Live detections, trends and your journal.'],
  ['2-recording.png', 'See every call', 'Spectrograms, playback, every bird in the clip.'],
  ['8-live-detect.png', 'Name birds anywhere', 'Live Detect listens through your iPhone.'],
  ['3-life-list.png', 'A life list that builds itself', 'Counts, firsts and streaks for every bird.'],
  ['4-bird-profile.png', 'Meet each bird', 'Photos, songs, range maps and when it visits.'],
  ['5-field-guide.png', "What's around right now", 'Birds likely near you this month, from eBird.'],
  ['6-notifications.png', 'Never miss a newcomer', 'New species, watched birds and daily journals.'],
  ['7-my-notifications.png', 'Alerts your way', 'Choose which birds and moments reach you.'],
];
const html = (img, h, sub, pill) => `<!doctype html><html><head><style>${FONTS}
*{margin:0;box-sizing:border-box}
html,body{width:1320px;height:2868px;overflow:hidden}
body{background:radial-gradient(ellipse 1100px 820px at 50% 0%,rgba(212,175,55,.30),rgba(212,175,55,0) 70%),linear-gradient(180deg,#14200f 0%,#0b130a 55%,#070c06 100%);
 display:flex;flex-direction:column;align-items:center;font-family:'DM Sans',sans-serif;color:#f4efe2}
h1{white-space:nowrap;font-family:'Lora',serif;font-weight:600;font-size:118px;letter-spacing:-1.5px;line-height:1.05;margin-top:150px;text-align:center;padding:0 70px}
p{font-size:52px;color:rgba(244,239,226,.72);margin-top:30px;text-align:center;padding:0 90px;line-height:1.25}
.pill{margin-top:38px;padding:18px 44px;border-radius:999px;background:#f2c230;color:#1b1a0e;font-weight:500;font-size:44px;box-shadow:0 10px 40px rgba(242,194,48,.35)}
.phone{position:absolute;top:${pill ? 640 : 560}px;width:1010px;border-radius:96px;padding:22px;background:#0c0f0b;
 border:3px solid rgba(255,255,255,.14);box-shadow:0 40px 120px rgba(0,0,0,.65),0 0 0 2px rgba(0,0,0,.6)}
.phone img{display:block;width:100%;border-radius:76px}
</style></head><body><h1>${h}</h1><p>${sub}</p>${pill ? `<div class="pill">${pill}</div>` : ''}
<div class="phone"><img src="data:image/png;base64,${fs.readFileSync(path.join(SRC, img)).toString('base64')}"></div></body></html>`;
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1320, height: 2868 }, deviceScaleFactor: 1 });
  for (const [img, h, sub, pill] of SHOTS) {
    await p.setContent(html(img, h, sub, pill), { waitUntil: 'load' });
    await p.evaluate(async () => {
      await document.fonts.ready
      const h = document.querySelector('h1'); let f = 118
      while (h.scrollWidth > 1200 && f > 80) { f -= 2; h.style.fontSize = f + 'px' }
    });
    await p.screenshot({ path: path.join(OUT, img) });
    console.log('ok', img);
  }
  await b.close();
})();
