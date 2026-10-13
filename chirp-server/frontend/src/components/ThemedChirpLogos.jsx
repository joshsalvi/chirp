/**
 * Themed Chirp logos: the Songbird mark (SongbirdMark.jsx) drawn in each
 * theme's own medium. Same bird, same three bars, same animation loop;
 * the line, color and surface treatment change. Themes not listed here
 * use the default mark in ChirpLogo.jsx.
 *
 * Every component takes { size, animate, className } like ChirpLogo.
 * Shared by both server forks; themes a fork doesn't define are unused.
 */
import { useId } from 'react'
import SongbirdMark, { PATHS, EYE, BAR_CY } from './SongbirdMark'

// Frames, grids and margin notes only at sizes where they stay legible.
const roomy = props => (props.size ?? 36) >= 40

// Cornell Lab: color-blocked. Carnelian body, black line, gold wing and beak.
export function CornellLogo(props) {
  return (
    <SongbirdMark {...props} ink="#1a1a1a" wingInk="#f4b400" beakInk="#f4b400" accent="#b31b1b"
                  catchlight="#fdf8f0"
                  underBird={() => <path d={PATHS.silhouette} fill="#b31b1b"/>}/>
  )
}

// Field Notebook: pencil line with a second loose pass, a construction
// guide, ruled lines and a margin note.
export function FieldNotebookLogo(props) {
  const pencil = '#4a4540'
  return (
    <SongbirdMark {...props} ink={pencil} accent={pencil} strokeWidth={2.2} eyeR={2.8}
                  catchlight={null} barWidth={2}
                  inkProps={{ opacity: 0.9 }}
                  under={() => roomy(props) && (
                    <g stroke="#c9c0a8" strokeWidth="0.4" opacity="0.6">
                      <line x1="0" y1="24" x2="118" y2="24"/>
                      <line x1="0" y1="78" x2="118" y2="78"/>
                    </g>
                  )}
                  underBird={() => (
                    <g fill="none" stroke={pencil} strokeLinecap="round">
                      {/* second, looser pencil pass */}
                      <path d={PATHS.body} strokeWidth="0.8" opacity="0.35"
                            transform="translate(0.9 0.6)"/>
                      <ellipse cx="47" cy="54" rx="21" ry="16" strokeWidth="0.4" opacity="0.3" strokeDasharray="1 2.5"/>
                      <path d="M34 64 L40 58 M38 66 L45 59 M43 67 L50 60" strokeWidth="0.5" opacity="0.35"/>
                    </g>
                  )}
                  over={() => roomy(props) && (
                    <text x="86" y="62" fontFamily="Georgia, serif" fontSize="6" fontStyle="italic"
                          fill="#6b6452" opacity="0.7" transform="rotate(-4 86 62)">sp.?</text>
                  )}/>
  )
}

// Terminal: phosphor green, square ends, glow, stepped motion, cursor.
export function TerminalLogo(props) {
  return (
    <SongbirdMark {...props} ink="#00ff41" accent="#00ff41" cap="square" join="miter"
                  catchlight="#010401" stepped glow={{ blur: 2.4, opacity: 0.55 }}
                  over={() => (
                    <rect className={props.animate ? 'cb-cursor' : undefined}
                          x="107" y={BAR_CY + 9} width="5.5" height="2.2" fill="#00ff41"/>
                  )}/>
  )
}

// Paper: thin ink line over soft watercolor washes.
export function PaperLogo(props) {
  return (
    <SongbirdMark {...props} ink="#3a3530" accent={['#15803d', '#15803d', '#15803d']} strokeWidth={2.4}
                  eyeR={3} catchlight="#fdfaf3" barWidth={4.5} inkProps={{ opacity: 0.8 }}
                  underBird={ids => (
                    <>
                      <defs>
                        <filter id={`${ids.uid}_wash`} x="-20%" y="-20%" width="140%" height="140%">
                          <feGaussianBlur stdDeviation="1.6"/>
                        </filter>
                        <radialGradient id={`${ids.uid}_body`} cx="0.35" cy="0.3" r="0.9">
                          <stop offset="0" stopColor="#fde68a" stopOpacity="0.75"/>
                          <stop offset="0.55" stopColor="#4ade80" stopOpacity="0.55"/>
                          <stop offset="1" stopColor="#15803d" stopOpacity="0.7"/>
                        </radialGradient>
                      </defs>
                      <path d={PATHS.silhouette} fill={`url(#${ids.uid}_body)`} filter={`url(#${ids.uid}_wash)`}
                            transform="translate(1 1)"/>
                    </>
                  )}/>
  )
}

