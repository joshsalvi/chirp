import React, { useEffect, useState, useRef, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { format } from 'date-fns'
import ReactMarkdown from 'react-markdown'
import {
  Play, Pause, Download, ArrowLeft,
  AlertCircle, RefreshCw, Pencil, Trash2, Save, X,
  Share2, Copy, Check, CheckCircle, MapPin, ChevronDown, ChevronUp, Activity, Sparkles, Wand2,
  Archive, ArchiveRestore, Server, Cpu, MessageSquare, Bookmark, BookmarkCheck
} from 'lucide-react'
import { BirdIcon, BatIcon } from './BirdBatIcons'
import { api, clearApiCache } from '../lib/api'
import { saveUrl } from '../lib/download'
import { pickSpeciesColors, DEFAULT_PALETTE, confBadgeClass, confLabel } from '../lib/detectionColors'
import { useTz, toLocalInput, fromLocalInput } from '../lib/time'
import Comments from './Comments'
import InatSubmitButton from './InatSubmitButton'
import ReanalysisHistory from './ReanalysisHistory'
import ShadowComparison from './ShadowComparison'
import { hapticEvent } from '../lib/haptics'

function CollapsibleSection({ title, icon: Icon, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="card overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
              className="w-full flex items-center justify-between px-4 py-3 transition-colors hover:bg-raised"
              style={{ background: 'var(--bg-card)' }}>
        <div className="flex items-center gap-2">
          {Icon && <Icon size={14} style={{ color: 'var(--accent-400)' }}/>}
          <span className="text-sm font-semibold font-display" style={{ color: 'var(--text-primary)' }}>{title}</span>
        </div>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
             style={{ color: 'var(--text-tertiary)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }}>
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
      {open && <div className="px-4 pb-4 pt-2">{children}</div>}
    </div>
  )
}

// Kept only as a generic "active/played" accent color for UI elements
// unrelated to species (see DET_COLORS[0] usage below) — actual
// per-species coloring now goes through pickSpeciesColors() and the
// user's chosen palette instead of this fixed array directly.
const DET_COLORS = [
  "#ef4444",  // Red
  "#f97316",  // Orange
  "#eab308",  // Yellow
  "#84cc16",  // Yellow-green
  "#22c55e",  // Green
  "#14b8a6",  // Teal
  "#06b6d4",  // Cyan
  "#3b82f6",  // Blue
  "#6366f1",  // Indigo
  "#a855f7",  // Purple
  "#ec4899",  // Pink
  "#f43f5e",  // Rose
]

// Stable per-species color (matches spectrogram overlay colors) — see
// lib/detectionColors.js for the full palette definitions and the
// even-spread-by-count assignment algorithm this now uses.
function speciesColor(detections, speciesName, paletteKey = DEFAULT_PALETTE) {
  const unique = [...new Set((detections || []).map(d => d.common_name))]
  const colorMap = pickSpeciesColors(unique, paletteKey)
  return colorMap[speciesName] || '#ef4444'
}

function fmt(s) {
  if (!s || isNaN(s)) return '0:00'
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
}


// Birds: one Enhance control. "Enhanced" cuts low rumble (traffic, wind,
// HVAC) and reduces steady background noise together; "AI" is neural
// denoising (Settings → AI Features → AI Enhance), which works at 16 kHz.
function EnhanceControl({ mode, onChange, aiAvailable, aiLoading, aiError, compact = false }) {
  const opts = [['original', 'Original'], ['enhanced', 'Enhanced'], ...(aiAvailable ? [['ai', 'AI']] : [])]
  const tips = {
    original: 'The recording as made',
    enhanced: 'Cuts low rumble and reduces background noise',
    ai: aiError || 'Neural denoising: isolates the call (sound above 8 kHz is lost)',
  }
  return (
    <div role="radiogroup" aria-label="Enhance" className={`inline-flex rounded-full p-0.5 ${compact ? 'text-[11px]' : 'text-xs'}`}
         style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
      {opts.map(([k, label]) => {
        const on = mode === k
        return (
          <button key={k} role="radio" aria-checked={on} title={tips[k]} onClick={() => onChange(k)}
                  className={`flex items-center gap-1 rounded-full transition-colors ${compact ? 'px-2 py-0.5' : 'px-2.5 py-1'}`}
                  style={on
                    ? { background: k === 'ai' && aiError ? 'rgba(248,113,113,.18)' : 'var(--nav-active-bg)', color: k === 'ai' && aiError ? '#f87171' : 'var(--accent-400)' }
                    : { color: 'var(--text-tertiary)' }}>
            {k === 'enhanced' && <Sparkles size={compact ? 10 : 12}/>}
            {k === 'ai' && (on && aiLoading ? <RefreshCw size={compact ? 10 : 12} className="animate-spin"/> : <Wand2 size={compact ? 10 : 12}/>)}
            {label}
          </button>
        )
      })}
    </div>
  )
}

// AI Second Opinion: one overall rating (server overall_rating(): the AI's
// read of the spectrogram combined with the measured audio check), the
// audio check's findings, then the AI's full reasoning folded under "Why".
// Rating scale, worst to best. Only the reached step is lit and labelled.
const RATING_SCALE = [
  { level: 'unlikely',  color: '#f87171', text: 'badge-red' },
  { level: 'uncertain', color: '#fbbf24', text: 'badge-yellow' },
  { level: 'probably',  color: '#a3e635', text: 'badge-green' },
  { level: 'likely',    color: '#4ade80', text: 'badge-green' },
]
function RatingScale({ level, label }) {
  const idx = Math.max(0, RATING_SCALE.findIndex(r => r.level === level))
  const { text } = RATING_SCALE[idx]
  return (
    <div role="img" aria-label={`AI second opinion: ${label}`} className="space-y-1">
      <div className="grid grid-cols-4 gap-1">
        {RATING_SCALE.map((r, i) => (
          <span key={r.level} className="h-2 rounded-full"
                style={{ background: r.color, opacity: i === idx ? 1 : 0.18 }}/>
        ))}
      </div>
      <div className="grid grid-cols-4 gap-1 text-xs font-semibold">
        {/* badge-* for a text colour that reads in light themes too */}
        <span className={text} style={{ background: 'none', border: 0, padding: 0, gridColumn: idx + 1, textAlign: idx === 0 ? 'left' : idx === 3 ? 'right' : 'center', whiteSpace: 'nowrap' }}>
          {label}
        </span>
      </div>
    </div>
  )
}
const md = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong style={{ color: 'var(--text-primary)' }}>{children}</strong>,
}
function SecondOpinionBody({ note, rating }) {
  if (!rating) {
    return (
      <div className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        <ReactMarkdown components={md}>{note}</ReactMarkdown>
      </div>
    )
  }
  // The audio check is shown above; the model's closing "Overall:" is its
  // read of the image only, so it's labelled that way in the details.
  const details = note
    .split(/\n\s*\n/)
    .filter(p => !p.trim().startsWith('**Audio check for'))
    .join('\n\n')
    .replace(/\*\*Overall:\*\*/g, '**The AI’s read of the spectrogram:**')
  return (
    <div className="space-y-3">
      <div className="rounded-lg p-3 space-y-1.5" style={{ background: 'var(--bg-raised)' }}>
        <RatingScale level={rating.level} label={rating.label}/>
        <p className="text-sm" style={{ color: 'var(--text-primary)' }}>{rating.summary}</p>
        {rating.checks?.length > 0 && (
          <ul className="text-sm space-y-0.5" style={{ color: 'var(--text-secondary)' }}>
            {rating.checks.map((c, i) => <li key={i}>• {c}</li>)}
          </ul>
        )}
      </div>
      <details className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        <summary className="cursor-pointer text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>Why: the AI’s full read</summary>
        <div className="mt-2"><ReactMarkdown components={md}>{details}</ReactMarkdown></div>
      </details>
    </div>
  )
}

// ── Audio player with amplitude waveform ─────────────────────────────────────
const WAVEFORM_BARS = 200   // number of amplitude bars to display
const WAVEFORM_H = 56       // total canvas height in px (28px each half)
const BAR_H_MAX = 26        // max bar half-height in px

function AudioPlayer({ src, detections, duration: recDuration, recordingId, seekRef, enhanced, onToggleEnhanced, isBat, colorPalette, rumbleRemovalMode = 'auto', rumbleRemoved = false, onToggleRumbleRemoved, aiEnhanceEnabled = false, aiEnhanced = false, onToggleAiEnhanced, onSetEnhanceMode }) {
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(recDuration || 0)
  const [waveform, setWaveform] = useState(null)   // [[min,max], ...]
  // De-wobbled is independent of the parent-controlled `enhanced` state
  // (Original/Enhanced) — kept local since it's bat-only and doesn't
  // affect the spectrogram view the way `enhanced` does for birds.
  // Combinable WITH enhanced (both can be on at once) — the server has
  // a dedicated /audio/dewobbled-enhanced endpoint for exactly that
  // combination, chaining remove_bat_wobble then downshift_bat_clip in
  // that order (see the endpoint's own docstring for why the order is
  // fixed). Only duration-restore timing needs to account for time
  // expansion; de-wobbling alone doesn't change duration at all.
  const [dewobbled, setDewobbled] = useState(false)
  // Rumble removal is bird-only (the bat-equivalent concept is
  // dewobbled, above) — independent of enhanced for the same reason
  // dewobbled is: requested directly as two separate options rather
  // than one bundled "Enhanced" toggle, so a person can pick just the
  // rumble cutoff, just noise reduction, or both. Combinable with
  // enhanced via the dedicated /audio/rumble-removed-enhanced endpoint,
  // same pattern as dewobbled+enhanced below.
  // Reported directly: rumble removal needed to be automatic, not
  // something a person has to remember to toggle on every recording —
  // defaults to on for birds (bats don't have this option at all, see
  // the !isBat check on the toggle button below). Still a real toggle,
  // not forced — someone who wants the true unfiltered original can
  // switch it off.
  //
  // rumbleRemovalMode (Settings > Recording, server-controlled):
  //   "auto"     — toggle shown, defaults on for birds (behavior above,
  //                unchanged).
  //   "auto_off" — toggle shown, defaults off — for when people should
  //                be able to turn it on themselves without it being
  //                applied automatically.
  //   "disabled" — feature hidden entirely, always off.
  //
  // Lifted to the parent (like `enhanced`/`aiEnhanced` already are)
  // rather than kept local, so SpectrogramImage can react to the same
  // toggle — reported directly: toggling Rumble removed changed the
  // audio but the spectrogram stayed the original, the same gap
  // Enhanced/AI Enhanced already had fixed for their own toggles.
  // AI Enhance (Experimental) — a separate, independent neural-denoising
  // alternative to Enhanced/Rumble removed (see services/ai_enhance.py).
  // Lifted to the parent (like `enhanced` already is) rather than kept
  // local, so SpectrogramImage can react to the same toggle — reported
  // directly: toggling AI Enhance changed the audio but the spectrogram
  // stayed the original, the same gap the classical Enhanced toggle had
  // before it got the same treatment.
  //
  // aiLoading/aiError track the actual network request for THIS specific
  // audio source, since AI Enhance is a real neural-net pass — first
  // request per recording can take a genuinely noticeable amount of
  // time (and downloads a one-time ~75MB model on this server's very
  // first use of the feature, ever), unlike the classical toggles which
  // are near-instant. Reported directly: clicking AI Enhance then Play
  // did nothing with no indication why — root cause was never showing
  // a loading state, AND never surfacing a load failure (the <audio>
  // element had no onError handler at all before this, so a 400/500
  // from the server — e.g. torch/torchaudio genuinely not installed on
  // this server despite the Settings toggle being on — just looked
  // identical to a still-buffering, was-about-to-play audio element).
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState(null)
  const audioRef = useRef(null)
  // Captured just before switching sources, so we can restore position —
  // changing <audio src> resets playback, and without this the player would
  // jump back to 0:00 every time the Enhanced toggle is clicked.
  const resumeStateRef = useRef({ fraction: 0, wasPlaying: false })

  // Manual cutoff override for Rumble removed, requested directly to
  // match LiveDetect.jsx's own "Cut low rumble" slider (0-2000Hz) —
  // previously the cutoff was ALWAYS the automatic species-aware
  // value with no way to adjust it directly. null = automatic
  // (unchanged default behavior); a number is the person's own choice.
  // Kept local (not lifted like rumbleRemoved) since the spectrogram
  // doesn't yet have an hz-aware counterpart — only the audio reacts
  // to this for now.
  const [rumbleHz, setRumbleHz] = useState(null)
  const [rumbleHzDraft, setRumbleHzDraft] = useState(null) // live slider position while dragging, before it's committed to a real request

  // AI Enhance takes priority over the classical toggles when on — it's
  // a full alternative processing path, not something meant to combine
  // with bandpass/noise-reduction (avoids a combinatorial explosion of
  // endpoints for combinations that would be redundant anyway, since AI
  // Enhance already does its own noise suppression).
  const effectiveSrc = !recordingId ? src
    : aiEnhanced ? api.recordings.audioAiEnhancedUrl(recordingId)
    : (dewobbled && enhanced) ? api.recordings.audioDewobbledEnhancedUrl(recordingId)
    : dewobbled ? api.recordings.audioDewobbledUrl(recordingId)
    : (rumbleRemoved && enhanced) ? api.recordings.audioRumbleRemovedEnhancedUrl(recordingId, rumbleHz)
    : rumbleRemoved ? api.recordings.audioRumbleRemovedUrl(recordingId, rumbleHz)
    : enhanced ? api.recordings.audioEnhancedUrl(recordingId)
    : src

  const captureResumeState = () => {
    const a = audioRef.current
    const fraction = a && a.duration > 0 ? a.currentTime / a.duration : 0
    resumeStateRef.current = { fraction, wasPlaying: !!a && !a.paused }
  }

  const toggleEnhanced = () => {
    // Store playback position as a FRACTION of duration, not raw seconds —
    // enhanced (time-expanded) bat audio has a genuinely different total
    // duration than the original, so restoring the same second-value would
    // land at the wrong relative position (e.g. 0.3s into a 0.5s original
    // is 60% through, but 0.3s into a 5s time-expanded version is only 6%).
    captureResumeState()
    onToggleEnhanced()
  }

  const toggleDewobbled = () => {
    captureResumeState()
    setDewobbled(d => !d)
  }

  // AI Enhance is the one source in this chain that's a real, possibly-
  // slow network request rather than an instant local toggle — start the
  // loading indicator the moment it's turned on (rather than waiting for
  // the <audio> element's own onLoadStart, which can lag behind a click
  // by a render cycle) and clear it once the source actually changes
  // away, so a person switching back to Original mid-generation doesn't
  // see a stuck spinner for a request that's no longer relevant.
  useEffect(() => {
    if (aiEnhanced) setAiLoading(true)
    else { setAiLoading(false); setAiError(null) }
  }, [aiEnhanced, recordingId])

  const toggleRumbleRemoved = () => {
    captureResumeState()
    onToggleRumbleRemoved && onToggleRumbleRemoved()
  }

  const toggleAiEnhanced = () => {
    captureResumeState()
    setAiError(null)
    onToggleAiEnhanced && onToggleAiEnhanced()
  }

  // Restore position/playback state once the new source has loaded enough
  // to seek (loadedmetadata fires before the browser knows duration on some
  // sources, so we wait for it explicitly rather than racing the src swap).
  // Also syncs duration state right here, at the moment it's actually known
  // for whichever source just loaded, rather than relying only on the
  // <audio> tag's own onLoadedMetadata prop.
  useEffect(() => {
    const a = audioRef.current
    if (!a) return
    const restore = () => {
      setDuration(a.duration)
      a.currentTime = resumeStateRef.current.fraction * (a.duration || 0)
      if (resumeStateRef.current.wasPlaying) a.play().catch(() => {})
    }
    a.addEventListener('loadedmetadata', restore, { once: true })
    return () => a.removeEventListener('loadedmetadata', restore)
  }, [effectiveSrc])

  // Fetch amplitude waveform once recordingId is known
  useEffect(() => {
    if (!recordingId) return
    api.recordings.waveform(recordingId, WAVEFORM_BARS)
      .then(d => { if (Array.isArray(d.waveform)) setWaveform(d.waveform) })
      .catch(() => {})
  }, [recordingId])

  const seekTo = (t) => {
    const a = audioRef.current
    if (!a) return
    a.currentTime = Math.max(0, Math.min(t, a.duration || 0))
    a.play().catch(() => {})
    setPlaying(true)
  }
  if (seekRef) seekRef.current = seekTo

  const d = duration || recDuration || 0
  const pct = d > 0 ? Math.min(100, (currentTime / d) * 100) : 0

  const handleSeekClick = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    seekTo(ratio * d)
  }

  // Pre-compute placeholder sine-wave bars (no Math.random - stable across renders)
  const placeholder = Array.from({ length: WAVEFORM_BARS }, (_, i) =>
    4 + Math.abs(Math.sin(i * 0.18) * 10 + Math.sin(i * 0.07) * 6))

  // Normalize to the peak amplitude so the waveform always fills the view
  const bars = waveform
    ? (() => {
        const raw = waveform.map(([mn, mx]) => Math.abs(mx - mn))
        const peak = Math.max(...raw, 0.001)   // avoid div-by-zero on silence
        return raw.map(v => Math.max(2, Math.round((v / peak) * BAR_H_MAX)))
      })()
    : placeholder

  return (
    <div>
      <audio ref={audioRef} src={effectiveSrc} preload="metadata"
        onTimeUpdate={e => setCurrentTime(e.target.currentTime)}
        onLoadedMetadata={e => setDuration(e.target.duration)}
        onCanPlay={() => { if (aiEnhanced) setAiLoading(false) }}
        onError={() => {
          if (aiEnhanced) {
            setAiLoading(false)
            setAiError('AI Enhance failed to load — check Settings > AI Features, or server logs if it\'s enabled there')
          }
          setPlaying(false)
        }}
        onEnded={() => setPlaying(false)}/>

      {/* Waveform - full bleed, overlays for label + time */}
      <div className="relative overflow-hidden cursor-pointer select-none bg-surface-950"
           style={{ height: WAVEFORM_H }}
           onClick={handleSeekClick}>
        {/* Label overlay top-left */}
        <span className="absolute top-1 left-2 z-10 text-xs font-medium text-gray-400 pointer-events-none select-none">
          Full Recording{(() => {
            const tags = [aiEnhanced && 'AI Enhanced', enhanced && 'Enhanced', dewobbled && 'De-wobbled', rumbleRemoved && 'Rumble removed'].filter(Boolean)
            return tags.length ? ` (${tags.join(', ')})` : ''
          })()}
        </span>


        {/* Detection region overlays */}
        {(detections || []).map((det, i) => {
          if (!d) return null
          // Reported directly: detection markers squeezed toward the left
          // when Enhanced/De-wobbled was toggled on a bat recording. Root
          // cause: det.start_time/end_time are always in the ORIGINAL
          // recording's timeline, but this used `d` (the CURRENTLY
          // LOADED audio's real duration) as the denominator — and bat
          // time-expansion genuinely changes duration (a 1s original can
          // become several seconds once downshifted), so dividing an
          // original-timeline position by an expanded total duration
          // produced a much smaller percentage than the true position.
          // recDuration is always the original timeline's total length —
          // the same timeline start_time/end_time are already expressed
          // in — so it's the correct denominator regardless of which
          // variant is currently loaded, unlike `d`.
          const timelineDuration = recDuration || d
          const left = (det.start_time / timelineDuration) * 100
          const width = Math.max(0.3, ((det.end_time - det.start_time) / timelineDuration) * 100)
          const color = speciesColor(detections, det.common_name, colorPalette)
          return (
            <div key={det.id} className="absolute inset-y-0 opacity-25 pointer-events-none"
                 style={{ left: `${left}%`, width: `${width}%`,
                          background: color, borderLeft: `2px solid ${color}` }}
                 title={`${det.common_name} ${(det.confidence * 100).toFixed(0)}%`}/>
          )
        })}

        {/* Amplitude bars — symmetric waveform, pixel heights */}
        <div className="absolute inset-0 flex items-end justify-center px-1 gap-px pointer-events-none"
             style={{ paddingBottom: '50%' }}>
          {bars.map((h, i) => {
            const barPct = (i / bars.length) * 100
            const played = barPct < pct
            const barH = Math.max(2, h)
            return (
              <div key={i} className="flex-1 relative flex flex-col items-center"
                   style={{ height: barH * 2, transform: 'translateY(50%)' }}>
                {/* Upper half */}
                <div className="w-full absolute" style={{
                  height: barH, bottom: '50%', left: 0,
                  background: played ? DET_COLORS[0] : '#4b5563',
                  borderRadius: '1px 1px 0 0',
                }}/>
                {/* Lower half (mirror) */}
                <div className="w-full absolute" style={{
                  height: barH, top: '50%', left: 0,
                  background: played ? DET_COLORS[0] : '#374151',
                  borderRadius: '0 0 1px 1px',
                  opacity: 0.7,
                }}/>
              </div>
            )
          })}
        </div>

        {/* Playhead */}
        <div className="absolute inset-y-0 w-px bg-white/80 pointer-events-none"
             style={{ left: `${pct}%` }}/>

        {/* Time overlay */}
        <div className="absolute bottom-1 right-2 text-xs text-gray-400 font-mono pointer-events-none bg-surface-950/60 px-1 rounded">
          {fmt(currentTime)} / {fmt(d)}
        </div>

        {/* Waveform loading indicator */}
        {!waveform && recordingId && (
          <div className="absolute top-1 left-2 text-xs text-gray-600 pointer-events-none">
            Loading waveform…
          </div>
        )}
      </div>

      {/* Custom scrubber — uses identical left:pct% to waveform playhead for pixel-perfect sync */}
      <div className="relative h-5 cursor-pointer select-none"
           onClick={e => {
             const rect = e.currentTarget.getBoundingClientRect()
             seekTo(Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)) * d)
           }}
           onMouseDown={e => {
             const el = e.currentTarget
             const move = mv => {
               const rect = el.getBoundingClientRect()
               seekTo(Math.max(0, Math.min(1, (mv.clientX - rect.left) / rect.width)) * d)
             }
             const up = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up) }
             window.addEventListener('mousemove', move)
             window.addEventListener('mouseup', up)
           }}>
        {/* Track */}
        <div className="absolute left-0 right-0 top-1/2 -translate-y-1/2 h-1 bg-surface-600 rounded-full"/>
        {/* Fill */}
        <div className="absolute top-1/2 -translate-y-1/2 h-1 bg-chirp-500 rounded-full"
             style={{ left: 0, width: `${pct}%` }}/>
        {/* Thumb — centered on pct% */}
        <div className="absolute top-1/2 w-4 h-4 bg-white rounded-full shadow-md pointer-events-none"
             style={{ left: `${pct}%`, transform: 'translate(-50%, -50%)' }}/>
      </div>
      {/* Play controls row — play button + time only. Toggles moved to
          their own row below: reported directly, with a screenshot, that
          cramming Original/Enhanced + De-wobbled + Rumble removed + AI
          Enhance into this same row (the last one pushed almost entirely
          off-screen) was unreadable on a phone. */}
      <div className="flex items-center gap-3 px-4 pt-1 pb-2">
        <button onClick={() => {
          const a = audioRef.current
          if (!a || (aiEnhanced && aiLoading)) return
          if (a.paused) { a.play().catch(() => {}); setPlaying(true) }
          else { a.pause(); setPlaying(false) }
        }} disabled={aiEnhanced && aiLoading}
           className="w-9 h-9 bg-chirp-600 hover:bg-chirp-500 rounded-full flex items-center justify-center flex-shrink-0 transition-colors disabled:opacity-50">
          {aiEnhanced && aiLoading
            ? <RefreshCw size={14} className="animate-spin"/>
            : playing ? <Pause size={16}/> : <Play size={16} className="ml-0.5"/>}
        </button>
        <span className="text-xs text-gray-400 font-mono">{fmt(currentTime)} / {fmt(d)}</span>
      </div>
      {/* Toggle row — wraps naturally (flex-wrap) if it still doesn't fit
          one line on a narrow screen, rather than clipping off the edge. */}
      <div className="flex items-center gap-2 px-4 pb-3 flex-wrap">
        {isBat ? (<>
          <button onClick={toggleEnhanced}
                className={`flex items-center gap-1 text-xs px-2 py-1 rounded-full border transition-colors ${
                  enhanced
                    ? 'bg-chirp-900/40 border-chirp-600 text-chirp-300'
                    : 'bg-surface-800 border-surface-600 text-gray-400 hover:text-gray-200'
                }`}>
          <Sparkles size={12}/> {enhanced ? 'Enhanced' : 'Original'}
        </button>
        {isBat && (
          <button onClick={toggleDewobbled}
                  title="Experimental: attenuates the persistent AudioMoth/fan interference tone — can occasionally affect a real call's own content, see Settings for detail"
                  className={`flex items-center gap-1 text-xs px-2 py-1 rounded-full border transition-colors ${
                    dewobbled
                      ? 'bg-chirp-900/40 border-chirp-600 text-chirp-300'
                      : 'bg-surface-800 border-surface-600 text-gray-400 hover:text-gray-200'
                  }`}>
            <Sparkles size={12}/> De-wobbled
          </button>
        )}
        </>) : (
          <EnhanceControl
            mode={aiEnhanced ? 'ai' : (enhanced || rumbleRemoved) ? 'enhanced' : 'original'}
            onChange={m => { captureResumeState(); setAiError(null); onSetEnhanceMode && onSetEnhanceMode(m) }}
            aiAvailable={aiEnhanceEnabled} aiLoading={aiLoading} aiError={aiError}/>
        )}
      </div>
      {rumbleRemoved && !aiEnhanced && rumbleRemovalMode !== 'disabled' && (
        <div className="flex items-center gap-2 px-4 pb-3">
          <label className="text-xs flex-shrink-0" style={{ color: 'var(--text-tertiary)' }} title="Sound below this pitch is cut. Auto picks it from the birds detected.">Low cut</label>
          <input type="range" min="0" max="2000" step="50"
                 title="Manual cutoff — starts at the automatic species-aware value; drag to override it directly, matching Live Detect's own rumble slider"
                 value={rumbleHzDraft ?? rumbleHz ?? 800}
                 onChange={e => setRumbleHzDraft(parseInt(e.target.value, 10))}
                 onMouseUp={() => { if (rumbleHzDraft != null) { captureResumeState(); setRumbleHz(rumbleHzDraft); setRumbleHzDraft(null) } }}
                 onTouchEnd={() => { if (rumbleHzDraft != null) { captureResumeState(); setRumbleHz(rumbleHzDraft); setRumbleHzDraft(null) } }}
                 className="flex-1" style={{ accentColor: 'var(--accent-500)' }}/>
          <span className="text-xs font-mono flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>
            {rumbleHzDraft != null ? (rumbleHzDraft === 0 ? 'Off' : `${rumbleHzDraft}Hz`)
              : rumbleHz != null ? (rumbleHz === 0 ? 'Off' : `${rumbleHz}Hz`)
              : 'Auto'}
          </span>
        </div>
      )}
      {aiError && (
        <p className="px-4 pb-2 text-xs" style={{ color: 'var(--pastel-red, #f87171)' }}>{aiError}</p>
      )}
    </div>
  )
}

