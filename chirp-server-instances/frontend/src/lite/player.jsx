// One audio player for the whole app: any card can start a sound, and the
// "now playing" bar above the tabs shows and stops it.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { media } from './api'

const PlayerContext = createContext(null)

export function PlayerProvider({ children }) {
  const audio = useRef(null)
  const [now, setNow] = useState(null)       // { key, title, photo, src, start }
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0) // 0–1 of the clip
  const [error, setError] = useState(null)

  useEffect(() => {
    const a = new Audio()
    a.preload = 'none'
    const tick = () => setProgress(a.duration ? a.currentTime / a.duration : 0)
    a.addEventListener('timeupdate', tick)
    a.addEventListener('play', () => setPlaying(true))
    a.addEventListener('pause', () => setPlaying(false))
    a.addEventListener('ended', () => { setPlaying(false); setProgress(1) })
    a.addEventListener('error', () => { setPlaying(false); setError('This sound couldn’t be played.') })
    audio.current = a
    return () => { a.pause(); a.src = '' }
  }, [])

  const toggle = useCallback((item) => {
    const a = audio.current
    if (!a || !item?.src) return
    setError(null)
    if (now?.key === item.key) {
      if (a.paused) a.play().catch(() => {})
      else a.pause()
      return
    }
    a.pause()
    a.src = media(item.src)
    const start = Math.max(0, (item.start || 0) - 0.4)
    const seek = () => { try { a.currentTime = start } catch {} }
    if (start) a.addEventListener('loadedmetadata', seek, { once: true })
    setNow(item)
    setProgress(0)
    a.play().catch(() => {})
  }, [now])

  // Jump to a moment of the clip that's playing (song line marks).
  const seek = useCallback((seconds) => {
    const a = audio.current
    if (!a) return
    try { a.currentTime = Math.max(0, seconds) } catch { /* not seekable yet */ }
    if (a.paused) a.play().catch(() => {})
  }, [])

  const stop = useCallback(() => {
    audio.current?.pause()
    setNow(null)
  }, [])

  return (
    <PlayerContext.Provider value={{ now, playing, progress, error, toggle, seek, stop }}>
      {children}
    </PlayerContext.Provider>
  )
}

export const usePlayer = () => useContext(PlayerContext)

// Is this item the one playing right now?
export function useIsPlaying(key) {
  const p = usePlayer()
  return { active: p.now?.key === key, playing: p.now?.key === key && p.playing, progress: p.now?.key === key ? p.progress : 0 }
}
