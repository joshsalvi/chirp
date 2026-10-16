import { useEffect, useRef, useState, useMemo, lazy, Suspense } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
// Recharts loads with the charts, not with the Dashboard (see DashboardBarChart).
const DashboardBarChart = lazy(() => import('./DashboardBarChart'))
import { Mic, Activity, Clock, ArrowRight, Feather, Sparkles, MessageSquare, X, Flame, Leaf, Info, ChevronDown, RefreshCw, BookOpen, Sun, Sunrise, Sunset, Moon } from 'lucide-react'
import { BirdIcon, BatIcon } from './BirdBatIcons'
import { api, mediaUrl } from '../lib/api'
import { useTz } from '../lib/time'
import ChirpLogo from './ChirpLogo'
import { isCardOpen, setCardOpen } from '../lib/cardState'

// Small helper for Dashboard sections with their own custom, interactive
// header (period buttons, an embedded toggle link, etc.) that can't just
// be handed to UnifiedCard's plain title prop. Uses the exact same
// cardState persistence everything else in the app uses, just with a
// bare chevron rather than UnifiedCard's full header.
function useSectionCollapse(id, fallbackOpen = true) {
  const [open, setOpen] = useState(() => isCardOpen(id, fallbackOpen))
  const toggle = () => setOpen(o => { setCardOpen(id, !o); return !o })
  return [open, toggle]
}
const STAT_TINTS = {
  mic:      { bg: 'linear-gradient(135deg, rgba(251,191,36,.18), rgba(217,119,6,.10))', fg: 'var(--pastel-amber)' },
  bird:     { bg: 'linear-gradient(135deg, rgba(134,239,172,.18), rgba(22,163,74,.10))', fg: '#4ade80' },
  sparkles: { bg: 'linear-gradient(135deg, rgba(196,181,253,.18), rgba(124,58,237,.10))', fg: '#c4b5fd' },
  clock:    { bg: 'linear-gradient(135deg, rgba(125,211,252,.18), rgba(3,105,161,.10))', fg: 'var(--pastel-sky)' },
}

// Per-card vertical offset for a subtle layered-depth feel across the stat
// row, instead of four flat boxes sitting at identical height. Small
// enough not to misalign with adjacent rows/cards, applied only at lg+
// breakpoints via inline transform (cheap, no layout reflow concerns since
// it's a transform, not a margin/position change).
const STAT_LIFT = [0, -4, -7, -2]

// Animates a stat card's number counting up to its new value instead of
// just appearing — a small bit of polish, kept genuinely optional:
// respects prefers-reduced-motion (same matchMedia check Tutorial.jsx
// already uses elsewhere in this app, for consistency) by jumping
// straight to the final value with no animation at all. Falls back to
// rendering the raw string completely unchanged for anything that isn't
// actually a plain formatted number — "Last Detection"'s value is a
// relative-time string like "2m ago", not a count, and forcing that
// through a numeric tween would either crash or produce nonsense.
function CountUp({ value }) {
  const [display, setDisplay] = useState(value)
  const prevNumRef = useRef(null)
  const rafRef = useRef(null)

  useEffect(() => {
    const numeric = typeof value === 'string' ? Number(value.replace(/,/g, '')) : Number(value)
    const isPlainNumber = Number.isFinite(numeric) && String(value).replace(/,/g, '') === String(Math.trunc(numeric))

    if (!isPlainNumber) {
      // Not a count (e.g. "—" or a relative-time string) — show as-is,
      // no animation attempted.
      setDisplay(value)
      prevNumRef.current = null
      return
    }

    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const from = prevNumRef.current ?? 0 // first mount counts up from 0; later updates count from the previous value
    prevNumRef.current = numeric

    if (reduceMotion || from === numeric) {
      setDisplay(numeric.toLocaleString())
      return
    }

    const duration = 700
    const start = performance.now()
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3) // ease-out cubic — fast start, gentle settle, not a linear/mechanical count
      const current = Math.round(from + (numeric - from) * eased)
      setDisplay(current.toLocaleString())
      if (t < 1) rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [value])

  return <>{display}</>
}

function StatCard({ icon: Icon, label, value, sub, to, delay = 0, tint = 'bird', lift = 0, animateValue = false }) {
  const t = STAT_TINTS[tint] || STAT_TINTS.bird
  const inner = (
    <div className="p-5 flex flex-col gap-3" style={{ animationDelay: `${delay}ms` }}>
      <div className="flex items-start justify-between">
        <div className="p-2 rounded-lg transition-transform duration-300 group-hover:scale-110" style={{ background: t.bg }}>
          <Icon size={16} style={{ color: t.fg }}/>
        </div>
        {to && <ArrowRight size={14} className="transition-transform duration-200 group-hover:translate-x-0.5"
                            style={{ color: 'var(--text-tertiary)' }}/>}
      </div>
      <div>
        <div className="stat-value">{animateValue ? <CountUp value={value}/> : value}</div>
        <div className="stat-label">{label}</div>
        {sub && <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>{sub}</p>}
      </div>
    </div>
  )
  const liftStyle = { '--tint-color': t.fg, ...(lift ? { transform: `translateY(${lift}px)` } : {}) }
  if (to) return <Link to={to} className="card-hover stat-tile group block animate-slide-up" style={liftStyle}>{inner}</Link>
  return <div className="card stat-tile group animate-slide-up" style={liftStyle}>{inner}</div>
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="card px-3 py-2 text-xs" style={{ boxShadow: '0 8px 32px rgba(0,0,0,.5)' }}>
      <p style={{ color: 'var(--text-secondary)' }}>{label}</p>
      <p className="font-semibold mt-0.5" style={{ color: 'var(--accent-400)' }}>{payload[0].value} detections</p>
    </div>
  )
}

function toDate(raw) {
  if (!raw) return null
  return new Date(raw.endsWith('Z') ? raw : raw + 'Z')
}

// Purely decorative pairing of an icon + label with the existing
// time-of-day greeting logic already used for "Good morning/afternoon/
// evening" — kept as its own small function rather than inlined so the
// three thresholds only ever need to agree with themselves in one place.
function hourInTimezone(timezone) {
  // The greeting text/icon should reflect what time it is at
  // the configured location, not the browser's own local clock — this
  // dashboard already shows a location-aware date line right next to
  // it, so a phone in a different timezone than the deployment
  // shouldn't get a greeting/icon out of sync with that. Falls back to
  // the browser's own local time if timezone isn't set yet or is
  // invalid, same as new Date().getHours() always did.
  try {
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: timezone, hour: 'numeric', hour12: false }).formatToParts(new Date())
    const hourPart = parts.find(p => p.type === 'hour')
    // hour12:false can report "24" for midnight in some engines — a
    // documented Intl quirk, not a bug in this code — so normalize.
    return hourPart ? Number(hourPart.value) % 24 : new Date().getHours()
  } catch {
    return new Date().getHours()
  }
}

function greetingMeta(hour) {
  // Label buckets (morning/afternoon/evening) stay the coarse 3-way
  // split people say out loud. The ICON is deliberately on its
  // OWN, finer thresholds — tying it to the same 3 buckets is exactly
  // what put a sunset icon on the entire noon-to-6pm span, showing a
  // sunset at 1pm. A sunset icon should mean sunset, not "afternoon."
  const label = hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'
  if (hour < 6 || hour >= 20)  return { Icon: Moon,    label, color: '#a78bfa' }
  if (hour < 8)                return { Icon: Sunrise, label, color: '#fb923c' }
  if (hour < 17)               return { Icon: Sun,     label, color: '#fbbf24' }
  return                             { Icon: Sunset,  label, color: '#fb923c' }
}

function SummaryBirdCard({ bird, label }) {
  if (!bird) return (
    <div className="flex items-center justify-center h-full rounded-xl" style={{ background: 'var(--bg-raised)', minHeight: 140 }}>
      <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>No detections yet</p>
    </div>
  )
  const inner = (
    <div className="relative h-full rounded-xl overflow-hidden transition-all hover:opacity-95 group"
         style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', minHeight: 140 }}>
      {bird.photo_url ? (
        <>
          <img src={mediaUrl(bird.photo_url)} alt="" aria-hidden="true"
               className="absolute inset-0 w-full h-full object-cover"
               style={{ filter: 'blur(20px) brightness(0.55) saturate(1.1)', transform: 'scale(1.15)' }}/>
          <div className="absolute inset-0 flex items-center justify-center transition-transform duration-300 group-hover:scale-[1.03]">
            <img src={mediaUrl(bird.photo_url)} alt=""
                 className="max-w-full max-h-full w-auto h-auto object-contain"
                 onError={e => { e.target.style.display = 'none' }}/>
          </div>
        </>
      ) : (
        <div className="absolute inset-0 flex items-center justify-center">
          <BirdIcon size={32} style={{ color: "var(--text-tertiary)" }}/>
        </div>
      )}
      <div className="absolute inset-0" style={{ background: 'linear-gradient(to top, rgba(0,0,0,.85), rgba(0,0,0,.15) 60%, transparent)' }}/>
      <div className="absolute bottom-0 left-0 right-0 p-3">
        <p className="text-[11px] font-medium uppercase tracking-wide" style={{ color: 'rgba(255,255,255,.65)' }}>{label}</p>
        <p className="text-lg font-bold leading-tight truncate" style={{ color: '#fff', fontFamily: "'Lora', serif" }}>{bird.common_name}</p>
        <p className="text-xs mt-0.5" style={{ color: 'rgba(255,255,255,.7)' }}>
          {bird.count} detection{bird.count === 1 ? '' : 's'} · {(bird.avg_confidence * 100).toFixed(0)}% avg confidence
        </p>
      </div>
    </div>
  )
  return bird.bird_profile_id ? <Link to={`/library/${bird.bird_profile_id}`} className="block h-full">{inner}</Link> : inner
}