// Mono: two-tone noir. Lit body, hard diagonal shadow, sharp bars.
export function MonoLogo(props) {
  const light = '#e8e8e8', dark = '#0a0a0a'
  return (
    <SongbirdMark {...props} ink={light} accent={light} wingInk={dark} eyeInk={dark} catchlight={light}
                  barCap="butt" stepped
                  underBird={ids => (
                    <>
                      <defs><clipPath id={ids.clip}><path d={PATHS.silhouette}/></clipPath></defs>
                      <path d={PATHS.silhouette} fill={light}/>
                      <g clipPath={`url(#${ids.clip})`}>
                        <polygon points="46,76 80,30 90,80" fill={dark} opacity="0.92"/>
                      </g>
                    </>
                  )}/>
  )
}

// Plate: engraved line, cross-hatched belly, plate border.
export function PlateLogo(props) {
  const ink = '#2b2440'
  return (
    <SongbirdMark {...props} ink={ink} accent={ink} strokeWidth={2} eyeR={2.8} catchlight={null}
                  barWidth={1.6} stepped
                  underBird={ids => (
                    <>
                      <defs>
                        <clipPath id={ids.clip}><path d={PATHS.silhouette}/></clipPath>
                        <pattern id={`${ids.uid}_hatch`} width="2.4" height="2.4" patternTransform="rotate(35)" patternUnits="userSpaceOnUse">
                          <line x1="0" y1="0" x2="0" y2="2.4" stroke={ink} strokeWidth="0.45"/>
                        </pattern>
                      </defs>
                      <g clipPath={`url(#${ids.clip})`}>
                        <rect x="20" y="54" width="60" height="22" fill={`url(#${ids.uid}_hatch)`}/>
                      </g>
                    </>
                  )}
                  under={() => roomy(props) && (
                    <rect x="8" y="14" width="102" height="68" fill="none" stroke={ink} strokeWidth="0.6" opacity="0.4"/>
                  )}/>
  )
}

// Oscilloscope: amber phosphor on a graticule, square ends, stepped motion.
export function OscilloscopeLogo(props) {
  const amber = '#ffb000'
  return (
    <SongbirdMark {...props} ink={amber} accent={amber} cap="square" join="miter" catchlight="#0c0a06"
                  stepped glow={{ blur: 3, opacity: 0.6 }}
                  under={() => roomy(props) && (
                    <g stroke={amber} strokeWidth="0.35" opacity="0.22">
                      {[20, 36, 52, 68].map(y => <line key={y} x1="8" y1={y} x2="110" y2={y}/>)}
                      {[12, 32, 52, 72, 92].map(x => <line key={x} x1={x} y1="14" x2={x} y2="82"/>)}
                    </g>
                  )}/>
  )
}

// Aviary: field-guide contour line, stippled belly, terracotta beak and bars.
export function AviaryLogo(props) {
  const ink = '#2a2620', terra = '#b5552e'
  const dots = [[34, 64], [38, 66], [42, 67], [46, 67], [36, 61], [40, 63], [44, 64], [48, 64], [52, 63],
                [56, 61], [60, 58], [50, 60], [54, 58], [58, 55], [62, 53]]
  return (
    <SongbirdMark {...props} ink={ink} beakInk={terra} accent={terra} strokeWidth={2.4} eyeR={3}
                  catchlight="var(--bg-panel, #f6f1e7)" barWidth={3.2}
                  underBird={() => (
                    <g fill={ink} opacity="0.7">{dots.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="0.55"/>)}</g>
                  )}/>
  )
}

// Dracula: purple line, pink wing, glowing red eye and bars.
export function DraculaLogo(props) {
  return (
    <SongbirdMark {...props} ink="#bd93f9" wingInk="#ff79c6" beakInk="#f8f8f2"
                  accent={['#ff5555', '#ff79c6', '#bd93f9']}
                  eye={() => (
                    <>
                      <circle cx={EYE.cx} cy={EYE.cy} r="4.4" fill="#1a0a14"/>
                      <circle cx={EYE.cx} cy={EYE.cy} r="3" fill="#ff5555"/>
                      <circle cx={EYE.cx + 1.1} cy={EYE.cy - 1.1} r="1" fill="#ffb3b3"/>
                    </>
                  )}
                  glow={{ blur: 2.2, opacity: 0.35 }}/>
  )
}

