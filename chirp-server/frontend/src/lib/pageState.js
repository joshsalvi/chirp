/**
 * Page state persistence — saves and restores scroll position, page number,
 * search terms, and filters when navigating away and back.
 *
 * Uses sessionStorage (cleared on tab close, not shared between tabs).
 */

const PREFIX = 'chirp_ps_'

export function savePageState(key, state) {
  try {
    sessionStorage.setItem(PREFIX + key, JSON.stringify({ ...state, _ts: Date.now() }))
  } catch {}
}

export function loadPageState(key, maxAgeMs = 1000 * 60 * 30) {
  try {
    const raw = sessionStorage.getItem(PREFIX + key)
    if (!raw) return null
    const state = JSON.parse(raw)
    if (Date.now() - (state._ts || 0) > maxAgeMs) {
      sessionStorage.removeItem(PREFIX + key)
      return null
    }
    return state
  } catch {
    return null
  }
}

export function clearPageState(key) {
  try { sessionStorage.removeItem(PREFIX + key) } catch {}
}

/** Save the current scroll position of a scrollable element ref */
export function saveScroll(key, el) {
  if (!el) return
  savePageState(key + '_scroll', { top: el.scrollTop })
}

/** Restore scroll position — call after data loads and DOM settles */
export function restoreScroll(key, el, delay = 50) {
  if (!el) return
  const state = loadPageState(key + '_scroll')
  if (!state) return
  setTimeout(() => { if (el) el.scrollTop = state.top }, delay)
}
