/**
 * Chirp — Capacitor Native Bridge
 *
 * Provides a unified API for native iOS features with graceful fallbacks
 * when running in a browser (PWA mode) or during development.
 *
 * Usage:
 *   import { native } from '../native'
 *   native.haptic.light()
 *   native.status.setStyle('dark')
 */

// ── Detection helper ──────────────────────────────────────────────────────────
export const isNative = () =>
  typeof window !== 'undefined' && !!(window.Capacitor?.isNativePlatform?.())

export const isIOS = () =>
  typeof window !== 'undefined' && window.Capacitor?.getPlatform?.() === 'ios'

// The iOS app appends "ChirpApp/1" to its user agent (capacitor.config.json),
// so the app is recognized even before the native bridge reports in.
export const isApp = () =>
  isNative() || (typeof navigator !== 'undefined' && /\bChirpApp\//.test(navigator.userAgent || ''))

// Test builds with the server picker add "ChirpApp/2" and start on a bundled
// page (ios-launcher/index.html) that chooses which Chirp server to open.
export const hasServerPicker = () =>
  typeof navigator !== 'undefined' && /\bChirpApp\/2\b/.test(navigator.userAgent || '')

export const openServerPicker = () => { window.location.href = 'capacitor://localhost/?pick=1' }

// Picker builds allow navigation to any host (so any server loads in the
// app), which would also keep plain links to other sites inside the app.
// Send those to Safari instead, as the release build does.
export function installExternalLinkGuard() {
  if (!hasServerPicker() || window.__chirpLinkGuard) return
  window.__chirpLinkGuard = true
  document.addEventListener('click', (e) => {
    const a = e.target?.closest?.('a[href]')
    if (!a || a.target === '_blank' || e.defaultPrevented) return
    let url
    try { url = new URL(a.href, window.location.href) } catch { return }
    if (!/^https?:$/.test(url.protocol) || url.origin === window.location.origin) return
    e.preventDefault()
    window.open(url.href, '_blank')
  }, true)
}

// A push relayed for another server carries that server's address; returns
// the full URL to open when it isn't the server this page is on.
export function otherServerUrl(data, path) {
  try {
    const origin = data?.server ? new URL(data.server).origin : ''
    return origin && origin !== window.location.origin ? origin + (path || '/notifications') : ''
  } catch { return '' }
}

// ── Haptics ───────────────────────────────────────────────────────────────────
let _haptics = null
async function getHaptics() {
  if (!isNative()) return null   // web: no vibrate() fallback
  if (_haptics) return _haptics
  try {
    const { Haptics, ImpactStyle, NotificationType } = await import('@capacitor/haptics')
    _haptics = { Haptics, ImpactStyle, NotificationType }
  } catch { _haptics = false }
  return _haptics
}

export const native = {
  /**
   * Haptic feedback — no-op in browser.
   * native.haptic.light()   — button tap, selection change
   * native.haptic.medium()  — action confirmation
   * native.haptic.heavy()   — destructive action
   * native.haptic.success() — detection arrived
   * native.haptic.error()   — failure
   */
  haptic: {
    light:   async () => { const h = await getHaptics(); if (h) await h.Haptics.impact({ style: h.ImpactStyle.Light }) },
    medium:  async () => { const h = await getHaptics(); if (h) await h.Haptics.impact({ style: h.ImpactStyle.Medium }) },
    heavy:   async () => { const h = await getHaptics(); if (h) await h.Haptics.impact({ style: h.ImpactStyle.Heavy }) },
    success: async () => { const h = await getHaptics(); if (h) await h.Haptics.notification({ type: h.NotificationType.Success }) },
    warning: async () => { const h = await getHaptics(); if (h) await h.Haptics.notification({ type: h.NotificationType.Warning }) },
    error:   async () => { const h = await getHaptics(); if (h) await h.Haptics.notification({ type: h.NotificationType.Error }) },
    // Picker/slider tick (the light click iOS plays while a value changes)
    selection: async () => { const h = await getHaptics(); if (h) await h.Haptics.selectionChanged() },
  },

  /**
   * Status bar control.
   * native.status.setDark()  — white icons (our default)
   * native.status.setLight() — black icons (for light pages)
   */
  status: {
    setDark:  async () => {
      try {
        const { StatusBar, Style } = await import('@capacitor/status-bar')
        await StatusBar.setStyle({ style: Style.Dark })
        await StatusBar.setBackgroundColor({ color: '#08090d' })
      } catch {}
    },
    setLight: async () => {
      try {
        const { StatusBar, Style } = await import('@capacitor/status-bar')
        await StatusBar.setStyle({ style: Style.Light })
      } catch {}
    },
  },

  /**
   * Splash screen — call hide() once the app is loaded.
   */
  splash: {
    hide: async (delay = 300) => {
      try {
        const { SplashScreen } = await import('@capacitor/splash-screen')
        await new Promise(r => setTimeout(r, delay))
        await SplashScreen.hide({ fadeOutDuration: 400 })
      } catch {}
    },
  },

  /**
   * Network status — listen for online/offline changes.
   * Returns an unsubscribe function.
   */
  network: {
    onChange: async (callback) => {
      try {
        const { Network } = await import('@capacitor/network')
        const { remove } = await Network.addListener('networkStatusChange', callback)
        return remove
      } catch { return () => {} }
    },
    getStatus: async () => {
      try {
        const { Network } = await import('@capacitor/network')
        return await Network.getStatus()
      } catch { return { connected: navigator.onLine, connectionType: 'unknown' } }
    },
  },

  /**
   * Push notifications — request permission and register.
   * Pass onRegistration(token) and onNotification(notification) callbacks.
   */
  push: {
    /**
     * Launch-time registration: only when notifications are already allowed,
     * so the permission prompt comes from the first-launch setup card, not
     * out of nowhere at startup.
     */
    register: async ({ onRegistration, onNotification, onReceived } = {}) => {
      if (!isNative()) return
      try {
        const { PushNotifications } = await import('@capacitor/push-notifications')
        const perm = await PushNotifications.checkPermissions()
        if (perm.receive !== 'granted') return
        if (onRegistration) await PushNotifications.addListener('registration', onRegistration)
        // Arriving while the app is open only refreshes the inbox; tapping a
        // banner (app closed or in the background) opens its page.
        if (onReceived) await PushNotifications.addListener('pushNotificationReceived', onReceived)
        if (onNotification) {
          await PushNotifications.addListener('pushNotificationActionPerformed', ({ notification }) => onNotification(notification))
        }
        await PushNotifications.register()
      } catch (e) {
        console.warn('Push registration failed:', e)
      }
    },

    /**
     * Ask for permission and register. Resolves to:
     *   'granted'      allowed and registered with Apple (token passed to onToken)
     *   'no-delivery'  allowed, but this build can't receive push (free Apple
     *                  signing has no push entitlement)
     *   'denied'       not allowed
     *   'unavailable'  not the iOS app, or the native bridge isn't there
     */
    enable: async ({ onToken } = {}) => {
      if (!isNative()) return 'unavailable'
      try {
        const { PushNotifications } = await import('@capacitor/push-notifications')
        const perm = await PushNotifications.requestPermissions()
        if (perm.receive !== 'granted') return 'denied'
        return await new Promise(resolve => {
          let done = false
          const finish = r => { if (!done) { done = true; resolve(r) } }
          PushNotifications.addListener('registration', t => { onToken?.(t.value); finish('granted') })
          PushNotifications.addListener('registrationError', () => finish('no-delivery'))
          PushNotifications.register().catch(() => finish('no-delivery'))
          setTimeout(() => finish('no-delivery'), 10000)
        })
      } catch (e) {
        console.warn('Push permission failed:', e)
        return 'unavailable'
      }
    },

    status: async () => {
      if (!isNative()) return 'unavailable'
      try {
        const { PushNotifications } = await import('@capacitor/push-notifications')
        return (await PushNotifications.checkPermissions()).receive
      } catch { return 'unavailable' }
    },
  },

  /**
   * Microphone — triggers the iOS permission prompt (the app's Info.plist
   * carries NSMicrophoneUsageDescription). Opens and immediately releases
   * the mic. Resolves 'granted' | 'denied' | 'insecure' | 'unavailable'.
   */
  mic: {
    request: async () => {
      // Plain http:// pages get no microphone at all (not a secure context).
      if (!window.isSecureContext) return 'insecure'
      if (!navigator.mediaDevices?.getUserMedia) return 'unavailable'
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        stream.getTracks().forEach(t => t.stop())
        return 'granted'
      } catch (e) {
        return e?.name === 'NotAllowedError' || e?.name === 'SecurityError' ? 'denied' : 'unavailable'
      }
    },
  },

  /**
   * Device info — model name, OS version etc.
   */
  device: {
    getInfo: async () => {
      try {
        const { Device } = await import('@capacitor/device')
        return await Device.getInfo()
      } catch { return { platform: 'web' } }
    },
  },
}
