import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { lite, media } from '../api'
import { Icon } from '../icons'
import { Empty, Failed, Photo, PlayButton, longDate, plural, useLoad, when } from '../ui'

const TAG_ICON = { habitat: '🌳', food: '🍒', nesting: '🪺', behavior: '🐦' }

export default function Bird() {
  const { id } = useParams()
  const nav = useNavigate()
  const { data: b, error, loading, reload } = useLoad(() => lite.bird(id), [id])
  useEffect(() => { window.scrollTo(0, 0) }, [id])
  const back = () => (window.history.length > 1 ? nav(-1) : nav('/birds'))

  return (
    <div className="bird">
      <button className="round-btn back" onClick={back} aria-label="Back"><Icon.back /></button>
      {loading && !b ? <div className="skel skel-photo" />
        : error ? <div className="page"><Failed error={error} onRetry={reload} /></div>
        : !b ? <Empty title="Bird not found" />
        : <BirdBody b={b} />}
    </div>
  )
}

function Gallery({ photos, name }) {
  const [i, setI] = useState(0)
  const ref = useRef(null)
  const onScroll = () => {
    const el = ref.current
    if (el) setI(Math.round(el.scrollLeft / el.clientWidth))
  }
  if (!photos.length) return <div className="gallery"><Photo name={name} className="gallery-img" /></div>
  return (
    <div className="gallery">
      <div className="gallery-track" ref={ref} onScroll={onScroll}>
        {photos.map((p, n) => <Photo key={n} src={p.url} name={name} className="gallery-img" alt={`${name}, photo ${n + 1}`} />)}
      </div>
      {photos.length > 1 && (
        <div className="dots">{photos.map((_, n) => <span key={n} className={n === i ? 'on' : ''} />)}</div>
      )}
      {photos[i]?.credit && <span className="credit">{photos[i].yours ? 'Your photo' : '© ' + photos[i].credit.replace(/^\s*(©|\(c\)|copyright)\s*/i, '')}</span>}
    </div>
  )
}

function BirdBody({ b }) {
  const song = b.song && {
    key: b.song.recording_id ? 'rec-' + b.song.recording_id : 'ref-' + b.id,
    src: b.song.audio, start: b.song.starts_at, title: b.name,
    subtitle: b.song.kind === 'yours' ? 'Heard ' + when(b.song.time) : 'Reference song',
    photo: b.photos[0]?.url,
  }
  const facts = [
    b.size && { icon: <Icon.ruler />, label: 'Size', value: b.size.label, detail: b.size.detail, tone: 'sky' },
    b.season && { icon: <Icon.calendar />, label: 'Around', value: b.season, tone: 'sun' },
    { icon: <Icon.ear />, label: 'Visits', value: b.how_often, tone: 'green' },
  ].filter(Boolean)

  return (
    <>
      <Gallery photos={b.photos} name={b.name} />
      <div className="bird-sheet">
        <div className="bird-title">
          <div>
            <h1>{b.name}</h1>
            {b.scientific && <p className="sci">{b.scientific}</p>}
          </div>
          {b.conservation && <span className="pill pill-soft">{b.conservation}</span>}
        </div>

        {song && (
          <div className="song">
            <PlayButton item={song} size="lg" label={b.name + ' song'} />
            <div>
              <strong>{b.song.kind === 'yours' ? 'Hear it in your yard' : 'Hear its song'}</strong>
              <span>{b.song.kind === 'yours' ? 'Recorded ' + when(b.song.time) : (b.song.credit ? 'Recording © ' + b.song.credit : 'Reference recording')}</span>
            </div>
          </div>
        )}

        <div className="facts">
          {facts.map((f) => (
            <div key={f.label} className={'fact tone-' + f.tone} title={f.detail || undefined}>
              {f.icon}
              <span>{f.label}</span>
              <strong>{f.value}</strong>
            </div>
          ))}
        </div>

        {b.heard_count > 0 && (
          <p className="heard-line">
            Your Chirp has heard it <strong>{plural(b.heard_count, 'time')}</strong>
            {b.first_heard && <> since {longDate(b.first_heard)}</>}.
          </p>
        )}

        {b.blurb && <p className="blurb">{b.blurb}</p>}

        {b.fun_fact && (
          <div className="funfact">
            <span className="eyebrow">Did you know?</span>
            <p>{b.fun_fact}</p>
          </div>
        )}

        {b.tags?.length > 0 && (
          <div className="tags">
            {b.tags.map((t) => <span key={t.kind} className="tag"><span aria-hidden="true">{TAG_ICON[t.kind] || '•'}</span>{t.label}</span>)}
          </div>
        )}

        {b.range_map && (
          <section className="range">
            <h3>Where it lives</h3>
            {b.range_map_source && <p className="range-source">Map: {b.range_map_source}</p>}
            <img src={media(b.range_map)} alt={`Range map for ${b.name}`} loading="lazy"
                 onError={(e) => { e.currentTarget.closest('section').style.display = 'none' }} />
          </section>
        )}

        {b.heard_count > 0 && (
          <Link to={'/listen?bird=' + encodeURIComponent(b.name)} className="btn wide">
            <Icon.listen /> All recordings of this bird
          </Link>
        )}
      </div>
    </>
  )
}