// NEXRAD: radar green, reticle eye, reflectivity-scale bars, frame corners.
export function NexradLogo(props) {
  const g = '#22e066'
  return (
    <SongbirdMark {...props} ink={g} accent={[g, '#ffd400', '#ff3b30']} cap="square" join="miter" stepped
                  eye={() => (
                    <g stroke={g} strokeWidth="0.9" fill="none">
                      <circle cx={EYE.cx} cy={EYE.cy} r="4.2"/>
                      <circle cx={EYE.cx} cy={EYE.cy} r="1.3" fill={g} stroke="none"/>
                      <path d={`M${EYE.cx - 6.5} ${EYE.cy} h3 M${EYE.cx + 3.5} ${EYE.cy} h3 M${EYE.cx} ${EYE.cy - 6.5} v3 M${EYE.cx} ${EYE.cy + 3.5} v3`}/>
                    </g>
                  )}
                  over={() => roomy(props) && (
                    <g stroke={g} strokeWidth="0.8" opacity="0.5" fill="none">
                      <path d="M8 20 V14 H14 M104 14 H110 V20 M8 76 V82 H14 M104 82 H110 V76"/>
                    </g>
                  )}/>
  )
}

// Moth Trap: blacklight violet glow over a dark body.
export function MothTrapLogo(props) {
  const uv = '#c63dff'
  return (
    <SongbirdMark {...props} ink={uv} accent={uv} catchlight="#f0d0ff" weightScale={0.9}
                  glow={{ blur: 3.2, opacity: 0.75 }}
                  under={ids => (
                    <>
                      <defs>
                        <radialGradient id={`${ids.uid}_halo`} cx="0.45" cy="0.5" r="0.55">
                          <stop offset="0" stopColor={uv} stopOpacity="0.28"/>
                          <stop offset="1" stopColor={uv} stopOpacity="0"/>
                        </radialGradient>
                      </defs>
                      <rect x="0" y="8" width="118" height="80" fill={`url(#${ids.uid}_halo)`}/>
                    </>
                  )}
                  underBird={() => (
                    <path d={PATHS.silhouette} fill="#1a0a24" opacity="0.85"/>
                  )}/>
  )
}

// Spectrogram: the line runs through the viridis colormap Chirp's
// spectrograms use; bars step up the same scale.
export function SpectrogramLogo(props) {
  const id = `spg_${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  return (
    <SongbirdMark {...props} ink={`url(#${id})`} accent={['#35b779', '#90d743', '#fde725']} catchlight="#08031a"
                  eyeInk="#fde725"
                  under={() => (
                    <defs>
                      <linearGradient id={id} x1="12" y1="0" x2="80" y2="0" gradientUnits="userSpaceOnUse">
                        <stop offset="0" stopColor="#5b2a8c"/><stop offset="0.35" stopColor="#31688e"/>
                        <stop offset="0.7" stopColor="#35b779"/><stop offset="1" stopColor="#b5de2b"/>
                      </linearGradient>
                    </defs>
                  )}/>
  )
}

// Migration: star-gold line on a night sky with a dotted flight path.
export function MigrationLogo(props) {
  const gold = '#f4d58d'
  const stars = [[14, 22, 0.8], [30, 17, 0.6], [100, 20, 0.7], [110, 64, 0.6], [22, 80, 0.7], [84, 78, 0.5], [62, 16, 0.5]]
  return (
    <SongbirdMark {...props} ink={gold} accent={gold} catchlight="#04060d"
                  under={() => roomy(props) && (
                    <g>
                      <g fill={gold} opacity="0.7">{stars.map(([x, y, r], i) => <circle key={i} cx={x} cy={y} r={r}/>)}</g>
                      <path d="M4 76 Q 40 88 70 80" stroke={gold} strokeWidth="0.7" strokeDasharray="1 2.4" fill="none" opacity="0.45"/>
                    </g>
                  )}/>
  )
}

