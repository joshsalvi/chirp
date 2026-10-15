/**
 * Settings → Experimental → Detection models: BirdNET v3 (compare, or use
 * as the main model) and Nighthawk night flight calls. Server side:
 * services/birdnet3.py, services/nighthawk_service.py, api/night_calls.py.
 * Lives in the Settings form, so changes save with the Save bar.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'

function Row({ title, children, checked, onChange, disabled }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <p className="text-sm font-medium text-gray-200">{title}</p>
        <div className="text-xs text-gray-500 mt-1 max-w-2xl space-y-1">{children}</div>
      </div>
      <input type="checkbox" checked={!!checked} disabled={disabled} onChange={e => onChange(e.target.checked)}
             className="w-4 h-4 accent-chirp-500 flex-shrink-0 mt-0.5"/>
    </div>
  )
}

function Slider({ label, value, min, max, step, onChange, format }) {
  return (
    <label className="block">
      <span className="flex justify-between text-xs text-gray-300">
        <span>{label}</span><span className="font-mono">{format(value)}</span>
      </span>
      <input type="range" min={min} max={max} step={step} value={value}
             onChange={e => onChange(Number(e.target.value))} className="w-full accent-chirp-500"/>
    </label>
  )
}

function birdnet3Text(st) {
  if (!st) return null
  if (st.state === 'ready') return `Model ready (${st.size_mb ?? '?'} MB on the server).`
  if (st.state === 'downloading') {
    const pct = st.total ? Math.round(100 * st.bytes / st.total) : null
    return `Downloading the model${pct != null ? ` (${pct}%)` : ''}…`
  }
  if (st.state === 'error') return `Problem: ${st.error}`
  return 'The model (557 MB) downloads to the server when you turn this on and save.'
}

export default function ExperimentalModels({ form, setForm }) {
  const [status, setStatus] = useState(null)
  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const bn3On = form.exp_birdnet3_shadow || form.exp_birdnet3_main

  useEffect(() => {
    let alive = true, timer
    const load = () => api.nightCalls.status()
      .then(s => {
        if (!alive) return
        setStatus(s)
        if (s?.birdnet3?.state === 'downloading') timer = setTimeout(load, 3000)
      })
      .catch(() => {})
    load()
    return () => { alive = false; clearTimeout(timer) }
  }, [form.exp_birdnet3_shadow, form.exp_birdnet3_main])

  const nh = status?.nighthawk
  const st = status?.birdnet3

  return (
    <div className="space-y-5">
      {/* ── BirdNET v3 ── */}
      <div className="space-y-3">
        <Row title="Compare with BirdNET v3" checked={form.exp_birdnet3_shadow}
             onChange={set('exp_birdnet3_shadow')}>
          <p>
            After the usual BirdNET 2.4 pass, the server also runs BirdNET v3 (developer preview) on each new
            recording. Each recording page shows what BirdNET v3 heard next to the main detections. Nothing else
            changes: alerts, the life list and the owl checks still use BirdNET 2.4.
          </p>
        </Row>
        <Row title="Use BirdNET v3 as the main model" checked={form.exp_birdnet3_main}
             onChange={set('exp_birdnet3_main')}>
          <p>
            BirdNET v3's results become the detections for new recordings, Re-analyze and Live Detect. In our test it
            found about twice as many species as BirdNET 2.4 at the same accuracy, with far fewer false alarms from
            noise.
          </p>
          <p className="text-amber-400/90">
            BirdNET 2.4's owl checks and night-caller thresholds don't apply to it, and its scores run on a different
            scale. The station itself still uses BirdNET 2.4 to decide what to record.
          </p>
        </Row>
        {bn3On && (
          <div className="pl-1 space-y-2">
            <Slider label="BirdNET v3 minimum confidence" min={0.2} max={0.9} step={0.05}
                    value={form.exp_birdnet3_min_conf ?? 0.5} onChange={set('exp_birdnet3_min_conf')}
                    format={v => `${Math.round(v * 100)}%`}/>
            <p className="text-xs text-gray-500">50% kept about 9 in 10 reports correct in testing.</p>
          </div>
        )}
        {st && (bn3On || st.state === 'ready') && (
          <div className="flex items-center gap-3 text-xs">
            <span className={st.state === 'error' ? 'text-red-400' : 'text-gray-400'}>{birdnet3Text(st)}</span>
            {(st.state === 'error' || st.state === 'missing') && bn3On && (
              <button className="btn-secondary text-xs px-2 py-1"
                      onClick={() => api.nightCalls.downloadBirdnet3().then(s => setStatus(x => ({ ...x, birdnet3: s })))}>
                Download now
              </button>
            )}
          </div>
        )}
        <p className="text-[11px] text-gray-600">
          BirdNET v3 preview: CC BY-SA 4.0, for research and evaluation; its terms prohibit poaching and military use.
        </p>
      </div>

      {/* ── Nighthawk ── */}
      <div className="pt-4 border-t border-surface-700 space-y-3">
        <Row title="Night flight calls (Nighthawk)" checked={form.exp_nighthawk_enabled}
             onChange={set('exp_nighthawk_enabled')} disabled={nh && !nh.available}>
          <p>
            Migrating birds give short, high calls at night that BirdNET rarely picks up. With this on, stations upload
            their audio between the hours below, and Nighthawk lists the calls it finds on the{' '}
            <Link to="/night-calls" className="text-chirp-400 underline">Night Flight Calls</Link> page. It names a
            species when it's confident, otherwise a family or a group of species that sound alike.
          </p>
          <p>
            Uses about 60–90 MB of upload per station per hour of night; the audio is deleted once analyzed. Stations
            need software 1.4.0 or later. Trained on birds of the Americas, mostly eastern North America.
          </p>
          {nh && !nh.available && <p className="text-red-400">{nh.why}</p>}
        </Row>
        {form.exp_nighthawk_enabled && (
          <div className="pl-1 space-y-3">
            <div className="flex flex-wrap items-center gap-3 text-xs text-gray-300">
              <label className="flex items-center gap-2">From
                <input type="time" className="input text-xs py-1" value={form.exp_nighthawk_start || '21:00'}
                       onChange={e => set('exp_nighthawk_start')(e.target.value)}/>
              </label>
              <label className="flex items-center gap-2">to
                <input type="time" className="input text-xs py-1" value={form.exp_nighthawk_end || '05:00'}
                       onChange={e => set('exp_nighthawk_end')(e.target.value)}/>
              </label>
              <span className="text-gray-500">site time</span>
            </div>
            <Slider label="Nighthawk threshold" min={50} max={95} step={5}
                    value={form.exp_nighthawk_threshold ?? 80} onChange={set('exp_nighthawk_threshold')}
                    format={v => `${v}%`}/>
            {nh && (
              <p className="text-xs text-gray-500">
                {nh.calls} call{nh.calls === 1 ? '' : 's'} found so far
                {nh.pending ? ` · ${nh.pending} chunk${nh.pending === 1 ? '' : 's'} waiting` : ''}
                {nh.errors ? ` · ${nh.errors} failed` : ''}
                {nh.last_processed ? ` · last analyzed ${new Date(nh.last_processed).toLocaleString()}` : ''}
              </p>
            )}
          </div>
        )}
        <p className="text-[11px] text-gray-600">
          Nighthawk: Van Doren et al. 2023, CC BY-NC 4.0 (non-commercial).
        </p>
      </div>
    </div>
  )
}
