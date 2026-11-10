import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { account, AuthError, lite } from './api'
import { AppContext } from './context'
import { BirdMark, Icon } from './icons'
import { PlayerProvider, usePlayer } from './player'
import { Photo, PlayButton } from './ui'
import SongLine from '../components/SongLine'
import Today from './screens/Today'
import Birds from './screens/Birds'
import Listen from './screens/Listen'
import Guide from './screens/Guide'
import Bird from './screens/Bird'
import SignIn, { PickSite } from './screens/SignIn'
import MeSheet from './screens/Me'

export default function LiteApp() {
  const [me, setMe] = useState(null)
  const [stage, setStage] = useState('checking')   // checking | ready | signin | site | offline
  const [meOpen, setMeOpen] = useState(false)

  const check = useCallback(async () => {
    if (account.needsSite()) { setStage('site'); return }
    try {
      setMe(await account.me())
      setStage('ready')
    } catch (e) {
      setStage(e instanceof AuthError ? 'signin' : 'offline')
    }
  }, [])

  useEffect(() => { check() }, [check])
  useEffect(() => {
    const out = () => { setMe(null); setStage('signin') }
    window.addEventListener('lite-signed-out', out)
    return () => window.removeEventListener('lite-signed-out', out)
  }, [])

  if (stage === 'checking') return <Splash />
  if (stage === 'signin') return <SignIn onDone={check} />
  if (stage === 'site') return <PickSite onDone={check} />
  if (stage === 'offline') return <Splash message="Can’t reach your Chirp right now." onRetry={check} />

  return (
    <AppContext.Provider value={{ me, openMe: () => setMeOpen(true) }}>
      <PlayerProvider>
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<Today />} />
            <Route path="birds" element={<Birds />} />
            <Route path="listen" element={<Listen />} />
            <Route path="guide" element={<Guide />} />
          </Route>
          <Route path="bird/:id" element={<Bird />} />
          <Route path="*" element={<Today />} />
        </Routes>
        {meOpen && <MeSheet onClose={() => setMeOpen(false)} />}
      </PlayerProvider>
    </AppContext.Provider>
  )
}

function Splash({ message, onRetry }) {
  return (
    <div className="splash">
      <BirdMark size={88} className={message ? '' : 'bob'} />
      {message && <p>{message}</p>}
      {onRetry && <button className="btn" onClick={onRetry}>Try again</button>}
    </div>
  )
}

const TABS = [
  { to: '/', label: 'Today', icon: Icon.today, end: true },
  { to: '/birds', label: 'Birds', icon: Icon.birds },
  { to: '/listen', label: 'Listen', icon: Icon.listen },
  { to: '/guide', label: 'Guide', icon: Icon.guide },
]

function Shell() {
  const { pathname } = useLocation()
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  return (
    <div className="shell">
      <main className="page"><Outlet /></main>
      <NowPlaying />
      <nav className="tabbar" aria-label="Main">
        {TABS.map(({ to, label, icon: I, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => 'tab' + (isActive ? ' on' : '')}>
            <I /><span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

function NowPlaying() {
  const { now, error, stop, progress, seek } = usePlayer()
  // Recordings get a song line: loudness, where the bird is, and a mark per call.
  const rid = now?.key?.startsWith('rec-') ? now.key.slice(4) : null
  const [line, setLine] = useState(null)
  useEffect(() => {
    setLine(null)
    if (!rid) return
    let alive = true
    lite.songline(rid, now.title).then(l => { if (alive) setLine(l) }).catch(() => {})
    return () => { alive = false }
  }, [rid, now?.title])
  if (!now) return null
  return (
    <div className="nowplaying" role="region" aria-label="Now playing">
      <Photo src={now.photo} name={now.title} className="np-photo" />
      <div className="np-text">
        <strong>{now.title}</strong>
        {line?.duration && !error ? (
          <SongLine line={line} progress={progress} onSeek={seek} height={18}
                    accent="#FFC53D" accentSoft="rgba(255,197,61,.42)" muted="rgba(244,248,242,.75)" mutedSoft="rgba(244,248,242,.22)"/>
        ) : (
          <span>{error || now.subtitle || 'Playing'}</span>
        )}
      </div>
      <PlayButton item={now} size="sm" />
      <button className="np-close" onClick={stop} aria-label="Stop"><Icon.close /></button>
    </div>
  )
}
