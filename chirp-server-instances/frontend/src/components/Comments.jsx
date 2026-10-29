/**
 * Shared Comments component — used on BirdProfile, RecordingDetail, and Dashboard.
 * Supports edit and delete for the author (or admin), and Report / Block
 * on other people's notes (api/moderation.py).
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { Send, Trash2, MessageSquare, Pencil, Check, X, MoreHorizontal, Flag, UserX } from 'lucide-react'
import { api, mediaUrl } from '../lib/api'
import { hapticEvent } from '../lib/haptics'

// A note author's profile photo (author_photo_url), or their initial.
// Shared with All Notes and the dashboard's Recent comments.
export function AuthorAvatar({ name, photo, size = 28, accent = false, style }) {
  const [failed, setFailed] = useState(false)
  const box = { width: size, height: size, ...style }
  if (photo && !failed) {
    return <img src={mediaUrl(photo)} alt="" onError={() => setFailed(true)}
                className="rounded-full flex-shrink-0 object-cover" style={{ ...box, background: 'var(--bg-raised)' }}/>
  }
  return (
    <div className="rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold"
         style={{ ...box, background: accent ? 'var(--nav-active-bg)' : 'var(--bg-raised)',
                  color: accent ? 'var(--accent-400)' : 'var(--text-secondary)' }}>
      {(name || 'A')[0].toUpperCase()}
    </div>
  )
}

// Report or block, for a note someone else wrote. Shared with All Notes.
export function NoteActions({ c, onBlocked }) {
  const [mode, setMode] = useState(null) // null | 'menu' | 'report' | 'block' | 'reported'
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const author = c.author || 'Anonymous'
  const sendReport = async () => {
    setBusy(true)
    try { await api.moderation.report(c.id, reason.trim() || null); setMode('reported'); hapticEvent('success') } catch {}
    setBusy(false)
  }
  const block = async () => {
    setBusy(true)
    try { await api.moderation.block(author); hapticEvent('success'); onBlocked?.(author) } catch {}
    setBusy(false)
  }
  const box = { background: 'var(--bg-card)', border: '1px solid var(--border-default)' }
  if (mode === 'reported') return <span className="text-xs" style={{ color: 'var(--accent-400)' }}>Reported</span>
  return (
    <span className="relative inline-flex">
      <button onClick={() => setMode(m => (m ? null : 'menu'))} aria-label={`Note options for ${author}`}
              className="p-0.5" style={{ color: 'var(--text-tertiary)' }}>
        <MoreHorizontal size={14}/>
      </button>
      {mode && (
        <div className="absolute right-0 top-full z-30 mt-1 w-64 rounded-lg p-2.5 space-y-2 text-xs"
             style={{ ...box, boxShadow: '0 8px 24px rgba(0,0,0,.35)' }}>
          {mode === 'menu' && (
            <div className="flex flex-col">
              <button onClick={() => setMode('report')} className="flex items-center gap-2 py-1.5 text-left" style={{ color: 'var(--text-primary)' }}>
                <Flag size={13}/> Report this note
              </button>
              <button onClick={() => setMode('block')} className="flex items-center gap-2 py-1.5 text-left" style={{ color: 'var(--pastel-red)' }}>
                <UserX size={13}/> Block {author}
              </button>
            </div>
          )}
          {mode === 'report' && (
            <>
              <p style={{ color: 'var(--text-secondary)' }}>Tell the site's admins what's wrong (optional).</p>
              <textarea className="input w-full text-sm" rows={2} value={reason} onChange={e => setReason(e.target.value)}
                        placeholder="Spam, offensive, wrong bird…" style={{ fontSize: 16 }}/>
              <div className="flex gap-2">
                <button onClick={sendReport} disabled={busy} className="btn-primary" style={{ padding: '4px 10px', fontSize: 12 }}>Send report</button>
                <button onClick={() => setMode(null)} className="btn-ghost" style={{ padding: '4px 8px', fontSize: 12 }}>Cancel</button>
              </div>
            </>
          )}
          {mode === 'block' && (
            <>
              <p style={{ color: 'var(--text-secondary)' }}>You won't see notes from {author} anywhere in Chirp. You can unblock them in Account.</p>
              <div className="flex gap-2">
                <button onClick={block} disabled={busy} className="btn-primary" data-haptic="heavy" style={{ padding: '4px 10px', fontSize: 12 }}>Block {author}</button>
                <button onClick={() => setMode(null)} className="btn-ghost" style={{ padding: '4px 8px', fontSize: 12 }}>Cancel</button>
              </div>
            </>
          )}
        </div>
      )}
    </span>
  )
}

function timeAgo(isoStr) {
  if (!isoStr) return ''
  const diff = (Date.now() - new Date(isoStr + (isoStr.endsWith('Z') ? '' : 'Z'))) / 1000
  if (diff < 60)   return 'just now'
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

// ── Single comment row ────────────────────────────────────────────────────────
function CommentRow({ c, currentUser, onDelete, onUpdate, onBlocked }) {
  const isOwn  = currentUser && (currentUser === c.author || currentUser === 'admin')
  const isOther = currentUser && (c.author || '').toLowerCase() !== currentUser.toLowerCase()
  const [editing, setEditing] = useState(false)
  const [draft,   setDraft]   = useState(c.body)
  const [saving,  setSaving]  = useState(false)
  const editRef = useRef(null)

  useEffect(() => { if (editing) editRef.current?.focus() }, [editing])

  const confirmEdit = async () => {
    const text = draft.trim()
    if (!text || text === c.body) { setEditing(false); setDraft(c.body); return }
    setSaving(true)
    try {
      const updated = await onUpdate(c.id, text)
      if (updated?.body) setDraft(updated.body)
      setEditing(false)
    } catch { /* leave open */ }
    setSaving(false)
  }

  const cancelEdit = () => { setEditing(false); setDraft(c.body) }

  return (
    <div className="flex gap-2.5 group">
      {/* Avatar */}
      <AuthorAvatar name={c.author} photo={c.author_photo_url} style={{ marginTop: 2 }}/>

      {/* Bubble */}
      <div className="flex-1 min-w-0 rounded-xl px-3 py-2"
           style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
        {/* Header */}
        <div className="flex items-center justify-between gap-2 mb-1">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
              {c.author || 'Anonymous'}
            </span>
            {c.updated_at && c.updated_at !== c.created_at && (
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>(edited)</span>
            )}
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              {timeAgo(c.created_at)}
            </span>
            {isOwn && !editing && (
              <>
                <button onClick={() => setEditing(true)}
                  className="md:opacity-0 md:group-hover:opacity-100 transition-opacity"
                  style={{ color: 'var(--text-tertiary)' }} title="Edit">
                  <Pencil size={11}/>
                </button>
                <button onClick={() => onDelete(c.id)}
                  className="md:opacity-0 md:group-hover:opacity-100 transition-opacity"
                  style={{ color: 'var(--text-tertiary)' }} title="Delete">
                  <Trash2 size={11}/>
                </button>
              </>
            )}
            {isOther && !isOwn && <NoteActions c={c} onBlocked={onBlocked}/>}
          </div>
        </div>

        {/* Body or editor */}
        {editing ? (
          <div className="space-y-1.5">
            <textarea ref={editRef} className="input w-full resize-none text-sm" rows={2}
                      value={draft} onChange={e => setDraft(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) confirmEdit()
                        if (e.key === 'Escape') cancelEdit()
                      }}
                      style={{ lineHeight: 1.5 }}/>
            <div className="flex items-center gap-1.5">
              <button onClick={confirmEdit} disabled={saving || !draft.trim()}
                      className="btn-primary flex items-center gap-1" style={{ padding: '4px 10px', fontSize: 11 }}>
                <Check size={10}/> {saving ? 'Saving…' : 'Save'}
              </button>
              <button onClick={cancelEdit}
                      className="btn-ghost flex items-center gap-1" style={{ padding: '4px 8px', fontSize: 11 }}>
                <X size={10}/> Cancel
              </button>
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}><span className="kbd-hint">⌘↵ to save · Esc to cancel</span></span>
            </div>
          </div>
        ) : (
          <p className="text-sm whitespace-pre-wrap break-words" style={{ color: 'var(--text-primary)' }}>
            {c.body}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function Comments({
  fetchFn, postFn, deleteFn, updateFn,
  currentUser,
  placeholder = 'Add a note…',
  emptyText   = 'No notes yet. Be the first!',
}) {
  const [comments,   setComments]   = useState([])
  const [loading,    setLoading]    = useState(true)
  const [body,       setBody]       = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error,      setError]      = useState(null)
  const textRef = useRef(null)
  const [myPhoto, setMyPhoto] = useState(null)
  useEffect(() => {
    api.auth.me().then(r => (r?.json ? r.json() : r)).then(u => setMyPhoto(u?.photo_url || null)).catch(() => {})
  }, [])

  const load = useCallback(() => {
    fetchFn()
      .then(data => setComments(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [fetchFn])

  useEffect(() => { load() }, [load])

  const submit = async () => {
    const text = body.trim()
    if (!text) return
    setSubmitting(true)
    setError(null)
    try {
      const author = currentUser || 'Anonymous'
      const newComment = await postFn(text, author)
      setComments(prev => [newComment, ...prev])
      setBody('')
      textRef.current?.focus()
    } catch {
      setError('Failed to post. Please try again.')
    }
    setSubmitting(false)
  }

  const handleDelete = async (commentId) => {
    try {
      await deleteFn(commentId)
      setComments(prev => prev.filter(c => c.id !== commentId))
    } catch {}
  }

  const handleUpdate = async (commentId, newBody) => {
    const updated = await updateFn(commentId, newBody)
    setComments(prev => prev.map(c => c.id === commentId ? { ...c, ...updated } : c))
    return updated
  }

  return (
    <div className="space-y-3">
      {/* Composer */}
      <div className="flex gap-2">
        <AuthorAvatar name={currentUser} photo={myPhoto} accent style={{ marginTop: 2 }}/>
        <div className="flex-1 space-y-1.5">
          <textarea ref={textRef} className="input w-full resize-none text-sm" rows={2}
                    placeholder={placeholder} value={body}
                    onChange={e => setBody(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit() }}
                    style={{ lineHeight: 1.5 }}/>
          <div className="flex items-center justify-between">
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              <span className="kbd-hint">⌘↵ to post · </span>visible to everyone at this site
            </span>
            <button onClick={submit} disabled={submitting || !body.trim()}
                    className="btn-primary flex items-center gap-1" style={{ padding: '5px 12px', fontSize: 12 }}>
              <Send size={11}/>
              {submitting ? 'Posting…' : 'Post'}
            </button>
          </div>
          {error && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{error}</p>}
        </div>
      </div>

      {/* Thread */}
      {loading ? (
        <div className="space-y-2">
          {[0, 1].map(i => <div key={i} className="skeleton h-14 rounded-xl"/>)}
        </div>
      ) : comments.length === 0 ? (
        <div className="flex items-center gap-2 py-4" style={{ color: 'var(--text-tertiary)' }}>
          <MessageSquare size={14}/>
          <p className="text-sm">{emptyText}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {comments.map(c => (
            <CommentRow key={c.id} c={c} currentUser={currentUser}
                        onDelete={handleDelete} onUpdate={handleUpdate}
                        onBlocked={author => setComments(prev => prev.filter(x => x.author !== author))}/>
          ))}
        </div>
      )}
    </div>
  )
}
