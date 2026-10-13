import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { X, Sparkles, ChevronDown, GitBranch, BookOpen } from 'lucide-react'
import { api } from '../lib/api'
import { WHATS_NEW } from '../lib/whatsNew'
import { useAppInfo } from '../lib/appVersion'

const ANON_STORAGE_KEY = 'chirp_whats_new_seen_version'

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
 * Only WHATS_NEW.latest is ever shown expanded — this popup announces
 * what's new right now, not a running archive of every past release
 * (that accumulated into a very long single-scroll list before this
 * rewrite). Older versions get one condensed line each under a
 * collapsed "Previously" toggle, and the full detail lives on the
 * Changelog page this links to — not duplicated here.
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
        if (u.last_seen_whats_new_version !== WHATS_NEW.version) setVisible(true)
      } else {
        // Anon / auth disabled — no real user row to persist to, fall back
        // to a browser-local marker instead
        setMode('anon')
        const seen = localStorage.getItem(ANON_STORAGE_KEY)
        if (seen !== WHATS_NEW.version) setVisible(true)
      }
    }).catch(() => {})
  }, [])

  const dismiss = async () => {
    setVisible(false)
    if (mode === 'user') {
      try { await api.auth.updateProfile({ last_seen_whats_new_version: WHATS_NEW.version }) } catch (e) { /* worst case it shows again next load — not worth blocking dismissal on this */ }
    } else {
      localStorage.setItem(ANON_STORAGE_KEY, WHATS_NEW.version)
    }
  }

  if (!visible) return null

  const { latest, previousHighlights, olderHistory } = WHATS_NEW

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,.6)', backdropFilter: 'blur(4px)' }}
         onClick={e => { if (e.target === e.currentTarget) dismiss() }}>
      <div className="w-full max-w-lg rounded-2xl p-6 sm:p-7 relative max-h-[85vh] overflow-y-auto"
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
        <p className="text-xs mb-5" style={{ color: 'var(--text-tertiary)' }}>
          Version {WHATS_NEW.version}{appInfo ? ` · iPhone app ${appInfo.version} (build ${appInfo.build})` : ''}
        </p>

        {latest.intro && (
          <p className="text-sm mb-5" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>{latest.intro}</p>
        )}

        <div className="space-y-4 mb-2">
          {latest.sections.map((s, i) => (
            <div key={i}>
              <p className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>{s.heading}</p>
              <p className="text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>{s.body}</p>
            </div>
          ))}
        </div>

        {(previousHighlights?.length > 0 || olderHistory?.length > 0) && (
          <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            <button onClick={() => setShowHistory(h => !h)}
                    className="tactile-press flex items-center gap-1.5 text-xs font-medium w-full"
                    style={{ color: 'var(--text-tertiary)' }}>
              <ChevronDown size={13} style={{ transform: showHistory ? 'rotate(180deg)' : 'none', transition: 'transform 150ms ease' }}/>
              Previously
            </button>
            {showHistory && (
              <div className="mt-2 space-y-3">
                {previousHighlights?.length > 0 && <div className="space-y-1.5">
                  {previousHighlights.map((h, i) => (
                    <p key={i} className="text-xs" style={{ color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
                      <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{h.version}</span> — {h.summary}
                    </p>
                  ))}
                </div>}
                {olderHistory?.length > 0 && (
                  <div className="space-y-1.5 pt-2" style={previousHighlights?.length > 0 ? { borderTop: '1px solid var(--border-subtle)' } : undefined}>
                    {olderHistory.map((h, i) => (
                      <p key={i} className="text-xs" style={{ color: 'var(--text-tertiary)', lineHeight: 1.5, opacity: 0.8 }}>
                        <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{h.range}</span> — {h.summary}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <div className="flex items-center gap-2 mt-4 mb-4">
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
