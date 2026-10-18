import React, { useEffect, useState, useRef, useCallback } from 'react'
import { useParams, Link, useSearchParams, useLocation } from 'react-router-dom'
import {
  Play, Pause, ArrowLeft, ExternalLink, RefreshCw,
  Mic, ChevronDown, ChevronUp, ChevronRight, MapPin, Shield, Camera, Info,
  ZoomIn, ZoomOut, RotateCcw, Maximize2, Sparkles, Feather, Compass, Lightbulb,
  TreePine, Bug, Egg, Bird,
  Upload, X, CheckCircle2, AlertTriangle, HelpCircle, Trash2, Radio
, StickyNote, FileAudio, Save , Bell, BellRing } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceArea } from 'recharts'
import { format } from 'date-fns'
import { setCardOpen } from '../lib/cardState'
import { splitLede } from '../lib/textLede'
import BirdSizeRuler from './BirdSizeRuler'
import { AABIcon, MacaulayIcon, INatIcon, BirdLifeIcon, EbirdSTIcon } from './MapSourceIcons'
import { BirdIcon } from './BirdBatIcons'
import { api, mediaUrl } from '../lib/api'
import { useTz } from '../lib/time'
import Comments from './Comments'
import UnifiedCard from './UnifiedCard'
import { cartoDarkUrl } from '../lib/mapTiles'

const MONTHS_SHORT = ['J','F','M','A','M','J','J','A','S','O','N','D']
const MONTHS_FULL = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const SEASONS = [
  { label: 'Winter', months: [11,0,1], color: '#60a5fa' },
  { label: 'Spring', months: [2,3,4], color: '#4ade80' },
  { label: 'Summer', months: [5,6,7], color: '#facc15' },
  { label: 'Autumn', months: [8,9,10], color: '#f97316' },
]

// Section navigation tabs — matching the Settings and Tech Docs pages'
// own left-nav pattern (per direct request). At a Glance and Life
// History stay together in the same tab (Overview) deliberately: an At
// a Glance tile click already scrolls straight to its matching Life
// History section via scrollToLifeHistory() below, which has no
// tab-switching logic of its own — splitting them across tabs would
// silently break that jump (the target would sit in a hidden,
// unmounted tab). Seasonal Presence moved into Overview too, per direct
// request, right after At a Glance rather than at the very bottom.
const PROFILE_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'sounds', label: 'Sounds & Trivia' },
  { id: 'range', label: 'Range & Media' },
  { id: 'yourdata', label: 'Your Data' },
  { id: 'reference', label: 'Reference' },
]

// ── Collapsible card wrapper ────────────────────────────────────────────────
function CollapsibleCard({ id, title, icon, headerRight, children, className = '', fallbackOpen = null }) {
  return (
    <UnifiedCard id={id} title={title} icon={icon} headerRight={headerRight} className={className} fallbackOpen={fallbackOpen} variant="bordered">
      {children}
    </UnifiedCard>
  )
}

