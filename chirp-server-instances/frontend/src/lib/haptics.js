/**
 * App-wide haptic feedback for the iOS app (installed once by App.jsx; does
 * nothing in a browser). One set of document listeners instead of a call in
 * every component:
 *  - taps on buttons and links: light; tab bar and section navigation:
 *    medium; delete/remove-style buttons: heavy
 *  - toggles, checkboxes, radios and pickers: light when they change
 *  - sliders: a selection tick while the value moves
 *  - events: a new detection arriving (light), settings saved, uploads,
 *    copies and shares (success), failed actions (error)
 * An element (or an ancestor) can choose its own feedback with
 * data-haptic="light|medium|heavy|success|warning|none"; code elsewhere
 * calls hapticEvent(kind) without touching the native bridge.
 */
import { native, isNative } from '../native'

const TAP = 'button, a[href], [role="button"], [role="tab"], summary'
const DESTRUCTIVE = /^\s*(delete|remove|purge|discard|sign out|log out|clear|revoke|empty)\b/i
const KINDS = new Set(['light', 'medium', 'heavy', 'success', 'warning', 'error', 'selection'])

export function hapticEvent(kind) {
  window.dispatchEvent(new CustomEvent('chirp-haptic', { detail: kind }))
}

let lastAt = 0
function fire(kind, { force = false } = {}) {
  const now = Date.now()
  if (!force && now - lastAt < 60) return // a label click also fires its input's change
  lastAt = now
  if (KINDS.has(kind)) native.haptic[kind]().catch(() => {})
}

function chosen(el) {
  const v = el.closest('[data-haptic]')?.getAttribute('data-haptic')
  return v || null
}

function onClick(e) {
  const el = e.target.closest?.(TAP)
  if (!el || el.disabled || el.getAttribute('aria-disabled') === 'true') return
  const pick = chosen(el)
  if (pick === 'none') return
  if (pick) return fire(pick)
  if (el.closest('nav')) return fire('medium')
  if (DESTRUCTIVE.test(el.textContent || '') || /danger|red/.test(el.className || '')) return fire('heavy')
  fire('light')
}

function onChange(e) {
  const el = e.target
  if (!(el instanceof HTMLElement) || chosen(el) === 'none') return
  if (el.matches('input[type="checkbox"], input[type="radio"]')) fire(chosen(el) || 'light')
  else if (el.matches('select')) fire('selection')
}

let lastTick = 0
function onInput(e) {
  if (!e.target.matches?.('input[type="range"]') || chosen(e.target) === 'none') return
  const now = Date.now()
  if (now - lastTick < 35) return
  lastTick = now
  native.haptic.selection().catch(() => {})
}

// Outcomes always play, even right after the tap that caused them.
const onSaved = () => fire('success', { force: true })
const onDetection = () => fire('light', { force: true })
const onEvent = e => fire(e.detail, { force: true })

export function installHaptics() {
  if (!isNative()) return () => {}
  document.addEventListener('click', onClick, true)
  document.addEventListener('change', onChange, true)
  document.addEventListener('input', onInput, true)
  window.addEventListener('chirp-settings-saved', onSaved)
  window.addEventListener('chirp-new-detection', onDetection)
  window.addEventListener('chirp-haptic', onEvent)
  return () => {
    document.removeEventListener('click', onClick, true)
    document.removeEventListener('change', onChange, true)
    document.removeEventListener('input', onInput, true)
    window.removeEventListener('chirp-settings-saved', onSaved)
    window.removeEventListener('chirp-new-detection', onDetection)
    window.removeEventListener('chirp-haptic', onEvent)
  }
}
