/**
 * First-launch setup card for the iOS app: asks for notifications and then
 * the microphone as soon as the app first opens (the card explains why
 * each prompt is appearing), with Allow buttons as a fallback. Shown once per
 * install (a reinstall starts with empty storage and shows it again).
 * Browsers and the home-screen web app never see it.
 */
import { useEffect, useState } from 'react'
import { Bell, Mic, X } from 'lucide-react'
import { native, isApp, deviceName } from '../native'
import { api } from '../lib/api'

const DONE_KEY = 'chirp_app_permissions_v1'

const LABEL = {
  granted: 'Allowed',
  denied: 'Not allowed. Turn it on in Settings → Chirp.',
  'no-delivery': "Allowed, but this build of the app can't receive push alerts. You'll still get email alerts.",
  unavailable: "Not available here.",
  insecure: "Needs an https:// server address; this server uses http://.",
}

export default function AppPermissions() {
  const [open, setOpen] = useState(false)
  const [push, setPush] = useState(null)
  const [mic, setMic] = useState(null)
  const [busy, setBusy] = useState(null)

  useEffect(() => {
    try {
      if (isApp() && !localStorage.getItem(DONE_KEY)) setOpen(true)
    } catch { /* storage blocked: skip the card */ }
  }, [])

  // First launch: ask for notifications, then the microphone, right away
  // (each shows the iPhone's own prompt). The card stays up to show what
  // was allowed and closes itself shortly after.
  useEffect(() => {
    if (!open) return
    let cancelled = false
    ;(async () => {
      await new Promise(r => setTimeout(r, 700))
      if (!cancelled) await askPush()
      if (!cancelled) await askMic()
      if (!cancelled) setTimeout(() => { if (!cancelled) finish() }, 2500)
    })()
    return () => { cancelled = true }
  }, [open])   // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null

  const finish = () => {
    try { localStorage.setItem(DONE_KEY, '1') } catch {}
    setOpen(false)
  }
  const askPush = async () => {
    setBusy('push')
    setPush(await native.push.enable({ onToken: t => api.push.registerNative(t).catch(() => {}) }))
    setBusy(null)
  }
  const askMic = async () => {
    setBusy('mic')
    setMic(await native.mic.request())
    setBusy(null)
  }

  const Row = ({ icon: Icon, title, text, state, onAsk, id }) => (
    <div className="flex items-start gap-3 py-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
      <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
           style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }}>
        <Icon size={17}/>
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</p>
        <p className="text-xs mt-0.5" style={{ color: state && state !== 'granted' ? 'var(--pastel-red, #fca5a5)' : 'var(--text-secondary)', lineHeight: 1.45 }}>
          {state ? LABEL[state] : text}
        </p>
      </div>
      {!state && (
        <button className="btn-primary flex-shrink-0" style={{ padding: '6px 12px', fontSize: 12 }}
                disabled={busy === id} onClick={onAsk}>
          {busy === id ? 'Asking…' : 'Allow'}
        </button>
      )}
    </div>
  )

  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center p-4"
         style={{ background: 'rgba(0,0,0,.55)', paddingBottom: 'calc(env(safe-area-inset-bottom) + 16px)' }}
         role="dialog" aria-labelledby="app-perm-title">
      <div className="w-full max-w-md rounded-2xl p-5 animate-fade-in"
           style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-default)', boxShadow: '0 16px 40px rgba(0,0,0,.5)' }}>
        <div className="flex items-start justify-between gap-3 mb-2">
          <div>
            <h2 id="app-perm-title" className="font-display text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
              Set up Chirp on this {deviceName()}
            </h2>
            <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
              Your {deviceName()} will ask about each one now. You can change them later in Settings → Chirp.
            </p>
          </div>
          <button aria-label="Close" onClick={finish} className="p-1 -m-1" style={{ color: 'var(--text-tertiary)' }}>
            <X size={18}/>
          </button>
        </div>
        <Row id="push" icon={Bell} title="Notifications" state={push} onAsk={askPush}
             text="New species, rare visitors and the daily digest."/>
        <Row id="mic" icon={Mic} title="Microphone" state={mic} onAsk={askMic}
             text="Used by Live Detect to listen with this phone. Nothing is recorded until you press Start."/>
        <button className="btn-secondary w-full mt-3" style={{ padding: '9px 12px', fontSize: 13 }} onClick={finish}>
          {push || mic ? 'Done' : 'Not now'}
        </button>
      </div>
    </div>
  )
}
