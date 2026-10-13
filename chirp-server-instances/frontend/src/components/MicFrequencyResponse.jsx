import { useState, useEffect } from 'react'
import { AudioLines, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'

// Requested directly, alongside Live Detect's window/sensitivity tuning:
// a way to actually see whether a phone's mic and a chirp-device's mic
// pick up sound across frequency differently, side by side — rather than
// just going on impression. Deliberately kept as its own small component
// (not folded into Settings.jsx, already enormous) so Settings only needs
// one import + one render call to host it.
//
// Also exports PhoneMicTest standalone (just the phone/computer half, no
// device selection at all) — requested separately as its own diagnostic
// item, since testing your own browser's mic shouldn't require a paired
// device to exist first. Both this file's default export and PhoneMicTest
// share the same capture/analyze logic via usePhoneMicTest() below, so
// there's one real implementation, not two copies to keep in sync.

const BAR_COLOR_PHONE = '#60a5fa'
const BAR_COLOR_DEVICE = '#4ade80'

function Spectrogram({ result }) {
  if (!result || !result.spectrogram_png_base64) return null
  return (
    <img src={`data:image/png;base64,${result.spectrogram_png_base64}`}
         alt="Spectrogram of this capture"
         className="w-full rounded-lg"
         style={{ border: '1px solid var(--border-subtle)' }}/>
  )
}

function FrequencyBars({ result, color }) {
  if (!result) return null
  const bands = result.bands.filter(b => b.magnitude_db !== null)
  return (
    <div className="space-y-1">
      {bands.map(b => {
        const pct = Math.max(0, 100 + b.magnitude_db) // magnitude_db is 0 (loudest) down to negative — floor bars at 0% rather than letting very quiet bands go visually negative
        return (
          <div key={b.label} className="flex items-center gap-2 text-[11px]">
            <span className="w-20 flex-shrink-0 text-right" style={{ color: 'var(--text-tertiary)' }}>{b.label}</span>
            <div className="flex-1 h-3 rounded-full overflow-hidden" style={{ background: 'var(--bg-raised)' }}>
              <div className="h-full rounded-full" style={{ width: `${Math.min(100, pct)}%`, background: color }}/>
            </div>
            <span className="w-10 flex-shrink-0 font-mono" style={{ color: 'var(--text-tertiary)' }}>{b.magnitude_db} dB</span>
          </div>
        )
      })}
    </div>
  )
}

// Shared capture+analyze logic for the phone/computer mic, used by both
// the combined comparison view below and the standalone PhoneMicTest.
function usePhoneMicTest() {
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const test = async () => {
    setError(null); setRunning(true)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const chunks = []
      let recorder
      try { recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' }) }
      catch { recorder = new MediaRecorder(stream) }
      const blob = await new Promise((resolve) => {
        recorder.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data) }
        recorder.onstop = () => resolve(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }))
        recorder.start()
        setTimeout(() => recorder.stop(), 4000)
      })
      stream.getTracks().forEach(t => t.stop())
      const r = await api.diagnostics.micFrequencyResponse({ source: 'phone', blob })
      setResult(r)
    } catch (e) {
      setError(e.message || 'Mic test failed — check microphone permission for this site.')
    } finally {
      setRunning(false)
    }
  }

  return { running, result, error, test }
}

// Standalone "Computer/Phone Mic Test" — no device required, just this
// browser's own mic. Used as its own separate Diagnostics item.
export function PhoneMicTest() {
  const { running, result, error, test } = usePhoneMicTest()
  return (
    <div className="card rounded-xl p-4 space-y-3" style={{ overflowX: 'hidden', maxWidth: '100%' }}>
      <div className="flex items-center justify-between">
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          Captures 4 seconds from whatever mic this browser is using and shows its spectrogram and frequency content.
        </p>
        <button onClick={test} disabled={running}
                className="text-xs px-2 py-1 rounded-lg flex items-center gap-1 flex-shrink-0"
                style={{ background: 'var(--bg-raised)', color: 'var(--text-primary)', opacity: running ? 0.6 : 1 }}>
          {running ? <><RefreshCw size={11} className="animate-spin"/> Listening…</> : 'Test (4s)'}
        </button>
      </div>
      <Spectrogram result={result}/>
      <FrequencyBars result={result} color={BAR_COLOR_PHONE}/>
      {error && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{error}</p>}
    </div>
  )
}

