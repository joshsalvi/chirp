/**
 * InatSubmitButton — submit a recording to iNaturalist as a sound observation.
 *
 * Props:
 *   recordingId   — ID of the recording
 *   detectionId   — (optional) specific detection to use; defaults to top species
 *   speciesName   — display name for the modal header
 *   canSubmit     — bool: true if role is admin or submitter
 *   hasAudio      — bool: true if the recording still has an audio file (defaults to
 *                   true for backward compatibility). False for an archived
 *                   recording (see Recording.archived_at) — iNaturalist sound
 *                   observations require audio, and the backend already
 *                   rejects this with a 400; showing the disabled state up
 *                   front here is just surfacing that earlier rather than
 *                   making someone open the modal and submit first to find out.
 */
import { useState } from 'react'
import { createPortal } from 'react-dom'
import { Send, ExternalLink, X, Leaf, AlertCircle, CheckCircle, Lock, Key, Archive } from 'lucide-react'
import { api } from '../lib/api'

const INAT_PREFS_KEY = 'chirp:inat:prefs'

// Real report: settings were being remembered, just not per-user — a
// shared browser with more than one logged-in Chirp account (submitter +
// admin sharing one machine, for example) would have each account's
// changes stomp the other's. Keyed by username when known; falls back to
// the old global key when auth is off (currentUser === 'Anonymous', same
// sentinel already used by BirdPhotoGallery/Comments elsewhere in the
// app) so a no-auth deployment keeps working exactly as before.
function keyFor(currentUser) {
  return currentUser && currentUser !== 'Anonymous'
    ? `${INAT_PREFS_KEY}:${currentUser}`
    : INAT_PREFS_KEY
}

function loadPrefs(currentUser) {
  const DEFAULTS = { includeSpectrogram: true, includeDetails: true, useEnhanced: false, includeSecondOpinion: false }
  try {
    // Per-user key first; if this user has never submitted from this
    // browser yet, fall back to reading the old global key once rather
    // than silently resetting everyone to defaults the first time this
    // shipped — inherits whatever was already saved, then starts writing
    // under the per-user key from the next change onward.
    const raw = localStorage.getItem(keyFor(currentUser)) ?? localStorage.getItem(INAT_PREFS_KEY)
    if (raw) {
      const p = JSON.parse(raw)
      return {
        includeSpectrogram:   p.includeSpectrogram   ?? DEFAULTS.includeSpectrogram,
        includeDetails:       p.includeDetails       ?? DEFAULTS.includeDetails,
        useEnhanced:          p.useEnhanced          ?? DEFAULTS.useEnhanced,
        includeSecondOpinion: p.includeSecondOpinion ?? DEFAULTS.includeSecondOpinion,
      }
    }
  } catch {}
  return DEFAULTS
}

function savePrefs(currentUser, prefs) {
  try { localStorage.setItem(keyFor(currentUser), JSON.stringify(prefs)) } catch {}
}

