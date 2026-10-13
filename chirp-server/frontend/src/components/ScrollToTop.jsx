import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { ChevronUp } from 'lucide-react'

/**
 * Floating "scroll to top" button — appears once the page is scrolled
 * down from the top, persists until back at the top, and smooth-scrolls
 * to the top on click. Rendered once, globally, in App.jsx rather than
 * per-page, since this is generic page-level behavior.
 *
 * Confirmed detail: this app's scrollable container is the
 * <main> element in App.jsx (`overflow-y-auto`), not the window/body —
 * confirmed directly (a first attempt using window.scrollY / scrollTo
 * never detected any scroll at all, since the window itself never
 * scrolls here; RecordingsList.jsx's own comments independently
 * document the same thing: "the scroll container is <main>").
 * There's exactly one <main> element in the whole app, so querying for
 * it directly is unambiguous.
 *
 * Positioned bottom-right, but with a taller bottom offset on mobile
 * specifically to clear MobileNav's own fixed bottom bar (56px tall +
 * safe-area-inset-bottom) — sitting flush with it would overlap. On
 * desktop, where MobileNav is hidden (md:hidden) and a sidebar is used
 * instead, there's no bottom bar to clear, so a much smaller offset is
 * enough.
 *
 * Reported directly with a screenshot and reproduced exactly (confirmed
 * a 2px overlap via bounding-box math in a headless browser test):
 * Settings has its own persistent floating Save button in this same
 * bottom-right zone. Rather than chasing an exact safe-area-aware pixel
 * offset to thread between the two (fragile, and would need updating
 * again if either button's own position ever changes), this is
 * suppressed entirely on the Settings route — it already has its own
 * always-visible floating action button there, and Settings' content is
 * now tab-segmented (each tab much shorter than the old single long
 * page), reducing the need for a scroll-to-top helper on that
 * page specifically.
 */
export default function ScrollToTop() {
  const [visible, setVisible] = useState(false)
  const location = useLocation()

  useEffect(() => {
    // scroll events don't bubble, so a listener on <main> itself would
    // need re-attaching every time <main> remounts (it does, on every
    // route change — App.jsx keys it on location.pathname). Capture-
    // phase listening on document sidesteps that entirely: it still
    // catches scroll events from any descendant, remounted or not, so
    // this only needs to be set up once regardless of navigation.
    const onScroll = () => {
      const main = document.querySelector('main')
      setVisible(!!main && main.scrollTop > 300)
    }
    onScroll()
    document.addEventListener('scroll', onScroll, { capture: true, passive: true })
    return () => document.removeEventListener('scroll', onScroll, { capture: true })
  }, [])

  if (!visible || location.pathname === '/settings') return null

  return (
    <button
      onClick={() => document.querySelector('main')?.scrollTo({ top: 0, behavior: 'smooth' })}
      aria-label="Scroll to top"
      className="fixed right-4 md:right-6 bottom-28 md:bottom-6 z-40 flex items-center justify-center rounded-full tactile-press animate-fade-in"
      style={{
        width: 44,
        height: 44,
        background: 'var(--bg-card)',
        border: '1px solid var(--border-default)',
        boxShadow: '0 4px 16px rgba(0,0,0,.35)',
        color: 'var(--text-primary)',
      }}
    >
      <ChevronUp size={22}/>
    </button>
  )
}
