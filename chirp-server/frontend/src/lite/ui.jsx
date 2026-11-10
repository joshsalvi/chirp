// Small shared pieces: photos with a friendly fallback, play buttons,
// loading and empty states, time words.
import { useCallback, useEffect, useState } from 'react'
import { media } from './api'
import { BirdMark, Icon } from './icons'
import { useIsPlaying, usePlayer } from './player'

// Load data for a screen; reload() refetches.
export function useLoad(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const load = useCallback(() => {
    let live = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fn().then((data) => live && setState({ data, error: null, loading: false }))
        .catch((error) => live && setState({ data: null, error, loading: false }))
    return () => { live = false }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(load, [load])
  return { ...state, reload: load }
}

const HUES = [150, 35, 200, 12, 265, 95, 330, 180]
const hueFor = (name = '') => HUES[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % HUES.length]

export function Photo({ src, name, className = '', alt }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) {
    const h = hueFor(name)
    return (
      <div className={`photo photo-empty ${className}`} style={{ background: `linear-gradient(140deg, hsl(${h} 70% 86%), hsl(${h + 25} 65% 74%))` }}>
        <BirdMark tile={false} size="46%" />
      </div>
    )
  }
  return <img className={`photo ${className}`} src={media(src)} alt={alt ?? name ?? ''} loading="lazy" onError={() => setFailed(true)} />
}

export function PlayButton({ item, size = 'md', className = '', label }) {
  const { toggle } = usePlayer()
  const { playing, progress, active } = useIsPlaying(item?.key)
  if (!item?.src) return null
  const r = 21, c = 2 * Math.PI * r
  return (
    <button type="button" className={`play play-${size} ${playing ? 'is-playing' : ''} ${className}`}
            aria-label={(playing ? 'Pause ' : 'Play ') + (label || item.title || 'sound')}
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggle(item) }}>
      {active && (
        <svg className="play-ring" viewBox="0 0 48 48" aria-hidden="true">
          <circle cx="24" cy="24" r={r} strokeDasharray={c} strokeDashoffset={c * (1 - progress)} />
        </svg>
      )}
      {playing ? <Icon.pause /> : <Icon.play />}
    </button>
  )
}

export function Loading({ rows = 4 }) {
  return (
    <div className="loading" aria-label="Loading">
      <div className="skel skel-hero" />
      <div className="tiles">{Array.from({ length: rows }, (_, i) => <div key={i} className="skel skel-tile" />)}</div>
    </div>
  )
}

export function Empty({ title, children, action }) {
  return (
    <div className="empty">
      <BirdMark size={84} />
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

export function Failed({ error, onRetry }) {
  return (
    <Empty title="Couldn’t reach your Chirp" action={<button className="btn" onClick={onRetry}>Try again</button>}>
      {error?.message === 'Failed to fetch' ? 'Check your connection.' : error?.message}
    </Empty>
  )
}

// ── Time words ───────────────────────────────────────────────────────────────
export const clock = (iso) => iso ? new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : ''

export function when(iso) {
  if (!iso) return ''
  const d = new Date(iso), now = new Date()
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diff = Math.round((day(now) - day(d)) / 86400000)
  if (diff === 0) {
    const mins = Math.round((now - d) / 60000)
    if (mins < 1) return 'Just now'
    if (mins < 60) return `${mins} min ago`
    return `Today, ${clock(iso)}`
  }
  if (diff === 1) return `Yesterday, ${clock(iso)}`
  if (diff < 7) return d.toLocaleDateString([], { weekday: 'long' }) + ', ' + clock(iso)
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' })
}

export const longDate = (iso) => iso ? new Date(iso).toLocaleDateString([], { month: 'long', day: 'numeric', year: 'numeric' }) : ''

export function greeting(d = new Date()) {
  const h = d.getHours()
  if (h < 5) return 'Good night'
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

export const plural = (n, one, many = one + 's') => `${n.toLocaleString()} ${n === 1 ? one : many}`
