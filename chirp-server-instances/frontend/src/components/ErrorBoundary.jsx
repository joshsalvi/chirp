import React from 'react'

// Matches the handful of ways browsers phrase "a dynamically-imported JS
// chunk 404'd" — different browsers/bundlers word this differently, and
// Vite's own chunk-loading error text varies by version too.
const CHUNK_LOAD_ERROR = /Failed to fetch dynamically imported module|Loading chunk .* failed|Importing a module script failed|error loading dynamically imported module/i

/**
 * Generic error boundary — catches a render crash in its children and shows
 * a recoverable "Something went wrong" card instead of a blank screen.
 *
 * Extracted from a pattern that already existed locally in Devices.jsx
 * (DevicesErrorBoundary) so every page gets the same protection, not just
 * one. Used in App.jsx wrapping the route element, keyed by location.pathname
 * so navigating to a different page always starts with a clean (non-error)
 * boundary instance rather than carrying a stale crash across routes.
 *
 * Chunk-load failures get special handling. Every JS chunk this app ships
 * is content-hashed (Statistics-CiT3LGWD.js, etc.) and a fresh deploy
 * replaces the whole dist/ folder with new hashes — so a tab that was
 * already open from before the deploy landed still has old JS in memory
 * referencing chunk filenames that no longer exist on disk. Navigating to
 * any route that tab hasn't already loaded in this session then fails with
 * exactly this error, on every route except whichever ones happen to be
 * eagerly bundled into the main entry chunk already in memory. The default
 * "Try again" button here previously just cleared local error state and
 * re-rendered — which re-attempts the exact same now-missing import() and
 * fails identically, forever, until the person manually hard-refreshes.
 * A real page reload fetches the current index.html and its correct chunk
 * manifest, which fixes this instantly — so that's what happens here,
 * automatically and near-invisibly on the first occurrence, guarded by a
 * sessionStorage flag so a genuinely broken chunk doesn't reload forever.
 */

// Reported directly: a plain window.location.reload() was NOT enough to
// recover from a chunk-load error — both a manual reload and a full app
// restart kept failing identically. A plain reload only re-fetches
// index.html; it does nothing about an already-active service worker
// that's still serving stale cached assets underneath that fresh HTML,
// and does nothing to hurry along the browser's own (often slow,
// sometimes stalled) background check for a newer sw.js. This forces
// both: asks every registered service worker to check for an update
// right now, then wipes the Cache API's storage entirely so nothing
// stale can be served even if the SW update itself hasn't landed yet —
// before finally reloading. Best-effort throughout (every step is
// wrapped so a failure in one doesn't block the reload that follows).
async function hardReload() {
  try {
    if ('serviceWorker' in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations()
      await Promise.all(regs.map(reg => reg.update().catch(() => {})))
    }
  } catch {}
  try {
    if ('caches' in window) {
      const keys = await caches.keys()
      await Promise.all(keys.map(k => caches.delete(k)))
    }
  } catch {}
  window.location.reload()
}

export default class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(e) { return { error: e } }
  componentDidCatch(e, info) {
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught:', e, info)
    const msg = String(e?.message || e)
    if (CHUNK_LOAD_ERROR.test(msg)) {
      const flagKey = 'chirp_chunk_reload_attempted'
      if (!sessionStorage.getItem(flagKey)) {
        sessionStorage.setItem(flagKey, '1')
        hardReload()
      }
      // else: already tried once this session and it's still failing —
      // fall through to the normal error UI below rather than reload forever.
    } else {
      // A non-chunk-load error means the reload flag (if set from an
      // earlier, unrelated chunk failure this session) is stale — clear
      // it so a future genuine chunk failure gets its own auto-reload
      // attempt instead of skipping straight to the manual error UI.
      sessionStorage.removeItem('chirp_chunk_reload_attempted')
    }
  }
  render() {
    if (this.state.error) {
      const label = this.props.label || 'this page'
      const isChunkError = CHUNK_LOAD_ERROR.test(String(this.state.error?.message || this.state.error))
      return (
        <div className="p-6 m-4 rounded-xl text-sm" style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--pastel-red)' }}>
          <p className="font-semibold mb-1">Something went wrong loading {label}</p>
          <p className="text-xs opacity-70 mb-3">
            {isChunkError
              ? "The app was updated since this page was loaded — a reload should fix this."
              : String(this.state.error?.message || this.state.error)}
          </p>
          <button onClick={() => {
                    if (isChunkError) { sessionStorage.removeItem('chirp_chunk_reload_attempted'); hardReload() }
                    else this.setState({ error: null })
                  }}
                  className="px-3 py-1.5 rounded-lg text-xs" style={{ background: 'rgba(248,113,113,0.15)', color: 'var(--pastel-red)' }}>
            {isChunkError ? 'Reload page' : 'Try again'}
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