// ── Detection card ────────────────────────────────────────────────────────────
function DetectionCard({ det, recordingId, detections, onPlayAt, colorPalette, aiEnhanceEnabled = false, rumbleRemovalMode = 'auto' }) {
  // Bat detections are always common_name === "Bat" (see reanalyze's
  // bat branch, which creates them this way) — no isBat prop needed.
  // Reported directly: 1s bat clip playback was "funky", doing nothing
  // when not enhanced. That's not really a playback bug — a bat clip's
  // "original" audio is the raw ultrasonic recording (see
  // downshift_bat_clip()'s docstring: enhancement here is a frequency
  // downshift, not noise reduction like it is for birds), which is
  // genuinely inaudible to a human listener regardless of whether
  // playback itself is working correctly. The audio element plays it
  // fine; there's just nothing a person can hear in it. Locking
  // enhanced on for bats — the toggle offered a real, audible option
  // for birds (raw vs. denoised), but its "off" position for bats
  // isn't a real option, just a broken-looking dead end.
  const isBatDetection = det.common_name === 'Bat'
  const [clipPlaying, setClipPlaying] = useState(false)
  const [clipEnhanced, setClipEnhanced] = useState(true)   // birds open in Enhanced, like the player
  // AI Enhance for a single clip — independent of clipEnhanced (the
  // classical noise-reduction toggle), same reasoning as the full-
  // recording player: a full alternative processing path, not meant to
  // combine with the classical one. Off by default even when the
  // feature is enabled server-wide — opt in per clip.
  const [aiClipEnhanced, setAiClipEnhanced] = useState(false)
  const [aiClipLoading, setAiClipLoading] = useState(false)
  const [aiClipError, setAiClipError] = useState(null)
  // Rumble removal at the clip level — didn't exist at all before this,
  // reported directly as "rumble removal doesn't seem to do anything,"
  // which for anyone checking via an individual clip rather than the
  // full-recording player was literally true: there was nothing here to
  // toggle. Independent of clipEnhanced, same reasoning as the full-
  // recording player keeps Rumble removed separate from Enhanced.
  // Mirrors rumbleRemovalMode's three states there too: shown+defaults
  // on for "auto" (Enabled (on)), shown+defaults off for "auto_off"
  // (Enabled (off) — reported directly: the point of this state is a
  // visible toggle people can turn on themselves, without it being
  // applied automatically), hidden entirely for "disabled".
  const [clipRumbleRemoved, setClipRumbleRemoved] = useState(!isBatDetection && rumbleRemovalMode === 'auto')
  // The mode arrives with Settings, which can land after this card
  // mounts; follow it until the listener flips the toggle themselves.
  const clipRumbleTouched = useRef(false)
  useEffect(() => {
    if (!clipRumbleTouched.current) setClipRumbleRemoved(!isBatDetection && rumbleRemovalMode === 'auto')
  }, [rumbleRemovalMode, isBatDetection])
  const clipRef = useRef(null)
  const color = speciesColor(detections, det.common_name, colorPalette)
  const conf = det.confidence || 0

  return (
    <div className="px-3 py-2 flex flex-wrap items-center gap-x-3 gap-y-2" style={{ borderLeft: `3px solid ${color}` }}>
      {/* Two groups that wrap onto two lines on a phone: what was heard
          (time, confidence, source), then what you can do with it. */}
      <div className="flex items-center gap-3 flex-1 min-w-[220px]">
      <span className="text-xs font-mono flex-shrink-0" style={{ color: 'var(--text-tertiary)', minWidth: 80 }}>
        {(det.start_time || 0).toFixed(1)}s–{(det.end_time || 0).toFixed(1)}s
      </span>

      {/* Compact inline confidence bar — the species identity (photo, name,
          scientific name) is already shown once in the group's own header
          row above; repeating it per-detection here was the actual source
          of visual repetition reported, not a styling issue. */}
      <div className="flex-1 min-w-0 flex items-center gap-2">
        <div className="flex-1 rounded-full overflow-hidden" style={{ height: 4, background: '#1f2937' }}>
          <div className="h-full rounded-full" style={{ width: `${conf * 100}%`, background: color }}/>
        </div>
        <span className={`badge text-xs flex-shrink-0 ${confBadgeClass(conf)}`}>
          {(conf * 100).toFixed(0)}%
        </span>
      </div>

      {det.source === 'server'
        ? <span title="Re-analyzed server-side"
                className="text-xs bg-blue-900/30 text-blue-400 border border-blue-700/40 px-1.5 py-0.5 rounded flex-shrink-0 hidden sm:inline-flex items-center gap-1"><Server size={11}/> Server</span>
        : <span title="Detected on-device"
                className="text-xs bg-surface-700 border border-surface-600 px-1.5 py-0.5 rounded flex-shrink-0 hidden sm:inline-flex items-center gap-1"
                style={{ color: 'var(--text-tertiary)' }}><Cpu size={11}/> Device</span>
      }
      {/* Source icon only on mobile — label hidden to save space */}
      {det.source === 'server'
        ? <span title="Re-analyzed server-side" className="flex-shrink-0 sm:hidden" style={{ color: '#60a5fa' }}><Server size={12}/></span>
        : <span title="Detected on-device" className="flex-shrink-0 sm:hidden" style={{ color: 'var(--text-tertiary)' }}><Cpu size={12}/></span>
      }
      </div>

      <div className="flex items-center gap-3 flex-shrink-0 ml-auto">
      <button onClick={() => onPlayAt && onPlayAt(det.start_time || 0)}
              className="text-xs flex items-center gap-0.5 hover:opacity-80 transition-opacity flex-shrink-0"
              style={{ color }}>
        <Play size={10}/> Jump
      </button>
      <button onClick={() => {
        if (!clipRef.current || (aiClipEnhanced && aiClipLoading)) return
        if (clipPlaying) { clipRef.current.pause(); setClipPlaying(false) }
        else { clipRef.current.play().catch(() => {}); setClipPlaying(true) }
      }} disabled={aiClipEnhanced && aiClipLoading}
         className="text-xs text-cyan-500 hover:text-cyan-400 flex items-center gap-0.5 transition-colors flex-shrink-0 disabled:opacity-50">
        {aiClipEnhanced && aiClipLoading
          ? <RefreshCw size={10} className="animate-spin"/>
          : clipPlaying ? <Pause size={10}/> : <Play size={10}/>} Clip
      </button>
      {!isBatDetection && (
        <EnhanceControl compact
          mode={aiClipEnhanced ? 'ai' : clipEnhanced ? 'enhanced' : 'original'}
          onChange={m => {
            clipRumbleTouched.current = true
            setAiClipError(null)
            setAiClipEnhanced(m === 'ai')
            setClipEnhanced(m === 'enhanced')
            setClipRumbleRemoved(m === 'enhanced' && rumbleRemovalMode !== 'disabled')
            setClipPlaying(false)
          }}
          aiAvailable={aiEnhanceEnabled} aiLoading={aiClipLoading} aiError={aiClipError}/>
      )}
      </div>
      <audio ref={clipRef}
             src={
               (aiClipEnhanced && !isBatDetection) ? api.recordings.clipAiEnhancedUrl(recordingId, det.id)
               : (clipEnhanced && clipRumbleRemoved && !isBatDetection) ? api.recordings.clipCleanUrl(recordingId, det.id)
               : (clipEnhanced || isBatDetection) ? api.recordings.clipEnhancedUrl(recordingId, det.id)
               : api.recordings.clipUrl(recordingId, det.id)
             }
             onLoadStart={() => { if (aiClipEnhanced) setAiClipLoading(true) }}
             onCanPlay={() => { if (aiClipEnhanced) setAiClipLoading(false) }}
             onError={() => {
               if (aiClipEnhanced) { setAiClipLoading(false); setAiClipError('AI Enhance unavailable') }
               setClipPlaying(false)
             }}
             onEnded={() => setClipPlaying(false)}
             preload="none"/>
    </div>
  )
}

