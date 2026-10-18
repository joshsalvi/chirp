import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import { Link, useLocation, useNavigationType, useSearchParams } from 'react-router-dom'
import { useTz } from '../lib/time'
import { Search, Mic, Activity, Upload, Trash2, SlidersHorizontal, X, LayoutGrid, List as ListIcon, ChevronDown, ChevronUp, Play, Pause, Sparkles, Archive, CheckSquare, Square, MoreHorizontal, RefreshCw, AudioLines, Bookmark } from 'lucide-react'
import ManualUpload from './ManualUpload'
import { confBadgeClass } from '../lib/detectionColors'
import { api, mediaUrl, clearApiCache } from '../lib/api'
import { savePageState, loadPageState } from '../lib/pageState'
import { useDateRangeFilter, DateRangeFilter } from './DateRangeFilter'
import { BirdIcon, BatIcon } from './BirdBatIcons'

// Time of day (site time zone): presets plus custom from/to.
const TIME_PRESETS = [
  ['', 'Any time'], ['04:00-08:00', 'Dawn (4–8 am)'], ['06:00-12:00', 'Morning (6 am–noon)'],
  ['12:00-17:00', 'Afternoon (noon–5 pm)'], ['17:00-21:00', 'Evening (5–9 pm)'], ['21:00-04:00', 'Night (9 pm–4 am)'],
]
function TimeOfDayFilter({ from, to, onChange }) {
  const key = from || to ? `${from || '00:00'}-${to || '24:00'}` : ''
  const preset = TIME_PRESETS.some(([k]) => k === key) ? key : '__custom__'
  const [custom, setCustom] = useState(preset === '__custom__')
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <select className="input w-44 text-sm" aria-label="Time of day" value={custom ? '__custom__' : key}
              onChange={e => {
                const v = e.target.value
                if (v === '__custom__') { setCustom(true); onChange(from || '06:00', to || '09:00'); return }
                setCustom(false)
                const [a, b] = v ? v.split('-') : [null, null]
                onChange(a, b)
              }}>
        {TIME_PRESETS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        <option value="__custom__">Custom times…</option>
      </select>
      {custom && (
        <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-tertiary)' }}>
          <input type="time" className="input text-sm py-1 w-28" aria-label="From" value={from || ''} onChange={e => onChange(e.target.value, to)}/>
          to
          <input type="time" className="input text-sm py-1 w-28" aria-label="To" value={to || ''} onChange={e => onChange(from, e.target.value)}/>
        </span>
      )}
    </div>
  )
}

const STATE_KEY = 'recordings_list'

function SpectrogramThumb({ recordingId }) {
  const [visible, setVisible] = useState(false)
  const [loaded, setLoaded]   = useState(false)
  const [err, setErr]         = useState(false)
  const rootRef = useRef(null)
  // "&tv=2" (thumbnail-version) busts the BROWSER's own cache, not just
  // the server's file cache. These responses are served with
  // immutable/30-day Cache-Control headers — changing the server-side
  // rendering (dropping detection overlays for thumbnails) doesn't help
  // if this exact URL was already loaded once before, since the browser
  // won't even re-request it for a month regardless of what the server
  // would now return. Bump this number again if the thumbnail rendering
  // ever changes in the future.
  const src = mediaUrl(`/api/v1/recordings/${recordingId}/spectrogram?thumb=true&tv=2`)

  useEffect(() => {
    const el = rootRef.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); obs.disconnect() } },
      { rootMargin: '200px' }
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  return (
    <div ref={rootRef} className="absolute inset-0">
      {!loaded && !err && <div className="absolute inset-0 skeleton"/>}
      {visible && !err && (
        <img src={src} alt="" loading="lazy" decoding="async"
          className="absolute inset-0 w-full h-full object-cover object-bottom transition-opacity duration-300"
          style={{ opacity: loaded ? 1 : 0 }}
          onLoad={() => setLoaded(true)} onError={() => setErr(true)}/>
      )}
    </div>
  )
}

function ConfBadge({ conf }) {
  if (!conf) return null
  return <span className={`badge ${confBadgeClass(conf)}`}>{(conf * 100).toFixed(0)}%</span>
}

// One row inside a recording's expanded detections panel: species name,
// confidence, a play button, and an Enhanced toggle. Each row owns its own
// <audio> element and play/enhanced state so multiple expanded rows across
// the page don't interfere with each other.
function DetectionClipRow({ recordingId, det, hasAudio = true }) {
  const [playing, setPlaying] = useState(false)
  const [enhanced, setEnhanced] = useState(true)
  const audioRef = useRef(null)

  const togglePlay = (e) => {
    e.preventDefault(); e.stopPropagation()
    const a = audioRef.current
    if (!a) return
    if (playing) { a.pause(); setPlaying(false) }
    else { a.play().catch(() => {}); setPlaying(true) }
  }

  const toggleEnhanced = (e) => {
    e.preventDefault(); e.stopPropagation()
    setEnhanced(en => !en)
    setPlaying(false)   // clip is short — just restart rather than preserve position
  }

  return (
    <div className="flex items-center gap-2 py-1.5 px-2 rounded-lg" style={{ background: 'var(--bg-card)' }}>
      {det.bird_photo_url ? (
        <img src={mediaUrl(det.bird_photo_url)} alt="" className="w-6 h-6 rounded-md object-cover flex-shrink-0"
             onError={e => { e.target.style.display = 'none' }}/>
      ) : (
        <div className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0" style={{ background: 'var(--bg-raised)' }}>
          <BirdIcon size={12} style={{ color: 'var(--text-tertiary)' }}/>
        </div>
      )}
      <span className="text-xs font-medium truncate flex-1" style={{ color: 'var(--text-primary)', minWidth: 0 }}>
        {det.common_name}
      </span>
      <ConfBadge conf={det.confidence}/>
      <span className="text-xs flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
        {(det.start_time || 0).toFixed(1)}s
      </span>
      <button onClick={togglePlay}
              className="text-xs flex items-center gap-0.5 flex-shrink-0 hover:opacity-80 transition-opacity"
              style={{ color: 'var(--accent)' }}
              disabled={!hasAudio}>
        {playing ? <Pause size={11}/> : <Play size={11}/>}
      </button>
      {hasAudio && (
        <button onClick={toggleEnhanced}
                className={`flex-shrink-0 text-xs flex items-center gap-0.5 transition-colors ${
                  enhanced ? 'text-chirp-400' : 'text-gray-500 hover:text-gray-300'
                }`}>
          <Sparkles size={11}/>
        </button>
      )}
      {hasAudio && (
        <audio ref={audioRef}
               src={enhanced ? api.recordings.clipEnhancedUrl(recordingId, det.id) : api.recordings.clipUrl(recordingId, det.id)}
               onEnded={() => setPlaying(false)}
               preload="none"/>
      )}
    </div>
  )
}

