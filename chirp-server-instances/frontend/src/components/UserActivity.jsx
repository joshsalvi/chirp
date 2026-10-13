import { useEffect, useState, useCallback } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  Activity, Users, LogIn, Eye, ShieldAlert, Circle, RefreshCw,
  ChevronLeft, ChevronRight, Filter,
} from 'lucide-react'
import { api } from '../lib/api'
import UnifiedCard from './UnifiedCard'
import { useTz } from '../lib/time'

const DAY_WINDOWS = [7, 30, 90]
const PAGE_SIZE = 25

const EVENT_LABELS = {
  login: 'Login',
  login_failed: 'Failed login',
  logout: 'Logout',
  page_view: 'Page view',
}
const EVENT_COLORS = {
  login: 'var(--pastel-green)',
  login_failed: '#fb7185',
  logout: 'var(--text-tertiary)',
  page_view: '#60a5fa',
}

function ChirpTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="px-3 py-2 rounded-xl text-xs shadow-2xl"
         style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', minWidth: 100 }}>
      {label !== undefined && <p className="font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>{label}</p>}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full" style={{ background: p.color || p.fill }} />
          <span style={{ color: 'var(--text-secondary)' }}>{p.name || p.dataKey}:</span>
          <span className="font-bold" style={{ color: 'var(--text-primary)' }}>
            {typeof p.value === 'number' ? p.value.toLocaleString() : p.value}
          </span>
        </div>
      ))}
    </div>
  )
}

function StatCard({ label, value, color, icon: Icon }) {
  return (
    <div className="card p-4 text-center" style={{ border: '1px solid var(--border-subtle)' }}>
      <div className="w-8 h-8 rounded-lg flex items-center justify-center mx-auto mb-2" style={{ background: color + '18' }}>
        <Icon size={14} style={{ color }} />
      </div>
      <p className="text-xl font-bold font-display" style={{ color }}>{value}</p>
      <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{label}</p>
    </div>
  )
}

function EventBadge({ type }) {
  const color = EVENT_COLORS[type] || 'var(--text-tertiary)'
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium"
          style={{ background: color + '18', color, border: `1px solid ${color}30` }}>
      {EVENT_LABELS[type] || type}
    </span>
  )
}

