import { Link } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { ArrowLeft, ArrowRight, ArrowUp, Mic, Award, LayoutDashboard, Settings, Radio, MessageSquare, ChevronRight, ChevronDown, BookOpen, Smartphone, Clock, AudioLines } from 'lucide-react'
import ChirpLogo from './ChirpLogo'
import { isApp } from '../native'
import { BirdIcon } from './BirdBatIcons'

/**
 * Wraps content so its entrance animation fires when it actually
 * scrolls into view, instead of once at page-mount time. This page is
 * long (9 sections); every section's fade/slide-in previously fired
 * together within the first ~400ms of load (a 40ms stagger across 9
 * sections), which means by the time someone actually scrolled down to
 * section 6, 7, 8, or 9, that section's "entrance" had already finished
 * long before they could see it — the rest of the scroll experience was
 * completely static. This makes every section (and anything else
 * wrapped in it) animate in fresh, each time it's actually about to
 * become visible, so scrolling through the whole page feels alive
 * throughout instead of only at the very top.
 *
 * Reveals once and stays revealed (disconnects its own observer after
 * firing) — scrolling back up and down past an already-seen section
 * re-triggering the same animation over and over would read as
 * distracting flicker, not polish.
 */
function Reveal({ children, className = '', style = {}, animation = 'animate-slide-up', threshold = 0.12, ...props }) {
  const ref = useRef(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    // Respect reduced-motion preference — show content immediately,
    // fully visible, rather than forcing a motion effect on someone
    // who's explicitly asked their OS not to do this.
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setVisible(true)
      return
    }
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          obs.disconnect()
        }
      },
      { threshold, rootMargin: '0px 0px -40px 0px' }
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [threshold])

  return (
    <div ref={ref} className={`${className} ${visible ? animation : ''}`}
         style={visible ? style : { opacity: 0, ...style }}
         {...props}>
      {children}
    </div>
  )
}

function Step({ number, icon: Icon, title, color, children }) {
  return (
    <div className="relative">
      <div className="flex items-start gap-4">
        {/* Number bubble */}
        <div className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm animate-pop-in"
             style={{ background: color + '22', border: `2px solid ${color}44`, color }}>
          {number}
        </div>
        <div className="flex-1 pb-8 animate-slide-up">
          <div className="flex items-center gap-2 mb-3">
            <Icon size={16} style={{ color }}/>
            <h3 className="font-display font-semibold text-base" style={{ color: 'var(--text-primary)' }}>{title}</h3>
          </div>
          {children}
        </div>
      </div>
      {/* Connector line */}
      <div className="absolute left-5 top-10 bottom-0 w-px" style={{ background: 'var(--border-subtle)' }}/>
    </div>
  )
}

function ScreenMockup({ children, label }) {
  return (
    <div className="rounded-xl overflow-hidden border my-4 transition-shadow duration-300 hover:shadow-lg animate-scale-in"
         style={{ borderColor: 'var(--border-default)', background: 'var(--bg-card)' }}>
      {/* Browser chrome */}
      <div className="flex items-center gap-1.5 px-3 py-2 border-b" style={{ background: 'var(--bg-panel)', borderColor: 'var(--border-subtle)' }}>
        <div className="w-2.5 h-2.5 rounded-full bg-red-500/60"/>
        <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/60"/>
        <div className="w-2.5 h-2.5 rounded-full bg-green-500/60"/>
        <div className="flex-1 mx-3 rounded px-2 py-0.5 text-xs text-center"
             style={{ background: 'var(--bg-raised)', color: 'var(--text-tertiary)' }}>
          chirp.local
        </div>
      </div>
      <div className="p-4">{children}</div>
      {label && <p className="text-xs text-center pb-3" style={{ color: 'var(--text-tertiary)' }}>{label}</p>}
    </div>
  )
}

function AnnotatedItem({ label, arrow = 'right', color = 'var(--accent-400)', children }) {
  return (
    <div className="relative inline-flex items-center gap-2">
      {children}
      <div className="flex items-center gap-1">
        <svg width="20" height="14" viewBox="0 0 20 14" fill="none">
          {arrow === 'right'
            ? <path d="M0 7h16M10 1l6 6-6 6" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            : <path d="M20 7H4M10 1L4 7l6 6" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          }
        </svg>
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full" style={{ background: color + '22', color, border: `1px solid ${color}44` }}>
          {label}
        </span>
      </div>
    </div>
  )
}

function NavMockup() {
  const items = [
    { icon: LayoutDashboard, label: 'Dashboard',  active: false },
    { icon: Mic,             label: 'Recordings', active: true  },
    { icon: Award,           label: 'Life List',  active: false },
    { icon: BookOpen,        label: 'Field Guide', active: false },
  ]
  return (
    <div className="flex items-center rounded-xl overflow-hidden border" style={{ background: 'var(--bg-panel)', borderColor: 'var(--border-default)' }}>
      {items.map(({ icon: Icon, label, active }) => (
        <div key={label}
             className="flex-1 flex flex-col items-center gap-1 py-2 px-1"
             style={{
               background: active ? 'var(--nav-active-bg)' : 'transparent',
               color: active ? 'var(--accent-400)' : 'var(--text-tertiary)',
             }}>
          <Icon size={16}/>
          <span className="text-xs">{label}</span>
        </div>
      ))}
    </div>
  )
}

function CardMockup({ species, conf, time, photo }) {
  return (
    <div className="card-hover flex items-center gap-3 p-3 rounded-xl" style={{ maxWidth: 300 }}>
      <div className="w-12 h-12 rounded-lg flex-shrink-0 overflow-hidden flex items-center justify-center text-2xl"
           style={{ background: 'var(--bg-raised)' }}>
        {photo || <BirdIcon size={24} style={{ color: 'var(--text-tertiary)' }}/>}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{species}</p>
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{time}</p>
      </div>
      <span className="badge badge-green">{conf}</span>
    </div>
  )
}

// ── Animated demo: tapping the Enhance toggle ───────────────────────────────────
// Auto-cycles through idle → tap → enhanced → (pause) → back to idle, on a loop,
// so the page communicates the feature without requiring the reader to interact.
const ENHANCE_DEMO_PHASES = ['idle', 'tap', 'enhanced', 'hold']
const ENHANCE_DEMO_DURATIONS = [1200, 1200, 1200, 1200]   // ms per phase — all equal

