import { useState, useCallback, useEffect, useRef } from 'react'
import { Calendar, ChevronDown, X } from 'lucide-react'

// Quick date-range presets. Each `hours` value is converted to a
// start/end pair at request time (start = now - hours, end = now) —
// computed fresh on every load rather than once on mount, so a preset
// stays correct even if the page is left open a while before refreshing.
export const DATE_PRESETS = [
  { id: 'all',    label: 'All time',      hours: null },
  { id: '24h',    label: 'Last 24 hours', hours: 24 },
  { id: '7d',     label: 'Last 7 days',   hours: 24 * 7 },
  { id: '30d',    label: 'Last 30 days',  hours: 24 * 30 },
  { id: '90d',    label: 'Last 3 months', hours: 24 * 90 },
  { id: 'custom', label: 'Custom range…', hours: undefined },
]

/**
 * Hook holding all date-filter state + the logic to resolve it into a
 * concrete {start, end} ISO pair for the server. Pulled out of
 * HaikuboxDetections.jsx so RecordingsList.jsx can use the identical,
 * already-tested behavior rather than a second hand-written copy.
 */
// initial: a saved {datePreset, customStart, customEnd} to start from.
export function useDateRangeFilter(initial) {
  const [datePreset, setDatePreset] = useState(initial?.datePreset || 'all')
  const [customStart, setCustomStart] = useState(initial?.customStart || '')   // yyyy-mm-dd, from <input type="date">
  const [customEnd, setCustomEnd] = useState(initial?.customEnd || '')

  // Resolve the active preset/custom range into a concrete {start, end}
  // ISO pair to actually send the server — kept separate from the preset
  // selection itself so "Last 24 hours" always means the 24 hours
  // ending now, recomputed on every load, not frozen at whenever the
  // preset was first clicked.
  const resolveRange = useCallback(() => {
    if (datePreset === 'all') return { start: null, end: null }
    if (datePreset === 'custom') {
      return {
        start: customStart ? new Date(customStart + 'T00:00:00').toISOString() : null,
        end:   customEnd   ? new Date(customEnd   + 'T23:59:59').toISOString() : null,
      }
    }
    const preset = DATE_PRESETS.find(p => p.id === datePreset)
    if (!preset || preset.hours == null) return { start: null, end: null }
    const end = new Date()
    const start = new Date(end.getTime() - preset.hours * 3600 * 1000)
    return { start: start.toISOString(), end: end.toISOString() }
  }, [datePreset, customStart, customEnd])

  const clear = () => { setDatePreset('all'); setCustomStart(''); setCustomEnd('') }

  return { datePreset, setDatePreset, customStart, setCustomStart, customEnd, setCustomEnd, resolveRange, clear }
}

/**
 * The dropdown button + panel UI. Takes the state from useDateRangeFilter
 * as props rather than calling the hook itself, so the parent page owns
 * the state (needed since the parent's data-loading effect must also
 * depend on it) while this component only renders it.
 */
export function DateRangeFilter({ datePreset, setDatePreset, customStart, setCustomStart, customEnd, setCustomEnd, clear }) {
  const [dateMenuOpen, setDateMenuOpen] = useState(false)
  const dateMenuRef = useRef(null)

  useEffect(() => {
    if (!dateMenuOpen) return
    const handler = (e) => {
      if (dateMenuRef.current && !dateMenuRef.current.contains(e.target)) {
        setDateMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [dateMenuOpen])

  const handlePresetSelect = (id) => {
    setDatePreset(id)
    if (id !== 'custom') setDateMenuOpen(false)
  }

  const activePresetLabel = datePreset === 'custom'
    ? (customStart || customEnd)
      ? `${customStart || '…'} → ${customEnd || '…'}`
      : 'Custom range…'
    : (DATE_PRESETS.find(p => p.id === datePreset)?.label || 'All time')

  return (
    <>
      <div className="relative flex-shrink-0" ref={dateMenuRef}>
        <button
          onClick={() => setDateMenuOpen(o => !o)}
          className="flex items-center gap-2 px-3.5 rounded-xl text-xs font-medium transition-colors whitespace-nowrap"
          style={{ height: 34, background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
          <Calendar size={13} className="flex-shrink-0"/>
          <span className="hidden sm:inline">{activePresetLabel}</span>
          <ChevronDown size={12} className="flex-shrink-0" style={{ transform: dateMenuOpen ? 'rotate(180deg)' : 'none', transition: 'transform 150ms ease' }}/>
        </button>

        {dateMenuOpen && (
          <div className="absolute right-0 mt-1.5 rounded-xl overflow-hidden z-20"
               style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-card-hover)', minWidth: 220 }}>
            {DATE_PRESETS.map(p => (
              <button key={p.id}
                      onClick={() => handlePresetSelect(p.id)}
                      className="w-full text-left px-3.5 py-2.5 text-xs transition-colors"
                      style={{
                        color: datePreset === p.id ? 'var(--accent-400)' : 'var(--text-primary)',
                        background: datePreset === p.id ? 'var(--nav-active-bg)' : 'transparent',
                        borderBottom: p.id !== 'custom' ? '1px solid var(--border-subtle)' : 'none',
                      }}>
                {p.label}
              </button>
            ))}
            {datePreset === 'custom' && (
              <div className="p-3 space-y-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <div>
                  <label className="text-xs block mb-1" style={{ color: 'var(--text-tertiary)' }}>From</label>
                  <input type="date" value={customStart} onChange={e => setCustomStart(e.target.value)}
                         className="input w-full text-xs" style={{ padding: '6px 8px' }}/>
                </div>
                <div>
                  <label className="text-xs block mb-1" style={{ color: 'var(--text-tertiary)' }}>To</label>
                  <input type="date" value={customEnd} onChange={e => setCustomEnd(e.target.value)}
                         className="input w-full text-xs" style={{ padding: '6px 8px' }}/>
                </div>
                <button onClick={() => setDateMenuOpen(false)}
                        className="w-full text-xs font-medium py-1.5 rounded-lg mt-1"
                        style={{ background: 'var(--accent-500)', color: 'var(--btn-primary-text)' }}>
                  Apply
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {datePreset !== 'all' && (
        <button onClick={() => { clear(); setDateMenuOpen(false) }}
                title="Clear date filter"
                className="flex items-center justify-center w-9 flex-shrink-0 rounded-xl transition-colors"
                style={{ height: 34, background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--text-tertiary)' }}>
          <X size={14}/>
        </button>
      )}
    </>
  )
}
