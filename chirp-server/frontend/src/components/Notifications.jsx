import { useEffect, useState, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Bell, Bird, Newspaper, CheckCheck, Trash2, RefreshCw, Settings as Cog, X } from 'lucide-react'
import { api } from '../lib/api'
import { setUnread } from '../lib/unread'
import { appPath } from '../lib/appPath'
import { native, isApp } from '../native'

const ICON = { 'new-bird': Bird, 'daily-digest': Newspaper }

function ago(iso) {
  const t = new Date(iso).getTime()
  if (!t) return ''
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  if (s < 7 * 86400) return `${Math.floor(s / 86400)}d ago`
  return new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// The day a digest notification reports on: stored with newer ones, or the
// day before it was sent (digests go out each morning for the previous day).
function digestDate(n) {
  if (n.data?.date) return n.data.date
  const m = (n.url || '').match(/digest=(\d{4}-\d{2}-\d{2})/)
  if (m) return m[1]
  const d = new Date(n.created_at)
  d.setDate(d.getDate() - 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function Notifications() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [pushState, setPushState] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    try {
      const r = await api.notifications.list()
      setItems(r.items)
      // Opening the tab reads them; the dots stay on this visit.
      if (r.unread) api.notifications.readAll().then(() => setUnread(0)).catch(() => {})
      else setUnread(0)
    } catch (e) {
      setError(e.message || 'Could not load notifications')
      setItems([])
    }
  }, [])

  useEffect(() => {
    load()
    window.addEventListener('chirp-notification', load)
    if (isApp()) native.push.status().then(setPushState)
    return () => window.removeEventListener('chirp-notification', load)
  }, [load])

  const clearAll = async () => {
    setBusy(true)
    try { await api.notifications.clear(); setItems([]); setUnread(0) } catch {}
    setBusy(false)
  }
  const enablePush = async () => {
    const r = await native.push.enable({ onToken: t => api.push.registerNative(t).catch(() => {}) })
    setPushState(r === 'granted' ? 'granted' : r)
  }
  const removeOne = async n => {
    setItems(list => list.filter(x => x.id !== n.id))
    try {
      const r = await api.notifications.remove(n.id)
      setUnread(r.unread)
    } catch { load() }
  }
  const open = n => {
    if (n.kind === 'daily-digest') navigate(`/digest?date=${digestDate(n)}`)
    else if (appPath(n.url)) navigate(appPath(n.url))
  }

  // Digest pushes from 0.5.12.f–h link here with ?digest=<date>.
  const wanted = searchParams.get('digest')
  useEffect(() => {
    if (wanted) navigate(`/digest?date=${wanted}`, { replace: true })
  }, [wanted, navigate])

  return (
    <div className="max-w-2xl mx-auto px-4 md:px-6 py-5 md:py-8 animate-fade-in">
      <div className="flex items-center justify-between gap-3 mb-4">
        <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Notifications</h1>
        <div className="flex items-center gap-1">
          <button className="btn-ghost p-2" aria-label="Refresh" onClick={load}><RefreshCw size={16}/></button>
          {items?.length > 0 && (
            <button className="btn-ghost p-2" aria-label="Clear all" disabled={busy} onClick={clearAll}><Trash2 size={16}/></button>
          )}
        </div>
      </div>

      {isApp() && pushState && pushState !== 'granted' && (
        <div className="card p-4 mb-4 flex items-start gap-3">
          <Bell size={18} style={{ color: 'var(--accent-400)', flexShrink: 0, marginTop: 2 }}/>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Push alerts are off</p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              {pushState === 'denied'
                ? 'Turn them on in the iPhone Settings app → Chirp → Notifications. New notifications still collect here.'
                : 'Allow notifications to hear about new birds as they are detected. They also collect here.'}
            </p>
          </div>
          {pushState !== 'denied' && (
            <button className="btn-primary flex-shrink-0" style={{ padding: '6px 12px', fontSize: 12 }} onClick={enablePush}>Allow</button>
          )}
        </div>
      )}

      {error && <p className="text-sm mb-3" style={{ color: 'var(--pastel-red, #fca5a5)' }}>{error}</p>}

      {items === null ? (
        <div className="space-y-2">{[0, 1, 2].map(i => <div key={i} className="card h-16 animate-pulse"/>)}</div>
      ) : items.length === 0 ? (
        <div className="card p-8 text-center">
          <CheckCheck size={28} className="mx-auto mb-3" style={{ color: 'var(--text-tertiary)' }}/>
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>No notifications yet</p>
          <p className="text-xs mt-1.5" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            New species, birds you watch, the journals and the daily digest show up here. Choose which ones you get in{' '}
            <button className="underline" onClick={() => navigate('/settings?tab=mine')}>Settings</button>.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {items.map(n => {
            const Icon = ICON[n.kind] || Bell
            return (
              <li key={n.id} className="card flex items-stretch overflow-hidden">
                <button onClick={() => open(n)} disabled={!n.url && n.kind !== 'daily-digest'}
                        className="flex-1 min-w-0 text-left p-3.5 pr-1 flex items-start gap-3 tactile-press"
                        style={{ cursor: (n.url || n.kind === 'daily-digest') ? 'pointer' : 'default' }}>
                  <span className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                        style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }}>
                    <Icon size={17}/>
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline gap-2">
                      <span className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{n.title}</span>
                      <span className="text-[11px] flex-shrink-0 ml-auto" style={{ color: 'var(--text-tertiary)' }}>{ago(n.created_at)}</span>
                    </span>
                    {n.body && <span className="block text-xs mt-0.5" style={{ color: 'var(--text-secondary)', lineHeight: 1.45 }}>{n.body}</span>}
                  </span>
                  {!n.read && <span aria-label="Unread" className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0" style={{ background: 'var(--accent-400)' }}/>}
                </button>
                <button onClick={() => removeOne(n)} aria-label={`Delete notification: ${n.title}`} data-haptic="heavy"
                        className="px-3 flex items-center flex-shrink-0 hover:opacity-100"
                        style={{ color: 'var(--text-tertiary)', opacity: 0.7 }}>
                  <X size={15}/>
                </button>
              </li>
            )
          })}
        </ul>
      )}

      <button className="mt-5 text-xs flex items-center gap-1.5" style={{ color: 'var(--text-tertiary)' }}
              onClick={() => navigate('/settings?tab=mine')}>
        <Cog size={13}/> Notification settings
      </button>

    </div>
  )
}
