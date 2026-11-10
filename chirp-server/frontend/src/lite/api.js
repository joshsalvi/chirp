// Chirp Lite's API client: the /api/v1/lite screens plus sign-in.
// Shares the main app's token (lib/token.js), so one sign-in covers both.
import { tokenStore, mediaUrl } from '../lib/token'

const BASE = '/api/v1'

export class AuthError extends Error {}

async function request(path, options = {}) {
  const token = tokenStore.get()
  const res = await fetch(BASE + path, {
    ...options,
    headers: {
      ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
      ...options.headers,
    },
  })
  if (res.status === 401) {
    window.dispatchEvent(new Event('lite-signed-out'))
    throw new AuthError('Please sign in')
  }
  if (!res.ok) {
    let msg = 'Something went wrong'
    try {
      const d = await res.json()
      if (typeof d.detail === 'string') msg = d.detail
    } catch {}
    const err = new Error(msg)
    err.status = res.status
    throw err
  }
  return res.status === 204 ? null : res.json()
}

const q = (params) => {
  const s = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== '')).toString()
  return s ? '?' + s : ''
}

export const lite = {
  today: () => request('/lite/today'),
  birds: (sort = 'recent') => request('/lite/birds' + q({ sort })),
  listen: ({ before, bird, limit = 20 } = {}) => request('/lite/listen' + q({ before, bird, limit })),
  guide: () => request('/lite/guide'),
  bird: (id) => request('/lite/bird/' + encodeURIComponent(id)),
  songline: (id, bird) => request(`/lite/recording/${encodeURIComponent(id)}/songline` + q({ bird })),
}

export const account = {
  me: () => request('/auth/me'),
  login: async (username, password) => {
    const fd = new FormData()
    fd.append('username', username)
    fd.append('password', password)
    fd.append('remember_me', 'true')
    const res = await fetch(BASE + '/auth/login', { method: 'POST', body: fd })
    if (res.status === 429) throw new Error('Too many tries. Wait a minute and try again.')
    if (!res.ok) throw new Error('That username and password didn’t match.')
    const data = await res.json()
    tokenStore.set(data.access_token)
    if (data.username) localStorage.setItem('chirp_user', data.username)
    return data
  },
  logout: () => {
    fetch(BASE + '/auth/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + tokenStore.get() } }).catch(() => {})
    tokenStore.clear()
  },
  setMode: (ui_mode) => request('/auth/me/profile', { method: 'PUT', body: JSON.stringify({ ui_mode }) }),
  // Multi-site servers: a sign-in with several sites needs one picked.
  needsSite: () => !!tokenStore.get() && typeof tokenStore.getActiveInstanceId === 'function' && !tokenStore.getActiveInstanceId(),
  sites: () => request('/instances'),
  pickSite: async (id) => {
    const data = await request('/instances/switch', { method: 'POST', body: JSON.stringify({ instance_id: id }) })
    tokenStore.set(data.access_token)
  },
}

// <img>/<audio> addresses. Server paths may need the token; others are as is.
export const media = (path) => (path && path.startsWith('/api/') ? mediaUrl(path) : path)
