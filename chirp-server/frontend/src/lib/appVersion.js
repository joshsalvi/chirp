/**
 * iPhone app version. Each Chirp release ships to TestFlight as its own iOS
 * version: the patch letter is folded into the third number, as in
 * build-ios.sh (0.5.12.e → 0.5.1205, a=1 … z=26, aa=27). Releases before
 * 0.5.12.c used the first three numbers only (0.5.12, 0.5.11).
 */
import { useEffect, useState } from 'react'
import { isNative } from '../native'

export function iosVersionFor(chirpVersion) {
  const [a, b, c, letters = ''] = String(chirpVersion).split('.')
  let n = 0
  for (const ch of letters.toLowerCase()) n = n * 26 + (ch.charCodeAt(0) - 96)
  return `${Number(a)}.${Number(b)}.${Number(c) * 100 + n}`
}

// First release with a separate iOS version per Chirp release.
export const FIRST_PER_RELEASE = '0.5.12.c'

// "0.5.12.c" → sortable tuple, for comparing releases.
export function versionKey(v) {
  const [a, b, c, letters = ''] = String(v).split('.')
  let n = 0
  for (const ch of letters.toLowerCase()) n = n * 26 + (ch.charCodeAt(0) - 96)
  return [Number(a), Number(b), Number(c), n]
}
export const atLeast = (v, min) => {
  const x = versionKey(v), y = versionKey(min)
  for (let i = 0; i < 4; i++) if (x[i] !== y[i]) return x[i] > y[i]
  return true
}

/** The installed iPhone app's version and build, or null outside the app. */
export function useAppInfo() {
  const [info, setInfo] = useState(null)
  useEffect(() => {
    if (!isNative()) return
    import('@capacitor/app')
      .then(({ App }) => App.getInfo())
      .then(i => setInfo({ version: i.version, build: i.build }))
      .catch(() => {})
  }, [])
  return info
}
