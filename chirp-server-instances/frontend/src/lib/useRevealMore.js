import { useCallback, useRef } from 'react'

// Callback ref for the "show more" sentinel at the end of a list that renders
// in chunks. It watches whichever node is mounted, so it works when the
// sentinel only appears after loading ends, and calls onReveal when the node
// comes within rootMargin of the screen.
// Give the sentinel key={visibleCount}: an observer only reports changes, so
// a sentinel still on screen after a chunk was added would never fire again.
// A fresh node gets a fresh first report.
export function useRevealMore(onReveal, rootMargin = '400px') {
  const cb = useRef(onReveal)
  cb.current = onReveal
  const obs = useRef(null)
  return useCallback(el => {
    obs.current?.disconnect()
    obs.current = null
    if (!el || typeof IntersectionObserver === 'undefined') return
    obs.current = new IntersectionObserver(([e]) => { if (e.isIntersecting) cb.current() }, { rootMargin })
    obs.current.observe(el)
  }, [rootMargin])
}