function DailyWeeklySummary({ summary, summaryPeriod, setSummaryPeriod, timezone }) {
  const [open, toggleOpen] = useSectionCollapse('dashboard:daily-weekly', true)
  if (!summary) return null
  const p = summary[summaryPeriod]
  const isDaily = summaryPeriod === 'daily'

  const bucketChartData = (p.buckets || []).map(b => {
    let label = b.label
    if (isDaily) {
      // "2026-06-18T14:00" -> local hour
      const d = new Date(b.label + ':00Z')
      if (!isNaN(d)) {
        const tz = timezone || Intl.DateTimeFormat().resolvedOptions().timeZone
        label = String(parseInt(d.toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: tz }), 10)).padStart(2, '0')
      }
    } else {
      const d = new Date(b.label + 'T00:00:00Z')
      if (!isNaN(d)) label = d.toLocaleDateString('en', { weekday: 'short', timeZone: timezone || 'UTC' })
    }
    return { label, detections: b.detections, recordings: b.recordings }
  })

  const periodWord = isDaily ? "Today's" : "This Week's"
  const otherKey = isDaily ? 'weekly' : 'daily'
  const otherWord = isDaily ? 'this week' : 'today'

  return (
    <div className="card p-5 mb-4 animate-stagger-2">
      <div onClick={toggleOpen} role="button" tabIndex={0}
           onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') toggleOpen() }}
           className="flex items-center justify-between mb-4 flex-wrap gap-2 cursor-pointer">
        <h2 className="font-display text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          <button onClick={e => { e.stopPropagation(); setSummaryPeriod(otherKey) }}
                  className="transition-colors hover:underline"
                  style={{ color: 'var(--accent-400)' }}
                  title={`Switch to ${otherWord}`}>
            {periodWord}
          </button>
          <span style={{ color: 'var(--text-primary)' }}> Summary</span>
        </h2>
        <ChevronDown size={16} style={{
          color: 'var(--text-tertiary)',
          transform: open ? 'none' : 'rotate(-90deg)',
          transition: 'transform .2s',
          flexShrink: 0,
        }}/>
      </div>

      {open && (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-stretch">
        {/* Most common bird + totals */}
        <div className="flex flex-col gap-3 h-full">
          <div className="flex-1">
            <SummaryBirdCard bird={p.most_common_bird} label="Most common"/>
          </div>
          <div className="grid grid-cols-2 gap-2 mt-auto">
            <div className="p-2.5 rounded-xl text-center" style={{ background: 'var(--bg-raised)' }}>
              <p className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>{p.total_detections}</p>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Detections</p>
            </div>
            <div className="p-2.5 rounded-xl text-center" style={{ background: 'var(--bg-raised)' }}>
              <p className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>{p.total_recordings}</p>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Recordings</p>
            </div>
          </div>
        </div>

        {/* Mini activity chart */}
        <div className="flex flex-col h-full">
          <p className="text-xs mb-2" style={{ color: 'var(--text-tertiary)' }}>
            Detections per {isDaily ? 'hour' : 'day'}
          </p>
          <div className="flex-1" style={{ minHeight: 120 }}>
            {bucketChartData.some(b => b.detections > 0) ? (
              <Suspense fallback={null}>
                <DashboardBarChart data={bucketChartData} yKey="detections" tooltip={<CustomTooltip/>}
                  margin={{ top: 4, right: 4, bottom: 0, left: -28 }} gap="15%" tickSize={9} yWidth={20}
                  interval={isDaily ? 3 : 0} radius={[3, 3, 0, 0]} fill="var(--accent-700)"/>
              </Suspense>
            ) : (
              <div className="h-full flex items-center justify-center" style={{ color: 'var(--text-tertiary)' }}>
                <p className="text-xs">No activity {isDaily ? 'today' : 'this week'}</p>
              </div>
            )}
          </div>
        </div>

        {/* Rarest species */}
        <div className="flex flex-col h-full">
          <p className="text-xs mb-2" style={{ color: 'var(--text-tertiary)' }}>
            Rarest {isDaily ? 'today' : 'this week'}
          </p>
          {p.rarest_species?.length > 0 ? (
            <div className="space-y-1.5 flex-1 flex flex-col justify-between">
              {p.rarest_species.map((b, i) => {
                const row = (
                  <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg transition-colors hover:opacity-90 animate-fade-in"
                       style={{ background: 'var(--bg-raised)', animationDelay: `${i * 40}ms` }}>
                    {b.photo_url ? (
                      <img src={mediaUrl(b.photo_url)} alt="" className="w-6 h-6 rounded-md object-cover flex-shrink-0" loading="lazy"
                           onError={e => { e.target.style.display = 'none' }}/>
                    ) : (
                      <div className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0" style={{ background: 'var(--nav-active-bg)' }}>
                        <BirdIcon size={11} style={{ color: "var(--text-tertiary)" }}/>
                      </div>
                    )}
                    <p className="text-xs truncate flex-1 min-w-0" style={{ color: 'var(--text-primary)' }}>{b.common_name}</p>
                    <span className="text-xs flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>{b.count}</span>
                  </div>
                )
                return b.bird_profile_id
                  ? <Link key={i} to={`/library/${b.bird_profile_id}`}>{row}</Link>
                  : <div key={i}>{row}</div>
              })}
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-tertiary)' }}>
              <p className="text-xs">No detections {isDaily ? 'today' : 'this week'}</p>
            </div>
          )}
        </div>
      </div>
      )}
    </div>
  )
}

const DIVERSITY_BANDS = [
  { max: 1.0, color: '#f59e0b', label: 'Low' },
  { max: 2.0, color: '#eab308', label: 'Moderate' },
  { max: 3.0, color: '#4ade80', label: 'High' },
  { max: 4.0, color: '#22d3ee', label: 'Very High' },
  { max: Infinity, color: '#c4b5fd', label: 'Exceptional' },
]
function diversityColor(shannon) {
  return (DIVERSITY_BANDS.find(b => shannon < b.max) || DIVERSITY_BANDS[DIVERSITY_BANDS.length - 1]).color
}

const SIMPSON_BANDS = [
  { max: 0.5,  color: '#f59e0b' },
  { max: 0.7,  color: '#eab308' },
  { max: 0.85, color: '#4ade80' },
  { max: Infinity, color: '#22d3ee' },
]
function simpsonColor(simpson) {
  return (SIMPSON_BANDS.find(b => simpson < b.max) || SIMPSON_BANDS[SIMPSON_BANDS.length - 1]).color
}

function IndexGauge({ value, scale, color, unitLabel, decimals = 2, asPercent = false }) {
  // Custom SVG ring rather than pulling in recharts for a single gauge.
  // `scale` is the full-ring reference value — for Shannon this is 4.5
  // (comfortably past "Exceptional," so the ring rarely if ever visually
  // maxes out); for Simpson it's just 1, its natural bound.
  const pct = Math.max(0, Math.min(1, value / scale))
  const r = 42, circ = 2 * Math.PI * r
  const displayValue = asPercent ? `${Math.round(value * 100)}%` : value.toFixed(decimals)
  return (
    <svg width={104} height={104} viewBox="0 0 104 104" className="flex-shrink-0">
      <circle cx="52" cy="52" r={r} fill="none" stroke="var(--bg-raised)" strokeWidth="9"/>
      <circle cx="52" cy="52" r={r} fill="none" stroke={color} strokeWidth="9" strokeLinecap="round"
              strokeDasharray={circ} strokeDashoffset={circ * (1 - pct)}
              transform="rotate(-90 52 52)"
              style={{ transition: 'stroke-dashoffset 900ms cubic-bezier(.34,1.4,.64,1)', filter: `drop-shadow(0 0 6px ${color}55)` }}/>
      <text x="52" y="49" textAnchor="middle" fontSize="22" fontWeight="700" fill="var(--text-primary)"
            style={{ fontFamily: "'Lora', serif" }}>{displayValue}</text>
      <text x="52" y="66" textAnchor="middle" fontSize="9" fill="var(--text-tertiary)"
            style={{ textTransform: 'uppercase', letterSpacing: '.05em' }}>{unitLabel}</text>
    </svg>
  )
}

