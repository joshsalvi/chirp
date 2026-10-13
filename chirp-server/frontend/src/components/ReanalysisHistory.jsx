import { useEffect, useState } from 'react'
import { History, Undo2, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import { api } from '../lib/api'

const pct = v => (v == null ? '—' : `${Math.round(v * 100)}%`)

const CHANGE_STYLE = {
  added:   { sign: '+', color: 'var(--pastel-green, #4ade80)' },
  removed: { sign: '−', color: 'var(--pastel-red, #f87171)' },
  hidden:  { sign: '↓', color: 'var(--pastel-yellow, #eab308)' },
  kept:    { sign: '=', color: 'var(--text-tertiary)' },
}

function fmtWhen(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function ChangeRow({ c }) {
  const st = CHANGE_STYLE[c.change] || CHANGE_STYLE.kept
  const scores = c.change === 'added' ? pct(c.now)
    : c.change === 'removed' ? `${pct(c.was)} → ${c.now == null ? 'none' : pct(c.now)}`
    : `${pct(c.was)} → ${pct(c.now)}`
  return (
    <div className="flex items-start gap-2 text-xs py-0.5">
      <span className="font-mono w-3 flex-shrink-0 text-center" style={{ color: st.color }}>{st.sign}</span>
      <span className="flex-1 min-w-0">
        <span style={{ color: 'var(--text-primary)' }}>{c.species}</span>
        <span className="font-mono ml-2" style={{ color: 'var(--text-tertiary)' }}>{scores}</span>
        {c.reason && <span className="block" style={{ color: 'var(--text-tertiary)' }}>{c.reason}</span>}
      </span>
    </div>
  )
}

/**
 * Re-analyses of one recording, newest first: what each changed and why,
 * with Undo on the newest. refreshKey reloads after a re-analysis ends.
 */
export default function ReanalysisHistory({ recordingId, refreshKey = 0, busy = false, onUndone }) {
  const [runs, setRuns] = useState(null)
  const [open, setOpen] = useState(true)
  const [showKept, setShowKept] = useState(false)
  const [undoing, setUndoing] = useState(null)
  const [error, setError] = useState(null)

  const load = () => api.recordings.reanalysisHistory(recordingId)
    .then(d => setRuns(d?.runs || []))
    .catch(() => setRuns([]))

  useEffect(() => { load() // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordingId, refreshKey])

  if (!runs || runs.length === 0) return null

  const undo = async (run) => {
    const n = run.before_count
    if (!window.confirm(`Undo this re-analysis? The ${n} detection${n === 1 ? '' : 's'} from before it come back and its results are removed.`)) return
    setUndoing(run.id)
    setError(null)
    try {
      await api.recordings.undoReanalysis(recordingId, run.id)
      await load()
      onUndone?.()
    } catch (e) {
      setError(e.message || String(e))
    }
    setUndoing(null)
  }

  return (
    <div className="card p-4 animate-fade-in">
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          <History size={14} style={{ color: 'var(--accent-400)' }}/> Re-analysis history
          <span className="text-xs font-normal" style={{ color: 'var(--text-tertiary)' }}>{runs.length}</span>
        </span>
        {open ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          {runs.map(run => {
            const changes = (run.changes || []).filter(c => showKept || c.change !== 'kept')
            const undone = run.status === 'undone'
            return (
              <div key={run.id} className="rounded-lg p-3"
                   style={{ background: 'var(--bg-raised)', opacity: undone ? 0.55 : 1 }}>
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    <span style={{ color: 'var(--text-primary)' }}>{fmtWhen(run.created_at)}</span>
                    {run.use_ai_enhance && <span className="ml-2 px-1.5 py-0.5 rounded" style={{ background: 'var(--bg-base)' }}>AI-Enhanced</span>}
                    {run.min_conf != null && <span className="ml-2">min {pct(run.min_conf)}</span>}
                    {run.status === 'running' && <span className="ml-2 inline-flex items-center gap-1"><RefreshCw size={10} className="animate-spin"/> running</span>}
                    {undone && <span className="ml-2">undone {fmtWhen(run.undone_at)}</span>}
                  </div>
                  {run.can_undo && (
                    <button onClick={() => undo(run)} disabled={!!undoing || busy}
                            className="btn-secondary" style={{ padding: '3px 9px', fontSize: 11 }}>
                      {undoing === run.id ? <RefreshCw size={11} className="animate-spin"/> : <Undo2 size={11}/>}
                      {undoing === run.id ? 'Undoing…' : 'Undo'}
                    </button>
                  )}
                </div>
                {run.summary && <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>{run.summary}</p>}
                {changes.length > 0 && (
                  <div className="mt-2">{changes.map(c => <ChangeRow key={c.species + c.change} c={c}/>)}</div>
                )}
              </div>
            )
          })}
          {runs.some(r => (r.changes || []).some(c => c.change === 'kept')) && (
            <label className="flex items-center gap-2 text-xs cursor-pointer w-fit" style={{ color: 'var(--text-tertiary)' }}>
              <input type="checkbox" className="toggle" checked={showKept} onChange={e => setShowKept(e.target.checked)}/>
              Show unchanged species
            </label>
          )}
          {error && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{error}</p>}
        </div>
      )}
    </div>
  )
}
