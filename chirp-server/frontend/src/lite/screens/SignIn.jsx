import { useEffect, useState } from 'react'
import { account } from '../api'
import { APP_NAME } from '../context'
import { BirdMark } from '../icons'

export default function SignIn({ onDone }) {
  const [username, setUsername] = useState(() => localStorage.getItem('chirp_user') || '')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await account.login(username.trim(), password)
      onDone()
    } catch (err) {
      setError(err.message === 'Failed to fetch' ? 'Can’t reach your Chirp. Check your connection.' : err.message)
      setBusy(false)
    }
  }

  return (
    <div className="welcome">
      <div className="welcome-art" aria-hidden="true">
        <span className="sun" />
        <span className="hill hill-back" />
        <span className="hill" />
        <BirdMark tile={false} size={150} className="welcome-bird bob" />
      </div>
      <form className="welcome-card" onSubmit={submit}>
        <h1>{APP_NAME}</h1>
        <p className="muted">The birds in your backyard, in pictures and sound.</p>
        <label className="field">
          <span>Username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
                 autoCapitalize="none" autoCorrect="off" required />
        </label>
        <label className="field">
          <span>Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 autoComplete="current-password" required />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn wide big" disabled={busy || !username || !password}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="fine">Use the same account as Chirp. <a href="/">Open full Chirp</a></p>
      </form>
    </div>
  )
}

// Accounts with several sites (multi-site servers) pick one.
export function PickSite({ onDone }) {
  const [sites, setSites] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    account.sites().then(setSites).catch((e) => setError(e.message))
  }, [])
  useEffect(() => {
    if (sites?.length === 1) account.pickSite(sites[0].id).then(onDone).catch((e) => setError(e.message))
  }, [sites, onDone])

  const pick = async (id) => {
    try { await account.pickSite(id); onDone() } catch (e) { setError(e.message) }
  }
  return (
    <div className="welcome">
      <div className="welcome-card">
        <BirdMark size={64} />
        <h1>Which yard?</h1>
        {error && <p className="form-error" role="alert">{error}</p>}
        {sites?.length === 0 && <p className="muted">Your account isn’t part of a Chirp site yet. Ask its owner for an invite, or set one up in <a href="/">full Chirp</a>.</p>}
        <div className="site-list">
          {sites?.length > 1 && sites.map((s) => (
            <button key={s.id} className="site" onClick={() => pick(s.id)}>
              <strong>{s.name}</strong>
              {s.location_name && <span>{s.location_name}</span>}
            </button>
          ))}
        </div>
        <button className="btn btn-soft wide" onClick={() => { account.logout(); window.location.reload() }}>Sign out</button>
      </div>
    </div>
  )
}
