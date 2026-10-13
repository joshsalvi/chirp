/**
 * Chirp Logs Page — admin-only view of server and device logs.
 *
 * Server logs:
 *   • Live WebSocket stream of in-process log records (ring buffer)
 *   • Historical lines via docker logs / journalctl / file
 *
 * Device logs:
 *   • Select a paired device; fetches via SSH on the server side
 *   • Re-fetch on demand
 */

import { saveText } from '../lib/download'
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  Server, Radio, RefreshCw, X, Download,
  Search, AlertCircle, Terminal
} from 'lucide-react'
import { api } from '../lib/api'

// ── Constants ──────────────────────────────────────────────────────────────────
const LEVEL_STYLES = {
  DEBUG:    { color: 'var(--text-tertiary)',  dot: '#4b5563' },
  INFO:     { color: 'var(--text-primary)',   dot: '#22c55e' },
  WARNING:  { color: 'var(--pastel-yellow)',              dot: 'var(--pastel-amber)' },
  WARN:     { color: 'var(--pastel-yellow)',              dot: 'var(--pastel-amber)' },
  ERROR:    { color: 'var(--pastel-red)',              dot: '#ef4444' },
  CRITICAL: { color: '#f87171',              dot: '#dc2626' },
}

const LEVEL_FILTERS = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

function levelStyle(line) {
  if (!line) return LEVEL_STYLES.INFO
  const upper = (line.level || '').toUpperCase()
  return LEVEL_STYLES[upper] || LEVEL_STYLES.INFO
}

function levelFromText(text) {
  const t = text.toUpperCase()
  if (t.includes('CRITICAL')) return 'CRITICAL'
  if (t.includes('ERROR'))    return 'ERROR'
  if (t.includes('WARNING') || t.includes('WARN')) return 'WARNING'
  if (t.includes('DEBUG'))    return 'DEBUG'
  return 'INFO'
}

// ── Terminal line renderer ─────────────────────────────────────────────────────
function LogLine({ line, search }) {
  // line may be a structured object {ts, level, name, msg} or a plain string
  const isStructured = typeof line === 'object' && line !== null
  const text    = isStructured ? `[${line.ts}] ${line.level.padEnd(8)} ${line.name} — ${line.msg}` : String(line)
  const style   = isStructured ? levelStyle(line) : { color: LEVEL_STYLES[levelFromText(text)]?.color || 'var(--text-secondary)', dot: '#4b5563' }

  // Highlight search term
  if (search && text.toLowerCase().includes(search.toLowerCase())) {
    const idx  = text.toLowerCase().indexOf(search.toLowerCase())
    const pre  = text.slice(0, idx)
    const match = text.slice(idx, idx + search.length)
    const post = text.slice(idx + search.length)
    return (
      <div style={{ color: style.color, lineHeight: 1.55, wordBreak: 'break-all', padding: '1px 0' }}>
        {pre}<mark style={{ background: 'rgba(234,179,8,.35)', color: 'var(--pastel-yellow)', borderRadius: 2 }}>{match}</mark>{post}
      </div>
    )
  }

  return (
    <div style={{ color: style.color, lineHeight: 1.55, wordBreak: 'break-all', padding: '1px 0' }}>
      {text}
    </div>
  )
}

