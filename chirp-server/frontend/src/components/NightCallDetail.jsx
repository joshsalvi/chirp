/**
 * One night flight call: large spectrogram, audio, what Nighthawk could tell.
 * Opened from the Night Flight Calls list (NightCalls.jsx). API: GET
 * /night-calls/{id}, /spectrogram?large=true, /audio (api/night_calls.py).
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Moon, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { fmtNight } from './NightCalls'

const LEVEL_COLOR = { species: 'var(--accent-400)', group: '#a3e635', family: '#7dd3fc', order: 'var(--text-tertiary)' }
const LEVEL_TEXT = {
  species: 'Nighthawk named the bird.',
  group: 'A sound-alike group: a few species whose flight calls Nighthawk can’t tell apart.',
  family: 'Nighthawk could tell the family but not the species.',
  order: 'Nighthawk could only tell the order (songbird, shorebird…).',
}

function Row({ label, children }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm" style={{ borderTop: '1px solid var(--border-subtle)' }}>
      <span style={{ color: 'var(--text-tertiary)' }}>{label}</span>
      <span className="text-right" style={{ color: 'var(--text-primary)' }}>{children}</span>
    </div>
  )
}

export default function NightCallDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [c, setC] = useState(null)
  const [err, setErr] = useState(null)
  const [isAdmin, setIsAdmin] = useState(false)
  const [imgFailed, setImgFailed] = useState(false)

  useEffect(() => {
    setC(null); setErr(null); setImgFailed(false)
    api.nightCalls.get(id).then(setC).catch(e => setErr(e?.message || 'Not found'))
    api.auth.me().then(r => (r?.json ? r.json() : r)).then(u => setIsAdmin(u?.role === 'admin')).catch(() => {})
  }, [id])

  const remove = () => api.nightCalls.remove(id).then(() => nav('/night-calls'))

  return (
    <div className="page-root space-y-4">
      <Link to="/night-calls" className="inline-flex items-center gap-1 text-sm" style={{ color: 'var(--text-secondary)' }}>
        <ArrowLeft size={16}/> Night Flight Calls
      </Link>
      {err && <div className="card p-4 text-sm" style={{ color: 'var(--text-secondary)' }}>This call couldn’t be loaded ({err}).</div>}
      {!c && !err && <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>Loading…</p>}
      {c && (
        <>
          <div className="flex items-start gap-2">
            <Moon size={22} className="mt-1 flex-shrink-0" style={{ color: 'var(--accent-400)' }}/>
            <div className="min-w-0 flex-1">
              <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>{c.name}</h1>
              {c.scientific_name && <p className="text-sm italic" style={{ color: 'var(--text-tertiary)' }}>{c.scientific_name}</p>}
            </div>
            {isAdmin && (
              <button onClick={remove} className="btn-secondary text-sm flex items-center gap-1" aria-label="Delete">
                <Trash2 size={14}/> Delete
              </button>
            )}
          </div>

          {c.has_clip ? (
            <div className="card p-3 space-y-3">
              {!imgFailed
                ? <img src={api.nightCalls.spectrogramUrl(c.id, true)} alt={`Spectrogram of the ${c.name} call`}
                       onError={() => setImgFailed(true)} className="w-full rounded" style={{ background: '#0b130e' }}/>
                : <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>The spectrogram couldn’t be drawn.</p>}
              <audio controls preload="none" src={api.nightCalls.audioUrl(c.id)} className="w-full"/>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                Flight calls are short (often under 0.2 s) and high (2–10 kHz): look for a thin mark in the upper half.
              </p>
            </div>
          ) : (
            <div className="card p-4 text-sm" style={{ color: 'var(--text-secondary)' }}>The audio for this call has been deleted.</div>
          )}

          <div className="card px-4 py-1">
            <Row label="Heard">{new Date(c.detected_at).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit' })}</Row>
            <Row label="Night of">{fmtNight(c.night)}</Row>
            {c.device_name && <Row label="Station">{c.device_name}</Row>}
            <Row label="How sure"><span style={{ color: LEVEL_COLOR[c.level] }}>{c.level_label}</span> · {Math.round(c.prob * 100)}%</Row>
            {c.level === 'group' && c.group_members?.length > 0 && <Row label="Could be">{c.group_members.join(', ')}</Row>}
            {c.family_name && <Row label="Family">{c.family_name}</Row>}
            {c.duration > 0 && <Row label="Call length">{c.duration.toFixed(2)} s</Row>}
          </div>
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{LEVEL_TEXT[c.level]}</p>
        </>
      )}
    </div>
  )
}
