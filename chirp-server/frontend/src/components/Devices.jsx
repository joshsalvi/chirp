import * as React from 'react'
import { useState, useEffect, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  Cpu, Wifi, WifiOff, MapPin, RefreshCw, Trash2, Edit2,
  Check, X, ChevronDown, ChevronUp, Radio, Mic, Zap,
  Activity, Copy, Plus, AudioLines,
  AlertCircle, Settings2, Info, ExternalLink, FileText, Server
} from 'lucide-react'
import { BirdBuddyIcon } from './BirdBatIcons'
import MicFrequencyResponse from './MicFrequencyResponse'
import BleDeviceSetup from './BleDeviceSetup'
// Lazy-loaded: SSHTerminal pulls in xterm (a full terminal emulator),
// which is only needed when someone explicitly opens the SSH panel for a
// device — bundling it into the main chunk meant every page load paid for
// a feature most sessions never touch. Confirmed via an optimization audit
// that this was a real, measurable contributor to the bundle-size warning
// vite's build has been flagging since early sessions.
const SSHTerminal = React.lazy(() => import('./SSHTerminal'))
import ErrorBoundary from './ErrorBoundary'
import { api } from '../lib/api'
import { hapticEvent } from '../lib/haptics'

// ── helpers ──────────────────────────────────────────────────────────────────