// ── Edit modal ────────────────────────────────────────────────────────────────
function EditModal({ recording, onSave, onClose }) {
  const [label, setLabel] = useState(recording.label || '')
  const [notes, setNotes] = useState(recording.notes || '')
  const { timezone } = useTz()
  const initialWhen = toLocalInput(recording.trigger_timestamp, timezone)
  const [when, setWhen] = useState(initialWhen)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const whenChanged = when && when !== initialWhen
  const save = async () => {
    setSaving(true); setError(null)
    try {
      const body = { label: label || null, notes: notes || null }
      if (whenChanged) {
        const iso = fromLocalInput(when, timezone)
        if (!iso) throw new Error('Unreadable date and time')
        body.recorded_at = iso
      }
      const u = await api.recordings.edit(recording.id, body)
      onSave(u, { timeChanged: !!whenChanged })
    } catch (e) { setError(e.message || String(e)) }
    setSaving(false)
  }
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70"
         onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="bg-surface-800 border border-surface-600 rounded-2xl w-full max-w-md">
        <div className="flex items-center justify-between p-5 border-b border-surface-700">
          <h2 className="font-semibold text-white flex items-center gap-2">
            <Pencil size={15} className="text-chirp-500"/> Edit Recording
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-200"><X size={18}/></button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-sm text-gray-300 mb-1">Label</label>
            <input className="input" value={label} onChange={e => setLabel(e.target.value)}
                   onKeyDown={e => e.key === 'Enter' && save()} placeholder="Custom label…"/>
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">Recorded</label>
            <input type="datetime-local" step={1} className="input" value={when}
                   onChange={e => setWhen(e.target.value)}/>
            <p className="text-xs text-gray-500 mt-1">
              {timezone || 'This device\'s time zone'}.
              {whenChanged && ' BirdNET\'s species list depends on the date: re-analyze after saving.'}
            </p>
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">Notes</label>
            <textarea className="input resize-none" rows={3} value={notes}
                      onChange={e => setNotes(e.target.value)} placeholder="Notes…"/>
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 p-5 pt-0">
          <button onClick={onClose} className="btn-secondary">Cancel</button>
          <button onClick={save} disabled={saving} className="btn-primary flex items-center gap-2">
            {saving ? <RefreshCw size={13} className="animate-spin"/> : <Save size={13}/>}
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>,
    document.body
  )
}

