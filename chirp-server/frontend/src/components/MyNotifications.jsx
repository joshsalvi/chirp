/**
 * Settings → My Notifications: each person's own choices, visible to every
 * signed-in user (the rest of Settings is admin-only). Push types, email
 * types, this device's push status, and watched birds.
 */
import { useEffect, useMemo, useState } from 'react'
import { Bell, Bird, Mail, Plus, Smartphone, Trash2, Check, AlertCircle, Radio } from 'lucide-react'
import { api } from '../lib/api'
import { native, isApp } from '../native'
import { PushNotificationSection } from './UserProfile'

// "Every day at 9 PM, covering that day" — the site's digest hour (local).
function digestWhen(h) {
  if (h == null) return 'Once a day'
  const t = `${h % 12 === 0 ? 12 : h % 12} ${h < 12 ? 'AM' : 'PM'}`
  return `Every day at ${t}, covering ${h >= 12 ? 'that day' : 'the day before'}`
}

const PUSH = [
  ['new_bird_push', 'New species', 'The first time a species is detected at your site. Opens the recording.'],
  ['daily_journal_push', 'Daily Journal', 'Every evening at 6 pm, with the day\'s journal entry.'],
  ['weekly_journal_push', 'Weekly Journal', 'Sundays at noon, with the week\'s journal entry.'],
  ['daily_digest_push', 'Daily digest', h => `${digestWhen(h)}: counts, new birds and every species, opening the full digest.`, 'digest_push_hour'],
]
const EMAIL = [
  ['new_bird_email', 'New species', 'An email for each new species.'],
  ['daily_digest_email', 'Daily digest', h => `A summary email ${digestWhen(h).toLowerCase()}.`, 'digest_email_hour'],
]

function Switch({ checked, onChange, label, sub, disabled }) {
  return (
    <label className="flex items-start gap-3 py-2.5 cursor-pointer" style={{ opacity: disabled ? 0.5 : 1 }}>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{label}</span>
        {sub && <span className="block text-xs mt-0.5" style={{ color: 'var(--text-tertiary)', lineHeight: 1.45 }}>{sub}</span>}
      </span>
      <input type="checkbox" className="w-5 h-5 mt-0.5 accent-chirp-500 flex-shrink-0" checked={!!checked}
             disabled={disabled} onChange={e => onChange(e.target.checked)}/>
    </label>
  )
}

function Card({ icon: Icon, title, children }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-1">
        <Icon size={15} style={{ color: 'var(--accent-400)' }}/>
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</h3>
      </div>
      {children}
    </div>
  )
}

