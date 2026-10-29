// Global Admin: messages from the app's Help & feedback (and, on ourchirp.com,
// the support and About pages). Shown under Requests on ourchirp.com and as
// Messages elsewhere.
import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const muted = { color: 'var(--text-tertiary)' }

const KIND_LABEL = { question: 'Question', problem: 'Problem', feature: 'Feature idea', testflight: 'TestFlight', other: 'Other' }

export default function SupportMessagesCard() {
  const [rows, setRows] = useState(null)
  const [showDone, setShowDone] = useState(false)
  const [error, setError] = useState(null)
  useEffect(() => { api.admin.supportMessages().then(setRows).catch(e => setError(e.message)) }, [])
  const mark = (m, done) => api.admin.markSupportMessage(m.id, done).then(u => setRows(rs => rs.map(x => x.id === u.id ? u : x)))
  const remove = (m) => api.admin.deleteSupportMessage(m.id).then(() => setRows(rs => rs.filter(x => x.id !== m.id)))
  const shown = (rows || []).filter(m => showDone || !m.done)
  const open = (rows || []).filter(m => !m.done).length
  return (
    <div className="card px-4 py-3 space-y-3 min-w-0" style={{ border: '1px solid var(--border-subtle)', overflowWrap: 'anywhere' }}>
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Messages{rows ? ` · ${open} open` : ''}</p>
          <p className="text-xs" style={muted}>From Help &amp; Feedback in the app (and, on ourchirp.com, its support and About pages).</p>
        </div>
        <button className="text-xs" style={muted} onClick={() => setShowDone(v => !v)}>{showDone ? 'Hide done' : 'Show done'}</button>
      </div>
      {error && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{error}</p>}
      {rows && shown.length === 0 && <p className="text-xs" style={muted}>No {showDone ? '' : 'open '}messages.</p>}
      {shown.map(m => (
        <div key={m.id} className="p-2.5 rounded-lg space-y-1" style={{ background: 'var(--bg-subtle)', opacity: m.done ? 0.55 : 1 }}>
          <div className="flex items-center gap-2 flex-wrap text-xs">
            <span className="px-1.5 py-0.5 rounded-full font-semibold uppercase text-[10px]"
                  style={m.kind === 'feature' ? { background: 'rgba(251,191,36,.14)', color: 'var(--pastel-amber)' }
                       : m.kind === 'problem' ? { background: 'rgba(248,113,113,.12)', color: '#f87171' }
                       : m.kind === 'testflight' ? { background: 'rgba(96,165,250,.14)', color: '#93c5fd' }
                       : { background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>{KIND_LABEL[m.kind] || m.kind}</span>
            <span style={{ color: 'var(--text-primary)' }}>{m.name || m.username || m.email}</span>
            {m.email && <a href={`mailto:${m.email}`}>{m.email}</a>}
            {m.site && <span style={muted}>· {m.site}</span>}
            <span className="ml-auto" style={muted}>{new Date(m.created_at + 'Z').toLocaleString()}</span>
          </div>
          <p className="text-sm whitespace-pre-wrap" style={{ color: 'var(--text-secondary)' }}>{m.message}</p>
          <div className="flex gap-3 text-xs">
            <button style={{ color: 'var(--accent-400)' }} onClick={() => mark(m, !m.done)}>{m.done ? 'Reopen' : 'Mark done'}</button>
            <button style={muted} onClick={() => { if (confirm('Delete this message?')) remove(m) }}>Delete</button>
          </div>
        </div>
      ))}
    </div>
  )
}
