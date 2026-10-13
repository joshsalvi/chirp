/**
 * iOS app glue, mounted once in App.jsx. Does nothing in a browser.
 *  - hides the launch screen as soon as the app has rendered (the config's
 *    launchShowDuration is only a ceiling for a slow or failed load)
 *  - status bar icons follow the theme: light icons on dark themes, dark
 *    icons on light ones
 *  - back from the background after a server update: reloads so the new
 *    version runs instead of the one still in memory. Uses @capacitor/app's
 *    appStateChange (iOS's own active/background events, which fire even
 *    when the web view's timers were frozen); builds without that plugin
 *    fall back to the page's visibilitychange.
 *  - on every return to the foreground, dispatches "chirp-resume" so open
 *    pages can refresh what may have gone stale
 */
import { useEffect } from 'react'
import { native, isNative } from '../native'

// Relative luminance of a CSS color (rgb()/#hex) as the browser computes it.
function luminance(color) {
  const m = (color || '').match(/\d+(\.\d+)?/g)
  if (!m || m.length < 3) return 0
  const [r, g, b] = m.slice(0, 3).map(v => {
    const c = Number(v) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function syncStatusBar() {
  const probe = document.createElement('div')
  probe.style.cssText = 'position:absolute;visibility:hidden;background:var(--bg-panel)'
  document.body.appendChild(probe)
  const bg = getComputedStyle(probe).backgroundColor
  probe.remove()
  if (luminance(bg) > 0.4) native.status.setLight()
  else native.status.setDark()
}

// Resume check: at most once every 10 minutes of background time.
const RESUME_CHECK_MS = 10 * 60 * 1000

export default function AppNative({ version }) {
  useEffect(() => {
    if (!isNative()) return
    native.splash.hide(0)
    syncStatusBar()
    window.addEventListener('chirp-theme-changed', syncStatusBar)

    let hiddenAt = 0
    const onBackground = () => { hiddenAt = Date.now() }
    const onForeground = async () => {
      window.dispatchEvent(new Event('chirp-resume'))
      if (!hiddenAt || Date.now() - hiddenAt < RESUME_CHECK_MS) return
      hiddenAt = 0
      try {
        const r = await fetch('/api/v1/health', { cache: 'no-store' })
        const { version: live } = await r.json()
        if (live && version && live !== version) window.location.reload()
      } catch { /* offline: keep the current page */ }
    }

    let removeAppListener = null
    let cancelled = false
    const onVisibility = () => (document.visibilityState === 'hidden' ? onBackground() : onForeground())
    if (window.Capacitor?.isPluginAvailable?.('App')) {
      import('@capacitor/app').then(({ App }) =>
        App.addListener('appStateChange', ({ isActive }) => (isActive ? onForeground() : onBackground())),
      ).then(h => {
        if (cancelled) h?.remove?.()
        else removeAppListener = () => h?.remove?.()
      }).catch(() => document.addEventListener('visibilitychange', onVisibility))
    } else {
      document.addEventListener('visibilitychange', onVisibility)
    }
    return () => {
      cancelled = true
      window.removeEventListener('chirp-theme-changed', syncStatusBar)
      document.removeEventListener('visibilitychange', onVisibility)
      removeAppListener?.()
    }
  }, [version])
  return null
}
