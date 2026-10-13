/**
 * Songbird mark: the Chirp logo (0.5.9.a).
 *
 * One continuous outline bird (closed beak with a lifted tip, cocked tail,
 * head tipped up, bright eye) with three meter bars that rise with the
 * beak's angle. ChirpLogo and every themed logo render through this, so the
 * shape stays identical and only the styling changes per theme.
 *
 * animate:
 *   false            still mark
 *   true | 'sing'    Dashboard: the beak opens for two notes with the bars,
 *                    tail flick, blink (3.2 s loop)
 *   'draw'           login/launch: the outline draws itself, then the eye
 *                    and bars appear; plays once
 *   'meter'          Live Detect while listening: bars move like a level
 *                    meter, occasional blink
 * Keyframes live in index.css (.cb-anim / .cb-draw / .cb-meter). Reduced
 * motion shows the still mark.
 *
 * Line weight adapts to rendered size unless strokeWidth is given: bold
 * where the mark is small (favicon, header), finer as it grows (hero).
 */
import { useId } from 'react'

export const MARK_VIEWBOX = '6 12 106 72'
const VB_W = 106
const VB_H = 72

// Pre-tilt geometry (the bird group is rotated -8° about 46,56).
const TIP = [80.5, 42.2]
export const PATHS = {
  tail: 'M13 49 L26.5 62',
  // Belly → tail point → back, one stroke: no overlapping caps at the joint.
  body: 'M71 49 C 69 62 56 71 42 71 C 34 71 28.5 67 26.5 62 C 28 45 40 32 55 32 C 63 32 69 36 71 42',
  beakUp: `M71 42 L${TIP[0]} ${TIP[1]}`,
  beakLo: `M${TIP[0]} ${TIP[1]} L71 49`,
  wing: 'M34 59.5 C 40.5 59.5 46.5 56.3 50.5 51',
}
// Closed silhouette (body + beak) for fills: washes, hatching, shadows.
PATHS.silhouette = `${PATHS.body} L${TIP[0]} ${TIP[1]} Z`
export const EYE = { cx: 60, cy: 41 }
const TILT = -8
// Beak tip after the tilt is ~(78.24, 37.53). Bars start 10.5 ahead of it,
// raised 3 units toward the beak's center line (0.5.10.c), and each sits a
// little higher, following the beak's angle.
export const BAR_CY = 34.5
export const BARS = [
  { x: 88.74, cy: 34.73, h: 9 },
  { x: 95.24, cy: 33.33, h: 18 },
  { x: 101.74, cy: 31.93, h: 11 },
]
export const WARM = ['#fdba74', '#fb923c', '#ea580c']

// Rendered width (px) → line weight, interpolated.
const WEIGHTS = [[24, 6.5], [36, 6.0], [56, 5.2], [96, 4.4], [180, 3.8], [420, 3.4]]
export function weightForWidth(px) {
  if (px <= WEIGHTS[0][0]) return WEIGHTS[0][1]
  for (let i = 1; i < WEIGHTS.length; i++) {
    const [x1, y1] = WEIGHTS[i - 1], [x2, y2] = WEIGHTS[i]
    if (px <= x2) return y1 + (y2 - y1) * (px - x1) / (x2 - x1)
  }
  return WEIGHTS[WEIGHTS.length - 1][1]
}

const MODE_CLASS = { sing: 'cb-anim', draw: 'cb-draw', meter: 'cb-meter' }