// Roost: warm wood-grain body in birdhouse amber.
export function RoostLogo(props) {
  const amber = '#e0983e'
  return (
    <SongbirdMark {...props} ink="#eeaf5c" accent={amber} catchlight="#100a05"
                  underBird={ids => (
                    <>
                      <defs><clipPath id={ids.clip}><path d={PATHS.silhouette}/></clipPath></defs>
                      <path d={PATHS.silhouette} fill="#3a2410"/>
                      <g clipPath={`url(#${ids.clip})`} stroke="#c9812f" strokeWidth="0.7" fill="none" opacity="0.6">
                        <path d="M20 44 C 40 40 60 46 80 42 M20 52 C 40 48 60 54 80 50 M20 60 C 40 56 60 62 80 58 M20 68 C 40 64 60 70 80 66"/>
                      </g>
                    </>
                  )}/>
  )
}

// Echo Cave: cave teal, with sonar rings spreading past the bars.
export function EchoCaveLogo(props) {
  const teal = '#3fc0b6'
  return (
    <SongbirdMark {...props} ink={teal} accent={['#63d4cb', teal, '#29a89e']} catchlight="#06080b"
                  under={() => roomy(props) && (
                    <g fill="none" stroke={teal} strokeWidth="0.8">
                      {[16, 24, 32].map((r, i) => (
                        <path key={r} d={`M${96 + r * 0.64} ${BAR_CY - r * 0.77} A${r} ${r} 0 0 1 ${96 + r * 0.64} ${BAR_CY + r * 0.77}`}
                              opacity={0.45 - i * 0.12} transform={`translate(${-r * 0.1} 0)`}/>
                      ))}
                    </g>
                  )}/>
  )
}

// Dawn Chorus: warm line in front of a rising sun; bars run orange to magenta.
export function DawnChorusLogo(props) {
  const id = `dawn_${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  return (
    <SongbirdMark {...props} ink="#ffb04f" accent={['#ff8a1a', '#ff5fa2', '#d946ef']} catchlight="#180e1a"
                  under={() => roomy(props) && (
                    <>
                      <defs>
                        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0" stopColor="#ff8a1a" stopOpacity="0.55"/>
                          <stop offset="1" stopColor="#d946ef" stopOpacity="0.1"/>
                        </linearGradient>
                      </defs>
                      <path d="M20 82 A 32 32 0 0 1 84 82 Z" fill={`url(#${id})`}/>
                      <line x1="10" y1="82" x2="108" y2="82" stroke="#ffb04f" strokeWidth="0.6" opacity="0.5"/>
                    </>
                  )}/>
  )
}

// Feather: iridescent line, magenta through violet to teal.
export function FeatherLogo(props) {
  const id = `fth_${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  return (
    <SongbirdMark {...props} ink={`url(#${id})`} accent={['#d946ef', '#6366f1', '#06b6d4']} eyeInk="#e879f9"
                  catchlight="#0d0818" glow={{ blur: 2, opacity: 0.3 }}
                  under={() => (
                    <defs>
                      <linearGradient id={id} x1="12" y1="70" x2="80" y2="30" gradientUnits="userSpaceOnUse">
                        <stop offset="0" stopColor="#10b981"/><stop offset="0.35" stopColor="#06b6d4"/>
                        <stop offset="0.7" stopColor="#6366f1"/><stop offset="1" stopColor="#d946ef"/>
                      </linearGradient>
                    </defs>
                  )}/>
  )
}

// Maps a theme id to its logo. Themes not listed use ChirpLogo's default.
export const THEMED_LOGOS = {
  cornell: CornellLogo,
  fieldnotebook: FieldNotebookLogo,
  terminal: TerminalLogo,
  paper: PaperLogo,
  mono: MonoLogo,
  plate: PlateLogo,
  oscilloscope: OscilloscopeLogo,
  aviary: AviaryLogo,
  dracula: DraculaLogo,
  nexrad: NexradLogo,
  mothtrap: MothTrapLogo,
  spectrogram: SpectrogramLogo,
  migration: MigrationLogo,
  roost: RoostLogo,
  echocave: EchoCaveLogo,
  dawnchorus: DawnChorusLogo,
  feather: FeatherLogo,
}

export function getThemedLogo(themeId) {
  return THEMED_LOGOS[themeId] || null
}
