/**
 * BirdNET v3 next to the main detections for one recording (Settings →
 * Experimental → Compare with BirdNET v3). GET /recordings/{id}/shadow.
 */
import { useEffect, useState } from 'react'
import { FlaskConical } from 'lucide-react'
import { api } from '../lib/api'

const pct = v => `${Math.round(v * 100)}%`

export default function ShadowComparison({ recordingId, refreshKey }) {
  const [data, setData] = useState(null)
  useEffect(() => {
    let alive = true
    api.recordings.shadow(recordingId).then(d => { if (alive) setData(d) }).catch(() => {})
    return () => { alive = false }
  }, [recordingId, refreshKey])
  if (!data) return null

  const both = data.species.filter(s => s.in_main)
  const onlyV3 = data.species.filter(s => !s.in_main)
  return (
    <div className="card p-4 animate-fade-in">
      <div className="flex items-center gap-2 mb-2">
        <FlaskConical size={14} style={{ color: 'var(--accent-400)' }}/>
        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>BirdNET v3 comparison</span>
        <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded"
              style={{ background: 'var(--bg-raised)', color: 'var(--text-tertiary)' }}>Experimental</span>
      </div>
      {!data.ran ? (
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          BirdNET v3 hasn't scored this recording. New recordings are scored as they arrive; Re-analyze scores this one.
        </p>
      ) : (
        <div className="space-y-2 text-xs">
          {data.species.length === 0 && (
            <p style={{ color: 'var(--text-secondary)' }}>BirdNET v3 heard no birds above its threshold.</p>
          )}
          {both.length > 0 && (
            <div>
              <p style={{ color: 'var(--text-tertiary)' }}>Both models</p>
              <p style={{ color: 'var(--text-primary)' }}>
                {both.map(s => `${s.common_name} ${pct(s.confidence)}`).join(' · ')}
              </p>
            </div>
          )}
          {onlyV3.length > 0 && (
            <div>
              <p style={{ color: 'var(--text-tertiary)' }}>Only BirdNET v3</p>
              <p style={{ color: 'var(--pastel-green, #4ade80)' }}>
                {onlyV3.map(s => `${s.common_name} ${pct(s.confidence)}`).join(' · ')}
              </p>
            </div>
          )}
          {data.main_only.length > 0 && (
            <div>
              <p style={{ color: 'var(--text-tertiary)' }}>Only BirdNET 2.4</p>
              <p style={{ color: 'var(--pastel-yellow, #eab308)' }}>{data.main_only.join(' · ')}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
