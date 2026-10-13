/**
 * Chirp Theme System
 * Built-in themes (static CSS, compiled at build time) + user-created
 * custom themes (dynamic CSS, generated at runtime from 5 chosen colors
 * and injected via a <style> tag — see lib/themeColors.js for the color
 * derivation and applyCustomTheme() below for how it's wired in).
 * Persists in localStorage, applies [data-theme] to <html>.
 */

import { deriveThemeVariables } from './themeColors'

export const THEMES = [
  // ── Rich dark themes ──────────────────────────────────────────
  {
    id: 'forest',
    name: 'Forest',
    description: 'Amber on deep forest dark',
    swatch: ['#071009', '#eab308'],
    group: 'Rich',
  },
  {
    id: 'midnight',
    name: 'Midnight',
    description: 'Electric blue on true black',
    swatch: ['#050912', '#3b82f6'],
    group: 'Rich',
  },
  {
    id: 'dawn',
    name: 'Dawn',
    description: 'Rose gold on warm dark',
    swatch: ['#140c0e', '#f43f5e'],
    group: 'Rich',
  },
  {
    id: 'ocean',
    name: 'Ocean',
    description: 'Teal on deep navy',
    swatch: ['#061818', '#14b8a6'],
    group: 'Rich',
  },
  {
    id: 'ember',
    name: 'Ember',
    description: 'Orange on charcoal',
    swatch: ['#180d06', '#f97316'],
    group: 'Rich',
  },
  {
    id: 'slate',
    name: 'Slate',
    description: 'Purple on near-black',
    swatch: ['#100c1c', '#a855f7'],
    group: 'Rich',
  },

  // ── Soft / easy-on-eyes themes ────────────────────────────────
  {
    id: 'sage',
    name: 'Sage',
    description: 'Muted green, easy on eyes',
    swatch: ['#0c1610', '#22c55e'],
    group: 'Soft',
  },
  {
    id: 'dusk',
    name: 'Dusk',
    description: 'Warm lavender, relaxing',
    swatch: ['#160d1a', '#d946ef'],
    group: 'Soft',
  },
  {
    id: 'sand',
    name: 'Sand',
    description: 'Warm neutral, cream on brown',
    swatch: ['#1a1209', '#c8722f'],
    group: 'Soft',
  },
  {
    id: 'arctic',
    name: 'Arctic',
    description: 'Cool sky blue on deep slate',
    swatch: ['#081520', '#0ea5e9'],
    group: 'Soft',
  },
  {
    id: 'clay',
    name: 'Clay',
    description: 'Warm terracotta on rust brown',
    swatch: ['#1c110b', '#cf6b3e'],
    group: 'Soft',
  },
  {
    id: 'marsh',
    name: 'Marsh',
    description: 'Wetland blue-green, cool and quiet',
    swatch: ['#0a1512', '#3fb18d'],
    group: 'Soft',
  },

  // ── Accessibility ─────────────────────────────────────────────
  {
    id: 'contrast',
    name: 'High Contrast',
    description: 'WCAG AA — white on true black',
    swatch: ['#000000', '#ffff00'],
    group: 'Accessibility',
  },
  {
    id: 'contrast-light',
    name: 'High Contrast Light',
    description: 'WCAG AA — black on true white, for those who find light-on-dark harder to read',
    swatch: ['#ffffff', '#0a3ba8'],
    group: 'Accessibility',
  },

  // ── Distinct looks — not just a new color, a different feel ──
  {
    id: 'paper',
    name: 'Paper',
    description: 'Light field-journal — cream paper, sharp corners, serif headings',
    swatch: ['#f7f3e8', '#15803d'],
    group: 'Distinct Looks',
    iconId: 'paper',
  },
  {
    id: 'mono',
    name: 'Mono',
    description: 'Flat minimal — no glow, no grain, sharp corners',
    swatch: ['#0a0a0a', '#e8e8e8'],
    group: 'Distinct Looks',
    iconId: 'mono',
  },
  {
    id: 'terminal',
    name: 'Terminal',
    description: 'Retro CRT — phosphor green, monospace, scanlines',
    swatch: ['#010401', '#00ff41'],
    group: 'Distinct Looks',
    iconId: 'terminal',
  },
  {
    id: 'plate',
    name: 'Plate',
    description: 'Engraved field-guide plate — ink on aged paper, hairline rules',
    swatch: ['#ece5d3', '#2b2440'],
    group: 'Distinct Looks',
    iconId: 'plate',
  },
  {
    id: 'oscilloscope',
    name: 'Oscilloscope',
    description: 'Instrument panel — amber phosphor, calibrated ticks, CRT vignette',
    swatch: ['#0c0a06', '#ffb000'],
    group: 'Distinct Looks',
    iconId: 'oscilloscope',
  },
  {
    id: 'aviary',
    name: 'Aviary',
    description: 'Museum gallery — warm stone, clay accent, borderless cards',
    swatch: ['#e8e2d8', '#b5552e'],
    group: 'Distinct Looks',
    iconId: 'aviary',
  },
  {
    id: 'cornell',
    name: 'Cornell Lab',
    description: 'Ornithology institute — carnelian red, warm cream, friendly geometric type',
    swatch: ['#fdf8f0', '#b31b1b'],
    group: 'Distinct Looks',
    iconId: 'cornell',
  },
  {
    id: 'fieldnotebook',
    name: 'Field Notebook',
    description: 'Real paper — ruled lines, pencil grey, dog-eared warmth',
    swatch: ['#f0ead8', '#2c4a3e'],
    group: 'Distinct Looks',
    iconId: 'fieldnotebook',
  },
  {
    id: 'dracula',
    name: 'Dracula',
    description: 'The classic developer palette — purple, pink, and cyan on slate',
    swatch: ['#282a36', '#bd93f9'],
    group: 'Distinct Looks',
    iconId: 'dracula',
  },
  {
    id: 'nexrad',
    name: 'NEXRAD',
    description: 'Weather-radar migration tracking — green returns, rotating sweep',
    swatch: ['#030a0d', '#22e066'],
    group: 'Distinct Looks',
    iconId: 'nexrad',
  },
  {
    id: 'mothtrap',
    name: 'Moth Trap',
    description: 'Nocturnal field recording — UV blacklight glow on true black',
    swatch: ['#030103', '#c63dff'],
    group: 'Distinct Looks',
    iconId: 'mothtrap',
  },
  {
    id: 'spectrogram',
    name: 'Spectrogram',
    description: 'Styled after Chirp\'s own audio spectrograms — scrolling frequency-band colormap',
    swatch: ['#08031a', '#35b779'],
    group: 'Distinct Looks',
    iconId: 'spectrogram',
  },
  {
    id: 'migration',
    name: 'Migration',
    description: 'Night-sky starfield — the way real nocturnal migrants navigate',
    swatch: ['#04060d', '#f4d58d'],
    group: 'Distinct Looks',
    iconId: 'migration',
  },
  {
    id: 'roost',
    name: 'Roost',
    description: 'Warm wood-grain birdhouse — a little bird hops in the corner',
    swatch: ['#100a05', '#c9812f'],
    group: 'Distinct Looks',
    iconId: 'roost',
  },
  {
    id: 'echocave',
    name: 'Echo Cave',
    description: 'Rough stone roost — a bat pings the dark with real sonar rings',
    swatch: ['#06080b', '#29a89e'],
    group: 'Distinct Looks',
    iconId: 'echocave',
  },
  {
    id: 'dawnchorus',
    name: 'Dawn Chorus',
    description: 'The real birding term for the burst of song right at first light',
    swatch: ['#180e1a', '#ff8a1a'],
    group: 'Distinct Looks',
    iconId: 'dawnchorus',
  },
  {
    id: 'feather',
    name: 'Feather',
    description: 'Iridescent jewel tones, like a real hummingbird or peacock feather',
    swatch: ['#0d0818', '#c026d3'],
    group: 'Distinct Looks',
    iconId: 'feather',
  },
]

