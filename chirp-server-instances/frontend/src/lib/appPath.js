// In-app path for a push link. Older servers sent full URLs (built from the
// site's server URL), which made the iOS app open Safari at that host.
export function appPath(url) {
  if (!url) return null
  if (url.startsWith('/')) return url
  try {
    const u = new URL(url.includes('://') ? url : `https://${url}`)
    return (u.pathname || '/') + u.search + u.hash
  } catch {
    return null
  }
}
