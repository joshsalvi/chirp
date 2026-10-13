/**
 * Saving files with a dialog, everywhere downloads happen (backups, life
 * list exports, recordings, logs, diagnostics).
 *
 *  - iOS app: the web view has no download support, so the file is written
 *    to the app's cache and the iOS share sheet opens (Save to Files,
 *    AirDrop, Mail...). Large files download natively, not through memory.
 *  - Chrome / Edge: the system Save As dialog (File System Access API); the
 *    response streams straight to disk.
 *  - Other browsers: a normal download, which Safari and Firefox confirm or
 *    save per their own settings.
 *
 * saveUrl(url, { filename, auth })  fetch a server file and save it
 * saveBlob(blob, filename)           save something built in the page
 * saveText(text, filename, type)     same, for text
 *
 * A cancelled dialog resolves quietly; other failures throw.
 */
import { isNative } from '../native'
import { hapticEvent } from './haptics'

const TOKEN_KEY = 'chirp_token'

function authHeaders(auth) {
  if (!auth) return {}
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function nameFromResponse(res, fallback) {
  const cd = res.headers.get('Content-Disposition') || ''
  const star = cd.match(/filename\*=(?:UTF-8'')?([^;]+)/i)
  if (star) { try { return decodeURIComponent(star[1].trim().replace(/^"|"$/g, '')) } catch { /* fall through */ } }
  const plain = cd.match(/filename=([^;]+)/i)
  return plain ? plain[1].trim().replace(/^"|"$/g, '') : fallback
}

function isCancel(e) {
  const msg = String(e?.message || e || '')
  return e?.name === 'AbortError' || /cancel/i.test(msg)
}

function safeName(name) {
  return (name || 'chirp-download').replace(/[\\/:*?"<>|]+/g, '_').slice(0, 180)
}

function absolute(url) {
  return new URL(url, window.location.href).toString()
}

// ── iOS app ─────────────────────────────────────────────────────────────────
function nativeReady() {
  const C = window.Capacitor
  return isNative() && C?.isPluginAvailable?.('Filesystem') && C?.isPluginAvailable?.('Share')
}

async function shareNativeFile(uri, filename) {
  const { Share } = await import('@capacitor/share')
  try {
    await Share.share({ title: filename, files: [uri] })
    hapticEvent('success')
  } catch (e) {
    if (!isCancel(e)) throw e
  }
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result).split(',', 2)[1] || '')
    r.onerror = () => reject(r.error)
    r.readAsDataURL(blob)
  })
}

async function nativeSaveBlob(blob, filename) {
  const { Filesystem, Directory } = await import('@capacitor/filesystem')
  const path = `downloads/${safeName(filename)}`
  const { uri } = await Filesystem.writeFile({
    path, data: await blobToBase64(blob), directory: Directory.Cache, recursive: true,
  })
  await shareNativeFile(uri, filename)
}

async function nativeSaveUrl(url, headers, filename) {
  const { Filesystem, Directory } = await import('@capacitor/filesystem')
  // The server names most files (backups, exports): read its headers, then
  // let the native downloader fetch the body straight to disk.
  const ctl = new AbortController()
  const head = await fetch(url, { headers, signal: ctl.signal })
  if (!head.ok) {
    const err = await head.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${head.status}`)
  }
  const name = safeName(nameFromResponse(head, filename))
  const C = window.Capacitor
  if (!C?.isPluginAvailable?.('FileTransfer')) {
    const blob = await head.blob()
    return nativeSaveBlob(blob, name)
  }
  ctl.abort()
  const { uri } = await Filesystem.getUri({ path: `downloads/${name}`, directory: Directory.Cache })
  await Filesystem.mkdir({ path: 'downloads', directory: Directory.Cache, recursive: true }).catch(() => {})
  const { FileTransfer } = await import('@capacitor/file-transfer')
  await FileTransfer.downloadFile({ url, path: uri, headers })
  await shareNativeFile(uri, name)
}

// ── Browsers ────────────────────────────────────────────────────────────────
function anchorDownload(blob, filename) {
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  // Safari ignores .click() on an <a> that isn't in the document.
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(href), 30000)
}

async function pickFile(filename) {
  if (typeof window.showSaveFilePicker !== 'function') return null
  try {
    return await window.showSaveFilePicker({ suggestedName: filename })
  } catch (e) {
    if (e?.name === 'AbortError') return 'cancelled'
    return null   // e.g. no user gesture left; fall back to a normal download
  }
}

// ── Public API ──────────────────────────────────────────────────────────────
export async function saveBlob(blob, filename) {
  filename = safeName(filename)
  if (nativeReady()) return nativeSaveBlob(blob, filename)
  const handle = await pickFile(filename)
  if (handle === 'cancelled') return
  if (handle) {
    const w = await handle.createWritable()
    await w.write(blob)
    await w.close()
    return
  }
  anchorDownload(blob, filename)
}

export function saveText(text, filename, type = 'text/plain') {
  return saveBlob(new Blob([text], { type }), filename)
}

/**
 * filename: suggested name (the server's Content-Disposition name wins
 * where the platform allows reading it first). auth: send the session
 * token (default true).
 */
export async function saveUrl(url, { filename = 'chirp-download', auth = true } = {}) {
  url = absolute(url)
  const headers = authHeaders(auth)
  if (nativeReady()) return nativeSaveUrl(url, headers, filename)
  // Open the Save dialog first, while the click still counts as a user
  // gesture, then stream the response into the chosen file.
  const handle = await pickFile(safeName(filename))
  if (handle === 'cancelled') return
  const res = await fetch(url, { headers })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  if (handle) {
    const w = await handle.createWritable()
    if (res.body?.pipeTo) await res.body.pipeTo(w)
    else { await w.write(await res.blob()); await w.close() }
    return
  }
  anchorDownload(await res.blob(), safeName(nameFromResponse(res, filename)))
}
