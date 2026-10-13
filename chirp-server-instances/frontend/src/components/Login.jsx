import { useState } from 'react'
import { RefreshCw, Eye, EyeOff } from 'lucide-react'
import ChirpLogo from './ChirpLogo'
import { api } from '../lib/api'
import { hapticEvent } from '../lib/haptics'
import { hasServerPicker, openServerPicker } from '../native'

function InputField({ label, type = 'text', value, onChange, placeholder, required, autoFocus, autoComplete }) {
  const [show, setShow] = useState(false)
  const isPassword = type === 'password'
  return (
    <div>
      <label className="block text-sm font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>{label}</label>
      <div className="relative">
        <input className="input" type={isPassword && show ? 'text' : type}
               placeholder={placeholder} value={value} onChange={onChange}
               required={required} autoFocus={autoFocus} autoComplete={autoComplete}
               /* iPhone keyboards otherwise capitalise and autocorrect usernames */
               autoCapitalize="none" autoCorrect="off" spellCheck={false}/>
        {isPassword && (
          <button type="button" onClick={() => setShow(s => !s)}
            className="absolute right-3 top-1/2 -translate-y-1/2 transition-colors"
            style={{ color: 'var(--text-tertiary)' }} tabIndex={-1}>
            {show ? <EyeOff size={15}/> : <Eye size={15}/>}
          </button>
        )}
      </div>
    </div>
  )
}

function LoginForm({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      const data = await api.auth.login(username.trim(), password, remember)
      hapticEvent('success')
      onLogin(data)
    } catch (e) {
      hapticEvent('error')
      const msg = e.message || ''
      if (msg.includes('disabled')) setError('Account disabled. Contact an administrator.')
      else if (/too many/i.test(msg)) setError(msg.replace(/^.*?(Too many)/i, '$1'))
      else setError('Incorrect username or password.')
    }
    setLoading(false)
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <InputField label="Username" value={username} onChange={e => setUsername(e.target.value)} placeholder="username" required autoFocus autoComplete="username"/>
      <InputField label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" required autoComplete="current-password"/>
      <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: 'var(--text-secondary)' }}>
        <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)}
               className="w-4 h-4 accent-chirp-500"/>
        Stay signed in for 7 days
      </label>
      {error && (
        <div className="p-3 rounded-xl text-sm" style={{ background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.25)', color: 'var(--pastel-red)' }}>
          {error}
        </div>
      )}
      <button type="submit" disabled={loading} className="btn-primary w-full" style={{ padding: '11px 18px' }}>
        {loading ? <><RefreshCw size={14} className="animate-spin"/> Signing in…</> : 'Sign In'}
      </button>
    </form>
  )
}