export default function InatSubmitButton({ recordingId, detectionId, speciesName, canSubmit, hasAudio = true, hasEnhanced = true, secondOpinionNote = null, currentUser = 'Anonymous', onSuccess }) {
  const [open,       setOpen]       = useState(false)
  const [notes,      setNotes]      = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result,     setResult]     = useState(null)  // { inat_url, inat_id }
  const [error,      setError]      = useState(null)

  // Settings — initialized from localStorage, saved on every change.
  // Loaded lazily at mount with whatever `currentUser` prop is available
  // then (often still 'Anonymous' this early — the parent's own
  // /api/v1/auth/me fetch is async and hasn't resolved yet at first
  // render). That's fine for the initial values; handleOpen() below
  // re-loads with the by-then-resolved currentUser right when the modal
  // actually opens, which is what matters for correctness.
  const [useEnhanced,          setUseEnhancedRaw]          = useState(() => loadPrefs(currentUser).useEnhanced)
  const [includeSpectrogram,   setIncludeSpectrogramRaw]   = useState(() => loadPrefs(currentUser).includeSpectrogram)
  const [includeDetails,       setIncludeDetailsRaw]       = useState(() => loadPrefs(currentUser).includeDetails)
  const [includeSecondOpinion, setIncludeSecondOpinionRaw] = useState(() => loadPrefs(currentUser).includeSecondOpinion)

  const setUseEnhanced = v => {
    setUseEnhancedRaw(v)
    savePrefs(currentUser, { includeSpectrogram, includeDetails, useEnhanced: v, includeSecondOpinion })
  }
  const setIncludeSpectrogram = v => {
    setIncludeSpectrogramRaw(v)
    savePrefs(currentUser, { includeSpectrogram: v, includeDetails, useEnhanced, includeSecondOpinion })
  }
  const setIncludeDetails = v => {
    setIncludeDetailsRaw(v)
    savePrefs(currentUser, { includeSpectrogram, includeDetails: v, useEnhanced, includeSecondOpinion })
  }
  const setIncludeSecondOpinion = v => {
    setIncludeSecondOpinionRaw(v)
    savePrefs(currentUser, { includeSpectrogram, includeDetails, useEnhanced, includeSecondOpinion: v })
  }

  const handleOpen = () => {
    if (!canSubmit) return
    // Re-load right now, not just at mount — currentUser has very likely
    // resolved from 'Anonymous' to a real username by the time someone
    // actually clicks the button, and per-recording-detail-page remounts
    // shouldn't require a full page refresh to pick up the right user's
    // saved settings.
    const p = loadPrefs(currentUser)
    setUseEnhancedRaw(p.useEnhanced)
    setIncludeSpectrogramRaw(p.includeSpectrogram)
    setIncludeDetailsRaw(p.includeDetails)
    setIncludeSecondOpinionRaw(p.includeSecondOpinion)
    setOpen(true)
    setResult(null)
    setError(null)
    setNotes('')
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const res = await api.recordings.submitToInat(recordingId, detectionId, notes, {
        useEnhancedAudio: useEnhanced,
        includeSpectrogram,
        includeDetails,
        includeSecondOpinion: includeSecondOpinion && !!secondOpinionNote,
      })
      setResult(res)
      if (onSuccess) onSuccess(res)
    } catch (e) {
      const msg = (e.message || '').trim()
      const lower = msg.toLowerCase()
      // Known NON-auth failure modes — these have a specific, actionable cause
      // unrelated to the token, so show the plain message rather than the
      // profile link.
      const isStructural = lower.includes('not found') || lower.includes('no detections')
        || lower.includes('403') || lower.includes('requires admin or submitter role')
        || lower.includes('date observed') || lower.includes('in the future')
      // Everything else (including empty/unexpected messages, network errors,
      // or raw 502s from a proxy) is treated as a likely token problem by
      // default — iNaturalist tokens expire every 24h and that's overwhelmingly
      // the most common failure here, so defaulting to the actionable link is
      // more useful than a wall of red text the user can't act on.
      setError(isStructural ? (msg || 'Submission failed.') : 'AUTH_ERROR:' + (msg || 'Submission failed — your iNaturalist token may need to be refreshed.'))
    } finally {
      setSubmitting(false)
    }
  }

  // Archived recordings have no audio left to submit — show this before
  // the role check below, since "no audio" is the more fundamental
  // blocker regardless of who's looking at it.
  if (!hasAudio) {
    return (
      <div title="This recording has been archived — its audio file was deleted, so it can't be submitted." className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg cursor-not-allowed select-none"
           style={{ background: 'var(--bg-raised)', color: 'var(--text-tertiary)', border: '1px solid var(--border-subtle)', opacity: 0.55 }}>
        <Archive size={11}/>
        Submit to iNaturalist
      </div>
    )
  }

  // Grayed-out button for viewers
  if (!canSubmit) {
    return (
      <div title="Requires admin or submitter role" className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg cursor-not-allowed select-none"
           style={{ background: 'var(--bg-raised)', color: 'var(--text-tertiary)', border: '1px solid var(--border-subtle)', opacity: 0.55 }}>
        <Lock size={11}/>
        Submit to iNaturalist
      </div>
    )
  }

  return (
    <>
      {/* Trigger button */}
      <button onClick={handleOpen}
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-all hover:opacity-90"
              style={{ background: 'rgb(var(--accent-500-rgb) / .12)', color: 'var(--accent-600)', border: '1px solid rgb(var(--accent-500-rgb) / .25)' }}>
        <Leaf size={11}/>
        Submit to iNaturalist
      </button>

      {/* Modal — rendered via a portal directly into document.body, not
          inline in the component tree. Same root cause already confirmed
          and fixed once this session for the dashboard's "Seen Today"
          popup: WebKit/Chrome/Safari have a documented cross-browser quirk
          where a position:fixed element can be clipped/repositioned by any
          ancestor with position:relative + z-index, even with zero
          transform anywhere in the chain — contradicting the CSS spec's
          stated behavior that fixed positioning escapes ancestor stacking
          entirely. A portal sidesteps the whole class of problem: this
          modal is no longer a descendant of any page wrapper, so no
          ancestor combination on whatever page it's opened from can affect
          it. */}
      {open && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
             style={{ background: 'rgba(0,0,0,.6)', backdropFilter: 'blur(4px)' }}
             onClick={e => { if (e.target === e.currentTarget) setOpen(false) }}>
          <div className="w-full max-w-md rounded-2xl p-6 space-y-4 shadow-2xl"
               style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)' }}>

            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                     style={{ background: 'rgb(var(--accent-500-rgb) / .15)', border: '1px solid rgb(var(--accent-500-rgb) / .3)' }}>
                  <Leaf size={15} style={{ color: 'var(--accent-600)' }}/>
                </div>
                <div>
                  <h2 className="font-display font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                    Submit to iNaturalist
                  </h2>
                  {speciesName && (
                    <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{speciesName}</p>
                  )}
                </div>
              </div>
              <button onClick={() => setOpen(false)} style={{ color: 'var(--text-tertiary)' }}>
                <X size={16}/>
              </button>
            </div>

            {/* Success state */}
            {result ? (
              <div className="space-y-4">
                <div className="flex items-start gap-3 p-4 rounded-xl"
                     style={{ background: 'rgb(var(--accent-500-rgb) / .08)', border: '1px solid rgb(var(--accent-500-rgb) / .2)' }}>
                  <CheckCircle size={18} style={{ color: 'var(--accent-600)', flexShrink: 0, marginTop: 1 }}/>
                  <div>
                    <p className="text-sm font-semibold" style={{ color: 'var(--accent-600)' }}>Submitted successfully!</p>
                    <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                      Observation #{result.inat_id} created on iNaturalist.
                    </p>
                  </div>
                </div>
                <a href={result.inat_url} target="_blank" rel="noreferrer"
                   className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-semibold transition-opacity hover:opacity-80"
                   style={{ background: 'rgb(var(--accent-500-rgb) / .15)', color: 'var(--accent-600)', border: '1px solid rgb(var(--accent-500-rgb) / .3)' }}>
                  <ExternalLink size={13}/>
                  View on iNaturalist
                </a>
                <button onClick={() => setOpen(false)} className="btn-ghost w-full text-sm">
                  Close
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Info */}
                <div className="text-xs p-3 rounded-xl space-y-1"
                     style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
                  <p>This will create a <strong style={{ color: 'var(--text-primary)' }}>Sound observation</strong> on iNaturalist with the recording attached (and the spectrogram as a second photo, if selected below).</p>
                  <p className="mt-1">Location and timestamp are taken from the recording. The species identification will be submitted as a suggestion — iNaturalist community will confirm it.</p>
                </div>

                {/* Notes */}
                <div>
                  <label className="text-xs font-semibold uppercase tracking-widest mb-1.5 block"
                         style={{ color: 'var(--text-tertiary)' }}>
                    Notes (optional)
                  </label>
                  <textarea className="input w-full resize-none text-sm" rows={3}
                            placeholder="Additional observations, habitat notes, equipment used…"
                            value={notes} onChange={e => setNotes(e.target.value)}/>
                </div>

                {/* Submission options */}
                <div className="space-y-2.5">
                  <label className="text-xs font-semibold uppercase tracking-widest block"
                         style={{ color: 'var(--text-tertiary)' }}>
                    Options
                  </label>

                  <label className="flex items-start gap-3 cursor-pointer group">
                    <input type="checkbox" checked={includeDetails} onChange={e => setIncludeDetails(e.target.checked)}
                           className="toggle mt-0.5"/>
                    <div>
                      <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Include recording details</p>
                      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                        Adds duration, device, and every detection's species/timestamp/confidence to the description.
                      </p>
                    </div>
                  </label>

                  <label className="flex items-start gap-3 cursor-pointer group">
                    <input type="checkbox" checked={includeSpectrogram} onChange={e => setIncludeSpectrogram(e.target.checked)}
                           className="toggle mt-0.5"/>
                    <div>
                      <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Attach spectrogram</p>
                      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                        Adds the spectrogram image (with detection boxes and confidence already labeled) as a second photo.
                      </p>
                    </div>
                  </label>

                  {secondOpinionNote && (
                    <label className="flex items-start gap-3 cursor-pointer group">
                      <input type="checkbox" checked={includeSecondOpinion} onChange={e => setIncludeSecondOpinion(e.target.checked)}
                             className="toggle mt-0.5"/>
                      <div>
                        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Include AI second opinion</p>
                        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                          Posts the AI's spectrogram sanity-check as a separate comment on the observation, clearly labeled as AI-generated — not an official identification.
                        </p>
                      </div>
                    </label>
                  )}

                  {hasEnhanced && (
                    <label className="flex items-start gap-3 cursor-pointer group">
                      <input type="checkbox" checked={useEnhanced} onChange={e => setUseEnhanced(e.target.checked)}
                             className="toggle mt-0.5"/>
                      <div>
                        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Use enhanced (noise-reduced) audio</p>
                        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                          Off submits the original recording — generally preferred for citizen-science accuracy. On submits the noise-reduced version instead.
                        </p>
                      </div>
                    </label>
                  )}
                </div>

                {/* Error */}
                {error && (() => {
                  const isAuth = error.startsWith('AUTH_ERROR:')
                  const msg = isAuth ? error.slice(11) : error
                  return (
                    <div className="flex items-start gap-2 p-3 rounded-xl text-xs"
                         style={{ background: isAuth ? 'rgba(251,191,36,0.08)' : 'rgba(248,113,113,.08)',
                                  border: isAuth ? '1px solid rgba(251,191,36,0.2)' : '1px solid rgba(248,113,113,.2)',
                                  color: isAuth ? 'var(--pastel-amber)' : 'var(--pastel-red)' }}>
                      <AlertCircle size={13} style={{ flexShrink: 0, marginTop: 1 }}/>
                      <div className="flex-1">
                        {isAuth ? (
                          <>
                            <p>Your iNaturalist token needs to be refreshed.</p>
                            <a href="/profile"
                               className="inline-flex items-center gap-1 mt-1.5 font-medium underline"
                               style={{ color: 'var(--pastel-amber-light)' }}>
                              <Key size={11}/> Update token in Account →
                            </a>
                          </>
                        ) : (
                          <span>{msg}</span>
                        )}
                      </div>
                    </div>
                  )
                })()}

                {/* Actions */}
                <div className="flex gap-2 pt-1">
                  <button onClick={() => setOpen(false)} className="btn-ghost text-sm px-4">
                    Cancel
                  </button>
                  <button onClick={handleSubmit} disabled={submitting}
                          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-sm font-semibold transition-opacity hover:opacity-90 disabled:opacity-50 whitespace-nowrap"
                          style={{ background: 'rgb(var(--accent-500-rgb) / .15)', color: 'var(--accent-600)', border: '1px solid rgb(var(--accent-500-rgb) / .3)' }}>
                    {submitting ? (
                      <><span className="animate-spin">⟳</span> Submitting…</>
                    ) : (
                      <><Send size={13}/> Submit Observation</>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>,
        document.body
      )}
    </>
  )
}
