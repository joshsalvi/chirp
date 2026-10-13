import { useEffect, useState, useCallback } from 'react'
import {
  BarChart, Bar, AreaChart, Area, LineChart, Line,
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Cell, Legend
} from 'recharts'
import { BarChart2, TrendingUp, Calendar, Clock, Award, Zap, Sun, Filter, Leaf, MessageCircle, Camera, Flame, ChevronUp, ChevronDown, Mic } from 'lucide-react'
import { BirdIcon, BatIcon } from './BirdBatIcons'
import { api, mediaUrl } from '../lib/api'
import UnifiedCard from './UnifiedCard'
import { isCardOpen, setCardOpen } from '../lib/cardState'

const METRIC_KEY = 'chirp:stats:metric'
const EXCLUDE_BATS_KEY = 'chirp:stats:excludeBats'
const DIVERSITY_WINDOW_KEY = 'chirp:stats:diversityWindow'
const DIVERSITY_WINDOW_LABELS = { '12': '12 months', '24': '24 months', all: 'All time' }
const DIVERSITY_WINDOW_BTN_LABELS = { '12': '12mo', '24': '24mo', all: 'All' }

const COLORS = ['#f97316','#22d3ee','#a78bfa','#4ade80','var(--pastel-amber)','#f472b6',
                '#34d399','#60a5fa','#fb7185','#a3e635','#e879f9','#67e8f9',
                'var(--pastel-green)','var(--pastel-yellow)','#fdba74','#c4b5fd','#6ee7b7','var(--pastel-blue)']
const SEASON_COLORS = { Spring:'#4ade80', Summer:'var(--pastel-amber)', Autumn:'#f97316', Winter:'#60a5fa' }
const HEATMAP_SIZES = [10, 25, 50, 100, 'All']
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

const ChirpTooltip = ({ active, payload, label, suffix='' }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="px-3 py-2 rounded-xl text-xs shadow-2xl"
         style={{ background:'var(--bg-card)', border:'1px solid var(--border-default)', minWidth:100 }}>
      {label !== undefined && <p className="font-semibold mb-1" style={{ color:'var(--text-primary)' }}>{label}</p>}
      {payload.map((p,i) => (
        <div key={i} className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full" style={{ background: p.color || p.fill }}/>
          <span style={{ color:'var(--text-secondary)' }}>{p.name || p.dataKey}:</span>
          <span className="font-bold" style={{ color:'var(--text-primary)' }}>
            {typeof p.value === 'number' ? p.value.toLocaleString() : p.value}{suffix}
          </span>
        </div>
      ))}
    </div>
  )
}

function ChartCard({ id, title, icon, color='var(--accent-400)', children, span=1, headerRight, fallbackOpen=true }) {
  return (
    <UnifiedCard id={id} title={title} icon={icon} color={color} span={span} headerRight={headerRight} fallbackOpen={fallbackOpen} variant="stripe">
      {children}
    </UnifiedCard>
  )
}

/**
 * Groups two related charts under ONE shared collapsible header, spanning
 * the full row width. Replaces the previous approach of two independent
 * ChartCards side by side in a 2-up grid — when only one of the pair was
 * collapsed, items-stretch correctly matched its box height to its taller
 * expanded neighbor, but that just left an awkward, mostly-empty stretched
 * card next to a full chart (reported directly from a screenshot). A
 * single shared toggle for the whole row avoids that case entirely: both
 * charts show or hide together, and a collapsed row shrinks to one compact
 * header bar instead of leaving any empty space.
 *
 * id: the row's own cardState key (e.g. 'stats:row-monthly-hourly') —
 * intentionally NOT either child's own id, since this is a new, distinct
 * collapsible unit with its own identity, not an alias for one of the two
 * charts it contains.
 */
function PairedRow({ id, title, leftIcon, leftColor = 'var(--accent-400)', singleColumn = false, headerRight, children }) {
  const [open, setOpen] = useState(() => isCardOpen(id, true))

  useEffect(() => {
    const onDefaultChange = () => setOpen(isCardOpen(id, true))
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

  const Icon = leftIcon
  return (
    <div className="card overflow-hidden lg:col-span-2" style={{ border: '1px solid var(--border-default)' }}>
      <div style={{ height: 3, background: `linear-gradient(90deg,${leftColor},transparent)` }}/>
      <button onClick={toggle}
              className="w-full flex items-center justify-between gap-2 text-left p-5"
              style={{ paddingBottom: open ? undefined : 20 }}>
        <div className="flex items-center gap-2.5">
          {Icon && (
            <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                 style={{ background: leftColor + '18', border: `1px solid ${leftColor}30` }}>
              <Icon size={14} style={{ color: leftColor }}/>
            </div>
          )}
          <h3 className="font-display font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>{title}</h3>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Same nested-interactive-inside-a-clickable-header pattern
              UnifiedCard.jsx's own headerRight already uses — stopping
              propagation here is what keeps a click on the control from
              also triggering the row's own collapse toggle. */}
          {headerRight && <span onClick={e => e.stopPropagation()}>{headerRight}</span>}
          {open
            ? <ChevronUp size={15} style={{ color: 'var(--text-tertiary)' }}/>
            : <ChevronDown size={15} style={{ color: 'var(--text-tertiary)' }}/>}
        </div>
      </button>
      {open && (
        <div className={`px-5 pb-5 grid grid-cols-1 ${singleColumn ? '' : 'md:grid-cols-2'} gap-6`}>
          {children}
        </div>
      )}
    </div>
  )
}

/** A single chart's content + its own sub-heading inside a PairedRow — no
 * card chrome of its own (no border, no collapse toggle), since the
 * shared PairedRow header already provides that for both halves. */
function PairedChart({ title, icon, color = 'var(--accent-400)', headerRight, children }) {
  const Icon = icon
  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          {Icon && <Icon size={13} style={{ color }}/>}
          <h4 className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text-tertiary)' }}>{title}</h4>
        </div>
        {headerRight}
      </div>
      {children}
    </div>
  )
}

