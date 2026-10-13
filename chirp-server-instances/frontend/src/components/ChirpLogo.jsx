/**
 * Chirp logo, theme-aware.
 *
 * Themes with their own artwork (ThemedChirpLogos.jsx) get that; every
 * other theme gets the default Songbird mark: the bird in the theme's
 * text color with the warm orange meter bars.
 *
 * animate: true/'sing' (Dashboard, Tutorial), 'draw' (login, launch),
 * 'meter' (Live Detect while listening). Header and sidebar stay still.
 */
import { useEffect, useState } from 'react'
import { getThemedLogo } from './ThemedChirpLogos'
import SongbirdMark from './SongbirdMark'

export default function ChirpLogo({ size = 36, showText = false, className = '', animate = false }) {
  // Follow [data-theme] live: Settings changes it without a reload.
  const [themeId, setThemeId] = useState(() =>
    typeof document !== 'undefined' ? document.documentElement.getAttribute('data-theme') : null
  )
  useEffect(() => {
    if (typeof document === 'undefined') return
    const observer = new MutationObserver(() => {
      setThemeId(document.documentElement.getAttribute('data-theme'))
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  const Mark = getThemedLogo(themeId)

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {Mark
        ? <Mark size={size} animate={animate}/>
        : <SongbirdMark size={size} animate={animate} ink="var(--text-primary, #f5efe6)"
                        catchlight="var(--bg-panel, #0a160c)"/>}
      {showText && (
        <span className="font-bold tracking-wide" style={{ fontSize: size * 0.45, color: 'var(--text-primary)' }}>
          Chirp
        </span>
      )}
    </div>
  )
}
