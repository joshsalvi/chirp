// A short in-memory log of what went wrong in this copy of the app, for the
// diagnostics export (lib/appDiagnostics.js): failed API calls, script
// errors and What's New popups. Nothing here leaves the device unless the
// person exports it.
const MAX = 40
const entries = []
let installed = false

export function note(kind, detail) {
  entries.push({ at: new Date().toISOString(), kind, detail: String(detail ?? '').slice(0, 300) })
  if (entries.length > MAX) entries.shift()
}

export function recent() { return entries.slice() }

export function installErrorHooks() {
  if (installed || typeof window === 'undefined') return
  installed = true
  window.addEventListener('error', e => note('script error', `${e.message || e.type} ${e.filename ? `(${e.filename.split('/').pop()}:${e.lineno})` : ''}`))
  window.addEventListener('unhandledrejection', e => note('unhandled promise', e.reason?.message || e.reason))
}

// What's New: when it showed and why, kept across launches (last 10) to
// answer "why did I see it again?".
const WN_KEY = 'chirp_whats_new_log'
export function noteWhatsNew(info) {
  try {
    const list = JSON.parse(localStorage.getItem(WN_KEY) || '[]')
    list.push({ at: new Date().toISOString(), ...info })
    localStorage.setItem(WN_KEY, JSON.stringify(list.slice(-10)))
  } catch { /* storage off */ }
}
export function whatsNewLog() {
  try { return JSON.parse(localStorage.getItem(WN_KEY) || '[]') } catch { return [] }
}