function timeAgo(dt) {
  if (!dt) return 'Never'
  const s = Math.floor((Date.now() - new Date(dt + (dt.endsWith('Z') ? '' : 'Z'))) / 1000)
  if (s < 5) return 'Just now'
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

function formatConfigVersion(v) {
  if (!v || v <= 1) return `v${v || 0}`
  const s = String(v)
  if (s.length === 12) {
    // YYYYMMDDHHmm → "config v20260602-1534"
    return `v${s.slice(0,4)}${s.slice(4,6)}${s.slice(6,8)}-${s.slice(8,10)}${s.slice(10,12)}`
  }
  return `v${v}`
}

function StatusBadge({ status }) {
  const map = {
    online: { color: 'bg-chirp-500', text: 'Online', pulse: true },
    offline: { color: 'bg-yellow-500', text: 'Offline', pulse: false },
    never_connected: { color: 'bg-gray-600', text: 'Never connected', pulse: false },
  }
  const s = map[status] || map.never_connected
  return (
    <span className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${s.color} ${s.pulse ? 'live-dot' : ''}`}/>
      <span className={`text-xs font-medium ${status === 'online' ? 'text-chirp-400' : status === 'offline' ? 'text-yellow-400' : 'text-gray-500'}`}>
        {s.text}
      </span>
    </span>
  )
}

function ConfigField({ label, hint, children }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-300 mb-1">{label}</label>
      {hint && <p className="text-xs text-gray-600 mb-1.5">{hint}</p>}
      {children}
      </div>
  )
}

function NumberInput({ value, onChange, min, max, step = 0.01, unit }) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="number" min={min} max={max} step={step}
        value={value ?? ''}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="input w-32 text-sm"
      />
      {unit && <span className="text-xs text-gray-500">{unit}</span>}
      </div>
  )
}

function RangeSlider({ value, onChange, min, max, step, format }) {
  return (
    <div className="flex items-center gap-3">
      <input type="range" min={min} max={max} step={step}
             value={value ?? min}
             onChange={e => onChange(parseFloat(e.target.value))}
             className="flex-1 accent-chirp-500"/>
      <span className="text-sm text-gray-300 w-12 text-right">{format ? format(value) : value}</span>
      </div>
  )
}

// ── config editor ─────────────────────────────────────────────────────────────

function ConfigEditor({ config, onChange, device }) {
  const d = config?.detection || {}
  const bn = d.birdnet || {}
  const ef = d.energy_filter || {}
  const bat = d.bat_echolocation || {}
  const r = config?.recording || {}
  const a = config?.audio || {}
  const sys = config?.system || {}
  const log = config?.logging || {}

  const set = (path, value) => {
    const parts = path.split('.')
    const next = JSON.parse(JSON.stringify(config || {}))
    let cur = next
    for (let i = 0; i < parts.length - 1; i++) {
      cur[parts[i]] = cur[parts[i]] || {}
      cur = cur[parts[i]]
    }
    cur[parts[parts.length - 1]] = value
    onChange(next)
  }

  const [sectionsOpen, setSectionsOpen] = useState({ birdnet: true, recording: false, audio: false, bat: false, system: false })
  const toggle = (k) => setSectionsOpen(s => ({ ...s, [k]: !s[k] }))

  const Section = ({ id, title, icon: Icon, children }) => (
    <div className="border border-surface-700 rounded-lg overflow-hidden">
      <button
        onClick={() => toggle(id)}
        className="w-full flex items-center justify-between px-4 py-3 bg-surface-800 hover:bg-surface-700 transition-colors text-left"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-gray-200">
          <Icon size={14} className="text-chirp-500"/> {title}
        </span>
        {sectionsOpen[id] ? <ChevronUp size={14} className="text-gray-500"/> : <ChevronDown size={14} className="text-gray-500"/>}
      </button>
      {sectionsOpen[id] && <div className="px-4 py-4 space-y-4 bg-surface-900">{children}</div>}
    </div>
  )

  return (
    <div className="space-y-3">
      {/* BirdNET */}
      <Section id="birdnet" title="BirdNET Analysis" icon={Activity}>
        <ConfigField label="Min. Detection Confidence"
          hint="Lower = more detections, more false positives. Default: 5%">
          <RangeSlider value={bn.min_confidence ?? 0.05} min={0.01} max={0.9} step={0.01}
            format={v => `${(v*100).toFixed(0)}%`}
            onChange={v => set('detection.birdnet.min_confidence', v)}/>
        </ConfigField>

        <ConfigField label="Sensitivity" hint="BirdNET sensitivity. Higher lifts faint and distant calls (night owls). Default: 1.5">
          <RangeSlider value={bn.sensitivity ?? 1.5} min={0.5} max={1.5} step={0.05}
            format={v => v.toFixed(2)}
            onChange={v => set('detection.birdnet.sensitivity', v)}/>
        </ConfigField>

        <ConfigField label="Window Overlap" hint="Overlap between consecutive 3s analysis windows. Default: 1.5s">
          <RangeSlider value={bn.overlap_seconds ?? 1.5} min={0} max={2.9} step={0.1}
            format={v => `${v.toFixed(1)}s`}
            onChange={v => set('detection.birdnet.overlap_seconds', v)}/>
        </ConfigField>

        <ConfigField label="Inference Backend"
          hint={!device?.coral_present
            ? 'No Coral TPU detected on this device.'
            : device.coral_model_present === true
              ? `Coral ${device.coral_form_factor === 'm2_pcie' ? 'M.2 PCIe' : device.coral_form_factor === 'usb' ? 'USB' : 'TPU'} detected — switch to Coral for ~8–10× faster inference.`
              : 'Coral detected, but no compiled BirdNET EdgeTPU model is on the device (none exists upstream yet), so BirdNET runs on the CPU.'}>
          <div className="flex gap-2">
            {['cpu', 'coral'].map(b => (
              <button key={b}
                onClick={() => set('detection.birdnet.backend', b)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors
                  ${(bn.backend ?? 'cpu') === b
                    ? 'bg-chirp-600/30 border-chirp-600 text-chirp-300'
                    : 'border-surface-600 text-gray-500 hover:border-surface-500'}
                  ${b === 'coral' && !device?.coral_present ? 'opacity-40' : ''}`}>
                {b === 'coral' ? <Zap size={11}/> : <Cpu size={11}/>}
                {b === 'coral'
                  ? (device?.coral_form_factor === 'm2_pcie' ? 'Coral M.2' : device?.coral_form_factor === 'usb' ? 'Coral USB' : 'Coral TPU')
                  : 'CPU'}
              </button>
            ))}
          </div>
        </ConfigField>

        <div className="grid grid-cols-2 gap-3">
          <ConfigField label="Latitude" hint="For species filtering">
            <NumberInput value={bn.latitude} min={-90} max={90} step={0.0001}
              onChange={v => set('detection.birdnet.latitude', v)}/>
          </ConfigField>
          <ConfigField label="Longitude">
            <NumberInput value={bn.longitude} min={-180} max={180} step={0.0001}
              onChange={v => set('detection.birdnet.longitude', v)}/>
          </ConfigField>
        </div>

        <ConfigField label="Energy Filter Threshold (dB)"
          hint="Audio must exceed this level to reach BirdNET. More negative = more sensitive. Above -70 dB gates out distant owls at night. Default: -90 dB">
          <RangeSlider value={ef.threshold_db ?? -90} min={-100} max={-30} step={1}
            format={v => `${v.toFixed(0)} dB`}
            onChange={v => set('detection.energy_filter.threshold_db', v)}/>
        </ConfigField>

        <ConfigField label="Energy Filter Low Cut (Hz)"
          hint="Lowest frequency the energy gate listens to. Keep at 150 Hz or below for Great Horned and Barred Owl hoots.">
          <NumberInput value={(ef.frequency_band_hz ?? [150, 12000])[0]} min={50} max={2000} step={10} unit="Hz"
            onChange={v => set('detection.energy_filter.frequency_band_hz', [v, (ef.frequency_band_hz ?? [150, 12000])[1]])}/>
        </ConfigField>

        <ConfigField label="Cooldown Between Detections (s)">
          <NumberInput value={d.cooldown_seconds ?? 10} min={1} max={300} step={1} unit="seconds"
            onChange={v => set('detection.cooldown_seconds', v)}/>
        </ConfigField>
      </Section>

      {/* Recording */}
      <Section id="recording" title="Recording" icon={Mic}>
        <ConfigField label="Recording Duration" hint="How long to record after trigger">
          <NumberInput value={r.duration_seconds ?? 30} min={5} max={300} step={5} unit="seconds"
            onChange={v => set('recording.duration_seconds', v)}/>
        </ConfigField>

        <ConfigField label="Max Duration (hard cap)">
          <NumberInput value={r.max_duration_seconds ?? 120} min={10} max={600} step={10} unit="seconds"
            onChange={v => set('recording.max_duration_seconds', v)}/>
        </ConfigField>

        <ConfigField label="Max Local Storage">
          <NumberInput value={r.max_disk_gb ?? 20} min={1} max={500} step={1} unit="GB"
            onChange={v => set('recording.max_disk_gb', v)}/>
        </ConfigField>

        <ConfigField label="Auto-delete Local Recordings After" hint="0 = never">
          <NumberInput value={r.auto_delete_days ?? 30} min={0} max={365} step={1} unit="days"
            onChange={v => set('recording.auto_delete_days', v)}/>
        </ConfigField>

        <ConfigField label="Max Recordings Per Hour" hint="Rate limit on this device. 0 = unlimited.">
          <NumberInput value={r.max_per_hour ?? 0} min={0} max={3600} step={1} unit="per hour"
            onChange={v => set('recording.max_per_hour', v)}/>
        </ConfigField>

        <div className="flex items-center gap-3">
          <input type="checkbox" id="extend_activity"
            checked={r.extend_on_activity ?? true}
            onChange={e => set('recording.extend_on_activity', e.target.checked)}
            className="w-4 h-4 accent-chirp-500"/>
          <label htmlFor="extend_activity" className="text-sm text-gray-300">
            Extend recording while bird continues calling
          </label>
        </div>

        <div className="flex items-center gap-3">
          <input type="checkbox" id="delete_after"
            checked={r.delete_after_upload ?? false}
            onChange={e => set('recording.delete_after_upload', e.target.checked)}
            className="w-4 h-4 accent-chirp-500"/>
          <label htmlFor="delete_after" className="text-sm text-gray-300">
            Delete local copy after successful upload
          </label>
        </div>
      </Section>

      {/* Audio */}
      <Section id="audio" title="Audio" icon={Mic}>
        <ConfigField label="Input Gain" hint="Software gain applied to all microphone inputs">
          <RangeSlider value={a.input_gain_db ?? 6} min={-20} max={20} step={0.5}
            format={v => `${v > 0 ? '+' : ''}${v.toFixed(1)} dB`}
            onChange={v => set('audio.input_gain_db', v)}/>
        </ConfigField>

        <ConfigField label="Max Microphone Count" hint="Maximum USB mics to use simultaneously">
          <NumberInput value={a.max_devices ?? 2} min={1} max={8} step={1}
            onChange={v => set('audio.max_devices', v)}/>
        </ConfigField>

        {(config?.respeaker?.xvf3800_output || device?.mic_names?.some(n => /3800|xvf|respeaker|seeed/i.test(n))) && (
          <ConfigField label="ReSpeaker XVF3800 Output"
            hint="Raw capsules skip the chip's voice processing (noise suppression, AGC, beamforming), which tends to erase faint, low, steady calls like owl hoots. Default: Raw">
            <div className="flex gap-2">
              {[['raw', 'Raw mics'], ['processed', 'Processed beam']].map(([v, label]) => (
                <button key={v}
                  onClick={() => set('respeaker.xvf3800_output', v)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors
                    ${(config?.respeaker?.xvf3800_output ?? 'raw') === v
                      ? 'bg-chirp-600/30 border-chirp-600 text-chirp-300'
                      : 'border-surface-600 text-gray-500 hover:border-surface-500'}`}>
                  {label}
                </button>
              ))}
            </div>
          </ConfigField>
        )}

        {/* Requested directly: a way to turn a specific connected mic on
            or off for detection without editing config.yaml by hand — to
            A/B a mic (e.g. temporarily disable the ReSpeaker to compare
            against a different setup) without unplugging anything.
            Writes the mic's exact reported name into the existing
            device_name_excludes list (already supported server/device-
            side — see config.yaml's own comment on it — this is the
            first UI for it). Only lists mics this device has actually
            reported having; nothing to show if none have been detected
            yet (e.g. right after first pairing, before a heartbeat). */}
        {device?.mic_names?.length > 0 && (
          <ConfigField label="Active Microphones" hint="Uncheck a mic to exclude it from bird detection entirely, without unplugging it — useful for comparing setups.">
            <div className="space-y-2">
              {device.mic_names.map(name => {
                const excludes = a.device_name_excludes || []
                const isExcluded = excludes.includes(name)
                return (
                  <label key={name} className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                    <input type="checkbox" checked={!isExcluded}
                           onChange={() => {
                             const next = isExcluded
                               ? excludes.filter(n => n !== name)
                               : [...excludes, name]
                             set('audio.device_name_excludes', next)
                           }}
                           className="rounded border-surface-600"/>
                    <span className={isExcluded ? 'text-gray-500 line-through' : ''}>{name}</span>
                  </label>
                )
              })}
            </div>
          </ConfigField>
        )}
      </Section>

      {/* Bat Detection */}
      <Section id="bat" title="Bat Detection" icon={Zap}>
        <ConfigField label="Mic Gain" hint="Software gain applied to the ultrasonic (bat) mic only — separate from the bird mic's Input Gain above, since it's usually a different device with its own sensitivity. Raise this if the mic-check live level reads too quiet to reliably trigger detections. Takes effect immediately, no restart needed.">
          <RangeSlider value={bat.gain_db ?? 0} min={-20} max={20} step={0.5}
            format={v => `${v > 0 ? '+' : ''}${v.toFixed(1)} dB`}
            onChange={v => set('detection.bat_echolocation.gain_db', v)}/>
        </ConfigField>
        <ConfigField label="Minimum Clip Length" hint="If clips are still coming out shorter than you'd like (e.g. under 1 second): raise this. A brief but genuine bat pass can naturally span well under a second; this is a hard floor — the clip's padding window is symmetrically expanded (equal time added before and after the detected pulses) until the total reaches this length, rather than only ever getting the small fixed padding below regardless of how short the actual pass was. Can only pad with real audio already captured in the rolling buffer, so right at startup there may occasionally be a little less than this available yet.">
          <RangeSlider value={bat.snippet_min_seconds ?? 2.0} min={0.5} max={10} step={0.5}
            format={v => `${v.toFixed(1)}s`}
            onChange={v => set('detection.bat_echolocation.snippet_min_seconds', v)}/>
        </ConfigField>
        <ConfigField label="Clip Padding" hint="Fixed buffer time added before the first pulse and after the last pulse of every event, regardless of how long the pass was. Raising this adds a bit more context to every clip, short or long.">
          <RangeSlider value={bat.snippet_padding_seconds ?? 0.5} min={0} max={3} step={0.1}
            format={v => `${v.toFixed(1)}s`}
            onChange={v => set('detection.bat_echolocation.snippet_padding_seconds', v)}/>
        </ConfigField>
        <ConfigField label="Maximum Clip Length" hint="Upper bound on total clip length, regardless of how long a continuous pulse train runs. A genuine continuous bat pass can legitimately run longer than a few seconds — raise this to capture longer real passes in full (more memory/upload per event); lower it to truncate anything longer to this length, keeping the most recent portion of the pass.">
          <RangeSlider value={bat.snippet_max_seconds ?? 20} min={5} max={60} step={1}
            format={v => `${v.toFixed(0)}s`}
            onChange={v => set('detection.bat_echolocation.snippet_max_seconds', v)}/>
        </ConfigField>
        <ConfigField label="Event Gap" hint="How long a gap of silence (no new pulse) means a bat's pass has actually ended, vs. just a brief pause within one continuous encounter. Raising this lets a single event span longer pauses — capturing more of a longer, intermittent pass as ONE event instead of splitting it into several — at the cost of delaying when a finished event actually gets saved, and a higher chance two genuinely separate passes get merged into one.">
          <RangeSlider value={bat.event_gap_seconds ?? 2.0} min={0.5} max={10} step={0.5}
            format={v => `${v.toFixed(1)}s`}
            onChange={v => set('detection.bat_echolocation.event_gap_seconds', v)}/>
        </ConfigField>
        <ConfigField label="Minimum Pulses" hint="How many echolocation pulses must be detected before a pass counts as a real event at all (vs. noise or a single stray pulse). Doesn't affect clip length directly — only whether a pass gets recorded in the first place.">
          <NumberInput value={bat.min_pulses_for_event ?? 3} min={1} max={20} step={1}
            onChange={v => set('detection.bat_echolocation.min_pulses_for_event', v)}/>
        </ConfigField>
      </Section>

      {/* System */}
      <Section id="system" title="System" icon={Settings2}>
        <ConfigField label="Timezone">
          <input
            type="text"
            value={sys.timezone ?? 'America/New_York'}
            onChange={e => set('system.timezone', e.target.value)}
            className="input w-full text-sm font-mono"
            placeholder="America/New_York"
          />
        </ConfigField>

        <ConfigField label="Log Level">
          <select
            value={log.level ?? 'INFO'}
            onChange={e => set('logging.level', e.target.value)}
            className="input text-sm"
          >
            {['DEBUG', 'INFO', 'WARNING', 'ERROR'].map(l => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </ConfigField>
      </Section>
      </div>
  )
}

// ── Device card ───────────────────────────────────────────────────────────────


// ── Inline IP editor ─────────────────────────────────────────────────────────
function IpField({ device, onUpdated }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal]         = useState(device.ip_address || '')
  const [saving, setSaving]   = useState(false)
  const [err, setErr]         = useState(null)
  const isIPv6 = (device.ip_address || '').includes(':')

  const save = async () => {
    if (!val.trim()) return
    setSaving(true); setErr(null)
    try {
      const d = await api.devices.setIp(device.id, val.trim())
      onUpdated({ ...device, ip_address: d.ip_address })
      setEditing(false)
    } catch (e) { setErr(e.message) }
    setSaving(false)
  }

  if (editing) return (
    <span className="flex items-center gap-1 text-xs">
      <Wifi size={12} className="text-gray-600 flex-shrink-0"/>
      <input autoFocus value={val} onChange={e => setVal(e.target.value)}
             className="input py-0 px-1.5 text-xs w-36"
             placeholder="192.168.x.x"
             onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false) }}/>
      <button onClick={save} disabled={saving} className="btn-icon p-0.5">
        {saving ? <RefreshCw size={11} className="animate-spin"/> : <Check size={11}/>}
      </button>
      <button onClick={() => setEditing(false)} className="btn-icon p-0.5"><X size={11}/></button>
      {err && <span className="text-red-400">{err}</span>}
    </span>
  )

  return (
    <button onClick={() => { setVal(device.ip_address || ''); setEditing(true) }}
            className="flex items-center gap-1.5 text-xs hover:text-chirp-400 transition-colors group"
            style={{ color: isIPv6 ? 'var(--pastel-amber)' : 'rgb(75 85 99)' }}
            title={isIPv6 ? 'IPv6 detected — click to enter IPv4 address for SSH' : 'Click to edit IP'}>
      <Wifi size={12}/>
      <span>{device.ip_address || 'Set IP…'}</span>
      {isIPv6 && <span className="text-yellow-500 font-medium">(IPv6 — set IPv4)</span>}
      <Edit2 size={10} className="opacity-0 group-hover:opacity-60 transition-opacity"/>
    </button>
  )
}

function DeviceCard({ device, onUpdated, onDeleted, serverHasLocation, onOpenSsh, onOpenLogs }) {
  const [expanded, setExpanded] = useState(false)
  const [showMicTest, setShowMicTest] = useState(false)
  const [editing, setEditing] = useState(false)
  const [nameInput, setNameInput] = useState(device.name)
  const [config, setConfig] = useState(device.managed_config || {})
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [dismissing, setDismissing] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const pendingConfig = device.config_version !== device.config_applied_version

  const handleSaveName = async () => {
    if (!nameInput.trim()) return
    try {
      const d = await api.devices.rename(device.id, nameInput.trim())
      onUpdated(d)
      setEditing(false)
    } catch (e) {
      setError('Rename failed')
    }
  }

  const handlePushConfig = async () => {
    setSaving(true)
    setError(null)
    try {
      const d = await api.devices.pushConfig(device.id, config)
      onUpdated(d)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (e) {
      setError('Push failed: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const set = (key, val) => setConfig(c => ({ ...c, [key]: val }))

  // Coral nudge: TPU present but not in use. Either the config still says
  // CPU, or Coral is selected and the device fell back to CPU at runtime.
  // Only offered when the device has a compiled BirdNET EdgeTPU model —
  // without one, Coral can't run BirdNET and CPU is the right backend.
  const configuredBackend = device.managed_config?.detection?.birdnet?.backend ?? 'cpu'
  const coralUsable = device.coral_present && device.coral_model_present === true
  const coralFellBack = device.coral_present && device.birdnet_backend !== 'coral' && configuredBackend === 'coral' && !pendingConfig
  const coralIdle = coralFellBack || (coralUsable && device.birdnet_backend !== 'coral')
  const [switchingCoral, setSwitchingCoral] = useState(false)

  const [savingVia, setSavingVia] = useState(false)
  const handleConnectVia = async (via) => {
    setSavingVia(true)
    setError(null)
    try {
      onUpdated(await api.devices.setConnectVia(device.id, via))
    } catch (e) {
      setError('Could not change connection: ' + e.message)
    } finally {
      setSavingVia(false)
    }
  }

  const handleSwitchBackend = async (backend) => {
    setSwitchingCoral(true)
    setError(null)
    try {
      const next = JSON.parse(JSON.stringify(device.managed_config || {}))
      next.detection = next.detection || {}
      next.detection.birdnet = { ...(next.detection.birdnet || {}), backend }
      const d = await api.devices.pushConfig(device.id, next)
      setConfig(d.managed_config)
      onUpdated(d)
    } catch (e) {
      setError(`Switch to ${backend === 'coral' ? 'Coral' : 'CPU'} failed: ` + e.message)
    } finally {
      setSwitchingCoral(false)
    }
  }

  const handleSyncLocation = async () => {
    setSyncing(true)
    setError(null)
    try {
      const d = await api.devices.syncLocation(device.id)
      setConfig(d.managed_config)
      onUpdated(d)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (e) {
      setError(e.message || 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  const handleDismissPending = async () => {
    // Only ever tells the SERVER's bookkeeping "treat this as applied" —
    // config_applied_version is reported BY THE DEVICE on every
    // heartbeat, so this doesn't survive a real, still-pending change:
    // it'll show Pending again on the device's very next heartbeat if
    // the device genuinely hasn't applied it. Safe for a false-positive
    // pending state; not a way to skip a real one — the confirm below
    // says as much rather than letting this look like a silent fix.
    if (!window.confirm("Mark this device's pending config as already applied?\n\nThis only updates what the server tracks — it doesn't send anything to the device. If the device genuinely hasn't applied this config yet, it'll show Pending again on its next heartbeat.")) return
    setDismissing(true)
    setError(null)
    try {
      const d = await api.devices.dismissPendingConfig(device.id)
      onUpdated(d)
    } catch (e) {
      setError(e.message || 'Dismiss failed')
    } finally {
      setDismissing(false)
    }
  }

  const handleDelete = async () => {
    try {
      await api.devices.unpair(device.id)
      onDeleted(device.id)
    } catch (e) {
      setError('Unpair failed')
      setConfirmDelete(false)
    }
  }

  return (
    <div className="card overflow-hidden">
      {/* Header row */}
      <div className="px-4 py-3 border-b border-surface-700 flex flex-wrap items-center gap-3">
        <div className={`p-2 rounded-lg ${device.status === 'online' ? 'bg-chirp-900/40' : 'bg-surface-800'}`}>
          {device.birdnet_backend === 'bird_buddy'
            ? <BirdBuddyIcon size={16} className={device.status === 'online' ? 'text-chirp-400' : 'text-gray-600'}/>
            : device.status === 'online'
            ? <Radio size={16} className="text-chirp-400"/>
            : <WifiOff size={16} className="text-gray-600"/>}
        </div>
        <div className="flex-1 min-w-0">
          {editing ? (
            <div className="flex items-center gap-2">
              <input value={nameInput} onChange={e => setNameInput(e.target.value)}
                     className="input text-sm py-1 flex-1" autoFocus
                     onKeyDown={e => { if (e.key === 'Enter') handleSaveName(); if (e.key === 'Escape') setEditing(false) }}/>
              <button onClick={handleSaveName} className="p-1 text-chirp-400 hover:text-chirp-300"><Check size={14}/></button>
              <button onClick={() => setEditing(false)} className="p-1 text-gray-500 hover:text-gray-400"><X size={14}/></button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-white truncate">{device.name}</h3>
              <button onClick={() => setEditing(true)} className="p-0.5 text-gray-600 hover:text-gray-400 flex-shrink-0">
                <Edit2 size={12}/>
              </button>
            </div>
          )}
          <div className="flex items-center gap-3 mt-0.5 flex-wrap">
            <StatusBadge status={device.status}/>
            {device.last_seen && (
              <span className="text-xs text-gray-600">{timeAgo(device.last_seen)}</span>
            )}
            {device.last_recording_at && (
              <span className="text-xs text-gray-600">· last recording {timeAgo(device.last_recording_at)}</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap justify-end w-full sm:w-auto sm:flex-shrink-0">
          {pendingConfig && (
            <span className="text-xs text-yellow-400 bg-yellow-900/30 border border-yellow-700/50 px-2 py-0.5 rounded-full flex items-center gap-1">
              <AlertCircle size={10}/> Config pending
            </span>
          )}
          {(device.ip_address || device.tailscale_ip) && (
            <button
              onClick={e => { e.stopPropagation(); onOpenSsh && onOpenSsh(device) }}
              className="p-1.5 rounded-lg transition-colors"
              style={{ color: '#58a6ff', background: 'rgba(88,166,255,0.1)' }}
              title="Open SSH terminal">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>
              </svg>
            </button>
          )}
          {device.tailscale_ip && (
            <span
              className="text-xs px-1.5 py-0.5 rounded-full flex items-center gap-1 flex-shrink-0"
              style={{ color: '#8b5cf6', background: 'rgba(139,92,246,0.12)' }}
              title={`Reachable over Tailscale at ${device.tailscale_ip}, not just the local network`}>
              <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/></svg>
              Tailscale
            </span>
          )}
          {device.ip_address && (
            <button
              onClick={e => { e.stopPropagation(); onOpenLogs && onOpenLogs(device) }}
              className="p-1.5 rounded-lg transition-colors"
              style={{ color: 'var(--pastel-yellow)', background: 'rgba(234,179,8,0.1)' }}
              title="View device logs">
              <FileText size={14}/>
            </button>
          )}
          <button onClick={() => setExpanded(e => !e)}
            className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-surface-700 transition-colors">
            {expanded ? <ChevronUp size={16}/> : <ChevronDown size={16}/>}
          </button>
        </div>
      </div>

      {/* Hardware summary (always visible) */}
      <div className="px-4 py-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {device.platform && (
          <span className="flex items-center gap-1.5 text-xs text-gray-400">
            <Cpu size={12} className="text-gray-600"/> {device.platform}
          </span>
        )}
        <span className="flex items-center gap-1.5 text-xs text-gray-400">
          <Mic size={12} className="text-gray-600"/> {device.mic_count} mic{device.mic_count !== 1 ? 's' : ''}
          {device.mic_names?.length > 0 && <span className="text-gray-600 truncate max-w-24">({device.mic_names[0]})</span>}
        </span>
        <span className={`flex items-center gap-1.5 text-xs ${device.coral_present ? 'text-chirp-400' : 'text-gray-600'}`}>
          <Zap size={12}/>
          {device.coral_present
            ? (device.coral_form_factor === 'm2_pcie'
                ? 'Coral M.2 PCIe'
                : device.coral_form_factor === 'usb'
                  ? 'Coral USB'
                  : 'Coral TPU')
            : 'CPU only'}
        </span>
        <IpField device={device} onUpdated={onUpdated}/>
        {device.hostname && (
          <span className="flex items-center gap-1.5 text-xs text-gray-600">
            {device.hostname}
          </span>
        )}
      </div>

      {coralIdle && device.platform !== 'Haikubox' && (
        <div className="mx-4 mb-3 flex items-center gap-2 px-3 py-2 rounded-lg text-xs"
             style={{ background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.35)' }}>
          <Zap size={13} style={{ color: 'var(--pastel-yellow)' }} className="flex-shrink-0"/>
          <span className="flex-1" style={{ color: 'var(--text-secondary)' }}>
            {coralFellBack
              ? (device.coral_model_present === false
                  ? 'Coral is selected but there is no BirdNET EdgeTPU model on the device, so it runs on CPU. Switch the backend back to CPU.'
                  : 'Coral is selected but the device is running BirdNET on CPU — the TPU failed to load. Check the device logs for "Coral".')
              : configuredBackend === 'coral'
                ? 'Coral selected — waiting for the device to apply it.'
                : 'Coral TPU detected but BirdNET is running on CPU. Coral is ~8× faster and avoids dropped windows at night.'}
          </span>
          {coralFellBack && !pendingConfig && (
            <button onClick={() => handleSwitchBackend('cpu')} disabled={switchingCoral}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-md font-medium flex-shrink-0 bg-chirp-600/30 border border-chirp-600 text-chirp-300 hover:bg-chirp-600/50">
              {switchingCoral ? <RefreshCw size={11} className="animate-spin"/> : <Cpu size={11}/>}
              {switchingCoral ? 'Switching…' : 'Switch to CPU'}
            </button>
          )}
          {configuredBackend !== 'coral' && (
            <button onClick={() => handleSwitchBackend('coral')} disabled={switchingCoral}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-md font-medium flex-shrink-0 bg-chirp-600/30 border border-chirp-600 text-chirp-300 hover:bg-chirp-600/50">
              {switchingCoral ? <RefreshCw size={11} className="animate-spin"/> : <Zap size={11}/>}
              {switchingCoral ? 'Switching…' : 'Switch to Coral'}
            </button>
          )}
        </div>
      )}

      {/* Expanded: config editor */}
      {expanded && (
        <div className="border-t border-surface-700 px-4 py-4 space-y-4">
          {/* Config version status */}
          <div className="flex items-center justify-between text-xs text-gray-500">
            <span>
              Config {formatConfigVersion(device.config_version)} ·{' '}
              {device.config_version === device.config_applied_version
                ? <span style={{ color: 'var(--accent-400)' }}>✓ Applied</span>
                : <span style={{ color: 'var(--pastel-amber)' }}>Pending (device: {formatConfigVersion(device.config_applied_version)})</span>
              }
            </span>
            {pendingConfig
              ? (
                <span className="flex items-center gap-2">
                  <span className="text-yellow-400">Waiting for device to apply…</span>
                  <button onClick={handleDismissPending} disabled={dismissing}
                          className="text-gray-500 hover:text-gray-300 underline underline-offset-2"
                          title="Mark as already applied — only updates the server's own bookkeeping, doesn't send anything to the device">
                    {dismissing ? 'Dismissing…' : 'Dismiss'}
                  </button>
                </span>
              )
              : <span className="text-chirp-500">✓ In sync</span>}
          </div>

          {/* Location sync */}
          <div className="flex items-center gap-2 p-3 rounded-lg bg-surface-800 border border-surface-700">
            <MapPin size={14} className="text-chirp-500 flex-shrink-0"/>
            <p className="text-xs text-gray-400 flex-1">
              Sync server location (lat/lon/timezone) to this device's BirdNET config
            </p>
            <button
              onClick={handleSyncLocation}
              disabled={syncing || !serverHasLocation}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex-shrink-0
                ${serverHasLocation
                  ? 'bg-chirp-600/30 border border-chirp-600 text-chirp-300 hover:bg-chirp-600/50'
                  : 'bg-surface-700 border border-surface-600 text-gray-600 cursor-not-allowed'}`}>
              {syncing ? <RefreshCw size={11} className="animate-spin"/> : <MapPin size={11}/>}
              {syncing ? 'Syncing…' : serverHasLocation ? 'Sync Location' : 'No server location set'}
            </button>
          </div>

          {/* Config editor */}
          <ConfigEditor config={config} onChange={setConfig} device={device}/>

          {/* Mic test — pre-selects this device's mic so it's not up to
              the person to find it again in a device dropdown elsewhere */}
          <div className="space-y-2 pt-2 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <button onClick={() => setShowMicTest(v => !v)}
                    className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide"
                    style={{ color: 'var(--text-tertiary)', letterSpacing: '.06em' }}>
              <AudioLines size={12}/> Test Microphone
              {showMicTest ? <ChevronUp size={12}/> : <ChevronDown size={12}/>}
            </button>
            {showMicTest && <MicFrequencyResponse defaultDeviceId={device.id}/>}
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 text-xs text-red-400 bg-red-900/20 border border-red-800/50 rounded-lg px-3 py-2">
              <AlertCircle size={12}/> {error}
            </div>
          )}

          {/* How the server reaches the device (SSH, logs, Listen, mic levels) */}
          <div className="space-y-2 pt-2 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text-tertiary)', letterSpacing: '.06em' }}>
              Server Connects Via
            </p>
            <div className="flex gap-2">
              {[['auto', 'Auto'], ['lan', 'LAN IP'], ['tailscale', 'Tailscale']].map(([v, label]) => (
                <button key={v} onClick={() => handleConnectVia(v)} disabled={savingVia || (v === 'tailscale' && !device.tailscale_ip)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors
                    ${(device.connect_via || 'auto') === v
                      ? 'bg-chirp-600/30 border-chirp-600 text-chirp-300'
                      : 'border-surface-600 text-gray-500 hover:border-surface-500'}
                    ${v === 'tailscale' && !device.tailscale_ip ? 'opacity-40 cursor-not-allowed' : ''}`}>
                  {label}
                </button>
              ))}
            </div>
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              {device.connect_address
                ? <>Using <span className="font-mono">{device.connect_address}</span>{device.connect_address === device.tailscale_ip ? ' (Tailscale)' : ' (LAN)'}. </>
                : 'No address yet. '}
              Auto uses Tailscale when the server is on the tailnet and the device has a Tailscale IP, and falls back to the LAN IP.
            </p>
          </div>

          {/* SSH Credentials */}
          <div className="space-y-2 pt-2 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text-tertiary)', letterSpacing: '.06em' }}>
              SSH Credentials
            </p>
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              Used for log viewing. Saved with config — click Push Config to store.
            </p>
            <div className="flex gap-2">
              <div className="flex-1">
                <label className="text-xs mb-1 block" style={{ color: 'var(--text-secondary)' }}>Username</label>
                <input className="input text-xs py-1.5 w-full"
                       value={config?.ssh_user ?? 'pi'}
                       onChange={e => set('ssh_user', e.target.value)}
                       placeholder="pi"/>
              </div>
              <div className="flex-1">
                <label className="text-xs mb-1 block" style={{ color: 'var(--text-secondary)' }}>Password</label>
                <input type="password" className="input text-xs py-1.5 w-full"
                       value={config?.ssh_password ?? ''}
                       onChange={e => set('ssh_password', e.target.value)}
                       placeholder="Leave blank if key auth works"/>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between pt-2">
            {!confirmDelete ? (
              <button onClick={() => setConfirmDelete(true)}
                className="flex items-center gap-1.5 text-xs text-red-500 hover:text-red-400 transition-colors">
                <Trash2 size={12}/> Unpair device
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-xs text-red-400">Confirm unpair?</span>
                <button onClick={handleDelete} className="text-xs text-red-400 border border-red-700 px-2 py-1 rounded hover:bg-red-900/30">Yes</button>
                <button onClick={() => setConfirmDelete(false)} className="text-xs text-gray-500 border border-surface-600 px-2 py-1 rounded hover:bg-surface-700">No</button>
              </div>
            )}

            <button
              onClick={handlePushConfig}
              disabled={saving}
              className="flex items-center gap-1.5 btn-primary py-2 px-4 text-sm">
              {saving ? <RefreshCw size={14} className="animate-spin"/> : saved ? <Check size={14}/> : <Activity size={14}/>}
              {saving ? 'Pushing…' : saved ? 'Pushed!' : 'Push Config to Device'}
            </button>
          </div>
        </div>
      )}
      </div>
  )
}


// ── Discovered device row ─────────────────────────────────────────────────────

function ThirdPartyDeviceRow({ d, onUpdated }) {
  const [editing, setEditing] = useState(false)
  const [nameInput, setNameInput] = useState(d.name)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (!nameInput.trim() || nameInput.trim() === d.name) { setEditing(false); return }
    setSaving(true)
    try {
      const updated = await api.devices.rename(d.id, nameInput.trim())
      onUpdated(updated)
    } catch (e) { alert(e.message) }
    setSaving(false)
    setEditing(false)
  }

  return (
    <div className="px-4 py-3 flex items-center justify-between gap-3 text-sm">
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <span className="w-2 h-2 rounded-full flex-shrink-0" style={{
          background: d.status === 'online' ? '#4ade80' : d.status === 'offline' ? '#f87171' : '#6b7280'
        }}/>
        {editing ? (
          <input autoFocus value={nameInput} onChange={e => setNameInput(e.target.value)}
                 onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false) }}
                 onBlur={save} disabled={saving}
                 className="input text-sm py-0.5 px-2 flex-1 min-w-0"/>
        ) : (
          <>
            <span className="text-gray-200 truncate">{d.name}</span>
            <button onClick={() => { setNameInput(d.name); setEditing(true) }}
                    className="text-gray-600 hover:text-gray-300 flex-shrink-0" aria-label="Rename">
              <Edit2 size={11}/>
            </button>
          </>
        )}
      </div>
      <div className="flex items-center gap-4 text-xs text-gray-500 flex-shrink-0">
        <span className="hidden sm:inline">{d.bird_buddy_feeder_id || d.id.slice(0, 8)}</span>
        <span>{d.last_recording_at ? timeAgo(d.last_recording_at) : 'No recordings yet'}</span>
      </div>
    </div>
  )
}

function ThirdPartyDeviceGroup({ label, icon: Icon, devices, defaultOpen = false, onUpdated }) {
  const [open, setOpen] = useState(defaultOpen)
  if (!devices.length) return null
  return (
    <div className="card overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-700 transition-colors text-left">
        <span className="flex items-center gap-2 text-sm font-medium text-gray-200">
          <Icon size={14} className="text-chirp-500"/>
          {label} <span className="text-gray-500 font-normal">· {devices.length}</span>
        </span>
        {open ? <ChevronUp size={14} className="text-gray-500"/> : <ChevronDown size={14} className="text-gray-500"/>}
      </button>
      {open && (
        <div className="divide-y divide-surface-700">
          {devices.map(d => <ThirdPartyDeviceRow key={d.id} d={d} onUpdated={onUpdated}/>)}
        </div>
      )}
    </div>
  )
}

function DiscoveredDeviceRow({ result, onRefresh }) {
  // Hooks must run unconditionally on every render — the guard for an
  // invalid `result` prop was previously BEFORE these declarations, which
  // is a React rules-of-hooks violation: if `result` is sometimes valid and
  // sometimes not across renders of the same component instance (e.g. a
  // live discovery scan re-rendering this row with updated/filtered data),
  // React calls a different number of hooks on different renders, which can
  // silently corrupt state (the wrong hook slot's value bleeding into a
  // different state variable) or crash with "Rendered fewer hooks than
  // expected". Moved the guard below, after all hooks, so it only affects
  // what gets rendered, never which hooks get called.
  const [pushing, setPushing] = useState(false)
  const [pushed, setPushed] = useState(false)
  const [error, setError] = useState(null)
  const [showSsh, setShowSsh] = useState(false)
  const [sshUser, setSshUser] = useState('pi')
  const [sshPass, setSshPass] = useState('')
  const [serverUrl, setServerUrl] = useState(window.location.origin)

  if (!result || typeof result !== 'object') return null

  const handlePush = async () => {
    if (!sshPass && !pushed) { setShowSsh(true); return }
    setPushing(true)
    setError(null)
    try {
      const res = await api.devices.pushCredentials({
        ip: result.ip,
        ssh_user: sshUser,
        ssh_password: sshPass,
        key_name: result.hostname || result.ip,
        server_url: serverUrl,
      })
      if (res.ok) {
        setPushed(true)
        setShowSsh(false)
        setTimeout(onRefresh, 3000)  // check if device paired
      } else {
        setError(res.error || 'Push failed')
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setPushing(false)
    }
  }

  return (
    <div className="border border-surface-700 rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-2 h-2 rounded-full flex-shrink-0 ${result.chirp_device ? 'bg-chirp-500' : 'bg-yellow-500'}`}/>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-white">{result.hostname || result.ip}</span>
              {result.chirp_device && (
                <span className="text-xs bg-chirp-900/40 text-chirp-400 border border-chirp-700/50 px-1.5 py-0.5 rounded">
                  chirp-device
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-0.5">
              <span className="text-xs text-gray-500">{result.ip}</span>
              {result.ssh_available && (
                <span className="text-xs text-gray-600 flex items-center gap-1">
                  <Check size={10}/> SSH
                </span>
              )}
            </div>
          </div>
        </div>
        {!pushed ? (
          <button
            onClick={handlePush}
            disabled={pushing}
            className="flex items-center gap-1.5 btn-primary py-1.5 px-3 text-xs">
            {pushing ? <RefreshCw size={11} className="animate-spin"/> : <Zap size={11}/>}
            {pushing ? 'Pushing…' : 'Auto-configure'}
          </button>
        ) : (
          <span className="flex items-center gap-1.5 text-xs text-chirp-400">
            <Check size={11}/> Configured — waiting for pair…
          </span>
        )}
      </div>

      {showSsh && !pushed && (
        <div className="border-t border-surface-700 pt-2 space-y-2">
          <p className="text-xs text-gray-400">
            SSH credentials to write config to the Pi. The server generates a new API key,
            writes it to <code className="text-chirp-400">config.yaml</code>, and restarts chirp-device.
          </p>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">SSH User</label>
              <input value={sshUser} onChange={e => setSshUser(e.target.value)}
                className="input w-full text-xs py-1.5" placeholder="pi"/>
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">SSH Password</label>
              <input type="password" value={sshPass} onChange={e => setSshPass(e.target.value)}
                className="input w-full text-xs py-1.5" placeholder="raspberry"
                onKeyDown={e => e.key === 'Enter' && handlePush()}/>
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Server URL (what Pi will connect to)</label>
            <input value={serverUrl} onChange={e => setServerUrl(e.target.value)}
              className="input w-full text-xs py-1.5 font-mono"/>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setShowSsh(false)} className="btn-secondary px-3 py-1 text-xs">Cancel</button>
            <button onClick={handlePush} disabled={pushing || !sshPass}
              className="btn-primary px-3 py-1 text-xs flex items-center gap-1">
              {pushing ? <RefreshCw size={11} className="animate-spin"/> : <Zap size={11}/>}
              Push Credentials
            </button>
          </div>
        </div>
      )}

      {/* No SSH terminal here — discovered devices connect via Auto-configure above */}
      {result.ip && result.ssh_available && (
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          SSH available · use Auto-configure to pair
        </p>
      )}

      {error && (
        <p className="text-xs text-red-400 flex items-center gap-1.5">
          <AlertCircle size={11}/> {error}
        </p>
      )}
      </div>
  )
}

// ── New device key modal ──────────────────────────────────────────────────────

function NewKeyModal({ onClose, onCreate }) {
  const [name, setName] = useState('')
  const [created, setCreated] = useState(null)
  const [copied, setCopied] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleCreate = async () => {
    if (!name.trim()) return
    setLoading(true)
    try {
      const k = await api.settings.deviceKeys.create(name.trim())
      setCreated(k)
      onCreate(k)
    } catch (e) {
      alert('Failed: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(created.key)
    hapticEvent('success')
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="card w-full max-w-md p-6 space-y-4">
        <h2 className="text-lg font-semibold text-white">Generate Device Key</h2>

        {!created ? (
          <>
            <p className="text-sm text-gray-400">
              Give this key a name (e.g. "Garden Pi"), then copy the generated key into your Pi's <code className="text-chirp-400">config.yaml</code>.
            </p>
            <input
              className="input w-full"
              placeholder="Key name (e.g. Garden Pi)"
              value={name}
              onChange={e => setName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <button onClick={onClose} className="btn-secondary px-4 py-2 text-sm">Cancel</button>
              <button onClick={handleCreate} disabled={!name.trim() || loading}
                className="btn-primary px-4 py-2 text-sm flex items-center gap-2">
                {loading ? <RefreshCw size={14} className="animate-spin"/> : <Plus size={14}/>}
                Generate
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="p-3 rounded-lg bg-chirp-900/30 border border-chirp-700/50">
              <p className="text-xs text-chirp-400 mb-2 font-medium">⚠️ Copy this key now — it won't be shown again.</p>
              <div className="flex items-center gap-2">
                <code className="text-xs text-gray-200 font-mono flex-1 break-all bg-surface-950 px-2 py-1.5 rounded">
                  {created.key}
                </code>
                <button onClick={handleCopy}
                  className="flex-shrink-0 p-1.5 rounded text-gray-400 hover:text-white hover:bg-surface-700 transition-colors">
                  {copied ? <Check size={14} className="text-chirp-400"/> : <Copy size={14}/>}
                </button>
              </div>
            </div>
            <p className="text-sm text-gray-400">
              Add this to your Pi's <code className="text-chirp-400">config.yaml</code>:
            </p>
            <pre className="text-xs bg-surface-950 rounded-lg p-3 text-gray-300 overflow-x-auto">{`server_sync:
  enabled: true
  server_url: "https://YOUR_SERVER_URL"
  api_key: "${created.key}"`}</pre>
            <button onClick={onClose} className="w-full btn-primary py-2 text-sm">Done</button>
          </>
        )}
      </div>
      </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────


// ── Device Log Viewer ────────────────────────────────────────────────────────
function DeviceLogViewer({ device, onClose }) {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lines, setLines] = useState(200)
  const bottomRef = useRef(null)

  const load = async (n = lines) => {
    setLoading(true); setError(null)
    try {
      const r = await api.devices.logs(device.id, n)
      setLogs(r.lines || [])
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (e) {
      setError(e.message || 'Could not fetch logs — check SSH access to the device.')
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [device.id])

  const levelColor = (line) => {
    if (/error|ERROR|CRITICAL|critical/i.test(line)) return 'var(--pastel-red)'
    if (/warn|WARNING/i.test(line)) return 'var(--pastel-yellow)'
    if (/INFO/i.test(line)) return 'var(--text-primary)'
    if (/DEBUG/i.test(line)) return 'var(--text-tertiary)'
    return 'var(--text-secondary)'
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col" style={{ background: 'var(--bg-base)' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b flex-shrink-0"
           style={{ background: 'var(--bg-panel)', borderColor: 'var(--border-subtle)' }}>
        <div className="flex items-center gap-3">
          <Server size={16} style={{ color: 'var(--accent-400)' }}/>
          <div>
            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              {device.name} — Logs
            </p>
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              {device.ip_address || 'IP unknown'} · via SSH
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select className="input text-xs" style={{ width: 100, padding: '4px 8px' }}
                  value={lines} onChange={e => { setLines(parseInt(e.target.value, 10)); load(parseInt(e.target.value, 10)) }}>
            <option value={50}>50 lines</option>
            <option value={200}>200 lines</option>
            <option value={500}>500 lines</option>
          </select>
          <button onClick={() => load(lines)} disabled={loading} className="btn-icon">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''}/>
          </button>
          <button onClick={onClose} className="btn-icon">
            <X size={14}/>
          </button>
        </div>
      </div>

      {/* Log output */}
      <div className="flex-1 overflow-y-auto p-4"
           style={{ background: '#050a05', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>
        {loading && <p style={{ color: 'var(--text-tertiary)' }}>Fetching logs via SSH…</p>}
        {error && (
          <div className="rounded-xl p-4 mb-4" style={{ background: 'rgba(239,68,68,.08)', border: '1px solid rgba(239,68,68,.2)', color: 'var(--pastel-red)' }}>
            {error}
          </div>
        )}
        {!loading && logs.length === 0 && !error && (
          <p style={{ color: 'var(--text-tertiary)' }}>No log output received.</p>
        )}
        {logs.map((line, i) => (
          <div key={i} style={{ color: levelColor(line), lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {line}
          </div>
        ))}
        <div ref={bottomRef}/>
      </div>
      </div>
  )
}

function DevicesInner() {
  const [devices, setDevices] = useState([])
  const [sshDevice, setSshDevice] = useState(null)
  const [logsDevice, setLogsDevice] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showNewKey, setShowNewKey] = useState(false)
  const [serverHasLocation, setServerHasLocation] = useState(false)
  const [discovering, setDiscovering] = useState(false)
  const [discovered, setDiscovered] = useState([])
  const [discoverError, setDiscoverError] = useState(null)
  const [showDiscovery, setShowDiscovery] = useState(false)
  const [haikuboxOpen, setHaikuboxOpen] = useState(false)   // collapsed by default
  const [appSettings, setAppSettings] = useState(null)
  const [userRole, setUserRole] = useState('admin')
  useEffect(() => {
    // Determine current user role to gate admin-only sections — same
    // pattern as Settings.jsx. Real fix for a previous version of this:
    // isAdmin defaulted to true with a comment claiming it would be
    // "narrowed once role loads," but nothing ever called its setter, so
    // every user regardless of actual role saw the admin-only Haikubox
    // serial number field below.
    api.auth.me()
      .then(r => (r && typeof r.json === 'function') ? r.json() : r)
      .then(u => { if (u?.role) setUserRole(u.role) })
      .catch(() => {}) // Auth disabled = open access, leave default 'admin'
  }, [])
  const isAdmin = userRole === 'admin'
  const [haikuboxSerial, setHaikuboxSerial] = useState('')
  const [haikuboxSaving, setHaikuboxSaving] = useState(false)
  const [haikuboxSaved, setHaikuboxSaved] = useState(false)

  const [haikuboxStatus, setHaikuboxStatus] = useState(null)
  const [haikuboxSyncing, setHaikuboxSyncing] = useState(false)
  const [haikuboxSyncMsg, setHaikuboxSyncMsg] = useState(null)

  useEffect(() => {
    api.settings.haikubox.status().then(setHaikuboxStatus).catch(() => {})
  }, [])

  const load = useCallback(async () => {
    try {
      const [devs, settings] = await Promise.all([
        api.devices.list(),
        api.settings.get(),
      ])
      setDevices(devs)
      setServerHasLocation(!!(settings.latitude && settings.longitude))
      setAppSettings(settings)
    } catch (e) {
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const iv = setInterval(load, 30000) // refresh every 30s for heartbeat status
    return () => clearInterval(iv)
  }, [load])

  const handleDiscover = async () => {
    setDiscovering(true)
    setDiscoverError(null)
    setDiscovered([])
    setShowDiscovery(true)
    try {
      const results = await api.devices.discover()
      // Guard: backend may return error object instead of array
      const list = Array.isArray(results) ? results : []
      setDiscovered(list)
      if (list.length === 0) setDiscoverError('No Raspberry Pi devices found on the local network. Make sure the Pi is on the same subnet as the server.')
    } catch (e) {
      setDiscovering(false)
      setDiscoverError('Discovery failed: ' + (e.message || 'Unknown error'))
    } finally {
      setDiscovering(false)
    }
  }

  const handleUpdated = (updated) => {
    setDevices(ds => ds.map(d => d.id === updated.id ? updated : d))
  }

  const handleDeleted = (id) => {
    setDevices(ds => ds.filter(d => d.id !== id))
  }

  const handleSaveHaikuboxSerial = async () => {
    setHaikuboxSaving(true)
    setHaikuboxSaved(false)
    try {
      const updated = await api.settings.update({ haikubox_serial: haikuboxSerial })
      setAppSettings(updated)
      setHaikuboxSerial('')
      setHaikuboxSaved(true)
      setTimeout(() => setHaikuboxSaved(false), 3000)
      // Trigger an immediate sync and refresh status
      api.settings.haikubox.sync().catch(() => {})
      setTimeout(() => api.settings.haikubox.status().then(setHaikuboxStatus).catch(() => {}), 3000)
    } catch (e) {
    } finally {
      setHaikuboxSaving(false)
    }
  }

  const handleHaikuboxSync = async () => {
    setHaikuboxSyncing(true)
    setHaikuboxSyncMsg(null)
    try {
      await api.settings.haikubox.sync()
      setHaikuboxSyncMsg('Sync started — new detections will appear shortly.')
      setTimeout(() => {
        api.settings.haikubox.status().then(s => { setHaikuboxStatus(s); setHaikuboxSyncMsg(null) }).catch(() => {})
      }, 4000)
    } catch (e) {
      setHaikuboxSyncMsg('Sync failed: ' + (e.message || 'unknown error'))
    } finally {
      setHaikuboxSyncing(false)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="text-chirp-500 animate-pulse">Loading devices…</div>
    </div>
  )

  const onlineCount = devices.filter(d => d.status === 'online').length

  return (
    <div className="p-4 md:p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Devices</h1>
          <p className="text-sm text-gray-400 mt-1">
            {devices.length === 0 ? 'No paired devices' : `${devices.length} paired · ${onlineCount} online`}
          </p>
        </div>
        {/* Reported directly: this row caused horizontal scroll on mobile —
            three buttons (refresh, Discover, New Device Key) plus the title
            block never fit one row below ~640px, and nothing here was
            allowed to wrap or shrink, so "New Device Key" got clipped at
            the viewport edge instead. Stacks under the title on narrow
            screens now, and button labels hide below sm (same
            icon-only-on-mobile convention already used elsewhere, e.g.
            RecordingDetail.jsx's DetectionCard buttons) as a second margin
            of safety, since even the button row alone was tight. */}
        <div className="flex items-center gap-2 flex-wrap">

          <button onClick={load} className="p-2 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-surface-700 transition-colors flex-shrink-0">
            <RefreshCw size={16}/>
          </button>
          <button
            onClick={handleDiscover}
            disabled={discovering}
            className="btn-secondary flex items-center gap-2 py-2 px-4 text-sm flex-shrink-0">
            {discovering ? <RefreshCw size={14} className="animate-spin"/> : <Radio size={14}/>}
            <span className="hidden sm:inline">{discovering ? 'Scanning…' : 'Discover'}</span>
          </button>
          <button onClick={() => setShowNewKey(true)} className="btn-primary flex items-center gap-2 py-2 px-4 text-sm flex-shrink-0">
            <Plus size={14}/> <span className="hidden sm:inline">New Device Key</span>
          </button>
        </div>
      </div>

      <BleDeviceSetup/>

      {/* No location warning */}
      {!serverHasLocation && (
        <div className="flex items-start gap-3 p-4 rounded-lg bg-yellow-900/20 border border-yellow-700/40">
          <AlertCircle size={16} className="text-yellow-400 flex-shrink-0 mt-0.5"/>
          <div>
            <p className="text-sm font-medium text-yellow-300">Server location not configured</p>
            <p className="text-xs text-yellow-500/80 mt-0.5">
              Set your location in <a href="/settings" className="underline hover:text-yellow-300">Settings</a> so devices can use location-based species filtering.
            </p>
          </div>
        </div>
      )}

      {/* Device list — excludes the virtual Haikubox device, which has
          its own dedicated status panel further down this page (see the
          "Got a Haikubox?" / HaikuboxStatusPanel-equivalent section).
          DeviceCard renders a full settings panel (BirdNET confidence/
          overlap sliders, inference backend, config-version sync) that
          has no meaning for a cloud-hosted virtual device — Chirp has no
          ability to configure Cornell's own BirdNET pipeline running on
          Haikubox's servers, so showing those controls just implies a
          capability that doesn't exist. The underlying Device row is
          untouched by this filter — it's still required for
          Recording.device_id, is_online(), and the dedicated panel's own
          status queries; this only changes what renders in this one list. */}
      <div className="space-y-4">
        {devices.filter(d => d.platform !== 'Haikubox' && d.birdnet_backend !== 'haikubox' && d.birdnet_backend !== 'bird_buddy').map(d => (
          <DeviceCard
            key={d.id}
            device={d}
            onUpdated={handleUpdated}
            onDeleted={handleDeleted}
            serverHasLocation={serverHasLocation}
            onOpenSsh={setSshDevice}
            onOpenLogs={setLogsDevice}
          />
        ))}
      </div>

      <ThirdPartyDeviceGroup
        label="Bird Buddy"
        icon={BirdBuddyIcon}
        devices={devices.filter(d => d.birdnet_backend === 'bird_buddy')}
        defaultOpen={false}
        onUpdated={handleUpdated}
      />
      {/* Haikubox integration box — hidden only when the feature is
          globally disabled AND was never configured (enabled===false,
          disabled===false meaning no serial was ever set either):
          inviting someone to set up a disabled feature is genuinely
          misleading. Every other real state still shows the box —
          including "enabled but not yet configured" (genuine first-time
          invite) and "previously configured, now disabled" (existing,
          intentional design letting someone re-enable without hunting
          for a separate toggle first). Waits for haikuboxStatus to
          actually load (!== null) before deciding, so the box doesn't
          flash hidden during the brief initial fetch. */}
      {!(haikuboxStatus && haikuboxStatus.enabled === false && !haikuboxStatus.disabled) && (
      <div className="card overflow-hidden">
        <button onClick={() => setHaikuboxOpen(o => !o)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-700 transition-colors text-left">
          <span className="flex items-center gap-2 text-sm font-medium text-gray-200">
            <Info size={14} className="text-chirp-500"/>
            {haikuboxStatus?.configured
              ? <>Haikubox <span className="text-gray-500 font-normal">· {haikuboxStatus.serial}</span></>
              : haikuboxStatus?.disabled
                ? 'Haikubox (disabled)'
                : 'Got a Haikubox?'}
          </span>
          <div className="flex items-center gap-2">
            {haikuboxStatus?.configured && (
              <span className="w-2 h-2 rounded-full" style={{
                background: haikuboxStatus.status === 'online' ? '#4ade80'
                  : haikuboxStatus.status === 'offline' ? '#f87171' : '#6b7280'
              }}/>
            )}
            {haikuboxOpen ? <ChevronUp size={14} className="text-gray-500"/> : <ChevronDown size={14} className="text-gray-500"/>}
          </div>
        </button>
        {haikuboxOpen && (
          <div className="px-4 py-4 space-y-4 bg-surface-900 text-sm text-gray-300">
            {haikuboxStatus?.configured ? (
              <>
                {/* Status row */}
                <div className="flex items-center justify-between gap-3">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full flex-shrink-0" style={{
                        background: haikuboxStatus.status === 'online' ? '#4ade80'
                          : haikuboxStatus.status === 'offline' ? '#f87171' : '#6b7280'
                      }}/>
                      <span className="font-medium text-gray-200">
                        {haikuboxStatus.status === 'online' ? 'Active'
                          : haikuboxStatus.status === 'offline' ? 'Offline'
                          : 'Not yet synced'}
                      </span>
                    </div>
                    {haikuboxStatus.last_seen && (
                      <p className="text-xs text-gray-500 pl-4">
                        Last synced {new Date(haikuboxStatus.last_seen + 'Z').toLocaleString()}
                      </p>
                    )}
                    {haikuboxStatus.total_recordings > 0 && (
                      <Link to="/haikubox"
                            className="text-xs pl-4 hover:underline inline-block"
                            style={{ color: 'var(--accent-400)' }}>
                        {haikuboxStatus.total_recordings.toLocaleString()} detection{haikuboxStatus.total_recordings !== 1 ? 's' : ''} imported — view them
                      </Link>
                    )}
                  </div>
                  <button onClick={handleHaikuboxSync} disabled={haikuboxSyncing}
                          className="btn-secondary text-xs px-3 py-1.5 flex-shrink-0 disabled:opacity-50">
                    {haikuboxSyncing ? 'Syncing…' : 'Sync Now'}
                  </button>
                </div>
                {haikuboxSyncMsg && (
                  <p className="text-xs text-gray-400">{haikuboxSyncMsg}</p>
                )}
                <p className="text-xs text-gray-500">
                  Chirp polls the Haikubox API every 15 minutes. Detections appear in Recordings and Bird Library
                  tagged to this device. Only the last 24 hours are available through the API — no audio is included.
                </p>
              </>
            ) : haikuboxStatus?.disabled ? (
              <div className="flex items-start gap-2.5 p-3 rounded-lg text-xs" style={{ background: 'rgba(251,191,36,.08)', border: '1px solid rgba(251,191,36,.25)', color: 'var(--pastel-amber-light)' }}>
                <Info size={14} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--pastel-amber)' }}/>
                <span>
                  Haikubox is currently disabled. Your serial number is saved — turning it back on in{' '}
                  <Link to="/settings" className="underline">Settings → Account &amp; Advanced</Link> resumes syncing
                  immediately without needing to re-enter it. All previously imported detections will reappear.
                </span>
              </div>
            ) : (
              <>
                <p>
                  Haikubox publishes a public REST API at{' '}
                  <a href="https://api.haikubox.com/docs" target="_blank" rel="noopener noreferrer"
                     className="text-chirp-400 hover:underline inline-flex items-center gap-1">
                    api.haikubox.com/docs <ExternalLink size={11}/>
                  </a>{' '}
                  — no separate API key needed, just your device serial number. Chirp polls it
                  every 15 minutes and imports detections as a virtual device so they show up
                  alongside your Pi recordings.
                </p>
                <p className="text-gray-500 text-xs">
                  Note: data is CC BY-NC-SA 4.0 (non-commercial). Only the last 24 hours are
                  available — there's no historical backfill.
                </p>
              </>
            )}

            {/* Admin serial input */}
            {isAdmin && (
              <div className="pt-3 border-t border-surface-700 space-y-2">
                <label className="text-xs font-semibold uppercase tracking-widest text-gray-500">
                  {haikuboxStatus?.configured ? 'Change Serial Number' : 'Haikubox Serial Number'}
                </label>
                <div className="flex items-center gap-2">
                  <input
                    className="input font-mono flex-1"
                    type="text"
                    placeholder={appSettings?.haikubox_serial || 'e.g. 1000000066e59043'}
                    value={haikuboxSerial}
                    onChange={e => setHaikuboxSerial(e.target.value)}
                  />
                  <button onClick={handleSaveHaikuboxSerial}
                          disabled={haikuboxSaving || !haikuboxSerial}
                          className="btn-secondary text-sm px-3 py-1.5 flex-shrink-0 flex items-center gap-1.5 disabled:opacity-50">
                    {haikuboxSaved ? <Check size={13} className="text-chirp-400"/> : null}
                    {haikuboxSaving ? 'Saving…' : haikuboxSaved ? 'Saved' : 'Save'}
                  </button>
                </div>
                <p className="text-xs text-gray-500">
                  Also editable from Settings → API Keys. Saving triggers an immediate sync.
                </p>
                <Link to="/haikubox"
                      className="flex items-center gap-1.5 text-xs pt-1"
                      style={{ color: 'var(--accent-400)' }}>
                  <Radio size={12}/> View Haikubox Detections →
                </Link>
              </div>
            )}
          </div>
        )}
      </div>
      )}

      {/* Discovery panel */}
      {showDiscovery && (
        <div className="card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <Radio size={14} className="text-chirp-500"/> Network Discovery
            </h2>
            <button onClick={() => setShowDiscovery(false)} className="p-1 text-gray-600 hover:text-gray-400">
              <X size={14}/>
            </button>
          </div>
          <p className="text-xs text-gray-500">
            Scanning local network for Raspberry Pi devices running chirp-device.
            Devices with mDNS/Zeroconf active appear first; others found via ARP table.
          </p>
          {discovering && (
            <div className="flex items-center gap-2 text-xs text-chirp-400">
              <RefreshCw size={12} className="animate-spin"/> Scanning…
            </div>
          )}
          {discoverError && (
            <div className="flex items-center gap-2 text-xs text-yellow-400 bg-yellow-900/20 border border-yellow-700/40 rounded-lg px-3 py-2">
              <AlertCircle size={12}/> {discoverError}
            </div>
          )}
          {discovered.length > 0 && (
            <div className="space-y-2">
              {discovered.filter(Boolean).map((d, i) => (
                <DiscoveredDeviceRow key={d.ip || i} result={d} onRefresh={load}/>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Setup instructions */}
      {devices.length === 0 && (
        <div className="card p-6 space-y-4">
          <h2 className="text-base font-semibold text-white flex items-center gap-2">
            <Radio size={16} className="text-chirp-500"/> Pairing a Raspberry Pi
          </h2>
          <ol className="space-y-3 text-sm text-gray-400">
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-chirp-700/50 text-chirp-300 text-xs flex items-center justify-center font-bold">1</span>
              <span>Click <strong className="text-gray-200">New Device Key</strong> above to generate an API key for your Pi.</span>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-chirp-700/50 text-chirp-300 text-xs flex items-center justify-center font-bold">2</span>
              <span>On your Pi, add the key to <code className="text-chirp-400">config.yaml</code> under <code className="text-chirp-400">server_sync</code>.</span>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-chirp-700/50 text-chirp-300 text-xs flex items-center justify-center font-bold">3</span>
              <span>Start (or restart) the chirp-device service on the Pi. It will pair automatically and appear here.</span>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-chirp-700/50 text-chirp-300 text-xs flex items-center justify-center font-bold">4</span>
              <span>Configure BirdNET settings, push the config, and the Pi applies it within 60 seconds.</span>
            </li>
          </ol>
        </div>
      )}


      {showNewKey && (
        <NewKeyModal
          onClose={() => setShowNewKey(false)}
          onCreate={() => {}}
        />
      )}

      {sshDevice && (
        <React.Suspense fallback={
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="text-sm text-gray-400">Loading terminal…</div>
          </div>
        }>
          <SSHTerminal
            device={sshDevice}
            onClose={() => setSshDevice(null)}
          />
        </React.Suspense>
      )}
      {logsDevice && (
        <DeviceLogViewer
          device={logsDevice}
          onClose={() => setLogsDevice(null)}
        />
      )}
    </div>
  )
}

export default function Devices(props) {
  return <ErrorBoundary label="Devices"><DevicesInner {...props}/></ErrorBoundary>
}