function HeatCell({ value, max }) {
  const intensity = max > 0 ? value / max : 0
  const bg = intensity === 0 ? 'var(--bg-raised)' : `rgba(249,115,22,${0.1 + intensity * 0.85})`
  return (
    <div className="rounded text-center flex items-center justify-center"
         style={{ background: bg, color: intensity > 0.5 ? '#fff' : 'var(--text-secondary)',
                  minHeight: 26, fontSize: 9, lineHeight: 1 }}
         title={`${value}`}>
      {value > 0 ? value : ''}
    </div>
  )
}

export default function Statistics() {
  const [heatmapSize, setHeatmapSize] = useState(10)
  const [data, setData]     = useState(null)
  const [diversityData, setDiversityData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)
  const [dowNormalized, setDowNormalized] = useState(true)
  const [hourlyNormalized, setHourlyNormalized] = useState(false)
  const [metric, setMetric] = useState(() => {
    try { return localStorage.getItem(METRIC_KEY) || 'detections' } catch { return 'detections' }
  })
  const [excludeBats, setExcludeBats] = useState(() => {
    try { return localStorage.getItem(EXCLUDE_BATS_KEY) !== 'false' } catch { return true }
  })
  const [diversityWindow, setDiversityWindow] = useState(() => {
    try { return localStorage.getItem(DIVERSITY_WINDOW_KEY) || '12' } catch { return '12' }
  })

  const load = useCallback((size, m, eb) => {
    const limit = size === 'All' ? 500 : size
    setLoading(true)
    api.recordings.statistics(limit, m || metric, eb ?? excludeBats)
      .then(d => { setData(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [metric, excludeBats])

  useEffect(() => { load(heatmapSize, metric, excludeBats) }, [heatmapSize, metric, excludeBats])
  useEffect(() => {
    api.recordings.diversityTrend(diversityWindow).then(r => setDiversityData(r.months)).catch(() => {})
  }, [diversityWindow])
  const [streaksData, setStreaksData] = useState(null)
  useEffect(() => { api.recordings.speciesStreaks().then(setStreaksData).catch(() => {}) }, [])
  const [batData, setBatData] = useState(null)
  useEffect(() => { api.recordings.batActivity(30).then(setBatData).catch(() => {}) }, [])

  if (loading) return (
    <div className="page-root flex items-center justify-center min-h-64">
      <div className="flex flex-col items-center gap-3 animate-pulse">
        <BarChart2 size={28} style={{ color:'var(--accent-400)' }}/>
        <p className="text-sm" style={{ color:'var(--text-tertiary)' }}>Crunching the numbers…</p>
      </div>
    </div>
  )

  if (error || !data) return (
    <div className="page-root flex items-center justify-center min-h-64">
      <p className="text-sm" style={{ color:'var(--text-tertiary)' }}>{error || 'No data yet'}</p>
    </div>
  )

  const heatMax     = Math.max(1, ...Object.values(data.species_by_month || {}).flat())
  const topNames    = data.top10_names || []
  const totalDets   = (data.top_species || []).reduce((s, d) => s + d.count, 0)
  // Use total_species from the backend (authoritative distinct count).
  // data.top_species is capped at 30, so its .length is wrong for species counts.
  const uniqueSp    = data.total_species ?? data.top_species?.length ?? 0
  const peakMonth   = data.monthly ? [...data.monthly].sort((a,b) => b.count - a.count)[0] : null
  const peakHour    = data.hourly  ? [...data.hourly].sort((a,b) => b.count - a.count)[0] : null
  const peakDay     = data.day_of_week ? [...data.day_of_week].sort((a,b) => b.count - a.count)[0] : null

  const maxNameLen  = Math.max(0, ...(data.top_species||[]).map(s => s.name.length))
  const yAxisWidth  = Math.min(200, Math.max(100, maxNameLen * 6.5))

  const fmt12 = h => h == null ? '—' : h === 0 ? 'midnight' : h < 12 ? `${h}am` : h === 12 ? 'noon' : `${h-12}pm`

  const metricLabel = metric === 'recordings' ? 'Recordings' : 'Detections'
  const metricIcon  = metric === 'recordings' ? Mic : BirdIcon

  return (
    <div className="page-root space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="font-display text-2xl font-bold" style={{ color:'var(--text-primary)' }}>Statistics</h1>
          <p className="text-sm mt-0.5" style={{ color:'var(--text-tertiary)' }}>All-time {metric} analytics</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 flex-wrap w-full sm:w-auto">
          {/* Detections / Recordings toggle */}
          <div className="flex items-center rounded-xl overflow-hidden"
               style={{ border:'1px solid var(--border-subtle)' }}>
            {['detections','recordings'].map(m => (
              <button key={m} onClick={() => { try { localStorage.setItem(METRIC_KEY, m) } catch {} ; setMetric(m) }}
                      className={`seg-btn px-2.5 text-xs font-medium capitalize flex items-center gap-1 ${metric===m ? 'active' : ''}`}>
                {m === 'detections' ? <BirdIcon size={11}/> : <Mic size={11}/>}
                {m.charAt(0).toUpperCase() + m.slice(1)}
              </button>
            ))}
          </div>
          {/* Exclude bats toggle — bat recordings get a generic
              common_name of "Bat" (no bird species ID exists for them),
              which otherwise shows up as if it were a real species in
              every chart below. Bats already have their own dedicated
              Bat Activity section further down. Defaults to excluded.
              Ported from chirp-server. */}
          <button onClick={() => {
                    const next = !excludeBats
                    try { localStorage.setItem(EXCLUDE_BATS_KEY, String(next)) } catch {}
                    setExcludeBats(next)
                  }}
                  title={excludeBats ? 'Bats are excluded from these charts — click to include them' : 'Bats are included in these charts — click to exclude them'}
                  className={`seg-btn px-2.5 text-xs font-medium flex items-center gap-1.5 rounded-xl ${excludeBats ? 'active' : ''}`}
                  style={{ border: '1px solid var(--border-subtle)' }}>
            <BatIcon size={11}/> {excludeBats ? 'Bats excluded' : 'Bats included'}
          </button>
          <button onClick={() => load(heatmapSize, metric, excludeBats)} className="btn-ghost text-xs flex items-center gap-1.5">
            <Zap size={12}/> Refresh
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label:`Total ${metricLabel}`, value: totalDets.toLocaleString(), color:'#f97316', icon:metricIcon },
          { label:'Species Detected', value: uniqueSp.toString(),        color:'#22d3ee', icon:Award },
          { label:'Peak Month',       value: peakMonth ? MONTHS[peakMonth.month-1] : '—', color:'#a78bfa', icon:Calendar },
          { label:'Peak Hour',        value: peakHour ? fmt12(peakHour.hour) : '—', color:'#4ade80', icon:Clock },
        ].map(({ label, value, color, icon:Icon }) => (
          <div key={label} className="card p-4 text-center" style={{ border:'1px solid var(--border-subtle)' }}>
            <div className="w-8 h-8 rounded-lg flex items-center justify-center mx-auto mb-2" style={{ background: color+'18' }}>
              <Icon size={14} style={{ color }}/>
            </div>
            <p className="text-xl font-bold font-display" style={{ color }}>{value}</p>
            <p className="text-xs mt-0.5" style={{ color:'var(--text-tertiary)' }}>{label}</p>
          </div>
        ))}
      </div>

      {/* Fun facts — community & enrichment engagement */}
      {data.fun_stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label:'Submitted to iNaturalist', value: (data.fun_stats.inat_submitted_count||0).toLocaleString(), color:'var(--pastel-green)', icon:Leaf },
            { label:'Community Comments',       value: (data.fun_stats.comment_count||0).toLocaleString(),       color:'#60a5fa', icon:MessageCircle },
            { label:'Species with Photos',      value: (data.fun_stats.photo_count||0).toLocaleString(),         color:'var(--pastel-amber)', icon:Camera },
            { label:'Longest New-Species Streak', value: `${data.fun_stats.longest_new_species_streak_days||0}d`, color:'#fb7185', icon:Flame },
          ].map(({ label, value, color, icon:Icon }) => (
            <div key={label} className="card p-4 text-center" style={{ border:'1px solid var(--border-subtle)' }}>
              <div className="w-8 h-8 rounded-lg flex items-center justify-center mx-auto mb-2" style={{ background: color+'18' }}>
                <Icon size={14} style={{ color }}/>
              </div>
              <p className="text-xl font-bold font-display" style={{ color }}>{value}</p>
              <p className="text-xs mt-0.5" style={{ color:'var(--text-tertiary)' }}>{label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Rarest species + busiest day, grouped under one shared collapsible header */}
      {data.fun_stats && (data.fun_stats.rarest_species?.length > 0 || data.fun_stats.busiest_day) && (
        <PairedRow id="stats:row-rarest-busiest" title="Rarest Species & Busiest Day" leftIcon={Leaf} leftColor="#a78bfa"
                   singleColumn={!(data.fun_stats.rarest_species?.length > 0 && data.fun_stats.busiest_day)}>
          {data.fun_stats.rarest_species?.length > 0 && (
            <PairedChart title="Rarest species detected" icon={Leaf} color="#a78bfa">
              <div className="space-y-2">
                {data.fun_stats.rarest_species.map((s, i) => (
                  <div key={s.name} className="flex items-center justify-between text-sm py-1.5 px-2 rounded-lg"
                       style={{ background: i===0 ? 'rgba(167,139,250,0.08)' : 'transparent' }}>
                    <span style={{ color:'var(--text-secondary)' }}>{s.name}</span>
                    <span className="font-mono text-xs font-semibold" style={{ color:'#a78bfa' }}>
                      {s.count} detection{s.count===1?'':'s'}
                    </span>
                  </div>
                ))}
              </div>
            </PairedChart>
          )}
          {data.fun_stats.busiest_day && (
            <PairedChart title="Busiest day ever" icon={Flame} color="#f97316">
              <div className="flex items-center justify-center flex-col py-4">
                <p className="text-3xl font-bold font-display" style={{ color:'#f97316' }}>
                  {data.fun_stats.busiest_day.count}
                </p>
                <p className="text-sm mt-1" style={{ color:'var(--text-secondary)' }}>{metricLabel.toLowerCase()} on</p>
                <p className="text-sm font-semibold mt-0.5" style={{ color:'var(--text-primary)' }}>
                  {data.fun_stats.busiest_day.date}
                </p>
              </div>
            </PairedChart>
          )}
        </PairedRow>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">

        {/* Top species */}
        <ChartCard id="stats:top-species" title={`Top Species by ${metricLabel} (all time)`} icon={Award} color="#f97316" span={2}>
          <ResponsiveContainer width="100%" height={Math.max(320, (data.top_species?.length||0) * 30)}>
            <BarChart data={data.top_species||[]} layout="vertical"
                      margin={{ left:8, right:24, top:0, bottom:0 }}>
              <CartesianGrid horizontal={false} stroke="var(--border-subtle)"/>
              <XAxis type="number" tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false}/>
              <YAxis type="category" dataKey="name" width={yAxisWidth}
                     tick={{ fill:'var(--text-secondary)', fontSize:11 }} axisLine={false} tickLine={false}
                     interval={0}/>
              <Tooltip content={<ChirpTooltip/>}/>
              <Bar dataKey="count" name={metricLabel} radius={[0,4,4,0]} maxBarSize={22}>
                {(data.top_species||[]).map((_,i) => <Cell key={i} fill={COLORS[i%COLORS.length]}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Monthly + Hour of day */}
        <PairedRow id="stats:row-monthly-hourly" title={`${metricLabel} by Month & Hour of Day`} leftIcon={Calendar} leftColor="#22d3ee">
          <PairedChart title="By month" icon={Calendar} color="#22d3ee">
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={(data.monthly||[]).map((d,i) => ({ ...d, month: MONTHS[i] }))}>
                <defs>
                  <linearGradient id="monthGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#22d3ee" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3"/>
                <XAxis dataKey="month" tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false}/>
                <YAxis tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false} width={35}/>
                <Tooltip content={<ChirpTooltip/>}/>
                <Area type="monotone" dataKey="count" name={metricLabel} stroke="#22d3ee" fill="url(#monthGrad)" strokeWidth={2}/>
              </AreaChart>
            </ResponsiveContainer>
          </PairedChart>

          <PairedChart title="By hour of day" icon={Clock} color="#a78bfa"
            headerRight={
              <button
                onClick={() => setHourlyNormalized(v => !v)}
                className="text-xs px-2 py-1 rounded-lg transition-colors"
                style={{
                  background: hourlyNormalized ? 'rgba(167,139,250,0.15)' : 'var(--bg-raised)',
                  color: hourlyNormalized ? '#a78bfa' : 'var(--text-tertiary)',
                  border: `1px solid ${hourlyNormalized ? 'rgba(167,139,250,0.3)' : 'var(--border-subtle)'}`,
                }}
                title={hourlyNormalized
                  ? 'Showing detections per hour actually recorded — switch to raw counts'
                  : 'Showing raw detection counts — switch to per-hour-recorded'}>
                {hourlyNormalized ? 'Per hour recorded' : 'Raw counts'}
              </button>
            }>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={(data.hourly_normalized || data.hourly || []).map(d => {
                  const h = d.hour
                  const label = h === 0 ? '12 AM' : h < 12 ? `${h} AM` : h === 12 ? '12 PM' : `${h-12} PM`
                  return { ...d, hourLabel: label }
                })}>
                <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3"/>
                <XAxis dataKey="hourLabel" tick={{ fill:'var(--text-tertiary)', fontSize:9 }} axisLine={false} tickLine={false} interval={2}/>
                <YAxis tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false} width={35}/>
                <Tooltip content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div className="px-3 py-2 rounded-xl text-xs shadow-xl"
                         style={{ background:'var(--bg-card)', border:'1px solid var(--border-default)' }}>
                      <p className="font-semibold" style={{ color:'#a78bfa' }}>{d.hourLabel}</p>
                      {hourlyNormalized ? (
                        <>
                          <p style={{ color:'var(--text-secondary)' }}>{d.per_hour} {metricLabel.toLowerCase()}/hour</p>
                          <p style={{ color:'var(--text-tertiary)' }}>{d.count} total · {d.hours_recorded}h recorded</p>
                        </>
                      ) : (
                        <p style={{ color:'var(--text-secondary)' }}>{d.count} {metricLabel.toLowerCase()}</p>
                      )}
                    </div>
                  )
                }}/>
                <Bar dataKey={hourlyNormalized ? 'per_hour' : 'count'} name={hourlyNormalized ? `${metricLabel}/hour` : metricLabel} fill="#a78bfa" radius={[3,3,0,0]} maxBarSize={18}/>
              </BarChart>
            </ResponsiveContainer>
          </PairedChart>
        </PairedRow>

        {/* Seasonal + Day of week */}
        <PairedRow id="stats:row-seasonal-dow" title="Seasonal & Weekly Patterns" leftIcon={Sun} leftColor="#fbbf24">
          <PairedChart title="Seasonal distribution" icon={Sun} color="#fbbf24">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.seasonal||[]} barCategoryGap="30%">
                <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3"/>
                <XAxis dataKey="season" tick={{ fill:'var(--text-secondary)', fontSize:11 }} axisLine={false} tickLine={false}/>
                <YAxis tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false} width={40}/>
                <Tooltip content={<ChirpTooltip/>}/>
                <Bar dataKey="count" name={metricLabel} radius={[6,6,0,0]} maxBarSize={60}>
                  {(data.seasonal||[]).map((d,i) => <Cell key={i} fill={SEASON_COLORS[d.season]||'#f97316'}/>)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </PairedChart>

          <PairedChart title="By day of week" icon={Calendar} color="#4ade80"
            headerRight={
              <button
                onClick={() => setDowNormalized(v => !v)}
                className="text-xs px-2 py-1 rounded-lg transition-colors"
                style={{
                  background: dowNormalized ? 'rgba(74,222,128,0.15)' : 'var(--bg-raised)',
                  color: dowNormalized ? '#4ade80' : 'var(--text-tertiary)',
                  border: `1px solid ${dowNormalized ? 'rgba(74,222,128,0.3)' : 'var(--border-subtle)'}`,
                }}
                title={dowNormalized
                  ? 'Showing detections per hour actually recorded — switch to raw counts'
                  : 'Showing raw detection counts — switch to per-hour-recorded'}>
                {dowNormalized ? 'Per hour recorded' : 'Raw counts'}
              </button>
            }>
            <ResponsiveContainer width="100%" height={220}>
              <RadarChart data={data.day_of_week_normalized || data.day_of_week || []} cx="50%" cy="50%" outerRadius="70%">
                <PolarGrid stroke="var(--border-subtle)"/>
                <PolarAngleAxis dataKey="day" tick={{ fill:'var(--text-secondary)', fontSize:11 }}/>
                <Radar name={dowNormalized ? `${metricLabel}/hour` : metricLabel}
                       dataKey={dowNormalized ? 'per_hour' : 'count'}
                       stroke="#4ade80" fill="#4ade80" fillOpacity={0.25}/>
                <Tooltip content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div className="px-3 py-2 rounded-xl text-xs shadow-xl"
                         style={{ background:'var(--bg-card)', border:'1px solid var(--border-default)' }}>
                      <p className="font-semibold" style={{ color:'#4ade80' }}>{d.day}</p>
                      {dowNormalized ? (
                        <>
                          <p style={{ color:'var(--text-secondary)' }}>{d.per_hour} {metricLabel.toLowerCase()}/hour</p>
                          <p style={{ color:'var(--text-tertiary)' }}>{d.count} total · {d.hours_recorded}h recorded</p>
                        </>
                      ) : (
                        <p style={{ color:'var(--text-secondary)' }}>{d.count} {metricLabel.toLowerCase()}</p>
                      )}
                    </div>
                  )
                }}/>
              </RadarChart>
            </ResponsiveContainer>
          </PairedChart>
        </PairedRow>

        {/* Diversity indices — window selectable (12/24 months, or all
            time — see DIVERSITY_WINDOW_LABELS). Each on its own natural
            scale (Shannon ~0-4.5, Simpson/Evenness 0-1, richness
            uncapped) rather than forced onto one shared axis, since they
            measure genuinely different things. See yard-pulse's Shannon
            bands (Dashboard) for interpretation guidance — same bands
            used here, though the Dashboard's own card uses a rolling
            30-day window rather than calendar months like this chart
            does; deliberately different windows for different purposes,
            not an inconsistency. */}
        {diversityData && diversityData.some(m => m.species_richness > 0) && (
          <PairedRow id="stats:row-diversity" title={`Diversity Indices (${DIVERSITY_WINDOW_LABELS[diversityWindow] || diversityWindow})`} leftIcon={Leaf} leftColor="#4ade80"
                     headerRight={
                       <div className="flex items-center rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-subtle)' }}>
                         {['12', '24', 'all'].map(w => (
                           <button key={w}
                                   onClick={() => { try { localStorage.setItem(DIVERSITY_WINDOW_KEY, w) } catch {} ; setDiversityWindow(w) }}
                                   className={`seg-btn px-2 text-[11px] font-medium ${diversityWindow === w ? 'active' : ''}`}>
                             {DIVERSITY_WINDOW_BTN_LABELS[w]}
                           </button>
                         ))}
                       </div>
                     }>
            <PairedChart title="Species richness" icon={Leaf} color="#4ade80">
              <p className="text-xs mb-2" style={{ color: 'var(--text-tertiary)' }}>Distinct species detected each month — no theoretical ceiling.</p>
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={diversityData}>
                  <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3"/>
                  <XAxis dataKey="month" tick={{ fill:'var(--text-secondary)', fontSize:10 }} axisLine={false} tickLine={false}/>
                  <YAxis tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false} width={30}/>
                  <Tooltip content={<ChirpTooltip/>}/>
                  <Area type="monotone" dataKey="species_richness" name="Species" stroke="#4ade80" fill="#4ade8033" strokeWidth={2}/>
                </AreaChart>
              </ResponsiveContainer>
            </PairedChart>

            <PairedChart title="Shannon diversity (H')" icon={Leaf} color="#22d3ee">
              <p className="text-xs mb-2" style={{ color: 'var(--text-tertiary)' }}>Richness weighted by evenness. Real bird communities typically run 1.5–3.5; rarely above 4.</p>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={diversityData}>
                  <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3"/>
                  <XAxis dataKey="month" tick={{ fill:'var(--text-secondary)', fontSize:10 }} axisLine={false} tickLine={false}/>
                  <YAxis domain={[0, 4.5]} tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false} width={30}/>
                  <Tooltip content={<ChirpTooltip/>}/>
                  <Line type="monotone" dataKey="shannon_index" name="Shannon H'" stroke="#22d3ee" strokeWidth={2} dot={{ r:3 }} connectNulls/>
                </LineChart>
              </ResponsiveContainer>
            </PairedChart>

            <PairedChart title="Simpson's diversity (1-D)" icon={Leaf} color="#a78bfa">
              <p className="text-xs mb-2" style={{ color: 'var(--text-tertiary)' }}>Probability two random detections are different species. Bounded 0–1; weighted toward common species.</p>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={diversityData}>
                  <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3"/>
                  <XAxis dataKey="month" tick={{ fill:'var(--text-secondary)', fontSize:10 }} axisLine={false} tickLine={false}/>
                  <YAxis domain={[0, 1]} tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false} width={30}/>
                  <Tooltip content={<ChirpTooltip/>}/>
                  <Line type="monotone" dataKey="simpson_index" name="Simpson 1-D" stroke="#a78bfa" strokeWidth={2} dot={{ r:3 }} connectNulls/>
                </LineChart>
              </ResponsiveContainer>
            </PairedChart>

            <PairedChart title="Pielou's evenness (J')" icon={Leaf} color="var(--pastel-amber)">
              <p className="text-xs mb-2" style={{ color: 'var(--text-tertiary)' }}>Shannon's evenness component alone, independent of richness. Low + high richness means a few species dominate detections.</p>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={diversityData}>
                  <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3"/>
                  <XAxis dataKey="month" tick={{ fill:'var(--text-secondary)', fontSize:10 }} axisLine={false} tickLine={false}/>
                  <YAxis domain={[0, 1]} tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false} width={30}/>
                  <Tooltip content={<ChirpTooltip/>}/>
                  <Line type="monotone" dataKey="evenness" name="Evenness J'" stroke="var(--pastel-amber)" strokeWidth={2} dot={{ r:3 }} connectNulls/>
                </LineChart>
              </ResponsiveContainer>
            </PairedChart>
          </PairedRow>
        )}

        {/* Species streaks — active (current, unbroken) vs lifetime longest ever */}
        {streaksData && (streaksData.active.length > 0 || streaksData.lifetime.length > 0) && (
          <PairedRow id="stats:row-streaks" title="Species Streaks" leftIcon={Flame} leftColor="#f59e0b">
            <PairedChart title="Active now" icon={Flame} color="#f59e0b">
              <p className="text-xs mb-2" style={{ color: 'var(--text-tertiary)' }}>Consecutive days detected, ending today or yesterday — breaks the moment a full day is missed.</p>
              {streaksData.active.length > 0 ? (
                <div className="space-y-1.5">
                  {streaksData.active.map((s, i) => (
                    <div key={s.common_name} className="flex items-center gap-3 p-2 rounded-lg"
                         style={{ background: i === 0 ? 'rgba(245,158,11,.08)' : 'transparent' }}>
                      <div className="w-8 h-8 rounded-full overflow-hidden flex-shrink-0 flex items-center justify-center" style={{ background: 'var(--bg-raised)' }}>
                        {s.photo_url ? <img src={mediaUrl(s.photo_url)} alt="" className="w-full h-full object-cover"/> : <BirdIcon size={14} style={{ color: 'var(--text-tertiary)' }}/>}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{s.common_name}</p>
                        {s.scientific_name && <p className="text-xs italic truncate" style={{ color: 'var(--text-tertiary)' }}>{s.scientific_name}</p>}
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0" style={{ color: i === 0 ? '#f59e0b' : 'var(--text-secondary)' }}>
                        <Flame size={12}/><span className="text-sm font-bold">{s.streak_days}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <p className="text-sm py-4 text-center" style={{ color: 'var(--text-tertiary)' }}>No active streaks right now.</p>}
            </PairedChart>

            <PairedChart title="Lifetime longest" icon={Award} color="#c4b5fd">
              <p className="text-xs mb-2" style={{ color: 'var(--text-tertiary)' }}>The longest run each species has ever had, whether or not it's still going.</p>
              {streaksData.lifetime.length > 0 ? (
                <div className="space-y-1.5">
                  {streaksData.lifetime.map((s, i) => (
                    <div key={s.common_name} className="flex items-center gap-3 p-2 rounded-lg"
                         style={{ background: i === 0 ? 'rgba(196,181,253,.08)' : 'transparent' }}>
                      <div className="w-8 h-8 rounded-full overflow-hidden flex-shrink-0 flex items-center justify-center" style={{ background: 'var(--bg-raised)' }}>
                        {s.photo_url ? <img src={mediaUrl(s.photo_url)} alt="" className="w-full h-full object-cover"/> : <BirdIcon size={14} style={{ color: 'var(--text-tertiary)' }}/>}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{s.common_name}</p>
                        {s.scientific_name && <p className="text-xs italic truncate" style={{ color: 'var(--text-tertiary)' }}>{s.scientific_name}</p>}
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0" style={{ color: i === 0 ? '#c4b5fd' : 'var(--text-secondary)' }}>
                        <Award size={12}/><span className="text-sm font-bold">{s.streak_days}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <p className="text-sm py-4 text-center" style={{ color: 'var(--text-tertiary)' }}>Not enough history yet.</p>}
            </PairedChart>
          </PairedRow>
        )}

        {batData && batData.total > 0 && (
          <>
            <PairedRow id="stats:row-bat-nightly-hourly" title="Bat Activity — Nightly & Hourly" leftIcon={BatIcon} leftColor="#c4b5fd">
              <PairedChart title={`Nights active (last ${batData.nights_window})`} icon={BatIcon} color="#c4b5fd"
                           headerRight={
                             <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                               {batData.confirmed} confirmed{batData.interference_flagged > 0 ? ` · ${batData.interference_flagged} flagged` : ''}
                             </span>
                           }>
                {batData.by_night.length > 0 ? (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={batData.by_night}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)"/>
                      <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
                             tickFormatter={d => d.slice(5)}/>
                      <YAxis tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} allowDecimals={false}/>
                      <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 8, fontSize: 12 }}/>
                      <Bar dataKey="count" fill="#c4b5fd" radius={[4, 4, 0, 0]}/>
                    </BarChart>
                  </ResponsiveContainer>
                ) : <p className="text-sm py-8 text-center" style={{ color: 'var(--text-tertiary)' }}>No bat activity yet.</p>}
              </PairedChart>
              <PairedChart title="By hour of night" icon={Clock} color="#a78bfa">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={batData.by_hour.map((count, hour) => ({ hour, count }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)"/>
                    <XAxis dataKey="hour" tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
                           tickFormatter={h => `${h}:00`} interval={2}/>
                    <YAxis tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} allowDecimals={false}/>
                    <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 8, fontSize: 12 }}
                             labelFormatter={h => `${h}:00`}/>
                    <Bar dataKey="count" fill="#a78bfa" radius={[4, 4, 0, 0]}/>
                  </BarChart>
                </ResponsiveContainer>
              </PairedChart>
            </PairedRow>

            <PairedRow id="stats:row-bat-freq-species" title="Bat Call Frequency & Species" leftIcon={Zap} leftColor="#22d3ee">
              <PairedChart title="Peak frequency spread" icon={Zap} color="#22d3ee">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={Object.entries(batData.peak_freq_buckets).map(([band, count]) => ({ band, count }))} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)"/>
                    <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }} allowDecimals={false}/>
                    <YAxis type="category" dataKey="band" width={70} tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }}/>
                    <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 8, fontSize: 12 }}/>
                    <Bar dataKey="count" fill="#22d3ee" radius={[0, 4, 4, 0]}/>
                  </BarChart>
                </ResponsiveContainer>
              </PairedChart>
              <PairedChart title="Species identified" icon={BatIcon} color="#4ade80">
                {batData.species_breakdown.length > 0 ? (
                  <div className="space-y-2">
                    {batData.species_breakdown.map((s, i) => (
                      <div key={s.common_name} className="flex items-center gap-2 p-2 rounded-lg" style={{ background: 'var(--bg-raised)' }}>
                        <div className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'var(--bg-card)' }}>
                          <BatIcon size={14} style={{ color: 'var(--text-tertiary)' }}/>
                        </div>
                        <p className="text-sm font-medium flex-1 truncate" style={{ color: 'var(--text-primary)' }}>{s.common_name}</p>
                        <span className="text-sm font-bold flex-shrink-0" style={{ color: i === 0 ? '#4ade80' : 'var(--text-secondary)' }}>{s.count}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm py-8 text-center" style={{ color: 'var(--text-tertiary)' }}>
                    No species confidently identified yet — enable species classification in Settings → Experimental Features → Bat Echolocation Detection.
                  </p>
                )}
              </PairedChart>
            </PairedRow>
          </>
        )}

        {/* Confidence distribution + Activity by time period, grouped under one shared collapsible header */}
        <PairedRow id="stats:row-confidence-timeofday" title="Confidence & Time-of-Day Patterns" leftIcon={Filter} leftColor="#f472b6">
          <PairedChart title="Detection confidence distribution" icon={Filter} color="#f472b6">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.confidence||[]}>
                <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3"/>
                <XAxis dataKey="bucket" tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false}/>
                <YAxis tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false} width={40}/>
                <Tooltip content={<ChirpTooltip/>}/>
                <Bar dataKey="count" name={metricLabel} radius={[4,4,0,0]} maxBarSize={30}>
                  {(data.confidence||[]).map((_,i) => <Cell key={i} fill={`hsl(${200+i*16},80%,60%)`}/>)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </PairedChart>

          <PairedChart title="Activity by time of day" icon={Sun} color="#fbbf24">
            {(() => {
              const hourly = data.hourly || []
              const periods = [
                { label:'Pre-dawn (0–4h)',    hours:[0,1,2,3],          color:'#6366f1' },
                { label:'Dawn (4–7h)',         hours:[4,5,6],            color:'#22d3ee' },
                { label:'Morning (7–12h)',     hours:[7,8,9,10,11],      color:'#4ade80' },
                { label:'Afternoon (12–17h)', hours:[12,13,14,15,16],   color:'var(--pastel-amber)' },
                { label:'Evening (17–21h)',   hours:[17,18,19,20],      color:'#f97316' },
                { label:'Night (21–24h)',     hours:[21,22,23],         color:'#a78bfa' },
              ]
              const totals   = periods.map(p => ({ ...p, count: p.hours.reduce((s,h) => s + (hourly.find(x => x.hour===h)?.count||0), 0) }))
              const maxCount = Math.max(1, ...totals.map(t => t.count))
              const grand    = totals.reduce((s,t) => s+t.count, 0) || 1
              return (
                <div className="space-y-3 mt-1">
                  {totals.map(t => (
                    <div key={t.label} className="flex items-center gap-2">
                      <span className="text-xs flex-shrink-0 w-28 sm:w-36 truncate" style={{ color:'var(--text-tertiary)', fontSize: 10 }}>{t.label}</span>
                      <div className="flex-1 rounded-full overflow-hidden" style={{ height:10, background:'var(--bg-raised)' }}>
                        <div className="h-full rounded-full transition-all" style={{ width:`${Math.round(t.count/maxCount*100)}%`, background:t.color }}/>
                      </div>
                      <span className="text-xs w-14 text-right font-semibold flex-shrink-0" style={{ color:'var(--text-secondary)', fontSize: 10 }}>
                        {t.count} <span style={{ color:'var(--text-tertiary)', fontWeight:400 }}>({Math.round(t.count/grand*100)}%)</span>
                      </span>
                    </div>
                  ))}
                </div>
              )
            })()}
          </PairedChart>
        </PairedRow>

        {/* Life list growth */}
        {(data.cumulative_species?.length||0) > 0 && (
          <ChartCard id="stats:life-list-growth" title="Life List Growth Over Time" icon={TrendingUp} color="#34d399" span={2}>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={data.cumulative_species} margin={{ left:0, right:8, top:4, bottom:0 }}>
                <defs>
                  <linearGradient id="growthGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#34d399" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#34d399" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3"/>
                {/* type="category" with evenly-spaced points would make growth look linear
                    regardless of real elapsed time. The backend now sends one point per real
                    calendar day (or week, for long ranges) with the cumulative total carried
                    forward, so equal spacing here is actually correct — each tick IS a real day. */}
                <XAxis dataKey="date" tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false}
                       interval={Math.max(0, Math.floor((data.cumulative_species.length)/8))}/>
                <YAxis tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false} width={35}
                       allowDecimals={false}/>
                <Tooltip content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div className="px-3 py-2 rounded-xl text-xs shadow-xl"
                         style={{ background:'var(--bg-card)', border:'1px solid var(--border-default)' }}>
                      <p className="font-semibold" style={{ color:'#34d399' }}>{d.total} species</p>
                      {d.species && <p style={{ color:'var(--text-secondary)' }}>{d.species}</p>}
                      <p style={{ color:'var(--text-tertiary)' }}>{d.date}</p>
                    </div>
                  )
                }}/>
                <Area type="stepAfter" dataKey="total" name="Species" stroke="#34d399" fill="url(#growthGrad)" strokeWidth={2}/>
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {/* Per-species confidence — ALL species, dynamically sized + scrollable */}
        {(data.species_confidence?.length||0) > 0 && (
          <ChartCard id="stats:confidence-by-species" title={`Avg. Confidence by Species (${data.species_confidence.length})`} icon={Award} color="#fb7185" span={2}>
            <div style={{ maxHeight: 420, overflowY: 'auto' }}>
              <ResponsiveContainer width="100%" height={Math.max(260, data.species_confidence.length * 24)}>
                <BarChart data={data.species_confidence} layout="vertical"
                          margin={{ left:8, right:32, top:0, bottom:0 }}>
                  <CartesianGrid horizontal={false} stroke="var(--border-subtle)"/>
                  <XAxis type="number" domain={[0,100]} unit="%" tick={{ fill:'var(--text-tertiary)', fontSize:10 }} axisLine={false} tickLine={false}/>
                  <YAxis type="category" dataKey="name" width={150} interval={0}
                         tick={{ fill:'var(--text-secondary)', fontSize:10 }} axisLine={false} tickLine={false}/>
                  <Tooltip content={<ChirpTooltip suffix="%"/>}/>
                  <Legend wrapperStyle={{ fontSize:11, color:'var(--text-tertiary)' }}/>
                  <Bar dataKey="avg" name="Avg %" fill="#fb7185" radius={[0,3,3,0]} maxBarSize={14}/>
                  <Bar dataKey="max" name="Max %" fill="#fda4af" radius={[0,3,3,0]} maxBarSize={14} opacity={0.5}/>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </ChartCard>
        )}

        {/* Species × Month heatmap with size selector */}
        {topNames.length > 0 && (
          <ChartCard id="stats:species-month-heatmap" title={`Species × Month Heatmap (${metricLabel})`} icon={Calendar} color="#f97316" span={2}
                     headerRight={
                       <div className="flex items-center gap-1">
                         <span className="text-xs" style={{ color:'var(--text-tertiary)' }}>Top:</span>
                         {HEATMAP_SIZES.map(s => (
                           <button key={s} onClick={() => setHeatmapSize(s)}
                                   className="px-2 py-0.5 rounded text-xs font-medium transition-all"
                                   style={{
                                     background: heatmapSize===s ? 'var(--nav-active-bg)' : 'var(--bg-raised)',
                                     color: heatmapSize===s ? 'var(--accent-400)' : 'var(--text-tertiary)',
                                     border:`1px solid ${heatmapSize===s ? 'var(--accent-500)' : 'var(--border-subtle)'}`,
                                   }}>
                             {s}
                           </button>
                         ))}
                       </div>
                     }>
            <div className="overflow-x-auto -mx-1">
              <div style={{ minWidth: 380 }}>
                <div className="grid text-xs font-semibold mb-1 sticky top-0"
                     style={{ gridTemplateColumns:`90px repeat(12,1fr)`, color:'var(--text-tertiary)' }}>
                  <div/>
                  {MONTHS.map(m => <div key={m} className="text-center" style={{ fontSize: 9 }}>{m}</div>)}
                </div>
                {topNames.map(name => (
                  <div key={name} className="grid gap-0.5 mb-0.5 items-center"
                       style={{ gridTemplateColumns:`90px repeat(12,1fr)` }}>
                    <div className="text-xs truncate pr-1" style={{ color:'var(--text-secondary)', fontSize: 10 }} title={name}>{name}</div>
                    {((data.species_by_month||{})[name] || Array(12).fill(0)).map((v,mi) => (
                      <HeatCell key={mi} value={v} max={heatMax}/>
                    ))}
                  </div>
                ))}
                <div className="flex items-center gap-2 mt-3 text-xs" style={{ color:'var(--text-tertiary)' }}>
                  <div className="w-3 h-3 rounded" style={{ background:'var(--bg-raised)' }}/> None
                  <div className="w-3 h-3 rounded" style={{ background:'rgba(249,115,22,.4)' }}/> Few
                  <div className="w-3 h-3 rounded" style={{ background:'rgba(249,115,22,.95)' }}/> Many
                </div>
              </div>
            </div>
          </ChartCard>
        )}

        {/* Top Active Hours + Detection Summary, grouped under one shared collapsible header */}
        <PairedRow id="stats:row-active-hours-summary" title="Top Active Hours & Detection Summary" leftIcon={Clock} leftColor="#22d3ee">
          <PairedChart title="Top active hours" icon={Clock} color="#22d3ee">
            <div className="space-y-1.5">
              {[...(data.hourly||[])].sort((a,b) => b.count - a.count).slice(0,8).map((d,i) => {
                const max = Math.max(1, ...(data.hourly||[]).map(h => h.count))
                const hr = d.hour
                const label = hr === 0 ? 'Midnight' : hr < 12 ? `${hr}:00 AM` : hr === 12 ? '12:00 PM' : `${hr-12}:00 PM`
                return (
                  <div key={d.hour} className="flex items-center gap-2">
                    <span className="text-xs w-20 flex-shrink-0 text-right font-mono" style={{ color:'var(--text-tertiary)' }}>{label}</span>
                    <div className="flex-1 rounded-full overflow-hidden" style={{ height:8, background:'var(--bg-raised)' }}>
                      <div className="h-full rounded-full" style={{ width:`${Math.round(d.count/max*100)}%`, background:`hsl(${190+i*8},80%,55%)` }}/>
                    </div>
                    <span className="text-xs w-10 text-right font-semibold" style={{ color:'var(--text-secondary)' }}>{d.count}</span>
                  </div>
                )
              })}
            </div>
          </PairedChart>

          <PairedChart title={`${metricLabel} summary`} icon={Zap} color="#a78bfa">
            <div className="grid grid-cols-2 gap-2">
              {[
                { label:`Total ${metricLabel}`,  value: totalDets.toLocaleString() },
                { label:'Unique species',        value: uniqueSp.toString() },
                { label:'Peak hour',             value: peakHour ? fmt12(peakHour.hour) : '—' },
                { label:'Quietest hour',         value: (() => { const q = [...(data.hourly||[])].filter(h=>h.count>0).sort((a,b)=>a.count-b.count)[0]; return q ? fmt12(q.hour) : '—' })() },
                { label:'Peak month',            value: peakMonth ? MONTHS[peakMonth.month-1] : '—' },
                { label:'Most active day',       value: peakDay?.day || '—' },
                { label:`Avg per species`,       value: uniqueSp ? Math.round(totalDets/uniqueSp).toString() : '—' },
                { label:'Species per month',     value: data.monthly ? Math.round(data.monthly.filter(m=>m.count>0).length/12*uniqueSp).toString() : '—' },
              ].map(({ label, value }) => (
                <div key={label} className="p-2.5 rounded-lg" style={{ background:'var(--bg-raised)', border:'1px solid var(--border-subtle)' }}>
                  <p className="text-xs mb-0.5" style={{ color:'var(--text-tertiary)' }}>{label}</p>
                  <p className="text-sm font-bold" style={{ color:'var(--accent-400)' }}>{value}</p>
                </div>
              ))}
            </div>
          </PairedChart>
        </PairedRow>

      </div>
    </div>
  )
}