function YardPulse() {
  const [data, setData] = useState(null)
  const [showGuide, setShowGuide] = useState(false)
  const [streaksOpen, toggleStreaksOpen] = useSectionCollapse('dashboard:streaks', true)
  const [diversityOpen, toggleDiversityOpen] = useSectionCollapse('dashboard:diversity', true)

  useEffect(() => {
    const load = () => api.recordings.yardPulse().then(setData).catch(() => {})
    load()
    // No polling interval here — refreshes on the same real-time
    // 'chirp-new-detection' event Dashboard's own data uses, debounced
    // the same way (see the comment there) so a burst of detections
    // collapses into one refresh instead of one per message.
    let debounceTimer = null
    const debouncedLoad = () => { clearTimeout(debounceTimer); debounceTimer = setTimeout(load, 2000) }
    window.addEventListener('chirp-new-detection', debouncedLoad)
    return () => { clearTimeout(debounceTimer); window.removeEventListener('chirp-new-detection', debouncedLoad) }
  }, [])

  if (!data) return null
  const { streaks, diversity } = data
  const hasStreaks = streaks && streaks.length > 0
  const hasDiversity = diversity && diversity.species_last_30d > 0
  if (!hasStreaks && !hasDiversity) return null

  const trend = diversity ? diversity.species_last_30d - diversity.species_prev_30d : 0

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-7 animate-fade-in">
      {/* ── Species streaks ─────────────────────────────────────────── */}
      <div className="card rounded-xl p-4 relative overflow-hidden">
        <button onClick={toggleStreaksOpen} className="flex items-center gap-2 mb-1 w-full text-left">
          <Flame size={16} style={{ color: '#f59e0b' }}/>
          <p className="text-sm font-semibold flex-1" style={{ color: 'var(--text-primary)', fontFamily: "'Lora', serif" }}>Active Streaks</p>
          <ChevronDown size={16} style={{
            color: 'var(--text-tertiary)',
            transform: streaksOpen ? 'none' : 'rotate(-90deg)',
            transition: 'transform .2s',
            flexShrink: 0,
          }}/>
        </button>
        <p className="text-xs mb-3" style={{ color: 'var(--text-tertiary)' }}>
          Consecutive days each species has been detected, without missing a full day.
        </p>
        {streaksOpen && (hasStreaks ? (
          <div className="space-y-2">
            {streaks.map((s, i) => (
              <Link key={s.common_name} to={s.profile_id ? `/library/${s.profile_id}` : '#'}
                    className="flex items-center gap-3 p-2 rounded-lg transition-colors hover:opacity-90"
                    style={{ background: i === 0 ? 'rgba(245,158,11,.08)' : 'transparent' }}>
                <div className="w-9 h-9 rounded-full overflow-hidden flex-shrink-0 flex items-center justify-center"
                     style={{ background: 'var(--bg-raised)' }}>
                  {s.photo_url
                    ? <img src={mediaUrl(s.photo_url)} alt="" className="w-full h-full object-cover" loading="lazy"/>
                    : <BirdIcon size={16} style={{ color: 'var(--text-tertiary)' }}/>}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{s.common_name}</p>
                  {s.scientific_name && <p className="text-xs italic truncate" style={{ color: 'var(--text-tertiary)' }}>{s.scientific_name}</p>}
                </div>
                <div className="flex items-center gap-1 flex-shrink-0" style={{ color: i === 0 ? '#f59e0b' : 'var(--text-secondary)' }}>
                  <Flame size={13}/>
                  <span className="text-sm font-bold">{s.streak_days}</span>
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <p className="text-sm py-4 text-center" style={{ color: 'var(--text-tertiary)' }}>No active streaks yet — check back tomorrow.</p>
        ))}
      </div>

      {/* ── Diversity gauge ─────────────────────────────────────────── */}
      <div className="card rounded-xl p-4 relative overflow-hidden">
        <div onClick={toggleDiversityOpen} role="button" tabIndex={0}
             onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') toggleDiversityOpen() }}
             className="flex items-center justify-between mb-3 cursor-pointer">
          <div className="flex items-center gap-2">
            <Leaf size={16} style={{ color: '#4ade80' }}/>
            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)', fontFamily: "'Lora', serif" }}>Yard Diversity</p>
          </div>
          <div className="flex items-center gap-1">
            <button onClick={e => { e.stopPropagation(); setShowGuide(true) }}
                    className="flex items-center gap-1 pl-1.5 pr-2 py-1 rounded-full transition-colors hover:opacity-80"
                    style={{ color: 'var(--text-tertiary)' }}>
              <Info size={14}/>
              <span className="text-xs">Learn more</span>
            </button>
            <ChevronDown size={16} style={{
              color: 'var(--text-tertiary)',
              transform: diversityOpen ? 'none' : 'rotate(-90deg)',
              transition: 'transform .2s',
              flexShrink: 0,
            }}/>
          </div>
        </div>

        {diversityOpen && (hasDiversity ? (
          <>
            {/* Description at top — the one thing worth reading at a
                glance, combining richness + both diversity scores into a
                single sentence. The rows below give the real numbers for
                anyone who wants them. */}
            <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              This month's detections are
              {' '}
              <strong style={{ color: diversityColor(diversity.shannon_index) }}>{diversity.label.toLowerCase()}</strong>
              {diversity.simpson_index != null && (
                <>, <strong style={{ color: simpsonColor(diversity.simpson_index) }}>{diversity.simpson_label.toLowerCase()}</strong></>
              )}.
            </p>

            {/* Three rows, same shape throughout: a fixed-width visual on
                the left (a circle for the two bounded indices, a number +
                trend arrow for richness — which has no natural ceiling so
                a circle gauge wouldn't mean anything), metric name + gray
                description + a brighter one-line status on the right. */}
            <div className="space-y-3">
              <div className="flex items-center gap-4 pb-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <div className="flex flex-col items-center justify-center flex-shrink-0" style={{ width: 104 }}>
                  <p className="text-3xl font-bold leading-none" style={{ color: 'var(--text-primary)', fontFamily: "'Lora', serif" }}>{diversity.species_last_30d}</p>
                  {diversity.species_prev_30d > 0 && (
                    <p className="text-xs mt-1.5" style={{ color: trend >= 0 ? '#4ade80' : '#f87171' }}>
                      {trend > 0 ? `▲ ${trend}` : trend < 0 ? `▼ ${Math.abs(trend)}` : '— same'}
                    </p>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Species Richness</p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>Distinct species in the last 30 days</p>
                  <p className="text-xs mt-1" style={{ color: trend >= 0 ? '#4ade80' : '#f87171' }}>
                    {diversity.species_prev_30d > 0
                      ? (trend > 0 ? `${trend} more than the previous 30 days` : trend < 0 ? `${Math.abs(trend)} fewer than the previous 30 days` : 'Same as the previous 30 days')
                      : 'First 30-day window of data'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-4 pb-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <div className="flex-shrink-0" style={{ width: 104 }}>
                  <IndexGauge value={diversity.shannon_index} scale={4.5} color={diversityColor(diversity.shannon_index)} unitLabel="Shannon H"/>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Shannon Diversity</p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>How evenly species are detected</p>
                  <p className="text-xs mt-1" style={{ color: diversityColor(diversity.shannon_index) }}>{diversity.label}</p>
                </div>
              </div>

              {diversity.simpson_index != null && (
                <div className="flex items-center gap-4">
                  <div className="flex-shrink-0" style={{ width: 104 }}>
                    <IndexGauge value={diversity.simpson_index} scale={1} color={simpsonColor(diversity.simpson_index)} unitLabel="Balance" asPercent/>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Balance</p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>Common vs. rare species</p>
                    <p className="text-xs mt-1" style={{ color: simpsonColor(diversity.simpson_index) }}>{diversity.simpson_label}</p>
                  </div>
                </div>
              )}
            </div>

          </>
        ) : (
          <p className="text-sm py-4 text-center" style={{ color: 'var(--text-tertiary)' }}>Detect a few different species in the last 30 days to see a diversity score.</p>
        ))}
      </div>
      {showGuide && <DiversityGuideModal onClose={() => setShowGuide(false)}/>}
    </div>
  )
}

function SeenTodayTile({ s, delay = 0 }) {
  // "Bat" is a synthetic pseudo-species — used below to pick the right
  // fallback icon. No longer redirects away from the real profile page
  // (an earlier version of this fix did that); the actual fix is making
  // the profile page itself work correctly for bats.
  const isBat = !!s.is_bat
  const tile = (
    <div className="relative rounded-xl overflow-hidden group animate-pop-in transition-transform duration-150 active:scale-95"
         style={{ aspectRatio: '1', background: 'var(--bg-raised)', animationDelay: `${delay}ms` }}>
      {s.photo_url ? (
        <img src={mediaUrl(s.photo_url)} alt="" className="absolute inset-0 w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" loading="lazy"
             onError={e => { e.target.style.display = 'none' }}/>
      ) : (
        <div className="absolute inset-0 flex items-center justify-center">
          {isBat
            ? <BatIcon size={20} style={{ color: "var(--text-tertiary)" }}/>
            : <BirdIcon size={20} style={{ color: "var(--text-tertiary)" }}/>}
        </div>
      )}
      <div className="absolute bottom-0 left-0 right-0 px-1.5 pt-4 pb-1"
           style={{ background: 'linear-gradient(transparent, rgba(0,0,0,.72))' }}>
        <p className="text-[10px] font-medium truncate leading-tight" style={{ color: '#fff' }}>
          {s.common_name}
        </p>
      </div>
      {s.is_new && (
        <span className="absolute top-1 right-1 text-[8px] font-bold px-1.5 py-0.5 rounded-full"
              style={{ background: 'var(--accent-500)', color: 'var(--btn-primary-text, #fff)' }}>
          NEW
        </span>
      )}
    </div>
  )
  // Bat entries don't carry a bird_profile_id (no per-species taxonomy
  // entry for the "Bat" pseudo-species) — fall back to the name-based
  // profile lookup route instead of leaving the tile unclickable, matching
  // the same fallback Life List already uses for any species without a
  // resolved profile_id yet.
  const profileTo = s.bird_profile_id
    ? `/library/${s.bird_profile_id}`
    : isBat ? `/library?name=${encodeURIComponent(s.common_name)}` : null
  return profileTo ? <Link to={profileTo}>{tile}</Link> : <div>{tile}</div>
}

export function SeenTodayModal({ species, onClose }) {
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Rendered via a portal directly into document.body, not inline in the
  // component tree. Root cause of a real, twice-reported bug: WebKit/
  // Chrome/Safari have a longstanding, documented cross-browser quirk
  // where a position:fixed element can be clipped/repositioned by ANY
  // ancestor that has position:relative combined with a z-index set —
  // even with zero transform/filter anywhere in the chain, contradicting
  // the CSS spec's stated behavior that fixed positioning should escape
  // ancestor stacking entirely. The first fix (lowering decorative
  // overlay z-indexes) was a real, separate, correct fix for a real
  // separate bug, but didn't address this one, since the modal was still
  // a DOM descendant of whichever page-level wrapper was actually
  // triggering the browser quirk. A portal sidesteps the whole class of
  // problem: the modal is no longer a descendant of any page wrapper at
  // all, so no ancestor's position/z-index/overflow can affect it,
  // regardless of which specific element was responsible.
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,.7)' }}
         onClick={onClose}>
      <div className="card w-full max-h-[85vh] overflow-y-auto" style={{ maxWidth: 760 }}
           onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between p-5 pb-4" style={{ position: 'sticky', top: 0, background: 'var(--bg-card)', zIndex: 1 }}>
          <h2 className="font-display text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
            Seen today <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>· {species.length} species</span>
          </h2>
          <button onClick={onClose} className="p-1.5 rounded-lg transition-colors hover:opacity-70"
                  style={{ background: 'var(--bg-raised)' }}>
            <X size={16} style={{ color: 'var(--text-secondary)' }}/>
          </button>
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-5 gap-2.5 p-5 pt-0">
          {species.map((s, i) => <SeenTodayTile key={s.bird_profile_id || s.common_name} s={s} delay={i * 20}/>)}
        </div>
      </div>
    </div>,
    document.body
  )
}

// Same portal-based modal pattern as SeenTodayModal above — see its own
// comment for why this needs a portal (a documented cross-browser
// position:fixed clipping quirk, not just style preference). Content
// moved here verbatim from what used to be an inline expand-in-place
// section on the Diversity card itself; only the container changed.
function DiversityGuideModal({ onClose }) {
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,.7)' }}
         onClick={onClose}>
      <div className="card w-full max-h-[85vh] overflow-y-auto" style={{ maxWidth: 480 }}
           onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between p-5 pb-4" style={{ position: 'sticky', top: 0, background: 'var(--bg-card)', zIndex: 1 }}>
          <h2 className="font-display text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
            About Yard Diversity
          </h2>
          <button onClick={onClose} className="p-1.5 rounded-lg transition-colors hover:opacity-70"
                  style={{ background: 'var(--bg-raised)' }}>
            <X size={16} style={{ color: 'var(--text-secondary)' }}/>
          </button>
        </div>
        <div className="text-xs space-y-1.5 p-5 pt-0" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          <p style={{ color: 'var(--text-tertiary)' }}>
            Both scores use standard ecological benchmarks from human point-count studies (a person
            standing still for 10-30 minutes, a handful of visits). Chirp's continuous acoustic detection
            samples very differently — common yard birds vocalize far more often than a brief human
            survey would catch, which can pull both scores lower than the literature bands even in a
            genuinely diverse yard. Treat them as a consistent way to track your own yard over time
            rather than a precise match to a textbook number.
          </p>
          <p style={{ color: 'var(--text-tertiary)' }}>
            Shannon diversity index (H) — species count weighted by how evenly detections are
            spread across them, not just a raw tally:
          </p>
          {DIVERSITY_BANDS.map(b => (
            <div key={b.label} className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: b.color }}/>
              <span style={{ color: b.color }}>{b.label}</span>
              <span style={{ color: 'var(--text-tertiary)' }}>
                {b.max === Infinity ? '4.0+' : `${b.max === 1.0 ? '0' : DIVERSITY_BANDS[DIVERSITY_BANDS.indexOf(b) - 1].max.toFixed(1)}–${b.max.toFixed(1)}`}
              </span>
            </div>
          ))}
          <p style={{ color: 'var(--text-tertiary)', marginTop: 8 }}>
            <strong>Balance</strong> (technically Simpson's diversity, 1-D) — the odds two random
            detections in the last 30 days were different species. Weighs common species more heavily
            than the score above, so an occasional rare visitor doesn't swing it much. Shown as
            a percentage, 0–100%, with no open-ended top end:
          </p>
          {SIMPSON_BANDS.map((b, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: b.color }}/>
              <span style={{ color: 'var(--text-tertiary)' }}>
                {i === 0 ? `0–${b.max*100}%` : b.max === Infinity ? `${SIMPSON_BANDS[i-1].max*100}%+` : `${SIMPSON_BANDS[i-1].max*100}–${b.max*100}%`}
              </span>
            </div>
          ))}
          <p style={{ color: 'var(--text-tertiary)', marginTop: 8 }}>
            Both measure evenness of what was detected and recorded — not a direct claim
            about ecosystem health, which acoustic detections alone can't establish.
          </p>
        </div>
      </div>
    </div>,
    document.body
  )
}

