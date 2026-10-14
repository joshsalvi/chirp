// Chirp Service Worker — offline shell caching
//
// CACHE is auto-stamped at build time from the project's VERSION file by
// scripts/stamp-sw-version.mjs (npm `prebuild` hook, runs before `vite
// build`); vite.config.js's verify-sw-version plugin then confirms the
// stamped value made it into dist/sw.js unchanged, and fails the build
// loudly if not. The literal value below is a placeholder that only
// survives in dev (`vite dev` doesn't run the production build pipeline,
// so the service worker itself is largely inert there anyway; if this
// string is ever the one actually running in production, the prebuild
// step didn't run and the version-bust mechanism is broken again).
//
// This used to be a MANUAL edit required on every release, which is a
// real, confirmed root cause of "the server was redeployed but nothing
// changed in the browser": the string was stuck at 'chirp-v0.1.14.n'
// across every release from 0.1.14.n through 0.1.15.v, so the
// activate handler's "delete any cache that isn't the current one" logic
// never had anything to actually invalidate — the cache-first /assets/
// strategy below kept serving JS/CSS bundles cached under that same key
// indefinitely, regardless of how many times the server was actually
// redeployed. A hard refresh does NOT fix this on its own: it reloads the
// page, but doesn't bypass an already-active service worker intercepting
// the asset requests before they'd reach the network.
const CACHE = 'chirp-v0.5.12.x'
const SHELL = ['/', '/recordings', '/library', '/regional', '/likely', '/settings']

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', e => {
  const { request } = e
  const url = new URL(request.url)

  // Only GET requests get intercepted at all, full stop. Reported
  // directly: recording/photo uploads (POST, multipart FormData) kept
  // failing on Safari/iOS even after switching the page's own upload
  // code from XMLHttpRequest to fetch() — a real, separate WebKit bug
  // from the XHR one already fixed, one layer further out. This
  // handler was doing `fetch(request)` on the INTERCEPTED Request
  // object for every /api/ call regardless of method, to always get
  // fresh (never cached) API responses. For a GET that's harmless — a
  // GET has no body to lose. For a POST/PUT/PATCH carrying a body,
  // re-fetching an already-intercepted Request object has documented
  // Safari-specific bugs around correctly forwarding that body, and a
  // POST was never cacheable in the first place, so "network-first"
  // never bought anything for these — there's no cached fallback for a
  // POST to race against. Letting non-GET requests fall through
  // unintercepted (no event.respondWith() call at all) means the
  // browser sends them exactly as constructed, with nothing in this
  // service worker's own request-forwarding between the page code and
  // the network to go wrong.
  if (request.method !== 'GET') {
    return
  }

  // Network-first for API calls — always want fresh data
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(request).catch(() =>
        new Response(JSON.stringify({ error: 'offline' }), {
          headers: { 'Content-Type': 'application/json' }
        })
      )
    )
    return
  }

  // Cache-first for static assets (JS/CSS/fonts)
  if (url.pathname.startsWith('/assets/') || url.pathname.match(/\.(js|css|woff2?|png|svg|ico)$/)) {
    e.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(res => {
        const clone = res.clone()
        caches.open(CACHE).then(c => c.put(request, clone))
        return res
      }))
    )
    return
  }

  // Network-first for HTML pages, fall back to cached shell
  e.respondWith(
    fetch(request).catch(() => caches.match('/').then(r => r || fetch(request)))
  )
})

// Real Web Push support — see app/services/push_notifications.py for the
// server side. This is what actually shows an OS-level notification while
// the app is closed or backgrounded; the existing notify_new_bird/
// notify_daily_digest settings only ever sent email before this existed.
self.addEventListener('push', e => {
  let payload = { title: 'Chirp', body: 'New activity' }
  try {
    if (e.data) payload = { ...payload, ...e.data.json() }
  } catch (err) {
    // Not JSON for some reason — fall back to raw text rather than showing nothing
    if (e.data) payload.body = e.data.text()
  }
  const options = {
    body: payload.body,
    icon: `/icon-192.png?v=${CACHE.replace('chirp-v', '')}`,
    badge: `/icon-192.png?v=${CACHE.replace('chirp-v', '')}`,
    tag: payload.tag || 'chirp-notification',
    data: { url: payload.url || '/' },
  }
  e.waitUntil(self.registration.showNotification(payload.title, options))
})

self.addEventListener('notificationclick', e => {
  e.notification.close()
  // Same-origin path only: a full URL from an older server could point at another host.
  let targetUrl = (e.notification.data && e.notification.data.url) || '/'
  try { const u = new URL(targetUrl, self.location.origin); targetUrl = u.pathname + u.search + u.hash } catch (_) { targetUrl = '/' }
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
      // Focus an already-open tab on the same origin rather than opening
      // a new one, if one exists
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(targetUrl)
          return client.focus()
        }
      }
      return clients.openWindow(targetUrl)
    })
  )
})
