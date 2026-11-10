import { Link, useNavigate } from 'react-router-dom'
import { lite } from '../api'
import { CHIRP_LIVE_URL } from '../context'
import { Header } from '../header'
import { Icon } from '../icons'
import { Empty, Failed, Loading, Photo, PlayButton, clock, greeting, plural, useLoad, when } from '../ui'

export default function Today() {
  const { data, error, loading, reload } = useLoad(() => lite.today())
  const date = new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })
  return (
    <>
      <Header sub={date} title={greeting()} />
      {loading && !data ? <Loading /> : error ? <Failed error={error} onRetry={reload} /> : <TodayBody t={data} />}
    </>
  )
}

function TodayBody({ t }) {
  const nav = useNavigate()
  const { hero } = t
  const heroItem = hero?.has_audio && {
    key: 'rec-' + hero.recording_id, src: `/api/v1/recordings/${hero.recording_id}/audio`,
    title: hero.name, subtitle: when(hero.time), photo: hero.photo,
  }
  return (
    <div className="stack">
      {hero ? (
        <article className={'hero' + (hero.profile_id ? ' tappable' : '')}
                 onClick={() => hero.profile_id && nav('/bird/' + hero.profile_id)}>
          <Photo src={hero.photo} name={hero.name} className="hero-photo" />
          <div className="hero-shade" />
          <span className="pill pill-glass">{hero.today ? 'Latest visitor' : 'Last heard'}</span>
          <div className="hero-text">
            <h2>{hero.name}</h2>
            <p>{hero.today ? clock(hero.time) : when(hero.time)}</p>
          </div>
          {heroItem && <PlayButton item={heroItem} size="lg" className="hero-play" label={hero.name} />}
        </article>
      ) : (
        <Empty title="No birds yet">When your Chirp hears its first bird, it shows up here.</Empty>
      )}

      {t.species_count > 0 ? (
        <div className="stats">
          <Stat n={t.species_count} label={t.species_count === 1 ? 'bird today' : 'birds today'} tone="green" />
          {t.new_count > 0
            ? <Stat n={t.new_count} label="new to you" tone="coral" />
            : t.first_song && <Stat n={<TimeValue iso={t.first_song.time} />} label="first song" tone="sun" />}
          <Stat n={t.recordings} label={t.recordings === 1 ? 'recording' : 'recordings'} tone="sky" />
        </div>
      ) : hero && (
        <div className="quiet card">
          <strong>Quiet so far today</strong>
          <span>Birds sing most around sunrise. See who to listen for in the <Link to="/guide">Guide</Link>.</span>
        </div>
      )}

      {t.summary && (
        <blockquote className="journal card">
          <span className="eyebrow">Today’s story</span>
          <p>{t.summary}</p>
        </blockquote>
      )}

      {t.detections > 0 && <DayChart hourly={t.hourly} />}

      {t.species.length > 0 && (
        <section>
          <div className="section-head">
            <h3>Heard today</h3>
            <Link to="/listen" className="more">Listen <Icon.arrow /></Link>
          </div>
          <div className="tiles">
            {t.species.map((s) => <BirdTile key={s.name} bird={s} badge={s.count > 1 ? '×' + s.count : null} sub={clock(s.last)} />)}
          </div>
        </section>
      )}

      <a href={CHIRP_LIVE_URL} target="_blank" rel="noreferrer" className="cta card">
        <span className="cta-icon"><Icon.live /></span>
        <span><strong>Out on a walk?</strong><small>Chirp Live names birds by sound on your iPhone</small></span>
        <Icon.arrow className="cta-arrow" />
      </a>
    </div>
  )
}

// "6:12" large with a small "AM".
function TimeValue({ iso }) {
  const [, time, half] = clock(iso).match(/^(.*?)\s*([AP]M)?$/i) || []
  return <>{time}{half && <small className="stat-unit">{half}</small>}</>
}

function Stat({ n, label, tone }) {
  return (
    <div className={'stat tone-' + tone}>
      <strong className={typeof n === 'number' ? undefined : 'stat-time'}>{typeof n === 'number' ? n.toLocaleString() : n}</strong>
      <span>{label}</span>
    </div>
  )
}

function DayChart({ hourly }) {
  const max = Math.max(1, ...hourly)
  const nowH = new Date().getHours()
  const busiest = hourly.indexOf(Math.max(...hourly))
  const hourWord = (h) => new Date(2000, 0, 1, h).toLocaleTimeString([], { hour: 'numeric' })
  return (
    <section className="card day">
      <div className="section-head">
        <h3>Your day</h3>
        <span className="muted">Busiest around {hourWord(busiest)}</span>
      </div>
      <div className="bars" role="img" aria-label={`Bird activity by hour; busiest around ${hourWord(busiest)}`}>
        {hourly.map((v, h) => (
          <div key={h} className={'bar' + (h === nowH ? ' now' : '') + (h > nowH ? ' later' : '')}
               style={{ height: `${Math.max(v ? 14 : 5, (v / max) * 100)}%` }} title={`${hourWord(h)}: ${plural(v, 'call')}`} />
        ))}
      </div>
      <div className="bar-labels"><span>12a</span><span>6a</span><span>12p</span><span>6p</span><span>11p</span></div>
    </section>
  )
}

export function BirdTile({ bird, badge, sub, children }) {
  const body = (
    <>
      <div className="tile-photo">
        <Photo src={bird.photo} name={bird.name} />
        {bird.new && <span className="pill pill-new">New</span>}
        {badge && <span className="pill pill-count">{badge}</span>}
      </div>
      <div className="tile-text">
        <strong>{bird.name}</strong>
        {sub && <span>{sub}</span>}
        {children}
      </div>
    </>
  )
  return bird.profile_id
    ? <Link to={'/bird/' + bird.profile_id} className="tile">{body}</Link>
    : <div className="tile">{body}</div>
}