// ── Log panel — shared between server and device tabs ─────────────────────────
function LogPanel({ lines, loading, error, search, setSearch, levelFilter, setLevelFilter,
                    autoScroll, setAutoScroll, liveCount, onRefresh, onDownload, title, source }) {
  const bottomRef  = useRef(null)
  const containerRef = useRef(null)

  // Auto-scroll to bottom when new lines arrive
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [lines, autoScroll])

  // If user scrolls up, pause auto-scroll
  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    if (!atBottom) setAutoScroll(false)
    else setAutoScroll(true)
  }, [setAutoScroll])

  const filtered = useMemo(() => {
    let out = lines
    if (levelFilter !== 'ALL') {
      out = out.filter(l => {
        const lvl = typeof l === 'object' ? l.level?.toUpperCase() : levelFromText(String(l))
        return lvl === levelFilter
      })
    }
    if (search) {
      const q = search.toLowerCase()
      out = out.filter(l => {
        const text = typeof l === 'object'
          ? `${l.ts} ${l.level} ${l.name} ${l.msg}`.toLowerCase()
          : String(l).toLowerCase()
        return text.includes(q)
      })
    }
    return out
  }, [lines, levelFilter, search])

  return (
    <div className="flex flex-col" style={{ height: '100%' }}>
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b flex-shrink-0 flex-wrap gap-y-2"
           style={{ background: 'var(--bg-panel)', borderColor: 'var(--border-subtle)' }}>
        {/* Search */}
        <div className="relative flex-1 min-w-40">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-tertiary)' }}/>
          <input className="input pl-8 text-xs py-1.5" placeholder="Search logs…"
                 value={search} onChange={e => setSearch(e.target.value)}/>
          {search && (
            <button className="absolute right-2 top-1/2 -translate-y-1/2"
                    style={{ color: 'var(--text-tertiary)' }} onClick={() => setSearch('')}>
              <X size={11}/>
            </button>
          )}
        </div>

        {/* Level filter */}
        <div className="flex gap-px">
          {LEVEL_FILTERS.map(l => (
            <button key={l} onClick={() => setLevelFilter(l)}
              className="px-2 py-1 text-xs font-medium rounded transition-all"
              style={levelFilter === l
                ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)', border: '1px solid var(--border-default)' }
                : { background: 'var(--bg-raised)', color: 'var(--text-tertiary)', border: '1px solid transparent' }
              }>{l}</button>
          ))}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-1.5 ml-auto">
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            {filtered.length}/{lines.length}
          </span>
          {liveCount !== undefined && liveCount > 0 && (
            <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--accent-400)' }}>
              <span className="w-1.5 h-1.5 rounded-full live-dot" style={{ background: 'var(--accent-400)' }}/>
              Live
            </span>
          )}
          <label className="flex items-center gap-1 cursor-pointer text-xs" style={{ color: 'var(--text-secondary)' }}>
            <input type="checkbox" className="toggle" style={{ width: 24, height: 14 }}
                   checked={autoScroll} onChange={e => setAutoScroll(e.target.checked)}/>
            Follow
          </label>
          <button onClick={onRefresh} disabled={loading} className="btn-icon" title="Refresh">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''}/>
          </button>
          <button onClick={onDownload} className="btn-icon" title="Download">
            <Download size={13}/>
          </button>
        </div>
      </div>

      {/* Log output */}
      <div ref={containerRef} onScroll={handleScroll}
           className="flex-1 overflow-y-auto p-4"
           style={{ background: '#030906', fontFamily: 'JetBrains Mono, Fira Code, monospace', fontSize: 11 }}>
        {loading && lines.length === 0 && (
          <p className="animate-pulse" style={{ color: 'var(--text-tertiary)' }}>Fetching logs…</p>
        )}
        {error && (
          <div className="flex items-start gap-2 p-3 rounded-xl mb-3"
               style={{ background: 'rgba(239,68,68,.08)', border: '1px solid rgba(239,68,68,.2)', color: 'var(--pastel-red)' }}>
            <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }}/>
            <span>{error}</span>
          </div>
        )}
        {!loading && !error && filtered.length === 0 && (
          <p style={{ color: 'var(--text-tertiary)' }}>
            {lines.length === 0 ? 'No log lines available.' : 'No lines match your filters.'}
          </p>
        )}
        {filtered.map((line, i) => (
          <LogLine key={i} line={line} search={search}/>
        ))}
        <div ref={bottomRef}/>
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between px-4 py-1.5 border-t flex-shrink-0"
           style={{ background: 'var(--bg-panel)', borderColor: 'var(--border-subtle)' }}>
        <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          {source && `Source: ${source}`}
        </span>
        <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          {filtered.length} lines shown
        </span>
      </div>
    </div>
  )
}