export default function SongbirdMark({
  size = 36,
  animate = false,
  className = '',
  style,
  title = 'Chirp',
  ink = 'currentColor',          // outline color
  wingInk,                       // defaults to ink
  beakInk,                       // defaults to ink
  eyeInk,                        // defaults to ink
  accent = WARM,                 // bar color, or an array of three
  catchlight = 'var(--bg-panel, #0a160c)',  // null to omit
  strokeWidth,                   // defaults to the size-adaptive weight
  weightScale = 1,               // themes that want a heavier/lighter adaptive line
  cap = 'round',
  join = 'round',
  barCap,                        // defaults to cap
  barWidth,                      // defaults to max(weight * 0.9, 3.2)
  eyeR,                          // defaults to max(weight * 0.56, 2.7)
  stepped = false,               // digital themes: stepped motion
  inkProps = {},                 // extra attributes on every outline stroke
  glow,                          // { blur, opacity }: blurred copy underneath
  under,                         // (ids) => nodes behind everything, untilted
  underBird,                     // (ids) => nodes behind the outline, in the tilted bird space
  overBird,                      // (ids) => nodes above the outline, in the tilted bird space
  over,                          // (ids) => nodes on top, untilted
  eye,                           // (ids) => custom eye nodes (replaces the default eye)
}) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const ids = { uid, glow: `cbglow_${uid}`, clip: `cbclip_${uid}` }
  const h = size * 0.9
  const w = h * VB_W / VB_H
  const mode = animate === true ? 'sing' : (animate || null)
  const animated = !!mode
  const cls = c => (animated ? c : undefined)
  const sw = strokeWidth ?? weightForWidth(w) * weightScale
  const stroke = { strokeWidth: sw, strokeLinecap: cap, strokeLinejoin: join, fill: 'none', pathLength: 1, ...inkProps }
  const er = eyeR ?? Math.max(sw * 0.56, 2.7)
  const bc = barCap ?? cap
  const bw = barWidth ?? Math.max(sw * 0.9, 3.2)
  const colors = Array.isArray(accent) ? accent : [accent, accent, accent]

  const bird = (key, extra = {}) => (
    <g key={key} transform={`rotate(${TILT} 46 56)`} {...extra}>
      <g className={cls('cb-bob')}>
        {key === 'main' && underBird?.(ids)}
        <path className={cls('cb-ln cb-tail')} d={PATHS.tail} stroke={ink} {...stroke}/>
        <path className={cls('cb-ln cb-body')} d={PATHS.body} stroke={ink} {...stroke}/>
        <path className={cls('cb-ln cb-up')} d={PATHS.beakUp} stroke={beakInk ?? ink} {...stroke}/>
        <path className={cls('cb-ln cb-lo')} d={PATHS.beakLo} stroke={beakInk ?? ink} {...stroke}/>
        <path className={cls('cb-ln cb-wing')} d={PATHS.wing} stroke={wingInk ?? ink} {...stroke}/>
        <g className={cls('cb-eye')}>
          {eye ? eye(ids) : (
            <>
              <circle cx={EYE.cx} cy={EYE.cy} r={er} fill={eyeInk ?? ink}/>
              {catchlight && <circle cx={EYE.cx + er * 0.36} cy={EYE.cy - er * 0.36} r={Math.max(er * 0.34, 0.9)} fill={catchlight}/>}
            </>
          )}
        </g>
        {key === 'main' && overBird?.(ids)}
      </g>
    </g>
  )

  const bars = (key, extra = {}) => (
    <g key={key} {...extra}>
      {BARS.map((b, i) => (
        <line key={i} className={cls(`cb-bar cb-bar${i}`)}
              x1={b.x} y1={b.cy - b.h / 2} x2={b.x} y2={b.cy + b.h / 2}
              stroke={colors[i]} strokeWidth={bw} strokeLinecap={bc}/>
      ))}
    </g>
  )

  return (
    <svg width={w} height={h} viewBox={MARK_VIEWBOX} xmlns="http://www.w3.org/2000/svg" role="img" aria-label={title}
         className={[mode ? MODE_CLASS[mode] : '', stepped ? 'cb-steps' : '', className].filter(Boolean).join(' ')}
         style={{ overflow: 'visible', flexShrink: 0, ...style }}>
      {glow && (
        <defs>
          <filter id={ids.glow} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation={glow.blur ?? 3}/>
          </filter>
        </defs>
      )}
      {under?.(ids)}
      {glow && (
        <g filter={`url(#${ids.glow})`} opacity={glow.opacity ?? 0.7}>
          {bird('glow')}
          {bars('glowbars')}
        </g>
      )}
      {bird('main')}
      {bars('bars')}
      {over?.(ids)}
    </svg>
  )
}
