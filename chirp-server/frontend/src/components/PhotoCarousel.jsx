import { useEffect, useRef, useState } from 'react'

// Photos side by side: swipe (or scroll) between them. Dots show which one
// is up while you move through them, then fade away, as in Chirp Lite.
// renderSlide(item, index) draws each one; onChange(index) follows along.
export default function PhotoCarousel({ items, renderSlide, onChange, className = '', style, label = 'Photos' }) {
  const box = useRef(null)
  const [page, setPage] = useState(0)
  const [dots, setDots] = useState(false)
  const hide = useRef(null)

  // Back to the first photo when the set changes (another bird), not on every render.
  const first = items[0] && typeof items[0] === 'object' ? items[0].url : items[0]
  useEffect(() => { setPage(0); onChange?.(0); if (box.current) box.current.scrollLeft = 0 }, [items.length, first])

  const scrolled = () => {
    const el = box.current
    if (!el) return
    const i = Math.max(0, Math.min(items.length - 1, Math.round(el.scrollLeft / Math.max(el.clientWidth, 1))))
    if (i !== page) { setPage(i); onChange?.(i) }
    setDots(true)
    clearTimeout(hide.current)
    hide.current = setTimeout(() => setDots(false), 1400)
  }
  useEffect(() => () => clearTimeout(hide.current), [])

  const go = (i) => box.current?.scrollTo({ left: i * box.current.clientWidth, behavior: 'smooth' })

  if (items.length <= 1) return <div className={className} style={style}>{items.length ? renderSlide(items[0], 0) : null}</div>
  return (
    <div className={`photo-carousel ${className}`} style={style} role="region" aria-roledescription="carousel" aria-label={label}
         onKeyDown={e => { if (e.key === 'ArrowRight') go(Math.min(page + 1, items.length - 1)); if (e.key === 'ArrowLeft') go(Math.max(page - 1, 0)) }}>
      <div ref={box} className="photo-carousel-track" data-no-pull onScroll={scrolled} tabIndex={0}>
        {items.map((it, i) => (
          <div key={i} className="photo-carousel-slide" aria-roledescription="slide" aria-label={`${i + 1} of ${items.length}`}>
            {renderSlide(it, i)}
          </div>
        ))}
      </div>
      <div className={`photo-carousel-dots${dots ? ' on' : ''}`} aria-hidden="true">
        {items.map((_, i) => <span key={i} className={i === page ? 'cur' : ''}/>)}
      </div>
    </div>
  )
}
