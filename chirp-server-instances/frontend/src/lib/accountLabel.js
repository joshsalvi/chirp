// "My Profile" is called "Account" from iPhone app 1.0 on. The iPhone app
// in App Review (0.5.x) was described to Apple as having "My Profile", so
// app versions before 1.0 keep that name until people update. Browsers and
// the web app show "Account".
import { useEffect, useState } from 'react'
import { isNative } from '../native'

let label = isNative() ? 'My Profile' : 'Account'
const listeners = new Set()

if (isNative()) {
  import('@capacitor/app')
    .then(({ App }) => App.getInfo())
    .then(info => {
      const major = parseInt(String(info?.version || '0').split('.')[0], 10)
      if (major >= 1) { label = 'Account'; listeners.forEach(f => f(label)) }
    })
    .catch(() => {})
}

export const accountLabel = () => label

/** Re-renders the caller once the iPhone app's version is known. */
export function useAccountLabel() {
  const [l, set] = useState(label)
  useEffect(() => { listeners.add(set); set(label); return () => { listeners.delete(set) } }, [])
  return l
}
