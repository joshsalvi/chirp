import { useState } from 'react'
import { lite } from '../api'
import { Header } from '../header'
import { Icon } from '../icons'
import { Empty, Failed, Loading, useLoad } from '../ui'
import { BirdTile } from './Today'

const CHANCE = { common: 'Common', uncommon: 'Uncommon', rare: 'Rare' }

export default function Guide() {
  const { data, error, loading, reload } = useLoad(() => lite.guide())
  const [show, setShow] = useState('all')
  const birds = (data?.birds || []).filter((b) => show === 'all' || (show === 'todo' ? !b.heard : b.heard))
  const pct = data?.count ? Math.round((data.heard / data.count) * 100) : 0
  return (
    <>
      <Header sub={'Around you in ' + new Date().toLocaleDateString([], { month: 'long' })} title="Bird guide" />
      {loading && !data ? <Loading rows={6} /> : error ? <Failed error={error} onRetry={reload} /> : !data.count ? (
        <Empty title="Set your location">Add your location in full Chirp’s Settings to see which birds are around this month.</Empty>
      ) : (
        <>
          <div className="progress card">
            <div className="progress-text">
              <strong>{data.heard} of {data.count}</strong>
              <span>birds seen near you this month have visited your yard</span>
            </div>
            <div className="meter" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
              <div style={{ width: `${Math.max(pct, 2)}%` }} />
            </div>
          </div>
          <div className="toolbar">
            <div className="chips" role="tablist" aria-label="Show">
              {[['all', 'All'], ['todo', 'Not heard yet'], ['heard', 'Heard']].map(([id, label]) => (
                <button key={id} role="tab" aria-selected={show === id} className={'chip' + (show === id ? ' on' : '')}
                        onClick={() => setShow(id)}>{label}</button>
              ))}
            </div>
          </div>
          {birds.length === 0 ? (
            <Empty title={show === 'todo' ? 'You’ve heard them all!' : 'None yet'}>
              {show === 'todo' ? 'Every bird on this month’s list has visited.' : 'Birds you hear show up here.'}
            </Empty>
          ) : (
            <div className="tiles">
              {birds.map((b) => (
                <BirdTile key={b.name} bird={b}>
                  <span className="tile-tags">
                    <span className={'chance chance-' + b.likely}>{CHANCE[b.likely] || b.likely}</span>
                    {b.heard && <span className="heard"><Icon.check /> Heard</span>}
                  </span>
                </BirdTile>
              ))}
            </div>
          )}
        </>
      )}
    </>
  )
}