const STORAGE_KEY = 'chirp_theme'
const CUSTOM_THEMES_KEY = 'chirp_custom_themes'
const DEFAULT_THEME = 'forest'
const CUSTOM_STYLE_TAG_ID = 'chirp-custom-theme-style'

export function getStoredTheme() {
  try { return localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME } catch { return DEFAULT_THEME }
}

// ── Custom theme persistence ──────────────────────────────────────────────
// Stored as { [id]: { id, name, colors: {background, card, text, accent, border} } }
// — a plain object keyed by id rather than an array, so saving/renaming/
// deleting one custom theme never requires reading-modifying-rewriting
// every other saved custom theme's entry.
export function getCustomThemes() {
  try { return JSON.parse(localStorage.getItem(CUSTOM_THEMES_KEY) || '{}') }
  catch { return {} }
}

function _writeCustomThemes(map) {
  try { localStorage.setItem(CUSTOM_THEMES_KEY, JSON.stringify(map)) } catch {}
}

/** Save (or overwrite, if id already exists) a custom theme. Returns the saved theme's id. */
export function saveCustomTheme({ id, name, colors }) {
  const themes = getCustomThemes()
  const themeId = id || `custom-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  themes[themeId] = { id: themeId, name: name || 'Custom Theme', colors }
  _writeCustomThemes(themes)
  return themeId
}

export function deleteCustomTheme(id) {
  const themes = getCustomThemes()
  delete themes[id]
  _writeCustomThemes(themes)
  // If the deleted theme was active, fall back to default rather than
  // leaving the app pointed at a theme id that no longer resolves to
  // anything — applyTheme() would otherwise silently no-op on a dangling id.
  if (getStoredTheme() === id) applyTheme(DEFAULT_THEME)
}

function _isCustomThemeId(id) {
  return typeof id === 'string' && id.startsWith('custom-')
}

function _applyCustomThemeStyle(themeId, colors) {
  const vars = deriveThemeVariables(colors)
  const declarations = Object.entries(vars)
    .filter(([k]) => k !== '--color-scheme')
    .map(([k, v]) => `${k}: ${v};`)
    .join(' ')
  const scheme = vars['--color-scheme']

  let tag = document.getElementById(CUSTOM_STYLE_TAG_ID)
  if (!tag) {
    tag = document.createElement('style')
    tag.id = CUSTOM_STYLE_TAG_ID
    document.head.appendChild(tag)
  }
  // Scoped to this exact theme id, not a bare [data-theme] wildcard —
  // a wildcard would also match every BUILT-IN theme's [data-theme="x"]
  // attribute once this tag exists, silently overriding their variables
  // with whatever custom theme was last applied. Scoping to the specific
  // id means switching to a built-in theme is automatically correct with
  // no cleanup needed: the selector just stops matching anything.
  tag.textContent = `html[data-theme="${themeId}"] { color-scheme: ${scheme}; ${declarations} }`
}

function _clearCustomThemeStyle() {
  const tag = document.getElementById(CUSTOM_STYLE_TAG_ID)
  if (tag) tag.textContent = ''
}

// iOS 26 Safari (Liquid Glass) tints its toolbar/status area from
// theme-color and the page's fixed/sticky top bar; match the header
// panel color so the top edge reads as solid chrome instead of blur.
function _syncChromeColor() {
  try {
    const c = getComputedStyle(document.documentElement).getPropertyValue('--bg-panel').trim()
    if (!c) return
    let m = document.querySelector('meta[name="theme-color"]')
    if (!m) { m = document.createElement('meta'); m.name = 'theme-color'; document.head.appendChild(m) }
    m.content = c
    document.documentElement.style.backgroundColor = c
  } catch {}
}
if (typeof window !== 'undefined') window.addEventListener('chirp-theme-changed', _syncChromeColor)

export function applyTheme(themeId) {
  if (_isCustomThemeId(themeId)) {
    const custom = getCustomThemes()[themeId]
    if (custom) {
      document.documentElement.setAttribute('data-theme', themeId)
      _applyCustomThemeStyle(themeId, custom.colors)
      try { localStorage.setItem(STORAGE_KEY, themeId) } catch {}
      window.dispatchEvent(new CustomEvent('chirp-theme-changed', { detail: { theme: themeId } }))
      return
    }
    // Saved theme no longer exists (e.g. deleted in another tab) — fall
    // through to the default-theme path below rather than apply a
    // custom data-theme value with no matching style.
  }

  // Switching to (or staying on) a built-in theme — make sure no
  // leftover custom-theme CSS lingers. With the id-scoped selector above
  // this is already redundant for correctness, but clearing it keeps
  // the injected tag from silently growing stale content across many
  // theme switches in a single session.
  _clearCustomThemeStyle()

  const valid = THEMES.find(t => t.id === themeId)
  const id = valid ? themeId : DEFAULT_THEME
  document.documentElement.setAttribute('data-theme', id)
  try { localStorage.setItem(STORAGE_KEY, id) } catch {}
  window.dispatchEvent(new CustomEvent('chirp-theme-changed', { detail: { theme: id } }))
}

// Apply immediately on load to prevent flash of wrong theme
applyTheme(getStoredTheme())
