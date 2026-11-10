import { useMemo, useState } from 'react'
import { lite } from '../api'
import { Header } from '../header'
import { Icon } from '../icons'
import { Empty, Failed, Loading, plural, useLoad, when } from '../ui'
import { BirdTile } from './Today'

const SORTS = [
  { id: 'recent', label: 'Recent' },
  { id: 'most', label: 'Most heard' },
  { id: 'new', label: 'Newest' },
  { id: 'az', label: 'A–Z' },
]

export default function Birds() {
  const [sort, setSort] = useState(() => sessionStorageGet('lite_birds_sort') || 'recent')
  const [find, setFind] = useState('')
  const { data, error, loading, reload } = useLoad(() => lite.birds(sort), [sort])
  const birds = useMemo(() => {
    const words = find.trim().toLowerCase()
    return (data?.birds || []).filter((b) => !words || b.name.toLowerCase().includes(words))
  }, [data, find])

  const choose = (id) => { setSort(id); sessionStorageSet('lite_birds_sort', id) }
  const sub = (b) => sort === 'most' ? plural(b.count, 'time')
    : sort === 'new' ? 'First ' + when(b.first)
    : sort === 'az' ? plural(b.count, 'time') : when(b.last)

  return (
    <>
      <Header sub={data ? plural(data.count, 'kind') + ' of bird' : 'Your collection'} title="Your birds" />
      <div className="toolbar">
        <div className="chips" role="tablist" aria-label="Sort birds">
          {SORTS.map((s) => (
            <button key={s.id} role="tab" aria-selected={sort === s.id} className={'chip' + (sort === s.id ? ' on' : '')}
                    onClick={() => choose(s.id)}>{s.label}</button>
          ))}
        </div>
        {(data?.count || 0) > 8 && (
          <label className="search">
            <Icon.search />
            <input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Find a bird" aria-label="Find a bird" />
          </label>
        )}
      </div>
      {loading && !data ? <Loading rows={6} /> : error ? <Failed error={error} onRetry={reload} /> : (
        data.count === 0 ? <Empty title="Your collection starts here">Every new bird your Chirp hears gets a card.</Empty>
        : birds.length === 0 ? <Empty title="No match">Nothing called “{find}” yet.</Empty>
        : <div className="tiles">{birds.map((b) => <BirdTile key={b.name} bird={b} sub={sub(b)} />)}</div>
      )}
    </>
  )
}

function sessionStorageGet(k) { try { return sessionStorage.getItem(k) } catch { return null } }
function sessionStorageSet(k, v) { try { sessionStorage.setItem(k, v) } catch {} }
