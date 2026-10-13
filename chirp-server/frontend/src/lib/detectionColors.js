// Detection-color palettes — which color each detected species gets,
// in the detection list, the waveform, and the spectrogram overlay.
//
// Added directly after a report, with a screenshot: with only two
// species in a recording (Downy Woodpecker, Cooper's Hawk), the two
// got assigned red and orange — adjacent hues on the old fixed wheel,
// hard to tell apart at a glance on a small screen. The root cause
// wasn't the colors themselves, it was the ASSIGNMENT: species got
// palette[0], palette[1], palette[2]... in detection order, so any
// recording with few species always landed on whichever colors happen
// to sit next to each other at the start of the wheel, regardless of
// how many total colors the palette has to offer.
//
// Fixed by spreading assigned colors evenly around the wheel based on
// how many species are ACTUALLY present (see pickSpeciesColors below)
// — 2 species now land on opposite sides of the wheel, 3 species land
// 120° apart, and so on — rather than always starting from index 0.
// Also added multiple selectable palettes (see PALETTES below), since
// which colors count as "different enough" is somewhat a matter of
// taste and vision, not just something one fixed default can solve for
// everyone.

export const PALETTES = {
  vivid: {
    label: 'Vivid',
    description: 'The original, high-saturation rainbow wheel.',
    colors: [
      '#ef4444', // Red
      '#f97316', // Orange
      '#eab308', // Yellow
      '#84cc16', // Yellow-green
      '#22c55e', // Green
      '#14b8a6', // Teal
      '#06b6d4', // Cyan
      '#3b82f6', // Blue
      '#6366f1', // Indigo
      '#a855f7', // Purple
      '#ec4899', // Pink
      '#f43f5e', // Rose
    ],
  },
  colorblind_safe: {
    label: 'Colorblind Safe',
    description: 'Okabe–Ito palette — chosen to stay distinct under the common forms of color vision deficiency.',
    colors: [
      '#E69F00', // Orange
      '#56B4E9', // Sky blue
      '#009E73', // Bluish green
      '#F0E442', // Yellow
      '#0072B2', // Blue
      '#D55E00', // Vermillion
      '#CC79A7', // Reddish purple
      '#999999', // Neutral gray (in place of the original's pure black, which reads as invisible on this app's dark background)
    ],
  },
  pastel: {
    label: 'Pastel',
    description: 'Softer, lower-saturation tones for a gentler look.',
    colors: [
      '#fca5a5', // Red
      '#fdba74', // Orange
      '#fde047', // Yellow
      '#bef264', // Yellow-green
      '#86efac', // Green
      '#5eead4', // Teal
      '#67e8f9', // Cyan
      '#93c5fd', // Blue
      '#a5b4fc', // Indigo
      '#d8b4fe', // Purple
      '#f9a8d4', // Pink
      '#fda4af', // Rose
    ],
  },
  high_contrast: {
    label: 'High Contrast',
    description: 'Maximally distinct hues and brightness, for quick scanning at a glance.',
    colors: [
      '#ffffff', // White
      '#facc15', // Yellow
      '#22d3ee', // Cyan
      '#f472b6', // Pink
      '#4ade80', // Green
      '#818cf8', // Indigo
      '#fb923c', // Orange
      '#c084fc', // Purple
    ],
  },
}

export const DEFAULT_PALETTE = 'vivid'

/**
 * Returns { speciesName: colorHex } for a list of common names, in
 * FIRST-SEEN order (matching every existing caller's own
 * dict.fromkeys()/Set-based dedup) — but with colors spread evenly
 * around the chosen palette's own wheel based on the TOTAL number of
 * species present, not assigned sequentially from index 0. This is
 * the one piece every caller (detection list, waveform highlight,
 * spectrogram legend) should share, so all three always agree on
 * which color belongs to which species within one recording.
 */
export function pickSpeciesColors(uniqueSpeciesNames, paletteKey = DEFAULT_PALETTE) {
  const palette = PALETTES[paletteKey] || PALETTES[DEFAULT_PALETTE]
  const colors = palette.colors
  const n = uniqueSpeciesNames.length
  const result = {}
  uniqueSpeciesNames.forEach((name, i) => {
    // Evenly spaced index into the palette's own wheel: for n species,
    // the i-th one sits at i * (wheelSize / n) around the wheel — e.g.
    // 2 species out of a 12-color wheel land on indices 0 and 6
    // (opposite sides), 3 species land on 0, 4, 8 (120° apart), etc.
    // n=1 is a no-op (index 0) since there's nothing to spread apart.
    const idx = n <= 1 ? 0 : Math.round((i * colors.length) / n) % colors.length
    result[name] = colors[idx]
  })
  return result
}
