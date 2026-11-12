// The phone tab bar, Liquid Glass style (as in Chirp Live and Chirp Lite):
// one glass lens marks the current tab and slides between tabs. Press and
// drag along the bar and the lens follows your finger, swells a little, and
// ticks (haptics) as it crosses each tab; let go to open the tab under it.
// A plain tap works as before. Styles: index.css .glass-nav / .glass-lens.
import { useLayoutEffect, useRef, useState } from 'react'
import { hapticEvent } from '../lib/haptics'

const TAP_SLOP = 8 // px a press can wander and still count as a tap

/** items: [{ key, label, icon, active, alert, badge, onSelect }] */
export default function GlassTabBar({ items }) {
  const navRef = useRef(null)
  const [width, setWidth] = useState(0)
  const [drag, setDrag] = useState(null) // { x, index } while pressed
  const press = useRef(null)            // { startX, index, moved, id }

  useLayoutEffect(() => {
    const el = navRef.current
    if (!el) return
    const measure = () => setWidth(el.clientWidth)
    measure()
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null
    ro?.observe(el)
    return () => ro?.disconnect()
  }, [])

  const PAD = 5
  const n = items.length
  const slot = n ? (width - PAD * 2) / n : 0
  const active = items.findIndex(i => i.active)
  const indexAt = (clientX) => {
    const r = navRef.current.getBoundingClientRect()
    return Math.max(0, Math.min(n - 1, Math.floor((clientX - r.left - PAD) / slot)))
  }

  const down = (e) => {
    if (e.button > 0 || !slot) return
    const index = indexAt(e.clientX)
    press.current = { startX: e.clientX, index, moved: false, id: e.pointerId }
    navRef.current.setPointerCapture?.(e.pointerId)
    setDrag({ x: e.clientX, index })
  }
  const move = (e) => {
    const p = press.current
    if (!p || p.id !== e.pointerId) return
    if (Math.abs(e.clientX - p.startX) > TAP_SLOP) p.moved = true
    const index = indexAt(e.clientX)
    if (index !== p.index) { p.index = index; hapticEvent('selection') }
    setDrag({ x: e.clientX, index })
  }
  const up = (e) => {
    const p = press.current
    if (!p || p.id !== e.pointerId) return
    press.current = null
    setDrag(null)
    const index = p.moved ? indexAt(e.clientX) : p.index
    hapticEvent('medium')                    // as the app's other tab-bar taps
    items[index]?.onSelect()
  }
  const cancel = () => { press.current = null; setDrag(null) }

  // Where the lens sits: under the finger while dragging, else on the current tab.
  let lensLeft = null
  if (drag && slot) {
    const r = navRef.current.getBoundingClientRect()
    lensLeft = Math.max(PAD, Math.min(width - PAD - slot, drag.x - r.left - slot / 2))
  } else if (active >= 0 && slot) {
    lensLeft = PAD + active * slot
  }

  return (
    <nav ref={navRef} className={`glass-nav${drag ? ' pressed' : ''}`} aria-label="Main"
         onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={cancel}
         onLostPointerCapture={cancel}>
      {lensLeft !== null && (
        <span aria-hidden="true" className={`glass-lens${drag ? ' dragging' : ''}`}
              style={{ left: lensLeft, width: slot }}/>
      )}
      {items.map((it, i) => {
        const lit = drag ? drag.index === i : it.active
        return (
          // Activation happens on pointer up (so a drag can end on any tab);
          // keyboard users still get Enter/Space through onClick's detail 0.
          <button key={it.key} type="button" aria-label={it.label} aria-current={it.active ? 'page' : undefined}
                  data-haptic="none"
                  className={`glass-tab${lit ? ' on' : ''}${it.alert ? ' alert' : ''}`}
                  onClick={(e) => { if (e.detail === 0) it.onSelect() }}>
            <span style={{ position: 'relative', display: 'flex' }}>
              {it.icon}
              {it.badge}
            </span>
          </button>
        )
      })}
    </nav>
  )
}
