import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { Download, CheckCircle, AlertCircle, Loader } from 'lucide-react'

export default function GeomodelDownloadPanel({ allowRedownload = false }) {
  const [status, setStatus] = useState(null)
  const [starting, setStarting] = useState(false)

  const load = () =>
    api.settings.geomodelStatus()
      .then(setStatus)
      .catch(() => {})

  useEffect(() => {
    load()
  }, [])

  // Poll while downloading
  useEffect(() => {
    if (!status?.downloading) return
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [status?.downloading])

  const handleDownload = async () => {
    setStarting(true)
    try {
      await api.settings.geomodelDownload()
      await load()
    } catch (e) {
      alert(e.message || 'Download failed')
    } finally {
      setStarting(false)
    }
  }

  const files = status?.files || {}
  const fileList = Object.entries(files)
  const allReady = status?.ready
  const anyDownloading = status?.downloading

  return (
    <div className="rounded-lg border border-surface-700 bg-surface-800 p-4 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-200 flex items-center gap-2">
            iNaturalist Geomodel Range Maps
            <span className="text-xs bg-cyan-900/40 text-cyan-300 border border-cyan-700/40 px-1.5 py-0.5 rounded">
              Local
            </span>
          </p>
          <p className="text-xs text-gray-500 mt-1">
            Download iNaturalist's bird range prediction models once (~2–5 GB each).
            Once downloaded, bird profiles can show a locally-rendered range map based
            on the species' iNaturalist taxon ID — no internet required per view.
          </p>
        </div>
      </div>

      {/* File status rows */}
      {fileList.length > 0 && (
        <div className="space-y-1.5">
          {fileList.map(([name, info]) => (
            <div key={name} className="flex items-center gap-2 text-xs px-3 py-1.5 rounded"
                 style={{ background: 'var(--bg-surface)' }}>
              {info.status === 'ready' ? (
                <CheckCircle size={12} className="text-chirp-400 flex-shrink-0"/>
              ) : info.status === 'downloading' ? (
                <Loader size={12} className="text-cyan-400 animate-spin flex-shrink-0"/>
              ) : (
                <AlertCircle size={12} className="text-gray-500 flex-shrink-0"/>
              )}
              <span className="flex-1 truncate font-mono" style={{ color: 'var(--text-secondary)' }}>
                {name}
              </span>
              {info.status === 'ready' && (
                <span className="text-chirp-400">{info.size_gb} GB</span>
              )}
              {info.status === 'downloading' && (
                <span className="text-cyan-400">
                  {info.downloaded_mb} / {info.total_mb} MB ({info.pct}%)
                </span>
              )}
              {info.status === 'missing' && (
                <span style={{ color: 'var(--text-tertiary)' }}>Not downloaded</span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        {allReady && !anyDownloading && (
          <p className="text-xs text-chirp-400 flex items-center gap-1.5 flex-1">
            <CheckCircle size={12}/>
            Ready — iNat Model available on bird profiles.
          </p>
        )}
        {(!allReady || allowRedownload) && (
          <button
            onClick={handleDownload}
            disabled={anyDownloading || starting}
            className="flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition-opacity disabled:opacity-50"
            style={{ background: 'rgba(34,197,94,0.12)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.25)' }}>
            {anyDownloading || starting
              ? <Loader size={13} className="animate-spin"/>
              : <Download size={13}/>}
            {anyDownloading ? 'Downloading…' : allReady ? 'Re-download' : 'Download Geopackages'}
          </button>
        )}
      </div>
    </div>
  )
}
