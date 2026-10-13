import { useState, useEffect, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { AudioLines, Mic, Radio, ChevronRight, CheckCircle, X } from 'lucide-react'
import { BirdIcon } from './BirdBatIcons'
import ChirpLogo from './ChirpLogo'
import { isApp } from '../native'
import { hapticEvent } from '../lib/haptics'
import { SeenTodayModal } from './Dashboard'
import { api, mediaUrl } from '../lib/api'
import { useTz } from '../lib/time'

const SOURCE_KEY = 'chirp:liveDetect:source'
const DEVICE_KEY = 'chirp:liveDetect:deviceId'

// Same "is this the bird mic, not the bat/ultrasonic one" heuristic
// Settings.jsx's mic check already uses (isBird/isBat there) — kept in
// sync deliberately rather than sharing a literal import, since mic
// check works off live /levels rows (name + sample rate) while this
// works off Device.mic_names (name only, no live sample rate) — close
// enough in shape that a shared abstraction would need to paper over
// the difference more than it would save.
function pickBirdMicName(micNames) {
  if (!micNames || micNames.length === 0) return null
  const nonBat = micNames.filter(n => !n.toLowerCase().includes('audiomoth'))
  const respeaker = nonBat.find(n => {
    const nl = n.toLowerCase()
    return nl.includes('respeaker') || nl.includes('xvf')
  })
  return respeaker || nonBat[0] || null
}

// Real-time scrolling frequency waterfall, drawn from the phone's own
// mic input via an AnalyserNode — existing purely client-side, no
// server round-trip, independent of the ~3s analyze polling loop below.
// Standard technique: each frame, shift the whole canvas left by a
// couple pixels, then paint one new column of frequency-bin colors at
// the right edge — same "waterfall" shape spectrograms use throughout
// the rest of this app, just live instead of pre-rendered from a
// finished recording.
function LiveWaterfall({ analyser, active }) {
  const canvasRef = useRef(null)
  const rafRef = useRef(null)

  useEffect(() => {
    if (!active || !analyser || !canvasRef.current) return
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const cssWidth = canvas.clientWidth
    const cssHeight = canvas.clientHeight
    canvas.width = Math.round(cssWidth * dpr)
    canvas.height = Math.round(cssHeight * dpr)
    // Deliberately NOT using ctx.scale(dpr, dpr) here, unlike most of
    // this app's canvas code — getImageData/putImageData always read
    // and write the canvas's raw device-pixel buffer and ignore the
    // current transform entirely, while fillRect/drawImage DO respect
    // it. Mixing scaled fillRect calls with unscaled getImageData/
    // putImageData calls (as an earlier version of this function did)
    // silently breaks the "shift left" step — confirmed directly: a
    // fixed test stripe measured on a simulated 3x-DPR canvas showed
    // ZERO movement after 20 simulated scroll frames that should have
    // shifted it 40px, because the two calls were operating on
    // completely different coordinate scales. Working in raw device
    // pixels throughout, with no transform active, sidesteps the
    // mismatch entirely rather than trying to keep two different
    // coordinate systems in sync by hand.
    const width = canvas.width
    const height = canvas.height
    ctx.fillStyle = '#03080a'
    ctx.fillRect(0, 0, width, height)

    const bins = new Uint8Array(analyser.frequencyBinCount)
    const colStep = Math.max(1, Math.round(2 * dpr)) // device px scrolled per frame — ~2 CSS px worth, how "fast" the waterfall moves

    const draw = () => {
      analyser.getByteFrequencyData(bins)
      // Scroll existing content left — all in raw device-pixel coordinates now
      const img = ctx.getImageData(colStep, 0, width - colStep, height)
      ctx.putImageData(img, 0, 0)
      ctx.fillStyle = '#03080a'
      ctx.fillRect(width - colStep, 0, colStep, height)

      // Paint the new column at the right edge — only the lower ~60% of
      // BirdNET's own useful range (roughly 0-12kHz covers the vast
      // majority of bird vocalizations) mapped onto the column height,
      // matching how this app's own spectrograms already crop/emphasize
      // range for readability rather than showing the full raw FFT.
      const usableBins = Math.floor(bins.length * 0.55)
      for (let y = 0; y < height; y++) {
        const bin = usableBins - 1 - Math.floor((y / height) * usableBins)
        const v = bins[Math.max(0, Math.min(usableBins - 1, bin))]
        // Viridis-ish mapping (dark purple -> teal -> yellow), matching
        // this app's own spectrogram color scheme elsewhere, rather than
        // introducing an unrelated color language just for this widget.
        const t = v / 255
        const r = Math.round(68 + t * (253 - 68))
        const g = Math.round(1 + t * (231 - 1) * (t > 0.5 ? 1 : 0.6))
        const b = Math.round(84 + t * (37 - 84) * (t < 0.7 ? 1 : 0.3))
        ctx.fillStyle = `rgb(${Math.max(0,Math.min(255,r))},${Math.max(0,Math.min(255,g))},${Math.max(0,Math.min(255,b))})`
        ctx.fillRect(width - colStep, y, colStep, 1)
      }
      rafRef.current = requestAnimationFrame(draw)
    }
    rafRef.current = requestAnimationFrame(draw)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [analyser, active])

  return <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }}/>
}

// Groups this session's flat detection list by species — reported
// directly: 11 separate rows for the same repeatedly-heard Hairy
// Woodpecker was unreadable. sessionDetections is already newest-first
// (recordDetections prepends), so the FIRST occurrence encountered per
// species while grouping is already its most recent — no separate
// timestamp comparison needed to find it.
function groupDetectionsBySpecies(detections) {
  const groups = new Map()
  for (const d of detections) {
    let g = groups.get(d.common_name)
    if (!g) {
      g = {
        common_name: d.common_name,
        scientific_name: d.scientific_name,
        photo_url: d.photo_url,
        profile_id: d.profile_id,
        count: 0,
        bestConfidence: 0,
        mostRecentAt: d.at,
        mostRecentRecordingId: d.recording_id,
      }
      groups.set(d.common_name, g)
    }
    g.count += 1
    if (d.confidence > g.bestConfidence) g.bestConfidence = d.confidence
  }
  return Array.from(groups.values())
}

