// Custom icons for themes that have a specific visual concept worth
// representing directly rather than just a color swatch — same idea as
// BirdIcon/BatIcon (BirdBatIcons.jsx) and INatIcon (MapSourceIcons.jsx).
// Only themes with a genuinely distinct *concept* (not just a new color)
// get one; ThemeSection falls back to the plain swatch dot otherwise.

export function SpectrogramIcon({ size = 16, className = '' }) {
  // Vertical bars of varying height, colored low-to-high like a real
  // spectrogram's intensity colormap (deep purple → teal → bright green) —
  // literally what every Chirp recording's spectrogram looks like.
  const bars = [
    { h: 5,  c: '#3f2a94' },
    { h: 9,  c: '#2b6f8e' },
    { h: 13, c: '#1f9a83' },
    { h: 16, c: '#35b779' },
    { h: 11, c: '#5ecb6f' },
    { h: 7,  c: '#8fd94f' },
    { h: 4,  c: '#3f2a94' },
  ]
  const w = 2
  const gap = 1.4
  const totalW = bars.length * w + (bars.length - 1) * gap
  return (
    <svg width={size} height={size} viewBox={`0 0 ${totalW} 16`} className={className} fill="none">
      {bars.map((b, i) => (
        <rect key={i}
              x={i * (w + gap)}
              y={16 - b.h}
              width={w}
              height={b.h}
              rx={0.5}
              fill={b.c}/>
      ))}
    </svg>
  )
}

export function MigrationIcon({ size = 16, className = '' }) {
  // Crescent moon + a couple of small stars — night-sky navigation, the
  // way real nocturnal migrants (most songbirds migrate at night) actually
  // orient. Distinct from any weather/instrument iconography already used
  // by other themes.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <path d="M15.5 4.5a8 8 0 1 0 4 13.2 9.5 9.5 0 0 1-4-13.2z"
            fill="#f4d58d"/>
      <circle cx="19.5" cy="5" r="0.9" fill="#eef2fb"/>
      <circle cx="21" cy="9.5" r="0.6" fill="#eef2fb"/>
      <circle cx="16.5" cy="2.5" r="0.5" fill="#eef2fb"/>
    </svg>
  )
}

export function RoostIcon({ size = 16, className = '' }) {
  // A small birdhouse with a perched bird — warm wood tones. The literal
  // "character" this theme is built around (see index.css's hop animation).
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <path d="M5 11 12 4l7 7" stroke="#c9812f" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
      <rect x="6.5" y="11" width="11" height="9" rx="1" fill="#8a6741"/>
      <circle cx="12" cy="15" r="1.6" fill="#38220a"/>
      <path d="M15.5 17.5c1.4 0 2.2-.8 2.2-1.9 0-.7-.4-1.2-1-1.4.1.9-.4 1.5-1.2 1.5-.6 0-1-.4-1-1 0-.3.1-.5.3-.7-1 .1-1.7.9-1.7 1.8 0 .9.6 1.7 2.4 1.7z" fill="#e0983e"/>
    </svg>
  )
}

export function EchoCaveIcon({ size = 16, className = '' }) {
  // A small bat with expanding echolocation rings — the literal
  // "character" this theme is built around (see index.css's sonar-ping
  // animation).
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <path d="M12 8c-1.5-2.5-4-3-5.5-1.5C5 8 5.5 10.5 8 12c-2 0-3.5 1-4 2.5 2 .5 3.5 0 4.5-1 .3 1 1.5 2 3.5 2s3.2-1 3.5-2c1 1 2.5 1.5 4.5 1 -.5-1.5-2-2.5-4-2.5 2.5-1.5 3-4 1.5-5.5C16 5 13.5 5.5 12 8z"
            fill="#29a89e"/>
      <circle cx="12" cy="9.3" r="0.9" fill="#06080b"/>
      <path d="M12 15.5c-2 5-2 5-2 5M12 15.5c2 5 2 5 2 5" stroke="#3fc0b6" strokeWidth="0" fill="none"/>
      <circle cx="19" cy="6" r="1.2" stroke="#3fc0b6" strokeWidth="0.8" fill="none" opacity="0.8"/>
      <circle cx="19" cy="6" r="2.6" stroke="#3fc0b6" strokeWidth="0.6" fill="none" opacity="0.4"/>
    </svg>
  )
}

