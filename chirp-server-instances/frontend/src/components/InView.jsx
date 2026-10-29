import { useEffect, useRef, useState } from 'react'

// Renders its children once they come near the screen, holding their height
// until then. The Statistics page has about fifteen charts; drawing them all
// on load blocked an iPhone for over a second.
export default function InView({ height, margin = '400px', children }) {
  const ref = useRef(null)
  const [shown, setShown] = useState(typeof IntersectionObserver === 'undefined')
  useEffect(() => {
    if (shown || !ref.current) return
    const io = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting)) { setShown(true); io.disconnect() }
    }, { rootMargin: margin })
    io.observe(ref.current)
    return () => io.disconnect()
  }, [shown, margin])
  return shown ? children : <div ref={ref} style={{ height }} aria-hidden="true"/>
}