// ── Article section (inside About card) ────────────────────────────────────
function Section({ title, text, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  if (!text?.trim()) return null
  return (
    <div className="border-b border-surface-700 last:border-0">
      <button onClick={() => setOpen(o=>!o)}
              className="w-full flex items-center justify-between py-2.5 text-left text-sm font-medium text-gray-300 hover:text-white transition-colors">
        {title}
        {open ? <ChevronUp size={12} className="text-gray-600 flex-shrink-0"/> : <ChevronDown size={12} className="text-gray-600 flex-shrink-0"/>}
      </button>
      {open && <p className="pb-3 text-sm text-gray-400 leading-relaxed whitespace-pre-line">{text}</p>}
    </div>
  )
}

// Clicking a tile in At a Glance jumps to the matching, fuller
// explanation in the Life History card below — direct request. The Life
// History card is a normal CollapsibleCard (its open/closed state lives
// in localStorage via cardState.js, read once at mount by UnifiedCard),
// so a click from outside it can't just call its own setOpen — instead
// this writes the new state to storage and re-uses the existing
// 'chirp-card-default-changed' event UnifiedCard already listens for
// (originally meant for "the global card-open default changed") to make
// the already-mounted instance re-sync and open, without any change to
// UnifiedCard itself. The scroll then waits one paint cycle for that
// open animation/layout to happen before scrolling to a
// section that may have still been display:none in the same tick.
// Ported from chirp-server.
function scrollToLifeHistory(section) {
  setCardOpen('profile:life-history', true)
  window.dispatchEvent(new Event('chirp-card-default-changed'))
  setTimeout(() => {
    const el = document.getElementById(`lifehistory-${section}`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, 80)
}

// ── Conservation badge ──────────────────────────────────────────────────────
function ConsBadge({ status, authority }) {
  if (!status) return null
  const IUCN = { LC:'Least Concern', NT:'Near Threatened', VU:'Vulnerable', EN:'Endangered', CR:'Critically Endangered', EW:'Extinct in Wild', EX:'Extinct' }
  const IUCN_CLR = { LC:'text-chirp-400 bg-chirp-900/30 border-chirp-700/40', NT:'text-yellow-400 bg-yellow-900/30 border-yellow-700/40', VU:'text-orange-400 bg-orange-900/30 border-orange-700/40', EN:'text-red-400 bg-red-900/30 border-red-700/40', CR:'text-red-400 bg-red-900/50 border-red-600/60', EW:'text-purple-400 bg-purple-900/30 border-purple-700/40', EX:'text-gray-400 bg-gray-900/30 border-gray-700/40' }

  // NatureServe global conservation ranks — a distinct rating system
  // from IUCN's, used for many North American species (including several
  // bats) where iNaturalist's own conservation_status data comes from
  // NatureServe rather than the IUCN Red List. The badge previously only
  // knew IUCN's two-letter codes, so any NatureServe rank (which look
  // like "G3", "G4", or a range like "G3G4" when NatureServe itself
  // isn't certain of the exact rank) failed that lookup and silently
  // fell back to showing the same raw code twice (e.g. "G3G4 · G3G4")
  // instead of a translation.
  const NATURESERVE = {
    GX: 'Presumed Extinct', GH: 'Possibly Extinct',
    G1: 'Critically Imperiled', G2: 'Imperiled', G3: 'Vulnerable',
    G4: 'Apparently Secure', G5: 'Secure',
    GU: 'Unrankable', GNR: 'Not Yet Ranked',
  }
  const NATURESERVE_CLR = {
    GX:'text-gray-400 bg-gray-900/30 border-gray-700/40', GH:'text-gray-400 bg-gray-900/30 border-gray-700/40',
    G1:'text-red-400 bg-red-900/50 border-red-600/60', G2:'text-red-400 bg-red-900/30 border-red-700/40',
    G3:'text-orange-400 bg-orange-900/30 border-orange-700/40', G4:'text-yellow-400 bg-yellow-900/30 border-yellow-700/40',
    G5:'text-chirp-400 bg-chirp-900/30 border-chirp-700/40',
    GU:'text-gray-400 bg-surface-700 border-surface-600', GNR:'text-gray-400 bg-surface-700 border-surface-600',
  }

  const isNatureServe = authority && authority.toLowerCase().includes('natureserve')
  let label, colorClass
  if (isNatureServe) {
    // Range ranks like "G3G4" mean NatureServe itself is uncertain between
    // two adjacent ranks — decode each half and join them, rather than
    // treating the whole string as one opaque code.
    const rankCodes = status.match(/G(?:X|H|[1-5]|U|NR)/g) || [status]
    if (rankCodes.length === 2) {
      label = `${NATURESERVE[rankCodes[0]] || rankCodes[0]}–${NATURESERVE[rankCodes[1]] || rankCodes[1]}`
      colorClass = NATURESERVE_CLR[rankCodes[0]] || NATURESERVE_CLR[rankCodes[1]] // the more cautious/lower end, if ranks differ
    } else {
      label = NATURESERVE[status] || status
      colorClass = NATURESERVE_CLR[status]
    }
  } else {
    label = IUCN[status] || status
    colorClass = IUCN_CLR[status]
  }

  return (
    <span className={`text-xs font-bold px-2 py-1 rounded-full border ${colorClass || 'text-gray-400 bg-surface-700 border-surface-600'}`}
          title={isNatureServe ? `NatureServe global conservation rank` : undefined}>
      {status} · {label}{isNatureServe ? ` (${authority || 'NatureServe'})` : ''}
    </span>
  )
}

// ── Seasonal frequency chart ────────────────────────────────────────────────
// Pixel constants — percentage heights inside flex-col children don't reliably
// resolve when the parent height is determined by content (circular reference).
const BAR_H_MAX = 56 // px — max bar height
const LABEL_H = 10 // px — month label height
const CHART_H = BAR_H_MAX + LABEL_H // 66px total column height

function SeasonalChart({ monthly }) {
  if (!monthly || monthly.length < 12) return null
  const allZero = monthly.every(v => v === 0)
  const now = new Date()
  const currentMonth = now.getMonth()
  const max = Math.max(...monthly, 0.001)

  if (allZero) return (
    <div className="px-4 py-8 text-center">
      <p className="text-sm text-gray-500">Seasonal data not yet available</p>
      <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>Click <strong style={{ color: 'var(--text-secondary)' }}>Refresh All Data</strong> to fetch from eBird &amp; iNaturalist</p>
    </div>
  )

  return (
    <div className="space-y-4 px-4 py-4">
      {/* 12-month bar chart — explicit px heights so flex layout resolves correctly */}
      <div>
        <p className="text-xs text-gray-500 mb-2">Monthly frequency (Jan–Dec)</p>
        <div className="flex items-end gap-px" style={{ height: CHART_H }}>
          {monthly.map((v, i) => {
            const barH = Math.max(1, Math.round((v / max) * BAR_H_MAX))
            const isCurrent = i === currentMonth
            const season = SEASONS.find(s => s.months.includes(i))
            return (
              <div key={i} className="flex-1 flex flex-col items-center group relative"
                   style={{ height: CHART_H }}>
                {/* Spacer pushes bar to bottom of column */}
                <div style={{ flex: 1 }} />
                <div
                  className="w-full rounded-sm transition-all"
                  style={{
                    height: barH,
                    flexShrink: 0,
                    background: isCurrent ? '#22c55e' : (season?.color || '#6b7280'),
                    opacity: barH <= 1 ? 0.15 : (isCurrent ? 1 : 0.65),
                  }}
                />
                <span className="text-gray-600 text-center leading-none"
                      style={{ fontSize: 8, height: LABEL_H, display: 'block', paddingTop: 2 }}>
                  {MONTHS_SHORT[i]}
                </span>
                {/* Tooltip — month only, no percentage; matches eBird's own
                    weekly bar chart, which shows relative bar height with
                    no numbers anywhere. Reported directly as confusing —
                    the percentage's baseline (relative to what?) was never
                    obvious at a glance the way a bar's relative height is. */}
                <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block z-10 pointer-events-none">
                  <div className="bg-surface-800 border border-surface-600 rounded px-2 py-1 text-xs text-gray-300 whitespace-nowrap">
                    {MONTHS_FULL[i]}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>eBird checklist frequency · iNaturalist observations · Green bar = current month</p>
    </div>
  )
}

// ── Local presence — this profile's OWN detection history at this location,
// added ALONGSIDE the eBird-sourced chart above, not replacing it — the two
// answer different questions ("what does eBird expect regionally"
// vs. "what has THIS setup heard here"), so both stay visible.
function LocalPresenceTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  return (
    <div className="px-3 py-2 rounded-xl text-xs shadow-2xl"
         style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', minWidth: 100 }}>
      <p className="font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>{point.label}</p>
      <div className="flex items-center gap-1.5">
        <div className="w-2 h-2 rounded-full" style={{ background: '#4ade80' }}/>
        <span style={{ color: 'var(--text-secondary)' }}>Detections:</span>
        <span className="font-bold" style={{ color: 'var(--text-primary)' }}>{point.count}</span>
      </div>
    </div>
  )
}

function LocalPresenceChart({ profileId }) {
  const [data, setData] = useState(null) // null = still loading
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setFailed(false)
    api.birds.presenceHistory(profileId).then(d => {
      if (!cancelled) setData(d)
    }).catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true }
  }, [profileId])

  // Fails quietly rather than showing an error block — this is an
  // additive enhancement layered onto an already-useful card, not core
  // profile data; a fetch hiccup here shouldn't put a red error box on
  // an otherwise-working profile page.
  if (failed) return null

  if (!data) {
    return (
      <div className="px-4 py-4">
        <div className="skeleton rounded-lg" style={{ height: 180 }}/>
      </div>
    )
  }

  if (data.total_detections === 0) {
    return (
      <div className="px-4 py-6 text-center">
        <p className="text-sm text-gray-500">No local detections yet</p>
        <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
          This fills in from your own detections of this species over time.
        </p>
      </div>
    )
  }

  // Season bands, computed from the SAME SEASONS colors/labels the eBird
  // chart above already uses (module-level constant, not redefined here)
  // — reads each week's own `month` field rather than hardcoding week
  // ranges separately, so Winter (which wraps the year boundary: Dec +
  // Jan/Feb) naturally produces two separate bands from this loop
  // without needing wrap-around special-casing.
  const bands = []
  for (const season of SEASONS) {
    let runStart = null
    for (let i = 0; i <= data.weekly.length; i++) {
      const inSeason = i < data.weekly.length && season.months.includes(data.weekly[i].month)
      if (inSeason && runStart === null) runStart = i
      if (!inSeason && runStart !== null) {
        bands.push({ x1: data.weekly[runStart].week, x2: data.weekly[i - 1].week, ...season })
        runStart = null
      }
    }
  }

  const tickWeeks = [1, 9, 18, 27, 35, 44, 52]

  return (
    <div className="space-y-3 px-4 py-4">
      <div>
        <p className="text-xs text-gray-500 mb-2">Your detections at this location, by week (all years combined)</p>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data.weekly} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            {bands.map((b, i) => (
              <ReferenceArea key={i} x1={b.x1} x2={b.x2} fill={b.color} fillOpacity={0.12} strokeOpacity={0}/>
            ))}
            <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3" vertical={false}/>
            <XAxis dataKey="week" type="number" domain={[1, 52]} ticks={tickWeeks}
                   tickFormatter={w => data.weekly[w - 1]?.label || w}
                   tick={{ fill: 'var(--text-tertiary)', fontSize: 9 }} axisLine={false} tickLine={false}/>
            <YAxis allowDecimals={false} tick={{ fill: 'var(--text-tertiary)', fontSize: 10 }} axisLine={false} tickLine={false} width={28}/>
            <Tooltip content={<LocalPresenceTooltip/>}/>
            <Line type="monotone" dataKey="count" name="Detections" stroke="#4ade80" strokeWidth={2} dot={false} activeDot={{ r: 4 }}/>
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {SEASONS.map(s => (
          <div key={s.label} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm" style={{ background: s.color, opacity: 0.5 }}/>
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{s.label}</span>
          </div>
        ))}
      </div>

      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        {data.total_detections.toLocaleString()} detection{data.total_detections !== 1 ? 's' : ''}
        {data.peak_week && <> · busiest around {data.peak_week.label}</>}
        {data.years_covered.length > 0 && <> · {data.years_covered.join(', ')}</>}
      </p>
    </div>
  )
}

// ── Zoomable/pannable range map ────────────────────────────────────────────
function EbirdRangeMap({ profileId, speciesCode, commonName, rangeMapUrl, rangeMapSource, enabledSources, sourceOrder, onProfileUpdate }) {
  const ebirdUrl = speciesCode
    ? `https://science.ebird.org/en/status-and-trends/species/${speciesCode}/abundance-map`
    : `https://ebird.org/species/${speciesCode || ''}`

  const [mapError, setMapError] = useState(false)
  const [aabLoading, setAabLoading] = useState(false)
  const [macaulayLoading, setMacaulayLoading] = useState(false)
  const [parsedLegend, setParsedLegend] = useState(null)
  const [aspectRatio, setAspectRatio] = useState('2 / 1')
  const [mapSource, setMapSource] = useState('auto') // 'auto'|'wikipedia'|'ebird_st'|'gbif'
  // 'aab' | 'macaulay' | 'geomodel' | 'birdlife'
  const [mapView, setMapView] = useState('aab')

  const [aabRefresh, setAabRefresh] = useState(0)
  const [macaulayRefresh, setMacaulayRefresh] = useState(0)
  // source param tracks whichever of the AAB-family tabs (aab/macaulay)
  // is active, rather than always asking the backend for "aab"
  // regardless of mapView — previously hardcoded, which meant the
  // Macaulay tab would have silently requested the AAB-specific source
  // and refresh path instead of its own.
  const localMapSrc = profileId
    ? mediaUrl(`/api/v1/birds/${profileId}/range-map?v=${encodeURIComponent(rangeMapUrl || 'none')}&source=${mapView === 'macaulay' ? 'macaulay' : 'aab'}`
      + (mapView === 'aab' && aabRefresh > 0 ? '&refresh=true&t=' + aabRefresh : '')
      + (mapView === 'macaulay' && macaulayRefresh > 0 ? '&refresh=true&t=' + macaulayRefresh : ''))
    : null

  // Auto-switch if the current view's source gets disabled
  useEffect(() => {
    if (!enabledSources) return
    if (enabledSources[mapView] === false) {
      const first = ['aab', 'macaulay', 'geomodel', 'birdlife'].find(s => enabledSources[s] !== false)
      if (first) setMapView(first)
    }
  }, [enabledSources, mapView])
  const [geomodelError, setGeomodelError] = useState(false)
  const [geomodelLoading, setGeomodelLoading] = useState(false)
  const [birdlifeError, setBirdlifeError] = useState(false)
  const [birdlifeLoading, setBirdlifeLoading] = useState(false)
  const [ebirdStError, setEbirdStError] = useState(false)
  const [ebirdStLoading, setEbirdStLoading] = useState(false)
  const [geomodelRefresh, setGeomodelRefresh] = useState(0)
  const geomodelSrc = profileId
    ? mediaUrl(`/api/v1/birds/${profileId}/range-map/geomodel`
      + (geomodelRefresh > 0 ? '?refresh=true&t=' + geomodelRefresh : ''))
    : null
  const [birdlifeRefresh, setBirdlifeRefresh] = useState(0)
  const birdlifeSrc = profileId ? mediaUrl(`/api/v1/birds/${profileId}/range-map/birdlife${birdlifeRefresh > 0 ? '?refresh=true&t=' + birdlifeRefresh : ''}`) : null
  // eBird S&T now has its own dedicated endpoint and cached file, same
  // pattern as geomodel/birdlife immediately above — it used to share
  // profile.range_map_url/range_map_source with AAB/Macaulay/Wikipedia,
  // which meant visiting ANY of those other three tabs afterward silently
  // overwrote S&T's own successful result back to "unavailable", even
  // though its PNG was still cached on disk untouched. Reported directly
  // as "S&T shows nothing, even after refreshing" — root-caused by reading
  // every write site for that shared field before touching this file.
  const [ebirdStRefresh, setEbirdStRefresh] = useState(0)
  const ebirdStSrc = profileId
    ? mediaUrl(`/api/v1/birds/${profileId}/range-map/ebird_st`
      + (ebirdStRefresh > 0 ? '?refresh=true&t=' + ebirdStRefresh : ''))
    : null
  const geomodelView = mapView === 'geomodel'
  const [mapFetching, setMapFetching] = useState(false)
  const [mapFetchError, setMapFetchError] = useState(null)

  // Zoom/pan state
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const dragStart = useRef(null)
  const containerRef = useRef(null)

  useEffect(() => { setMapError(false); setMapFetchError(null) }, [localMapSrc])

  const SOURCE_LABELS = {
    auto: 'Auto', wikipedia: 'Wikipedia SVG', ebird_st: 'eBird S&T', gbif: 'GBIF',
  }
  // Use the DB-stored source if available, otherwise infer from URL pattern
  const ACTIVE_SOURCE = rangeMapSource || (
    rangeMapUrl?.startsWith('file://') ? (
      rangeMapUrl.includes('_ebird_st') ? 'ebird_st'
      : rangeMapUrl.includes('_gbif') ? 'gbif'
      : 'wikipedia'
    ) : (rangeMapUrl ? 'wikipedia' : null)
  )

  const handleReset = async () => {
    if (!profileId) return
    setMapFetching(true)
    setMapFetchError(null)
    try {
      await api.birds.resetRangeMap(profileId)
      // Poll until range_map_source is null / wikipedia
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 2000))
        const status = await api.birds.rangeMapStatus(profileId)
        if (!status.range_map_source || status.range_map_source === 'wikipedia') {
          const updated = await api.birds.get(profileId)
          if (onProfileUpdate) onProfileUpdate(updated)
          setMapSource('auto')
          return
        }
      }
    } catch (e) {
      setMapFetchError('Reset failed')
    } finally {
      setMapFetching(false)
    }
  }

  const handleFetchSource = async (src, force = false) => {
    // Only gbif still routes through here — ebird_st has its own dedicated
    // endpoint now (see ebirdStSrc's own comment above). Kept for gbif in
    // case a future UI surfaces it as a selectable tab; currently unreachable
    // from any button in this file since gbif has no tab of its own.
    if (!profileId || src === 'auto' || src === 'wikipedia') return
    if (src === ACTIVE_SOURCE && !force) return
    setMapFetching(true)
    setMapFetchError(null)
    try {
      const result = await api.birds.fetchRangeMap(profileId, src, force)
      if (result?.status === 'cached') {
        // Backend already had a fresh file for this source and pointed
        // the profile at it synchronously — no background work was
        // queued, so there's nothing to poll for. Reload immediately
        // instead of waiting through the 2s poll interval for no reason.
        const updated = await api.birds.get(profileId)
        if (onProfileUpdate) onProfileUpdate(updated)
        setMapSource('auto')
        return
      }
      // Poll the lightweight status endpoint (avoids full profile re-fetch)
      let prevUrl = rangeMapUrl
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 2000))
        const status = await api.birds.rangeMapStatus(profileId)
        if (
          status.range_map_source === src ||
          (status.range_map_url && status.range_map_url !== prevUrl)
        ) {
          // Reload the full profile so the new map URL flows down as a prop
          const updated = await api.birds.get(profileId)
          if (onProfileUpdate) onProfileUpdate(updated)
          setMapSource('auto')
          return
        }
      }
      setMapFetchError('Timed out — check server logs for errors')
    } catch (e) {
      setMapFetchError((e?.message || String(e)).replace('API 400:', '').replace('API 500:', 'Server error:').trim())
    } finally {
      setMapFetching(false)
    }
  }

  useEffect(() => {
    if (!profileId) return
    // ebird_st and gbif have their own correct local legend (RGB-matched
    // discrete swatches for ebird_st, a GBIF classic-style gradient for
    // gbif — see the LEGENDS table below) and never read parsedLegend, so
    // there's no reason to hit the backend legend endpoint for them at all.
    if (mapView === 'ebird_st' || mapView === 'gbif') { setParsedLegend(null); return }
    // Request the legend scoped to whichever map tab is active. The backend
    // returns the per-species legend for birdlife/aab (extracted at
    // enrichment/fetch time from that species' own page — not a fixed
    // global swatch list), falling back to Wikipedia SVG parsing otherwise.
    const src = mapView === 'birdlife' ? 'birdlife' : mapView === 'aab' ? 'aab' : mapView === 'macaulay' ? 'macaulay' : 'wikipedia'
    fetch(mediaUrl(`/api/v1/birds/${profileId}/range-map-legend?source=${src}`))
      .then(r => r.json())
      .then(data => {
        if (data.legend?.length > 0 && data.legend.some(e => e.label)
            && data.source !== 'none' && data.source !== 'error') {
          setParsedLegend(data.legend)
        } else {
          // No per-species legend available for this source/species —
          // clear any stale legend from a previously-viewed tab so the
          // fallback static list (rather than a wrong cached one) is used.
          setParsedLegend(null)
        }
        if (data.aspect_ratio && data.aspect_ratio !== 'auto') {
          setAspectRatio(data.aspect_ratio)
        }
      })
      .catch(() => setParsedLegend(null))
  }, [profileId, rangeMapUrl, mapView])

  const handleMouseDown = useCallback(e => {
    if (zoom <= 1) return
    setDragging(true)
    dragStart.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }
    e.preventDefault()
  }, [zoom, pan])

  const handleMouseMove = useCallback(e => {
    if (!dragging || !dragStart.current) return
    setPan({ x: e.clientX - dragStart.current.x, y: e.clientY - dragStart.current.y })
  }, [dragging])

  const handleMouseUp = useCallback(() => { setDragging(false) }, [])

  const handleWheel = useCallback(e => {
    e.preventDefault()
    setZoom(z => Math.min(4, Math.max(1, z * (e.deltaY < 0 ? 1.15 : 0.87))))
  }, [])

  // Two-finger touch: pan via the midpoint of the two touches, pinch via the
  // distance between them. Deliberately not single-finger — one finger needs
  // to keep scrolling the page normally on mobile, the same way it would
  // over any other image; only a second finger signals "interact with the
  // map," matching the desktop pattern where panning only activates once
  // already zoomed in (click-drag), not on every touch.
  const touchStart = useRef(null) // { midX, midY, dist, panX, panY, zoom }

  const touchMidAndDist = (touches) => {
    const [t0, t1] = [touches[0], touches[1]]
    return {
      midX: (t0.clientX + t1.clientX) / 2,
      midY: (t0.clientY + t1.clientY) / 2,
      dist: Math.hypot(t1.clientX - t0.clientX, t1.clientY - t0.clientY),
    }
  }

  const handleTouchStart = useCallback(e => {
    if (e.touches.length !== 2) return
    const { midX, midY, dist } = touchMidAndDist(e.touches)
    touchStart.current = { midX, midY, dist, panX: pan.x, panY: pan.y, zoom }
    e.preventDefault()
  }, [pan, zoom])

  const handleTouchMove = useCallback(e => {
    if (e.touches.length !== 2 || !touchStart.current) return
    e.preventDefault()
    const { midX, midY, dist } = touchMidAndDist(e.touches)
    const s = touchStart.current

    // Pinch → zoom, same [1,4] clamp the wheel handler uses.
    if (s.dist > 0) {
      const newZoom = Math.min(4, Math.max(1, s.zoom * (dist / s.dist)))
      setZoom(newZoom)
    }
    // Two-finger drag → pan, only meaningful once zoomed in (matches the
    // existing zoom > 1 gate on mouse-drag panning).
    if (s.zoom > 1 || zoom > 1) {
      setPan({ x: s.panX + (midX - s.midX), y: s.panY + (midY - s.midY) })
    }
  }, [zoom])

  const handleTouchEnd = useCallback(e => {
    if (e.touches.length < 2) touchStart.current = null
  }, [])

  const resetView = () => { setZoom(1); setPan({ x: 0, y: 0 }) }

  return (
    <CollapsibleCard
      id="profile:range-map"
      fallbackOpen={true}
      title="Seasonal Range Map"
      icon={MapPin}
      headerRight={
        <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
          {speciesCode && (
            <a href={ebirdUrl} target="_blank" rel="noopener noreferrer"
               className="text-xs text-gray-500 hover:text-chirp-400 flex items-center gap-1">
              eBird <ExternalLink size={10}/>
            </a>
          )}
        </div>
      }
    >
      {profileId ? (
        <>
          {/* Map container: overflow:hidden clips any remaining blank edges.
               The server-side SVG endpoint already crops the top 22% of world maps
               so the viewBox starts where North American ranges begin. */}
          <div
            ref={containerRef}
            className="bg-white relative select-none"
            style={{
              overflow: 'hidden',
              maxHeight: 480,
              cursor: zoom > 1 ? (dragging ? 'grabbing' : 'grab') : 'default',
              // Permanently 'none', not toggled dynamically — touch-action is
              // evaluated by the browser at the moment a touch begins, not
              // reactively mid-gesture, so a value that only flips to 'none'
              // once two fingers are already down would not reliably
              // intercept the first pinch attempt in every browser (this is
              // a documented, unresolved ambiguity in the touch-action spec
              // itself for "let 1 finger scroll, let JS own 2 fingers" —
              // see W3C pointerevents issue #159). Claiming touch gestures
              // permanently on this one contained map widget, rather than
              // the whole page, is the standard pattern other interactive
              // map/canvas components use for exactly this reason.
              touchAction: 'none',
            }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onWheel={handleWheel}
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
          >
            {(() => {
              const currentTabHasError =
                (mapView === 'aab' && mapError) ||
                (mapView === 'macaulay' && mapError) ||
                (mapView === 'geomodel' && geomodelError) ||
                (mapView === 'birdlife' && birdlifeError) ||
                (mapView === 'ebird_st' && ebirdStError)
              if (currentTabHasError) return null
              const activeSrc = mapView === 'geomodel' ? geomodelSrc
                : mapView === 'birdlife' ? birdlifeSrc
                : mapView === 'ebird_st' ? ebirdStSrc
                : localMapSrc
              const currentTabIsLoading =
                (mapView === 'aab' && aabLoading) ||
                (mapView === 'macaulay' && macaulayLoading) ||
                (mapView === 'geomodel' && geomodelLoading) ||
                (mapView === 'birdlife' && birdlifeLoading) ||
                (mapView === 'ebird_st' && ebirdStLoading)
              return (
                <>
                  <img
                    key={activeSrc}
                    src={activeSrc}
                    alt={`${commonName} range map`}
                    draggable={false}
                    style={{
                      display: 'block',
                      width: '100%',
                      height: 'auto',
                      maxHeight: 480,
                      objectFit: 'contain',
                      opacity: currentTabIsLoading ? 0.4 : 1,
                      transition: dragging ? 'opacity 0.2s ease' : 'opacity 0.2s ease, transform 0.1s ease',
                      transform: `scale(${zoom}) translate(${pan.x/zoom}px, ${pan.y/zoom}px)`,
                      transformOrigin: 'center top',
                    }}
                    onLoad={() => {
                      if (mapView === 'birdlife') setBirdlifeLoading(false)
                      else if (mapView === 'aab') setAabLoading(false)
                      else if (mapView === 'macaulay') setMacaulayLoading(false)
                      else if (mapView === 'geomodel') setGeomodelLoading(false)
                      else if (mapView === 'ebird_st') { setEbirdStError(false); setEbirdStLoading(false) }
                    }}
                    onError={() => {
                      if (mapView === 'geomodel') { setGeomodelError(true); setGeomodelLoading(false) }
                      else if (mapView === 'birdlife') { setBirdlifeError(true); setBirdlifeLoading(false) }
                      else if (mapView === 'ebird_st') { setEbirdStError(true); setEbirdStLoading(false) }
                      else if (mapView === 'macaulay') { setMapError(true); setMacaulayLoading(false) }
                      else { setMapError(true); setAabLoading(false) }
                    }}
                  />
                  {currentTabIsLoading && (
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none"
                         style={{ background: 'rgba(0,0,0,0.15)' }}>
                      <div className="flex items-center gap-2 px-3 py-2 rounded-lg"
                           style={{ background: 'rgba(0,0,0,0.7)' }}>
                        <RefreshCw size={14} className="animate-spin text-white"/>
                        <span className="text-xs text-white font-medium">Refreshing map…</span>
                      </div>
                    </div>
                  )}
                </>
              )
            })()}
            {/* Per-tab unavailable state — shown INSIDE the tabbed view so
                switching to a different source (e.g. iNat or BirdLife after
                AAB fails) always stays possible. Previously AAB's error
                collapsed the entire section including the tab bar itself,
                which meant a person stuck on a broken AAB map had no way to
                even see that iNat/BirdLife were independent options. */}
            {mapView === 'aab' && mapError && (
              <div className="flex flex-col items-center justify-center gap-2 py-10 px-5 text-center"
                   style={{ minHeight: 200 }}>
                <MapPin size={22} className="text-gray-700"/>
                <p className="text-sm text-gray-500">AAB map not available for this species</p>
                <p className="text-xs text-gray-600">
                  Try the <strong style={{ color: 'var(--text-secondary)' }}>iNat</strong> or <strong style={{ color: 'var(--text-secondary)' }}>BirdLife</strong> tab above,
                  or click <strong className="text-gray-400">Refresh All Data</strong> to fetch from Cornell Lab.
                </p>
                {speciesCode && (
                  <a href={ebirdUrl} target="_blank" rel="noopener noreferrer"
                     className="text-xs text-chirp-500 hover:text-chirp-400 flex items-center gap-1 mt-1">
                    <ExternalLink size={11}/> View on eBird S&amp;T →
                  </a>
                )}
              </div>
            )}

            {mapView === 'macaulay' && mapError && (
              <div className="flex flex-col items-center justify-center gap-2 py-10 px-5 text-center"
                   style={{ minHeight: 200 }}>
                <MapPin size={22} className="text-gray-700"/>
                <p className="text-sm text-gray-500">Macaulay Library map not available for this species</p>
                <p className="text-xs text-gray-600">
                  {speciesCode
                    ? <>Click the refresh icon above to try the Cornell CDN again, or try the
                        {' '}<strong style={{ color: 'var(--text-secondary)' }}>iNat</strong> or
                        {' '}<strong style={{ color: 'var(--text-secondary)' }}>BirdLife</strong> tab.</>
                    : <>Needs an eBird species code on file — click <strong className="text-gray-400">Refresh All Data</strong> first.</>}
                </p>
              </div>
            )}

            {/* geomodel/birdlife/ebird_st unavailable states — same fix,
                same reason, as the AAB/Macaulay blocks immediately above:
                these three previously only had a small absolutely-positioned
                <p> tucked inside the tab-selector's own `absolute` wrapper.
                Absolutely-positioned elements contribute zero height to
                their parent, so when the <img> above also returns null
                (currentTabHasError), the whole map container collapsed to
                0px and its own overflow:hidden clipped everything inside
                it out of view — including the tab row itself, not just the
                error text. Reported directly, from screenshots showing only
                the card header and the static legend footer with nothing
                in between for iNat/BirdLife/S&T specifically, while AAB/
                Macaulay (which already had this real-height block) still
                showed their tab row fine. Giving these three the same
                normal-flow, minHeight:200 treatment fixes all three at
                once; the small corner text for each is removed as
                redundant now that this bigger, clearer message covers it. */}
            {mapView === 'geomodel' && geomodelError && (
              <div className="flex flex-col items-center justify-center gap-2 py-10 px-5 text-center"
                   style={{ minHeight: 200 }}>
                <MapPin size={22} className="text-gray-700"/>
                <p className="text-sm text-gray-500">iNat model unavailable for this species</p>
                <p className="text-xs text-gray-600">
                  Ensure geopackages are downloaded in <strong style={{ color: 'var(--text-secondary)' }}>Settings → Range Maps</strong>,
                  and that this species has an iNat taxon ID.
                </p>
              </div>
            )}

            {mapView === 'birdlife' && birdlifeError && (
              <div className="flex flex-col items-center justify-center gap-2 py-10 px-5 text-center"
                   style={{ minHeight: 200 }}>
                <MapPin size={22} className="text-gray-700"/>
                <p className="text-sm text-gray-500">BirdLife map not available for this species</p>
                <p className="text-xs text-gray-600">
                  Playwright may need setup, or click the refresh icon above to try again.
                </p>
              </div>
            )}

            {mapView === 'ebird_st' && !ebirdStLoading && ebirdStError && (
              <div className="flex flex-col items-center justify-center gap-2 py-10 px-5 text-center"
                   style={{ minHeight: 200 }}>
                <MapPin size={22} className="text-gray-700"/>
                <p className="text-sm text-gray-500">eBird S&T unavailable for this species</p>
                <p className="text-xs text-gray-600">
                  Requires an S&amp;T key in Settings → Range Maps (get one free at ebird.org/st/request),
                  and an eBird species code on file — click <strong className="text-gray-400">Refresh All Data</strong> if missing.
                </p>
              </div>
            )}

            {/* Map source selector */}
            <div className="absolute top-2 left-2 z-10 flex flex-col gap-1">
              <div className="flex gap-1">
                {(() => {
                  const TAB_DEFS = {
                    aab: { id: 'aab', Icon: AABIcon, text: 'AAB', title: 'All About Birds / eBird' },
                    macaulay: { id: 'macaulay', Icon: MacaulayIcon, text: 'Macaulay',title: 'Macaulay Library (Cornell CDN)' },
                    geomodel: { id: 'geomodel', Icon: INatIcon, text: 'iNat', title: 'iNaturalist Geomodel' },
                    birdlife: { id: 'birdlife', Icon: BirdLifeIcon, text: 'BirdLife',title: 'BirdLife International' },
                    ebird_st: { id: 'ebird_st', Icon: EbirdSTIcon, text: 'S&T', title: 'eBird Status & Trends (testing)' },
                  }
                  // Sort by the user's configured order (Settings → Map
                  // Sources, drag-and-drop); any tab id not present in
                  // sourceOrder (e.g. a newly-added source on an older
                  // saved order) falls back to the end in its original
                  // position, so it's never silently hidden.
                  const order = sourceOrder?.length ? sourceOrder : Object.keys(TAB_DEFS)
                  const ordered = [
                    ...order.filter(id => TAB_DEFS[id]).map(id => TAB_DEFS[id]),
                    ...Object.keys(TAB_DEFS).filter(id => !order.includes(id)).map(id => TAB_DEFS[id]),
                  ]
                  return ordered
                })()
                .filter(({ id }) => (enabledSources ?? {})[id] !== false)
                .map(({ id, Icon, text, title }) => (
                  <button key={id}
                    onClick={e => {
                      e.stopPropagation()
                      setMapView(id)
                      if (id === 'geomodel') { setGeomodelError(false); setGeomodelLoading(true) }
                      if (id === 'birdlife') { setBirdlifeError(false); setBirdlifeLoading(true) }
                      if (id === 'aab') { setMapError(false); setAabLoading(true) }
                      if (id === 'macaulay') { setMapError(false); setMacaulayLoading(true) }
                      if (id === 'ebird_st') { setEbirdStError(false); setEbirdStLoading(true) }
                    }}
                    title={title}
                    className="px-2 py-0.5 rounded text-xs font-medium transition-colors flex items-center gap-1"
                    style={{
                      background: mapView === id ? 'rgba(34,197,94,0.3)' : 'rgba(0,0,0,0.55)',
                      color: mapView === id ? '#4ade80' : '#9ca3af',
                      border: `1px solid ${mapView === id ? 'rgba(34,197,94,0.5)' : 'rgba(255,255,255,0.1)'}`,
                    }}>
                    <Icon size={12} className="flex-shrink-0"/>
                    {text}
                  </button>
                ))}
              </div>
              {mapView === 'geomodel' && (
                <button
                  onClick={e => { e.stopPropagation(); setGeomodelError(false); setGeomodelLoading(true); setGeomodelRefresh(Date.now()) }}
                  className="tactile-press text-xs px-1.5 py-0.5 rounded bg-black/50 text-gray-400 hover:text-white"
                  title="Re-render from iNaturalist geomodel (clears cache)">
                  ↻
                </button>
              )}
              {mapView === 'birdlife' && (
                <button
                  onClick={e => { e.stopPropagation(); setBirdlifeError(false); setBirdlifeLoading(true); setBirdlifeRefresh(Date.now()) }}
                  className="tactile-press text-xs px-1.5 py-0.5 rounded bg-black/50 text-gray-400 hover:text-white"
                  title="Re-capture from BirdLife (clears cache)">
                  ↻
                </button>
              )}
              {mapView === 'aab' && (
                <button
                  onClick={e => { e.stopPropagation(); setMapError(false); setAabLoading(true); setAabRefresh(Date.now()) }}
                  className="tactile-press text-xs px-1.5 py-0.5 rounded bg-black/50 text-gray-400 hover:text-white"
                  title="Re-capture from All About Birds (clears cache)">
                  ↻
                </button>
              )}
              {mapView === 'macaulay' && (
                <button
                  onClick={e => { e.stopPropagation(); setMapError(false); setMacaulayLoading(true); setMacaulayRefresh(Date.now()) }}
                  className="tactile-press text-xs px-1.5 py-0.5 rounded bg-black/50 text-gray-400 hover:text-white"
                  title="Re-fetch from Macaulay Library / Cornell CDN (clears cache)">
                  ↻
                </button>
              )}
              {/* eBird S&T's status/refresh block — same simple pattern as
                  geomodel/birdlife immediately above now that it has its
                  own dedicated endpoint (see ebirdStSrc's own comment). */}
              {mapView === 'ebird_st' && ebirdStLoading && (
                <p className="text-xs px-2 py-1 rounded bg-black/70 text-blue-300 max-w-52 flex items-center gap-1.5">
                  <RefreshCw size={11} className="animate-spin flex-shrink-0"/>
                  Fetching seasonal abundance data from eBird S&amp;T…
                </p>
              )}
              {mapView === 'ebird_st' && (
                <button
                  onClick={e => { e.stopPropagation(); setEbirdStError(false); setEbirdStLoading(true); setEbirdStRefresh(Date.now()) }}
                  className="tactile-press text-xs px-1.5 py-0.5 rounded bg-black/50 text-gray-400 hover:text-white"
                  title="Re-fetch from eBird Status & Trends (clears cache)">
                  ↻
                </button>
              )}
            </div>

            {/* Zoom controls */}
            <div className="absolute top-2 right-2 flex flex-col gap-1 z-10">
              <button onClick={e => { e.stopPropagation(); setZoom(z => Math.min(4, z * 1.3)) }}
                className="tactile-press w-7 h-7 bg-black/50 hover:bg-black/70 text-white rounded flex items-center justify-center transition-colors">
                <ZoomIn size={13}/>
              </button>
              <button onClick={e => { e.stopPropagation(); setZoom(z => Math.max(1, z * 0.77)) }}
                className="tactile-press w-7 h-7 bg-black/50 hover:bg-black/70 text-white rounded flex items-center justify-center transition-colors">
                <ZoomOut size={13}/>
              </button>
              {zoom > 1.05 && (
                <button onClick={e => { e.stopPropagation(); resetView() }}
                  className="tactile-press w-7 h-7 bg-black/50 hover:bg-black/70 text-white rounded flex items-center justify-center transition-colors">
                  <RotateCcw size={13}/>
                </button>
              )}
            </div>
            {zoom > 1 && (
              <div className="absolute bottom-2 left-2 text-xs text-white bg-black/50 px-2 py-0.5 rounded z-10">
                {Math.round(zoom * 100)}% · drag to pan · scroll to zoom
              </div>
            )}
          </div>

          {/* Legend + footer — source-specific */}
          <div className="px-4 py-3 border-t border-surface-700 bg-surface-950">
            {(() => {
              // Each source has its own legend. Both aab and birdlife prefer
              // the per-species legend (parsedLegend, fetched scoped to
              // the active mapView above) when one was successfully
              // extracted; the hardcoded lists below are only a fallback
              // for when extraction didn't find anything for that species
              // (rather than every species being forced through one fixed
              // global swatch list regardless of what its map shows).
              const LEGENDS = {
                aab: parsedLegend?.filter(e => e.label)?.length > 0
                  ? parsedLegend.filter(e => e.label)
                  : [
                    { color: 'rgb(239,68,68)', label: 'Breeding' },
                    { color: 'rgb(59,130,246)', label: 'Non-breeding' },
                    { color: 'rgb(147,51,234)', label: 'Year-round' },
                    { color: 'rgb(250,204,21)', label: 'Migration' },
                  ],
                geomodel: [
                    { color: 'rgb(74,222,128)', label: 'Estimated range' },
                ],
                birdlife: parsedLegend?.filter(e => e.label)?.length > 0
                  ? parsedLegend.filter(e => e.label)
                  : [
                    { color: 'rgb(56,168,0)', label: 'Resident' },
                    { color: 'rgb(255,255,0)', label: 'Breeding' },
                    { color: 'rgb(0,112,255)', label: 'Non-breeding' },
                    { color: 'rgb(0,69,0)', label: 'Re-introduced' },
                    { color: 'rgb(230,152,0)', label: 'Introduced' },
                    { color: 'rgb(0,230,169)', label: 'Passage' },
                    { color: 'rgb(190,210,255)', label: 'Possibly extant' },
                ],
                // Exact same RGB values as SEASON_COLOURS in
                // range_map_service.py (alpha dropped — this is a flat
                // swatch, not a composited raster) so the legend genuinely
                // matches what gets rendered rather than being a guess.
                ebird_st: [
                    { color: 'rgb(255,140,30)', label: 'Breeding' },
                    { color: 'rgb(0,130,255)', label: 'Non-breeding' },
                    { color: 'rgb(255,220,0)', label: 'Migration' },
                    { color: 'rgb(102,0,200)', label: 'Resident' },
                ],
                // GBIF is an occurrence-density hexbin heatmap (classic.poly
                // style — see fetch_gbif_map), not a discrete categorical map
                // like AAB/BirdLife/S&T. A swatch legend with season labels
                // would misrepresent what's rendered, so this is a
                // gradient legend instead, in the same light→dark direction
                // GBIF's own occurrence tiles use for low→high density.
                gbif: 'gradient',
              }
              const items = LEGENDS[mapView]
              if (!items) return null
              if (items === 'gradient') {
                // GBIF's "classic" style is documented as a yellow→red
                // ramp (https://api.gbif.org/v2/map/styles.html) — these are
                // GBIF's own published ramp colors, not an invented generic
                // gradient, so the legend accurately reflects what the tiles
                // use.
                return (
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Fewer records</span>
                    <div className="w-24 h-2.5 rounded-full flex-shrink-0"
                         style={{ background: 'linear-gradient(to right, #ffffb2, #fd8d3c, #bd0026)',
                                  outline: '1px solid rgba(0,0,0,0.15)' }}/>
                    <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>More records</span>
                  </div>
                )
              }
              return (
                <div className="flex flex-wrap gap-x-4 gap-y-1.5 mb-2">
                  {items.map(({ color, label }) => (
                    <div key={label} className="flex items-center gap-1.5">
                      <div className="w-3 h-3 rounded-sm flex-shrink-0"
                           style={{ background: color, outline: '1px solid rgba(0,0,0,0.15)' }}/>
                      <span className="text-xs text-gray-400">{label}</span>
                    </div>
                  ))}
                </div>
              )
            })()}
            <div className="flex items-center justify-between">
              {mapView === 'aab' && <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>© Cornell Lab · iNaturalist · NatureServe</p>}
              {mapView === 'macaulay' && <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>© Macaulay Library · Cornell Lab of Ornithology</p>}
              {mapView === 'geomodel' && <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>© iNaturalist · Geomodel predictions</p>}
              {mapView === 'birdlife' && <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>© BirdLife International · IUCN Red List</p>}
              {mapView === 'ebird_st' && <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>© eBird Status &amp; Trends · Cornell Lab of Ornithology</p>}
              {mapView === 'gbif' && <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>© GBIF.org · Global Biodiversity Information Facility</p>}
              {mapView === 'aab' && speciesCode && (
                <a href={ebirdUrl} target="_blank" rel="noopener noreferrer"
                   className="text-xs text-chirp-500 hover:text-chirp-400 flex items-center gap-1">
                  eBird S&amp;T abundance map →
                </a>
              )}
            </div>
          </div>
        </>
      ) : (
        <div className="p-5 flex flex-col items-center justify-center gap-3" style={{ minHeight: 140 }}>
          <MapPin size={22} className="text-gray-700"/>
          <p className="text-sm text-gray-500 text-center">Range map not yet available</p>
          <p className="text-xs text-gray-600 text-center">
            Click <strong className="text-gray-400">Refresh All Data</strong> above to fetch from Cornell Lab
          </p>
          {speciesCode && (
            <a href={ebirdUrl} target="_blank" rel="noopener noreferrer"
               className="text-xs text-chirp-500 hover:text-chirp-400 flex items-center gap-1 mt-1">
              <ExternalLink size={11}/> View on eBird S&amp;T →
            </a>
          )}
        </div>
      )}
    </CollapsibleCard>
  )
}

