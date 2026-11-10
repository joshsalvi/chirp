import { useEffect, useState } from 'react'
import { X } from 'lucide-react'

// Standard or Advanced dashboard. Shown once to everyone who hasn't picked
// one of the two (new people, and everyone on the old Simplified/Detailed
// names), and again from the view button or Settings → Appearance.
// Closing it keeps the highlighted choice.

function StandardSketch() {
  return (
    <div aria-hidden="true" className="mode-sketch">
      <div style={{ width: '62%', height: 8, borderRadius: 4, background: 'var(--text-secondary)', opacity: 0.55 }}/>
      <div style={{ display: 'flex', gap: 8, height: '40%' }}>
        <div style={{ width: '52%', borderRadius: 7, background: 'linear-gradient(135deg, var(--accent-700), var(--s500))' }}/>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6 }}>
          <div style={{ width: '80%', height: 6, borderRadius: 3, background: 'var(--text-secondary)', opacity: 0.45 }}/>
          <div style={{ width: 18, height: 18, borderRadius: '50%', background: 'var(--accent-400)' }}/>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 4, flex: 1 }}>
        {[0, 1, 2, 3].map(i => (
          <div key={i} style={{ borderRadius: 5, background: 'var(--s500)', opacity: 0.5 + i * 0.12 }}/>
        ))}
      </div>
    </div>
  )
}

const BARS = [30, 45, 38, 60, 82, 70, 55, 48, 40, 52, 66, 58, 44, 36, 28, 22]

function AdvancedSketch() {
  return (
    <div aria-hidden="true" className="mode-sketch">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 5 }}>
        {[0, 1, 2, 3].map(i => <div key={i} style={{ height: 20, borderRadius: 5, background: 'var(--text-secondary)', opacity: 0.18 }}/>)}
      </div>
      <div style={{ flex: 1, display: 'flex', alignItems: 'flex-end', gap: 3 }}>
        {BARS.map((h, i) => <div key={i} style={{ flex: 1, height: `${h}%`, borderRadius: '2px 2px 0 0', background: 'var(--accent-400)', opacity: 0.55 }}/>)}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 5 }}>
        {[0, 1].map(i => <div key={i} style={{ height: 14, borderRadius: 5, background: 'var(--text-secondary)', opacity: 0.18 }}/>)}
      </div>
    </div>
  )
}

const OPTIONS = [
  { id: 'standard', label: 'Standard', Sketch: StandardSketch, badge: 'Recommended',
    desc: "The latest bird, who's been singing today, and a line from the journal. Calm and simple." },
  { id: 'advanced', label: 'Advanced', Sketch: AdvancedSketch,
    desc: 'Everything: activity charts, diversity scores, stat cards, journals and comments.' },
]

export default function DashboardModePicker({ current, onChoose, onClose }) {
  const [picked, setPicked] = useState(current || 'standard')
  const [saving, setSaving] = useState(false)
  const done = async (mode) => {
    if (saving) return
    setSaving(true)
    try { await onChoose(mode) } finally { setSaving(false) }
  }
  const close = () => (onClose ? onClose(picked) : done(picked))

  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <div className="mode-picker-backdrop fixed inset-0 flex items-center justify-center animate-fade-in"
         style={{ background: 'rgba(0,0,0,.65)', backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)' }}
         onClick={e => { if (e.target === e.currentTarget) close() }}>
      <div role="dialog" aria-modal="true" aria-labelledby="mode-picker-title"
           className="mode-picker w-full rounded-3xl p-5 sm:p-8 animate-pop-in overflow-y-auto"
           style={{ maxWidth: 640, background: 'var(--bg-card)', border: '1px solid var(--border-default)', boxShadow: '0 24px 80px rgba(0,0,0,.55)' }}>
        <div className="flex items-start justify-between gap-4 mb-5 sm:mb-6">
          <div>
            <h2 id="mode-picker-title" className="font-display" style={{ fontSize: 'clamp(21px, 5.5vw, 26px)', fontWeight: 500, color: 'var(--text-primary)', lineHeight: 1.2 }}>
              How should your dashboard look?
            </h2>
            <p className="text-sm mt-1.5" style={{ color: 'var(--text-secondary)' }}>
              You can switch any time here or in Settings → Appearance.
            </p>
          </div>
          <button type="button" onClick={close} aria-label="Close"
                  className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-opacity hover:opacity-80"
                  style={{ background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
            <X size={16}/>
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4 mb-5 sm:mb-6">
          {OPTIONS.map(({ id, label, Sketch, badge, desc }) => {
            const on = picked === id
            return (
              <button key={id} type="button" aria-pressed={on} onClick={() => setPicked(id)}
                      className="mode-card text-left p-3.5 sm:p-4 rounded-2xl transition-all hover:-translate-y-0.5"
                      style={{ background: on ? 'var(--bg-raised)' : 'var(--bg-card)',
                               border: `2px solid ${on ? 'var(--accent-400)' : 'var(--border-default)'}` }}>
                <Sketch/>
                <span className="mode-card-text">
                <span className="flex items-center justify-between gap-x-2 gap-y-1 flex-wrap">
                  <span className="font-display" style={{ fontSize: 20, color: 'var(--text-primary)' }}>{label}</span>
                  {badge && (
                    <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full"
                          style={{ background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)' }}>{badge}</span>
                  )}
                </span>
                <span className="text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>{desc}</span>
                </span>
              </button>
            )
          })}
        </div>

        <div className="mode-picker-foot flex justify-end">
          <button type="button" onClick={() => done(picked)} disabled={saving}
                  className="min-h-[44px] px-6 rounded-full text-[15px] font-semibold transition-opacity hover:opacity-90 disabled:opacity-60"
                  style={{ background: 'var(--accent-400)', color: '#071009' }}>
            {saving ? 'Saving…' : `Use ${picked === 'standard' ? 'Standard' : 'Advanced'}`}
          </button>
        </div>
      </div>
    </div>
  )
}
