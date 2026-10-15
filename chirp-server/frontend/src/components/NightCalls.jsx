/**
 * Night Flight Calls (Settings → Experimental → Night flight calls):
 * calls Nighthawk found in the stations' night audio, one night at a time.
 * API: /night-calls (api/night_calls.py).
 */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Moon, Play, Pause, Trash2 } from 'lucide-react'
import { api } from '../lib/api'

// Media paths are open on this server (see main.py _is_media_path).
const mediaUrl = path => path

const LEVEL_LABEL = { species: 'Species', group: 'Sound group', family: 'Family', order: 'Order' }

function fmtNight(night) {
  const d = new Date(`${night}T12:00:00`)
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' })
}

function CallRow({ c, playing, onPlay, onDelete }) {
  return (
    <div className="flex items-center gap-3 py-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
      <button onClick={() => onPlay(c)} disabled={!c.has_clip} aria-label={playing ? 'Pause' : 'Play'}
              className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)', opacity: c.has_clip ? 1 : 0.4 }}>
        {playing ? <Pause size={15}/> : <Play size={15}/>}
      </button>
      {c.has_clip && (
        <img src={mediaUrl(`/api/v1/night-calls/${c.id}/spectrogram`)} alt="" loading="lazy"
             className="h-10 w-24 rounded object-cover flex-shrink-0 hidden sm:block"/>
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{c.name}</p>
        <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>
          {fmtTime(c.detected_at)} · {LEVEL_LABEL[c.level] || c.level} · {Math.round(c.prob * 100)}%
          {c.level === 'group' && c.group_members?.length ? ` · e.g. ${c.group_members.slice(0, 3).join(', ')}` : ''}
          {c.level !== 'species' && c.family ? ` · ${c.family}` : ''}
        </p>
      </div>
      {onDelete && (
        <button onClick={() => onDelete(c)} aria-label="Delete" className="p-1.5 flex-shrink-0"
                style={{ color: 'var(--text-tertiary)' }}>
          <Trash2 size={14}/>
        </button>
      )}
    </div>
  )
}

export default function NightCalls() {
  const [nights, setNights] = useState(null)
  const [night, setNight] = useState(null)
  const [calls, setCalls] = useState(null)
  const [status, setStatus] = useState(null)
  const [playing, setPlaying] = useState(null)
  const [canDelete, setCanDelete] = useState(false)
  const audioRef = useRef(null)

  useEffect(() => {
    api.nightCalls.nights().then(d => {
      setNights(d.nights || [])
      if (d.nights?.length) setNight(d.nights[0].night)
    }).catch(() => setNights([]))
    api.nightCalls.status().then(setStatus).catch(() => {})
    api.auth.me().then(r => (r?.json ? r.json() : r)).then(u => setCanDelete(u?.role === 'admin')).catch(() => {})
  }, [])

  useEffect(() => {
    if (!night) return
    setCalls(null)
    api.nightCalls.list(night).then(d => setCalls(d.calls || [])).catch(() => setCalls([]))
  }, [night])

  useEffect(() => () => audioRef.current?.pause(), [])

  const play = c => {
    if (playing === c.id) { audioRef.current?.pause(); setPlaying(null); return }
    audioRef.current?.pause()
    const a = new Audio(mediaUrl(`/api/v1/night-calls/${c.id}/audio`))
    a.onended = () => setPlaying(null)
    a.play().then(() => setPlaying(c.id)).catch(() => setPlaying(null))
    audioRef.current = a
  }

  const remove = c => api.nightCalls.remove(c.id).then(() => setCalls(cs => cs.filter(x => x.id !== c.id)))

  const nh = status?.nighthawk
  const summary = nights?.find(n => n.night === night)

  return (
    <div className="page-root space-y-4">
      <div className="flex items-center gap-2">
        <Moon size={22} style={{ color: 'var(--accent-400)' }}/>
        <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Night Flight Calls</h1>
      </div>
      <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
        Short calls migrating birds give overhead at night, found by Nighthawk in your stations' night audio.
        It names a species when it's confident; otherwise a family, or a group of species whose calls sound alike.
      </p>

      {nh && !nh.enabled && (
        <div className="card p-4 text-sm" style={{ color: 'var(--text-secondary)' }}>
          Night flight calls are off. An admin can turn them on in{' '}
          <Link to="/settings?tab=experimental" className="underline" style={{ color: 'var(--accent-400)' }}>
            Settings → Experimental
          </Link>.
        </div>
      )}
      {nh?.enabled && nh.pending > 0 && (
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          {nh.pending} stretch{nh.pending === 1 ? '' : 'es'} of night audio waiting to be analyzed.
        </p>
      )}

      {nights && nights.length === 0 && nh?.enabled && (
        <div className="card p-4 text-sm" style={{ color: 'var(--text-secondary)' }}>
          No calls yet. Stations upload audio between the hours set in Settings, and calls appear here after each
          10-minute stretch is analyzed. Stations need software 1.4.0 or later.
        </div>
      )}

      {nights && nights.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
          {nights.map(n => (
            <button key={n.night} onClick={() => setNight(n.night)}
                    className="px-3 py-1.5 rounded-lg text-sm whitespace-nowrap flex-shrink-0"
                    style={n.night === night
                      ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)' }
                      : { background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
              {fmtNight(n.night)} <span className="opacity-70">· {n.calls}</span>
            </button>
          ))}
        </div>
      )}

      {summary && (
        <div className="card p-4">
          <p className="text-xs uppercase tracking-wider mb-2" style={{ color: 'var(--text-tertiary)' }}>
            Night of {fmtNight(summary.night)} · {summary.calls} call{summary.calls === 1 ? '' : 's'}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {summary.top.map(t => (
              <span key={t.name} className="text-xs px-2 py-1 rounded-full"
                    style={{ background: 'var(--bg-raised)', color: 'var(--text-primary)' }}>
                {t.name} <span style={{ color: 'var(--text-tertiary)' }}>×{t.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {calls && calls.length > 0 && (
        <div className="card px-4 py-1">
          {calls.map(c => (
            <CallRow key={c.id} c={c} playing={playing === c.id} onPlay={play}
                     onDelete={canDelete ? remove : null}/>
          ))}
        </div>
      )}
      {night && !calls && <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>Loading…</p>}
    </div>
  )
}