// ── Audio call player ──────────────────────────────────────────────────────
function CallPlayer({ call, callUrl }) {
  const [playing, setPlaying] = useState(false)
  const audioRef = useRef(null)
  const src = callUrl || call?.url
  if (!src) return null
  const toggle = () => {
    const a = audioRef.current
    if (!a) return
    if (playing) { a.pause(); setPlaying(false) }
    else { a.play().then(() => setPlaying(true)).catch(() => {}) }
  }
  return (
    <div className="flex items-center gap-3 py-2 border-b border-surface-700 last:border-0">
      <button onClick={toggle}
              className="w-8 h-8 rounded-full bg-chirp-600/30 hover:bg-chirp-600/50 text-chirp-400 flex items-center justify-center flex-shrink-0 transition-colors">
        {playing ? <Pause size={13}/> : <Play size={13}/>}
      </button>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-300 font-medium">{call?.type || 'Call'}</p>
        <p className="text-xs text-gray-600 truncate">
          {call?.recordist && `${call.recordist} · `}{call?.country || ''}
        </p>
      </div>
      {call?.source === 'inaturalist' && call?.obs_id && (
        <a href={`https://www.inaturalist.org/observations/${call.obs_id}`}
           target="_blank" rel="noopener noreferrer"
           className="text-gray-600 hover:text-gray-400 flex-shrink-0">
          <ExternalLink size={12}/>
        </a>
      )}
      <audio ref={audioRef} src={src} onEnded={() => setPlaying(false)} preload="none"/>
    </div>
  )
}