const PAGE_SIZES = [6, 12, 24, 48]
const LIST_PAGE_SIZES = [25, 50, 100, 200]

export default function RecordingsList() {
  const location  = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()

  // Optional source filter, set via URL query params — e.g. linked from a
  // Haikubox device card ("View its detections") or a future bat-specific
  // entry point. Read once on mount per navigation rather than kept in
  // page-state localStorage: this is meant to be an explicit, intentional
  // navigation (clicking a specific link), not a sticky preference that
  // should persist across unrelated visits to the page.
  const filterDeviceId = searchParams.get('device_id') || null
  const filterIsBat = searchParams.has('is_bat') ? searchParams.get('is_bat') === 'true' : null
  const filterNoDetections = searchParams.get('no_detections') === 'true'
  const filterInterference = searchParams.has('flag_interference') ? searchParams.get('flag_interference') === 'true' : null
  const filterLiveSession = searchParams.get('is_live_session') === 'true'
  const filterMultiSpecies = searchParams.get('multi_species') === 'true'
  const filterSaved = searchParams.get('saved') === 'true'
  const filterTimeFrom = searchParams.get('time_from') || null
  const filterTimeTo = searchParams.get('time_to') || null
  const setTimeOfDay = (a, b) => {
    setPage(0)
    setSearchParams(prev => {
      const n = new URLSearchParams(prev)
      if (a) n.set('time_from', a); else n.delete('time_from')
      if (b) n.set('time_to', b); else n.delete('time_to')
      return n
    }, { replace: true })
  }

  // Only show the "Bats only" filter toggle when bat detection is actually
  // enabled — surfacing a filter for a feature that's off would be
  // confusing clutter for the vast majority of deployments that don't use it.
  const [batDetectionEnabled, setBatDetectionEnabled] = useState(false)

  // Device filter dropdown options. Excludes Haikubox specifically —
  // its recordings are unconditionally hard-excluded from this feed
  // (see list_recordings' haikubox_detection_id filter and the dedicated
  // /haikubox page above), so listing it here would be a dead option
  // that always returns zero results. Bird Buddy devices ARE included,
  // but only the ones actually enabled: if Bird Buddy sync is off
  // entirely, or a specific feeder isn't in bird_buddy_selected_feeders
  // (non-empty selection = sync only those feeders), that device won't
  // ever receive new recordings — same "would be a dead/misleading
  // option" reasoning as the Haikubox exclusion, just per-feeder instead
  // of per-integration. Pi devices have no such enabled/disabled
  // concept in this codebase, so they're always included.
  const [deviceOptions, setDeviceOptions] = useState([])
  useEffect(() => {
    Promise.all([api.devices.list(), api.settings.get()])
      .then(([devs, s]) => {
        setBatDetectionEnabled(!!s.bat_detection_enabled)
        const bbEnabled = !!s.bird_buddy_enabled
        const bbSelected = s.bird_buddy_selected_feeders || []
        setDeviceOptions((devs || []).filter(d => {
          if (d.birdnet_backend === 'haikubox') return false
          if (d.birdnet_backend === 'bird_buddy') {
            if (!bbEnabled) return false
            if (bbSelected.length > 0 && !bbSelected.includes(d.bird_buddy_feeder_id)) return false
          }
          return true
        }))
      })
      .catch(() => {})
  }, [])

  const setFilterDeviceId = useCallback((id) => {
    setPage(0)
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      if (id) next.set('device_id', id)
      else next.delete('device_id')
      return next
    })
  }, [setSearchParams])

  // Back/Forward (a POP, also a reload) returns to the page as it was: page,
  // filters, date range, search and scroll. Opening Recordings any other
  // way (tab bar, menu, a link) starts fresh on page 1, keeping only the
  // grid/list view and page size. Filters in the URL come back with the
  // history entry itself. Read once: the save effects below overwrite it
  // on the first render.
  const navType = useNavigationType()
  const [saved] = useState(() => {
    const st = loadPageState(STATE_KEY, 12 * 60 * 60 * 1000)
    if (navType === 'POP' || !st) return st
    return { viewMode: st.viewMode, limit: st.limit, customLimit: st.customLimit }
  })
  const dateFilter = useDateRangeFilter(saved?.date)
  const { resolveRange, datePreset, customStart, customEnd } = dateFilter
  // ?species=Name (from a bird profile or the digest) sets the species filter.
  const urlSpecies = searchParams.get('species')
  const [page,        setPage]        = useState(urlSpecies != null ? 0 : (saved?.page || 0))
  const [viewMode,    setViewMode]    = useState(saved?.viewMode || 'grid')   // 'grid' | 'list'
  const [limit,       setLimit]       = useState(saved?.limit || 24)
  const [customLimit, setCustomLimit] = useState(saved?.customLimit || '')
  const [search,      setSearch]      = useState(urlSpecies ?? (saved?.search || ''))
  useEffect(() => {
    if (urlSpecies != null) { setSearch(urlSpecies); setPage(0) }
  }, [urlSpecies])
  const [totalCount,  setTotalCount]  = useState(null)
  const [minConf,     setMinConf]     = useState(saved?.minConf || '')
  const [customConf,  setCustomConf]  = useState(saved?.customConf || '')
  const [showCustomConf, setShowCustomConf] = useState(false)

  // Bulk selection
  const [selected,    setSelected]    = useState(new Set())
  const [bulkLoading, setBulkLoading] = useState(false)
  const [bulkResult,  setBulkResult]  = useState(null)
  const [showFilters, setShowFilters] = useState(saved?.showFilters || false)

  const [recordings, setRecordings] = useState([])
  const fetchIdRef = useRef(0)
  const [loading,    setLoading]    = useState(true)
  const [loadError,  setLoadError]  = useState(null)
  const [retryTick,  setRetryTick]  = useState(0)
  const [showUpload, setShowUpload] = useState(false)
  const [deleting,   setDeleting]   = useState(null)
  const [expandedIds, setExpandedIds] = useState(() => new Set())
  const toggleExpanded = (e, id) => {
    e.preventDefault(); e.stopPropagation()
    setExpandedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }
  const { fmtAgo }  = useTz()
  const scrollRef   = useRef(null)

  // Small, low-emphasis link to the dedicated Haikubox page — only shown
  // if Haikubox is actually in use (at least one detection exists), so
  // this stays invisible for anyone not using one. Deliberately NOT a
  // count or list inline here — that's what the dedicated page is for;
  // this is just a doorway, per explicit direction that Haikubox data
  // shouldn't distract from the main Chirp device recordings feed.
  const [haikuboxTotal, setHaikuboxTotal] = useState(null)
  useEffect(() => {
    api.recordings.haikuboxSummary()
      .then(s => setHaikuboxTotal(s.total || 0))
      .catch(e => {
        // Previously fully silent — a genuine failure here (anything
        // other than the already-fixed 401 case, e.g. a transient
        // network/server error) looked identical to "no Haikubox
        // detections exist," with zero way to tell the difference short
        // of guessing. Logged rather than shown as a visible error
        // banner, since this doorway is deliberately low-emphasis and
        // shouldn't become an alarming error box over one failed fetch.
        console.warn('haikuboxSummary() failed — Haikubox banner will not show even if detections exist:', e)
      })
  }, [])

  // Save state whenever relevant values change. limit/customLimit must be
  // in the deps even though they're "just" read here — otherwise changing
  // ONLY the per-page selector (without also changing page/search/etc.)
  // doesn't re-run this effect, so the saved state silently keeps whatever
  // limit/customLimit was in effect last time one of the OTHER deps changed.
  // Navigating away and back would then restore a stale per-page choice.
  useEffect(() => {
    savePageState(STATE_KEY, { ...stateNow(), scrollTop: scrollRef.current?.closest('main')?.scrollTop ?? saved?.scrollTop })
  }, [page, limit, customLimit, search, minConf, customConf, showFilters, viewMode, datePreset, customStart, customEnd, location.search])

  // Restore scroll after load. scrollRef itself is just a marker element
  // (see the root <div> below) — the scroll container is <main>
  // in App.jsx, found via closest('main') rather than assumed to be
  // scrollRef.current itself. Making this component's own root a second,
  // competing scroll container (the previous approach: h-full +
  // overflowY:'auto' on the root div) trapped content within whatever
  // height that root happened to compute to, clipping it at the
  // viewport's edge instead of letting <main> scroll to reveal the rest
  // — confirmed as the cause of a reported "list mode cuts off
  // content" bug: every other page in the app uses plain `page-root`
  // with no special scroll handling, relying on <main>'s existing
  // overflow-y-auto, and only this one component had its own competing
  // scroll setup.
  useEffect(() => {
    const scrollEl = scrollRef.current?.closest('main')
    if (!loading && saved?.scrollTop && scrollEl) {
      setTimeout(() => { if (scrollEl) scrollEl.scrollTop = saved.scrollTop }, 60)
    }
  }, [loading])

  // Track scroll position continuously. Same limit/customLimit fix as above —
  // without them in deps, the listener closure goes stale and overwrites the
  // saved state with an old limit/customLimit on every scroll event.
  useEffect(() => {
    const el = scrollRef.current?.closest('main')
    if (!el) return
    const onScroll = () => savePageState(STATE_KEY, { ...stateNow(), scrollTop: el.scrollTop })
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [page, limit, customLimit, search, minConf, customConf, showFilters, viewMode, datePreset, customStart, customEnd, location.search])

  // Single source of truth for the page size in effect — was
  // previously recomputed inline in 6 different places with inconsistent
  // fallback defaults (24, 10, 8), which is the root cause of "changing
  // per-page in list mode doesn't work": clicking a list-mode button (25/50/
  // 100/200) correctly clears customLimit, but if the user had typed
  // anything into the Custom box first, that stale value could win in some
  // of the 6 inline calculations and not others, depending on which fallback
  // default happened to apply. Consolidating to one memoized value makes
  // every consumer agree, by construction.
  const effectiveLimit = useMemo(() => {
    const fallback = viewMode === 'list' ? 50 : 24
    if (!customLimit) return limit
    const parsed = parseInt(customLimit, 10)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
  }, [customLimit, limit, viewMode])

  // Date preset/custom values feed into resolveRange's own memoized
  // identity (see DateRangeFilter.jsx's useCallback deps), so depending
  // on resolveRange itself in the data-loading effect below is enough to
  // correctly re-fetch whenever the date filter actually changes — same
  // pattern already verified working on HaikuboxDetections.jsx. Page
  // reset is handled separately here (rather than inline at each preset
  // button, which live inside the shared component) so applying a
  // narrower range while on page 3+ doesn't land on an empty out-of-range
  // page, matching every other filter on this page already resetting to
  // page 0 on change.
  // Everything needed to come back to this page as it was.
  function stateNow() {
    return { page, limit, customLimit, search, minConf, customConf, showFilters, viewMode,
             date: { datePreset, customStart, customEnd }, qs: location.search }
  }

  // Skips the first run: on mount it reset a restored page number to 1.
  const dateMounted = useRef(false)
  useEffect(() => {
    if (!dateMounted.current) { dateMounted.current = true; return }
    setPage(0)
  }, [datePreset, customStart, customEnd])

  useEffect(() => {
    // Debounced + guarded against stale out-of-order responses. Before
    // this, every single filter change — including each keystroke while
    // typing a species search, and the several state resets "Clear" does
    // in one click — fired its own separate, immediate network request.
    // Rapid changes queued up multiple in-flight requests; whichever
    // happened to resolve LAST won, but a slower earlier request
    // resolving AFTER a faster later one could flicker the list back to
    // stale data. Debouncing coalesces rapid changes into one request;
    // the requestId guard drops any response that isn't from the most
    // recent request fired, regardless of arrival order.
    const requestId = ++fetchIdRef.current
    setLoading(true)
    const timer = setTimeout(() => {
      const p = { skip: page * effectiveLimit, limit: effectiveLimit }
      if (search)  p.species = search
      if (customConf && !isNaN(parseFloat(customConf))) p.min_confidence = (parseFloat(customConf) / 100).toFixed(2)
      else if (minConf) p.min_confidence = minConf
      if (filterDeviceId) p.device_id = filterDeviceId
      if (filterIsBat !== null) p.is_bat = filterIsBat
      if (filterNoDetections) p.no_detections = true
      if (filterInterference !== null) p.flag_interference = filterInterference
      if (filterLiveSession) p.is_live_session = true
      if (filterMultiSpecies) p.multi_species = true
      if (filterSaved) p.saved = true
      if (filterTimeFrom) p.time_from = filterTimeFrom
      if (filterTimeTo) p.time_to = filterTimeTo
      const { start, end } = resolveRange()
      if (start) p.start = start
      if (end) p.end = end
      api.recordings.list(p)
        .then(({ items, total }) => {
          if (requestId !== fetchIdRef.current) return  // a newer request superseded this one
          setRecordings(items)
          if (total !== null) setTotalCount(total)
          setLoadError(null)
        })
        .catch(e => {
          if (requestId !== fetchIdRef.current) return
          // Previously silently swallowed (.catch(() => {})) — the
          // symptom this caused: any failure here (an expired auth token
          // being the case found, but any other transient failure
          // would behave identically) left the page showing whatever had
          // last loaded successfully, with no indication anything was
          // wrong, no matter what filter/page-size the person clicked
          // afterward. api.recordings.list() now redirects to /login on a
          // genuine 401 on its own, so reaching this catch means something
          // else went wrong — surface it rather than fail invisibly again.
          setLoadError(e.message || 'Failed to load recordings.')
        })
        .finally(() => { if (requestId === fetchIdRef.current) setLoading(false) })
    }, 250)
    return () => clearTimeout(timer)
  }, [search, minConf, customConf, page, effectiveLimit, filterDeviceId, filterIsBat, filterNoDetections, filterInterference, filterLiveSession, filterMultiSpecies, filterSaved, filterTimeFrom, filterTimeTo, resolveRange, retryTick])

  const handleDelete = async (e, rec) => {
    e.preventDefault(); e.stopPropagation()
    if (!window.confirm(`Delete "${rec.top_species || rec.filename}"?`)) return
    setDeleting(rec.id)
    try {
      await api.recordings.delete(rec.id, { deleteFiles: true, hardDelete: true })
      setRecordings(p => p.filter(r => r.id !== rec.id))
    } catch (err) { alert('Delete failed: ' + err.message) }
    setDeleting(null)
  }

  return (
    <div className="page-root flex flex-col" ref={scrollRef}>

      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h1 className="section-title">
            {filterIsBat === true ? 'Bat Detections'
              : filterDeviceId ? 'Filtered Recordings'
              : 'Recordings'}
          </h1>
          <p className="section-subtitle">
            {!loading && `${recordings.length} on page ${page + 1}`}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* View mode toggle */}
          <div className="flex items-center rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-subtle)', height: 34 }}>
            <button
              onClick={() => { setViewMode('grid'); setPage(0); if (limit > 48) { setLimit(24); setCustomLimit('') } }}
              title="Grid view — spectrogram thumbnails"
              className={`seg-btn px-2.5 ${viewMode === 'grid' ? 'active' : ''}`}>
              <LayoutGrid size={14}/>
            </button>
            <button
              onClick={() => { setViewMode('list'); setPage(0); if (limit < 48) { setLimit(50); setCustomLimit('') } }}
              title="Compact list view — no thumbnails, many more recordings per page"
              className={`seg-btn px-2.5 ${viewMode === 'list' ? 'active' : ''}`}>
              <ListIcon size={14}/>
            </button>
          </div>
          <DateRangeFilter {...dateFilter}/>
          <button onClick={() => setShowFilters(s => !s)}
            className="btn-icon" title="Filters"
            style={showFilters ? { borderColor: 'var(--border-focus)', color: 'var(--accent-400)' } : {}}>
            <SlidersHorizontal size={15}/>
          </button>
          <button onClick={() => setShowUpload(true)} className="btn-primary">
            <Upload size={13}/> <span className="hidden sm:inline">Upload</span>
          </button>
        </div>
      </div>

      {/* Low-emphasis doorway to the dedicated Haikubox page — only
          rendered when at least one Haikubox detection exists, so this
          stays invisible for anyone not using one. Deliberately not a
          count/list inline here; that's what the dedicated page is for. */}
      {!!haikuboxTotal && (
        <Link to="/haikubox"
              className="flex items-center justify-between gap-2 px-3.5 py-2 rounded-xl mb-4 text-xs transition-colors"
              style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
          <span>📡 {haikuboxTotal.toLocaleString()} Haikubox detection{haikuboxTotal === 1 ? '' : 's'} (no audio) — viewed separately</span>
          <span style={{ color: 'var(--accent-400)' }}>View →</span>
        </Link>
      )}

      {/* Active source filter banner — shown when navigated here via a
          filtered link (e.g. a Haikubox device card's "View detections",
          or a bat-detections entry point). Lets the person see what
          they're looking at and clear it without losing their place via
          back-button navigation, which wouldn't be obvious otherwise
          since the filter lives silently in the URL query string.

          Deliberately does NOT trigger for filterIsBat === false: that's
          the in-page "Birds only" toggle's own state (see Source filter
          below), which already has its own highlighted-button affordance —
          nothing links here with `?is_bat=false` as a cross-page entry
          point, so treating it as one produced an empty banner with no
          message text, just a floating "Clear filter". Styled to match the
          subtler Haikubox banner above rather than a loud full-width
          highlight border, since this is informational, not a warning. */}
      {/* Species filter set by a link (?species=, from a bird profile or the digest) */}
      {urlSpecies != null && search && (
        <div className="flex items-center justify-between gap-2 px-3.5 py-2 rounded-xl mb-4 text-xs"
             style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
          <span>Showing recordings of <strong style={{ color: 'var(--text-primary)' }}>{search}</strong>.</span>
          <button className="flex items-center gap-1 flex-shrink-0 hover:underline" style={{ color: 'var(--accent-400)' }}
                  onClick={() => {
                    setSearch(''); setPage(0)
                    setSearchParams(prev => { const n = new URLSearchParams(prev); n.delete('species'); return n }, { replace: true })
                  }}>
            <X size={13}/> Clear filter
          </button>
        </div>
      )}
      {(filterDeviceId || filterIsBat === true) && (
        <div className="flex items-center justify-between gap-2 px-3.5 py-2 rounded-xl mb-4 text-xs transition-colors"
             style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
          <span>
            {filterIsBat === true && 'Showing bat-echolocation detections only.'}
            {filterDeviceId && !filterIsBat && (() => {
              const dev = deviceOptions.find(d => d.id === filterDeviceId)
              return `Showing detections from ${dev ? dev.name : 'one device'} only.`
            })()}
          </span>
          <Link to="/recordings" className="flex items-center gap-1 flex-shrink-0 hover:underline"
                style={{ color: 'var(--accent-400)' }}>
            <X size={13}/> Clear filter
          </Link>
        </div>
      )}

      {/* Filters */}
      {showFilters && (
        <div className="card p-3 mb-4 animate-slide-down space-y-3">
          <div className="flex flex-wrap gap-2">
            <div className="relative flex-1 min-w-36">
              <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-tertiary)' }}/>
              <input className="input pl-8 text-sm" placeholder="Filter by species…"
                     value={search} onChange={e => {
                       setSearch(e.target.value); setPage(0)
                       if (urlSpecies != null) setSearchParams(prev => { const n = new URLSearchParams(prev); n.delete('species'); return n }, { replace: true })
                     }}/>
            </div>
            {/* Device: populated from all standard + Bird Buddy devices (Haikubox excluded — see deviceOptions fetch above) */}
            {deviceOptions.length > 0 && (
              <select className="input w-40 text-sm" value={filterDeviceId || ''}
                      onChange={e => setFilterDeviceId(e.target.value || null)}>
                <option value="">All devices</option>
                {deviceOptions.map(d => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            )}
            {/* Confidence: preset OR custom numeric input */}
            <select className="input w-36 text-sm" value={showCustomConf ? '__custom__' : minConf}
                    onChange={e => {
                      if (e.target.value === '__custom__') { setShowCustomConf(true); setMinConf(''); }
                      else { setMinConf(e.target.value); setCustomConf(''); setShowCustomConf(false); setPage(0) }
                    }}>
              <option value="">All confidence</option>
              <option value="0.25">≥ 25%</option>
              <option value="0.5">≥ 50%</option>
              <option value="0.75">≥ 75%</option>
              <option value="__custom__">Custom…</option>
            </select>
            {showCustomConf && (
              <div className="flex items-center gap-1">
                <input type="number" min={0} max={100} step={1} placeholder="e.g. 60"
                  className="input w-24 text-sm"
                  value={customConf}
                  onChange={e => { setCustomConf(e.target.value); setPage(0) }}
                  autoFocus/>
                <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>%</span>
              </div>
            )}
            <TimeOfDayFilter from={filterTimeFrom} to={filterTimeTo} onChange={setTimeOfDay}/>
            {(search || minConf || customConf || filterDeviceId || filterNoDetections || filterTimeFrom || filterTimeTo || filterSaved) && (
              <button className="btn-ghost text-sm" onClick={() => {
                setSearch(''); setMinConf(''); setCustomConf(''); setShowCustomConf(false); setFilterDeviceId(null); setPage(0)
                setSearchParams(prev => { const next = new URLSearchParams(prev); ['no_detections', 'time_from', 'time_to', 'saved'].forEach(k => next.delete(k)); return next })
              }}>
                <X size={12}/> Clear
              </button>
            )}
          </div>
          {/* Source filter — birds only + bats only */}
          <div className="flex items-center gap-2 pt-1 border-t flex-wrap" style={{ borderColor: 'var(--border-subtle)' }}>
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Source:</span>
            {/* Birds only */}
            <button
              onClick={() => {
                setPage(0)
                setSearchParams(prev => {
                  const next = new URLSearchParams(prev)
                  if (filterIsBat === false) next.delete('is_bat')
                  else next.set('is_bat', 'false')
                  return next
                })
              }}
              className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 whitespace-nowrap"
              style={filterIsBat === false
                ? { background: 'rgba(34,211,238,.15)', color: '#22d3ee', border: '1px solid rgba(34,211,238,.4)' }
                : { background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
              <BirdIcon size={13}/> Birds only
            </button>
            {/* Bats only */}
            {batDetectionEnabled && (
              <button
                onClick={() => {
                  setPage(0)
                  setSearchParams(prev => {
                    const next = new URLSearchParams(prev)
                    if (filterIsBat === true) next.delete('is_bat')
                    else next.set('is_bat', 'true')
                    return next
                  })
                }}
                className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 whitespace-nowrap"
                style={filterIsBat === true
                  ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)', border: '1px solid var(--border-default)' }
                  : { background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
                <BatIcon size={13}/> Bats only
              </button>
            )}
            {/* Unknown — recordings with nothing at the display threshold.
                The list hides finished device recordings like this unless
                this filter is on (see list_recordings). */}
            <button
              title="Recordings with no detection at your display threshold. They're hidden from the list unless this is on."
              onClick={() => {
                setPage(0)
                setSearchParams(prev => {
                  const next = new URLSearchParams(prev)
                  if (filterNoDetections === true) next.delete('no_detections')
                  else next.set('no_detections', 'true')
                  return next
                })
              }}
              className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 whitespace-nowrap"
              style={filterNoDetections === true
                ? { background: 'rgba(248,113,113,.15)', color: '#f87171', border: '1px solid rgba(248,113,113,.4)' }
                : { background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
              Unknown only
            </button>
            {/* Live Detect — recordings saved from a Live Detect session
                (is_live_session), as opposed to the device's own
                continuous background recording. #f97316 matches Live
                Detect's own branding color elsewhere in the app. */}
            <button
              onClick={() => {
                setPage(0)
                setSearchParams(prev => {
                  const next = new URLSearchParams(prev)
                  if (filterLiveSession === true) next.delete('is_live_session')
                  else next.set('is_live_session', 'true')
                  return next
                })
              }}
              className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 whitespace-nowrap"
              style={filterLiveSession === true
                ? { background: 'rgba(249,115,22,.15)', color: '#f97316', border: '1px solid rgba(249,115,22,.4)' }
                : { background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
              <AudioLines size={13}/> Live Detect
            </button>
            {/* Saved: kept out of automatic cleanup (Recording.is_saved). */}
            <button
              onClick={() => {
                setPage(0)
                setSearchParams(prev => {
                  const next = new URLSearchParams(prev)
                  if (filterSaved) next.delete('saved')
                  else next.set('saved', 'true')
                  return next
                })
              }}
              className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 whitespace-nowrap"
              style={filterSaved
                ? { background: 'rgba(250,204,21,.15)', color: '#facc15', border: '1px solid rgba(250,204,21,.4)' }
                : { background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
              <Bookmark size={13}/> Saved
            </button>
            {/* Multiple species — more than one DISTINCT species detected
                in the same recording, not just more than one detection
                (three calls from the same bird doesn't count). */}
            <button
              onClick={() => {
                setPage(0)
                setSearchParams(prev => {
                  const next = new URLSearchParams(prev)
                  if (filterMultiSpecies === true) next.delete('multi_species')
                  else next.set('multi_species', 'true')
                  return next
                })
              }}
              className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 whitespace-nowrap"
              style={filterMultiSpecies === true
                ? { background: 'rgba(167,139,250,.15)', color: '#a78bfa', border: '1px solid rgba(167,139,250,.4)' }
                : { background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
              Multiple species
            </button>
            {/* Interference flag — only meaningful for bat recordings, see
                bat_detector.py's timing-regularity check: a smoothly
                oscillating electrical/mechanical noise source can pass
                the existing FM-sweep and pulse-rate filters, but never
                produces the naturally irregular timing a bat does. */}
            {filterIsBat === true && (
              <button
                onClick={() => {
                  setPage(0)
                  setSearchParams(prev => {
                    const next = new URLSearchParams(prev)
                    if (filterInterference === true) next.delete('flag_interference')
                    else next.set('flag_interference', 'true')
                    return next
                  })
                }}
                title="Bat recordings with unusually regular call timing — a strong tell for electrical/mechanical interference rather than a pass"
                className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 whitespace-nowrap"
                style={filterInterference === true
                  ? { background: 'rgba(251,191,36,.15)', color: '#fbbf24', border: '1px solid rgba(251,191,36,.4)' }
                  : { background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
                ⚡ Possible interference
              </button>
            )}
          </div>
          <div className="flex items-center gap-2 pt-1 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Per page:</span>
            {(viewMode === 'list' ? LIST_PAGE_SIZES : PAGE_SIZES).map(n => (
              <button key={n} onClick={() => { setLimit(n); setCustomLimit(''); setPage(0) }}
                className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all"
                style={(!customLimit && limit === n)
                  ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)', border: '1px solid var(--border-default)' }
                  : { background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
                {n}
              </button>
            ))}
            <div className="flex items-center gap-1">
              <input
                type="number" min="1" max="200" placeholder="Custom"
                value={customLimit}
                onChange={e => { setCustomLimit(e.target.value); setPage(0) }}
                className="input text-xs py-1" style={{ width: 72 }}/>
            </div>
          </div>
        </div>
      )}

      {/* Bulk action bar — shown when at least one recording is selected */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl mb-3 flex-wrap"
             style={{ background: 'rgba(34,211,238,.08)', border: '1px solid rgba(34,211,238,.25)' }}>
          <label className="flex items-center gap-2 cursor-pointer text-sm" style={{ color: 'var(--text-primary)' }}>
            <input type="checkbox" checked={recordings.length > 0 && recordings.every(r => selected.has(r.id))}
              onChange={e => setSelected(e.target.checked ? new Set(recordings.map(r => r.id)) : new Set())}
              className="w-4 h-4 accent-chirp-500"/>
            <span className="font-medium" style={{ color: '#22d3ee' }}>{selected.size} selected</span>
          </label>
          <div className="flex items-center gap-2 flex-wrap">
            {[
              { label: 'Re-analyze', icon: <RefreshCw size={13}/>, color: '#60a5fa', action: 'reanalyze' },
              { label: 'Archive audio', icon: <Archive size={13}/>, color: '#fbbf24', action: 'archive' },
              { label: 'Delete', icon: <Trash2 size={13}/>, color: '#f87171', action: 'delete' },
            ].map(({ label, icon, color, action }) => (
              <button key={action} disabled={bulkLoading}
                onClick={async () => {
                  if (action === 'delete' && !window.confirm(`Delete ${selected.size} recording(s)? This cannot be undone.`)) return
                  setBulkLoading(true); setBulkResult(null)
                  try {
                    const token = localStorage.getItem('chirp_token')
                    clearApiCache()
                    const res = await fetch(`/api/v1/recordings/bulk-${action}`, {
                      method: 'POST',
                      headers: {
                        'Content-Type': 'application/json',
                        ...(token ? { Authorization: `Bearer ${token}` } : {}),
                      },
                      body: JSON.stringify({ ids: [...selected] }),
                    })
                    const d = await res.json()
                    setBulkResult({ ok: res.ok, msg: d.message || d.detail || (res.ok ? 'Done' : 'Failed') })
                    if (res.ok) { setSelected(new Set()); setRetryTick(t => t + 1) }
                  } catch (e) {
                    setBulkResult({ ok: false, msg: e.message })
                  } finally {
                    setBulkLoading(false)
                  }
                }}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                style={{ background: 'var(--bg-raised)', color, border: `1px solid ${color}40` }}>
                {icon} {label}
              </button>
            ))}
            <button onClick={() => setSelected(new Set())}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
                    style={{ color: 'var(--text-tertiary)', border: '1px solid var(--border-subtle)' }}>
              <X size={12}/> Clear
            </button>
          </div>
          {bulkResult && (
            <span className="text-xs ml-auto" style={{ color: bulkResult.ok ? '#4ade80' : '#f87171' }}>
              {bulkResult.msg}
            </span>
          )}
        </div>
      )}

      {/* Recordings — grid or compact list */}
      {loading ? (
        viewMode === 'list' ? (
          <div className="space-y-1">
            {Array.from({ length: Math.min(effectiveLimit, 20) }).map((_, i) => (
              <div key={i} className="h-10 skeleton rounded-lg"/>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {Array.from({ length: Math.min(effectiveLimit, 12) }).map((_, i) => (
              <div key={i} className="card overflow-hidden">
                <div style={{ height: 88 }} className="skeleton"/>
                <div className="p-3 space-y-2">
                  <div className="h-3 skeleton w-3/4"/>
                  <div className="h-2 skeleton w-1/2"/>
                </div>
              </div>
            ))}
          </div>
        )
      ) : loadError ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <Mic size={36} style={{ color: 'var(--text-tertiary)' }}/>
          <p style={{ color: 'var(--text-secondary)' }}>Couldn't load recordings.</p>
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{loadError}</p>
          <button onClick={() => setRetryTick(t => t + 1)} className="btn-secondary text-sm mt-1">
            Retry
          </button>
        </div>
      ) : recordings.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <Mic size={36} style={{ color: 'var(--text-tertiary)' }}/>
          <p style={{ color: 'var(--text-secondary)' }}>
            {search ? 'No recordings match your filter.' : 'No recordings yet.'}
          </p>
        </div>
      ) : viewMode === 'list' ? (
        /* ── Compact list — no spectrogram images, optimized for density ── */
        <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--border-subtle)' }}>
          {recordings.map((rec, i) => (
            <div key={rec.id}>
              <Link to={`/recordings/${rec.id}`}
                    className="list-row flex items-center gap-3 px-3 py-2 group"
                    style={{ borderTop: i === 0 ? 'none' : '1px solid var(--border-subtle)' }}>
                {/* Species photo — tiny, no spectrogram fetch */}
                {rec.top_species_photo_url ? (
                  <img src={mediaUrl(rec.top_species_photo_url)} alt="" loading="lazy"
                       className="w-6 h-6 rounded-md object-cover flex-shrink-0"
                       onError={e => { e.target.style.display = 'none' }}/>
                ) : rec.is_bat ? (
                  <div className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0" style={{ background: 'var(--bg-raised)' }}>
                    <BatIcon size={12} style={{ color: 'var(--text-tertiary)' }}/>
                  </div>
                ) : (
                  <div className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0" style={{ background: 'var(--bg-raised)' }}>
                    <BirdIcon size={12} style={{ color: 'var(--text-tertiary)' }}/>
                  </div>
                )}
                <p className="text-sm font-medium truncate flex-shrink-0" style={{ color: 'var(--text-primary)', minWidth: 140, maxWidth: 220 }}>
                  {rec.top_species || 'Unknown'}
                </p>
                <div className="flex-shrink-0"><ConfBadge conf={rec.max_confidence}/></div>
                <button onClick={(e) => toggleExpanded(e, rec.id)} disabled={!rec.detections?.length}
                  className="text-xs flex-shrink-0 flex items-center gap-0.5 hover:opacity-80 transition-opacity disabled:opacity-40"
                  style={{ color: 'var(--text-tertiary)', minWidth: 60 }}>
                  {expandedIds.has(rec.id) ? <ChevronUp size={11}/> : <ChevronDown size={11}/>}
                  {rec.detections?.length ?? 0} det.
                </button>
                <p className="text-xs truncate flex-1" style={{ color: 'var(--text-tertiary)' }}>
                  {rec.is_saved && <Bookmark size={11} className="inline -mt-0.5 mr-1" style={{ color: '#facc15' }} aria-label="Saved"/>}{rec.is_live_session && <span style={{ color: 'var(--accent-500)' }}>Live Detect · </span>}
                  {fmtAgo(rec.trigger_timestamp)}
                </p>
                <button onClick={(e) => handleDelete(e, rec)} disabled={deleting === rec.id}
                  className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0
                             opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ background: 'rgba(239,68,68,.85)', color: '#fff' }}>
                  <Trash2 size={10}/>
                </button>
              </Link>
              {expandedIds.has(rec.id) && rec.detections?.length > 0 && (
                <div className="flex flex-col gap-1 py-2 px-3" style={{ background: 'var(--bg-raised)' }}>
                  {rec.detections.map(det => (
                    <DetectionClipRow key={det.id} recordingId={rec.id} det={det} hasAudio={rec.has_audio !== false}/>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {recordings.map(rec => (
            <div key={rec.id} className="card-hover group overflow-hidden relative">
              {/* Bulk select checkbox */}
              <label className="absolute top-2 left-2 z-10 cursor-pointer"
                     onClick={e => e.stopPropagation()}>
                <input type="checkbox" checked={selected.has(rec.id)}
                  onChange={e => setSelected(prev => {
                    const n = new Set(prev)
                    e.target.checked ? n.add(rec.id) : n.delete(rec.id)
                    return n
                  })}
                  className="w-4 h-4 accent-chirp-500 opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ opacity: selected.has(rec.id) ? 1 : undefined }}/>
              </label>
              <Link to={`/recordings/${rec.id}`} className="block">
                <div className="relative overflow-hidden" style={{ height: 88, background: '#000' }}>
                  <SpectrogramThumb recordingId={rec.id}/>
                  <div className="absolute top-2 right-2"><ConfBadge conf={rec.max_confidence}/></div>
                  {rec.is_bat && rec.bat_metadata?.likely_interference && (
                    <div className="absolute top-2 left-2 px-1.5 py-0.5 rounded-full text-[10px] font-semibold flex items-center gap-0.5"
                         style={{ background: 'rgba(251,191,36,.9)', color: '#1a1300' }}
                         title="Unusually regular call timing — a strong tell for electrical/mechanical interference rather than a bat pass">
                      ⚡ Interference?
                    </div>
                  )}
                  {rec.top_species_photo_url && (
                    <img src={mediaUrl(rec.top_species_photo_url)} alt={rec.top_species} loading="lazy"
                         className="absolute bottom-2 left-2 w-8 h-8 rounded-full object-cover"
                         style={{ border: '2px solid var(--bg-card)', boxShadow: '0 2px 6px rgba(0,0,0,.4)' }}
                         onError={e => { e.target.style.display = 'none' }}/>
                  )}
                  <button onClick={(e) => handleDelete(e, rec)} disabled={deleting === rec.id}
                    className="absolute bottom-2 right-2 w-6 h-6 rounded-md flex items-center justify-center
                               opacity-0 group-hover:opacity-100 transition-opacity"
                    style={{ background: 'rgba(239,68,68,.85)', color: '#fff' }}>
                    <Trash2 size={11}/>
                  </button>
                </div>
                <div className="p-3">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                      {rec.top_species || 'Unknown'}
                    </p>
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <div className="flex items-center gap-1">
                      {rec.is_bat
                        ? <BatIcon size={10} style={{ color: 'var(--text-tertiary)' }}/>
                        : <BirdIcon size={10} style={{ color: 'var(--text-tertiary)' }}/>}
                      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                        {rec.is_saved && <Bookmark size={11} className="inline -mt-0.5 mr-1" style={{ color: '#facc15' }} aria-label="Saved"/>}{rec.is_live_session && <span style={{ color: 'var(--accent-500)' }}>Live Detect · </span>}
                        {fmtAgo(rec.trigger_timestamp)}
                      </p>
                    </div>
                  </div>
                </div>
              </Link>
              <button onClick={(e) => toggleExpanded(e, rec.id)} disabled={!rec.detections?.length}
                className="w-full flex items-center justify-center gap-1 text-xs py-1.5 transition-opacity disabled:opacity-40 hover:opacity-80"
                style={{ color: 'var(--text-tertiary)', borderTop: '1px solid var(--border-subtle)' }}>
                {expandedIds.has(rec.id) ? <ChevronUp size={11}/> : <ChevronDown size={11}/>}
                {rec.detections?.length ?? 0} detection{rec.detections?.length === 1 ? '' : 's'}
              </button>
              {expandedIds.has(rec.id) && rec.detections?.length > 0 && (
                <div className="flex flex-col gap-1 py-2 px-2" style={{ background: 'var(--bg-raised)', borderTop: '1px solid var(--border-subtle)' }}>
                  {rec.detections.map(det => (
                    <DetectionClipRow key={det.id} recordingId={rec.id} det={det} hasAudio={rec.has_audio !== false}/>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {(recordings.length >= effectiveLimit || page > 0) && (
        <div className="flex justify-center items-center gap-3 pt-6">
          <button className="btn-secondary" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Prev</button>
          <select
            className="input text-sm text-center"
            style={{ width: 110, cursor: 'pointer' }}
            value={page}
            onChange={e => setPage(Number(e.target.value))}
          >
            {(() => {
              const totalPages = totalCount !== null
                ? Math.ceil(totalCount / effectiveLimit)
                : page + 2   // fallback until first load completes
              const pages = Math.max(totalPages, page + 1)
              return Array.from({ length: pages }, (_, i) => (
                <option key={i} value={i}>Page {i + 1}</option>
              ))
            })()}
          </select>
          <button className="btn-secondary" disabled={recordings.length < effectiveLimit} onClick={() => setPage(p => p + 1)}>Next →</button>
        </div>
      )}

      {showUpload && <ManualUpload onClose={() => { setShowUpload(false); setPage(0) }}/>}
    </div>
  )
}
