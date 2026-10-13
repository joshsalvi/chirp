import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { MessageSquare, Mic, Search, X } from 'lucide-react'
import { BirdIcon } from './BirdBatIcons'
import { api } from '../lib/api'
import { NoteActions } from './Comments'

function timeAgo(isoStr) {
  if (!isoStr) return ''
  const diff = (Date.now() - new Date(isoStr + (isoStr.endsWith('Z') ? '' : 'Z'))) / 1000
  if (diff < 60)    return 'just now'
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export default function AllNotes() {
  const [notes,   setNotes]   = useState([])
  const [loading, setLoading] = useState(true)
  const [search,  setSearch]  = useState('')
  const [me,      setMe]      = useState(null)
  useEffect(() => {
    api.auth.me().then(r => (r?.json ? r.json() : r)).then(u => setMe(u?.username || null)).catch(() => {})
  }, [])

  useEffect(() => {
    api.birds.recentComments(500)
      .then(data => setNotes(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const filtered = search
    ? notes.filter(n =>
        n.body?.toLowerCase().includes(search.toLowerCase()) ||
        n.author?.toLowerCase().includes(search.toLowerCase()) ||
        n.context_name?.toLowerCase().includes(search.toLowerCase())
      )
    : notes

  return (
    <div className="page-root max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <MessageSquare size={18} style={{ color: 'var(--accent-400)' }}/>
          <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
            All Notes
          </h1>
        </div>
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
          {loading ? 'Loading…' : `${notes.length} note${notes.length !== 1 ? 's' : ''} across all recordings and bird profiles`}
        </p>
      </div>

      {/* Search */}
      <div className="relative mb-5">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-tertiary)' }}/>
        <input className="input w-full pl-8 pr-8 text-sm" placeholder="Search notes, authors, or species…"
               value={search} onChange={e => setSearch(e.target.value)}/>
        {search && (
          <button onClick={() => setSearch('')} className="tactile-press absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--text-tertiary)' }}>
            <X size={14}/>
          </button>
        )}
      </div>

      {/* List */}
      {loading ? (
        <div className="space-y-3">
          {[0,1,2,3].map(i => <div key={i} className="skeleton h-20 rounded-xl"/>)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="card p-10 text-center">
          <MessageSquare size={28} className="mx-auto mb-3" style={{ color: 'var(--text-tertiary)' }}/>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {search ? 'No notes match your search.' : 'No notes have been posted yet.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(n => (
            <Link key={n.id} to={n.context_url || '#'} className="block" style={{ textDecoration: 'none' }}>
              <div className="card-hover p-4 transition-all"
                   style={{ border: '1px solid var(--border-subtle)' }}>
                <div className="flex items-start gap-3">
                  {/* Avatar */}
                  <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold"
                       style={{ background: 'var(--nav-active-bg)', color: 'var(--accent-400)' }}>
                    {(n.author || 'A')[0].toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    {/* Meta row */}
                    <div className="flex items-center gap-1.5 flex-wrap mb-1.5">
                      <span className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
                        {n.author || 'Anonymous'}
                      </span>
                      <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>on</span>
                      <span className="flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full"
                            style={{
                              background: n.context_type === 'bird' ? 'rgba(167,139,250,.12)' : 'rgba(34,197,94,.1)',
                              color: n.context_type === 'bird' ? '#c4b5fd' : 'var(--pastel-green)',
                              border: `1px solid ${n.context_type === 'bird' ? 'rgba(167,139,250,.25)' : 'rgba(34,197,94,.2)'}`,
                            }}>
                        {n.context_type === 'bird' ? <BirdIcon size={10}/> : <Mic size={10}/>}
                        {n.context_name}
                      </span>
                      <span className="text-xs ml-auto" style={{ color: 'var(--text-tertiary)' }}>
                        {timeAgo(n.created_at)}
                      </span>
                      {me && (n.author || '').toLowerCase() !== me.toLowerCase() && (
                        // inside a link: keep taps here from opening the note's page
                        <span onClick={e => { e.preventDefault(); e.stopPropagation() }}>
                          <NoteActions c={n} onBlocked={author => setNotes(prev => prev.filter(x => x.author !== author))}/>
                        </span>
                      )}
                    </div>
                    {/* Body */}
                    <p className="text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                      {n.body}
                    </p>
                  </div>
                </div>
              </div>
            </Link>
          ))}
          {filtered.length > 0 && search && (
            <p className="text-xs text-center pt-2" style={{ color: 'var(--text-tertiary)' }}>
              {filtered.length} of {notes.length} notes
            </p>
          )}
        </div>
      )}
    </div>
  )
}
