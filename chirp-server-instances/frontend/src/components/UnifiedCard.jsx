import { useEffect, useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { isCardOpen, setCardOpen } from '../lib/cardState'

/**
 * Single collapsible-card component shared by Bird Profile, Settings,
 * Statistics, and My Profile. Open/closed state is driven entirely by
 * lib/cardState.js — a global default (Settings → Display → "Expand cards
 * by default") plus a per-card override once a person has explicitly
 * clicked a given card's header. See cardState.js for the full design
 * rationale and the previously-separate mechanisms this replaces.
 *
 * id: REQUIRED, globally unique across the whole app. Callers namespace
 * their own ids by page, e.g. 'profile:about', 'stats:rarest-species',
 * 'settings:appearance', 'me:identity' — this file does not enforce the
 * namespacing convention itself (it has no way to know which page called
 * it), so every call site is responsible for keeping its own ids unique.
 *
 * domId: optional. Settings.jsx has a real jump-to-section feature that
 * scrollIntoView()s a specific DOM element by id (e.g. 'settings-notif') —
 * those exact id strings predate this component and other code depends on
 * them, so they're kept as the real DOM id via this separate prop rather
 * than overloading the cardState `id` (which uses its own ':'-namespaced
 * convention and isn't meant to double as a DOM id selector target).
 *
 * variant:
 *   'bordered' — header with bottom border + chevron, matches the look
 *                BirdProfile.jsx's CollapsibleCard already used.
 *   'stripe'   — colored top accent strip + icon chip, matches the look
 *                Statistics.jsx's ChartCard and UserProfile.jsx's Section
 *                already used.
 *   'plain'    — whole card is the button, single rotating chevron, no
 *                border split or top strip — matches Settings.jsx's own
 *                prior Section exactly, including scrollMarginTop for the
 *                jump-to-section feature.
 */
export default function UnifiedCard({
  id,
  domId,
  title,
  icon: Icon,
  variant = 'bordered',
  color = 'var(--accent-400)',
  headerRight,
  className = '',
  span = 1,
  fallbackOpen = null,
  children,
}) {
  if (!id) {
    // Fail loudly in dev rather than silently sharing state across cards —
    // a missing id would otherwise make every untitled card collapse/expand
    // together, which is a confusing bug to track down later.
    console.error('UnifiedCard requires a unique `id` prop; got:', id, title)
  }

  const [open, setOpen] = useState(() => isCardOpen(id, fallbackOpen))

  // Re-read if the global default changes while this card is mounted (e.g.
  // the person flips the Settings toggle in another tab, or — more
  // commonly — toggles it on this same Settings page and this card hasn't
  // been individually overridden, so it should visibly react immediately).
  useEffect(() => {
    const onDefaultChange = () => setOpen(isCardOpen(id, fallbackOpen))
    window.addEventListener('chirp-card-default-changed', onDefaultChange)
    return () => window.removeEventListener('chirp-card-default-changed', onDefaultChange)
  }, [id])

  const toggle = () => {
    setOpen(o => {
      const next = !o
      setCardOpen(id, next)
      return next
    })
  }

  if (variant === 'plain') {
    return (
      <div id={domId} className={`card p-5 ${className}`} style={{ animation: 'fadeIn .22s ease-out both', scrollMarginTop: '56px' }}>
        <button onClick={toggle} className="w-full flex items-center justify-between gap-2 text-left -m-1 p-1 rounded-lg transition-colors active:bg-[var(--bg-raised)]"
                style={{ marginBottom: open ? 16 : 0 }}>
          <h2 className="font-semibold text-gray-200 flex items-center gap-2">
            {Icon && <Icon size={16} className="text-chirp-500"/>}
            {title}
          </h2>
          <ChevronDown size={16} className="text-gray-500 flex-shrink-0 transition-transform duration-200"
                       style={{ transform: open ? 'rotate(180deg)' : 'none' }}/>
        </button>
        {open && children}
      </div>
    )
  }

  if (variant === 'stripe') {
    return (
      <div className={`card overflow-hidden flex flex-col ${span === 2 ? 'lg:col-span-2' : ''} ${className}`}
           style={{ border: '1px solid var(--border-default)' }}>
        <div style={{ height: 3, background: `linear-gradient(90deg,${color},transparent)`, flexShrink: 0 }}/>
        <button onClick={toggle}
                className="w-full flex items-center justify-between gap-2 text-left p-5 transition-colors active:bg-[var(--bg-raised)]"
                style={{ paddingBottom: open ? undefined : 20, flex: open ? undefined : 1 }}>
          <div className="flex items-center gap-2.5">
            {Icon && (
              <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                   style={{ background: color + '18', border: `1px solid ${color}30` }}>
                <Icon size={14} style={{ color }}/>
              </div>
            )}
            <h3 className="font-display font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>{title}</h3>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0" onClick={e => e.stopPropagation()}>
            {headerRight}
            <span onClick={toggle} className="tactile-press" style={{ cursor: 'pointer' }}>
              {open
                ? <ChevronUp size={15} style={{ color: 'var(--text-tertiary)' }}/>
                : <ChevronDown size={15} style={{ color: 'var(--text-tertiary)' }}/>}
            </span>
          </div>
        </button>
        {open && <div className="px-5 pb-5">{children}</div>}
      </div>
    )
  }

  // 'bordered' variant
  return (
    <div className={`card overflow-hidden ${className}`}>
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-4 py-3 border-b border-surface-700 hover:bg-surface-700/30 active:bg-surface-700/50 transition-colors text-left"
      >
        <span className="font-semibold text-gray-200 flex items-center gap-2 text-sm">
          {Icon && <Icon size={14} className="text-chirp-500"/>}
          {title}
        </span>
        <div className="flex items-center gap-3" onClick={e => e.stopPropagation()}>
          {headerRight}
          <span onClick={toggle} className="tactile-press" style={{ cursor: 'pointer' }}>
            {open ? <ChevronUp size={14} className="text-gray-500"/> : <ChevronDown size={14} className="text-gray-500"/>}
          </span>
        </div>
      </button>
      {open && children}
    </div>
  )
}
