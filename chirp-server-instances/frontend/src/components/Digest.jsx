/**
 * One day's digest in full: where the daily digest push (and a digest in
 * Notifications) opens. Same numbers as the email and push digest
 * (GET /recordings/statistics/digest), plus activity by hour and every
 * species with its photo, first time heard and best recording.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ChevronLeft, ChevronRight, Sparkles, Play } from 'lucide-react'
import { api, mediaUrl } from '../lib/api'
import { BirdIcon } from './BirdBatIcons'

const iso = d => d.toISOString().slice(0, 10)
const shift = (dateStr, days) => {
  const d = new Date(dateStr + 'T12:00:00Z')
  d.setUTCDate(d.getUTCDate() + days)
  return iso(d)
}
const today = () => iso(new Date(Date.now() - new Date().getTimezoneOffset() * 60000))
const yesterday = () => shift(today(), -1)
const HOUR_LABELS = { 0: '12a', 6: '6a', 12: '12p', 18: '6p' }

function Stat({ value, label }) {
  return (
    <div className="rounded-2xl px-3 py-3 text-center" style={{ background: 'var(--bg-raised)' }}>
      <p className="font-display text-2xl font-bold leading-none" style={{ color: 'var(--accent-400)' }}>
        {value?.toLocaleString?.() ?? value}
      </p>
      <p className="text-[11px] mt-1.5 uppercase tracking-wide" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
    </div>
  )
}

function HourChart({ hours }) {
  const max = Math.max(1, ...hours)
  const peak = hours.indexOf(Math.max(...hours))
  return (
    <div>
      <div className="flex items-end gap-[3px] h-24">
        {hours.map((n, h) => (
          <div key={h} className="flex-1 rounded-t-sm transition-all"
               title={`${n} at ${h}:00`}
               style={{
                 height: `${n ? Math.max(6, (n / max) * 100) : 2}%`,
                 background: h === peak && n ? 'var(--accent-400)' : 'var(--accent-500)',
                 opacity: n ? (h === peak ? 1 : 0.45) : 0.15,
               }}/>
        ))}
      </div>
      <div className="flex mt-1.5">
        {hours.map((_, h) => (
          <span key={h} className="flex-1 text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{HOUR_LABELS[h] || ''}</span>
        ))}
      </div>
    </div>
  )
}

function SpeciesRow({ sp }) {
  const to = sp.profile_id ? `/library/${sp.profile_id}` : `/bird?label=${encodeURIComponent(sp.name)}`
  return (
    <li className="flex items-center gap-3 py-2.5">
      <Link to={to} className="flex items-center gap-3 flex-1 min-w-0" style={{ textDecoration: 'none' }}>
        <span className="w-11 h-11 rounded-full overflow-hidden flex-shrink-0 flex items-center justify-center"
              style={{ background: 'var(--bg-raised)', border: sp.new ? '2px solid var(--accent-400)' : '1px solid var(--border-subtle)' }}>
          {sp.photo_url
            ? <img src={mediaUrl(sp.photo_url)} alt="" loading="lazy" className="w-full h-full object-cover"/>
            : <BirdIcon size={18} style={{ color: 'var(--text-tertiary)' }}/>}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{sp.name}</span>
            {sp.new && (
              <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0"
                    style={{ background: 'var(--accent-400)', color: 'var(--bg-base, #000)' }}>NEW</span>
            )}
          </span>
          <span className="block text-[11px] truncate" style={{ color: 'var(--text-tertiary)' }}>
            {[sp.first_heard && `first ${sp.first_heard}`, sp.best != null && `best ${Math.round(sp.best * 100)}%`].filter(Boolean).join(' · ')}
          </span>
        </span>
        <span className="font-display text-lg font-semibold flex-shrink-0 tabular-nums" style={{ color: 'var(--text-primary)' }}>
          {sp.count}
        </span>
      </Link>
      {sp.best_recording_id && (
        <Link to={`/recordings?species=${encodeURIComponent(sp.name)}`} aria-label={`Recordings of ${sp.name}`}
              className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }}>
          <Play size={13} fill="currentColor"/>
        </Link>
      )}
    </li>
  )
}

export default function Digest() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const date = params.get('date') || yesterday()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setData(null); setError(null)
    api.recordings.digest(date).then(setData).catch(e => setError(e.message || 'Could not load the digest'))
  }, [date])

  const go = days => setParams({ date: shift(date, days) }, { replace: true })
  const atLatest = date >= today()

  return (
    <div className="max-w-2xl mx-auto px-4 md:px-6 py-5 md:py-8 space-y-4 animate-fade-in">
      <button className="btn-ghost text-sm flex items-center gap-1.5 -ml-2" onClick={() => navigate('/notifications')}>
        <ArrowLeft size={14}/> Notifications
      </button>

      {/* Day header with previous / next day */}
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-widest" style={{ color: 'var(--accent-400)' }}>
            Daily digest{data?.partial ? ' · so far today' : ''}
          </p>
          <h1 className="font-display text-2xl font-bold leading-tight" style={{ color: 'var(--text-primary)' }}>
            {data?.day || new Date(date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
          </h1>
        </div>
        <div className="flex gap-1.5 flex-shrink-0">
          <button onClick={() => go(-1)} aria-label="Previous day" data-haptic="selection"
                  className="w-9 h-9 rounded-full flex items-center justify-center" style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
            <ChevronLeft size={18}/>
          </button>
          <button onClick={() => go(1)} disabled={atLatest} aria-label="Next day" data-haptic="selection"
                  className="w-9 h-9 rounded-full flex items-center justify-center disabled:opacity-30" style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
            <ChevronRight size={18}/>
          </button>
        </div>
      </div>

      {error && <p className="text-sm" style={{ color: 'var(--pastel-red)' }}>{error}</p>}
      {!data && !error && (
        <div className="space-y-3">
          <div className="skeleton h-20 rounded-2xl"/><div className="skeleton h-32 rounded-2xl"/><div className="skeleton h-64 rounded-2xl"/>
        </div>
      )}

      {data?.quiet && (
        <div className="card p-8 text-center">
          <BirdIcon size={28} style={{ color: 'var(--text-tertiary)', margin: '0 auto 10px' }}/>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{date >= today() ? 'No birds recorded yet today.' : 'No birds were recorded this day.'}</p>
        </div>
      )}

      {data && !data.quiet && (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Stat value={data.species_count} label="species"/>
            <Stat value={data.recordings} label="recordings"/>
            <Stat value={data.detections} label="detections"/>
          </div>

          {data.new_species?.length > 0 && (
            <section className="card p-4" style={{ borderColor: 'var(--accent-400)' }}>
              <div className="flex items-center gap-2 mb-2.5">
                <Sparkles size={15} style={{ color: 'var(--accent-400)' }}/>
                <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                  First time at your site
                </h2>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {data.new_species.map(n => (
                  <Link key={n} to={`/bird?label=${encodeURIComponent(n)}`} className="text-xs px-2.5 py-1 rounded-full"
                        style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)', textDecoration: 'none' }}>{n}</Link>
                ))}
              </div>
            </section>
          )}

          <section className="card p-4">
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Activity by hour</h2>
              {data.busiest_hour && <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>busiest {data.busiest_hour}</span>}
            </div>
            <HourChart hours={data.hours}/>
          </section>

          <section className="card px-4 pt-4 pb-1">
            <div className="flex items-baseline justify-between">
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Every species heard</h2>
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>detections</span>
            </div>
            <ul className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
              {data.species.map(sp => <SpeciesRow key={sp.name} sp={sp}/>)}
            </ul>
          </section>
        </>
      )}
    </div>
  )
}
