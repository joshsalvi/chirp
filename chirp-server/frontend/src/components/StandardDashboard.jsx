import { useEffect, useRef, useState } from 'react'
import SetupGuideCard from './SetupGuideCard'
import PhotoCarousel from './PhotoCarousel'
import { Link } from 'react-router-dom'
import { ChevronDown, Play, Pause } from 'lucide-react'
import { BirdIcon } from './BirdBatIcons'
import SongLine from './SongLine'
import { api, mediaUrl } from '../lib/api'
import { useTz } from '../lib/time'
import { whenVisible } from '../lib/visible'

// The Standard dashboard: the latest bird, today's birds as photos, three
// facts and a line from the journal. One request (GET /lite/today, the same
// data as Chirp Lite's Today), refreshed on new detections.

function greeting(hour) {
  if (hour < 5) return 'Good night'
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

function hourIn(tz) {
  try { return parseInt(new Date().toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: tz || undefined }), 10) % 24 }
  catch { return new Date().getHours() }
}

function Photo({ src, className, style, alt = '', onLoad }) {
  const [bad, setBad] = useState(false)
  if (!src || bad) {
    return (
      <div className={className} style={{ ...style, display: 'grid', placeItems: 'center', background: 'linear-gradient(135deg, var(--bg-raised), var(--s700))' }}>
        <BirdIcon size={32} style={{ color: 'var(--accent-400)', opacity: 0.6 }}/>
      </div>
    )
  }
  return <img src={mediaUrl(src)} alt={alt} className={className} style={style} onError={() => setBad(true)} onLoad={onLoad} loading="lazy"/>
}

// The latest bird's photo fills its box, and the box takes roughly the
// photo's shape (within limits), so a tall photo (an owl on a post) gets a
// tall box and only a sliver is cropped, from the bottom more than the top.
function HeroPhoto({ hero }) {
  const [ratio, setRatio] = useState(null)
  const photos = hero.photos?.length ? hero.photos : [hero.photo_large || hero.photo]
  useEffect(() => { setRatio(null) }, [photos[0]])
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))
  const style = ratio ? { '--hero-ratio': clamp(ratio, 0.72, 1.5), '--hero-ratio-phone': clamp(ratio, 1, 1.6) } : undefined
  const to = hero.profile_id ? `/library/${hero.profile_id}` : '/recordings'
  // The box takes the first photo's shape; the others fill it.
  return (
    <div className="sd-hero-photo" style={style}>
      <PhotoCarousel items={photos} label={`Photos of ${hero.name}`} renderSlide={(src, i) => (
        <Link to={to} aria-label={hero.name} className="block w-full h-full">
          <Photo src={src} alt={i ? '' : hero.name} className="w-full h-full object-cover"
                 onLoad={i ? undefined : e => { const im = e.currentTarget; if (im.naturalHeight) setRatio(im.naturalWidth / im.naturalHeight) }}/>
        </Link>
      )}/>
    </div>
  )
}

function fmtClock(sec) {
  if (!isFinite(sec) || sec < 0) return '0:00'
  return `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`
}

