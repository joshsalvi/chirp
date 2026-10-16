// Chirp API client
import { saveUrl } from './download'
import { hapticEvent } from './haptics'
const BASE = '/api/v1'

// Extracts a readable error message from a parsed JSON error body's
// `detail` field. FastAPI's own automatic validation errors shape
// `detail` as an ARRAY of {loc, msg, type} objects, not a string —
// every raw-XHR/fetch upload path below used to do `detail || fallback`
// and hand the result straight to `new Error(...)`, which silently
// stringifies a non-string via JS's default object-to-string coercion,
// producing the literal text "[object Object]" in the UI instead of
// the actual validation message. request()'s own error handling
// already guards against this (only trusts `detail` when it's already
// a string) — but that guard lives in request() alone, and the several
// upload endpoints below bypass request() entirely (a multipart body
// needs the browser's own Content-Type boundary, not request()'s
// hardcoded application/json), so each grew its own copy of the same
// unguarded pattern independently. This is the one shared fix for all
// of them, extracting each validation error's own message instead of
// just falling back to a generic one.
function extractErrorDetail(detail, fallback) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail.map(e => {
      if (typeof e === 'string') return e
      const loc = Array.isArray(e?.loc) ? e.loc.filter(x => x !== 'body').join('.') : ''
      return loc ? `${loc}: ${e?.msg || 'invalid value'}` : (e?.msg || 'invalid value')
    })
    return msgs.length ? msgs.join('; ') : fallback
  }
  if (detail && typeof detail === 'object' && typeof detail.msg === 'string') return detail.msg
  return fallback
}

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

// ── GET cache ────────────────────────────────────────────────────────────────
// Makes going back to a page you just left instant (the iOS tab bar mostly).
// - Identical GETs in flight at once share one network request.
// - A page opened within NAV_WINDOW_MS of a route change gets a response
//   younger than CACHE_TTL_MS from memory. Later calls (polling, refresh
//   buttons, WebSocket-driven reloads) always go to the network.
// - Any write (non-GET), a new detection, a notification or a settings save
//   empties the cache.
const CACHE_TTL_MS = 30_000
const NAV_WINDOW_MS = 1500
const getCache = new Map()   // key → { at, data }
const inflight = new Map()   // key → Promise
let navAt = 0

export function markNavigation() { navAt = Date.now() }
export function clearApiCache() { getCache.clear() }

if (typeof window !== 'undefined') {
  for (const ev of ['chirp-new-detection', 'chirp-notification', 'chirp-settings-saved']) {
    window.addEventListener(ev, clearApiCache)
  }
}

// POSTs that record or warm something but change no data a page shows.
const KEEPS_CACHE = /^\/(auth\/activity\/ping|auth\/logout|recordings\/ai-warm|diagnostics\/client|push\/(register|unregister|test)-native)\b/

function cachedGet(path, load) {
  const key = `${tokenStore.get() || ''}|${path}`
  const copy = d => (d == null ? d : structuredClone(d))
  const hit = getCache.get(key)
  if (hit && Date.now() - navAt < NAV_WINDOW_MS && Date.now() - hit.at < CACHE_TTL_MS) {
    return Promise.resolve(copy(hit.data))
  }
  if (inflight.has(key)) return inflight.get(key).then(copy)
  const p = load()
    .then(data => { if (data != null) getCache.set(key, { at: Date.now(), data }); return data })
    .finally(() => inflight.delete(key))
  inflight.set(key, p)
  return p.then(copy)
}

async function request(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  if (method !== 'GET') {
    if (KEEPS_CACHE.test(path)) return sendRequest(path, options)
    clearApiCache()
    return sendRequest(path, options).catch(e => { hapticEvent('error'); throw e })
  }
  return cachedGet(path, () => sendRequest(path, options))
}

