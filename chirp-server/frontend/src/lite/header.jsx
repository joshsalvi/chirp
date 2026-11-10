import { useApp } from './context'
import { BirdMark } from './icons'

// Big screen title with the account button.
export function Header({ title, sub, children }) {
  const { me, openMe } = useApp()
  const initial = (me?.username || '').slice(0, 1).toUpperCase()
  return (
    <header className="head">
      <div className="head-text">
        {sub && <p className="head-sub">{sub}</p>}
        <h1>{title}</h1>
      </div>
      {children}
      <button className="avatar" onClick={openMe} aria-label="Account and settings">
        {initial || <BirdMark tile={false} size={26} />}
      </button>
    </header>
  )
}
