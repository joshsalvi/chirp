import { useEffect, useState } from 'react'
import { Users, Plus, Trash2, Check, ChevronDown } from 'lucide-react'
import { api, tokenStore } from '../lib/api'

const ROLE_COLORS = {
  admin:     { bg: 'rgba(167,139,250,.15)', color: '#c4b5fd', border: 'rgba(167,139,250,.3)' },
  submitter: { bg: 'rgba(251,146,60,.12)',  color: '#fdba74', border: 'rgba(251,146,60,.28)' },
  viewer:    { bg: 'rgba(34,197,94,.1)',    color: 'var(--pastel-green)', border: 'rgba(34,197,94,.2)' },
}

function RoleDropdown({ userId, currentRole, onChanged, disabled }) {
  const [open, setOpen]   = useState(false)
  const [saving, setSaving] = useState(false)
  const c = ROLE_COLORS[currentRole] || ROLE_COLORS.viewer

  const change = async (role) => {
    if (role === currentRole) { setOpen(false); return }
    setSaving(true)
    try {
      await api.auth.users.changeRole(userId, role)
      onChanged(role)
    } catch (e) {
      alert(e.message || 'Failed to change role')
    } finally {
      setSaving(false)
      setOpen(false)
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => !disabled && setOpen(o => !o)}
        disabled={disabled || saving}
        className="flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold transition-all"
        style={{ background: c.bg, color: c.color, border: `1px solid ${c.border}` }}>
        {saving ? '…' : currentRole}
        {!disabled && <ChevronDown size={10}/>}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)}/>
          <div className="absolute right-0 top-full mt-1 z-50 rounded-xl overflow-hidden shadow-xl"
               style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', minWidth: 130 }}>
            {['admin','submitter','viewer'].map(role => {
              const rc = ROLE_COLORS[role]
              return (
                <button key={role} onClick={() => change(role)}
                        className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm hover:bg-raised transition-colors">
                  <span className="w-2 h-2 rounded-full" style={{ background: rc.color }}/>
                  <span className="capitalize" style={{ color: 'var(--text-primary)' }}>{role}</span>
                  {role === currentRole && <Check size={12} className="ml-auto" style={{ color: rc.color }}/>}
                </button>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

// The site's invite code: people create an account with it and join as
// viewers. Shown to this site's admins (the server only returns it to them).
function InviteCodeCard() {
  const [site, setSite] = useState(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    const active = tokenStore.getActiveInstanceId()
    api.instances.list().then(list => setSite(list.find(i => i.id === active && i.invite_code) || null)).catch(() => {})
  }, [])
  if (!site) return null
  const text = `Join ${site.name} on Chirp: create an account at ${window.location.origin} with invite code ${site.invite_code}`
  return (
    <div className="card p-4 mb-4 flex flex-wrap items-center gap-3" style={{ border: '1px solid var(--border-subtle)' }}>
      <div className="flex-1 min-w-[12rem]">
        <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Invite people</p>
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          Share this code. People create an account with it and join {site.name} as viewers; change their role below.
        </p>
      </div>
      <span className="font-mono text-lg font-bold tracking-wider" style={{ color: 'var(--accent-400)' }}>{site.invite_code}</span>
      <button className="btn-secondary text-xs px-3 py-1.5"
              onClick={() => navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })}>
        {copied ? 'Copied' : 'Copy invite'}
      </button>
    </div>
  )
}

export default function UserManagement() {
  const [users,     setUsers]     = useState([])
  const [loading,   setLoading]   = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newUser,   setNewUser]   = useState({ username: '', email: '', password: '', role: 'viewer' })
  const [creating,  setCreating]  = useState(false)
  const [error,     setError]     = useState(null)
  const [loadError, setLoadError] = useState(null)

  const load = () => {
    setLoading(true)
    setLoadError(null)
    api.auth.users.list()
      .then(setUsers)
      // Bug: this used to swallow every failure silently, so a 400
      // ("no active instance selected"), a 403, or any other real
      // error just left the list empty with zero indication anything
      // had gone wrong — indistinguishable from "there are no users."
      // Now surfaced in the UI instead.
      .catch(e => setLoadError(e.message || 'Failed to load users'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    if (!newUser.username || !newUser.password) { setError('Username and password required'); return }
    setCreating(true); setError(null)
    try {
      await api.auth.users.create(newUser)
      load()
      setShowCreate(false)
      setNewUser({ username: '', email: '', password: '', role: 'viewer' })
    } catch (e) { setError(e.message || 'Failed to create user') }
    setCreating(false)
  }

  const handleDelete = async (user) => {
    if (!window.confirm(`Delete "${user.username}"? This cannot be undone.`)) return
    try { await api.auth.users.delete(user.id); load() } catch (e) { alert(e.message) }
  }

  const handleSetActive = async (user) => {
    try {
      // Pending users need /approve which clears pending_approval + sets active=true.
      // Toggling active alone leaves pending_approval=true so the badge never clears.
      if (user.pending_approval) {
        await api.auth.users.approve(user.id)
      } else {
        await api.auth.users.setActive(user.id, !user.active)
      }
      load()
    } catch (e) { alert(e.message) }
  }

  const handleRoleChange = (userId, newRole) => {
    setUsers(prev => prev.map(u => u.id === userId ? { ...u, role: newRole } : u))
  }

  return (
    <div className="page-root max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <Users size={18} style={{ color: 'var(--accent-400)' }}/>
          <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Users</h1>
        </div>
        <button onClick={() => setShowCreate(s => !s)} className="btn-primary flex items-center gap-1.5 text-sm">
          <Plus size={13}/> New User
        </button>
      </div>

      <InviteCodeCard/>

      {/* Create form */}
      {showCreate && (
        <div className="card p-5 mb-4 space-y-3" style={{ border: '1px solid var(--accent-500)40' }}>
          <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Create User</p>
          {error && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{error}</p>}
          <div className="grid grid-cols-2 gap-3">
            <input className="input text-sm" placeholder="Username *" value={newUser.username}
                   onChange={e => setNewUser(u => ({ ...u, username: e.target.value }))}/>
            <input className="input text-sm" placeholder="Email (optional)" value={newUser.email}
                   onChange={e => setNewUser(u => ({ ...u, email: e.target.value }))}/>
            <input className="input text-sm" type="password" placeholder="Password *" value={newUser.password}
                   onChange={e => setNewUser(u => ({ ...u, password: e.target.value }))}/>
            <select className="input text-sm" value={newUser.role}
                    onChange={e => setNewUser(u => ({ ...u, role: e.target.value }))}>
              <option value="viewer">Viewer</option>
              <option value="submitter">Submitter</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div className="flex gap-2">
            <button onClick={handleCreate} disabled={creating} className="btn-primary flex items-center gap-1.5 text-sm">
              <Check size={12}/> {creating ? 'Creating…' : 'Create'}
            </button>
            <button onClick={() => setShowCreate(false)} className="btn-ghost text-sm">Cancel</button>
          </div>
        </div>
      )}

      {/* User list */}
      {loadError && (
        <div className="card p-4 mb-4 text-sm" style={{ border: '1px solid var(--pastel-red)40', color: 'var(--pastel-red)' }}>
          {loadError}
        </div>
      )}
      {loading ? (
        <div className="space-y-2">
          {[0,1,2].map(i => <div key={i} className="skeleton h-16 rounded-xl"/>)}
        </div>
      ) : loadError ? null : (
        <div className="space-y-2">
          {users.map(user => {
            const isAdmin = user.role === 'admin'
            return (
              <div key={user.id} className="card px-4 py-3 flex items-center gap-3"
                   style={{ border: '1px solid var(--border-subtle)', opacity: user.active ? 1 : 0.6 }}>
                {/* Avatar */}
                <div className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0"
                     style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }}>
                  {user.username[0].toUpperCase()}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                      {user.username}
                    </span>
                    {user.pending_approval && (
                      <span className="text-xs px-2 py-0.5 rounded-full"
                            style={{ background: 'rgba(251,146,60,.15)', color: '#fdba74', border: '1px solid rgba(251,146,60,.3)' }}>
                        Pending
                      </span>
                    )}
                    {!user.active && (
                      <span className="text-xs px-2 py-0.5 rounded-full"
                            style={{ background: 'rgba(100,116,139,.15)', color: '#94a3b8' }}>
                        Inactive
                      </span>
                    )}
                  </div>
                  {user.email && (
                    <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>{user.email}</p>
                  )}
                </div>

                {/* Role dropdown */}
                <RoleDropdown
                  userId={user.id}
                  currentRole={user.role}
                  onChanged={(role) => handleRoleChange(user.id, role)}
                  disabled={false}
                />

                {/* Actions */}
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button onClick={() => handleSetActive(user)}
                          className="p-1.5 rounded-lg transition-colors hover:bg-raised text-xs"
                          style={{ color: user.pending_approval ? '#4ade80' : user.active ? 'var(--text-tertiary)' : 'var(--accent-400)' }}
                          title={user.pending_approval ? 'Approve account' : user.active ? 'Deactivate' : 'Activate'}>
                    <Check size={13}/>
                  </button>
                  <button onClick={() => handleDelete(user)}
                          className="p-1.5 rounded-lg transition-colors hover:bg-raised"
                          style={{ color: 'var(--text-tertiary)' }} title="Delete">
                    <Trash2 size={13}/>
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Role legend */}
      <div className="mt-5 p-4 rounded-xl space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
        <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>Roles</p>
        {[
          { role: 'admin',     desc: 'Full access: settings, users, devices, backup/restore, iNat submit' },
          { role: 'submitter', desc: 'View everything + submit to iNaturalist + upload recordings' },
          { role: 'viewer',    desc: 'View all data, add notes, change theme and profile settings' },
        ].map(({ role, desc }) => {
          const c = ROLE_COLORS[role]
          return (
            <div key={role} className="flex items-start gap-2">
              <span className="px-2 py-0.5 rounded-full text-xs font-semibold flex-shrink-0 mt-0.5"
                    style={{ background: c.bg, color: c.color, border: `1px solid ${c.border}` }}>
                {role}
              </span>
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{desc}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