// Shared by both Daily and Weekly Journal sub-cards below. Always
// starts collapsed on mount (plain useState, no persistence) per the
// explicit requirement that these reset every page load rather than
// remembering an expanded state — unlike most collapsible cards
// elsewhere in the app, which deliberately DO persist via cardState.
// "Collapsed" here still shows a real preview (not just a hidden
// header) via CSS line-clamp, with a Read more/Show less toggle —
// distinct from other cards' collapse behavior (which hides content
// entirely), because a Journal entry's whole appeal is a nice line or
// two visible without a click, not a title-only teaser.
const PREVIEW_LINE_CLAMP = 4

function JournalEntryCard({ icon: Icon, title, subheading, data, onRegenerate, regenerating, errorHint }) {
  const [expanded, setExpanded] = useState(false)
  const textRef = useRef(null)
  const [isTruncatable, setIsTruncatable] = useState(false)

  // Detects whether the text actually overflows the clamped preview —
  // measuring the real rendered height rather than guessing from
  // character count, so a short entry that already fits within the
  // clamp doesn't show a pointless "Read more" that reveals nothing new.
  useEffect(() => {
    if (!textRef.current || !data?.text) return
    const el = textRef.current
    setIsTruncatable(el.scrollHeight > el.clientHeight + 2)  // +2px slack for sub-pixel rounding
  }, [data?.text])

  if (!data || !data.enabled) return null

  return (
    <div className="p-3.5 rounded-xl" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-2 min-w-0">
          <Icon size={15} style={{ color: 'var(--accent-400)', flexShrink: 0 }}/>
          <div className="min-w-0">
            <p className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)', fontFamily: "'Lora', serif" }}>{title}</p>
            {subheading && (
              <p className="text-xs font-medium truncate flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
                <Clock size={10} style={{ flexShrink: 0, opacity: 0.7 }}/>
                {subheading}
              </p>
            )}
          </div>
        </div>
        <button onClick={onRegenerate} disabled={regenerating}
                className="tactile-press p-1 rounded-full transition-colors hover:opacity-80 disabled:opacity-40 flex-shrink-0"
                style={{ color: 'var(--text-tertiary)' }}
                title={data.text ? 'Regenerate now' : 'Generate now'} aria-label="Regenerate">
          <RefreshCw size={12} className={regenerating ? 'animate-spin' : ''}/>
        </button>
      </div>

      {data.text && (
        <>
          <p ref={textRef} className="text-sm whitespace-pre-line" style={{
            color: 'var(--text-secondary)', lineHeight: 1.6, fontFamily: "'Lora', serif",
            ...(!expanded ? {
              display: '-webkit-box',
              WebkitLineClamp: PREVIEW_LINE_CLAMP,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            } : {}),
          }}>
            {data.text}
          </p>
          {isTruncatable && (
            <button onClick={() => setExpanded(e => !e)}
                    className="tactile-press text-xs font-medium mt-1.5" style={{ color: 'var(--accent-400)' }}>
              {expanded ? 'Show less' : 'Read more'}
            </button>
          )}
        </>
      )}

      {!data.text && data.error && (
        <div>
          <p className="text-sm" style={{ color: '#f87171' }}>Last attempt failed: {data.error}</p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>{errorHint}</p>
        </div>
      )}
      {!data.text && !data.error && (
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
          Nothing generated yet — it'll run automatically at the scheduled time, or use the regenerate button above to generate it now.
        </p>
      )}
    </div>
  )
}

function JournalCard({ showDaily = true, showWeekly = true }) {
  const [dailyData, setDailyData] = useState(null)
  const [weeklyData, setWeeklyData] = useState(null)
  const [regeneratingDaily, setRegeneratingDaily] = useState(false)
  const [regeneratingWeekly, setRegeneratingWeekly] = useState(false)
  const [open, toggleOpen] = useSectionCollapse('dashboard:journal', true)

  useEffect(() => {
    if (showDaily) api.recordings.dailyJournal().then(setDailyData).catch(() => {})
    if (showWeekly) api.recordings.weeklyJournal().then(setWeeklyData).catch(() => {})
  }, [showDaily, showWeekly])

  const regenerateDaily = async () => {
    setRegeneratingDaily(true)
    try { setDailyData(await api.recordings.regenerateDailyJournal()) } catch (e) { /* keep whatever was showing before */ }
    setRegeneratingDaily(false)
  }
  const regenerateWeekly = async () => {
    setRegeneratingWeekly(true)
    try { setWeeklyData(await api.recordings.regenerateWeeklyJournal()) } catch (e) { /* keep whatever was showing before */ }
    setRegeneratingWeekly(false)
  }

  // Same "only fully hidden when BOTH features are off" rule the old
  // single card used for its one feature — an enabled-but-no-text-yet
  // state is real and needs its own visible status with a way to act
  // on it, not silent disappearance.
  if ((!dailyData || !dailyData.enabled) && (!weeklyData || !weeklyData.enabled)) return null

  const dailySubheading = dailyData?.generated_at
    ? new Date(dailyData.generated_at + 'Z').toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
    : null
  const weeklySubheading = (weeklyData?.period_start && weeklyData?.period_end)
    ? `Week of ${new Date(weeklyData.period_start + 'Z').toLocaleDateString([], { month: 'short', day: 'numeric' })} – ${new Date(weeklyData.period_end + 'Z').toLocaleDateString([], { month: 'short', day: 'numeric' })}`
    : null

  return (
    <div className="card rounded-xl p-4 mb-4 animate-stagger-1">
      <button onClick={toggleOpen} className="flex items-center justify-between w-full mb-1 text-left">
        <div className="flex items-center gap-2">
          <Sparkles size={16} style={{ color: 'var(--accent-400)' }}/>
          <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)', fontFamily: "'Lora', serif" }}>Journal</p>
        </div>
        <ChevronDown size={16} style={{
          color: 'var(--text-tertiary)',
          transform: open ? 'none' : 'rotate(-90deg)',
          transition: 'transform .2s',
          flexShrink: 0,
        }}/>
      </button>
      {open && (
        <>
          <div className="space-y-3 mt-2">
            {dailyData?.enabled && (
              <JournalEntryCard icon={Sparkles} title="Daily Journal" subheading={dailySubheading}
                                 data={dailyData} onRegenerate={regenerateDaily} regenerating={regeneratingDaily}
                                 errorHint="Check the provider key in Settings → AI Features, then use the regenerate button above to try again."/>
            )}
            {weeklyData?.enabled && (
              <JournalEntryCard icon={BookOpen} title="Weekly Journal" subheading={weeklySubheading}
                                 data={weeklyData} onRegenerate={regenerateWeekly} regenerating={regeneratingWeekly}
                                 errorHint="Check the provider key in Settings → AI Features, then use the regenerate button above to try again."/>
            )}
          </div>
          <p className="text-[10px] uppercase tracking-wide mt-3" style={{ color: 'var(--text-tertiary)' }}>AI-generated</p>
        </>
      )}
    </div>
  )
}

