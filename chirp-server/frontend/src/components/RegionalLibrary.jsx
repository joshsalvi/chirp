/**
 * Regional Bird Library — year-round checklist from eBird + local detections.
 * All species in the region are shown regardless of season; users can filter
 * by any month using the month selector.
 */

import { useEffect, useState, useCallback, useMemo, useRef, memo } from 'react'
import { publicPlace } from '../lib/place'
import { Link } from 'react-router-dom'
import { Search, RefreshCw, MapPin, ExternalLink, CheckCircle, AlertCircle, Calendar, X, ChevronDown, ChevronUp } from 'lucide-react'
import { api } from '../lib/api'
import { BirdIcon, BatIcon } from './BirdBatIcons'
import { useRevealMore } from '../lib/useRevealMore'

// ── Constants ──────────────────────────────────────────────────────────────────
const MONTHS_SHORT = ['J','F','M','A','M','J','J','A','S','O','N','D']
const MONTHS_FULL  = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

const SEASONS = [
  { months: [11, 0, 1], color: '#60a5fa', label: 'Winter' },
  { months: [2,  3, 4], color: '#4ade80', label: 'Spring' },
  { months: [5,  6, 7], color: '#facc15', label: 'Summer' },
  { months: [8, 9,10], color: '#f97316', label: 'Autumn' },
]

const FILTER_TABS = ['All', 'Detected Here', 'Very Likely', 'Likely', 'Possible', 'Rare']

// ── Helpers ───────────────────────────────────────────────────────────────────
// Pure likelihood rank — ignores locally_detected so detected birds still appear
// in likelihood-based filter tabs (Very Likely, Likely, etc.)
function getLikelihoodRank(sp, allFreqs, viewMonth) {
  const freq = sp.monthly_frequency?.[viewMonth] ?? sp.current_likelihood ?? 0
  if (freq <= 0) return 'Rare'
  const total = Math.max(allFreqs.length, 1)
  const below = allFreqs.filter(f => f < freq).length
  const rank  = (below + allFreqs.filter(f => f === freq).length / 2) / total
  if (rank >= 0.75) return 'Very Likely'
  if (rank >= 0.45) return 'Likely'
  if (rank >= 0.20) return 'Possible'
  return 'Rare'
}

// Note: display-label logic (locally_detected takes priority over rank) is
// now computed directly in displayLabelBySpecies below, rather than via a
// separate getLikelihoodLabel(sp, allFreqs, viewMonth) helper — the memoized
// map already has rankBySpecies available, so re-deriving from allFreqs a
// second time here would be redundant.

const LIKELIHOOD_STYLE = {
  'Detected Here': { badge: 'badge-purple',  dot: '#a78bfa' },
  'Very Likely':   { badge: 'badge-green',   dot: '#22c55e' },
  'Likely':        { badge: 'badge-teal',    dot: '#14b8a6' },
  'Possible':      { badge: 'badge-yellow',  dot: '#f59e0b' },
  'Rare':          { badge: 'badge-gray',    dot: '#6b7280' },
}

function sortSpecies(list, sortBy, month) {
  return [...list].sort((a, b) => {
    const fa = a.monthly_frequency?.[month] ?? a.current_likelihood ?? 0
    const fb = b.monthly_frequency?.[month] ?? b.current_likelihood ?? 0
    if (sortBy === 'name_asc') return a.common_name.localeCompare(b.common_name)
    if (sortBy === 'cur_asc')  return fa - fb
    return fb - fa  // default: this month desc
  })
}