function Player({ recordingId, bird, size = 56 }) {
  const audio = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [pos, setPos] = useState(0)
  const [dur, setDur] = useState(0)
  const [line, setLine] = useState(null)
  useEffect(() => {
    setPlaying(false); setPos(0); setDur(0); setLine(null)
    const a = audio.current
    let alive = true
    if (recordingId) api.recordings.songline(recordingId, bird).then(l => { if (alive) setLine(l) }).catch(() => {})
    return () => { alive = false; if (a) a.pause() }
  }, [recordingId, bird])
  if (!recordingId) return null
  const toggle = () => {
    const a = audio.current
    if (!a) return
    if (a.paused) a.play().catch(() => setPlaying(false))
    else a.pause()
  }
  const length = dur || line?.duration || 0
  const seekTo = (sec) => {
    const a = audio.current
    if (!a) return
    const go = () => { try { a.currentTime = Math.max(0, sec) } catch { /* not seekable yet */ } }
    if (a.readyState >= 1) go()
    else { a.preload = 'metadata'; a.addEventListener('loadedmetadata', go, { once: true }); a.load() }
    if (a.paused) a.play().catch(() => setPlaying(false))
  }
  const seek = (e) => {
    if (!length) return
    const r = e.currentTarget.getBoundingClientRect()
    seekTo(Math.min(length, Math.max(0, ((e.clientX - r.left) / r.width) * length)))
  }
  const pct = length ? Math.min(100, (pos / length) * 100) : 0
  return (
    <div className="flex items-center gap-4 w-full">
      <button type="button" onClick={toggle} aria-label={playing ? 'Pause' : 'Play the recording'}
              className="sd-play flex-shrink-0" style={{ width: size, height: size }}>
        {playing ? <Pause size={size * 0.38} fill="currentColor"/> : <Play size={size * 0.38} fill="currentColor" style={{ marginLeft: size * 0.05 }}/>}
      </button>
      <div className="flex-1 min-w-0 flex flex-col gap-1.5">
        {line?.duration ? (
          <SongLine line={line} progress={length ? pos / length : 0} onSeek={seekTo}/>
        ) : (
          <div className="sd-track" onClick={seek} role="presentation">
            <div className="sd-track-fill" style={{ width: `${pct}%` }}/>
          </div>
        )}
        <div className="flex justify-between text-xs tabular-nums" style={{ color: 'var(--text-secondary)' }}>
          <span>{fmtClock(pos)}</span>
          <span>{length ? fmtClock(length) : ''}</span>
        </div>
      </div>
      <audio ref={audio} preload="none" src={api.recordings.audioUrl(recordingId)}
             onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => { setPlaying(false); setPos(0) }}
             onTimeUpdate={e => setPos(e.currentTarget.currentTime)}
             onLoadedMetadata={e => setDur(e.currentTarget.duration)}/>
    </div>
  )
}

function ViewButton({ onClick }) {
  return (
    <button type="button" onClick={onClick} aria-haspopup="dialog" className="sd-pill">
      <span className="sd-pill-label">View:</span> Standard <ChevronDown size={14} style={{ color: 'var(--text-secondary)' }}/>
    </button>
  )
}

function Skeleton() {
  return (
    <div className="flex flex-col gap-8" aria-busy="true">
      <div className="skeleton" style={{ height: 320, borderRadius: 22 }}/>
      <div className="skeleton" style={{ height: 96, borderRadius: 12 }}/>
      <div className="sd-tiles">
        {[0, 1, 2, 3, 4, 5].map(i => <div key={i} className={`skeleton sd-tile ${i === 0 ? 'sd-tile-big' : ''}`}/>)}
      </div>
    </div>
  )
}

// Tiles before "All N birds": three rows on a phone, four on a wider screen.
function useTileLimit() {
  const query = '(max-width: 760px)'
  const [small, setSmall] = useState(() => typeof window !== 'undefined' && window.matchMedia?.(query).matches)
  useEffect(() => {
    const m = window.matchMedia?.(query)
    if (!m) return
    const on = () => setSmall(m.matches)
    m.addEventListener?.('change', on)
    return () => m.removeEventListener?.('change', on)
  }, [])
  return small ? 8 : 12
}

// The busiest bird gets a big tile and the next a wide one; the last row is
// widened so it ends flush with no gaps.
function tileSizes(birds, cols) {
  const size = birds.map((_, i) => (i === 0 ? 'sd-tile-big' : i === 1 ? 'sd-tile-wide' : ''))
  const singles = Math.max(0, birds.length - 2)
  const r = (6 + singles) % cols          // cells used by the last row (big = 4, wide = 2)
  const last = birds.length - 1
  if (singles > 0 && r) {
    if (cols === 2) size[last] = 'sd-tile-wide'
    else if (r === 1) size[last] = 'sd-tile-full'
    else if (r === 2) { size[last] = 'sd-tile-wide'; size[last - 1] = 'sd-tile-wide' }
    else size[last] = 'sd-tile-wide'
  }
  return birds.map((bird, i) => ({ bird, size: size[i] }))
}

