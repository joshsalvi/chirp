// Standard or Advanced dashboard. A missing or old value (simplified,
// detailed) counts as not chosen, so the picker shows once.
export const DASHBOARD_MODES = ['standard', 'advanced']

export function chosenMode(value) {
  return DASHBOARD_MODES.includes(value) ? value : null
}

// Sites without sign-in keep the choice in this browser.
const KEY = 'chirp:dashboard-mode'

export function localMode() {
  try { return chosenMode(localStorage.getItem(KEY)) } catch { return null }
}

export function setLocalMode(mode) {
  try { localStorage.setItem(KEY, mode) } catch { /* private mode: the picker shows again next time */ }
}
