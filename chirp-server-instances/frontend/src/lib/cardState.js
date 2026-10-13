/**
 * Unified per-card expand/collapse preference system.
 *
 * Covers every collapsible card across Bird Profile, Settings, Statistics,
 * and My Profile. Two layers, in priority order:
 *
 *   1. Per-card override — once a person has explicitly clicked a specific
 *      card's header, THAT card remembers its own open/closed state forever
 *      (or until they toggle it again), regardless of the global default.
 *   2. Global default — controls every card that has never been individually
 *      touched. Two values: 'expanded' (everything open on first visit) or
 *      'collapsed' (everything closed on first visit). Configurable in
 *      Settings → Display.
 *
 * This intentionally replaces three previously-separate, inconsistent
 * mechanisms that existed before this module:
 *   - BirdProfile.jsx's CollapsibleCard: a hardcoded `defaultOpen` boolean
 *     prop set individually per usage in JSX, with zero persistence — every
 *     page load reset every card to whatever the prop said, ignoring
 *     whatever the person had toggled last time.
 *   - Settings.jsx's own bespoke Section + COLLAPSE_STORAGE_KEY: real
 *     localStorage persistence, but only ever "default to collapsed unless
 *     explicitly opened before" — no way to flip that default, and a
 *     separate storage key/shape from everything else.
 *   - Statistics.jsx's ChartCard and UserProfile.jsx's Section: no collapse
 *     capability at all; every card was always fully expanded.
 *
 * Storage shape (single localStorage key, one JSON object for the whole
 * app): { _globalDefault: 'expanded' | 'collapsed', [cardId]: 'open' | 'closed' }
 * Per-card entries are written ONLY when a person actually clicks a card's
 * header — a card with no entry has never been touched and falls through
 * to _globalDefault. This is deliberately the same "only write on explicit
 * action" shape Settings.jsx's prior mechanism already used (map[id] ===
 * 'open' / true), so existing real stored preferences are preserved and
 * reinterpreted under the new system rather than being silently reset to a
 * default the person never asked for. See migrateLegacySettingsCollapse()
 * below for the one-time import of those existing values.
 */

const STORAGE_KEY = 'chirp_card_state'
const LEGACY_SETTINGS_KEY = 'chirp_settings_collapsed'

export const GLOBAL_DEFAULTS = { EXPANDED: 'expanded', COLLAPSED: 'collapsed' }

function _read() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

function _write(map) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(map)) } catch {}
}

/**
 * One-time migration: Settings.jsx previously stored its own per-card
 * collapse state under a different key ('chirp_settings_collapsed') with a
 * different default philosophy (always-collapsed-unless-opened). Reads it
 * once, folds any real per-card entries into the new unified store under
 * settings:<id> namespacing (so they can never collide with a Bird Profile
 * card that happens to share an id string), then leaves the legacy key in
 * place untouched — this is a read-and-merge, not a destructive migration,
 * so nothing is lost if this runs more than once or something goes wrong.
 * Safe to call on every app load; it's a no-op once the new store already
 * has its own real entries for those ids.
 */
export function migrateLegacySettingsCollapse() {
  let legacy
  try { legacy = JSON.parse(localStorage.getItem(LEGACY_SETTINGS_KEY) || '{}') }
  catch { return }
  if (!legacy || typeof legacy !== 'object' || Object.keys(legacy).length === 0) return

  const map = _read()
  let changed = false
  for (const [id, val] of Object.entries(legacy)) {
    const namespacedId = `settings:${id}`
    if (namespacedId in map) continue  // already migrated or already explicitly set under the new system
    // Legacy shape: 'open' meant explicitly expanded, `true` meant
    // explicitly collapsed (see the old Section component's toggle()).
    map[namespacedId] = val === 'open' ? 'open' : 'closed'
    changed = true
  }
  if (changed) _write(map)
}

export function getGlobalDefault() {
  const map = _read()
  return map._globalDefault === GLOBAL_DEFAULTS.EXPANDED ? GLOBAL_DEFAULTS.EXPANDED : GLOBAL_DEFAULTS.COLLAPSED
}

export function setGlobalDefault(value) {
  const map = _read()
  map._globalDefault = value === GLOBAL_DEFAULTS.EXPANDED ? GLOBAL_DEFAULTS.EXPANDED : GLOBAL_DEFAULTS.COLLAPSED
  _write(map)
  // Let every currently-mounted UnifiedCard on the page re-read immediately,
  // without requiring a full reload — same broadcast pattern already used
  // elsewhere in this codebase for cross-component settings updates (see
  // the existing 'chirp-settings-saved' window event Dashboard.jsx already
  // listens for).
  try { window.dispatchEvent(new Event('chirp-card-default-changed')) } catch {}
}

/**
 * Resolve whether a specific card should render open right now.
 * cardId must be globally unique across the whole app (callers namespace
 * their own ids, e.g. 'profile:about', 'stats:rarest-species').
 *
 * fallbackOpen: optional. If the person has never explicitly toggled this
 * card, use this instead of the global default — for the handful of cards
 * that have a deliberate, specific reason to start open (or closed)
 * regardless of the app-wide setting (e.g. the Photo Gallery card, which
 * was explicitly requested to default open). Once the person actually
 * clicks the card, their choice is remembered as a real override and wins
 * forever after, exactly like every other card — this only affects what
 * happens before they've ever touched it.
 */
export function isCardOpen(cardId, fallbackOpen = null) {
  const map = _read()
  const override = map[cardId]
  if (override === 'open') return true
  if (override === 'closed') return false
  if (fallbackOpen !== null) return fallbackOpen
  return getGlobalDefault() === GLOBAL_DEFAULTS.EXPANDED
}

export function setCardOpen(cardId, open) {
  const map = _read()
  map[cardId] = open ? 'open' : 'closed'
  _write(map)
}

/** Clear every per-card override, reverting every card to the global default. */
export function resetAllCardOverrides() {
  const map = _read()
  const kept = { _globalDefault: map._globalDefault }
  _write(kept)
  try { window.dispatchEvent(new Event('chirp-card-default-changed')) } catch {}
}