// ── Delete modal ──────────────────────────────────────────────────────────────
function DeleteModal({ recording, onDeleted, onClose }) {
  const [deleteFiles, setDeleteFiles] = useState(true)
  const [hardDelete, setHardDelete] = useState(true)
  const [deleting, setDeleting] = useState(false)
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
         onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="bg-surface-700 border border-surface-500 rounded-2xl w-full max-w-sm shadow-xl animate-scale-in">
        <div className="page-root">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-full bg-red-900/40 border border-red-700/40 flex items-center justify-center flex-shrink-0">
              <Trash2 size={15} className="text-red-400"/>
            </div>
            <div>
              <h2 className="font-semibold text-[15px]" style={{ color: 'var(--text-primary)' }}>Delete Recording?</h2>
              <p className="text-xs text-gray-400 mt-0.5 truncate max-w-[220px]">
                {recording.label || recording.top_species || recording.filename}
              </p>
            </div>
          </div>

          <div className="space-y-3 mb-5">
            <label className="flex items-start gap-3 cursor-pointer group">
              <input type="checkbox" checked={deleteFiles} onChange={e => setDeleteFiles(e.target.checked)}
                     className="toggle mt-0.5"/>
              <div>
                <p className="text-sm font-medium text-gray-200">Delete audio file from disk</p>
                <p className="text-xs text-gray-500">Removes the WAV/FLAC/Opus file permanently</p>
              </div>
            </label>
            <label className="flex items-start gap-3 cursor-pointer group">
              <input type="checkbox" checked={hardDelete} onChange={e => setHardDelete(e.target.checked)}
                     className="toggle mt-0.5"/>
              <div>
                <p className="text-sm font-medium text-gray-200">Remove from database</p>
                <p className="text-xs text-gray-500">Permanently removes all detections and metadata. Uncheck to soft-delete (hides from counts but keeps data)</p>
              </div>
            </label>
          </div>

          <div className="flex gap-2 justify-end">
            <button onClick={onClose} className="btn-secondary">Cancel</button>
            <button disabled={deleting}
                    onClick={async () => {
                      setDeleting(true)
                      try {
                        await api.recordings.delete(recording.id, { deleteFiles, hardDelete })
                        onDeleted()
                      } catch (e) { alert('Delete failed: ' + e.message); setDeleting(false) }
                    }}
                    className="inline-flex items-center gap-2 px-4 py-2 bg-red-700 hover:bg-red-600 active:bg-red-800 text-white text-sm font-medium rounded-lg transition-colors">
              {deleting ? <RefreshCw size={13} className="animate-spin"/> : <Trash2 size={13}/>}
              {deleting ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}

// ── Share modal ───────────────────────────────────────────────────────────────
function ShareModal({ recording, onClose }) {
  const [shareUrl, setShareUrl] = useState(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    api.recordings.share(recording.id)
      .then(d => setShareUrl(window.location.origin + d.url))
  }, [recording.id])
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70"
         onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="bg-surface-800 border border-surface-600 rounded-2xl w-full max-w-md">
        <div className="flex items-center justify-between p-5 border-b border-surface-700">
          <h2 className="font-semibold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
            <Share2 size={15} className="text-chirp-500"/> Share Recording
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-200"><X size={18}/></button>
        </div>
        <div className="p-5">
          <p className="text-sm text-gray-400 mb-3">Anyone with this link can view without logging in.</p>
          {shareUrl
            ? <div className="flex gap-2">
                <input className="input flex-1 font-mono text-xs" readOnly value={shareUrl}/>
                <button className="btn-primary flex items-center gap-1.5 flex-shrink-0"
                        onClick={async () => {
                          await navigator.clipboard.writeText(shareUrl)
                          hapticEvent('success')
                          setCopied(true); setTimeout(() => setCopied(false), 2000)
                        }}>
                  {copied ? <><Check size={13}/> Copied</> : <><Copy size={13}/> Copy</>}
                </button>
              </div>
            : <div className="h-10 bg-surface-700 animate-pulse rounded"/>}
        </div>
      </div>
    </div>,
    document.body
  )
}

