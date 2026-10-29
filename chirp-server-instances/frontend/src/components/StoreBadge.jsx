import { IPHONE_APP_STORE_URL, TV_APP_STORE_URL } from '../lib/appStore'

// Apple's own badge artwork (public/badges), unaltered, 40px tall, as
// Apple's marketing guidelines ask. Until a link exists the badge shows
// without one, with "Coming soon" beside it.
const BADGES = {
  tv: { url: TV_APP_STORE_URL, src: '/badges/apple-tv.svg', alt: 'Download on Apple TV' },
  iphone: { url: IPHONE_APP_STORE_URL, src: '/badges/app-store.svg', alt: 'Download on the App Store' },
}

export default function StoreBadge({ kind }) {
  const b = BADGES[kind]
  if (!b) return null
  const img = <img src={b.src} alt={b.alt} style={{ height: 40, width: 'auto', display: 'block' }}/>
  if (b.url) {
    return <a href={b.url} target="_blank" rel="noopener noreferrer" className="inline-block flex-shrink-0">{img}</a>
  }
  return (
    <span className="inline-flex items-center gap-2 flex-shrink-0" title="Coming soon to the App Store">
      {img}
      <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full"
            style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-subtle, rgba(255,255,255,.12))' }}>Coming soon</span>
    </span>
  )
}
