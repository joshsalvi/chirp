import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, ChevronUp, RefreshCw, Save } from 'lucide-react'
import { api } from '../lib/api'

const pct = v => (v == null ? '—' : `${Math.round(v * 100)}%`)
const REASONS = {
  'below threshold': 'under threshold',
  'no hoot': 'no hoot heard',
  'no hoot at its pitch': 'hoot at the wrong pitch',
  'outscored by another owl': 'another owl scored higher',
}

function SpeciesRows({ species, days }) {
  const [items, setItems] = useState(null)
  useEffect(() => {
    api.nearMisses.list({ species, days, limit: 10 }).then(d => setItems(d?.items || [])).catch(() => setItems([]))
  }, [species, days])
  if (!items) return <p className="text-xs py-2" style={{ color: 'var(--text-tertiary)' }}>Loading…</p>
  return (
    <div className="py-1">
      {items.map(it => (
        <Link key={it.id} to={`/recordings/${it.recording_id}`}
              className="flex items-center justify-between gap-3 text-xs py-1 px-2 rounded hover:opacity-80"
              style={{ color: 'var(--text-secondary)' }}>
          <span className="font-mono">{pct(it.confidence)}</span>
          <span className="flex-1 truncate">
            {it.recorded_at ? new Date(it.recorded_at + 'Z').toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : it.filename}
            {' · '}{it.start_time?.toFixed(1)}–{it.end_time?.toFixed(1)} s
          </span>
          <span style={{ color: 'var(--text-tertiary)' }}>{REASONS[it.reason] || it.reason}</span>
        </Link>
      ))}
    </div>
  )
}

/**
 * Night callers BirdNET scored but didn't report, per species, with a
 * per-species threshold editor. Listen to the top near misses; if they're
 * the species, lower its threshold; if they're noise, leave it (or raise it
 * when the species' detections are noise too).
 */
export default function NearMisses() {
  const [days, setDays] = useState(90)
  const [data, setData] = useState(null)
  const [thresholds, setThresholds] = useState({})
  const [open, setOpen] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  const load = () => {
    setData(null)
    Promise.all([api.nearMisses.summary(days), api.settings.get()])
      .then(([sum, s]) => {
        setData(sum)
        setThresholds({ ...(s?.birdnet_species_thresholds || {}) })
      })
      .catch(e => { setError(e.message || String(e)); setData({ species: [] }) })
  }
  useEffect(load, [days]) // eslint-disable-line react-hooks/exhaustive-deps

  const setOne = (name, v) => setThresholds(t => {
    const n = { ...t }
    if (v === '' || v == null) delete n[name]
    else n[name] = Number(v) / 100
    return n
  })

  const save = async () => {
    setSaving(true); setError(null)
    try {
      const r = await api.settings.update({ birdnet_species_thresholds: thresholds })
      setThresholds({ ...(r?.birdnet_species_thresholds || thresholds) })
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      load()
    } catch (e) { setError(e.message || String(e)) }
    setSaving(false)
  }

  const rows = data?.species || []
  const steps = data?.steps || []
  return (
    <div className="space-y-3">
      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        Owls and other night callers BirdNET scored but didn't report: under the threshold, or an owl score
        with no hoot at that owl's pitch. Listen to the top ones. If they're the species, lower its threshold;
        a threshold here replaces the default (20% for owls, 10% for other night callers) for that species on
        new analyses and re-analyses.
      </p>
      <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
        Last
        {[30, 90, 365].map(d => (
          <button key={d} type="button" onClick={() => setDays(d)}
                  className={`px-2 py-1 rounded border ${days === d ? 'border-chirp-500 text-chirp-300' : 'border-surface-600'}`}>
            {d} days
          </button>
        ))}
      </div>
      {!data ? (
        <p className="text-xs flex items-center gap-1" style={{ color: 'var(--text-tertiary)' }}><RefreshCw size={11} className="animate-spin"/> Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>No near misses in this period. They're logged from 0.5.10 on, as recordings are analyzed.</p>
      ) : (
        <div className="space-y-1">
          {rows.map(r => {
            const custom = thresholds[r.species]
            const would = steps.filter(t => t < r.threshold).map(t => [t, r.would_add[t.toFixed(3)] || 0]).filter(([, n]) => n > 0)
            return (
              <div key={r.species} className="rounded-lg" style={{ background: 'var(--bg-raised)' }}>
                <div className="flex items-center gap-3 px-3 py-2 flex-wrap">
                  <button type="button" onClick={() => setOpen(o => o === r.species ? null : r.species)}
                          className="flex items-center gap-1 text-sm flex-1 min-w-[160px] text-left" style={{ color: 'var(--text-primary)' }}>
                    {open === r.species ? <ChevronUp size={12}/> : <ChevronDown size={12}/>} {r.species}
                  </button>
                  <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {r.recordings} rec · best {pct(r.max)} · median {pct(r.p50)}
                    {r.detections > 0 && <> · {r.detections} detected (lowest {pct(r.lowest_detection)})</>}
                  </span>
                  <label className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
                    Threshold
                    <input type="number" min={1} max={99} step={1} className="input w-16 text-xs py-1"
                           placeholder={String(Math.round(r.threshold * 100))}
                           value={custom != null ? Math.round(custom * 100) : ''}
                           onChange={e => setOne(r.species, e.target.value)}/>%
                  </label>
                </div>
                <div className="px-3 pb-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  {Object.entries(r.reasons).map(([k, n]) => `${REASONS[k] || k}: ${n}`).join(' · ')}
                  {would.length > 0 && <> · lowering to {would.map(([t, n]) => `${Math.round(t * 100)}% adds ${n}`).join(', ')}</>}
                </div>
                {open === r.species && <div className="px-1 pb-2"><SpeciesRows species={r.species} days={days}/></div>}
              </div>
            )
          })}
        </div>
      )}
      <div className="flex items-center gap-3">
        <button type="button" onClick={save} disabled={saving || !data} className="btn-secondary text-xs">
          {saving ? <RefreshCw size={12} className="animate-spin"/> : <Save size={12}/>} {saved ? 'Saved' : 'Save thresholds'}
        </button>
        {Object.keys(thresholds).length > 0 && (
          <span className="text-xs flex flex-wrap gap-1 items-center" style={{ color: 'var(--text-tertiary)' }}>
            Custom:
            {Object.entries(thresholds).map(([k, v]) => (
              <button key={k} type="button" onClick={() => setOne(k, '')} title="Remove (unsaved until Save)"
                      className="px-1.5 py-0.5 rounded border border-surface-600">{k} {pct(v)} ×</button>
            ))}
          </span>
        )}
      </div>
      {error && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{error}</p>}
    </div>
  )
}