function RegisterForm({ onBack, onLogin }) {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [useInvite, setUseInvite] = useState(false)
  const [inviteCode, setInviteCode] = useState('')
  const [memberPassword, setMemberPassword] = useState('')
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault(); setError(null)
    if (password !== confirm) { setError('Passwords do not match.'); return }
    if (password.length < 6) { setError('Password must be at least 6 characters.'); return }
    if (useInvite) {
      if (!inviteCode.trim()) { setError('Enter an invite code, or turn this off to just create an account.'); return }
      if (memberPassword.length < 6) { setError('That location\'s password must be at least 6 characters too.'); return }
    }
    setLoading(true)
    try {
      const data = await api.auth.register(username.trim(), email.trim(), password, useInvite ? inviteCode.trim() : null, useInvite ? memberPassword : null)
      // Registering with an invite code joins immediately and returns a
      // real session (see auth.py's register()) — no separate sign-in
      // step needed, same as if they'd just logged in normally.
      if (data.access_token && onLogin) onLogin(data)
      else setResult(data)
    }
    catch (e) { setError(e.message || 'Registration failed.') }
    setLoading(false)
  }

  if (result) return (
    <div className="text-center space-y-4 py-2">
      <div className="w-14 h-14 rounded-full flex items-center justify-center mx-auto text-xl"
           style={{ background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)' }}>✓</div>
      <div>
        <p className="font-semibold" style={{ color: 'var(--text-primary)' }}>Account created</p>
        <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>{result.message || 'You can sign in now.'}</p>
      </div>
      <button onClick={onBack} className="btn-secondary w-full">Back to Sign In</button>
    </div>
  )

  return (
    <form onSubmit={submit} className="space-y-4">
      <InputField label="Username" value={username} onChange={e => setUsername(e.target.value)} placeholder="choose a username" required autoFocus autoComplete="username"/>
      <InputField label="Email (optional)" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email"/>
      <InputField label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="6+ characters" required autoComplete="new-password"/>
      <InputField label="Confirm password" type="password" value={confirm} onChange={e => setConfirm(e.target.value)} placeholder="repeat password" required autoComplete="new-password"/>

      <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: 'var(--text-secondary)' }}>
        <input type="checkbox" checked={useInvite} onChange={e => setUseInvite(e.target.checked)}
               className="w-4 h-4 accent-chirp-500"/>
        I have an invite code for a location
      </label>

      {useInvite && (
        <div className="space-y-4 pl-1 border-l-2" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="pl-3 space-y-4">
            <InputField label="Invite code" value={inviteCode} onChange={e => setInviteCode(e.target.value)} placeholder="e.g. ABC123" required/>
            <InputField label="Location password" type="password" value={memberPassword} onChange={e => setMemberPassword(e.target.value)} placeholder="6+ characters" required/>
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              This is a separate password just for that location — kept independent from your account password above.
              You'll join immediately as a viewer, and that location's admins will be notified.
            </p>
          </div>
        </div>
      )}

      {error && <div className="p-3 rounded-xl text-sm" style={{ background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.25)', color: 'var(--pastel-red)' }}>{error}</div>}
      <button type="submit" disabled={loading} className="btn-primary w-full" style={{ padding: '11px 18px' }}>
        {loading ? <><RefreshCw size={14} className="animate-spin"/> {useInvite ? 'Joining…' : 'Requesting…'}</> : (useInvite ? 'Create Account & Join' : 'Request Account')}
      </button>
    </form>
  )
}

export default function Login({ onLogin }) {
  const [mode, setMode] = useState('login')
  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: 'var(--bg-base)' }}>
      {/* Background glow */}
      <div className="fixed inset-0 pointer-events-none" style={{ background: 'var(--gradient-hero)' }}/>

      <div className="w-full max-w-sm relative z-10">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <ChirpLogo size={56} animate="draw"/>
          </div>
          <h1 className="font-display text-3xl font-bold" style={{ color: 'var(--text-primary)', letterSpacing: '-.02em' }}>Chirp</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>Bird Call Detection</p>
        </div>

        <div className="card-glass p-7 animate-scale-in">
          {/* Tabs */}
          <div className="flex mb-6 p-1 rounded-xl" style={{ background: 'var(--bg-raised)' }}>
            {[['login','Sign In'],['register','Register']].map(([m, label]) => (
              <button key={m} onClick={() => setMode(m)}
                className="flex-1 py-2 text-sm font-medium rounded-lg transition-all"
                style={mode === m
                  ? { background: 'var(--bg-card)', color: 'var(--text-primary)', boxShadow: '0 1px 3px rgba(0,0,0,.3)' }
                  : { color: 'var(--text-tertiary)' }}>
                {label}
              </button>
            ))}
          </div>
          {mode === 'login' ? <LoginForm onLogin={onLogin}/> : <RegisterForm onBack={() => setMode('login')} onLogin={onLogin}/>}
        </div>

        <p className="text-xs text-center mt-4" style={{ color: 'var(--text-tertiary)' }}>
          {mode === 'login' ? 'No account yet? Switch to Register above.' : 'You can sign in right away — no approval needed.'}
        </p>
        <p className="text-xs text-center mt-3">
          <a href="/about" style={{ color: 'var(--accent-400)' }}>What is Chirp?</a>
        </p>
        {hasServerPicker() && (
          <p className="text-xs text-center mt-2" style={{ color: 'var(--text-tertiary)' }}>
            Server: {window.location.host} ·{' '}
            <button type="button" onClick={openServerPicker} style={{ color: 'var(--accent-400)' }}>Change</button>
          </p>
        )}
      </div>
    </div>
  )
}
