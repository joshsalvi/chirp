import { useEffect, useState, useMemo, useRef } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { useTz } from '../lib/time'
import { Search, ExternalLink, Award, Calendar, TrendingUp, X, Download, ChevronDown } from 'lucide-react'
import { BirdIcon, BatIcon } from './BirdBatIcons'
import { api } from '../lib/api'

const MONTHS_FULL  = ['January','February','March','April','May','June',
                      'July','August','September','October','November','December']
const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun',
                      'Jul','Aug','Sep','Oct','Nov','Dec']

const SEASONS = [
  { id: 'spring', label: 'Spring', months: [2, 3, 4],  color: '#4ade80' },
  { id: 'summer', label: 'Summer', months: [5, 6, 7],  color: '#facc15' },
  { id: 'autumn', label: 'Autumn', months: [8, 9, 10], color: '#f97316' },
  { id: 'winter', label: 'Winter', months: [11, 0, 1], color: '#60a5fa' },
]

// Top-3 rank badge tints — gold/silver/bronze, subtle enough to sit
// alongside the plain gray used for every other row.
const RANK_TINTS = [
  { background: 'rgba(250,204,21,.18)', color: '#facc15', boxShadow: 'inset 0 0 0 1px rgba(250,204,21,.35)' },
  { background: 'rgba(203,213,225,.18)', color: '#cbd5e1', boxShadow: 'inset 0 0 0 1px rgba(203,213,225,.35)' },
  { background: 'rgba(217,119,6,.18)',  color: '#d97706', boxShadow: 'inset 0 0 0 1px rgba(217,119,6,.35)' },
]

const STATUS_COLORS = {
  'least concern': 'badge-green', 'lc': 'badge-green',
  'near threatened': 'badge-blue', 'nt': 'badge-blue',
  'vulnerable': 'badge-yellow', 'vu': 'badge-yellow',
  'endangered': 'badge-red', 'en': 'badge-red',
  'critically endangered': 'badge-red', 'cr': 'badge-red',
}

function monthInFilter(bird, activeMonths) {
  if (!activeMonths || activeMonths.length === 0) return true

  // Primary: use Chirp's own detection_months — the months this bird was
  // actually detected at your location (0 = Jan, 11 = Dec)
  if (Array.isArray(bird.detection_months) && bird.detection_months.length > 0) {
    return activeMonths.some(m => bird.detection_months.includes(m))
  }

  // Fallback: eBird monthly_frequency (regional estimate, not local detections)
  if (Array.isArray(bird.monthly_frequency) && bird.monthly_frequency.some(v => v > 0)) {
    return activeMonths.some(m => (bird.monthly_frequency[m] ?? 0) > 0)
  }

  // No data at all — exclude from filtered view so we don't show noise
  return false
}

