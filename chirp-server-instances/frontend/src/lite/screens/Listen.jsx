import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { lite, media } from '../api'
import { Header } from '../header'
import { Icon } from '../icons'
import { useIsPlaying } from '../player'
import { Empty, Failed, Loading, Photo, PlayButton, when } from '../ui'

export default function Listen() {
  const [params, setParams] = useSearchParams()
  const bird = params.get('bird') || ''
  const [cards, setCards] = useState([])
  const [next, setNext] = useState(null)
  const [state, setState] = useState({ loading: true, error: null })

  const load = useCallback(async (before) => {
    setState({ loading: true, error: null })
    try {
      const page = await lite.listen({ before, bird: bird || undefined })
      setCards((c) => (before ? [...c, ...page.recordings] : page.recordings))
      setNext(page.next_before)
      setState({ loading: false, error: null })
    } catch (error) {
      setState({ loading: false, error })
    }
  }, [bird])

  useEffect(() => { setCards([]); load() }, [load])

  return (
    <>
      <Header sub={bird ? 'Recordings of' : 'Tap a card to hear it'} title={bird || 'Listen'} />
      {bird && (
        <div className="toolbar">
          <button className="chip on chip-x" onClick={() => setParams({})}>{bird} <Icon.close /></button>
        </div>
      )}
      {state.error && !cards.length ? <Failed error={state.error} onRetry={() => load()} />
        : state.loading && !cards.length ? <Loading rows={2} />
        : !cards.length ? <Empty title="Nothing to hear yet">Recordings show up here as your Chirp catches birds.</Empty>
        : (
          <div className="feed">
            {cards.map((c) => <SoundCard key={c.id} c={c} />)}
            {next && (
              <button className="btn btn-soft wide" disabled={state.loading} onClick={() => load(next)}>
                {state.loading ? 'Loading…' : 'Show older'}
              </button>
            )}
          </div>
        )}
    </>
  )
}

function SoundCard({ c }) {
  const item = c.has_audio && {
    key: 'rec-' + c.id, src: c.audio, start: c.starts_at, title: c.bird, subtitle: when(c.time), photo: c.photo,
  }
  const { active, progress } = useIsPlaying(item?.key)
  const others = c.others?.length ? 'with ' + c.others.slice(0, 2).join(', ') + (c.others.length > 2 ? ` +${c.others.length - 2}` : '') : null
  return (
    <article className={'sound card' + (active ? ' active' : '')}>
      <div className="sound-top">
        {c.profile_id
          ? <Link to={'/bird/' + c.profile_id} className="sound-photo"><Photo src={c.photo} name={c.bird} /></Link>
          : <div className="sound-photo"><Photo src={c.photo} name={c.bird} /></div>}
        <div className="sound-text">
          <strong>{c.bird}</strong>
          <span>{when(c.time)}{c.duration ? ` · ${Math.round(c.duration)}s` : ''}</span>
          {others && <span className="others">
            {c.other_photos?.slice(0, 2).map((p, i) => p && <img key={i} src={media(p)} alt="" />)}
            {others}
          </span>}
        </div>
        <PlayButton item={item} label={c.bird} />
      </div>
      {c.spectrogram && (
        <div className="spectro">
          <img src={media(c.spectrogram)} alt="" loading="lazy" onError={(e) => { e.currentTarget.parentElement.style.display = 'none' }} />
          {active && <div className="spectro-head" style={{ left: `${progress * 100}%` }} />}
        </div>
      )}
    </article>
  )
}
