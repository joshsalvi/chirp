import { useEffect } from 'react'
import { account, AuthError } from '../api'
import { APP_NAME, CHIRP_LIVE_URL, useApp } from '../context'
import { BirdMark, Icon } from '../icons'
import { tokenStore } from '../../lib/token'

export default function MeSheet({ onClose }) {
  const { me } = useApp()
  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])

  // Remember the choice when signed in, then open the full app.
  const openFull = async () => {
    try { if (me?.username) await account.setMode('pro') } catch (e) { if (e instanceof AuthError) return }
    window.location.href = '/'
  }
  const signOut = () => { account.logout(); window.location.reload() }

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Account" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-grip" />
        <div className="sheet-head">
          <BirdMark size={52} />
          <div>
            <strong>{me?.username || APP_NAME}</strong>
            <span>{me?.username ? 'Signed in' : 'Your backyard birds'}</span>
          </div>
          <button className="round-btn" onClick={onClose} aria-label="Close"><Icon.close /></button>
        </div>
        <div className="sheet-list">
          <button className="row" onClick={openFull}>
            <span className="row-icon tone-green"><Icon.grid /></span>
            <span><strong>Open full Chirp</strong><small>Statistics, devices, settings and more</small></span>
            <Icon.arrow />
          </button>
          <a className="row" href={CHIRP_LIVE_URL} target="_blank" rel="noreferrer">
            <span className="row-icon tone-sky"><Icon.live /></span>
            <span><strong>Get Chirp Live</strong><small>Name birds by sound anywhere, on iPhone</small></span>
            <Icon.arrow />
          </a>
          {tokenStore.get() && (
            <button className="row" onClick={signOut}>
              <span className="row-icon tone-coral"><Icon.out /></span>
              <span><strong>Sign out</strong></span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