function SeenTodayGrid({ species }) {
  const [showAll, setShowAll] = useState(false)
  const [open, toggleOpen] = useSectionCollapse('dashboard:seen-today', true)
  if (!species || species.length === 0) return null
  // No single fixed "show N, then a +more tile" count lands the +more tile
  // as the last item of a complete row at every breakpoint (3/5/9 columns)
  // simultaneously, since the real species count varies daily and grids
  // reflow independently per breakpoint. Rather than chase an unsolvable
  // exact-fit, the +more tile is styled to carry its own visual weight
  // (matches the photo tiles' presence, not a sparse leftover-looking
  // placeholder) so it reads intentionally even on the rare row it ends up
  // alone in — confirmed from a real reported screenshot where the
  // previous dashed-border, low-contrast version looked like an accident.
  // 8, not 9: at the lg breakpoint (9 columns), 8 shown + 1 "+more" tile
  // fills exactly one full row. Confirmed from a real reported screenshot
  // where VISIBLE=9 plus the +more tile (10 items total) left the +more
  // tile alone in its own row at this exact breakpoint. Narrower
  // breakpoints (3/5 columns) can still leave a partial final row, but a
  // partial row of several items reads as ordinary grid wrapping — the
  // specific bug reported was the +more tile rendering completely alone.
  const VISIBLE = 8
  const shown = species.slice(0, VISIBLE)
  const remaining = species.length - shown.length

  return (
    <div className="mb-6 animate-stagger-1">
      <button onClick={toggleOpen} className="flex items-center justify-between mb-2 w-full text-left">
        <p className="text-xs font-medium uppercase tracking-wide" style={{ color: 'var(--text-tertiary)' }}>
          Seen today
        </p>
        <ChevronDown size={16} style={{
          color: 'var(--text-tertiary)',
          transform: open ? 'none' : 'rotate(-90deg)',
          transition: 'transform .2s',
          flexShrink: 0,
        }}/>
      </button>
      {open && (
      <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-9 gap-3">
        {shown.map((s, i) => <div key={s.bird_profile_id || s.common_name}><SeenTodayTile s={s} delay={i * 35}/></div>)}
        {remaining > 0 && (
          <button onClick={() => setShowAll(true)}
                  className="relative rounded-xl overflow-hidden group flex flex-col items-center justify-center gap-0.5 transition-all hover:opacity-90 active:scale-95 animate-pop-in"
                  style={{ aspectRatio: '1', background: 'var(--nav-active-bg)', border: '1px solid var(--border-default)', animationDelay: `${shown.length * 35}ms` }}>
            <BirdIcon size={16} style={{ color: 'var(--accent-400)', opacity: .5 }}/>
            <span className="text-base font-bold" style={{ color: 'var(--accent-400)' }}>+{remaining}</span>
            <span className="text-[9px] font-medium uppercase tracking-wide" style={{ color: 'var(--text-tertiary)' }}>more</span>
          </button>
        )}
      </div>
      )}
      {showAll && <SeenTodayModal species={species} onClose={() => setShowAll(false)}/>}
    </div>
  )
}

