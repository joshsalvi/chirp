import { useEffect, useState, useRef, useCallback, lazy, Suspense } from 'react'
import { isApp, deviceName, native } from '../native'
import { getIconChoice, setIconChoice, iconForTheme } from '../lib/appIcon'
import { DEFAULTS } from '../lib/constants'
import { Link, useSearchParams } from 'react-router-dom'
import {
  MapPin, Key, Bell, Eye, EyeOff, Save, Check, RefreshCw, Trash2, Plus,
  ChevronDown, Brain, Lock, HardDrive, Sliders, Clock, FlaskConical,
  Palette, CheckCircle, Mail, Send, Smartphone, GripVertical, Stethoscope,
  Download, AlertCircle, CheckCircle2, XCircle, Server, Database, Cpu, Zap, Mic, Activity,
  Plug, Radio, LayoutDashboard, Sparkles, X, Search, ChevronRight, ChevronLeft, Volume2, AudioLines, Moon, Globe, Calendar, Cloud
} from 'lucide-react'
import { api, clearApiCache } from '../lib/api'
import { saveUrl } from '../lib/download'
import MicFrequencyResponse, { PhoneMicTest } from './MicFrequencyResponse'
import ExperimentalModels from './ExperimentalModels'
import DetectionModel from './DetectionModel'
import { PALETTES, DEFAULT_PALETTE } from '../lib/detectionColors'
import { BirdIcon, BatIcon } from './BirdBatIcons'
import GeomodelDownloadPanel from './GeomodelDownloadPanel'
import { AABIcon, MacaulayIcon, INatIcon, BirdLifeIcon, EbirdSTIcon } from './MapSourceIcons'
import { setGlobalTimezone } from '../lib/time'
import { useAppInfo } from '../lib/appVersion'
import { THEMES, applyTheme, getStoredTheme, getCustomThemes, saveCustomTheme, deleteCustomTheme } from '../lib/theme'
import UnifiedCard from './UnifiedCard'
const NearMisses = lazy(() => import('./NearMisses'))
const NightThresholds = lazy(() => import('./NightThresholds'))
const MyNotifications = lazy(() => import('./MyNotifications'))
import { getGlobalDefault, setGlobalDefault, resetAllCardOverrides, GLOBAL_DEFAULTS } from '../lib/cardState'
import { DashboardModePicker } from './Dashboard'
import { SpectrogramIcon, MigrationIcon, RoostIcon, EchoCaveIcon,
         PaperIcon, MonoIcon, TerminalIcon, PlateIcon, OscilloscopeIcon,
         AviaryIcon, CornellIcon, FieldNotebookIcon, DraculaIcon,
         NexradIcon, MothTrapIcon } from './ThemeIcons'

const THEME_ICONS = {
  spectrogram: SpectrogramIcon, migration: MigrationIcon, roost: RoostIcon, echocave: EchoCaveIcon,
  paper: PaperIcon, mono: MonoIcon, terminal: TerminalIcon, plate: PlateIcon,
  oscilloscope: OscilloscopeIcon, aviary: AviaryIcon, cornell: CornellIcon,
  fieldnotebook: FieldNotebookIcon, dracula: DraculaIcon, nexrad: NexradIcon, mothtrap: MothTrapIcon,
}

// All IANA timezones grouped by region for the dropdown
const TIMEZONE_GROUPS = [
  { label: 'US & Canada', zones: [
    'America/New_York','America/Detroit','America/Indiana/Indianapolis',
    'America/Chicago','America/Winnipeg','America/Denver','America/Phoenix',
    'America/Los_Angeles','America/Anchorage','America/Juneau','Pacific/Honolulu',
    'America/Halifax','America/Toronto','America/Vancouver','America/Whitehorse',
  ]},
  { label: 'Central & South America', zones: [
    'America/Mexico_City','America/Bogota','America/Lima','America/Santiago',
    'America/Sao_Paulo','America/Argentina/Buenos_Aires','America/Caracas',
  ]},
  { label: 'Europe', zones: [
    'Europe/London','Europe/Dublin','Europe/Lisbon',
    'Europe/Paris','Europe/Berlin','Europe/Amsterdam','Europe/Brussels',
    'Europe/Madrid','Europe/Rome','Europe/Zurich','Europe/Stockholm',
    'Europe/Warsaw','Europe/Prague','Europe/Vienna','Europe/Budapest',
    'Europe/Bucharest','Europe/Athens','Europe/Helsinki','Europe/Oslo',
    'Europe/Copenhagen','Europe/Kiev','Europe/Moscow','Europe/Istanbul',
  ]},
  { label: 'Africa', zones: [
    'Africa/Cairo','Africa/Casablanca','Africa/Lagos',
    'Africa/Nairobi','Africa/Johannesburg','Africa/Accra',
  ]},
  { label: 'Middle East', zones: [
    'Asia/Dubai','Asia/Riyadh','Asia/Qatar','Asia/Kuwait',
    'Asia/Baghdad','Asia/Beirut','Asia/Jerusalem','Asia/Tehran',
  ]},
  { label: 'Asia & Pacific', zones: [
    'Asia/Kolkata','Asia/Colombo','Asia/Dhaka','Asia/Kathmandu',
    'Asia/Karachi','Asia/Tashkent','Asia/Almaty',
    'Asia/Bangkok','Asia/Ho_Chi_Minh','Asia/Jakarta',
    'Asia/Shanghai','Asia/Hong_Kong','Asia/Taipei','Asia/Singapore',
    'Asia/Manila','Asia/Seoul','Asia/Tokyo',
    'Asia/Vladivostok','Asia/Magadan','Asia/Kamchatka',
  ]},
  { label: 'Australia & Pacific', zones: [
    'Australia/Perth','Australia/Darwin','Australia/Adelaide',
    'Australia/Sydney','Australia/Melbourne','Australia/Brisbane',
    'Australia/Hobart','Pacific/Auckland','Pacific/Fiji',
    'Pacific/Guam','Pacific/Port_Moresby',
  ]},
  { label: 'UTC / Other', zones: [
    'UTC','Etc/GMT','Etc/GMT+1','Etc/GMT+2','Etc/GMT+3','Etc/GMT+4',
    'Etc/GMT+5','Etc/GMT+6','Etc/GMT-1','Etc/GMT-2','Etc/GMT-3',
  ]},
]
// flat list for backwards compat
const TIMEZONES = TIMEZONE_GROUPS.flatMap(g => g.zones)

// Admin-only — which of Dashboard's cards show up, set separately per
// mode (see DashboardStyleSection just below for the per-user mode
// choice this complements). The backend's null-means-everything default
// can't be round-tripped back to null through the settings PUT endpoint
// (it uses exclude_none, so a field once set can't be unset that way),
// so this expands a null response into an explicit "every section"
// list right away — the save button always sends an explicit list, never
// relies on omission to mean "select all".
function DashboardSectionsSettings() {
  const [sections, setSections] = useState(null)
  const [full, setFull] = useState(null)
  const [simplified, setSimplified] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.settings.dashboardSections().then(r => {
      setSections(r.sections)
      setFull(new Set(r.full ?? r.sections.map(s => s.id)))
      setSimplified(new Set(r.simplified ?? r.sections.map(s => s.id)))
    }).catch(() => {})
  }, [])

  const toggle = (which, id) => {
    const setter = which === 'full' ? setFull : setSimplified
    setter(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const save = async () => {
    setSaving(true)
    try {
      await api.settings.update({
        dashboard_sections_full: Array.from(full),
        dashboard_sections_simplified: Array.from(simplified),
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      // Non-fatal — matches this page's other save buttons, which stay
      // silent on failure rather than surfacing a dedicated error state.
    } finally {
      setSaving(false)
    }
  }

  if (!sections || !full || !simplified) return null

  return (
    <Section icon={LayoutDashboard} title="Dashboard Sections" id="settings-appearance-dashboard-sections">
      <p className="text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>
Choose which Dashboard cards to show in Detailed and Simplified mode. A hidden card's data isn't loaded, so turning off cards you don't use makes the Dashboard faster.
</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {['full', 'simplified'].map(which => (
          <div key={which}>
            <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--text-tertiary)' }}>
              {which === 'full' ? 'Detailed mode' : 'Simplified mode'}
            </p>
            <div className="space-y-1.5">
              {sections.map(s => {
                const checked = (which === 'full' ? full : simplified).has(s.id)
                return (
                  <label key={s.id} className="flex items-start gap-2 cursor-pointer">
                    <input type="checkbox" checked={checked}
                           onChange={() => toggle(which, s.id)}
                           className="w-4 h-4 mt-0.5 accent-chirp-500 flex-shrink-0"/>
                    <div className="min-w-0">
                      <p className="text-sm" style={{ color: 'var(--text-primary)' }}>{s.label}</p>
                      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{s.description}</p>
                    </div>
                  </label>
                )
              })}
            </div>
          </div>
        ))}
      </div>
      <button onClick={save} disabled={saving}
              className="mt-4 px-4 py-2 rounded-lg text-sm font-semibold"
              style={{ background: 'var(--accent-500)', color: '#000', opacity: saving ? 0.7 : 1 }}>
        {saving ? 'Saving…' : saved ? 'Saved!' : 'Save'}
      </button>
    </Section>
  )
}

function DashboardStyleSection() {
  const [mode, setMode] = useState(null)
  const [saving, setSaving] = useState(false)
  const [showPicker, setShowPicker] = useState(false)

  useEffect(() => {
    api.auth.whoami().then(u => setMode(u?.dashboard_mode || 'detailed')).catch(() => setMode('detailed'))
  }, [])

  const choose = async (m) => {
    setMode(m)
    setSaving(true)
    try { await api.auth.updateProfile({ dashboard_mode: m }) } catch (e) {}
    setSaving(false)
    setShowPicker(false)
  }

  if (mode === null) return null

  return (
    <Section icon={LayoutDashboard} title="Dashboard Style" id="settings-appearance-dashboard">
      <p className="text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>
        How much shows up on your Dashboard. This is personal to your account, not this browser.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
        {[
          { id: 'simplified', emoji: '✨', label: 'Simplified', desc: "Just the essentials — what's singing now, today's activity, and a quick summary." },
          { id: 'detailed', emoji: '📊', label: 'Detailed', desc: 'Everything — streaks, yard diversity, activity charts, top species, recordings and notes.' },
        ].map(opt => (
          <button key={opt.id} onClick={() => choose(opt.id)} disabled={saving}
                  className="text-left p-4 rounded-xl transition-all disabled:opacity-60"
                  style={{
                    background: mode === opt.id ? 'var(--nav-active-bg)' : 'var(--bg-raised)',
                    border: `1px solid ${mode === opt.id ? 'var(--border-focus)' : 'var(--border-subtle)'}`,
                  }}>
            <p className="font-semibold text-sm mb-1" style={{ color: mode === opt.id ? 'var(--accent-400)' : 'var(--text-primary)' }}>
              {opt.emoji} {opt.label} {mode === opt.id && '· current'}
            </p>
            <p className="text-xs" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>{opt.desc}</p>
          </button>
        ))}
      </div>
      <button onClick={() => setShowPicker(true)}
              className="text-xs underline hover:opacity-80" style={{ color: 'var(--text-tertiary)' }}>
        View the original picker again
      </button>
      {showPicker && (
        <DashboardModePicker onChoose={choose} onClose={() => setShowPicker(false)}/>
      )}
    </Section>
  )
}

// ── App icon (iPhone/iPad app only) ─────────────────────────────────────────
function AppIconSection() {
  const [show, setShow] = useState(false)
  const [choice, setChoice] = useState(getIconChoice())
  const [theme, setTheme] = useState(getStoredTheme())
  const [msg, setMsg] = useState(null)
  const [current, setCurrent] = useState(null)    // the icon on the Home Screen now
  useEffect(() => {
    native.appIcon.available().then(ok => { setShow(ok); if (ok) native.appIcon.current().then(setCurrent) })
  }, [])
  useEffect(() => {
    const on = e => setTheme(e.detail?.theme || getStoredTheme())
    window.addEventListener('chirp-theme-changed', on)
    return () => window.removeEventListener('chirp-theme-changed', on)
  }, [])
  if (!show) return null
  const shown = choice === 'theme' ? (iconForTheme(theme) || current) : choice === 'keep' ? current : choice
  const pick = async (c) => {
    setChoice(c)
    setMsg(null)
    const ok = await setIconChoice(c, theme)
    if (ok && c !== 'keep') setCurrent(c === 'theme' ? (iconForTheme(theme) || current) : c)
    if (!ok && (c !== 'theme' || iconForTheme(theme))) setMsg('Couldn\u2019t change the icon. Try again with Chirp open.')
  }
  return (
    <Section icon={Smartphone} title="App Icon" id="settings-appearance-icon">
      <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)' }}>
        The Chirp icon on this {deviceName()}'s Home Screen. The one you pick stays when you change themes,
        unless you choose Match my theme. iOS confirms each change with a short alert.
      </p>
      <div className="flex gap-2 mb-4">
        {[['pick', 'Choose an icon'], ['theme', 'Match my theme']].map(([k, label]) => {
          const on = k === 'theme' ? choice === 'theme' : choice !== 'theme'
          return (
            <button key={k} type="button"
                    onClick={() => k === 'theme' ? pick('theme') : choice === 'theme' && pick('keep')}
                    className="text-xs px-3 py-1.5 rounded-full"
                    style={{ background: on ? 'var(--nav-active-bg)' : 'var(--bg-raised)', color: on ? 'var(--nav-active-text)' : 'var(--text-secondary)',
                             border: `1px solid ${on ? 'var(--border-focus)' : 'var(--border-subtle)'}` }}>
              {label}
            </button>
          )
        })}
      </div>
      {choice === 'theme' && !iconForTheme(theme) && (
        <p className="text-xs mb-3" style={{ color: 'var(--text-tertiary)' }}>Custom themes have no icon of their own, so the last one stays.</p>
      )}
      <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(64px, 1fr))' }}>
        {THEMES.map(t => {
          const on = shown === t.id
          return (
            <button key={t.id} type="button" onClick={() => pick(t.id)} title={t.name}
                    className="flex flex-col items-center gap-1" aria-pressed={on}>
              <img src={`/app-icons/${t.id}.png`} alt="" width={52} height={52} loading="lazy"
                   style={{ borderRadius: 12, outline: on ? '2px solid var(--accent-400)' : '1px solid var(--border-subtle)', outlineOffset: 2 }}/>
              <span className="text-[10px] truncate max-w-full" style={{ color: on ? 'var(--accent-400)' : 'var(--text-tertiary)' }}>{t.name}</span>
            </button>
          )
        })}
      </div>
      {msg && <p className="text-xs mt-3" style={{ color: 'var(--pastel-red)' }}>{msg}</p>}
    </Section>
  )
}

function ThemeSection() {
  const [activeTheme, setActiveTheme] = useState(getStoredTheme())
  const [customThemes, setCustomThemes] = useState(() => Object.values(getCustomThemes()))
  const handleTheme = (id) => { setActiveTheme(id); applyTheme(id) }
  const groups = [...new Set(THEMES.map(t => t.group))]

  const refreshCustomThemes = () => setCustomThemes(Object.values(getCustomThemes()))

  return (
    <Section icon={Palette} title="Theme" id="settings-appearance-theme">
      <p className="text-xs mb-5" style={{ color: 'var(--text-secondary)' }}>
        Choose a color theme. Changes apply instantly.
      </p>
      {groups.map(group => (
        <div key={group} className="mb-5 last:mb-0">
          <p className="text-xs font-semibold uppercase tracking-wider mb-2.5" style={{ color: 'var(--text-tertiary)' }}>
            {group}{group === 'Accessibility' && <span className="ml-1.5 normal-case font-normal tracking-normal" style={{ color: 'var(--accent-400)' }}>· WCAG AA</span>}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {THEMES.filter(t => t.group === group).map(theme => (
              <button key={theme.id} onClick={() => handleTheme(theme.id)}
                className="flex items-center gap-3 p-3 rounded-xl transition-all text-left"
                style={{
                  background: activeTheme === theme.id ? 'var(--nav-active-bg)' : 'var(--bg-raised)',
                  border: `1px solid ${activeTheme === theme.id ? 'var(--border-focus)' : 'var(--border-subtle)'}`,
                }}>
                <div className="relative flex-shrink-0" style={{ width: 30, height: 30 }}>
                  <div className="absolute inset-0 rounded-full overflow-hidden flex items-center justify-center"
                       style={{ background: theme.swatch[0], border: '1px solid rgba(255,255,255,.08)' }}>
                    {THEME_ICONS[theme.iconId]
                      ? (() => { const Icon = THEME_ICONS[theme.iconId]; return <Icon size={16}/> })()
                      : <div className="absolute inset-0 rounded-full" style={{
                          background: `radial-gradient(circle at 68% 50%, ${theme.swatch[1]} 0%, transparent 65%)`
                        }}/>}
                  </div>
                  {activeTheme === theme.id && (
                    <div className="absolute -bottom-0.5 -right-0.5 rounded-full flex items-center justify-center"
                         style={{ width: 14, height: 14, background: 'var(--bg-card)', border: '1.5px solid var(--bg-card)' }}>
                      <CheckCircle size={14} style={{ color: theme.swatch[1] }}/>
                    </div>
                  )}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{theme.name}</p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{theme.description}</p>
                </div>
              </button>
            ))}
          </div>
        </div>
      ))}
      {activeTheme === 'contrast' && (
        <div className="mt-3 p-3 rounded-xl text-xs" style={{ background: 'rgba(255,255,0,.08)', border: '1px solid rgba(255,255,0,.3)', color: '#ffff99' }}>
          High Contrast mode active — WCAG AA compliant. Grain and gradients disabled.
        </div>
      )}

      <CustomThemeBuilder
        customThemes={customThemes}
        activeTheme={activeTheme}
        onApply={handleTheme}
        onChange={refreshCustomThemes}
      />
    </Section>
  )
}
function Section({ icon, title, id, children }) {
  // `id` here is the pre-existing DOM anchor id used by Settings.jsx's own
  // jump-to-section feature (scrollIntoView by getElementById) — kept
  // exactly as-is via UnifiedCard's domId prop. The cardState key is a
  // separately-namespaced derivative so it can never collide with a
  // same-named card on another page, while the DOM id a person can
  // already deep-link to stays unchanged.
  return (
    <UnifiedCard id={id ? `settings:${id}` : undefined} domId={id} title={title} icon={icon} variant="plain">
      {children}
    </UnifiedCard>
  )
}

function CardExpandDefaultControl() {
  const [globalDefault, setGlobalDefaultState] = useState(() => getGlobalDefault())
  const [justReset, setJustReset] = useState(false)

  const choose = (value) => {
    setGlobalDefault(value)
    setGlobalDefaultState(value)
  }

  const handleReset = () => {
    resetAllCardOverrides()
    setJustReset(true)
    setTimeout(() => setJustReset(false), 2000)
  }

  return (
    <Field label="Card expand/collapse default"
           hint="Sets whether cards on Bird Profile, Settings, Statistics and My Profile start open or closed. A card you've opened or closed yourself keeps that.">
      <div className="flex items-center gap-2 flex-wrap">
        {[[GLOBAL_DEFAULTS.EXPANDED, 'Expanded'], [GLOBAL_DEFAULTS.COLLAPSED, 'Collapsed']].map(([value, label]) => (
          <button key={value} type="button" onClick={() => choose(value)}
                  className="text-sm px-3 py-1.5 rounded-lg font-medium transition-all"
                  style={globalDefault === value
                    ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)', border: '1px solid var(--border-default)' }
                    : { background: 'var(--bg-raised)', color: 'var(--text-tertiary)', border: '1px solid var(--border-subtle)' }
                  }>
            {label}
          </button>
        ))}
        <button type="button" onClick={handleReset}
                className="text-sm px-3 py-1.5 rounded-lg font-medium transition-all flex items-center gap-1.5"
                style={{ background: 'var(--bg-raised)', color: justReset ? '#4ade80' : 'var(--text-tertiary)', border: '1px solid var(--border-subtle)' }}>
          {justReset ? <><Check size={14}/> Reset</> : 'Reset all cards to default'}
        </button>
      </div>
    </Field>
  )
}

function BatMicInfoBox() {
  // Collapsed by default per explicit request — this is a long block of
  // hardware-shopping detail that isn't needed at a glance; the warning
  // icon and headline alone are enough to signal "read this before you
  // flip the toggle above" without taking up vertical space until asked.
  const [open, setOpen] = useState(false)
  return (
    <div className="text-xs bg-amber-900/15 border border-amber-700/30 rounded px-3 py-2.5" style={{ color: 'var(--pastel-amber-soft)' }}>
      <button onClick={() => setOpen(o => !o)}
              className="w-full flex items-center justify-between gap-2 text-left font-semibold">
        <span className="flex items-center gap-1.5">⚠️ Requires a separate ultrasonic USB microphone</span>
        <ChevronDown size={14} className="flex-shrink-0 transition-transform duration-200"
                     style={{ transform: open ? 'rotate(180deg)' : 'none' }}/>
      </button>
      {open && (
        <div className="space-y-1.5 mt-2">
          <p style={{ color: 'var(--pastel-amber-light)' }}>
Bat calls are about 15–120 kHz. A standard USB mic, including the ReSpeaker, records at 48 kHz and can't hear above 24 kHz. You need an ultrasonic mic that records at 192 kHz or more:
</p>
          <ul className="space-y-1 pl-4 list-disc" style={{ color: 'var(--pastel-amber-light)' }}>
            <li>
              <strong>AudioMoth USB Microphone</strong> (~$80–100) — cheapest option, not a
              heterodyne toy: genuine full spectrum to 384kHz, open-source hardware, documented
              to work plugged into a Raspberry Pi directly.
            </li>
            <li>
              <strong>Dodotronic UltraMic 192K/200K/250K</strong> (~$200–275) — same product
              line at different sample rates; higher covers more high-frequency species.
            </li>
            <li>
              <strong>Pettersson M500-384</strong> (~$430–470) — standard USB audio device, no
              custom drivers, native Linux support, full spectrum to 384kHz. The safest
              mainstream choice for this Pi-based setup.
            </li>
            <li>
              <strong>Dodotronic UltraMic Evo 384K</strong> (~$745–800) — top of the range, dual
              omnidirectional sensors and the lowest self-noise of this lineup. Likely overkill
              for casual backyard detection.
            </li>
          </ul>
          <p style={{ color: 'var(--pastel-amber-light)' }}>
Without one this does nothing: the station checks the mic's sample rate at startup and won't start bat detection if it's too low.
</p>
          <p style={{ color: 'var(--pastel-amber-light)' }}>
It runs alongside the bird mic; the ultrasonic mic gets a separate audio stream.
</p>
        </div>
      )}
    </div>
  )
}

// Drag-and-drop reorderable list for the map source TABS shown on bird
// profiles (Settings → Map Tab Order). Uses native HTML5 drag-and-drop
// (draggable + onDragStart/onDragOver/onDrop) rather than a new
// dependency — this is a simple 4-5-item list, not worth pulling in a
// full DnD library for.
const MAP_TAB_LABELS = {
  aab: { Icon: AABIcon, label: 'All About Birds' },
  macaulay: { Icon: MacaulayIcon, label: 'Macaulay Library' },
  geomodel: { Icon: INatIcon, label: 'iNat Geomodel' },
  birdlife: { Icon: BirdLifeIcon, label: 'BirdLife International' },
  ebird_st: { Icon: EbirdSTIcon, label: 'eBird Status & Trends' },
}

function MapTabOrderList({ order, onChange }) {
  const [dragIndex, setDragIndex] = useState(null)
  const [overIndex, setOverIndex] = useState(null)

  const handleDrop = (dropIndex) => {
    if (dragIndex === null || dragIndex === dropIndex) {
      setDragIndex(null); setOverIndex(null)
      return
    }
    const next = [...order]
    const [moved] = next.splice(dragIndex, 1)
    next.splice(dropIndex, 0, moved)
    onChange(next)
    setDragIndex(null); setOverIndex(null)
  }

  return (
    <div className="space-y-1.5">
      {order.map((id, i) => {
        const def = MAP_TAB_LABELS[id]
        if (!def) return null
        const { Icon, label, note } = def
        const isDragging = dragIndex === i
        const isOver = overIndex === i && dragIndex !== null && dragIndex !== i
        return (
          <div key={id}
            draggable
            onDragStart={() => setDragIndex(i)}
            onDragOver={e => { e.preventDefault(); setOverIndex(i) }}
            onDragEnd={() => { setDragIndex(null); setOverIndex(null) }}
            onDrop={e => { e.preventDefault(); handleDrop(i) }}
            className="flex items-center gap-2 px-2.5 py-2 rounded-lg border cursor-grab active:cursor-grabbing select-none transition-colors"
            style={{
              background: isDragging ? 'var(--bg-raised)' : 'var(--bg-base)',
              borderColor: isOver ? 'var(--accent-400)' : 'var(--border-subtle)',
              opacity: isDragging ? 0.5 : 1,
            }}>
            <GripVertical size={14} className="flex-shrink-0 text-gray-500"/>
            <Icon size={14} className="flex-shrink-0 text-gray-400"/>
            <span className="text-sm text-gray-300">{label}</span>
            {note && <span className="text-xs text-gray-500 ml-1">{note}</span>}
          </div>
        )
      })}
    </div>
  )
}


// (Appearance / Detection / Notifications / Storage & Data / Account &
// Advanced) — purely a navigation/scanning aid layered on top of the
// existing per-card collapse + jump-to-section dropdown, not a new
// collapse mechanism of its own. Renders once per group, directly in the
// page flow, so a person scrolling (not just using the dropdown) can see
// at a glance which cluster they're in.
// A button that runs one test send and shows the result beside it.
function TestSendButton({ label, run }) {
  const [state, setState] = useState(null)   // null | 'sending' | {ok, text}
  const go = async () => {
    setState('sending')
    try {
      const r = await run()
      setState({ ok: true, text: r?.message || 'Sent' })
    } catch (e) {
      setState({ ok: false, text: e.message || 'Failed' })
    }
  }
  return (
    <div className="flex flex-col items-end gap-1">
      <button onClick={go} disabled={state === 'sending'} className="btn-secondary" style={{ fontSize: 13 }}>
        {state === 'sending' ? 'Sending…' : label}
      </button>
      {state && state !== 'sending' && (
        <p className="text-xs text-right max-w-[16rem]" style={{ color: state.ok ? 'var(--accent-400)' : 'var(--pastel-red)' }}>
          {state.ok ? '✓ ' : ''}{state.text}
        </p>
      )}
    </div>
  )
}

// Hour picker in the site's time zone. From noon on a digest covers that
// day so far; earlier, the day before (see scheduled_push.digest_day).
function DigestHourSelect({ value, onChange }) {
  const label = h => `${h % 12 === 0 ? 12 : h % 12}:00 ${h < 12 ? 'AM' : 'PM'}`
  return (
    <select className="input text-sm flex-shrink-0" style={{ width: 'auto' }} value={value} onChange={e => onChange(parseInt(e.target.value, 10))}>
      {Array.from({ length: 24 }, (_, h) => (
        <option key={h} value={h}>{label(h)} · {h >= 12 ? 'same day' : 'day before'}</option>
      ))}
    </select>
  )
}

// The app only: a text file about this copy of the app (lib/appDiagnostics.js),
// also offered under My Profile → Help & Feedback.
function AppDiagnosticsCard() {
  const [state, setState] = useState(null)
  const run = async () => {
    setState('Collecting…')
    try {
      const [{ buildReport }, { saveText }] = await Promise.all([import('../lib/appDiagnostics'), import('../lib/download')])
      await saveText(await buildReport(), `chirp-app-diagnostics-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')}.txt`)
      setState(null)
    } catch (e) { setState(e.message || 'Couldn\u2019t export.') }
  }
  return (
    <div className="rounded-2xl p-4 md:p-5 mb-4 flex items-center gap-3 flex-wrap"
         style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)' }}>
      <div className="flex-1 min-w-[200px]">
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>This {deviceName()} app</p>
        <p className="text-xs" style={{ color: state && state !== 'Collecting…' ? 'var(--pastel-red)' : 'var(--text-tertiary)' }}>
          {state || 'A text file about the app, this device, notifications and recent errors, to send with a problem report. No passwords or sign-in tokens.'}
        </p>
      </div>
      <button onClick={run} disabled={state === 'Collecting…'} className="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5">
        <Download size={13}/> Export app diagnostics
      </button>
    </div>
  )
}

function GroupHeader({ id }) {
  // Zero-height start marker for a tab's content (the tab title is shown in
  // the page header instead).
  return <div id={id} aria-hidden="true" style={{ height: 0, scrollMarginTop: '56px' }}/>
}

