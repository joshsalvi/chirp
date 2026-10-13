// Unread notifications count, shared by the bottom bar, the sidebar and
// the Notifications page. Refreshed every minute, when the app comes back
// to the foreground, and when a push arrives ('chirp-notification').
import { useEffect, useState } from 'react'
import { api } from './api'

let count = 0
let started = false
const subs = new Set()

export function setUnread(n) {
  count = Math.max(0, Number(n) || 0)
  subs.forEach(f => f(count))
}

export async function refreshUnread() {
  try {
    const r = await api.notifications.unread()
    setUnread(r.unread)
  } catch { /* offline or signed out: keep the last count */ }
}

function start() {
  if (started) return
  started = true
  refreshUnread()
  setInterval(refreshUnread, 60000)
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshUnread() })
  window.addEventListener('chirp-notification', refreshUnread)
}

export function useUnread() {
  const [n, setN] = useState(count)
  useEffect(() => {
    subs.add(setN)
    start()
    return () => { subs.delete(setN) }
  }, [])
  return n
}
