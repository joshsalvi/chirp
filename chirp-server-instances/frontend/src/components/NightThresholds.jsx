import { useEffect, useMemo, useState } from 'react'
import { RefreshCw, Save, Search } from 'lucide-react'
import { api } from '../lib/api'

const pct = v => (v == null ? '—' : `${Math.round(v * 100)}%`)

const MODES = [
  { id: 'night', label: 'Night floors', hint: 'Owls 20%, other night callers 10% (or the global threshold, if lower).' },
  { id: 'global', label: 'Global threshold', hint: 'Night callers need the same score as every other species.' },
  { id: 'per_species', label: 'Per species', hint: 'Choose for each night caller below.' },
]

/**
 * How owls, nightjars, rails, woodcock and bitterns are thresholded:
 * their own lower floors, the global BirdNET threshold, or a choice per
 * species. A per-species score from Near Misses below still wins.
 * Applies to new analyses and re-analyses, and is sent to devices.
 */
export default function NightThresholds() {
  const [data, setData] = useState(null)
  const [mode, setMode] = useState('night')
  const [perSpecies, setPerSpecies] = useState({})
  const [filter, setFilter] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  const load = () => {
    Promise.all([api.nearMisses.nightSpecies(), api.settings.get()])
      .then(([d, s]) => {
        setData(d)
        setMode(s?.night_threshold_mode || 'night')
        setPerSpecies({ ...(s?.night_threshold_species || {}) })
      })
      .catch(e => { setError(e.message || String(e)); setData({ items: [] }) })
  }
  useEffect(load, [])

  const items = data?.items || []
  const shown = useMemo(() => {
    const f = filter.trim().toLowerCase()
    return f ? items.filter(i => i.species.toLowerCase().includes(f)) : items
  }, [items, filter])

  const usesNight = name => perSpecies[name] !== false
  const setAll = night => setPerSpecies(Object.fromEntries(items.map(i => [i.species, night])))

  const save = async () => {
    setSaving(true); setError(null)
    try {
      await api.settings.update({ night_threshold_mode: mode, night_threshold_species: perSpecies })
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      load()
    } catch (e) { setError(e.message || String(e)) }
    setSaving(false)
  }

  const g = data?.global_threshold
  return (
    <div className="space-y-3">
      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        Night callers score lower than day birds (faint, far, often in insect noise), so by default they're kept
        at lower floors than the global BirdNET threshold{g != null && <> ({pct(g)})</>}. Use the global threshold
        if night noise gets through, or choose per species. A threshold set under Near Misses still applies to that
        species. Takes effect on new recordings and re-analyses, and on devices at their next check-in.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {MODES.map(m => (
          <button key={m.id} type="button" onClick={() => setMode(m.id)}
                  className="text-left rounded-lg px-3 py-2 border transition-colors"
                  style={mode === m.id
                    ? { background: 'var(--nav-active-bg)', borderColor: 'var(--border-focus)', color: 'var(--text-primary)' }
                    : { background: 'var(--bg-raised)', borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}>
            <span className="block text-sm font-medium">{m.label}</span>
            <span className="block text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{m.hint}</span>
          </button>
        ))}
      </div>

      {mode === 'per_species' && (
        !data ? (
          <p className="text-xs flex items-center gap-1" style={{ color: 'var(--text-tertiary)' }}><RefreshCw size={11} className="animate-spin"/> Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>No night callers known for this location yet. Set the location in Settings → Location.</p>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <div className="relative flex-1 min-w-[160px]">
                <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-tertiary)' }}/>
                <input className="input text-xs py-1 pl-7 w-full" placeholder="Filter species" value={filter}
                       onChange={e => setFilter(e.target.value)}/>
              </div>
              <button type="button" className="btn-ghost text-xs" onClick={() => setAll(true)}>All night floors</button>
              <button type="button" className="btn-ghost text-xs" onClick={() => setAll(false)}>All global</button>
            </div>
            <div className="rounded-lg divide-y" style={{ background: 'var(--bg-raised)', borderColor: 'var(--border-subtle)' }}>
              {shown.map(i => {
                const night = usesNight(i.species)
                return (
                  <label key={i.species} className="flex items-center gap-3 px-3 py-2 cursor-pointer"
                         style={{ borderColor: 'var(--border-subtle)' }}>
                    <span className="flex-1 min-w-0">
                      <span className="text-sm block truncate" style={{ color: 'var(--text-primary)' }}>{i.species}</span>
                      <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                        needs {pct(night ? i.night_threshold : i.global_threshold)}
                        {i.custom != null && <> · custom {pct(i.custom)} applies</>}
                        {i.detections > 0 && <> · {i.detections.toLocaleString()} detected</>}
                      </span>
                    </span>
                    <span className="text-xs" style={{ color: night ? 'var(--accent-400)' : 'var(--text-secondary)' }}>
                      {night ? 'Night floor' : 'Global'}
                    </span>
                    <input type="checkbox" className="h-4 w-4" checked={night}
                           aria-label={`${i.species} uses the night floor`}
                           onChange={e => setPerSpecies(p => ({ ...p, [i.species]: e.target.checked }))}/>
                  </label>
                )
              })}
            </div>
          </div>
        )
      )}

      <div className="flex items-center gap-3">
        <button type="button" onClick={save} disabled={saving || !data} className="btn-secondary text-xs">
          {saving ? <RefreshCw size={12} className="animate-spin"/> : <Save size={12}/>} {saved ? 'Saved' : 'Save night thresholds'}
        </button>
      </div>
      {error && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{error}</p>}
    </div>
  )
}
