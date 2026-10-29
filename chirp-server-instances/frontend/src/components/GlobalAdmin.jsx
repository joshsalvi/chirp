import { useEffect, useState } from 'react'
import { Shield, Users, Home, Trash2, Plus, X, ChevronDown, Check, RefreshCw, UserPlus, Upload, Radio, Laptop, Inbox } from 'lucide-react'
import { api } from '../lib/api'
import SupportMessagesCard from './SupportMessages'
// ourchirp.com's own tabs; an empty list in everyone else's build.
import { websiteTabsFirst, websiteTabsLast } from '../website/WebsiteAdmin'

const ROLE_COLORS = {
  admin:     { bg: 'rgba(167,139,250,.15)', color: '#c4b5fd', border: 'rgba(167,139,250,.3)' },
  submitter: { bg: 'rgba(251,146,60,.12)',  color: '#fdba74', border: 'rgba(251,146,60,.28)' },
  viewer:    { bg: 'rgba(34,197,94,.1)',    color: 'var(--pastel-green)', border: 'rgba(34,197,94,.2)' },
}
const ROLES = ['admin', 'submitter', 'viewer']

function RoleBadgeDropdown({ role, onChange, disabled }) {
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const c = ROLE_COLORS[role] || ROLE_COLORS.viewer

  const pick = async (newRole) => {
    if (newRole === role) { setOpen(false); return }
    setSaving(true)
    try { await onChange(newRole) } finally { setSaving(false); setOpen(false) }
  }

  return (
    <div className="relative">
      <button onClick={() => !disabled && setOpen(o => !o)} disabled={disabled || saving}
              className="flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold transition-all"
              style={{ background: c.bg, color: c.color, border: `1px solid ${c.border}` }}>
        {saving ? '…' : role}
        {!disabled && <ChevronDown size={10}/>}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)}/>
          <div className="absolute right-0 top-full mt-1 z-50 rounded-xl overflow-hidden shadow-xl"
               style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', minWidth: 120 }}>
            {ROLES.map(r => {
              const rc = ROLE_COLORS[r]
              return (
                <button key={r} onClick={() => pick(r)}
                        className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm hover:bg-raised transition-colors">
                  <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: rc.color }}/>
                  <span style={{ color: 'var(--text-primary)' }}>{r}</span>
                </button>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <div className="card px-4 py-3 flex-1 text-center" style={{ border: '1px solid var(--border-subtle)' }}>
      <p className="text-2xl font-bold" style={{ color: 'var(--accent-400)' }}>{value ?? '—'}</p>
      <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
    </div>
  )
}