function SpeciesGroupRow({ group, fmtAgo }) {
  // A profile page gives the fuller picture (every recording of this
  // species, not just this session) — preferred over linking to one
  // arbitrary recording whenever a profile exists yet. Falls
  // back to the most recent recording for a species too new to have
  // been enriched into a full profile yet.
  const linkTo = group.profile_id ? `/library/${group.profile_id}` : (group.mostRecentRecordingId ? `/recordings/${group.mostRecentRecordingId}` : null)
  return (
    <Link to={linkTo || '#'}
          className="card-hover flex items-center gap-3 p-3 rounded-xl"
          style={{ textDecoration: 'none', pointerEvents: linkTo ? 'auto' : 'none' }}>
      <div className="w-9 h-9 rounded-lg overflow-hidden flex items-center justify-center flex-shrink-0"
           style={{ background: 'rgba(74,222,128,.12)' }}>
        {group.photo_url ? (
          <img src={mediaUrl(group.photo_url)} alt="" className="w-full h-full object-cover"
               onError={e => { e.target.style.display = 'none' }}/>
        ) : (
          <BirdIcon size={16} style={{ color: '#4ade80' }}/>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
          {group.common_name}
          {group.count > 1 && <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}> × {group.count}</span>}
        </p>
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          {Math.round(group.bestConfidence * 100)}% best · {fmtAgo(group.mostRecentAt)}
        </p>
      </div>
      <ChevronRight size={14} style={{ color: 'var(--text-tertiary)', flexShrink: 0 }}/>
    </Link>
  )
}

// Concatenates decoded clip buffers (device mode) into one continuous
// buffer, in order — used when saving a session as one recording.
// Verified directly with a round-trip encode+decode test: sample data
// at each segment boundary matches the source buffer exactly, no
// shift or corruption.
function concatAudioBuffers(audioCtx, buffers) {
  if (buffers.length === 0) return null
  const numChannels = buffers[0].numberOfChannels
  const sampleRate = buffers[0].sampleRate
  const totalLength = buffers.reduce((sum, b) => sum + b.length, 0)
  const result = audioCtx.createBuffer(numChannels, totalLength, sampleRate)
  let offset = 0
  for (const buffer of buffers) {
    for (let ch = 0; ch < numChannels; ch++) {
      // A clip could in principle arrive with fewer channels than the
      // first one — only copy channels that exist on THIS buffer
      // rather than assuming every clip matches the first exactly.
      if (ch < buffer.numberOfChannels) {
        result.getChannelData(ch).set(buffer.getChannelData(ch), offset)
      }
    }
    offset += buffer.length
  }
  return result
}

// Standard 16-bit PCM WAV encoding from a decoded AudioBuffer — there's
// no MediaRecorder equivalent for "I already have the samples in
// memory", so this writes the RIFF header and interleaved samples by
// hand. Verified directly with a round-trip test: encoded byte size
// matches the expected header+PCM size exactly, and re-decoding the
// result reproduces the original duration and sample values (within
// 16-bit quantization error).
function audioBufferToWav(audioBuffer) {
  const numChannels = audioBuffer.numberOfChannels
  const sampleRate = audioBuffer.sampleRate
  const numFrames = audioBuffer.length
  const bytesPerSample = 2
  const blockAlign = numChannels * bytesPerSample
  const dataSize = numFrames * blockAlign
  const buffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(buffer)
  const writeString = (offset, str) => { for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i)) }
  writeString(0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, numChannels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * blockAlign, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, dataSize, true)
  const channelData = []
  for (let ch = 0; ch < numChannels; ch++) channelData.push(audioBuffer.getChannelData(ch))
  let offset = 44
  for (let i = 0; i < numFrames; i++) {
    for (let ch = 0; ch < numChannels; ch++) {
      const sample = Math.max(-1, Math.min(1, channelData[ch][i]))
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
      offset += 2
    }
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

// Offered only when the session heard something (see
// toggleListening's own hasDetections check) — reuses
// groupDetectionsBySpecies() for the same species-with-count summary
// Live Detect's own session list already shows, so what's asked about
// here matches what the person was just looking at.
function SaveSessionModal({ sessionDetections, onSave, onDiscard, saving, error, savedRecordingId }) {
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape' && !saving) onDiscard() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [saving, onDiscard])

  const groups = groupDetectionsBySpecies(sessionDetections)

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,.7)' }}
         onClick={() => { if (!saving) onDiscard() }}>
      <div className="card w-full p-5" style={{ maxWidth: 400 }} onClick={e => e.stopPropagation()}>
        {savedRecordingId ? (
          <>
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle size={18} style={{ color: '#4ade80' }}/>
              <h2 className="font-display text-base font-semibold" style={{ color: 'var(--text-primary)' }}>Session saved</h2>
            </div>
            <p className="text-sm mb-4" style={{ color: 'var(--text-tertiary)' }}>
              The whole session is now one recording.
            </p>
            <div className="flex gap-2">
              <button onClick={onDiscard} className="flex-1 py-2 rounded-lg text-sm" style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
                Close
              </button>
              <Link to={`/recordings/${savedRecordingId}`} onClick={onDiscard}
                    className="flex-1 py-2 rounded-lg text-sm font-semibold text-center"
                    style={{ background: 'var(--accent-500)', color: '#000', textDecoration: 'none' }}>
                View recording
              </Link>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-display text-base font-semibold" style={{ color: 'var(--text-primary)' }}>Save this session?</h2>
              <button onClick={onDiscard} disabled={saving} className="p-1.5 rounded-lg transition-colors hover:opacity-70"
                      style={{ background: 'var(--bg-raised)' }}>
                <X size={16} style={{ color: 'var(--text-secondary)' }}/>
              </button>
            </div>
            <p className="text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
              {groups.length} {groups.length === 1 ? 'species' : 'species'} heard this session. Save the whole
              session as one recording, or discard it — the individual detections stay in your history either way.
            </p>
            <div className="flex flex-wrap gap-1.5 mb-4">
              {groups.map(g => (
                <span key={g.common_name} className="text-xs px-2 py-1 rounded-md"
                      style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
                  {g.common_name}{g.count > 1 ? ` \u00d7${g.count}` : ''}
                </span>
              ))}
            </div>
            {error && <p className="text-xs mb-3" style={{ color: '#f87171' }}>{error}</p>}
            <div className="flex gap-2">
              <button onClick={onDiscard} disabled={saving} className="flex-1 py-2 rounded-lg text-sm"
                      style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
                Discard
              </button>
              <button onClick={onSave} disabled={saving} className="flex-1 py-2 rounded-lg text-sm font-semibold"
                      style={{ background: 'var(--accent-500)', color: '#000', opacity: saving ? 0.7 : 1 }}>
                {saving ? 'Saving\u2026' : 'Save'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body
  )
}

export default function LiveDetect() {
  const { fmtAgo } = useTz()

  // "Device is default" would read backwards to anyone who's never used
  // Merlin — the source this defaults to is deliberately the PHONE
  // you're holding right now (matching how Merlin's own Sound ID always
  // works: walk around, use the phone's own mic), not a deployed
  // ChirpPi. "device" here means "a chirp-device", which is the OTHER
  // option, not the default.
  const [source, setSource] = useState(() => {
    try { return localStorage.getItem(SOURCE_KEY) || 'phone' } catch { return 'phone' }
  })
  const [devices, setDevices] = useState([])
  const [selectedDeviceId, setSelectedDeviceId] = useState(() => {
    try { return localStorage.getItem(DEVICE_KEY) || '' } catch { return '' }
  })

  const [listening, setListening] = useState(false)
  const [statusText, setStatusText] = useState('Not listening')
  // Reported directly: "Heard X!" was flashing too quickly to read. Root
  // cause — each analyze cycle's own next-iteration status update
  // ("Listening…"/"Analyzing…") was overwriting it after as little as
  // 250ms (the gap between cycles), well before a person could read a
  // species name. This holds a "Heard X!" message on screen for a fixed
  // minimum duration, silently skipping any ROUTINE status update that
  // would otherwise land inside that window — detection itself isn't
  // slowed at all, only what's displayed about it.
  const HEARD_DISPLAY_MS = 2500
  const heardUntilRef = useRef(0)
  // Reported directly, with a screenshot: the status card's icon stayed
  // a generic placeholder even while "Heard X!" named a specific,
  // already-known species — the same species' real photo was sitting
  // one section down in Heard Today the whole time, from the exact
  // same analyze response (detections[].photo_url, already resolved
  // server-side whenever a profile exists). Held on the same
  // isHeard/heardUntilRef timer as the text itself, so the photo and
  // the name never fall out of sync with each other — one clears back
  // to the generic icon exactly when the other reverts to "Listening…".
  const [heardPhotoUrl, setHeardPhotoUrl] = useState(null)
  const setStatusTextHeld = useCallback((text, isHeard, photoUrl) => {
    const now = Date.now()
    if (isHeard) {
      heardUntilRef.current = now + HEARD_DISPLAY_MS
      setStatusText(text)
      setHeardPhotoUrl(photoUrl || null)
    } else if (now >= heardUntilRef.current) {
      setStatusText(text)
      setHeardPhotoUrl(null)
    }
  }, [])
  const [error, setError] = useState(null)
  const [sessionDetections, setSessionDetections] = useState([])
  const [heardToday, setHeardToday] = useState([])
  const [micPermissionDenied, setMicPermissionDenied] = useState(false)
  const [showSeenToday, setShowSeenToday] = useState(false)
  // Gain/filter for live monitoring only — never applied to what's
  // uploaded for BirdNET analysis (see connectProcessingChain() below
  // for exactly where this branches off), so boosting or filtering to
  // make something audible/watchable can't accidentally change what
  // gets detected.
  const [gainLevel, setGainLevel] = useState(1.0)
  const [filterFreq, setFilterFreq] = useState(0) // highpass cutoff in Hz; 0 = off

  // "Save this session as one recording?" flow, offered on Stop only
  // when the session heard something — see toggleListening's own stop
  // branch for where sessionAudioRef gets filled in before this modal
  // ever shows.
  const [showSaveConfirm, setShowSaveConfirm] = useState(false)
  const [savingSession, setSavingSession] = useState(false)
  const [saveSessionError, setSaveSessionError] = useState(null)
  const [savedSessionRecordingId, setSavedSessionRecordingId] = useState(null)
  const sessionAudioRef = useRef(null)   // the finalized Blob, set once at Stop, read by the modal's own Save button
  const sessionDeviceIdRef = useRef(null) // which device (if any) this session used, for the new recording's own device_id

  const streamRef = useRef(null)
  const analyserRef = useRef(null)
  const audioCtxRef = useRef(null)
  const bufferSourceRef = useRef(null) // device-mode visualizer's currently-playing clip, so stopEverything() can stop it
  // Session-audio accumulation, for the "save the whole session as one
  // recording" option on Stop — separate from everything above, which
  // exists for live analysis/visualization, not for keeping a copy.
  const sessionStartRef = useRef(null)          // Date the session began, needed both to timestamp the saved recording and to compute each original clip's offset into it server-side
  const sessionRecorderRef = useRef(null)       // phone mode: one continuous MediaRecorder for the whole session, separate from the short per-cycle recorder used for analysis
  const sessionChunksRef = useRef([])           // phone mode: that recorder's accumulated chunks
  const sessionBuffersRef = useRef([])          // device mode: every clip's decoded AudioBuffer, in order, for concatenation at Stop
  const gainNodeRef = useRef(null)
  const filterNodeRef = useRef(null)
  const recorderRef = useRef(null)
  const activeRecordersRef = useRef([]) // phone mode's two overlapping capture lanes — both tracked here so Stop can halt whichever ones are mid-clip, not just one
  const pollTimerRef = useRef(null)
  const laneTimersRef = useRef([]) // the two lanes' own setTimeout handles, separate from pollTimerRef (device-polling mode's own single timer)
  const stoppedRef = useRef(true) // ref mirror of `listening`, readable inside async closures without a stale-state bug
  const [sensitivity, setSensitivity] = useState(() => {
    const saved = parseFloat(localStorage.getItem('chirp_live_detect_sensitivity'))
    return Number.isFinite(saved) ? saved : 0.05
  })
  const sensitivityRef = useRef(sensitivity) // readable inside the capture loop's closures without a stale-state bug, same reasoning as stoppedRef above
  useEffect(() => {
    sensitivityRef.current = sensitivity
    localStorage.setItem('chirp_live_detect_sensitivity', String(sensitivity))
  }, [sensitivity])

  // Phone location for Live Detect (phone microphone only): saved on the
  // recordings it makes, and used by BirdNET to judge which birds are
  // likely where you are instead of at the home site. On by default; the
  // iPhone asks for permission the first time.
  const [useLocation, setUseLocation] = useState(() => {
    try { return localStorage.getItem('chirp_live_detect_location') !== '0' } catch { return true }
  })
  const [locState, setLocState] = useState(null)   // null | 'locating' | {acc} | 'denied' | 'unavailable'
  const locRef = useRef(null)                        // { latitude, longitude } or null
  const locWatchRef = useRef(null)
  useEffect(() => { try { localStorage.setItem('chirp_live_detect_location', useLocation ? '1' : '0') } catch {} }, [useLocation])
  const startLocation = useCallback(() => {
    if (!useLocation || !navigator.geolocation) { locRef.current = null; if (useLocation) setLocState('unavailable'); return }
    setLocState('locating')
    const ok = pos => {
      locRef.current = { latitude: +pos.coords.latitude.toFixed(5), longitude: +pos.coords.longitude.toFixed(5) }
      setLocState({ acc: Math.round(pos.coords.accuracy || 0) })
    }
    const fail = err => { if (!locRef.current) setLocState(err?.code === 1 ? 'denied' : 'unavailable') }
    navigator.geolocation.getCurrentPosition(ok, fail, { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 })
    try { locWatchRef.current = navigator.geolocation.watchPosition(ok, fail, { enableHighAccuracy: true, maximumAge: 30000 }) } catch {}
  }, [useLocation])
  const stopLocation = useCallback(() => {
    if (locWatchRef.current != null && navigator.geolocation) navigator.geolocation.clearWatch(locWatchRef.current)
    locWatchRef.current = null
  }, [])
  useEffect(() => stopLocation, [stopLocation])
  const [windowSeconds, setWindowSeconds] = useState(() => {
    const saved = parseFloat(localStorage.getItem('chirp_live_detect_window_seconds'))
    return Number.isFinite(saved) ? saved : 5
  })
  const windowSecondsRef = useRef(windowSeconds) // read fresh at the start of each capture cycle, so adjusting mid-session takes effect on the next clip without needing to stop/restart
  useEffect(() => {
    windowSecondsRef.current = windowSeconds
    localStorage.setItem('chirp_live_detect_window_seconds', String(windowSeconds))
  }, [windowSeconds])
  const [analyserVersion, setAnalyserVersion] = useState(0) // bumps to re-render LiveWaterfall once analyser exists

  useEffect(() => {
    api.devices.list().then(list => {
      // Live Detect needs a physical device with a bird mic to stream from —
      // Haikubox and Bird Buddy show up in this same devices list (for
      // the Devices admin page, recording attribution, etc.) but are
      // virtual rows with no status_server/listen endpoint behind them
      // at all. api_key_id is null ONLY for these virtual rows (see
      // DeviceOut's own comment on the field) — the same marker
      // haikubox_sync.py/bird_buddy_sync.py already use when creating
      // them, reused here rather than checking `platform` string
      // values, which would need updating every time a new third-party
      // integration gets its own virtual device type.
      const pairedDevices = (list || []).filter(d => d.api_key_id != null)
      setDevices(pairedDevices)
      if (pairedDevices.length > 0 && !pairedDevices.some(d => d.id === selectedDeviceId)) {
        setSelectedDeviceId(pairedDevices[0].id)
      }
    }).catch(() => {})
    api.recordings.dashboardSummary().then(s => {
      setHeardToday(s?.daily?.species_today || [])
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    try { localStorage.setItem(SOURCE_KEY, source) } catch {}
  }, [source])
  useEffect(() => {
    try { if (selectedDeviceId) localStorage.setItem(DEVICE_KEY, selectedDeviceId) } catch {}
  }, [selectedDeviceId])

  const selectedDevice = devices.find(d => d.id === selectedDeviceId) || null
  const birdMicName = selectedDevice ? pickBirdMicName(selectedDevice.mic_names) : null

  // ── Recording a positive detection ──────────────────────────────────────
  // Species already felt this session: the first time each is heard gets a
  // success buzz, repeats a light tap.
  const hapticSpeciesRef = useRef(new Set())
  const recordDetections = useCallback((resp) => {
    if (!resp.detected) return
    const fresh = resp.detections.some(d => !hapticSpeciesRef.current.has(d.common_name))
    resp.detections.forEach(d => hapticSpeciesRef.current.add(d.common_name))
    hapticEvent(fresh ? 'success' : 'light')
    const now = new Date().toISOString()
    setSessionDetections(prev => [
      ...resp.detections.map(d => ({ ...d, recording_id: resp.recording_id, at: now })),
      ...prev,
    ])
    setHeardToday(prev => {
      const names = new Set(prev.map(s => s.common_name))
      const additions = resp.detections.filter(d => !names.has(d.common_name))
        .map(d => ({ common_name: d.common_name }))
      return additions.length ? [...additions, ...prev] : prev
    })
  }, [])

  // ── Phone-mic capture loop ──────────────────────────────────────────────
  // Shared by both phone and device audio graphs — inserts a highpass
  // filter (cut low rumble) then a gain node (volume boost) between a
  // source and the analyser, for live monitoring only. Deliberately
  // NEVER touches what gets sent to /live-detect/analyze: phone mode's
  // MediaRecorder taps the RAW stream directly (see startPhoneCapture,
  // untouched by this chain), and device mode's analysis clip is a
  // completely separate server-side fetch (startDevicePolling) from the
  // client-side clip this chain processes for visualization/listening —
  // so cranking the gain to hear something better can never change what
  // BirdNET sees.
  const connectProcessingChain = useCallback((audioCtx, sourceNode, analyser, toDestination) => {
    let filter = filterNodeRef.current
    if (!filter) {
      filter = audioCtx.createBiquadFilter()
      filter.type = 'highpass'
      // Only set the initial value here, at creation — NOT on every
      // call. Reported directly: the slider would visibly move the
      // filter for a moment, then the cutoff would silently revert.
      // Root cause: this function is re-invoked on every new audio
      // buffer in device mode (see playBuffer's own repeated call to
      // this), and this callback's closure over filterFreq is frozen
      // at first render (empty deps below, deliberately, so the graph
      // itself doesn't get torn down and rebuilt every render) — so an
      // unconditional `filter.frequency.value = filterFreq` here was
      // stamping the STALE original value back over whatever the
      // dedicated useEffect further down had just live-updated it to,
      // as often as once per captured clip. That effect is the only
      // thing that should ever touch an already-existing node's value.
      filter.frequency.value = filterFreq
      filterNodeRef.current = filter
    }
    let gain = gainNodeRef.current
    if (!gain) {
      gain = audioCtx.createGain()
      gain.gain.value = gainLevel
      gainNodeRef.current = gain
    }
    sourceNode.connect(filter)
    filter.connect(gain)
    gain.connect(analyser)
    if (toDestination) gain.connect(audioCtx.destination)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Live-updates the already-connected nodes whenever a slider moves
  // during an active session — setting an AudioParam's .value directly
  // takes effect immediately, no need to rebuild the graph or restart
  // listening.
  useEffect(() => {
    if (gainNodeRef.current) gainNodeRef.current.gain.value = gainLevel
  }, [gainLevel])
  useEffect(() => {
    if (filterNodeRef.current) filterNodeRef.current.frequency.value = filterFreq
  }, [filterFreq])

  const startPhoneCapture = useCallback(async () => {
    let stream
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setMicPermissionDenied(false)
      setError("Live Detect needs an https:// server address. Browsers and the iPhone app block the microphone on plain http:// addresses like this one; everything else works.")
      return false
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      setMicPermissionDenied(true)
      setError(isApp()
        ? 'Microphone access is off for Chirp. Turn it on in Settings → Chirp → Microphone, then press Start again.'
        : 'Microphone access was denied. Allow microphone access for this site to use Live Detect.')
      return false
    }
    streamRef.current = stream
    setMicPermissionDenied(false)

    // Session-wide recording — separate from the short per-cycle
    // recorder below used for analysis. One continuous MediaRecorder
    // from Start to Stop, tapping the same stream (a MediaStream can
    // have multiple independent consumers reading it at once), so the
    // saved session — if the person chooses to save it — has no gaps
    // between analysis cycles the way stitching the small per-cycle
    // clips together would.
    sessionStartRef.current = new Date()
    sessionChunksRef.current = []
    try {
      let sessionRecorder
      try {
        sessionRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })
      } catch {
        sessionRecorder = new MediaRecorder(stream)
      }
      sessionRecorder.ondataavailable = (e) => { if (e.data && e.data.size > 0) sessionChunksRef.current.push(e.data) }
      sessionRecorder.start(1000) // periodic chunks rather than one giant buffer only flushed at Stop
      sessionRecorderRef.current = sessionRecorder
    } catch {
      // Session recording is a nice-to-have on top of live detection,
      // not required for it — if this browser can't run two
      // MediaRecorders on one stream for some reason, detection itself
      // should still work; saving the session just won't be offered.
      sessionRecorderRef.current = null
    }

    // AnalyserNode for the live waterfall — a separate tap on the same
    // stream, entirely independent of MediaRecorder below; drawing this
    // never touches what gets uploaded for analysis.
    const AudioCtx = window.AudioContext || window.webkitAudioContext
    const audioCtx = new AudioCtx()
    // Verified this is created "running" (not suspended) when called
    // from a click — which toggleListening always is, via the
    // Start button — but resume() defensively anyway: cheap, a no-op
    // if already running, and removes any residual risk from a browser
    // that behaves differently here.
    audioCtx.resume().catch(() => {})
    const source_node = audioCtx.createMediaStreamSource(stream)
    const analyser = audioCtx.createAnalyser()
    analyser.fftSize = 1024
    // Never routed to destination — this is the phone's OWN mic, so
    // playing it back through the phone's OWN speakers would just be
    // feedback, not monitoring.
    connectProcessingChain(audioCtx, source_node, analyser, false)
    audioCtxRef.current = audioCtx
    analyserRef.current = analyser
    setAnalyserVersion(v => v + 1)

    const captureOneClip = () => new Promise((resolve) => {
      const chunks = []
      let recorder
      try {
        recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })
      } catch {
        recorder = new MediaRecorder(stream) // let the browser pick a supported format if opus/webm isn't available
      }
      activeRecordersRef.current.push(recorder)
      recorder.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data) }
      recorder.onstop = () => {
        activeRecordersRef.current = activeRecordersRef.current.filter(r => r !== recorder)
        resolve(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }))
      }
      recorder.start()
      // Reads windowSecondsRef fresh on every call (not captured once at
      // startPhoneCapture time) so dragging the slider mid-session takes
      // effect on each lane's very next clip, no restart needed.
      setTimeout(() => { if (recorder.state !== 'inactive') recorder.stop() }, windowSecondsRef.current * 1000)
    })

    // Two staggered, overlapping lanes instead of one — requested
    // directly, on top of the earlier no-gap fix. Both lanes run this
    // exact same loop, just offset from each other by half the window
    // length: at any given moment, one lane is roughly midway through
    // its own clip while the other is near either its start or end.
    // Consequence: a call landing exactly on one lane's clip boundary
    // (the one remaining way a call could still get truncated, even
    // with zero gap between a single lane's own consecutive clips)
    // lands comfortably in the MIDDLE of the other lane's clip instead,
    // where it can't be split at all. Both lanes report detections
    // through the same recordDetections callback — safe to call from
    // two places concurrently, since it only ever does functional state
    // updates (see recordDetections' own definition).
    const startLane = (laneIndex, initialDelayMs) => {
      const loop = () => {
        if (stoppedRef.current) return
        setStatusTextHeld('Listening\u2026', false)
        captureOneClip().then(blob => {
          if (stoppedRef.current) return
          laneTimersRef.current[laneIndex] = setTimeout(loop, 50) // minimal gap — just long enough for MediaRecorder to finish tearing down before this lane's next clip starts
          api.liveDetect.analyze('phone', { blob, minConfidence: sensitivityRef.current, ...(locRef.current || {}) })
            .then(resp => {
              if (stoppedRef.current) return
              recordDetections(resp)
              if (resp.detected) setStatusTextHeld(`Heard ${resp.detections[0].common_name}!`, true, resp.detections[0].photo_url)
            })
            .catch(e => {
              if (!stoppedRef.current) setError(e.message || 'Analysis failed')
            })
        }).catch(e => {
          if (!stoppedRef.current) setError(e.message || 'Capture failed')
        })
      }
      laneTimersRef.current[laneIndex] = setTimeout(loop, initialDelayMs)
    }
    activeRecordersRef.current = []
    laneTimersRef.current = [null, null]
    startLane(0, 0)
    startLane(1, (windowSecondsRef.current * 1000) / 2) // offset by half the window — the actual overlap
    return true
  }, [recordDetections, connectProcessingChain])

  // ── ChirpPi polling loop (no local mic access needed) ───────────────────
  // Live waterfall AND audible playback for device mode — reuses the SAME
  // LiveWaterfall component the phone mic already uses, but there's no
  // continuous local stream to tap for device audio (it only ever arrives
  // as discrete clips via the same /listen endpoint the mic-check Listen
  // button already uses). So instead: fetch a clip, decode it, play it
  // back through the shared gain/filter chain (audible now — requested
  // directly, unlike the original muted-for-visualization-only version of
  // this) with the analyser tapped in parallel, and fetch the next one —
  // double-buffered, the same idiom already used for the audible Listen
  // feature in Settings.jsx: the NEXT clip's fetch+decode starts the
  // moment the CURRENT one starts playing, not after it ends, so it's
  // normally ready by the time playback needs it. Reported directly:
  // without this, audio audibly skipped/paused every few seconds —
  // exactly the symptom of fetching each clip only after the previous
  // one finished, leaving a network-round-trip-sized gap between every
  // single clip.
  // Independent of startDevicePolling()'s own analyze loop below — the
  // two fetch their own clips from the device on their own cadence
  // rather than sharing one, since they serve different
  // purposes (detection vs. what you see/hear) and /listen is already a
  // lightweight read from a rolling in-memory buffer, not something
  // expensive to call twice in parallel.
  const startDeviceVisualizer = useCallback((deviceId, micName) => {
    sessionStartRef.current = new Date()
    sessionBuffersRef.current = []
    const AudioCtx = window.AudioContext || window.webkitAudioContext
    if (!audioCtxRef.current) {
      const ctx = new AudioCtx()
      ctx.resume().catch(() => {})
      audioCtxRef.current = ctx
    }
    const audioCtx = audioCtxRef.current
    if (!analyserRef.current) {
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 1024
      analyserRef.current = analyser
      setAnalyserVersion(v => v + 1)
    }
    const analyser = analyserRef.current

    const fetchAndDecode = () =>
      api.diagnostics.listen(deviceId, micName)
        .then(blob => blob.arrayBuffer())
        .then(arrayBuffer => audioCtx.decodeAudioData(arrayBuffer))

    const playBuffer = async (bufferPromise) => {
      if (stoppedRef.current) return
      let audioBuffer
      try {
        audioBuffer = await bufferPromise
      } catch {
        audioBuffer = null
      }
      if (stoppedRef.current) return
      if (!audioBuffer) {
        // A transient fetch/decode failure here shouldn't kill the whole
        // visual over one bad clip — the detection loop already surfaces
        // connectivity errors to the person; this one just quietly
        // retries after a beat.
        setTimeout(() => playBuffer(fetchAndDecode().catch(() => null)), 1000)
        return
      }
      sessionBuffersRef.current.push(audioBuffer) // accumulated for a possible "save this session" at Stop, independent of playback
      const source = audioCtx.createBufferSource()
      source.buffer = audioBuffer
      connectProcessingChain(audioCtx, source, analyser, true)
      bufferSourceRef.current = source
      // Start fetching the NEXT clip now — while THIS one plays — rather
      // than waiting for onended, which is the entire fix.
      const nextPromise = fetchAndDecode().catch(() => null)
      source.onended = () => { if (!stoppedRef.current) playBuffer(nextPromise) }
      source.start()
    }

    playBuffer(fetchAndDecode().catch(() => null))
  }, [connectProcessingChain])

  const startDevicePolling = useCallback(() => {
    if (!selectedDevice) {
      setError('Select a ChirpPi device first.')
      return false
    }
    if (!birdMicName) {
      setError(`${selectedDevice.name} has no recognized bird mic to listen through.`)
      return false
    }
    startDeviceVisualizer(selectedDevice.id, birdMicName)
    const loop = async () => {
      if (stoppedRef.current) return
      setStatusTextHeld(`Listening through ${selectedDevice.name}\u2026`, false)
      try {
        const resp = await api.liveDetect.analyze('device', { deviceId: selectedDevice.id, micName: birdMicName, minConfidence: sensitivityRef.current })
        if (stoppedRef.current) return
        recordDetections(resp)
        if (resp.detected) setStatusTextHeld(`Heard ${resp.detections[0].common_name}!`, true, resp.detections[0].photo_url)
        else setStatusTextHeld(`Listening through ${selectedDevice.name}\u2026`, false)
      } catch (e) {
        if (!stoppedRef.current) setError(e.message || 'Analysis failed')
      }
      if (!stoppedRef.current) pollTimerRef.current = setTimeout(loop, 500)
    }
    loop()
    return true
  }, [selectedDevice, birdMicName, recordDetections, startDeviceVisualizer])

  const stopEverything = useCallback(() => {
    stoppedRef.current = true
    setListening(false)
    setStatusText('Not listening')
    if (pollTimerRef.current) { clearTimeout(pollTimerRef.current); pollTimerRef.current = null }
    laneTimersRef.current.forEach(t => { if (t) clearTimeout(t) })
    laneTimersRef.current = []
    activeRecordersRef.current.forEach(r => {
      if (r.state !== 'inactive') { try { r.stop() } catch {} }
    })
    activeRecordersRef.current = []
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      try { recorderRef.current.stop() } catch {}
    }
    recorderRef.current = null
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    if (bufferSourceRef.current) {
      try { bufferSourceRef.current.onended = null; bufferSourceRef.current.stop() } catch {}
      bufferSourceRef.current = null
    }
    if (audioCtxRef.current) {
      try { audioCtxRef.current.close() } catch {}
      audioCtxRef.current = null
    }
    // Only reached directly here when finalizeSessionAudio() wasn't
    // called at all (no detections this session, so nothing to offer
    // saving) — when it WAS called, it already stopped this recorder
    // itself to produce the final Blob. Stopping streamRef's tracks
    // above would eventually stop this recorder too as a side effect
    // of its input track ending, but stopping it explicitly here is
    // clearer than relying on that, and clearing the chunk/buffer
    // arrays frees the accumulated audio promptly rather than leaving
    // it sitting in memory until the next session's start overwrites it.
    if (sessionRecorderRef.current && sessionRecorderRef.current.state !== 'inactive') {
      try { sessionRecorderRef.current.stop() } catch {}
    }
    sessionRecorderRef.current = null
    sessionChunksRef.current = []
    sessionBuffersRef.current = []
    // closing the AudioContext invalidates every node created from it —
    // these refs need clearing too, or the next session's chain-builder
    // would see a stale ref and try to reuse an already-closed node.
    gainNodeRef.current = null
    filterNodeRef.current = null
    analyserRef.current = null
  }, [])

  // Finalizes whatever session audio was accumulated into one Blob, or
  // null if there's nothing to save (the session recorder failed to
  // start, or a device-mode session somehow ended with zero clips).
  // Must run BEFORE stopEverything() — phone mode needs the session
  // recorder's onstop to fire while the stream/recorder still exist,
  // and device mode needs audioCtxRef.current still open to build the
  // concatenated buffer.
  const finalizeSessionAudio = useCallback(async () => {
    if (source === 'phone') {
      const recorder = sessionRecorderRef.current
      if (!recorder || recorder.state === 'inactive') return null
      return new Promise((resolve) => {
        recorder.onstop = () => {
          const blob = sessionChunksRef.current.length
            ? new Blob(sessionChunksRef.current, { type: recorder.mimeType || 'audio/webm' })
            : null
          resolve(blob)
        }
        try { recorder.stop() } catch { resolve(null) }
      })
    }
    const audioCtx = audioCtxRef.current
    const buffers = sessionBuffersRef.current
    if (!audioCtx || buffers.length === 0) return null
    const combined = concatAudioBuffers(audioCtx, buffers)
    return combined ? audioBufferToWav(combined) : null
  }, [source])

  const toggleListening = useCallback(async () => {
    if (listening) {
      // Captured before stopEverything() tears anything down — see
      // finalizeSessionAudio()'s own comment for why the ordering here
      // matters (it needs live audio resources that stopEverything()
      // is about to close).
      const hasDetections = sessionDetections.length > 0
      const audioBlob = hasDetections ? await finalizeSessionAudio() : null
      sessionDeviceIdRef.current = source === 'device' ? (selectedDevice?.id ?? null) : null
      stopLocation()
      stopEverything()
      if (hasDetections && audioBlob) {
        sessionAudioRef.current = audioBlob
        setSaveSessionError(null)
        setSavedSessionRecordingId(null)
        setShowSaveConfirm(true)
      }
      return
    }
    setError(null)
    stoppedRef.current = false
    const ok = source === 'phone' ? await startPhoneCapture() : startDevicePolling()
    if (ok) {
      setListening(true)
      if (source === 'phone') startLocation()
    } else {
      stoppedRef.current = true
    }
  }, [listening, source, startPhoneCapture, startDevicePolling, stopEverything, sessionDetections, finalizeSessionAudio, selectedDevice, startLocation, stopLocation])

  const handleSaveSession = async () => {
    if (!sessionAudioRef.current || !sessionStartRef.current) return
    setSavingSession(true)
    setSaveSessionError(null)
    try {
      // sessionDetections itself accumulates across the whole page visit
      // (Start/Stop/Start again all add to the same list, the same way
      // Heard Today does), so it's filtered down to just this one
      // session by timestamp — anything at or after this session's own
      // start — rather than assumed to already be scoped to it.
      const sessionStart = sessionStartRef.current
      const thisSessionDetections = sessionDetections.filter(d => new Date(d.at) >= sessionStart)
      const recordingIds = [...new Set(thisSessionDetections.map(d => d.recording_id).filter(Boolean))]
      if (recordingIds.length === 0) {
        setSaveSessionError('No recordings from this session to save.')
        return
      }
      const resp = await api.liveDetect.saveSession(
        sessionAudioRef.current,
        recordingIds,
        sessionStart.toISOString(),
        sessionDeviceIdRef.current,
        sessionDeviceIdRef.current ? {} : (locRef.current || {}),
      )
      setSavedSessionRecordingId(resp.recording_id)
    } catch (e) {
      setSaveSessionError(e.message || 'Could not save the session')
    } finally {
      setSavingSession(false)
    }
  }

  const handleDiscardSession = () => {
    setShowSaveConfirm(false)
    setSavingSession(false)
    setSaveSessionError(null)
    setSavedSessionRecordingId(null)
    sessionAudioRef.current = null
  }

  // Stop cleanly on unmount — leaving getUserMedia's mic indicator lit
  // and a polling loop running after navigating away is exactly the
  // kind of silent leak that's easy to miss in review.
  useEffect(() => () => stopEverything(), [stopEverything])

  // Switching source or device mid-session stops the current session
  // rather than trying to hot-swap it — avoids a whole class of "which
  // stream is this analyser even attached to anymore" bugs for a
  // trade-off (press Start again) that costs the user one tap.
  const changeSource = (s) => { if (listening) stopEverything(); setSource(s) }
  const changeDevice = (id) => { if (listening) stopEverything(); setSelectedDeviceId(id) }

  return (
    <div className="page-root">
      <div className="flex items-center gap-2 mb-1">
        <ChirpLogo size={30} animate={listening ? 'meter' : false}/>
        <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Live Detect</h1>
        <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full"
              style={{ background: 'rgba(251,146,60,.18)', color: '#fb923c', border: '1px solid rgba(251,146,60,.35)' }}>
          Beta
        </span>
      </div>
      <p className="text-sm mb-5" style={{ color: 'var(--text-tertiary)' }}>
        Listen in real time and save what's calling — separate from your device's own always-on recording.
      </p>

      {/* Source selector */}
      <div className="flex items-center gap-2 mb-4">
        <div className="flex items-center rounded-xl overflow-hidden flex-1" style={{ border: '1px solid var(--border-subtle)' }}>
          <button onClick={() => changeSource('phone')}
                  className="seg-btn flex-1 flex items-center justify-center gap-1.5 py-2 text-sm font-medium"
                  style={source === 'phone' ? { background: 'var(--nav-active-bg)', color: 'var(--accent-400)' } : { color: 'var(--text-tertiary)' }}>
            <Mic size={14}/> This device
          </button>
          <button onClick={() => changeSource('device')}
                  className="seg-btn flex-1 flex items-center justify-center gap-1.5 py-2 text-sm font-medium"
                  style={source === 'device' ? { background: 'var(--nav-active-bg)', color: 'var(--accent-400)' } : { color: 'var(--text-tertiary)' }}>
            <Radio size={14}/> ChirpPi
          </button>
        </div>
      </div>

      {source === 'device' && (
        <div className="mb-4">
          {devices.length === 0 ? (
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>No ChirpPi devices found — Haikubox and Bird Buddy don't support Live Detect. Add a ChirpPi in Devices first.</p>
          ) : (
            <select value={selectedDeviceId} onChange={e => changeDevice(e.target.value)}
                    className="w-full text-sm px-3 py-2 rounded-lg"
                    style={{ background: 'var(--bg-raised)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}>
              {devices.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          )}
          {selectedDevice && !birdMicName && (
            <p className="text-xs mt-1.5" style={{ color: '#f87171' }}>No bird mic recognized on this device.</p>
          )}
        </div>
      )}

      {/* Live visual */}
      <div className="rounded-xl overflow-hidden mb-4" style={{ height: 160, background: '#03080a', border: '1px solid var(--border-subtle)' }}>
        {listening && analyserRef.current ? (
          <LiveWaterfall analyser={analyserRef.current} active={listening} key={analyserVersion}/>
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <AudioLines size={28} className={listening ? 'animate-pulse' : ''} style={{ color: listening ? '#4ade80' : 'var(--text-tertiary)', opacity: listening ? 1 : 0.4 }}/>
          </div>
        )}
      </div>

      {/* Gain/filter — live monitoring only, never applied to what's sent
          for analysis (see connectProcessingChain's own comment for
          exactly where that boundary sits). Two columns rather than a
          single wide row so each slider's own w-full stays a fraction
          of the screen at any width, not a fixed pixel size that could
          overflow on a narrow phone. */}
      <div className="flex gap-4 mb-4 px-1">
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Volume boost</label>
            <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>{gainLevel.toFixed(1)}×</span>
          </div>
          <input type="range" min="0.5" max="4" step="0.1" value={gainLevel}
                 onChange={e => setGainLevel(parseFloat(e.target.value))}
                 className="w-full" style={{ accentColor: 'var(--accent-500)' }}/>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Cut low rumble</label>
            <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>{filterFreq === 0 ? 'Off' : `${filterFreq}Hz`}</span>
          </div>
          <input type="range" min="0" max="2000" step="50" value={filterFreq}
                 onChange={e => setFilterFreq(parseInt(e.target.value, 10))}
                 className="w-full" style={{ accentColor: 'var(--accent-500)' }}/>
        </div>
      </div>

      {/* Status card */}
      <div className="card rounded-xl p-4 mb-2 flex items-center gap-3">
        <div className="w-11 h-11 rounded-xl overflow-hidden flex items-center justify-center flex-shrink-0"
             style={{ background: listening ? 'rgba(74,222,128,.15)' : 'var(--bg-raised)' }}>
          {heardPhotoUrl ? (
            <img src={mediaUrl(heardPhotoUrl)} alt="" className="w-full h-full object-cover"
                 onError={e => { e.target.style.display = 'none' }}/>
          ) : (
            <BirdIcon size={20} style={{ color: listening ? '#4ade80' : 'var(--text-tertiary)' }}/>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>{statusText}</p>
          {error && <p className="text-xs mt-0.5" style={{ color: '#f87171' }}>{error}</p>}
        </div>
        <button onClick={toggleListening}
                className="tactile-press px-4 py-2 rounded-full text-sm font-semibold flex-shrink-0"
                style={listening
                  ? { background: 'rgba(248,113,113,.15)', color: '#f87171', border: '1px solid rgba(248,113,113,.35)' }
                  : { background: 'var(--accent-500)', color: '#000' }}>
          {listening ? 'Stop' : 'Start'}
        </button>
      </div>

      {source === 'phone' && (
        <div className="card rounded-xl p-4 mb-2">
          <label className="flex items-start gap-3 cursor-pointer">
            <span className="flex-1 min-w-0">
              <span className="block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Use my location</span>
              <span className="block text-[11px] mt-0.5" style={{ color: 'var(--text-tertiary)', lineHeight: 1.45 }}>
                {!useLocation ? 'Off: recordings use the home site\'s location.'
                  : locState === 'locating' ? 'Finding your location…'
                  : locState === 'denied' ? 'Location isn\'t allowed. Turn it on in the iPhone Settings app → Chirp → Location.'
                  : locState === 'unavailable' ? 'Location isn\'t available right now; using the home site\'s.'
                  : locState?.acc != null ? `Saved with recordings and used to judge likely birds (±${locState.acc} m).`
                  : 'Saved with Live Detect recordings and used to judge which birds are likely where you are.'}
              </span>
            </span>
            <input type="checkbox" className="w-5 h-5 mt-0.5 accent-chirp-500 flex-shrink-0" checked={useLocation}
                   onChange={e => { setUseLocation(e.target.checked); if (!e.target.checked) { stopLocation(); locRef.current = null; setLocState(null) } }}/>
          </label>
        </div>
      )}

      {source === 'device' && (
        <p className="text-[11px] px-1 mb-2" style={{ color: 'var(--text-tertiary)' }}>
          Recordings use {selectedDevice?.name ? `${selectedDevice.name}'s` : 'the device\'s'} location.
        </p>
      )}

      {/* Sensitivity slider — lower = catches more, including more false positives; this only affects Live Detect's own disposable checks, never anything permanently saved or the server-wide BirdNET setting */}
      <div className="card rounded-xl p-4 mb-2">
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Sensitivity</label>
          <span className="text-xs font-mono" style={{ color: 'var(--text-tertiary)' }}>{Math.round(sensitivity * 100)}% confidence minimum</span>
        </div>
        <input type="range" min="0.01" max="0.5" step="0.01" value={sensitivity}
               onChange={e => setSensitivity(parseFloat(e.target.value))}
               className="w-full accent-chirp-500"/>
        <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>
          Lower catches more (including more misses/false alarms) — doesn't change what gets permanently saved elsewhere.
        </p>
      </div>

      {/* Window length — phone mode only: device mode polls the Pi's own /listen endpoint on a fixed interval, not this client-side overlapping-clip scheme, so there's nothing here for it to adjust. */}
      {source === 'phone' && (
        <div className="card rounded-xl p-4 mb-2">
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Listening window</label>
            <span className="text-xs font-mono" style={{ color: 'var(--text-tertiary)' }}>{windowSeconds}s, {(windowSeconds / 2).toFixed(1)}s overlap</span>
          </div>
          <input type="range" min="3" max="10" step="0.5" value={windowSeconds}
                 onChange={e => setWindowSeconds(parseFloat(e.target.value))}
                 className="w-full accent-chirp-500"/>
          <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>
            Longer gives each analysis more context; two overlapping listening lanes (offset by half this window) mean a call is never split across a clip boundary either way. Takes effect on the next clip — no need to restart.
          </p>
        </div>
      )}
      {micPermissionDenied && (
        <p className="text-xs mb-5" style={{ color: 'var(--text-tertiary)' }}>
          Check your browser's site settings to allow microphone access, then press Start again.
        </p>
      )}

      {/* Heard today */}
      <div className="flex items-center justify-between mt-6 mb-2">
        <div>
          <h2 className="font-display text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>Heard Today</h2>
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{heardToday.length} species</p>
        </div>
        {/* A button that opens the SAME "Seen today" grid modal Dashboard's
            own Seen Today card already uses (imported straight from
            Dashboard.jsx, not a duplicate) — deliberately NOT a Link to
            another page. Reported directly: this used to navigate to
            Statistics, which is a strange destination for "show me
            today's species" (that page's own primary purpose is a much
            broader diversity/trend view — see its own Diversity Trend
            section), and navigating away would have also silently killed
            an active listening session, since stopEverything() runs on
            unmount. */}
        {heardToday.length > 0 && (
          <button onClick={() => setShowSeenToday(true)}
                  className="text-xs font-medium flex items-center gap-1"
                  style={{ color: 'var(--accent-400)', background: 'none', border: 'none', cursor: 'pointer' }}>
            View all <ChevronRight size={12}/>
          </button>
        )}
      </div>
      {showSeenToday && <SeenTodayModal species={heardToday} onClose={() => setShowSeenToday(false)}/>}
      {showSaveConfirm && (
        <SaveSessionModal
          sessionDetections={sessionDetections.filter(d => sessionStartRef.current && new Date(d.at) >= sessionStartRef.current)}
          onSave={handleSaveSession}
          onDiscard={handleDiscardSession}
          saving={savingSession}
          error={saveSessionError}
          savedRecordingId={savedSessionRecordingId}
        />
      )}

      {/* This session's detections, grouped by species */}
      {sessionDetections.length > 0 ? (
        <div className="flex flex-col gap-2 mt-2">
          {groupDetectionsBySpecies(sessionDetections).map(group => (
            <SpeciesGroupRow key={group.common_name} group={group} fmtAgo={fmtAgo}/>
          ))}
        </div>
      ) : (
        <p className="text-sm text-center py-8" style={{ color: 'var(--text-tertiary)' }}>
          {listening ? 'Listening\u2026 detections will appear here as they happen.' : 'Press Start to begin listening.'}
        </p>
      )}
    </div>
  )
}