function EnhanceAudioDemo() {
  const [phaseIdx, setPhaseIdx] = useState(0)

  useEffect(() => {
    const t = setTimeout(
      () => setPhaseIdx(i => (i + 1) % ENHANCE_DEMO_PHASES.length),
      ENHANCE_DEMO_DURATIONS[phaseIdx]
    )
    return () => clearTimeout(t)
  }, [phaseIdx])

  const phase = ENHANCE_DEMO_PHASES[phaseIdx]
  const enhanced = phase === 'enhanced' || phase === 'hold'
  const tapping = phase === 'tap'

  // Two waveform paths — "noisy" (jagged, irregular) vs "enhanced" (smoother,
  // more even amplitude) — cross-faded by opacity so the difference reads
  // clearly without needing real audio analysis on a tutorial page.
  const noisyPath = "M0,18 L4,9 L8,24 L12,6 L16,21 L20,11 L24,26 L28,8 L32,19 L36,3 L40,22 L44,13 L48,28 L52,7 L56,20 L60,10 L64,25 L68,5 L72,17 L76,23 L80,9 L84,19 L88,4 L92,21 L96,12 L100,18"
  const cleanPath  = "M0,16 L4,12 L8,19 L12,11 L16,17 L20,13 L24,20 L28,10 L32,16 L36,9 L40,18 L44,13 L48,21 L52,11 L56,17 L60,12 L64,19 L68,10 L72,15 L76,18 L80,12 L84,16 L88,9 L92,17 L96,13 L100,16"

  return (
    <div className="rounded-xl overflow-hidden border my-4" style={{ borderColor: 'var(--border-default)', background: 'var(--bg-card)' }}>
      <div className="p-4 flex flex-col items-center gap-3">
        {/* Mock detection row */}
        <div className="w-full max-w-xs flex items-center gap-2 p-2.5 rounded-xl" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <div className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center" style={{ background: 'var(--bg-panel)' }}><BirdIcon size={16} style={{ color: 'var(--text-tertiary)' }}/></div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }}>Carolina Wren</p>
            {/* Waveform */}
            <svg width="100%" height="22" viewBox="0 0 100 32" preserveAspectRatio="none" className="mt-0.5">
              <path d={noisyPath} fill="none" stroke="#fb923c" strokeWidth="1.6"
                    style={{ opacity: enhanced ? 0 : 1, transition: 'opacity .45s ease' }}/>
              <path d={cleanPath} fill="none" stroke="#4ade80" strokeWidth="1.6"
                    style={{ opacity: enhanced ? 1 : 0, transition: 'opacity .45s ease' }}/>
            </svg>
          </div>
          {/* Enhance button with tap ripple */}
          <div className="relative flex-shrink-0">
            {tapping && (
              <span className="absolute inset-0 rounded-full" style={{
                background: 'var(--accent-400)', opacity: 0.35,
                animation: 'tutorialTapRipple .35s ease-out',
              }}/>
            )}
            <div className="relative flex items-center gap-1 text-xs px-2 py-1 rounded-full border transition-colors duration-300"
                 style={{
                   background: enhanced ? 'rgba(34,197,94,.18)' : 'var(--bg-panel)',
                   borderColor: enhanced ? 'rgba(34,197,94,.5)' : 'var(--border-default)',
                   color: enhanced ? '#4ade80' : 'var(--text-tertiary)',
                   transform: tapping ? 'scale(0.88)' : 'scale(1)',
                   transition: 'transform .15s ease, background .3s ease, color .3s ease, border-color .3s ease',
                 }}>
              <span style={{ display: 'inline-block', transition: 'transform .3s ease', transform: enhanced ? 'rotate(15deg) scale(1.15)' : 'none' }}>✨</span>
              {enhanced ? 'Enhanced' : 'Original'}
            </div>
          </div>
        </div>
        {/* Status caption */}
        {/* minHeight reserves 2 lines, not 1 — "Background noise filtered
            out — just the call remains" wraps to 2 lines on a narrow phone
            (confirmed directly at 320px width) while the other phases'
            text fits on 1, so a 1-line reservation let the demo's whole
            height grow and shrink as phases cycled, visibly shifting
            everything below it. Centered vertically within the reserved
            space so the 1-line phases don't look top-aligned with a gap. */}
        <p className="text-xs text-center transition-opacity duration-300 flex items-center justify-center"
           style={{ color: 'var(--text-tertiary)', minHeight: 32 }}>
          {phase === 'idle'    && 'Each clip starts as it was recorded…'}
          {phase === 'tap'     && 'Tap the ✨ sparkle icon…'}
          {(phase === 'enhanced' || phase === 'hold') && 'Background noise removed, leaving the call'}
        </p>
      </div>
      <style>{`
        @keyframes tutorialTapRipple {
          0%   { transform: scale(0.6); opacity: 0.5; }
          100% { transform: scale(2.2); opacity: 0; }
        }
      `}</style>
    </div>
  )
}

// ── Animated demo: tapping through the bottom nav bar ───────────────────────────
const NAV_DEMO_ITEMS = [
  { icon: LayoutDashboard, label: 'Dashboard'  },
  { icon: Mic,             label: 'Recordings' },
  { icon: Award,           label: 'Life List'  },
  { icon: BookOpen,        label: 'Field Guide' },
]

