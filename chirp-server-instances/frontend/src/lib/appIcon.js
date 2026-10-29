// Home Screen icon in the iPhone/iPad app: one icon per built-in theme
// (public/app-icons/ shows them; the app bundles the full-size ones).
// "keep" (the default) leaves the icon alone when the theme changes;
// "theme" follows the current theme; any other value is a theme id the
// person picked. Kept on this device only: each phone or iPad has its own
// Home Screen. Custom themes have no icon, so they keep the last one.
import { native } from '../native'
import { THEMES } from './theme'

const KEY = 'chirp_app_icon'

export function getIconChoice() {
  try { return localStorage.getItem(KEY) || 'keep' } catch { return 'keep' }
}

export function iconForTheme(themeId) {
  return THEMES.some(t => t.id === themeId) ? themeId : null
}

/** Picks an icon ('theme', 'keep' or a theme id) and applies it now. */
export async function setIconChoice(choice, currentTheme) {
  try { localStorage.setItem(KEY, choice) } catch {}
  if (choice === 'keep') return true
  const id = choice === 'theme' ? iconForTheme(currentTheme) : choice
  return id ? native.appIcon.set(id) : false
}

let installed = false
/** In the app, keeps the icon in step with the theme while "theme" is chosen. */
export function installIconSync(getTheme) {
  if (installed || typeof window === 'undefined') return
  installed = true
  native.appIcon.available().then(ok => {
    if (!ok) return
    const sync = (themeId) => {
      if (getIconChoice() !== 'theme') return
      const id = iconForTheme(themeId)
      if (id) native.appIcon.set(id)
    }
    window.addEventListener('chirp-theme-changed', e => sync(e.detail?.theme))
    sync(getTheme())
  })
}