export default function LifeList() {
  const [list, setList] = useState([])
  const { fmtDate } = useTz()
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filterMonth, setFilterMonth]   = useState(null)   // null = all months
  const [filterSeason, setFilterSeason] = useState(null)   // season id or null
  const [sortBy, setSortBy]             = useState('first') // 'count' | 'name' | 'first'
  const [sortDir, setSortDir]           = useState('desc')  // 'asc' | 'desc' — default: most recently seen first
  const [downloadOpen, setDownloadOpen] = useState(false)
  const [exportError, setExportError] = useState(null)
  const downloadRef = useRef(null)
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const currentMonth = new Date().getMonth()

  // Redirect shim for "/library?name=X" — a real, previously-unnoticed bug:
  // this route (bare /library, no :id) always renders LifeList regardless
  // of any query string, since React Router matches on path only. Every
  // place that fell back to "/library?name=X" for a species without a
  // resolved profile_id yet (Dashboard's Seen Today tiles, this page's own
  // row links, RecordingDetail when profileId isn't already known) was
  // silently landing here and showing the generic Life List instead of the
  // intended profile — not an error, just the wrong page, which is exactly
  // why it looked like "clicking does nothing" / "goes to the life list"
  // rather than an obvious crash. Resolving the name here and redirecting
  // to the real /library/:id fixes every current and future caller of that
  // fallback pattern in one place.
  useEffect(() => {
    const name = searchParams.get('name') || searchParams.get('label')
    if (!name) return
    let cancelled = false
    api.birds.byLabel(name)
      .then(profile => {
        if (!cancelled && profile?.id) navigate(`/library/${profile.id}`, { replace: true })
      })
      .catch(() => {}) // stay on the Life List if resolution fails — better than a dead end
    return () => { cancelled = true }
  }, [searchParams, navigate])

  // Close the download dropdown on outside click
  useEffect(() => {
    if (!downloadOpen) return
    const handler = (e) => {
      if (downloadRef.current && !downloadRef.current.contains(e.target)) {
        setDownloadOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [downloadOpen])

  // Handle ?name= and ?label= params
  useEffect(() => {
    const nameParam = searchParams.get('name')
    const labelParam = searchParams.get('label')
    const ebirdParam = searchParams.get('ebird')
    const query = nameParam || labelParam
    if (!query && !ebirdParam) return
    const name = decodeURIComponent(query || '')
    api.birds.list({ search: name || ebirdParam })
      .then(async profiles => {
        const match = profiles.find(p =>
          (name && p.common_name.toLowerCase() === name.toLowerCase()) ||
          (ebirdParam && p.ebird_species_code === ebirdParam)
        )
        if (match?.id) { navigate(`/library/${match.id}`, { replace: true }); return }
        if (name) {
          try {
            const p = await api.birds.ensure(name)
            if (p?.id) navigate(`/library/${p.id}`, { replace: true })
          } catch {}
        }
      })
      .catch(() => {})
  }, [searchParams, navigate])

  useEffect(() => {
    const load = () =>
      api.birds.lifeList().then(setList).catch(() => {}).finally(() => setLoading(false))
    load()
    const t = setTimeout(load, 8000)
    return () => clearTimeout(t)
  }, [])

  // Determine active months from season/month selection
  // Stable top-3-by-detections lookup, independent of `sortBy`/`sortDir` —
  // previously the medal tint just used the current row's display index,
  // so switching to sort-by-name or sort-by-first-seen would tint
  // whichever species happened to land in positions 1-3 for THAT sort,
  // not the species that actually have the most detections. Built from
  // the full `list` (not the filtered/sorted view) so a species keeps
  // its true rank regardless of search/season/month filtering too.
  const detectionRankMap = useMemo(() => {
    const byCount = [...list].sort((a, b) => (b.total_detections || 0) - (a.total_detections || 0))
    const map = new Map()
    byCount.slice(0, 3).forEach((b, i) => map.set(b.common_name, i))
    return map
  }, [list])

  const activeMonths = useMemo(() => {
    if (filterMonth !== null) return [filterMonth]
    if (filterSeason) return SEASONS.find(s => s.id === filterSeason)?.months || []
    return []
  }, [filterMonth, filterSeason])

  const filtered = useMemo(() => {
    const base = list.filter(b => {
      if (search) {
        const q = search.toLowerCase()
        if (!b.common_name.toLowerCase().includes(q) &&
            !(b.scientific_name || '').toLowerCase().includes(q)) return false
      }
      if (!monthInFilter(b, activeMonths)) return false
      return true
    })
    return [...base].sort((a, b) => {
      let cmp = 0
      if (sortBy === 'name') {
        cmp = a.common_name.localeCompare(b.common_name)
      } else if (sortBy === 'first') {
        cmp = (a.first_detected || '').localeCompare(b.first_detected || '')
      } else {
        cmp = (a.total_detections || 0) - (b.total_detections || 0)
      }
      return sortDir === 'desc' ? -cmp : cmp
    })
  }, [list, search, activeMonths, sortBy, sortDir])

  // Same chunked-reveal idiom already proven on RegionalLibrary.jsx (Field
  // Guide) for the identical problem — an established deployment's life
  // list can run into the hundreds of species, and rendering all of them
  // as DOM rows at once (each with a photo, badges, and a Link) was the
  // measured slowness there, not the API call itself. 24 matches the same
  // established page-size vocabulary RegionalLibrary already uses
  // (Recordings' 6/12/24/48 options).
  const CHUNK = 24
  const [visibleCount, setVisibleCount] = useState(CHUNK)
  const sentinelRef = useRef(null)

  // Reset back to the first chunk whenever the result set changes shape —
  // otherwise a stale high visibleCount from a previous broad view would
  // make a newly-narrowed search/filter feel inconsistent with a fresh
  // page load.
  useEffect(() => { setVisibleCount(CHUNK) }, [search, activeMonths, sortBy, sortDir])

  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisibleCount(c => Math.min(c + CHUNK, filtered.length))
        }
      },
      { rootMargin: '400px' }  // start revealing the next chunk well before the sentinel is actually on-screen
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [filtered.length])

  const toggleSort = (key) => {
    if (sortBy === key) setSortDir(d => d === 'desc' ? 'asc' : 'desc')
    else { setSortBy(key); setSortDir(key === 'name' ? 'asc' : 'desc') }
  }

  const clearFilters = () => { setFilterMonth(null); setFilterSeason(null); setSearch('') }
  const hasFilters = search || filterMonth !== null || filterSeason !== null

  return (
    <div className="page-root">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h1 className="section-title">Life List</h1>
          <p className="section-subtitle">
            {filtered.length}{filtered.length !== list.length ? ` of ${list.length}` : ''} species
            {activeMonths.length > 0 && ` · ${
              filterSeason ? SEASONS.find(s=>s.id===filterSeason)?.label :
              MONTHS_FULL[filterMonth]
            }`}
          </p>
        </div>
        <div className="relative flex-shrink-0">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-tertiary)' }}/>
          <input className="input pl-9 w-48 text-sm" placeholder="Search…"
                 value={search} onChange={e => setSearch(e.target.value)}/>
        </div>
      </div>

      {/* Sort controls + eBird export */}
      <div className="flex items-center justify-between gap-2 mb-1 flex-wrap">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs font-semibold uppercase tracking-wider mr-1" style={{ color: 'var(--text-tertiary)' }}>Sort:</span>
          {[
            { key: 'count', label: 'Detections' },
            { key: 'name',  label: 'Name' },
            { key: 'first', label: 'First Seen' },
          ].map(({ key, label }) => (
            <button key={key} onClick={() => toggleSort(key)}
                    className="tactile-press flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-medium transition-all"
                    style={{
                      background: sortBy === key ? 'var(--nav-active-bg)' : 'var(--bg-raised)',
                      color: sortBy === key ? 'var(--accent-400)' : 'var(--text-secondary)',
                      border: `1px solid ${sortBy === key ? 'var(--accent-500)' : 'var(--border-subtle)'}`,
                    }}>
            {label}
            {sortBy === key && <span style={{ fontSize: 10 }}>{sortDir === 'desc' ? ' ↓' : ' ↑'}</span>}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {/* Single Download control with a CSV/JSON format dropdown.
              Previously two separate buttons: a CSV download, and an
              "Upload to eBird" button that opened a dead URL
              (ebird.org/import/upload.do — eBird removed direct deep
              links to the import tool; it's now a multi-step flow behind
              login starting from the eBird homepage's Submit tab, with
              no single page to link straight into). Replaced with a
              format picker — CSV remains the eBird-compatible format,
              with a working link to eBird's real submit page alongside
              it rather than implying any direct-import shortcut still
              exists. JSON is a separate, general-purpose export of the
              same life list, NOT an eBird format — eBird's bulk import
              only accepts CSV. */}
          <div className="relative" ref={downloadRef}>
            <button
              onClick={() => setDownloadOpen(o => !o)}
              className="tactile-press flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
              style={{ background: 'rgba(34,197,94,0.08)', color: 'var(--pastel-green)', border: '1px solid rgba(34,197,94,0.2)' }}
              title="Download your life list">
              <Download size={13}/> Download
              <ChevronDown size={12} style={{ transform: downloadOpen ? 'rotate(180deg)' : 'none', transition: 'transform 150ms ease' }}/>
            </button>
            {downloadOpen && (
              <div className="absolute left-0 sm:left-auto sm:right-0 mt-1.5 rounded-lg overflow-hidden z-20"
                   style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-card-hover)', minWidth: 240, maxWidth: 'calc(100vw - 2rem)' }}>
                <button onClick={async () => {
                    setDownloadOpen(false)
                    setExportError(null)
                    try { await api.birds.exportLifeList('csv') }
                    catch (e) { setExportError(e.message || 'Export failed') }
                  }}
                   className="w-full flex flex-col gap-0.5 px-3 py-2.5 text-left transition-colors hover:bg-[var(--bg-card)]"
                   style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>CSV (eBird format)</span>
                  <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>Import at eBird's Submit page</span>
                </button>
                <button onClick={async () => {
                    setDownloadOpen(false)
                    setExportError(null)
                    try { await api.birds.exportLifeList('json') }
                    catch (e) { setExportError(e.message || 'Export failed') }
                  }}
                   className="w-full flex flex-col gap-0.5 px-3 py-2.5 text-left transition-colors hover:bg-[var(--bg-card)]">
                  <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>JSON</span>
                  <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>For your own use — not an eBird format</span>
                </button>
                <a href="https://ebird.org/submit" target="_blank" rel="noopener noreferrer"
                   onClick={() => setDownloadOpen(false)}
                   className="flex items-center gap-1.5 px-3 py-2.5 text-xs transition-colors hover:bg-[var(--bg-card)]"
                   style={{ color: 'var(--text-secondary)', borderTop: '1px solid var(--border-subtle)' }}>
                  Open eBird Submit page <ExternalLink size={11}/>
                </a>
              </div>
            )}
          </div>
        </div>
        {exportError && (
          <p className="text-xs mt-1.5" style={{ color: '#f87171' }}>
            Export failed: {exportError}
          </p>
        )}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          { icon: Award,     label: 'Species',          value: list.length },
          { icon: TrendingUp,label: 'Total Detections',  value: list.reduce((s,b) => s + b.total_detections, 0).toLocaleString() },
          { icon: Calendar,  label: 'First Detection',   value: list[0]?.first_detected ? fmtDate(list[0].first_detected) : '—' },
        ].map(({ icon: Icon, label, value }) => (
          <div key={label} className="card p-3 flex items-center gap-3">
            <Icon size={16} style={{ color: 'var(--accent-500)', flexShrink: 0 }}/>
            <div>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
              <p className="text-base font-bold" style={{ color: 'var(--accent-400)' }}>{value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Season + month filter */}
      <div className="card p-3 mb-4 space-y-2.5">
        {/* Season pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>Season</span>
          {SEASONS.map(s => (
            <button key={s.id} onClick={() => {
              setFilterSeason(filterSeason === s.id ? null : s.id)
              setFilterMonth(null)
            }}
              className="tactile-press px-2.5 py-1 rounded-lg text-xs font-medium transition-all"
              style={filterSeason === s.id
                ? { background: s.color + '22', color: s.color, border: `1px solid ${s.color}55` }
                : { background: 'var(--bg-raised)', color: 'var(--text-tertiary)', border: '1px solid var(--border-subtle)' }
              }>
              {s.label}
            </button>
          ))}
          {filterSeason && (
            <button className="btn-icon w-6 h-6" style={{ borderRadius: 6 }} onClick={() => setFilterSeason(null)}>
              <X size={10}/>
            </button>
          )}
        </div>

        {/* Month row */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>Month</span>
          <div className="flex gap-px flex-1">
            {MONTHS_SHORT.map((m, i) => {
              const season = SEASONS.find(s => s.months.includes(i))
              const isActive = filterMonth === i
              const isCurrent = i === currentMonth
              return (
                <button key={i} onClick={() => {
                  setFilterMonth(filterMonth === i ? null : i)
                  setFilterSeason(null)
                }}
                  className="tactile-press flex-1 py-1 rounded-sm text-center transition-all"
                  style={{
                    fontSize: 10, fontWeight: isActive ? 700 : 400,
                    background: isActive ? (season?.color + '22' || 'var(--nav-active-bg)') : 'transparent',
                    color: isActive ? (season?.color || 'var(--accent-400)') : isCurrent ? 'var(--accent-500)' : 'var(--text-tertiary)',
                    outline: isActive ? `1px solid ${season?.color || 'var(--border-focus)'}55` : 'none',
                  }}
                  title={MONTHS_FULL[i]}>
                  {m}
                </button>
              )
            })}
          </div>
          {filterMonth !== null && (
            <button className="btn-icon w-6 h-6" style={{ borderRadius: 6 }} onClick={() => setFilterMonth(null)}>
              <X size={10}/>
            </button>
          )}
        </div>

        {hasFilters && (
          <button className="text-xs transition-colors hover:underline" style={{ color: 'var(--text-tertiary)' }}
                  onClick={clearFilters}>
            Clear all filters
          </button>
        )}
      </div>

      {/* List */}
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="card p-4 flex gap-3">
              <div className="w-14 h-14 skeleton rounded-lg flex-shrink-0"/>
              <div className="flex-1 space-y-2 pt-1">
                <div className="skeleton h-3 w-1/3 rounded"/>
                <div className="skeleton h-2 w-1/4 rounded"/>
              </div>
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16">
          <BirdIcon size={36} className="mx-auto mb-3" style={{ color: 'var(--text-tertiary)' }}/>
          <p style={{ color: 'var(--text-secondary)' }}>
            {hasFilters ? 'No species match your filters.' : 'No birds detected yet.'}
          </p>
          {hasFilters && (
            <button className="btn-secondary mt-3 mx-auto" onClick={clearFilters}>Clear filters</button>
          )}
        </div>
      ) : (
        <div className="space-y-1.5">
          {filtered.slice(0, visibleCount).map((bird, index) => {
            const statusKey = (bird.conservation_status || '').toLowerCase()
            const statusBadge = STATUS_COLORS[statusKey]
            // "Bat" is a synthetic pseudo-species (every echolocation detection
            // shares this one generic label) — still used below to pick the
            // right fallback icon, but no longer redirects away from the real
            // profile page; the actual fix is making that page work correctly
            // for bats (recordings tab, photos), not routing around it.
            const isBat = !!bird.is_bat
            const profileTo = bird.profile_id
              ? `/library/${bird.profile_id}`
              : `/library?name=${encodeURIComponent(bird.common_name)}`

            return (
              <Link key={bird.common_name}
                to={profileTo}
                state={{ from: '/library' }}
                className="card-hover flex items-center gap-3 p-3 group">

                {/* Number — top 3 BY ACTUAL DETECTION COUNT get a medal
                    tint, looked up by identity (detectionRankMap) rather
                    than by this row's current display position, so it
                    stays correct across every sort order. The digit
                    itself still shows display position — only the tint
                    is rank-based. */}
                <div className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold"
                     style={RANK_TINTS[detectionRankMap.get(bird.common_name)] ?? { background: 'var(--bg-raised)', color: 'var(--text-tertiary)' }}>
                  {index + 1}
                </div>

                {/* Photo */}
                <div className="w-12 h-12 rounded-lg overflow-hidden flex-shrink-0"
                     style={{ background: 'var(--bg-raised)' }}>
                  {bird.photo_url
                    ? <img src={bird.photo_url} alt={bird.common_name}
                           className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" loading="lazy"/>
                    : <div className="w-full h-full flex items-center justify-center">
                        {isBat
                          ? <BatIcon size={22} style={{ color: 'var(--text-tertiary)' }}/>
                          : <BirdIcon size={22} style={{ color: 'var(--text-tertiary)' }}/>}
                      </div>}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold truncate transition-colors group-hover:text-accent"
                          style={{ color: 'var(--text-primary)' }}>
                      {bird.common_name}
                    </span>
                    {statusBadge && (
                      <span className={`badge ${statusBadge}`}>
                        {bird.conservation_status.toUpperCase()}
                      </span>
                    )}
                  </div>
                  <p className="text-xs italic truncate" style={{ color: 'var(--text-tertiary)' }}>
                    {bird.scientific_name}
                  </p>
                  <div className="flex items-center gap-3 mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    <span className="flex items-center gap-1">
                      <Calendar size={9}/>
                      {bird.first_detected ? fmtDate(bird.first_detected) : '—'}
                    </span>
                    <span>{bird.total_detections} detection{bird.total_detections !== 1 ? 's' : ''}</span>

                  </div>
                </div>

                {/* eBird link — stop propagation so card click goes to profile */}
                {bird.ebird_url && (
                  <a href={bird.ebird_url} target="_blank" rel="noopener noreferrer"
                     onClick={e => { e.preventDefault(); e.stopPropagation(); window.open(bird.ebird_url, '_blank') }}
                     className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg flex-shrink-0 transition-all opacity-0 group-hover:opacity-100"
                     style={{ color: 'var(--accent-600)', border: '1px solid var(--border-subtle)' }}>
                    eBird <ExternalLink size={10}/>
                  </a>
                )}
              </Link>
            )
          })}
          {visibleCount < filtered.length && <div ref={sentinelRef} style={{ height: 1 }}/>}
        </div>
      )}
    </div>
  )
}