// Calls per hour today (site time), like Chirp Lite's "Your day".
function DayChart({ hourly, nowHour }) {
  if (hourly.length !== 24) return null
  const max = Math.max(1, ...hourly)
  const busiest = hourly.indexOf(Math.max(...hourly))
  const word = (h) => `${h % 12 || 12} ${h < 12 ? 'am' : 'pm'}`
  return (
    <div className="sd-day">
      <div className="flex items-baseline justify-between gap-3">
        <span className="sd-fact-label">Today by hour</span>
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>Busiest around {word(busiest)}</span>
      </div>
      <div className="sd-bars" role="img" aria-label={`Calls by hour today; busiest around ${word(busiest)}`}>
        {hourly.map((v, h) => (
          <div key={h} title={`${word(h)}: ${v} ${v === 1 ? 'call' : 'calls'}`}
               className={`sd-bar${h === nowHour ? ' now' : ''}${h > nowHour ? ' later' : ''}`}
               style={{ height: `${Math.max(v ? 10 : 4, (v / max) * 100)}%` }}/>
        ))}
      </div>
      <div className="sd-bar-labels" aria-hidden="true"><span>12a</span><span>6a</span><span>12p</span><span>6p</span><span>11p</span></div>
    </div>
  )
}

export default function StandardDashboard({ onOpenPicker, onAdvanced }) {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const [allBirds, setAllBirds] = useState(false)
  const birdsRef = useRef(null)
  const limit = useTileLimit()
  const { timezone, fmtTime, fmtDate } = useTz()

  useEffect(() => {
    let alive = true
    const load = () => api.recordings.today()
      .then(d => { if (alive) { setData(d); setFailed(false) } })
      .catch(() => { if (alive) setFailed(true) })
    load()
    let t = null
    const soon = () => { clearTimeout(t); t = setTimeout(load, 2000) }
    const iv = setInterval(whenVisible(load), 60000)
    window.addEventListener('chirp-new-detection', soon)
    window.addEventListener('chirp-resume', soon)
    window.addEventListener('chirp-settings-saved', load)
    return () => {
      alive = false
      clearTimeout(t); clearInterval(iv)
      window.removeEventListener('chirp-new-detection', soon)
      window.removeEventListener('chirp-resume', soon)
      window.removeEventListener('chirp-settings-saved', load)
    }
  }, [])

  const clock = (iso) => (iso ? fmtTime(iso, { second: undefined }).replace(' AM', ' am').replace(' PM', ' pm') : '')
  const species = data?.species || []
  const n = data?.species_count || 0
  const hero = data?.hero
  const busiest = species[0]
  const first = data?.first_song
  const today = fmtDate(new Date().toISOString(), { weekday: 'long', month: 'long', day: 'numeric', year: undefined })
  const headline = !data ? ' '
    : n === 0 ? "It's quiet in your yard so far today."
    : n === 1 ? 'One bird has sung in your yard today.'
    : `${n} birds have sung in your yard today.`
  const heroWhen = hero ? (hero.today ? `Latest · ${clock(hero.time)}` : `Last heard · ${fmtDate(hero.time, { year: undefined })}, ${clock(hero.time)}`) : ''
  const heroCount = hero && species.find(s => s.name === hero.name)?.count

  return (
    <div className="page-root sd-root">
      <div className="sd-wrap">
        <header className="flex items-start justify-between gap-4 flex-wrap animate-slide-down">
          <div className="flex flex-col gap-2.5 min-w-0">
            <p className="sd-eyebrow">{today} · {greeting(hourIn(timezone))}</p>
            <h1 className="sd-headline">{headline}</h1>
          </div>
          <ViewButton onClick={onOpenPicker}/>
        </header>

        {!data && !failed && <Skeleton/>}
        {failed && !data && (
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Couldn't load today's birds. They'll appear when the server answers.</p>
        )}

        {data?.has_station === false && <SetupGuideCard/>}
        {hero && (
          <section aria-label="Latest bird" className="sd-hero animate-slide-up">
            <HeroPhoto hero={hero}/>
            <div className="sd-hero-body">
              <div className="flex flex-col gap-2.5">
                <p className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                  {hero.today && <span className="sd-dot"/>}{heroWhen}
                </p>
                <Link to={`/recordings/${hero.recording_id}`} className="sd-hero-name">{hero.name}</Link>
                {heroCount > 1 && (
                  <p className="text-[15px]" style={{ color: 'var(--text-secondary)' }}>Heard {heroCount} times today.</p>
                )}
              </div>
              {hero.has_audio ? <Player recordingId={hero.recording_id} bird={hero.name}/> : (
                <Link to={`/recordings/${hero.recording_id}`} className="text-sm font-medium" style={{ color: 'var(--accent-400)' }}>Open the recording</Link>
              )}
            </div>
          </section>
        )}

        {data && n > 0 && (
          <section aria-label="Today at a glance" className="sd-facts">
            <div className="sd-fact">
              <span className="sd-fact-label">First song</span>
              <span className="sd-fact-value">{clock(first?.time)}</span>
              <span className="sd-fact-sub">{first?.name}</span>
            </div>
            <div className="sd-fact">
              <span className="sd-fact-label">Busiest bird</span>
              <span className="sd-fact-value">{busiest?.name}</span>
              <span className="sd-fact-sub">{busiest?.count} {busiest?.count === 1 ? 'call' : 'calls'}</span>
            </div>
            <div className="sd-fact">
              <span className="sd-fact-label">Recordings</span>
              <span className="sd-fact-value">{data.recordings}</span>
              <span className="sd-fact-sub">since midnight</span>
            </div>
          </section>
        )}

        {species.length > 0 && (
          <section aria-label="Heard today" className="flex flex-col gap-4" ref={birdsRef}>
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="sd-h2">Heard today</h2>
              {species.length > limit ? (
                <button type="button" onClick={() => setAllBirds(v => !v)} aria-expanded={allBirds}
                        className="text-sm font-medium hover:opacity-80" style={{ color: 'var(--accent-400)' }}>
                  {allBirds ? 'Show fewer' : `All ${species.length} birds`}
                </button>
              ) : (
                <Link to="/library" className="text-sm font-medium" style={{ color: 'var(--accent-400)' }}>Life list</Link>
              )}
            </div>
            <div className="sd-tiles">
              {tileSizes(allBirds ? species : species.slice(0, limit), limit === 8 ? 2 : 4).map(({ bird: s, size }) => (
                <Link key={s.name} to={s.profile_id ? `/library/${s.profile_id}` : '/library'}
                      className={`sd-tile ${size}`}>
                  <Photo src={s.photo} alt="" className="absolute inset-0 w-full h-full object-cover"/>
                  {s.new && <span className="sd-new">New</span>}
                  <span className="sd-tile-caption">
                    <span className="sd-tile-name">{s.name}</span>
                    <span className="sd-count">{s.count}</span>
                  </span>
                </Link>
              ))}
            </div>
            {species.length > limit && (
              // A second toggle under the grid, so a long list closes where it ends.
              <button type="button" className="sd-more" aria-expanded={allBirds}
                      onClick={() => {
                        if (allBirds) birdsRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
                        setAllBirds(v => !v)
                      }}>
                {allBirds ? 'Show fewer' : `Show all ${species.length} birds`}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
                     strokeLinejoin="round" aria-hidden="true" style={{ transform: allBirds ? 'rotate(180deg)' : 'none' }}><path d="M6 9l6 6 6-6"/></svg>
              </button>
            )}
            {data.detections > 0 && <DayChart hourly={data.hourly || []} nowHour={hourIn(timezone)}/>}
          </section>
        )}

        {data?.journal?.text && (
          <section aria-label="Journal" className="sd-journal">
            <span className="sd-fact-label">{data.journal.day === 'today' ? "Today's journal" : "Yesterday's journal"}</span>
            <p className="sd-quote">{data.journal.text}</p>
            <Link to="/journal" className="text-sm font-medium" style={{ color: 'var(--accent-400)' }}>Read the full entry</Link>
          </section>
        )}

        {data && n === 0 && !hero && (
          <section className="sd-journal items-start">
            <p className="sd-quote" style={{ fontStyle: 'normal' }}>No birds yet. Once your station hears one, it shows up here with its photo and song.</p>
            <Link to="/tutorial" className="text-sm font-medium" style={{ color: 'var(--accent-400)' }}>Getting started</Link>
          </section>
        )}

        <p className="text-center text-sm pb-2" style={{ color: 'var(--text-secondary)' }}>
          Want charts, diversity scores and every stat?{' '}
          <button type="button" onClick={onAdvanced} className="font-medium hover:opacity-80" style={{ color: 'var(--accent-400)' }}>Switch to Advanced</button>
        </p>
      </div>
    </div>
  )
}
