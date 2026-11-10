// Multi-instance addition (see ARCHITECTURE.md). Shown after a real
// login when the account has zero active instances selected — either
// because they have none yet (brand new account), or more than one and
// haven't picked which to use this session. Deliberately its own full
// screen, not a modal over the normal app shell, since none of the
// normal app's own data (which depends on an active instance existing
// at all) can render correctly yet at this point.
import { useState, useEffect } from 'react'
import { RefreshCw, MapPin, Plus, KeyRound, LogOut, Upload, Clock, X } from 'lucide-react'
import ChirpLogo from './ChirpLogo'
import { api, tokenStore } from '../lib/api'

function InputField({ label, type = 'text', value, onChange, placeholder, required, autoFocus }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>{label}</label>
      <input className="input" type={type} placeholder={placeholder} value={value}
             onChange={onChange} required={required} autoFocus={autoFocus}/>
    </div>
  )
}

function CreateForm({ onDone, onPending, approval }) {
  const [name, setName] = useState('')
  const [locationName, setLocationName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      const res = await api.instances.create({ name, location_name: locationName || null })
      if (res?.pending) onPending()
      else onDone()
    } catch (e) {
      setError(e.message || 'Could not create location.')
    }
    setLoading(false)
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <InputField label="Location name" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Natick Backyard" required autoFocus/>
      <InputField label="City / area (optional)" value={locationName} onChange={e => setLocationName(e.target.value)} placeholder="e.g. Natick, MA"/>
      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        You'll be the admin of this location. It gets its own separate database; nothing is shared with other locations.
      </p>
      {approval?.approval_required && (
        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          New locations here are approved by a Chirp admin, usually within a day.
          {approval.has_email ? " We'll email you when it's ready." : ' Check back here; it appears in your list once approved.'}
          {' '}Joining with an invite code is instant.
        </p>
      )}
      {error && <div className="p-3 rounded-xl text-sm" style={{ background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.25)', color: 'var(--pastel-red)' }}>{error}</div>}
      <button type="submit" disabled={loading} className="btn-primary w-full" style={{ padding: '11px 18px' }}>
        {loading ? <><RefreshCw size={14} className="animate-spin"/> {approval?.approval_required ? 'Sending…' : 'Creating…'}</>
          : approval?.approval_required ? 'Request Location' : 'Create Location'}
      </button>
    </form>
  )
}

function JoinForm({ onDone }) {
  const [inviteCode, setInviteCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      await api.instances.join({ invite_code: inviteCode.trim().toUpperCase() })
      onDone()
    } catch (e) {
      setError(e.message || 'Could not join — check the invite code.')
    }
    setLoading(false)
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <InputField label="Invite code" value={inviteCode} onChange={e => setInviteCode(e.target.value)} placeholder="e.g. 7CCGEL6H" required autoFocus/>
      {error && <div className="p-3 rounded-xl text-sm" style={{ background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.25)', color: 'var(--pastel-red)' }}>{error}</div>}
      <button type="submit" disabled={loading} className="btn-primary w-full" style={{ padding: '11px 18px' }}>
        {loading ? <><RefreshCw size={14} className="animate-spin"/> Joining…</> : 'Join Location'}
      </button>
    </form>
  )
}

function ImportForm({ onDone }) {
  const [file, setFile] = useState(null)
  const [name, setName] = useState('')
  const [locationName, setLocationName] = useState('')
  const [adminUsername, setAdminUsername] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (!file) { setError('Choose a database file first.'); return }
    setLoading(true); setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('name', name)
      if (locationName) fd.append('location_name', locationName)
      if (adminUsername) fd.append('admin_username', adminUsername)
      await api.instances.import(fd)
      onDone()
    } catch (e) {
      setError(e.message || 'Could not import that database.')
    }
    setLoading(false)
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>Database file</label>
        <input className="input" type="file" accept=".db,.sqlite,.sqlite3"
               onChange={e => setFile(e.target.files?.[0] || null)} required/>
        <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
          A chirp-server database (e.g. one downloaded from Settings → Backup on a single-location deployment), or a backup of another location here.
        </p>
      </div>
      <InputField label="Location name" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Natick Backyard" required/>
      <InputField label="City / area (optional)" value={locationName} onChange={e => setLocationName(e.target.value)} placeholder="e.g. Natick, MA"/>
      <InputField label="Your username here (optional)" value={adminUsername} onChange={e => setAdminUsername(e.target.value)} placeholder="Defaults to your current username"/>
      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        Every recording, detection, and setting in the file is copied in as-is. Any users already in the file are kept; you're added as this location's admin.
      </p>
      <p className="text-xs" style={{ color: 'var(--pastel-amber)' }}>
        This only imports the database — audio files and spectrograms are NOT included (a database upload can't carry them). Copy this location's recordings/spectrograms/clips folders over separately on the server, or spectrograms and playback will be unavailable until you do.
      </p>
      {error && <div className="p-3 rounded-xl text-sm" style={{ background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.25)', color: 'var(--pastel-red)' }}>{error}</div>}
      <button type="submit" disabled={loading} className="btn-primary w-full" style={{ padding: '11px 18px' }}>
        {loading ? <><RefreshCw size={14} className="animate-spin"/> Importing…</> : 'Import Database'}
      </button>
    </form>
  )
}

// Location requests waiting for a Chirp admin (or turned down), so nobody
// is left wondering where their new location went.
function RequestList({ requests, onChanged }) {
  const [busy, setBusy] = useState(null)
  if (!requests?.length) return null
  const remove = async (id) => {
    setBusy(id)
    try { await api.instances.cancelRequest(id) } catch {}
    setBusy(null)
    onChanged()
  }
  return (
    <div className="space-y-2">
      {requests.map(r => {
        const denied = r.status === 'denied'
        return (
          <div key={r.id} className="flex items-start gap-3 p-3.5 rounded-xl"
               style={{ background: 'var(--bg-raised)', border: `1px dashed ${denied ? 'rgba(239,68,68,.35)' : 'var(--border-subtle)'}` }}>
            <Clock size={16} style={{ color: denied ? 'var(--pastel-red)' : 'var(--text-tertiary)', flexShrink: 0, marginTop: 2 }}/>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)', overflowWrap: 'anywhere' }}>{r.name}</p>
              <p className="text-xs" style={{ color: denied ? 'var(--pastel-red)' : 'var(--text-tertiary)' }}>
                {denied ? `Not approved${r.deny_reason ? `: ${r.deny_reason}` : ''}` : 'Waiting for approval'}
              </p>
            </div>
            <button onClick={() => remove(r.id)} disabled={busy === r.id} title={denied ? 'Dismiss' : 'Withdraw request'}
                    aria-label={denied ? `Dismiss ${r.name}` : `Withdraw ${r.name}`}
                    className="p-1 rounded flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
              {busy === r.id ? <RefreshCw size={13} className="animate-spin"/> : <X size={14}/>}
            </button>
          </div>
        )
      })}
    </div>
  )
}


export default function InstancePicker({ onReady }) {
  const [instances, setInstances] = useState(null)
  const [mode, setMode] = useState('list')  // 'list' | 'create' | 'join' | 'import'
  const [switching, setSwitching] = useState(null)

  const [approval, setApproval] = useState(null)   // { approval_required, has_email, requests }

  const loadRequests = () => api.instances.requests().then(setApproval).catch(() => setApproval(null))
  useEffect(() => {
    api.instances.list().then(setInstances).catch(() => setInstances([]))
    loadRequests()
  }, [])
  const waiting = approval?.requests || []
  const pending = waiting.some(r => r.status === 'pending')

  // While a request waits, check every 30 s; once approved the new location
  // shows up in the list (and opens by itself when it's their only one).
  useEffect(() => {
    if (!pending) return
    const t = setInterval(async () => {
      try {
        const list = await api.instances.list()
        setInstances(prev => {
          if (prev?.length === 0 && list.length === 1) switchTo(list[0].id)
          return list
        })
        loadRequests()
      } catch {}
    }, 30000)
    return () => clearInterval(t)
  }, [pending])

  const switchTo = async (id) => {
    setSwitching(id)
    try {
      await api.instances.switch(id)
      onReady()
    } catch {
      setSwitching(null)
    }
  }

  const afterCreateOrJoin = () => onReady()

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: 'var(--bg-base)' }}>
      <div className="fixed inset-0 pointer-events-none" style={{ background: 'var(--gradient-hero)' }}/>

      <div className="w-full max-w-sm relative z-10">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <ChirpLogo size={56} animate="draw"/>
          </div>
          <h1 className="font-display text-3xl font-bold" style={{ color: 'var(--text-primary)', letterSpacing: '-.02em' }}>
            {instances?.length > 0 ? 'Choose a Location' : waiting.some(r => r.status === 'pending') ? 'Almost There' : 'Get Started'}
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
            {instances?.length > 0 ? 'Pick which one to use this session'
              : waiting.some(r => r.status === 'pending')
                ? (approval?.has_email ? "Your location is being set up. We'll email you when it's ready." : 'Your location is being set up. It appears here once approved.')
                : approval?.approval_required ? 'Request your first location, or join one with an invite code'
                : 'Create your first location, or join one with an invite code'}
          </p>
        </div>

        <div className="card-glass p-7 animate-scale-in space-y-5">
          {instances === null && (
            <div className="flex justify-center py-6"><RefreshCw size={18} className="animate-spin" style={{ color: 'var(--text-tertiary)' }}/></div>
          )}

          {instances?.length > 0 && mode === 'list' && (
            <div className="space-y-2">
              {instances.map(inst => (
                <button key={inst.id} onClick={() => switchTo(inst.id)} disabled={switching === inst.id}
                        className="w-full flex items-center gap-3 p-3.5 rounded-xl text-left transition-all hover:opacity-90"
                        style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
                  <MapPin size={16} style={{ color: 'var(--accent-400)', flexShrink: 0 }}/>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{inst.name}</p>
                    {inst.location_name && <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>{inst.location_name}</p>}
                  </div>
                  {switching === inst.id && <RefreshCw size={13} className="animate-spin" style={{ color: 'var(--text-tertiary)' }}/>}
                </button>
              ))}
            </div>
          )}

          {mode === 'list' && <RequestList requests={waiting} onChanged={loadRequests}/>}

          {instances !== null && (mode === 'list' ? (
            <div className="space-y-2 pt-1">
              <div className="flex gap-2">
                <button onClick={() => setMode('create')} className="btn-secondary flex-1 flex items-center justify-center gap-1.5 text-sm">
                  <Plus size={14}/> New Location
                </button>
                <button onClick={() => setMode('join')} className="btn-secondary flex-1 flex items-center justify-center gap-1.5 text-sm">
                  <KeyRound size={14}/> Join with Code
                </button>
              </div>
              {!approval?.approval_required && (
                <button onClick={() => setMode('import')} className="btn-secondary w-full flex items-center justify-center gap-1.5 text-sm">
                  <Upload size={14}/> Import from Database File
                </button>
              )}
            </div>
          ) : (
            <>
              {mode === 'create' ? <CreateForm onDone={afterCreateOrJoin} approval={approval}
                                               onPending={() => { loadRequests(); setMode('list') }}/>
                : mode === 'join' ? <JoinForm onDone={afterCreateOrJoin}/>
                : <ImportForm onDone={afterCreateOrJoin}/>}
              <button onClick={() => setMode('list')} className="text-xs w-full text-center" style={{ color: 'var(--text-tertiary)' }}>
                ← Back
              </button>
            </>
          ))}
        </div>

        <button onClick={() => { tokenStore.clear(); window.location.reload() }}
                className="flex items-center justify-center gap-1.5 text-xs mx-auto mt-4" style={{ color: 'var(--text-tertiary)' }}>
          <LogOut size={12}/> Sign out
        </button>
      </div>
    </div>
  )
}