export function PaperIcon({ size = 16, className = '' }) {
  // A dog-eared page corner — the actual paper-fold detail, not a generic document icon.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <path d="M6 3h9l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" fill="#f7f3e8" stroke="#15803d" strokeWidth="1.2"/>
      <path d="M15 3v5h5" fill="none" stroke="#15803d" strokeWidth="1.2"/>
      <path d="M8 13h8M8 16.5h6" stroke="#15803d" strokeWidth="1" strokeLinecap="round"/>
    </svg>
  )
}

export function MonoIcon({ size = 16, className = '' }) {
  // Flat, single-color square — the whole point of this theme is the
  // absence of ornamentation, so the icon has to be equally plain.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <rect x="4" y="4" width="16" height="16" fill="#e8e8e8"/>
      <rect x="4" y="4" width="16" height="16" fill="none" stroke="#0a0a0a" strokeWidth="1.5"/>
    </svg>
  )
}

export function TerminalIcon({ size = 16, className = '' }) {
  // The actual prompt glyph, phosphor green — not a generic monitor icon.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <rect x="2" y="4" width="20" height="16" rx="1.5" fill="#010401" stroke="#00ff41" strokeWidth="1"/>
      <path d="M6 10l3 2.5L6 15" stroke="#00ff41" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
      <path d="M12 15h6" stroke="#00ff41" strokeWidth="1.6" strokeLinecap="round"/>
    </svg>
  )
}

export function PlateIcon({ size = 16, className = '' }) {
  // An engraved oval medallion with a bird silhouette inside — the field-
  // guide "plate" motif, not a generic frame.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <ellipse cx="12" cy="12" rx="9" ry="7" fill="#ece5d3" stroke="#2b2440" strokeWidth="1"/>
      <ellipse cx="12" cy="12" rx="7" ry="5.2" fill="none" stroke="#2b2440" strokeWidth="0.5"/>
      <path d="M9 13c0-2 1.5-3 3-3s3 1 3 3-1.5 2-3 2-3 0-3-2z" fill="#2b2440"/>
    </svg>
  )
}

export function OscilloscopeIcon({ size = 16, className = '' }) {
  // A real oscilloscope trace — amber sine wave on a dark CRT screen with
  // a faint grid, the actual instrument this theme is styled after. The
  // previous icon (a generic bird logo swatch) didn't reference the
  // theme's own concept at all.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <rect x="2" y="3" width="20" height="18" rx="1.5" fill="#0c0a06" stroke="#ffb000" strokeWidth="1"/>
      <path d="M2 12h20M12 3v18" stroke="#ffb000" strokeWidth="0.3" opacity="0.4"/>
      <path d="M3 12c1.5 0 1.5-6 3-6s1.5 12 3 12 1.5-9 3-9 1.5 6 3 6 1.5-3 3-3 1.5 0 3 0"
            stroke="#ffb000" strokeWidth="1.4" fill="none" strokeLinecap="round"/>
    </svg>
  )
}

export function AviaryIcon({ size = 16, className = '' }) {
  // A birdcage — the aviary/gallery motif.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <path d="M12 3v3M8 6h8" stroke="#b5552e" strokeWidth="1.2" strokeLinecap="round"/>
      <path d="M6 6c0 6-2 8-2 11a8 8 0 0 0 16 0c0-3-2-5-2-11" fill="none" stroke="#b5552e" strokeWidth="1.2"/>
      <path d="M8 6v11M12 6v11M16 6v11" stroke="#b5552e" strokeWidth="0.8" opacity="0.7"/>
      <path d="M10 13c0-1.5 1-2.3 2-2.3s2 .8 2 2.3-1 1.5-2 1.5-2 0-2-1.5z" fill="#b5552e"/>
    </svg>
  )
}

