// App diagnostics export (My Profile → Help & Feedback): a plain-text report
// about this copy of the app, for working out problems that only happen on
// one phone or browser. Sign-in tokens, push tokens and passwords are never
// included. Same file in both forks.
import { api, tokenStore } from './api'
import { WHATS_NEW } from './whatsNew'
import { recent, whatsNewLog } from './diagLog'
import { isNative, deviceName, native, PUSH_TOKEN_KEY } from '../native'

const SECRET = /token|password|secret|key$/i

function claims() {
  try {
    const t = tokenStore.get()
    if (!t) return null
    const c = JSON.parse(atob(t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return { scope: c.scope || 'full', site: c.active_instance_id || null,
             expires: c.exp ? new Date(c.exp * 1000).toISOString() : null }
  } catch { return null }
}

async function safe(fn, fallback = 'unavailable') {
  try { const v = await fn(); return v ?? fallback } catch (e) { return `error: ${e?.message || e}` }
}

function storageSummary() {
  const out = []
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (!k || !k.startsWith('chirp')) continue
      const v = localStorage.getItem(k) || ''
      out.push(`  ${k} = ${SECRET.test(k) || k === PUSH_TOKEN_KEY ? `(set, ${v.length} chars)` : v.length > 80 ? v.slice(0, 80) + '…' : v}`)
    }
  } catch { out.push('  (storage unavailable)') }
  return out.sort()
}

export async function buildReport() {
  const lines = []
  const add = (k, v) => lines.push(`${k.padEnd(26)} ${v ?? ''}`)
  const h = t => lines.push('', `== ${t} ==`)

  lines.push('Chirp app diagnostics', `Made ${new Date().toISOString()}`)

  h('App')
  add('Web app version', WHATS_NEW.version)
  add('What’s New popup', WHATS_NEW.popup || WHATS_NEW.version)
  add('Running in', isNative() ? `${deviceName()} app` : (navigator.standalone ? 'Home Screen web app' : 'browser'))
  if (isNative()) {
    const info = await safe(async () => { const { App } = await import('@capacitor/app'); return App.getInfo() }, null)
    if (info && typeof info === 'object') add('Native app', `${info.version} (${info.build})`)
  }
  add('Address', location.origin)
  const health = await safe(() => api.health(), null)
  add('Server version', health?.version || (typeof health === 'string' ? health : 'unreachable'))

  h('Device')
  add('User agent', navigator.userAgent)
  add('Language, time zone', `${navigator.language}, ${Intl.DateTimeFormat().resolvedOptions().timeZone}`)
  add('Screen', `${screen.width}×${screen.height} @${window.devicePixelRatio}x, window ${innerWidth}×${innerHeight}`)
  add('Color scheme', matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  add('Online', String(navigator.onLine))

  h('Account')
  const me = await safe(() => api.auth.whoami(), null)
  if (me && typeof me === 'object') {
    add('Signed in as', me.username ? `${me.username} (${me.role})` : 'no sign-in (auth off)')
    add('What’s New seen (server)', me.last_seen_whats_new_version || 'none')
  } else add('Signed in', String(me))
  const c = claims()
  if (c) { add('Sign-in scope', c.scope); add('Site id', c.site || 'single site'); add('Sign-in expires', c.expires || 'never') }

  h('Notifications')
  add('Browser permission', typeof Notification === 'undefined' ? 'not supported' : Notification.permission)
  if (isNative()) {
    add('iPhone permission', await safe(() => native.push.status()))
    add('Push token saved', (() => { try { return localStorage.getItem(PUSH_TOKEN_KEY) ? 'yes' : 'no' } catch { return 'unknown' } })())
    const w = await safe(() => native.watch.status(), null)
    add('Apple Watch', w && typeof w === 'object' ? JSON.stringify(w).slice(0, 200) : String(w ?? 'none'))
  }

  h('Offline copy')
  add('Service worker', navigator.serviceWorker?.controller ? navigator.serviceWorker.controller.scriptURL.split('/').pop() : 'none')
  add('Caches', await safe(async () => ('caches' in window ? (await caches.keys()).join(', ') : 'not supported') || 'none'))

  h('What’s New, last shown')
  const wn = whatsNewLog()
  if (!wn.length) lines.push('  (not shown on this device since logging began)')
  wn.forEach(e => lines.push(`  ${e.at}  popup ${e.popup}  server ${e.server ?? '-'}  local ${e.local ?? '-'}  app ${e.app ?? '-'}`))

  h('Saved on this device')
  lines.push(...storageSummary())

  h('Recent problems')
  const r = recent()
  if (!r.length) lines.push('  none')
  r.forEach(e => lines.push(`  ${e.at}  ${e.kind}: ${e.detail}`))

  return lines.join('\n') + '\n'
}
