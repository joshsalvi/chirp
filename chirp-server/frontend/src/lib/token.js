// Sign-in token storage, shared by the main app (lib/api.js) and Chirp Lite
// (src/lite) so one sign-in works for both.
const TOKEN_KEY = 'chirp_token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

// Media URLs (<img>/<audio> src). This server authenticates media like any
// other request, so the path is used as is (the instances fork adds a token).
export function mediaUrl(path) { return path }
