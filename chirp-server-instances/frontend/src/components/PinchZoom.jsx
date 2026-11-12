import { useEffect, useRef, useState } from 'react'

// An image you can zoom: pinch or double-tap on a phone, ctrl/trackpad
// pinch, scroll wheel or double-click on a computer; drag to pan once
// zoomed. A tap (not a drag) on the image calls onTap, so a viewer can
// close itself only while the image isn't zoomed.
const MAX = 6

export default function PinchZoom({ src, alt, className, onTap }) {
  const box = useRef(null)
  const img = useRef(null)
  const [t, setT] = useState({ s: 1, x: 0, y: 0 })
  const tr = useRef(t)
  tr.current = t
  const pts = useRef(new Map())
  const g = useRef(null)          // gesture start: { d, s, x, y, cx, cy } or pan { px, py, x, y }
  const moved = useRef(false)
  const lastTap = useRef(0)

  // Keeps the image covering its box once zoomed: no panning off into empty space.
  const clamp = ({ s, x, y }) => {
    s = Math.min(MAX, Math.max(1, s))
    if (s === 1) return { s, x: 0, y: 0 }
    const r = img.current?.getBoundingClientRect(), b = box.current?.getBoundingClientRect()
    if (!r || !b) return { s, x, y }
    const w = (r.width / tr.current.s) * s, h = (r.height / tr.current.s) * s
    const mx = Math.max(0, (w - b.width) / 2), my = Math.max(0, (h - b.height) / 2)
    return { s, x: Math.min(mx, Math.max(-mx, x)), y: Math.min(my, Math.max(-my, y)) }
  }
  // Zoom to scale s keeping the point (cx, cy) (relative to the box centre) still.
  const zoomAt = (s, cx, cy, from = tr.current) => {
    const k = Math.min(MAX, Math.max(1, s)) / from.s
    return clamp({ s: from.s * k, x: cx - (cx - from.x) * k, y: cy - (cy - from.y) * k })
  }
  const centre = (e) => {
    const b = box.current.getBoundingClientRect()
    return [e.clientX - b.left - b.width / 2, e.clientY - b.top - b.height / 2]
  }

  const down = (e) => {
    e.stopPropagation()
    box.current.setPointerCapture?.(e.pointerId)
    pts.current.set(e.pointerId, e)
    moved.current = false
    if (pts.current.size === 2) {
      const [a, b] = [...pts.current.values()]
      const [ax, ay] = centre(a), [bx, by] = centre(b)
      g.current = { d: Math.hypot(ax - bx, ay - by), cx: (ax + bx) / 2, cy: (ay + by) / 2, ...tr.current }
    } else if (pts.current.size === 1) {
      g.current = { px: e.clientX, py: e.clientY, ...tr.current }
    }
  }
  const move = (e) => {
    if (!pts.current.has(e.pointerId)) return
    pts.current.set(e.pointerId, e)
    const st = g.current
    if (!st) return
    if (pts.current.size >= 2 && st.d) {
      const [a, b] = [...pts.current.values()]
      const [ax, ay] = centre(a), [bx, by] = centre(b)
      const d = Math.hypot(ax - bx, ay - by)
      const cx = (ax + bx) / 2, cy = (ay + by) / 2
      const z = zoomAt(st.s * d / st.d, st.cx, st.cy, st)
      setT(clamp({ s: z.s, x: z.x + cx - st.cx, y: z.y + cy - st.cy }))
      moved.current = true
    } else if (pts.current.size === 1 && st.px !== undefined) {
      const dx = e.clientX - st.px, dy = e.clientY - st.py
      if (Math.abs(dx) + Math.abs(dy) > 6) moved.current = true
      if (st.s > 1) setT(clamp({ s: st.s, x: st.x + dx, y: st.y + dy }))
    }
  }
  const up = (e) => {
    e.stopPropagation()
    const was = pts.current.size
    pts.current.delete(e.pointerId)
    if (pts.current.size === 1) {                 // lifted one finger of a pinch: keep panning
      const [p] = [...pts.current.values()]
      g.current = { px: p.clientX, py: p.clientY, ...tr.current }
      return
    }
    g.current = null
    if (was !== 1 || moved.current) return
    const now = Date.now()
    if (now - lastTap.current < 300) {           // double tap: zoom in there, or back out
      lastTap.current = 0
      const [cx, cy] = centre(e)
      setT(tr.current.s > 1 ? { s: 1, x: 0, y: 0 } : zoomAt(2.5, cx, cy))
      return
    }
    lastTap.current = now
    const zoomed = tr.current.s > 1
    setTimeout(() => { if (lastTap.current === now && !zoomed) onTap?.() }, 300)
  }

  // Wheel / trackpad pinch (ctrlKey) on a computer. Not passive, so the page doesn't zoom.
  useEffect(() => {
    const el = box.current
    if (!el) return
    const wheel = (e) => {
      e.preventDefault()
      const [cx, cy] = centre(e)
      setT(zoomAt(tr.current.s * Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0025)), cx, cy))
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  }, [])

  return (
    <div ref={box} className="pinch-zoom" data-no-pull
         onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}
         onClick={e => e.stopPropagation()}>
      <img ref={img} src={src} alt={alt} draggable={false} className={className}
           style={{ transform: `translate(${t.x}px, ${t.y}px) scale(${t.s})`,
                    transition: g.current ? 'none' : 'transform .18s ease-out',
                    cursor: t.s > 1 ? 'grab' : 'zoom-in' }}/>
      {t.s > 1 && (
        <button type="button" className="pinch-zoom-reset" onPointerDown={e => e.stopPropagation()}
                onClick={e => { e.stopPropagation(); setT({ s: 1, x: 0, y: 0 }) }}>
          {Math.round(t.s * 10) / 10}× · Reset
        </button>
      )}
    </div>
  )
}