function ThisDevice() {
  const [state, setState] = useState(null)
  const [msg, setMsg] = useState(null)
  useEffect(() => { native.push.status().then(setState) }, [])
  const allow = async () => {
    const r = await native.push.enable({ onToken: t => api.push.registerNative(t).catch(() => {}) })
    setState(r === 'granted' ? 'granted' : r)
  }
  const test = async () => {
    setMsg('Sending…')
    try { const r = await api.push.testNative(); setMsg(`Sent to ${r.sent} iPhone${r.sent === 1 ? '' : 's'}.`) }
    catch (e) { setMsg(e.message || 'Send failed') }
    window.dispatchEvent(new Event('chirp-notification'))
  }
  return (
    <Card icon={Smartphone} title="This iPhone">
      <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
        {state === 'granted' ? 'Push alerts are on for this iPhone.'
          : state === 'denied' ? 'Push alerts are off. Turn them on in the iPhone Settings app → Chirp → Notifications.'
          : 'Allow push alerts so the choices above reach this phone.'}
      </p>
      <div className="flex gap-2 flex-wrap">
        {state !== 'granted' && state !== 'denied' && <button className="btn-primary text-sm" onClick={allow}>Allow notifications</button>}
        {state === 'granted' && <button className="btn-secondary text-sm" onClick={test}>Send a test</button>}
      </div>
      {msg && <p className="text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>{msg}</p>}
    </Card>
  )
}

function Watches({ watches, onChange }) {
  const [species, setSpecies] = useState([])
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('every')
  const [error, setError] = useState(null)
  useEffect(() => {
    api.birds.lifeList().then(r => {
      const list = (Array.isArray(r) ? r : r?.items || []).filter(b => !b.is_bat).map(b => b.common_name)
      setSpecies([...new Set(list)].sort())
    }).catch(() => {})
  }, [])
  const watched = new Set(watches.map(w => w.common_name.toLowerCase()))
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    return species.filter(n => n.toLowerCase().includes(q) && !watched.has(n.toLowerCase())).slice(0, 6)
  }, [query, species, watches])   // eslint-disable-line react-hooks/exhaustive-deps

  const add = async (name) => {
    setError(null)
    try { await api.notifications.addWatch(name, mode); setQuery(''); onChange() }
    catch (e) { setError(e.message) }
  }
  const setWatchMode = async (w, m) => { await api.notifications.updateWatch(w.id, m).catch(() => {}); onChange() }
  const remove = async (w) => { await api.notifications.deleteWatch(w.id).catch(() => {}); onChange() }

  return (
    <Card icon={Bird} title="Watched birds">
      <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
        Get a push when a species you care about is heard: <b>every time</b> (opens the recording; at most one per bird every 10 minutes)
        or <b>once a day</b> in a 7 pm summary. You can also tap the bell on any species page.
      </p>
      {watches.length > 0 && (
        <ul className="mb-3 divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
          {watches.map(w => (
            <li key={w.id} className="flex items-center gap-2 py-2">
              <span className="text-sm flex-1 min-w-0 truncate" style={{ color: 'var(--text-primary)' }}>{w.common_name}</span>
              <select className="input text-xs" style={{ width: 'auto', padding: '4px 8px' }} value={w.mode}
                      onChange={e => setWatchMode(w, e.target.value)} aria-label={`When to notify for ${w.common_name}`}>
                <option value="every">Every time</option>
                <option value="daily">Daily summary</option>
              </select>
              <button className="p-1.5" aria-label={`Stop watching ${w.common_name}`} onClick={() => remove(w)}
                      style={{ color: 'var(--text-tertiary)' }}><Trash2 size={14}/></button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <input className="input text-sm flex-1" placeholder="Add a species…" value={query}
               onChange={e => setQuery(e.target.value)} autoCapitalize="none" autoCorrect="off"/>
        <select className="input text-xs" style={{ width: 'auto' }} value={mode} onChange={e => setMode(e.target.value)} aria-label="When to notify">
          <option value="every">Every time</option>
          <option value="daily">Daily</option>
        </select>
      </div>
      {matches.length > 0 && (
        <div className="mt-2 rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-subtle)' }}>
          {matches.map(n => (
            <button key={n} className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-raised"
                    style={{ color: 'var(--text-primary)' }} onClick={() => add(n)}>
              <Plus size={13} style={{ color: 'var(--accent-400)' }}/> {n}
            </button>
          ))}
        </div>
      )}
      {query.trim() && matches.length === 0 && !species.some(n => n.toLowerCase() === query.trim().toLowerCase()) && (
        <button className="mt-2 text-xs underline" style={{ color: 'var(--text-secondary)' }} onClick={() => add(query.trim())}>
          Watch "{query.trim()}" anyway (not heard here yet)
        </button>
      )}
      {error && <p className="text-xs mt-2 flex items-center gap-1" style={{ color: '#f87171' }}><AlertCircle size={12}/> {error}</p>}
    </Card>
  )
}

export default function MyNotifications() {
  const [prefs, setPrefs] = useState(null)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)
  const load = () => api.notifications.prefs().then(setPrefs).catch(e => setError(e.message))
  useEffect(() => { load() }, [])

  const toggle = async (key, value) => {
    setPrefs(p => ({ ...p, [key]: value }))
    try {
      setPrefs(await api.notifications.putPrefs({ [key]: value }))
      setSaved(true); setTimeout(() => setSaved(false), 1500)
    } catch (e) { setError(e.message); load() }
  }

  if (!prefs) return error ? <p className="text-sm" style={{ color: '#f87171' }}>{error}</p> : <div className="card h-40 animate-pulse"/>

  return (
    <div className="space-y-4">
      <Card icon={Bell} title="Push alerts">
        {PUSH.map(([k, label, sub, hourKey]) => <Switch key={k} label={label} sub={hourKey ? sub(prefs[hourKey]) : sub} checked={prefs[k]} onChange={v => toggle(k, v)}/>)}
        <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>
          Every alert is also kept in the Notifications tab. Times follow the site's time zone.
        </p>
      </Card>
      <Watches watches={prefs.watches || []} onChange={load}/>
      <Card icon={Mail} title="Email">
        {EMAIL.map(([k, label, sub, hourKey]) => <Switch key={k} label={label} sub={hourKey ? sub(prefs[hourKey]) : sub} checked={prefs[k]} onChange={v => toggle(k, v)}/>)}
        <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>Sent to the email address on your profile.</p>
      </Card>
      {prefs.is_admin && (
        <Card icon={Radio} title="Stations">
          <p className="text-xs mb-1" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            When a station stops reporting for 10 minutes (crashed, lost power or Wi-Fi), and again when it's back.
          </p>
          <Switch label="Station offline: push" checked={prefs.device_offline_push} onChange={v => toggle('device_offline_push', v)}/>
          <Switch label="Station offline: email" checked={prefs.device_offline_email} onChange={v => toggle('device_offline_email', v)}/>
        </Card>
      )}
      {isApp() ? <ThisDevice/> : <PushNotificationSection/>}
      {saved && <p className="text-xs flex items-center gap-1" style={{ color: 'var(--accent-400)' }}><Check size={12}/> Saved</p>}
    </div>
  )
}
