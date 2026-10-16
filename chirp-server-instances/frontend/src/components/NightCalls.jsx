/**
 * Night Flight Calls (Settings → Experimental → Night flight calls):
 * calls Nighthawk found in the stations' night audio, by night, week or
 * month, collapsed into family groups. Each call has its own page
 * (NightCallDetail.jsx).
 * API: /night-calls (api/night_calls.py); names from nighthawk_service.describe.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Moon, Play, Pause, Trash2, ChevronDown, ChevronRight } from 'lucide-react'
import { api, mediaUrl } from '../lib/api'

const LEVELS = [
  ['species', 'Species', 'Nighthawk named the bird.'],
  ['group', 'Sound-alike group', 'A few species whose flight calls Nighthawk can’t tell apart; it lists the ones it could be.'],
  ['family', 'Family only', 'It could tell the family (warblers, sparrows, thrushes…) but not the species.'],
  ['order', 'Not narrowed down', 'Only that it’s a songbird, shorebird, heron or cuckoo. Hidden unless you ask for them.'],
]
const LEVEL_COLOR = { species: 'var(--accent-400)', group: '#a3e635', family: '#7dd3fc', order: 'var(--text-tertiary)' }

export const LEVEL_RANK = { species: 0, group: 1, family: 2, order: 3 }

export function fmtNight(night) {
  const d = new Date(`${night}T12:00:00`)
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

// Night (YYYY-MM-DD, the evening's date) → the bucket it falls in.
function bucketOf(night, period) {
  if (period === 'night') return { key: night, start: night, end: night, label: fmtNight(night) }
  const d = new Date(`${night}T12:00:00`)
  if (period === 'month') {
    const start = new Date(d.getFullYear(), d.getMonth(), 1), end = new Date(d.getFullYear(), d.getMonth() + 1, 0)
    return { key: iso(start), start: iso(start), end: iso(end),
             label: d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }) }
  }
  const start = new Date(d); start.setDate(d.getDate() - ((d.getDay() + 6) % 7))   // Monday
  const end = new Date(start); end.setDate(start.getDate() + 6)
  return { key: iso(start), start: iso(start), end: iso(end),
           label: `Week of ${start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}` }
}

function buckets(nights, period) {
  const by = new Map()
  for (const n of nights) {
    const b = bucketOf(n.night, period)
    const cur = by.get(b.key) || { ...b, calls: 0, nights: 0, by_level: {} }
    cur.calls += n.calls; cur.nights += 1
    for (const [k, v] of Object.entries(n.by_level || {})) cur.by_level[k] = (cur.by_level[k] || 0) + v
    by.set(b.key, cur)
  }
  return [...by.values()].sort((a, b) => (a.key < b.key ? 1 : -1))
}

// Calls → family groups (all warblers together); calls without a family
// (songbird, shorebird…) group by name. Biggest first.
function groupCalls(calls) {
  const by = new Map()
  for (const c of calls) {
    const key = c.family_name || c.name
    const g = by.get(key) || { key, calls: [], names: new Map(), best: 'order', top: 0 }
    g.calls.push(c)
    g.names.set(c.name, (g.names.get(c.name) || 0) + 1)
    if (LEVEL_RANK[c.level] < LEVEL_RANK[g.best]) g.best = c.level
    g.top = Math.max(g.top, c.prob)
    by.set(key, g)
  }
  return [...by.values()].sort((a, b) => b.calls.length - a.calls.length || a.key.localeCompare(b.key))
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' })
}

function CallRow({ c, playing, failed, onPlay, onDelete, showDate }) {
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
        <Link to={`/night-calls/${c.id}`} className="flex-shrink-0" title="Open this call">
          <img src={mediaUrl(`/api/v1/night-calls/${c.id}/spectrogram`)} alt="Spectrogram" loading="lazy"
               className="h-9 w-16 sm:w-24 rounded object-cover"/>
        </Link>
      )}
      <div className="min-w-0 flex-1">
        <Link to={`/night-calls/${c.id}`} className="text-sm font-medium hover:underline" style={{ color: 'var(--text-primary)' }}>{c.name}</Link>
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          {showDate ? `${fmtNight(c.night)}, ` : ''}{fmtTime(c.detected_at)} · <span style={{ color: LEVEL_COLOR[c.level] }}>{c.level_label}</span> · {Math.round(c.prob * 100)}%
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

function CallGroup({ g, open, onToggle, rowProps }) {
  const names = [...g.names.entries()].sort((a, b) => b[1] - a[1])
  return (
    <div style={{ borderTop: '1px solid var(--border-subtle)' }}>
      <button onClick={onToggle} aria-expanded={open} className="w-full flex items-center gap-3 py-3 text-left">
        {open ? <ChevronDown size={16} style={{ color: 'var(--text-tertiary)' }}/> : <ChevronRight size={16} style={{ color: 'var(--text-tertiary)' }}/>}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            {g.key} <span className="font-normal" style={{ color: 'var(--text-tertiary)' }}>· {g.calls.length.toLocaleString()} call{g.calls.length === 1 ? '' : 's'}</span>
          </p>
          <p className="text-xs truncate" style={{ color: 'var(--text-secondary)' }}>
            {names.slice(0, 4).map(([n, k]) => (names.length > 1 || n !== g.key) ? `${n} ×${k}` : null).filter(Boolean).join(' · ')}
            {names.length > 4 ? ` · +${names.length - 4} more` : ''}
          </p>
        </div>
        <span className="text-xs flex-shrink-0" style={{ color: LEVEL_COLOR[g.best] }}>best {Math.round(g.top * 100)}%</span>
      </button>
      {open && (
        <div className="pl-7 pb-1">
          {g.calls.map(c => <CallRow key={c.id} c={c} {...rowProps(c)}/>)}
        </div>
      )}
    </div>
  )
}

export default function NightCalls() {
  const [nights, setNights] = useState(null)
  const [period, setPeriod] = useState(() => { try { return localStorage.getItem('chirp_nc_period') || 'night' } catch { return 'night' } })
  const [bucketKey, setBucketKey] = useState(null)
  const [grouped, setGrouped] = useState(() => { try { return localStorage.getItem('chirp_nc_grouped') !== '0' } catch { return true } })
  const [openGroups, setOpenGroups] = useState(() => new Set())
  const [data, setData] = useState(null)          // { calls, total, unnarrowed }
  const [showAll, setShowAll] = useState(false)
  const [status, setStatus] = useState(null)
  const [playing, setPlaying] = useState(null)
  const [failed, setFailed] = useState(null)
  const [canDelete, setCanDelete] = useState(false)
  const audioRef = useRef(null)

  useEffect(() => {
    api.nightCalls.nights(366).then(d => setNights(d.nights || [])).catch(() => setNights([]))
    api.nightCalls.status().then(setStatus).catch(() => {})
    api.auth.me().then(r => (r?.json ? r.json() : r)).then(u => setCanDelete(u?.role === 'admin')).catch(() => {})
  }, [])

  const bucketList = useMemo(() => buckets(nights || [], period), [nights, period])
  const bucket = bucketList.find(b => b.key === bucketKey) || bucketList[0]

  useEffect(() => { try { localStorage.setItem('chirp_nc_period', period); localStorage.setItem('chirp_nc_grouped', grouped ? '1' : '0') } catch {} }, [period, grouped])

  useEffect(() => {
    if (!bucket) return
    setData(null); setOpenGroups(new Set())
    api.nightCalls.range(bucket.start, bucket.end, showAll, period === 'night' ? 500 : 5000)
      .then(setData).catch(() => setData({ calls: [], total: 0, unnarrowed: 0 }))
  }, [bucket?.start, bucket?.end, showAll])

  const groups = useMemo(() => (data ? groupCalls(data.calls) : []), [data])

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
  const counts = bucket?.by_level || {}
  const multi = period !== 'night'
  const rowProps = c => ({ playing: playing === c.id, failed: failed === c.id, onPlay: play,
                           onDelete: canDelete ? remove : null, showDate: multi })
  const toggleGroup = k => setOpenGroups(s => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n })
  const pill = on => (on ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)' }
                         : { background: 'var(--bg-raised)', color: 'var(--text-secondary)' })

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
          10-minute stretch is analyzed. Stations need software 1.4.1 or later.
        </div>
      )}

      {nights && nights.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <div role="radiogroup" aria-label="Period" className="inline-flex rounded-lg p-0.5 text-sm" style={{ background: 'var(--bg-raised)' }}>
            {[['night', 'Night'], ['week', 'Week'], ['month', 'Month']].map(([k, label]) => (
              <button key={k} role="radio" aria-checked={period === k} onClick={() => { setPeriod(k); setBucketKey(null); setShowAll(false) }}
                      className="px-3 py-1 rounded-md" style={period === k ? pill(true) : { color: 'var(--text-secondary)' }}>{label}</button>
            ))}
          </div>
          <label className="flex items-center gap-1.5 text-xs ml-auto" style={{ color: 'var(--text-secondary)' }}>
            <input type="checkbox" checked={grouped} onChange={e => setGrouped(e.target.checked)} className="accent-chirp-500"/>
            Group by family
          </label>
        </div>
      )}

      {bucketList.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
          {bucketList.map(n => (
            <button key={n.key} onClick={() => { setBucketKey(n.key); setShowAll(false) }}
                    className="px-3 py-1.5 rounded-lg text-sm whitespace-nowrap flex-shrink-0" style={pill(n.key === bucket?.key)}>
              {n.label} <span className="opacity-70">· {n.calls.toLocaleString()}</span>
            </button>
          ))}
        </div>
      )}

      {bucket && (
        <div className="card p-4 space-y-2">
          <p className="text-xs uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
            {period === 'night' ? `Night of ${fmtNight(bucket.start)}` : `${bucket.label} · ${bucket.nights} night${bucket.nights === 1 ? '' : 's'}`}
            {' · '}{bucket.calls.toLocaleString()} call{bucket.calls === 1 ? '' : 's'}
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
            {LEVELS.map(([k, label]) => counts[k] ? (
              <span key={k}><span style={{ color: LEVEL_COLOR[k] }}>{counts[k].toLocaleString()}</span>{' '}
                <span style={{ color: 'var(--text-secondary)' }}>{label.toLowerCase()}</span></span>
            ) : null)}
          </div>
        </div>
      )}

      {data && data.calls.length > 0 && (grouped ? (
        <div className="card px-4">
          {groups.map(g => (
            <CallGroup key={g.key} g={g} open={openGroups.has(g.key)} onToggle={() => toggleGroup(g.key)} rowProps={rowProps}/>
          ))}
        </div>
      ) : (
        <div className="card px-4 py-1">
          {data.calls.map(c => <CallRow key={c.id} c={c} {...rowProps(c)}/>)}
        </div>
      ))}
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
          Every call here was only placed as a songbird or similar.
        </p>
      )}
      {bucket && !data && <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>Loading…</p>}
    </div>
  )
}
