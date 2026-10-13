/**
 * Map Source Icons — small, original glyphs for the range-map tab pills.
 *
 * These are NOT reproductions of any organization's actual logo — Chirp
 * has no way to source official brand assets (the relevant domains aren't
 * reachable from this build environment, and recreating a trademarked mark
 * from memory wouldn't be an accurate or appropriate substitute anyway).
 * Instead, each is a simple, original icon evoking that source's general
 * focus, replacing the previous generic emoji (🗺️ 🌿 🐦 📊) with something
 * a little more deliberately designed while staying clearly distinct from
 * any real logo:
 *
 *   AAB (All About Birds)   — binoculars, evoking field observation, in a
 *                             warm amber gradient
 *   iNat (iNaturalist)      — a leaf with a magnifying glass, evoking
 *                             citizen-science species identification, in
 *                             a green gradient
 *   BirdLife International — a globe with latitude bands, evoking the
 *                             org's global scope, in a blue gradient
 *   eBird S&T               — a small rising bar chart, evoking the
 *                             underlying statistical abundance data, in
 *                             a teal gradient
 *
 * Each gets a soft gradient fill rather than a flat single-color stroke —
 * matching the polish level ChirpLogo.jsx already uses elsewhere in the
 * app (multi-stop gradients, subtle highlight) instead of looking like a
 * generic outline icon set. All four share sizing conventions so they sit
 * consistently inside a small tab pill alongside text.
 */
import { useId } from 'react'

export function AABIcon({ size = 14, className = '' }) {
  const reactId = useId()
  const id = `aab-${reactId}`
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}
         xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={id} x1="4" y1="6" x2="20" y2="19" gradientUnits="userSpaceOnUse">
          <stop stopColor="#fbbf24"/>
          <stop offset="1" stopColor="#d97706"/>
        </linearGradient>
      </defs>
      <circle cx="7" cy="15" r="4.2" fill={`url(#${id})`} fillOpacity="0.22"
              stroke={`url(#${id})`} strokeWidth="1.7"/>
      <circle cx="17" cy="15" r="4.2" fill={`url(#${id})`} fillOpacity="0.22"
              stroke={`url(#${id})`} strokeWidth="1.7"/>
      <path d="M10.8 13.3 L13.2 13.3" stroke={`url(#${id})`} strokeWidth="1.7" strokeLinecap="round"/>
      <path d="M9.3 11 L11 6.7 L13 6.7 L14.7 11" stroke={`url(#${id})`} strokeWidth="1.7"
            strokeLinecap="round" strokeLinejoin="round" fill="none"/>
      <circle cx="6" cy="14" r="0.9" fill="#fef3c7" fillOpacity="0.9"/>
      <circle cx="16" cy="14" r="0.9" fill="#fef3c7" fillOpacity="0.9"/>
    </svg>
  )
}

export function INatIcon({ size = 14, className = '' }) {
  const reactId = useId()
  const id = `inat-${reactId}`
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}
         xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={id} x1="6" y1="4" x2="18" y2="21" gradientUnits="userSpaceOnUse">
          <stop stopColor="#86efac"/>
          <stop offset="1" stopColor="#16a34a"/>
        </linearGradient>
      </defs>
      <path d="M12 4 C8 6 6 10 7.5 14 C9 18 12 19 12 19 C12 19 15 18 16.5 14 C18 10 16 6 12 4 Z"
            fill={`url(#${id})`} fillOpacity="0.25" stroke={`url(#${id})`} strokeWidth="1.5"
            strokeLinejoin="round"/>
      <path d="M12 6.8 L12 16.5" stroke={`url(#${id})`} strokeWidth="1.2" strokeLinecap="round" opacity="0.8"/>
      <circle cx="16.3" cy="17.3" r="2.5" fill="#0a3a1f" fillOpacity="0.85"
              stroke={`url(#${id})`} strokeWidth="1.5"/>
      <path d="M18 19 L19.6 20.6" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  )
}

export function BirdLifeIcon({ size = 14, className = '' }) {
  const reactId = useId()
  const id = `birdlife-${reactId}`
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}
         xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={id} x1="4" y1="4" x2="20" y2="20" gradientUnits="userSpaceOnUse">
          <stop stopColor="#7dd3fc"/>
          <stop offset="1" stopColor="#0369a1"/>
        </linearGradient>
      </defs>
      <circle cx="12" cy="12" r="8" fill={`url(#${id})`} fillOpacity="0.2" stroke={`url(#${id})`} strokeWidth="1.5"/>
      <path d="M4.3 9.5 C8 11 16 11 19.7 9.5" stroke={`url(#${id})`} strokeWidth="1" opacity="0.85"/>
      <path d="M4.3 14.5 C8 13 16 13 19.7 14.5" stroke={`url(#${id})`} strokeWidth="1" opacity="0.85"/>
      <path d="M12 4 C9.3 6.6 9.3 17.4 12 20 C14.7 17.4 14.7 6.6 12 4 Z"
            stroke={`url(#${id})`} strokeWidth="1.2" opacity="0.9"/>
      <circle cx="12" cy="12" r="1.4" fill="#e0f2fe"/>
    </svg>
  )
}

export function EbirdSTIcon({ size = 14, className = '' }) {
  const reactId = useId()
  const id = `ebird-st-${reactId}`
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}
         xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={id} x1="4" y1="20" x2="20" y2="4" gradientUnits="userSpaceOnUse">
          <stop stopColor="#5eead4"/>
          <stop offset="1" stopColor="#0d9488"/>
        </linearGradient>
      </defs>
      <path d="M4 20 L4 4" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round" opacity="0.6"/>
      <path d="M4 20 L20.5 20" stroke={`url(#${id})`} strokeWidth="1.5" strokeLinecap="round" opacity="0.6"/>
      <rect x="6.5" y="13.5" width="3" height="6.5" rx="0.8" fill={`url(#${id})`}/>
      <rect x="11.5" y="9.5" width="3" height="10.5" rx="0.8" fill={`url(#${id})`} fillOpacity="0.9"/>
      <rect x="16.5" y="5.5" width="3" height="14.5" rx="0.8" fill={`url(#${id})`}/>
      <path d="M7 12.3 L12 8.3 L17 4.3" stroke="#a7f3d0" strokeWidth="1" strokeLinecap="round" opacity="0.7"/>
    </svg>
  )
}

export function MacaulayIcon({ size = 14, className = '' }) {
  const reactId = useId()
  const id = `macaulay-${reactId}`
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}
         xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={id} x1="4" y1="6" x2="20" y2="18" gradientUnits="userSpaceOnUse">
          <stop stopColor="#fbbf24"/>
          <stop offset="1" stopColor="#b45309"/>
        </linearGradient>
      </defs>
      {/* Camera body, evoking Macaulay Library's identity as Cornell's
          media archive (photos, audio, video) rather than an
          illustration-style range map source like AAB. */}
      <rect x="3" y="7.5" width="18" height="12" rx="2" fill={`url(#${id})`} opacity="0.9"/>
      <path d="M8.5 7.5 L9.7 5.3 A1.5 1.5 0 0 1 11 4.5 H13 A1.5 1.5 0 0 1 14.3 5.3 L15.5 7.5"
            fill={`url(#${id})`}/>
      <circle cx="12" cy="13.5" r="3.6" fill="#1a1208"/>
      <circle cx="12" cy="13.5" r="2.5" fill={`url(#${id})`} opacity="0.85"/>
      <circle cx="13.1" cy="12.4" r="0.7" fill="#fef3c7" opacity="0.8"/>
    </svg>
  )
}
