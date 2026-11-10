// Chirp Lite inside the Chirp iPhone app (Account → Chirp Lite): hide the
// launch screen and match the status bar to Lite's light or dark theme.
// The native helpers load as their own chunk, so the web first load is unchanged.
export function setupAppShell() {
  if (!window.Capacitor?.isNativePlatform?.()) return
  import('../native').then(({ native }) => {
    native.splash.hide(0)
    const dark = window.matchMedia?.('(prefers-color-scheme: dark)')
    const apply = () => (dark?.matches ? native.status.setDark() : native.status.setLight())
    apply()
    dark?.addEventListener?.('change', apply)
  }).catch(() => {})
}