function LiveDetectionCard({ recordingId }) {
  const [detail, setDetail] = useState(null)
  const [imgError, setImgError] = useState(false)

  useEffect(() => {
    setImgError(false)
    if (!recordingId) { setDetail(null); return }
    let cancelled = false
    api.recordings.get(recordingId).then(d => { if (!cancelled) setDetail(d) }).catch(() => {})
    return () => { cancelled = true }
  }, [recordingId])

  if (!recordingId) return null

  const topDetection = detail?.detections?.[0]
  const confidence = Math.round((detail?.max_confidence || topDetection?.confidence || 0) * 100)
  // Other species in the same clip — real data already on `detail`, no
  // extra fetch needed. Distinct by common_name (a clip can have several
  // detections of the same species at different timestamps; this counts
  // distinct SPECIES, not raw detection rows) and excludes the top one.
  const otherSpecies = detail
    ? [...new Map(
        (detail.detections || [])
          .filter(d => d.common_name !== detail.top_species)
          .map(d => [d.common_name, d])
      ).values()]
    : []
  const hasPhoto = detail?.top_species_photo_url && !imgError

  return (
    <Link to={`/recordings/${recordingId}`}
          className="card-hover flex overflow-hidden mb-6 animate-stagger-1 group" style={{ animationDelay: '0ms' }}>
      {/* Poster: top-species photo in a fixed-width square panel, not
          stretched full-bleed across the whole card. A full-bleed photo
          across a wide desktop card (often 6:1+ width:height) is a
          fundamentally poor fit for a portrait-oriented bird photo — no
          object-position value can fix a ratio that extreme, confirmed
          directly from a real reported screenshot where the bird's head
          was pushed out of frame regardless of crop bias. A square panel
          gives every photo, regardless of its own orientation, a sane,
          predictable crop target. */}
      {/* The panel runs the card's full height (at least square) and the
          photo fades into the card on its right and bottom edges, so a
          taller card never shows a hard-edged block above empty space. */}
      <div className="relative flex-shrink-0 self-stretch"
           style={{ width: 'clamp(120px, 30vw, 200px)', minHeight: 'clamp(120px, 30vw, 180px)' }}>
        <div className="absolute inset-0"
             style={{ background: 'linear-gradient(135deg, var(--bg-raised), var(--bg-card))',
                      WebkitMaskImage: 'linear-gradient(to right, #000 62%, transparent), linear-gradient(to bottom, #000 80%, transparent)',
                      WebkitMaskComposite: 'source-in',
                      maskImage: 'linear-gradient(to right, #000 62%, transparent), linear-gradient(to bottom, #000 80%, transparent)',
                      maskComposite: 'intersect' }}>
          {hasPhoto && (
            <img src={mediaUrl(detail.top_species_photo_url)} alt=""
                 className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                 onError={() => setImgError(true)}/>
          )}
        </div>
        <div className="absolute top-2 left-2 inline-flex items-center gap-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full"
             style={{ background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)' }}>
          <span className="relative inline-flex w-1.5 h-1.5">
            <span className="absolute inset-0 rounded-full" style={{ background: 'currentColor' }}/>
            <span className="absolute inset-0 rounded-full animate-live" style={{ background: 'currentColor' }}/>
          </span>
          Live
        </div>
      </div>

      <div className="flex-1 min-w-0 p-4 flex flex-col justify-center">
        <div className="flex items-start justify-between gap-2 flex-wrap">
          <div className="min-w-0 flex-1">
            {/* No forced single-line truncate — on a narrow viewport that
                clipped real species/scientific names mid-word ("Americ…",
                "Turdus migrator…", confirmed from a real screenshot).
                clamp() scales the font down on narrow screens and the text
                is allowed to wrap onto a second line instead of being cut
                off, which reads far better for longer names than an
                ellipsis on a single line ever could. */}
            <p className="font-bold leading-tight" style={{ color: 'var(--text-primary)', fontFamily: "'Lora', serif", fontSize: 'clamp(1.125rem, 4.5vw, 1.5rem)' }}>
              {detail?.top_species || 'Unidentified'}
            </p>
            {topDetection?.scientific_name && (
              <p className="italic" style={{ color: 'var(--text-secondary)', fontSize: 'clamp(0.8125rem, 3vw, 0.875rem)' }}>
                {topDetection.scientific_name}
              </p>
            )}
          </div>
          <span className="text-sm flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>
            {recHeaderAgo(detail)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3 mt-2.5">
          {confidence > 0 && (
            <span className="text-xs font-semibold flex items-center gap-1" style={{ color: '#4ade80' }}>
              <span style={{ fontSize: 10 }}>●</span> {confidence}% confidence
            </span>
          )}
          {detail?.duration_seconds != null && (
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{Math.floor(detail.duration_seconds)}s clip</span>
          )}
          {detail?.device_name && (
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{detail.device_name}</span>
          )}
        </div>

        {/* "Also in this clip" — only rendered when genuinely true, never a
            fabricated/empty row. */}
        {otherSpecies.length > 0 && (
          <div className="flex items-center gap-2 mt-3 pt-3 min-w-0" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            <span className="text-[10px] font-semibold uppercase tracking-wide flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
              Also in this clip
            </span>
            <div className="flex flex-shrink-0">
              {otherSpecies.slice(0, 4).map((d, i) => (
                d.bird_photo_url ? (
                  <img key={d.common_name} src={mediaUrl(d.bird_photo_url)} alt=""
                       className="w-6 h-6 rounded-full object-cover"
                       style={{ border: '2px solid var(--bg-card)', marginLeft: i === 0 ? 0 : -8, zIndex: 10 - i }}/>
                ) : (
                  <div key={d.common_name} className="w-6 h-6 rounded-full flex items-center justify-center"
                       style={{ background: 'var(--nav-active-bg)', border: '2px solid var(--bg-card)', marginLeft: i === 0 ? 0 : -8, zIndex: 10 - i }}>
                    <BirdIcon size={10} style={{ color: "var(--accent-400)" }}/>
                  </div>
                )
              ))}
            </div>
            <span className="text-xs truncate min-w-0" style={{ color: 'var(--text-secondary)' }}>
              {otherSpecies.map(d => d.common_name).join(', ')}
            </span>
            <span className="text-xs font-medium flex-shrink-0 ml-auto transition-colors group-hover:text-accent" style={{ color: 'var(--text-tertiary)' }}>
              View →
            </span>
          </div>
        )}
      </div>
    </Link>
  )
}

// Relative "Xs ago" / "Xm ago" specifically for the live card's corner badge
// — independent of the page-level fmtRelative (which uses the recordings
// list's own conventions); this needs second-level granularity since the
// whole point of the card is "this just happened."
function recHeaderAgo(detail) {
  if (!detail?.trigger_timestamp && !detail?.created_at) return ''
  const ts = detail.trigger_timestamp || detail.created_at
  const t = new Date(ts.endsWith('Z') ? ts : ts + 'Z')
  if (isNaN(t)) return ''
  const secs = Math.max(0, Math.round((Date.now() - t.getTime()) / 1000))
  if (secs < 60) return `${secs}s ago`
  const mins = Math.round(secs / 60)
  return `${mins}m ago`
}

export function DashboardModePicker({ onChoose, onClose }) {
  const [saving, setSaving] = useState(null)  // which option is being saved, for a brief loading state
  const pick = async (mode) => {
    setSaving(mode)
    await onChoose(mode)
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,.6)', backdropFilter: 'blur(4px)' }}
         onClick={e => { if (e.target === e.currentTarget && onClose) onClose() }}>
      <div className="w-full max-w-lg rounded-2xl p-6 sm:p-8 animate-stagger-1 relative" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)' }}>
        {onClose && (
          <button onClick={onClose} className="absolute top-4 right-4 p-1 rounded-lg transition-colors hover:opacity-70"
                  style={{ color: 'var(--text-tertiary)' }} aria-label="Close">
            <X size={16}/>
          </button>
        )}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-3" style={{ background: 'var(--nav-active-bg)' }}>
            <Sparkles size={26} style={{ color: 'var(--accent-400)' }}/>
          </div>
          <h2 className="text-xl font-bold" style={{ color: 'var(--text-primary)', fontFamily: "'Lora', serif" }}>
            How much do you want to see?
          </h2>
          <p className="text-sm mt-2" style={{ color: 'var(--text-secondary)' }}>
            Pick a starting point for your Dashboard — you can change this anytime.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
          <button onClick={() => pick('simplified')} disabled={!!saving}
                  className="text-left p-4 rounded-xl transition-all hover:-translate-y-0.5 disabled:opacity-60"
                  style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
            <p className="font-semibold text-sm mb-1" style={{ color: 'var(--text-primary)' }}>✨ Simplified</p>
            <p className="text-xs" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Just the essentials — what's singing right now, what you've seen today, and a quick summary. Clean and calm.
            </p>
            {saving === 'simplified' && <p className="text-xs mt-2" style={{ color: 'var(--accent-400)' }}>Saving…</p>}
          </button>

          <button onClick={() => pick('detailed')} disabled={!!saving}
                  className="text-left p-4 rounded-xl transition-all hover:-translate-y-0.5 disabled:opacity-60"
                  style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
            <p className="font-semibold text-sm mb-1" style={{ color: 'var(--text-primary)' }}>📊 Detailed</p>
            <p className="text-xs" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Everything — streaks, yard diversity, activity charts, top species, recent recordings and notes.
            </p>
            {saving === 'detailed' && <p className="text-xs mt-2" style={{ color: 'var(--accent-400)' }}>Saving…</p>}
          </button>
        </div>

        <p className="text-xs text-center" style={{ color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
          Change your mind later — there's a link at the bottom of the Dashboard, or go to{' '}
          <strong style={{ color: 'var(--text-secondary)' }}>Settings → Appearance</strong>.
        </p>
      </div>
    </div>
  )
}

export default function Dashboard({ currentUser, requiresAuth, onDashboardModeChange } = {}) {
  const [stats, setStats] = useState(null)
  const [period, setPeriod] = useState('24h')
  const [activityOpen, toggleActivityOpen] = useSectionCollapse('dashboard:activity-chart', true)
  const [recentOpen, toggleRecentOpen] = useSectionCollapse('dashboard:recent-recordings', true)
  const [notesOpen, toggleNotesOpen] = useSectionCollapse('dashboard:recent-notes', true)
  const [recent, setRecent] = useState([])
  const [recentComments, setRecentComments] = useState([])
  const [summary, setSummary] = useState(null)
  const [summaryPeriod, setSummaryPeriod] = useState('daily')   // 'daily' | 'weekly'
  const [dashboardMode, setDashboardMode] = useState(undefined)  // undefined = not yet loaded, null = never chosen
  const { fmtTs, fmtAgo: fmtRelative, fmtDate, timezone } = useTz()
  const latestId = stats?.latest_recording_id

  // Admin-configurable Dashboard sections (see Settings' own
  // DashboardSectionsSettings) — undefined while loading, so the
  // enabledSections derivation below can tell "not loaded yet, assume
  // everything's on so nothing flashes hidden-then-shown" apart from
  // "loaded, and some sections really are off". Fetched once, not tied
  // to `period` or anything else that changes during a session — an
  // admin's own settings changes elsewhere already trigger a full page
  // context via 'chirp-settings-saved' if needed, this doesn't need its
  // own listener for that.
  const [dashboardSectionsConfig, setDashboardSectionsConfig] = useState(undefined)
  useEffect(() => {
    api.settings.dashboardSections().then(setDashboardSectionsConfig).catch(() => setDashboardSectionsConfig(null))
  }, [])

  // Which section ids are on for the CURRENT mode — before
  // dashboardMode itself resolves, or before the config loads, assume
  // everything's enabled (matches this feature's own "null means
  // everything" default) rather than showing nothing while waiting.
  const enabledSections = useMemo(() => {
    if (!dashboardSectionsConfig) return null // null = "not known yet, treat everything as enabled"
    const key = dashboardMode === 'simplified' ? 'simplified' : 'full'
    const list = dashboardSectionsConfig[key]
    return list ? new Set(list) : null
  }, [dashboardSectionsConfig, dashboardMode])
  const sectionOn = (id) => !enabledSections || enabledSections.has(id)
  // load() below is registered once (in a WebSocket listener and a
  // setInterval callback) and needs to see the LATEST enabledSections on
  // every call, not whatever it was when those listeners were first
  // attached — a ref instead of relying on closure capture over state,
  // updated by this small effect whenever the derived value changes,
  // avoids re-registering the WebSocket listener/interval on every
  // settings change just to keep a stale closure fresh.
  const enabledSectionsRef = useRef(enabledSections)
  useEffect(() => { enabledSectionsRef.current = enabledSections }, [enabledSections])

  // App.jsx already fetches this exact same /auth/me data once, at the
  // top level, before any route even mounts (see its own authChecked
  // gate) — Dashboard used to redundantly re-fetch it itself on every
  // single load just to read one field (dashboard_mode), adding a full
  // network round trip Dashboard's own render was needlessly waiting on.
  // Derived from props now instead; behaviorally identical to the old
  // fetch-based check in every case (auth disabled, disabled-
  // but-still-authenticated, and normal authenticated) — see the prop's
  // own construction in App.jsx's checkAuth() for how each maps.
  useEffect(() => {
    if (!requiresAuth || !currentUser) { setDashboardMode('detailed'); return }
    setDashboardMode(currentUser.dashboard_mode ?? null)
  }, [currentUser, requiresAuth])

  const chooseDashboardMode = async (mode) => {
    setDashboardMode(mode)
    onDashboardModeChange?.(mode)
    try { await api.auth.updateProfile({ dashboard_mode: mode }) } catch (e) { /* non-fatal — local state already updated */ }
  }

  useEffect(() => {
    function load() {
      // Reads the ref (not the enabledSections variable from this
      // render) so a call triggered later — by the WebSocket listener
      // or the safety-net interval registered further down, both set up
      // once — still respects whatever the CURRENT settings are, not
      // whatever they were the one time this effect itself ran.
      const on = enabledSectionsRef.current
      const sectionOn = id => !on || on.has(id)
      // stats powers three sections at once (stat cards, the activity
      // chart, and latest_recording via stats.latest_recording_id below)
      // — fire it if ANY of them are enabled, not just 'stats' itself.
      if (sectionOn('stats') || sectionOn('activity_chart') || sectionOn('latest_recording')) {
        api.recordings.stats(period).then(setStats).catch(() => {})
      }
      if (sectionOn('recent_recordings')) {
        api.recordings.list({ limit: 6 }).then(r => setRecent(r.items || r)).catch(() => {})
      }
      if (sectionOn('recent_comments')) {
        api.birds.recentComments(5).then(setRecentComments).catch(() => {})
      }
      // dashboardSummary similarly powers both seen_today and
      // daily_weekly_summary — same "either one" logic as stats above.
      if (sectionOn('seen_today') || sectionOn('daily_weekly_summary')) {
        api.recordings.dashboardSummary().then(setSummary).catch(() => {})
      }
    }
    load()
    // The WebSocket (see App.jsx's handleWsMessage) already knows the
    // instant a new detection lands and fires 'chirp-new-detection' —
    // that's the real refresh trigger now. Debounced (2s) so a burst of
    // several detections in quick succession — a genuinely normal
    // pattern when a few species are all active at once — collapses
    // into one refresh instead of firing a full reload per message,
    // which would be worse than the old flat-interval poll during
    // exactly the busy periods where efficiency matters most.
    let debounceTimer = null
    const debouncedLoad = () => {
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(load, 2000)
    }
    // The interval below is only a safety net for anything the socket
    // might miss (a dropped reconnect, etc.), so it can be far less
    // frequent than before: this used to poll on a flat 15s timer
    // regardless of whether anything had actually happened, which was
    // ~960 requests/hour from a single open Dashboard tab for data that
    // mostly hadn't changed.
    const iv = setInterval(load, 60000)
    window.addEventListener('chirp-settings-saved', load)
    window.addEventListener('chirp-new-detection', debouncedLoad)
    window.addEventListener('chirp-resume', debouncedLoad)
    return () => {
      clearInterval(iv)
      clearTimeout(debounceTimer)
      window.removeEventListener('chirp-settings-saved', load)
      window.removeEventListener('chirp-new-detection', debouncedLoad)
      window.removeEventListener('chirp-resume', debouncedLoad)
    }
  }, [period])

  // Recharts' ResponsiveContainer measures its parent via ResizeObserver at
  // mount time. This card fades in via a CSS opacity animation
  // (animate-stagger-2, ~400ms total) — on some mobile browsers the initial
  // ResizeObserver callback can fire while that transition is still
  // resolving and get a stale/zero measurement, which then never
  // self-corrects because no further *size* change occurs afterward (only
  // opacity changes, and opacity alone doesn't fire ResizeObserver). The
  // chart silently renders at zero size — no error, nothing in the console,
  // just a blank card — which is exactly why the plain-HTML "Top species"
  // column in the same card is unaffected: it has no ResizeObserver
  // dependency at all. Dispatching a synthetic resize event once the
  // fade-in has settled forces every ResizeObserver-based library
  // (Recharts included) to re-measure against final, stable layout. Fires
  // once per period change, since switching periods re-renders this card's
  // chart data and could in principle hit the same race on a slow device.
  useEffect(() => {
    const t = setTimeout(() => window.dispatchEvent(new Event('resize')), 500)
    return () => clearTimeout(t)
  }, [period])

  // Every other page in this app (LifeList, RecordingsList, Comments,
  // AllNotes, BirdProfile, HaikuboxDetections) shows shaped `.skeleton`
  // shimmer placeholders while loading; Dashboard used a single blanket
  // early-return skeleton for the WHOLE page, gated on `stats` alone —
  // meaning even sections that don't need stats at all (SeenTodayGrid,
  // JournalCard, DailyWeeklySummary, YardPulse — all driven by `summary`
  // or their own independent fetches) sat behind a skeleton until the
  // slowest of the four parallel API calls happened to be `stats`
  // specifically. Reported directly: the page feels like it loads all
  // at once instead of progressively. Fixed by removing the blanket
  // gate — each section below now shows its own content the moment its
  // OWN data is ready, with a skeleton only for that section
  // specifically, so whichever of the four calls resolves first is
  // what appears first, top to bottom, rather than the whole page
  // waiting on whichever happens to resolve last.

  const today = timezone
    ? new Date().toLocaleString('en-CA', { timeZone: timezone, hour12: false }).slice(0, 10)
    : new Date().toISOString().slice(0, 10)

  const chartData = (stats?.detections_by_hour || []).map(b => {
    const bucket = b.bucket || ''
    let label = bucket
    let isCurrent = false

    if (b.unit === 'day') {
      const d = new Date(bucket + 'T00:00:00Z')
      label = d.toLocaleDateString('en', { month: 'short', day: 'numeric', timeZone: timezone || 'UTC' })
      isCurrent = bucket === today
    } else {
      const utcDate = new Date(bucket + ':00Z')
      if (!isNaN(utcDate)) {
        const tz = timezone || Intl.DateTimeFormat().resolvedOptions().timeZone
        const localHour = parseInt(utcDate.toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: tz }), 10)
        label = (period === '6h' || period === '24h')
          ? String(localHour).padStart(2, '0')
          : localHour === 0
            ? utcDate.toLocaleDateString('en', { month: 'short', day: 'numeric', timeZone: tz })
            : String(localHour).padStart(2, '0')
        const bLocalDate = utcDate.toLocaleString('en-CA', { timeZone: tz, hour12: false }).slice(0, 10)
        const nowHour = new Date(new Date().toLocaleString('en-US', { timeZone: tz })).getHours()
        isCurrent = bLocalDate === today && localHour === nowHour
      }
    }
    return { label, n: b.count, isCurrent }
  })

  const lastTs = stats ? toDate(stats.latest_recording) : null
  const maxCount = stats?.top_species?.[0]?.count || 1
  const hasChartData = chartData.some(d => d.n > 0)
  // Real, glanceable insight computed entirely from data already in
  // hand — no new endpoint needed. period fully determines the bucket
  // unit (see the backend's _PERIOD_MAP: only '30d' buckets by day,
  // everything else buckets by hour), so that's enough to know how to
  // read the winning bucket's label without threading a separate
  // unit field through chartData's mapping above.
  const peakBucket = hasChartData
    ? chartData.reduce((max, d) => (d.n > (max?.n ?? -1) ? d : max), null)
    : null
  const isLive = !!(lastTs && (Date.now() - lastTs.getTime()) < 5 * 60 * 1000)

  return (
    <div className="page-root">
      {/* Hero */}
      <div className="page-hero"
           style={{ background: 'var(--gradient-hero)' }}>
        <div className="flex items-center gap-4 animate-slide-down">
          <ChirpLogo size={48} animate={true}/>
          <div>
            <h1 className="font-display text-2xl font-semibold flex items-center gap-2.5" style={{ color: 'var(--text-primary)' }}>
              {(() => {
                const hour = hourInTimezone(timezone)
                const { Icon: GreetingIcon, label, color } = greetingMeta(hour)
                return (
                  <>
                    <GreetingIcon size={22} style={{ color }} className="flex-shrink-0"/>
                    Good {label}
                  </>
                )
              })()}
              {isLive && (
                <span className="relative inline-flex items-center" title="Recent activity">
                  <span className="w-2 h-2 rounded-full" style={{ background: '#4ade80' }}/>
                  <span className="absolute inset-0 w-2 h-2 rounded-full animate-live" style={{ background: '#4ade80' }}/>
                </span>
              )}
            </h1>
            <p className="text-sm mt-0.5" style={{ color: 'var(--text-secondary)' }}>
              {fmtDate(new Date().toISOString(), { weekday: 'long', year: undefined })}
              {' · '}
              {!stats
                ? <span className="skeleton inline-block align-middle" style={{ width: 90, height: 12, borderRadius: 4 }}/>
                : lastTs ? <>Last detection {fmtRelative(stats.latest_recording)}</> : 'No detections yet — start listening'}
            </p>
          </div>
        </div>
      </div>

      {isLive && sectionOn('latest_recording') && <LiveDetectionCard recordingId={latestId}/>}

      {sectionOn('seen_today') && <SeenTodayGrid species={summary?.daily?.species_today}/>}

      {(sectionOn('daily_journal') || sectionOn('weekly_journal')) &&
        <JournalCard showDaily={sectionOn('daily_journal')} showWeekly={sectionOn('weekly_journal')}/>}

      {sectionOn('daily_weekly_summary') &&
        <DailyWeeklySummary summary={summary} summaryPeriod={summaryPeriod} setSummaryPeriod={setSummaryPeriod} timezone={timezone}/>}

      {dashboardMode !== 'simplified' && (
      <>
      {sectionOn('yard_pulse') && <YardPulse/>}

      {/* Stat cards */}
      {sectionOn('stats') && (stats ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-7">
          <StatCard icon={Mic}      label="Recordings"       value={(stats.total_recordings || 0).toLocaleString()}  to="/recordings" delay={50}  tint="bird" lift={STAT_LIFT[0]} animateValue/>
          <StatCard icon={BirdIcon}     label="Species"           value={(stats.total_species || 0).toLocaleString()}    to="/library"    delay={100} tint="bird" lift={STAT_LIFT[1]} animateValue/>
          <StatCard icon={Sparkles} label="Detections"        value={(stats.total_detections || 0).toLocaleString()} to="/recordings" delay={150} tint="bird" lift={STAT_LIFT[2]} animateValue/>
          <StatCard icon={Clock}    label="Last Detection"    value={lastTs ? fmtRelative(stats.latest_recording) : '—'}
                    to={latestId ? `/recordings/${latestId}` : undefined} delay={200} tint="bird" lift={STAT_LIFT[3]}/>
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-7">
          {[0, 1, 2, 3].map(i => (
            <div key={i} className="card p-5" style={{ transform: STAT_LIFT[i] ? `translateY(${STAT_LIFT[i]}px)` : undefined }}>
              <div className="skeleton w-8 h-8 rounded-lg mb-4"/>
              <div className="skeleton h-6 w-16 mb-2"/>
              <div className="skeleton h-3 w-20"/>
            </div>
          ))}
        </div>
      ))}

      {/* Detection activity + Top species — grouped card, shared time filter */}
      {sectionOn('activity_chart') && (
      <div className="card mb-4 animate-stagger-2 overflow-hidden">
        <button onClick={toggleActivityOpen} className="flex items-center justify-between px-5 pt-4 pb-4 w-full text-left">
          <h2 className="font-display text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
            Detection Activity &amp; Top Species
          </h2>
          <ChevronDown size={16} style={{
            color: 'var(--text-tertiary)',
            transform: activityOpen ? 'none' : 'rotate(-90deg)',
            transition: 'transform .2s',
            flexShrink: 0,
          }}/>
        </button>
        {activityOpen && (stats ? (
        <div className="flex flex-col lg:flex-row -mt-4">

          {/* ── Chart column ─────────────────────────────────────────────── */}
          <div className="flex flex-col flex-1 min-w-0 p-5">
            {/* Period selector, paired with a "busiest bucket" callout on
                the left — a real, glanceable insight rather than just
                controls, computed client-side from chartData (no new
                endpoint). The outer card header already says "Detection
                Activity & Top Species", so no need to repeat that here. */}
            <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
              {peakBucket && peakBucket.n > 0 ? (
                <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  Busiest: <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>
                    {period === '30d' ? peakBucket.label : `${peakBucket.label}:00`}
                  </span> · {peakBucket.n} detection{peakBucket.n === 1 ? '' : 's'}
                </p>
              ) : <span/>}
              <div className="flex gap-1 flex-wrap">
                {['6h','24h','48h','7d','30d'].map(p => (
                  <button key={p} onClick={() => setPeriod(p)}
                    className="text-xs px-2.5 py-1 rounded-lg font-medium transition-all"
                    style={period === p
                      ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)', border: '1px solid var(--border-default)', boxShadow: '0 0 12px var(--glow-color)' }
                      : { background: 'var(--bg-raised)', color: 'var(--text-tertiary)', border: '1px solid var(--border-subtle)' }
                    }>{p}</button>
                ))}
              </div>
            </div>
            {/* Chart wrapper — height strategy differs by breakpoint on purpose:
                - Mobile (default, flex-col parent): h-[220px] is an UNCONDITIONAL,
                  non-flex-dependent explicit height. Previously this used
                  `flex:1 + minHeight:220` — mixing flex-grow with min-height on a
                  nested flex-column item is a known WebKit/iOS Safari bug where the
                  computed height can genuinely resolve to 0 (not just a stale
                  ResizeObserver reading — the layout engine actually computes zero),
                  which explains why the chart was blank specifically on mobile while
                  working fine on desktop, and why the earlier resize-event-nudge fix
                  (correct for a *different*, adjacent stale-measurement issue) didn't
                  fully resolve it. An explicit, unconditional height sidesteps the
                  whole class of bug — nothing to mis-measure or mis-compute.
                - Desktop (lg: flex-row parent): lg:h-auto cancels the fixed mobile
                  height, lg:flex-1 fills the column to match the Top Species
                  sibling's height, exactly as before (this half was already working). */}
            <div className="relative h-[220px] lg:h-auto lg:flex-1">
              {hasChartData ? (
                <Suspense fallback={null}>
                  <DashboardBarChart key={period} data={chartData} yKey="n" tooltip={<CustomTooltip/>} debounce={1}
                    margin={{ top: 4, right: 4, bottom: 0, left: -16 }}
                    cellFill={d => (d.n === 0 ? 'transparent' : d.isCurrent ? 'var(--accent-500)' : 'var(--accent-800)')}
                    cellOpacity={d => (d.n === 0 ? 0 : 1)}/>
                </Suspense>
              ) : (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2" style={{ color: 'var(--text-tertiary)' }}>
                  <Activity size={28}/>
                  <p className="text-sm">No detections in the last {period}</p>
                </div>
              )}
            </div>
          </div>

          {/* Divider — horizontal on mobile, vertical on desktop */}
          <div className="lg:hidden mx-5 h-px" style={{ background: 'var(--border-subtle)' }}/>
          <div className="hidden lg:block w-px flex-shrink-0" style={{ background: 'var(--border-subtle)' }}/>

          {/* ── Top species column ────────────────────────────────────────── */}
          <div className="lg:w-60 xl:w-72 flex-shrink-0 p-5">
            <h2 className="font-display text-base font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
              Top species
              <span className="ml-2 text-xs font-normal" style={{ color: 'var(--text-tertiary)' }}>
                · last {period}
              </span>
            </h2>
            {stats.top_species?.length > 0 ? (
              <div className="space-y-2.5">
                {stats.top_species.slice(0, 10).map((s, i) => (
                  <div key={i} className="flex items-center gap-2.5 animate-fade-in"
                       style={{ animationDelay: `${i * 30}ms` }}>
                    <span className="text-xs font-mono w-4 flex-shrink-0 text-right"
                          style={{ color: 'var(--text-tertiary)' }}>{i + 1}</span>
                    {s.bird_profile_id
                      ? <Link to={`/library/${s.bird_profile_id}`}
                            className="flex-1 min-w-0 text-sm truncate transition-colors hover:text-accent"
                            style={{ color: 'var(--text-primary)' }}>
                          {s.common_name || s.species}
                        </Link>
                      : <p className="flex-1 min-w-0 text-sm truncate"
                           style={{ color: 'var(--text-primary)' }}>
                          {s.common_name || s.species}
                        </p>
                    }
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <div className="w-12 h-1 rounded-full overflow-hidden" style={{ background: 'var(--bg-raised)' }}>
                        <div className="h-full confidence-bar rounded-full transition-all duration-700 ease-out"
                             style={{ width: `${Math.min(100, (s.count / maxCount) * 100)}%` }}/>
                      </div>
                      <span className="text-xs w-6 text-right tabular-nums"
                            style={{ color: 'var(--text-tertiary)' }}>{s.count}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-6" style={{ color: 'var(--text-tertiary)' }}>
                <Feather size={22} className="mb-2"/>
                <p className="text-sm">No detections in the last {period}</p>
              </div>
            )}
          </div>

        </div>
        ) : (
          <div className="flex flex-col lg:flex-row -mt-4">
            <div className="flex-1 min-w-0 p-5">
              <div className="skeleton h-5 w-56 mb-4"/>
              <div className="skeleton h-[220px] w-full rounded-xl"/>
            </div>
            <div className="lg:w-72 flex-shrink-0 p-5 lg:border-l" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="skeleton h-4 w-24 mb-4"/>
              {[0, 1, 2].map(i => <div key={i} className="skeleton h-9 w-full rounded-lg mb-2"/>)}
            </div>
          </div>
        ))}
      </div>
      )}

      {/* Recent recordings */}
      {sectionOn('recent_recordings') && (
      <div className="card p-5 animate-stagger-4">
        <div onClick={toggleRecentOpen} role="button" tabIndex={0}
             onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') toggleRecentOpen() }}
             className="flex items-center justify-between mb-4 cursor-pointer">
          <h2 className="font-display text-base font-semibold" style={{ color: 'var(--text-primary)' }}>Recent recordings</h2>
          <div className="flex items-center gap-3">
            <Link to="/recordings" onClick={e => e.stopPropagation()}
                  className="group flex items-center gap-1 text-xs transition-colors hover:text-accent"
                  style={{ color: 'var(--text-secondary)' }}>
              View all <ArrowRight size={12} className="transition-transform duration-200 group-hover:translate-x-0.5"/>
            </Link>
            <ChevronDown size={16} style={{
              color: 'var(--text-tertiary)',
              transform: recentOpen ? 'none' : 'rotate(-90deg)',
              transition: 'transform .2s',
              flexShrink: 0,
            }}/>
          </div>
        </div>
        {recentOpen && (recent.length === 0 ? (
          <div className="text-center py-10">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-3 animate-float"
                 style={{ background: 'var(--nav-active-bg)' }}>
              <Mic size={24} style={{ color: 'var(--accent-400)' }}/>
            </div>
            <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>No recordings yet</p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>Once your device starts listening, recordings will show up here</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {recent.map((rec, i) => (
              <Link key={rec.id} to={`/recordings/${rec.id}`}
                className="card-hover flex items-center gap-3 p-3 group overflow-hidden animate-pop-in"
                style={{ animationDelay: `${i * 40}ms` }}>
                <div className="w-16 h-10 rounded-lg overflow-hidden flex-shrink-0 relative"
                     style={{ background: 'var(--bg-raised)' }}>
                  <img src={mediaUrl(`/api/v1/recordings/${rec.id}/spectrogram?thumb=true`)} alt="" loading="lazy"
                       className="absolute inset-0 w-full h-full object-cover object-bottom transition-transform duration-300 group-hover:scale-105"
                       onError={e => e.target.style.opacity = 0}/>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate transition-colors"
                     style={{ color: 'var(--text-primary)' }}>
                    {rec.top_species || 'Unknown'}
                  </p>
                  <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>
                    {rec.detections?.length} detection{rec.detections?.length !== 1 ? 's' : ''} · {fmtRelative(rec.trigger_timestamp)}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        ))}
      </div>
      )}

      {/* Recent Notes */}
      {sectionOn('recent_comments') && recentComments.length > 0 && (
        <div className="card p-5 animate-fade-in mt-4">
          <div onClick={toggleNotesOpen} role="button" tabIndex={0}
               onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') toggleNotesOpen() }}
               className="flex items-center justify-between mb-4 cursor-pointer">
            <h2 className="font-display text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
              Recent Notes
            </h2>
            <div className="flex items-center gap-3">
              <Link to="/notes" onClick={e => e.stopPropagation()}
                    className="group flex items-center gap-1 text-xs transition-colors hover:text-accent"
                    style={{ color: 'var(--text-secondary)' }}>
                View all <MessageSquare size={12} className="transition-transform duration-200 group-hover:translate-x-0.5"/>
              </Link>
              <ChevronDown size={16} style={{
                color: 'var(--text-tertiary)',
                transform: notesOpen ? 'none' : 'rotate(-90deg)',
                transition: 'transform .2s',
                flexShrink: 0,
              }}/>
            </div>
          </div>
          {notesOpen && (
          <div className="space-y-2">
            {recentComments.map((c, i) => (
              <Link key={c.id} to={c.context_url || '#'}
                className="flex items-start gap-3 p-3 rounded-xl transition-all hover:bg-raised animate-slide-up"
                style={{ textDecoration: 'none', animationDelay: `${i * 40}ms` }}>
                <div className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold"
                     style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }}>
                  {(c.author || 'A')[0].toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5 min-w-0">
                    <span className="text-xs font-semibold truncate min-w-0" style={{ color: 'var(--text-primary)', maxWidth: '40%' }}>
                      {c.author}
                    </span>
                    <span className="text-xs flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>on</span>
                    <span className="text-xs font-medium truncate min-w-0" style={{ color: 'var(--accent-500)' }}>
                      {c.context_name}
                    </span>
                  </div>
                  <p className="text-sm truncate" style={{ color: 'var(--text-secondary)' }}>
                    {c.body}
                  </p>
                </div>
              </Link>
            ))}
          </div>
          )}
        </div>
      )}
      </>
      )}

      {/* Tutorial link */}
      <div className="text-center py-6">
        <Link to="/tutorial"
          className="inline-flex items-center gap-2 text-sm transition-colors hover:text-accent"
          style={{ color: 'var(--text-tertiary)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
          </svg>
          New to Chirp? Read the Getting Started guide →
        </Link>
        {dashboardMode && (
          <p className="text-xs mt-3" style={{ color: 'var(--text-tertiary)' }}>
            Showing the <strong>{dashboardMode === 'simplified' ? 'Simplified' : 'Detailed'}</strong> dashboard —{' '}
            <button onClick={() => chooseDashboardMode(dashboardMode === 'simplified' ? 'detailed' : 'simplified')}
                    className="underline hover:opacity-80" style={{ color: 'var(--accent-500)' }}>
              switch to {dashboardMode === 'simplified' ? 'Detailed' : 'Simplified'}
            </button>
            {' '}(also in Settings → Appearance)
          </p>
        )}
      </div>

      {dashboardMode === null && (
        <DashboardModePicker onChoose={chooseDashboardMode}/>
      )}
    </div>
  )
}