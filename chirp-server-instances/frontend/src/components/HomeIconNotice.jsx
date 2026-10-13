/**
 * One-time card for iPhone/iPad home-screen installs after the app icon
 * changes. iOS saves the icon when Chirp is added to the Home Screen and
 * never refreshes it, and there is no API to change it, so the only way
 * to get the new icon is to remove and re-add the app. Android and
 * desktop Chrome pick up the new icon from the versioned manifest URLs.
 *
 * Shown only when:
 *   - running as an iOS home-screen app (navigator.standalone), and
 *   - this install was used on a version older than ICON_VERSION
 *     (index.html snapshots storage before the app writes to it), and
 *   - it hasn't been dismissed for this icon.
 * A re-added app starts with empty storage, so it never sees the card.
 */
import { useEffect, useState } from 'react'
import { X } from 'lucide-react'

// Bump when the home-screen icon artwork changes.
export const ICON_VERSION = '0.5.9.a'
const DONE_KEY = 'chirp_icon_version'
const LAST_KEY = 'chirp_app_version'

// 0.5.8.c < 0.5.8.d < 0.5.8.z < 0.5.8.aa < 0.5.9.a
export function compareVersions(a, b) {
  const pa = String(a).split('.'), pb = String(b).split('.')
  for (let i = 0; i < 3; i++) {
    const d = (parseInt(pa[i], 10) || 0) - (parseInt(pb[i], 10) || 0)
    if (d) return d
  }
  const la = pa[3] || '', lb = pb[3] || ''
  if (la.length !== lb.length) return la.length - lb.length
  return la < lb ? -1 : la > lb ? 1 : 0
}

function shouldShow(currentVersion) {
  try {
    if (!window.navigator.standalone) return false
    if (localStorage.getItem(DONE_KEY) === ICON_VERSION) return false
    const snap = window.__chirpInstall || {}
    const old = snap.lastVersion
      ? compareVersions(snap.lastVersion, ICON_VERSION) < 0
      : !!snap.returning               // used before version tracking existed
    if (!old) localStorage.setItem(DONE_KEY, ICON_VERSION)   // fresh install already has it
    return old
  } catch {
    return false
  } finally {
    try { localStorage.setItem(LAST_KEY, currentVersion) } catch {}
  }
}

// A home-screen install made before 0.5.10.m keeps the translucent status
// bar (iOS reads the setting when the app is added). On iOS 26 that leaves
// the page short of the screen, with a band under the bottom nav. The
// translucent bar is the only case with a top safe-area inset in a
// portrait home-screen app, so measure it.
const LAYOUT_KEY = 'chirp_layout_notice'
const LAYOUT_VERSION = '0.5.10.m'

export function staleTranslucentLayout() {
  try {
    if (!window.navigator.standalone) return false
    if (localStorage.getItem(LAYOUT_KEY) === LAYOUT_VERSION) return false
    const probe = document.createElement('div')
    probe.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:env(safe-area-inset-top,0px);visibility:hidden;pointer-events:none'
    document.body.appendChild(probe)
    const inset = probe.offsetHeight
    probe.remove()
    return inset > 20
  } catch {
    return false
  }
}

export default function HomeIconNotice({ version }) {
  const [open, setOpen] = useState(false)
  const [layout, setLayout] = useState(false)
  useEffect(() => {
    if (!version) return
    const icon = shouldShow(version)
    const lay = false   // 0.5.10.n: viewportFix.js handles the short layout in place
    setLayout(lay)
    setOpen(icon || lay)
  }, [version])
  if (!open) return null

  const dismiss = forever => {
    if (forever) {
      try {
        localStorage.setItem(DONE_KEY, ICON_VERSION)
        localStorage.setItem(LAYOUT_KEY, LAYOUT_VERSION)
      } catch {}
    }
    setOpen(false)
  }

  return (
    <div role="dialog" aria-labelledby="home-icon-title"
         className="fixed left-3 right-3 z-40 mx-auto max-w-md rounded-2xl p-4 animate-fade-in"
         style={{ bottom: 'calc(env(safe-area-inset-bottom) + 76px)', background: 'var(--bg-raised)',
                  border: '1px solid var(--border-default)', boxShadow: '0 10px 30px rgba(0,0,0,.45)' }}>
      <div className="flex items-start gap-3">
        <img src={`/apple-touch-icon.png?v=${ICON_VERSION}`} alt="" width="48" height="48"
             className="rounded-xl flex-shrink-0"/>
        <div className="min-w-0 flex-1">
          <p id="home-icon-title" className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {layout ? 'Use the full screen' : 'New Chirp icon'}
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            {layout
              ? 'iPhone keeps the screen layout from when Chirp was added, which leaves a gap under the bottom bar. To fix it:'
              : 'iPhone keeps the old icon on your Home Screen. To get the new one:'}
          </p>
          <ol className="text-xs mt-1.5 space-y-1 list-decimal pl-4" style={{ color: 'var(--text-secondary)', lineHeight: 1.45 }}>
            <li>Press and hold Chirp on the Home Screen, tap <b>Remove App</b>, then <b>Delete from Home Screen</b>.</li>
            <li>Open this site in Safari, tap <b>Share</b>, then <b>Add to Home Screen</b>.</li>
          </ol>
          <p className="text-[11px] mt-1.5" style={{ color: 'var(--text-tertiary)' }}>
            Your recordings stay on the server. You may need to sign in again.
          </p>
          <div className="flex gap-2 mt-3">
            <button className="btn-primary" style={{ padding: '6px 12px', fontSize: 12 }} onClick={() => dismiss(true)}>Got it</button>
            <button className="btn-ghost" style={{ padding: '6px 12px', fontSize: 12 }} onClick={() => dismiss(false)}>Later</button>
          </div>
        </div>
        <button aria-label="Close" onClick={() => dismiss(false)} className="p-1 -m-1" style={{ color: 'var(--text-tertiary)' }}>
          <X size={16}/>
        </button>
      </div>
    </div>
  )
}