// ── Photo gallery ──────────────────────────────────────────────────────────
function PhotoGallery({ photos, onRefresh, refreshing }) {
  const [selected, setSelected] = useState(null)
  if (!photos?.length) return null
  return (
    <CollapsibleCard id="profile:photo-gallery" title="Photo Gallery" icon={Camera} fallbackOpen={true}
      headerRight={onRefresh && (
        <button onClick={e => { e.stopPropagation(); onRefresh() }} disabled={refreshing}
                className="text-xs text-gray-500 hover:text-chirp-400 flex items-center gap-1 disabled:opacity-50"
                title="Re-fetch this species' full profile data from iNaturalist/eBird/Wikipedia — picks up more photos if more are now available (same action as the 'Refresh All Data' button below)">
          <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''}/>
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      )}>
      <div className="p-4 grid grid-cols-2 gap-2">
        {photos.slice(0, 12).map((p, i) => (
          <img key={i}
               src={p.thumb || p.url}
               alt=""
               className="w-full aspect-square object-cover rounded-lg cursor-pointer hover:opacity-80 transition-opacity"
               onClick={() => setSelected(p.url || p.thumb)}
          />
        ))}
      </div>
      {selected && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
             onClick={() => setSelected(null)}>
          <img src={selected} alt="" className="max-w-full max-h-full rounded-xl object-contain"/>
        </div>
      )}
    </CollapsibleCard>
  )
}

// ── iNaturalist observation heatmap ────────────────────────────────────────
function ObservationMap({ taxonId, commonName }) {
  const ref = useRef(null)
  const mapRef = useRef(null)
  useEffect(() => {
    if (!taxonId || mapRef.current) return
    const loadLeaflet = () => {
      if (!ref.current) return
      const L = window.L
      const map = L.map(ref.current, { center: [30, -30], zoom: 2, scrollWheelZoom: false })
      cartoDarkUrl().then(url => {
        const base = L.tileLayer(url, { attribution: '© OpenStreetMap © CARTO', maxZoom: 18 }).addTo(map)
        base.bringToBack()
      })
      L.tileLayer(
        `https://api.inaturalist.org/v1/colored_heatmap/{z}/{x}/{y}.png?taxon_id=${taxonId}&color=%2322c55e`,
        { opacity: 0.7, maxZoom: 18, attribution: '© iNaturalist' }
      ).addTo(map)
      mapRef.current = map
    }
    if (!document.getElementById('leaflet-css')) {
      const l = document.createElement('link')
      l.id = 'leaflet-css'; l.rel = 'stylesheet'
      l.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
      document.head.appendChild(l)
    }
    if (window.L) { loadLeaflet() }
    else {
      const s = document.createElement('script')
      s.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
      s.onload = loadLeaflet; document.body.appendChild(s)
    }
    return () => { if (mapRef.current) { mapRef.current.remove(); mapRef.current = null } }
  }, [taxonId])
  return (
    <CollapsibleCard id="profile:observation-heatmap" title="Observation Heatmap" icon={MapPin} fallbackOpen={false}
      headerRight={
        taxonId && (
          <a href={`https://www.inaturalist.org/taxa/${taxonId}`}
             target="_blank" rel="noopener noreferrer"
             className="text-xs text-gray-500 hover:text-chirp-400 flex items-center gap-1"
             onClick={e => e.stopPropagation()}>
            iNaturalist <ExternalLink size={10}/>
          </a>
        )
      }
    >
      <div ref={ref} style={{ height: 280 }}/>
    </CollapsibleCard>
  )
}


