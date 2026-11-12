import { useState } from 'react'
import { Radio, X } from 'lucide-react'
import { tokenStore } from '../lib/api'

export const SETUP_GUIDE_URL = 'https://ourchirp.com/setup.html'

// Shown on the dashboards when the site has no Chirp station of its own
// (GET /lite/today and /statistics/dashboard-summary: has_station). Can be
// put away per site, on this device.
export default function SetupGuideCard({ className = '' }) {
  const key = `chirp_setup_hint_off_${tokenStore.getActiveInstanceId?.() || 'site'}`
  const [off, setOff] = useState(() => { try { return localStorage.getItem(key) === '1' } catch { return false } })
  if (off || tokenStore.isDemo?.()) return null
  const hide = () => { setOff(true); try { localStorage.setItem(key, '1') } catch { /* private mode */ } }
  return (
    <div className={`card p-4 flex items-start gap-3 ${className}`} role="note">
      <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'var(--nav-active-bg)' }}>
        <Radio size={18} style={{ color: 'var(--accent-400)' }}/>
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>No Chirp station yet</p>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
          A Raspberry Pi with a USB microphone listens around the clock and names every bird it hears.
        </p>
        <a href={SETUP_GUIDE_URL} target="_blank" rel="noopener" className="inline-block text-sm font-medium mt-2" style={{ color: 'var(--accent-400)' }}>
          Read the setup guide ↗
        </a>
      </div>
      <button type="button" onClick={hide} aria-label="Hide" className="p-1 rounded-lg hover:opacity-70" style={{ color: 'var(--text-tertiary)' }}>
        <X size={16}/>
      </button>
    </div>
  )
}
