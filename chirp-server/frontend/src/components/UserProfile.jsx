import { useEffect, useState, useRef } from 'react'
import { User, Lock, Bell, Check, AlertCircle, Eye, EyeOff, Save, Shield, Feather, Leaf, RefreshCw, LogOut, Camera, Trash2, UserX, Server, MessageSquare } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { format } from 'date-fns'
import UnifiedCard from './UnifiedCard'
import { InatRefreshInline } from './Settings'
import { hasServerPicker, openServerPicker } from '../native'

// ── Field wrapper ─────────────────────────────────────────────────────────────
function Field({ label, hint, error, children }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
        {label}
      </label>
      {children}
      {hint && !error && <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{hint}</p>}
      {error && <p className="text-xs flex items-center gap-1" style={{ color: '#f87171' }}><AlertCircle size={11}/>{error}</p>}
    </div>
  )
}

// ── Section card ──────────────────────────────────────────────────────────────
function Section({ id, icon, title, color = 'var(--accent-400)', fallbackOpen = null, children }) {
  return (
    <UnifiedCard id={id} title={title} icon={icon} color={color} fallbackOpen={fallbackOpen} variant="stripe">
      <div className="space-y-4">{children}</div>
    </UnifiedCard>
  )
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function Toast({ msg, type }) {
  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-fade-in"
         style={{ pointerEvents: 'none' }}>
      <div className="flex items-center gap-2.5 px-5 py-3 rounded-xl shadow-xl text-sm font-medium"
           style={{
             background: type === 'error' ? '#2d1212' : '#0f2d14',
             border: `1px solid ${type === 'error' ? '#f87171' : 'var(--accent-400)'}40`,
             color: type === 'error' ? '#f87171' : 'var(--accent-400)',
           }}>
        {type === 'error' ? <AlertCircle size={15}/> : <Check size={15}/>}
        {msg}
      </div>
    </div>
  )
}

// ── Avatar ────────────────────────────────────────────────────────────────────
function Avatar({ name, size = 64, photoUrl }) {
  const letter = (name || '?')[0].toUpperCase()
  const colors = [
    ['#f97316','#dc2626'], ['#22d3ee','#3b82f6'],
    ['#a78bfa','#ec4899'], ['#22c55e','#14b8a6'],
  ]
  const pair = colors[(letter.charCodeAt(0)) % colors.length]
  if (photoUrl) {
    return (
      <img src={photoUrl} alt={name || 'avatar'}
           style={{
             width: size, height: size, borderRadius: '50%', flexShrink: 0,
             objectFit: 'cover',
             boxShadow: `0 0 0 2px var(--bg-base), 0 0 0 4px ${pair[0]}40`,
           }}/>
    )
  }
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%', flexShrink: 0,
      background: `linear-gradient(135deg, ${pair[0]}, ${pair[1]})`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: size * 0.38, fontWeight: 800, color: '#fff',
      boxShadow: `0 0 0 2px var(--bg-base), 0 0 0 4px ${pair[0]}40`,
    }}>
      {letter}
    </div>
  )
}

// ── Password field ────────────────────────────────────────────────────────────
function PwInput({ value, onChange, placeholder }) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <input type={show ? 'text' : 'password'} className="input pr-10 w-full"
             value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}/>
      <button type="button" onClick={() => setShow(s => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 opacity-40 hover:opacity-70 transition-opacity">
        {show ? <EyeOff size={14}/> : <Eye size={14}/>}
      </button>
    </div>
  )
}

