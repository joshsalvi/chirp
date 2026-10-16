/**
 * Settings → Detection → Detection Model: BirdNET v3 (default) or 2.4.
 * Server side: AppSettings.detection_model, services/birdnet3.py,
 * api/recordings.py (_bn3_main). Saves with the Settings Save bar.
 */
import { useEffect, useState } from 'react'
import { api } from '../lib/api'

function modelStatus(st) {
  if (!st) return null
  if (st.state === 'ready') return `Model ready (${st.size_mb ?? '?'} MB on the server).`
  if (st.state === 'downloading') {
    const pct = st.total ? Math.round(100 * st.bytes / st.total) : null
    return `Downloading the model${pct != null ? ` (${pct}%)` : ''}… Recordings use BirdNET 2.4 until it's ready.`
  }
  if (st.state === 'error') return `Download problem: ${st.error}. Recordings use BirdNET 2.4 meanwhile.`
  return 'The model (557 MB) downloads to the server when you save.'
}

function Choice({ checked, onSelect, title, badge, children }) {
  return (
    <button type="button" onClick={onSelect}
            className="w-full text-left rounded-xl p-3 transition-colors"
            style={{ border: `1px solid ${checked ? 'var(--accent-500)' : 'var(--border-subtle)'}`,
                     background: checked ? 'var(--nav-active-bg)' : 'transparent' }}>
      <span className="flex items-center gap-2">
        <span className="w-4 h-4 rounded-full flex-shrink-0 flex items-center justify-center"
              style={{ border: `2px solid ${checked ? 'var(--accent-400)' : 'var(--text-tertiary)'}` }}>
          {checked && <span className="w-2 h-2 rounded-full" style={{ background: 'var(--accent-400)' }}/>}
        </span>
        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{title}</span>
        {badge && <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded"
                        style={{ background: 'var(--bg-raised)', color: 'var(--accent-400)' }}>{badge}</span>}
      </span>
      <span className="block text-xs mt-1.5 pl-6" style={{ color: 'var(--text-tertiary)', lineHeight: 1.5 }}>{children}</span>
    </button>
  )
}

export default function DetectionModel({ form, setForm }) {
  const [st, setSt] = useState(null)
  const model = form.detection_model || 'birdnet3'
  const set = k => v => setForm(f => ({ ...f, [k]: v }))

  useEffect(() => {
    let alive = true, timer
    const load = () => api.nightCalls.status()
      .then(s => {
        if (!alive) return
        setSt(s?.birdnet3)
        if (s?.birdnet3?.state === 'downloading') timer = setTimeout(load, 3000)
      })
      .catch(() => {})
    load()
    return () => { alive = false; clearTimeout(timer) }
  }, [model])

  return (
    <div className="space-y-3">
      <Choice checked={model === 'birdnet3'} onSelect={() => set('detection_model')('birdnet3')}
              title="BirdNET v3" badge="Recommended">
        Finds about twice as many species as 2.4 at the same accuracy, with far fewer false alarms from noise.
        Owls need a hoot at the owl's pitch, and in daylight a score of 80% or more.
      </Choice>
      <Choice checked={model === 'birdnet24'} onSelect={() => set('detection_model')('birdnet24')}
              title="BirdNET 2.4">
        The earlier model, with the night-caller thresholds and owl checks below tuned to it.
      </Choice>

      {model === 'birdnet3' && (
        <div className="space-y-2 pt-1">
          <label className="block">
            <span className="flex justify-between text-xs" style={{ color: 'var(--text-secondary)' }}>
              <span>Minimum confidence</span>
              <span className="font-mono">{Math.round((form.exp_birdnet3_min_conf ?? 0.5) * 100)}%</span>
            </span>
            <input type="range" min={0.2} max={0.9} step={0.05} value={form.exp_birdnet3_min_conf ?? 0.5}
                   onChange={e => set('exp_birdnet3_min_conf')(Number(e.target.value))} className="w-full accent-chirp-500"/>
          </label>
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            50% kept about 9 in 10 reports correct in testing. Live Detect uses this too.
          </p>
          {st && <p className="text-xs" style={{ color: st.state === 'error' ? '#f87171' : 'var(--text-tertiary)' }}>{modelStatus(st)}</p>}
          {st && (st.state === 'error' || st.state === 'missing' || st.state === 'idle') && (
            <button className="btn-secondary text-xs px-2 py-1"
                    onClick={() => api.nightCalls.downloadBirdnet3().then(setSt).catch(() => {})}>
              Download now
            </button>
          )}
        </div>
      )}

      {model === 'birdnet24' && (
        <label className="flex items-start justify-between gap-4 pt-1">
          <span>
            <span className="block text-sm" style={{ color: 'var(--text-primary)' }}>Compare with BirdNET v3</span>
            <span className="block text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
              Also scores each new recording with v3 and shows what it heard on the recording page. Nothing else changes.
            </span>
          </span>
          <input type="checkbox" checked={!!form.exp_birdnet3_shadow} onChange={e => set('exp_birdnet3_shadow')(e.target.checked)}
                 className="w-4 h-4 accent-chirp-500 flex-shrink-0 mt-0.5"/>
        </label>
      )}

      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        Stations still use BirdNET 2.4 to decide what to record; the server then identifies the birds.
        BirdNET v3 is a developer preview (CC BY-SA 4.0); its terms prohibit poaching and military use.
      </p>
    </div>
  )
}