// defaultDeviceId: optional — pre-selects a device's mic instead of the
// first paired device found. Used when this is embedded on a specific
// device's own page, so the right mic is already selected instead of
// making the person re-pick it.
export default function MicFrequencyResponse({ defaultDeviceId } = {}) {
  const [devices, setDevices] = useState([])
  const [selectedDevice, setSelectedDevice] = useState(null)
  const [selectedMic, setSelectedMic] = useState('')
  const [deviceRunning, setDeviceRunning] = useState(false)
  const [deviceResult, setDeviceResult] = useState(null)
  const [error, setError] = useState(null)
  const phone = usePhoneMicTest()

  useEffect(() => {
    api.devices.list().then(list => {
      setDevices(list)
      const preferred = defaultDeviceId
        ? list.find(d => d.id === defaultDeviceId && d.mic_names?.length)
        : null
      const first = preferred || list.find(d => d.mic_names && d.mic_names.length)
      if (first) {
        setSelectedDevice(first.id)
        setSelectedMic(first.mic_names[0])
      }
    }).catch(() => {})
  }, [defaultDeviceId])

  const testDevice = async () => {
    if (!selectedDevice || !selectedMic) { setError('Select a device and mic first.'); return }
    setError(null); setDeviceRunning(true)
    try {
      const result = await api.diagnostics.micFrequencyResponse({ source: 'device', deviceId: selectedDevice, micName: selectedMic })
      setDeviceResult(result)
    } catch (e) {
      setError(e.message || 'Device mic test failed.')
    } finally {
      setDeviceRunning(false)
    }
  }

  const devicesWithMics = devices.filter(d => d.mic_names && d.mic_names.length)
  const currentDevice = devicesWithMics.find(d => d.id === selectedDevice)

  return (
    <div className="card rounded-xl p-4 space-y-4" style={{ overflowX: 'hidden', maxWidth: '100%' }}>
      <div className="flex items-center gap-2">
        <AudioLines size={16} style={{ color: 'var(--text-secondary)' }}/>
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Mic Frequency Response</h3>
      </div>
      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        Captures a few seconds of whatever's audible right now and shows its spectrogram and frequency content, per mic — not a calibrated response curve (that needs a known reference tone), but a useful side-by-side: capture the same real sound on each mic, one after another, and compare the shapes below.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Phone mic */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium" style={{ color: BAR_COLOR_PHONE }}>This phone's mic</span>
            <button onClick={phone.test} disabled={phone.running}
                    className="text-xs px-2 py-1 rounded-lg flex items-center gap-1"
                    style={{ background: 'var(--bg-raised)', color: 'var(--text-primary)', opacity: phone.running ? 0.6 : 1 }}>
              {phone.running ? <><RefreshCw size={11} className="animate-spin"/> Listening…</> : 'Test (4s)'}
            </button>
          </div>
          <Spectrogram result={phone.result}/>
          <FrequencyBars result={phone.result} color={BAR_COLOR_PHONE}/>
        </div>

        {/* Device mic */}
        <div className="space-y-2">
          <div className="flex items-center gap-2" style={{ maxWidth: '100%' }}>
            {/* Reported directly: this row caused horizontal scroll on
                mobile in both places it's embedded (Devices page,
                Diagnostics). Root cause: a native <select> on iOS Safari
                can force its layout box to its widest OPTION text's
                intrinsic width and ignore flex-shrink/min-w-0 while doing
                it — an explicit maxWidth (which Safari does respect,
                unlike flex-shrink alone here) on both this wrapper and
                the select itself is what actually constrains it. Also
                shortened the option text — no point repeating a device's
                name on every one of its mics when there's only one
                paired device, which is the common case and was making
                the overflow worse for no benefit. */}
            <select value={selectedMic ? `${selectedDevice}::${selectedMic}` : ''}
                    onChange={e => { const [id, mic] = e.target.value.split('::'); setSelectedDevice(id); setSelectedMic(mic) }}
                    className="text-xs px-1.5 py-1 rounded-lg flex-1 min-w-0"
                    style={{ background: 'var(--bg-raised)', color: BAR_COLOR_DEVICE, maxWidth: '100%' }}>
              {devicesWithMics.length === 0 && <option value="">No paired devices with mics</option>}
              {devicesWithMics.map(d => d.mic_names.map(m => (
                <option key={`${d.id}::${m}`} value={`${d.id}::${m}`}>
                  {devicesWithMics.length > 1 ? `${d.name} — ${m}` : m}
                </option>
              )))}
            </select>
            <button onClick={testDevice} disabled={deviceRunning || !currentDevice}
                    className="text-xs px-2 py-1 rounded-lg flex items-center gap-1 flex-shrink-0"
                    style={{ background: 'var(--bg-raised)', color: 'var(--text-primary)', opacity: (deviceRunning || !currentDevice) ? 0.6 : 1 }}>
              {deviceRunning ? <><RefreshCw size={11} className="animate-spin"/> Listening…</> : 'Test'}
            </button>
          </div>
          <Spectrogram result={deviceResult}/>
          <FrequencyBars result={deviceResult} color={BAR_COLOR_DEVICE}/>
        </div>
      </div>

      {(error || phone.error) && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{error || phone.error}</p>}
    </div>
  )
}
