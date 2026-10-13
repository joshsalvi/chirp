import { useEffect, useState, useCallback } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Search, Radio, ArrowLeft, Info } from 'lucide-react'
import { BirdIcon } from './BirdBatIcons'
import { useTz } from '../lib/time'
import { api } from '../lib/api'
import { useDateRangeFilter, DateRangeFilter } from './DateRangeFilter'

const PAGE_SIZE = 30

/**
 * Dedicated page for Haikubox-sourced detections — deliberately separate
 * from the main Recordings list (see api/recordings.py's
 * list_haikubox_recordings docstring for the full reasoning). Haikubox
 * supplies a species + timestamp record only, never an audio file (see
 * services/haikubox_sync.py), so this page is intentionally simpler than
 * RecordingsList.jsx: no audio player, no spectrogram thumbnails, no
 * grid/list toggle — just a clear, scannable record of what the Haikubox
 * reported, framed as supplemental to (not a replacement for) the
 * Chirp device's own recordings.
 */
export default function HaikuboxDetections() {
  const { fmtTs } = useTz()
  const [searchParams] = useSearchParams()
  const speciesParam = searchParams.get('species') || ''
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [search, setSearch] = useState(speciesParam)
  const [error, setError] = useState(null)

  const dateFilter = useDateRangeFilter()
  const { datePreset, resolveRange } = dateFilter

  const load = useCallback((skip = 0, append = false) => {
    const setBusy = append ? setLoadingMore : setLoading
    setBusy(true)
    setError(null)
    const params = { skip, limit: PAGE_SIZE }
    if (speciesParam) params.species = speciesParam
    const { start, end } = resolveRange()
    if (start) params.start = start
    if (end) params.end = end
    api.recordings.haikuboxList(params)
      .then(({ items: newItems, total: newTotal }) => {
        setItems(prev => append ? [...prev, ...newItems] : newItems)
        setTotal(newTotal)
      })
      .catch(e => setError(e.message || 'Failed to load Haikubox detections'))
      .finally(() => setBusy(false))
  }, [speciesParam, resolveRange])

  // Re-fetch from the top whenever the species deep-link or the resolved
  // date range changes — a date filter change should reset pagination,
  // not append onto whatever was already loaded under the old range.
  useEffect(() => { load(0, false) }, [load])

  // The species URL param scopes the server-side fetch; the date range
  // above does too (both reset pagination via the load() effect). The
  // visible search box below is a separate, simpler client-side substring
  // filter over whatever's already been loaded for the current species/
  // date scope — deliberately not wired back into a server refetch on
  // every keystroke, since this page's job is a quick supplemental
  // glance, not a full search experience.
  const filtered = search.trim()
    ? items.filter(r => (r.top_species || '').toLowerCase().includes(search.trim().toLowerCase()))
    : items

  const hasMore = total !== null && items.length < total

  return (
    <div className="max-w-3xl mx-auto px-4 py-5 space-y-4">
      <div className="flex items-center gap-3">
        <Link to="/recordings" className="p-2 rounded-lg transition-colors" style={{ color: 'var(--text-secondary)' }}>
          <ArrowLeft size={18}/>
        </Link>
        <div className="flex-1">
          <h1 className="text-xl font-semibold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
            <Radio size={18} style={{ color: 'var(--accent-400)' }}/> Haikubox Detections
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
            {speciesParam
              ? `Showing only ${speciesParam} · `
              : ''}
            {total !== null ? `${total.toLocaleString()} detection${total === 1 ? '' : 's'}` : '\u00A0'}
            {speciesParam && (
              <Link to="/haikubox" className="ml-1.5 underline" style={{ color: 'var(--accent-400)' }}>
                show all
              </Link>
            )}
          </p>
        </div>
      </div>

      {/* Explicit framing per product direction: this supplements the
          Chirp device's own recordings, it isn't a parallel primary feed. */}
      <div className="flex items-start gap-2.5 p-3 rounded-xl text-xs"
           style={{ background: 'var(--nav-active-bg)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
        <Info size={14} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--accent-400)' }}/>
        <span>
          These detections come from your Haikubox's own cloud service, not your Chirp device — they have
          no audio recording attached, just a species and timestamp. They supplement your Chirp device's
          recordings; they don't replace them.
        </span>
      </div>

      <div className="flex items-stretch gap-2">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-tertiary)' }}/>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by species…"
            className="input w-full pl-9"
          />
        </div>

        <DateRangeFilter {...dateFilter}/>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => <div key={i} className="skeleton h-16 rounded-xl"/>)}
        </div>
      ) : error ? (
        <div className="card p-6 text-center text-sm" style={{ color: 'var(--text-tertiary)' }}>
          {error}
        </div>
      ) : filtered.length === 0 ? (
        <div className="card p-8 text-center">
          <Radio size={28} className="mx-auto mb-2" style={{ color: 'var(--text-tertiary)' }}/>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {search.trim()
              ? 'No matching detections.'
              : datePreset !== 'all'
                ? 'No detections in this date range.'
                : 'No Haikubox detections yet.'}
          </p>
          {!search.trim() && datePreset === 'all' && (
            <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
              Make sure a Haikubox serial is configured in Settings → Devices.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(rec => {
            return (
              <Link key={rec.id} to={`/library?species=${encodeURIComponent(rec.top_species || '')}`}
                    className="card-hover flex items-center gap-3 p-3.5 transition-colors">
                <div className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
                     style={{ background: 'var(--bg-raised)' }}>
                  <BirdIcon size={16} style={{ color: "var(--accent-400)" }}/>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                    {rec.top_species || 'Unknown species'}
                  </p>
                  <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>
                    {fmtTs(rec.trigger_timestamp)}
                  </p>
                </div>
              </Link>
            )
          })}

          {hasMore && !search.trim() && (
            <button
              onClick={() => load(items.length, true)}
              disabled={loadingMore}
              className="w-full py-2.5 text-sm rounded-xl transition-colors"
              style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
              {loadingMore ? 'Loading…' : 'Load more'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