function AddMemberForm({ instanceId, onAdded, onCancel }) {
  const [username, setUsername] = useState('')
  const [role, setRole] = useState('viewer')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const submit = async () => {
    if (!username.trim()) { setError('Enter a username.'); return }
    setSaving(true); setError(null)
    try {
      await api.admin.addMember(instanceId, { username: username.trim(), role })
      onAdded()
    } catch (e) {
      setError(e.message || 'Failed to add member')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-lg p-3 mt-2 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
      {error && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{error}</p>}
      <div className="grid grid-cols-2 gap-2">
        <input className="input text-xs" placeholder="Username" value={username}
               onChange={e => setUsername(e.target.value)}/>
        <select className="input text-xs" value={role} onChange={e => setRole(e.target.value)}>
          {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <p className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
        The username must belong to an existing account. They sign in to this site with their usual password.
      </p>
      <div className="flex gap-2">
        <button onClick={submit} disabled={saving} className="btn-primary text-xs flex items-center gap-1">
          <Check size={11}/> {saving ? 'Adding…' : 'Add'}
        </button>
        <button onClick={onCancel} className="btn-ghost text-xs">Cancel</button>
      </div>
    </div>
  )
}

function InstanceCard({ instance, onDeleted }) {
  const [expanded, setExpanded] = useState(false)
  const [members, setMembers] = useState(null)
  const [loadingMembers, setLoadingMembers] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const loadMembers = async () => {
    setLoadingMembers(true)
    try { setMembers(await api.admin.instanceMembers(instance.id)) }
    catch (e) { alert(e.message) }
    finally { setLoadingMembers(false) }
  }

  const toggleExpand = () => {
    const next = !expanded
    setExpanded(next)
    if (next && members === null) loadMembers()
  }

  const changeRole = async (membershipId, newRole) => {
    try {
      await api.admin.updateMembershipRole(membershipId, newRole)
      setMembers(prev => prev.map(m => m.membership_id === membershipId ? { ...m, role: newRole } : m))
    } catch (e) { alert(e.message) }
  }

  const removeMember = async (membershipId, username) => {
    if (!confirm(`Remove ${username} from ${instance.name}? They'll no longer be able to switch into this location.`)) return
    try {
      await api.admin.removeMembership(membershipId)
      setMembers(prev => prev.filter(m => m.membership_id !== membershipId))
    } catch (e) { alert(e.message) }
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      const res = await api.admin.deleteInstance(instance.id)
      onDeleted(instance.id, res.note)
    } catch (e) {
      alert(e.message)
      setDeleting(false)
    }
  }

  return (
    <div className="card p-4" style={{ border: '1px solid var(--border-subtle)' }}>
      <div className="flex items-center justify-between gap-3">
        <button onClick={toggleExpand} className="flex-1 flex items-center gap-3 text-left min-w-0">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
               style={{ background: 'var(--nav-active-bg)' }}>
            <Home size={16} style={{ color: 'var(--accent-400)' }}/>
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-sm truncate" style={{ color: 'var(--text-primary)' }}>{instance.name}</p>
            <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>
              {instance.location_name || 'No location set'} · {instance.member_count} member{instance.member_count === 1 ? '' : 's'}
              {instance.created_by_username && <> · created by {instance.created_by_username}</>}
            </p>
          </div>
          <ChevronDown size={16} style={{ color: 'var(--text-tertiary)', transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform .15s', flexShrink: 0 }}/>
        </button>
        {confirmDelete ? (
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <button onClick={handleDelete} disabled={deleting}
                    className="text-xs px-2 py-1 rounded-lg font-medium" style={{ background: 'rgba(248,113,113,.15)', color: '#f87171' }}>
              {deleting ? 'Removing…' : 'Confirm'}
            </button>
            <button onClick={() => setConfirmDelete(false)} className="btn-ghost text-xs px-2 py-1">Cancel</button>
          </div>
        ) : (
          <button onClick={() => setConfirmDelete(true)} title="Remove this instance from the registry"
                  className="p-1.5 rounded-lg flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
            <Trash2 size={14}/>
          </button>
        )}
      </div>

      {expanded && (
        <div className="mt-3 pt-3 space-y-1.5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          {loadingMembers ? (
            <div className="skeleton h-10 rounded-lg"/>
          ) : (
            (members || []).map(m => (
              <div key={m.membership_id} className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg"
                   style={{ background: 'var(--bg-raised)' }}>
                <div className="min-w-0">
                  <p className="text-sm truncate" style={{ color: 'var(--text-primary)' }}>{m.username}</p>
                  {m.email && <p className="text-[11px] truncate" style={{ color: 'var(--text-tertiary)' }}>{m.email}</p>}
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <RoleBadgeDropdown role={m.role} onChange={(r) => changeRole(m.membership_id, r)}/>
                  <button onClick={() => removeMember(m.membership_id, m.username)} title="Remove from this instance"
                          className="p-1 rounded" style={{ color: 'var(--text-tertiary)' }}>
                    <X size={13}/>
                  </button>
                </div>
              </div>
            ))
          )}
          {showAdd ? (
            <AddMemberForm instanceId={instance.id} onCancel={() => setShowAdd(false)}
                            onAdded={() => { setShowAdd(false); loadMembers() }}/>
          ) : (
            <button onClick={() => setShowAdd(true)} className="btn-ghost text-xs flex items-center gap-1 mt-1">
              <UserPlus size={12}/> Add member
            </button>
          )}
          <p className="text-[11px] pt-1" style={{ color: 'var(--text-tertiary)' }}>
            Invite code: <span className="font-mono">{instance.invite_code}</span>
          </p>
          <InstanceDiagnosticsPanel instanceId={instance.id}/>
        </div>
      )}
    </div>
  )
}

function NewInstanceModal({ onClose, onCreated }) {
  const [mode, setMode] = useState('create')  // 'create' | 'import'
  const [name, setName] = useState('')
  const [locationName, setLocationName] = useState('')
  const [adminUsername, setAdminUsername] = useState('')
  const [password, setPassword] = useState('')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Deliberately does NOT try to switch the admin's own active instance
  // back to whatever it was before — create()/import() both log the
  // caller into the newly created instance as a side effect (that's
  // how those same endpoints already work for a normal user creating
  // their first location), so a global admin ends up viewing the new
  // location after this. That's an acceptable, honest outcome rather
  // than guessing at which instance to restore; they can switch back
  // via the normal instance picker if needed.

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      if (mode === 'create') {
        await api.instances.create({ name, location_name: locationName || null, admin_password: password })
      } else {
        if (!file) { setError('Choose a database file first.'); setLoading(false); return }
        const fd = new FormData()
        fd.append('file', file)
        fd.append('name', name)
        if (locationName) fd.append('location_name', locationName)
        if (adminUsername) fd.append('admin_username', adminUsername)
        fd.append('admin_password', password)
        await api.instances.import(fd)
      }
      onCreated()
    } catch (e) {
      setError(e.message || 'Could not create the location.')
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,.6)' }} onClick={onClose}>
      <div className="card-glass p-6 w-full max-w-sm space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>New Location</h3>
          <button onClick={onClose}><X size={16} style={{ color: 'var(--text-tertiary)' }}/></button>
        </div>

        <div className="flex gap-1 p-1 rounded-lg w-fit" style={{ background: 'var(--bg-raised)' }}>
          {[['create', 'Create Empty'], ['import', 'Import Database']].map(([val, label]) => (
            <button key={val} type="button" onClick={() => setMode(val)}
                    className="px-3 py-1 rounded text-xs font-medium transition-all"
                    style={mode === val ? { background: 'var(--bg-card)', color: 'var(--text-primary)' } : { color: 'var(--text-tertiary)' }}>
              {label}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-3">
          {mode === 'import' && (
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Database file</label>
              <input className="input" type="file" accept=".db,.sqlite,.sqlite3"
                     onChange={e => setFile(e.target.files?.[0] || null)} required/>
            </div>
          )}
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Location name</label>
            <input className="input" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Natick Backyard" required/>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>City / area (optional)</label>
            <input className="input" value={locationName} onChange={e => setLocationName(e.target.value)} placeholder="e.g. Natick, MA"/>
          </div>
          {mode === 'import' && (
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Admin username there (optional)</label>
              <input className="input" value={adminUsername} onChange={e => setAdminUsername(e.target.value)} placeholder="Defaults to your own username"/>
            </div>
          )}
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>Admin password for this location</label>
            <input className="input" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="6+ characters" required/>
          </div>
          {mode === 'import' && (
            <>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                Every recording, detection, and setting in the file is copied in as-is. Users already in the file are kept.
              </p>
              <p className="text-xs" style={{ color: 'var(--pastel-amber)' }}>
                This only imports the database — audio files and spectrograms are NOT included (a database upload can't carry them). Copy this location's recordings/spectrograms/clips folders over separately on the server, or spectrograms and playback will be unavailable until you do.
              </p>
            </>
          )}
          {error && <div className="p-2.5 rounded-lg text-xs" style={{ background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.25)', color: 'var(--pastel-red)' }}>{error}</div>}
          <button type="submit" disabled={loading} className="btn-primary w-full text-sm" style={{ padding: '9px 16px' }}>
            {loading
              ? <><RefreshCw size={13} className="animate-spin"/> {mode === 'create' ? 'Creating…' : 'Importing…'}</>
              : (mode === 'create' ? <><Plus size={13}/> Create Location</> : <><Upload size={13}/> Import Database</>)}
          </button>
        </form>
      </div>
    </div>
  )
}

function InstanceDiagnosticsPanel({ instanceId }) {
  const [mode, setMode] = useState('full')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [running, setRunning] = useState(false)

  const run = async () => {
    setRunning(true)
    setError(null)
    try {
      setResult(await api.admin.instanceDiagnostics(instanceId, mode))
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
      <div className="flex items-center gap-2">
        <select value={mode} onChange={e => setMode(e.target.value)}
                className="text-xs px-2 py-1 rounded-lg" style={{ background: 'var(--bg-raised)', color: 'var(--text-primary)' }}>
          <option value="full">Full</option>
          <option value="db">Database only</option>
          <option value="mic">Mic only</option>
        </select>
        <button onClick={run} disabled={running} className="btn-ghost text-xs flex items-center gap-1">
          <RefreshCw size={12} className={running ? 'animate-spin' : ''}/> {running ? 'Running…' : 'Run Diagnostics'}
        </button>
        {result && <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{result.elapsed_ms}ms</span>}
      </div>
      {error && <p className="text-xs mt-1.5" style={{ color: 'var(--pastel-red)' }}>{error}</p>}
      {result && (
        <pre className="text-[10px] mt-1.5 p-2 rounded-lg overflow-auto max-h-64"
             style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  )
}

function InstancesTab() {
  const [instances, setInstances] = useState(null)
  const [error, setError] = useState(null)
  const [showNew, setShowNew] = useState(false)

  const load = () => {
    api.admin.instances().then(setInstances).catch(e => setError(e.message))
  }
  useEffect(load, [])

  const handleDeleted = (id, note) => {
    setInstances(prev => prev.filter(i => i.id !== id))
    if (note) alert(note)
  }

  const handleCreated = () => {
    setShowNew(false)
    setInstances(null)
    load()
  }

  return (
    <div className="space-y-2">
      <button onClick={() => setShowNew(true)}
              className="btn-secondary w-full flex items-center justify-center gap-1.5 text-sm mb-1">
        <Plus size={14}/> New Location
      </button>
      {showNew && <NewInstanceModal onClose={() => setShowNew(false)} onCreated={handleCreated}/>}
      {error && <p className="text-sm" style={{ color: 'var(--pastel-red)' }}>{error}</p>}
      {!error && instances === null && <div className="space-y-2">{[0,1].map(i => <div key={i} className="skeleton h-16 rounded-xl"/>)}</div>}
      {!error && instances?.length === 0 && <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>No instances exist on this server yet.</p>}
      {!error && instances?.length > 0 && instances.map(inst => <InstanceCard key={inst.id} instance={inst} onDeleted={handleDeleted}/>)}
    </div>
  )
}

function UserRow({ user, onUpdated }) {
  const [busy, setBusy] = useState(false)

  const toggle = async (field) => {
    setBusy(true)
    try {
      const updated = await api.admin.updateUser(user.id, { [field]: !user[field] })
      onUpdated(updated)
    } catch (e) {
      alert(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card px-4 py-3 flex items-center gap-3" style={{ border: '1px solid var(--border-subtle)', opacity: user.active ? 1 : 0.55 }}>
      <div className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0"
           style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }}>
        {user.username[0].toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>{user.username}</span>
          {user.is_global_admin && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full font-semibold" style={{ background: 'rgba(167,139,250,.15)', color: '#c4b5fd' }}>
              GLOBAL ADMIN
            </span>
          )}
          {!user.active && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full font-semibold" style={{ background: 'rgba(248,113,113,.12)', color: '#f87171' }}>
              DISABLED
            </span>
          )}
        </div>
        <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>
          {user.email || 'no email'} · {user.instance_count} location{user.instance_count === 1 ? '' : 's'}
          {user.last_login && <> · last seen {new Date(user.last_login).toLocaleDateString()}</>}
        </p>
      </div>
      <div className="flex items-center gap-1.5 flex-shrink-0">
        <button onClick={() => toggle('is_global_admin')} disabled={busy}
                className="text-xs px-2.5 py-1 rounded-full font-medium"
                style={user.is_global_admin
                  ? { background: 'rgba(167,139,250,.15)', color: '#c4b5fd' }
                  : { background: 'var(--bg-raised)', color: 'var(--text-tertiary)' }}>
          {user.is_global_admin ? 'Demote' : 'Make admin'}
        </button>
        <button onClick={() => toggle('active')} disabled={busy}
                className="text-xs px-2.5 py-1 rounded-full font-medium"
                style={user.active
                  ? { background: 'var(--bg-raised)', color: 'var(--text-tertiary)' }
                  : { background: 'rgba(34,197,94,.12)', color: 'var(--pastel-green)' }}>
          {user.active ? 'Disable' : 'Enable'}
        </button>
      </div>
    </div>
  )
}

function UsersTab() {
  const [users, setUsers] = useState(null)
  const [error, setError] = useState(null)

  const load = () => {
    api.admin.users().then(setUsers).catch(e => setError(e.message))
  }
  useEffect(load, [])

  const handleUpdated = (updated) => {
    setUsers(prev => prev.map(u => u.id === updated.id ? updated : u))
  }

  if (error) return <p className="text-sm" style={{ color: 'var(--pastel-red)' }}>{error}</p>
  if (users === null) return <div className="space-y-2">{[0,1,2].map(i => <div key={i} className="skeleton h-16 rounded-xl"/>)}</div>

  return (
    <div className="space-y-2">
      {users.map(u => <UserRow key={u.id} user={u} onUpdated={handleUpdated}/>)}
    </div>
  )
}

function MessagesTab() {
  return <SupportMessagesCard/>
}

const TABS = [
  ...(websiteTabsFirst.length ? websiteTabsFirst : [['messages', 'Messages', Inbox, MessagesTab]]),
  ['instances', 'Instances', Home, InstancesTab],
  ['users', 'Users', Users, UsersTab],
  ['network', 'Network', Radio, NetworkTab],
  ...websiteTabsLast,
]

export default function GlobalAdmin() {
  const [tab, setTab] = useState('instances')
  const [overview, setOverview] = useState(null)
  const [forbidden, setForbidden] = useState(false)

  useEffect(() => {
    api.admin.overview().then(setOverview).catch(e => {
      if (e.status === 403) setForbidden(true)
    })
  }, [])

  if (forbidden) {
    return (
      <div className="page-root max-w-2xl mx-auto">
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
          This page is only available to a server-wide global admin.
        </p>
      </div>
    )
  }

  return (
    <div className="page-root max-w-3xl mx-auto">
      <div className="flex items-center gap-2 mb-5">
        <Shield size={18} style={{ color: 'var(--accent-400)' }}/>
        <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Global Admin</h1>
      </div>

      <div className="flex gap-2 mb-5">
        <StatCard label="Locations" value={overview?.total_instances}/>
        <StatCard label="Accounts" value={overview?.total_users}/>
        <StatCard label="Global admins" value={overview?.total_global_admins}/>
      </div>

      <div className="flex gap-1 mb-4 p-1 rounded-xl w-fit max-w-full overflow-x-auto" style={{ background: 'var(--bg-raised)' }}>
        {TABS.map(([id, label, Icon]) => (
          <button key={id} onClick={() => setTab(id)}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all"
                  style={tab === id
                    ? { background: 'var(--bg-card)', color: 'var(--text-primary)' }
                    : { color: 'var(--text-tertiary)' }}>
            <Icon size={13}/> {label}
          </button>
        ))}
      </div>

      {(() => { const Tab = (TABS.find(t => t[0] === tab) || TABS[1])[3]; return <Tab/> })()}
    </div>
  )
}

function NetworkTab() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)
  const [authKey, setAuthKey] = useState('')
  const [loginServer, setLoginServer] = useState('')
  const [hostname, setHostname] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  const load = () => {
    api.admin.tailscaleStatus().then(s => {
      setStatus(s)
      setEnabled(s.enabled)
      setLoginServer(s.login_server || '')
    }).catch(e => setError(e.message))
  }
  useEffect(() => { load() }, [])

  if (error) return <p className="text-sm" style={{ color: 'var(--pastel-red)' }}>{error}</p>
  if (!status) return <div className="skeleton h-24 rounded-xl"/>

  if (!status.binary_installed) {
    return (
      <p className="text-sm" style={{ color: 'var(--pastel-amber)' }}>
        The tailscale client isn't installed in this image yet — rebuild from the current Dockerfile.
      </p>
    )
  }

  const save = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      const result = await api.admin.tailscaleConfig({ enabled, auth_key: authKey, login_server: loginServer, hostname })
      setStatus(result)
      setAuthKey('')
    } catch (e) {
      setSaveError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card p-5 space-y-4" style={{ border: '1px solid var(--border-subtle)' }}>
      <div className="flex items-center gap-3">
        <span className="relative inline-flex w-2 h-2 flex-shrink-0">
          <span className="absolute inset-0 rounded-full" style={{ background: status.connected ? '#4ade80' : (status.enabled ? '#f59e0b' : '#6b7280') }}/>
          {status.connected && <span className="absolute inset-0 rounded-full animate-live" style={{ background: '#4ade80' }}/>}
        </span>
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          {status.connected ? `Connected — ${status.ip}` : status.enabled ? 'Enabled, not yet connected' : 'Not connected'}
        </p>
      </div>

      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        Reach this server from anywhere on your tailnet, not just its local network — one identity shared
        by every location this server hosts. If you're using the bundled self-hosted Headscale (the
        "headscale" service in docker-compose.yml), a reusable key is generated automatically — this
        panel picks it up within seconds of `docker compose up`, no key needed here. Paste one in below
        only if you'd rather point this at a real Tailscale.com account, or a different Headscale server.
      </p>

      <label className="flex items-center gap-2.5 cursor-pointer">
        <input type="checkbox" className="toggle" checked={enabled} onChange={e => setEnabled(e.target.checked)}/>
        <span className="text-sm" style={{ color: 'var(--text-primary)' }}>Enable Tailscale</span>
      </label>

      <div className="space-y-2">
        <label className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Auth key (optional — leave blank to use the bundled Headscale's own key)</label>
        <input type="password" className="input w-full"
               placeholder={status.enabled ? '•••••••••••••• (saved — leave blank to keep it)' : 'tskey-auth-...'}
               value={authKey} onChange={e => setAuthKey(e.target.value)}/>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <label className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Login server</label>
          <input className="input w-full" placeholder="http://localhost:9877 (bundled Headscale)"
                 value={loginServer} onChange={e => setLoginServer(e.target.value)}/>
        </div>
        <div className="space-y-2">
          <label className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Hostname (optional)</label>
          <input className="input w-full" placeholder="auto"
                 value={hostname} onChange={e => setHostname(e.target.value)}/>
        </div>
      </div>

      {saveError && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{saveError}</p>}

      <button onClick={save} disabled={saving} className="btn-primary text-sm px-4 py-2">
        {saving ? 'Connecting…' : 'Save & Connect'}
      </button>

      <HeadscaleNodesCard/>
      <HeadscaleBasicAuthCard/>
    </div>
  )
}

function HeadscaleNodesCard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = () => {
    setRefreshing(true)
    api.admin.headscaleNodes()
      .then(d => { setData(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setRefreshing(false))
  }
  useEffect(() => { load() }, [])

  // Not an error — just means this deployment isn't using the bundled
  // Headscale (a real Tailscale.com account, most likely), where this
  // node list has no meaning: that account's own admin console already
  // shows it. Nothing to show here either way, so render nothing rather
  // than an empty card.
  if (data && !data.available) return null

  return (
    <div className="pt-2 border-t space-y-3" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          Headscale network — who's connected
        </p>
        <button onClick={load} disabled={refreshing} title="Refresh">
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} style={{ color: 'var(--text-tertiary)' }}/>
        </button>
      </div>

      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        Every device the bundled Headscale server knows about — chirp-server-instances itself,
        chirp-server and chirp-device if pointed at this same Headscale, and anything else you've
        joined to this tailnet.
      </p>

      {error && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{error}</p>}
      {!data && !error && <div className="skeleton h-16 rounded-xl"/>}

      {data && data.error && (
        <p className="text-xs" style={{ color: 'var(--pastel-amber)' }}>
          Couldn't reach Headscale's own API: {data.error}
        </p>
      )}

      {data && data.available && !data.error && data.nodes.length === 0 && (
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          No devices have joined this tailnet yet.
        </p>
      )}

      {data && data.nodes.length > 0 && (
        <div className="space-y-2">
          {data.nodes.map(node => (
            <div key={node.id} className="flex items-center gap-3 p-2.5 rounded-lg"
                 style={{ background: 'var(--bg-subtle)' }}>
              <Laptop size={16} className="flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}/>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="relative inline-flex w-1.5 h-1.5 flex-shrink-0">
                    <span className="absolute inset-0 rounded-full" style={{ background: node.online ? '#4ade80' : '#6b7280' }}/>
                    {node.online && <span className="absolute inset-0 rounded-full animate-live" style={{ background: '#4ade80' }}/>}
                  </span>
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                    {node.name || node.hostname || `node ${node.id}`}
                  </p>
                </div>
                <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>
                  {node.ip_addresses?.join(', ') || 'no IP assigned'}
                  {!node.online && node.last_seen && ` · last seen ${new Date(node.last_seen).toLocaleString()}`}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function HeadscaleBasicAuthCard() {
  const [data, setData] = useState(null)
  const [enabled, setEnabled] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)

  const load = () => {
    api.admin.headscaleBasicAuth()
      .then(d => {
        setData(d)
        setEnabled(d.enabled)
        setUsername(d.username || '')
      })
      .catch(e => setError(e.message))
  }
  useEffect(() => { load() }, [])

  const save = () => {
    setSaving(true)
    setError(null)
    setSaved(false)
    api.admin.saveHeadscaleBasicAuth({ enabled, username, password: password || (data?.password_set ? '****' : '') })
      .then(d => {
        setData(d)
        setPassword('')
        setSaved(true)
        setTimeout(() => setSaved(false), 2500)
      })
      .catch(e => setError(e.message))
      .finally(() => setSaving(false))
  }

  // Same reasoning as HeadscaleNodesCard above — nothing meaningful to
  // show if this deployment isn't using the bundled Headscale at all.
  if (data === null && !error) return <div className="skeleton h-16 rounded-xl"/>

  return (
    <div className="pt-2 border-t space-y-3" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="flex items-center gap-2">
        <Shield size={16} style={{ color: 'var(--text-tertiary)' }}/>
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          Password-protect Headscale's setup pages
        </p>
      </div>

      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        Headscale's own /apple, /windows, and /linux pages show setup instructions with no login of
        their own — anyone who finds this subdomain can see them. This adds Basic Auth in front of
        just those pages, live, via Caddy — actual device registration keeps working either way,
        since those endpoints aren't touched.
      </p>

      {error && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{error}</p>}

      <label className="flex items-center gap-2.5 cursor-pointer">
        <input type="checkbox" className="toggle" checked={enabled} onChange={e => setEnabled(e.target.checked)}/>
        <span className="text-sm" style={{ color: 'var(--text-primary)' }}>Enabled</span>
      </label>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Username</label>
          <input className="input w-full mt-1" value={username} onChange={e => setUsername(e.target.value)}
                 placeholder="e.g. josh"/>
        </div>
        <div>
          <label className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            Password{data?.password_set ? ' (saved — leave blank to keep it)' : ''}
          </label>
          <input type="password" className="input w-full mt-1" value={password}
                 onChange={e => setPassword(e.target.value)}
                 placeholder={data?.password_set ? '••••••••••••' : ''}/>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button onClick={save} disabled={saving} className="btn-primary text-sm px-4 py-2">
          {saving ? 'Saving…' : 'Save'}
        </button>
        {saved && <span className="text-xs" style={{ color: '#4ade80' }}>Saved and applied live.</span>}
      </div>
    </div>
  )
}


// ── Requests from /about: hosted sites and push relay tokens ─────────────

const muted = { color: 'var(--text-tertiary)' }

