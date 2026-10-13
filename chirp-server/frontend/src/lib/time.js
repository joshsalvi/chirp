/**
 * Chirp — centralised time-zone formatting
 *
 * All date/time display goes through this module so changing the timezone
 * in Settings instantly affects every component.
 *
 * Usage:
 *   import { useTz, fmtTs, fmtDate, fmtTime, fmtAgo } from '../lib/time'
 *
 *   // Inside a component that needs the configured timezone:
 *   const { fmtTs, fmtDate, fmtTime, fmtAgo, timezone } = useTz()
 *
 *   // Or pass a timezone string directly (e.g. from a parent):
 *   fmtDate('2026-06-02T14:00:00', 'America/New_York')
 */

import { useState, useEffect } from 'react'
import { api } from './api'

// ── Module-level cache so every useTz() call shares the same value ────────────
let _cached = null       // 'America/New_York' etc, or null = browser default
let _listeners = new Set()

function _notify() { _listeners.forEach(fn => fn(_cached)) }

/** Called by Settings when the user saves a new timezone. */
export function setGlobalTimezone(tz) {
  _cached = tz || null
  _notify()
}

/** Called once on app startup to load timezone from server settings. */
export async function initTimezone() {
  try {
    const s = await api.settings.get()
    _cached = s.timezone || null
  } catch { /* leave null = browser default */ }
  _notify()
}

// ── Core helpers ──────────────────────────────────────────────────────────────

/**
 * Ensure a raw ISO string from the server (stored as naive UTC, no 'Z' suffix)
 * is treated as UTC when passed to `new Date()`.
 */
function _toDate(raw) {
  if (!raw) return new Date(NaN)
  const s = String(raw)
  // If it already has a timezone designator, use as-is
  if (/[Z+\-]\d*$/.test(s) && !s.endsWith('-')) return new Date(s)
  // Bare ISO string — stored UTC, add Z
  return new Date(s + 'Z')
}

/**
 * Format an ISO timestamp string in the given IANA timezone.
 * @param {string}  raw  - ISO timestamp from server (UTC, bare or with Z)
 * @param {string}  tz   - IANA timezone, e.g. 'America/New_York' (or undefined = browser)
 * @param {object}  opts - Intl.DateTimeFormat options overrides
 */
export function fmtTs(raw, tz, opts = {}) {
  const dt = _toDate(raw)
  if (isNaN(dt)) return '—'
  const options = {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit', second: '2-digit',
    hour12: true,
    ...opts,
    ...(tz ? { timeZone: tz } : {}),
  }
  try {
    return new Intl.DateTimeFormat('en-US', options).format(dt)
  } catch { return dt.toLocaleString() }
}

export function fmtDate(raw, tz, opts = {}) {
  return fmtTs(raw, tz, { month: 'short', day: 'numeric', year: 'numeric', ...opts,
    hour: undefined, minute: undefined, second: undefined, hour12: undefined })
}

export function fmtTime(raw, tz, opts = {}) {
  return fmtTs(raw, tz, { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true, ...opts,
    month: undefined, day: undefined, year: undefined })
}

export function fmtDateFull(raw, tz) {
  return fmtTs(raw, tz, {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true,
  })
}

