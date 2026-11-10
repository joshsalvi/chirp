// Sign-in token storage, shared by the main app (lib/api.js) and Chirp Lite
// (src/lite) so one sign-in works for both.
const TOKEN_KEY = 'chirp_token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
  // Multi-instance addition (see ARCHITECTURE.md): reads the
  // active_instance_id claim straight out of the stored JWT's own
  // payload, client-side. Deliberately NOT verified here — only the
  // server's own verification (on every real request) matters for
  // security; this is purely a UI-routing signal ("do we need to show
  // the instance picker before calling anything instance-scoped"), and
  // a tampered value here can't grant access to anything real, since
  // the server independently re-decodes and re-verifies its own copy
  // on every request regardless of what the client thinks it says.
  getActiveInstanceId: () => {
    const token = tokenStore.get()
    if (!token) return null
    try {
      const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
      return payload.active_instance_id || null
    } catch {
      return null
    }
  },
}

// Appends the current auth token as a ?token= query param — for the
// handful of cases where the browser itself makes the request (a plain
// <img>/<audio> src) and can never attach a custom Authorization
// header no matter how the surrounding React code is written. Every
// spectrogram, waveform, and audio-playback URL needs this; a normal
// api.*() call above does NOT, since fetch() already attaches the real
// header — adding this there too wouldn't break anything, but doing it
// only where actually needed keeps the token out of server logs/proxy
// history for the far more common case of a real API call.
export function mediaUrl(path) {
  if (!path) return path
  const token = tokenStore.get()
  if (!token) return path
  const sep = path.includes('?') ? '&' : '?'
  return `${path}${sep}token=${encodeURIComponent(token)}`
}