export function CornellIcon({ size = 16, className = '' }) {
  // Binoculars with a small bird silhouette between the barrels — closer
  // to the Merlin Bird ID app's own mark than the previous icon, which
  // had no relationship to birding-in-the-field at all.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <circle cx="7.5" cy="14" r="4" fill="none" stroke="#b31b1b" strokeWidth="1.6"/>
      <circle cx="16.5" cy="14" r="4" fill="none" stroke="#b31b1b" strokeWidth="1.6"/>
      <path d="M11 12h2" stroke="#b31b1b" strokeWidth="1.6"/>
      <path d="M9 6c1-1.5 2-2 3-2s2 .5 3 2" stroke="#b31b1b" strokeWidth="1" fill="none" strokeLinecap="round"/>
      <path d="M12 8.5c-.9 0-1.6.6-1.6 1.4 0 .6.4 1 1 1.2-.5.3-.8.7-.8 1.2 0 .8.8 1.4 1.8 1.4h.2c1 0 1.8-.6 1.8-1.4 0-.5-.3-.9-.8-1.2.6-.2 1-.6 1-1.2 0-.8-.7-1.4-1.6-1.4z" fill="#b31b1b"/>
    </svg>
  )
}

export function FieldNotebookIcon({ size = 16, className = '' }) {
  // A small spiral-bound notebook — the ruled-paper field notebook motif.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <rect x="5" y="3" width="15" height="18" rx="1" fill="#f0ead8" stroke="#2c4a3e" strokeWidth="1"/>
      <path d="M3 6h3M3 10h3M3 14h3M3 18h3" stroke="#2c4a3e" strokeWidth="1.4" strokeLinecap="round"/>
      <path d="M8 8h9M8 11.5h9M8 15h6" stroke="#2c4a3e" strokeWidth="0.8" opacity="0.7"/>
    </svg>
  )
}

export function DraculaIcon({ size = 16, className = '' }) {
  // A small bat silhouette in the theme's own purple/pink palette — the
  // one non-bird-specific "character" reference this palette theme gets.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <path d="M12 9c-1.8-3-4.8-3.6-6.6-1.8C3.6 9 4.2 12 7 13.8c-2.4 0-4.2 1.2-4.8 3 2.4.6 4.2 0 5.4-1.2.4 1.2 1.8 2.4 4.2 2.4s3.8-1.2 4.2-2.4c1.2 1.2 3 1.8 5.4 1.2-.6-1.8-2.4-3-4.8-3 2.8-1.8 3.4-4.8 1.8-6.6C16.8 5.4 13.8 6 12 9z"
            fill="#bd93f9"/>
      <circle cx="12" cy="10.5" r="1" fill="#282a36"/>
    </svg>
  )
}

export function NexradIcon({ size = 16, className = '' }) {
  // A radar sweep — concentric rings with a rotating beam wedge, the
  // actual weather-radar display this theme is styled after.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <circle cx="12" cy="12" r="9" fill="#030a0d" stroke="#22e066" strokeWidth="1"/>
      <circle cx="12" cy="12" r="6" fill="none" stroke="#22e066" strokeWidth="0.6" opacity="0.5"/>
      <circle cx="12" cy="12" r="3" fill="none" stroke="#22e066" strokeWidth="0.6" opacity="0.5"/>
      <path d="M12 12L12 3A9 9 0 0 1 19.5 16.5z" fill="#22e066" opacity="0.35"/>
      <circle cx="12" cy="12" r="1" fill="#22e066"/>
    </svg>
  )
}

export function MothTrapIcon({ size = 16, className = '' }) {
  // A moth silhouette under UV glow — the blacklight field-recording motif.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <path d="M12 7v10" stroke="#c63dff" strokeWidth="1" opacity="0.6"/>
      <path d="M12 9c-1-3-4-4.5-6.5-3-2 3 0 6 3.5 6.5-2 .5-3.5 2-3.5 4 2 0 4-1 5-2.5.3 1 1 1.5 1.5 1.5s1.2-.5 1.5-1.5c1 1.5 3 2.5 5 2.5 0-2-1.5-3.5-3.5-4 3.5-.5 5.5-3.5 3.5-6.5-2.5-1.5-5.5 0-6.5 3z"
            fill="#c63dff" opacity="0.9"/>
    </svg>
  )
}