async function sendRequest(path, options = {}) {
  const token = tokenStore.get()
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  if (token) headers['Authorization'] = 'Bearer ' + token

  const res = await fetch(`${BASE}${path}`, { ...options, headers })

  if (res.status === 401) {
    tokenStore.clear()
    // Redirect to login only if not already there
    if (window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
    throw new Error('Not authenticated')
  }

  if (!res.ok) {
    // This used to do `const err = await res.text()` and throw that raw
    // body verbatim as the error message — fine for a normal JSON
    // {"detail": "..."} error, but a non-JSON error response (a
    // proxy/CDN's own HTML error page for a 502/504, for example) got
    // dumped whole, sometimes several KB of raw HTML, directly into a
    // UI element expecting a short message. Now checks the content-type
    // and only trusts a parsed JSON `detail` field for the message shown
    // to the user; anything else collapses to a short, safe, generic
    // message instead.
    const ct = res.headers.get('content-type') || ''
    let message = `Request failed (HTTP ${res.status})`
    if (ct.includes('application/json')) {
      try {
        const body = await res.json()
        if (body && typeof body.detail === 'string') message = body.detail
        else if (body && typeof body === 'string') message = body
      } catch (e) { /* malformed JSON despite the content-type header — keep the generic message */ }
    }
    // Defensive cap regardless of source — a legitimate but very long
    // JSON `detail` string shouldn't be able to do this either.
    if (message.length > 500) message = message.slice(0, 500) + '…'
    const err = new Error(message)
    // Attach the real status code so callers can distinguish error types
    // reliably (e.g. 403 vs 404 vs 500) instead of string-matching on
    // message text, which breaks the moment a backend's own detail
    // message doesn't happen to mention the status code anywhere in it
    // — confirmed directly: GlobalAdmin.jsx's own forbidden-page check
    // silently never triggered for exactly this reason, since a 403's
    // detail is "Global admin access required", not anything containing
    // the digits "403".
    err.status = res.status
    throw err
  }
  // 204 No Content (DELETE, etc.) — no body to parse
  if (res.status === 204 || res.headers.get('content-length') === '0') return null
  const ct = res.headers.get('content-type') || ''
  if (!ct.includes('application/json')) return null
  return res.json()
}

export const api = {
  health: () => request('/health'),

  // Multi-instance addition (see ARCHITECTURE.md) — registry-level
  // actions, work regardless of whether an instance is currently active.
  instances: {
    list: () => request('/instances'),
    create: async (body) => {
      const data = await request('/instances/create', { method: 'POST', body: JSON.stringify(body) })
      tokenStore.set(data.access_token)
      return data
    },
    join: async (body) => {
      const data = await request('/instances/join', { method: 'POST', body: JSON.stringify(body) })
      tokenStore.set(data.access_token)
      return data
    },
    switch: async (instanceId) => {
      const data = await request('/instances/switch', { method: 'POST', body: JSON.stringify({ instance_id: instanceId }) })
      tokenStore.set(data.access_token)
      return data
    },
    // FormData upload, not JSON — same reasoning as settings.backup.restore()
    // above: request()'s own unconditional Content-Type: application/json
    // header would break the multipart boundary the browser needs to set
    // itself for a real file upload.
    import: async (formData) => {
      const token = localStorage.getItem('chirp_token')
      clearApiCache()
      const res = await fetch(`${BASE}/instances/import`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      })
      if (!res.ok) {
        const e = await res.json().catch(() => ({}))
        throw new Error(e.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      tokenStore.set(data.access_token)
      return data
    },
  },

  // Global admin panel — server-wide management, gated by is_global_admin
  // on the caller's own GlobalUser row (see app/api/admin_panel.py).
  admin: {
    overview: () => request('/admin/overview'),
    instances: () => request('/admin/instances'),
    instanceMembers: (instanceId) => request(`/admin/instances/${instanceId}/members`),
    addMember: (instanceId, body) => request(`/admin/instances/${instanceId}/members`, { method: 'POST', body: JSON.stringify(body) }),
    updateMembershipRole: (membershipId, role) => request(`/admin/memberships/${membershipId}`, { method: 'PATCH', body: JSON.stringify({ role }) }),
    removeMembership: (membershipId) => request(`/admin/memberships/${membershipId}`, { method: 'DELETE' }),
    deleteInstance: (instanceId) => request(`/admin/instances/${instanceId}`, { method: 'DELETE' }),
    users: () => request('/admin/users'),
    updateUser: (userId, body) => request(`/admin/users/${userId}`, { method: 'PATCH', body: JSON.stringify(body) }),
    tailscaleStatus: () => request('/admin/tailscale-status'),
    tailscaleConfig: (body) => request('/admin/tailscale-config', { method: 'POST', body: JSON.stringify(body) }),
    headscaleNodes: () => request('/admin/headscale-nodes'),
    headscaleBasicAuth: () => request('/admin/headscale-basic-auth'),
    saveHeadscaleBasicAuth: (body) => request('/admin/headscale-basic-auth', { method: 'POST', body: JSON.stringify(body) }),
    instanceDiagnostics: (instanceId, mode = 'full') => request(`/admin/instances/${instanceId}/diagnostics?mode=${mode}`),
    siteRequests: (status) => request(`/admin/site-requests${status ? `?status=${status}` : ''}`),
    approveSiteRequest: (id) => request(`/admin/site-requests/${id}/approve`, { method: 'POST' }),
    denySiteRequest: (id, body) => request(`/admin/site-requests/${id}/deny`, { method: 'POST', body: JSON.stringify(body) }),
    deleteSiteRequest: (id) => request(`/admin/site-requests/${id}`, { method: 'DELETE' }),
    supportMessages: () => request('/admin/support'),
    markSupportMessage: (id, done) => request(`/admin/support/${id}`, { method: 'PATCH', body: JSON.stringify({ done }) }),
    deleteSupportMessage: (id) => request(`/admin/support/${id}`, { method: 'DELETE' }),
    relayServers: () => request('/admin/relay-servers'),
    createRelayServer: (body) => request('/admin/relay-servers', { method: 'POST', body: JSON.stringify(body) }),
    updateRelayServer: (id, body) => request(`/admin/relay-servers/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    deleteRelayServer: (id) => request(`/admin/relay-servers/${id}`, { method: 'DELETE' }),
  },

  support: {
    send: (body) => request('/support', { method: 'POST', body: JSON.stringify(body) }),
  },

  notifications: {
    list:    (limit = 100) => request(`/notifications?limit=${limit}`),
    unread:  () => request('/notifications/unread'),
    readAll: () => request('/notifications/read-all', { method: 'POST' }),
    read:    (id) => request(`/notifications/${id}/read`, { method: 'POST' }),
    clear:   () => request('/notifications', { method: 'DELETE' }),
    remove:  (id) => request(`/notifications/${id}`, { method: 'DELETE' }),
    prefs:   () => request('/notifications/prefs'),
    putPrefs: (body) => request('/notifications/prefs', { method: 'PUT', body: JSON.stringify(body) }),
    addWatch: (common_name, mode) => request('/notifications/watches', { method: 'POST', body: JSON.stringify({ common_name, mode }) }),
    updateWatch: (id, mode) => request(`/notifications/watches/${id}`, { method: 'PUT', body: JSON.stringify({ mode }) }),
    deleteWatch: (id) => request(`/notifications/watches/${id}`, { method: 'DELETE' }),
  },
  push: {
    vapidPublicKey: () => request('/push/vapid-public-key'),
    subscribe: (body) => request('/push/subscribe', { method: 'POST', body: JSON.stringify(body) }),
    unsubscribe: (endpoint) => request('/push/unsubscribe', { method: 'POST', body: JSON.stringify({ endpoint }) }),
    status: (endpoint) => request(`/push/status${endpoint ? '?endpoint=' + encodeURIComponent(endpoint) : ''}`),
    test: (endpoint) => request('/push/test', { method: 'POST', body: JSON.stringify({ endpoint }) }),
    // Native (APNs) counterpart to subscribe/unsubscribe above, for the
    // Capacitor app rather than the PWA — see App.jsx's push
    // registration effect and services/apns_push.py for the full path
    // this feeds into.
    registerNative: (deviceToken) => request('/push/register-native', { method: 'POST', body: JSON.stringify({ device_token: deviceToken }) }),
    testNative: () => request('/push/test-native', { method: 'POST' }),
    unregisterNative: (deviceToken) => request('/push/unregister-native', { method: 'POST', body: JSON.stringify({ device_token: deviceToken }) }),
  },

  // Reporting and blocking notes (api/moderation.py)
  moderation: {
    report:  (commentId, reason) => request('/moderation/report', { method: 'POST', body: JSON.stringify({ comment_id: commentId, reason }) }),
    blocks:  () => request('/moderation/blocks'),
    block:   (author) => request('/moderation/blocks', { method: 'POST', body: JSON.stringify({ author }) }),
    unblock: (author) => request(`/moderation/blocks/${encodeURIComponent(author)}`, { method: 'DELETE' }),
  },

  recordings: {
    aiRecheck: (id) => request(`/recordings/${id}/ai-recheck`, { method: 'POST' }),
    aiWarm: () => request(`/recordings/ai-warm`, { method: 'POST' }),
    list: (params = {}) => {
      const qs = new URLSearchParams(params).toString()
      return cachedGet(`/recordings?${qs}#list`, () => api.recordings._list(qs))
    },
    _list: async (qs) => {
      const token = localStorage.getItem('chirp_token')
      const headers = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${BASE}/recordings${qs ? '?' + qs : ''}`, { headers })
      if (res.status === 401) {
        // Same handling as the shared request() helper — without this,
        // an expired/invalid token caused every subsequent list() call
        // (e.g. clicking a different page-size button) to silently fail
        // with no redirect and no token clearing, while the calling
        // component's error handling (RecordingsList.jsx's .catch(() =>
        // {})) swallowed the failure completely. The visible symptom was
        // the page looking "stuck" on whatever had last loaded
        // successfully, regardless of what the person clicked afterward,
        // with nothing telling them they'd been logged out.
        tokenStore.clear()
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
        throw new Error('Not authenticated')
      }
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`) }
      const data = await res.json()
      const total = res.headers.get('X-Total-Count')
      return { items: data, total: total ? parseInt(total, 10) : null }
    },
    get: (id) => request(`/recordings/${id}`),
    haikuboxList: async (params = {}) => {
      const qs = new URLSearchParams(params).toString()
      const token = localStorage.getItem('chirp_token')
      const headers = token ? { Authorization: `Bearer ${token}` } : {}
      const res = await fetch(`${BASE}/recordings/haikubox${qs ? '?' + qs : ''}`, { headers })
      if (res.status === 401) {
        // Same fix as recordings.list() above — see that comment for the
        // full explanation of why this matters.
        tokenStore.clear()
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
        throw new Error('Not authenticated')
      }
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`) }
      const data = await res.json()
      const total = res.headers.get('X-Total-Count')
      return { items: data, total: total ? parseInt(total, 10) : null }
    },
    haikuboxSummary: () => request('/recordings/haikubox/summary'),
    stats: (period = '24h') => request(`/recordings/stats?period=${period}`),
    dashboardSummary: () => request('/recordings/statistics/dashboard-summary'),
    yardPulse: () => request('/recordings/statistics/yard-pulse'),
    dailyJournal: () => request('/recordings/statistics/daily-journal'),
    digest:       (date) => request(`/recordings/statistics/digest${date ? `?date=${date}` : ''}`),
    regenerateDailyJournal: () => request('/recordings/statistics/daily-journal/regenerate', { method: 'POST' }),
    weeklyJournal: () => request('/recordings/statistics/weekly-journal'),
    regenerateWeeklyJournal: () => request('/recordings/statistics/weekly-journal/regenerate', { method: 'POST' }),
    diversityTrend: (window = '12') => request(`/recordings/statistics/diversity-trend?window=${window}`),
    speciesStreaks: () => request('/recordings/statistics/species-streaks'),
    batActivity: (nights = 30) => request(`/recordings/statistics/bat-activity?nights=${nights}`),
    audioUrl: (id) => mediaUrl(`${BASE}/recordings/${id}/audio`),
    audioEnhancedUrl: (id) => mediaUrl(`${BASE}/recordings/${id}/audio/enhanced`),
    audioRumbleRemovedUrl: (id, hz) => mediaUrl(`${BASE}/recordings/${id}/audio/rumble-removed${hz != null ? `?hz=${hz}` : ''}`),
    audioRumbleRemovedEnhancedUrl: (id, hz) => mediaUrl(`${BASE}/recordings/${id}/audio/rumble-removed-enhanced${hz != null ? `?hz=${hz}` : ''}`),
    audioDewobbledUrl: (id) => mediaUrl(`${BASE}/recordings/${id}/audio/dewobbled`),
    audioDewobbledEnhancedUrl: (id) => mediaUrl(`${BASE}/recordings/${id}/audio/dewobbled-enhanced`),
    audioAiEnhancedUrl: (id) => mediaUrl(`${BASE}/recordings/${id}/audio/ai-enhanced`),
    clipAiEnhancedUrl: (rId, dId) => mediaUrl(`${BASE}/recordings/${rId}/clip/${dId}/ai-enhanced`),
    spectrogramUrl: (id) => mediaUrl(`${BASE}/recordings/${id}/spectrogram`),
    clipUrl: (rId, dId) => mediaUrl(`${BASE}/recordings/${rId}/clip/${dId}`),
    clipEnhancedUrl: (rId, dId) => mediaUrl(`${BASE}/recordings/${rId}/clip/${dId}/enhanced`),
    clipRumbleRemovedUrl: (rId, dId) => mediaUrl(`${BASE}/recordings/${rId}/clip/${dId}/rumble-removed`),
    clipCleanUrl: (rId, dId) => mediaUrl(`${BASE}/recordings/${rId}/clip/${dId}/rumble-removed?nr=true`),
    waveform: (id, points = 200) => request(`/recordings/${id}/waveform?points=${points}`),
    upload: async (fileOrFormData, onProgress) => {
      // Accept either a File object or a pre-built FormData
      const fd = (fileOrFormData instanceof FormData)
        ? fileOrFormData
        : (() => { const f = new FormData(); f.append('file', fileOrFormData); return f })()
      const token = tokenStore.get()
      // Reported directly, confirmed by ruling out everything else first
      // (Cloudflare, the tunnel, multi-tenancy, VPN/Private Relay — all
      // real things worth checking, none of them it): this was
      // XMLHttpRequest, which has a genuine, documented WebKit bug where
      // Safari can silently send an EMPTY body for a FormData containing
      // a File object — arrives with a correctly-formed multipart
      // Content-Type/boundary but zero bytes behind it, which is exactly
      // "file: Field required" with Content-Length: 0. Confirmed by
      // elimination: fails in Safari on iOS, works in Chrome on iOS
      // (shares Safari's rendering engine but not its full networking
      // stack) and in Safari on macOS. fetch() does not have this bug.
      // Costs the upload progress percentage (fetch has no equivalent to
      // xhr.upload.onprogress) — onProgress is now called with 0 then 1
      // instead of granular updates; a real upload actually completing
      // is a large enough improvement over one that silently never does
      // to be worth that trade.
      if (onProgress) onProgress(0)
      let res
      try {
        clearApiCache()
        res = await fetch(`${BASE}/recordings/upload-manual`, {
          method: 'POST',
          headers: token ? { 'Authorization': 'Bearer ' + token } : {},
          body: fd,
        })
      } catch (e) {
        throw new Error('Network error — could not reach the server')
      }
      // 100, not 1 — ManualUpload.jsx renders this directly as `${progress}%`
      // (a 0-100 scale). The XHR version this replaced called back with
      // e.loaded / e.total (a 0-1 fraction) — a real, separate, pre-existing
      // bug that made the progress bar sit visibly stuck under 1% for the
      // entire upload regardless of actual progress, only reaching 100 when
      // ManualUpload.jsx's own "processing" transition set it explicitly
      // afterward. Fixed while already here rather than carried forward.
      if (onProgress) onProgress(100)
      if (res.status < 300) {
        try { return await res.json() }
        catch { throw new Error('Invalid response') }
      }
      let msg = await res.text()
      try { msg = extractErrorDetail(JSON.parse(msg)?.detail, msg) } catch {}
      throw new Error(msg)
    },
    share: (id) => request(`/recordings/${id}/share`, { method: 'POST' }),
    getShared: (token) => request(`/recordings/shared/${token}`),
    delete: (id, { deleteFiles=true, hardDelete=true } = {}) => request(`/recordings/${id}?delete_files=${deleteFiles}&hard_delete=${hardDelete}`, { method: 'DELETE' }),
    storageStatus: () => request(`/recordings/storage/status`),
    purgeOrphans: (target, confirm = false) =>
      request(`/recordings/storage/purge-orphans?target=${target}&confirm=${confirm}`, { method: 'POST' }),
    patch: (id, body) => request(`/recordings/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    edit:  (id, body) => request(`/recordings/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    reanalyze: (id, { useAiEnhance = false } = {}) => request(`/recordings/${id}/reanalyze${useAiEnhance ? '?use_ai_enhance=true' : ''}`, { method: 'POST' }),
    reanalysisHistory: (id) => request(`/recordings/${id}/reanalysis-history`),
    // BirdNET v3 shadow results next to the main detections (Settings → Experimental)
    shadow: (id) => request(`/recordings/${id}/shadow`),
    undoReanalysis: (id, runId) => request(`/recordings/${id}/reanalysis/${runId}/undo`, { method: 'POST' }),
    archive:   (id) => request(`/recordings/${id}/archive`, { method: 'POST' }),
    unarchive: (id) => request(`/recordings/${id}/unarchive`, { method: 'POST' }),
    // Comments
    comments:      (id) => request(`/recordings/${id}/comments`),
    postComment:   (id, body, author) => request(`/recordings/${id}/comments`, {
      method: 'POST', body: JSON.stringify({ body, author })
    }),
    deleteComment: (id, commentId) => request(`/recordings/${id}/comments/${commentId}`, { method: 'DELETE' }),
    updateComment: (id, commentId, body) => request(`/recordings/${id}/comments/${commentId}`, {
      method: 'PUT', body: JSON.stringify({ body })
    }),
    submitToInat: (id, detectionId, notes, opts = {}) => request(`/recordings/${id}/submit-inaturalist`, {
      method: 'POST', body: JSON.stringify({
        detection_id: detectionId || null,
        notes: notes || '',
        use_enhanced_audio: opts.useEnhancedAudio ?? false,
        include_spectrogram: opts.includeSpectrogram ?? true,
        include_details: opts.includeDetails ?? true,
        include_second_opinion: opts.includeSecondOpinion ?? false,
      })
    }),
    verifyInatToken: () => request('/recordings/settings/inat-verify'),
    postInatComment: (id, commentType = 'second_opinion', body = null) => request(`/recordings/${id}/inaturalist-comment`, {
      method: 'POST', body: JSON.stringify({ comment_type: commentType, body })
    }),
    statistics:      (heatmapLimit = 10, metric = 'detections', excludeBats = true) => request(`/recordings/statistics/full?heatmap_limit=${heatmapLimit}&metric=${metric}&exclude_bats=${excludeBats}`),
  },

  revealKeys: () => request('/settings/reveal-keys'),

  backup: {
    // Real fetch + blob download instead of a bare URL for an <a href>
    // link: the backend's /settings/backup/download endpoint reads the
    // Authorization header directly and isn't on the auth-bypass list for
    // browser-navigated media paths, so a plain anchor click never sent
    // the Bearer token when auth was enabled — the browser would silently
    // download the resulting 403 JSON error body instead of the real
    // backup, with a generic browser-guessed filename (hence the
    // reported "download.json" instead of a real backup file). Using
    // fetch() lets us send the token correctly AND read the server's
    // real filename from Content-Disposition rather than guessing it.
    download: () => saveUrl(`${BASE}/settings/backup/download`, {
      filename: `chirp_backup_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.db`,
    }),
    restore:  (formData) => {
      const token = localStorage.getItem('chirp_token')
      clearApiCache()
      return fetch(`${BASE}/settings/backup/restore`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      }).then(async r => {
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${r.status}`) }
        return r.json()
      })
    },
    // Automatic (scheduled) backups — same auth-header-via-fetch pattern
    // as download() above, for the same reason: these need the Bearer
    // token sent explicitly rather than relying on browser navigation.
    autoList: () => request('/settings/backup/auto/list'),
    autoDownload: (filename) =>
      saveUrl(`${BASE}/settings/backup/auto/download/${encodeURIComponent(filename)}`, { filename }),
    autoRestore: (filename) => {
      const token = localStorage.getItem('chirp_token')
      clearApiCache()
      return fetch(`${BASE}/settings/backup/auto/restore/${encodeURIComponent(filename)}`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      }).then(async r => {
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${r.status}`) }
        return r.json()
      })
    },
    // Runs one automatic backup immediately (for the caller's own
    // active instance) and reports the real result/error — added so
    // "is automatic backup actually working" can be answered right now
    // instead of waiting for the scheduled hour and checking back
    // tomorrow.
    runNow: () => request('/settings/backup/auto/run-now', { method: 'POST' }),
  },

  birds: {
    list: (params = {}) => {
      const qs = new URLSearchParams(params).toString()
      return request(`/birds${qs ? '?' + qs : ''}`)
    },
    get: (id) => request(`/birds/${id}`),
    regeneratePresenceSummary: (id) => request(`/birds/${id}/presence-summary/regenerate`, { method: 'POST' }),
    lifeList: () => request('/birds/life-list'),
    // Fetch + blob download instead of a bare URL for an <a href> link —
    // same root cause already fixed once for settings.backup.download:
    // these endpoints read the Authorization header directly and aren't on
    // the auth-bypass list for browser-navigated media paths (deliberately
    // not added there either, since a full life-list export is genuine
    // personal data, not a low-sensitivity media file — bypassing auth for
    // it would mean anyone with the URL could download it with no login).
    // A plain anchor click never sent the Bearer token when auth was
    // enabled, so the browser silently downloaded the resulting 401 JSON
    // error body instead of the real export — the downloaded files both
    // contained literally {"detail":"Not authenticated"}.
    exportLifeList: (format) => saveUrl(
      `${BASE}${format === 'csv' ? '/birds/life-list/ebird-export' : '/birds/life-list/json-export'}`,
      { filename: format === 'csv' ? 'chirp_ebird_export.csv' : 'chirp_life_list.json' }),
    regionalLibrary: (params = {}) => {
      const qs = new URLSearchParams(params).toString()
      return request(`/birds/regional-library${qs ? '?' + qs : ''}`)
    },
    refreshRegionalLibrary: () => request('/birds/regional-library/refresh', { method: 'POST' }),
    identifiedBats: () => request('/birds/identified-bats'),
    byLabel: (label) => request(`/birds/by-label/${encodeURIComponent(label)}`),
    ensure: (name) => request(`/birds/ensure/${encodeURIComponent(name)}`, { method: 'POST' }),
    enrich: (id) => request(`/birds/${id}/enrich`, { method: 'POST' }),
    fetchRangeMap: (id, source, force = false) =>
      request(`/birds/${id}/range-map/fetch?source=${encodeURIComponent(source)}${force ? '&force=true' : ''}`, { method: 'POST' }),
    rangeMapStatus: (id) => request(`/birds/${id}/range-map/status`),
    resetRangeMap:  (id) => request(`/birds/${id}/range-map/reset`, { method: 'POST' }),
    photoUrl: (id) => `${BASE}/birds/${id}/photo`,
    userPhotos: {
      list: (profileId) => request(`/birds/${profileId}/photos`),
      delete: (photoId) => request(`/birds/photos/${photoId}`, { method: 'DELETE' }),
      fileUrl: (photoId) => `${BASE}/birds/photos/${photoId}/file`,
      upload: async (profileId, file, onProgress, uploadedBy) => {
        const fd = new FormData()
        fd.append('file', file)
        const token = tokenStore.get()
        const qs = uploadedBy ? `?uploaded_by=${encodeURIComponent(uploadedBy)}` : ''
        // Same fix, same reason, as recordings.upload above — XHR can
        // silently send an empty body for a FormData containing a File
        // on Safari specifically; fetch() doesn't have this bug. This
        // caller (BirdProfile.jsx) renders progress as `progress * 100`,
        // a 0-1 fraction — matches what the old xhr.upload.onprogress
        // callback actually produced, so kept as 0/1 here rather than
        // the 0-100 scale used above (that one really was a different,
        // separate bug — this one wasn't).
        if (onProgress) onProgress(0)
        let res
        try {
          clearApiCache()
          res = await fetch(`${BASE}/birds/${profileId}/photos${qs}`, {
            method: 'POST',
            headers: token ? { 'Authorization': 'Bearer ' + token } : {},
            body: fd,
          })
        } catch (e) {
          throw new Error('Network error — could not reach the server')
        }
        if (onProgress) onProgress(1)
        if (res.status < 300) {
          try { return await res.json() }
          catch { throw new Error('Invalid response') }
        }
        let msg = `Photo upload failed (${res.status})`
        try { msg = extractErrorDetail((await res.json())?.detail, msg) } catch {}
        throw new Error(msg)
      },
    },
    calls: (id) => request(`/birds/${id}/calls`),
    presenceHistory: (id) => request(`/birds/${id}/presence-history`),
    // Comments (shared across all users)
    comments:        (id) => request(`/birds/${id}/comments`),
    postComment:     (id, body, author) => request(`/birds/${id}/comments`, {
      method: 'POST', body: JSON.stringify({ body, author })
    }),
    deleteComment:   (id, commentId) => request(`/birds/${id}/comments/${commentId}`, { method: 'DELETE' }),
    updateComment:   (id, commentId, body) => request(`/birds/${id}/comments/${commentId}`, {
      method: 'PUT', body: JSON.stringify({ body })
    }),
    recentComments:  (limit = 10) => request(`/birds/comments/recent?limit=${limit}`),
    // Keep updateNotes for backward compat (now posts a comment)
    updateNotes:     (id, body, author) => request(`/birds/${id}/comments`, {
      method: 'POST', body: JSON.stringify({ body, author: author || 'Me' })
    }),
  },

  devices: {
    list: () => request('/devices'),
    get: (id) => request(`/devices/${id}`),
    rename: (id, name) => request(`/devices/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
    pushConfig: (id, config) => request(`/devices/${id}/managed-config`, { method: 'PUT', body: JSON.stringify({ config }) }),
    syncLocation: (id) => request(`/devices/${id}/sync-location`, { method: 'POST' }),
    dismissPendingConfig: (id) => request(`/devices/${id}/dismiss-pending-config`, { method: 'POST' }),
    unpair: (id) => request(`/devices/${id}`, { method: 'DELETE' }),
    discover: (timeout = 3.0) => request(`/devices/discover?timeout=${timeout}`),
    pushCredentials: (body) => request('/devices/push-credentials', { method: 'POST', body: JSON.stringify(body) }),
    syncAllFromSettings: () => request('/devices/sync-all-from-settings', { method: 'POST' }),
    exportConfigProfile: (id) => `/api/v1/devices/${id}/config-profile`,  // direct download URL
    importConfigProfile: (id, config) => request(`/devices/${id}/config-profile`, {
      method: 'POST',
      body: JSON.stringify({ config }),
    }),
    logs: (id, lines = 200, password = '', user = 'pi') => request(
      `/devices/${id}/logs?lines=${lines}${password ? '&ssh_password=' + encodeURIComponent(password) : ''}${user && user !== 'pi' ? '&ssh_user=' + encodeURIComponent(user) : ''}`),
    setupSshKey: (id, ssh_password, ssh_user = 'pi') =>
      request(`/devices/${id}/setup-ssh-key`, { method: 'POST', body: JSON.stringify({ ssh_password, ssh_user }) }),
    setIp: (id, ip) => request(`/devices/${id}/ip`, { method: 'PUT', body: JSON.stringify({ ip_address: ip }) }),
    setConnectVia: (id, via) => request(`/devices/${id}/connect-via`, { method: 'PUT', body: JSON.stringify({ connect_via: via }) }),
    saveSshCredentials: (id, { username, password } = {}) => {
      const body = {}
      if (username !== undefined) body.username = username
      if (password !== undefined) body.password = password
      return request(`/devices/${id}/ssh-credentials`, { method: 'PUT', body: JSON.stringify(body) })
    },
    configStatus: (id) => request(`/devices/${id}/config-status`),
  },
  nearMisses: {
    summary: (days = 90) => request(`/near-misses/summary?days=${days}`),
    nightSpecies: () => request(`/near-misses/night-species`),
    list: ({ species, days = 90, limit = 50 } = {}) =>
      request(`/near-misses?days=${days}&limit=${limit}${species ? `&species=${encodeURIComponent(species)}` : ''}`),
  },
  logs: {
    server:        (n = 500, level = '') => request(`/logs/server?n=${n}${level ? '&level='+level : ''}`),
    serverHistory: (n = 500) => request(`/logs/server/history?n=${n}`),
    devices:       () => request('/logs/devices'),
    device:        (id, lines = 200) => request(`/logs/devices/${id}?lines=${lines}`),
    serverWsUrl:   () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      return `${proto}://${location.host}/api/v1/logs/server/stream`
    },
  },
  settings: {
    get: () => request('/settings'),
    dashboardSections: () => request('/settings/dashboard-sections'),
    tailscaleStatus: () => request('/settings/tailscale-status'),
    sendTestEmail: () => request('/settings/test-email', { method: 'POST' }),
    saveEnv: () => request('/settings/save-env', { method: 'POST' }),
    sendTestNewBirdEmail: () => request('/settings/test-new-bird-email', { method: 'POST' }),
    sendTestDigestEmail:  () => request('/settings/test-digest-email',   { method: 'POST' }),
    update: (body) => request('/settings', { method: 'PUT', body: JSON.stringify(body) }),
    searchLocation: (q) => request(`/settings/location/search?q=${encodeURIComponent(q)}`),
    deletedCount:   () => request('/settings/deleted-count'),
    cleanupDeleted: (deleteFiles = true) => request(`/settings/cleanup-deleted?delete_files=${deleteFiles}`, { method: 'POST' }),
    emptyCount:     () => request('/settings/empty-recordings-count'),
    purgeEmpty:     (mode = 'no_detections', deleteFiles = true) =>
      request(`/settings/purge-empty-recordings?mode=${mode}&delete_files=${deleteFiles}`, { method: 'POST' }),
    activityLogPurge: () => request('/recordings/activity-log/purge', { method: 'POST' }),
    deviceKeys: {
      list: () => request('/settings/device-keys'),
      create: (name) => request('/settings/device-keys', { method: 'POST', body: JSON.stringify({ name }) }),
      delete: (id) => request(`/settings/device-keys/${id}`, { method: 'DELETE' }),
    },
    geomodelStatus:   () => request('/settings/geomodel/status'),
    geomodelDownload: () => request('/settings/geomodel/download', { method: 'POST' }),
    haikubox: {
      status: () => request('/settings/haikubox/status'),
      sync:   () => request('/settings/haikubox/sync', { method: 'POST' }),
    },
    birdBuddy: {
      feeders: () => request('/settings/bird-buddy/feeders'),
      sync:    () => request('/settings/bird-buddy/sync-now', { method: 'POST' }),
    },
    inat: {
      refreshNow: () => request('/settings/inat/refresh-now', { method: 'POST' }),
      test: () => request('/settings/inat/test', { method: 'POST' }),
    },
    testAiKey: (body) => request('/settings/ai/test', { method: 'POST', body: JSON.stringify(body) }),
    ollamaModels: (baseUrl) => request(`/settings/ai/ollama/models${baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : ''}`),
    ollamaPull: (model, baseUrl) => request('/settings/ai/ollama/pull', { method: 'POST', body: JSON.stringify({ model, base_url: baseUrl || undefined }) }),
    getAiUsage: () => request('/settings/ai/usage'),
  },

  liveDetect: {
    // Analyzes one short clip. source='phone' needs `blob` (a WebM/Opus
    // Blob from MediaRecorder); source='device' needs deviceId+micName
    // instead and ignores blob entirely — the server fetches the clip
    // itself via the same /listen path the mic-check Listen button uses.
    //
    // Deliberately bypasses request() rather than calling it the way
    // every other endpoint here does — request() unconditionally sets
    // Content-Type: application/json on every call, which would stomp
    // on the multipart boundary header the browser needs to set itself
    // for a FormData body. recordings.upload() above has the exact same
    // constraint and solves it the same way, for the same reason.
    analyze: async (source, { blob, deviceId, micName, latitude, longitude, minConfidence } = {}) => {
      const fd = new FormData()
      fd.append('source', source)
      if (source === 'phone' && blob) fd.append('file', blob, 'clip.webm')
      if (source === 'device') {
        if (deviceId) fd.append('device_id', deviceId)
        if (micName) fd.append('mic_name', micName)
      }
      if (latitude != null) fd.append('latitude', latitude)
      if (longitude != null) fd.append('longitude', longitude)
      if (minConfidence != null) fd.append('min_confidence', minConfidence)

      const token = tokenStore.get()
      const headers = token ? { Authorization: 'Bearer ' + token } : {}
      const res = await fetch(`${BASE}/live-detect/analyze`, { method: 'POST', body: fd, headers })
      if (res.status === 401) {
        tokenStore.clear()
        if (window.location.pathname !== '/login') window.location.href = '/login'
        throw new Error('Not authenticated')
      }
      if (!res.ok) {
        let msg = `Live Detect analyze failed (${res.status})`
        try { msg = extractErrorDetail((await res.json())?.detail, msg) } catch {}
        throw new Error(msg)
      }
      return res.json()
    },

    // Consolidates a session into one Recording — same multipart/no-
    // request() reasoning as analyze() above (a FormData body needs the
    // browser's own Content-Type boundary header, not request()'s
    // hardcoded application/json).
    saveSession: async (audioBlob, recordingIds, sessionStart, deviceId, { latitude, longitude } = {}) => {
      const fd = new FormData()
      const ext = /wav/.test(audioBlob.type) ? 'wav' : /mp4|aac|m4a/.test(audioBlob.type) ? 'm4a' : 'webm'
      fd.append('file', audioBlob, `session.${ext}`)
      fd.append('recording_ids', JSON.stringify(recordingIds))
      fd.append('session_start', sessionStart)
      if (deviceId) fd.append('device_id', deviceId)
      if (latitude != null) fd.append('latitude', latitude)
      if (longitude != null) fd.append('longitude', longitude)

      const token = tokenStore.get()
      const headers = token ? { Authorization: 'Bearer ' + token } : {}
      clearApiCache()
      const res = await fetch(`${BASE}/live-detect/save-session`, { method: 'POST', body: fd, headers })
      if (res.status === 401) {
        tokenStore.clear()
        if (window.location.pathname !== '/login') window.location.href = '/login'
        throw new Error('Not authenticated')
      }
      if (!res.ok) {
        let msg = `Saving the session failed (${res.status})`
        try { msg = extractErrorDetail((await res.json())?.detail, msg) } catch {}
        throw new Error(msg)
      }
      return res.json()
    },
  },

  diagnostics: {
    run:        (mode = 'full', sshPassword = '') => request(`/diagnostics/run?mode=${mode}&ssh_password=${encodeURIComponent(sshPassword)}`),
    vacuum:     () => request('/diagnostics/db/vacuum', { method: 'POST' }),
    queryPlan:  () => request('/diagnostics/db/query-plan'),
    reportUrl:  (mode = 'full', includeLogs = false, sshPassword = '') =>
      `${BASE}/diagnostics/report?mode=${mode}&include_logs=${includeLogs}&ssh_password=${encodeURIComponent(sshPassword)}`,
    emailReport: (to, mode = 'full', includeLogs = false, sshPassword = '') =>
      request(`/diagnostics/report/email?to=${encodeURIComponent(to)}&mode=${mode}&include_logs=${includeLogs}&ssh_password=${encodeURIComponent(sshPassword)}`,
        { method: 'POST' }),
    listen: async (deviceId, micName) => {
      const token = tokenStore.get()
      const headers = token ? { Authorization: `Bearer ${token}` } : {}
      const resp = await fetch(`${BASE}/diagnostics/devices/${deviceId}/listen?name=${encodeURIComponent(micName)}`, { headers })
      if (!resp.ok) throw new Error(`Listen failed (${resp.status})`)
      return resp.blob()
    },
    micFrequencyResponse: async ({ source, blob, deviceId, micName }) => {
      const fd = new FormData()
      fd.append('source', source)
      if (source === 'phone' && blob) fd.append('file', blob, 'clip.webm')
      if (source === 'device') {
        if (deviceId) fd.append('device_id', deviceId)
        if (micName) fd.append('mic_name', micName)
      }
      const token = tokenStore.get()
      const headers = token ? { Authorization: 'Bearer ' + token } : {}
      const res = await fetch(`${BASE}/diagnostics/mic-frequency-response`, { method: 'POST', body: fd, headers })
      if (!res.ok) {
        let msg = `Mic frequency response failed (${res.status})`
        try { msg = extractErrorDetail((await res.json()).detail, msg) } catch {}
        throw new Error(msg)
      }
      return res.json()
    },
  },

  // Night flight calls (Nighthawk) and experimental model status
  nightCalls: {
    status: () => request('/night-calls/status'),
    downloadBirdnet3: () => request('/night-calls/birdnet3/download', { method: 'POST' }),
    nights: (limit = 60) => request(`/night-calls/nights?limit=${limit}`),
    list: (night, includeUnnarrowed = false) => request(`/night-calls?night=${encodeURIComponent(night)}${includeUnnarrowed ? '&include_unnarrowed=true' : ''}`),
    range: (start, end, includeUnnarrowed = false, limit = 500) => request(`/night-calls?start=${start}&end=${end}&limit=${limit}${includeUnnarrowed ? '&include_unnarrowed=true' : ''}`),
    get: (id) => request(`/night-calls/${id}`),
    spectrogramUrl: (id, large = false) => mediaUrl(`${BASE}/night-calls/${id}/spectrogram${large ? '?large=true' : ''}`),
    audioUrl: (id) => mediaUrl(`${BASE}/night-calls/${id}/audio`),
    remove: (id) => request(`/night-calls/${id}`, { method: 'DELETE' }),
  },
  batActivity: {
    list: (limit = 50) => request(`/bat-activity?limit=${limit}`),
    delete: (id) => request(`/bat-activity/${id}`, { method: 'DELETE' }),
    audioUrl: (id) => mediaUrl(`${BASE}/bat-activity/${id}/audio`),
    audioEnhancedUrl: (id) => mediaUrl(`${BASE}/bat-activity/${id}/audio/enhanced`),
  },

  auth: {
    // Live Detect-only sign-in for the Apple Watch app (30 days)
    watchToken: () => request('/auth/watch-token', { method: 'POST' }),
    deleteAccount: (password) => request('/auth/me/delete', { method: 'POST', body: JSON.stringify({ password }) }),
    login: async (username, password, rememberMe = false) => {
      const fd = new FormData()
      fd.append('username', username)
      fd.append('password', password)
      fd.append('remember_me', rememberMe ? 'true' : 'false')
      const res = await fetch(`${BASE}/auth/login`, { method: 'POST', body: fd })
      if (!res.ok) throw new Error('Invalid credentials')
      const data = await res.json()
      tokenStore.set(data.access_token)
      if (data.username) localStorage.setItem('chirp_user', data.username)
      return data
    },
    me: () => {
      const token = tokenStore.get()
      return fetch(`${BASE}/auth/me`, {
        headers: token ? { Authorization: 'Bearer ' + token } : {}
      })
    },
    logout: () => tokenStore.clear(),
    updateNotificationPrefs: (prefs) => request('/auth/me/notification-prefs', {
      method: 'PUT', body: JSON.stringify(prefs)
    }),
    getProfile: () => request('/auth/me/profile'),
    updateProfile: (body) => request('/auth/me/profile', {
      method: 'PUT', body: JSON.stringify(body)
    }),
    uploadPhoto: (file) => {
      const token = tokenStore.get()
      const formData = new FormData()
      formData.append('photo', file)
      // Can't use the shared request() helper here — it always sets
      // Content-Type: application/json, but multipart/form-data needs the
      // browser to set its own Content-Type with the multipart boundary.
      clearApiCache()
      return fetch(`${BASE}/auth/me/photo`, {
        method: 'PUT',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      }).then(async res => {
        if (!res.ok) {
          const err = await res.text()
          throw new Error(`API ${res.status}: ${err}`)
        }
        return res.json()
      })
    },
    register: (username, email, password, inviteCode) => request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        username, email, password,
        ...(inviteCode ? { invite_code: inviteCode } : {}),
      }),
    }),
    users: {
      list: () => request('/auth/users'),
      create: (body) => request('/auth/users', { method: 'POST', body: JSON.stringify(body) }),
      setPassword: (id, pw) => request(`/auth/users/${id}/password`, { method: 'PUT', body: JSON.stringify({ password: pw }) }),
      setActive: (id, active) => request(`/auth/users/${id}/active`, { method: 'PUT', body: JSON.stringify({ active }) }),
      changeRole: (id, role) => request(`/auth/users/${id}/role`, { method: 'PUT', body: JSON.stringify({ role }) }),
      delete: (id) => request(`/auth/users/${id}`, { method: 'DELETE' }),
      approve: (id) => request(`/auth/users/${id}/approve`, { method: 'POST' }),
    },
    // Server-side logout event for the activity log (best-effort — separate
    // from api.auth.logout above, which only clears the local token and
    // never touches the network). Called from App.jsx's handleLogout.
    logoutEvent: () => request('/auth/logout', { method: 'POST' }),
    activity: {
      ping: (path) => request('/auth/activity/ping', { method: 'POST', body: JSON.stringify({ path }) }),
      list: (params = {}) => {
        const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString()
        return request(`/auth/activity${qs ? `?${qs}` : ''}`)
      },
      count: (params = {}) => {
        const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString()
        return request(`/auth/activity/count${qs ? `?${qs}` : ''}`)
      },
      summary: (days) => request(`/auth/activity/summary${days ? `?days=${days}` : ''}`),
    },
  },

  // Internal admin-only technical docs (see app/api/techdocs.py) — every
  // route there requires admin, matching everything else under api.auth
  // above. list() returns JSON so it uses the normal request() wrapper;
  // page() and asset() can't — request() only knows how to parse a JSON
  // body (anything else comes back as null, confirmed by reading its
  // actual implementation rather than assuming), and an <img src> can't
  // attach an Authorization header regardless — so both do their own
  // authenticated fetch, the same real pattern already used for
  // settings.backup.download() and spectrogram images. Ported from
  // chirp-server.
  techdocs: {
    list: () => request('/techdocs/pages'),
    page: async (id) => {
      const token = tokenStore.get()
      const res = await fetch(`${BASE}/techdocs/pages/${id}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.text()
    },
    assetUrl: async (filename) => {
      const token = tokenStore.get()
      const res = await fetch(`${BASE}/techdocs/assets/${filename}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      return URL.createObjectURL(blob)
    },
  },
}

// Backward-compat aliases used by UserManagement.jsx
api.auth.createUser = api.auth.users.create
api.auth.setActive  = api.auth.users.setActive
api.auth.deleteUser = api.auth.users.delete
api.auth.changePassword = (id, pw) => api.auth.users.setPassword(id, pw)

export function createWebSocket(onMessage) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${proto}//${window.location.host}/ws`)

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'heartbeat') return   // server keepalive — ignore
      if (onMessage) onMessage(msg)
    } catch {}
  }

  return ws
}
