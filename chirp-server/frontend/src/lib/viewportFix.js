// iPhone Home Screen app viewport fix (0.5.10.n-q).
//
// iOS 26.1+ / 27 (WebKit bug 301994) lay out a translucent Home Screen app
// one status bar short and pin it to the top of the screen: on iOS 27.0.1
// the page is 812 of 874 pt, drawn from y=0 under the status-bar blur, with
// an empty 62 pt strip at the bottom (client-diag from the phone). The
// page is the right size, just in the wrong place, so shift it down by the
// shortfall: html.vp-shift translates <body>, which also carries the fixed
// header and bottom bar with it.
//
// Reports the numbers once per launch to POST /api/v1/diagnostics/client.

let reported = false
let settled = false   // true from the 500 ms check on

function topInset() {
  const probe = document.createElement('div')
  probe.style.cssText = 'position:fixed;top:0;left:0;width:1px;visibility:hidden;pointer-events:none;padding-top:env(safe-area-inset-top,0px)'
  document.body.appendChild(probe)
  const v = parseFloat(getComputedStyle(probe).paddingTop) || 0
  probe.remove()
  return v
}

export function viewportShift({ standalone, portrait, screenW, screenH, innerH, top }) {
  if (!standalone || !portrait) return 0
  const full = Math.max(screenW, screenH)
  const gap = Math.round(full - innerH)
  // Drawn under the status bar (top inset reported) and short by about one
  // status bar. The keyboard and split views shrink the page far more.
  if (top < 20 || gap < 16 || gap > 120) return 0
  return gap
}

const firstH = {}   // orientation -> page height first seen (before the shift)

function report(data) {
  if (reported) return
  reported = true
  try {
    const token = localStorage.getItem('chirp_token')
    fetch('/api/v1/diagnostics/client', {
      method: 'POST', keepalive: true,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
      body: JSON.stringify({ kind: 'viewport', ...data }),
    }).catch(() => {})
  } catch { /* diagnostics only */ }
}

function apply() {
  try {
    const root = document.documentElement
    const standalone = !!(window.navigator.standalone || window.Capacitor?.isNativePlatform?.())
    const portrait = window.matchMedia('(orientation: portrait)').matches
    const key = portrait ? 'p' : 'l'
    firstH[key] ??= window.innerHeight
    const input = {
      standalone, portrait,
      screenW: window.screen.width, screenH: window.screen.height,
      innerH: firstH[key], top: topInset(),
    }
    const shift = viewportShift(input)
    root.style.setProperty('--vp-shift', `${shift}px`)
    root.classList.toggle('vp-shift', shift > 0)
    if (standalone && (shift || settled)) report({ ...input, shift, liveInnerH: window.innerHeight, ua: navigator.userAgent })
  } catch { /* never block the app over layout */ }
}

export function installViewportFix() {
  if (typeof window === 'undefined') return
  try { localStorage.removeItem('chirp_vp_offset') } catch {}   // 0.5.10.o/p
  if (document.body) apply()
  else document.addEventListener('DOMContentLoaded', apply, { once: true })
  window.addEventListener('orientationchange', () => setTimeout(apply, 300))
  document.addEventListener('visibilitychange', () => { if (!document.hidden) setTimeout(apply, 100) })
  setTimeout(() => { settled = true; apply() }, 500)
}