// ── Bird Photo Gallery (user-submitted, with optional AI confirmation) ────────
function BirdPhotoGallery({ profileId, commonName, currentUser }) {
  const [photos, setPhotos] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState(null)
  const [lightbox, setLightbox] = useState(null) // photo object or null
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef(null)

  const load = useCallback(() => {
    api.birds.userPhotos.list(profileId)
      .then(setPhotos)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [profileId])

  useEffect(() => { load() }, [load])

  const doUpload = (file) => {
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError('Please choose an image file (JPEG, PNG, WebP, or GIF).')
      return
    }
    setError(null)
    setUploading(true)
    setProgress(0)
    api.birds.userPhotos.upload(profileId, file, setProgress, currentUser !== 'Anonymous' ? currentUser : null)
      .then(photo => {
        setPhotos(p => [photo, ...p])
        setUploading(false)
      })
      .catch(e => {
        setError(e.message || 'Upload failed')
        setUploading(false)
      })
  }

  const handleDelete = (photoId) => {
    api.birds.userPhotos.delete(photoId).then(() => {
      setPhotos(p => p.filter(ph => ph.id !== photoId))
      setLightbox(l => (l?.id === photoId ? null : l))
    }).catch(() => {})
  }

  return (
    <div className="p-4 space-y-4">
      {/* Upload dropzone */}
      <div
        onClick={() => fileInputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => {
          e.preventDefault(); setDragOver(false)
          doUpload(e.dataTransfer.files?.[0])
        }}
        className="rounded-xl border-2 border-dashed flex flex-col items-center justify-center gap-2 py-6 cursor-pointer transition-colors"
        style={{
          borderColor: dragOver ? 'var(--accent-500)' : 'var(--border-default)',
          background: dragOver ? 'var(--accent-500)11' : 'var(--bg-raised)',
        }}
      >
        <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif"
               className="hidden" onChange={e => doUpload(e.target.files?.[0])}/>
        {uploading ? (
          <>
            <RefreshCw size={20} className="animate-spin" style={{ color: 'var(--accent-400)' }}/>
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Uploading… {Math.round(progress * 100)}%</p>
          </>
        ) : (
          <>
            <Upload size={20} style={{ color: 'var(--text-tertiary)' }}/>
            <p className="text-sm text-center" style={{ color: 'var(--text-secondary)' }}>
              Drop a photo here, or tap to choose one
            </p>
          </>
        )}
      </div>
      {error && (
        <p className="text-xs px-3 py-2 rounded-lg" style={{ background: 'rgba(248,113,113,.1)', color: 'var(--pastel-red)', border: '1px solid rgba(248,113,113,.3)' }}>
          {error}
        </p>
      )}

      {/* Gallery grid */}
      {loading ? (
        <p className="text-sm text-center py-4" style={{ color: 'var(--text-tertiary)' }}>Loading photos…</p>
      ) : photos.length === 0 ? (
        <p className="text-sm text-center py-2" style={{ color: 'var(--text-tertiary)' }}>
          No photos yet. Spotted this species? Add a photo above.
        </p>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
          {photos.map(photo => (
            <button key={photo.id} onClick={() => setLightbox(photo)}
                    className="tactile-press relative aspect-square rounded-lg overflow-hidden group">
              <img src={api.birds.userPhotos.fileUrl(photo.id)} alt={commonName}
                   className="w-full h-full object-cover transition-transform group-hover:scale-105"/>
              {photo.ai_checked && photo.ai_match === true && (
                <span className="absolute bottom-1 right-1 rounded-full p-0.5" style={{ background: 'rgba(0,0,0,.6)' }}>
                  <CheckCircle2 size={14} className="text-green-400"/>
                </span>
              )}
              {photo.ai_checked && photo.ai_match === false && (
                <span className="absolute bottom-1 right-1 rounded-full p-0.5" style={{ background: 'rgba(0,0,0,.6)' }}>
                  <AlertTriangle size={14} className="text-yellow-400"/>
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Lightbox */}
      {lightbox && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,.85)' }}
             onClick={() => setLightbox(null)}>
          <div className="max-w-lg w-full" onClick={e => e.stopPropagation()}>
            <div className="flex justify-end mb-2">
              <button onClick={() => setLightbox(null)} className="tactile-press text-gray-300 hover:text-white p-1">
                <X size={20}/>
              </button>
            </div>
            <img src={api.birds.userPhotos.fileUrl(lightbox.id)} alt={commonName}
                 className="w-full rounded-xl max-h-[70vh] object-contain"/>
            <div className="mt-3 rounded-xl p-3 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
              {!lightbox.ai_checked && (
                <p className="text-xs flex items-center gap-1.5" style={{ color: 'var(--text-tertiary)' }}>
                  <HelpCircle size={13}/> Not AI-checked
                  {!lightbox.ai_note ? ' (no Anthropic API key configured in Settings)' : ` — ${lightbox.ai_note}`}
                </p>
              )}
              {lightbox.ai_checked && lightbox.ai_match === true && (
                <p className="text-xs flex items-center gap-1.5 text-green-400">
                  <CheckCircle2 size={13}/> AI confirms this looks like a {commonName}
                </p>
              )}
              {lightbox.ai_checked && lightbox.ai_match === false && (
                <p className="text-xs flex items-center gap-1.5 text-yellow-400">
                  <AlertTriangle size={13}/> AI thinks this might be: {lightbox.ai_guess || 'a different species'}
                </p>
              )}
              {lightbox.ai_checked && lightbox.ai_match === null && (
                <p className="text-xs flex items-center gap-1.5" style={{ color: 'var(--text-tertiary)' }}>
                  <HelpCircle size={13}/> AI wasn't confident enough to confirm or rule out a match
                </p>
              )}
              {lightbox.ai_note && lightbox.ai_checked && (
                <p className="text-xs italic" style={{ color: 'var(--text-tertiary)' }}>"{lightbox.ai_note}"</p>
              )}
              <div className="flex items-center justify-between pt-1">
                <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  {lightbox.uploaded_by ? `Uploaded by ${lightbox.uploaded_by}` : 'Uploaded anonymously'}
                </p>
                <button onClick={() => handleDelete(lightbox.id)}
                        className="tactile-press text-xs flex items-center gap-1 text-red-400 hover:text-red-300">
                  <Trash2 size={12}/> Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Bird Notes component ──────────────────────────────────────────────────────
function BirdNotes({ profileId, initialNotes }) {
  const [notes, setNotes] = useState(initialNotes || '')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const timerRef = useRef(null)

  // Update if profile reloads
  useEffect(() => { setNotes(initialNotes || '') }, [initialNotes])

  const save = useCallback(async (val) => {
    setSaving(true)
    try {
      await api.birds.updateNotes(profileId, val)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      // save failed — silently ignore
    } finally {
      setSaving(false)
    }
  }, [profileId])

  const handleChange = (e) => {
    const val = e.target.value
    setNotes(val)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => save(val), 1200) // auto-save after 1.2s idle
  }

  return (
    <div className="p-4 space-y-2">
      <textarea
        className="input w-full resize-none text-sm"
        rows={5}
        placeholder="Add your personal notes about this species — behaviour observations, habitat notes, equipment used…"
        value={notes}
        onChange={handleChange}
        style={{ lineHeight: 1.6 }}
      />
      <div className="flex items-center justify-between">
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          Auto-saves as you type
        </p>
        <div className="flex items-center gap-2">
          {saving && <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Saving…</span>}
          {saved && <span className="text-xs" style={{ color: 'var(--accent-400)' }}>✓ Saved</span>}
          <button onClick={() => save(notes)} disabled={saving} className="btn-secondary" style={{ padding: '5px 12px', fontSize: 12 }}>
            <Save size={12}/> Save
          </button>
        </div>
      </div>
    </div>
  )
}

// Compact, self-contained play button for a single detection's clip — used
// inside BirdRecordings so each row can offer "play just this bird's call"
// as a separate, smaller action from the full-recording play button above it.
// Keeps its own play/enhanced state locally rather than adding another
// keyed-by-id map to the parent, since only this row's audio is affected.
function ClipPlayButton({ recordingId, detection }) {
  const [playing, setPlaying] = useState(false)
  const [enhanced, setEnhanced] = useState(true)
  const ref = useRef(null)

  if (!detection) return null

  const toggle = (e) => {
    e.preventDefault(); e.stopPropagation()
    const a = ref.current
    if (!a) return
    if (playing) { a.pause(); setPlaying(false) }
    else { a.play().catch(() => {}); setPlaying(true) }
  }
  const toggleEnhanced = (e) => {
    e.preventDefault(); e.stopPropagation()
    setEnhanced(en => !en)
    setPlaying(false)
  }

  return (
    <div className="flex items-center gap-1 flex-shrink-0">
      <button onClick={toggle}
              title="Play just this bird's call (not the full recording)"
              className="flex items-center gap-1 text-xs px-2 py-1 rounded-full transition-colors"
              style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }}>
        {playing ? <Pause size={10}/> : <Play size={10}/>} Clip
      </button>
      <span className="relative group">
        <button onClick={toggleEnhanced}
                className={`transition-colors ${enhanced ? 'text-chirp-400' : ''}`}
                style={{ color: enhanced ? undefined : 'var(--text-tertiary)' }}>
          <Sparkles size={12}/>
        </button>
        <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block z-10 pointer-events-none">
          <div className="bg-surface-800 border border-surface-600 rounded px-2 py-1 text-xs text-gray-300 whitespace-nowrap">
            Enhance clip
          </div>
        </div>
      </span>
      <audio ref={ref}
             src={enhanced ? api.recordings.clipEnhancedUrl(recordingId, detection.id) : api.recordings.clipUrl(recordingId, detection.id)}
             onEnded={() => setPlaying(false)}
             preload="none"/>
    </div>
  )
}

// ── Bird Recordings component ─────────────────────────────────────────────────
function BirdRecordings({ commonName, profileLabel }) {
  const [recordings, setRecordings] = useState([])
  const [loading, setLoading] = useState(true)
  const [playingId, setPlayingId] = useState(null)
  const [enhancedIds, setEnhancedIds] = useState(() => new Set())
  const audioRefs = useRef({})
  const { fmtAgo } = useTz()

  useEffect(() => {
    if (!commonName) return
    // "Bat" is a synthetic pseudo-species identified by its stable,
    // never-user-edited label — NOT by common_name, which is the
    // user-facing display name and can be changed (a "Bat" profile was
    // renamed to a custom display name once, which silently broke this
    // exact query when it checked commonName === 'Bat', since the two
    // are no longer the same string).
    // When this IS the Bat pseudo-species, is_bat=true is used ALONE,
    // without ALSO requiring species to match the (possibly renamed)
    // display name — the whole point of this pseudo-species is capturing
    // every bat recording regardless of what it's currently labeled.
    const isBatProfile = profileLabel === 'Bat'
    const params = isBatProfile
      ? { is_bat: true, limit: 20 }
      : { species: commonName, limit: 20 }
    api.recordings.list(params)
      .then(r => setRecordings(Array.isArray(r) ? r : (r?.items || [])))
      .finally(() => setLoading(false))
  }, [commonName, profileLabel])

  const togglePlay = useCallback((id) => {
    // Pause any other playing audio
    Object.entries(audioRefs.current).forEach(([k, a]) => {
      if (k !== id && a) { a.pause(); a.currentTime = 0 }
    })
    const audio = audioRefs.current[id]
    if (!audio) return
    if (playingId === id) {
      audio.pause()
      setPlayingId(null)
    } else {
      audio.play().then(() => setPlayingId(id)).catch(() => {})
    }
  }, [playingId])

  const toggleEnhanced = useCallback((id) => {
    // Pause first — switching <audio src> resets playback anyway, and these
    // are full recordings (could be 30s+), so jumping back to 0:00 silently
    // mid-playback would be more confusing than just stopping.
    const audio = audioRefs.current[id]
    if (audio) audio.pause()
    if (playingId === id) setPlayingId(null)
    setEnhancedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }, [playingId])

  if (loading) return (
    <div className="p-4 space-y-2">
      {[0,1,2].map(i => <div key={i} className="skeleton h-12 rounded-lg"/>)}
    </div>
  )

  if (recordings.length === 0) return (
    <div className="p-4 text-center py-6">
      <FileAudio size={24} className="mx-auto mb-2" style={{ color: 'var(--text-tertiary)' }}/>
      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>No recordings yet</p>
    </div>
  )

  return (
    <div className="p-3 space-y-2">
      {recordings.map(rec => {
        const isPlaying = playingId === rec.id
        const isEnhanced = enhancedIds.has(rec.id)
        const audioSrc = mediaUrl(isEnhanced
          ? `/api/v1/recordings/${rec.id}/audio/enhanced`
          : `/api/v1/recordings/${rec.id}/audio`)
        // The specific detection within this recording matching the current
        // bird species — used for the "play just this call" clip button.
        // If there are multiple matches (e.g. the same species called twice
        // in one recording), use the highest-confidence one.
        const matchedDetections = rec.detections?.filter(d =>
          d.common_name?.toLowerCase() === commonName?.toLowerCase()
        ) || []
        const clipDetection = matchedDetections.length
          ? matchedDetections.reduce((best, d) => d.confidence > best.confidence ? d : best)
          : null
        return (
          <div key={rec.id} className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all"
               style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
            {/* Play button — or, for a Haikubox-sourced detection (no
                audio file exists at all, confirmed via the already-
                correct has_audio flag computed server-side from
                wav_path), a Haikubox indicator shown in its place
                instead, since there's nothing to play. */}
            {rec.has_audio === false ? (
              <span title="From Haikubox — no audio available"
                    className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
                    style={{ background: 'var(--bg-base)', color: 'var(--text-tertiary)', border: '1px solid var(--border-subtle)' }}>
                <Radio size={13}/>
              </span>
            ) : (
              <button onClick={() => togglePlay(rec.id)}
                className="tactile-press w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 transition-all"
                style={{
                  background: isPlaying ? 'var(--accent-500)' : 'var(--nav-active-bg)',
                  color: isPlaying ? '#000' : 'var(--accent-400)',
                }}>
                {isPlaying
                  ? <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                  : <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
                }
              </button>
            )}

            {/* Info — clicking goes to recording page */}
            <Link to={`/recordings/${rec.id}`}
                  className="flex-1 min-w-0 hover:text-accent transition-colors"
                  style={{ color: 'var(--text-primary)' }}>
              <p className="text-sm font-medium truncate">
                {rec.top_species || rec.label || 'Recording'}
              </p>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                {fmtAgo(rec.trigger_timestamp)} · {matchedDetections.length} det
              </p>
            </Link>

            {/* Confidence */}
            {rec.max_confidence > 0 && (
              <span className="badge badge-accent flex-shrink-0 text-xs">
                {(rec.max_confidence * 100).toFixed(0)}%
              </span>
            )}

            {/* Play just this bird's call within the recording — no
                audio exists for a Haikubox row even though a matching
                Detection does, so this is hidden alongside the play
                button above rather than rendered into a dead end. */}
            {rec.has_audio !== false && <ClipPlayButton recordingId={rec.id} detection={clipDetection}/>}

            {/* Enhanced toggle (full recording) — same reasoning */}
            {rec.has_audio !== false && (
              <span className="relative group flex-shrink-0">
                <button onClick={() => toggleEnhanced(rec.id)}
                        className={`tactile-press transition-colors ${isEnhanced ? 'text-chirp-400' : ''}`}
                        style={{ color: isEnhanced ? undefined : 'var(--text-tertiary)' }}>
                  <Sparkles size={14}/>
                </button>
                <div className="absolute bottom-full mb-1 right-0 hidden group-hover:block z-10 pointer-events-none">
                  <div className="bg-surface-800 border border-surface-600 rounded px-2 py-1 text-xs text-gray-300 whitespace-nowrap">
                    Enhance full recording
                  </div>
                </div>
              </span>
            )}

            {/* Hidden audio element — only needed when audio exists */}
            {rec.has_audio !== false && (
              <audio ref={el => audioRefs.current[rec.id] = el}
                     src={audioSrc}
                     onEnded={() => setPlayingId(null)}
                     preload="none"/>
            )}
          </div>
        )
      })}

      {recordings.length >= 20 && (
        <Link to={`/recordings?species=${encodeURIComponent(commonName)}`}
              className="block text-center text-sm py-2 transition-colors hover:text-accent"
              style={{ color: 'var(--text-secondary)' }}>
          View all recordings →
        </Link>
      )}
    </div>
  )
}

// ── Haikubox detections link for this species ──────────────────────────────
// Small, conditional doorway to the dedicated /haikubox page (see
// HaikuboxDetections.jsx and api/recordings.py's list_haikubox_recordings
// for the full reasoning) — only renders if this species has at
// least one Haikubox detection, so it's invisible for the vast majority
// of species on a deployment not using one. Deliberately not its own
// CollapsibleCard: a single count + link doesn't need to expand/collapse
// the way a list of recordings does.
function HaikuboxSpeciesLink({ commonName }) {
  const [count, setCount] = useState(null)

  useEffect(() => {
    if (!commonName) return
    api.recordings.haikuboxSummary()
      .then(s => setCount(s.species_counts?.[commonName] || 0))
      .catch(() => {})
  }, [commonName])

  if (!count) return null

  return (
    <Link to={`/haikubox?species=${encodeURIComponent(commonName)}`}
          className="flex items-center justify-between gap-2 px-4 py-2.5 rounded-xl text-xs transition-colors"
          style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
      <span className="flex items-center gap-1.5">
        <Radio size={13} style={{ color: 'var(--accent-400)' }}/>
        {count.toLocaleString()} Haikubox detection{count === 1 ? '' : 's'} (no audio)
      </span>
      <span style={{ color: 'var(--accent-400)' }}>View →</span>
    </Link>
  )
}

// ── Main profile page ──────────────────────────────────────────────────────
function PresenceSummaryCard({ profile }) {
  const { fmtAgo, fmtDateFull } = useTz()
  const [text, setText] = useState(profile.ai_presence_summary)
  const [errorMsg, setErrorMsg] = useState(profile.ai_presence_summary_error)
  const [generatedAt, setGeneratedAt] = useState(profile.ai_presence_summary_generated_at)
  const [regenerating, setRegenerating] = useState(false)
  const [pollTick, setPollTick] = useState(0)

  // If the feature is enabled and no text exists yet, a background task
  // was just kicked off server-side on this same page load (see
  // api/birds.py's get_bird_profile) — poll briefly for it to land
  // rather than requiring a manual refresh, but only a few times so a
  // permanently-failing generation doesn't poll forever.
  useEffect(() => {
    if (!profile.ai_presence_summary_enabled || text || pollTick >= 5) return
    const t = setTimeout(() => {
      api.birds.get(profile.id).then(p => {
        if (p.ai_presence_summary) setText(p.ai_presence_summary)
        if (p.ai_presence_summary_error) setErrorMsg(p.ai_presence_summary_error)
        if (p.ai_presence_summary_generated_at) setGeneratedAt(p.ai_presence_summary_generated_at)
        setPollTick(n => n + 1)
      }).catch(() => setPollTick(n => n + 1))
    }, 2500)
    return () => clearTimeout(t)
  }, [profile.id, profile.ai_presence_summary_enabled, text, pollTick])

  const regenerate = async () => {
    setRegenerating(true)
    try {
      const p = await api.birds.regeneratePresenceSummary(profile.id)
      setText(p.ai_presence_summary)
      setErrorMsg(p.ai_presence_summary_error)
      setGeneratedAt(p.ai_presence_summary_generated_at)
    } catch (e) { /* keep whatever was showing before */ }
    setRegenerating(false)
  }

  // Only fully hidden when the feature is DISABLED. Enabled-but-nothing-
  // yet is a distinct state (still pending, or a past attempt
  // failed) and needs a visible status with a way to act on it — hiding
  // the whole card (including the only regenerate button) whenever text
  // didn't exist made a failed first generation a silent dead end with
  // no way to retry.
  if (!profile.ai_presence_summary_enabled) return null

  return (
    <div className="card rounded-xl p-4 relative">
      {text ? (
        <p className="text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontFamily: "'Lora', serif" }}>
          {text}
        </p>
      ) : errorMsg ? (
        <div>
          <p className="text-sm" style={{ color: '#f87171' }}>Last attempt failed: {errorMsg}</p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>Check the provider key in Settings → AI Features, then use the regenerate button below to try again.</p>
        </div>
      ) : (
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
          {pollTick < 5 ? 'Generating a presence summary…' : 'Nothing generated yet — use the regenerate button below to try.'}
        </p>
      )}
      <div className="flex items-center justify-between mt-2">
        <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--text-tertiary)' }}>
          AI-generated
          {/* Real gap: this timestamp was tracked server-side (used for
              the scheduled staleness refresh) but never actually sent to
              the frontend or shown anywhere — no way to tell whether a
              presence note reflects last week's activity or last year's.
              title carries the full date/time on hover, matching the
              same pattern used for recording timestamps elsewhere in
              this app; the visible text stays compact/relative. */}
          {generatedAt && (
            <span title={fmtDateFull(generatedAt)}> · Generated {fmtAgo(generatedAt)}</span>
          )}
        </p>
        <button onClick={regenerate} disabled={regenerating}
                className="tactile-press p-1 rounded-full transition-colors hover:opacity-80 disabled:opacity-40 flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}
                title={text ? 'Regenerate' : 'Generate'} aria-label="Regenerate">
          <RefreshCw size={13} className={regenerating ? 'animate-spin' : ''}/>
        </button>
      </div>
    </div>
  )
}

// Bell on a species page: watch this bird (Settings → My Notifications).
function WatchBirdButton({ name }) {
  const [watch, setWatch] = useState(undefined)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!name) return
    api.notifications.prefs()
      .then(p => setWatch((p.watches || []).find(w => w.common_name.toLowerCase() === name.toLowerCase()) || null))
      .catch(() => setWatch(null))
  }, [name])
  if (watch === undefined) return null
  const set = async (mode) => {
    setOpen(false)
    if (mode === 'off') { if (watch) await api.notifications.deleteWatch(watch.id).catch(() => {}); setWatch(null); return }
    try { setWatch(await api.notifications.addWatch(name, mode)) } catch {}
  }
  const label = watch ? (watch.mode === 'daily' ? 'Daily summary' : 'Notifying') : 'Notify me'
  return (
    <div className="relative ml-auto">
      <button className="btn-secondary inline-flex items-center gap-1.5" onClick={() => setOpen(o => !o)}
              aria-label={`Notifications for ${name}`}
              style={watch ? { color: 'var(--accent-400)', borderColor: 'var(--accent-400)' } : undefined}>
        {watch ? <BellRing size={14}/> : <Bell size={14}/>} {label}
      </button>
      {open && (
        <div className="absolute right-0 mt-1 z-30 rounded-xl overflow-hidden shadow-modal" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', minWidth: 200 }}>
          {[['every', 'Every time it\'s heard'], ['daily', 'Once a day (7 pm)'], ['off', 'Off']].map(([m, t]) => (
            <button key={m} onClick={() => set(m)} className="w-full text-left px-4 py-2.5 text-sm hover:bg-raised"
                    style={{ color: (watch?.mode || 'off') === m ? 'var(--accent-400)' : 'var(--text-primary)' }}>{t}</button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function BirdProfile() {
  const { id: profileId } = useParams() // route uses :id, alias to profileId
  const [searchParams] = useSearchParams()
  const location = useLocation()
  // Determine where to send the back button — check referrer in location.state first,
  // then fall back to the URL param 'from', then default to life list

  const [profile, setProfile] = useState(null)
  const [activeTab, setActiveTab] = useState('overview')
  const [enabledSources, setEnabledSources] = useState({ aab: true, macaulay: true, geomodel: true, birdlife: true, ebird_st: false })
  const [sourceOrder, setSourceOrder] = useState(['aab', 'macaulay', 'geomodel', 'birdlife', 'ebird_st'])

  // Fetch range map source settings once on mount
  useEffect(() => {
    api.settings.get().then(s => {
      if (s?.range_map_sources) setEnabledSources(s.range_map_sources)
      if (s?.range_map_source_order?.length) setSourceOrder(s.range_map_source_order)
    }).catch(() => {})
  }, [])
  const [calls, setCalls] = useState([])
  const [loading, setLoading] = useState(true)
  const [enriching, setEnriching] = useState(false)
  const [currentUser, setCurrentUser] = useState('Anonymous')
  const [userRole, setUserRole] = useState('viewer')

  useEffect(() => {
    try {
      const token = localStorage.getItem('chirp_token')
      if (token) {
        fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${token}` } })
          .then(r => r.ok ? r.json() : null)
          .then(u => { if (u?.username) { setCurrentUser(u.username); setUserRole(u.role || 'viewer') } })
          .catch(() => {})
      } else {
        setUserRole('admin')
      }
    } catch {}
  }, [])

  const loadData = useCallback(async (id) => {
    try {
      const [p, c] = await Promise.all([
        api.birds.get(id),
        api.birds.calls(id),
      ])
      setProfile(p)
      setCalls(c || [])

    } catch (e) {
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const id = profileId || searchParams.get('id')
    const label = searchParams.get('label') || searchParams.get('name')
    if (id) {
      loadData(id)
    } else if (label) {
      // Resolve label → profile id via the by-label endpoint, then load
      api.birds.byLabel(label)
        .then(p => { if (p?.id) loadData(p.id) })
        .catch(() => setLoading(false))
    } else {
      // No id or label — nothing to load
      setLoading(false)
    }
  }, [profileId, searchParams, loadData])

  const handleEnrich = async () => {
    // profileId comes from URL param :id (Life List navigation)
    // profile?.id comes from the loaded profile (Regional Birds / label navigation)
    const id = profileId || searchParams.get('id') || profile?.id
    if (!id || enriching) return
    setEnriching(true)
    try {
      await api.birds.enrich(id)
      // Poll for completion
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 2000))
        const p = await api.birds.get(id)
        setProfile(p)
        if (p.enrichment_complete) break
      }
      const c = await api.birds.calls(id)
      setCalls(c || [])
    } catch (e) {
    } finally {
      setEnriching(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64 text-chirp-500 animate-pulse">Loading…</div>
  if (!profile) return <div className="p-4 md:p-6 text-gray-400">Profile not found.</div>

  const rawSections = profile.description_sections
  const sections = Array.isArray(rawSections) ? rawSections
    : (profile.description ? [{ section: 'Overview', text: profile.description }] : [])

  return (
    <div className="p-4 md:p-6 max-w-5xl space-y-6 animate-fade-in">
      <div className="flex items-center gap-2">
        <Link to="/library" state={{ from: '/library' }}
              className="btn-secondary inline-flex items-center gap-1.5">
          <ArrowLeft size={14}/> Life List
        </Link>
        <Link to="/regional" state={{ from: '/regional' }}
              className="btn-secondary inline-flex items-center gap-1.5">
          <ArrowLeft size={14}/> Field Guide
        </Link>
        <WatchBirdButton name={profile?.common_name}/>
      </div>

      {/* Hero card */}
      <div className="card overflow-hidden">
        <div className="relative" style={{ height: 'clamp(380px, 48vw, 460px)' }}>
          {/* Full-bleed-width hero is an intentional poster-style design
              (matches the rest of the page). Two distinct framing
              problems were reported against the previous single
              object-cover image: a vertical one (the source photo's
              subject sat in the upper portion of its frame, so center
              cropping clipped the head) and a horizontal one (a
              differently-shaped source photo had its subject pushed to
              one side, with empty background on the other side of
              the same original image — confirmed by testing against the
              reported photo, not assumed). No single fixed
              object-position value can be correct for every possible
              source photo's composition on both axes at once — that's
              not a tuning problem, it's a structural limit of cropping at
              all. Switched to the standard fix for exactly this (the same
              treatment Spotify/Apple Music use for non-square album art):
              a heavily blurred, scaled-up copy of the photo fills the
              hero edge-to-edge for the full-bleed look, while the
              complete, unmodified photo sits on top via object-fit:
              contain — the subject can never be cropped out regardless of
              the source image's own aspect ratio or where the subject
              sits within it. */}
          <div className="absolute inset-0 overflow-hidden">
            {profile.photo_url ? (
              <>
                {/* Same bug, same fix, as the range-map images earlier this
                    session: when a local photo exists, the backend returns
                    /api/v1/birds/{id}/photo — a URL behind this project's
                    own multi-tenant get_db, which needs a token to resolve
                    which tenant DB to query, completely independent of
                    whether the app requires login. A plain <img src> can
                    never carry that token, so this always 401'd for any
                    profile with a downloaded photo — confirmed directly:
                    the Bat profile's photo fetch succeeded and saved to
                    disk (twice, per the logs), yet never rendered, because
                    nothing about a successful save ever touched this. Safe
                    to wrap unconditionally — mediaUrl() just appends
                    ?token=... harmlessly for the other case (an external
                    iNaturalist photo URL doesn't need or use it). */}
                <img src={mediaUrl(profile.photo_url)} alt="" aria-hidden="true"
                     className="absolute inset-0 w-full h-full object-cover"
                     style={{ filter: 'blur(32px) brightness(0.55) saturate(1.15)', transform: 'scale(1.15)' }}/>
                <div className="absolute inset-0 flex items-center justify-center">
                  <img src={mediaUrl(profile.photo_url)} alt={profile.common_name}
                       className="max-w-full max-h-full w-auto h-auto object-contain"
                       style={{ boxShadow: '0 12px 40px rgba(0,0,0,.45)' }}/>
                </div>
              </>
            ) : (
              <div className="absolute inset-0 bg-gradient-to-br from-chirp-900 to-surface-950 flex items-center justify-center"><BirdIcon size={100} style={{ color: 'rgba(255,255,255,.25)' }}/></div>
            )}
          </div>
          <div className="absolute inset-0 bg-gradient-to-t from-surface-900/95 via-surface-900/20 to-transparent"/>
          {profile.photo_credit && (
            <p className="absolute top-2 right-2 text-[10px] leading-none text-gray-300/90 bg-black/40 px-1.5 py-0.5 rounded max-w-[55%] truncate"
               title={profile.photo_credit}>
              {profile.photo_credit}
            </p>
          )}
          <div className="absolute bottom-0 left-0 right-0 p-5 flex items-end justify-between">
            <div className="inline-block px-3 py-1.5 -mx-3 -my-1.5 rounded-lg" style={{ background: 'rgba(0,0,0,0.38)' }}>
              <h1 className="text-3xl font-bold text-white" style={{ textShadow: '0 1px 6px rgba(0,0,0,0.6)' }}>{profile.common_name}</h1>
              <p className="text-base italic text-gray-300 mt-0.5" style={{ textShadow: '0 1px 4px rgba(0,0,0,0.6)' }}>{profile.scientific_name}</p>
            </div>
            <ConsBadge status={profile.conservation_status} authority={profile.conservation_authority}/>
          </div>
        </div>
        <div className="grid grid-cols-4 divide-x divide-surface-700 border-t border-surface-700">
          {[
            ['Detections', profile.total_detections],
            ['Confidence', profile.max_confidence ? `${(profile.max_confidence*100).toFixed(0)}%` : '—'],
            ['Last Seen', profile.last_detected ? format(new Date(profile.last_detected+'Z'), 'MMM d') : 'Never'],
            ['Order', profile.order_name || '—'],
          ].map(([l,v]) => (
            <div key={l} className="px-3 py-3 text-center">
              <p className="text-xs text-gray-500 mb-1 whitespace-nowrap">{l}</p>
              <p className="text-sm font-semibold text-gray-200 break-words leading-tight">{v}</p>
            </div>
          ))}
        </div>
      </div>

      <PresenceSummaryCard profile={profile}/>

      {enriching && (
        <div className="card p-4 border-chirp-700/50 bg-chirp-900/10 flex items-center gap-3">
          <RefreshCw size={16} className="text-chirp-400 animate-spin flex-shrink-0"/>
          <div>
            <p className="text-sm font-medium text-chirp-300">Fetching profile data…</p>
            <p className="text-xs text-chirp-600 mt-0.5">Cornell Lab · iNaturalist · eBird — ~20–30s</p>
          </div>
        </div>
      )}

      <div className="flex flex-col md:flex-row gap-5">
        {/* Section navigation — sidebar, matching the Settings and Tech
            Docs pages' own left-nav pattern (per direct request), reusing
            their exact same overflow-x-auto/flex-shrink-0 styling for
            mobile — a horizontal tab strip silently overflowing instead
            of wrapping was a bug found and fixed on a completely
            different page earlier this session, so this reuses that
            already-hardened pattern rather than risking the same class
            of bug again in a new one. */}
        <nav className="md:w-48 flex-shrink-0 flex md:flex-col gap-1 overflow-x-auto md:overflow-visible pb-2 md:pb-0">
          {PROFILE_TABS.map(t => (
            <button key={t.id}
                    onClick={() => { setActiveTab(t.id); window.scrollTo({ top: 0, behavior: 'smooth' }) }}
                    className="flex items-center justify-between gap-1.5 px-3 py-2 rounded-lg text-sm text-left whitespace-nowrap md:whitespace-normal flex-shrink-0"
                    style={{
                      background: activeTab === t.id ? 'var(--bg-raised)' : 'transparent',
                      color: activeTab === t.id ? 'var(--accent-400)' : 'var(--text-secondary)',
                      fontWeight: activeTab === t.id ? 600 : 400,
                    }}>
              {t.label}
              {activeTab === t.id && <ChevronRight size={14} className="hidden md:block"/>}
            </button>
          ))}
        </nav>

        <div className="flex-1 min-w-0 max-w-3xl space-y-5">

        {activeTab === 'overview' && (<>

          {/* At a Glance — the AAB habitat/food/nesting/behavior tags,
              split out from "Did you know?" into their own card so quick
              stats and long-form trivia aren't competing for attention
              in the same collapsible. Placed first: a scannable summary
              before the prose (About) and before the trivia (Did you
              know?, further down). */}
          {(profile.aab_habitat || profile.aab_food || profile.aab_nesting || profile.aab_behavior || profile.aab_length_min_cm) && (
            <CollapsibleCard id="profile:at-a-glance" fallbackOpen={true} title="At a Glance" icon={Compass}>
              <div className="p-5 space-y-5">
                {/* flex-wrap instead of a fixed grid-cols-5 — a species
                    genuinely missing one category (or, as reported, one
                    that hadn't been re-enriched since a bug in the AAB
                    fetch dropped Conservation entirely — see
                    bird_enricher.py) would otherwise always leave an
                    empty, oddly-spaced gap where a 5th column was
                    reserved but nothing rendered into it. */}
                <div className="flex flex-wrap gap-3">
                  {profile.aab_habitat && (
                    <button onClick={() => scrollToLifeHistory('habitat')}
                         className="rounded-xl p-3 flex flex-col items-center text-center gap-1.5 tactile-press flex-1 min-w-[calc(50%-0.375rem)] sm:min-w-[calc(20%-0.6rem)]"
                         style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
                      <TreePine size={20} style={{ color: 'var(--accent-400)' }}/>
                      <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Habitat</span>
                      <span className="text-sm font-semibold break-words leading-snug" style={{ color: 'var(--text-primary)' }}>{profile.aab_habitat}</span>
                    </button>
                  )}
                  {profile.aab_food && (
                    <button onClick={() => scrollToLifeHistory('food')}
                         className="rounded-xl p-3 flex flex-col items-center text-center gap-1.5 tactile-press flex-1 min-w-[calc(50%-0.375rem)] sm:min-w-[calc(20%-0.6rem)]"
                         style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
                      <Bug size={20} style={{ color: 'var(--accent-400)' }}/>
                      <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Food</span>
                      <span className="text-sm font-semibold break-words leading-snug" style={{ color: 'var(--text-primary)' }}>{profile.aab_food}</span>
                    </button>
                  )}
                  {profile.aab_nesting && (
                    <button onClick={() => scrollToLifeHistory('nesting')}
                         className="rounded-xl p-3 flex flex-col items-center text-center gap-1.5 tactile-press flex-1 min-w-[calc(50%-0.375rem)] sm:min-w-[calc(20%-0.6rem)]"
                         style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
                      <Egg size={20} style={{ color: 'var(--accent-400)' }}/>
                      <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Nesting</span>
                      <span className="text-sm font-semibold break-words leading-snug" style={{ color: 'var(--text-primary)' }}>{profile.aab_nesting}</span>
                    </button>
                  )}
                  {profile.aab_behavior && (
                    <button onClick={() => scrollToLifeHistory('behavior')}
                         className="rounded-xl p-3 flex flex-col items-center text-center gap-1.5 tactile-press flex-1 min-w-[calc(50%-0.375rem)] sm:min-w-[calc(20%-0.6rem)]"
                         style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
                      <Bird size={20} style={{ color: 'var(--accent-400)' }}/>
                      <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Behavior</span>
                      <span className="text-sm font-semibold break-words leading-snug" style={{ color: 'var(--text-primary)' }}>{profile.aab_behavior}</span>
                    </button>
                  )}
                  {profile.aab_conservation && (
                    <button onClick={() => scrollToLifeHistory('conservation')}
                         className="rounded-xl p-3 flex flex-col items-center text-center gap-1.5 tactile-press flex-1 min-w-[calc(50%-0.375rem)] sm:min-w-[calc(20%-0.6rem)]"
                         style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
                      <Shield size={20} style={{ color: 'var(--accent-400)' }}/>
                      <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Conservation</span>
                      <span className="text-sm font-semibold break-words leading-snug" style={{ color: 'var(--text-primary)' }}>{profile.aab_conservation}</span>
                    </button>
                  )}
                </div>
                {profile.aab_length_min_cm && (
                  <BirdSizeRuler minCm={profile.aab_length_min_cm} maxCm={profile.aab_length_max_cm} commonName={profile.common_name}/>
                )}
              </div>
            </CollapsibleCard>
          )}

          {/* Seasonal presence — moved up here, right after At a Glance,
              per direct request (was previously the last card in the
              main column, well below the fold). */}
          <CollapsibleCard id="profile:seasonal-presence" fallbackOpen={true} title="Seasonal Presence" icon={null}>
            <LocalPresenceChart profileId={profile.id}/>
            {profile.monthly_frequency && (
              <>
                <div style={{ borderTop: '1px solid var(--border-subtle)', margin: '0 1rem' }}/>
                <SeasonalChart monthly={profile.monthly_frequency}/>
              </>
            )}
          </CollapsibleCard>

          {/* About */}
          {(() => {
            // description_source is now frequently a Cornell Lab / All
            // About Birds URL, not always Wikipedia — see
            // bird_enricher.py's own comment on why AAB's description is
            // preferred when available. The label/attribution here need
            // to reflect whichever one it is, not assume
            // Wikipedia unconditionally the way this previously did (a
            // bug this backend change would have otherwise silently
            // introduced: showing "Wikipedia CC BY-SA" under content that
            // came from Cornell Lab).
            const isAAB = profile.description_source && profile.description_source.includes("allaboutbirds.org")
            const sourceLabel = isAAB ? "All About Birds" : "Wikipedia"
            const attributionText = isAAB ? "Cornell Lab of Ornithology" : "Wikipedia CC BY-SA"
            return (
          <CollapsibleCard id="profile:about" fallbackOpen={true} title="About" icon={Info}
            headerRight={profile.description_source && (
              <a href={profile.description_source} target="_blank" rel="noopener noreferrer"
                 className="text-xs hover:text-accent flex items-center gap-1"
                 style={{ color: 'var(--text-tertiary)' }}
                 onClick={e => e.stopPropagation()}>
                {sourceLabel} <ExternalLink size={10}/>
              </a>
            )}>
            <div className="p-5">
              {sections.length === 0
                ? <div className="py-4 text-center">
                    <p className="text-sm mb-3" style={{ color: 'var(--text-tertiary)' }}>No description yet.</p>
                    <button onClick={handleEnrich} disabled={enriching}
                            className="btn-primary flex items-center gap-1.5 mx-auto">
                      <RefreshCw size={14} className={enriching ? 'animate-spin' : ''}/> Fetch Description
                    </button>
                  </div>
                : <>
                    <div className="divide-y divide-surface-700">
                      {sections.map((sec, i) => <Section key={i} title={sec.section} text={sec.text} defaultOpen={i===0}/>)}
                    </div>
                    <p className="text-xs mt-3 pt-3 border-t border-surface-700" style={{ color: 'var(--text-tertiary)' }}>
                      {attributionText} ·{' '}
                      {profile.description_source && (
                        <a href={profile.description_source} target="_blank" rel="noopener noreferrer"
                           className="hover:text-accent" style={{ color: 'var(--accent-600)' }}>View full article →</a>
                      )}
                    </p>
                  </>
              }
            </div>
          </CollapsibleCard>
            )
          })()}

          {/* Life History — full narrative paragraphs from AAB's own
              separate /lifehistory page, genuinely distinct from the
              short tag values already shown in At a Glance above (which
              come from /overview). Each section's id matches what
              scrollToLifeHistory() jumps to when an At a Glance tile is
              clicked — which is why this stays in the SAME tab as At a
              Glance rather than being split out; that jump has no
              tab-switching logic of its own. */}
          {(profile.aab_habitat_text || profile.aab_food_text || profile.aab_nesting_text ||
            profile.aab_behavior_text || profile.aab_conservation_text) && (
            <CollapsibleCard id="profile:life-history" fallbackOpen={true} title="Life History" icon={Shield}
              headerRight={profile.aab_url && (
                <a href={profile.aab_url} target="_blank" rel="noopener noreferrer"
                   className="text-xs hover:text-accent flex items-center gap-1"
                   style={{ color: 'var(--text-tertiary)' }}
                   onClick={e => e.stopPropagation()}>
                  All About Birds <ExternalLink size={10}/>
                </a>
              )}>
              <div className="p-5 space-y-5">
                {[
                  { key: 'habitat', label: 'Habitat', icon: TreePine, text: profile.aab_habitat_text },
                  { key: 'food', label: 'Food', icon: Bug, text: profile.aab_food_text },
                  { key: 'nesting', label: 'Nesting', icon: Egg, text: profile.aab_nesting_text },
                  { key: 'behavior', label: 'Behavior', icon: Bird, text: profile.aab_behavior_text },
                  { key: 'conservation', label: 'Conservation', icon: Shield, text: profile.aab_conservation_text },
                ].filter(s => s.text).map(s => (
                  <div key={s.key} id={`lifehistory-${s.key}`} className="flex gap-3.5 scroll-mt-20">
                    <div className="flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center"
                         style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
                      <s.icon size={17} style={{ color: 'var(--accent-400)' }}/>
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>{s.label}</h3>
                      <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{s.text}</p>
                    </div>
                  </div>
                ))}
                <p className="text-xs pt-2 border-t border-surface-700" style={{ color: 'var(--text-tertiary)' }}>
                  Cornell Lab of Ornithology
                  {profile.aab_url && (
                    <> ·{' '}
                      <a href={profile.aab_url} target="_blank" rel="noopener noreferrer"
                         className="hover:text-accent" style={{ color: 'var(--accent-600)' }}>View on All About Birds →</a>
                    </>
                  )}
                </p>
              </div>
            </CollapsibleCard>
          )}

        </>)}

        {activeTab === 'sounds' && (<>

          {/* "Did you know?" — Cornell Lab / All About Birds
              trivia facts, genuinely distinct from both About (prose)
              and At a Glance (quick tags). */}
          {profile.aab_cool_facts?.length > 0 && (
            <CollapsibleCard id="profile:cool-facts" fallbackOpen={true} title="Did you know?" icon={Lightbulb}
              headerRight={profile.aab_url && (
                <a href={profile.aab_url} target="_blank" rel="noopener noreferrer"
                   className="text-xs hover:text-accent flex items-center gap-1"
                   style={{ color: 'var(--text-tertiary)' }}
                   onClick={e => e.stopPropagation()}>
                  All About Birds <ExternalLink size={10}/>
                </a>
              )}>
              <div className="p-5 space-y-4">
                {profile.aab_cool_facts?.length > 0 && (
                  <ul className="space-y-2.5">
                    {profile.aab_cool_facts.map((fact, i) => {
                      const [lede, rest] = splitLede(fact)
                      return (
                        <li key={i} className="flex gap-2.5 text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                          <Feather size={14} style={{ color: 'var(--accent-400)' }} className="flex-shrink-0 mt-0.5"/>
                          <span>
                            <strong style={{ color: 'var(--text-primary)' }}>{lede}</strong>{rest ? ' ' + rest : ''}
                          </span>
                        </li>
                      )
                    })}
                  </ul>
                )}
                <p className="text-xs pt-2 border-t border-surface-700" style={{ color: 'var(--text-tertiary)' }}>
                  Cornell Lab of Ornithology
                  {profile.aab_url && (
                    <> ·{' '}
                      <a href={profile.aab_url} target="_blank" rel="noopener noreferrer"
                         className="hover:text-accent" style={{ color: 'var(--accent-600)' }}>View on All About Birds →</a>
                    </>
                  )}
                </p>
              </div>
            </CollapsibleCard>
          )}

          {/* Calls & Songs */}
          <CollapsibleCard id="profile:calls-songs" fallbackOpen={true} title="Example Calls & Songs" icon={Mic}>
            <div className="p-5">
              {calls.length > 0
                ? <div>
                    {calls.map((call, i) => <CallPlayer key={i} call={call} callUrl={call.stream_url}/>)}
                    <p className="text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>Recordings from iNaturalist community. Licenses vary.</p>
                  </div>
                : <div className="text-center py-4">
                    <p className="text-gray-500 text-sm mb-3">
                      {profile.enrichment_complete ? 'No sounds found.' : 'Sounds not yet fetched.'}
                    </p>
                    <button onClick={handleEnrich} disabled={enriching}
                            className="btn-primary flex items-center gap-1.5 mx-auto">
                      <RefreshCw size={14} className={enriching ? 'animate-spin' : ''}/> Fetch Sounds
                    </button>
                  </div>
              }
            </div>
          </CollapsibleCard>

        </>)}

        {activeTab === 'range' && (<>

          {/* Range map — only when enabled in Settings, and never for the
              "Bat" profile (no species range exists to show — see
              BirdProfileOut.is_bat) */}
          {profile.is_bat
            ? null
            : profile.range_maps_enabled
            ? (
              <EbirdRangeMap
                profileId={profile.id}
                speciesCode={profile.ebird_species_code}
                commonName={profile.common_name}
                rangeMapUrl={profile.range_map_url}
                rangeMapSource={profile.range_map_source}
                enabledSources={enabledSources}
                sourceOrder={sourceOrder}
                onProfileUpdate={setProfile}
              />
            ) : (
              <div className="card p-4 text-center text-xs text-gray-600 flex items-center justify-center gap-2">
                <span>Range maps are disabled.</span>
                <a href="/settings?tab=experimental" className="text-chirp-500 hover:underline">Turn on in Settings → Experimental</a>
              </div>
            )
          }

          {/* Observation heatmap — only when enabled in Settings */}
          {profile.observation_heatmap_enabled && profile.inaturalist_id && (
            <ObservationMap taxonId={profile.inaturalist_id} commonName={profile.common_name}/>
          )}

          {/* iNaturalist photo gallery */}
          {Array.isArray(profile.extra_photos) && profile.extra_photos.length > 0 && (
            <PhotoGallery photos={profile.extra_photos} onRefresh={handleEnrich} refreshing={enriching}/>
          )}

        </>)}

        {activeTab === 'yourdata' && (<>

          {/* Recordings for this species */}
          <CollapsibleCard id="profile:recordings" title="Recordings" icon={FileAudio} fallbackOpen={false}>
            <BirdRecordings commonName={profile.common_name} profileLabel={profile.label}/>
          </CollapsibleCard>

          <HaikuboxSpeciesLink commonName={profile.common_name}/>

          {/* User-submitted photos */}
          <CollapsibleCard id="profile:user-photos" title="Photos" icon={Camera} fallbackOpen={false}>
            <BirdPhotoGallery profileId={profile.id} commonName={profile.common_name} currentUser={currentUser}/>
          </CollapsibleCard>

          {/* Notes / Comments */}
          <CollapsibleCard id="profile:notes" fallbackOpen={false} title="Notes" icon={StickyNote}>
            <div className="p-4">
              <Comments
                fetchFn={() => api.birds.comments(profile.id)}
                postFn={(body, author) => api.birds.postComment(profile.id, body, author)}
                deleteFn={(cid) => api.birds.deleteComment(profile.id, cid)}
                updateFn={(cid, body) => api.birds.updateComment(profile.id, cid, body)}
                currentUser={currentUser}
                placeholder="Add a note about this species — observations, habitat, equipment used…"
                emptyText="No notes yet. Be the first to add one!"
              />
            </div>
          </CollapsibleCard>

        </>)}

        {activeTab === 'reference' && (<>

          {/* Taxonomy */}
          <CollapsibleCard id="profile:taxonomy" fallbackOpen={true} title="Taxonomy">
            <div className="p-4 space-y-2 text-sm">
              {[
                ['Common Name', profile.common_name],
                ['Scientific Name', profile.scientific_name],
                ['Order', profile.order_name],
                ['Family', profile.family_name],
                ['eBird Code', profile.ebird_species_code],
                ['iNat Taxon ID', profile.inaturalist_id ? String(profile.inaturalist_id) : null],
              ].filter(([,v]) => v).map(([k,v]) => (
                <div key={k} className="flex justify-between gap-2">
                  <span className="text-gray-500 flex-shrink-0">{k}</span>
                  <span className="text-gray-200 text-right">{v}</span>
                </div>
              ))}
            </div>
          </CollapsibleCard>

          {/* Conservation */}
          {profile.conservation_status && (
            <CollapsibleCard id="profile:conservation" fallbackOpen={true} title="Conservation" icon={Shield}>
              <div className="p-4">
                <ConsBadge status={profile.conservation_status} authority={profile.conservation_authority}/>
              </div>
            </CollapsibleCard>
          )}

          {/* External links */}
          <CollapsibleCard id="profile:external-resources" fallbackOpen={false} title="External Resources">
            <div className="p-4 space-y-1">
              {[
                profile.ebird_species_code && [`https://ebird.org/species/${profile.ebird_species_code}`, '🦅 Cornell eBird'],
                profile.inaturalist_url && [profile.inaturalist_url, '🌿 iNaturalist'],
                profile.ebird_species_code && [`https://search.macaulaylibrary.org/catalog?taxonCode=${profile.ebird_species_code}&mediaType=audio`, '🎵 Macaulay Library'],
                profile.common_name && [`https://www.allaboutbirds.org/guide/${profile.common_name.replace(/ /g,'_')}`, '🔭 All About Birds'],
                profile.description_source && [profile.description_source, '📖 Wikipedia'],
              ].filter(Boolean).map(([href, label]) => (
                <a key={label} href={href} target="_blank" rel="noopener noreferrer"
                   className="flex items-center gap-2 text-sm text-chirp-500 hover:text-chirp-400 py-1.5 transition-colors">
                  {label} <ExternalLink size={11}/>
                </a>
              ))}
            </div>
          </CollapsibleCard>

        </>)}

          <button onClick={handleEnrich} disabled={enriching}
                  className="btn-secondary w-full flex items-center justify-center gap-1.5">
            <RefreshCw size={14} className={enriching ? 'animate-spin' : ''}/>
            {enriching ? 'Refreshing…' : 'Refresh All Data'}
          </button>

        </div>
      </div>
    </div>
  )
}