// ── Collapsible detection legend ─────────────────────────────────────────────
function CollapsibleLegend({ detections, isBat, colorPalette }) {
  const [open, setOpen] = useState(false)
  const unique = []
  const seen = new Set()
  for (const det of detections) {
    if (!seen.has(det.common_name)) { seen.add(det.common_name); unique.push(det) }
  }
  return (
    <div className="card overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-700/40 transition-colors text-left">
        <span className="text-xs font-medium text-gray-400 flex items-center gap-2">
          {isBat ? <BatIcon size={12} className="text-chirp-500"/> : <BirdIcon size={12} className="text-chirp-500"/>}
          {unique.length} species detected
          <span className="flex gap-1.5 ml-1">
            {unique.slice(0, 6).map((det) => (
              <span key={det.id} className="w-2 h-2 rounded-full inline-block"
                    style={{ background: speciesColor(detections, det.common_name, colorPalette) }}/>
            ))}
            {unique.length > 6 && <span className="text-gray-600 text-xs">+{unique.length - 6}</span>}
          </span>
        </span>
        {open ? <ChevronUp size={13} className="text-gray-500"/> : <ChevronDown size={13} className="text-gray-500"/>}
      </button>
      {open && (
        <div className="px-4 pb-3 pt-1 flex flex-wrap gap-2 border-t border-surface-700">
          {detections.map((det) => (
            <div key={det.id} className="flex items-center gap-1.5 px-2 py-1 rounded-full text-xs bg-surface-700 border border-surface-600">
              <div className="w-2 h-2 rounded-full" style={{ background: speciesColor(detections, det.common_name, colorPalette) }}/>
              <span className="text-gray-300">{det.common_name}</span>
              <span className="text-gray-500">{(det.start_time || 0).toFixed(1)}s</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Recording location map ────────────────────────────────────────────────────
function RecordingMap({ lat, lon }) {
  const mapRef = useRef(null)
  const mapInstanceRef = useRef(null)

  useEffect(() => {
    if (!lat || !lon || mapInstanceRef.current) return
    if (!document.getElementById('leaflet-css')) {
      const link = document.createElement('link')
      link.id = 'leaflet-css'; link.rel = 'stylesheet'
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
      document.head.appendChild(link)
    }
    const init = () => {
      if (!mapRef.current || mapInstanceRef.current) return
      const L = window.L
      const map = L.map(mapRef.current, { center: [lat, lon], zoom: 11, scrollWheelZoom: false })
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        { attribution: '© OpenStreetMap © CARTO', maxZoom: 19 }).addTo(map)
      const icon = L.divIcon({
        className: '',
        html: `<div style="width:14px;height:14px;background:#22c55e;border:3px solid #fff;border-radius:50%;box-shadow:0 2px 6px rgba(0,0,0,.5)"></div>`,
        iconSize: [14,14], iconAnchor: [7,7]
      })
      L.marker([lat,lon], { icon }).addTo(map)
        .bindPopup(`<b>Recording location</b><br>${lat.toFixed(5)}, ${lon.toFixed(5)}`)
      mapInstanceRef.current = map
    }
    if (window.L) { init() } else {
      const s = document.createElement('script')
      s.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
      s.onload = init; document.body.appendChild(s)
    }
    return () => { if (mapInstanceRef.current) { mapInstanceRef.current.remove(); mapInstanceRef.current = null } }
  }, [lat, lon])

  if (!lat || !lon) return null
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-surface-700 flex items-center gap-2">
        <MapPin size={14} className="text-chirp-500"/>
        <span className="text-sm font-medium text-gray-300">Recording Location</span>
        <span className="text-xs text-gray-500 ml-auto">{lat.toFixed(5)}, {lon.toFixed(5)}</span>
      </div>
      <div ref={mapRef} style={{ height: 220 }}/>
    </div>
  )
}

// ── BirdNET analysis settings display ────────────────────────────────────────
function BirdnetMetadata({ recording, onReanalyze, reanalyzing = false }) {
  const [settings, setSettings] = useState(null)
  const [showDeleted, setShowDeleted] = useState(false)
  const [useAiEnhance, setUseAiEnhance] = useState(false)

  useEffect(() => {
    api.settings.get().then(d => { if (d) setSettings(d) }).catch(() => {})
  }, [])

  // Spins until the parent's poll sees the pass finish, like the top button.
  const handleReanalyze = () => { onReanalyze?.(useAiEnhance === true) }

  const rows = settings ? [
    ['Min. Confidence', settings.birdnet_min_confidence != null ? `${(settings.birdnet_min_confidence * 100).toFixed(0)}%` : '—'],
    ['Overlap',         settings.birdnet_overlap != null ? `${settings.birdnet_overlap.toFixed(1)}s` : '—'],
    ['Sensitivity',     settings.birdnet_sensitivity != null ? settings.birdnet_sensitivity.toFixed(2) : '—'],
    ['Location filter', (settings.latitude && settings.longitude) ? `${Number(settings.latitude).toFixed(2)}, ${Number(settings.longitude).toFixed(2)}` : 'None'],
    ['Week filter',     settings.birdnet_week != null ? `Week ${settings.birdnet_week}` : 'Auto'],
  ] : []

  // Sub-threshold detections for debug view
  // Stored rows under the display threshold (the server leaves them out of
  // detections, so filtering that list could never find any).
  const hiddenDets = recording?.hidden_detections || []
  const displayMin = recording?.display_min_confidence ?? 0

  // AI-Enhanced re-analysis: only offered when the feature is actually on
  // and the recording is a real candidate for it — bats never go through
  // AI Enhance at all (the backend rejects it too, this just avoids
  // showing an option that would only ever error). Requested directly,
  // after measuring on a real noisy recording that AI Enhance's neural
  // denoising can raise in-band SNR from ~4dB to ~13dB — a gap BirdNET
  // never actually saw, since every prior use of Enhanced/AI Enhance was
  // playback-only and never touched what got analyzed or scored.
  const canUseAiEnhance = !!settings?.ai_enhance_enabled && !recording?.is_bat

  // Rough, not rigorously validated against a large dataset — calibrated
  // against exactly two real example recordings (one that needed AI
  // Enhance badly, one that didn't). Good enough to nudge someone toward
  // a checkbox that's already right there, not precise enough to hide
  // the checkbox entirely for recordings that fall on the wrong side of
  // this cutoff by a small margin.
  const LOW_SNR_THRESHOLD_DB = 6
  const isLowSnr = recording?.snr_db != null && recording.snr_db < LOW_SNR_THRESHOLD_DB

  // Default the checkbox on for a flagged-low recording — the whole
  // point of surfacing this signal is to make the helpful choice the
  // easy one, not just visible.
  useEffect(() => {
    if (isLowSnr && canUseAiEnhance) setUseAiEnhance(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recording?.id])

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text-tertiary)', letterSpacing: '.06em' }}>
          BirdNET Analysis
        </p>
        {settings?.allow_manual_reanalyze !== false && (
          <button onClick={handleReanalyze} disabled={reanalyzing}
            className="btn-secondary" style={{ padding: '4px 10px', fontSize: 11 }}>
            <RefreshCw size={11} className={reanalyzing ? 'animate-spin' : ''}/>
            {reanalyzing ? 'Running…' : 'Re-analyze'}
          </button>
        )}
      </div>
      {['opus', 'ogg', 'mp3', 'm4a', 'aac'].includes((recording.audio_format || '').toLowerCase()) && (
        <p className="text-xs px-3 py-2 rounded-lg" style={{ background: 'var(--bg-raised)', color: 'var(--text-tertiary)' }}>
          Stored compressed ({recording.audio_format.toUpperCase()}), so the original audio is gone. Re-analysis
          reads the compressed copy and its scores can differ by a few points from the first analysis;
          Chirp keeps earlier server detections that come back close.
        </p>
      )}
      {isLowSnr && (
        <p className="text-xs px-3 py-2 rounded-lg" style={{ background: 'var(--bg-raised)', color: 'var(--pastel-yellow, #eab308)' }}>
          This recording measures noisier than most ({recording.snr_db}dB) — AI-Enhanced re-analysis below may recover a detection the original missed or scored low.
        </p>
      )}
      {canUseAiEnhance && settings?.allow_manual_reanalyze !== false && (
        <label className="flex items-center gap-2 cursor-pointer w-fit">
          <input type="checkbox" className="toggle" checked={useAiEnhance}
                 onChange={e => setUseAiEnhance(e.target.checked)}/>
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            Use AI-Enhanced audio for this re-analysis — can rescue detections a noisy original scored low or missed
          </span>
        </label>
      )}
      {rows.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {rows.map(([k, v]) => (
            <div key={k} className="rounded-lg px-3 py-2" style={{ background: 'var(--bg-raised)' }}>
              <p className="text-xs mb-0.5" style={{ color: 'var(--text-tertiary)' }}>{k}</p>
              <p className="text-sm font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{v}</p>
            </div>
          ))}
        </div>
      )}
      {recording?.deleted_at && (
        <div className="rounded-lg px-3 py-2 text-xs" style={{ background: 'rgba(239,68,68,.08)', border: '1px solid rgba(239,68,68,.2)', color: 'var(--pastel-red)' }}>
          ⚠ Soft-deleted — hidden from counts and list views.
        </div>
      )}
      <label className="flex items-center gap-2 cursor-pointer text-sm" style={{ color: 'var(--text-secondary)' }}>
        <input type="checkbox" checked={showDeleted} onChange={e => setShowDeleted(e.target.checked)} className="toggle"/>
        Show sub-threshold detections (debug)
      </label>
      {showDeleted && (
        <div className="rounded-xl p-3" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          {hiddenDets.length === 0 ? (
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>No sub-threshold detections.</p>
          ) : (
            <>
              <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
                {hiddenDets.length} detection{hiddenDets.length !== 1 ? 's' : ''} below the {Math.round(displayMin * 100)}% display threshold:
              </p>
              <div className="space-y-1">
                {hiddenDets.slice(0, 30).map(d => (
                  <div key={d.id} className="flex items-center justify-between text-xs" style={{ color: 'var(--text-secondary)' }}>
                    <span>{d.common_name}</span>
                    <span className="font-mono" style={{ color: 'var(--text-tertiary)' }}>
                      {(d.confidence * 100).toFixed(1)}% · {(d.start_time||0).toFixed(1)}s–{(d.end_time||0).toFixed(1)}s
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
function SpectrogramImage({ recordingId, isBat = false, enhanced = false, aiEnhanced = false, rumbleRemoved = false, allowManualReanalyze = true, refreshKey = 0 }) {
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const imgRef = useRef(null)
  // Include conf threshold in URL so browser cache is invalidated when settings change,
  // and refreshKey so it's also invalidated after a reanalyze actually changes the image
  // (see reanalyzeVersion above — recordingId and confKey alone don't change on reanalysis).
  const confKey = Math.round((parseFloat(localStorage.getItem('chirp_min_conf') || '0')) * 100)
  // Enhanced/AI Enhanced/Rumble removed each use their own sibling
  // endpoint (mirrors /audio vs /audio/enhanced vs /audio/ai-enhanced vs
  // /audio/rumble-removed) rather than a query param on the same route —
  // first request per recording runs the actual processing +
  // regenerates the image, cached permanently after that, like every
  // other spectrogram variant. Reported directly: toggling Rumble
  // removed changed the audio but the spectrogram stayed the original —
  // the same gap Enhanced and AI Enhanced already had fixed for their
  // own toggles, just never extended to this one.
  // aiEnhanced checked first: same "AI Enhance takes priority over the
  // classical toggles" rule the audio player's effectiveSrc uses.
  // rumbleRemoved+enhanced both on uses the combined endpoint, matching
  // the audio player's own combinable rumble+enhanced behavior.
  const src = aiEnhanced && !isBat
    ? `/api/v1/recordings/${recordingId}/spectrogram/ai-enhanced?v=${refreshKey}`
    : (rumbleRemoved && enhanced && !isBat)
    ? `/api/v1/recordings/${recordingId}/spectrogram/rumble-removed-enhanced?v=${refreshKey}`
    : rumbleRemoved && !isBat
    ? `/api/v1/recordings/${recordingId}/spectrogram/rumble-removed?v=${refreshKey}`
    : enhanced && !isBat
    ? `/api/v1/recordings/${recordingId}/spectrogram/enhanced?v=${refreshKey}`
    : `/api/v1/recordings/${recordingId}/spectrogram?c=${confKey}&v=${refreshKey}`
  // Bat spectrograms use a plain linear-frequency STFT (see
  // generate_bat_spectrogram()'s docstring for why mel scale is the wrong
  // tool for ultrasonic content) — "Mel spectrogram" would be an inaccurate
  // label for that image.
  const altText = isBat ? 'Echolocation spectrogram'
    : aiEnhanced ? 'AI-enhanced mel spectrogram'
    : rumbleRemoved ? 'Rumble-removed mel spectrogram'
    : enhanced ? 'Enhanced mel spectrogram'
    : 'Mel spectrogram'

  // Reset to the loading state whenever the source actually changes —
  // otherwise toggling Enhanced would keep showing the previous image
  // (now stale/wrong) until the new one happens to finish loading, with
  // no visual indication a switch is even in progress.
  useEffect(() => {
    setLoaded(false)
    setError(false)
  }, [src])

  useEffect(() => {
    const img = imgRef.current
    if (img && img.complete && img.naturalWidth > 0) setLoaded(true)
  }, [src])

  // Close on Escape key
  useEffect(() => {
    if (!expanded) return
    const handler = (e) => { if (e.key === 'Escape') setExpanded(false) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [expanded])

  return (
    <>
      <div
        className="bg-surface-900 relative rounded-lg overflow-hidden"
        style={{ minHeight: loaded ? 'auto' : 112, cursor: loaded ? 'zoom-in' : 'default' }}
        onClick={() => loaded && setExpanded(true)}
        title={loaded ? 'Click to expand' : undefined}
      >
        {!loaded && !error && (
          <div className="absolute inset-0 flex items-center justify-center text-chirp-600 text-sm animate-pulse">
            {aiEnhanced ? 'Generating AI-enhanced spectrogram…' : rumbleRemoved ? 'Generating rumble-removed spectrogram…' : enhanced ? 'Generating enhanced spectrogram…' : 'Generating spectrogram…'}
          </div>
        )}
        {!error && (
          <img
            ref={imgRef}
            src={src}
            alt={altText}
            className="w-full block rounded-lg"
            style={{ opacity: loaded ? 1 : 0, transition: 'opacity 0.2s' }}
            onLoad={() => setLoaded(true)}
            onError={() => setError(true)}
          />
        )}
        {loaded && (
          <div className="absolute bottom-2 right-2 bg-black/60 rounded px-2 py-1 text-xs text-white/60 flex items-center gap-1 pointer-events-none">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
            </svg>
            Expand
          </div>
        )}
        {error && (
          <div className="h-28 flex items-center justify-center text-gray-600 text-xs">
            {allowManualReanalyze ? 'Spectrogram unavailable · Re-analyze to regenerate' : 'Spectrogram unavailable'}
          </div>
        )}
      </div>

      {expanded && createPortal(
        <div
          className="spectrogram-modal-backdrop"
          onClick={() => setExpanded(false)}
        >
          <img
            src={src}
            alt={`${altText} (expanded)`}
            className="spectrogram-modal-img"
            onClick={e => e.stopPropagation()}
          />
          <button
            onClick={() => setExpanded(false)}
            className="absolute top-4 right-4 w-9 h-9 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M18 6 6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>,
        document.body
      )}
    </>
  )
}

// ── Species-grouped detections ───────────────────────────────────────────────
function SpeciesClassificationDetail({ guess, actualCommonName }) {
  if (!guess) return null
  const { model, model_trained_on, top_species, top_non_species, all_species, all_non_species, num_windows } = guess
  // If the actual detection's common_name matches the classifier's own top
  // pick (and isn't just the generic "Bat" placeholder), that's proof this
  // specific result cleared the confidence threshold and got asserted —
  // simpler and more robust than fetching the threshold value separately
  // just to redo that comparison here.
  const wasConfident = top_species && actualCommonName === top_species.common_name && actualCommonName !== 'Bat'

  return (
    <div className="p-4 space-y-3" style={{ background: 'var(--bg-raised)', borderTop: '1px solid var(--border-subtle)' }}>
      <div className="flex items-center gap-2 flex-wrap">
        <Sparkles size={14} style={{ color: '#a78bfa' }}/>
        <span className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
          Species Classification Detail
        </span>
        <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          ({num_windows} window{num_windows !== 1 ? 's' : ''} analyzed)
        </span>
      </div>

      {wasConfident ? (
        <p className="text-xs flex items-center gap-1.5" style={{ color: 'var(--pastel-green)' }}>
          <CheckCircle size={12}/> Confidently identified as {top_species.common_name} ({(top_species.confidence * 100).toFixed(1)}%)
          — this is what's shown as the detection's species above.
        </p>
      ) : (
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          No confident match — the candidates below are informational only, not asserted as an
          identification anywhere (this recording stays labeled generic "Bat").
        </p>
      )}

      {all_species && all_species.length > 0 && (
        <div>
          <p className="text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>Top species candidates</p>
          <div className="space-y-1">
            {all_species.slice(0, 5).map(sp => (
              <div key={sp.label} className="flex items-center gap-2">
                <span className="text-xs flex-shrink-0 truncate italic" style={{ color: 'var(--text-tertiary)', width: 130 }} title={sp.scientific_name}>
                  {sp.common_name}
                </span>
                <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bg-panel)' }}>
                  <div className="h-full rounded-full" style={{ width: `${Math.max(1, sp.confidence * 100)}%`, background: '#a78bfa' }}/>
                </div>
                <span className="text-xs font-mono flex-shrink-0" style={{ color: 'var(--text-tertiary)', width: 44, textAlign: 'right' }}>
                  {(sp.confidence * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {all_non_species && all_non_species.length > 0 && (
        <div>
          <p className="text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>
            Non-species classes <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>(noise, cricket, silence, etc.)</span>
          </p>
          <div className="space-y-1">
            {all_non_species.slice(0, 3).map(ns => (
              <div key={ns.label} className="flex items-center gap-2">
                <span className="text-xs flex-shrink-0 truncate" style={{ color: 'var(--text-tertiary)', width: 130 }}>
                  {ns.label}
                </span>
                <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bg-panel)' }}>
                  <div className="h-full rounded-full" style={{ width: `${Math.max(1, ns.confidence * 100)}%`, background: 'var(--text-tertiary)' }}/>
                </div>
                <span className="text-xs font-mono flex-shrink-0" style={{ color: 'var(--text-tertiary)', width: 44, textAlign: 'right' }}>
                  {(ns.confidence * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-xs" style={{ color: 'var(--text-tertiary)', opacity: 0.7 }}>
        Model: {model} (trained on {model_trained_on}) — real, tested accuracy limits apply.
        See Settings → Bat Detection → Identify bat species for detail.
      </p>
    </div>
  )
}

function SpeciesGroups({ detections, recordingId, seekRef, duration, batMetadata, isBat, colorPalette, aiEnhanceEnabled = false, rumbleRemovalMode = 'auto' }) {
  // Group detections by common_name, preserving species order of first appearance
  const grouped = useMemo(() => {
    const map = new Map()
    for (const det of detections) {
      const name = det.common_name || 'Unknown'
      if (!map.has(name)) map.set(name, [])
      map.get(name).push(det)
    }
    return [...map.entries()]  // [[name, [dets]], ...]
  }, [detections])

  const [expanded, setExpanded] = useState(new Set())  // all collapsed by default

  const toggle = (name) => setExpanded(prev => {
    const next = new Set(prev)
    next.has(name) ? next.delete(name) : next.add(name)
    return next
  })

  // Real per-species mini-waveform: one shared fetch of the recording's
  // actual amplitude data (not re-fetched per species card — every group's
  // mini-waveform is a slice of this same array), so each species' header
  // row shows what that species' detection actually sounded like instead
  // of a decorative shape. Falls back to the same stable placeholder
  // AudioPlayer already uses while loading, for visual consistency rather
  // than an empty gap.
  const MINI_BARS = 28
  const [waveform, setWaveform] = useState(null)
  useEffect(() => {
    if (!recordingId) return
    api.recordings.waveform(recordingId, MINI_BARS)
      .then(d => { if (Array.isArray(d.waveform)) setWaveform(d.waveform) })
      .catch(() => {})
  }, [recordingId])

  const placeholderBars = Array.from({ length: 6 }, (_, i) =>
    20 + Math.abs(Math.sin(i * 0.7) * 50 + Math.sin(i * 0.3) * 30))

  const miniWaveformFor = (dets) => {
    if (!waveform || !duration) return placeholderBars
    const raw = waveform.map(([mn, mx]) => Math.abs(mx - mn))
    const peak = Math.max(...raw, 0.001)
    // Union of this species' own detection time ranges only — a species
    // detected twice in a 30s clip (e.g. 0–3s and 19–22s) should show
    // bars from BOTH windows, not just its first occurrence.
    const ranges = dets.map(d => [d.start_time || 0, d.end_time || 0])
    const barDuration = duration / MINI_BARS
    const inAnyRange = (barStart, barEnd) => ranges.some(([s, e]) => barStart < e && barEnd > s)
    const picked = raw
      .map((v, i) => ({ v, i, barStart: i * barDuration, barEnd: (i + 1) * barDuration }))
      .filter(({ barStart, barEnd }) => inAnyRange(barStart, barEnd))
    const slice = picked.length > 0 ? picked.map(p => p.v) : raw.slice(0, 6)
    // Down-sample a long slice to 6 evenly-spaced bars, or pad a short one
    // back up to 6 by cycling its own values — a 3-second detection within
    // a 30-second recording (the common case) only has 2-3 raw bars
    // falling inside its window, and without padding every species card
    // would show a different, visually inconsistent bar count/density.
    let sampled
    if (slice.length >= 6) {
      const step = Math.max(1, Math.floor(slice.length / 6))
      sampled = slice.filter((_, i) => i % step === 0).slice(0, 6)
    } else {
      sampled = Array.from({ length: 6 }, (_, i) => slice[i % slice.length])
    }
    return sampled.map(v => Math.max(15, Math.round((v / peak) * 100)))
  }

  return (
    <div className="space-y-2">
      {grouped.map(([name, dets]) => {
        const color = speciesColor(detections, name, colorPalette)
        const maxConf = Math.max(...dets.map(d => d.confidence || 0))
        const isOpen = expanded.has(name)
        const bird = dets[0]
        const photoUrl = bird.bird_photo_url || bird.photo_url || null
        const profileId = bird.bird_profile_id || null
        const isBatSpecies = isBat
        const miniBars = miniWaveformFor(dets)
        return (
          <div key={name} className="card overflow-hidden" style={{ borderLeft: `3px solid ${color}` }}>
            {/* Species header row — click to expand */}
            <button
              className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-surface-700/30 transition-colors text-left"
              onClick={() => toggle(name)}>
              {photoUrl ? (
                <img src={photoUrl} alt={name}
                     className="w-10 h-10 rounded-lg object-cover flex-shrink-0"
                     style={{ boxShadow: `0 0 0 2px ${color}40` }}/>
              ) : (
                <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                     style={{ background: `${color}18`, border: `1px solid ${color}30` }}>
                  {isBatSpecies
                    ? <BatIcon size={16} style={{ color }}/>
                    : <BirdIcon size={16} style={{ color }}/>}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-100 truncate">{name}</p>
                <p className="text-xs text-gray-500">{dets.length} detection{dets.length !== 1 ? 's' : ''}</p>
              </div>
              {/* Mini-waveform */}
              <div className="hidden sm:flex items-end gap-px flex-shrink-0" style={{ height: 16, width: 32 }}>
                {miniBars.map((h, i) => (
                  <div key={i} className="flex-1 rounded-sm" style={{ height: `${h}%`, background: color, opacity: 0.55 + (h / 100) * 0.45 }}/>
                ))}
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className={`badge text-xs ${confBadgeClass(maxConf)}`}>
                  {Math.round(maxConf * 100)}% {confLabel(maxConf)}
                </span>
                {/* Profile link — stopPropagation so it doesn't toggle the accordion.
                    Bat detections don't reliably carry a bird_profile_id (no real
                    per-species taxonomy entry for the "Bat" pseudo-species), so this
                    falls back to the name-based profile lookup route for bats instead
                    of requiring profileId — same fallback Life List/Dashboard use. */}
                {(profileId || isBatSpecies) && (
                  <Link
                    to={profileId ? `/library/${profileId}` : `/library?name=${encodeURIComponent(name)}`}
                    onClick={e => e.stopPropagation()}
                    className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg transition-colors"
                    style={{
                      background: `${color}14`,
                      color: color,
                      border: `1px solid ${color}30`,
                    }}
                    title={`View ${name} profile`}>
                    {isBatSpecies ? <BatIcon size={11}/> : <BirdIcon size={11}/>} Profile
                  </Link>
                )}
                <svg className={`w-4 h-4 text-gray-500 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                     fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7"/>
                </svg>
              </div>
            </button>
            {/* Expanded: individual detection cards */}
            {isOpen && (
              <div className="border-t border-surface-700 divide-y divide-surface-700 bg-surface-800">
                {dets.map(det => (
                  <DetectionCard
                    key={det.id}
                    det={det}
                    recordingId={recordingId}
                    detections={detections}
                    onPlayAt={t => seekRef.current && seekRef.current(t)}
                    colorPalette={colorPalette}
                    aiEnhanceEnabled={aiEnhanceEnabled}
                    rumbleRemovalMode={rumbleRemovalMode}
                  />
                ))}
                {batMetadata?.species_guess && (
                  <SpeciesClassificationDetail guess={batMetadata.species_guess} actualCommonName={name}/>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}


export default function RecordingDetail({ shared = false }) {
  const { id, token } = useParams()
  const navigate = useNavigate()
  const [recording, setRecording] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showEdit, setShowEdit] = useState(false)
  const [showDelete, setShowDelete] = useState(false)
  const [showShare, setShowShare] = useState(false)
  const [reanalyzing, setReanalyzing] = useState(false)
  // Reported directly: an admin needs to be able to hide the Re-analyze
  // button (Settings > Server-Side Analysis). Defaults true so the
  // button stays visible before this loads or if the setting is
  // unset — matching the setting's own server-side default.
  const [allowManualReanalyze, setAllowManualReanalyze] = useState(true)
  const [colorPalette, setColorPalette] = useState(DEFAULT_PALETTE)
  // null until Settings loads, so a recording that loads first doesn't
  // get the "auto" rumble default when the setting is Auto Off.
  const [rumbleRemovalMode, setRumbleRemovalMode] = useState(null)
  const [settingsLoaded, setSettingsLoaded] = useState(false)
  // Ref mirror of rumbleRemovalMode, read by the recording-load effect
  // below for the same reason aiEnhanceAutoApplyRef exists — that
  // effect's deps are [id, token, shared], so a closure over the state
  // value directly could read a stale 'auto' if this settings fetch
  // resolves after the closure was created.
  const rumbleRemovalModeRef = useRef(null)
  const [aiEnhanceEnabled, setAiEnhanceEnabled] = useState(false)
  const [aiEnhanceAutoApply, setAiEnhanceAutoApply] = useState(false)
  // Ref mirror of aiEnhanceAutoApply, read by the recording-load effect
  // below — that effect's own deps are [id, token, shared] (unchanged
  // since before this feature), so it can't just close over the state
  // value directly without either adding it as a dep (re-running the
  // whole fetch on every settings change, not wanted) or reading a ref
  // that's always current.
  const aiEnhanceAutoApplyRef = useRef(false)
  const [shadowOn, setShadowOn] = useState(false)   // Experimental: BirdNET v3 comparison
  useEffect(() => {
    api.settings.get().then(d => {
      if (d && d.allow_manual_reanalyze === false) setAllowManualReanalyze(false)
      if (d && d.detection_color_palette) setColorPalette(d.detection_color_palette)
      if (d) setAiEnhanceEnabled(!!d.ai_enhance_enabled)
      if (d) setShadowOn(!!d.exp_birdnet3_shadow && d.detection_model === 'birdnet24')
      if (d) { setAiEnhanceAutoApply(!!d.ai_enhance_auto_apply); aiEnhanceAutoApplyRef.current = !!d.ai_enhance_auto_apply }
      const mode = (d && d.rumble_removal_mode) || 'auto'
      setRumbleRemovalMode(mode); rumbleRemovalModeRef.current = mode
    }).catch(() => { setRumbleRemovalMode('auto'); rumbleRemovalModeRef.current = 'auto' })
      .finally(() => setSettingsLoaded(true))
  }, [])
  const [aiRechecking, setAiRechecking] = useState(false)
  const [postingInatComment, setPostingInatComment] = useState(false)
  const [inatCommentResult, setInatCommentResult] = useState(null)
  const [currentUser, setCurrentUser] = useState('Anonymous')
  const [userRole,    setUserRole]    = useState('viewer')
  const canChange = userRole !== 'viewer'
  // Lifted out of AudioPlayer (which used to own this internally) so
  // SpectrogramImage can react to the same toggle — clicking "Enhanced"
  // now swaps both the audio source AND the spectrogram image together,
  // rather than only the audio while the spectrogram silently stayed on
  // the original regardless of which playback mode was selected.
  const [enhanced, setEnhanced] = useState(false)
  // Lifted the same way `enhanced` is, for the same reason — see
  // SpectrogramImage's own aiEnhanced prop. Defaults from
  // aiEnhanceAutoApply once the recording loads (mirroring how
  // rumbleRemovalMode's default is read at AudioPlayer's own mount),
  // set in the settings-fetch effect below.
  const [aiEnhanced, setAiEnhanced] = useState(false)
  // Lifted the same way `enhanced`/`aiEnhanced` are, for the same
  // reason — see SpectrogramImage's own rumbleRemoved prop. Starts
  // false and gets set once the recording loads (in the fetch effect
  // below), mirroring the bat-default-Enhanced pattern — needs to know
  // is_bat first, which isn't available until then. Unlike
  // aiEnhanceAutoApply, rumbleRemovalMode's own default ('auto') is
  // already a safe assumption even before its settings fetch
  // resolves, so this doesn't need a ref-based workaround for the
  // same timing issue.
  const [rumbleRemoved, setRumbleRemoved] = useState(false)
  // One Enhance control for birds (EnhanceControl): Original, Enhanced
  // (low cut + noise reduction) or AI.
  const setEnhanceMode = m => {
    setAiEnhanced(m === 'ai')
    setEnhanced(m === 'enhanced')
    setRumbleRemoved(m === 'enhanced' && rumbleRemovalModeRef.current !== 'disabled')
  }
  // Bumped after every reanalyze completes — see SpectrogramImage's
  // refreshKey prop below for why.
  const [reanalyzeVersion, setReanalyzeVersion] = useState(0)

  useEffect(() => {
    try {
      const token = localStorage.getItem('chirp_token')
      if (token) {
        fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${token}` } })
          .then(r => r.ok ? r.json() : null)
          .then(u => { if (u?.username) { setCurrentUser(u.username); setUserRole(u.role || 'viewer') } })
          .catch(() => {})
      } else {
        // When auth is off, treat as admin
        setUserRole('admin')
      }
    } catch {}
  }, [])
  const { fmtDateFull, fmtAgo } = useTz()
  const seekRef = useRef(null)

  useEffect(() => {
    const promise = shared ? api.recordings.getShared(token) : api.recordings.get(id)
    promise
      .then(data => {
        setRecording(data)
        setLoading(false)
        // Reported directly: bat recordings didn't default to Enhanced —
        // same underlying issue as the per-detection clip fix (bat
        // "Original" audio is the raw ultrasonic recording, genuinely
        // inaudible to a human listener), just missed here since this is
        // a separate toggle for the whole-recording player rather than a
        // per-clip one. Only sets it on initial load, not on every
        // recording refetch (e.g. after reanalyze) — doesn't fight a
        // listener who deliberately switched back to Original.
        if (data?.is_bat) setEnhanced(true)
      })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [id, token, shared])

  // Playback defaults that depend on Settings: applied once per
  // recording, only after BOTH the recording and Settings have loaded
  // (either can arrive first).
  const defaultsAppliedFor = useRef(null)
  useEffect(() => {
    if (!recording || !settingsLoaded || defaultsAppliedFor.current === recording.id) return
    defaultsAppliedFor.current = recording.id
    if (recording.is_bat) return
    if (aiEnhanceAutoApplyRef.current) setEnhanceMode('ai')
    else if (rumbleRemovalModeRef.current === 'auto') setEnhanceMode('enhanced')
  }, [recording, settingsLoaded])

  const [archiving, setArchiving] = useState(false)
  const toggleArchive = async () => {
    if (archiving) return
    const isArchived = !!recording?.archived_at
    if (!isArchived) {
      const ok = window.confirm(
        'Archive this recording? This deletes the audio file permanently to save space — ' +
        'the recording stays in your list with its spectrogram, detections, and notes intact, ' +
        'and still counts toward all statistics. This cannot be undone.'
      )
      if (!ok) return
    }
    setArchiving(true)
    try {
      const updated = isArchived
        ? await api.recordings.unarchive(id)
        : await api.recordings.archive(id)
      // Both endpoints return a status object, not the full updated
      // recording — re-fetch so has_audio/archived_at and everything
      // else reflects the real new state rather than guessing at a
      // partial local update.
      const fresh = await api.recordings.get(id)
      setRecording(fresh)
    } catch (e) {
      alert(`${isArchived ? 'Unarchive' : 'Archive'} failed: ${e.message || e}`)
    }
    setArchiving(false)
  }

  const reanalyze = async (useAiEnhance = false) => {
    // Strict: an onClick handler passes its event here, which is truthy.
    useAiEnhance = useAiEnhance === true
    if (reanalyzing) return
    setReanalyzing(true)
    try {
      await api.recordings.reanalyze(id, { useAiEnhance })
      waitForProcessing()
    } catch {
      setReanalyzing(false)
    }
  }

  const [downloadingAudio, setDownloadingAudio] = useState(false)
  const downloadAudio = async () => {
    const ext = recording?.audio_format || 'wav'
    const stem = (recording?.filename || recording?.id || 'recording').replace(/\.[^.]+$/, '')
    setDownloadingAudio(true)
    try {
      await saveUrl(api.recordings.audioUrl(recording.id), { filename: `${stem}.${ext}` })
    } catch (e) {
      alert('Download failed: ' + (e.message || e))
    }
    setDownloadingAudio(false)
  }

  // Poll until a re-analysis (or an Undo's redraw) finishes, then refresh.
  const waitForProcessing = () => {
    setReanalyzing(true)
    let attempts = 0
    const poll = setInterval(async () => {
      attempts++
      try {
        const u = await api.recordings.get(id)
        if (u.processing_status === 'done' || u.processing_status === 'error' || attempts > 40) {
          clearInterval(poll)
          setRecording(u)
          // Reported directly: after a reanalyze that changed the
          // detections, the spectrogram kept showing the old image —
          // its <img src> is built from recordingId + a confidence
          // threshold from localStorage, neither of which changes just
          // because the backend regenerated a genuinely different
          // image (detection overlays are baked directly into it).
          // Bumping this forces a real new URL, and therefore a real
          // re-fetch, exactly when the image actually changed.
          setReanalyzeVersion(v => v + 1)
          setReanalyzing(false)
        }
      } catch { clearInterval(poll); setReanalyzing(false) }
    }, 2000)
  }

  // AI Second Opinion runs in the background on the server (a local model
  // can take minutes); poll until the note is newer or an error is stored.
  const [aiRecheckError, setAiRecheckError] = useState(null)
  const [aiElapsed, setAiElapsed] = useState(0)
  const aiPollRef = useRef(null)
  useEffect(() => () => clearInterval(aiPollRef.current), [])
  const watchAiRecheck = (previous) => {
    const started = Date.now()
    setAiRechecking(true); setAiElapsed(0)
    clearInterval(aiPollRef.current)
    aiPollRef.current = setInterval(async () => {
      const secs = Math.round((Date.now() - started) / 1000)
      setAiElapsed(secs)
      try {
        const u = await api.recordings.get(id)
        const newer = u.ai_reanalysis_generated_at && u.ai_reanalysis_generated_at !== previous
        if (newer || u.ai_reanalysis_error || (!u.ai_reanalysis_running && secs > 15)) {
          clearInterval(aiPollRef.current)
          setRecording(u)
          setAiRecheckError(u.ai_reanalysis_error || (newer ? null : 'The AI Second Opinion stopped without an answer. Try again.'))
          setAiRechecking(false)
        }
      } catch { /* network blip: keep polling */ }
      if (secs > 600) {
        clearInterval(aiPollRef.current)
        setAiRecheckError('No answer after 10 minutes. The AI provider may be down or overloaded.')
        setAiRechecking(false)
      }
    }, 3000)
  }
  // With a local AI model, start loading it while the page is read, at most
  // every 10 minutes (the server keeps it loaded for 30).
  useEffect(() => {
    if (!recording?.ai_reanalysis_enabled) return
    const now = Date.now()
    if (now - (window.__chirpAiWarmAt || 0) < 600000) return
    window.__chirpAiWarmAt = now
    api.recordings.aiWarm().catch(() => {})
  }, [recording?.ai_reanalysis_enabled])
  // Pick up a second opinion still running after the page is reopened.
  useEffect(() => {
    if (recording?.ai_reanalysis_running && !aiRechecking) watchAiRecheck(recording.ai_reanalysis_generated_at)
  }, [recording?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const aiRecheck = async () => {
    if (aiRechecking) return
    setAiRecheckError(null)
    try {
      const r = await api.recordings.aiRecheck(id)
      watchAiRecheck(r?.previous_generated_at ?? recording?.ai_reanalysis_generated_at ?? null)
    } catch (e) {
      setAiRecheckError(e?.message || 'Could not start the AI Second Opinion.')
    }
  }

  const postSecondOpinionAsComment = async () => {
    if (postingInatComment) return
    setPostingInatComment(true)
    setInatCommentResult(null)
    try {
      await api.recordings.postInatComment(id, 'second_opinion')
      setInatCommentResult({ ok: true, message: 'Posted to iNaturalist.' })
    } catch (e) {
      setInatCommentResult({ ok: false, message: e?.message || 'Failed to post comment.' })
    }
    setPostingInatComment(false)
    setTimeout(() => setInatCommentResult(null), 5000)
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-chirp-500 animate-pulse">
      Loading recording…
    </div>
  )
  if (error) return (
    <div className="p-6 flex items-center gap-2 text-red-400">
      <AlertCircle size={16}/> {error}
    </div>
  )
  if (!recording) return (
    <div className="p-6 text-gray-400">Recording not found.</div>
  )

  const ts = recording.trigger_timestamp || ''
  const parsedTs = ts ? new Date(ts.endsWith('Z') ? ts : ts + 'Z') : new Date()
  const displayName = recording.label || recording.top_species || recording.filename || 'Recording'
  const detections = [...(recording.detections || [])].sort((a, b) => (a.start_time || 0) - (b.start_time || 0))

  // Derive iNat URL from notes for recordings submitted before dedicated columns were added
  const inatUrl = recording.inat_observation_url || (() => {
    const m = (recording.notes || '').match(/https:\/\/www\.inaturalist\.org\/observations\/\d+/)
    return m ? m[0] : null
  })()
  const inatId = recording.inat_observation_id || (() => {
    const m = (recording.notes || '').match(/inaturalist\.org\/observations\/(\d+)/)
    return m ? m[1] : null
  })()

  const topDetection = detections.length > 0
    ? [...detections].sort((a, b) => (b.confidence || 0) - (a.confidence || 0))[0]
    : null
  const heroPhoto = recording.top_species_photo_url
  const uniqueSpeciesCount = new Set(detections.map(d => d.common_name)).size

  return (
    <div className="p-6 space-y-5 max-w-6xl">
      {/* Poster hero — same crop-safe blurred-backdrop + fully-contained-photo
          treatment already proven this session for the BirdProfile hero and
          the Dashboard Summary card, so the top species' photo is never
          cropped regardless of its own aspect ratio or composition. */}
      <div className="card overflow-hidden animate-fade-in">
        <div className="relative" style={{ height: 'clamp(380px, 48vw, 460px)' }}>
          <div className="absolute inset-0 overflow-hidden">
            {heroPhoto ? (
              <>
                <img src={heroPhoto} alt="" aria-hidden="true"
                     className="absolute inset-0 w-full h-full object-cover"
                     style={{ filter: 'blur(28px) brightness(0.5) saturate(1.1)', transform: 'scale(1.15)' }}/>
                <div className="absolute inset-0 flex items-center justify-center">
                  <img src={heroPhoto} alt={displayName}
                       className="max-w-full max-h-full w-auto h-auto object-contain"
                       style={{ boxShadow: '0 10px 36px rgba(0,0,0,.4)' }}/>
                </div>
              </>
            ) : (
              <div className="absolute inset-0 flex items-center justify-center" style={{ background: 'linear-gradient(135deg, var(--bg-raised), var(--bg-card))' }}>
                {recording.is_bat
                  ? <BatIcon size={90} style={{ color: 'var(--text-tertiary)' }}/>
                  : <BirdIcon size={90} style={{ color: 'var(--text-tertiary)' }}/>}
              </div>
            )}
          </div>
          <div className="absolute inset-0" style={{ background: 'linear-gradient(to top, rgba(0,0,0,.9), rgba(0,0,0,.15) 55%, transparent)' }}/>

          {!shared && (
            <button onClick={() => navigate(-1)} className="absolute top-3 left-3 flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg transition-colors hover:opacity-80"
                  style={{ background: 'rgba(0,0,0,.4)', color: '#f5f5f4', border: 'none', cursor: 'pointer' }}>
              <ArrowLeft size={13}/> Back
            </button>
          )}
          {recording.archived_at && (
            <span title="Audio file deleted to save space — everything else is preserved"
                  className="absolute top-3 right-3 flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium"
                  style={{ background: 'rgba(0,0,0,.4)', color: '#f5f5f4' }}>
              <Archive size={10}/> Archived
            </span>
          )}

          <div className="absolute bottom-0 left-0 right-0 p-4">
            <h1 className="text-2xl font-bold" style={{ color: '#fff', fontFamily: "'Lora', serif", textShadow: '0 2px 10px rgba(0,0,0,.6)' }}>
              {displayName}
            </h1>
            {topDetection?.scientific_name && (
              <p className="text-sm italic" style={{ color: 'rgba(255,255,255,.7)', textShadow: '0 1px 6px rgba(0,0,0,.6)' }}>
                {topDetection.scientific_name}
              </p>
            )}
            <div className="flex items-center gap-3 mt-1.5 flex-wrap">
              <span className="text-xs" style={{ color: 'rgba(255,255,255,.75)' }}>{fmtDateFull(recording.trigger_timestamp)}</span>
              {recording.notes && (() => {
                const cleaned = (recording.notes || '').split('\n').filter(line => !line.includes('inaturalist.org')).join('\n').trim()
                return cleaned ? <span className="text-xs italic" style={{ color: 'rgba(255,255,255,.6)' }}>{cleaned}</span> : null
              })()}
            </div>
          </div>
        </div>

        {/* Real stat strip — actual recording data, not decorative */}
        <div className="grid grid-cols-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          {[
            [topDetection ? `${Math.round((topDetection.confidence || 0) * 100)}%` : '—', 'Top Confidence'],
            [detections.length.toString(), 'Detections'],
            [uniqueSpeciesCount.toString(), 'Species'],
            [recording.duration_seconds != null ? `${Math.floor(recording.duration_seconds)}s` : '—', 'Duration'],
          ].map(([v, l], i) => (
            <div key={l} className="p-3 text-center" style={{ borderRight: i < 3 ? '1px solid var(--border-subtle)' : undefined }}>
              <p className="text-lg font-bold" style={{ color: 'var(--accent-400)', fontFamily: "'Lora', serif" }}>{v}</p>
              <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--text-tertiary)' }}>{l}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Action buttons — kept as their own row below the hero rather than
          overlaid on the photo: this page has 6+ real actions (iNat submit,
          On iNat link, Share, Edit, Re-analyze, Archive/Unarchive, Delete),
          which would visibly overcrowd a photo-overlay pill row. */}
      {!shared && (
        <div className="flex items-center gap-2 flex-wrap animate-fade-in">
          <InatSubmitButton
            recordingId={id}
            detectionId={recording?.detections?.[0]?.id}
            speciesName={recording?.detections?.[0]?.common_name}
            canSubmit={userRole === 'admin' || userRole === 'submitter'}
            hasAudio={recording?.has_audio !== false}
            hasEnhanced={!recording?.is_bat}
            secondOpinionNote={recording?.ai_reanalysis_enabled ? recording?.ai_reanalysis_note : null}
            currentUser={currentUser}
            onSuccess={() => api.recordings.get(id).then(data => setRecording(data)).catch(() => {})}
          />
          {inatUrl && (
            <a
              href={inatUrl}
              target="_blank"
              rel="noopener noreferrer"
              title={`View iNaturalist observation #${inatId}`}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium"
              style={{ background: 'rgba(74,222,128,0.12)', color: '#4ade80', border: '1px solid rgba(74,222,128,0.3)' }}
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              On iNat
            </a>
          )}
          <button onClick={() => setShowShare(true)} className="btn-secondary flex items-center gap-1.5">
            <Share2 size={13}/> Share
          </button>
          {canChange && (
            <button
              onClick={() => api.recordings.patch(id, { is_saved: !recording?.is_saved })
                .then(r => { setRecording(r); clearApiCache?.() }).catch(e => alert(e.message))}
              title={recording?.is_saved ? 'Saved: kept out of automatic cleanup. Tap to unsave.' : 'Keep this recording out of automatic cleanup'}
              className="btn-secondary flex items-center gap-1.5"
              style={recording?.is_saved ? { color: '#facc15', borderColor: 'rgba(250,204,21,.4)' } : undefined}>
              {recording?.is_saved ? <BookmarkCheck size={13}/> : <Bookmark size={13}/>} {recording?.is_saved ? 'Saved' : 'Save'}
            </button>
          )}
          {/* View-only accounts: the server refuses these (main.py), so don't offer them. */}
          {canChange && (
          <button onClick={() => setShowEdit(true)} className="btn-secondary flex items-center gap-1.5">
            <Pencil size={13}/> Edit
          </button>
          )}
          {canChange && allowManualReanalyze && (
            recording?.has_audio === false ? (
              <div title="No audio file — this recording has been archived"
                   className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium cursor-not-allowed select-none"
                   style={{ background: 'var(--bg-raised)', color: 'var(--text-tertiary)', opacity: 0.55 }}>
                <RefreshCw size={13}/> Re-analyze
              </div>
            ) : (
              <button onClick={() => reanalyze(false)} disabled={reanalyzing}
                      className="btn-secondary flex items-center gap-1.5">
                <RefreshCw size={13} className={reanalyzing ? 'animate-spin' : ''}/>
                {reanalyzing ? 'Analyzing…' : 'Re-analyze'}
              </button>
            )
          )}
          {canChange && recording?.ai_reanalysis_enabled && (
            <button onClick={aiRecheck} disabled={aiRechecking}
                    title="Ask an AI vision model to look at the spectrogram directly and give a second opinion on the identification(s) already made — a sanity check, not a replacement for BirdNET/the pulse detector"
                    className="btn-secondary flex items-center gap-1.5">
              <Sparkles size={13} className={aiRechecking ? 'animate-pulse' : ''}/>
              {aiRechecking ? `Asking AI…${aiElapsed >= 10 ? ` ${aiElapsed}s` : ''}` : 'AI Second Opinion'}
            </button>
          )}
          {aiRecheckError && !aiRechecking && (
            <span className="text-xs flex items-center gap-1 basis-full order-last" style={{ color: 'var(--pastel-red, #f87171)' }}>
              <AlertCircle size={12}/> AI Second Opinion failed: {aiRecheckError}
            </span>
          )}
          {!canChange ? null : recording?.archived_at ? (
            <button onClick={toggleArchive} disabled={archiving}
                    title="Archive status can be cleared, but the deleted audio file cannot be restored"
                    className="btn-secondary flex items-center gap-1.5">
              <ArchiveRestore size={13}/> {archiving ? 'Working…' : 'Unarchive'}
            </button>
          ) : (
            <button onClick={toggleArchive} disabled={archiving || recording?.has_audio === false}
                    title="Delete the audio file to save space — keeps the spectrogram, detections, and statistics intact"
                    className="btn-secondary flex items-center gap-1.5">
              <Archive size={13}/> {archiving ? 'Archiving…' : 'Archive'}
            </button>
          )}
          {canChange && (
          <button onClick={() => setShowDelete(true)}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium border border-red-800/60 text-red-400 hover:bg-red-900/20 transition-colors">
            <Trash2 size={13}/> Delete
          </button>
          )}
        </div>
      )}

      {!shared && recording && !recording.is_bat && (
        <ReanalysisHistory recordingId={recording.id} refreshKey={reanalyzeVersion}
                           busy={reanalyzing} onUndone={waitForProcessing}/>
      )}

      {!shared && shadowOn && recording && !recording.is_bat && (
        <ShadowComparison recordingId={recording.id} refreshKey={reanalyzeVersion}/>
      )}

      {/* AI second-opinion result — only shown once there's something to show */}
      {recording?.ai_reanalysis_enabled && recording?.ai_reanalysis_note && (
        <div className="card p-4 animate-fade-in" style={{ animationDelay: '80ms' }}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Sparkles size={14} style={{ color: 'var(--accent-400)' }}/>
              <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>AI second opinion</span>
            </div>
            {inatId && (
              <button onClick={postSecondOpinionAsComment} disabled={postingInatComment}
                      title="Post this AI second opinion as a comment on the iNaturalist observation, clearly labeled as AI-generated"
                      className="text-xs hover:text-accent transition-colors flex items-center gap-1 flex-shrink-0"
                      style={{ color: 'var(--text-tertiary)' }}>
                <MessageSquare size={11} className={postingInatComment ? 'animate-pulse' : ''}/>
                {postingInatComment ? 'Posting…' : 'Post to iNaturalist'}
              </button>
            )}
          </div>
          {/* Rendered as markdown now, not plain text — the backend prompt
              (see call_reanalysis.py) asks the model to bold each species
              name and end with an "Overall:" consensus line, which needs
              markdown parsing to show as bold/a paragraph
              break rather than literal "**" characters and run-together
              text. Only p/strong are overridden — the prompt explicitly
              asks for no headers, lists, or other markdown, so nothing
              else needs styling here. */}
          <SecondOpinionBody note={recording.ai_reanalysis_note} rating={recording.ai_reanalysis_rating}/>
          {inatCommentResult && (
            <p className={`text-xs mt-2 ${inatCommentResult.ok ? 'text-green-400' : 'text-red-400'}`}>
              {inatCommentResult.message}
            </p>
          )}
        </div>
      )}

      {/* Color legend — collapsible, starts collapsed */}
      {detections.length > 0 && (
        <CollapsibleLegend detections={detections} isBat={recording.is_bat} colorPalette={colorPalette}/>
      )}

      {/* Spectrogram + Audio player — unified card for alignment */}
      <div className="card overflow-hidden animate-fade-in" style={{ animationDelay: '60ms' }}>
        <div className="px-4 py-2 border-b border-surface-700 flex items-center justify-between">
          <span className="text-sm font-medium text-gray-300">Mel Spectrogram</span>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500">Colors match detections</span>
            {recording.has_audio !== false && (
              <button type="button" onClick={downloadAudio} disabled={downloadingAudio}
                 title="Download the recording"
                 className="text-xs flex items-center gap-1 text-gray-400 hover:text-chirp-400 transition-colors">
                {downloadingAudio ? <RefreshCw size={12} className="animate-spin"/> : <Download size={12}/>}
                {(recording.audio_format || 'wav').toUpperCase()}
              </button>
            )}
          </div>
        </div>
        <div className="bg-surface-950 overflow-x-auto">
          {recording.archived_at
            ? <SpectrogramImage recordingId={recording.id} spectrogramUrl={recording.spectrogram_url} isBat={recording.is_bat} enhanced={false} allowManualReanalyze={allowManualReanalyze} refreshKey={reanalyzeVersion}/>
            : recording.has_audio !== false
              ? <SpectrogramImage recordingId={recording.id} spectrogramUrl={recording.spectrogram_url} isBat={recording.is_bat} enhanced={enhanced} aiEnhanced={aiEnhanced} rumbleRemoved={rumbleRemoved} allowManualReanalyze={allowManualReanalyze} refreshKey={reanalyzeVersion}/>
              : <div className="flex items-center justify-center h-24 text-sm" style={{ color: 'var(--text-tertiary)' }}>
                  No audio — Haikubox detections are metadata-only
                </div>
          }
        </div>
        {recording.has_audio !== false && (
          <div className="border-t border-surface-700 bg-surface-900">
            <AudioPlayer
              src={api.recordings.audioUrl(recording.id)}
              detections={detections}
              duration={recording.duration_seconds}
              recordingId={recording.id}
              seekRef={seekRef}
              enhanced={enhanced}
              onToggleEnhanced={() => setEnhanced(e => !e)}
              isBat={recording.is_bat}
              colorPalette={colorPalette}
              rumbleRemovalMode={rumbleRemovalMode}
              rumbleRemoved={rumbleRemoved}
              onToggleRumbleRemoved={() => setRumbleRemoved(r => !r)}
              aiEnhanceEnabled={aiEnhanceEnabled}
              aiEnhanced={aiEnhanced}
              onToggleAiEnhanced={() => setAiEnhanced(a => !a)}
              onSetEnhanceMode={setEnhanceMode}
            />
          </div>
        )}
      </div>

      {/* Detections */}
      <div className="animate-fade-in" style={{ animationDelay: '100ms' }}>
        <h2 className="font-semibold text-gray-200 mb-3 flex items-center gap-2">
          {recording?.is_bat ? <BatIcon size={16} className="text-chirp-500"/> : <BirdIcon size={16} className="text-chirp-500"/>} Detections ({detections.length})
        </h2>

        {/* iNaturalist submission badge — subtle, below detections header */}
        {inatUrl && (
          <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-lg"
               style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#4ade80" strokeWidth="2.5" className="flex-shrink-0"><polyline points="20 6 9 17 4 12"/></svg>
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              Submitted to iNaturalist &middot; Obs&nbsp;#{inatId}
            </span>
            <a href={inatUrl} target="_blank" rel="noopener noreferrer"
               className="text-xs ml-auto flex items-center gap-1 flex-shrink-0"
               style={{ color: '#4ade80' }}>
              View ↗
            </a>
          </div>
        )}

        {recording.processing_error && (() => {
          // Detect old-format iNat submission JSON stored in processing_error
          let inatResult = null
          let errorText = recording.processing_error
          try {
            const parsed = JSON.parse(recording.processing_error)
            if (parsed.inat_submission) {
              inatResult = parsed.inat_submission
              errorText = null  // not a real error
            }
          } catch {}

          if (inatResult) {
            // Render iNat submission as a clean card, not raw JSON
            const soundOk = inatResult.sound_attached !== false
            return (
              <div className="mb-3 card p-4" style={{ borderColor:'rgba(34,197,94,.3)', background:'rgba(34,197,94,.06)' }}>
                <div className="flex items-start gap-3">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4ade80" strokeWidth="2" className="flex-shrink-0 mt-0.5"><polyline points="20 6 9 17 4 12"/></svg>
                  <div>
                    <p className="text-sm font-medium" style={{ color:'#4ade80' }}>Submitted to iNaturalist</p>
                    {inatResult.inat_url && (
                      <a href={inatResult.inat_url} target="_blank" rel="noopener noreferrer"
                         className="text-xs mt-1 inline-block" style={{ color:'var(--pastel-green)' }}>
                        Observation #{inatResult.inat_id} ↗
                      </a>
                    )}
                    {!soundOk && (
                      <p className="text-xs mt-1" style={{ color:'var(--pastel-amber)' }}>
                        ⚠️ Audio attachment unavailable — observation created without sound.
                        You can <a href={inatResult.inat_url} target="_blank" rel="noopener noreferrer"
                          style={{ color:'var(--pastel-amber-light)', textDecoration:'underline' }}>add it manually</a> on iNaturalist.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )
          }

          if (!errorText) return null
          return (
            <div className="mb-3 card p-4 border-yellow-700/50 bg-yellow-900/10">
              <div className="flex items-start gap-3">
                <AlertCircle size={16} className="text-yellow-400 flex-shrink-0 mt-0.5"/>
                <div>
                  <p className="text-sm font-medium text-yellow-300">Analysis note</p>
                  <p className="text-xs text-yellow-500 mt-1">{errorText}</p>
                  {!shared && allowManualReanalyze && (
                    <button onClick={() => reanalyze(false)} disabled={reanalyzing}
                            className="mt-2 flex items-center gap-1 text-xs text-yellow-300 bg-yellow-900/40 border border-yellow-700/50 px-3 py-1 rounded transition-colors hover:text-yellow-200">
                      <RefreshCw size={11} className={reanalyzing ? 'animate-spin' : ''}/> {reanalyzing ? 'Analyzing…' : 'Re-run BirdNET'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          )
        })()}

        {detections.length === 0 && !recording.processing_error ? (
          <p className="text-sm text-gray-500">No species identified in this recording.</p>
        ) : (
          <SpeciesGroups
            detections={detections}
            recordingId={recording.id}
            seekRef={seekRef}
            duration={recording.duration_seconds}
            batMetadata={recording.bat_metadata}
            isBat={recording.is_bat}
            colorPalette={colorPalette}
            aiEnhanceEnabled={aiEnhanceEnabled}
            rumbleRemovalMode={rumbleRemovalMode}
          />
        )}
      </div>

      {/* Location map */}
      <RecordingMap lat={recording.latitude} lon={recording.longitude}/>

      {/* Metadata — collapsed by default */}
      {showEdit && (
        <EditModal recording={recording}
                   onSave={u => { setRecording(u); setShowEdit(false) }}
                   onClose={() => setShowEdit(false)}/>
      )}
      {showDelete && (
        <DeleteModal recording={recording}
                     onDeleted={() => navigate('/recordings')}
                     onClose={() => setShowDelete(false)}/>
      )}
      {showShare && (
        <ShareModal recording={recording} onClose={() => setShowShare(false)}/>
      )}

      {/* Comments — collapsible, open by default */}
      {!shared && recording && (
        <CollapsibleSection title="Notes" defaultOpen={true}>
          <Comments
            fetchFn={() => api.recordings.comments(recording.id)}
            postFn={(body, author) => api.recordings.postComment(recording.id, body, author)}
            deleteFn={(cid) => api.recordings.deleteComment(recording.id, cid)}
            updateFn={(cid, body) => api.recordings.updateComment(recording.id, cid, body)}
            currentUser={currentUser}
            placeholder="Add a note about this recording…"
            emptyText="No notes yet."
          />
        </CollapsibleSection>
      )}

      <CollapsibleSection title="Recording Details" defaultOpen={false}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs mb-4">
            {[
              ['File', recording.filename],
              ['Duration', `${(recording.duration_seconds || 0).toFixed(1)}s`],
              ['Sample Rate', `${((recording.sample_rate || 48000) / 1000).toFixed(0)} kHz`],
              ['Channels', (recording.channels || 1) === 2 ? 'Stereo' : 'Mono'],
              ['Format', (recording.audio_format || 'wav').toUpperCase()],
              ['File Size', recording.file_size_bytes
                ? recording.file_size_bytes > 1048576
                  ? `${(recording.file_size_bytes / 1048576).toFixed(1)} MB`
                  : `${(recording.file_size_bytes / 1024).toFixed(0)} KB`
                : '—'],
              ['Pre-roll', `${(recording.pre_roll_seconds || 0).toFixed(1)}s`],
              ['Energy', recording.energy_db ? `${recording.energy_db.toFixed(1)} dBFS` : '—'],
              ['Status', recording.processing_status || '—'],
              ['Device', recording.device_name || recording.device_id || `${recording.device_count || 1} mic(s)`],
              ...(recording.is_live_session ? [['Source', 'Live Detect session']] : []),
              ...(recording.deleted_at ? [['Deleted', new Date(recording.deleted_at + (recording.deleted_at.endsWith('Z') ? '' : 'Z')).toLocaleDateString()]] : []),
              ...(recording.latitude ? [['Location', `${recording.latitude.toFixed(4)}, ${recording.longitude?.toFixed(4)}`]] : []),
            ].map(([k, v]) => (
              <div key={k}>
                <p className="mb-0.5" style={{ color: 'var(--text-tertiary)' }}>{k}</p>
                <p className="font-mono break-all" style={{ color: 'var(--text-primary)' }}>{v}</p>
              </div>
            ))}
          </div>
          <BirdnetMetadata recording={recording} onReanalyze={reanalyze} reanalyzing={reanalyzing}/>
      </CollapsibleSection>
    </div>
  )
}
