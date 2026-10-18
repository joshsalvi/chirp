// Dark CARTO basemap tile URL, with this server's CARTO key when it has
// one (GET /map-config, CHIRP_CARTO_KEY). Without a key CARTO serves tiles
// with an "API key required" watermark.
const BASE = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
let _url = null

export function cartoDarkUrl() {
  if (!_url) {
    _url = fetch('/api/v1/map-config')
      .then(r => (r.ok ? r.json() : {}))
      .catch(() => ({}))
      .then(j => BASE + (j?.carto_key ? `?key=${encodeURIComponent(j.carto_key)}` : ''))
  }
  return _url
}