// ── Toggle pill ───────────────────────────────────────────────────────────────
function Toggle({ checked, onChange, label, sub }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer group">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{label}</p>
        {sub && <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{sub}</p>}
      </div>
      <div className="relative flex-shrink-0 mt-0.5">
        <input type="checkbox" className="sr-only" checked={checked} onChange={e => onChange(e.target.checked)}/>
        <div className="w-10 h-5 rounded-full transition-all duration-200"
             style={{ background: checked ? 'var(--accent-500)' : 'var(--bg-raised)', border: '1px solid var(--border-default)' }}>
          <div className="w-4 h-4 rounded-full bg-white absolute top-0.5 transition-all duration-200"
               style={{ left: checked ? '22px' : '2px', boxShadow: '0 1px 3px rgba(0,0,0,.4)' }}/>
        </div>
      </div>
    </label>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
// Standard conversion — PushManager.subscribe() needs applicationServerKey
// as a Uint8Array, not the base64url string the server returns it as.
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; i++) outputArray[i] = rawData.charCodeAt(i)
  return outputArray
}

export function PushNotificationSection() {
  // 'unsupported' | 'checking' | 'default' | 'denied' | 'subscribed' | 'available'
  const [status, setStatus] = useState('checking')
  const [busy, setBusy] = useState(false)
  const [testResult, setTestResult] = useState(null)  // null | 'ok' | error string
  const [currentEndpoint, setCurrentEndpoint] = useState(null)
  const [digestPush, setDigestPush] = useState(false)
  const [digestPushSaving, setDigestPushSaving] = useState(false)

  useEffect(() => {
    api.auth.me().then(p => setDigestPush(p?.notify_daily_digest_push ?? false)).catch(() => {})
  }, [])

  const toggleDigestPush = async (next) => {
    setDigestPush(next)  // optimistic — matches how instant-feeling toggles already work elsewhere in this app
    setDigestPushSaving(true)
    try {
      await api.auth.updateProfile({ notify_daily_digest_push: next })
    } catch (e) {
      setDigestPush(!next)  // real failure — revert rather than leave the UI showing a state that didn't actually save
    }
    setDigestPushSaving(false)
  }

  useEffect(() => {
    (async () => {
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        setStatus('unsupported')
        return
      }
      if (Notification.permission === 'denied') {
        setStatus('denied')
        return
      }
      try {
        const reg = await navigator.serviceWorker.ready
        const sub = await reg.pushManager.getSubscription()
        if (sub) {
          setCurrentEndpoint(sub.endpoint)
          setStatus('subscribed')
        } else {
          setStatus(Notification.permission === 'granted' ? 'available' : 'default')
        }
      } catch (e) {
        setStatus('unsupported')
      }
    })()
  }, [])

  const enable = async () => {
    setBusy(true)
    try {
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') {
        setStatus(permission === 'denied' ? 'denied' : 'default')
        setBusy(false)
        return
      }
      const { public_key } = await api.push.vapidPublicKey()
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key),
      })
      const json = sub.toJSON()
      await api.push.subscribe({ endpoint: json.endpoint, keys: json.keys, user_agent: navigator.userAgent })
      setCurrentEndpoint(json.endpoint)
      setStatus('subscribed')
    } catch (e) {
      console.error('Push subscribe failed:', e)
      setStatus('default')
    }
    setBusy(false)
  }

  const disable = async () => {
    setBusy(true)
    try {
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.getSubscription()
      if (sub) {
        await api.push.unsubscribe(sub.endpoint).catch(() => {})
        await sub.unsubscribe()
      }
      setCurrentEndpoint(null)
      setStatus('available')
    } catch (e) {
      console.error('Push unsubscribe failed:', e)
    }
    setBusy(false)
  }

  const sendTest = async () => {
    if (!currentEndpoint) return
    setTestResult(null)
    try {
      await api.push.test(currentEndpoint)
      setTestResult('ok')
    } catch (e) {
      setTestResult(e?.message || 'Failed')
    }
    setTimeout(() => setTestResult(null), 5000)
  }

  if (status === 'unsupported') return null  // this browser genuinely can't do this — no point showing a dead-end control

  return (
    <Section id="me:push" fallbackOpen={false} icon={Bell} title="Device Notifications" color="#4ade80">
      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        Real notifications on this device — including while Chirp is closed — separate from the
        email notifications above. Follows the same "new species" preference set there.
      </p>

      {status === 'denied' && (
        <div className="flex items-center gap-2 p-3 rounded-lg text-xs"
             style={{ background: 'rgba(248,113,113,.08)', border: '1px solid rgba(248,113,113,.2)', color: '#f87171' }}>
          <AlertCircle size={13} style={{ flexShrink: 0 }}/>
          Notifications are blocked for this site in your browser. Re-enable them in your browser's
          site settings, then reload this page.
        </div>
      )}

      {(status === 'default' || status === 'available') && (
        <button onClick={enable} disabled={busy} className="btn-primary flex items-center gap-1.5 text-sm">
          {busy ? <span className="animate-spin">⟳</span> : <Bell size={13}/>}
          Enable on this device
        </button>
      )}

      {status === 'subscribed' && (
        <div className="space-y-2">
          <p className="text-xs flex items-center gap-1.5" style={{ color: '#4ade80' }}>
            <Check size={13}/> Enabled on this device
          </p>
          <div className="flex items-center gap-2">
            <button onClick={sendTest} className="text-xs px-2.5 py-1.5 rounded-lg"
                    style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
              Send test notification
            </button>
            <button onClick={disable} disabled={busy} className="text-xs px-2.5 py-1.5 rounded-lg"
                    style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
              Disable
            </button>
          </div>
          {testResult === 'ok' && <p className="text-xs" style={{ color: '#4ade80' }}>Sent — check for it now.</p>}
          {testResult && testResult !== 'ok' && <p className="text-xs" style={{ color: '#f87171' }}>{testResult}</p>}
          <div className="pt-2 mt-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            <Toggle checked={digestPush} onChange={toggleDigestPush}
                    label={digestPushSaving ? 'Daily digest (saving…)' : 'Daily digest'}
                    sub="Same summary as the email digest, as a push notification instead — a separate opt-in, on or off independent of email"/>
          </div>
        </div>
      )}
    </Section>
  )
}