// One collapsible card per experimental feature — each independently
// expandable/collapsible, matching the existing Diagnostics section's
// header+chevron pattern rather than the shared Section component (which
// collapses as a single whole, not per-feature).
function ExpCard({ id, title, subtitle, collapsed, setCollapsed, children }) {
  // Collapsed by default — only open once explicitly expanded
  // (collapsed[id] === false, set the first time someone opens it).
  const isOpen = collapsed[id] === false
  return (
    <div id={`settings-exp-${id}`} className="rounded-lg border border-surface-700 bg-surface-800 overflow-hidden" style={{ scrollMarginTop: '56px' }}>
      <button className="flex items-start gap-3 p-4 w-full text-left"
              onClick={() => setCollapsed(c => ({ ...c, [id]: isOpen }))}>
        <h2 className="sr-only">{title}</h2>
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-200">{title}</p>
          {isOpen && subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
        </div>
        <ChevronDown size={16} style={{
          color: 'var(--text-tertiary)',
          transform: isOpen ? 'none' : 'rotate(-90deg)',
          transition: 'transform .2s',
          flexShrink: 0,
          marginTop: 2,
        }}/>
      </button>
      {isOpen && <div className="px-4 pb-4 space-y-3">{children}</div>}
    </div>
  )
}

const DEFAULT_CUSTOM_COLORS = {
  background: '#10141a',
  card: '#171c24',
  text: '#e6ebf0',
  accent: '#3b9dd6',
  border: '#2a313d',
}

function CustomThemeBuilder({ customThemes, activeTheme, onApply, onChange }) {
  const [creating, setCreating] = useState(false)
  const [editingId, setEditingId] = useState(null) // null = creating new, else editing existing
  const [name, setName] = useState('')
  const [colors, setColors] = useState(DEFAULT_CUSTOM_COLORS)
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)

  const startCreate = () => {
    setEditingId(null)
    setName('')
    setColors(DEFAULT_CUSTOM_COLORS)
    setCreating(true)
  }

  const startEdit = (theme) => {
    setEditingId(theme.id)
    setName(theme.name)
    setColors(theme.colors)
    setCreating(true)
  }

  const cancelEdit = () => setCreating(false)

  const handleSave = () => {
    const id = saveCustomTheme({ id: editingId, name: name.trim() || 'Custom Theme', colors })
    onChange()
    onApply(id)
    setCreating(false)
  }

  const handleDelete = (id) => {
    deleteCustomTheme(id)
    onChange()
    setConfirmDeleteId(null)
  }

  const setColor = (key) => (e) => setColors(c => ({ ...c, [key]: e.target.value }))

  const colorFields = [
    { key: 'background', label: 'Background' },
    { key: 'card', label: 'Card' },
    { key: 'text', label: 'Text' },
    { key: 'accent', label: 'Accent' },
    { key: 'border', label: 'Border' },
  ]

  return (
    <div className="mt-5 pt-5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
      <div className="flex items-center justify-between mb-2.5">
        <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
          Custom Themes
        </p>
        {!creating && (
          <button onClick={startCreate}
                  className="flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-lg transition-colors"
                  style={{ color: 'var(--accent-400)', background: 'var(--nav-active-bg)' }}>
            <Plus size={12}/> New
          </button>
        )}
      </div>

      {customThemes.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 mb-3">
          {customThemes.map(theme => (
            <div key={theme.id} className="relative group">
              <button onClick={() => onApply(theme.id)}
                className="w-full flex items-center gap-3 p-3 rounded-xl transition-all text-left"
                style={{
                  background: activeTheme === theme.id ? 'var(--nav-active-bg)' : 'var(--bg-raised)',
                  border: `1px solid ${activeTheme === theme.id ? 'var(--border-focus)' : 'var(--border-subtle)'}`,
                }}>
                <div className="relative flex-shrink-0" style={{ width: 30, height: 30 }}>
                  <div className="absolute inset-0 rounded-full overflow-hidden"
                       style={{ background: theme.colors.background, border: '1px solid rgba(255,255,255,.08)' }}>
                    <div className="absolute inset-0 rounded-full" style={{
                      background: `radial-gradient(circle at 68% 50%, ${theme.colors.accent} 0%, transparent 65%)`
                    }}/>
                  </div>
                  {activeTheme === theme.id && (
                    <div className="absolute -bottom-0.5 -right-0.5 rounded-full flex items-center justify-center"
                         style={{ width: 14, height: 14, background: 'var(--bg-card)', border: '1.5px solid var(--bg-card)' }}>
                      <CheckCircle size={14} style={{ color: theme.colors.accent }}/>
                    </div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{theme.name}</p>
                  <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-tertiary)' }}>Custom theme</p>
                </div>
              </button>
              {/* Edit/delete controls — shown on hover (desktop) or always
                  visible at small size (mobile has no hover state) */}
              <div className="absolute top-1.5 right-1.5 flex gap-1 opacity-70 group-hover:opacity-100">
                <button onClick={(e) => { e.stopPropagation(); startEdit(theme) }}
                        title="Edit colors"
                        className="p-1 rounded-md transition-colors"
                        style={{ background: 'var(--bg-card)', color: 'var(--text-tertiary)' }}>
                  <Palette size={11}/>
                </button>
                {confirmDeleteId === theme.id ? (
                  <button onClick={(e) => { e.stopPropagation(); handleDelete(theme.id) }}
                          title="Click again to confirm delete"
                          className="p-1 rounded-md transition-colors"
                          style={{ background: '#dc2626', color: '#fff' }}>
                    <Trash2 size={11}/>
                  </button>
                ) : (
                  <button onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(theme.id) }}
                          title="Delete this theme"
                          className="p-1 rounded-md transition-colors"
                          style={{ background: 'var(--bg-card)', color: 'var(--text-tertiary)' }}>
                    <Trash2 size={11}/>
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {!creating && customThemes.length === 0 && (
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          No custom themes yet. Pick your own colors and save as many as you like.
        </p>
      )}

      {creating && (
        <div className="p-4 rounded-xl" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <div className="flex items-center gap-3 mb-4">
            {/* Live preview swatch — same visual language as every other
                theme card, so what's about to be saved is recognizable
                immediately, not just a row of color codes. */}
            <div className="relative flex-shrink-0" style={{ width: 36, height: 36 }}>
              <div className="absolute inset-0 rounded-full overflow-hidden"
                   style={{ background: colors.background, border: '1px solid rgba(255,255,255,.08)' }}>
                <div className="absolute inset-0 rounded-full" style={{
                  background: `radial-gradient(circle at 68% 50%, ${colors.accent} 0%, transparent 65%)`
                }}/>
              </div>
            </div>
            <input value={name} onChange={e => setName(e.target.value)}
                   placeholder="Name this theme…"
                   className="input flex-1" style={{ fontSize: 14 }}/>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
            {colorFields.map(({ key, label }) => (
              <div key={key} className="flex flex-col items-center gap-1.5">
                <input type="color" value={colors[key]} onChange={setColor(key)}
                       title={label}
                       style={{ width: 40, height: 40, borderRadius: 8, border: '1px solid var(--border-subtle)', padding: 0, cursor: 'pointer', background: 'none' }}/>
                <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{label}</span>
              </div>
            ))}
          </div>

          <p className="text-xs mb-4" style={{ color: 'var(--text-tertiary)' }}>
Hover colors, secondary text, focus rings and shadows are made from these 5 colors.
</p>

          <div className="flex items-center gap-2">
            <button onClick={handleSave}
                    className="btn-primary flex items-center gap-1.5 px-4 py-2 text-sm">
              <Save size={14}/> {editingId ? 'Save Changes' : 'Save Theme'}
            </button>
            <button onClick={cancelEdit}
                    className="px-4 py-2 text-sm rounded-lg transition-colors"
                    style={{ color: 'var(--text-secondary)', background: 'var(--bg-card)' }}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-300 mb-1">{label}</label>
      {hint && <p className="text-xs text-gray-500 mb-2">{hint}</p>}
      {children}
    </div>
  )
}

function Slider({ label, hint, min, max, step, value, onChange, format }) {
  const safe = value ?? ((min + max) / 2)
  return (
    <Field label={label} hint={hint}>
      <div className="flex items-center gap-3">
        <input type="range" min={min} max={max} step={step}
               value={safe}
               onChange={e => onChange(parseFloat(e.target.value))}
               className="flex-1 accent-chirp-500"/>
        <span className="text-sm text-chirp-400 font-mono w-14 text-right">
          {format ? format(safe) : safe}
        </span>
      </div>
    </Field>
  )
}

// ── BackupRestorePanel ────────────────────────────────────────────────────────
function BackupRestorePanel({ form, setForm }) {
  const [restoring, setRestoring] = useState(false)
  const [restoreMsg, setRestoreMsg] = useState(null)
  const [restoreErr, setRestoreErr] = useState(null)
  const [downloading, setDownloading] = useState(false)
  const [downloadErr, setDownloadErr] = useState(null)
  const [autoBackups, setAutoBackups] = useState([])
  const [autoBackupsErr, setAutoBackupsErr] = useState(null)
  const [autoBusyFile, setAutoBusyFile] = useState(null) // filename currently being downloaded/restored, for per-row loading state
  const [runningNow, setRunningNow] = useState(false)
  const [runNowErr, setRunNowErr] = useState(null)
  const fileRef = useRef(null)

  useEffect(() => {
    api.backup.autoList().then(setAutoBackups).catch(e => setAutoBackupsErr(e.message || 'Failed to load backups'))
  }, [])

  const handleRunNow = async () => {
    setRunningNow(true)
    setRunNowErr(null)
    try {
      await api.backup.runNow()
      const list = await api.backup.autoList()
      setAutoBackups(list)
      setAutoBackupsErr(null)
      // Reflect the fresh last-run/last-error status immediately without
      // waiting for the page's own next settings refetch — the whole
      // point of this button is seeing the real result right now.
      setForm(f => ({
        ...f,
        auto_backup_last_run_at: new Date().toISOString(),
        auto_backup_last_success_at: new Date().toISOString(),
        auto_backup_last_error: null,
      }))
    } catch (err) {
      setRunNowErr(err.message || 'Backup failed')
      setForm(f => ({
        ...f,
        auto_backup_last_run_at: new Date().toISOString(),
        auto_backup_last_error: err.message || 'Backup failed',
      }))
    } finally {
      setRunningNow(false)
    }
  }

  const handleAutoDownload = async (filename) => {
    setAutoBusyFile(filename)
    try {
      await api.backup.autoDownload(filename)
    } catch (err) {
      setAutoBackupsErr(err.message || 'Download failed')
    } finally {
      setAutoBusyFile(null)
    }
  }

  const handleAutoRestore = async (filename) => {
    if (!window.confirm(`Replace the entire Chirp database with the automatic backup "${filename}"?\n\nA pre-restore backup will be kept on the server. This cannot be easily undone.`)) return
    setAutoBusyFile(filename)
    setRestoreMsg(null)
    setRestoreErr(null)
    try {
      const res = await api.backup.autoRestore(filename)
      setRestoreMsg(res.message || 'Restored successfully. Reload the page to see your data.')
    } catch (err) {
      setRestoreErr(err.message || 'Restore failed')
    } finally {
      setAutoBusyFile(null)
    }
  }

  const fmtBytes = (n) => n < 1024*1024 ? `${(n/1024).toFixed(0)} KB` : `${(n/(1024*1024)).toFixed(1)} MB`

  const handleRestore = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!window.confirm(
      `Replace the entire Chirp database with "${file.name}"?\n\nA pre-restore backup will be kept on the server. This cannot be easily undone.`
    )) {
      e.target.value = ''
      return
    }
    setRestoring(true)
    setRestoreMsg(null)
    setRestoreErr(null)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await api.backup.restore(fd)
      setRestoreMsg(`Restored successfully — ${res.tables?.length ?? '?'} tables loaded. Reload the page to see your data.`)
    } catch (err) {
      setRestoreErr(err.message || 'Restore failed')
    } finally {
      setRestoring(false)
      e.target.value = ''
    }
  }

  const handleBackupDownload = async () => {
    setDownloading(true)
    setDownloadErr(null)
    try {
      await api.backup.download()
    } catch (err) {
      setDownloadErr(err.message || 'Download failed')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
Download a copy of the Chirp database, or upload a backup to restore it. It holds recordings and detections, species profiles, settings and notes; audio files aren't included.
</p>

      {/* Backup download */}
      <div className="flex items-center justify-between p-4 rounded-xl"
           style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
        <div>
          <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Download Backup</p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
            Saves as chirp_v{'{'}version{'}'}_{'{'}date{'}'}.db
          </p>
          {downloadErr && (
            <p className="text-xs mt-1" style={{ color: 'var(--accent-danger, #f87171)' }}>{downloadErr}</p>
          )}
        </div>
        <button onClick={handleBackupDownload} disabled={downloading}
           className="btn-primary flex items-center gap-1.5 text-sm disabled:opacity-50">
          <Save size={13} className={downloading ? 'animate-pulse' : ''}/>
          {downloading ? 'Downloading…' : 'Download'}
        </button>
      </div>

      {/* Restore upload */}
      <div className="flex items-center justify-between p-4 rounded-xl"
           style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
        <div className="flex-1 min-w-0 mr-4">
          <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Restore Backup</p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
            Upload a .db file to replace the current database
          </p>
        </div>
        <input ref={fileRef} type="file" accept=".db,application/octet-stream"
               className="hidden" onChange={handleRestore}/>
        <button onClick={() => fileRef.current?.click()} disabled={restoring}
                className="btn-secondary flex items-center gap-1.5 text-sm flex-shrink-0"
                style={{ borderColor: 'rgba(248,113,113,.4)', color: 'var(--pastel-red)' }}>
          {restoring
            ? <><RefreshCw size={12} className="animate-spin"/> Restoring…</>
            : <><HardDrive size={12}/> Restore…</>}
        </button>
      </div>

      {/* Automatic backups */}
      <div className="p-4 rounded-xl" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Automatic Backups</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
On by default: backs up the database once a day and keeps the most recent copies. Audio and media aren't included; back those up with the server's disk backup.
</p>
          </div>
          <input type="checkbox"
            checked={form?.auto_backup_enabled ?? true}
            onChange={e => setForm(f => ({ ...f, auto_backup_enabled: e.target.checked }))}
            className="w-4 h-4 accent-chirp-500 flex-shrink-0"/>
        </div>
        {(form?.auto_backup_enabled ?? true) && (
          <div className="flex items-center gap-4 mt-3 pt-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
              Run at
              <input type="number" min={0} max={23}
                     value={form?.auto_backup_hour ?? 3}
                     onChange={e => setForm(f => ({ ...f, auto_backup_hour: Math.min(23, Math.max(0, parseInt(e.target.value) || 0)) }))}
                     className="input text-xs py-1 text-center" style={{ width: 48 }}/>
              :00 (your timezone)
            </label>
            <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
              Keep last
              <input type="number" min={1} max={90}
                     value={form?.auto_backup_retention_count ?? 14}
                     onChange={e => setForm(f => ({ ...f, auto_backup_retention_count: parseInt(e.target.value) || 14 }))}
                     className="input text-xs py-1 text-center" style={{ width: 56 }}/>
              backups
            </label>
          </div>
        )}

        {/* Real last-run status — previously the ONLY way to know whether
            this was actually working was to tail server logs, since a
            failure was just a logger.warning call. Shown regardless of
            the enabled checkbox above so a person can tell "it's been
            failing" apart from "I turned it off." */}
        <div className="flex items-center justify-between gap-3 mt-3 pt-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            {form?.auto_backup_last_run_at
              ? <>
                  Last attempt: {new Date(form.auto_backup_last_run_at).toLocaleString()}
                  {form?.auto_backup_last_error
                    ? <span style={{ color: 'var(--accent-danger, #f87171)' }}> — failed: {form.auto_backup_last_error}</span>
                    : <span style={{ color: 'var(--pastel-green)' }}> — succeeded</span>}
                </>
              : 'Never run yet'}
          </div>
          <button onClick={handleRunNow} disabled={runningNow}
                  className="btn-secondary flex items-center gap-1.5 text-xs flex-shrink-0 disabled:opacity-50">
            <RefreshCw size={12} className={runningNow ? 'animate-spin' : ''}/>
            {runningNow ? 'Running…' : 'Run Now'}
          </button>
        </div>
        {runNowErr && (
          <p className="text-xs mt-2" style={{ color: 'var(--accent-danger, #f87171)' }}>{runNowErr}</p>
        )}

        {autoBackupsErr && (
          <p className="text-xs mt-3" style={{ color: 'var(--accent-danger, #f87171)' }}>{autoBackupsErr}</p>
        )}

        {autoBackups.length > 0 && (
          <div className="mt-3 pt-3 space-y-1.5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            {autoBackups.map(b => (
              <div key={b.filename} className="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded-lg"
                   style={{ background: 'var(--bg-card)' }}>
                <div className="min-w-0">
                  <p className="truncate" style={{ color: 'var(--text-primary)' }}>{new Date(b.created_at).toLocaleString()}</p>
                  <p style={{ color: 'var(--text-tertiary)' }}>{fmtBytes(b.size_bytes)}</p>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button onClick={() => handleAutoDownload(b.filename)} disabled={autoBusyFile === b.filename}
                          className="tactile-press p-1.5 rounded-lg" style={{ color: 'var(--text-tertiary)' }} title="Download">
                    <Save size={13}/>
                  </button>
                  <button onClick={() => handleAutoRestore(b.filename)} disabled={autoBusyFile === b.filename}
                          className="tactile-press p-1.5 rounded-lg" style={{ color: 'var(--pastel-red)' }} title="Restore from this backup">
                    <HardDrive size={13}/>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        {autoBackups.length === 0 && !autoBackupsErr && (
          <p className="text-xs mt-3" style={{ color: 'var(--text-tertiary)' }}>No automatic backups yet — the first one runs at the configured hour above.</p>
        )}
      </div>

      {restoreMsg && (
        <div className="flex items-start gap-2 p-3 rounded-xl text-xs"
             style={{ background: 'rgba(34,197,94,.08)', border: '1px solid rgba(34,197,94,.2)', color: 'var(--pastel-green)' }}>
          <Check size={13} style={{ flexShrink: 0, marginTop: 1 }}/>
          {restoreMsg}
        </div>
      )}
      {restoreErr && (
        <div className="flex items-start gap-2 p-3 rounded-xl text-xs"
             style={{ background: 'rgba(248,113,113,.08)', border: '1px solid rgba(248,113,113,.2)', color: 'var(--pastel-red)' }}>
          <Lock size={13} style={{ flexShrink: 0, marginTop: 1 }}/>
          {restoreErr}
        </div>
      )}

      <div className="flex items-start gap-2 p-3 rounded-xl"
           style={{ background: 'rgba(251,146,60,.06)', border: '1px solid rgba(251,146,60,.18)' }}>
        <p className="text-xs" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          <strong style={{ color: '#fdba74' }}>⚠️ Restore replaces all current data.</strong> The server saves a pre-restore
          snapshot as <code style={{ color: 'var(--text-primary)' }}>chirp.db.pre-restore.bak</code> alongside the database
          in case you need to roll back manually.
        </p>
      </div>
    </div>
  )
}

// ── ApiKeysPanel — admin can reveal full key values ───────────────────────────
const AI_FEATURES = [
  { key: 'photo_id', label: 'Photo ID Confirmation', desc: 'Sanity-checks a species when you upload a photo to a Bird Profile.' },
  { key: 'call_reanalysis', label: 'AI Second Opinion', desc: 'A second opinion on a recording\u2019s spectrogram.' },
  { key: 'daily_summary', label: 'Daily Journal Summary', desc: 'An AI-written recap of the day on the Dashboard, in a birder\u2019s-journal tone.' },
  { key: 'weekly_summary', label: 'Weekly Journal Summary', desc: 'A weekly recap with arrivals and departures and more room for detail.' },
  { key: 'profile_summary', label: 'Bird Profile Summaries', desc: 'A short note at the top of each bird\u2019s profile about its visits to your yard.' },
]

const PROVIDER_META = {
  anthropic: { label: 'Anthropic', color: '#d97757' },
  openai: { label: 'OpenAI', color: '#74aa9c' },
  gemini: { label: 'Gemini', color: '#4285f4' },
  ollama: { label: 'Ollama', color: '#a78bfa' },
}
const FEATURE_LABELS = {
  photo_id: 'Photo ID', call_reanalysis: 'AI Second Opinion',
  daily_summary: 'Daily Journal', weekly_summary: 'Weekly Journal', profile_summary: 'Profile Summaries',
}

function AiSettingsPanel({ form, setForm, settings }) {
  const [revealed, setRevealed] = useState(null)
  const [revealing, setRevealing] = useState(false)
  const [revealErr, setRevealErr] = useState(null)
  const [testState, setTestState] = useState({})

  const handleReveal = async () => {
    if (revealed) { setRevealed(null); return }
    setRevealing(true)
    setRevealErr(null)
    try {
      const data = await api.revealKeys()
      setRevealed(data)
    } catch (e) {
      setRevealErr(e.message || 'Could not reveal keys')
    } finally {
      setRevealing(false)
    }
  }

  const testKey = async (provider, formKey) => {
    setTestState(t => ({ ...t, [provider]: 'loading' }))
    try {
      const currentValue = form[formKey]
      const body = currentValue ? { provider, api_key: currentValue } : { provider }
      await api.settings.testAiKey(body)
      setTestState(t => ({ ...t, [provider]: 'ok' }))
    } catch (e) {
      setTestState(t => ({ ...t, [provider]: e?.message || 'Failed' }))
    }
    setTimeout(() => setTestState(t => ({ ...t, [provider]: null })), 5000)
  }

  const KeyField = ({ label, hint, formKey, revealedKey, placeholder, testProvider }) => (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
        {label}
      </label>
      <div className="relative flex items-center gap-2">
        <div className="relative flex-1">
          <input
            className="input font-mono w-full pr-10"
            type={revealed ? 'text' : 'password'}
            placeholder={placeholder || 'Enter key…'}
            value={revealed ? (revealed[revealedKey] || form[formKey]) : form[formKey]}
            onChange={e => {
              if (revealed) return
              setForm(f => ({ ...f, [formKey]: e.target.value }))
            }}
            readOnly={!!revealed}
          />
          {revealed && revealed[revealedKey] && (
            <span className="absolute right-3 top-1/2 -translate-y-1/2">
              <CheckCircle size={13} style={{ color: 'var(--accent-400)' }}/>
            </span>
          )}
        </div>
        {testProvider && (
          <button onClick={() => testKey(testProvider, formKey)} disabled={testState[testProvider] === 'loading'}
                  className="text-xs px-2.5 py-2 rounded-lg flex-shrink-0 flex items-center gap-1.5"
                  style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
            {testState[testProvider] === 'loading' ? <RefreshCw size={12} className="animate-spin"/> : <Plug size={12}/>}
            Test
          </button>
        )}
      </div>
      {testProvider && testState[testProvider] === 'ok' && (
        <p className="text-xs flex items-center gap-1" style={{ color: '#4ade80' }}><CheckCircle size={11}/> Key works</p>
      )}
      {testProvider && testState[testProvider] && testState[testProvider] !== 'loading' && testState[testProvider] !== 'ok' && (
        <p className="text-xs" style={{ color: '#f87171' }}>{testState[testProvider]}</p>
      )}
      {hint && <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{hint}</p>}
    </div>
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
Keys and settings for Chirp's AI features. eBird, iNaturalist and station keys are under API Keys.
</p>
        <button onClick={handleReveal} disabled={revealing}
                className="text-xs px-2.5 py-1.5 rounded-lg flex items-center gap-1.5 flex-shrink-0 ml-3"
                style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
          {revealed ? <EyeOff size={12}/> : <Eye size={12}/>}
          {revealing ? 'Loading…' : revealed ? 'Hide' : 'Reveal'}
        </button>
      </div>
      {revealErr && <p className="text-xs" style={{ color: '#f87171' }}>{revealErr}</p>}

      <KeyField label="Anthropic API Key" formKey="anthropic_api_key" revealedKey="anthropic_api_key" testProvider="anthropic"
                placeholder={settings?.anthropic_api_key || 'Enter Anthropic API key…'}
                hint={<>Optional — powers AI species confirmation on user-uploaded bird photos
                  (Bird Profile pages). Without this, photo upload still works, there's just no
                  confirmation check. Get a key at{' '}
                  <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer"
                     style={{color:'var(--accent-500)'}}>console.anthropic.com</a></>}/>

      <KeyField label="OpenAI API Key" formKey="openai_api_key" revealedKey="openai_api_key" testProvider="openai"
                placeholder={settings?.openai_api_key || 'Enter OpenAI API key…'}
                hint={<>Optional — an alternative provider for the AI features below. Assign
                  each feature to whichever key you'd rather use. Get a key at{' '}
                  <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer"
                     style={{color:'var(--accent-500)'}}>platform.openai.com</a></>}/>

      <KeyField label="Gemini API Key" formKey="gemini_api_key" revealedKey="gemini_api_key" testProvider="gemini"
                placeholder={settings?.gemini_api_key || 'Enter Gemini API key…'}
                hint={<>Optional — a third provider option for the AI features below. Get a key at{' '}
                  <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer"
                     style={{color:'var(--accent-500)'}}>aistudio.google.com</a></>}/>

      <OllamaSection form={form} setForm={setForm} settings={settings}/>

      <AiFeatureProviderSection form={form} setForm={setForm} settings={settings}/>

      <AiUsageSection/>
    </div>
  )
}

function AiUsageSection() {
  const [usage, setUsage] = useState(null)
  const [range, setRange] = useState('last_30d') // 'last_30d' | 'all_time'

  useEffect(() => {
    api.settings.getAiUsage().then(setUsage).catch(() => {})
  }, [])

  if (!usage) return null

  const totalCalls = Object.values(usage[range]).reduce((s, p) => s + p.calls, 0)
  const hasAnyUsage = Object.values(usage.all_time).some(p => p.calls > 0)
  if (!hasAnyUsage) return null // nothing logged yet anywhere — no point showing an all-zero table

  return (
    <div className="p-3 rounded-lg" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>API Usage</p>
        <div className="flex rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-subtle)' }}>
          {['last_30d', 'all_time'].map(r => (
            <button key={r} onClick={() => setRange(r)}
                    className="text-xs px-2.5 py-1 transition-colors"
                    style={{ background: range === r ? 'var(--nav-active-bg)' : 'transparent', color: range === r ? 'var(--accent-400)' : 'var(--text-tertiary)' }}>
              {r === 'last_30d' ? 'Last 30 days' : 'All time'}
            </button>
          ))}
        </div>
      </div>

      {totalCalls === 0 ? (
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>No calls in this window.</p>
      ) : (
        <div className="space-y-2">
          {Object.entries(usage[range]).filter(([, v]) => v.calls > 0).map(([provider, v]) => (
            <div key={provider} className="flex items-center gap-3">
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: PROVIDER_META[provider]?.color }}/>
              <span className="text-xs flex-1" style={{ color: 'var(--text-secondary)' }}>{PROVIDER_META[provider]?.label || provider}</span>
              <span className="text-xs font-mono" style={{ color: 'var(--text-primary)' }}>{v.calls} call{v.calls !== 1 ? 's' : ''}</span>
              <span className="text-xs font-mono" style={{ color: 'var(--text-tertiary)' }}>{(v.input_tokens + v.output_tokens).toLocaleString()} tokens</span>
            </div>
          ))}
        </div>
      )}

      {usage.by_feature && Object.keys(usage.by_feature).length > 0 && (
        <div className="mt-3 pt-3 flex flex-wrap gap-x-4 gap-y-1" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          {Object.entries(usage.by_feature).map(([feat, count]) => (
            <span key={feat} className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              {FEATURE_LABELS[feat] || feat}: <strong style={{ color: 'var(--text-secondary)' }}>{count}</strong>
            </span>
          ))}
        </div>
      )}

      <p className="text-xs mt-3" style={{ color: 'var(--text-tertiary)' }}>
Token counts come from each provider. Prices vary by model and change often, so check the provider's billing page for cost.
</p>
    </div>
  )
}

function formatBytes(bytes) {
  if (bytes == null) return ''
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`
  return `${(bytes / 1e3).toFixed(0)} KB`
}

function OllamaSection({ form, setForm, settings }) {
  const savedKey = settings?.ollama_api_key && !form.ollama_api_key_clear
  const [testState, setTestState] = useState(null) // null | 'loading' | 'ok' | error-string
  const [models, setModels] = useState(null) // null = not loaded yet; [] = loaded, none pulled
  const [modelsError, setModelsError] = useState(null)
  const [pullModelName, setPullModelName] = useState('')
  const [pullState, setPullState] = useState(null) // null | 'loading' | 'ok' | error-string

  const test = async () => {
    setTestState('loading')
    try {
      await api.settings.testAiKey({ provider: 'ollama', base_url: form.ollama_base_url, model: form.ollama_model, api_key: form.ollama_api_key || undefined })
      setTestState('ok')
    } catch (e) {
      setTestState(e?.message || 'Failed')
    }
    setTimeout(() => setTestState(null), 6000)
  }

  const refreshModels = useCallback(async () => {
    if (!form.ollama_base_url) { setModels(null); setModelsError(null); return }
    try {
      const resp = await api.settings.ollamaModels(form.ollama_base_url, form.ollama_api_key)
      setModels(resp.models || [])
      setModelsError(null)
    } catch (e) {
      setModelsError(e?.message || 'Could not reach Ollama server')
      setModels(null)
    }
  }, [form.ollama_base_url, form.ollama_api_key])

  // Only re-fetches when the base_url changes (typing pauses,
  // not every keystroke) — a debounce-free effect here would hammer a
  // server that might be slow/on a LAN with every character typed.
  useEffect(() => {
    const t = setTimeout(refreshModels, 500)
    return () => clearTimeout(t)
  }, [refreshModels])

  const pull = async () => {
    const name = pullModelName.trim()
    if (!name) return
    setPullState('loading')
    try {
      await api.settings.ollamaPull(name, form.ollama_base_url, form.ollama_api_key)
      setPullState('ok')
      setPullModelName('')
      refreshModels()
    } catch (e) {
      setPullState(e?.message || 'Pull failed')
    }
    setTimeout(() => setPullState(null), 8000)
  }

  return (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
        Ollama (self-hosted)
      </label>
      <div className="grid grid-cols-2 gap-2">
        <input className="input text-sm" placeholder="http://localhost:11434 or a LAN address"
               value={form.ollama_base_url ?? ''}
               onChange={e => setForm(f => ({ ...f, ollama_base_url: e.target.value }))}/>
        <div className="flex items-center gap-2">
          <input className="input text-sm flex-1" placeholder="Model name, e.g. llama3.2"
                 value={form.ollama_model ?? ''}
                 onChange={e => setForm(f => ({ ...f, ollama_model: e.target.value }))}/>
          <button onClick={test} disabled={testState === 'loading'}
                  className="text-xs px-2.5 py-2 rounded-lg flex-shrink-0 flex items-center gap-1.5"
                  style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
            {testState === 'loading' ? <RefreshCw size={12} className="animate-spin"/> : <Plug size={12}/>}
            Test
          </button>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <input className="input text-sm flex-1" type="password" autoComplete="off"
               placeholder={savedKey ? `API key saved (${settings.ollama_api_key})` : 'API key (optional, only if your server asks for one)'}
               value={form.ollama_api_key ?? ''}
               onChange={e => setForm(f => ({ ...f, ollama_api_key: e.target.value, ollama_api_key_clear: false }))}/>
        {savedKey && !form.ollama_api_key && (
          <button onClick={() => setForm(f => ({ ...f, ollama_api_key: '', ollama_api_key_clear: true }))}
                  className="text-xs px-2.5 py-2 rounded-lg flex-shrink-0"
                  style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
            Remove key
          </button>
        )}
      </div>
      {form.ollama_api_key_clear && (
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>The saved key will be removed when you save.</p>
      )}
      {testState === 'ok' && (
        <p className="text-xs flex items-center gap-1" style={{ color: '#4ade80' }}><CheckCircle size={11}/> Server reachable, model available</p>
      )}
      {testState && testState !== 'loading' && testState !== 'ok' && (
        <p className="text-xs" style={{ color: '#f87171' }}>{testState}</p>
      )}

      {/* Model management — download a model onto the Ollama server
          directly, instead of needing to SSH in and run `ollama pull`
          by hand. Only shown once a base_url is entered; a pull attempt
          with nothing configured has nowhere to send the request. */}
      {form.ollama_base_url && (
        <div className="rounded-lg p-3 mt-2 space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Models on this server</p>
          {modelsError ? (
            <p className="text-xs" style={{ color: '#f87171' }}>{modelsError}</p>
          ) : models === null ? (
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Checking…</p>
          ) : models.length === 0 ? (
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>No models pulled yet.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {models.map(m => (
                <span key={m.name} className="text-xs px-2 py-1 rounded-md flex items-center gap-1"
                      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
                  {m.name}
                  {m.size_bytes != null && <span style={{ color: 'var(--text-tertiary)' }}>· {formatBytes(m.size_bytes)}</span>}
                </span>
              ))}
            </div>
          )}
          <div className="flex items-center gap-2 pt-1">
            <input className="input text-sm flex-1" placeholder="Model to download, e.g. llava"
                   value={pullModelName}
                   onChange={e => setPullModelName(e.target.value)}
                   onKeyDown={e => { if (e.key === 'Enter') pull() }}/>
            <button onClick={pull} disabled={pullState === 'loading' || !pullModelName.trim()}
                    className="text-xs px-2.5 py-2 rounded-lg flex-shrink-0 flex items-center gap-1.5"
                    style={{ background: 'var(--bg-panel)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
              {pullState === 'loading' ? <RefreshCw size={12} className="animate-spin"/> : <Download size={12}/>}
              {pullState === 'loading' ? 'Pulling\u2026' : 'Download'}
            </button>
          </div>
          {pullState === 'loading' && (
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>This can take several minutes for a large model — the page will update once it's done.</p>
          )}
          {pullState === 'ok' && (
            <p className="text-xs flex items-center gap-1" style={{ color: '#4ade80' }}><CheckCircle size={11}/> Downloaded successfully</p>
          )}
          {pullState && pullState !== 'loading' && pullState !== 'ok' && (
            <p className="text-xs" style={{ color: '#f87171' }}>{pullState}</p>
          )}
        </div>
      )}

      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
Optional: run models on an Ollama server you host; nothing leaves your network. Ollama has no sign-in of its own, so the API key is only for a server behind a proxy that checks one (sent as a Bearer token). Photo ID and AI Second Opinion need a vision model such as llava or llama3.2-vision.
</p>
    </div>
  )
}

function AiFeatureProviderSection({ form, setForm, settings }) {
  const providers = form.ai_feature_providers || {}
  const hasAnthropic = !!(settings?.anthropic_api_key || form.anthropic_api_key)
  const hasOpenai = !!(settings?.openai_api_key || form.openai_api_key)
  const hasGemini = !!(settings?.gemini_api_key || form.gemini_api_key)
  const hasOllama = !!((settings?.ollama_base_url || form.ollama_base_url) && (settings?.ollama_model || form.ollama_model))
  const [refreshState, setRefreshState] = useState(null) // null | 'loading' | 'ok' | 'error'

  const setProvider = (featureKey, value) => {
    setForm(f => ({
      ...f,
      ai_feature_providers: { ...(f.ai_feature_providers || {}), [featureKey]: value || null },
    }))
  }

  const forceRefreshDailyJournal = async () => {
    setRefreshState('loading')
    try {
      await api.recordings.regenerateDailyJournal()
      setRefreshState('ok')
    } catch (e) {
      setRefreshState('error')
    }
    setTimeout(() => setRefreshState(null), 4000)
  }

  return (
    <div className="space-y-3">
      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
Pick a provider for each AI feature, or turn it off. A feature that's off is hidden everywhere in the app.
</p>
      {AI_FEATURES.map(feat => {
        const current = providers[feat.key] || ''
        return (
          <div key={feat.key} className="p-3 rounded-lg" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{feat.label}</p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{feat.desc}</p>
              </div>
              <select value={current} onChange={e => setProvider(feat.key, e.target.value)}
                      className="input text-xs py-1.5 flex-shrink-0" style={{ width: 140 }}>
                <option value="">Disabled</option>
                <option value="anthropic" disabled={!hasAnthropic}>Anthropic{!hasAnthropic ? ' (no key)' : ''}</option>
                <option value="openai" disabled={!hasOpenai}>OpenAI{!hasOpenai ? ' (no key)' : ''}</option>
                <option value="gemini" disabled={!hasGemini}>Gemini{!hasGemini ? ' (no key)' : ''}</option>
                <option value="ollama" disabled={!hasOllama}>Ollama{!hasOllama ? ' (not configured)' : ''}</option>
              </select>
            </div>

            {/* Force-refresh only makes sense for daily_summary — it's the
                one thing here that's a single, global, cached value. The
                other two are per-item (one bird, one recording), so a
                "refresh all" button doesn't map to anything for
                them — pointing at where to do it instead. */}
            {feat.key === 'daily_summary' && current && (
              <div className="flex items-center gap-2 mt-2 pt-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <button onClick={forceRefreshDailyJournal} disabled={refreshState === 'loading'}
                        className="text-xs px-2.5 py-1 rounded-lg flex items-center gap-1.5"
                        style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
                  <RefreshCw size={11} className={refreshState === 'loading' ? 'animate-spin' : ''}/>
                  Regenerate now
                </button>
                {refreshState === 'ok' && <span className="text-xs" style={{ color: '#4ade80' }}>Regenerated</span>}
                {refreshState === 'error' && <span className="text-xs" style={{ color: '#f87171' }}>Failed — check the Dashboard card for details</span>}
              </div>
            )}
            {feat.key === 'profile_summary' && current && (
              <p className="text-xs mt-2 pt-2" style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-tertiary)' }}>
Set per species: open a bird's profile and use the regenerate button next to its summary.
</p>
            )}
            {feat.key === 'call_reanalysis' && current && (
              <p className="text-xs mt-2 pt-2" style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-tertiary)' }}>
Run per recording: open a recording and tap AI Second Opinion.
</p>
            )}
          </div>
        )
      })}

      {providers.daily_summary && (
        <div className="p-3 rounded-lg" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Daily Journal — generation times</p>
          <p className="text-xs mt-0.5 mb-3" style={{ color: 'var(--text-tertiary)' }}>
Times are in your time zone. The journal is rewritten at each time listed; add two for a morning and an evening entry. The Dashboard card also has a regenerate button.
</p>
          <div className="space-y-2">
            {(form.daily_summary_schedule_times?.length ? form.daily_summary_schedule_times : [form.daily_summary_schedule_time || '07:00']).map((t, i) => (
              <div key={i} className="flex items-center gap-2">
                <input type="time" value={t}
                       onChange={e => setForm(f => {
                         const current = f.daily_summary_schedule_times?.length ? f.daily_summary_schedule_times : [f.daily_summary_schedule_time || '07:00']
                         const next = [...current]
                         next[i] = e.target.value
                         return { ...f, daily_summary_schedule_times: next }
                       })}
                       className="input text-xs py-1.5" style={{ width: 110 }}/>
                {(form.daily_summary_schedule_times?.length || 1) > 1 && (
                  <button onClick={() => setForm(f => {
                    const current = f.daily_summary_schedule_times?.length ? f.daily_summary_schedule_times : [f.daily_summary_schedule_time || '07:00']
                    return { ...f, daily_summary_schedule_times: current.filter((_, idx) => idx !== i) }
                  })} className="p-1.5 rounded-lg" style={{ color: 'var(--text-tertiary)' }} aria-label="Remove time">
                    <X size={13}/>
                  </button>
                )}
              </div>
            ))}
            <button onClick={() => setForm(f => {
              const current = f.daily_summary_schedule_times?.length ? f.daily_summary_schedule_times : [f.daily_summary_schedule_time || '07:00']
              return { ...f, daily_summary_schedule_times: [...current, '17:00'] }
            })} className="text-xs px-2.5 py-1 rounded-lg flex items-center gap-1.5"
                    style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
              <Plus size={11}/> Add another time
            </button>
          </div>
        </div>
      )}

      {providers.weekly_summary && (
        <div className="p-3 rounded-lg" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Weekly Journal — generation time</p>
          <p className="text-xs mt-0.5 mb-3" style={{ color: 'var(--text-tertiary)' }}>
Covers the last 7 days, in your time zone. The Dashboard card also has a regenerate button.
</p>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
              Every
              <select value={form.weekly_summary_schedule_day ?? 6}
                      onChange={e => setForm(f => ({ ...f, weekly_summary_schedule_day: parseInt(e.target.value) }))}
                      className="input text-xs py-1.5">
                {['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map((day, idx) => (
                  <option key={idx} value={idx}>{day}</option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
              at
              <input type="number" min={0} max={23}
                     value={form.weekly_summary_schedule_hour ?? 7}
                     onChange={e => setForm(f => ({ ...f, weekly_summary_schedule_hour: Math.min(23, Math.max(0, parseInt(e.target.value) || 0)) }))}
                     className="input text-xs py-1 text-center" style={{ width: 48 }}/>
              :00
            </label>
          </div>
        </div>
      )}

      {providers.profile_summary && (
        <div className="p-3 rounded-lg" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Bird Profile Summaries — auto-refresh</p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
Off: a species summary is written once, the first time its profile is opened, and never updated. On: once a day, summaries older than the interval below are rewritten. Failed ones are skipped; use Regenerate on the profile to retry.
</p>
            </div>
            <input type="checkbox"
              checked={form.profile_summary_auto_refresh ?? false}
              onChange={e => setForm(f => ({ ...f, profile_summary_auto_refresh: e.target.checked }))}
              className="w-4 h-4 accent-chirp-500 flex-shrink-0"/>
          </div>
          {form.profile_summary_auto_refresh && (
            <div className="flex items-center gap-4 mt-3 pt-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                Refresh if older than
                <input type="number" min={1} max={90}
                       value={form.profile_summary_refresh_days ?? 7}
                       onChange={e => setForm(f => ({ ...f, profile_summary_refresh_days: parseInt(e.target.value) || 7 }))}
                       className="input text-xs py-1 text-center" style={{ width: 56 }}/>
                days
              </label>
              <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                Check at
                <input type="number" min={0} max={23}
                       value={form.profile_summary_refresh_hour ?? 3}
                       onChange={e => setForm(f => ({ ...f, profile_summary_refresh_hour: Math.min(23, Math.max(0, parseInt(e.target.value) || 0)) }))}
                       className="input text-xs py-1 text-center" style={{ width: 48 }}/>
                :00 (your timezone)
              </label>
            </div>
          )}
        </div>
      )}

      {(providers.daily_summary || providers.weekly_summary) && (
        <div className="p-3.5 rounded-lg" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Web search grounding</p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
Off by default. On: the Daily and Weekly Journal can look up Wikipedia and recent news about the period's most notable species. The search runs from this server, so it works with any AI provider, and it's only used when relevant.
</p>
            </div>
            <input type="checkbox"
              checked={form.ai_web_search_enabled ?? false}
              onChange={e => setForm(f => ({ ...f, ai_web_search_enabled: e.target.checked }))}
              className="w-4 h-4 accent-chirp-500 flex-shrink-0"/>
          </div>
        </div>
      )}

      {/* AI personality sliders — applies to Daily Journal and Bird
          Profile Summaries (the two creative-writing features).
          Deliberately NOT applied to Call Re-analysis: that's a
          technical accuracy judgment (is this really a bird call?),
          and dialing in "irreverence" has no business anywhere near it. */}
      {(providers.daily_summary || providers.weekly_summary || providers.profile_summary) && (
        <div className="p-4 rounded-lg" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>AI Personality</p>
          <p className="text-xs mt-0.5 mb-4" style={{ color: 'var(--text-tertiary)' }}>
Sets the tone of the Daily and Weekly Journal and Bird Profile summaries. The defaults keep the usual tone. AI Second Opinion isn't affected.
</p>
          <PersonalitySlider
            label="Friendliness" formKey="ai_personality_friendliness" form={form} setForm={setForm}
            defaultValue={60} lowLabel="Neutral" highLabel="Very personal"
            hint="How warm and personal the writing feels, vs. neutral and matter-of-fact."
          />
          <PersonalitySlider
            label="Informational" formKey="ai_personality_informational" form={form} setForm={setForm}
            defaultValue={50} lowLabel="Atmospheric" highLabel="Fact-dense"
            hint="Mood and narrative scene-setting vs. concrete facts and data points."
          />
          <PersonalitySlider
            label="Irreverence" formKey="ai_personality_irreverence" form={form} setForm={setForm}
            defaultValue={35} lowLabel="Sincere" highLabel="Playful"
            hint="How much wit and tongue-in-cheek humor comes through, vs. staying fairly straight."
          />
          <PersonalitySlider
            label="Depth" formKey="ai_personality_depth" form={form} setForm={setForm}
            defaultValue={50} lowLabel="Brief" highLabel="In-depth"
            hint="How long and detailed an entry is, not its tone. Higher explains trends instead of just naming them."
          />
          <PersonalitySlider
            label="Curiosity" formKey="ai_personality_curiosity" form={form} setForm={setForm}
            defaultValue={50} lowLabel="Just the facts" highLabel="Explores why"
            hint="Whether entries only report what happened or also suggest why, framed as a possibility, not a fact."
          />
        </div>
      )}
    </div>
  )
}

function PersonalitySlider({ label, formKey, form, setForm, defaultValue, lowLabel, highLabel, hint }) {
  const value = form[formKey] ?? defaultValue
  return (
    <div className="mb-4 last:mb-0">
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>{label}</label>
        <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          {value === defaultValue ? 'Default' : value < defaultValue ? `More ${lowLabel.toLowerCase()}` : `More ${highLabel.toLowerCase()}`}
        </span>
      </div>
      <input type="range" min={0} max={100} step={5} value={value}
             onChange={e => setForm(f => ({ ...f, [formKey]: parseInt(e.target.value) }))}
             className="w-full accent-chirp-500"/>
      <div className="flex items-center justify-between text-[10px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
        <span>{lowLabel}</span>
        <span>{highLabel}</span>
      </div>
      <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>{hint}</p>
    </div>
  )
}

// The site's public web address, used for links in emails and pushes.
function ServerUrlField({ form, setForm }) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <label className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
          Server Public URL
        </label>
        <input className="input w-full" type="url" placeholder="https://ourchirp.com"
               value={form.server_url}
               onChange={e => setForm(f => ({ ...f, server_url: e.target.value }))}/>
        {!form.server_url && (
          <p className="text-xs flex items-center gap-1.5 px-2 py-1.5 rounded"
             style={{ background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.2)', color: 'var(--pastel-amber)' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="flex-shrink-0"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            Required for working links in notification emails (e.g. https://ourchirp.com)
          </p>
        )}
        {form.server_url && (
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            Used to generate links in notification emails.
          </p>
        )}
      </div>

    </div>
  )
}

// only='ebird': the eBird keys; only='device': revealing saved device keys.
function ApiKeysPanel({ form, setForm, settings, only = 'ebird' }) {
  const [revealed, setRevealed] = useState(null) // { ebird_api_key, ebird_st_api_key, inat_api_token }
  const [revealing, setRevealing] = useState(false)
  const [revealErr, setRevealErr] = useState(null)

  const handleReveal = async () => {
    if (revealed) { setRevealed(null); return }
    setRevealing(true)
    setRevealErr(null)
    try {
      const data = await api.revealKeys()
      setRevealed(data)
    } catch (e) {
      setRevealErr(e.message || 'Could not reveal keys')
    } finally {
      setRevealing(false)
    }
  }

  const [testState, setTestState] = useState({}) // { [provider]: 'loading' | 'ok' | error-string }
  const testKey = async (provider, formKey) => {
    setTestState(t => ({ ...t, [provider]: 'loading' }))
    try {
      const currentValue = form[formKey]
      const body = currentValue ? { provider, api_key: currentValue } : { provider }
      await api.settings.testAiKey(body)
      setTestState(t => ({ ...t, [provider]: 'ok' }))
    } catch (e) {
      setTestState(t => ({ ...t, [provider]: e?.message || 'Failed' }))
    }
    setTimeout(() => setTestState(t => ({ ...t, [provider]: null })), 5000)
  }

  const KeyField = ({ label, hint, formKey, revealedKey, placeholder, testProvider }) => (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
        {label}
      </label>
      <div className="relative flex items-center gap-2">
        <div className="relative flex-1">
          <input
            className="input font-mono w-full pr-10"
            type={revealed ? 'text' : 'password'}
            placeholder={placeholder || 'Enter key…'}
            value={revealed ? (revealed[revealedKey] || form[formKey]) : form[formKey]}
            onChange={e => {
              if (revealed) return // read-only while revealed
              setForm(f => ({ ...f, [formKey]: e.target.value }))
            }}
            readOnly={!!revealed}
          />
          {revealed && revealed[revealedKey] && (
            <span className="absolute right-3 top-1/2 -translate-y-1/2">
              <CheckCircle size={13} style={{ color: 'var(--accent-400)' }}/>
            </span>
          )}
        </div>
        {testProvider && (
          <button onClick={() => testKey(testProvider, formKey)} disabled={testState[testProvider] === 'loading'}
                  className="text-xs px-2.5 py-2 rounded-lg flex-shrink-0 flex items-center gap-1.5"
                  style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
            {testState[testProvider] === 'loading' ? <RefreshCw size={12} className="animate-spin"/> : <Plug size={12}/>}
            Test
          </button>
        )}
      </div>
      {testProvider && testState[testProvider] === 'ok' && (
        <p className="text-xs flex items-center gap-1" style={{ color: '#4ade80' }}><CheckCircle size={11}/> Key works</p>
      )}
      {testProvider && testState[testProvider] && testState[testProvider] !== 'loading' && testState[testProvider] !== 'ok' && (
        <p className="text-xs" style={{ color: '#f87171' }}>{testState[testProvider]}</p>
      )}
      {hint && <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{hint}</p>}
    </div>
  )

  return (
    <div className="space-y-4">
      {only === 'ebird' && <>
      <KeyField label="eBird API Key" formKey="ebird_api_key" revealedKey="ebird_api_key"
                placeholder={settings?.ebird_api_key || 'Enter API key…'}
                hint="Required for Regional Birds page. Get yours free at ebird.org/api/keygen"/>

      <KeyField label="eBird S&T API Key" formKey="ebird_st_api_key" revealedKey="ebird_st_api_key"
                placeholder={settings?.ebird_st_api_key || 'Enter S&T access key…'}
                hint="Required for eBird Status & Trends range maps. Get yours at ebird.org/st/request"/>
      </>}

      {/* Haikubox, Bird Buddy, and iNaturalist integration settings moved to their own Third-Party Integrations section — see HaikuboxCard, BirdBuddyCard, InatCard below */}


      {/* Device API keys when revealed */}
      {only === 'device' && revealed?.device_api_keys?.length > 0 && (
        <div className="space-y-1.5">
          <label className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
            Device API Keys
          </label>
          {(revealed.device_api_keys || []).map(k => (
            <div key={k.id} className="flex items-center gap-2 p-2 rounded-lg"
                 style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
              <span className="text-xs font-medium flex-shrink-0" style={{ color: 'var(--text-secondary)', minWidth: 80 }}>
                {k.name}
              </span>
              <code className="text-xs font-mono flex-1 truncate" style={{ color: 'var(--accent-400)' }}>
                {k.key}
              </code>
              <button onClick={() => navigator.clipboard?.writeText(k.key)}
                      className="text-xs flex-shrink-0 px-2 py-0.5 rounded"
                      style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }}>
                Copy
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Reveal / hide button */}
      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={handleReveal}
          disabled={revealing}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-all"
          style={{
            background: revealed ? 'rgba(248,113,113,.1)' : 'var(--bg-raised)',
            color: revealed ? 'var(--pastel-red)' : 'var(--text-secondary)',
            border: `1px solid ${revealed ? 'rgba(248,113,113,.3)' : 'var(--border-subtle)'}`,
          }}>
          {revealing
            ? <><RefreshCw size={11} className="animate-spin"/> Revealing…</>
            : revealed
              ? <><EyeOff size={11}/> Hide Keys</>
              : <><Eye size={11}/> {only === 'device' ? 'Reveal Saved Keys' : 'Reveal Keys'}</>}
        </button>
        {revealErr && <span className="text-xs" style={{ color: 'var(--pastel-red)' }}>{revealErr}</span>}
        {revealed && (
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            Keys are visible — close this tab when done.
          </span>
        )}
      </div>
    </div>
  )
}

export function InatRefreshInline() {
  const [state, setState] = useState('idle') // idle | refreshing | ok | error
  const [msg, setMsg] = useState(null)

  const handleRefresh = async () => {
    setState('refreshing')
    setMsg(null)
    try {
      const r = await api.settings.inat.refreshNow()
      setState('ok')
      setMsg(r.status === 'skipped' ? 'Skipped — check credentials are saved first.' : 'Your personal token was refreshed.')
    } catch (e) {
      setState('error')
      setMsg(e.message || 'Refresh failed')
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button onClick={handleRefresh} disabled={state === 'refreshing'}
              className="btn-secondary text-xs px-3 py-1 disabled:opacity-50">
        {state === 'refreshing' ? 'Refreshing…' : 'Refresh Now'}
      </button>
      {msg && <span className={`text-xs ${state === 'error' ? 'text-red-400' : 'text-gray-500'}`}>{msg}</span>}
    </div>
  )
}

// ── Bird Buddy feeder picker — fetches feeders live using saved
// credentials, lets the user pick which ones to sync ─────────────────────
// Shared masked-secret input, same pattern as ApiKeysPanel's own KeyField
// but usable standalone since each integration Section below manages its
// own independent reveal state rather than sharing ApiKeysPanel's.
function MaskedField({ label, hint, formKey, revealedKey, placeholder, form, setForm, revealed }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
        {label}
      </label>
      <div className="relative">
        <input
          className="input font-mono w-full pr-10"
          type={revealed ? 'text' : 'password'}
          placeholder={placeholder || 'Enter key…'}
          value={revealed ? (revealed[revealedKey] || form[formKey]) : form[formKey]}
          onChange={e => {
            if (revealed) return
            setForm(f => ({ ...f, [formKey]: e.target.value }))
          }}
          readOnly={!!revealed}
        />
        {revealed && revealed[revealedKey] && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2">
            <CheckCircle size={13} style={{ color: 'var(--accent-400)' }}/>
          </span>
        )}
      </div>
      {hint && <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{hint}</p>}
    </div>
  )
}

// Small "Reveal" toggle reused by each integration card below — each card
// manages this independently (its own useState), so revealing one card's
// secret doesn't affect the others. Calls the same api.revealKeys()
// ApiKeysPanel uses; cheap and infrequent enough that per-card duplication
// isn't worth sharing state across three otherwise-independent cards for.
function useCardReveal() {
  const [revealed, setRevealed] = useState(null)
  const [revealing, setRevealing] = useState(false)
  const handleReveal = async () => {
    if (revealed) { setRevealed(null); return }
    setRevealing(true)
    try {
      setRevealed(await api.revealKeys())
    } catch (e) {
      setRevealed(null)
    } finally {
      setRevealing(false)
    }
  }
  return { revealed, revealing, handleReveal }
}

function RevealButton({ revealed, revealing, onClick }) {
  return (
    <button onClick={onClick} disabled={revealing}
            className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg transition-all flex-shrink-0"
            style={{
              background: revealed ? 'rgba(248,113,113,.1)' : 'var(--bg-raised)',
              color: revealed ? 'var(--pastel-red)' : 'var(--text-secondary)',
              border: `1px solid ${revealed ? 'rgba(248,113,113,.3)' : 'var(--border-subtle)'}`,
            }}>
      {revealing ? <><RefreshCw size={11} className="animate-spin"/> Revealing…</>
        : revealed ? <><EyeOff size={11}/> Hide</> : <><Eye size={11}/> Reveal</>}
    </button>
  )
}

function HaikuboxSection({ form, setForm, settings }) {
  const { revealed, revealing, handleReveal } = useCardReveal()
  return (
    <Section icon={Radio} title="Haikubox" id="settings-integrations-haikubox">
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <p className="text-xs flex-1" style={{ color: 'var(--text-tertiary)' }}>
Checks your Haikubox every 15 minutes and imports its detections as a device. Turning this off hides the Haikubox and everything from it; the serial number below is kept for when you turn it back on.
</p>
          <input type="checkbox" checked={form.haikubox_enabled ?? false}
                 onChange={e => setForm(f => ({ ...f, haikubox_enabled: e.target.checked }))}
                 className="w-4 h-4 accent-chirp-500 flex-shrink-0 mt-0.5"/>
        </div>

        <div className="flex items-end gap-2">
          <div className="flex-1">
            <MaskedField label="Haikubox Serial Number" formKey="haikubox_serial" revealedKey="haikubox_serial"
                         placeholder={settings?.haikubox_serial || 'Enter Haikubox serial number…'}
                         hint="e.g. 1000000066e59043"
                         form={form} setForm={setForm} revealed={revealed}/>
          </div>
          <RevealButton revealed={revealed} revealing={revealing} onClick={handleReveal}/>
        </div>

        {/* Sync Now doubles as the connection test — a live pull against the
            Haikubox API surfaces auth/serial errors immediately via
            the status panel below, same as a dedicated test would. */}
        {form.haikubox_enabled && settings?.haikubox_serial
          ? <HaikuboxStatusPanel/>
          : (
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              Enable and save a serial number above to test the connection.
            </p>
          )}
      </div>
    </Section>
  )
}

function BirdBuddySection({ form, setForm, settings }) {
  const { revealed, revealing, handleReveal } = useCardReveal()
  return (
    <Section icon={BirdIcon} title="Bird Buddy" id="settings-integrations-birdbuddy">
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <p className="text-xs flex-1" style={{ color: 'var(--text-tertiary)' }}>
Checks your Bird Buddy every 15 minutes for new postcards and runs each video's audio through BirdNET, like an upload. Bird Buddy's species ID isn't used, so scores match the rest of Chirp.
</p>
          <input type="checkbox" checked={form.bird_buddy_enabled ?? false}
                 onChange={e => setForm(f => ({ ...f, bird_buddy_enabled: e.target.checked }))}
                 className="w-4 h-4 accent-chirp-500 flex-shrink-0 mt-0.5"/>
        </div>

        <div className="flex items-end gap-2">
          <div className="flex-1 space-y-1">
            <label className="text-xs text-gray-500 mb-1 block">Bird Buddy Email</label>
            <input className="input text-sm w-full" type="email"
                   value={form.bird_buddy_email ?? ''}
                   onChange={e => setForm(f => ({ ...f, bird_buddy_email: e.target.value }))}
                   placeholder={settings?.bird_buddy_email || 'you@example.com'}/>
          </div>
        </div>

        <div className="flex items-end gap-2">
          <div className="flex-1">
            <MaskedField label="Bird Buddy Password" formKey="bird_buddy_password" revealedKey="bird_buddy_password"
                         placeholder={settings?.bird_buddy_password || 'Enter Bird Buddy account password…'}
                         hint="Stored on the server — never sent back to the browser in plain text once saved."
                         form={form} setForm={setForm} revealed={revealed}/>
          </div>
          <RevealButton revealed={revealed} revealing={revealing} onClick={handleReveal}/>
        </div>

        {form.bird_buddy_email && <BirdBuddyFeederPicker form={form} setForm={setForm}/>}

        {/* Sync Now doubles as the connection test, same reasoning as Haikubox above */}
        {form.bird_buddy_enabled && settings?.bird_buddy_email
          ? <BirdBuddyStatusPanel settings={settings}/>
          : (
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              Enable and save your email/password above to test the connection.
            </p>
          )}
      </div>
    </Section>
  )
}

function BirdWeatherSection({ form, setForm, settings }) {
  const { revealed, revealing, handleReveal } = useCardReveal()
  const [busy, setBusy] = useState(null)   // 'test' | 'sync'
  const [msg, setMsg] = useState(null)
  const run = async (what) => {
    setBusy(what); setMsg(null)
    try {
      if (what === 'test') {
        const r = await api.settings.birdWeather.test()
        setMsg({ ok: true, text: r.soundscapes_last_7_days
          ? `Connected: ${r.soundscapes_last_7_days} sound${r.soundscapes_last_7_days === 1 ? '' : 's'} in the last 7 days, latest ${new Date(r.latest).toLocaleString()}.`
          : 'Connected, but the station has no sound from the last 7 days.' })
      } else {
        await api.settings.birdWeather.sync()
        setMsg({ ok: true, text: 'Sync started. New recordings appear within a few minutes.' })
      }
    } catch (e) {
      setMsg({ ok: false, text: e.message || 'Could not reach BirdWeather' })
    } finally { setBusy(null) }
  }
  const err = settings?.birdweather_last_sync_error
  return (
    <Section icon={Cloud} title="BirdWeather" id="settings-integrations-birdweather">
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <p className="text-xs flex-1" style={{ color: 'var(--text-tertiary)' }}>
            Brings in the sound from a BirdWeather station (PUC, BirdNET-Pi or BirdNET-Go) every 15 minutes and runs it through BirdNET like an upload, with spectrograms and playback. The station token is on app.birdweather.com under your station's settings.
          </p>
          <input type="checkbox" checked={form.birdweather_enabled ?? false}
                 onChange={e => setForm(f => ({ ...f, birdweather_enabled: e.target.checked }))}
                 className="w-4 h-4 accent-chirp-500 flex-shrink-0 mt-0.5" aria-label="Sync BirdWeather"/>
        </div>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <MaskedField label="Station token" formKey="birdweather_token" revealedKey="birdweather_token"
                         placeholder={settings?.birdweather_token || 'Paste the BirdWeather station token…'}
                         hint="Stored on the server and shown masked once saved."
                         form={form} setForm={setForm} revealed={revealed}/>
          </div>
          <RevealButton revealed={revealed} revealing={revealing} onClick={handleReveal}/>
        </div>
        {settings?.birdweather_token ? (
          <div className="rounded-xl border p-4 space-y-3 text-sm" style={{ background: 'var(--bg-raised)', borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2 min-w-0">
                <span className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: err ? '#f87171' : settings?.birdweather_last_sync_at ? '#4ade80' : '#6b7280' }}/>
                <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  {!settings?.birdweather_enabled ? 'Sync is off'
                    : settings?.birdweather_last_sync_at ? `Last synced ${new Date(settings.birdweather_last_sync_at + 'Z').toLocaleTimeString()}` : 'Not synced yet'}
                </span>
              </div>
              <div className="flex gap-2">
                <button onClick={() => run('test')} disabled={!!busy} className="btn-secondary text-xs px-3 py-1 disabled:opacity-50">
                  {busy === 'test' ? 'Testing…' : 'Test'}
                </button>
                {settings?.birdweather_enabled && (
                  <button onClick={() => run('sync')} disabled={!!busy} className="btn-secondary text-xs px-3 py-1 disabled:opacity-50">
                    {busy === 'sync' ? 'Starting…' : 'Sync now'}
                  </button>
                )}
              </div>
            </div>
            {err && <p className="text-xs text-red-400">{err}</p>}
            {msg && <p className="text-xs" style={{ color: msg.ok ? 'var(--text-tertiary)' : '#f87171' }}>{msg.text}</p>}
          </div>
        ) : (
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Save a station token to test the connection.</p>
        )}
      </div>
    </Section>
  )
}

function InatSection({ form, setForm, settings }) {
  const { revealed, revealing, handleReveal } = useCardReveal()
  const [testState, setTestState] = useState('idle') // idle | testing | ok | error
  const [testMsg, setTestMsg] = useState(null)

  const handleTest = async () => {
    setTestState('testing')
    setTestMsg(null)
    try {
      const r = await api.settings.inat.test()
      setTestState('ok')
      setTestMsg(`✓ Valid — logged in as ${r.login} (${r.source === 'personal' ? 'your personal token' : 'global fallback token'})`)
    } catch (e) {
      setTestState('error')
      setTestMsg(e.message || 'Test failed')
    }
  }

  return (
    <Section icon={INatIcon} title="iNaturalist" id="settings-integrations-inat">
      <div className="space-y-4">
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
Used for photos, range data and submitting sound observations. The site token below is used by anyone without a personal token (set on their Profile page); a personal token always wins for that person's submissions.
</p>

        {/* iNat token age warning */}
        {settings?.inat_token_set_at && (() => {
          const setAt = new Date(settings.inat_token_set_at)
          const ageH = (Date.now() - setAt.getTime()) / 3600000
          if (ageH < 20) return null
          const color = ageH > 24 ? '#f87171' : 'var(--pastel-amber)'
          const msg = ageH > 24
            ? `⚠️ Global token expired ${Math.round(ageH - 24)}h ago — submissions using it will fail until refreshed.`
            : `⏰ Global token expires in ~${Math.round(24 - ageH)}h — consider refreshing it soon.`
          return (
            <div className="text-xs px-3 py-2 rounded flex items-start gap-2"
                 style={{ background: 'rgba(248,113,113,0.06)', border: `1px solid ${color}40`, color }}>
              <span>{msg}</span>
              <a href="https://www.inaturalist.org/users/api_token" target="_blank" rel="noreferrer"
                 className="flex-shrink-0 underline" style={{ color }}>Refresh ↗</a>
            </div>
          )
        })()}

        <div className="flex items-end gap-2">
          <div className="flex-1">
            <MaskedField label="iNaturalist API Token (global fallback)" formKey="inat_api_token" revealedKey="inat_api_token"
                         placeholder={settings?.inat_api_token || 'Enter iNaturalist token…'}
                         hint={<>Expires every 24h — paste a fresh one from{' '}
                           <a href="https://www.inaturalist.org/users/api_token" target="_blank" rel="noreferrer"
                              style={{color:'var(--accent-500)'}}>inaturalist.org/users/api_token</a>, or set up
                           auto-refresh below.</>}
                         form={form} setForm={setForm} revealed={revealed}/>
          </div>
          <RevealButton revealed={revealed} revealing={revealing} onClick={handleReveal}/>
        </div>

        <div className="rounded-lg border border-surface-700 bg-surface-800 p-4 space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-200">Auto-Refresh Token</p>
              <p className="text-xs text-gray-500 mt-1">
Gets a new token every 12 hours so you don't have to paste one daily. It updates <strong>your personal token</strong> (Profile page), not the site token, and needs your iNaturalist username and password. An OAuth app (free,{' '} <a href="https://www.inaturalist.org/oauth/applications/new" target="_blank" rel="noreferrer" style={{color:'var(--accent-500)'}}>register here</a>, any redirect URI) is optional but more reliable; without one Chirp signs in like a browser, which can break if iNaturalist changes its sign-in page.
</p>
            </div>
            <input type="checkbox" checked={form.inat_auto_refresh_enabled ?? false}
                   onChange={e => setForm(f => ({ ...f, inat_auto_refresh_enabled: e.target.checked }))}
                   className="w-4 h-4 accent-chirp-500 flex-shrink-0 mt-0.5"/>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input className="input text-sm" placeholder="iNaturalist username"
                   value={form.inat_username ?? ''}
                   onChange={e => setForm(f => ({ ...f, inat_username: e.target.value }))}/>
            <input className="input text-sm" type="password" placeholder={settings?.inat_password || 'iNaturalist password'}
                   value={form.inat_password ?? ''}
                   onChange={e => setForm(f => ({ ...f, inat_password: e.target.value }))}/>
            <input className="input text-sm" placeholder="OAuth client_id (optional)"
                   value={form.inat_oauth_client_id ?? ''}
                   onChange={e => setForm(f => ({ ...f, inat_oauth_client_id: e.target.value }))}/>
            <input className="input text-sm" type="password" placeholder={settings?.inat_oauth_client_secret || 'OAuth client_secret (optional)'}
                   value={form.inat_oauth_client_secret ?? ''}
                   onChange={e => setForm(f => ({ ...f, inat_oauth_client_secret: e.target.value }))}/>
          </div>
          {settings?.inat_last_refresh_error && (
            <p className="text-xs text-red-400">{settings.inat_last_refresh_error}</p>
          )}
          <InatRefreshInline/>
        </div>

        {/* Test Connection — genuinely new, distinct from Refresh Now: this
            validates whichever token is in use right now (checks
            the calling admin's personal token first, falling back to the
            global one) against the iNaturalist API, rather than
            fetching a brand-new token. */}
        <div className="flex items-center gap-2">
          <button onClick={handleTest} disabled={testState === 'testing'}
                  className="btn-secondary text-xs px-3 py-1 disabled:opacity-50 flex items-center gap-1.5">
            {testState === 'testing' ? <><RefreshCw size={11} className="animate-spin"/> Testing…</> : 'Test Connection'}
          </button>
          {testMsg && (
            <span className="text-xs" style={{ color: testState === 'error' ? '#f87171' : 'var(--pastel-green)' }}>
              {testMsg}
            </span>
          )}
        </div>
      </div>
    </Section>
  )
}

function TailscaleStatusPanel() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)
  const [authKey, setAuthKey] = useState('')
  const [loginServer, setLoginServer] = useState('')
  const [hostname, setHostname] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  const load = () => {
    api.settings.tailscaleStatus().then(s => {
      setStatus(s)
      setEnabled(s.enabled)
      setLoginServer(s.login_server || '')
    }).catch(e => setError(e.message))
  }
  useEffect(() => { load() }, [])

  if (error) return <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{error}</p>
  if (!status) return <div className="skeleton h-16 rounded-xl"/>

  if (!status.binary_installed) {
    return (
      <p className="text-sm" style={{ color: 'var(--pastel-amber)' }}>
        The tailscale client isn't installed in this image yet — rebuild from the current Dockerfile to get it.
      </p>
    )
  }

  const save = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      const result = await api.settings.tailscaleConfig({ enabled, auth_key: authKey, login_server: loginServer, hostname })
      setStatus(result)
      setAuthKey('')  // clear the input; a saved key is never echoed back
    } catch (e) {
      setSaveError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="relative inline-flex w-2 h-2 flex-shrink-0">
          <span className="absolute inset-0 rounded-full" style={{ background: status.connected ? '#4ade80' : (status.enabled ? '#f59e0b' : '#6b7280') }}/>
          {status.connected && <span className="absolute inset-0 rounded-full animate-live" style={{ background: '#4ade80' }}/>}
        </span>
        <p className="text-sm font-medium text-gray-200">
          {status.connected ? `Connected — ${status.ip}` : status.enabled ? 'Enabled, not yet connected' : 'Not connected'}
        </p>
      </div>

      <p className="text-xs text-gray-500">
        Reach this server from anywhere on your tailnet, not just its local network — the same way chirp-device
        already lets you reach a Pi over Tailscale. Generate a key from your Tailscale (or self-hosted Headscale)
        admin console, paste it below, and turn this on — no .env editing or container restart needed.
      </p>

      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2.5 cursor-pointer">
          <input type="checkbox" className="toggle" checked={enabled} onChange={e => setEnabled(e.target.checked)}/>
          <span className="text-sm text-gray-300">Enable Tailscale</span>
        </label>
      </div>

      <div className="space-y-2">
        <label className="text-xs text-gray-500">Auth key</label>
        <input type="password" className="input w-full"
               placeholder={status.enabled ? '•••••••••••••• (saved — leave blank to keep it)' : 'tskey-auth-...'}
               value={authKey} onChange={e => setAuthKey(e.target.value)}/>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <label className="text-xs text-gray-500">Login server (optional)</label>
          <input className="input w-full" placeholder="tailscale.com (default)"
                 value={loginServer} onChange={e => setLoginServer(e.target.value)}/>
        </div>
        <div className="space-y-2">
          <label className="text-xs text-gray-500">Hostname (optional)</label>
          <input className="input w-full" placeholder="auto"
                 value={hostname} onChange={e => setHostname(e.target.value)}/>
        </div>
      </div>

      {saveError && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{saveError}</p>}

      <button onClick={save} disabled={saving || (enabled && !authKey && !status.enabled)}
              className="btn-primary text-sm px-4 py-2">
        {saving ? 'Connecting…' : 'Save & Connect'}
      </button>
    </div>
  )
}

function DeviceKeyRow({ k, onDeleted }) {
  const [revealed, setRevealed] = useState(false)
  return (
    <div className="flex items-center justify-between py-2 px-3 bg-surface-800 rounded-lg border border-surface-700 gap-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-200">{k.name}</p>
        <p className="text-xs text-gray-600">Created {new Date(k.created_at).toLocaleDateString()}</p>
        {revealed && (
          <p className="text-xs font-mono mt-1 truncate" style={{ color: 'var(--accent-400)' }}>{k.key || '(no value stored)'}</p>
        )}
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <button onClick={() => setRevealed(r => !r)}
                className="text-gray-500 hover:text-gray-300 p-1" aria-label={revealed ? 'Hide key' : 'Reveal key'}>
          {revealed ? <EyeOff size={13}/> : <Eye size={13}/>}
        </button>
        <button onClick={async () => { await api.settings.deviceKeys.delete(k.id); onDeleted() }}
                className="text-red-500 hover:text-red-400 text-xs px-2 py-1 rounded border border-red-800/40 hover:bg-red-900/20 transition-colors">
          Revoke
        </button>
      </div>
    </div>
  )
}

function BirdBuddyFeederPicker({ form, setForm }) {
  const [feeders, setFeeders] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchFeeders = () => {
    setLoading(true)
    setError(null)
    api.settings.birdBuddy.feeders()
      .then(r => setFeeders(r.feeders || []))
      .catch(e => setError(e.message || 'Could not reach Bird Buddy'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchFeeders() }, [])

  const selected = form.bird_buddy_selected_feeders || []
  const toggle = (id) => {
    const next = selected.includes(id) ? selected.filter(x => x !== id) : [...selected, id]
    setForm(f => ({ ...f, bird_buddy_selected_feeders: next }))
  }

  return (
    <div className="rounded-lg border border-surface-700 bg-surface-800 p-4 space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-gray-200">Feeders to Sync</p>
        <button onClick={fetchFeeders} disabled={loading} className="btn-secondary text-xs px-2 py-1 disabled:opacity-50">
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      <p className="text-xs text-gray-500">Leave all unchecked to sync every feeder on the account.</p>
      {error && <p className="text-xs text-red-400">{error}</p>}
      {feeders && feeders.length === 0 && <p className="text-xs text-gray-500">No feeders found on this account.</p>}
      {feeders && feeders.map(f => (
        <label key={f.id} className="flex items-center gap-2 text-sm text-gray-300">
          <input type="checkbox" checked={selected.includes(f.id)} onChange={() => toggle(f.id)}
                 className="w-4 h-4 accent-chirp-500"/>
          {f.name} <span className="text-xs text-gray-500">({f.serial})</span>
        </label>
      ))}
    </div>
  )
}

// ── Bird Buddy status panel — top-level component so hooks are stable ───
function BirdBuddyStatusPanel({ settings }) {
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState(null)

  const handleSync = async () => {
    setSyncing(true)
    setSyncMsg(null)
    try {
      await api.settings.birdBuddy.sync()
      setSyncMsg('Sync started — new recordings will appear within a minute or two.')
    } catch (e) {
      setSyncMsg('Sync failed: ' + (e.message || 'unknown error'))
    } finally {
      setSyncing(false)
    }
  }

  const hasError = !!settings?.bird_buddy_last_sync_error
  const statusColor = hasError ? '#f87171' : settings?.bird_buddy_last_sync_at ? '#4ade80' : '#6b7280'

  return (
    <div className="rounded-xl border p-4 space-y-3 text-sm"
         style={{ background: 'var(--bg-raised)', borderColor: 'var(--border-subtle)' }}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: statusColor }}/>
          <span className="font-medium" style={{ color: 'var(--text-primary)' }}>Bird Buddy</span>
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            {settings?.bird_buddy_last_sync_at
              ? `last synced ${new Date(settings.bird_buddy_last_sync_at + 'Z').toLocaleTimeString()}`
              : 'not yet synced'}
          </span>
        </div>
        <button onClick={handleSync} disabled={syncing}
                className="btn-secondary text-xs px-3 py-1 disabled:opacity-50 flex-shrink-0">
          {syncing ? 'Syncing…' : 'Sync Now'}
        </button>
      </div>
      {hasError && <p className="text-xs text-red-400">{settings.bird_buddy_last_sync_error}</p>}
      {syncMsg && <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{syncMsg}</p>}
    </div>
  )
}

function HaikuboxStatusPanel() {
  const [status, setStatus] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState(null)

  useEffect(() => {
    api.settings.haikubox.status().then(setStatus).catch(() => {})
  }, [])

  const handleSync = async () => {
    setSyncing(true)
    setSyncMsg(null)
    try {
      await api.settings.haikubox.sync()
      setSyncMsg('Sync started — new detections will appear within a few seconds.')
      setTimeout(() => {
        api.settings.haikubox.status().then(setStatus).catch(() => {})
      }, 4000)
    } catch (e) {
      setSyncMsg('Sync failed: ' + (e.message || 'unknown error'))
    } finally {
      setSyncing(false)
    }
  }

  if (!status) return null

  const statusColor = status.status === 'online' ? '#4ade80'
    : status.status === 'offline' ? '#f87171' : '#6b7280'

  return (
    <div className="rounded-xl border p-4 space-y-3 text-sm"
         style={{ background: 'var(--bg-raised)', borderColor: 'var(--border-subtle)' }}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: statusColor }}/>
          <span className="font-medium" style={{ color: 'var(--text-primary)' }}>
            Haikubox {status.serial}
          </span>
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            {status.status === 'online' ? 'synced'
              : status.status === 'never_connected' ? 'not yet synced' : 'offline'}
            {status.last_seen ? ` · ${new Date(status.last_seen + 'Z').toLocaleTimeString()}` : ''}
          </span>
        </div>
        <button onClick={handleSync} disabled={syncing}
                className="btn-secondary text-xs px-3 py-1 disabled:opacity-50 flex-shrink-0">
          {syncing ? 'Syncing…' : 'Sync Now'}
        </button>
      </div>
      {status.total_recordings > 0 && (
        <p style={{ color: 'var(--text-secondary)' }}>
          {status.total_recordings} detection{status.total_recordings !== 1 ? 's' : ''} imported
        </p>
      )}
      {syncMsg && (
        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{syncMsg}</p>
      )}
    </div>
  )
}

function ExpandableError({ text }) {
  // Fix for a direct report: this error text used to be
  // hard-truncated at 35 characters with only a hover-only `title`
  // tooltip as the fallback — which doesn't work at all on mobile,
  // the platform this diagnostic panel gets used on (touch has
  // no hover state). Tap-to-expand works identically on touch and mouse.
  const [expanded, setExpanded] = useState(false)
  const truncated = text.length > 35
  if (!truncated) {
    return <span style={{ color: '#f87171', fontSize: 9, flexShrink: 0 }}>{text}</span>
  }
  return (
    <span onClick={() => setExpanded(e => !e)}
          style={{
            color: '#f87171', fontSize: 9, cursor: 'pointer',
            flexShrink: expanded ? 1 : 0,
            whiteSpace: expanded ? 'normal' : 'nowrap',
            wordBreak: expanded ? 'break-word' : 'normal',
            textAlign: 'right',
          }}
          title={text}>
      {expanded ? text : text.slice(0, 35) + '… (tap for full error)'}
    </span>
  )
}

// ── Page structure ───────────────────────────────────────────────────────────
// One entry per tab, in page order. `anchor` is the zero-height marker that
// starts the tab's content (see GroupHeader); `blurb` shows on the Settings
// home list (phones) and under the tab title.
const SETTINGS_TABS = [
  { id: 'mine',         label: 'My Notifications',  icon: Bell,         anchor: 'settings-my-notifications',   blurb: 'Your push and email alerts, journals and watched birds', adminOnly: false },
  { id: 'appearance',   label: 'Appearance',        icon: Palette,      anchor: 'settings-appearance',         blurb: 'Theme, dashboard style, card layout and installing the app', adminOnly: false },
  { id: 'site',         label: 'General',           icon: MapPin,       anchor: 'settings-site-group',         blurb: 'Location, time zone, web address and what everyone sees', adminOnly: true },
  { id: 'detection',    label: 'Detection',         icon: Brain,        anchor: 'settings-detection-group',    blurb: 'BirdNET model and thresholds, night callers, server analysis and recording limits', adminOnly: true },
  { id: 'bats',         label: 'Bats',              icon: Moon,         anchor: 'settings-bats-group',         blurb: 'Bat echolocation detection, its microphone and filters', adminOnly: true },
  { id: 'notif',        label: 'Alerts & Email',    icon: Mail,         anchor: 'settings-notif-group',        blurb: 'Daily digest times, station offline alerts, the email server and iPhone push keys', adminOnly: true },
  { id: 'integrations', label: 'Integrations',      icon: Plug,         anchor: 'settings-integrations-group', blurb: 'eBird, Haikubox, Bird Buddy, BirdWeather and iNaturalist', adminOnly: true },
  { id: 'ai',           label: 'AI Features',       icon: Sparkles,     anchor: 'settings-ai-group',           blurb: 'Journals, profile summaries, AI Second Opinion and AI Enhance', adminOnly: true },
  { id: 'storage',      label: 'Storage & Backup',  icon: HardDrive,    anchor: 'settings-storage-group',      blurb: 'Disk use, cleanup, backups and bird data refresh', adminOnly: true },
  { id: 'account',      label: 'Access & Security', icon: Lock,         anchor: 'settings-account-group',      blurb: 'Sign-in, device keys, activity log and network', adminOnly: true },
  { id: 'experimental', label: 'Experimental',      icon: FlaskConical, anchor: 'settings-experimental',       blurb: 'Night flight calls, range maps and the sightings heatmap', adminOnly: true },
  { id: 'diagnostics',  label: 'Diagnostics',       icon: Stethoscope,  anchor: 'settings-diagnostics-group',  blurb: 'Server health, device checks, microphones and logs', adminOnly: true },
]

// What each card holds, so search finds settings inside collapsed cards
// (a collapsed card doesn't render its contents). Keyed by the card's DOM id.
const CARD_KEYWORDS = {
  'settings-exp-range_maps': 'range maps, All About Birds, Macaulay, BirdLife, Geomodel, eBird Status and Trends, GBIF',
  'settings-exp-heatmap': 'heatmap, observation map, iNaturalist sightings',
  'settings-exp-nighthawk': 'Nighthawk, night flight calls, migration, night audio, flight calls',
  'settings-pwa': 'install app, home screen, PWA, progressive web app',
  'settings-my-notifications': 'my notifications, push alerts, email alerts, watched birds, daily digest, journal notifications, station offline',
  'settings-detection-model': 'detection model, BirdNET v3, BirdNET 2.4, model version, minimum confidence, compare, owls',
  'settings-bats': 'bats, bat detection, echolocation, ultrasonic microphone, AudioMoth, species classification, pulse rate, active hours, FM sweep, wobble',
  'settings-ai': 'AI, Anthropic, Claude, OpenAI, Gemini, Ollama, API key, daily journal, weekly journal, profile summaries, AI Second Opinion, photo ID, AI Enhance, tone, token usage, web search',
  'settings-experimental': 'experimental, Nighthawk, night flight calls, range maps, heatmap',
  'settings-appearance-theme': 'theme, colors, dark mode, light mode, custom theme',
  'settings-appearance-icon': 'app icon, home screen icon, icon color',
  'settings-appearance-dashboard': 'dashboard style, simplified, detailed',
  'settings-appearance-dashboard-sections': 'dashboard sections, cards shown',
  'settings-appearance-layout': 'cards expanded by default, collapsed cards, layout',
  'settings-detection': 'BirdNET 2.4, minimum confidence, min. detection confidence, window overlap, detection sensitivity, station threshold',
  'settings-detection-night-thresholds': 'owls, night callers, thresholds',
  'settings-detection-near-misses': 'near misses, owls, night callers',
  'settings-detection-server': 're-analyze every upload, auto-delete device identifications, allow manual re-analyze, rumble removal, enhance, playback, noise reduction, detection colors',
  'settings-detection-devices': 'min. gap between recordings, max recording length, max recordings per hour',
  'settings-site-display': 'min. confidence to display, show low-confidence detections, show deleted recording identifications, what everyone sees',
  'settings-site-address': 'server public URL, web address, links in emails, domain',
  'settings-location': 'location, latitude, longitude, time zone, timezone, address',
  'settings-integrations-haikubox': 'Haikubox serial number',
  'settings-integrations-birdbuddy': 'Bird Buddy email, password, feeders',
  'settings-integrations-birdweather': 'BirdWeather station token, sync',
  'settings-integrations-inat': 'iNaturalist API token, username, auto refresh, OAuth',
  'settings-digest': 'daily digest, digest time, push notification time, email time, evening, morning, test digest',
  'settings-station-offline': 'station offline, device offline, back online, alert delay, minutes, pi down',
  'settings-notif-email': 'SMTP host, port, username, password, from address, admin email, test email, new-species emails, registration emails',
  'settings-notif-apns': 'iPhone push, relay token, APNs, team ID, key ID, bundle ID, auth key, push environment',
  'settings-storage': 'disk usage, compression, archive audio, remove old recordings, size limit, soft-deleted cleanup',
  'settings-storage-empty': 'empty recordings, show nothing, nothing from the server, auto-delete, delete now, purge',
  'settings-activity-log': 'activity log, IP address, history retention',
  'settings-experimental-data': 'refresh all bird profiles, range maps refresh',
  'settings-backup': 'database backup, restore, automatic backups',
  'settings-integrations-ebird': 'eBird API key, eBird S&T API key, Status and Trends',
  'settings-api-device': 'device API keys, generate key',
  'settings-tailscale': 'Tailscale, server network, VPN',
  'settings-auth': 'require login, authentication, admin password',
}

function useIsDesktop() {
  const query = '(min-width: 768px)'
  const [desktop, setDesktop] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setDesktop(mq.matches)
    mq.addEventListener?.('change', on)
    return () => mq.removeEventListener?.('change', on)
  }, [])
  return desktop
}

// Phone home screen: grouped list of tabs, iOS Settings style.
function SettingsHome({ tabs, onOpen, version, isAdmin }) {
  const appInfo = useAppInfo()
  const personal = tabs.filter(t => !t.adminOnly)
  const site = tabs.filter(t => t.adminOnly)
  const Group = ({ title, items }) => (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider px-1 mb-2" style={{ color: 'var(--text-tertiary)' }}>{title}</p>
      <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}>
        {items.map((t, i) => {
          const Icon = t.icon
          return (
            <button key={t.id} onClick={() => onOpen(t.id)} data-haptic="medium"
                    className="w-full flex items-center gap-3 px-4 py-3 text-left active:opacity-70"
                    style={{ borderTop: i ? '1px solid var(--border-subtle)' : 'none' }}>
              <span className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }}>
                <Icon size={16}/>
              </span>
              <span className="flex-1 min-w-0">
                <span className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{t.label}</span>
                <span className="block text-xs line-clamp-2" style={{ color: 'var(--text-tertiary)' }}>{t.blurb}</span>
              </span>
              <ChevronRight size={16} style={{ color: 'var(--text-tertiary)', flexShrink: 0 }}/>
            </button>
          )
        })}
      </div>
    </div>
  )
  return (
    <div className="space-y-5 md:hidden">
      <Group title="You" items={personal}/>
      {isAdmin && site.length > 0 && <Group title="Site (admins)" items={site}/>}
      {!isAdmin && (
        <p className="text-xs px-1" style={{ color: 'var(--text-tertiary)' }}>
          You're signed in as a viewer. Site settings are changed by an administrator.
        </p>
      )}
      <Link to="/changelog" className="block text-center text-xs py-2" style={{ color: 'var(--text-tertiary)', textDecoration: 'none' }}>
        Chirp {version ? `v${version}` : ''}{appInfo ? ` · ${deviceName()} app ${appInfo.version}` : ''} · What&#39;s New
      </Link>
    </div>
  )
}

// Live results under the search box. Built from the rendered page (every
// tab stays in the DOM, only hidden), so new settings are found without
// keeping a separate index.
function SettingsSearch({ containerRef, tabs, tabForElement, onPick }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  useEffect(() => {
    const query = q.trim().toLowerCase()
    if (query.length < 2 || !containerRef.current) { setResults([]); return }
    const t = setTimeout(() => {
      // Cards first (their titles and keywords: a collapsed card's settings
      // aren't in the page until it's opened), then tabs, then any text
      // showing in open cards. Every word typed has to match.
      const words = query.split(/\s+/)
      const hits = hay => words.every(w => hay.includes(w))
      const seen = new Set()
      const out = []
      const add = (el, text, tab) => {
        if (!el || !tab || seen.has(text) || out.length >= 10) return
        seen.add(text); out.push({ el, text, tab })
      }
      for (const [id, kw] of Object.entries(CARD_KEYWORDS)) {
        const card = document.getElementById(id)
        if (!card) continue
        const tab = tabs.find(x => x.anchor === id)?.id || tabForElement(card)
        const title = card.querySelector('h2')?.textContent?.trim() || tabs.find(x => x.id === tab)?.label || ''
        const list = kw.split(',').map(w => w.trim())
        if (hits(title.toLowerCase())) { add(card, title, tab); continue }
        const hit = list.find(w => hits(w.toLowerCase())) || (hits(`${title} ${kw}`.toLowerCase()) ? list[0] : null)
        if (hit) add(card, `${title} › ${hit}`, tab)
      }
      for (const el of containerRef.current.querySelectorAll('[data-settings-content] h2')) {
        const title = (el.textContent || '').trim()
        if (title && hits(title.toLowerCase())) add(el.closest('[id]') || el, title, tabForElement(el))
      }
      for (const tb of tabs) {
        if (hits(`${tb.label} ${tb.blurb}`.toLowerCase())) add(document.getElementById(tb.anchor), `${tb.label} (tab)`, tb.id)
      }
      for (const el of containerRef.current.querySelectorAll('[data-settings-content] label, [data-settings-content] h3, [data-settings-content] p')) {
        const text = (el.textContent || '').trim().replace(/\s+/g, ' ')
        if (!text || text.length > 140 || !hits(text.toLowerCase())) continue
        add(el, text.length > 80 ? text.slice(0, 78) + '…' : text, tabForElement(el))
      }
      setResults(out)
    }, 120)
    return () => clearTimeout(t)
  }, [q, containerRef, tabForElement])
  const label = id => tabs.find(t => t.id === id)?.label || ''
  return (
    <div className="relative">
      <Search size={14} className="absolute left-3 top-[18px] -translate-y-1/2 pointer-events-none" style={{ color: 'var(--text-tertiary)' }}/>
      <input type="search" value={q} onChange={e => setQ(e.target.value)}
             onKeyDown={e => { if (e.key === 'Enter' && results[0]) { onPick(results[0]); setQ('') } }}
             placeholder="Search settings"
             className="w-full pl-9 pr-3 py-2 rounded-xl"
             style={{ fontSize: 16, background: 'var(--bg-raised)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}/>
      {q.trim().length >= 2 && (
        <div className="absolute left-0 right-0 mt-1 z-30 rounded-xl overflow-hidden"
             style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', boxShadow: '0 8px 32px rgba(0,0,0,.35)' }}>
          {results.length === 0 ? (
            <p className="px-4 py-3 text-sm" style={{ color: 'var(--text-tertiary)' }}>No matching settings</p>
          ) : results.map((r, i) => (
            <button key={i} onClick={() => { onPick(r); setQ('') }}
                    className="w-full text-left px-4 py-2.5 hover:bg-raised"
                    style={{ borderTop: i ? '1px solid var(--border-subtle)' : 'none' }}>
              <span className="block text-sm truncate" style={{ color: 'var(--text-primary)' }}>{r.text}</span>
              <span className="block text-xs" style={{ color: 'var(--text-tertiary)' }}>{label(r.tab)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// Appears only while site settings have unsaved edits; sits above the
// phone tab bar.
function SaveBar({ dirty, saving, saved, onSave, onDiscard }) {
  if (!dirty && !saved) return null
  return (
    <div className="fixed left-0 right-0 z-40 flex justify-center pointer-events-none bottom-[calc(56px+max(env(safe-area-inset-bottom),8px)+10px)] md:bottom-5 px-3">
      <div className="pointer-events-auto flex items-center gap-2 pl-4 pr-2 py-2 rounded-2xl w-full max-w-md animate-slide-up"
           style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', boxShadow: '0 8px 28px rgba(0,0,0,.4)' }}>
        <span className="flex-1 text-sm" style={{ color: saved && !dirty ? '#4ade80' : 'var(--text-primary)' }}>
          {saved && !dirty ? 'Saved' : 'Unsaved changes'}
        </span>
        {dirty && (
          <button onClick={onDiscard} disabled={saving} data-haptic="warning" className="btn-ghost px-3 py-1.5 text-sm rounded-lg">Discard</button>
        )}
        {dirty && (
          <button onClick={onSave} disabled={saving} className="btn-primary flex items-center gap-1.5 px-4 py-1.5 text-sm">
            {saving ? <RefreshCw size={14} className="animate-spin"/> : <Save size={14}/>}
            {saving ? 'Saving…' : 'Save'}
          </button>
        )}
        {saved && !dirty && <Check size={16} style={{ color: '#4ade80', marginRight: 8 }}/>}
      </div>
    </div>
  )
}

// Unsaved site-setting edits survive leaving the page (sessionStorage).
// Secrets typed into the form are never written there.
const DRAFT_KEY = 'chirp_settings_draft'
const SECRET_FIELD = /password|secret|api_key|_token|auth_key/
function saveDraft(base, form) {
  try {
    const safe = Object.fromEntries(Object.entries(form).filter(([k]) => !SECRET_FIELD.test(k)))
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ base, form: safe }))
  } catch {}
}
function loadDraft(base) {
  try {
    const d = JSON.parse(sessionStorage.getItem(DRAFT_KEY) || 'null')
    return d && d.base === base ? d.form : null
  } catch { return null }
}
function clearDraft() { try { sessionStorage.removeItem(DRAFT_KEY) } catch {} }

export default function SettingsPage({ currentUser } = {}) {
  const [settings, setSettings] = useState(null)
  const [form, setForm] = useState(null)
  // Reported directly: a failed initial settings fetch left the page
  // stuck on "Loading settings…" forever, silently — the fetch's own
  // promise chain had no .catch() at all, so a rejection (network
  // error, an expired/invalid session, anything) just vanished with no
  // sign of what went wrong or how to recover. Surfaced here instead.
  const [loadError, setLoadError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [serverVersion, setServerVersion] = useState('')
  const [bulkRefreshing, setBulkRefreshing] = useState(false)
  const [bulkDone, setBulkDone] = useState(false)
  const [bulkCount, setBulkCount] = useState(0)
  const [bulkProgress, setBulkProgress] = useState(null) // polled from /enrich-all/status while running
  const [bulkMode, setBulkMode] = useState(null) // 'full' | 'maps_only' — which button triggered the active/last run
  const [deviceKeys, setDeviceKeys] = useState([])
  const [newKeyName, setNewKeyName] = useState('')
  const [newKeyValue, setNewKeyValue] = useState(null) // shown once after creation
  const [saved, setSaved] = useState(false)
  const [storageStatus, setStorageStatus] = useState(null)
  const [cleanupRunning, setCleanupRunning] = useState(false)
  const [activityPurgeRunning, setActivityPurgeRunning] = useState(false)
  const [activityPurgeResult, setActivityPurgeResult] = useState(null)
  const [cleanupResult, setCleanupResult] = useState(null)
  const [orphanTarget, setOrphanTarget] = useState(null) // 'recordings' | 'clips' | null while a confirm dialog is open
  const [orphanBusy, setOrphanBusy] = useState(false)
  const [orphanResult, setOrphanResult] = useState(null) // last purge result, keyed by target
  const [storageDetailsOpen, setStorageDetailsOpen] = useState(false) // collapsed by default — the fetch itself still always runs on mount, this only controls display
  const [softDeletedCount, setSoftDeletedCount] = useState(null)
  const [cleanupDeleteFiles, setCleanupDeleteFiles] = useState(true)
  const [emptyCount, setEmptyCount] = useState(null)
  const [purging, setPurging] = useState(null)
  const [locationSearch, setLocationSearch] = useState('')
  const [locationResults, setLocationResults] = useState([])
  const [searchingLoc, setSearchingLoc] = useState(false)
  const searchTimeout = useRef(null)

  const [userRole, setUserRole] = useState(currentUser?.role || 'admin')
  const [saveEnvStatus, setSaveEnvStatus] = useState(null)
  useEffect(() => {
    if (currentUser?.role) { setUserRole(currentUser.role); return }
    // Opened without the signed-in user (auth off): ask the server.
    api.auth.me()
      .then(r => {
        // api.auth.me() may return a Response or parsed object depending on auth state
        if (r && typeof r.json === 'function') return r.json()
        return r
      })
      .then(u => { if (u?.role) setUserRole(u.role) })
      .catch(() => {}) // Auth disabled = open access, leave default 'admin'
  }, [currentUser?.role])
  const isAdmin = userRole === 'admin'
  // The open tab lives in the URL (?tab=mine is linked from Notifications),
  // so Back and the iOS swipe-back return to the list. Phones show the list
  // of tabs when none is open; wider screens open the first tab.
  const isDesktop = useIsDesktop()
  const [searchParams, setSearchParams] = useSearchParams()
  // In the app, everyone gets Diagnostics for the app's own report; for
  // people who aren't admins it's theirs, not the site's.
  const visibleTabs = SETTINGS_TABS
    .filter(t => !t.adminOnly || isAdmin || (t.id === 'diagnostics' && isApp()))
    .map(t => (!isAdmin && t.id === 'diagnostics') ? { ...t, adminOnly: false, blurb: 'A report about this app for problem reports' } : t)
  const tabParam = searchParams.get('tab')
  const activeTab = visibleTabs.some(t => t.id === tabParam) ? tabParam : (isDesktop ? visibleTabs[0].id : null)
  const activeMeta = SETTINGS_TABS.find(t => t.id === activeTab)
  const scrollToTop = () => settingsContainerRef.current?.closest('main')?.scrollTo({ top: 0 })
  const setActiveTab = (id, { replace = false } = {}) => {
    if (id === activeTab) return
    setSearchParams(id ? { tab: id } : {}, { replace })
    scrollToTop()
  }

  // Diagnostics state
  const [diagLoading, setDiagLoading] = useState(false)
  const [diagData, setDiagData] = useState(null)
  const [diagError, setDiagError] = useState(null)
  const [diagMode, setDiagMode] = useState('full')
  const [diagIncludeLogs, setDiagIncludeLogs] = useState(false)
  const [diagEmailTo, setDiagEmailTo] = useState('')
  const [diagEmailSending, setDiagEmailSending] = useState(false)
  const [diagEmailResult, setDiagEmailResult] = useState(null)
  // Pre-fill from the configured admin email once the form loads — only if
  // the field is still untouched, so it never clobbers something the
  // person already typed in after the initial load.
  useEffect(() => {
    if (form?.admin_email && !diagEmailTo) setDiagEmailTo(form.admin_email)
  }, [form?.admin_email])
  const [diagCollapsed, setDiagCollapsed] = useState({})
  const EXP_COLLAPSE_STORAGE_KEY = 'chirp_exp_cards_collapsed'
  const [expCollapsed, setExpCollapsed] = useState(() => {
    try {
      const saved = localStorage.getItem(EXP_COLLAPSE_STORAGE_KEY)
      return saved ? JSON.parse(saved) : {}
    } catch (e) {
      return {}
    }
  })
  useEffect(() => {
    try { localStorage.setItem(EXP_COLLAPSE_STORAGE_KEY, JSON.stringify(expCollapsed)) } catch (e) { /* storage full/unavailable — collapse state just won't persist this session, not worth surfacing an error for */ }
  }, [expCollapsed])
  const [diagSshPassword, setDiagSshPassword] = useState('')
  const [vacuumRunning, setVacuumRunning] = useState(false)
  const [vacuumResult, setVacuumResult] = useState(null)
  const [vacuumError, setVacuumError] = useState(null)
  const runVacuum = async () => {
    setVacuumRunning(true)
    setVacuumError(null)
    setVacuumResult(null)
    try {
      const r = await api.diagnostics.vacuum()
      setVacuumResult(r)
      runDiagnostics() // refresh db_size/db_reclaimable to reflect the just-freed space
    } catch (e) {
      setVacuumError(e.message || 'VACUUM failed')
    } finally {
      setVacuumRunning(false)
    }
  }
  const [queryPlanRunning, setQueryPlanRunning] = useState(false)
  const [queryPlanResult, setQueryPlanResult] = useState(null)
  const [queryPlanError, setQueryPlanError] = useState(null)
  const runQueryPlan = async () => {
    setQueryPlanRunning(true)
    setQueryPlanError(null)
    setQueryPlanResult(null)
    try {
      setQueryPlanResult(await api.diagnostics.queryPlan())
    } catch (e) {
      setQueryPlanError(e.message || 'Query plan check failed')
    } finally {
      setQueryPlanRunning(false)
    }
  }
  const [diagSshUsername, setDiagSshUsername] = useState('')
  const [sshCredsSaved, setSshCredsSaved] = useState(false) // any device already has a saved password
  const [sshSaveRemember, setSshSaveRemember] = useState(false)
  const [sshSaveStatus, setSshSaveStatus] = useState(null) // null | 'saving' | 'saved' | 'error'

  const toggleDiagSection = (key) =>
    setDiagCollapsed(c => ({ ...c, [key]: !c[key] }))

  // Live mic levels via WebSocket
  const [micLevels, setMicLevels] = useState({}) // deviceId → [{name, db, peak, card, bins}]
  const [micStatus, setMicStatus] = useState({}) // deviceId → string status message
  const [micLocalStatus, setMicLocalStatus] = useState({}) // deviceId → device-local status-server reachability message (kept separate — must not be clobbered by connecting/connected/error)
  const [micSpectro, setMicSpectro] = useState({}) // deviceId → {cardIndex → [[bins],...]} waterfall history
  const [micLiveActive, setMicLiveActive] = useState(false)
  const WATERFALL_ROWS = 40 // rows of FFT history to show
  const micWsRef = useRef(null)

  const startMicLive = (deviceId) => {
    if (micWsRef.current) {
      micWsRef.current.close()
      micWsRef.current = null
    }
    const wsBase = window.location.origin.replace(/^http/, 'ws')
    const token = localStorage.getItem('chirp_token')
    const params = new URLSearchParams()
    if (token) params.set('token', token)
    if (diagSshPassword) params.set('ssh_password', diagSshPassword)
    const ws = new WebSocket(`${wsBase}/api/v1/diagnostics/mic-levels/${deviceId}?${params.toString()}`)
    ws.onopen = () => setMicLiveActive(true)
    ws.onclose = () => { setMicLiveActive(false); micWsRef.current = null }
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'levels') {
          setMicLevels(prev => ({ ...prev, [deviceId]: msg.devices }))
          // Accumulate waterfall rows per card
          setMicSpectro(prev => {
            const hist = { ...(prev[deviceId] || {}) }
            for (const dev of msg.devices) {
              if (!dev.bins) continue
              const rows = hist[dev.card] ? [...hist[dev.card]] : []
              rows.push(dev.bins)
              if (rows.length > WATERFALL_ROWS) rows.shift()
              hist[dev.card] = rows
            }
            return { ...prev, [deviceId]: hist }
          })
        } else if (msg.type === 'local_status') {
          setMicLocalStatus(prev => ({ ...prev, [deviceId]: msg.message }))
        } else if (msg.type === 'status') {
          setMicStatus(prev => ({ ...prev, [deviceId]: msg.message }))
        } else if (msg.type === 'connected' || msg.type === 'connecting') {
          setMicStatus(prev => ({ ...prev, [deviceId]: msg.message }))
        } else if (msg.type === 'error') {
          setMicStatus(prev => ({ ...prev, [deviceId]: '⚠ ' + msg.message }))
        }
      } catch {}
    }
    micWsRef.current = ws
  }

  const stopMicLive = () => {
    if (micWsRef.current) {
      micWsRef.current.send('stop')
      micWsRef.current.close()
      micWsRef.current = null
    }
    setMicLiveActive(false)
    setMicStatus({})
    setMicLocalStatus({})
    setMicSpectro({})
    stopListening()
  }

  // Live LISTEN — hearing a mic, not just watching its level
  // number. Deliberately separate from the level/spectrum WebSocket
  // above: it's an on-demand audio clip fetched on a timer, not a
  // continuous stream, and only ever available for device-local rows
  // (source === 'device_local') — see the server's device_listen()
  // endpoint docstring for why there's no SSH fallback for this one.
  // "Continuous-sounding" playback is approximated by double-buffering:
  // as soon as one clip STARTS playing, the next one is already being
  // fetched, so it's normally ready by the time the current clip ends
  // rather than leaving an audible fetch-latency gap between them.
  const [listeningTo, setListeningTo] = useState(null) // {deviceId, micName} | null
  const listenAudioRef = useRef(null)
  const listenNextClipRef = useRef(null) // Promise<Blob> | null — the pre-fetched next clip
  const listenObjectUrlRef = useRef(null) // current blob: URL, revoked on swap/stop to avoid leaking memory

  const fetchListenClip = (deviceId, micName) =>
    api.diagnostics.listen(deviceId, micName).catch(() => null)

  const stopListening = () => {
    if (listenAudioRef.current) {
      listenAudioRef.current.pause()
      listenAudioRef.current.onended = null
      listenAudioRef.current = null
    }
    if (listenObjectUrlRef.current) {
      URL.revokeObjectURL(listenObjectUrlRef.current)
      listenObjectUrlRef.current = null
    }
    listenNextClipRef.current = null
    setListeningTo(null)
  }

  const playListenClip = async (deviceId, micName, blob) => {
    if (!blob) { stopListening(); return }
    if (listenObjectUrlRef.current) URL.revokeObjectURL(listenObjectUrlRef.current)
    const url = URL.createObjectURL(blob)
    listenObjectUrlRef.current = url
    const audio = new Audio(url)
    listenAudioRef.current = audio
    // Kick off the NEXT clip's fetch now, in parallel with this one
    // playing, rather than waiting for onended to start fetching —
    // that's the difference between a small gap between clips and none.
    listenNextClipRef.current = fetchListenClip(deviceId, micName)
    audio.onended = async () => {
      if (listeningTo?.deviceId !== deviceId || listeningTo?.micName !== micName) return // stopped/switched mid-flight
      const next = await listenNextClipRef.current
      if (listeningTo?.deviceId !== deviceId || listeningTo?.micName !== micName) return // stopped while awaiting
      playListenClip(deviceId, micName, next)
    }
    try { await audio.play() } catch { /* autoplay-policy or similar — surfaced as playback just not starting */ }
  }

  const toggleListen = async (deviceId, micName) => {
    if (listeningTo?.deviceId === deviceId && listeningTo?.micName === micName) {
      stopListening()
      return
    }
    stopListening() // switching mics — stop whatever was playing first
    setListeningTo({ deviceId, micName })
    const first = await fetchListenClip(deviceId, micName)
    playListenClip(deviceId, micName, first)
  }

  // Stop any in-progress listening on unmount — an <audio> element with
  // an object: URL left playing after the component using it unmounts
  // is exactly the kind of leak that's easy to miss since nothing
  // visibly breaks, it just silently keeps a blob (and a network poll
  // loop) alive.
  useEffect(() => () => stopListening(), [])

  const runDiagnostics = async (mode) => {
    const m = mode || diagMode
    setDiagLoading(true)
    setDiagError(null)
    setDiagCollapsed({})
    try {
      const d = await api.diagnostics.run(m, diagSshPassword)
      setDiagData(d)
    } catch (e) {
      setDiagError(e.message || 'Diagnostics failed')
    } finally {
      setDiagLoading(false)
    }
  }

  // Tabbed navigation (matching the Tech Docs admin page's left-nav
  // pattern, per direct request) — shows only the active tab's section,
  // hiding the rest, rather than the earlier "one long page, dropdown
  // scrolls you to it" approach. Deliberately does this by walking 
  // DOM siblings (toggling display:none) instead of restructuring this
  // file's ~5000 lines of existing JSX into conditionally-rendered
  // blocks — every section's content, state, and effects stay
  // completely untouched; only which siblings are visible changes. Each
  // section's start is its existing GroupHeader anchor (already used by
  // scrollTo above); its end is the next section's anchor, or the
  // explicit settings-tabs-end-sentinel div for the last one (Diagnostics)
  // — walking until nextElementSibling is null instead would incorrectly
  // hide the floating Save button, which is a DOM
  // siblings after the last section, not part of any tab.
  // Cards that render only after their data loads (Dashboard Style,
  // Dashboard Sections) appear after this has run, so it runs again
  // whenever the content gains or loses a card.
  useEffect(() => {
    const apply = () => {
    const order = [...SETTINGS_TABS.map(t => t.anchor), 'settings-tabs-end-sentinel']
    const activeAnchor = activeMeta?.anchor
    for (let i = 0; i < order.length - 1; i++) {
      const startEl = document.getElementById(order[i])
      const stopEl = document.getElementById(order[i + 1])
      if (!startEl) continue // section not in the DOM for this user (e.g. non-admin) — nothing to toggle
      const isActive = order[i] === activeAnchor
      let node = startEl
      while (node && node !== stopEl) {
        // Reported directly, with screenshots: every tab except
        // Appearance (the first one) rendered slightly lower than it
        // should, as if extra space were creeping in above it. Root
        // cause: this container uses Tailwind's space-y-6, whose
        // generated selector is `> :not([hidden]) ~ :not([hidden])` —
        // it specifically checks the hidden ATTRIBUTE, confirmed
        // directly in the compiled CSS. Setting only style.display here
        // hides sections visually, but they still lack the hidden
        // attribute, so Tailwind's selector still counts them as
        // "present" siblings and keeps adding their margin-top to
        // whatever comes after — which is every tab but the first, since
        // only Appearance has no hidden-but-still-counted siblings
        // before it. Setting the hidden attribute too (not display
        // alone) is what excludes a section from that
        // calculation.
        node.style.display = isActive ? '' : 'none'
        node.hidden = !isActive
        node = node.nextElementSibling
      }
    }
    }
    apply()
    const content = settingsContainerRef.current?.querySelector('[data-settings-content]')
    if (!content) return
    const watcher = new MutationObserver(apply)
    watcher.observe(content, { childList: true })
    return () => watcher.disconnect()
  })

  // Simple text search across the page's own labels/headings —
  // deliberately reuses what's already rendered rather than maintaining
  // a separate searchable index of every setting, which would need to
  // stay in sync by hand as settings are added or reworded. Finds the
  // first matching element within the settings container, switches to
  // whichever tab contains it (a match inside a display:none
  // section can't be meaningfully scrolled to — the old "one long page"
  // version didn't need this step, since nothing was ever hidden then),
  // then scrolls to it and gives it a brief highlight. Ported from
  // chirp-server.
  const settingsContainerRef = useRef(null)

  const findTabForElement = useCallback((el) => {
    let best = null
    for (const t of SETTINGS_TABS) {
      const anchorEl = document.getElementById(t.anchor)
      if (!anchorEl) continue
      // SETTINGS_TABS is in document order: the last anchor before the
      // element starts the tab that contains it.
      if (anchorEl.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) best = t.id
    }
    return best
  }, [])

  const openSearchResult = ({ el, tab }) => {
    const highlightAndScroll = () => {
      // A collapsed card renders only its header button: open it.
      const cardEl = el.closest('.card') || (el.id?.startsWith('settings-exp-') ? el : null)
      if (cardEl && cardEl.children.length === 1) cardEl.querySelector('button')?.click()
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      const prevTransition = el.style.transition
      const prevBg = el.style.backgroundColor
      el.style.transition = 'background-color 0.3s ease'
      el.style.backgroundColor = 'rgba(251, 146, 60, 0.25)'
      setTimeout(() => {
        el.style.backgroundColor = prevBg
        setTimeout(() => { el.style.transition = prevTransition }, 350)
      }, 1200)
    }
    if (tab !== activeTab) {
      setSearchParams({ tab })
      // wait for the tab's content to be shown before scrolling to it
      setTimeout(highlightAndScroll, 80)
    } else {
      highlightAndScroll()
    }
  }

  useEffect(() => {
    api.health().then(d => setServerVersion(d?.version || '')).catch(() => {})
  }, [])

  // Each tab's extra data loads the first time the tab opens, not all at once.
  const loadedTabs = useRef(new Set())
  useEffect(() => {
    if (!isAdmin || !activeTab || loadedTabs.current.has(activeTab)) return
    loadedTabs.current.add(activeTab)
    if (activeTab === 'storage') {
      api.settings.deletedCount().then(d => setSoftDeletedCount(d.soft_deleted_count)).catch(() => {})
      api.settings.emptyCount().then(setEmptyCount).catch(() => {})
      api.recordings.storageStatus().then(setStorageStatus).catch(() => {})
    } else if (activeTab === 'account') {
      api.settings.deviceKeys.list().then(setDeviceKeys).catch(() => {})
    } else if (activeTab === 'diagnostics') {
      api.devices.list().then(devs => {
        const withIp = (devs || []).filter(d => d.ip_address)
        setSshCredsSaved(withIp.length > 0 && withIp.some(d => d.ssh_password_set))
        const withUsername = withIp.find(d => d.ssh_username)
        if (withUsername) setDiagSshUsername(withUsername.ssh_username)
      }).catch(() => {})
    }
  }, [activeTab, isAdmin])

  // Site settings (admins only; viewers' tabs don't use them).
  const [baseJson, setBaseJson] = useState(null)
  useEffect(() => {
    if (!isAdmin) return
    api.settings.get()
      .then(s => {
        setSettings(s)
        const initial = ({
          latitude: s.latitude ?? '',
          longitude: s.longitude ?? '',
          location_name: s.location_name ?? '',
          ebird_api_key: '',
          ebird_st_api_key: '',
          inat_api_token: '',
          haikubox_serial: '',
          haikubox_enabled: s.haikubox_enabled ?? false,
          bird_buddy_enabled: s.bird_buddy_enabled ?? false,
          bird_buddy_email: s.bird_buddy_email ?? '',
          bird_buddy_password: '',
          bird_buddy_selected_feeders: s.bird_buddy_selected_feeders ?? [],
          birdweather_enabled: s.birdweather_enabled ?? false,
          birdweather_token: '',
          inat_auto_refresh_enabled: s.inat_auto_refresh_enabled ?? false,
          inat_username: s.inat_username ?? '',
          inat_password: '',
          inat_oauth_client_id: s.inat_oauth_client_id ?? '',
          inat_oauth_client_secret: '',
          anthropic_api_key: '',
          openai_api_key: '',
          gemini_api_key: '',
          ollama_base_url: s.ollama_base_url ?? '',
          ollama_model: s.ollama_model ?? '',
          ollama_api_key: '',
          ollama_api_key_clear: false,
          ai_feature_providers: s.ai_feature_providers ?? {},
          daily_summary_schedule_time: s.daily_summary_schedule_time ?? '07:00',
          daily_summary_schedule_times: s.daily_summary_schedule_times ?? null,
          profile_summary_auto_refresh: s.profile_summary_auto_refresh ?? false,
          profile_summary_refresh_days: s.profile_summary_refresh_days ?? 7,
          profile_summary_refresh_hour: s.profile_summary_refresh_hour ?? 3,
          auto_backup_enabled: s.auto_backup_enabled ?? true,
          auto_backup_hour: s.auto_backup_hour ?? 3,
          auto_backup_retention_count: s.auto_backup_retention_count ?? 14,
          auto_backup_last_run_at: s.auto_backup_last_run_at ?? null,
          auto_backup_last_success_at: s.auto_backup_last_success_at ?? null,
          auto_backup_last_error: s.auto_backup_last_error ?? null,
          weekly_summary_schedule_day: s.weekly_summary_schedule_day ?? 6,
          weekly_summary_schedule_hour: s.weekly_summary_schedule_hour ?? 7,
          ai_personality_friendliness: s.ai_personality_friendliness ?? 60,
          ai_personality_informational: s.ai_personality_informational ?? 50,
          ai_personality_irreverence: s.ai_personality_irreverence ?? 35,
          ai_personality_depth: s.ai_personality_depth ?? 50,
          ai_personality_curiosity: s.ai_personality_curiosity ?? 50,
          ai_web_search_enabled: s.ai_web_search_enabled ?? false,
          apns_team_id: s.apns_team_id ?? '',
          apns_key_id: s.apns_key_id ?? '',
          apns_bundle_id: s.apns_bundle_id ?? '',
          apns_auth_key: s.apns_auth_key ?? '',
          apns_production: s.apns_production ?? true,
          push_relay_token: s.push_relay_token ?? '',
          push_relay_url: s.push_relay_url ?? '',
          server_url: s.server_url ?? '',
          timezone: s.timezone ?? 'America/New_York',
          dark_mode: s.dark_mode ?? true,
          notifications_enabled: s.notifications_enabled ?? false,
          notification_min_confidence: Number(s.notification_min_confidence ?? DEFAULTS.NOTIFICATION_MIN_CONFIDENCE),
          notification_webhook_url: s.notification_webhook_url ?? '',
          min_confidence_display: Number(s.min_confidence_display ?? DEFAULTS.MIN_CONFIDENCE_DISPLAY),
          show_low_confidence: s.show_low_confidence ?? true,
          bat_species_id_enabled: s.bat_species_id_enabled ?? false,
          bat_species_id_min_confidence: Number(s.bat_species_id_min_confidence ?? 0.75),
          birdnet_min_confidence: Number(s.birdnet_min_confidence ?? DEFAULTS.BIRDNET_MIN_CONFIDENCE),
          birdnet_overlap: Number(s.birdnet_overlap ?? DEFAULTS.BIRDNET_OVERLAP),
          birdnet_sensitivity: Number(s.birdnet_sensitivity ?? DEFAULTS.BIRDNET_SENSITIVITY),
          auth_enabled: s.auth_enabled ?? false,
          range_maps_enabled: s.range_maps_enabled ?? false,
          range_map_sources: s.range_map_sources ?? { aab: true, geomodel: true, birdlife: true },
          observation_heatmap_enabled: s.observation_heatmap_enabled ?? false,
          bat_detection_enabled: s.bat_detection_enabled ?? false,
          bat_detection_device_name: s.bat_detection_device_name ?? '',
          bat_active_hours_start: s.bat_active_hours_start ?? '20:00',
          bat_active_hours_end: s.bat_active_hours_end ?? '06:00',
          bat_min_swept_fraction: s.bat_min_swept_fraction ?? 0.3,
          bat_max_pulse_rate: s.bat_max_pulse_rate ?? 60,
          bat_discard_likely_interference: s.bat_discard_likely_interference ?? false,
          bat_auto_remove_wobble: s.bat_auto_remove_wobble ?? false,
          server_reanalyze_on_upload: s.server_reanalyze_on_upload ?? true,
          server_reanalyze_delete_device: s.server_reanalyze_delete_device ?? true,
          allow_manual_reanalyze: s.allow_manual_reanalyze ?? true,
          detection_color_palette: s.detection_color_palette || 'vivid',
          rumble_removal_mode: s.rumble_removal_mode || 'auto',
          ai_enhance_enabled: s.ai_enhance_enabled ?? false,
          ai_enhance_auto_apply: s.ai_enhance_auto_apply ?? false,
          ai_enhance_dry: s.ai_enhance_dry ?? 0.1,
          detection_model: s.detection_model || 'birdnet3',
          exp_birdnet3_shadow: s.exp_birdnet3_shadow ?? false,
          exp_birdnet3_min_conf: s.exp_birdnet3_min_conf ?? 0.5,
          exp_nighthawk_enabled: s.exp_nighthawk_enabled ?? false,
          exp_nighthawk_start: s.exp_nighthawk_start || '21:00',
          exp_nighthawk_end: s.exp_nighthawk_end || '05:00',
          exp_nighthawk_threshold: s.exp_nighthawk_threshold ?? 80,
          show_deleted_detections: s.show_deleted_detections ?? false,
          // Recording device settings
          recording_min_gap_seconds: s.recording_min_gap_seconds ?? DEFAULTS.RECORDING_MIN_GAP_SECONDS,
          recording_max_duration_sec: s.recording_max_duration_sec ?? DEFAULTS.RECORDING_MAX_DURATION_SEC,
          recording_max_per_hour: s.recording_max_per_hour ?? DEFAULTS.RECORDING_MAX_PER_HOUR,
          // Storage management
          storage_compress_on_upload: s.storage_compress_on_upload ?? true,
          storage_compress_quality: s.storage_compress_quality ?? 'lossless',
          storage_max_dir_gb: s.storage_max_dir_gb ?? 0,
          storage_cleanup_keep_flagged: s.storage_cleanup_keep_flagged ?? true,
          auto_delete_recordings_days: s.auto_delete_recordings_days ?? DEFAULTS.AUTO_DELETE_DAYS,
          auto_archive_recordings_days: s.auto_archive_recordings_days ?? DEFAULTS.AUTO_ARCHIVE_DAYS,
          max_recordings_gb: s.max_recordings_gb ?? DEFAULTS.MAX_RECORDINGS_GB,
          auto_purge_empty_recordings: s.auto_purge_empty_recordings ?? false,
          auto_purge_min_confidence: s.auto_purge_min_confidence ?? DEFAULTS.AUTO_PURGE_MIN_CONFIDENCE,
          auto_purge_all_device: s.auto_purge_all_device ?? false,
          distance_unit: s.distance_unit ?? 'mi',
          temperature_unit: s.temperature_unit ?? 'F',
          // Activity log (login + page-view audit trail, admin-only)
          activity_log_enabled: s.activity_log_enabled ?? true,
          activity_log_track_ip: s.activity_log_track_ip ?? true,
          activity_log_retention_days: s.activity_log_retention_days ?? 90,
          // Email / SMTP
          smtp_host: s.smtp_host ?? '',
          smtp_port: s.smtp_port ?? 587,
          smtp_username: s.smtp_username ?? '',
          smtp_password: s.smtp_password ?? '', // arrives masked if set
          smtp_from_address: s.smtp_from_address ?? '',
          smtp_use_tls: s.smtp_use_tls ?? true,
          admin_email: s.admin_email ?? '',
          notify_on_register: s.notify_on_register ?? true,
          digest_hour: s.digest_hour ?? 7,
          digest_push_hour: s.digest_push_hour ?? 21,
          digest_email_hour: s.digest_email_hour ?? 21,
          show_tutorial: localStorage.getItem('chirp_tutorial_disabled') !== '1',
        })
        const base = JSON.stringify(initial)
        const draft = loadDraft(base)
        setBaseJson(base)
        setForm(draft ? { ...initial, ...draft } : initial)
      })
      .catch(e => {
        console.error('Failed to load settings:', e)
        setLoadError(e.message || 'Failed to load settings. Check your connection and try reloading.')
      })
  }, [isAdmin])

  const dirty = !!form && !!baseJson && JSON.stringify(form) !== baseJson
  useEffect(() => {
    if (!baseJson || !form) return
    if (dirty) saveDraft(baseJson, form)
    else clearDraft()
  }, [form, baseJson, dirty])
  useEffect(() => {
    if (!dirty) return
    const warn = e => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
  const discardChanges = () => {
    if (baseJson) setForm(JSON.parse(baseJson))
    clearDraft()
  }

  // Bulk "Refresh All Bird Data" progress polling — checks once on mount
  // (so reloading mid-refresh still shows the live bar, not a stale idle
  // state) and then polls every 2s for as long as a refresh is running.
  // Same setInterval/clearInterval pattern as GeomodelDownloadPanel.jsx.
  const pollBulkStatus = () => {
    fetch('/api/v1/birds/enrich-all/status', {
      headers: localStorage.getItem('chirp_token')
        ? { Authorization: 'Bearer ' + localStorage.getItem('chirp_token') } : {}
    }).then(r => r.ok ? r.json() : null).then(s => {
      if (!s) return
      setBulkProgress(s)
      if (s.running) {
        setBulkRefreshing(true)
        setBulkCount(s.total)
        setBulkMode(s.mode)
      } else if (bulkRefreshing) {
        // A run that was in progress just finished
        setBulkRefreshing(false)
        setBulkDone(true)
        setBulkCount(s.total)
        setBulkMode(s.mode)
      }
    }).catch(() => {})
  }

  useEffect(() => {
    pollBulkStatus()
  }, [])

  useEffect(() => {
    if (!bulkRefreshing) return
    const t = setInterval(pollBulkStatus, 2000)
    return () => clearInterval(t)
  }, [bulkRefreshing])

  const searchLocation = async (q) => {
    if (!q.trim()) { setLocationResults([]); return }
    setSearchingLoc(true)
    try { setLocationResults(await api.settings.searchLocation(q)) }
    catch { setLocationResults([]) }
    setSearchingLoc(false)
  }

  const handleLocationInput = (e) => {
    const v = e.target.value
    setLocationSearch(v)
    clearTimeout(searchTimeout.current)
    searchTimeout.current = setTimeout(() => searchLocation(v), 600)
  }

  const selectLocation = (loc) => {
    // Auto-suggest timezone from browser when geolocation is set
    const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone
    setForm(f => ({
      ...f,
      latitude: loc.latitude,
      longitude: loc.longitude,
      location_name: loc.name,
      // Only auto-set if the current timezone is still the default
      timezone: (f.timezone === 'America/New_York' || !f.timezone) ? browserTz : f.timezone,
    }))
    setLocationSearch(loc.name)
    setLocationResults([])
  }

  const set = (key) => (val) => setForm(f => ({ ...f, [key]: val }))

  const handleSave = async () => {
    setSaving(true)
    const submitted = form
    try {
      const payload = { ...form }
      if (!payload.ebird_api_key) delete payload.ebird_api_key
      if (!payload.ebird_st_api_key) delete payload.ebird_st_api_key
      if (!payload.inat_api_token) delete payload.inat_api_token
      if (!payload.haikubox_serial) delete payload.haikubox_serial
      if (!payload.birdweather_token) delete payload.birdweather_token
      if (!payload.anthropic_api_key) delete payload.anthropic_api_key
      if (!payload.openai_api_key) delete payload.openai_api_key
      if (!payload.gemini_api_key) delete payload.gemini_api_key
      if (payload.ollama_api_key_clear) payload.ollama_api_key = ''
      else if (!payload.ollama_api_key) delete payload.ollama_api_key
      delete payload.ollama_api_key_clear
      if (!payload.inat_password) delete payload.inat_password
      if (!payload.inat_oauth_client_secret) delete payload.inat_oauth_client_secret
      if (!payload.bird_buddy_password) delete payload.bird_buddy_password
      // Frontend-only keys — never sent to the settings API
      delete payload.show_tutorial
      // Owned by the Near Misses panel, which saves it itself
      delete payload.birdnet_species_thresholds
      // Owned by the Night-Caller Thresholds panel
      delete payload.night_threshold_mode
      delete payload.night_threshold_species
      if (payload.latitude !== '') payload.latitude = parseFloat(payload.latitude)
      else delete payload.latitude
      if (payload.longitude !== '') payload.longitude = parseFloat(payload.longitude)
      else delete payload.longitude



      const updated = await api.settings.update(payload)
      setSettings(updated)
      setBaseJson(JSON.stringify(submitted))
      clearDraft()
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
      setGlobalTimezone(payload.timezone || null)
      window.dispatchEvent(new CustomEvent('chirp-settings-saved'))
      const deviceAffectingKeys = [
        'recording_min_gap_seconds', 'recording_max_duration_sec', 'recording_max_per_hour',
        'latitude', 'longitude', 'birdnet_min_confidence', 'birdnet_overlap',
        'bat_detection_enabled', 'bat_detection_device_name',
        'bat_active_hours_start', 'bat_active_hours_end',
        'bat_min_swept_fraction', 'bat_max_pulse_rate', 'bat_discard_likely_interference',
      ]
      if (deviceAffectingKeys.some(k => payload[k] !== undefined)) {
        api.devices.syncAllFromSettings().catch(() => {})
      }
    } catch (e) { alert('Save failed: ' + e.message) }
    setSaving(false)
  }

  const handleSaveSshCredentials = async () => {
    setSshSaveStatus('saving')
    try {
      const devs = await api.devices.list()
      const withIp = (devs || []).filter(d => d.ip_address)
      if (withIp.length === 0) {
        setSshSaveStatus('error')
        return
      }
      await Promise.all(withIp.map(d =>
        api.devices.saveSshCredentials(d.id, { username: diagSshUsername, password: diagSshPassword })
      ))
      setSshCredsSaved(true)
      setSshSaveStatus('saved')
      setTimeout(() => setSshSaveStatus(null), 2500)
    } catch (e) {
      setSshSaveStatus('error')
    }
  }

  const handlePurgeOrphans = async (target, confirmed) => {
    setOrphanBusy(true)
    try {
      const result = await api.recordings.purgeOrphans(target, confirmed)
      setOrphanResult({ target, ...result })
      if (confirmed) {
        setOrphanTarget(null) // close the confirm dialog
        api.recordings.storageStatus().then(setStorageStatus).catch(() => {})
      } else {
        setOrphanTarget(target) // open the confirm dialog showing the preview
      }
    } catch (e) {
      setOrphanResult({ target, dry_run: confirmed !== true, error: e.message })
    } finally {
      setOrphanBusy(false)
    }
  }

  const handleSaveEnv = async () => {
    setSaveEnvStatus('saving')
    try {
      await handleSave() // save to DB first
      const r = await api.settings.saveEnv()
      setSaveEnvStatus('ok')
      setTimeout(() => setSaveEnvStatus(null), 5000)
    } catch (e) {
      setSaveEnvStatus('error: ' + (e.message || 'unknown'))
      setTimeout(() => setSaveEnvStatus(null), 6000)
    }
  }


  if (isAdmin && !form) return (
    <div className="flex items-center justify-center h-64">
      {loadError ? (
        <div className="text-center max-w-sm px-4">
          <p className="text-sm mb-3" style={{ color: 'var(--pastel-red)' }}>{loadError}</p>
          <button onClick={() => window.location.reload()} className="btn-secondary text-sm">
            Reload page
          </button>
        </div>
      ) : (
        <div className="text-chirp-500 animate-pulse">Loading settings…</div>
      )}
    </div>
  )

  const ActiveIcon = activeMeta?.icon
  return (
    <div ref={settingsContainerRef} className="p-4 md:p-6 max-w-6xl space-y-5 animate-fade-in">
      {/* Header: phones show the list or one tab with a way back; wider
          screens keep the title, search and a sidebar. */}
      {!isDesktop && activeTab ? (
        <div>
          <button data-haptic="medium" onClick={() => (window.history.state?.idx > 0 ? window.history.back() : setActiveTab(null, { replace: true }))}
                  className="flex items-center gap-1 -ml-1 mb-2 text-sm font-medium"
                  style={{ color: 'var(--accent-400)' }}>
            <ChevronLeft size={18}/> Settings
          </button>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>{activeMeta.label}</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{activeMeta.blurb}</p>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Settings</h1>
<span className="text-xs flex items-center gap-3">
              <a href="https://ourchirp.com/guide.html#settings-you" target="_blank" rel="noopener" style={{ color: 'var(--accent-400)', textDecoration: 'none' }}>Settings guide ↗</a>
              <Link to="/changelog" className="hidden md:inline" style={{ color: 'var(--text-tertiary)', textDecoration: 'none' }}>
                {serverVersion ? `v${serverVersion}` : ''} · What&#39;s New
              </Link>
            </span>
          </div>
          <SettingsSearch containerRef={settingsContainerRef} tabs={SETTINGS_TABS}
                          tabForElement={findTabForElement} onPick={openSearchResult}/>
        </div>
      )}

      <div className="flex flex-col md:flex-row gap-6">
        <nav className="hidden md:flex md:w-56 flex-shrink-0 flex-col gap-0.5 self-start sticky top-0">
          {visibleTabs.map((t, i) => {
            const Icon = t.icon
            const on = activeTab === t.id
            return (
              <div key={t.id}>
                {i > 0 && t.adminOnly && !visibleTabs[i - 1].adminOnly && (
                  <p className="text-[11px] font-semibold uppercase tracking-wider px-3 pt-4 pb-1" style={{ color: 'var(--text-tertiary)' }}>Site</p>
                )}
                <button onClick={() => setActiveTab(t.id)}
                        className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-left"
                        style={{
                          background: on ? 'var(--nav-active-bg)' : 'transparent',
                          color: on ? 'var(--nav-active-text)' : 'var(--text-secondary)',
                          fontWeight: on ? 600 : 400,
                        }}>
                  <Icon size={15} style={{ flexShrink: 0, color: on ? 'var(--accent-400)' : 'var(--text-tertiary)' }}/>
                  {t.label}
                </button>
              </div>
            )
          })}
        </nav>

        {!activeTab && (
          <SettingsHome tabs={visibleTabs} onOpen={setActiveTab} version={serverVersion} isAdmin={isAdmin}/>
        )}

        <div data-settings-content className={`flex-1 min-w-0 max-w-2xl space-y-6 ${activeTab ? '' : 'hidden'}`}>
      {isDesktop && activeMeta && (
        <div className="flex items-start gap-3">
          <span className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }}>
            <ActiveIcon size={18}/>
          </span>
          <div>
            <h2 className="text-lg font-semibold leading-tight" style={{ color: 'var(--text-primary)' }}>{activeMeta.label}</h2>
            <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>{activeMeta.blurb}</p>
          </div>
        </div>
      )}

      <GroupHeader id="settings-my-notifications"/>
      <Suspense fallback={<div className="card h-40 animate-pulse"/>}><MyNotifications/></Suspense>

      <GroupHeader id="settings-appearance"/>
      <ThemeSection />
      <AppIconSection />
      <DashboardStyleSection />

      <Section icon={Eye} title="Card Layout" id="settings-appearance-layout">
        <CardExpandDefaultControl/>
      </Section>

      {!isApp() && (
      <Section icon={Smartphone} title="Install as App (PWA)" id="settings-pwa">
        <p className="text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
Chirp is a <strong style={{ color: 'var(--text-primary)' }}>Progressive Web App</strong>: install it on any device, no app store needed.
</p>
        <div className="space-y-3 mt-2">

          {/* iOS */}
          <div className="rounded-xl p-4" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
            <p className="text-xs font-bold uppercase tracking-wider mb-2.5 flex items-center gap-2"
               style={{ color: 'var(--text-tertiary)' }}>
              <span>🍎</span> iPhone &amp; iPad — Safari only
            </p>
            <div className="space-y-1.5">
              {['Open Chirp in Safari (not Chrome or Firefox)',
                'Tap the Share button — the box with an arrow pointing up',
                'Scroll down and tap Add to Home Screen',
                'Tap Add to confirm'].map((step, i) => (
                <div key={i} className="flex items-start gap-2.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                  <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                        style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>
                    {i + 1}
                  </span>
                  {step}
                </div>
              ))}
            </div>
          </div>

          {/* Android */}
          <div className="rounded-xl p-4" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
            <p className="text-xs font-bold uppercase tracking-wider mb-2.5 flex items-center gap-2"
               style={{ color: 'var(--text-tertiary)' }}>
              <span>🤖</span> Android — Chrome
            </p>
            <div className="space-y-1.5">
              {['Open Chirp in Chrome',
                'Tap the ⋮ menu (top right), then Add to Home Screen or Install App',
                'Tap Install to confirm'].map((step, i) => (
                <div key={i} className="flex items-start gap-2.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                  <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                        style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>
                    {i + 1}
                  </span>
                  {step}
                </div>
              ))}
            </div>
          </div>

          {/* Desktop */}
          <div className="rounded-xl p-4" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
            <p className="text-xs font-bold uppercase tracking-wider mb-2.5 flex items-center gap-2"
               style={{ color: 'var(--text-tertiary)' }}>
              <span>💻</span> Desktop — Chrome, Edge, Brave
            </p>
            <div className="space-y-1.5">
              {['Look for the install icon (computer with down-arrow) in the address bar and click it',
                'Or: open the ⋮ menu → Install Chirp',
                'Click Install — Chirp opens in its own window'].map((step, i) => (
                <div key={i} className="flex items-start gap-2.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                  <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                        style={{ background: 'rgba(34,211,238,.15)', color: '#22d3ee', marginTop: 1 }}>
                    {i + 1}
                  </span>
                  {step}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-start gap-2.5 p-3 rounded-xl mt-1"
             style={{ background: 'rgba(34,211,238,.06)', border: '1px solid rgba(34,211,238,.18)' }}>
          <Smartphone size={14} style={{ color: '#22d3ee', flexShrink: 0, marginTop: 1 }}/>
          <p className="text-xs" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
Installed, Chirp opens faster, runs full screen and sits on your home screen or taskbar.
</p>
        </div>
      </Section>
      )}

      {!isAdmin && (
        <div className="card p-4" style={{ border: '1px solid var(--border-subtle)' }}>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            You're signed in as a <strong style={{ color: 'var(--text-primary)' }}>viewer</strong>.
            You can change your notifications and the Appearance theme.
            Contact an administrator to change other settings.
          </p>
        </div>
      )}

      {isAdmin && <>

      <GroupHeader id="settings-site-group"/>
      <Section icon={MapPin} title="Location & Time Zone" id="settings-location">
        <div className="space-y-4">
          <Field label="Search location">
            <div className="relative">
              <input className="input w-full" placeholder="City, address, or place name…"
                     value={locationSearch} onChange={handleLocationInput}
                     autoComplete="off"/>
              {searchingLoc && (
                <RefreshCw size={14} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-gray-500"/>
              )}
              {locationResults.length > 0 && (
                <div className="absolute left-0 right-0 top-full mt-1 bg-surface-800 border border-surface-600 rounded-lg overflow-hidden shadow-2xl z-50">
                  {locationResults.map((loc, i) => (
                    <button key={i} onClick={() => selectLocation(loc)}
                            className="w-full text-left px-3 py-2.5 text-sm text-gray-300 hover:bg-surface-700 hover-text-primary border-b border-surface-700 last:border-0 transition-colors">
                      {loc.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Latitude">
              <input className="input" type="number" step="0.0001"
                     value={form.latitude}
                     onChange={e => setForm(f => ({ ...f, latitude: e.target.value }))}/>
            </Field>
            <Field label="Longitude">
              <input className="input" type="number" step="0.0001"
                     value={form.longitude}
                     onChange={e => setForm(f => ({ ...f, longitude: e.target.value }))}/>
            </Field>
          </div>
          {form.location_name && (
            <p className="text-xs text-chirp-500 flex items-center gap-1">
              <MapPin size={11}/> <span className="truncate">{form.location_name}</span>
            </p>
          )}
          <Field label="Timezone">
            <div className="space-y-1">
              <select className="input w-full" value={form.timezone}
                      onChange={e => setForm(f => ({ ...f, timezone: e.target.value }))}>
                {TIMEZONE_GROUPS.map(group => (
                  <optgroup key={group.label} label={group.label}>
                    {group.zones?.map(tz => (
                      <option key={tz} value={tz}>{tz.replace(/_/g,' ')}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <p className="text-xs text-gray-600">
                Auto-suggested from location when you search and save.
                Current: <span className="text-gray-400">{form.timezone}</span>
              </p>
            </div>
          </Field>
        </div>
      </Section>
      <Section icon={Globe} title="Web Address" id="settings-site-address">
        <ServerUrlField form={form} setForm={setForm}/>
      </Section>
      <Section icon={Eye} title="What Everyone Sees" id="settings-site-display">
        <div className="space-y-4">
          <Slider label="Min. Confidence to Display"
                  hint="Detections below this threshold are hidden in the UI. Takes effect immediately after saving."
                  min={0.01} max={1} step={0.01}
                  value={form.min_confidence_display}
                  onChange={set('min_confidence_display')}
                  format={v => `${(v*100).toFixed(0)}%`}/>
          <Field label="Show low-confidence detections">
            <label className="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" checked={form.show_low_confidence}
                     onChange={e => setForm(f => ({ ...f, show_low_confidence: e.target.checked }))}
                     className="w-4 h-4 accent-chirp-500"/>
              <span className="text-sm text-gray-300">Show detections below confidence threshold</span>
            </label>
          </Field>
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-200">Show deleted recording identifications</p>
              <p className="text-xs text-gray-500 mt-1">
Off (default): detections from deleted recordings are left out of dashboard totals, the life list, bird profiles and Likely Birds. On: they're counted.
</p>
            </div>
            <input type="checkbox"
              checked={form.show_deleted_detections ?? false}
              onChange={e => setForm(f => ({ ...f, show_deleted_detections: e.target.checked }))}
              className="w-4 h-4 accent-chirp-500 flex-shrink-0 mt-0.5"
            />
          </div>
          {form.show_deleted_detections && (
            <p className="text-xs text-yellow-400/80 bg-yellow-900/10 border border-yellow-700/30 rounded px-3 py-2 flex items-start gap-1.5">
              <span className="flex-shrink-0">ℹ️</span>
              <span>Deleted recordings are counted in all statistics and lists.</span>
            </p>
          )}
        </div>
      </Section>
      <DashboardSectionsSettings/>

      <GroupHeader id="settings-detection-group"/>
      <Section icon={Brain} title="Detection Model" id="settings-detection-model">
        <DetectionModel form={form} setForm={setForm}/>
      </Section>
      {/* Only with BirdNET 2.4 as the model. With v3, these still seed new
          stations' config (devices.py) and the 2.4 fallback, at their saved values. */}
      {form.detection_model === 'birdnet24' && (
      <Section icon={Brain} title="BirdNET 2.4 Settings" id="settings-detection">
        <div className="space-y-5">
          <p className="text-xs text-gray-500">
            The server identifies birds with these. New stations also start with them (each station's own
            are on the Devices page).
          </p>
          <Slider label="Minimum confidence"
                  hint="New recordings only. Lower finds more, with more false alarms. Default 5%."
                  min={0.01} max={0.5} step={0.01}
                  value={form.birdnet_min_confidence}
                  onChange={set('birdnet_min_confidence')}
                  format={v => `${(v*100).toFixed(0)}%`}/>
          <Slider label="Window Overlap"
                  hint="Overlap between consecutive 3 s analysis windows. Higher catches more calls at boundaries. Default 2.5."
                  min={0} max={2.9} step={0.1}
                  value={form.birdnet_overlap}
                  onChange={set('birdnet_overlap')}
                  format={v => v.toFixed(1)}/>
          <div className="flex justify-between text-xs text-gray-600 -mt-3 px-0.5">
            <span>No overlap</span><span>Max overlap</span>
          </div>
          <Slider label="Detection Sensitivity"
                  hint="Higher picks up fainter, more distant calls. Default 1.5."
                  min={0.5} max={1.5} step={0.05}
                  value={form.birdnet_sensitivity}
                  onChange={set('birdnet_sensitivity')}
                  format={v => v.toFixed(2)}/>
        </div>
      </Section>
      )}
      <Section icon={Moon} title="Night-Caller Thresholds" id="settings-detection-night-thresholds">
        <Suspense fallback={null}><NightThresholds/></Suspense>
      </Section>
      <Section icon={Moon} title="Night-Caller Near Misses" id="settings-detection-near-misses">
        <Suspense fallback={null}><NearMisses/></Suspense>
      </Section>
      <Section icon={Brain} title="Server-Side Analysis" id="settings-detection-server">
        <div className="space-y-5">

          {/* Re-analyze toggle */}
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-200">Re-analyze every upload</p>
              <p className="text-xs text-gray-500 mt-1">
The server runs BirdNET on every upload with your location, the time of year and the full sensitivity settings. It's usually more accurate than the station's quick pass. Turn off only if the server is short on CPU.
</p>
            </div>
            <input type="checkbox"
              checked={form.server_reanalyze_on_upload ?? true}
              onChange={e => setForm(f => ({ ...f, server_reanalyze_on_upload: e.target.checked }))}
              className="w-4 h-4 accent-chirp-500 flex-shrink-0 mt-0.5"
            />
          </div>

          {/* Auto-delete device detections — only shown when re-analyze is on */}
          {form.server_reanalyze_on_upload && (
            <div className="flex items-start justify-between gap-4 pl-4 border-l-2 border-surface-600">
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-300">Auto-delete device identifications</p>
                <p className="text-xs text-gray-500 mt-1">
After the server pass, remove the station's identifications and keep the server's. Turn off to show both.
</p>
              </div>
              <input type="checkbox"
                checked={form.server_reanalyze_delete_device ?? true}
                onChange={e => setForm(f => ({ ...f, server_reanalyze_delete_device: e.target.checked }))}
                className="w-4 h-4 accent-chirp-500 flex-shrink-0 mt-0.5"
              />
            </div>
          )}

          {/* Manual re-analyze button toggle */}
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-200">Allow manual re-analyze</p>
              <p className="text-xs text-gray-500 mt-1">
Shows a Re-analyze button on each recording so anyone can run BirdNET (or bat analysis) again, for example on an empty recording or after changing a threshold. The automatic pass on upload runs either way. Turn off to limit server load.
</p>
            </div>
            <input type="checkbox"
              checked={form.allow_manual_reanalyze ?? true}
              onChange={e => setForm(f => ({ ...f, allow_manual_reanalyze: e.target.checked }))}
              className="w-4 h-4 accent-chirp-500 flex-shrink-0 mt-0.5"
            />
          </div>

          {/* Rumble Removal mode */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-200">Playback: Enhance</p>
              <p className="text-xs text-gray-500 mt-1">
Recordings play through one Enhance control: Original, Enhanced (cuts low rumble from traffic, wind and HVAC, and reduces steady background noise) or AI (Settings → AI Features). This sets where bird recordings start. <strong>Enhanced</strong>: open in Enhanced. <strong>Original</strong>: open in Original. <strong>No low cut</strong>: Enhanced only reduces noise, without cutting low sound.
</p>
              <div className="flex gap-2 mt-2">
                {[
                  { key: 'auto', label: 'Enhanced' },
                  { key: 'auto_off', label: 'Original' },
                  { key: 'disabled', label: 'No low cut' },
                ].map(opt => (
                  <button key={opt.key} type="button"
                    onClick={() => setForm(f => ({ ...f, rumble_removal_mode: opt.key }))}
                    className={`text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
                      (form.rumble_removal_mode || 'auto') === opt.key
                        ? 'border-chirp-500 bg-chirp-900/30 text-chirp-300'
                        : 'border-surface-600 bg-surface-800 text-gray-400 hover:border-surface-500'
                    }`}>
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Detection color palette picker */}
          <div>
            <p className="text-sm font-medium text-gray-200">Detection colors</p>
            <p className="text-xs text-gray-500 mt-1 mb-3">
              Colors for each species in a recording's detection list, waveform and spectrogram.
            </p>
            <div role="radiogroup" aria-label="Detection colors" className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {Object.entries(PALETTES).map(([key, palette]) => {
                const selected = (form.detection_color_palette || DEFAULT_PALETTE) === key
                return (
                  <button
                    key={key}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setForm(f => ({ ...f, detection_color_palette: key }))}
                    className={`text-left rounded-lg border px-3 py-2.5 transition-colors flex flex-col gap-2 min-w-0 ${
                      selected
                        ? 'border-chirp-500 bg-chirp-900/20'
                        : 'border-surface-600 bg-surface-800 hover:border-surface-500'
                    }`}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-gray-200">{palette.label}</span>
                      {selected && <Check size={14} className="text-chirp-400 flex-shrink-0"/>}
                    </span>
                    {/* One strip, any number of colors: always fits the card. */}
                    <span className="flex h-3 rounded-full overflow-hidden" aria-hidden="true">
                      {palette.colors.map((c, i) => <span key={i} className="flex-1" style={{ background: c }}/>)}
                    </span>
                    <span className="text-xs text-gray-500">{palette.description}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {!(form.latitude) && (
            <div className="text-xs text-yellow-400/80 bg-yellow-900/10 border border-yellow-700/30 rounded px-3 py-2 flex items-start gap-1.5">
              <span className="flex-shrink-0">⚠️</span>
              <span>
                No server location set — species filtering by region is disabled.
                Set your location in <strong>Location</strong> above to restrict detections
                to birds likely near you.
              </span>
            </div>
          )}
        </div>
      </Section>
      <Section icon={Sliders} title="Recording Device Defaults" id="settings-detection-devices">
        <p className="text-xs text-gray-500 mb-4">
          These values are pushed to all paired Chirp devices as their default managed config.
          Per-device overrides can still be set from the <a href="/devices" className="text-chirp-400 hover:underline">Devices</a> page.
        </p>
        <div className="space-y-5">
          <Field label="Min. Gap Between Recordings"
                 hint="Seconds to wait after a recording ends before another can start, so one call isn't recorded twice.">
            <div className="flex items-center gap-3">
              <input type="number" min={0} max={3600} step={1}
                className="input w-28"
                value={form.recording_min_gap_seconds ?? 10}
                onChange={e => setForm(f => ({ ...f, recording_min_gap_seconds: parseInt(e.target.value, 10)||0 }))}
              />
              <span className="text-xs text-gray-500">seconds (0 = no cooldown)</span>
            </div>
          </Field>

          <Field label="Max Recording Length"
                 hint="Longest a recording can be. The station stops at this length even if the bird is still calling.">
            <div className="flex items-center gap-3">
              <input type="number" min={5} max={3600} step={5}
                className="input w-28"
                value={form.recording_max_duration_sec ?? 30}
                onChange={e => setForm(f => ({ ...f, recording_max_duration_sec: parseInt(e.target.value, 10)||30 }))}
              />
              <span className="text-xs text-gray-500">seconds</span>
            </div>
          </Field>

          <Field label="Max Recordings Per Hour"
                 hint="Most recordings the station makes in any 60 minutes. 0 = no limit.">
            <div className="flex items-center gap-3">
              <input type="number" min={0} max={3600} step={1}
                className="input w-28"
                value={form.recording_max_per_hour ?? 0}
                onChange={e => setForm(f => ({ ...f, recording_max_per_hour: parseInt(e.target.value, 10)||0 }))}
              />
              <span className="text-xs text-gray-500">recordings / hour (0 = unlimited)</span>
            </div>
          </Field>
        </div>
      </Section>

      <GroupHeader id="settings-bats-group"/>
      <Section icon={Moon} title="Bat Echolocation Detection" id="settings-bats">
        <div className="space-y-3">
        <p className="text-xs text-gray-500">
          Finds the ultrasonic pulse trains of bat echolocation on a station's ultrasonic mic, saves a
          slowed-down clip you can hear, and can try to name the species (off by default).
        </p>
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm text-gray-300">Enable bat echolocation detection</p>
          <input
                type="checkbox"
                checked={form.bat_detection_enabled ?? false}
                onChange={e => setForm(f => ({ ...f, bat_detection_enabled: e.target.checked }))}
                className="w-4 h-4 accent-chirp-500 flex-shrink-0"
              />
            </div>
            <BatMicInfoBox/>
            {form.bat_detection_enabled && (
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest text-gray-500 mb-1.5">
                  Ultrasonic Mic Device Name (optional)
                </label>
                <input
                  className="input text-sm w-full"
                  placeholder="e.g. UltraMic, M500 — leave blank to auto-pick the highest-rate input device"
                  value={form.bat_detection_device_name || ''}
                  onChange={e => setForm(f => ({ ...f, bat_detection_device_name: e.target.value }))}
                />
                <p className="text-xs text-gray-500 mt-1.5">
Matches part of the mic name the Pi reports. Leave blank to use the input with the highest sample rate.
</p>
              </div>
            )}
            {form.bat_detection_enabled && (
              <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--border-default)' }}>
                <div className="px-4 py-3" style={{ background: 'var(--bg-raised)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Noise rejection &amp; scheduling</p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
Keeps machine noise (lawnmowers, motors) from counting as bats. Sent to the station automatically.
</p>
                </div>
                <div className="p-4 space-y-4">
                  {/* Time-of-day gate */}
                  <div>
                    <p className="text-xs font-semibold mb-2" style={{ color: '#fbbf24' }}>
                      Active hours (local time)
                    </p>
                    <p className="text-xs mb-3" style={{ color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
Only record bats between these times. Bats fly from about sunset to sunrise, and skipping daytime cuts most false alarms from equipment. 00:00–23:59 records all day.
</p>
                    <div className="flex items-center gap-3 flex-wrap">
                      <div className="flex items-center gap-2">
                        <label className="text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>Start</label>
                        <input type="time" className="input text-sm w-32"
                          value={form.bat_active_hours_start ?? '20:00'}
                          onChange={e => setForm(f => ({ ...f, bat_active_hours_start: e.target.value }))}/>
                      </div>
                      <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>→</span>
                      <div className="flex items-center gap-2">
                        <label className="text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>End</label>
                        <input type="time" className="input text-sm w-32"
                          value={form.bat_active_hours_end ?? '06:00'}
                          onChange={e => setForm(f => ({ ...f, bat_active_hours_end: e.target.value }))}/>
                      </div>
                      <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                        {(form.bat_active_hours_start && form.bat_active_hours_end)
                          ? `Active ${form.bat_active_hours_start} – ${form.bat_active_hours_end} (wraps midnight)`
                          : 'No gating'}
                      </p>
                    </div>
                  </div>
                  {/* FM sweep filter */}
                  <div>
                    <p className="text-xs font-semibold mb-1" style={{ color: '#4ade80' }}>
                      FM sweep filter — min swept fraction
                    </p>
                    <p className="text-xs mb-2" style={{ color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
Bat calls sweep in pitch during each pulse; machine noise doesn't. This is the share of pulses that must sweep for an event to count. 0 turns it off; 0.3 is recommended.
</p>
                    <div className="flex items-center gap-3">
                      <input type="number" min={0} max={1} step={0.05} className="input w-24 text-sm"
                        value={form.bat_min_swept_fraction ?? 0.3}
                        onChange={e => setForm(f => ({ ...f, bat_min_swept_fraction: parseFloat(e.target.value) || 0 }))}/>
                      <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                        (0–1, e.g. 0.3 = 30% of pulses must sweep)
                      </span>
                    </div>
                  </div>
                  {/* Max pulse rate */}
                  <div>
                    <p className="text-xs font-semibold mb-1" style={{ color: '#a78bfa' }}>
                      Max pulse rate (pulses/sec)
                    </p>
                    <p className="text-xs mb-2" style={{ color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
Bats call 5–30 times a second; motors and fans look much faster. Events above this rate are dropped.
</p>
                    <div className="flex items-center gap-3">
                      <input type="number" min={10} max={300} step={5} className="input w-24 text-sm"
                        value={form.bat_max_pulse_rate ?? 60}
                        onChange={e => setForm(f => ({ ...f, bat_max_pulse_rate: parseInt(e.target.value) || 60 }))}/>
                      <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>pulses/sec (default 60)</span>
                    </div>
                  </div>
                  <div className="p-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="text-xs font-semibold mb-1" style={{ color: '#a78bfa' }}>
                          Discard likely electrical/mechanical interference
                        </p>
                        <p className="text-xs" style={{ color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
Off (default): recordings with a very regular timing pattern, usually electrical noise, are saved and flagged. On: they're dropped before saving and can't be recovered. A bat pass shouldn't trip this, but leave it off unless flagged noise is cluttering your recordings.
</p>
                      </div>
                      <input type="checkbox"
                        checked={form.bat_discard_likely_interference ?? false}
                        onChange={e => setForm(f => ({ ...f, bat_discard_likely_interference: e.target.checked }))}
                        className="w-4 h-4 accent-chirp-500 flex-shrink-0"/>
                    </div>
                  </div>
                  <div className="p-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="text-xs font-semibold mb-1" style={{ color: '#a78bfa' }}>
                          Auto-generate wobble-removed audio
                        </p>
                        <p className="text-xs" style={{ color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
Off by default. On: each new bat recording also gets a version with the AudioMoth/fan whine reduced, made in the background so it plays instantly. You still pick it per recording, and it works with Enhanced audio. Expect about 11 dB less whine; a call that crosses the whine's pitch can be clipped.
</p>
                      </div>
                      <input type="checkbox"
                        checked={form.bat_auto_remove_wobble ?? false}
                        onChange={e => setForm(f => ({ ...f, bat_auto_remove_wobble: e.target.checked }))}
                        className="w-4 h-4 accent-chirp-500 flex-shrink-0"/>
                    </div>
                  </div>
                </div>
              </div>
            )}
            {form.bat_detection_enabled && (
              <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--border-default)' }}>
                <div className="px-4 py-3" style={{ background: 'var(--bg-raised)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                    Identify bat species
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
Tries to name the bat species (Little brown bat, Big brown bat…) with a classifier trained on NABat data for the Northeast. It can be confidently wrong: in testing it named a species at 97% on silence. So a species is only shown, including in the Field Guide, Life List and iNaturalist submissions, when it clears the threshold below and beats the classifier's noise, cricket and silence scores. Otherwise the recording stays "Bat" and the guess is saved but not shown.
</p>
                </div>
                <div className="p-4 space-y-4">
                  <div className="flex items-center justify-between gap-4">
                    <label className="flex items-center gap-3 cursor-pointer flex-1">
                      <input type="checkbox" checked={form.bat_species_id_enabled ?? false}
                             onChange={e => setForm(f => ({ ...f, bat_species_id_enabled: e.target.checked }))}
                             className="w-4 h-4 accent-chirp-500"/>
                      <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>Enable species classification</span>
                    </label>
                  </div>
                  {form.bat_species_id_enabled && (
                    <Slider label="Minimum confidence to assert a species"
                            hint="Below this the recording stays “Bat”; the guess is saved but not shown."
                            min={0.5} max={0.99} step={0.01}
                            value={form.bat_species_id_min_confidence ?? 0.75}
                            onChange={set('bat_species_id_min_confidence')}
                            format={v => `${(v*100).toFixed(0)}%`}/>
                  )}
                </div>
              </div>
            )}
        </div>
      </Section>

      <GroupHeader id="settings-notif-group"/>
      <Section icon={Calendar} title="Daily Digest" id="settings-digest">
        <div className="space-y-4">
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Each person turns the digest push and email on in My Notifications. A time from noon on covers
            that day so far; an earlier time covers the day before. The digest page keeps updating until midnight.
            Times are in {form.timezone || 'the site time zone'}.
          </p>
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Push notification</p>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>iPhone app and browser push</p>
            </div>
            <DigestHourSelect value={form.digest_push_hour ?? 21} onChange={h => setForm(f => ({ ...f, digest_push_hour: h }))}/>
          </div>
          <div className="flex items-center justify-between gap-3 pt-3 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Email</p>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Needs the email server below</p>
            </div>
            <DigestHourSelect value={form.digest_email_hour ?? 21} onChange={h => setForm(f => ({ ...f, digest_email_hour: h }))}/>
          </div>
          <div className="flex items-center justify-between gap-3 pt-3 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              Emails the latest day's digest to the admin address.
            </p>
            <TestSendButton label="📋 Test Digest" run={() => api.settings.sendTestDigestEmail()}/>
          </div>
        </div>
      </Section>
      <Section icon={Radio} title="Station Offline Alerts" id="settings-station-offline">
        <div className="space-y-3">
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Admins who turn on Station offline in My Notifications are told when a station stops reporting for
            this long, and again when it's back.
          </p>
          <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-primary)' }}>
            Alert after
            <input type="number" min={5} max={1440} aria-label="Minutes offline before alerting"
                   value={form.device_offline_minutes ?? 15}
                   onChange={e => setForm(f => ({ ...f, device_offline_minutes: e.target.value === '' ? '' : parseInt(e.target.value, 10) }))}
                   onBlur={e => setForm(f => ({ ...f, device_offline_minutes: Math.min(1440, Math.max(5, parseInt(e.target.value, 10) || 15)) }))}
                   className="input text-sm py-1 text-center" style={{ width: 72 }}/>
            minutes offline
          </label>
        </div>
      </Section>
      <Section icon={Mail} title="Email (SMTP)" id="settings-notif-email">
        <div className="space-y-4">
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Outgoing email for registration alerts, new-bird emails and the daily digest.
            Uses SMTP — works with Gmail, SendGrid, Mailgun, or any SMTP server.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="SMTP Host" hint="e.g. smtp.gmail.com">
              <input className="input" placeholder="smtp.example.com"
                     value={form.smtp_host ?? ''} onChange={e => setForm(f => ({...f, smtp_host: e.target.value}))}/>
            </Field>
            <Field label="SMTP Port" hint="587 = STARTTLS 465 = SSL 25 = plain">
              <input className="input" type="number" placeholder="587"
                     value={form.smtp_port ?? 587} onChange={e => setForm(f => ({...f, smtp_port: parseInt(e.target.value, 10)||587}))}/>
            </Field>
            <Field label="Username / Email">
              <input className="input" placeholder="you@example.com"
                     value={form.smtp_username ?? ''} onChange={e => setForm(f => ({...f, smtp_username: e.target.value}))}/>
            </Field>
            <Field label="Password / App password">
              <input className="input" type="password"
                     placeholder={form.smtp_password ? 'Leave blank to keep current password' : '••••••••••••'}
                     value={form.smtp_password ?? ''} onChange={e => setForm(f => ({...f, smtp_password: e.target.value}))}/>
            </Field>
            <Field label="From address" hint="Shown in From: header">
              <input className="input" placeholder="chirp@yourdomain.com"
                     value={form.smtp_from_address ?? ''} onChange={e => setForm(f => ({...f, smtp_from_address: e.target.value}))}/>
            </Field>
            <Field label="Admin email" hint="Receives registration alerts">
              <input className="input" placeholder="admin@yourdomain.com"
                     value={form.admin_email ?? ''} onChange={e => setForm(f => ({...f, admin_email: e.target.value}))}/>
            </Field>
          </div>
          <div className="flex items-center justify-between py-2">
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input type="checkbox" className="toggle"
                     checked={form.smtp_use_tls ?? true}
                     onChange={e => setForm(f => ({...f, smtp_use_tls: e.target.checked}))}/>
              <div>
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Use STARTTLS</p>
                <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>On for port 587. Port 465 always uses SSL; off sends plain SMTP (port 25)</p>
              </div>
            </label>
          </div>
          <div className="flex items-center justify-between py-2 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>New-species emails</p>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Email people who turned on new-bird emails when a species is heard for the first time</p>
            </div>
            <input type="checkbox" className="toggle"
                   checked={form.notifications_enabled ?? false}
                   onChange={e => setForm(f => ({...f, notifications_enabled: e.target.checked}))}/>
          </div>
          <div className="flex items-center justify-between py-2 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Notify admin on new registration</p>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Email the admin address when a new user registers</p>
            </div>
            <input type="checkbox" className="toggle"
                   checked={form.notify_on_register ?? true}
                   onChange={e => setForm(f => ({...f, notify_on_register: e.target.checked}))}/>
          </div>

          {/* Save to .env button */}
          <div className="flex items-center justify-between pt-3 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Persist across reinstalls</p>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                Saves these settings to <code style={{ fontFamily: 'monospace', color: 'var(--accent-400)' }}>/app/data/.env</code> on
                the server — they'll be reloaded automatically after every container rebuild.
              </p>
              {saveEnvStatus && saveEnvStatus !== 'saving' && (
                <p className="text-xs mt-1 font-medium"
                   style={{ color: saveEnvStatus === 'ok' ? 'var(--accent-400)' : 'var(--pastel-red)' }}>
                  {saveEnvStatus === 'ok' ? '✓ Saved to /app/data/.env' : saveEnvStatus}
                </p>
              )}
            </div>
            <button onClick={handleSaveEnv} disabled={saveEnvStatus === 'saving'}
                    className="btn-secondary flex-shrink-0"
                    style={{ fontSize: 13 }}>
              {saveEnvStatus === 'saving'
                ? <><svg className="animate-spin" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> Saving…</>
                : <><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v14a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> Save to .env</>
              }
            </button>
          </div>

          {/* Test email button */}
          <div className="flex items-center justify-between pt-3 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Test configuration</p>
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                Sends test emails to the admin address. Save settings first.
              </p>
            </div>
            <div className="flex flex-col gap-2 flex-shrink-0">
              <TestSendButton label="✉ Send Test" run={() => api.settings.sendTestEmail()}/>
              <TestSendButton label="🐦 Test New Bird" run={() => api.settings.sendTestNewBirdEmail()}/>
            </div>
          </div>
        </div>
      </Section>

      <Section icon={Smartphone} title="iPhone Push" id="settings-notif-apns">
        <div className="space-y-4">
          {(() => {
            const route = settings?.push_route
            const [color, text] =
              route === 'site' ? ['var(--pastel-green)', "Sending with this site's own APNs key (below)."]
              : route === 'server' ? ['var(--pastel-green)', "Sending with this server's key. Nothing to set up."]
              : route === 'relay' ? ['var(--pastel-green)', `Sending through the push relay at ${settings?.push_relay_url || 'ourchirp.com'}.`]
              : ['var(--pastel-amber)', 'Not set up. The iPhone app gets no notifications from this server until you add a relay token or your own key.']
            return <p className="text-xs" style={{ color }}>{text}</p>
          })()}
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Apple only delivers Chirp app notifications signed with the app's key. A self-hosted server sends
            them through a relay: request a token at{' '}
            <a href="https://ourchirp.com/about#start" target="_blank" rel="noreferrer" style={{ color: 'var(--accent-400)' }}>ourchirp.com/about</a>{' '}
            and paste it here. Browser and home-screen (Web Push) notifications need no setup.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Relay token" hint="From the approval email; starts with chirprelay_">
              <input className="input font-mono text-xs" placeholder="chirprelay_…" autoComplete="off"
                     value={form.push_relay_token ?? ''} onChange={e => setForm(f => ({...f, push_relay_token: e.target.value}))}/>
            </Field>
            <Field label="Relay address" hint="Leave blank for ourchirp.com">
              <input className="input font-mono text-xs" placeholder="https://ourchirp.com"
                     value={form.push_relay_url ?? ''} onChange={e => setForm(f => ({...f, push_relay_url: e.target.value}))}/>
            </Field>
          </div>
          <details className="group">
            <summary className="text-sm cursor-pointer" style={{ color: 'var(--text-primary)' }}>Use your own APNs key</summary>
            <div className="space-y-4 pt-3">
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Only for your own build of the iPhone app (your own bundle ID). Requires a token-based .p8 auth key from{' '}
            <a href="https://developer.apple.com/account/resources/authkeys/list" target="_blank" rel="noreferrer"
               style={{ color: 'var(--accent-400)' }}>Apple Developer → Certificates, IDs &amp; Profiles → Keys</a>{' '}
            with "Apple Push Notifications service" checked. A key here is used instead of the relay.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Team ID" hint="Apple Developer account, top-right of the membership page">
              <input className="input font-mono text-xs" placeholder="ABCDE12345"
                     value={form.apns_team_id ?? ''} onChange={e => setForm(f => ({...f, apns_team_id: e.target.value}))}/>
            </Field>
            <Field label="Key ID" hint="Shown when the .p8 key is created — not recoverable afterward, save it then">
              <input className="input font-mono text-xs" placeholder="XYZW98765"
                     value={form.apns_key_id ?? ''} onChange={e => setForm(f => ({...f, apns_key_id: e.target.value}))}/>
            </Field>
            <Field label="Bundle ID" hint="Must exactly match capacitor.config.json's appId">
              <input className="input font-mono text-xs" placeholder="com.joshuasalvimd.chirp"
                     value={form.apns_bundle_id ?? ''} onChange={e => setForm(f => ({...f, apns_bundle_id: e.target.value}))}/>
            </Field>
            <Field label="Environment">
              <select className="input text-xs"
                      value={form.apns_production === false ? 'sandbox' : 'production'}
                      onChange={e => setForm(f => ({...f, apns_production: e.target.value === 'production'}))}>
                <option value="production">Production (App Store / TestFlight builds)</option>
                <option value="sandbox">Sandbox (Xcode debug builds only)</option>
              </select>
            </Field>
          </div>
          <Field label="Auth Key (.p8 file content)" hint="The full contents of the downloaded .p8 file, including the BEGIN/END lines">
            <textarea className="input font-mono text-xs" rows={4}
                      placeholder={form.apns_auth_key ? 'Leave blank to keep the current key' : '-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----'}
                      value={form.apns_auth_key ?? ''} onChange={e => setForm(f => ({...f, apns_auth_key: e.target.value}))}/>
          </Field>
            </div>
          </details>
        </div>
      </Section>

      <GroupHeader id="settings-integrations-group"/>
      <Section icon={Key} title="eBird" id="settings-integrations-ebird">
        <ApiKeysPanel form={form} setForm={setForm} settings={settings} only="ebird"/>
      </Section>
      <HaikuboxSection form={form} setForm={setForm} settings={settings}/>
      <BirdBuddySection form={form} setForm={setForm} settings={settings}/>
      <BirdWeatherSection form={form} setForm={setForm} settings={settings}/>
      <InatSection form={form} setForm={setForm} settings={settings}/>

      <GroupHeader id="settings-ai-group"/>
      <Section icon={Sparkles} title="AI Features" id="settings-ai">
        <p className="text-xs text-gray-500 mb-4">
          Daily and Weekly Journal, Bird Profile summaries and AI Second Opinion. Pick Anthropic, OpenAI,
          Gemini or Ollama for each, or leave it off; a feature without a provider stays hidden.
        </p>
        <AiSettingsPanel form={form} setForm={setForm} settings={settings}/>

        {/* AI Enhance — a local neural-network model, not
            a cloud AI feature like the ones above, so no provider/API
            key choice: it either runs on this server or it doesn't. */}
        <div className="mt-5 pt-5 border-t border-surface-700">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-200">AI Enhance</p>
              <p className="text-xs text-gray-500 mt-1 max-w-2xl">
Neural denoising for bird recordings and clips (biodenoising, Earth Species Project): isolates the call and lowers the background. An alternative to Enhanced and Rumble removed. Runs on this server with no API key, but needs <code>torch</code>/<code>torchaudio</code> (several hundred MB, not installed by default) and downloads a 75 MB model on first use. It works at 16 kHz, so sound above 8 kHz is lost; for high-pitched birds use Enhanced instead.
</p>
            </div>
            <input type="checkbox"
              checked={form.ai_enhance_enabled ?? false}
              onChange={e => setForm(f => ({ ...f, ai_enhance_enabled: e.target.checked }))}
              className="w-4 h-4 accent-chirp-500 flex-shrink-0 mt-0.5"
            />
          </div>
          {(form.ai_enhance_enabled ?? false) && (
            <div className="flex items-center justify-between gap-4 mt-3 pt-3 border-t border-surface-700">
              <div>
                <p className="text-xs font-medium text-gray-300">Open bird recordings in AI</p>
                <p className="text-xs text-gray-500 mt-0.5">
Recordings still have the Original and Enhanced choices; this only makes AI the starting point.
</p>
              </div>
              <input type="checkbox"
                checked={form.ai_enhance_auto_apply ?? false}
                onChange={e => setForm(f => ({ ...f, ai_enhance_auto_apply: e.target.checked }))}
                className="w-4 h-4 accent-chirp-500 flex-shrink-0"
              />
            </div>
          )}
        </div>
      </Section>

      <GroupHeader id="settings-storage-group"/>
      <Section icon={HardDrive} title="Storage Management" id="settings-storage">
        {/* Live usage bar */}
        {storageStatus && (
          <div className="mb-5 p-3 bg-surface-800 rounded-lg border border-surface-700 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-400 font-medium">Recordings directory usage</span>
              <span className={`font-mono font-semibold ${
                storageStatus.limit_pct > 90 ? 'text-red-400' :
                storageStatus.limit_pct > 70 ? 'text-yellow-400' : 'text-chirp-400'
              }`}>
                {(storageStatus.used_gb ?? 0).toFixed(2)} GB
                {storageStatus.limit_gb > 0 && ` / ${storageStatus.limit_gb} GB (${storageStatus.limit_pct}%)`}
              </span>
            </div>
            {storageStatus.limit_gb > 0 && (
              <div className="w-full bg-surface-700 rounded-full h-1.5">
                <div className={`h-1.5 rounded-full transition-all ${
                  storageStatus.limit_pct > 90 ? 'bg-red-500' :
                  storageStatus.limit_pct > 70 ? 'bg-yellow-500' : 'bg-chirp-500'
                }`} style={{ width: `${Math.min(100, storageStatus.limit_pct)}%` }}/>
              </div>
            )}
          </div>
        )}

        {/* Storage details — full directory breakdown + recordings accounting +
            orphan detection. Collapsed by default (this section has a lot of
            numbers most people only need occasionally) but the underlying
            fetch (api.recordings.storageStatus(), in the mount effect above)
            always runs regardless of whether this is expanded — collapsing
            only hides the display, it never skips or delays the data. */}
        {(storageStatus?.directories || storageStatus?.recordings_accounting) && (
          <div className="mb-5 rounded-lg border border-surface-700 overflow-hidden">
            <button onClick={() => setStorageDetailsOpen(o => !o)}
                    className="w-full flex items-center justify-between px-3 py-2.5 bg-surface-800 hover:bg-surface-700/50 transition-colors">
              <span className="text-xs text-gray-400 font-medium flex items-center gap-1.5">
                <Database size={12}/> Storage details
                {storageStatus?.total_all_gb != null && (
                  <span className="font-mono text-gray-500">— {storageStatus.total_all_gb.toFixed(2)} GB across all directories</span>
                )}
              </span>
              <ChevronDown size={14} className="text-gray-500 transition-transform"
                           style={{ transform: storageDetailsOpen ? 'rotate(180deg)' : 'none' }}/>
            </button>
            {storageDetailsOpen && (
              <div className="p-3 bg-surface-800 border-t border-surface-700 space-y-3">

        {storageStatus?.directories && (
          <div className="p-3 bg-surface-900/40 rounded-lg border border-surface-700">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-400 font-medium flex items-center gap-1.5">
                <Database size={12}/> All directories
              </span>
              <span className="text-xs font-mono font-semibold text-gray-300">
                {(storageStatus.total_all_gb ?? 0).toFixed(2)} GB total
              </span>
            </div>
            <div className="space-y-1">
              {Object.entries(storageStatus.directories).map(([key, d]) => (
                <div key={key} className="flex items-center justify-between text-xs py-1 px-2 rounded hover:bg-surface-700/50">
                  <span className="text-gray-400 capitalize">{key.replace('_', ' ')}</span>
                  <span className="font-mono text-gray-300">
                    {d.exists === false
                      ? <span className="text-gray-600">not configured</span>
                      : d.error
                      ? <span className="text-red-400">error</span>
                      : `${d.size_human} · ${(d.file_count ?? 0).toLocaleString()} files`}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {storageStatus?.recordings_accounting && (() => {
          const acc = storageStatus.recordings_accounting
          const recOrphans = storageStatus.orphans?.recordings
          const clipOrphans = storageStatus.orphans?.clips
          const enhOrphans = storageStatus.orphans?.enhanced
          const specOrphans = storageStatus.orphans?.spectrograms
          return (
            <div className="mb-5 p-3 bg-surface-800 rounded-lg border border-surface-700 space-y-3">
              <div className="flex items-center gap-1.5 text-xs text-gray-400 font-medium">
                <AlertCircle size={12}/> File count vs. recording count
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                <span className="text-gray-500">Active recordings</span>
                <span className="font-mono text-gray-300 text-right">{acc.db_rows_active.toLocaleString()}</span>
                <span className="text-gray-500">Soft-deleted (in DB, hidden from lists)</span>
                <span className="font-mono text-gray-300 text-right">{acc.db_rows_soft_deleted.toLocaleString()}</span>
                <span className="text-gray-500">— of those, still have a file on disk</span>
                <span className="font-mono text-yellow-400 text-right">
                  {acc.soft_deleted_with_file_on_disk.toLocaleString()}
                  {acc.soft_deleted_reclaimable_bytes > 0 && ` (${acc.soft_deleted_reclaimable_human} reclaimable)`}
                </span>
              </div>
              {acc.soft_deleted_with_file_on_disk > 0 && (
                <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
Recordings deleted without "also delete files", or before auto-purge was set up. Free the space with "Clean up deleted" below or an auto-delete age.
</p>
              )}

              {/* True orphans — files with no DB row at all */}
              {(recOrphans?.orphaned_count > 0 || clipOrphans?.orphaned_count > 0 || enhOrphans?.orphaned_count > 0 || specOrphans?.orphaned_count > 0) && (
                <div className="pt-2 border-t space-y-2" style={{ borderColor: 'var(--border-subtle)' }}>
                  <p className="text-xs text-gray-500">
Files no recording needs: leftovers with <em>no matching recording</em> (failed cleanups, interrupted compressions, old migrations) and spectrograms cached for old settings, which are redrawn when opened. Safe to remove:
</p>
                  {recOrphans?.orphaned_count > 0 && (
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-gray-400">Recordings dir: {recOrphans.orphaned_count} orphaned file(s) ({recOrphans.orphaned_human})</span>
                      <button onClick={() => handlePurgeOrphans('recordings', false)} disabled={orphanBusy}
                              className="text-xs px-2 py-1 rounded-md font-medium"
                              style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--accent-400)' }}>
                        Review & clean up
                      </button>
                    </div>
                  )}
                  {clipOrphans?.orphaned_count > 0 && (
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-gray-400">Clips dir: {clipOrphans.orphaned_count} orphaned file(s) ({clipOrphans.orphaned_human})</span>
                      <button onClick={() => handlePurgeOrphans('clips', false)} disabled={orphanBusy}
                              className="text-xs px-2 py-1 rounded-md font-medium"
                              style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--accent-400)' }}>
                        Review & clean up
                      </button>
                    </div>
                  )}
                  {enhOrphans?.orphaned_count > 0 && (
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-gray-400">
                        Enhanced cache: {enhOrphans.orphaned_count} file(s) ({enhOrphans.orphaned_human})
                        {enhOrphans.stale_version_count > 0 && ` · ${enhOrphans.stale_version_count} from older versions`}
                      </span>
                      <button onClick={() => handlePurgeOrphans('enhanced', false)} disabled={orphanBusy}
                              className="text-xs px-2 py-1 rounded-md font-medium"
                              style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--accent-400)' }}>
                        Review & clean up
                      </button>
                    </div>
                  )}
                  {specOrphans?.orphaned_count > 0 && (
                    <div className="flex items-center justify-between text-xs gap-2">
                      <span className="text-gray-400"
                            title="Images for recordings that no longer exist, and, for recordings that still have audio, images cached for an old display threshold, colour palette or thumbnail size. They regenerate when opened. Archived recordings keep every image.">
                        Spectrogram cache: {specOrphans.orphaned_count.toLocaleString()} file(s) ({specOrphans.orphaned_human})
                        {specOrphans.old_variant_count > 0 && ` · ${specOrphans.old_variant_count.toLocaleString()} for old thresholds`}
                      </span>
                      <button onClick={() => handlePurgeOrphans('spectrograms', false)} disabled={orphanBusy}
                              className="text-xs px-2 py-1 rounded-md font-medium shrink-0"
                              style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--accent-400)' }}>
                        Review & clean up
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Confirm dialog — shown after "Review & clean up" fetches the dry-run preview */}
              {orphanTarget && orphanResult?.target === orphanTarget && orphanResult.dry_run && (
                <div className="mt-2 p-3 rounded-lg space-y-2" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-focus)' }}>
                  <p className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                    Delete {orphanResult.orphaned_count} orphaned {orphanTarget} file(s) ({orphanResult.orphaned_human})?
                  </p>
                  {orphanResult.orphaned_sample?.length > 0 && (
                    <div className="max-h-24 overflow-y-auto text-xs font-mono text-gray-500 space-y-0.5">
                      {orphanResult.orphaned_sample.slice(0, 10).map((f, i) => (
                        <div key={i}>{f.name} — {f.size_human}</div>
                      ))}
                      {orphanResult.orphaned_count > 10 && <div>… and {orphanResult.orphaned_count - 10} more</div>}
                    </div>
                  )}
                  <div className="flex gap-2 pt-1">
                    <button onClick={() => handlePurgeOrphans(orphanTarget, true)} disabled={orphanBusy}
                            className="text-xs px-3 py-1.5 rounded-md font-medium bg-red-600/20 border border-red-600/40 text-red-300 hover:bg-red-600/30">
                      {orphanBusy ? 'Deleting…' : 'Delete these files'}
                    </button>
                    <button onClick={() => { setOrphanTarget(null); setOrphanResult(null) }} disabled={orphanBusy}
                            className="text-xs px-3 py-1.5 rounded-md font-medium"
                            style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}
              {orphanResult && !orphanResult.dry_run && orphanResult.target && !orphanResult.error && (
                <div className="mt-2 p-2 rounded-lg text-xs" style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
                  Deleted {orphanResult.deleted_count} file(s), freed {orphanResult.deleted_human}
                  {orphanResult.errors > 0 && ` (${orphanResult.errors} error(s) — see server logs)`}.
                </div>
              )}
              {orphanResult?.error && (
                <div className="mt-2 p-2 rounded-lg text-xs text-red-400" style={{ background: 'var(--bg-raised)' }}>
                  {orphanResult.error}
                </div>
              )}
            </div>
          )
        })()}

              </div>
            )}
          </div>
        )}

        <div className="space-y-6">
          {/* Compression */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-200">Compress recordings on upload</p>
                <p className="text-xs text-gray-500 mt-0.5">
Converts WAV uploads to FLAC (lossless) or Opus (smaller, lossy) and removes the WAV. Spectrograms and playback work the same.
</p>
              </div>
              <input type="checkbox"
                checked={form.storage_compress_on_upload ?? true}
                onChange={e => setForm(f => ({ ...f, storage_compress_on_upload: e.target.checked }))}
                className="w-4 h-4 accent-chirp-500 flex-shrink-0 ml-4"
              />
            </div>
            {form.storage_compress_on_upload && (
              <Field label="Compression quality">
                <div className="flex gap-2 flex-wrap">
                  {[
                    { v:'lossless', label:'Lossless (FLAC)', hint:'~50% size', color:'text-chirp-400' },
                    { v:'medium', label:'Medium (Opus 64k)', hint:'~10% size', color:'text-blue-400' },
                    { v:'low', label:'Low (Opus 24k)', hint:'~4% size', color:'text-yellow-400' },
                  ].map(({ v, label, hint, color }) => (
                    <button key={v}
                      onClick={() => setForm(f => ({ ...f, storage_compress_quality: v }))}
                      className={`px-3 py-2 rounded-lg border text-xs font-medium transition-colors text-left
                        ${form.storage_compress_quality === v
                          ? 'bg-chirp-900/40 border-chirp-600 text-chirp-200'
                          : 'border-surface-600 text-gray-500 hover:border-surface-500'}`}>
                      <div>{label}</div>
                      <div className={`${color} mt-0.5`}>{hint} of WAV</div>
                    </button>
                  ))}
                </div>
                <p className="text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>
                  Re-analysis and AI Enhance run on the stored file. Opus loses high-frequency detail (measured at 64k: 10–17 dB fidelity in the 6–11 kHz band), so choose Lossless if you re-analyze often.
                </p>
              </Field>
            )}
          </div>

          {/* ── Recording lifecycle / automation ─────────────────────────── */}
          <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--border-default)' }}>
            {/* Header */}
            <div className="px-4 py-3" style={{ background: 'var(--bg-raised)', borderBottom: '1px solid var(--border-subtle)' }}>
              <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                Automatic recording lifecycle
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
Three separate options, each more permanent than the last. Set any to 0 to turn it off.
</p>
            </div>

            {/* Lifecycle diagram */}
            <div className="px-4 py-3 flex items-center gap-1 text-xs flex-wrap"
                 style={{ background: 'rgba(34,211,238,.04)', borderBottom: '1px solid var(--border-subtle)' }}>
              <span className="px-2 py-1 rounded-lg font-medium" style={{ background:'rgba(74,222,128,.12)', color:'#4ade80' }}>
                New recording
              </span>
              <span style={{ color:'var(--text-tertiary)' }}>→</span>
              <span className="px-2 py-1 rounded-lg font-medium" style={{ background:'rgba(251,191,36,.12)', color:'#fbbf24' }}>
                Archived (audio removed)
              </span>
              <span style={{ color:'var(--text-tertiary)' }}>→</span>
              <span className="px-2 py-1 rounded-lg font-medium" style={{ background:'rgba(249,115,22,.12)', color:'#f97316' }}>
                Soft-deleted (hidden)
              </span>
              <span style={{ color:'var(--text-tertiary)' }}>→</span>
              <span className="px-2 py-1 rounded-lg font-medium" style={{ background:'rgba(248,113,113,.12)', color:'#f87171' }}>
                Permanently purged
              </span>
            </div>

            <div className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>

              {/* Tier 1: Archive */}
              <div className="p-4 space-y-3">
                <div className="flex items-start gap-3">
                  <div className="w-2.5 h-2.5 rounded-full mt-1 flex-shrink-0" style={{ background:'#fbbf24' }}/>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold" style={{ color:'#fbbf24' }}>Archive — gentlest option</p>
                    <p className="text-xs mt-1" style={{ color:'var(--text-secondary)', lineHeight:1.6 }}>
Deletes <strong style={{ color:'var(--text-primary)' }}>only the audio</strong> to free space. The recording, its detections and spectrogram stay and still count everywhere, including the Life List; playback, download and iNaturalist submission stop working. <span style={{ color:'#fbbf24' }}> The audio can't be recovered.</span>
</p>
                    <div className="mt-3 flex items-center gap-3">
                      <label className="text-xs font-medium" style={{ color:'var(--text-tertiary)' }}>
                        Archive audio older than
                      </label>
                      <input type="number" min={0} max={3650} step={1}
                        className="input w-24 text-sm"
                        value={form.auto_archive_recordings_days ?? 0}
                        onChange={e => setForm(f => ({ ...f, auto_archive_recordings_days: parseInt(e.target.value, 10)||0 }))}
                      />
                      <span className="text-xs" style={{ color:'var(--text-tertiary)' }}>
                        days&ensp;{form.auto_archive_recordings_days > 0
                          ? <span style={{ color:'#fbbf24' }}>active — audio older than {form.auto_archive_recordings_days}d will be removed</span>
                          : <span style={{ color:'var(--text-tertiary)' }}>disabled</span>}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Tier 2: Soft-delete by age */}
              <div className="p-4 space-y-3">
                <div className="flex items-start gap-3">
                  <div className="w-2.5 h-2.5 rounded-full mt-1 flex-shrink-0" style={{ background:'#f97316' }}/>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold" style={{ color:'#f97316' }}>Age-based removal</p>
                    <p className="text-xs mt-1" style={{ color:'var(--text-secondary)', lineHeight:1.6 }}>
Removes the recording from the list, statistics, Life List and charts, and deletes its audio, spectrogram and clips. <span style={{ color:'#f97316' }}> Treat this as permanent;</span> the database row is only marked deleted and can be restored by hand.
</p>
                    <div className="mt-3 flex items-center gap-3">
                      <label className="text-xs font-medium" style={{ color:'var(--text-tertiary)' }}>
                        Remove recordings older than
                      </label>
                      <input type="number" min={0} max={3650} step={1}
                        className="input w-24 text-sm"
                        value={form.auto_delete_recordings_days ?? 0}
                        onChange={e => setForm(f => ({ ...f, auto_delete_recordings_days: parseInt(e.target.value, 10)||0 }))}
                      />
                      <span className="text-xs" style={{ color:'var(--text-tertiary)' }}>
                        days&ensp;{form.auto_delete_recordings_days > 0
                          ? <span style={{ color:'#f97316' }}>active — recordings older than {form.auto_delete_recordings_days}d will be hidden</span>
                          : <span style={{ color:'var(--text-tertiary)' }}>disabled</span>}
                      </span>
                    </div>
                    {form.auto_delete_recordings_days > 0 && form.auto_archive_recordings_days > 0 &&
                     form.auto_archive_recordings_days >= form.auto_delete_recordings_days && (
                      <p className="mt-2 text-xs px-2 py-1.5 rounded-lg"
                         style={{ background:'rgba(248,113,113,.08)', color:'#f87171', border:'1px solid rgba(248,113,113,.2)' }}>
                        ⚠ Archive threshold ({form.auto_archive_recordings_days}d) should be lower than the removal
                        threshold ({form.auto_delete_recordings_days}d) — otherwise recordings are removed before
                        they're archived.
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* Tier 3: Size-based */}
              <div className="p-4 space-y-3">
                <div className="flex items-start gap-3">
                  <div className="w-2.5 h-2.5 rounded-full mt-1 flex-shrink-0" style={{ background:'#f87171' }}/>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold" style={{ color:'#f87171' }}>Size-based removal</p>
                    <p className="text-xs mt-1" style={{ color:'var(--text-secondary)', lineHeight:1.6 }}>
When recordings take more than this, the <strong style={{ color:'var(--text-primary)' }}>oldest</strong> are deleted until usage is back to 90% of the limit, the same as age-based removal. <span style={{ color:'#f87171' }}> Labeled or noted recordings are kept if the option below is on.</span>
</p>
                    <div className="mt-3 flex items-center gap-3">
                      <label className="text-xs font-medium" style={{ color:'var(--text-tertiary)' }}>
                        Max recordings directory size
                      </label>
                      <input type="number" min={0} max={10000} step={1}
                        className="input w-24 text-sm"
                        value={form.storage_max_dir_gb ?? 0}
                        onChange={e => setForm(f => ({ ...f, storage_max_dir_gb: parseFloat(e.target.value)||0 }))}
                      />
                      <span className="text-xs" style={{ color:'var(--text-tertiary)' }}>
                        GB&ensp;{form.storage_max_dir_gb > 0
                          ? <span style={{ color:'#f87171' }}>active — oldest recordings removed above {form.storage_max_dir_gb} GB</span>
                          : <span style={{ color:'var(--text-tertiary)' }}>disabled</span>}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Protected recordings */}
              <div className="p-4">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input type="checkbox"
                    checked={form.storage_cleanup_keep_flagged ?? true}
                    onChange={e => setForm(f => ({ ...f, storage_cleanup_keep_flagged: e.target.checked }))}
                    className="w-4 h-4 accent-chirp-500 mt-0.5"
                  />
                  <div>
                    <p className="text-sm font-medium" style={{ color:'var(--text-primary)' }}>
                      Protect recordings with labels or notes
                    </p>
                    <p className="text-xs mt-0.5" style={{ color:'var(--text-tertiary)' }}>
On: recordings you've labeled or noted are skipped by archive, age removal and size removal. Saved recordings are always skipped.
</p>
                  </div>
                </label>
              </div>
            </div>
          </div>

          {/* Manual trigger */}
          <div className="pt-2 border-t border-surface-700 flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-300 font-medium">Run cleanup now</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Applies all enabled lifecycle options immediately. Runs automatically every hour.
              </p>
            </div>
            <button
              onClick={async () => {
                setCleanupRunning(true)
                setCleanupResult(null)
                try {
                  clearApiCache()
                  const r = await fetch('/api/v1/recordings/storage/cleanup', {
                    method: 'POST',
                    headers: localStorage.getItem('chirp_token')
                      ? { Authorization: 'Bearer ' + localStorage.getItem('chirp_token') } : {}
                  })
                  const d = await r.json()
                  setCleanupResult(d)
                  api.recordings.storageStatus().then(setStorageStatus).catch(() => {})
                } catch(e) {
                  setCleanupResult({ status: 'error', detail: e.message })
                } finally {
                  setCleanupRunning(false)
                }
              }}
              disabled={cleanupRunning}
              className="flex items-center gap-2 px-4 py-2 rounded-lg border border-surface-600 bg-surface-800 hover:bg-surface-700 text-sm text-gray-300 disabled:opacity-50 transition-colors flex-shrink-0"
            >
              <RefreshCw size={14} className={cleanupRunning ? 'animate-spin' : ''}/>
              {cleanupRunning ? 'Running…' : 'Run Cleanup'}
            </button>
          </div>
          {cleanupResult && (
            <div className={`text-xs px-3 py-2 rounded-lg border ${
              cleanupResult.status === 'error'
                ? 'bg-red-900/20 border-red-800/50 text-red-400'
                : 'bg-chirp-900/20 border-chirp-700/50 text-chirp-300'
            }`}>
              {cleanupResult.status === 'error'
                ? `Error: ${cleanupResult.detail}`
                : `Done — archived: ${cleanupResult.archived ?? 0}, age-removed: ${cleanupResult.age_pruned ?? 0}, size-removed: ${cleanupResult.size_pruned ?? 0}. Directory: ${(cleanupResult.dir_size_gb_after ?? 0).toFixed(2)} GB`
              }
            </div>
          )}

          {/* Soft-deleted recordings purge */}
          <div className="border-t border-surface-600 pt-4">
            <p className="text-sm font-medium text-gray-200 mb-1">Purge soft-deleted recordings</p>
            <p className="text-xs text-gray-500 mb-3">
              Recordings deleted without "Remove from database" are hidden but not erased.
              {softDeletedCount !== null && softDeletedCount > 0
                ? <span className="text-yellow-400 font-medium"> {softDeletedCount} recording{softDeletedCount === 1 ? '' : 's'} pending.</span>
                : softDeletedCount === 0
                ? <span className="text-chirp-400"> None pending.</span>
                : null
              }
            </p>
            <label className="flex items-center gap-2 cursor-pointer mb-3 text-sm text-gray-300">
              <input type="checkbox" checked={cleanupDeleteFiles}
                     onChange={e => setCleanupDeleteFiles(e.target.checked)}
                     className="toggle"/>
              Also delete audio &amp; spectrogram files from disk
            </label>
            <button
              disabled={!softDeletedCount || cleanupRunning}
              onClick={async () => {
                if (!window.confirm(`Permanently delete ${softDeletedCount} soft-deleted recording${softDeletedCount === 1 ? '' : 's'} from the database${cleanupDeleteFiles ? ' and disk' : ''}?`)) return
                setCleanupRunning(true)
                try {
                  const r = await api.settings.cleanupDeleted(cleanupDeleteFiles)
                  setSoftDeletedCount(0)
                  alert(`✓ Purged ${r.removed_recordings} recording${r.removed_recordings === 1 ? '' : 's'}, freed ${r.freed_mb} MB`)
                } catch (e) { alert('Purge failed: ' + e.message) }
                setCleanupRunning(false)
              }}
              className="btn-danger flex items-center gap-2">
              <Trash2 size={13}/>
              {cleanupRunning ? 'Purging…' : `Purge ${softDeletedCount ?? 0} soft-deleted`}
            </button>
          </div>
        </div>
      </Section>
      <Section icon={Trash2} title="Empty Recordings" id="settings-storage-empty">
        <div className="space-y-5">

          {/* Counts row */}
          {emptyCount !== null && (
            <div className="flex flex-wrap gap-3">
              <div className="card px-3 py-2 text-center min-w-[110px]">
                <p className="text-lg font-bold text-red-400">{emptyCount.no_detections}</p>
                <p className="text-xs text-gray-500 mt-0.5">show nothing</p>
              </div>
              <div className="card px-3 py-2 text-center min-w-[130px]">
                <p className="text-lg font-bold text-yellow-400">{emptyCount.no_server_detections}</p>
                <p className="text-xs text-gray-500 mt-0.5">nothing from the server</p>
              </div>
            </div>
          )}
          <div className="text-xs text-gray-500 space-y-1">
            <p>
              <span className="text-gray-300">Show nothing</span>: no detection at the display threshold, from
              the station or the server. These are the "Unknown" cards in Recordings.
            </p>
            <p>
              <span className="text-gray-300">Nothing from the server</span>: the server's BirdNET pass found
              nothing, though the station's detections may still show. It covers almost everything in the first count too.
            </p>
            <p>Owls the server kept after hearing a hoot never count as empty.</p>
          </div>

          {/* Auto-purge toggle */}
          <div className="settings-row">
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-200">Auto-delete station recordings that show nothing</p>
              <p className="text-xs text-gray-500 mt-1">
                Checked after the server pass on each upload, and every 15 minutes for older ones.
                Saved recordings and those with a label, notes or an iNaturalist submission are kept.
              </p>
            </div>
            <input type="checkbox" className="toggle flex-shrink-0 mt-0.5"
              checked={form.auto_purge_empty_recordings ?? false}
              onChange={e => setForm(f => ({ ...f, auto_purge_empty_recordings: e.target.checked }))}/>
          </div>

          {/* Purge strategy — only shown when auto-purge is enabled */}
          {form.auto_purge_empty_recordings && (
            <div className="space-y-3 pl-4 border-l-2" style={{ borderColor: 'var(--border-subtle)' }}>

              {/* Delete-all toggle */}
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    Delete even if the Pi was confident
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                    {form.auto_purge_all_device
                      ? 'On: every recording that shows nothing is deleted, whatever the Pi scored.'
                      : 'Off: a recording the Pi scored highly is kept even when it shows nothing.'}
                  </p>
                </div>
                <input type="checkbox" className="toggle flex-shrink-0"
                  checked={form.auto_purge_all_device ?? false}
                  onChange={e => setForm(f => ({ ...f, auto_purge_all_device: e.target.checked }))}/>
              </div>

              {/* Confidence threshold — hidden when delete-all is active */}
              {!form.auto_purge_all_device && (
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      Keep if the Pi scored at least
                    </p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                      The Pi's top score for the recording, before the server pass. Default 65%.
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <input
                      type="number" min="0.10" max="0.99" step="0.05"
                      className="input w-20 text-sm text-center"
                      value={form.auto_purge_min_confidence ?? 0.65}
                      onChange={e => setForm(f => ({
                        ...f,
                        auto_purge_min_confidence: Math.min(0.99, Math.max(0.1, parseFloat(e.target.value) || 0.65))
                      }))}
                    />
                    <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                      ({Math.round((form.auto_purge_min_confidence ?? 0.65) * 100)}%)
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Manual purge */}
          <div className="border-t border-surface-600 pt-4 space-y-3">
            <p className="text-sm font-medium text-gray-200">Delete now</p>
            <div className="flex flex-wrap gap-2">
              <button
                disabled={purging || (emptyCount !== null && emptyCount.no_detections === 0)}
                onClick={async () => {
                  const n = emptyCount?.no_detections ?? '?'
                  if (!window.confirm(`Delete ${n} recording${n === 1 ? '' : 's'} that show nothing, with their audio? This can't be undone.`)) return
                  setPurging('all')
                  try {
                    const r = await api.settings.purgeEmpty('no_detections', true)
                    setEmptyCount(null)
                    api.settings.emptyCount().then(setEmptyCount).catch(() => {})
                    alert(`✓ Deleted ${r.purged} recording${r.purged === 1 ? '' : 's'}, freed ${r.freed_mb} MB`)
                  } catch (e) { alert('Delete failed: ' + e.message) }
                  setPurging(null)
                }}
                className="btn-danger flex items-center gap-2">
                <Trash2 size={13}/>
                {purging === 'all' ? 'Deleting…' : `Delete ${emptyCount?.no_detections ?? '…'} that show nothing`}
              </button>

              <button
                disabled={purging || (emptyCount !== null && emptyCount.no_server_detections === 0)}
                onClick={async () => {
                  const n = emptyCount?.no_server_detections ?? '?'
                  if (!window.confirm(`Delete ${n} recording${n === 1 ? '' : 's'} with nothing from the server, with their audio? This includes recordings where only the station's detections show. This can't be undone.`)) return
                  setPurging('server')
                  try {
                    const r = await api.settings.purgeEmpty('no_server_detections', true)
                    setEmptyCount(null)
                    api.settings.emptyCount().then(setEmptyCount).catch(() => {})
                    alert(`✓ Deleted ${r.purged} recording${r.purged === 1 ? '' : 's'}, freed ${r.freed_mb} MB`)
                  } catch (e) { alert('Delete failed: ' + e.message) }
                  setPurging(null)
                }}
                className="btn-danger flex items-center gap-2">
                <Trash2 size={13}/>
                {purging === 'server' ? 'Deleting…' : `Delete ${emptyCount?.no_server_detections ?? '…'} with nothing from the server`}
              </button>
            </div>
            <p className="text-xs text-gray-600">
              Unlike auto-delete, these also take uploads and recordings with labels or notes (not saved ones). Audio
              is deleted for good.
            </p>
          </div>
        </div>
      </Section>
      <Section icon={HardDrive} title="Database Backup &amp; Restore" id="settings-backup">
        <BackupRestorePanel form={form} setForm={setForm}/>
      </Section>
      <Section icon={RefreshCw} title="Bird Data and Range Maps" id="settings-experimental-data">
        <div className="space-y-4">
          <Field label="Refresh All Bird Profiles"
                 hint="Reloads Wikipedia text, range maps from every enabled source and iNaturalist data for every bird on your life list. Runs in the background, about 30–60 seconds per bird.">
            <div className="flex items-center gap-2 flex-wrap">
              <button onClick={async () => {
                setBulkRefreshing(true)
                setBulkDone(false)
                setBulkProgress(null)
                setBulkMode('full')
                try {
                  clearApiCache()
                  const r = await fetch('/api/v1/birds/enrich-all', {
                    method: 'POST',
                    headers: {
                      'Content-Type': 'application/json',
                      ...(localStorage.getItem('chirp_token')
                        ? { Authorization: 'Bearer ' + localStorage.getItem('chirp_token') }
                        : {})
                    }
                  })
                  if (r.status === 409) {
                    // Already running elsewhere (e.g. another tab, or the
                    // maps-only button) — just start polling, don't error
                    pollBulkStatus()
                    return
                  }
                  const d = await r.json()
                  setBulkCount(d.count || 0)
                } catch (e) {
                  alert('Refresh failed: ' + e.message)
                  setBulkRefreshing(false)
                }
              }} disabled={bulkRefreshing}
              className="flex items-center gap-2 px-4 py-2 rounded-lg border border-surface-600 bg-surface-800 hover:bg-surface-700 text-sm text-gray-300 hover-text-primary transition-colors disabled:opacity-50">
                <RefreshCw size={14} className={bulkRefreshing && bulkMode === 'full' ? 'animate-spin' : ''}/>
                {bulkRefreshing && bulkMode === 'full'
                  ? (bulkProgress ? `Refreshing… ${bulkProgress.done}/${bulkProgress.total}` : 'Starting…')
                  : bulkDone && bulkMode === 'full' ? `✓ Refreshed ${bulkCount} birds` : 'Refresh All Bird Data'}
              </button>

              <button onClick={async () => {
                setBulkRefreshing(true)
                setBulkDone(false)
                setBulkProgress(null)
                setBulkMode('maps_only')
                try {
                  clearApiCache()
                  const r = await fetch('/api/v1/birds/enrich-all/maps-only', {
                    method: 'POST',
                    headers: {
                      'Content-Type': 'application/json',
                      ...(localStorage.getItem('chirp_token')
                        ? { Authorization: 'Bearer ' + localStorage.getItem('chirp_token') }
                        : {})
                    }
                  })
                  if (r.status === 409) {
                    pollBulkStatus()
                    return
                  }
                  const d = await r.json()
                  setBulkCount(d.count || 0)
                } catch (e) {
                  alert('Range map refresh failed: ' + e.message)
                  setBulkRefreshing(false)
                }
              }} disabled={bulkRefreshing}
              title="Refreshes every map source only — skips Wikipedia descriptions, iNaturalist photos/sounds, seasonal frequency data, and Cornell Lab / All About Birds content (Cool Facts, At a Glance tags). Faster than a full refresh, but birds refreshed this way won't show those until a full refresh."
              className="flex items-center gap-2 px-4 py-2 rounded-lg border border-surface-600 bg-surface-800 hover:bg-surface-700 text-sm text-gray-300 hover-text-primary transition-colors disabled:opacity-50">
                <MapPin size={14} className={bulkRefreshing && bulkMode === 'maps_only' ? 'animate-pulse' : ''}/>
                {bulkRefreshing && bulkMode === 'maps_only'
                  ? (bulkProgress ? `Refreshing maps… ${bulkProgress.done}/${bulkProgress.total}` : 'Starting…')
                  : bulkDone && bulkMode === 'maps_only' ? `✓ Refreshed ${bulkCount} birds' maps` : 'Refresh Range Maps Only'}
              </button>
            </div>

            {bulkRefreshing && bulkProgress && bulkProgress.total > 0 && (
              <div className="mt-3 space-y-1">
                <div className="h-1.5 w-full max-w-md rounded-full bg-surface-700 overflow-hidden">
                  <div
                    className="h-full bg-chirp-500 transition-all duration-500 ease-out"
                    style={{ width: `${Math.min(100, Math.round((bulkProgress.done / bulkProgress.total) * 100))}%` }}
                  />
                </div>
                <p className="text-xs text-gray-500">
                  {bulkProgress.done} / {bulkProgress.total} birds
                  {bulkMode === 'maps_only' && <span className="text-gray-600"> (maps only)</span>}
                  {bulkProgress.current_name && <> — currently: <span className="text-gray-400">{bulkProgress.current_name}</span></>}
                  {bulkProgress.errors > 0 && <span className="text-amber-500"> ({bulkProgress.errors} error{bulkProgress.errors === 1 ? '' : 's'}, see server logs)</span>}
                </p>
              </div>
            )}

            {bulkDone && !bulkRefreshing && (
              <p className="text-xs text-chirp-400 mt-2">
                {bulkMode === 'maps_only'
                  ? `Refreshed range maps for ${bulkCount} birds — every enabled map source is now up to date.`
                  : `Refreshed ${bulkCount} birds. Range maps and descriptions are up to date.`}
                {bulkProgress?.errors > 0 && ` (${bulkProgress.errors} had errors — see server logs.)`}
              </p>
            )}
          </Field>
        </div>
      </Section>

      <GroupHeader id="settings-account-group"/>
      <Section icon={Lock} title="Authentication" id="settings-auth">
        <div className="space-y-4">
          <Field label="Require login"
                 hint="When enabled, users must log in to access Chirp. Requires container restart to take effect.">
            <label className="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" checked={form.auth_enabled ?? false}
                     onChange={e => setForm(f => ({ ...f, auth_enabled: e.target.checked }))}
                     className="w-5 h-5 accent-chirp-500"/>
              <span className="text-sm text-gray-300">
                {form.auth_enabled ? 'Authentication enabled — login required' : 'Authentication disabled — open access'}
              </span>
            </label>
            {form.auth_enabled && (
              <p className="text-xs text-yellow-400 mt-2">
                ⚠ Set CHIRP_ADMIN_PASSWORD in your .env, then restart the container.
                Default admin username: <code className="font-mono">admin</code>
              </p>
            )}
            <Link to="/login" className="inline-flex items-center gap-1 text-xs text-chirp-500 hover:text-chirp-400 mt-2">
              Preview login page →
            </Link>
          </Field>
        </div>
      </Section>
      <Section icon={Key} title="Device API Keys" id="settings-api-device">
        <div className="space-y-4">
          <p className="text-xs text-gray-500">
Keys stations use to upload. Tap the eye to see a key, for example to spot unused or duplicate ones before deleting them.
</p>
          {deviceKeys.length > 0 && (
            <div className="space-y-2">
              {deviceKeys.map(k => (
                <DeviceKeyRow key={k.id} k={k} onDeleted={() => setDeviceKeys(d => d.filter(x => x.id !== k.id))}/>
              ))}
            </div>
          )}
          {newKeyValue && (
            <div className="p-3 bg-chirp-900/20 border border-chirp-700/50 rounded-lg">
              <p className="text-xs font-semibold text-chirp-400 mb-1">New key — copy now, won't be shown again:</p>
              <div className="flex items-center gap-2">
                <code className="text-xs text-chirp-300 font-mono bg-surface-900 px-2 py-1 rounded flex-1 break-all">
                  {newKeyValue}
                </code>
                <button onClick={() => { navigator.clipboard.writeText(newKeyValue); setNewKeyValue(null) }}
                        className="btn-primary text-xs px-3 py-1 flex-shrink-0">Copy &amp; Close</button>
              </div>
            </div>
          )}
          <div className="flex items-center gap-2">
            <input className="input flex-1" placeholder="Device name (e.g. Pi-Garden)"
                   value={newKeyName} onChange={e => setNewKeyName(e.target.value)}/>
            <button disabled={!newKeyName.trim()} onClick={async () => {
              const k = await api.settings.deviceKeys.create(newKeyName.trim())
              setDeviceKeys(d => [...d, { id: k.id, name: k.name, created_at: k.created_at }])
              setNewKeyValue(k.key)
              setNewKeyName('')
            }} className="btn-primary px-4 py-2 text-sm flex-shrink-0">Generate Key</button>
          </div>
          <ApiKeysPanel form={form} setForm={setForm} settings={settings} only="device"/>
        </div>
      </Section>
      <Section icon={Activity} title="Activity Log" id="settings-activity-log">
        <div className="space-y-4">
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
Records sign-ins and page views so admins can see who uses the site and when. No passwords, tokens, notes or recording content are stored. The Activity page shows the log.
</p>

          <div className="settings-row">
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-200">Enable activity log</p>
              <p className="text-xs text-gray-500 mt-1">
Off: nothing is recorded beyond each account's last sign-in.
</p>
            </div>
            <input type="checkbox" className="toggle flex-shrink-0 mt-0.5"
              checked={form.activity_log_enabled ?? true}
              onChange={e => setForm(f => ({ ...f, activity_log_enabled: e.target.checked }))}/>
          </div>

          {form.activity_log_enabled && (
            <div className="space-y-3 pl-4 border-l-2" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    Record IP address and browser
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                    Off keeps only who did what and when — no IP address or browser
                    string with each event.
                  </p>
                </div>
                <input type="checkbox" className="toggle flex-shrink-0"
                  checked={form.activity_log_track_ip ?? true}
                  onChange={e => setForm(f => ({ ...f, activity_log_track_ip: e.target.checked }))}/>
              </div>

              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    Keep history for
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                    Events older than this are purged automatically, every hour. 0 = keep forever.
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <input
                    type="number" min="0" max="3650" step="1"
                    className="input w-20 text-sm text-center"
                    value={form.activity_log_retention_days ?? 90}
                    onChange={e => setForm(f => ({
                      ...f,
                      activity_log_retention_days: Math.max(0, parseInt(e.target.value) || 0)
                    }))}
                  />
                  <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {(form.activity_log_retention_days ?? 90) === 0 ? 'forever' : 'days'}
                  </span>
                </div>
              </div>

              <div className="pt-2 border-t border-surface-700 flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Run cleanup now</p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
Applies the retention setting now. It also runs every hour.
</p>
                  {activityPurgeResult && (
                    <p className="text-xs mt-1" style={{ color: activityPurgeResult.status === 'ok' ? 'var(--pastel-green)' : 'var(--pastel-red)' }}>
                      {activityPurgeResult.status === 'ok'
                        ? `✓ Purged ${activityPurgeResult.purged ?? 0} event${(activityPurgeResult.purged ?? 0) === 1 ? '' : 's'}`
                        : `Failed: ${activityPurgeResult.detail || activityPurgeResult.status}`}
                    </p>
                  )}
                </div>
                <button
                  className="btn-secondary text-xs flex-shrink-0"
                  disabled={activityPurgeRunning}
                  onClick={async () => {
                    setActivityPurgeRunning(true)
                    setActivityPurgeResult(null)
                    try {
                      const r = await api.settings.activityLogPurge()
                      setActivityPurgeResult(r)
                    } catch (e) {
                      setActivityPurgeResult({ status: 'error', detail: e.message })
                    } finally {
                      setActivityPurgeRunning(false)
                    }
                  }}>
                  {activityPurgeRunning ? 'Running…' : 'Run now'}
                </button>
              </div>
            </div>
          )}

          <Link to="/activity" className="text-xs inline-flex items-center gap-1 hover:underline"
                style={{ color: 'var(--accent-400)' }}>
            View login history and activity feed →
          </Link>
        </div>
      </Section>
      <Section icon={Radio} title="Server Network (Tailscale)" id="settings-tailscale">
        <TailscaleStatusPanel/>
      </Section>

      <GroupHeader id="settings-experimental"/>
      <div className="space-y-3">
      <ExpCard id="range_maps" title="Range Maps" collapsed={expCollapsed} setCollapsed={setExpCollapsed}
               subtitle="Range maps on bird profiles, from All About Birds, iNaturalist, BirdLife and others. Some species load slowly or have no map.">
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm text-gray-300">Enable range maps</p>
          <input
            type="checkbox"
            checked={form.range_maps_enabled ?? false}
            onChange={e => setForm(f => ({ ...f, range_maps_enabled: e.target.checked }))}
            className="w-4 h-4 accent-chirp-500 flex-shrink-0"
          />
        </div>
        {form.range_maps_enabled && (
          <p className="text-xs text-yellow-400/80 bg-yellow-900/10 border border-yellow-700/30 rounded px-3 py-2 flex items-start gap-1.5">
            <span className="flex-shrink-0">⚠️</span>
            <span>
              When enabled, bird profiles will show a range map panel. Maps are fetched on first view and cached locally.
              Disable to hide range maps entirely — existing cached maps are not deleted.
            </span>
          </p>
        )}

          {/* iNaturalist Geomodel range maps */}
          {/* Per-source enable/disable */}
          {form.range_maps_enabled && (
            <>
            <div className="rounded-lg border border-surface-700 bg-surface-800 p-4 space-y-3">
              <p className="text-sm font-medium text-gray-200">Map Tab Order</p>
              <p className="text-xs text-gray-500">Drag to reorder how the map source tabs appear on bird profiles.</p>
              <MapTabOrderList
                order={form.range_map_source_order?.length ? form.range_map_source_order : ['aab', 'macaulay', 'geomodel', 'birdlife', 'ebird_st']}
                onChange={newOrder => setForm(f => ({ ...f, range_map_source_order: newOrder }))}
              />
            </div>
            <div className="rounded-lg border border-surface-700 bg-surface-800 p-4 space-y-3">
              <p className="text-sm font-medium text-gray-200">Map Sources</p>
              <p className="text-xs text-gray-500">Enable or disable each range map source on bird profiles.</p>
              {[
                { id: 'aab', Icon: AABIcon, label: 'All About Birds', hint: 'Fetched via Playwright — requires Chromium in container' },
                { id: 'macaulay', Icon: MacaulayIcon, label: 'Macaulay Library', hint: 'Cornell CDN — same range map images used by eBird web and Merlin. Has its own tab, and is also used as AAB\'s fallback if AAB fails.' },
                { id: 'geomodel', Icon: INatIcon, label: 'iNat Geomodel', hint: 'Requires geopackage download below' },
                { id: 'birdlife', Icon: BirdLifeIcon, label: 'BirdLife International', hint: 'Fetched via Playwright — requires Chromium in container' },
                { id: 'ebird_st', Icon: EbirdSTIcon, label: 'eBird Status & Trends',
                  hint: 'Seasonal abundance raster — requires a separate S&T key below. Experimental alternative to the AAB/BirdLife screenshot pipeline.' },
              ].map(({ id, Icon, label, hint }) => (
                <div key={id} className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm text-gray-300 flex items-center gap-1.5">
                      <Icon size={14} className="flex-shrink-0 text-gray-400"/>
                      {label}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">{hint}</p>
                  </div>
                  <input type="checkbox"
                    checked={form.range_map_sources?.[id] ?? (id === 'ebird_st' ? false : true)}
                    onChange={e => setForm(f => ({
                      ...f,
                      range_map_sources: { ...(f.range_map_sources ?? {}), [id]: e.target.checked }
                    }))}
                    className="mt-1 flex-shrink-0"/>
                </div>
              ))}
            </div>
            </>
          )}
          {/* iNaturalist Geomodel download — re-download always available */}
          {form.range_maps_enabled && <GeomodelDownloadPanel allowRedownload={true} />}
      </ExpCard>

      <ExpCard id="heatmap" title="Observation Heatmap" collapsed={expCollapsed} setCollapsed={setExpCollapsed}
               subtitle="A map of iNaturalist sightings on bird profiles. Unreliable for now: some species or regions don't load.">
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm text-gray-300">Enable observation heatmap</p>
          <input
            type="checkbox"
            checked={form.observation_heatmap_enabled ?? false}
            onChange={e => setForm(f => ({ ...f, observation_heatmap_enabled: e.target.checked }))}
            className="w-4 h-4 accent-chirp-500 flex-shrink-0"
          />
        </div>
      </ExpCard>


      <ExpCard id="nighthawk" title="Night Flight Calls" collapsed={expCollapsed} setCollapsed={setExpCollapsed}
               subtitle="Nighthawk finds the flight calls of migrating birds in the stations' night audio.">
        <ExperimentalModels form={form} setForm={setForm}/>
      </ExpCard>
      </div>

      {/* pre-existing bug found while wiring up the new tabbed
          layout: the {isAdmin && <>...} fragment opened above (around
          "Detection" — gating Detection through Experimental Features
          behind admin) was never closed with a matching </>.
          It happened to not cause a hard build failure before because
          of what came after it; adding the new wrapping divs for the
          sidebar layout below made the mismatch surface as a 
          esbuild error. This closing tag restores what the opening
          syntax already implied — no behavior change, since
          isAdmin-gating everything in between was clearly the intent
          (matching the same pattern the Diagnostics section, right
          below, already uses correctly on its own). */}
      </>}

      {/* ── Diagnostics ─────────────────────────────────────────────── */}
      {!isAdmin && isApp() && (<>
        <GroupHeader id="settings-diagnostics-group"/>
        <AppDiagnosticsCard/>
      </>)}
      {isAdmin && (<>
        <GroupHeader id="settings-diagnostics-group"/>
        {isApp() && <AppDiagnosticsCard/>}

        <div className="rounded-2xl p-4 md:p-5 space-y-5"
             style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)' }}>

          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            Something not working? The <a href="https://ourchirp.com/troubleshooting.html" target="_blank" rel="noopener" style={{ color: 'var(--accent-400)' }}>troubleshooting guide ↗</a> covers common problems with the app, stations, sound and detections.
          </p>

          {/* Run controls */}
          <div className="space-y-3">
            {/* Mode selector */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium" style={{ color:'var(--text-tertiary)' }}>Mode:</span>
              {[
                { id:'full', label:'Full Report', hint:'All checks' },
                { id:'db', label:'Database Only', hint:'Counts & stats' },
                { id:'mic', label:'Microphone Check', hint:'SSH to devices' },
              ].map(m => (
                <button key={m.id} onClick={() => setDiagMode(m.id)}
                        className="tactile-press px-3 py-1.5 text-xs rounded-xl transition-all"
                        style={{
                          background: diagMode===m.id ? 'rgba(167,139,250,.15)' : 'var(--bg-raised)',
                          border: `1px solid ${diagMode===m.id ? 'rgba(167,139,250,.5)' : 'var(--border-subtle)'}`,
                          color: diagMode===m.id ? '#a78bfa' : 'var(--text-tertiary)',
                        }}>
                  {m.label}
                  <span className="ml-1.5 opacity-60">{m.hint}</span>
                </button>
              ))}
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-3 flex-wrap">
              <button onClick={() => runDiagnostics(diagMode)} disabled={diagLoading}
                      className="btn-primary flex items-center gap-2 px-5 py-2.5">
                {diagLoading
                  ? <><RefreshCw size={14} className="animate-spin"/> Running…</>
                  : <><Stethoscope size={14}/> Run {diagMode === 'mic' ? 'Mic Check' : diagMode === 'db' ? 'DB Check' : 'Diagnostics'}</>}
              </button>
              <div className="flex items-center gap-2">
                <button
                  onClick={async () => {
                    try {
                      const ext = diagIncludeLogs ? 'zip' : 'txt'
                      await saveUrl(api.diagnostics.reportUrl(diagMode, diagIncludeLogs, diagSshPassword),
                        { filename: `chirp_diagnostics_${new Date().toISOString().slice(0,10)}.${ext}` })
                    } catch (e) {
                      alert('Download failed: ' + e.message)
                    }
                  }}
                  className="flex items-center gap-1.5 text-xs px-4 py-2.5 rounded-xl transition-colors"
                  style={{ background:'var(--bg-raised)', color:'var(--text-secondary)', border:'1px solid var(--border-subtle)' }}>
                  <Download size={13}/> {diagIncludeLogs ? 'Download ZIP with Logs' : 'Download Report'}
                </button>
                <label className="flex items-center gap-1.5 cursor-pointer text-xs" style={{ color:'var(--text-tertiary)' }}>
                  <input type="checkbox" checked={diagIncludeLogs}
                         onChange={e => setDiagIncludeLogs(e.target.checked)}
                         className="w-3.5 h-3.5 accent-chirp-500"/>
                  Include log files
                </label>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <input type="email" placeholder="you@example.com" value={diagEmailTo}
                       onChange={e => setDiagEmailTo(e.target.value)}
                       className="input text-xs" style={{ width: 200 }}/>
                <button
                  onClick={async () => {
                    if (!diagEmailTo) return
                    setDiagEmailSending(true)
                    setDiagEmailResult(null)
                    try {
                      const r = await api.diagnostics.emailReport(diagEmailTo, diagMode, diagIncludeLogs, diagSshPassword)
                      setDiagEmailResult({ ok: true, msg: `Sent as ${r.filename}` })
                    } catch (e) {
                      setDiagEmailResult({ ok: false, msg: e.message })
                    } finally {
                      setDiagEmailSending(false)
                    }
                  }}
                  disabled={diagEmailSending || !diagEmailTo}
                  className="flex items-center gap-1.5 text-xs px-4 py-2.5 rounded-xl transition-colors disabled:opacity-50"
                  style={{ background:'var(--bg-raised)', color:'var(--text-secondary)', border:'1px solid var(--border-subtle)' }}>
                  <Mail size={13}/> {diagEmailSending ? 'Sending…' : 'Email Report'}
                </button>
                {diagEmailResult && (
                  <span className="text-xs" style={{ color: diagEmailResult.ok ? 'var(--pastel-green)' : 'var(--pastel-red)' }}>
                    {diagEmailResult.ok ? '✓' : '✗'} {diagEmailResult.msg}
                  </span>
                )}
              </div>
            </div>
            {diagMode === 'mic' && (
              <div className="space-y-2">
                <p className="text-xs px-3 py-2 rounded-xl"
                   style={{ background:'rgba(251,191,36,.07)', border:'1px solid rgba(251,191,36,.2)', color:'#fbbf24' }}>
                  SSH credentials required — virtual devices (Haikubox) are skipped automatically.
                  Key-based auth is tried first; enter a password below as fallback.
                  {sshCredsSaved && ' Saved credentials on file will also be used automatically if this field is left blank.'}
                </p>
                <div className="flex items-center gap-3">
                  <label className="text-xs font-medium flex-shrink-0" style={{ color:'var(--text-tertiary)' }}>
                    SSH username
                  </label>
                  <input
                    type="text"
                    placeholder="joshsalvi"
                    value={diagSshUsername}
                    onChange={e => setDiagSshUsername(e.target.value)}
                    className="input flex-1 text-sm"
                    autoComplete="off"
                  />
                </div>
                <div className="flex items-center gap-3">
                  <label className="text-xs font-medium flex-shrink-0" style={{ color:'var(--text-tertiary)' }}>
                    SSH password {sshCredsSaved ? '(leave blank to use saved)' : '(optional)'}
                  </label>
                  <input
                    type="password"
                    placeholder={sshCredsSaved ? '•••••••• (saved)' : 'Leave blank to use key-based auth'}
                    value={diagSshPassword}
                    onChange={e => setDiagSshPassword(e.target.value)}
                    className="input flex-1 text-sm"
                    autoComplete="off"
                  />
                </div>
                {isAdmin && (
                  <div className="flex items-center justify-between gap-3 pt-1">
                    <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: 'var(--text-tertiary)' }}>
                      <input type="checkbox" checked={sshSaveRemember}
                             onChange={e => setSshSaveRemember(e.target.checked)}
                             className="toggle"/>
                      Remember these credentials on the server (admin-only; stored plaintext,
                      never shown again after saving)
                    </label>
                    {sshSaveRemember && (
                      <button onClick={handleSaveSshCredentials} disabled={sshSaveStatus === 'saving'}
                              className="text-xs px-2.5 py-1 rounded-md font-medium flex-shrink-0"
                              style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)', color: 'var(--accent-400)' }}>
                        {sshSaveStatus === 'saving' ? 'Saving…' : sshSaveStatus === 'saved' ? 'Saved ✓' : 'Save credentials'}
                      </button>
                    )}
                  </div>
                )}
                {sshSaveStatus === 'error' && (
                  <p className="text-xs text-red-400">Couldn't save — check that at least one (non-virtual) device is paired.</p>
                )}
              </div>
            )}
          </div>

          {diagError && (
            <div className="flex items-center gap-2 p-3 rounded-xl text-xs"
                 style={{ background: 'rgba(248,113,113,.08)', border: '1px solid rgba(248,113,113,.2)', color: 'var(--pastel-red)' }}>
              <AlertCircle size={13}/> {diagError}
            </div>
          )}

          {diagData && (() => {
            const srv = diagData.server || {}
            const sys_d = srv.system || {}
            const db = srv.db || {}
            const disk = srv.disk || {}
            const sett = srv.settings || {}
            const cache = srv.cache || {}
            const devices = diagData.devices || []
            const logs = diagData.logs || {}
            const logLines = logs.all || []
            const errLines = logs.errors || []
            const warnLines = logs.warnings || []
            const micChecks = diagData.mic_checks || []

            const StatusIcon = ({ status }) => {
              if (status === 'ok') return <CheckCircle2 size={14} style={{ color:'#4ade80' }}/>
              if (status === 'stale') return <AlertCircle size={14} style={{ color:'#fbbf24' }}/>
              return <XCircle size={14} style={{ color:'#f87171' }}/>
            }

            const Collapsible = ({ id, icon: Icon, title, color='var(--accent-400)', badge, children }) => {
              const collapsed = diagCollapsed[id]
              return (
                <div className="space-y-2">
                  <button onClick={() => toggleDiagSection(id)}
                          className="w-full flex items-center gap-2 pb-2"
                          style={{ borderBottom:'1px solid var(--border-subtle)' }}>
                    <Icon size={14} style={{ color }}/>
                    <span className="text-xs font-semibold uppercase tracking-wider flex-1 text-left" style={{ color }}>{title}</span>
                    {badge != null && <span className="text-xs px-2 py-0.5 rounded-full" style={{ background:'var(--bg-raised)', color:'var(--text-tertiary)' }}>{badge}</span>}
                    <ChevronDown size={12} style={{ color:'var(--text-tertiary)', transform: collapsed ? 'rotate(-90deg)' : 'rotate(0deg)', transition:'transform .2s' }}/>
                  </button>
                  {!collapsed && children}
                </div>
              )
            }

            const Row = ({ label, value, mono=false, highlight }) => (
              <div className="flex items-center justify-between py-0.5 text-xs">
                <span style={{ color:'var(--text-tertiary)' }}>{label}</span>
                <span className={mono ? 'font-mono' : 'font-medium'} style={{ color: highlight || 'var(--text-secondary)' }}>{value ?? '—'}</span>
              </div>
            )

            const loc = sett.location || {}

            return (
              <div className="space-y-5 pt-1">
                <p className="text-xs" style={{ color:'var(--text-tertiary)' }}>
                  Generated {diagData.generated_at?.replace('T',' ')} UTC · {diagData.elapsed_ms}ms · mode: {diagData.mode}
                </p>

                {errLines.length > 0 && (
                  <div className="flex items-start gap-2 p-3 rounded-xl text-xs"
                       style={{ background:'rgba(248,113,113,.08)', border:'1px solid rgba(248,113,113,.2)', color:'#f87171' }}>
                    <AlertCircle size={13} style={{ flexShrink:0, marginTop:1 }}/>
                    <div>
                      <p className="font-semibold">{errLines.length} error{errLines.length>1?'s':''} in recent logs</p>
                      <p className="mt-0.5 opacity-80">{errLines[errLines.length-1]}</p>
                    </div>
                  </div>
                )}

                {sys_d.ok && (
                  <Collapsible id="sys" icon={Cpu} title="System" color="#22d3ee">
                    <Row label="Hostname" value={sys_d.hostname}/>
                    <Row label="Python" value={sys_d.python}/>
                    {sys_d.cpu_count && <>
                      <Row label="CPU" value={`${sys_d.cpu_count} cores · ${sys_d.cpu_pct}% used`}/>
                      <Row label="Memory" value={`${sys_d.mem_used} / ${sys_d.mem_total} (${sys_d.mem_pct}%)`}
                           highlight={sys_d.mem_pct > 85 ? '#f87171' : undefined}/>
                      <Row label="Uptime" value={sys_d.uptime_human}/>
                    </>}
                    <Row label="Disk (root)" value={sys_d.disk_root_total ? `${sys_d.disk_root_used} / ${sys_d.disk_root_total} (${sys_d.disk_root_pct}%)` : '—'}/>
                    {!sys_d.psutil && <Row label="psutil" value="not installed — rebuild image for full metrics" highlight="#fbbf24"/>}
                  </Collapsible>
                )}

                {db.ok && (
                  <Collapsible id="db" icon={Database} title="Database" color="#22d3ee" badge={db.db_size}>
                    <Row label="Reclaimable space" value={db.db_reclaimable ? `${db.db_reclaimable} (${db.db_reclaimable_pct}%)` : undefined}
                         highlight={db.db_reclaimable_pct > 20 ? '#fbbf24' : undefined}/>
                    <div className="flex items-center gap-2 py-1">
                      <button onClick={runVacuum} disabled={vacuumRunning}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold"
                              style={{ background: 'var(--bg-raised)', color: 'var(--text-primary)', opacity: vacuumRunning ? 0.6 : 1 }}>
                        {vacuumRunning ? 'Running VACUUM\u2026' : 'Run VACUUM now'}
                      </button>
                      {vacuumResult && (
                        <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                          Reclaimed {vacuumResult.reclaimed} ({vacuumResult.size_before} → {vacuumResult.size_after})
                        </span>
                      )}
                      {vacuumError && <span className="text-xs" style={{ color: '#f87171' }}>{vacuumError}</span>}
                    </div>
                    <p className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
Reclaims space left by deletes and archives. The database is locked until it finishes, which can take a while on a big database, so run it when the site is quiet.
</p>
                    <div className="flex items-center gap-2 py-1">
                      <button onClick={runQueryPlan} disabled={queryPlanRunning}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold"
                              style={{ background: 'var(--bg-raised)', color: 'var(--text-primary)', opacity: queryPlanRunning ? 0.6 : 1 }}>
                        {queryPlanRunning ? 'Checking\u2026' : 'Check query plans'}
                      </button>
                      {queryPlanError && <span className="text-xs" style={{ color: '#f87171' }}>{queryPlanError}</span>}
                    </div>
                    <p className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
Checks whether the slowest queries use an index or scan the whole table, to tell whether database size is slowing things down.
</p>
                    {queryPlanResult && (
                      <div className="rounded-lg p-2 mt-1 space-y-1.5" style={{ background: 'var(--bg-panel)' }}>
                        <p className="text-xs font-medium" style={{ color: queryPlanResult.checks.some(c => c.concern) ? '#fbbf24' : '#4ade80' }}>
                          {queryPlanResult.summary}
                        </p>
                        {queryPlanResult.checks.map((c, i) => (
                          <div key={i} className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                            <span style={{ color: c.full_table_scan ? '#fbbf24' : '#4ade80' }}>
                              {c.full_table_scan ? 'SCAN' : 'INDEX'}
                            </span>
                            {' '}· {c.row_count?.toLocaleString()} rows · {c.label}
                          </div>
                        ))}
                      </div>
                    )}
                    <Row label="Total recordings" value={db.total_recordings?.toLocaleString()}/>
                    <Row label=" Bird" value={db.bird_recordings?.toLocaleString()}/>
                    <Row label=" Bat" value={db.bat_recordings?.toLocaleString()}/>
                    <Row label=" Haikubox" value={db.haikubox_recordings?.toLocaleString()}/>
                    <Row label="Last 24h / 7d / 30d" value={`${db.recordings_24h} / ${db.recordings_7d} / ${db.recordings_30d}`}/>
                    <Row label="Total detections" value={db.total_detections?.toLocaleString()}/>
                    <Row label="Species" value={db.total_species?.toLocaleString()}/>
                    <Row label="Profiles" value={`${db.enriched_profiles} / ${db.total_profiles} enriched`}/>
                    <Row label="Queue (pend/proc/err)" value={`${db.queue_pending} / ${db.queue_processing} / ${db.queue_errors}`}
                         highlight={db.queue_errors > 0 ? '#f87171' : db.queue_pending > 10 ? '#fbbf24' : undefined}/>
                    <Row label="Latest recording" value={db.latest_recording?.slice(0,10)} mono/>
                    {(db.top5_species||[]).length > 0 && <>
                      <p className="text-xs pt-1" style={{ color:'var(--text-tertiary)' }}>Top species:</p>
                      {db.top5_species.map(s => <Row key={s.name} label={` ${s.name}`} value={`${s.count}`}/>)}
                    </>}
                    {(db.profiles_missing_photo||[]).length > 0 && (
                      <Row label="Missing photos" value={db.profiles_missing_photo.join(', ')} highlight="#fbbf24"/>
                    )}
                  </Collapsible>
                )}

                {Object.keys(disk).length > 0 && (
                  <Collapsible id="disk" icon={HardDrive} title="Disk Usage" color="#f97316">
                    {disk.filesystem && !disk.filesystem.error && <>
                      <Row label="Total / Used / Free" value={`${disk.filesystem.total_human} / ${disk.filesystem.used_human} / ${disk.filesystem.free_human}`}/>
                      <Row label="Used %" value={`${disk.filesystem.used_pct}%`}
                           highlight={disk.filesystem.used_pct > 90 ? '#f87171' : disk.filesystem.used_pct > 75 ? '#fbbf24' : undefined}/>
                    </>}
                    {['recordings','spectrograms','clips','enhanced','bat_clips','media'].map(k => {
                      const d = disk[k]; if (!d) return null
                      return <Row key={k} label={k.charAt(0).toUpperCase()+k.slice(1).replace('_',' ')}
                                  value={d.exists ? `${d.size_human} · ${d.file_count} files` : 'not found'}/>
                    })}
                  </Collapsible>
                )}

                {sett.ok && (
                  <Collapsible id="sett" icon={Sliders} title="Settings" color="#a78bfa">
                    <Row label="Location" value={loc.latitude ? `${loc.latitude?.toFixed(4)}, ${loc.longitude?.toFixed(4)} (${loc.name||'unnamed'})` : 'not set'}
                         highlight={!loc.latitude ? '#fbbf24' : undefined}/>
                    <Row label="Timezone" value={sett.timezone}/>
                    <Row label="eBird key" value={sett.ebird_key_configured ? '✓ set' : '✗ not set'}
                         highlight={!sett.ebird_key_configured ? '#fbbf24' : '#4ade80'}/>
                    <Row label="iNat token" value={sett.inat_token_configured ? '✓ set' : '✗ not set'}/>
                    <Row label="Device keys" value={sett.device_keys_count}/>
                    <Row label="Auth" value={sett.auth_enabled ? 'enabled' : 'disabled'}/>
                    <Row label="Server re-analysis" value={sett.server_reanalyze_on_upload ? 'on' : 'off'}/>
                    <Row label="Manual re-analyze button" value={sett.allow_manual_reanalyze === false ? 'off' : 'on'}/>
                  </Collapsible>
                )}

                {cache.ok && (
                  <Collapsible id="cache" icon={Zap} title="Cache" color="#34d399">
                    {(cache.caches||[]).map(c => (
                      <Row key={c.name} label={c.name} value={`${c.entries}/${c.maxsize} entries · TTL ${c.ttl_s}s`}/>
                    ))}
                  </Collapsible>
                )}

                {devices.length > 0 && (
                  <Collapsible id="devices" icon={Cpu} title="Devices" color="#4ade80" badge={`${devices.length} registered`}>
                    {devices.map((dev, i) => (
                      <div key={dev.id||i} className="p-3 rounded-xl space-y-1 mb-2"
                           style={{ background:'var(--bg-raised)', border:'1px solid var(--border-subtle)' }}>
                        <div className="flex items-center gap-2 mb-1.5">
                          <StatusIcon status={dev.heartbeat_status}/>
                          <span className="text-sm font-semibold" style={{ color:'var(--text-primary)' }}>{dev.name}</span>
                          <span className="text-xs px-2 py-0.5 rounded-full capitalize ml-auto"
                                style={{ background: dev.heartbeat_status==='ok' ? 'rgba(74,222,128,.12)' : 'rgba(251,191,36,.12)', color: dev.heartbeat_status==='ok' ? '#4ade80' : '#fbbf24' }}>
                            {dev.heartbeat_status}
                          </span>
                        </div>
                        <Row label="Hostname / IP" value={`${dev.hostname||'?'} · ${dev.ip_address||'?'}`} mono/>
                        <Row label="Platform" value={dev.platform}/>
                        <Row label="Chirp-device ver" value={dev.device_version||'unknown'}/>
                        <Row label="BirdNET backend" value={dev.birdnet_backend||'cpu'}/>
                        <Row label="Coral" value={dev.coral_present ? `✓ ${dev.coral_form_factor||'usb'}` : '✗ none'}/>
                        <Row label="Microphones" value={`${dev.mic_count||0} — ${(dev.mic_names||[]).join(', ')||'?'}`}/>
                        <Row label="Last heartbeat" value={dev.last_heartbeat ? `${dev.last_heartbeat.slice(0,19).replace('T',' ')} (${dev.heartbeat_age} ago)` : 'never'} mono/>
                        <Row label="Last upload" value={dev.last_upload ? `${dev.last_upload.at?.slice(0,10)} · ${dev.last_upload.age} ago` : 'none'} mono/>
                        {dev.bat_status?.enabled && (
                          <Row label="Bat detector"
                               value={`${dev.bat_status.sample_rate ? (dev.bat_status.sample_rate/1000)+'kHz' : '?kHz'} · ${dev.bat_status.level_db != null ? dev.bat_status.level_db.toFixed(0) + 'dBFS' : '?'} · active_hours=${dev.bat_status.active_hours} · pulses=${dev.bat_status.pulses_seen} · events=${dev.bat_status.events_fired}${dev.bat_status.last_heartbeat_age_s != null && dev.bat_status.last_heartbeat_age_s > 180 ? ' ⚠️ stale' : ''}`}
                               mono/>
                        )}
                        <Row label="Server recs (24h/7d/all)" value={`${dev.recordings_24h}/${dev.recordings_7d}/${dev.total_recordings}`}/>
                        <Row label="Avg confidence" value={dev.avg_confidence ? `${dev.avg_confidence}%` : '—'}/>
                        <Row label="Config in sync" value={dev.config_in_sync === true ? '✓' : dev.config_in_sync === false ? '✗ pending' : '—'}
                             highlight={dev.config_in_sync === false ? '#fbbf24' : undefined}/>
                      </div>
                    ))}
                  </Collapsible>
                )}

                {micChecks.length > 0 && (
                  <Collapsible id="mic" icon={Mic} title={`Microphone Check (${micChecks.length} device${micChecks.length>1?'s':''})`} color="#fb7185">
                    {micChecks.map((mc, i) => (
                      <div key={i} className="mb-3 p-3 rounded-xl space-y-2"
                           style={{ background:'var(--bg-raised)', border:'1px solid var(--border-subtle)' }}>
                        <div className="flex items-center gap-2">
                          {mc.ok ? <CheckCircle2 size={13} style={{ color:'#4ade80' }}/> : <XCircle size={13} style={{ color:'#f87171' }}/>}
                          <span className="text-sm font-semibold" style={{ color:'var(--text-primary)' }}>{mc.device_name||'Device'}</span>
                          <span className="text-xs font-mono" style={{ color:'var(--text-tertiary)' }}>{mc.ip}</span>
                          {/* Live levels toggle */}
                          {mc.ok && mc.device_id && (
                            <button onClick={() => micLiveActive ? stopMicLive() : startMicLive(mc.device_id)}
                                    className="ml-auto text-xs px-3 py-1 rounded-lg flex items-center gap-1.5 transition-all"
                                    style={{
                                      background: micLiveActive ? 'rgba(248,113,113,.15)' : 'rgba(74,222,128,.12)',
                                      border: `1px solid ${micLiveActive ? 'rgba(248,113,113,.4)' : 'rgba(74,222,128,.3)'}`,
                                      color: micLiveActive ? '#f87171' : '#4ade80',
                                    }}>
                              <Mic size={11}/>
                              {micLiveActive ? 'Stop Live' : 'Live Levels'}
                            </button>
                          )}
                        </div>

                        {/* Live level meters + mini spectrogram waterfall */}
                        {micLiveActive && (
                          <div className="space-y-3 p-2 rounded-lg"
                               style={{ background:'rgba(0,0,0,.25)', border:'1px solid var(--border-subtle)' }}>
                            <div className="flex items-center gap-1.5">
                              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse inline-block flex-shrink-0"/>
                              <p className="text-xs font-semibold" style={{ color:'#4ade80' }}>Live Input Levels</p>
                              <span className="text-xs ml-auto" style={{ color:'var(--text-tertiary)', fontSize:10 }}>
                                arecord — chirp-device running normally
                              </span>
                            </div>

                            {/* Device-local status-server reachability — the single most useful
                                diagnostic line for the dsnoop/busy-device class of bug. Rendered
                                in its own dedicated state (see micLocalStatus) so the subsequent
                                "Connecting to..."/"Connected" SSH messages never overwrite it. */}
                            {micLocalStatus[mc.device_id] && (
                              <p className="text-xs font-mono" style={{ color: 'var(--text-tertiary)' }}>
                                {micLocalStatus[mc.device_id]}
                              </p>
                            )}

                            {/* Status message — reports whether chirp-device's local status
                                server was reachable and which mics it's covering. Always shown
                                (not just before the first row arrives): this is the one piece of
                                text that says whether a fix to the local-source path 
                                took effect on hardware, and hiding it the instant any row
                                streamed in made that impossible to see in practice. */}
                            {micStatus[mc.device_id] && (
                              <p className="text-xs font-mono" style={{ color:'var(--text-tertiary)' }}>
                                {micStatus[mc.device_id]}
                              </p>
                            )}

                            {(micLevels[mc.device_id] || []).map((lev, j) => {
                              const db = lev.db ?? -100
                              const pct = Math.max(0, Math.min(100, ((db + 80) / 80) * 100))
                              const peakPct = Math.max(0, Math.min(100, (((lev.peak??-100) + 80) / 80) * 100))
                              const barColor = db > -10 ? '#f87171' : db > -30 ? '#fbbf24' : '#4ade80'
                              const nl = (lev.name||'').toLowerCase()
                              const isBat = nl.includes('audiomoth') || (lev.sr||0) >= 96000
                              const isBird = !isBat && (nl.includes('respeaker') || nl.includes('xvf'))
                              const isExcl = nl.includes('unitek') || nl.includes('usb audio device') && !isBird && !isBat
                              const roleLabel = isBat ? 'Bat' : isBird ? 'Bird' : isExcl ? 'Excluded' : null
                              const RoleIcon = isBat ? BatIcon : isBird ? BirdIcon : null
                              const roleColor = isBat ? '#a78bfa' : isBird ? '#4ade80' : '#f87171'
                              const waterfall = micSpectro[mc.device_id]?.[lev.card] || []
                              const N = 32
                              // Listen is only meaningful for device_local rows (only
                              // status_server backs it — see device_listen()'s own docstring
                              // for why there's deliberately no SSH fallback). Both bird and
                              // bat mics are supported — the bat/AudioMoth clip is
                              // automatically downshifted server-side (see
                              // status_server.py's bat_listen_expansion_factor) into human
                              // hearing range, the same technique already used for
                              // post-hoc enhanced-clip review, so it's audible
                              // rather than near-silent ultrasonic content.
                              const canListen = (isBird || isBat) && lev.source === 'device_local'
                              const isListening = listeningTo?.deviceId === mc.device_id && listeningTo?.micName === lev.name

                              return (
                                <div key={j} className="space-y-1">
                                  {/* Device name + dBFS */}
                                  <div className="flex items-center justify-between text-xs">
                                    <div className="flex items-center gap-1.5 min-w-0">
                                      {roleLabel && (
                                        <span className="px-1.5 py-0.5 rounded flex-shrink-0 flex items-center gap-1"
                                              style={{ background:'rgba(255,255,255,.07)', color: roleColor, fontSize:9 }}>
                                          {RoleIcon ? <RoleIcon size={9}/> : <span>✗</span>}
                                          {roleLabel}
                                        </span>
                                      )}
                                      <span className="font-mono truncate" style={{ color:'var(--text-secondary)', fontSize:10 }}>
                                        [{lev.card}] {lev.name}
                                      </span>
                                      {lev.sr && (
                                        <span style={{ color:'var(--text-tertiary)', fontSize:9, flexShrink:0 }}>
                                          {(lev.sr/1000).toFixed(0)}kHz
                                        </span>
                                      )}
                                      {/* Source badge — makes it immediately visible whether this
                                          row came from chirp-device's own local status server (no
                                          second ALSA open, can't hit a busy-device error) or the SSH
                                          + arecord fallback (a second, separate open — can fail if
                                          chirp-device already holds that card exclusively). Without
                                          this, there's no way to tell from the UI alone whether a
                                          fix to the local-source path took effect on 
                                          hardware, or whether every row is still silently falling
                                          back to the old SSH path. */}
                                      <span className="flex-shrink-0 px-1 rounded"
                                            style={{
                                              fontSize: 8, lineHeight: '12px',
                                              color: lev.source === 'device_local' ? '#4ade80' : 'var(--text-tertiary)',
                                              background: lev.source === 'device_local' ? 'rgba(74,222,128,.12)' : 'rgba(255,255,255,.05)',
                                            }}
                                            title={lev.source === 'device_local'
                                              ? 'From chirp-device\u2019s own status server \u2014 no second ALSA open'
                                              : 'From SSH + arecord fallback \u2014 a second, separate device open'}>
                                        {lev.source === 'device_local' ? 'local' : 'ssh'}
                                      </span>
                                    </div>
                                    {lev.error
                                      ? <ExpandableError text={lev.error}/>
                                      : (
                                        <div className="flex items-center gap-1.5 flex-shrink-0" style={{ marginLeft: 8 }}>
                                          {canListen && (
                                            <button onClick={() => toggleListen(mc.device_id, lev.name)}
                                                    className="tactile-press flex items-center justify-center rounded-full transition-colors"
                                                    style={{
                                                      width: 24, height: 24,
                                                      background: isListening ? 'rgba(74,222,128,.2)' : 'var(--nav-active-bg)',
                                                      border: isListening ? '1px solid rgba(74,222,128,.5)' : '1px solid var(--border-default)',
                                                      boxShadow: isListening ? '0 0 8px rgba(74,222,128,.35)' : 'none',
                                                    }}
                                                    title={isListening ? `Stop listening to ${lev.name}` : isBat
                                                      ? `Listen to ${lev.name} \u2014 a few seconds of live ultrasonic audio, downshifted ~10x into human hearing range (slower and lower-pitched than its native speed/pitch)`
                                                      : `Listen to ${lev.name} \u2014 a few seconds of live audio, separate from the level reading`}>
                                              <Volume2 size={13} className={isListening ? 'animate-pulse' : ''}
                                                       style={{ color: isListening ? '#4ade80' : 'var(--accent-400)' }}/>
                                            </button>
                                          )}
                                          <span className="font-mono font-bold" style={{ color: barColor, fontSize:11 }}>
                                            {db.toFixed(1)} dBFS
                                          </span>
                                        </div>
                                      )}
                                  </div>

                                  {!lev.error && (<>
                                    {/* RMS bar with peak marker */}
                                    <div className="relative h-1.5 rounded-full overflow-hidden"
                                         style={{ background:'rgba(255,255,255,.05)' }}>
                                      <div className="absolute inset-y-0 left-0 rounded-full transition-all duration-100"
                                           style={{ width:`${pct}%`, background:`linear-gradient(90deg, #4ade80, ${barColor})` }}/>
                                      <div className="absolute top-0 bottom-0 w-0.5"
                                           style={{ left:`${peakPct}%`, background:'rgba(255,255,255,.7)' }}/>
                                    </div>

                                    {/* Waterfall spectrogram — N cols × rows canvas */}
                                    {waterfall.length > 0 && (
                                      <div style={{ height: 36, position:'relative', overflow:'hidden', borderRadius:3 }}>
                                        {waterfall.slice().reverse().map((row, ri) => (
                                          <div key={ri} style={{
                                            display:'flex', height: 36 / Math.max(waterfall.length, 1),
                                            position:'absolute', top: ri * (36 / waterfall.length),
                                            left:0, right:0,
                                          }}>
                                            {row.map((v, ci) => (
                                              <div key={ci} style={{
                                                flex:1,
                                                background: v === 0 ? 'transparent'
                                                  : `hsl(${140 - Math.round(v / 255 * 140)},90%,${20 + Math.round(v / 255 * 50)}%)`,
                                              }}/>
                                            ))}
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </>)}
                                </div>
                              )
                            })}
                          </div>
                        )}

                        {!mc.ok ? (
                          <p className="text-xs" style={{ color:'#f87171' }}>SSH failed: {mc.error}</p>
                        ) : (<>
                          <Row label="Service status" value={mc.service_status}
                               highlight={mc.service_status === 'active' ? '#4ade80' : '#f87171'}/>
                          <Row label="Total audio devices" value={mc.audio_devices?.length}/>

                          {mc.bird_mics?.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold mt-2 mb-1 flex items-center gap-1.5" style={{ color:'#4ade80' }}><BirdIcon size={12}/> Bird mics (BirdNET input)</p>
                              {mc.bird_mics.map((m,j) => {
                                const name = typeof m === 'string' ? m : m.name
                                const active = typeof m === 'string' ? null : m.live_active
                                const detail = typeof m === 'string' ? null : m.live_detail
                                const symbol = active === true ? '✓' : active === false ? '✗' : '?'
                                const color = active === true ? '#4ade80' : active === false ? '#f87171' : 'var(--text-tertiary)'
                                return (
                                  <p key={j} className="text-xs pl-2 font-mono" style={{ color:'var(--text-secondary)' }} title={detail || undefined}>
                                    <span style={{ color }}>{symbol}</span> {name}
                                    {active === false && <span style={{ color: '#f87171' }}> — not capturing</span>}
                                    {active === null && <span style={{ color: 'var(--text-tertiary)' }}> (name match only — unconfirmed live)</span>}
                                  </p>
                                )
                              })}
                            </div>
                          )}
                          {mc.bat_mics?.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold mt-2 mb-1 flex items-center gap-1.5" style={{ color:'#a78bfa' }}><BatIcon size={12}/> Bat mics (echolocation detector)</p>
                              {mc.bat_mics.map((m,j) => {
                                const name = typeof m === 'string' ? m : m.name
                                const active = typeof m === 'string' ? null : m.live_active
                                const detail = typeof m === 'string' ? null : m.live_detail
                                const symbol = active === true ? '✓' : active === false ? '✗' : '?'
                                const color = active === true ? '#4ade80' : active === false ? '#f87171' : 'var(--text-tertiary)'
                                return (
                                  <p key={j} className="text-xs pl-2 font-mono" style={{ color:'var(--text-secondary)' }} title={detail || undefined}>
                                    <span style={{ color }}>{symbol}</span> {name}
                                    {active === false && <span style={{ color: '#f87171' }}> — not capturing</span>}
                                    {active === null && <span style={{ color: 'var(--text-tertiary)' }}> (name match only — unconfirmed live)</span>}
                                  </p>
                                )
                              })}
                            </div>
                          )}
                          {mc.excluded_mics?.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold mt-2 mb-1" style={{ color:'#f87171' }}>✗ Excluded (skipped by config)</p>
                              {mc.excluded_mics.map((m,j) => <p key={j} className="text-xs pl-2 font-mono" style={{ color:'var(--text-tertiary)' }}>✗ {m}</p>)}
                            </div>
                          )}
                          {mc.unknown_mics?.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold mt-2 mb-1" style={{ color:'#fbbf24' }}>? Unknown classification</p>
                              {mc.unknown_mics.map((m,j) => <p key={j} className="text-xs pl-2 font-mono" style={{ color:'var(--text-tertiary)' }}>? {m}</p>)}
                            </div>
                          )}
                          {mc.journal_tail && (
                            <details className="mt-2">
                              <summary className="text-xs cursor-pointer" style={{ color:'var(--text-tertiary)' }}>Device log tail (last 30 lines)</summary>
                              <pre className="text-xs mt-1 p-2 rounded-lg overflow-auto max-h-48 whitespace-pre-wrap"
                                   style={{ background:'var(--bg-surface)', color:'var(--text-secondary)', fontSize:'10px' }}>
                                {mc.journal_tail}
                              </pre>
                            </details>
                          )}
                        </>)}
                      </div>
                    ))}
                  </Collapsible>
                )}

                <Collapsible id="micfreq" icon={AudioLines} title="Mic Frequency Response" color="#60a5fa">
                  <MicFrequencyResponse/>
                </Collapsible>

                <Collapsible id="phonemic" icon={AudioLines} title="Computer/Phone Mic Test" color="#60a5fa">
                  <PhoneMicTest/>
                </Collapsible>

                {errLines.length > 0 && (
                  <Collapsible id="errs" icon={AlertCircle} title={`Errors (${errLines.length})`} color="#f87171">
                    <div className="rounded-xl overflow-auto font-mono text-xs p-3"
                         style={{ background:'rgba(248,113,113,.05)', border:'1px solid rgba(248,113,113,.2)', maxHeight:200, color:'#f87171' }}>
                      {errLines.map((l,i) => <div key={i} className="whitespace-pre-wrap break-all leading-relaxed">{l}</div>)}
                    </div>
                  </Collapsible>
                )}

                {warnLines.length > 0 && (
                  <Collapsible id="warns" icon={AlertCircle} title={`Warnings (${warnLines.length})`} color="#fbbf24">
                    <div className="rounded-xl overflow-auto font-mono text-xs p-3"
                         style={{ background:'rgba(251,191,36,.05)', border:'1px solid rgba(251,191,36,.2)', maxHeight:160, color:'#fbbf24' }}>
                      {warnLines.slice(-10).map((l,i) => <div key={i} className="whitespace-pre-wrap break-all leading-relaxed">{l}</div>)}
                    </div>
                  </Collapsible>
                )}

                {logLines.length > 0 && (
                  <Collapsible id="logs" icon={Server} title={`Server Log Tail (${logLines.length} lines)`} color="#fb7185">
                    <div className="rounded-xl overflow-auto font-mono text-xs p-3"
                         style={{ background:'var(--bg-raised)', border:'1px solid var(--border-subtle)', maxHeight:360 }}>
                      {logLines.map((l,i) => (
                        <div key={i} className="whitespace-pre-wrap break-all leading-relaxed"
                             style={{ color: l.includes('[ERROR]')||l.includes('[CRITICAL]') ? '#f87171' : l.includes('[WARNING]') ? '#fbbf24' : 'var(--text-secondary)' }}>
                          {l}
                        </div>
                      ))}
                    </div>
                  </Collapsible>
                )}
              </div>
            )
          })()}
        </div>

      </>)}

      {/* Explicit stop marker for the tab show/hide DOM-walk below — the
          Diagnostics section (the last tab) has no "next GroupHeader" to
          stop at, and the floating Save button below is a DOM
          sibling of the section content that must never be hidden by
          tab switching. Walking until nextElementSibling is null instead
          of stopping here would incorrectly hide it. */}
      <div id="settings-tabs-end-sentinel" style={{ display: 'none' }}/>

        </div>
      </div>

      {isAdmin && (
        <SaveBar dirty={dirty} saving={saving} saved={saved} onSave={handleSave} onDiscard={discardChanges}/>
      )}
    </div>
  )
}