/** "5 minutes ago" style relative time, no external library needed. */
export function fmtAgo(raw) {
  const dt = _toDate(raw)
  if (isNaN(dt)) return '—'
  const secs = Math.round((Date.now() - dt.getTime()) / 1000)
  if (secs < 5)   return 'just now'
  if (secs < 60)  return `${secs}s ago`
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`
  return `${Math.round(secs / 86400)}d ago`
}

// ── React hook ────────────────────────────────────────────────────────────────

/**
 * useTz() — returns timezone-aware formatting functions bound to the
 * currently configured timezone (from Settings).
 *
 * Components re-render automatically when the user changes timezone in Settings.
 */
export function useTz() {
  const [tz, setTz] = useState(_cached)

  useEffect(() => {
    // Subscribe to global changes
    _listeners.add(setTz)
    // If cache not loaded yet, fetch now
    if (_cached === null) {
      api.settings.get().then(s => {
        _cached = s.timezone || null
        _notify()
      }).catch(() => {})
    }
    return () => _listeners.delete(setTz)
  }, [])

  return {
    timezone: tz,
    fmtTs:   (raw, opts) => fmtTs(raw, tz, opts),
    fmtDate: (raw, opts) => fmtDate(raw, tz, opts),
    fmtTime: (raw, opts) => fmtTime(raw, tz, opts),
    fmtDateFull: (raw)   => fmtDateFull(raw, tz),
    fmtAgo,
  }
}

// ── Editing a recording's time ────────────────────────────────────────────────
const _pad = n => String(n).padStart(2, '0')

function _wallParts(date, tz) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz || undefined, hourCycle: 'h23',
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).formatToParts(date)
  const p = Object.fromEntries(parts.map(x => [x.type, x.value]))
  return { y: +p.year, mo: +p.month, d: +p.day, h: +p.hour % 24, mi: +p.minute, s: +p.second }
}

/** Server timestamp -> 'YYYY-MM-DDTHH:MM:SS' wall time in tz, for <input type="datetime-local">. */
export function toLocalInput(raw, tz) {
  const dt = _toDate(raw)
  if (isNaN(dt)) return ''
  try {
    const w = _wallParts(dt, tz)
    return `${w.y}-${_pad(w.mo)}-${_pad(w.d)}T${_pad(w.h)}:${_pad(w.mi)}:${_pad(w.s)}`
  } catch { return '' }
}

/** 'YYYY-MM-DDTHH:MM[:SS]' wall time in tz -> ISO 8601 UTC string ('' if unreadable). */
export function fromLocalInput(value, tz) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/.exec(value || '')
  if (!m) return ''
  const [y, mo, d, h, mi, s] = m.slice(1).map(x => +(x || 0))
  const want = Date.UTC(y, mo - 1, d, h, mi, s)
  let t = want
  try {
    // Two passes settle the zone's offset at that wall time (DST edges).
    for (let i = 0; i < 2; i++) {
      const w = _wallParts(new Date(t), tz)
      t += want - Date.UTC(w.y, w.mo - 1, w.d, w.h, w.mi, w.s)
    }
  } catch { t = new Date(y, mo - 1, d, h, mi, s).getTime() }
  return new Date(t).toISOString()
}

const _MON = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 }

/**
 * Wall time from a recorder's file name ('YYYY-MM-DDTHH:MM:SS'), or ''.
 * HaikuBox (Oct_1_2026_121158_AM), YYYYMMDD_HHMMSS (Chirp, AudioMoth,
 * Song Meter) and YYYY-MM-DD HH-MM-SS. Same patterns as the server's
 * services/recorded_time.py.
 */
export function timeFromFilename(name) {
  if (!name) return ''
  let y, mo, d, h, mi, s
  let m = /(?<![A-Za-z])(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[_\- ](\d{1,2})[_\- ,]+(\d{4})[_\- ]+(\d{1,2})(\d{2})(\d{2})[_\- ]?(AM|PM)?/i.exec(name)
  if (m) {
    mo = _MON[m[1].slice(0, 3).toLowerCase()]; d = +m[2]; y = +m[3]; h = +m[4]; mi = +m[5]; s = +m[6]
    if (m[7]) h = (h % 12) + (m[7].toUpperCase() === 'PM' ? 12 : 0)
  } else {
    m = /(?<!\d)(20\d{2})(\d{2})(\d{2})[_\-T ]?(\d{2})(\d{2})(\d{2})(?!\d)/.exec(name)
      || /(?<!\d)(20\d{2})-(\d{2})-(\d{2})[_T ](\d{2})[.:-](\d{2})[.:-](\d{2})(?!\d)/.exec(name)
    if (!m) return ''
    ;[y, mo, d, h, mi, s] = m.slice(1).map(Number)
  }
  const chk = new Date(Date.UTC(y, mo - 1, d, h, mi, s))
  if (chk.getUTCMonth() !== mo - 1 || chk.getUTCDate() !== d || h > 23 || mi > 59 || s > 59) return ''
  return `${y}-${_pad(mo)}-${_pad(d)}T${_pad(h)}:${_pad(mi)}:${_pad(s)}`
}