// ── Server (picker builds only) ───────────────────────────────────────────────
function ServerSection() {
  return (
    <Section id="me:server" fallbackOpen={false} icon={Server} title="Server" color="#60a5fa">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{window.location.host}</p>
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>You stay signed in here when you switch.</p>
        </div>
        <button onClick={openServerPicker} className="btn-secondary text-xs px-3 py-1.5 flex-shrink-0">Change server</button>
      </div>
    </Section>
  )
}

// ── Help & feedback ───────────────────────────────────────────────────────────
// Questions, problems and feature ideas go to the server's admins
// (api/support.py), signed with this account.
const FEEDBACK_KINDS = [
  ['feature', 'Suggest a feature', 'What would you like Chirp to do?'],
  ['problem', "Something's wrong", 'What happened, and what did you expect?'],
  ['question', 'Question', 'How can we help?'],
]
function FeedbackSection() {
  const [kind, setKind] = useState('feature')
  const [message, setMessage] = useState('')
  const [state, setState] = useState(null)   // null | 'sending' | 'sent' | error text
  const send = async () => {
    if (message.trim().length < 5) { setState('Write a few words first.'); return }
    setState('sending')
    try {
      await api.support.send({ kind, message: message.trim(), page: 'app' })
      setMessage(''); setState('sent')
    } catch (e) { setState(e.message || 'Couldn\u2019t send. Try again.') }
  }
  return (
    <Section id="me:feedback" fallbackOpen={false} icon={MessageSquare} title="Help & Feedback" color="#fbbf24">
      <div className="flex flex-wrap gap-1.5 mb-3">
        {FEEDBACK_KINDS.map(([k, label]) => (
          <button key={k} onClick={() => { setKind(k); setState(null) }}
                  className="text-xs px-3 py-1.5 rounded-full font-medium"
                  style={kind === k ? { background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }
                                    : { background: 'var(--bg-raised)', color: 'var(--text-tertiary)' }}>
            {label}
          </button>
        ))}
      </div>
      <textarea className="input w-full text-sm" rows={4} value={message} onChange={e => setMessage(e.target.value)}
                placeholder={FEEDBACK_KINDS.find(x => x[0] === kind)[2]}/>
      <div className="flex items-center gap-3 mt-2">
        <button onClick={send} disabled={state === 'sending'} className="btn-primary text-sm px-4 py-2">
          {state === 'sending' ? 'Sending…' : 'Send'}
        </button>
        {state === 'sent' && <span className="text-xs" style={{ color: 'var(--pastel-green)' }}>Thanks! It's on its way.</span>}
        {state && state !== 'sent' && state !== 'sending' && <span className="text-xs" style={{ color: 'var(--pastel-red)' }}>{state}</span>}
      </div>
      <p className="text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>
        Sent with your username so we can reply. More help on the <a href="/support.html" target="_blank" rel="noopener" style={{ color: 'var(--accent-400)' }}>support page ↗</a>.
      </p>
    </Section>
  )
}

// ── Blocked people ────────────────────────────────────────────────────────────
// People whose notes are hidden from you (Block, on any note).
function BlockedPeopleSection() {
  const [blocked, setBlocked] = useState(null)
  useEffect(() => { api.moderation.blocks().then(setBlocked).catch(() => setBlocked([])) }, [])
  const unblock = async (name) => {
    try { await api.moderation.unblock(name); setBlocked(b => b.filter(x => x !== name)) } catch {}
  }
  return (
    <Section id="me:blocked" fallbackOpen={false} icon={UserX} title="Blocked People" color="#f87171">
      {blocked === null ? null : blocked.length === 0 ? (
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
          You haven't blocked anyone. Use ⋯ on someone's note to report it or block them.
        </p>
      ) : (
        <ul className="space-y-2">
          {blocked.map(name => (
            <li key={name} className="flex items-center justify-between text-sm" style={{ color: 'var(--text-primary)' }}>
              {name}
              <button onClick={() => unblock(name)} className="btn-ghost text-xs px-3 py-1">Unblock</button>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

// ── Delete account ────────────────────────────────────────────────────────────
// Required by the App Store for apps that let people create an account.
function DeleteAccountSection() {
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await api.auth.deleteAccount(password)
      localStorage.removeItem('chirp_token')
      window.location.replace('/login')
    } catch (err) {
      setError(err.message || 'Could not delete the account')
      setBusy(false)
    }
  }

  return (
    <div className="rounded-2xl p-4" style={{ border: '1px solid rgba(248,113,113,0.25)', background: 'rgba(248,113,113,0.04)' }}>
      <div className="flex items-center gap-2">
        <Trash2 size={15} style={{ color: '#f87171' }}/>
        <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Delete account</p>
        {!open && (
          <button className="ml-auto text-xs font-medium px-3 py-1.5 rounded-lg" onClick={() => setOpen(true)}
                  style={{ color: '#f87171', border: '1px solid rgba(248,113,113,0.25)' }}>
            Delete…
          </button>
        )}
      </div>
      {open && (
        <form onSubmit={submit} className="mt-3 space-y-3">
          <p className="text-xs" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            This permanently deletes your sign-in, your notes, notifications and push registrations, at every location you belong to.
            Recordings and detections stay with the location. This can't be undone.
          </p>
          <input className="input" type="password" required autoComplete="current-password"
                 placeholder="Your password to confirm" value={password} onChange={e => setPassword(e.target.value)}/>
          {error && <p className="text-xs flex items-center gap-1" style={{ color: '#f87171' }}><AlertCircle size={12}/> {error}</p>}
          <div className="flex gap-2">
            <button type="submit" disabled={busy || !password}
                    className="px-3 py-2 rounded-lg text-sm font-semibold"
                    style={{ background: '#dc2626', color: '#fff', opacity: busy || !password ? 0.6 : 1 }}>
              {busy ? 'Deleting…' : 'Delete my account'}
            </button>
            <button type="button" className="btn-ghost text-sm" onClick={() => { setOpen(false); setPassword(''); setError(null) }}>Cancel</button>
          </div>
        </form>
      )}
    </div>
  )
}

export default function UserProfile() {
  const navigate = useNavigate()
  const [profile, setProfile]         = useState(null)
  const [loading, setLoading]         = useState(true)

  // Identity form
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail]             = useState('')
  const [identitySaving, setIdentitySaving] = useState(false)
  const [identityErrors, setIdentityErrors] = useState({})

  // Photo upload
  const [photoUploading, setPhotoUploading] = useState(false)
  const photoInputRef = useRef(null)

  // Password form
  const [currentPw, setCurrentPw]     = useState('')
  const [newPw, setNewPw]             = useState('')
  const [confirmPw, setConfirmPw]     = useState('')
  const [pwSaving, setPwSaving]       = useState(false)
  const [pwErrors, setPwErrors]       = useState({})

  // Notification prefs
  const [notifyBird, setNotifyBird]   = useState(true)
  const [notifyDigest, setNotifyDigest] = useState(false)
  const [notifSaving, setNotifSaving] = useState(false)

  // iNaturalist token (submitters + admins)
  const [inatToken,    setInatToken]    = useState('')
  const [inatHasToken, setInatHasToken] = useState(false)
  const [inatSaving,   setInatSaving]   = useState(false)
  const [showInat,     setShowInat]     = useState(false)
  const [oauthUsername, setOauthUsername] = useState('')
  const [oauthPassword, setOauthPassword] = useState('')
  const [oauthClientId, setOauthClientId] = useState('')
  const [oauthClientSecret, setOauthClientSecret] = useState('')
  const [oauthSaving, setOauthSaving] = useState(false)
  const [hasOauth, setHasOauth] = useState(false)

  // Toast
  const [toast, setToast]             = useState(null)
  const toastRef                      = useRef(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    clearTimeout(toastRef.current)
    toastRef.current = setTimeout(() => setToast(null), 3000)
  }

  useEffect(() => {
    api.auth.getProfile()
      .then(p => {
        setProfile(p)
        setDisplayName(p.display_name || '')
        setEmail(p.email || '')
        setNotifyBird(p.notify_new_bird ?? true)
        setNotifyDigest(p.notify_daily_digest ?? false)
        setInatHasToken(p.has_inat_token ?? false)
        setOauthUsername(p.inat_username || '')
        setHasOauth(p.has_inat_oauth ?? false)
      })
      .catch(() => showToast('Could not load profile', 'error'))
      .finally(() => setLoading(false))
  }, [])

  const handlePhotoUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) {
      showToast('Please choose an image file', 'error')
      return
    }
    if (file.size > 8 * 1024 * 1024) {
      showToast('Image must be under 8MB', 'error')
      return
    }
    setPhotoUploading(true)
    try {
      const res = await api.auth.uploadPhoto(file)
      setProfile(p => ({ ...p, photo_url: res.photo_url }))
      showToast('Profile photo updated')
    } catch (err) {
      showToast(err.message || 'Failed to upload photo', 'error')
    } finally {
      setPhotoUploading(false)
      if (photoInputRef.current) photoInputRef.current.value = ''
    }
  }

  const saveIdentity = async () => {
    const errs = {}
    if (email && !email.includes('@')) errs.email = 'Enter a valid email address'
    if (Object.keys(errs).length) { setIdentityErrors(errs); return }
    setIdentityErrors({})
    setIdentitySaving(true)
    try {
      const res = await api.auth.updateProfile({ display_name: displayName, email })
      setProfile(p => ({ ...p, ...res }))
      showToast('Profile updated')
    } catch (e) {
      showToast(e.message || 'Failed to save', 'error')
    } finally {
      setIdentitySaving(false)
    }
  }

  const savePassword = async () => {
    const errs = {}
    if (!newPw) errs.newPw = 'Enter a new password'
    else if (newPw.length < 6) errs.newPw = 'Must be at least 6 characters'
    if (newPw !== confirmPw) errs.confirmPw = 'Passwords do not match'
    if (Object.keys(errs).length) { setPwErrors(errs); return }
    setPwErrors({})
    setPwSaving(true)
    try {
      await api.auth.updateProfile({ current_password: currentPw, new_password: newPw })
      setCurrentPw(''); setNewPw(''); setConfirmPw('')
      showToast('Password changed')
    } catch (e) {
      const msg = e.message || ''
      if (msg.toLowerCase().includes('current')) setPwErrors({ currentPw: 'Incorrect current password' })
      else showToast(msg || 'Failed to change password', 'error')
    } finally {
      setPwSaving(false)
    }
  }

  const saveNotifs = async () => {
    setNotifSaving(true)
    try {
      await api.auth.updateProfile({ notify_new_bird: notifyBird, notify_daily_digest: notifyDigest })
      showToast('Notification preferences saved')
    } catch {
      showToast('Failed to save preferences', 'error')
    } finally {
      setNotifSaving(false)
    }
  }

  const saveInatToken = async () => {
    setInatSaving(true)
    try {
      await api.auth.updateProfile({ inat_api_token: inatToken || '' })
      setInatHasToken(!!inatToken.trim())
      setInatToken('')
      showToast(inatToken.trim() ? 'iNaturalist token saved' : 'iNaturalist token removed')
    } catch {
      showToast('Failed to save token', 'error')
    } finally {
      setInatSaving(false)
    }
  }

  if (loading) return (
    <div className="page-root flex items-center justify-center min-h-64">
      <div className="flex flex-col items-center gap-3 animate-pulse">
        <Feather size={28} style={{ color: 'var(--accent-400)' }}/>
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>Loading profile…</p>
      </div>
    </div>
  )

  return (
    <div className="page-root max-w-xl mx-auto space-y-5">
      {toast && <Toast msg={toast.msg} type={toast.type}/>}

      {/* Hero header */}
      <div className="card p-6" style={{ background: 'var(--gradient-hero)' }}>
        <div className="flex items-center gap-4">
          <div className="relative flex-shrink-0">
            <Avatar name={profile?.display_name || profile?.username} photoUrl={profile?.photo_url} size={60}/>
            <input ref={photoInputRef} type="file" accept="image/*" className="hidden"
                   onChange={handlePhotoUpload}/>
            <button
              onClick={() => photoInputRef.current?.click()}
              disabled={photoUploading}
              title="Change profile photo"
              className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full flex items-center justify-center transition-opacity hover:opacity-80 disabled:opacity-50"
              style={{ background: 'var(--accent-500)', color: '#fff', border: '2px solid var(--bg-card)' }}>
              {photoUploading
                ? <RefreshCw size={11} className="animate-spin"/>
                : <Camera size={11}/>}
            </button>
          </div>
          <div className="min-w-0">
            <h1 className="font-display text-xl font-bold truncate" style={{ color: 'var(--text-primary)' }}>
              {profile?.display_name || profile?.username}
            </h1>
            <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>@{profile?.username}</p>
            <div className="flex items-center gap-2 mt-1.5">
              <span className="px-2 py-0.5 rounded-full text-xs font-semibold capitalize"
                    style={{
                      background: profile?.role === 'admin' ? 'rgba(167,139,250,.15)' : 'rgba(34,197,94,.1)',
                      color: profile?.role === 'admin' ? '#c4b5fd' : 'var(--pastel-green)',
                      border: `1px solid ${profile?.role === 'admin' ? 'rgba(167,139,250,.3)' : 'rgba(34,197,94,.2)'}`,
                    }}>
                {profile?.role === 'admin' ? '⚡ Admin' : '👤 Viewer'}
              </span>
              {profile?.created_at && (
                <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  Member since {format(new Date(profile.created_at), 'MMM yyyy')}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Identity */}
      <Section id="me:identity" fallbackOpen={true} icon={User} title="Identity" color="#f97316">
        <Field label="Display name" hint="Shown in the app instead of your username">
          <input className="input w-full" value={displayName}
                 onChange={e => setDisplayName(e.target.value)}
                 placeholder={profile?.username}/>
        </Field>
        <Field label="Email address" hint="Used for notifications. Never shared." error={identityErrors.email}>
          <input className="input w-full" type="email" value={email}
                 onChange={e => { setEmail(e.target.value); setIdentityErrors({}) }}
                 placeholder="your@email.com"/>
        </Field>
        <div className="flex justify-end pt-1">
          <button className="btn-primary flex items-center gap-1.5 text-sm"
                  onClick={saveIdentity} disabled={identitySaving}>
            {identitySaving ? <span className="animate-spin">⟳</span> : <Save size={13}/>}
            Save changes
          </button>
        </div>
      </Section>

      {/* Password */}
      <Section id="me:password" fallbackOpen={false} icon={Lock} title="Change Password" color="#22d3ee">
        <Field label="Current password" error={pwErrors.currentPw}>
          <PwInput value={currentPw} onChange={v => { setCurrentPw(v); setPwErrors({}) }} placeholder="Current password"/>
        </Field>
        <Field label="New password" error={pwErrors.newPw}
               hint={!pwErrors.newPw ? 'Minimum 6 characters' : undefined}>
          <PwInput value={newPw} onChange={v => { setNewPw(v); setPwErrors({}) }} placeholder="New password"/>
        </Field>
        <Field label="Confirm new password" error={pwErrors.confirmPw}>
          <PwInput value={confirmPw} onChange={v => { setConfirmPw(v); setPwErrors(p => ({ ...p, confirmPw: undefined })) }} placeholder="Repeat new password"/>
        </Field>
        <div className="flex justify-end pt-1">
          <button className="btn-primary flex items-center gap-1.5 text-sm"
                  onClick={savePassword} disabled={pwSaving || !newPw}>
            {pwSaving ? <span className="animate-spin">⟳</span> : <Shield size={13}/>}
            Change password
          </button>
        </div>
      </Section>

      {/* iNaturalist token — visible to submitters and admins */}
      {(profile?.role === 'admin' || profile?.role === 'submitter') && (
        <Section id="me:inaturalist" fallbackOpen={false} icon={Leaf} title="iNaturalist" color="#22c55e">
          <p className="text-xs" style={{ color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
            Your personal iNaturalist API token is used when submitting recordings as sound observations.
            It overrides the global token set by admins. Get yours at{' '}
            <a href="https://www.inaturalist.org/users/api_token" target="_blank" rel="noreferrer"
               style={{ color: 'var(--accent-500)' }}>inaturalist.org/users/api_token</a>.
          </p>
          {inatHasToken && (
            <div className="flex items-center gap-2 p-2.5 rounded-lg"
                 style={{ background: 'rgba(34,197,94,.08)', border: '1px solid rgba(34,197,94,.2)' }}>
              <Check size={13} style={{ color: 'var(--pastel-green)', flexShrink: 0 }}/>
              <span className="text-xs font-medium" style={{ color: 'var(--pastel-green)' }}>Token configured</span>
              <button onClick={() => { setInatToken(''); saveInatToken() }}
                      className="ml-auto text-xs" style={{ color: 'var(--text-tertiary)' }}>
                Remove
              </button>
            </div>
          )}
          <Field label={inatHasToken ? 'Replace token' : 'Add token'}>
            <div className="relative">
              <input
                className="input w-full font-mono pr-10"
                type={showInat ? 'text' : 'password'}
                placeholder="Paste your iNaturalist API token…"
                value={inatToken}
                onChange={e => setInatToken(e.target.value)}
              />
              <button type="button" onClick={() => setShowInat(s => !s)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 opacity-40 hover:opacity-70 transition-opacity">
                {showInat ? <EyeOff size={14}/> : <Eye size={14}/>}
              </button>
            </div>
          </Field>
          <div className="flex justify-end pt-1">
            <button className="btn-primary flex items-center gap-1.5 text-sm"
                    onClick={saveInatToken} disabled={inatSaving || !inatToken.trim()}>
              {inatSaving ? <><RefreshCw size={12} className="animate-spin"/> Saving…</> : <><Leaf size={12}/> Save Token</>}
            </button>
          </div>
        </Section>
      )}

      {(profile?.role === 'admin' || profile?.role === 'submitter') && (
        <Section id="me:inaturalist-oauth" fallbackOpen={false} icon={RefreshCw} title="iNaturalist Auto-Refresh" color="#22c55e">
          <p className="text-xs mb-3" style={{ color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
            Fetches a fresh token every 12h using your OWN iNaturalist username/password + a free
            OAuth app you register once ({' '}
            <a href="https://www.inaturalist.org/oauth/applications/new" target="_blank" rel="noreferrer"
               style={{color:'var(--accent-500)'}}>register here</a>, redirect URI can be anything),
            and updates <strong>your personal token above</strong> — never a shared account. If you
            don't set these, the admin-configured global credentials are used instead, same as before.
          </p>
          <div className="grid grid-cols-2 gap-2 mb-3">
            <input className="input text-sm" placeholder="Your iNaturalist username"
                   value={oauthUsername} onChange={e => setOauthUsername(e.target.value)}/>
            <input className="input text-sm" type="password"
                   placeholder={hasOauth ? '••••••••' : 'Your iNaturalist password'}
                   value={oauthPassword} onChange={e => setOauthPassword(e.target.value)}/>
            <input className="input text-sm" placeholder="OAuth client_id"
                   value={oauthClientId} onChange={e => setOauthClientId(e.target.value)}/>
            <input className="input text-sm" type="password"
                   placeholder={hasOauth ? '••••••••' : 'OAuth client_secret'}
                   value={oauthClientSecret} onChange={e => setOauthClientSecret(e.target.value)}/>
          </div>
          <button className="btn-primary flex items-center gap-1.5 text-sm mb-3"
                  onClick={async () => {
                    setOauthSaving(true)
                    try {
                      await api.auth.updateProfile({
                        inat_username: oauthUsername,
                        inat_password: oauthPassword,
                        inat_oauth_client_id: oauthClientId,
                        inat_oauth_client_secret: oauthClientSecret,
                      })
                      setHasOauth(!!(oauthUsername && oauthClientId))
                      setOauthPassword(''); setOauthClientSecret('')
                      showToast('OAuth credentials saved')
                    } catch (e) { showToast(e.message || 'Save failed', 'error') }
                    setOauthSaving(false)
                  }}
                  disabled={oauthSaving}>
            {oauthSaving ? <><RefreshCw size={12} className="animate-spin"/> Saving…</> : <><Leaf size={12}/> Save Credentials</>}
          </button>
          <InatRefreshInline/>
        </Section>
      )}

      {/* Notification choices live in Settings → My Notifications */}
      <button onClick={() => navigate('/settings?tab=mine')}
              className="card w-full p-4 flex items-center gap-3 text-left tactile-press">
        <Bell size={16} style={{ color: '#a78bfa' }}/>
        <span className="flex-1">
          <span className="block text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Notifications</span>
          <span className="block text-xs" style={{ color: 'var(--text-tertiary)' }}>Push alerts, email, watched birds</span>
        </span>
        <span style={{ color: 'var(--text-tertiary)' }}>›</span>
      </button>

      {hasServerPicker() && <ServerSection/>}
      <FeedbackSection/>
      <BlockedPeopleSection/>
      <DeleteAccountSection/>

      {/* Sign out */}
      <div className="flex items-center justify-between pt-1 pb-2 px-1">
        {profile?.last_login && (
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            Last login {format(new Date(profile.last_login), "MMM d, yyyy 'at' HH:mm")}
          </p>
        )}
        <button
          onClick={() => {
            localStorage.removeItem('chirp_token')
            navigate('/login', { replace: true })
            window.location.reload()
          }}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          style={{ color: '#f87171', border: '1px solid rgba(248,113,113,0.25)', background: 'rgba(248,113,113,0.06)' }}>
          <LogOut size={12}/>
          Sign out
        </button>
      </div>
    </div>
  )
}