function NavigationDemo() {
  const [active, setActive] = useState(0)

  useEffect(() => {
    const t = setInterval(() => setActive(i => (i + 1) % NAV_DEMO_ITEMS.length), 1300)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex justify-center my-4">
      <div className="rounded-xl overflow-hidden border relative w-full" style={{ borderColor: 'var(--border-default)', maxWidth: 320 }}>
        {/* Sliding highlight pill, positioned under the active icon */}
        <div className="absolute top-1 bottom-1 rounded-lg" style={{
          left: `calc(${active} * 25% + 2px)`,
          width: 'calc(25% - 4px)',
          background: 'var(--nav-active-bg)',
          transition: 'left .35s cubic-bezier(.34,1.56,.64,1)',
        }}/>
        <div className="flex items-center relative border-t" style={{ background: 'var(--bg-panel)', borderColor: 'var(--border-subtle)', padding: '10px 0 6px' }}>
          {NAV_DEMO_ITEMS.map(({ icon: Icon, label }, i) => (
            <div key={label} className="flex-1 flex flex-col items-center gap-1 relative">
              {/* Tap indicator: a small dot that pops in above the icon as it activates */}
              <span className="absolute -top-1 w-1 h-1 rounded-full" style={{
                background: 'var(--accent-400)',
                opacity: active === i ? 1 : 0,
                transform: active === i ? 'scale(1)' : 'scale(0)',
                transition: 'opacity .2s ease, transform .2s ease',
              }}/>
              <Icon size={18} style={{
                color: active === i ? 'var(--accent-400)' : 'var(--text-tertiary)',
                opacity: active === i ? 1 : 0.45,
                transition: 'color .3s ease, opacity .3s ease',
                transform: active === i ? 'translateY(-1px)' : 'none',
              }}/>
              <span className="text-xs" style={{
                color: active === i ? 'var(--accent-400)' : 'var(--text-tertiary)',
                opacity: active === i ? 1 : 0,
                transition: 'opacity .3s ease',
                fontSize: 9,
              }}>{label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Animated demo: tapping "+N more" on the Seen Today grid to open the popup ──
const SEEN_TODAY_PHASES    = ['idle', 'tap', 'open', 'hold']
const SEEN_TODAY_DURATIONS = [1600, 700, 1800, 1400]   // idle → tap → open → hold
const SEEN_TODAY_SPECIES = ['🐦','🦅','🐤','🦜','🐧','🦆','🦉','🦢','🐔','🦃']

function SeenTodayDemo() {
  const [phaseIdx, setPhaseIdx] = useState(0)
  useEffect(() => {
    const t = setTimeout(
      () => setPhaseIdx(i => (i + 1) % SEEN_TODAY_PHASES.length),
      SEEN_TODAY_DURATIONS[phaseIdx]
    )
    return () => clearTimeout(t)
  }, [phaseIdx])

  const phase = SEEN_TODAY_PHASES[phaseIdx]
  const tapping = phase === 'tap'
  const open = phase === 'open' || phase === 'hold'

  return (
    <div className="rounded-xl overflow-hidden border my-4 relative" style={{ borderColor: 'var(--border-default)', background: 'var(--bg-card)' }}>
      <div className="p-4">
        <p className="text-xs uppercase tracking-wide font-semibold mb-2" style={{ color: 'var(--text-tertiary)' }}>Seen today</p>
        <div className="grid grid-cols-5 gap-1.5">
          {SEEN_TODAY_SPECIES.slice(0, 4).map((emoji, i) => (
            <div key={i} className="rounded-lg flex items-center justify-center text-base" style={{ aspectRatio: '1', background: 'var(--bg-raised)' }}>{emoji}</div>
          ))}
          <div className="relative rounded-lg flex flex-col items-center justify-center gap-0.5 transition-transform"
               style={{
                 aspectRatio: '1', background: 'var(--nav-active-bg)', border: '1px solid var(--border-default)',
                 transform: tapping ? 'scale(0.92)' : 'scale(1)', transition: 'transform .15s ease',
               }}>
            <span className="text-xs font-bold" style={{ color: 'var(--accent-400)' }}>+6</span>
            <span className="text-[7px] font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>more</span>
          </div>
        </div>
      </div>

      {/* Popup overlay */}
      <div className="absolute inset-0 flex items-center justify-center p-3 transition-all"
           style={{
             background: 'rgba(0,0,0,.6)',
             opacity: open ? 1 : 0,
             pointerEvents: 'none',
             transition: 'opacity .3s ease',
           }}>
        <div className="card w-full p-3" style={{
          transform: open ? 'scale(1) translateY(0)' : 'scale(0.9) translateY(8px)',
          transition: 'transform .3s cubic-bezier(.34,1.56,.64,1)',
        }}>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>Seen today · 10 species</p>
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>✕</span>
          </div>
          <div className="grid grid-cols-5 gap-1.5">
            {SEEN_TODAY_SPECIES.map((emoji, i) => (
              <div key={i} className="rounded-lg flex items-center justify-center text-sm animate-pop-in"
                   style={{ aspectRatio: '1', background: 'var(--bg-raised)', animationDelay: `${i * 30}ms` }}>{emoji}</div>
            ))}
          </div>
        </div>
      </div>

      {/* Same 2-line reservation as EnhanceAudioDemo's own caption above,
          for the same reason — this demo's captions vary in length too,
          and a larger accessibility text size or a narrower device than
          tested could make any of them wrap without warning. */}
      <p className="text-xs text-center pb-3 transition-opacity duration-300 flex items-center justify-center"
         style={{ color: 'var(--text-tertiary)', minHeight: 32 }}>
        {phase === 'idle' && 'Tap "+more" to see everything detected today…'}
        {phase === 'tap'  && 'Tap'}
        {(phase === 'open' || phase === 'hold') && 'Every species heard today, each linked to its profile'}
      </p>
    </div>
  )
}

const ALL_SECTIONS = [
  {
    id: 'overview',
    title: 'What is Chirp?',
    icon: ChirpLogo,
    color: '#fb923c',
    tldr: 'A Raspberry Pi station listens all day and identifies bird calls. This server stores what it hears so you can browse it.',
    content: (
      <div className="space-y-4">
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          Chirp detects bird calls automatically. A Raspberry Pi station listens all day, identifies
          species with the BirdNET model, and sends each recording to this server. Here you can browse
          and search everything detected at your location.
        </p>
        <div className="grid grid-cols-3 gap-3">
          {[
            { icon: <BirdIcon size={24}/>, label: 'Raspberry Pi', sub: 'Records & detects' },
            { icon: '→',  label: 'Wi-Fi / LAN',  sub: 'Uploads automatically' },
            { icon: '📱', label: 'This app',      sub: 'Browse & explore' },
          ].map(({ icon, label, sub }) => (
            <div key={label} className="card p-3 text-center">
              <div className="text-2xl mb-1 flex items-center justify-center">{icon}</div>
              <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>{label}</p>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{sub}</p>
            </div>
          ))}
        </div>
        <div className="card p-4" style={{ background: 'var(--bg-raised)' }}>
          <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: 'var(--text-tertiary)' }}>
            How a detection works
          </p>
          <div className="space-y-1.5">
            {[
              '🎤  Pi detects audio above the energy threshold',
              '🧠  BirdNET AI analyses the 3-second window',
              '📤  Recording + detections uploaded to this server',
              '🔔  It appears on the Dashboard within seconds',
            ].map(s => (
              <p key={s} className="text-sm" style={{ color: 'var(--text-secondary)' }}>{s}</p>
            ))}
          </div>
        </div>
      </div>
    ),
  },
  {
    id: 'navigation',
    title: 'Navigating Chirp',
    icon: BookOpen,
    color: '#38bdf8',
    tldr: 'The main pages are in the bar at the bottom on a phone and in the sidebar on a computer.',
    content: (
      <div className="space-y-4">
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          Where the menu sits depends on your screen size.
        </p>

        {/* Desktop sidebar */}
        <div className="card p-4 space-y-3">
          <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            🖥 Desktop: sidebar and top menu
          </p>
          <div className="rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border-default)' }}>
            {/* Mock browser */}
            <div className="flex items-center gap-1.5 px-3 py-2 border-b" style={{ background: 'var(--bg-panel)', borderColor: 'var(--border-subtle)' }}>
              <div className="w-2 h-2 rounded-full bg-red-500/60"/><div className="w-2 h-2 rounded-full bg-yellow-500/60"/><div className="w-2 h-2 rounded-full bg-green-500/60"/>
            </div>
            <div className="flex" style={{ background: 'var(--bg-base)', minHeight: 100 }}>
              {/* Sidebar mock */}
              <div className="flex-shrink-0 w-14 border-r flex flex-col items-center py-3 gap-3" style={{ background: 'var(--bg-panel)', borderColor: 'var(--border-subtle)' }}>
                <div className="w-8 h-8 rounded-full flex items-center justify-center" style={{ background: 'var(--nav-active-bg)' }}>
                  <ChirpLogo size={14}/>
                </div>
                {[LayoutDashboard, Mic, Award, BookOpen].map((Icon, i) => (
                  <div key={i} className="w-8 h-8 rounded-lg flex items-center justify-center"
                       style={{ background: i===0 ? 'var(--nav-active-bg)' : 'transparent', color: i===0 ? 'var(--accent-400)' : 'var(--text-tertiary)' }}>
                    <Icon size={15}/>
                  </div>
                ))}
              </div>
              {/* Content */}
              <div className="flex-1 p-3">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-1.5 h-1.5 rounded-full live-dot" style={{ background: 'var(--accent-400)' }}/>
                  <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>Live</span>
                  {/* Dropdown mock */}
                  <div className="ml-auto flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs"
                       style={{ background: 'var(--bg-raised)', color: 'var(--text-primary)', border: '1px solid var(--border-default)' }}>
                    <LayoutDashboard size={10} style={{ color: 'var(--accent-400)' }}/>
                    Dashboard
                    <ChevronDown size={9} style={{ color: 'var(--text-tertiary)' }}/>
                  </div>
                </div>
                <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  ↑ Click the center dropdown to switch pages.<br/>
                  ← Use the sidebar for quick access too.
                </p>
              </div>
            </div>
          </div>
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            The <strong style={{ color: 'var(--accent-400)' }}>center dropdown</strong> in the top bar always shows the current page. Click it to go to any other page.
            The <strong style={{ color: 'var(--accent-400)' }}>sidebar</strong> collapses to icons with the ← button at the bottom.
          </p>
        </div>

        {/* Mobile nav */}
        <div className="card p-4 space-y-3">
          <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            📱 Phone: bottom navigation bar
          </p>
          <Reveal animation="animate-scale-in" threshold={0.05}><NavigationDemo/></Reveal>
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            The <strong style={{ color: 'var(--accent-400)' }}>bottom bar</strong> has Dashboard, Recordings, Live Detect, Life List, and Field Guide, plus a <strong style={{ color: 'var(--accent-400)' }}>⋮ menu</strong> for Notes, Statistics, Settings, What's New and My Profile. Admins also see Devices, Activity, Users, Logs and Tech Docs there.
          </p>
        </div>

        <div className="card p-3 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>💡 Finding the Tutorial again</p>
          <ul className="space-y-1 text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <li>• Scroll to the bottom of the <strong style={{ color: 'var(--accent-400)' }}>Dashboard</strong> to find the "Getting Started guide" link</li>
            <li>• Or navigate directly to <code style={{ fontFamily: 'monospace', color: 'var(--accent-400)' }}>/tutorial</code></li>
            <li>• Or toggle it back on in <strong style={{ color: 'var(--accent-400)' }}>Settings → My Notifications</strong></li>
          </ul>
        </div>
      </div>
    ),
  },
  {
    id: 'dashboard',
    title: 'Dashboard',
    icon: LayoutDashboard,
    color: '#22c55e',
    tldr: 'Live detections, recent recordings and today\'s journal.',
    content: (
      <div className="space-y-4">
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          The Dashboard is your home screen. From top to bottom: a live "Listening now" card
          for the most recent detection, a photo grid of every species seen today, your
          daily/weekly summary, your active species streaks and yard diversity score, four
          headline stats, and a chart with your top species.
        </p>

        <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>🔴 Listening now</p>
        <ScreenMockup label="Appears whenever the most recent detection was within the last few minutes">
          <Link to="#" onClick={e => e.preventDefault()}
                className="card-hover flex overflow-hidden rounded-xl" style={{ border: '1px solid var(--border-default)' }}>
            <div className="relative flex-shrink-0" style={{ width: 88, height: 88 }}>
              <div className="absolute inset-0 flex items-center justify-center" style={{ background: 'var(--bg-raised)' }}><BirdIcon size={32} style={{ color: 'var(--text-tertiary)' }}/></div>
              <div className="absolute top-1 left-1 inline-flex items-center gap-1 text-[8px] font-semibold px-1.5 py-0.5 rounded-full"
                   style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }}>
                <span className="w-1 h-1 rounded-full live-dot" style={{ background: 'currentColor' }}/>Live
              </div>
            </div>
            <div className="flex-1 p-3 flex flex-col justify-center min-w-0">
              <div className="flex items-start justify-between gap-2">
                <p className="font-bold text-base truncate" style={{ color: 'var(--text-primary)', fontFamily: "'Lora', serif" }}>American Robin</p>
                <span className="text-xs flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>38s ago</span>
              </div>
              <p className="text-xs italic" style={{ color: 'var(--text-tertiary)' }}>Turdus migratorius</p>
              <div className="flex gap-2 mt-1.5">
                <span className="text-xs font-semibold" style={{ color: '#4ade80' }}>● 94% confidence</span>
                <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>30s clip</span>
              </div>
            </div>
          </Link>
        </ScreenMockup>

        <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>📓 Journal</p>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          Two AI-written entries, each with its own schedule and regenerate button in
          Settings → AI Features. The <strong style={{ color: 'var(--accent-400)' }}>Daily Journal</strong>{' '}
          covers today so far. The <strong style={{ color: 'var(--accent-400)' }}>Weekly Journal</strong> covers
          the last 7 days, including arrivals and departures (a species that is new, or one that was
          regular and has gone quiet), with a little more background than a single day allows. Each
          shows a short preview with "Read more". Both are off until an AI provider is set up in Settings.
        </p>

        <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>📷 Seen today</p>
        <Reveal animation="animate-scale-in" threshold={0.05}><SeenTodayDemo/></Reveal>

        <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>🔥 Active streaks &amp; 🌿 yard diversity</p>
        <div className="card p-3 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <strong style={{ color: 'var(--accent-400)' }}>Active Streaks</strong> shows which species
            have been detected on each of the last several days, longest streak first. A streak ends
            after a full day without that species, so the list shows birds that are around now rather
            than birds that were common in the past.
          </p>
          <p className="text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <strong style={{ color: 'var(--accent-400)' }}>Yard Diversity</strong> shows species richness
            (a plain count) at the top, then a diversity score with a gauge, then a second score called
            <strong style={{ color: 'var(--accent-400)' }}> Balance</strong> as a bar. The diversity score combines
            the number of species with how evenly detections are spread across them: a month with 20 species
            where one bird dominates scores lower than 20 species heard about equally often. Balance is the
            chance that two random detections from the month are different species. It weighs common species
            more, so one rare visitor moves it less. Tap the
            <strong style={{ color: 'var(--accent-400)' }}> ⓘ</strong> icon for how to read both scores, their
            technical names (Shannon's H and Simpson's diversity) and their ranges. The ranges come from
            point-count surveys, and Chirp samples differently, so use the scores to compare your yard with
            itself over time rather than with published numbers.
          </p>
        </div>

        <div className="card p-3 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>💡 Tips</p>
          <ul className="space-y-1 text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <li>• Tap the live card to open that recording.</li>
            <li>• Tap <strong style={{ color: 'var(--accent-400)' }}>+N more</strong> on the species grid to see every bird detected today, each linked to its profile.</li>
            <li>• The <strong style={{ color: 'var(--accent-400)' }}>Today's / This Week's Summary</strong> heading switches the period. Tap "Today's" or "This Week's" in the title.</li>
            <li>• Tap any species in <strong style={{ color: 'var(--accent-400)' }}>Active Streaks</strong> to open its profile page.</li>
            <li>• Each Dashboard section folds up with the arrow in its corner, and Chirp remembers how you left it.</li>
            <li>• Use the time period buttons (6h / 24h / 7d…) further down to zoom the detection-activity chart.</li>
            <li>• Recent notes at the bottom show the latest comments from all users across every bird.</li>
            <li>• The first time you open Chirp, you pick a <strong style={{ color: 'var(--accent-400)' }}>Simplified</strong> or <strong style={{ color: 'var(--accent-400)' }}>Detailed</strong> Dashboard. Change it with the link at the bottom of the Dashboard or in Settings → Appearance. The choice is saved to your account, so it follows you to other devices.</li>
            <li>• <strong style={{ color: 'var(--accent-400)' }}>Today's Journal</strong> is an AI-written summary of the day, in the style of a birder's journal. It's off until you turn it on in Settings → AI Features, where all AI features and provider keys are. Nothing shows until the first entry has been written.</li>
            <li>• Bird profiles can also show an AI note near the top about when and how often your station has heard that species. It's set up in the same place and is written the first time you open a profile after turning it on.</li>
            <li>• <strong style={{ color: 'var(--accent-400)' }}>Device Notifications</strong> in My Profile turns on notifications for this device, including when Chirp is closed. On a phone, install the app or add it to your home screen so they arrive reliably.</li>
            <li>• When AI Second Opinion is on, a recording's page has a button that asks an AI model to review the spectrogram. Its verdict appears below the recording. It's a check on BirdNET's result and doesn't replace it.</li>
            <li>• Settings → AI Features holds the provider keys (Anthropic, OpenAI and Gemini, or an Ollama server at home, which needs an address and a model name, plus a key only if your server asks for one), a Test button for each, which provider each feature uses, and usage per provider.</li>
          </ul>
        </div>
      </div>
    ),
  },
  {
    id: 'recordings',
    title: 'Recordings',
    icon: Mic,
    color: '#3b82f6',
    tldr: 'Every clip Chirp has recorded, with its spectrogram and confidence score.',
    content: (
      <div className="space-y-4">
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          Each bird call the station detects becomes a recording card here.
          The card shows a small spectrogram, a picture of the sound.
        </p>
        <ScreenMockup label="Recording cards: tap one to open it">
          <div className="grid grid-cols-2 gap-2">
            {[
              { sp: 'American Robin', conf: '84%', t: '2h ago' },
              { sp: 'House Finch',    conf: '71%', t: '3h ago' },
              { sp: 'Song Sparrow',   conf: '90%', t: '4h ago' },
              { sp: 'Cedar Waxwing',  conf: '65%', t: '5h ago' },
            ].map(({ sp, conf, t }) => (
              <div key={sp} className="card overflow-hidden">
                <div className="h-14 flex items-center justify-center text-xs" style={{ background: '#020c08', color: '#22c55e' }}>
                  ▓▒░▓▓▒░░▒▓▓░▒
                </div>
                <div className="p-2">
                  <p className="text-xs font-medium truncate" style={{ color: 'var(--text-primary)' }}>{sp}</p>
                  <div className="flex items-center justify-between mt-0.5">
                    <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{t}</span>
                    <span className="badge badge-green" style={{ fontSize: 9 }}>{conf}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </ScreenMockup>
        <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>✨ Enhancing a clip</p>
        <Reveal animation="animate-scale-in" threshold={0.05}><EnhanceAudioDemo/></Reveal>
        <div className="card p-3 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>💡 Tips</p>
          <ul className="space-y-1 text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <li>• Tap a card to open the recording with its player, spectrogram and detections.</li>
            <li>• Tap the <strong style={{ color: 'var(--accent-400)' }}>detections count</strong> on a card to open the list of birds in it and play each call without leaving the page.</li>
            <li>• Every bird audio player has one <strong style={{ color: 'var(--accent-400)' }}>Enhance</strong> control: <strong style={{ color: 'var(--accent-400)' }}>Original</strong>, <strong style={{ color: 'var(--accent-400)' }}>Enhanced</strong> (cuts low rumble from traffic, wind and HVAC and reduces steady background noise, with a matching spectrogram) or <strong style={{ color: 'var(--accent-400)' }}>AI</strong> (neural denoising, when AI Enhance is on in Settings → AI Features; it isolates a call harder but loses sound above 8 kHz). In Enhanced, a <strong style={{ color: 'var(--accent-400)' }}>Low cut</strong> slider sets the rumble cutoff; Auto picks it from the birds detected. Settings → Detection → Playback: Enhance picks what recordings open in.</li>
            <li>• Bat recordings keep their own <strong style={{ color: 'var(--accent-400)' }}>Enhanced</strong> (slowed-down) and <strong style={{ color: 'var(--accent-400)' }}>De-wobbled</strong> toggles.</li>
            <li>• <strong style={{ color: 'var(--accent-400)' }}>AI Second Opinion</strong> asks an AI model that can read images to look at the spectrogram and rate each bird BirdNET found as likely right, likely wrong or uncertain, with its reasons. It also looks for anything BirdNET missed, such as another bird or insects. It needs an AI provider that handles images, set in Settings.</li>
            <li>• Use the filter icon (top-right) to search by species name or filter by confidence, filter by <strong style={{ color: 'var(--accent-400)' }}>device</strong> (if you have more than one), and the <strong style={{ color: 'var(--accent-400)' }}>calendar icon</strong> to narrow the list to the last 24 hours, 7/30/90 days, or a custom date range. <strong style={{ color: 'var(--accent-400)' }}>Time of day</strong> (dawn, morning, afternoon, evening, night or your own hours, in the site's time zone) narrows it further, and <strong style={{ color: 'var(--accent-400)' }}>Saved</strong> shows only recordings you've saved.</li>
            <li>• Tap <strong style={{ color: 'var(--accent-400)' }}>Save</strong> on a recording to keep it: saved recordings are never archived or deleted by automatic storage cleanup.</li>
            <li>• If bat detection is set up (a separate ultrasonic USB mic, in addition to your regular bird mic), a <strong style={{ color: 'var(--accent-400)' }}>Birds only / Bats only</strong> toggle appears next to the filters. Bat recordings show a series of pulses in the spectrogram, and Chirp tries to identify the bat species.</li>
            <li>• The <strong style={{ color: 'var(--accent-400)' }}>No detections</strong> toggle shows only recordings where nothing was identified. Use it to find false triggers or recordings to delete.</li>
            <li>• The <strong style={{ color: 'var(--accent-400)' }}>Upload</strong> button (top right) adds an audio file you recorded elsewhere. Mark it as a bird or bat recording so it's analyzed the right way. Bat uploads must come from an ultrasonic microphone (192 kHz or higher); a phone or bird microphone can't record echolocation calls, so those uploads are rejected.</li>
            <li>• The spectrogram shows frequency on the Y-axis and time on the X-axis. Bright spots = loud sounds.</li>
            <li>• You can add notes to any recording. Everyone on the site can read them.</li>
            <li>• <strong style={{ color: 'var(--accent-400)' }}>Archive</strong> a recording from its page to delete the audio and free up space. The spectrogram, detections and notes stay, and it still counts in statistics. <strong style={{ color: 'var(--accent-400)' }}>Delete</strong> removes everything. Admins can also set either to happen automatically after N days in Settings → Storage &amp; Backup; saved recordings are skipped.</li>
          </ul>
        </div>
      </div>
    ),
  },
  {
    id: 'livedetect',
    title: 'Live Detect',
    icon: AudioLines,
    color: '#f97316',
    tldr: 'Hold up your phone and see birds identified within a few seconds of calling.',
    content: (
      <div className="space-y-4">
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          The Recordings page shows what your station has already heard and analyzed.
          Live Detect listens now: you hold up your phone and get an answer within a few
          seconds, like Merlin Bird ID's live mode. Tap Live Detect in the bottom bar,
          choose a source and tap Start.
        </p>
        <ScreenMockup label="Live Detect during a session">
          <div className="space-y-2">
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full live-dot" style={{ background: '#f97316' }}/>
                <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>Listening…</span>
              </div>
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Phone mic</span>
            </div>
            <div className="h-12 rounded-lg flex items-center justify-center text-xs"
                 style={{ background: '#020c08', color: '#22c55e' }}>
              ▓▒░▓▓▒░░▒▓▓░▒░▓▒▓░▒▓▓░▒
            </div>
            {[
              { sp: 'American Robin', conf: '87%' },
              { sp: 'House Wren',     conf: '76%' },
            ].map(({ sp, conf }) => (
              <div key={sp} className="card p-2 flex items-center justify-between">
                <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>{sp}</span>
                <span className="badge badge-green" style={{ fontSize: 9 }}>{conf}</span>
              </div>
            ))}
          </div>
        </ScreenMockup>
        <div className="card p-3 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>💾 Saving a session</p>
          <p className="text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Tap Stop when you're done. If the session heard any birds, Chirp asks whether to
            save it as one recording. If you save it, the short clips are joined into a single
            recording with its own spectrogram, listed in Recordings as a Live Detect session.
            The detections stay in your history whether you save the session or not.
          </p>
        </div>
        <div className="card p-3 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>💡 Tips</p>
          <ul className="space-y-1 text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <li>• Choose <strong style={{ color: 'var(--accent-400)' }}>Phone mic</strong> for listening on the move, or <strong style={{ color: 'var(--accent-400)' }}>ChirpPi</strong> (if you have one) to listen through your station's microphone while you're away from home.</li>
            <li>• The <strong style={{ color: 'var(--accent-400)' }}>Volume boost</strong> and <strong style={{ color: 'var(--accent-400)' }}>cut low rumble</strong> sliders only change what you hear. They don't change what's analyzed or saved.</li>
            <li>• Each detected species shows a photo and confidence. Tap one to open its profile.</li>
            <li>• Live Detect uses the same identification as your station's recordings, so its detections count toward the Life List and Dashboard right away, whether or not you save the session.</li>
            <li>• Haikubox and Bird Buddy can't be used as sources here. Live Detect only works with a microphone.</li>
          </ul>
        </div>
      </div>
    ),
  },
  {
    id: 'lifelist',
    title: 'Life List',
    icon: Award,
    color: '#f59e0b',
    tldr: 'Every species your station has detected, sorted by how often it was heard.',
    content: (
      <div className="space-y-4">
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          Your Life List has every species detected at your location, with the most-detected first.
          New species are added as they're heard. You can also sort by name or by first detection.
        </p>
        <ScreenMockup label="Life List: tap a row to open the bird's profile">
          <div className="space-y-2">
            {[
              { n: 1, sp: 'American Robin',  sci: 'Turdus migratorius', det: 23, first: 'Jan 5' },
              { n: 2, sp: 'House Finch',     sci: 'Haemorhous mexicanus', det: 18, first: 'Jan 7' },
              { n: 3, sp: 'Song Sparrow',    sci: 'Melospiza melodia', det: 12, first: 'Jan 9' },
            ].map(({ n, sp, sci, det, first }) => (
              <div key={sp} className="card-hover flex items-center gap-3 p-2.5 rounded-xl">
                <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                     style={{ background: 'var(--bg-raised)', color: 'var(--text-tertiary)' }}>{n}</div>
                <div className="w-10 h-10 rounded-lg flex items-center justify-center"
                     style={{ background: 'var(--bg-raised)' }}><BirdIcon size={20} style={{ color: 'var(--text-tertiary)' }}/></div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{sp}</p>
                  <p className="text-xs italic truncate" style={{ color: 'var(--text-tertiary)' }}>{sci}</p>
                  <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>First: {first} · {det} detections</p>
                </div>
              </div>
            ))}
          </div>
        </ScreenMockup>
        <div className="card p-3 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>💡 Tips</p>
          <ul className="space-y-1 text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <li>• Filter by <strong style={{ color: 'var(--accent-400)' }}>season or month</strong> using the filter card to see which birds are present when.</li>
            <li>• Tap any row to open the full bird profile with description, range map, and example calls.</li>
            <li>• The eBird button (hover) opens that species on Cornell Lab's eBird database.</li>
          </ul>
        </div>
      </div>
    ),
  },
  {
    id: 'profile',
    title: 'Bird Profiles',
    icon: () => <BirdIcon size={16}/>,
    color: '#8b5cf6',
    tldr: 'Tap a species anywhere in Chirp to open its profile: range map, photos and an optional AI note about it in your yard.',
    content: (
      <div className="space-y-4">
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          Each bird has a profile page filled in from Wikipedia, eBird and iNaturalist, with
          photos, a description, range maps, example calls and when it's reported in your area.
        </p>
        <ScreenMockup label="Bird profile sections">
          <div className="space-y-2">
            {[
              { icon: '✨', title: 'AI Presence Summary', sub: 'Optional. A short note on when this species is heard in your yard; needs an AI provider set in Settings' },
              { icon: '📖', title: 'About', sub: 'Wikipedia description and taxonomy' },
              { icon: '🎵', title: 'Example Calls & Songs', sub: 'iNaturalist community recordings' },
              { icon: '🎙️', title: 'Recordings', sub: 'All detections of this species at your location' },
              { icon: '🗺️', title: 'Range Map', sub: 'eBird or GBIF occurrence data' },
              { icon: '📅', title: 'Seasonal Presence', sub: 'Monthly frequency bar chart' },
              { icon: '📷', title: 'Photos', sub: 'Upload photos; AI can check they show this species' },
              { icon: '📝', title: 'Notes', sub: 'Shared comments from all users' },
            ].map(({ icon, title, sub }) => (
              <div key={title} className="flex items-center gap-3 p-2 rounded-lg" style={{ background: 'var(--bg-raised)' }}>
                <span style={{ fontSize: 16 }}>{icon}</span>
                <div>
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{title}</p>
                  <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{sub}</p>
                </div>
              </div>
            ))}
          </div>
        </ScreenMockup>
        <div className="card p-3 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>💡 Tips</p>
          <ul className="space-y-1 text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <li>• If a profile has no photo or description yet, click <strong style={{ color: 'var(--accent-400)' }}>Refresh All Data</strong> to fetch it.</li>
            <li>• In the Recordings list on a profile, each entry has a small <strong style={{ color: 'var(--accent-400)' }}>Clip</strong> button that plays only that bird's call instead of the whole recording.</li>
            <li>• The <strong style={{ color: 'var(--accent-400)' }}>two ✨ icons</strong> next to each other work separately: <strong style={{ color: 'var(--accent-400)' }}>Enhance clip</strong> changes only the short clip, and <strong style={{ color: 'var(--accent-400)' }}>Enhance full recording</strong> changes the whole recording. Hover over each for its label.</li>
            <li>• Everyone on the site can read and add notes about a bird.</li>
            <li>• The range map can be switched between Wikipedia, eBird S&T, and GBIF occurrence data.</li>
            <li>
              • The Seasonal Presence bars show <strong style={{ color: 'var(--accent-400)' }}>eBird
              checklist frequency</strong> for this species. Each bar is scaled to the species' busiest
              month, so you can't compare bars between species. The Field Guide's Very Likely, Likely,
              Possible and Rare labels are ranked differently; the Field Guide section below explains how.
            </li>
          </ul>
        </div>
      </div>
    ),
  },
  {
    id: 'fieldguide',
    title: 'Field Guide',
    icon: BookOpen,
    color: '#14b8a6',
    tldr: 'Birds reported near your location, ranked by how likely they are this month.',
    content: (
      <div className="space-y-4">
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          The Field Guide lists the birds reported in your region on eBird, including ones
          Chirp hasn't detected yet. Pick a month to see what to expect then.
        </p>
        <ScreenMockup label="Field Guide with month selector">
          <div className="space-y-2">
            <div className="card p-2 space-y-2">
              {/* Month strip */}
              <div className="flex gap-px">
                {['J','F','M','A','M','J','J','A','S','O','N','D'].map((m, i) => (
                  <div key={i} className="flex-1 text-center text-xs py-1 rounded-sm"
                       style={{ background: i === 5 ? 'var(--nav-active-bg)' : 'transparent',
                                color: i === 5 ? 'var(--accent-400)' : 'var(--text-tertiary)', fontSize: 9 }}>
                    {m}
                  </div>
                ))}
              </div>
              {/* Filter tabs */}
              <div className="flex gap-1">
                {['All', 'Detected', 'Very Likely', 'Likely'].map((t, i) => (
                  <div key={t} className="px-2 py-0.5 rounded-lg text-xs"
                       style={{
                         background: i===0 ? 'var(--nav-active-bg)' : 'var(--bg-raised)',
                         color: i===0 ? 'var(--accent-400)' : 'var(--text-tertiary)',
                         border: `1px solid ${i===0 ? 'var(--border-default)' : 'var(--border-subtle)'}`,
                       }}>{t}</div>
                ))}
              </div>
            </div>
            {/* Sample cards */}
            <div className="card-hover flex items-start gap-2 p-2 rounded-xl">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'var(--bg-raised)' }}><BirdIcon size={18} style={{ color: 'var(--text-tertiary)' }}/></div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>Wood Thrush</p>
                  <span className="badge badge-green" style={{ fontSize: 9 }}>✓ Detected</span>
                </div>
                <div className="flex items-end gap-px mt-1" style={{ height: 14 }}>
                  {[0,0,.1,.3,.8,1,.9,.7,.2,0,0,0].map((h, i) => (
                    <div key={i} className="flex-1 rounded-sm"
                         style={{ height: `${Math.max(h*100, h>0?15:3)}%`, background: i===5?'var(--accent-400)':'var(--s500)' }}/>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </ScreenMockup>
        <div className="card p-3 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>📊 What the labels mean</p>
          <ul className="space-y-1.5 text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <li>
              The underlying number behind every bar is <strong style={{ color: 'var(--text-primary)' }}>the
              share of eBird checklists in your region that reported the species that month</strong>.
              The Merlin app shows the same figure as its blue frequency bars. It comes from people's
              observations, not from a model.
            </li>
            <li>
              <strong style={{ color: 'var(--accent-400)' }}>Very Likely / Likely / Possible / Rare</strong> are
              {' '}not fixed percentages. Each label is a <strong style={{ color: 'var(--text-primary)' }}>rank</strong>{' '}
              that compares the species with every other species shown for the same month. The same
              percentage can get a different label in different months: a species could be "Very Likely"
              in winter, when few species are around, and only "Possible" during spring migration.
            </li>
            <li>
              <strong style={{ color: 'var(--text-primary)' }}>"Detected Here"</strong> means your station
              has recorded the species, whatever its eBird frequency. A species can be "Detected Here" and
              "Rare" at the same time.
            </li>
          </ul>
        </div>
        <div className="card p-3 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>💡 Tips</p>
          <ul className="space-y-1 text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <li>• Tap any month to see frequency bars for that month. The highlighted bar = selected month.</li>
            <li>• "Detected Here" = Chirp has captured this species at your location.</li>
            <li>• Click <strong style={{ color: 'var(--accent-400)' }}>Refresh from eBird</strong> after setting your location in Settings.</li>
          </ul>
        </div>
      </div>
    ),
  },
  {
    id: 'settings',
    title: 'Settings & Devices',
    icon: Settings,
    color: '#64748b',
    tldr: 'Detection, AI features, devices, backups and the other settings.',
    content: (
      <div className="space-y-4">
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          Settings has tabs for My Notifications, Appearance, General, Detection, Bats,
          Alerts &amp; Email, Integrations, AI Features, Storage &amp; Backup, Access &amp; Security,
          Experimental and Diagnostics. The search box at the top finds a setting by name or by what
          it does. Tap a card's title to open it. Admins set the location, BirdNET options, storage
          limits and more; everyone can change their own theme.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {[
            { icon: '🎨', title: 'Themes', sub: '25 built-in themes, or make and save your own' },
            { icon: '🗂️', title: 'Card Defaults', sub: 'Choose whether collapsible cards start expanded or collapsed, app-wide' },
            { icon: '📍', title: 'Location', sub: 'Under Detection; sets the expected species and Field Guide data' },
            { icon: '🔑', title: 'eBird API Key', sub: 'Enables regional bird data' },
            { icon: '🧠', title: 'Detection Model', sub: 'BirdNET v3 (default; with owl checks) or BirdNET 2.4, plus confidence & sensitivity tuning' },
            { icon: '📦', title: 'Archive & Auto-Delete', sub: 'Two separate timers by age; see Tips below' },
            { icon: '📡', title: 'Haikubox', sub: 'Integrations: copy detections from a Haikubox into Chirp' },
            { icon: '🐦', title: 'Bird Buddy', sub: 'Integrations: copy postcards from your smart feeder' },
            { icon: '🔬', title: 'iNaturalist', sub: 'Integrations: personal or shared token, renewed automatically' },
            { icon: '📧', title: 'Email', sub: 'SMTP + notification preferences' },
            { icon: '🔐', title: 'Auth', sub: 'Enable login for shared servers' },
            { icon: '🤖', title: 'AI Features', sub: 'Daily and Weekly Journal, Bird Profile summaries, AI Second Opinion and AI Enhance; each cloud feature assignable to Anthropic, OpenAI, Gemini or a self-hosted Ollama server, off by default.' },
            { icon: '🦇', title: 'Bats', sub: 'Ultrasonic echolocation detection, optional species ID and wobble removal' },
            { icon: '🌙', title: 'Experimental', sub: 'Night flight calls (Nighthawk), range maps and the sightings heatmap' },
          ].map(({ icon, title, sub }) => (
            <div key={title} className="card p-3">
              <div className="flex items-center gap-2 mb-1">
                <span style={{ fontSize: 16 }}>{icon}</span>
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{title}</p>
              </div>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{sub}</p>
            </div>
          ))}
        </div>
        <div className="card p-3 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>💡 Tips</p>
          <ul className="space-y-1 text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <li>• On mobile, use the <strong style={{ color: 'var(--accent-400)' }}>⋮ menu</strong> (bottom-right) for the Field Guide, Statistics, Night Calls and Notes, then admin pages, then My Profile, Settings and What's New.</li>
            <li>• <strong style={{ color: 'var(--accent-400)' }}>Card Defaults</strong> sets whether cards on Bird Profile, Settings, Statistics and My Profile start open. A card you've opened or closed yourself stays that way. "Reset all cards to default" clears those choices.</li>
            <li>• The <strong style={{ color: 'var(--accent-400)' }}>Statistics</strong> page charts detections by month, hour, season and species. Related charts sit in pairs under one header and fold up together.</li>
            <li>• The Devices page lets you view live logs from your Pi, push config changes, and sync location.</li>
            <li>• If you have a <strong style={{ color: 'var(--accent-400)' }}>Haikubox</strong>, turn it on in Settings → Integrations. Chirp checks it every 15 minutes and lists its detections on a separate <strong style={{ color: 'var(--accent-400)' }}>Haikubox Detections</strong> page (linked from Recordings and Devices), because they come without audio.</li>
            <li>• A <strong style={{ color: 'var(--accent-400)' }}>Bird Buddy</strong> feeder is also set up in Settings → Integrations. Chirp downloads each new postcard's video, takes the audio, and identifies the bird with BirdNET like any other recording. Bird Buddy's species guess isn't used, so confidence scores stay comparable.</li>
            <li>• <strong style={{ color: 'var(--accent-400)' }}>Archive</strong> a recording (or set an age limit in Storage &amp; Backup) to delete its audio and free up space. The spectrogram, detections and notes stay, and it still counts in statistics. This is different from <strong style={{ color: 'var(--accent-400)' }}>Delete</strong>, which removes the recording entirely. Archiving can't be undone once the audio is gone.</li>
            <li>• Set <strong style={{ color: 'var(--accent-400)' }}>Min. Confidence Display</strong> to hide low-confidence detections without deleting them.</li>
            <li>• Admins can <strong style={{ color: 'var(--accent-400)' }}>backup and restore</strong> the database from Settings → Storage &amp; Backup.</li>
            <li>• The <strong style={{ color: 'var(--accent-400)' }}>Life List</strong> sorts by detections, name or first-seen date. Its Download button exports a CSV for eBird; pick <strong style={{ color: 'var(--accent-400)' }}>eBird Record Format</strong>, not Checklist Format, when importing it at eBird's Submit page.</li>
            <li>• <strong style={{ color: 'var(--accent-400)' }}>AI Features</strong> are optional and stay off until you choose a provider. The Daily Journal and Bird Profile Summaries can be written on a schedule, and profile summaries can be refreshed when they get old.</li>
          </ul>
        </div>
      </div>
    ),
  },
  {
    id: 'pwa',
    title: 'Install as an App',
    icon: Smartphone,
    color: '#22d3ee',
    tldr: 'Add Chirp to your home screen to use it like an app.',
    content: (
      <div className="space-y-4">
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          Chirp is a <strong style={{ color: 'var(--text-primary)' }}>Progressive Web App (PWA)</strong>, so you can install it from the browser on any device and use it like an app.
        </p>

        {/* Platform cards */}
        <div className="space-y-3">
          {/* iOS */}
          <div className="card p-4" style={{ border: '1px solid var(--border-subtle)' }}>
            <div className="flex items-center gap-2 mb-3">
              <span style={{ fontSize: 20 }}>🍎</span>
              <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>iPhone &amp; iPad (Safari)</p>
            </div>
            <ol className="space-y-1.5 text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>1</span>
               
                <span><span>Open Chirp in <strong style={{ color: 'var(--text-primary)' }}>Safari</strong>. Chrome on iPhone can't install web apps</span></span>
              </li>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>2</span>
               
                <span><span>Tap the <strong style={{ color: 'var(--text-primary)' }}>Share</strong> button <span style={{ color: 'var(--text-tertiary)' }}>(the box with an upward arrow: bottom center on iPhone, top right on iPad)</span></span></span>
              </li>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>3</span>
               
                <span><span>Scroll down and tap <strong style={{ color: 'var(--text-primary)' }}>Add to Home Screen</strong></span></span>
              </li>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>4</span>
               
                <span><span>Tap <strong style={{ color: 'var(--text-primary)' }}>Add</strong>. Chirp appears on your home screen with its icon</span></span>
              </li>
            </ol>
          </div>

          {/* Android */}
          <div className="card p-4" style={{ border: '1px solid var(--border-subtle)' }}>
            <div className="flex items-center gap-2 mb-3">
              <span style={{ fontSize: 20 }}>🤖</span>
              <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Android (Chrome)</p>
            </div>
            <ol className="space-y-1.5 text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>1</span>
                
                <span>Open Chirp in <strong style={{ color: 'var(--text-primary)' }}>Chrome</strong></span>
              </li>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>2</span>
                
                <span>Chrome may show an <strong style={{ color: 'var(--text-primary)' }}>"Add to Home Screen"</strong> banner; tap it. If it doesn't, tap the <strong style={{ color: 'var(--text-primary)' }}>⋮ menu</strong> (top right)</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>3</span>
                
                <span>Tap <strong style={{ color: 'var(--text-primary)' }}>Add to Home Screen</strong> or <strong style={{ color: 'var(--text-primary)' }}>Install App</strong></span>
              </li>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>4</span>
                
                <span>Tap <strong style={{ color: 'var(--text-primary)' }}>Install</strong>. Chirp opens in its own window without the browser's toolbars</span>
              </li>
            </ol>
          </div>

          {/* Desktop */}
          <div className="card p-4" style={{ border: '1px solid var(--border-subtle)' }}>
            <div className="flex items-center gap-2 mb-3">
              <span style={{ fontSize: 20 }}>💻</span>
              <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Desktop (Chrome, Edge, Brave)</p>
            </div>
            <ol className="space-y-1.5 text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>1</span>
                
                <span>Look for the <strong style={{ color: 'var(--text-primary)' }}>install icon</strong> <span style={{ color: 'var(--text-tertiary)' }}>(computer with down-arrow)</span> in the address bar and click it</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>2</span>
                
                <span>Or open the browser <strong style={{ color: 'var(--text-primary)' }}>⋮ menu → Install Chirp</strong> (or "Cast, save, and share" on Chrome)</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>3</span>
                
                <span>Click <strong style={{ color: 'var(--text-primary)' }}>Install</strong>. Chirp opens in its own window and appears in your taskbar or Dock</span>
              </li>
            </ol>
          </div>
        </div>

        <div className="card p-3" style={{ background: 'rgba(34,211,238,.06)', border: '1px solid rgba(34,211,238,.2)' }}>
          <p className="text-xs" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <strong style={{ color: '#22d3ee' }}>Why install it?</strong> The installed app loads faster, fills the screen, and opens from your home screen or taskbar without a browser. Your data stays on your Chirp server.
          </p>
        </div>
      </div>
    ),
  },
]

// The iOS app is already installed; skip the add-to-home-screen steps there.
const SECTIONS = ALL_SECTIONS.filter(s => s.id !== 'pwa' || !isApp())

export default function Tutorial() {
  const [tutorialEnabled, setTutorialEnabled] = useState(
    localStorage.getItem('chirp_tutorial_disabled') !== '1'
  )

  // Some themes (Plate, Mono, High Contrast) set --legend-mode: mono to opt
  // out of the per-topic rainbow-pill legend below — Plate and Mono because
  // it breaks their single-ink-color design discipline, High Contrast
  // because arbitrary hex colors have no guaranteed WCAG contrast ratio.
  // Read from the live theme rather than hardcoding theme IDs here, so any
  // future theme can opt in/out the same way every other override works.
  const [legendMono, setLegendMono] = useState(false)
  useEffect(() => {
    const checkLegendMode = () => {
      const mode = getComputedStyle(document.documentElement).getPropertyValue('--legend-mode').trim()
      setLegendMono(mode === 'mono')
    }
    checkLegendMode()
    window.addEventListener('chirp-theme-changed', checkLegendMode)
    return () => window.removeEventListener('chirp-theme-changed', checkLegendMode)
  }, [])

  // Stamp the "last shown" time every time the user visits this page.
  // This resets the 12-hour clock so that manually navigating to the
  // tutorial doesn't trigger another redirect shortly afterward.
  useEffect(() => {
    // Don't overwrite the far-future stamp set when the user disables the tutorial
    const disabled = localStorage.getItem('chirp_tutorial_disabled') === '1'
    if (!disabled) {
      localStorage.setItem('chirp_tutorial_shown', String(Date.now()))
    }
  }, [])

  const handleToggle = (enabled) => {
    setTutorialEnabled(enabled)
    if (enabled) {
      // Re-enable: remove the disabled flag; keep chirp_tutorial_shown
      // so the redirect still won't fire for another 12 hours
      localStorage.removeItem('chirp_tutorial_disabled')
    } else {
      // Disable: set the flag AND push chirp_tutorial_shown far into the
      // future — this survives even if the disabled flag is later evicted
      // by iOS Safari's 7-day localStorage purge.
      localStorage.setItem('chirp_tutorial_disabled', '1')
      const farFuture = Date.now() + 100 * 365 * 24 * 60 * 60 * 1000  // ~100 years
      localStorage.setItem('chirp_tutorial_shown', String(farFuture))
    }
  }

  const TutorialToggle = ({ className = '' }) => (
    <div className={`flex items-center justify-between p-4 rounded-xl ${className}`}
         style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
      <div>
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          Show this guide on startup
        </p>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
          When enabled, Chirp redirects here once every 12 hours when you open the app
        </p>
      </div>
      <input type="checkbox" className="toggle flex-shrink-0"
             checked={tutorialEnabled}
             onChange={e => handleToggle(e.target.checked)}/>
    </div>
  )

  // Real scroll-spy: tracks each section's actual position relative to the
  // viewport midpoint, not a decorative fake. Drives both the progress bar
  // and the active-state highlight on the matching quick-nav pill below.
  //
  // Root-caused a real bug in an earlier version of this that used
  // IntersectionObserver's intersection RATIO to pick the "winning"
  // section: ratio is the wrong metric when sections have very different
  // heights (true on this page — the Dashboard section, with its demo, is
  // much taller than several others). A long section barely scrolled into
  // view has a small ratio and could lose to a short section that's fully
  // visible, even though the short one isn't actually where the reader's
  // attention is — this is exactly why highlighting "didn't always work."
  // Switched to the explicitly correct, requested algorithm: the active
  // section is the LAST one whose top edge has scrolled above the
  // viewport's vertical midpoint — checked via getBoundingClientRect on
  // scroll (the standard approach for a position-relative-to-a-fixed-line
  // check; IntersectionObserver's threshold model isn't built for this).
  const [activeSection, setActiveSection] = useState(SECTIONS[0].id)
  useEffect(() => {
    const scroller = document.querySelector('main') || window
    const computeActive = () => {
      const container = scroller === window ? document.documentElement : scroller
      const scrollTop = scroller === window ? window.scrollY : scroller.scrollTop
      const viewHeight = scroller === window ? window.innerHeight : scroller.clientHeight
      const midpoint = scrollTop + viewHeight / 2
      let current = SECTIONS[0].id
      for (const s of SECTIONS) {
        const el = document.getElementById(s.id)
        if (!el) continue
        const offsetTop = el.getBoundingClientRect().top +
          (scroller === window ? window.scrollY : scroller.scrollTop) -
          (scroller === window ? 0 : scroller.getBoundingClientRect().top)
        if (offsetTop < midpoint) current = s.id
        else break
      }
      setActiveSection(current)
    }
    computeActive()
    scroller.addEventListener('scroll', computeActive, { passive: true })
    window.addEventListener('resize', computeActive)
    return () => {
      scroller.removeEventListener('scroll', computeActive)
      window.removeEventListener('resize', computeActive)
    }
  }, [])

  const scrollToSection = (id) => {
    const scroller = document.querySelector('main') || window
    const el = document.getElementById(id)
    if (!el) return
    if (scroller === window) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } else {
      const containerTop = scroller.getBoundingClientRect().top
      const elTop = el.getBoundingClientRect().top
      const offset = elTop - containerTop + scroller.scrollTop - 16
      scroller.scrollTo({ top: offset, behavior: 'smooth' })
    }
    setActiveSection(id)
  }

  const scrollToTop = () => {
    const scroller = document.querySelector('main') || window
    if (scroller === window) {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } else {
      scroller.scrollTo({ top: 0, behavior: 'smooth' })
    }
    setActiveSection(SECTIONS[0].id)
  }

  const activeIdx = SECTIONS.findIndex(s => s.id === activeSection)
  const progressPct = ((activeIdx + 1) / SECTIONS.length) * 100

  return (
    <div className="page-root max-w-2xl mx-auto">
      {/* Slim scroll-progress bar — sticky at top of the scrolling main
          container (not fixed to the viewport, which put it behind the
          app header). Negative margins cancel page-root's padding so the
          bar runs edge-to-edge. z-30 keeps it above card content. */}
      <div className="sticky top-0 z-30 tutorial-progress-bar"
           style={{
             height: 3,
             background: 'var(--border-subtle)',
             marginBottom: -3,
           }}>
        <div style={{
          height: '100%', width: `${progressPct}%`,
          background: legendMono ? 'var(--accent-400)' : (SECTIONS[activeIdx]?.color || 'var(--accent-400)'),
          transition: 'width .4s ease, background .4s ease',
        }}/>
      </div>

      {/* Header */}
      <div className="mb-8 animate-slide-down">
        <Link to="/" className="btn-ghost mb-4 inline-flex items-center gap-1.5 text-sm">
          <ArrowLeft size={14}/> Back to Dashboard
        </Link>
        <div className="flex items-center gap-4 mb-3">
          <ChirpLogo size={48} animate/>
          <div>
            <h1 className="font-display text-3xl font-bold" style={{ color: 'var(--text-primary)' }}>
              Getting Started
            </h1>
            <p className="text-base mt-1" style={{ color: 'var(--text-secondary)' }}>
              A short guide to each page of Chirp.
            </p>
            <p className="text-xs mt-2 flex items-center gap-1.5" style={{ color: 'var(--text-tertiary)' }}>
              <Clock size={11}/> {SECTIONS.length} sections, about 5 minutes to read. Tap a section below or scroll through.
            </p>
            <p className="text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>
              Also online: the <a href="https://ourchirp.com/guide.html" target="_blank" rel="noopener" style={{ color: 'var(--accent-400)' }}>user guide ↗</a> and
              the <a href="https://ourchirp.com/setup.html" target="_blank" rel="noopener" style={{ color: 'var(--accent-400)' }}>setup guide ↗</a> for stations and servers.
            </p>
          </div>
        </div>
        {/* Tutorial on/off toggle */}
        <TutorialToggle className="mb-4"/>

        {/* Quick nav — the pill for whichever section is actually in view
            right now gets a filled, elevated treatment instead of the flat
            outline style every other pill uses, so the reader always has a
            real sense of where they are in a now-longer page. */}
        <div className="flex flex-wrap gap-2 mt-4">
          {SECTIONS.map((s, i) => {
            const isActive = s.id === activeSection
            return (
              <button key={s.id} onClick={() => scrollToSection(s.id)}
                 className="px-3 py-1 rounded-full text-xs font-medium transition-all hover:scale-105 animate-pop-in"
                 style={{
                   animationDelay: `${i * 30}ms`,
                   transform: isActive ? 'scale(1.08)' : 'scale(1)',
                   boxShadow: isActive ? `0 2px 10px ${(legendMono ? 'var(--accent-400)' : s.color)}55` : 'none',
                   ...(legendMono
                     ? { background: isActive ? 'var(--accent-400)' : 'var(--nav-active-bg)', color: isActive ? 'var(--bg-base)' : 'var(--accent-400)', border: '1px solid var(--border-default)' }
                     : { background: isActive ? s.color : s.color + '18', color: isActive ? '#fff' : s.color, border: `1px solid ${s.color}33` })
                 }}>
                {s.title}
              </button>
            )
          })}
        </div>
      </div>

      {/* Sections */}
      <div className="space-y-2">
        {SECTIONS.map((section, i) => {
          const isActive = section.id === activeSection
          return (
            <Reveal key={section.id} threshold={0.08}>
              {/* card, not card-hover: these aren't links, and card-hover's tap
                  scale moved the Back to top button out from under the finger. */}
              <div id={section.id} className="card p-6 transition-[border-color,box-shadow] duration-300"
                   style={{
                     borderColor: isActive ? (legendMono ? 'var(--border-focus)' : section.color + '55') : undefined,
                     boxShadow: isActive ? `0 4px 24px ${(legendMono ? 'var(--accent-400)' : section.color)}1a` : undefined,
                   }}>
                <div className="flex items-center gap-3 mb-1.5">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-300"
                       style={legendMono
                         ? { background: isActive ? 'var(--accent-400)' : 'var(--nav-active-bg)', border: '1px solid var(--border-default)' }
                         : { background: isActive ? section.color : section.color + '18', border: `1px solid ${section.color}33` }}>
                    <span className="text-sm font-bold transition-colors duration-300"
                          style={{ color: isActive ? (legendMono ? 'var(--bg-base)' : '#fff') : (legendMono ? 'var(--accent-400)' : section.color) }}>{i + 1}</span>
                  </div>
                  <h2 className="font-display text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {section.title}
                  </h2>
                </div>
                {section.tldr && (
                  <p className="text-sm mb-4 pl-11" style={{ color: 'var(--text-tertiary)', fontStyle: 'italic' }}>
                    {section.tldr}
                  </p>
                )}
                {!section.tldr && <div className="mb-4"/>}
                {section.content}
                {i > 0 && (
                  <button onClick={scrollToTop}
                          className="tactile-press flex items-center gap-1.5 text-xs mt-5 pt-4 transition-colors hover:opacity-80"
                          style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-tertiary)' }}>
                    <ArrowUp size={12}/> Back to top
                  </button>
                )}
              </div>
            </Reveal>
          )
        })}
      </div>

      {/* Tutorial toggle at bottom too */}
      <TutorialToggle/>

      {/* Footer CTA */}
      <div className="card p-6 text-center mt-6" style={{ background: 'var(--gradient-hero)' }}>
        <ChirpLogo size={40} animate className="justify-center mb-3"/>
        <h3 className="font-display text-xl font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          Ready to explore?
        </h3>
        <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
          Head to the Dashboard to see what's been detected at your location.
        </p>
        <Link to="/" className="btn-primary">
          Go to Dashboard <ArrowRight size={13}/>
        </Link>
      </div>
    </div>
  )
}
