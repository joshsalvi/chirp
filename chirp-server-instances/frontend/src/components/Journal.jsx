/** The Daily and Weekly Journal in full: where journal push notifications open. */
import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { Sparkles, BookOpen, ArrowLeft } from 'lucide-react'
import { api } from '../lib/api'

function Entry({ icon: Icon, title, sub, data, highlight }) {
  if (!data?.enabled) return null
  return (
    <section className="card p-4" style={highlight ? { borderColor: 'var(--accent-400)' } : undefined}>
      <div className="flex items-center gap-2 mb-1">
        <Icon size={16} style={{ color: 'var(--accent-400)' }}/>
        <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)', fontFamily: "'Lora', serif" }}>{title}</h2>
      </div>
      {sub && <p className="text-xs mb-3" style={{ color: 'var(--text-tertiary)' }}>{sub}</p>}
      <p className="text-[15px] whitespace-pre-line" style={{ color: 'var(--text-secondary)', lineHeight: 1.7, fontFamily: "'Lora', serif" }}>
        {data.text || 'Nothing written yet.'}
      </p>
    </section>
  )
}

export default function Journal() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const which = params.get('entry') || 'daily'
  const [daily, setDaily] = useState(null)
  const [weekly, setWeekly] = useState(null)
  useEffect(() => {
    api.recordings.dailyJournal().then(setDaily).catch(() => setDaily({ enabled: false }))
    api.recordings.weeklyJournal().then(setWeekly).catch(() => setWeekly({ enabled: false }))
  }, [])
  const dailySub = daily?.generated_at
    ? new Date(daily.generated_at + 'Z').toLocaleString([], { weekday: 'long', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : null
  const weeklySub = weekly?.period_start && weekly?.period_end
    ? `Week of ${new Date(weekly.period_start + 'Z').toLocaleDateString([], { month: 'short', day: 'numeric' })} – ${new Date(weekly.period_end + 'Z').toLocaleDateString([], { month: 'short', day: 'numeric' })}` : null
  const entries = [
    <Entry key="daily" icon={Sparkles} title="Daily Journal" sub={dailySub} data={daily} highlight={which === 'daily'}/>,
    <Entry key="weekly" icon={BookOpen} title="Weekly Journal" sub={weeklySub} data={weekly} highlight={which === 'weekly'}/>,
  ]
  return (
    <div className="max-w-2xl mx-auto px-4 md:px-6 py-5 md:py-8 space-y-4 animate-fade-in">
      <button className="btn-ghost text-sm flex items-center gap-1.5 -ml-2" onClick={() => navigate('/')}><ArrowLeft size={14}/> Dashboard</button>
      <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Journal</h1>
      {which === 'weekly' ? entries.reverse() : entries}
      {daily && weekly && !daily.enabled && !weekly.enabled && (
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>The journal is turned off for this site.</p>
      )}
      <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--text-tertiary)' }}>AI-generated · Experimental</p>
    </div>
  )
}
