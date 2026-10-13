import { useState, useRef, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Upload, X, FileAudio, CheckCircle, AlertCircle,
  Loader, MapPin, ChevronDown
} from 'lucide-react'
import { api } from '../lib/api'
import { BirdIcon, BatIcon } from './BirdBatIcons'
import { useTz, fromLocalInput, timeFromFilename } from '../lib/time'
import { hapticEvent } from '../lib/haptics'

const ACCEPTED = ['.wav', '.mp3', '.flac', '.ogg', '.m4a']
const ACCEPTED_MIME = [
  'audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/mp3',
  'audio/flac', 'audio/ogg', 'audio/m4a', 'audio/x-m4a',
  'audio/aac', 'audio/',
]

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDuration(secs) {
  if (!secs) return '—'
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

// ── Single file row ───────────────────────────────────────────────────────────
function FileRow({ item, onRemove, onView, onWhen }) {
  const { file, status, progress, result, error, is_bat, when } = item

  const statusIcon = {
    queued:     <div className="w-4 h-4 rounded-full border-2 border-surface-500" />,
    uploading:  <Loader size={16} className="text-chirp-400 animate-spin" />,
    processing: <Loader size={16} className="text-yellow-400 animate-spin" />,
    done:       <CheckCircle size={16} className="text-chirp-400" />,
    error:      <AlertCircle size={16} className="text-red-400" />,
  }[status] || null

  const statusText = {
    queued:     'Waiting...',
    uploading:  `Uploading ${progress}%`,
    processing: is_bat ? 'Bat pipeline analyzing…' : 'BirdNET analyzing…',
    done:       result?.detectionCount != null
                ? (result.detectionCount > 0
                  ? `${result.detectionCount} detection${result.detectionCount !== 1 ? 's' : ''} found`
                  : 'No detections — open to see details')
                : 'Done',
    error:      error || 'Failed',
  }[status] || status

  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg border transition-colors
      ${status === 'done'  ? 'bg-chirp-900/20 border-chirp-700/40' :
        status === 'error' ? 'bg-red-900/20 border-red-700/40' :
        'bg-surface-700 border-surface-600'}`}
    >
      <FileAudio size={18} className={
        status === 'done' ? 'text-chirp-400' :
        status === 'error' ? 'text-red-400' : 'text-gray-400'
      } />

      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-200 font-medium truncate">{file.name}</p>
        <div className="flex items-center gap-3 mt-0.5">
          <span className="text-xs text-gray-500">{formatBytes(file.size)}</span>
          <span className={`text-xs flex items-center gap-1
            ${status === 'done' ? 'text-chirp-400' :
              status === 'error' ? 'text-red-400' : 'text-gray-500'}`}
          >
            {statusIcon}
            {statusText}
          </span>
        </div>

        {status === 'queued' && (
          <label className="flex items-center gap-2 mt-1.5 text-xs text-gray-400">
            Recorded
            <input type="datetime-local" step={1} className="input text-xs py-1 px-2 w-auto"
                   value={when || ''} onChange={e => onWhen(item.id, e.target.value)}/>
            {!when && <span className="text-gray-500">now</span>}
          </label>
        )}

        {/* Progress bar for upload */}
        {status === 'uploading' && (
          <div className="mt-1.5 h-1 bg-surface-600 rounded-full overflow-hidden">
            <div
              className="h-full bg-chirp-500 rounded-full transition-all duration-200"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1.5 flex-shrink-0">
        {status === 'done' && result?.id && (
          <button
            onClick={() => onView(result.id)}
            className="text-xs text-chirp-500 hover:text-chirp-400 bg-chirp-900/30 border border-chirp-700/50 px-2 py-1 rounded transition-colors"
          >
            View →
          </button>
        )}
        {(status === 'queued' || status === 'error') && (
          <button
            onClick={() => onRemove(item.id)}
            className="text-gray-500 hover:text-gray-300 transition-colors p-1"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  )
}

// ── Main upload modal / panel ─────────────────────────────────────────────────
export default function ManualUpload({ onClose }) {
  const navigate = useNavigate()
  const [files, setFiles] = useState([])   // Array of {id, file, status, progress, result, error}
  const [dragging, setDragging] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [latitude, setLatitude] = useState('')
  const [longitude, setLongitude] = useState('')
  const [label, setLabel] = useState('')
  const [isBat, setIsBat] = useState(false)
  const [batDetectionEnabled, setBatDetectionEnabled] = useState(false)
  const [running, setRunning] = useState(false)
  const { timezone } = useTz()
  const dropRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    api.settings.get().then(s => setBatDetectionEnabled(!!s.bat_detection_enabled)).catch(() => {})
  }, [])

  const addFiles = useCallback((newFiles) => {
    const valid = Array.from(newFiles).filter(f => {
      const ext = '.' + f.name.split('.').pop().toLowerCase()
      return ACCEPTED.includes(ext) || ACCEPTED_MIME.some(m => f.type.startsWith(m))
    })
    setFiles(prev => [
      ...prev,
      ...valid.map(f => ({
        id: Math.random().toString(36).slice(2),
        file: f,
        // Recorders put local time in the name (HaikuBox, AudioMoth, ...).
        when: timeFromFilename(f.name),
        status: 'queued',
        progress: 0,
        result: null,
        error: null,
      }))
    ])
  }, [])

  const onDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    addFiles(e.dataTransfer.files)
  }, [addFiles])

  const onDragOver = (e) => { e.preventDefault(); setDragging(true) }
  const onDragLeave = () => setDragging(false)

  const removeFile = (id) => setFiles(prev => prev.filter(f => f.id !== id))

  const updateFile = (id, patch) =>
    setFiles(prev => prev.map(f => f.id === id ? { ...f, ...patch } : f))

  const uploadAll = async () => {
    const queued = files.filter(f => f.status === 'queued')
    if (!queued.length) return
    setRunning(true)

    for (const item of queued) {
      updateFile(item.id, { status: 'uploading', progress: 0, is_bat: isBat })

      const formData = new FormData()
      formData.append('file', item.file)
      if (label) formData.append('label', label)
      if (latitude) formData.append('latitude', latitude)
      if (longitude) formData.append('longitude', longitude)
      formData.append('is_bat', isBat ? 'true' : 'false')
      if (item.when) {
        const iso = fromLocalInput(item.when, timezone)
        if (iso) formData.append('recorded_at', iso)
      }

      try {
        const result = await api.recordings.upload(
          formData,
          (pct) => updateFile(item.id, { progress: pct })
        )
        // Briefly show "processing" state
        updateFile(item.id, { status: 'processing', progress: 100 })

        // Poll for completion (up to 60s)
        let attempts = 0
        const maxAttempts = 30
        await new Promise(resolve => {
          const poll = setInterval(async () => {
            attempts++
            try {
              const rec = await api.recordings.get(result.id)
              if (rec.processing_status === 'done' || rec.processing_status === 'error') {
                clearInterval(poll)
                const noDetections = rec.processing_status === 'done' && rec.detections?.length === 0
                updateFile(item.id, {
                  status: rec.processing_status === 'done' ? 'done' : 'error',
                  result: { ...result, detectionCount: rec.detections?.length ?? 0 },
                  error: rec.processing_status === 'error'
                    ? 'Processing failed'
                    : noDetections
                    ? 'No bird calls detected — open recording for details'
                    : null,
                })
                resolve()
              }
            } catch {}
            if (attempts >= maxAttempts) {
              clearInterval(poll)
              // Treat as done anyway — might just be slow
              updateFile(item.id, { status: 'done', result })
              hapticEvent('success')
              resolve()
            }
          }, 2000)
        })
      } catch (e) {
        updateFile(item.id, { status: 'error', error: e.message })
        hapticEvent('error')
      }
    }

    setRunning(false)
  }

  const queuedCount = files.filter(f => f.status === 'queued').length
  const doneCount = files.filter(f => f.status === 'done').length
  const allDone = files.length > 0 && files.every(f => f.status === 'done' || f.status === 'error')

  return (
    /* Backdrop */
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
         onClick={(e) => e.target === e.currentTarget && onClose()}>

      <div className="bg-surface-800 border border-surface-600 rounded-2xl shadow-2xl w-full max-w-xl
                      flex flex-col max-h-[90vh] animate-slide-up">

        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-surface-700">
          <div>
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Upload size={18} className="text-chirp-500" />
              Manual Recording Upload
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              WAV · MP3 · FLAC · OGG · M4A — analyzed server-side
            </p>
          </div>
          <button onClick={onClose}
                  className="text-gray-500 hover:text-gray-200 transition-colors p-1 rounded-lg hover:bg-surface-700">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Drop zone */}
          <div
            ref={dropRef}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200
              ${dragging
                ? 'border-chirp-500 bg-chirp-900/30 scale-[1.01]'
                : 'border-surface-600 hover:border-chirp-700 hover:bg-surface-700/50'
              }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ACCEPTED.join(',')}
              className="hidden"
              onChange={e => addFiles(e.target.files)}
            />
            <div className={`w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-3 transition-colors
              ${dragging ? 'bg-chirp-600' : 'bg-surface-700'}`}>
              <Upload size={22} className={dragging ? 'text-white' : 'text-gray-400'} />
            </div>
            <p className="text-sm font-medium text-gray-300">
              {dragging ? 'Drop to add files' : 'Drop audio files here'}
            </p>
            <p className="text-xs text-gray-500 mt-1">or click to browse</p>
            <p className="text-xs text-gray-600 mt-2">{ACCEPTED.join(' · ')}</p>
          </div>

          {/* File list */}
          {files.length > 0 && (
            <div className="space-y-2">
              {files.map(item => (
                <FileRow
                  key={item.id}
                  item={item}
                  onRemove={removeFile}
                  onWhen={(id, when) => updateFile(id, { when })}
                  onView={(id) => { onClose(); navigate(`/recordings/${id}`) }}
                />
              ))}
            </div>
          )}

          {/* Recording type: bird vs bat — determines which pipeline processes
              the file (BirdNET vs the bat spectrogram/species pipeline).
              Shown prominently, not tucked into Advanced options, since it's
              not a minor setting — picking wrong sends the file through the
              wrong analysis entirely. Only shown when bat detection is
              actually enabled server-side (Settings → Detection), same
              gating as the "Bats only" filter on the Recordings page —
              no point offering a bat option nobody has set up for. */}
          {files.length > 0 && batDetectionEnabled && (
            <div className="flex items-center gap-2">
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Recording type:</span>
              <button
                onClick={() => setIsBat(false)}
                className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5"
                style={!isBat
                  ? { background: 'rgba(34,211,238,.15)', color: '#22d3ee', border: '1px solid rgba(34,211,238,.4)' }
                  : { background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
                <BirdIcon size={13}/> Bird
              </button>
              <button
                onClick={() => setIsBat(true)}
                className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5"
                style={isBat
                  ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)', border: '1px solid var(--border-default)' }
                  : { background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
                <BatIcon size={13}/> Bat
              </button>
            </div>
          )}
          {files.length > 0 && batDetectionEnabled && isBat && (
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              Needs a genuine ultrasonic microphone recording (192kHz+) — a normal phone or bird-mic
              recording (44.1/48kHz) can't physically contain bat echolocation calls and will be rejected.
            </p>
          )}

          {/* Advanced options */}
          {files.length > 0 && (
            <div>
              <button
                onClick={() => setShowAdvanced(v => !v)}
                className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                <ChevronDown size={14} className={`transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
                Advanced options
              </button>

              {showAdvanced && (
                <div className="mt-3 space-y-3 p-3 bg-surface-700/60 rounded-lg border border-surface-600">
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">
                      Label / Note (optional)
                    </label>
                    <input
                      className="input text-xs py-1.5"
                      placeholder="e.g. Backyard at dawn, June 2025"
                      value={label}
                      onChange={e => setLabel(e.target.value)}
                    />
                  </div>
                  <div className="flex gap-2 items-center">
                    <MapPin size={13} className="text-gray-500 flex-shrink-0" />
                    <div className="grid grid-cols-2 gap-2 flex-1">
                      <input
                        className="input text-xs py-1.5 font-mono"
                        placeholder="Latitude"
                        type="number"
                        step="0.0001"
                        value={latitude}
                        onChange={e => setLatitude(e.target.value)}
                      />
                      <input
                        className="input text-xs py-1.5 font-mono"
                        placeholder="Longitude"
                        type="number"
                        step="0.0001"
                        value={longitude}
                        onChange={e => setLongitude(e.target.value)}
                      />
                    </div>
                  </div>
                  <p className="text-xs text-gray-600">
                    GPS coordinates tag this recording for location-based species likelihood scoring.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Info box */}
          {files.length === 0 && (
            <div className="bg-surface-700/40 rounded-lg p-3 border border-surface-600 space-y-1.5">
              <p className="text-xs font-medium text-gray-300">How manual upload works</p>
              <ul className="text-xs text-gray-500 space-y-1">
                <li>• BirdNET scans the full recording in 3-second sliding windows</li>
                <li>• Detections are stored with timestamps so you can jump to each bird</li>
                <li>• A mel spectrogram is generated with colored detection overlays</li>
                <li>• Species profiles are enriched from eBird, Xeno-canto & Wikipedia</li>
                <li>• Large files may take 10–30s to analyze server-side</li>
              </ul>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-5 border-t border-surface-700 flex items-center justify-between gap-3">
          <div className="text-xs text-gray-500">
            {files.length > 0 && (
              <span>
                {files.length} file{files.length !== 1 ? 's' : ''}
                {doneCount > 0 && ` · ${doneCount} done`}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={onClose} className="btn-secondary">
              {allDone ? 'Close' : 'Cancel'}
            </button>
            {queuedCount > 0 && (
              <button
                onClick={uploadAll}
                disabled={running}
                className="btn-primary flex items-center gap-2"
              >
                {running
                  ? <><Loader size={14} className="animate-spin" /> Analyzing...</>
                  : <><Upload size={14} /> Analyze {queuedCount} file{queuedCount !== 1 ? 's' : ''}</>
                }
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
