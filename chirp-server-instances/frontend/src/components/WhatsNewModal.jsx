import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { X, Sparkles, ChevronDown, GitBranch, BookOpen } from 'lucide-react'
import { api } from '../lib/api'
import { WHATS_NEW } from '../lib/whatsNew'
import { useAppInfo } from '../lib/appVersion'

const ANON_STORAGE_KEY = 'chirp_whats_new_seen_version'
const POPUP = WHATS_NEW.popup || WHATS_NEW.version

/**
 * Shows once per version, per user (or per browser, for an anon/no-auth
 * install). Real per-user tracking goes through User.last_seen_whats_new_version
 * (see api/auth.py) when a real authenticated user exists; falls back to
 * localStorage for anon/no-auth mode, since there's no real user row to
 * persist the field on there.
 *
 * Deliberately its own fully self-contained component doing its own
 * api.auth.me() fetch, rather than reading App.jsx's currentUser state —
 * that state only ever carries {username, role}, not the full profile
 * fields this needs (same reason Dashboard.jsx's own mode-picker logic
 * does its own independent fetch instead of relying on it).
 *
 * Shows WHATS_NEW.latest (at most three short items) and, collapsed, one
 * line per earlier release of the current minor version. Everything older
 * is on the Changelog page.
 */
export default function WhatsNewModal() {
  const appInfo = useAppInfo()
  const [visible, setVisible] = useState(false)
  const [mode, setMode] = useState(null)  // 'user' | 'anon' — which dismiss mechanism to use
  const [showHistory, setShowHistory] = useState(false)

  useEffect(() => {
    api.auth.me().then(u => {
      if (!u) return
      if (u.username && u.auth_required !== false) {
        // Real authenticated user — use the per-account field
        setMode('user')
        if (u.last_seen_whats_new_version !== POPUP) setVisible(true)
      } else {
        // Anon / auth disabled — no real user row to persist to, fall back
        // to a browser-local marker instead
        setMode('anon')
        const seen = localStorage.getItem(ANON_STORAGE_KEY)
        if (seen !== POPUP) setVisible(true)
      }
    }).catch(() => {})
  }, [])

  const dismiss = async () => {
    setVisible(false)
    if (mode === 'user') {
      try { await api.auth.updateProfile({ last_seen_whats_new_version: POPUP }) } catch (e) { /* worst case it shows again next load — not worth blocking dismissal on this */ }
    } else {
      localStorage.setItem(ANON_STORAGE_KEY, POPUP)
    }
  }

  if (!visible) return null

  const { latest, recent } = WHATS_NEW

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,.6)', backdropFilter: 'blur(4px)' }}
         onClick={e => { if (e.target === e.currentTarget) dismiss() }}>
      <div className="w-full max-w-md rounded-2xl p-6 relative max-h-[85vh] overflow-y-auto"
           style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)' }}>
        <button onClick={dismiss} className="tactile-press absolute top-4 right-4 p-1 rounded-lg transition-colors hover:opacity-70"
                style={{ color: 'var(--text-tertiary)' }} aria-label="Close">
          <X size={16}/>
        </button>

        <div className="flex items-center gap-2 mb-1">
          <Sparkles size={20} style={{ color: 'var(--accent-400)' }}/>
          <h2 className="text-lg font-bold" style={{ color: 'var(--text-primary)', fontFamily: "'Lora', serif" }}>
            {WHATS_NEW.title}
          </h2>
        </div>
        <p className="text-xs mb-4" style={{ color: 'var(--text-tertiary)' }}>
          Version {WHATS_NEW.version}{appInfo ? ` · iPhone app ${appInfo.version}` : ''}
        </p>

        {latest.intro && (
          <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)', lineHeight: 1.55 }}>{latest.intro}</p>
        )}

        <div className="space-y-3">
          {latest.sections.map((s, i) => (
            <div key={i} className="rounded-xl px-3.5 py-3" style={{ background: 'var(--bg-subtle, rgba(255,255,255,.03))' }}>
              <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{s.heading}</p>
              <p className="text-[13px] mt-0.5" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>{s.body}</p>
            </div>
          ))}
        </div>

        {recent?.length > 1 && (
          <div className="mt-4">
            <button onClick={() => setShowHistory(h => !h)}
                    className="tactile-press flex items-center gap-1.5 text-xs font-medium"
                    style={{ color: 'var(--text-tertiary)' }}>
              <ChevronDown size={13} style={{ transform: showHistory ? 'rotate(180deg)' : 'none', transition: 'transform 150ms ease' }}/>
              Earlier in {WHATS_NEW.version.split('.').slice(0, 3).join('.')}
            </button>
            {showHistory && (
              <ul className="mt-2 space-y-1">
                {recent.slice(1).map(h => (
                  <li key={h.version} className="text-xs flex gap-2" style={{ color: 'var(--text-tertiary)', lineHeight: 1.45 }}>
                    <span className="font-mono flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>{h.version.split('.').pop()}</span>
                    <span>{h.summary}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex items-center gap-2 mt-5 mb-3">
          <Link to="/tutorial" onClick={dismiss}
                className="tactile-press flex items-center justify-center gap-1.5 text-xs flex-1 py-2 rounded-lg"
                style={{ color: 'var(--accent-400)', background: 'var(--nav-active-bg)' }}>
            <BookOpen size={12}/> Tutorial
          </Link>
          <Link to="/changelog" onClick={dismiss}
                className="tactile-press flex items-center justify-center gap-1.5 text-xs flex-1 py-2 rounded-lg"
                style={{ color: 'var(--accent-400)', background: 'var(--nav-active-bg)' }}>
            <GitBranch size={12}/> Changelog
          </Link>
        </div>

        <button onClick={dismiss} className="btn-primary w-full py-2.5">
          Got it
        </button>
      </div>
    </div>
  )
}