export default function UserActivity() {
  const [days, setDays] = useState(30)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const { fmtTs, fmtAgo } = useTz()

  // Raw feed — filterable, paginated
  const [feed, setFeed] = useState([])
  const [feedTotal, setFeedTotal] = useState(0)
  const [feedPage, setFeedPage] = useState(0)
  const [feedLoading, setFeedLoading] = useState(true)
  const [filterUser, setFilterUser] = useState('')
  const [filterType, setFilterType] = useState('')

  const loadSummary = useCallback((d) => {
    setLoading(true)
    api.auth.activity.summary(d)
      .then(setSummary)
      .catch(e => setError(e.message || 'Failed to load activity summary'))
      .finally(() => setLoading(false))
  }, [])

  const loadFeed = useCallback((page, userId, eventType) => {
    setFeedLoading(true)
    const params = { limit: PAGE_SIZE, offset: page * PAGE_SIZE }
    if (userId) params.user_id = userId
    if (eventType) params.event_type = eventType
    Promise.all([
      api.auth.activity.list(params),
      api.auth.activity.count(userId || eventType ? { user_id: userId || undefined, event_type: eventType || undefined } : {}),
    ])
      .then(([events, countRes]) => { setFeed(events); setFeedTotal(countRes.count) })
      .catch(() => { setFeed([]); setFeedTotal(0) })
      .finally(() => setFeedLoading(false))
  }, [])

  useEffect(() => { loadSummary(days) }, [days, loadSummary])
  useEffect(() => { loadFeed(feedPage, filterUser, filterType) }, [feedPage, filterUser, filterType, loadFeed])

  // Filter/user changes reset pagination to page 0
  useEffect(() => { setFeedPage(0) }, [filterUser, filterType])

  if (loading && !summary) return (
    <div className="page-root flex items-center justify-center min-h-64">
      <div className="flex flex-col items-center gap-3 animate-pulse">
        <Activity size={28} style={{ color: 'var(--accent-400)' }} />
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>Loading activity…</p>
      </div>
    </div>
  )

  if (error || !summary) return (
    <div className="page-root flex items-center justify-center min-h-64">
      <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>{error || 'No data yet'}</p>
    </div>
  )

  const { totals, per_user, daily_logins, top_pages } = summary
  const maxPageCount = Math.max(1, ...top_pages.map(p => p.count))
  const totalPages = Math.max(1, Math.ceil(feedTotal / PAGE_SIZE))

  return (
    <div className="page-root space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Activity</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
            Logins and page views, admin-only — no recording/note content, no passwords or tokens ever recorded.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <div className="flex items-center rounded-xl overflow-hidden"
               style={{ border: '1px solid var(--border-subtle)', background: 'var(--bg-raised)' }}>
            {DAY_WINDOWS.map(d => (
              <button key={d} onClick={() => setDays(d)}
                      className="px-2.5 py-1.5 text-xs font-medium transition-all"
                      style={{
                        background: days === d ? 'var(--nav-active-bg)' : 'transparent',
                        color: days === d ? 'var(--accent-400)' : 'var(--text-tertiary)',
                      }}>
                {d}d
              </button>
            ))}
          </div>
          <button onClick={() => { loadSummary(days); loadFeed(feedPage, filterUser, filterType) }}
                  className="btn-ghost text-xs flex items-center gap-1.5">
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard label="Online now"          value={totals.online_now}    color="var(--pastel-green)" icon={Circle} />
        <StatCard label={`Logins (${days}d)`} value={totals.logins}        color="#60a5fa"              icon={LogIn} />
        <StatCard label={`Page views (${days}d)`} value={totals.page_views.toLocaleString()} color="#a78bfa" icon={Eye} />
        <StatCard label={`Failed logins (${days}d)`} value={totals.failed_logins} color="#fb7185"        icon={ShieldAlert} />
        <StatCard label="Total users"         value={totals.total_users}   color="var(--pastel-amber)"  icon={Users} />
      </div>

      {/* Daily logins chart */}
      <UnifiedCard id="activity:daily-logins" title="Logins per day" icon={LogIn} color="#60a5fa" variant="stripe" fallbackOpen={true}>
        <div style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={daily_logins} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
                     tickFormatter={d => d.slice(5)} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }} allowDecimals={false} width={30} />
              <Tooltip content={<ChirpTooltip />} />
              <Bar dataKey="count" name="Logins" fill="#60a5fa" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </UnifiedCard>

      {/* Per-user table + top pages, side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <UnifiedCard id="activity:per-user" title="By user" icon={Users} color="var(--pastel-amber)" variant="stripe" fallbackOpen={true}>
          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: 'var(--text-tertiary)' }}>
                  <th className="text-left font-medium pb-2 px-1">User</th>
                  <th className="text-right font-medium pb-2 px-1">Logins</th>
                  <th className="text-right font-medium pb-2 px-1">Views</th>
                  <th className="text-right font-medium pb-2 px-1">Last active</th>
                </tr>
              </thead>
              <tbody>
                {per_user.map(u => (
                  <tr key={u.user_id} className="cursor-pointer transition-colors hover:opacity-80"
                      style={{ borderTop: '1px solid var(--border-subtle)' }}
                      onClick={() => setFilterUser(u.user_id)}>
                    <td className="py-2 px-1">
                      <div className="flex items-center gap-1.5">
                        <Circle size={7} fill={u.online_now ? 'var(--pastel-green)' : 'var(--border-default)'}
                                style={{ color: u.online_now ? 'var(--pastel-green)' : 'var(--border-default)' }} />
                        <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{u.username}</span>
                        <span className="capitalize" style={{ color: 'var(--text-tertiary)' }}>· {u.role}</span>
                      </div>
                    </td>
                    <td className="text-right py-2 px-1" style={{ color: 'var(--text-secondary)' }}>{u.login_count}</td>
                    <td className="text-right py-2 px-1" style={{ color: 'var(--text-secondary)' }}>{u.page_view_count}</td>
                    <td className="text-right py-2 px-1" style={{ color: 'var(--text-tertiary)' }}>
                      {u.last_activity ? fmtAgo(u.last_activity) : 'never'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </UnifiedCard>

        <UnifiedCard id="activity:top-pages" title="Most-visited pages" icon={Eye} color="#a78bfa" variant="stripe" fallbackOpen={true}>
          <div className="space-y-2">
            {top_pages.length === 0 && (
              <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>No page views recorded in this window.</p>
            )}
            {top_pages.map(p => (
              <div key={p.path} className="flex items-center gap-2">
                <span className="text-xs font-mono flex-shrink-0 w-28 truncate" style={{ color: 'var(--text-secondary)' }} title={p.path}>
                  {p.path}
                </span>
                <div className="flex-1 h-4 rounded-full overflow-hidden" style={{ background: 'var(--bg-raised)' }}>
                  <div className="h-full rounded-full" style={{ width: `${(p.count / maxPageCount) * 100}%`, background: '#a78bfa' }} />
                </div>
                <span className="text-xs w-8 text-right flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>{p.count}</span>
              </div>
            ))}
          </div>
        </UnifiedCard>
      </div>

      {/* Raw activity feed — filterable, paginated */}
      <UnifiedCard id="activity:feed" title="Activity feed" icon={Activity} color="var(--accent-400)" variant="stripe" fallbackOpen={true}>
        <div className="flex items-center gap-1.5 mb-3">
          <Filter size={11} style={{ color: 'var(--text-tertiary)' }} />
          <select value={filterUser} onChange={e => setFilterUser(e.target.value)}
                  className="input text-xs py-1 px-2" style={{ minWidth: 100 }}>
            <option value="">All users</option>
            {per_user.map(u => <option key={u.user_id} value={u.user_id}>{u.username}</option>)}
          </select>
          <select value={filterType} onChange={e => setFilterType(e.target.value)}
                  className="input text-xs py-1 px-2" style={{ minWidth: 100 }}>
            <option value="">All events</option>
            {Object.keys(EVENT_LABELS).map(t => <option key={t} value={t}>{EVENT_LABELS[t]}</option>)}
          </select>
          {(filterUser || filterType) && (
            <button onClick={() => { setFilterUser(''); setFilterType('') }} className="btn-ghost text-xs">
              Clear
            </button>
          )}
        </div>
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ color: 'var(--text-tertiary)' }}>
                <th className="text-left font-medium pb-2 px-1">When</th>
                <th className="text-left font-medium pb-2 px-1">User</th>
                <th className="text-left font-medium pb-2 px-1">Event</th>
                <th className="text-left font-medium pb-2 px-1">Path</th>
                <th className="text-left font-medium pb-2 px-1">IP</th>
              </tr>
            </thead>
            <tbody>
              {feedLoading && (
                <tr><td colSpan={5} className="text-center py-6" style={{ color: 'var(--text-tertiary)' }}>Loading…</td></tr>
              )}
              {!feedLoading && feed.length === 0 && (
                <tr><td colSpan={5} className="text-center py-6" style={{ color: 'var(--text-tertiary)' }}>No events match these filters.</td></tr>
              )}
              {!feedLoading && feed.map(e => (
                <tr key={e.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <td className="py-2 px-1 whitespace-nowrap" style={{ color: 'var(--text-tertiary)' }} title={fmtTs(e.created_at)}>
                    {fmtAgo(e.created_at)}
                  </td>
                  <td className="py-2 px-1" style={{ color: 'var(--text-primary)' }}>{e.username || '—'}</td>
                  <td className="py-2 px-1"><EventBadge type={e.event_type} /></td>
                  <td className="py-2 px-1 font-mono" style={{ color: 'var(--text-secondary)' }}>{e.path || '—'}</td>
                  <td className="py-2 px-1" style={{ color: 'var(--text-tertiary)' }}>{e.ip_address || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between mt-3 pt-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            {feedTotal.toLocaleString()} event{feedTotal === 1 ? '' : 's'} · page {feedPage + 1} of {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <button onClick={() => setFeedPage(p => Math.max(0, p - 1))} disabled={feedPage === 0}
                    className="btn-icon" style={{ opacity: feedPage === 0 ? 0.4 : 1 }}>
              <ChevronLeft size={14} />
            </button>
            <button onClick={() => setFeedPage(p => Math.min(totalPages - 1, p + 1))} disabled={feedPage >= totalPages - 1}
                    className="btn-icon" style={{ opacity: feedPage >= totalPages - 1 ? 0.4 : 1 }}>
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </UnifiedCard>
    </div>
  )
}