// ── Server logs tab ────────────────────────────────────────────────────────────
function ServerLogs() {
  const [lines,       setLines]       = useState([])
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState(null)
  const [source,      setSource]      = useState('')
  const [search,      setSearch]      = useState('')
  const [levelFilter, setLevelFilter] = useState('ALL')
  const [autoScroll,  setAutoScroll]  = useState(true)
  const [liveCount,   setLiveCount]   = useState(0)
  const [liveMode,    setLiveMode]    = useState(true)
  const wsRef = useRef(null)

  const fetchHistory = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const r = await api.logs.serverHistory(1000)
      const raw = r.lines || []
      // server/history returns plain strings; tag them
      setLines(raw.map(l => ({ level: levelFromText(l), msg: l, ts: '', name: '' })))
      setSource(r.source || 'history')
    } catch (e) {
      setError(e.message || 'Failed to fetch server logs')
    }
    setLoading(false)
  }, [])

  const connectWs = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    try {
      const ws = new WebSocket(api.logs.serverWsUrl())
      wsRef.current = ws

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.type === 'history') {
            setLines(msg.lines || [])
            setSource('live (ring buffer)')
          } else if (msg.type === 'lines') {
            setLines(prev => {
              const next = [...prev, ...(msg.lines || [])]
              return next.slice(-2000)   // keep max 2000 in DOM
            })
            setLiveCount(c => c + (msg.lines?.length || 0))
          }
        } catch {}
      }
      ws.onerror  = () => setError('WebSocket error')
      ws.onclose  = () => {}
    } catch {
      fetchHistory()
    }
  }, [fetchHistory])

  useEffect(() => {
    if (liveMode) {
      connectWs()
    } else {
      wsRef.current?.close()
      wsRef.current = null
      fetchHistory()
    }
    return () => { wsRef.current?.close() }
  }, [liveMode])

  const onDownload = () => {
    const text = lines.map(l =>
      typeof l === 'object' ? `[${l.ts}] ${l.level.padEnd(8)} ${l.name} — ${l.msg}` : l
    ).join('\n')
    saveText(text, `chirp-server-${new Date().toISOString().slice(0,10)}.log`)
      .catch(e => alert('Download failed: ' + (e.message || e)))
  }

  return (
    <div className="flex flex-col h-full">
      {/* Sub-toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b flex-shrink-0"
           style={{ background: 'var(--bg-raised)', borderColor: 'var(--border-subtle)' }}>
        <Server size={14} style={{ color: 'var(--accent-500)' }}/>
        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Server process logs</span>
        <div className="flex gap-1 ml-auto">
          <button onClick={() => setLiveMode(true)}
            className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all"
            style={liveMode
              ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)', border: '1px solid var(--border-default)' }
              : { background: 'var(--bg-card)', color: 'var(--text-tertiary)', border: '1px solid var(--border-subtle)' }
            }>
            <span className="flex items-center gap-1.5">
              {liveMode && <span className="w-1.5 h-1.5 rounded-full live-dot" style={{ background: 'var(--accent-400)' }}/>}
              Live
            </span>
          </button>
          <button onClick={() => setLiveMode(false)}
            className="px-2.5 py-1 rounded-lg text-xs font-medium transition-all"
            style={!liveMode
              ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)', border: '1px solid var(--border-default)' }
              : { background: 'var(--bg-card)', color: 'var(--text-tertiary)', border: '1px solid var(--border-subtle)' }
            }>
            History
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <LogPanel
          lines={lines} loading={loading} error={error}
          search={search} setSearch={setSearch}
          levelFilter={levelFilter} setLevelFilter={setLevelFilter}
          autoScroll={autoScroll} setAutoScroll={setAutoScroll}
          liveCount={liveCount}
          onRefresh={liveMode ? connectWs : fetchHistory}
          onDownload={onDownload}
          source={source}
        />
      </div>
    </div>
  )
}

// ── Device logs tab ────────────────────────────────────────────────────────────
function DeviceLogs() {
  const [devices,     setDevices]     = useState([])
  const [selectedId,  setSelectedId]  = useState(null)
  const [lines,       setLines]       = useState([])
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState(null)
  const [lineCount,   setLineCount]   = useState(200)
  const [search,      setSearch]      = useState('')
  const [levelFilter, setLevelFilter] = useState('ALL')
  const [autoScroll,  setAutoScroll]  = useState(true)

  useEffect(() => {
    api.logs.devices()
      .then(setDevices)
      .catch(() => {})
  }, [])

  const [sshPassword, setSshPassword] = useState('')
  const [sshUser, setSshUser] = useState('pi')
  const [needsPassword, setNeedsPassword] = useState(false)
  const [settingUpKey, setSettingUpKey] = useState(false)
  const [keySetupMsg, setKeySetupMsg] = useState(null)

  const fetchLogs = useCallback(async (id, n, password = '', user = 'pi') => {
    if (!id) return
    setLoading(true); setError(null); setLines([])
    try {
      const r = await api.logs.device(id, n, password, user)
      const raw = r.lines || []
      setLines(raw.map(l => ({ level: levelFromText(l), msg: l, ts: '', name: '' })))
      setNeedsPassword(false)
    } catch (e) {
      const msg = e.message || ''
      if (msg.includes('Permission denied') || msg.includes('publickey') || msg.includes('403')) {
        setNeedsPassword(true)
        setError('SSH authentication failed — enter the Pi password below to connect.')
      } else {
        setError(msg || 'SSH connection failed')
      }
    }
    setLoading(false)
  }, [])

  const handleSetupKey = async () => {
    if (!selectedId || !sshPassword) return
    setSettingUpKey(true); setKeySetupMsg(null)
    try {
      const r = await api.devices.setupSshKey(selectedId, sshPassword, sshUser)
      setKeySetupMsg({ ok: true, text: r.message })
      setNeedsPassword(false)
      setSshPassword('')
      fetchLogs(selectedId, lineCount)
    } catch (e) {
      setKeySetupMsg({ ok: false, text: e.message || 'Key setup failed' })
    }
    setSettingUpKey(false)
  }

  useEffect(() => {
    if (!selectedId) return
    // Read credentials synchronously from managed_config (don't rely on setState flush)
    const dev = devices.find(d => d.id === selectedId)
    const storedUser = dev?.managed_config?.ssh_user     || 'pi'
    const storedPass = dev?.managed_config?.ssh_password || ''
    // Update displayed fields for the password prompt (if it appears)
    setSshUser(storedUser)
    setSshPassword(storedPass)
    // Pass credentials directly — managed_config fallback also happens server-side
    fetchLogs(selectedId, lineCount, storedPass, storedUser)
  }, [selectedId])

  const selected = devices.find(d => d.id === selectedId)

  const onDownload = () => {
    const text = lines.map(l => l.msg).join('\n')
    saveText(text, `chirp-device-${selected?.name || selectedId}-${new Date().toISOString().slice(0,10)}.log`)
      .catch(e => alert('Download failed: ' + (e.message || e)))
  }

  return (
    <div className="flex h-full">
      {/* Device sidebar */}
      <div className="flex-shrink-0 w-56 border-r overflow-y-auto"
           style={{ background: 'var(--bg-panel)', borderColor: 'var(--border-subtle)' }}>
        <div className="px-3 py-2.5 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
          <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
            Devices
          </p>
        </div>
        {devices.length === 0 ? (
          <p className="px-3 py-3 text-xs" style={{ color: 'var(--text-tertiary)' }}>No paired devices</p>
        ) : (
          devices.map(d => (
            <button key={d.id} onClick={() => setSelectedId(d.id)}
              className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left transition-all"
              style={{
                background: selectedId === d.id ? 'var(--nav-active-bg)' : 'transparent',
                borderRight: selectedId === d.id ? '2px solid var(--accent-500)' : '2px solid transparent',
              }}>
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${d.status === 'online' ? 'live-dot' : ''}`}
                   style={{ background: d.status === 'online' ? 'var(--accent-400)' : '#4b5563' }}/>
              <div className="min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{d.name}</p>
                <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>
                  {d.ip_address || 'IP unknown'}
                </p>
              </div>
            </button>
          ))
        )}
      </div>

      {/* Log panel */}
      <div className="flex-1 flex flex-col min-w-0">
        {!selectedId ? (
          <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-tertiary)' }}>
            <div className="text-center space-y-2">
              <Radio size={32} className="mx-auto opacity-30"/>
              <p className="text-sm">Select a device to view its logs</p>
              <p className="text-xs">Fetched via SSH from the device</p>
            </div>
          </div>
        ) : (
          <>
            {/* Device sub-toolbar */}
            <div className="flex items-center gap-3 px-4 py-2 border-b flex-shrink-0"
                 style={{ background: 'var(--bg-raised)', borderColor: 'var(--border-subtle)' }}>
              <Radio size={14} style={{ color: selected?.status === 'online' ? 'var(--accent-500)' : '#4b5563' }}/>
              <div>
                <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{selected?.name}</span>
                <span className="text-xs ml-2" style={{ color: 'var(--text-tertiary)' }}>
                  {selected?.ip_address} · via SSH
                </span>
              </div>
              <div className="ml-auto flex items-center gap-2">
                <select className="input text-xs py-1" style={{ width: 90 }}
                        value={lineCount} onChange={e => setLineCount(+e.target.value)}>
                  <option value={50}>50 lines</option>
                  <option value={200}>200 lines</option>
                  <option value={500}>500 lines</option>
                </select>
                <button onClick={() => fetchLogs(selectedId, lineCount, sshPassword)}
                        disabled={loading} className="btn-secondary text-xs py-1 px-3">
                  <RefreshCw size={12} className={loading ? 'animate-spin' : ''}/> Refresh
                </button>
              </div>
            </div>

            {(needsPassword || keySetupMsg) && (
              <div className="flex-shrink-0 px-4 py-3 border-b space-y-2"
                   style={{ background: 'var(--bg-raised)', borderColor: 'var(--border-subtle)' }}>
                <p className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
                  SSH Authentication
                </p>
                {keySetupMsg && (
                  <p className="text-xs" style={{ color: keySetupMsg.ok ? 'var(--accent-400)' : 'var(--pastel-red)' }}>
                    {keySetupMsg.text}
                  </p>
                )}
                <div className="flex items-center gap-2">
                  <input type="text" className="input text-xs py-1.5" style={{ width: 90 }}
                         placeholder="Username"
                         value={sshUser}
                         onChange={e => setSshUser(e.target.value)}/>
                  <input type="password" className="input text-xs py-1.5 flex-1"
                         placeholder="Password"
                         value={sshPassword}
                         onChange={e => setSshPassword(e.target.value)}
                         onKeyDown={e => e.key === 'Enter' && fetchLogs(selectedId, lineCount, sshPassword)}/>
                  <button onClick={() => fetchLogs(selectedId, lineCount, sshPassword, sshUser)}
                          disabled={loading || !sshPassword}
                          className="btn-secondary text-xs py-1.5 px-3 flex-shrink-0">
                    Connect
                  </button>
                  <button onClick={handleSetupKey}
                          disabled={settingUpKey || !sshPassword}
                          className="btn-primary text-xs py-1.5 px-3 flex-shrink-0"
                          title="Install SSH key so future connections don't need a password">
                    {settingUpKey ? 'Installing…' : 'Install SSH Key'}
                  </button>
                </div>
                <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  "Install SSH Key" sets up passwordless access permanently. "Connect" uses the password just this once.
                </p>
              </div>
            )}
            <div className="flex-1 min-h-0">
              <LogPanel
                lines={lines} loading={loading} error={error}
                search={search} setSearch={setSearch}
                levelFilter={levelFilter} setLevelFilter={setLevelFilter}
                autoScroll={autoScroll} setAutoScroll={setAutoScroll}
                onRefresh={() => fetchLogs(selectedId, lineCount, sshPassword, sshUser)}
                onDownload={onDownload}
                source={`SSH → ${selected?.name}`}
              />
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Logs() {
  const [tab, setTab] = useState('server')

  return (
    <div className="flex flex-col" style={{ height: 'calc(100dvh - 60px)', overflow: 'hidden' }}>
      {/* Header */}
      <div className="flex items-center gap-4 px-5 py-3 border-b flex-shrink-0"
           style={{ background: 'var(--bg-panel)', borderColor: 'var(--border-subtle)' }}>
        <Terminal size={17} style={{ color: 'var(--accent-500)' }}/>
        <h1 className="font-display font-semibold text-base" style={{ color: 'var(--text-primary)' }}>
          Logs
        </h1>
        {/* Tabs */}
        <div className="flex gap-1 ml-4">
          {[
            { id: 'server', icon: Server, label: 'Server' },
            { id: 'device', icon: Radio,  label: 'Devices' },
          ].map(({ id, icon: Icon, label }) => (
            <button key={id} onClick={() => setTab(id)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all"
              style={tab === id
                ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)', border: '1px solid var(--border-default)' }
                : { color: 'var(--text-secondary)', border: '1px solid transparent' }
              }>
              <Icon size={13}/> {label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs px-2 py-0.5 rounded-full badge badge-red">Admin only</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0">
        {tab === 'server' ? <ServerLogs/> : <DeviceLogs/>}
      </div>
    </div>
  )
}
