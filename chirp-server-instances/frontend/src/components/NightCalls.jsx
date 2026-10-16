/**
 * Night Flight Calls (Settings → Experimental → Night flight calls):
 * calls Nighthawk found in the stations' night audio, one night at a time.
 * API: /night-calls (api/night_calls.py); names from nighthawk_service.describe.
 */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Moon, Play, Pause, Trash2, ChevronDown } from 'lucide-react'
import { api, mediaUrl } from '../lib/api'

const LEVELS = [
  ['species', 'Species', 'Nighthawk named the bird.'],
  ['group', 'Sound-alike group', 'A few species whose flight calls Nighthawk can’t tell apart; it lists the ones it could be.'],
  ['family', 'Family only', 'It could tell the family (warblers, sparrows, thrushes…) but not the species.'],
  ['order', 'Not narrowed down', 'Only that it’s a songbird, shorebird, heron or cuckoo. Hidden unless you ask for them.'],
]
const LEVEL_COLOR = { species: 'var(--accent-400)', group: '#a3e635', family: '#7dd3fc', order: 'var(--text-tertiary)' }

function fmtNight(night) {
  const d = new Date(`${night}T12:00:00`)
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' })
}

function CallRow({ c, playing, failed, onPlay, onDelete }) {
  const detail = c.level === 'group' && c.group_members?.length
    ? `Could be: ${c.group_members.join(', ')}`
    : c.level === 'species' && c.family_name ? c.family_name
      : null
  return (
    <div className="flex items-start gap-3 py-2.5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
      <button onClick={() => onPlay(c)} disabled={!c.has_clip} aria-label={playing ? 'Pause' : 'Play'}
              className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)', opacity: c.has_clip ? 1 : 0.4 }}>
        {playing ? <Pause size={15}/> : <Play size={15}/>}
      </button>
      {c.has_clip && (
        <img src={mediaUrl(`/api/v1/night-calls/${c.id}/spectrogram`)} alt="" loading="lazy"
             className="h-9 w-16 sm:w-24 rounded object-cover flex-shrink-0"/>
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{c.name}</p>
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          {fmtTime(c.detected_at)} · <span style={{ color: LEVEL_COLOR[c.level] }}>{c.level_label}</span> · {Math.round(c.prob * 100)}%
        </p>
        {detail && <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>{detail}</p>}
        {failed && <p className="text-xs mt-0.5" style={{ color: '#f87171' }}>Couldn’t play this clip.</p>}
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
  const [data, setData] = useState(null)          // { calls, total, unnarrowed }
  const [showAll, setShowAll] = useState(false)
  const [status, setStatus] = useState(null)
  const [playing, setPlaying] = useState(null)
  const [failed, setFailed] = useState(null)
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
    setData(null)
    api.nightCalls.list(night, showAll).then(setData).catch(() => setData({ calls: [], total: 0, unnarrowed: 0 }))
  }, [night, showAll])

  useEffect(() => () => audioRef.current?.pause(), [])

  // One audio element, reused: iOS only lets a page play sound it started from a tap.
  const play = c => {
    let a = audioRef.current
    if (!a) {
      a = new Audio()
      a.onended = () => setPlaying(null)
      audioRef.current = a
    }
    if (playing === c.id) { a.pause(); setPlaying(null); return }
    a.pause()
    setFailed(null)
    a.src = mediaUrl(`/api/v1/night-calls/${c.id}/audio`)
    a.play().then(() => setPlaying(c.id)).catch(() => { setPlaying(null); setFailed(c.id) })
  }

  const remove = c => api.nightCalls.remove(c.id)
    .then(() => setData(d => ({ ...d, calls: d.calls.filter(x => x.id !== c.id) })))

  const nh = status?.nighthawk
  const summary = nights?.find(n => n.night === night)
  const counts = summary?.by_level || {}

  return (
    <div className="page-root space-y-4">
      <div className="flex items-center gap-2">
        <Moon size={22} style={{ color: 'var(--accent-400)' }}/>
        <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Night Flight Calls</h1>
      </div>
      <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
        Short calls that migrating birds give as they fly over at night, found by Nighthawk in your stations’ night audio.
      </p>

      <details className="card p-4 text-sm">
        <summary className="cursor-pointer flex items-center gap-1 font-medium" style={{ color: 'var(--text-primary)' }}>
          How sure is each call? <ChevronDown size={14}/>
        </summary>
        <div className="mt-3 space-y-2">
          {LEVELS.map(([k, label, text]) => (
            <p key={k} className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              <span className="font-medium" style={{ color: LEVEL_COLOR[k] }}>{label}</span>: {text}
            </p>
          ))}
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            The percentage is Nighthawk’s confidence in that level. Many flight calls can only be told apart this far,
            even by experts.
          </p>
        </div>
      </details>

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
            <button key={n.night} onClick={() => { setNight(n.night); setShowAll(false) }}
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
        <div className="card p-4 space-y-3">
          <p className="text-xs uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
            Night of {fmtNight(summary.night)} · {summary.calls.toLocaleString()} call{summary.calls === 1 ? '' : 's'}
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
            {LEVELS.map(([k, label]) => counts[k] ? (
              <span key={k}><span style={{ color: LEVEL_COLOR[k] }}>{counts[k].toLocaleString()}</span>{' '}
                <span style={{ color: 'var(--text-secondary)' }}>{label.toLowerCase()}</span></span>
            ) : null)}
          </div>
          {summary.top.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {summary.top.map(t => (
                <span key={t.name} className="text-xs px-2 py-1 rounded-full"
                      style={{ background: 'var(--bg-raised)', color: 'var(--text-primary)' }}>
                  {t.name} <span style={{ color: 'var(--text-tertiary)' }}>×{t.count}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {data && data.calls.length > 0 && (
        <div className="card px-4 py-1">
          {data.calls.map(c => (
            <CallRow key={c.id} c={c} playing={playing === c.id} failed={failed === c.id} onPlay={play}
                     onDelete={canDelete ? remove : null}/>
          ))}
        </div>
      )}
      {data && data.total > data.calls.length && (
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          Showing the latest {data.calls.length} of {data.total.toLocaleString()}.
        </p>
      )}
      {data && data.unnarrowed > 0 && !showAll && (
        <button className="btn-secondary text-sm" onClick={() => setShowAll(true)}>
          Show {data.unnarrowed.toLocaleString()} call{data.unnarrowed === 1 ? '' : 's'} not narrowed down
        </button>
      )}
      {data && data.calls.length === 0 && data.unnarrowed > 0 && !showAll && (
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          Every call this night was only placed as a songbird or similar.
        </p>
      )}
      {night && !data && <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>Loading…</p>}
    </div>
  )
}
