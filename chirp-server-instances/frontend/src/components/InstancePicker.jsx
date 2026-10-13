// Multi-instance addition (see ARCHITECTURE.md). Shown after a real
// login when the account has zero active instances selected — either
// because they have none yet (brand new account), or more than one and
// haven't picked which to use this session. Deliberately its own full
// screen, not a modal over the normal app shell, since none of the
// normal app's own data (which depends on an active instance existing
// at all) can render correctly yet at this point.
import { useState, useEffect } from 'react'
import { RefreshCw, MapPin, Plus, KeyRound, LogOut, Upload } from 'lucide-react'
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

function CreateForm({ onDone }) {
  const [name, setName] = useState('')
  const [locationName, setLocationName] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      await api.instances.create({ name, location_name: locationName || null, admin_password: password })
      onDone()
    } catch (e) {
      setError(e.message || 'Could not create location.')
    }
    setLoading(false)
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <InputField label="Location name" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Natick Backyard" required autoFocus/>
      <InputField label="City / area (optional)" value={locationName} onChange={e => setLocationName(e.target.value)} placeholder="e.g. Natick, MA"/>
      <InputField label="Set a password for this location" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="6+ characters" required/>
      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        You'll be the admin of this location. It gets its own real, separate database — nothing here is shared with any other location.
      </p>
      {error && <div className="p-3 rounded-xl text-sm" style={{ background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.25)', color: 'var(--pastel-red)' }}>{error}</div>}
      <button type="submit" disabled={loading} className="btn-primary w-full" style={{ padding: '11px 18px' }}>
        {loading ? <><RefreshCw size={14} className="animate-spin"/> Creating…</> : 'Create Location'}
      </button>
    </form>
  )
}

function JoinForm({ onDone }) {
  const [inviteCode, setInviteCode] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      await api.instances.join({ invite_code: inviteCode.trim().toUpperCase(), member_password: password })
      onDone()
    } catch (e) {
      setError(e.message || 'Could not join — check the invite code.')
    }
    setLoading(false)
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <InputField label="Invite code" value={inviteCode} onChange={e => setInviteCode(e.target.value)} placeholder="e.g. 7CCGEL6H" required autoFocus/>
      <InputField label="Set your own password for this location" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="6+ characters" required/>
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
  const [password, setPassword] = useState('')
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
      fd.append('admin_password', password)
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
      <InputField label="Set a password for this location" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="6+ characters" required/>
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


export default function InstancePicker({ onReady }) {
  const [instances, setInstances] = useState(null)
  const [mode, setMode] = useState('list')  // 'list' | 'create' | 'join' | 'import'
  const [switching, setSwitching] = useState(null)

  useEffect(() => {
    api.instances.list().then(setInstances).catch(() => setInstances([]))
  }, [])

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
            {instances?.length > 0 ? 'Choose a Location' : 'Get Started'}
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
            {instances?.length > 0 ? 'Pick which one to use this session' : 'Create your first location, or join one with an invite code'}
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
              <button onClick={() => setMode('import')} className="btn-secondary w-full flex items-center justify-center gap-1.5 text-sm">
                <Upload size={14}/> Import from Database File
              </button>
            </div>
          ) : (
            <>
              {mode === 'create' ? <CreateForm onDone={afterCreateOrJoin}/>
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
