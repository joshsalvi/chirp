// The song line: a recording's loudness as one row of bars, with the
// stretches where the bird was identified highlighted (a soft band behind
// gold bars). Tap anywhere to jump there. No per-call marks: detections are
// 3–5 s windows, so a mark placed from loudness can point at the wrong sound.
// Used by the Standard dashboard's player and Chirp Lite's now-playing bar.
// Data: GET /lite/recording/{id}/songline (services/songline.py).

const clock = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

export default function SongLine({
  line, progress = 0, onSeek, height = 34,
  accent = 'var(--accent-400)', accentSoft = 'rgb(var(--accent-500-rgb) / .42)',
  muted = 'rgba(245,240,232,.7)', mutedSoft = 'rgba(245,240,232,.2)',
}) {
  const duration = line?.duration || 0
  if (!duration) return null
  const spans = (line.segments && line.bird && line.segments[line.bird]) || []
  const inside = (t) => spans.some(([a, b]) => t >= a && t < b)
  const pos = progress * duration
  const bars = line.bars || []
  const seekAt = (e) => {
    if (!onSeek) return
    const r = e.currentTarget.getBoundingClientRect()
    onSeek(Math.max(0, Math.min(duration, ((e.clientX - r.left) / r.width) * duration)))
  }
  const where = spans.map(([a, b]) => `${clock(a)}–${clock(b)}`).join(', ')

  return (
    <div role="slider" tabIndex={0} aria-label={line.bird ? `Position; ${line.bird} at ${where}` : 'Position'}
         aria-valuemin={0} aria-valuemax={Math.round(duration)} aria-valuenow={Math.round(pos)}
         aria-valuetext={`${clock(pos)} of ${clock(duration)}`}
         onClick={seekAt}
         onKeyDown={e => {
           if (e.key === 'ArrowRight') onSeek?.(Math.min(duration, pos + 2))
           if (e.key === 'ArrowLeft') onSeek?.(Math.max(0, pos - 2))
         }}
         style={{ position: 'relative', width: '100%', height, cursor: onSeek ? 'pointer' : 'default' }}>
      {/* The bird's stretches: a soft band the full height of the line. */}
      {spans.map(([a, b]) => (
        <span key={`band-${a}`} aria-hidden="true"
              style={{ position: 'absolute', top: -3, bottom: -3, left: `${(100 * a) / duration}%`,
                       width: `${(100 * (b - a)) / duration}%`, borderRadius: 4,
                       background: accentSoft, opacity: 0.35 }}/>
      ))}
      <div style={{ position: 'relative', height: '100%', display: 'flex', alignItems: 'center', gap: 2 }}>
        {bars.length ? bars.map((v, i) => {
          const t = ((i + 0.5) * duration) / bars.length
          const played = t <= pos
          const color = inside(t) ? (played ? accent : accentSoft) : (played ? muted : mutedSoft)
          return <span key={i} style={{ flex: 1, height: Math.max(3, Math.round(v * height)), borderRadius: 1.5, background: color }}/>
        }) : (
          // No sound to measure: a plain track with the bird's stretches tinted.
          <div style={{ position: 'relative', width: '100%', height: 6, borderRadius: 3, background: mutedSoft, overflow: 'hidden' }}>
            {spans.map(([a, b]) => (
              <span key={a} style={{ position: 'absolute', top: 0, bottom: 0, left: `${(100 * a) / duration}%`, width: `${(100 * (b - a)) / duration}%`, background: accentSoft }}/>
            ))}
            <span style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: `${progress * 100}%`, background: accent }}/>
          </div>
        )}
      </div>
      {bars.length > 0 && progress > 0 && (
        <span aria-hidden="true" style={{ position: 'absolute', top: -2, bottom: -2, left: `${progress * 100}%`, width: 2, marginLeft: -1, borderRadius: 1, background: accent }}/>
      )}
    </div>
  )
}
