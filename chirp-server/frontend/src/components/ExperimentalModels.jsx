/**
 * Settings → Experimental → Night flight calls (Nighthawk). Server side:
 * services/nighthawk_service.py, api/night_calls.py. Saves with the Save bar.
 * BirdNET v3 moved to Settings → Detection (DetectionModel.jsx) in 0.5.14.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'

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

export default function ExperimentalModels({ form, setForm }) {
  const [status, setStatus] = useState(null)
  const set = k => v => setForm(f => ({ ...f, [k]: v }))

  useEffect(() => {
    api.nightCalls.status().then(setStatus).catch(() => {})
  }, [form.exp_nighthawk_enabled])

  const nh = status?.nighthawk

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-200">Night flight calls (Nighthawk)</p>
          <div className="text-xs text-gray-500 mt-1 max-w-2xl space-y-1">
            <p>
              Migrating birds give short, high calls at night that BirdNET rarely picks up. With this on, stations
              upload their audio between the hours below, and Nighthawk lists the calls it finds on the{' '}
              <Link to="/night-calls" className="text-chirp-400 underline">Night Flight Calls</Link> page.
            </p>
            <p>
              About 60–90 MB of upload per station per hour of night; the audio is deleted once analyzed. Stations
              need software 1.4.1 or later (1.4.0 left short gaps in the audio, which sounded choppy). Trained on birds of the Americas, mostly eastern North America.
            </p>
            {nh && !nh.available && <p className="text-red-400">{nh.why}</p>}
          </div>
        </div>
        <input type="checkbox" checked={!!form.exp_nighthawk_enabled} disabled={nh && !nh.available}
               onChange={e => set('exp_nighthawk_enabled')(e.target.checked)}
               className="w-4 h-4 accent-chirp-500 flex-shrink-0 mt-0.5"/>
      </div>
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
      <p className="text-[11px] text-gray-600">Nighthawk: Van Doren et al. 2023, CC BY-NC 4.0 (non-commercial).</p>
    </div>
  )
}
