/**
 * Bird & Bat Icons — original, custom-designed glyphs replacing the plain
 * 🐦 / 🦇 emoji previously used as functional UI markers throughout the app
 * (filter toggle buttons, diagnostics category labels, role badges).
 *
 * Design goals: a simple, clean, unmistakably-bird / unmistakably-bat
 * silhouette that reads clearly even at small icon sizes (~16-20px), in a
 * matched visual style so the pair feels designed together rather than
 * mismatched — same construction approach (solid silhouette, dot eyes,
 * similar level of simplification), not just "two random icons."
 *
 * Both use `currentColor` for the fill, so they inherit color from
 * whatever context they're used in (the app already has established green/
 * purple conventions for bird/bat respectively — these icons don't hardcode
 * either, the caller controls color via CSS `color` same as any other icon).
 *
 * The eye dots are cut as genuine transparent holes via an SVG <mask>
 * (unique per-instance mask ids from useId(), with colons stripped — React's
 * useId() output contains colons like ":r0:", which are special characters
 * in CSS/URL-fragment contexts; some browsers can fail to resolve a
 * mask="url(#...)" reference containing one even though a more lenient
 * renderer used during design/verification might not reproduce the
 * problem, so they're removed rather than risking it) rather than drawn as
 * a fixed-color dot on top — a fixed dot would only look right against one
 * specific background color, and this app has multiple themes plus many
 * different badge/button background colors these icons get used against.
 * A real mask-based hole always shows whatever's truly behind the icon,
 * correct in every context without needing a background-color prop to
 * guess at.
 *
 * Verified visually before shipping (rendered to PNG via cairosvg and
 * inspected at both full size and actual ~20px UI scale) rather than
 * shipped on hand-authored path coordinates alone — hand-crafted SVG is
 * easy to get subtly wrong (proportions, overlap, illegibility at small
 * size) without an actual visual check.
 */
import { useId } from 'react'

export function BirdIcon({ size = 16, className = '', style, ...rest }) {
  const reactId = useId().replace(/:/g, '')
  const maskId = `bird-eye-${reactId}`
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} style={style}
         xmlns="http://www.w3.org/2000/svg" {...rest}>
      <mask id={maskId}>
        <rect width="24" height="24" fill="white"/>
        <circle cx="16.4" cy="7.2" r="0.95" fill="black"/>
      </mask>
      <g mask={`url(#${maskId})`}>
        {/* tail — two small fanned feathers */}
        <polygon points="5,11.3 0.5,9.2 2,13" fill="currentColor"/>
        <polygon points="5,13 0.8,12.5 2.6,15.3" fill="currentColor"/>
        {/* body */}
        <ellipse cx="10.5" cy="14" rx="6.3" ry="5.2" fill="currentColor"/>
        {/* head */}
        <circle cx="15.5" cy="8.2" r="3.6" fill="currentColor"/>
        {/* beak */}
        <polygon points="18.7,7.5 21.3,6.9 19,9.3" fill="currentColor"/>
      </g>
      {/* wing crease — a subtle darker-toned accent, not a background cutout,
          so it stays visibly a "wing line" rather than a hole regardless of
          what's behind the icon */}
      <path d="M6.5,11.5 Q10,14.5 7.5,18.5" stroke="currentColor" strokeWidth="0.9"
            fill="none" strokeLinecap="round" opacity="0.35"/>
      {/* legs */}
      <path d="M8.5,18.8 L7.3,22.2 M12.5,19 L13.7,22.2" stroke="currentColor"
            strokeWidth="1.4" strokeLinecap="round" fill="none"/>
    </svg>
  )
}

export function BirdBuddyIcon({ size = 16, className = '', style, ...rest }) {
  const reactId = useId().replace(/:/g, '')
  const maskId = `birdbuddy-eye-${reactId}`
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} style={style}
         xmlns="http://www.w3.org/2000/svg" {...rest}>
      <mask id={maskId}>
        <rect width="24" height="24" fill="white"/>
        <circle cx="14.6" cy="8.6" r="0.9" fill="black"/>
      </mask>
      <g mask={`url(#${maskId})`}>
        {/* tail */}
        <polygon points="5.5,11.5 1.5,10 2.8,13.3" fill="currentColor"/>
        {/* body — perched, sitting low on the feeder platform below */}
        <ellipse cx="10.5" cy="13.3" rx="5.2" ry="4.3" fill="currentColor"/>
        {/* head */}
        <circle cx="14.4" cy="9.5" r="3.1" fill="currentColor"/>
        {/* beak */}
        <polygon points="17.2,9 19.5,8.5 17.6,10.5" fill="currentColor"/>
      </g>
      {/* feeder platform + post — the "smart feeder" cue distinguishing
          this from the plain BirdIcon. Full opacity and bold width, not a
          subtle accent: a first attempt at a thin, low-opacity post was
          confirmed (by rendering at actual ~20px UI scale) to be nearly
          invisible at real icon sizes, undermining the entire point of a
          distinct icon. This is a simple, generic feeder shape — not any
          specific product's real design. */}
      <rect x="3.5" y="18.5" width="17" height="2.2" rx="1.1" fill="currentColor"/>
      <rect x="10.5" y="20.5" width="3" height="2.2" rx="0.6" fill="currentColor"/>
    </svg>
  )
}

export function BatIcon({ size = 16, className = '', style, ...rest }) {
  const reactId = useId().replace(/:/g, '')
  const maskId = `bat-eyes-${reactId}`
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} style={style}
         xmlns="http://www.w3.org/2000/svg" {...rest}>
      <mask id={maskId}>
        <rect width="24" height="24" fill="white"/>
        <circle cx="10.8" cy="10" r="0.8" fill="black"/>
        <circle cx="13.2" cy="10" r="0.8" fill="black"/>
      </mask>
      <g mask={`url(#${maskId})`}>
        {/* left wing — single bold scallop (simplified from an earlier
            multi-scallop version that had too much fine detail to render
            reliably at the small real-world sizes these icons are actually
            used at, e.g. 13px in the Bats-only filter button) */}
        <path d="M10.3,10.5 C6.5,8.5 3,9 1,12.5 C3,12.5 4.2,13.8 3.5,16.5
                 C6,14.8 8.5,13 9.7,11.5 Z" fill="currentColor"/>
        {/* right wing — mirrored */}
        <path d="M13.7,10.5 C17.5,8.5 21,9 23,12.5 C21,12.5 19.8,13.8 20.5,16.5
                 C18,14.8 15.5,13 14.3,11.5 Z" fill="currentColor"/>
        {/* ears */}
        <polygon points="9.6,7.6 10.5,3.6 12,7.2" fill="currentColor"/>
        <polygon points="12,7.2 13.5,3.6 14.4,7.6" fill="currentColor"/>
        {/* head */}
        <ellipse cx="12" cy="10.3" rx="2.9" ry="3.4" fill="currentColor"/>
        {/* lower body */}
        <ellipse cx="12" cy="15.8" rx="2.2" ry="2.7" fill="currentColor"/>
      </g>
    </svg>
  )
}