// ── Sub-components ─────────────────────────────────────────────────────────────
function FreqBars({ monthly, viewMonth }) {
  if (!monthly || monthly.length < 12) return null
  const max = Math.max(...monthly, 0.001)
  return (
    <div className="flex items-end gap-px mt-1" style={{ height: 24 }}>
      {monthly.map((v, i) => {
        const isCur = i === viewMonth
        const barH  = v > 0 ? Math.max(2, Math.round((v / max) * 20)) : 1
        const season = SEASONS.find(s => s.months.includes(i))
        const color  = isCur ? 'var(--accent-400)'
          : v > 0 ? (season?.color || '#059669')
          : 'var(--s700)'
        return (
          <div key={i} className="flex flex-col items-center flex-1"
               title={MONTHS_FULL[i]}>
            <div style={{ height: barH, background: color, borderRadius: 1, width: '100%',
                          outline: isCur ? `1px solid var(--accent-400)` : 'none' }}/>
            <div style={{ fontSize: 6, color: isCur ? 'var(--accent-400)' : 'transparent',
                          height: 7, lineHeight: '7px', fontWeight: 700 }}>
              {MONTHS_SHORT[i]}
            </div>
          </div>
        )
      })}
    </div>
  )
}

const SpeciesCard = memo(function SpeciesCard({ sp, label, viewMonth }) {
  const style   = LIKELIHOOD_STYLE[label] || LIKELIHOOD_STYLE['Rare']
  const hasFreq = sp.monthly_frequency?.some(v => v > 0)

  // Resolve profile link: prefer profile ID, fall back to label/name for lookup
  const profileLink = sp.profile_id
    ? { to: `/library/${sp.profile_id}`, state: { from: '/regional' } }
    : { to: `/bird?label=${encodeURIComponent(sp.label || sp.common_name)}`, state: { from: '/regional' } }

  return (
    <div className="card-hover cv-row flex items-start gap-3 p-3 group overflow-hidden"
         style={{ borderLeft: `2px solid ${style.dot}`, boxShadow: 'var(--shadow-card)' }}>
      {/* Photo */}
      <Link {...profileLink} className="flex-shrink-0">
        <div className="w-12 h-12 rounded-lg overflow-hidden" style={{ background: 'var(--bg-raised)' }}>
          {sp.photo_url
            ? <img src={sp.photo_url} alt={sp.common_name} className="w-full h-full object-cover" loading="lazy"/>
            : <div className="w-full h-full flex items-center justify-center"><BirdIcon size={22} style={{ color: 'var(--text-tertiary)' }}/></div>}
        </div>
      </Link>

      {/* Body */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-1">
          <Link {...profileLink}
            className="text-sm font-semibold truncate leading-snug transition-colors hover:text-accent"
            style={{ color: 'var(--text-primary)' }}>
            {sp.common_name}
          </Link>
          <div className="flex items-center gap-1 flex-shrink-0">
            <span className={`badge ${style.badge}`}>{label === 'Detected Here' ? '✓' : label}</span>
          </div>
        </div>
        <p className="text-xs italic truncate" style={{ color: 'var(--text-tertiary)' }}>{sp.scientific_name}</p>
        {hasFreq && <FreqBars monthly={sp.monthly_frequency} viewMonth={viewMonth}/>}

        {/* Footer */}
        <div className="flex items-center gap-2 mt-1">
          {sp.family_com_name && (
            <span className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>{sp.family_com_name}</span>
          )}
          <div className="flex-1"/>
          {sp.ebird_url && (
            <a href={sp.ebird_url} target="_blank" rel="noopener noreferrer"
               onClick={e => e.stopPropagation()} title="View on eBird"
               className="transition-colors" style={{ color: 'var(--text-tertiary)' }}>
              <ExternalLink size={10}/>
            </a>
          )}
        </div>
      </div>
    </div>
  )
})

const BatSpeciesCard = memo(function BatSpeciesCard({ sp }) {
  const profileLink = sp.profile_id
    ? { to: `/library/${sp.profile_id}`, state: { from: '/regional' } }
    : { to: `/library?name=${encodeURIComponent(sp.common_name)}`, state: { from: '/regional' } }

  return (
    <div className="card-hover cv-row flex items-start gap-3 p-3 group overflow-hidden"
         style={{ borderLeft: '2px solid #a78bfa' }}>
      <Link {...profileLink} className="flex-shrink-0">
        <div className="w-12 h-12 rounded-lg overflow-hidden" style={{ background: 'var(--bg-raised)' }}>
          {(sp.photo_url || sp.photo_path)
            ? <img src={sp.photo_url || sp.photo_path} alt={sp.common_name} className="w-full h-full object-cover" loading="lazy"/>
            : <div className="w-full h-full flex items-center justify-center"><BatIcon size={22} style={{ color: 'var(--text-tertiary)' }}/></div>}
        </div>
      </Link>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-1">
          <Link {...profileLink}
            className="text-sm font-semibold truncate leading-snug transition-colors hover:text-accent"
            style={{ color: 'var(--text-primary)' }}>
            {sp.common_name}
          </Link>
          <span className="text-xs font-mono flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
            {Math.round((sp.max_confidence || 0) * 100)}%
          </span>
        </div>
        <p className="text-xs italic truncate" style={{ color: 'var(--text-tertiary)' }}>{sp.scientific_name}</p>
        <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
          {sp.total_detections} detection{sp.total_detections !== 1 ? 's' : ''}
        </p>
      </div>
    </div>
  )
})

// ── Main component ─────────────────────────────────────────────────────────────
export default function RegionalLibrary() {
  const [species,    setSpecies]    = useState([])
  const [identifiedBats, setIdentifiedBats] = useState([])
  const [batsExpanded, setBatsExpanded] = useState(false)
  const [settings,   setSettings]   = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [search,     setSearch]     = useState('')
  const [filter,     setFilter]     = useState('All')
  const [sortBy,     setSortBy]     = useState('cur_desc')
  const [viewMonth,  setViewMonth]  = useState(new Date().getMonth())

  // Progressive rendering: mount cards (and their photos) in chunks instead
  // of all ~93 at once. Initial mount of ~93 simultaneous <img> requests +
  // card renders was the actual measured slowness on this page (the API
  // query itself is fast, ~25ms) — this cuts the initial paint down to one
  // chunk, revealing more as the user scrolls, via the same
  // IntersectionObserver sentinel idiom already used for lazy image reveal
  // in RecordingsList.jsx. 24 matches the app's own established page-size
  // vocabulary (Recordings' 6/12/24/48 options).
  const CHUNK = 24
  const [visibleCount, setVisibleCount] = useState(CHUNK)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, lib] = await Promise.all([
        api.settings.get(),
        api.birds.regionalLibrary({ limit: 1000 }),
      ])
      setSettings(s)
      // Identified bat species — separate, tolerant fetch: this section is
      // supplementary (the Field Guide's core purpose is the eBird
      // checklist above), so a failure here shouldn't block or blank out
      // the rest of the page.
      try {
        const bats = await api.birds.identifiedBats()
        setIdentifiedBats(Array.isArray(bats) ? bats : [])
      } catch { setIdentifiedBats([]) }
      // Deduplicate by eBird species code (stable canonical ID) — falls back
      // to a normalized common_name only when the code is missing. Pure
      // common_name matching is fragile against near-duplicate eBird entries
      // with subtly different name text (this is a second line of defense;
      // the backend already dedups the same way, but a stale cached response
      // or an older server build shouldn't be able to slip duplicates through).
      const seen = new Map()
      for (const sp of lib) {
        const key = (sp.ebird_species_code && sp.ebird_species_code.trim())
          || (sp.common_name || '').trim().toLowerCase()
        const existing = seen.get(key)
        if (!existing || sp.current_likelihood > existing.current_likelihood) {
          seen.set(key, sp)
        }
      }
      setSpecies([...seen.values()])
    } catch { /* load failed */ }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const handleRefresh = async () => {
    setRefreshing(true)
    try { await api.birds.refreshRegionalLibrary() } catch {}
    let n = 0
    const poll = setInterval(async () => {
      n++
      try {
        const d = await api.birds.regionalLibrary({ limit: 5 })
        if (d.length > 0) { clearInterval(poll); setRefreshing(false); load() }
      } catch {}
      if (n > 40) { clearInterval(poll); setRefreshing(false) }
    }, 2000)
  }

  // Frequencies for the currently-viewed month (for percentile ranking).
  // Memoized: only depends on species/viewMonth, not on search/filter/sortBy —
  // without this, typing in the search box recomputed this (and everything
  // derived from it below) from scratch on every keystroke.
  const allFreqs = useMemo(
    () => species.map(s => s.monthly_frequency?.[viewMonth] ?? s.current_likelihood ?? 0).filter(f => f > 0),
    [species, viewMonth]
  )

  // Each species' PURE rank, computed exactly ONCE per species per
  // [species, viewMonth] change — keyed the same way SpeciesCard is keyed
  // (ebird_species_code || common_name). Previously getLikelihoodRank (an
  // O(allFreqs.length) scan) ran up to 3x per species per render: once in
  // labelCounts, once in the filter predicate, and once more inside each
  // SpeciesCard's own render (via getLikelihoodLabel) — all three re-running
  // on every single search keystroke even though none of them depend on
  // search text. For ~93 species that's tens of thousands of redundant
  // comparisons per keystroke. Now: computed once, read three times.
  //
  // IMPORTANT: this must stay RANK (getLikelihoodRank), not the display
  // LABEL (getLikelihoodLabel) — labelCounts and the filter predicate below
  // intentionally use the locally_detected-agnostic rank (see the comment on
  // getLikelihoodRank above) so a locally-detected "Very Likely" species
  // still counts toward and appears under the "Very Likely" tab, not just
  // "Detected Here". Only the card's own badge should prioritize "Detected
  // Here" — that's handled separately below via displayLabelBySpecies.
  const rankBySpecies = useMemo(() => {
    const m = new Map()
    for (const sp of species) {
      const key = sp.ebird_species_code || sp.common_name
      m.set(key, getLikelihoodRank(sp, allFreqs, viewMonth))
    }
    return m
  }, [species, allFreqs, viewMonth])

  // Display label for each card's badge — cheap to derive from rankBySpecies
  // (no re-scan of allFreqs needed), but kept as its own map since it's a
  // different value (locally_detected takes priority) than what counting/
  // filtering use.
  const displayLabelBySpecies = useMemo(() => {
    const m = new Map()
    for (const sp of species) {
      const key = sp.ebird_species_code || sp.common_name
      m.set(key, sp.locally_detected ? 'Detected Here' : rankBySpecies.get(key))
    }
    return m
  }, [species, rankBySpecies])

  const labelCounts = useMemo(() => Object.fromEntries(
    FILTER_TABS.map(l => [l,
      l === 'All'            ? species.length
      : l === 'Detected Here' ? species.filter(s => s.locally_detected).length
      : species.filter(s => rankBySpecies.get(s.ebird_species_code || s.common_name) === l).length
    ])
  ), [species, rankBySpecies])

  const filtered = useMemo(() => sortSpecies(
    species.filter(sp => {
      if (search) {
        const q = search.toLowerCase()
        if (!sp.common_name.toLowerCase().includes(q) &&
            !(sp.scientific_name || '').toLowerCase().includes(q)) return false
      }
      if (filter !== 'All') {
        const key = sp.ebird_species_code || sp.common_name
        if (filter === 'Detected Here' && !sp.locally_detected) return false
        if (filter !== 'Detected Here' && rankBySpecies.get(key) !== filter) return false
      }
      return true
    }),
    sortBy, viewMonth
  ), [species, search, filter, sortBy, viewMonth, rankBySpecies])

  // Reset back to the first chunk whenever the result set changes shape —
  // otherwise a stale high visibleCount from a previous broad view would
  // make a newly-narrowed search feel inconsistent with a fresh page load.
  useEffect(() => { setVisibleCount(CHUNK) }, [search, filter, sortBy, viewMonth])

  // Next chunk as the end of the list nears the screen (lib/useRevealMore).
  const sentinelRef = useRevealMore(() => setVisibleCount(c => Math.min(c + CHUNK, filtered.length)))

  const locationStr = publicPlace(settings?.location_name)
    || (settings?.latitude ? `${settings.latitude.toFixed(3)}, ${settings.longitude.toFixed(3)}` : null)

  const currentSeason = SEASONS.find(s => s.months.includes(viewMonth))

  return (
    <div className="page-root">

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
        <div>
          <h1 className="section-title">Field Guide</h1>
          <div className="flex items-center gap-1.5 mt-1" style={{ color: 'var(--text-secondary)' }}>
            {locationStr && <><MapPin size={12}/><span className="text-sm">{locationStr}</span></>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!loading && species.length > 0 && (
            <span className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
              {filtered.length} / {species.length}
            </span>
          )}
          <button onClick={handleRefresh} disabled={refreshing} className="btn-secondary">
            <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''}/>
            <span className="hidden sm:inline">{refreshing ? 'Fetching…' : 'Refresh'}</span>
          </button>
        </div>
      </div>

      {/* Bats identified locally card moved below the controls bar — see there */}

      {/* ── Empty state ── */}
      {!loading && species.length === 0 && (
        <div className="card p-5 mb-4" style={{ border: '1px solid rgba(234,179,8,.2)', background: 'rgba(234,179,8,.04)' }}>
          <div className="flex items-start gap-3">
            <AlertCircle size={18} style={{ color: 'var(--pastel-yellow)', flexShrink: 0, marginTop: 1 }}/>
            <div>
              <p className="text-sm font-medium mb-1" style={{ color: 'var(--pastel-yellow)' }}>No regional data yet</p>
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                Set your location and eBird API key in Settings, then click Refresh above.
              </p>
              <Link to="/settings" className="btn-primary text-xs inline-flex mt-3">Open Settings →</Link>
            </div>
          </div>
        </div>
      )}

      {/* ── Controls bar ── */}
      {species.length > 0 && (
        <div className="card p-3 mb-4 space-y-3">
          {/* Row 1: search + sort */}
          <div className="flex gap-2 flex-wrap">
            <div className="relative flex-1 min-w-36">
              <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-tertiary)' }}/>
              <input className="input pl-8 text-sm" placeholder="Search…"
                     value={search} onChange={e => setSearch(e.target.value)}/>
            </div>
            <select className="input text-sm w-36" value={sortBy} onChange={e => setSortBy(e.target.value)}>
              <option value="cur_desc">Frequency ↓</option>
              <option value="cur_asc">Frequency ↑</option>
              <option value="name_asc">Name A→Z</option>
            </select>
            {search && (
              <button className="btn-icon" onClick={() => setSearch('')}><X size={13}/></button>
            )}
          </div>

          {/* Row 2: month picker */}
          <div>
            <div className="flex items-center gap-1 mb-2">
              <Calendar size={11} style={{ color: 'var(--text-tertiary)' }}/>
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                Viewing: <span style={{ color: 'var(--accent-400)', fontWeight: 600 }}>{MONTHS_FULL[viewMonth]}</span>
                {currentSeason && <span style={{ color: 'var(--text-tertiary)' }}> ({currentSeason.label})</span>}
              </span>
            </div>
            <div className="flex gap-px">
              {MONTHS_SHORT.map((m, i) => {
                const season = SEASONS.find(s => s.months.includes(i))
                const isActive = i === viewMonth
                return (
                  <button key={i} onClick={() => setViewMonth(i)}
                    className="tactile-press flex-1 py-1 text-center transition-all rounded-sm"
                    style={{
                      fontSize: 10, fontWeight: isActive ? 700 : 400,
                      background: isActive ? 'var(--nav-active-bg)' : 'transparent',
                      color: isActive ? 'var(--accent-400)' : 'var(--text-tertiary)',
                      outline: isActive ? '1px solid var(--border-focus)' : 'none',
                    }}
                    title={MONTHS_FULL[i]}>
                    {m}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Row 3: filter tabs */}
          <div className="flex flex-wrap gap-1.5">
            {FILTER_TABS.filter(l => labelCounts[l] > 0 || l === 'All').map(l => (
              <button key={l} onClick={() => setFilter(l)}
                className="tactile-press px-2.5 py-1 rounded-lg text-xs font-medium transition-all"
                style={filter === l
                  ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)', border: '1px solid var(--border-default)' }
                  : { background: 'var(--bg-raised)', color: 'var(--text-tertiary)', border: '1px solid var(--border-subtle)' }
                }>
                {l}
                {labelCounts[l] > 0 && (
                  <span className="ml-1 opacity-60">{labelCounts[l]}</span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Bats identified locally — moved below the controls bar and
          collapsed by default per feedback (previously always-expanded,
          at the very top of the page). Separate from the eBird checklist
          below since eBird has no bat taxonomy at all — see the
          identified-bats endpoint's own docstring. ── */}
      {identifiedBats.length > 0 && (
        <div className="card overflow-hidden mb-4" style={{ border: '1px solid rgba(167,139,250,.25)' }}>
          <button onClick={() => setBatsExpanded(v => !v)}
                  className="w-full flex items-center justify-between px-4 py-3 transition-colors hover:opacity-90"
                  style={{ background: 'rgba(167,139,250,.04)' }}>
            <div className="flex items-center gap-2">
              <BatIcon size={16} style={{ color: '#a78bfa' }}/>
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                Bats Identified Locally
              </h2>
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                ({identifiedBats.length} species)
              </span>
            </div>
            {batsExpanded ? <ChevronUp size={16} style={{ color: 'var(--text-tertiary)' }}/>
                          : <ChevronDown size={16} style={{ color: 'var(--text-tertiary)' }}/>}
          </button>
          {batsExpanded && (
            <div className="p-4" style={{ background: 'rgba(167,139,250,.04)', borderTop: '1px solid rgba(167,139,250,.15)' }}>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {identifiedBats.map(sp => (
                  <BatSpeciesCard key={sp.common_name} sp={sp}/>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Grid ── */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="card p-3 flex gap-3">
              <div className="w-12 h-12 skeleton rounded-lg flex-shrink-0"/>
              <div className="flex-1 space-y-2 pt-1">
                <div className="skeleton h-3 w-1/2 rounded"/>
                <div className="skeleton h-2 w-1/3 rounded"/>
                <div className="skeleton h-5 w-full rounded mt-2"/>
              </div>
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16" style={{ color: 'var(--text-secondary)' }}>
          {species.length > 0 ? 'No species match your filters.' : ''}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {filtered.slice(0, visibleCount).map(sp => (
              <SpeciesCard key={sp.ebird_species_code || sp.common_name}
                sp={sp} label={displayLabelBySpecies.get(sp.ebird_species_code || sp.common_name)}
                viewMonth={viewMonth}/>
            ))}
          </div>
          {/* Sentinel — revealing this (rootMargin: 400px, so well before it's
              actually visible) loads the next chunk of cards. Invisible, zero
              height, purely a scroll-position trigger. */}
          {visibleCount < filtered.length && (
            // Loads the next chunk on its own as it nears the screen; the
            // button is there in case the observer never fires.
            <button key={visibleCount} ref={sentinelRef} type="button"
                    onClick={() => setVisibleCount(c => Math.min(c + CHUNK, filtered.length))}
                    className="btn-secondary w-full justify-center text-sm py-2.5 mt-2">
              Show more · {filtered.length - visibleCount} more species
            </button>
          )}
        </>
      )}

      {/* Footer */}
      {species.length > 0 && (
        <p className="text-xs text-center mt-6" style={{ color: 'var(--text-tertiary)' }}>
          Frequency data from{' '}
          <a href="https://ebird.org" target="_blank" rel="noopener noreferrer"
             className="hover:underline" style={{ color: 'var(--accent-600)' }}>
            Cornell Lab eBird
          </a>
          {' '}· Bar chart shows Jan→Dec · All year-round species included
        </p>
      )}
    </div>
  )
}
