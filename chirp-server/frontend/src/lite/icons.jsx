// Line icons (24-unit grid) and the Chirp Lite bird mark.
const S = { fill: 'none', stroke: 'currentColor', strokeWidth: 2.2, strokeLinecap: 'round', strokeLinejoin: 'round' }

export const Icon = {
  today: (p) => <svg viewBox="0 0 24 24" {...p}><circle cx="12" cy="12" r="4.2" {...S} /><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" {...S} /></svg>,
  birds: (p) => <svg viewBox="0 0 24 24" {...p}><rect x="3" y="3" width="7.5" height="7.5" rx="2.4" {...S} /><rect x="13.5" y="3" width="7.5" height="7.5" rx="2.4" {...S} /><rect x="3" y="13.5" width="7.5" height="7.5" rx="2.4" {...S} /><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2.4" {...S} /></svg>,
  listen: (p) => <svg viewBox="0 0 24 24" {...p}><path d="M3 12h2M7 8v8M11 4v16M15 7v10M19 10v4M21.5 12h-.5" {...S} /></svg>,
  guide: (p) => <svg viewBox="0 0 24 24" {...p}><circle cx="12" cy="12" r="9.2" {...S} /><path d="M15.6 8.4l-2.2 5-5 2.2 2.2-5z" {...S} /></svg>,
  play: (p) => <svg viewBox="0 0 24 24" {...p}><path d="M8 5.2v13.6c0 .8.9 1.3 1.6.9l10.6-6.8c.6-.4.6-1.4 0-1.8L9.6 4.3C8.9 3.9 8 4.4 8 5.2z" fill="currentColor" /></svg>,
  pause: (p) => <svg viewBox="0 0 24 24" {...p}><rect x="6" y="4.5" width="4.2" height="15" rx="1.6" fill="currentColor" /><rect x="13.8" y="4.5" width="4.2" height="15" rx="1.6" fill="currentColor" /></svg>,
  back: (p) => <svg viewBox="0 0 24 24" {...p}><path d="M15 5l-7 7 7 7" {...S} strokeWidth="2.6" /></svg>,
  close: (p) => <svg viewBox="0 0 24 24" {...p}><path d="M6 6l12 12M18 6L6 18" {...S} strokeWidth="2.6" /></svg>,
  check: (p) => <svg viewBox="0 0 24 24" {...p}><path d="M5 12.5l4.5 4.5L19 7.5" {...S} strokeWidth="2.8" /></svg>,
  search: (p) => <svg viewBox="0 0 24 24" {...p}><circle cx="10.5" cy="10.5" r="6.5" {...S} /><path d="M15.5 15.5L20 20" {...S} /></svg>,
  arrow: (p) => <svg viewBox="0 0 24 24" {...p}><path d="M9 5l7 7-7 7" {...S} strokeWidth="2.6" /></svg>,
  ruler: (p) => <svg viewBox="0 0 24 24" {...p}><rect x="2.5" y="8" width="19" height="8" rx="2" {...S} /><path d="M6.5 8v3M10.5 8v4M14.5 8v3M18.5 8v4" {...S} /></svg>,
  calendar: (p) => <svg viewBox="0 0 24 24" {...p}><rect x="3" y="4.5" width="18" height="16.5" rx="3" {...S} /><path d="M3 9.5h18M8 2.5v4M16 2.5v4" {...S} /></svg>,
  ear: (p) => <svg viewBox="0 0 24 24" {...p}><path d="M7 9.5a5 5 0 0110 0c0 3-2.5 3.6-3 6.2-.4 2.2-1.6 3.8-3.6 3.8A3.4 3.4 0 017 16.6" {...S} /><path d="M10 10a2 2 0 014 0c0 1.2-1 1.5-1.4 2.3" {...S} /></svg>,
  live: (p) => <svg viewBox="0 0 24 24" {...p}><rect x="8.5" y="2.5" width="7" height="12" rx="3.5" {...S} /><path d="M5 11a7 7 0 0014 0M12 18v3.5" {...S} /></svg>,
  out: (p) => <svg viewBox="0 0 24 24" {...p}><path d="M14 4h4a2 2 0 012 2v12a2 2 0 01-2 2h-4M9.5 16.5L5 12l4.5-4.5M5 12h10.5" {...S} /></svg>,
  grid: (p) => <svg viewBox="0 0 24 24" {...p}><path d="M4 6h16M4 12h16M4 18h10" {...S} /></svg>,
}

// The Meadow bird (Classic) — keep in step with public/lite-icon.svg.
export function BirdMark({ size = 40, tile = true, className }) {
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} className={className} aria-hidden="true">
      {tile && <rect width="100" height="100" rx="23" fill="#22B573" />}
      {tile && <circle cx="80" cy="82" r="34" fill="#45C78A" />}
      <path d="M27 58 L8 44 Q10 61 24 69 Z" fill="#FFFFFF" />
      <ellipse cx="45" cy="60" rx="25" ry="21" fill="#FFFFFF" />
      <circle cx="60" cy="45" r="15.5" fill="#FFFFFF" />
      <path d="M33 58 Q47 50 59 61 Q46 70 33 58 Z" fill="#D4F2E2" />
      <path d="M74.5 41.5 L86 45 L74.5 49 Z" fill="#FF8A3D" />
      <circle cx="64.5" cy="41.5" r="2.8" fill="#0C3A24" />
      <rect x="80" y="17" width="4.2" height="11" rx="2.1" fill="#FFE45C" />
      <rect x="86" y="13" width="4.2" height="19" rx="2.1" fill="#FFE45C" />
      <rect x="92" y="18" width="4.2" height="9" rx="2.1" fill="#FFE45C" />
    </svg>
  )
}
