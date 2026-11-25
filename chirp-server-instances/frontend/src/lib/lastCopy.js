// The Dashboard's last good data, kept per person and site in
// localStorage, so opening the app paints right away and then refreshes.
// Removed on sign-out (lib/token.js clear).
import { tokenStore } from './token'

const PREFIX = 'chirp-last:'

function key(name) {
  const c = tokenStore.claims()
  if (!c?.sub) return null
  return `${PREFIX}${c.sub}:${c.active_instance_id || ''}:${name}`
}

// `sameDay`: only a copy saved today counts (for "today" screens).
export function lastCopy(name, fallback = null, { sameDay = false } = {}) {
  try {
    const k = key(name)
    const v = k && JSON.parse(localStorage.getItem(k) || 'null')
    if (!v || !('data' in v)) return fallback
    if (sameDay && new Date(v.at).toDateString() !== new Date().toDateString()) return fallback
    return v.data
  } catch {
    return fallback
  }
}

export function keepCopy(name, data) {
  try {
    const k = key(name)
    if (k && data != null) localStorage.setItem(k, JSON.stringify({ at: Date.now(), data }))
  } catch { /* storage full or blocked: the page still works */ }
  return data
}
