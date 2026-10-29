import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tv, Check } from 'lucide-react'
import { api } from '../lib/api'
import StoreBadge from './StoreBadge'

// Links an Apple TV to this account: the TV shows a 6-character code (and a
// QR code to /tv?code=...); entering it here signs the TV in (api/tv.py).
export function TVLinkForm({ initialCode = '' }) {
  const [code, setCode] = useState(initialCode.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6))
  const [state, setState] = useState(null)   // null | 'sending' | 'linked' | error text
  const submit = async (e) => {
    e.preventDefault()
    if (code.length !== 6) { setState('Enter the 6-character code from your TV.'); return }
    setState('sending')
    try { await api.tv.approve(code); setState('linked') }
    catch (err) { setState(err.message || 'Couldn’t link the TV. Try again.') }
  }
  if (state === 'linked') {
    return (
      <p className="text-sm flex items-center gap-2" style={{ color: 'var(--pastel-green, #4ade80)' }}>
        <Check size={16}/> Your Apple TV is signed in. It opens Chirp in a few seconds.
      </p>
    )
  }
  return (
    <form onSubmit={submit} className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <input id="tv-code" value={code} autoComplete="off" autoCapitalize="characters" spellCheck={false}
               aria-label="Code shown on your TV" placeholder="ABC234" maxLength={7}
               onChange={e => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6))}
               className="input text-lg tracking-[0.3em] font-mono w-44 text-center"/>
        <button type="submit" disabled={state === 'sending'} className="btn-primary text-sm px-4 py-2">
          {state === 'sending' ? 'Linking…' : 'Link TV'}
        </button>
      </div>
      {state && state !== 'sending' && <p className="text-xs" style={{ color: 'var(--pastel-red)' }}>{state}</p>}
    </form>
  )
}

export default function TVLinkPage() {
  const [params] = useSearchParams()
  return (
    <div className="max-w-md mx-auto py-8 space-y-4">
      <div className="flex items-center gap-3">
        <Tv size={26} style={{ color: 'var(--accent-400)' }}/>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-serif, inherit)' }}>Link your Apple TV</h1>
      </div>
      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
        Open Chirp on your Apple TV and enter the code it shows. The TV signs in to this site as you, and can only view birds, play recordings and listen through your stations.
      </p>
      <TVLinkForm initialCode={params.get('code') || ''}/>
      <div className="flex items-center gap-3 flex-wrap pt-4" style={{ borderTop: '1px solid var(--border-subtle, rgba(255,255,255,.08))' }}>
        <p className="text-xs flex-1 min-w-0" style={{ color: 'var(--text-secondary)' }}>Chirp isn’t on your TV yet? Get it from the App Store on the TV.</p>
        <StoreBadge kind="tv"/>
      </div>
    </div>
  )
}
