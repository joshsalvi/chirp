import { useState, useEffect } from 'react'
import { api } from '../lib/api'

export default function VersionBadge() {
  const [version, setVersion] = useState(null)

  useEffect(() => {
    api.health()
      .then(d => setVersion(d?.version || null))
      .catch(() => {})
  }, [])

  if (!version) return null

  return (
    <a
      href="/changelog"
      className="flex items-center gap-1.5 text-xs"
      style={{ color: 'var(--text-tertiary)', textDecoration: 'none' }}
      title="View changelog">
      <span className="font-mono px-1.5 py-0.5 rounded"
            style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-subtle)' }}>
        v{version}
      </span>
      <span>What&#39;s New</span>
    </a>
  )
}
