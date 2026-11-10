import { createContext, useContext } from 'react'

// { me, openMe() } — who's signed in, and the account sheet.
export const AppContext = createContext({ me: null, openMe: () => {} })
export const useApp = () => useContext(AppContext)

export const APP_NAME = 'Chirp Lite'
export const CHIRP_LIVE_URL = 'https://apps.apple.com/us/app/chirp-live-bird-sound-id/id6827668744'
