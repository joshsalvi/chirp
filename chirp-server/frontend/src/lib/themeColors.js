/**
 * Color math utilities for the custom theme builder.
 *
 * The 5 colors a user picks (background, card, text, accent, border) are
 * not enough variables on their own — every built-in theme defines ~30
 * CSS variables (a 9-step accent ramp, an 8-step neutral ramp, distinct
 * panel/raised background tiers, secondary/tertiary text tones, focus
 * borders, shadows, etc.). Asking someone to hand-pick all of those would
 * defeat the point of a simple "5 colors" builder, so this module derives
 * the rest algorithmically from the 5 real inputs using straightforward
 * HSL lighten/darken math — the same kind of derivation a designer would
 * do by hand when extending a brand color into a UI palette.
 */

export function hexToRgb(hex) {
  const h = hex.replace('#', '').trim()
  const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h
  const n = parseInt(full, 16)
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 }
}

export function rgbToHex(r, g, b) {
  const c = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0')
  return `#${c(r)}${c(g)}${c(b)}`
}

function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  let h, s
  const l = (max + min) / 2
  if (max === min) { h = s = 0 }
  else {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)); break
      case g: h = (b - r) / d + 2; break
      default: h = (r - g) / d + 4
    }
    h /= 6
  }
  return { h: h * 360, s: s * 100, l: l * 100 }
}

function hslToRgb(h, s, l) {
  h /= 360; s /= 100; l /= 100
  let r, g, b
  if (s === 0) { r = g = b = l }
  else {
    const hue2rgb = (p, q, t) => {
      if (t < 0) t += 1
      if (t > 1) t -= 1
      if (t < 1 / 6) return p + (q - p) * 6 * t
      if (t < 1 / 2) return q
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
      return p
    }
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s
    const p = 2 * l - q
    r = hue2rgb(p, q, h + 1 / 3)
    g = hue2rgb(p, q, h)
    b = hue2rgb(p, q, h - 1 / 3)
  }
  return { r: r * 255, g: g * 255, b: b * 255 }
}

/** Lighten (positive amount) or darken (negative) a hex color by an HSL-lightness delta (0-100 scale). */
export function adjustLightness(hex, deltaPercent) {
  const { r, g, b } = hexToRgb(hex)
  const hsl = rgbToHsl(r, g, b)
  const newL = Math.max(0, Math.min(100, hsl.l + deltaPercent))
  const rgb = hslToRgb(hsl.h, hsl.s, newL)
  return rgbToHex(rgb.r, rgb.g, rgb.b)
}

/** Blend two hex colors by a 0-1 ratio (0 = all colorA, 1 = all colorB). */
export function mix(colorA, colorB, ratio) {
  const a = hexToRgb(colorA), b = hexToRgb(colorB)
  return rgbToHex(
    a.r + (b.r - a.r) * ratio,
    a.g + (b.g - a.g) * ratio,
    a.b + (b.b - a.b) * ratio,
  )
}

export function hexToRgbTriplet(hex) {
  const { r, g, b } = hexToRgb(hex)
  return `${Math.round(r)} ${Math.round(g)} ${Math.round(b)}`
}

/** True if background is perceptually light (used to decide button text color and color-scheme). */
export function isLight(hex) {
  const { r, g, b } = hexToRgb(hex)
  // Standard relative luminance approximation, good enough for this decision
  return (0.299 * r + 0.587 * g + 0.114 * b) > 140
}

/**
 * Derive a full theme CSS variable map from 5 user-chosen colors.
 * Returns a plain object of { '--var-name': 'value' } pairs, ready to be
 * written into a <style> rule or applied as inline styles.
 */
export function deriveThemeVariables({ background, card, text, accent, border }) {
  const light = isLight(background)
  const dir = light ? -1 : 1 // darken for light themes' "raised" surfaces, lighten for dark themes'

  // Accent ramp: 50 (near-white/black) -> 900 (near-black/white), with 500
  // anchored exactly to the user's chosen accent color.
  const accentRamp = {
    50:  mix(accent, light ? '#000000' : '#ffffff', 0.94),
    100: mix(accent, light ? '#000000' : '#ffffff', 0.84),
    200: mix(accent, light ? '#000000' : '#ffffff', 0.64),
    300: mix(accent, light ? '#000000' : '#ffffff', 0.4),
    400: mix(accent, light ? '#000000' : '#ffffff', 0.18),
    500: accent,
    600: mix(accent, '#000000', 0.18),
    700: mix(accent, '#000000', 0.38),
    800: mix(accent, '#000000', 0.58),
    900: mix(accent, '#000000', 0.76),
  }

  // Neutral ramp derived from the background color's own hue, not a
  // generic grey — keeps the UI's neutrals feeling related to the chosen
  // palette rather than looking like a mismatched default grey was
  // dropped on top of a custom background.
  const s950 = background
  const s900 = adjustLightness(background, dir * 4)
  const s800 = adjustLightness(background, dir * 10)
  const s700 = adjustLightness(background, dir * 20)
  const s600 = adjustLightness(background, dir * 32)
  const s500 = mix(background, text, 0.5)
  const s400 = adjustLightness(text, -dir * 20)
  const s300 = text

  return {
    '--accent-50': accentRamp[50], '--accent-100': accentRamp[100], '--accent-200': accentRamp[200],
    '--accent-300': accentRamp[300], '--accent-400': accentRamp[400], '--accent-500': accentRamp[500],
    '--accent-600': accentRamp[600], '--accent-700': accentRamp[700], '--accent-800': accentRamp[800],
    '--accent-900': accentRamp[900],
    '--accent-500-rgb': hexToRgbTriplet(accent),
    '--s950': s950, '--s900': s900, '--s800': s800, '--s700': s700,
    '--s600': s600, '--s500': s500, '--s400': s400, '--s300': s300,
    '--bg-base':   background,
    '--bg-panel':  adjustLightness(background, dir * 2),
    '--bg-card':   card,
    '--bg-raised': adjustLightness(card, dir * 6),
    '--border-subtle':  border + '40',   // ~25% alpha, hex alpha suffix
    '--border-default': border + '80',   // ~50% alpha
    '--border-focus':   accent + 'b3',   // ~70% alpha
    '--text-primary':   text,
    '--text-secondary': mix(text, background, 0.32),
    '--text-tertiary':  mix(text, background, 0.42),
    '--glow-color': accent + '00',
    '--nav-active-bg': accent + '1a',    // ~10% alpha
    '--nav-active-text': accent,
    '--gradient-hero': 'none',
    '--radius-card': '14px',
    '--shadow-card': light
      ? '0 1px 3px rgba(0,0,0,.08), 0 6px 16px rgba(0,0,0,.06)'
      : '0 1px 3px rgba(0,0,0,.4), 0 4px 12px rgba(0,0,0,.15)',
    '--shadow-card-hover': light
      ? '0 3px 8px rgba(0,0,0,.1), 0 10px 24px rgba(0,0,0,.08)'
      : '0 4px 16px rgba(0,0,0,.35), 0 1px 4px rgba(0,0,0,.2)',
    '--radius-btn': '10px',
    '--btn-primary-text': light ? '#ffffff' : background,
    '--color-scheme': light ? 'light' : 'dark',
  }
}
