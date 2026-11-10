import { useEffect, useRef, useState } from 'react'
import { isNative } from '../native'
import { hapticEvent } from './haptics'

// Touch gestures for the iPhone/iPad app (and the home-screen web app):
// pull down at the top of a page to refresh it, and tap the status bar to
// scroll to the top. Swiping back and forward from the screen edges is
// native (ChirpBridgeViewController turns on WKWebView's gestures).
//
// Pages scroll inside <main>, not the document, so iOS's own versions of
// these don't reach them.
//
// Haptics, as in iOS's own pull to refresh: a tap when the pull passes the
// point where letting go refreshes (again if it's pulled back and past
// once more), and a light one when the refresh finishes.

const PULL_MAX = 110     // px the indicator travels
const PULL_TRIGGER = 70  // px of pull that refreshes on release

function wantsGestures() {
  if (typeof window === 'undefined') return false
  try { return isNative() || window.matchMedia('(display-mode: standalone)').matches } catch { return false }
}

// A touch that starts inside something that scrolls on its own (a list in a
// sheet, a carousel) or in a dialog belongs to that, not to the page.
function ownedElsewhere(target, main) {
  for (let el = target; el && el !== main; el = el.parentElement) {
    if (el.getAttribute?.('role') === 'dialog' || el.dataset?.noPull !== undefined) return true
    const s = getComputedStyle(el)
    if (/(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight && el.scrollTop > 0) return true
  }
  return false
}

export function usePageGestures(mainRef, onRefresh) {
  // gap: how far the page has been pulled down, px. On iOS the page itself
  // rubber-bands (scrollTop goes negative), so the gap is read from it and
  // the indicator sits in the space that opens above the page. Where nothing
  // bounces, the page is moved by `shift` instead.
  const [gap, setGap] = useState(0)
  const [shift, setShift] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const latest = useRef(onRefresh)
  latest.current = onRefresh

  useEffect(() => {
    if (!wantsGestures()) return
    // On the document, so the listeners survive the page remounting <main>.
    let main = null, startY = null, startX = 0, dist = 0, bounced = false, busy = false, armed = false

    const set = (d, moved) => {
      dist = d; setGap(d); setShift(moved)
      if (startY !== null && !armed && d >= PULL_TRIGGER) { armed = true; hapticEvent('medium') }
      else if (armed && d < PULL_TRIGGER * 0.8) armed = false
    }
    const down = (e) => {
      main = mainRef.current
      if (!main || !main.contains(e.target) || busy || e.touches.length !== 1 || main.scrollTop > 0 || ownedElsewhere(e.target, main)) { startY = null; return }
      startY = e.touches[0].clientY; startX = e.touches[0].clientX; dist = 0; bounced = false; armed = false
    }
    const move = (e) => {
      if (startY === null) return
      const dy = e.touches[0].clientY - startY
      const dx = Math.abs(e.touches[0].clientX - startX)
      if (dy <= 0 || dx > dy) { if (dist) set(0, 0); return }
      const bounce = Math.max(0, -main.scrollTop)
      if (bounce > 0) bounced = true
      if (bounced) set(Math.min(PULL_MAX * 1.5, bounce), 0)
      else if (main.scrollTop <= 0) { const d = Math.min(PULL_MAX, dy * 0.5); set(d, d) }
    }
    const scroll = (e) => {
      if (startY === null || e.target !== main) return
      const bounce = Math.max(0, -main.scrollTop)
      if (bounce > 0) { bounced = true; set(Math.min(PULL_MAX * 1.5, bounce), 0) }
    }
    const up = async () => {
      if (startY === null) return
      startY = null; armed = false
      if (dist < PULL_TRIGGER) { set(0, 0); return }
      busy = true
      setRefreshing(true); set(0, 0)
      try { await latest.current?.() } catch { /* the page shows its own errors */ }
      hapticEvent('light')
      setTimeout(() => { setRefreshing(false); busy = false }, 700)
    }
    const statusTap = () => mainRef.current?.scrollTo({ top: 0, behavior: 'smooth' })

    document.addEventListener('touchstart', down, { passive: true })
    document.addEventListener('touchmove', move, { passive: true })
    document.addEventListener('touchend', up)
    document.addEventListener('touchcancel', up)
    document.addEventListener('scroll', scroll, { capture: true, passive: true })
    window.addEventListener('statusTap', statusTap)
    return () => {
      document.removeEventListener('touchstart', down)
      document.removeEventListener('touchmove', move)
      document.removeEventListener('touchend', up)
      document.removeEventListener('touchcancel', up)
      document.removeEventListener('scroll', scroll, { capture: true })
      window.removeEventListener('statusTap', statusTap)
    }
  }, [mainRef])

  return { gap, shift, refreshing }
}

// The refresh indicator: centred in the space above the page while pulling,
// then held in a 56 px band (the page is pushed down by REFRESH_BAND) while
// the page reloads.
export const REFRESH_BAND = 56
