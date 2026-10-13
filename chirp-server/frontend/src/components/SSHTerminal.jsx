import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Terminal } from 'xterm'
import { FitAddon } from '@xterm/addon-fit'
import 'xterm/css/xterm.css'

/**
 * Full-screen SSH terminal modal.
 *
 * Props:
 *   device   — { id, ip_address, ssh_username, name }
 *   onClose  — callback when the modal is dismissed
 */
export default function SSHTerminal({ device, onClose }) {
  const termRef = useRef(null)   // DOM div xterm renders into
  const xtermRef = useRef(null)  // Terminal instance
  const fitRef  = useRef(null)   // FitAddon instance
  const wsRef   = useRef(null)   // WebSocket

  // phase: 'credentials' → 'terminal'  (controls which panel is shown)
  // status: 'connecting' | 'connected' | 'error' | 'closed'  (shown in header only)
  // IMPORTANT: status must NOT be a useEffect dependency — it changes inside the
  // effect and would trigger cleanup/re-init, disposing the terminal.
  const [phase,    setPhase]   = useState('credentials')
  const [status,   setStatus]  = useState('idle')
  const [errorMsg, setErrorMsg] = useState('')

  const [username, setUsername] = useState(device.ssh_username || 'joshsalvi')
  // Which address to connect through. "auto" follows the device's
  // Connect via setting (server picks Tailscale or LAN and falls back to
  // the other); Local/Tailscale force one address.
  const [via, setVia] = useState('auto')
  const connectIp = via === 'tailscale' ? device.tailscale_ip
    : via === 'local' ? device.ip_address
    : (device.connect_address || device.ip_address || device.tailscale_ip)
  const [password, setPassword] = useState('')
  const [port,     setPort]    = useState(22)
  const passwordRef = useRef(null)

  // ── Terminal session — runs once when phase becomes 'terminal' ─────────────
  // Depends ONLY on `phase`, never on `status`.  This ensures status transitions
  // (connecting → connected → error) do NOT dispose and recreate the terminal.
  useEffect(() => {
    if (phase !== 'terminal') return
    if (!termRef.current)     return

    // Dispose any previous session
    xtermRef.current?.dispose()
    if (wsRef.current?.readyState < 2) wsRef.current.close()

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: '"JetBrains Mono", "Fira Code", "Cascadia Code", monospace',
      theme: {
        background:  '#0d1117',
        foreground:  '#e6edf3',
        cursor:      '#f0b429',
        black:       '#161b22',
        red:         '#ff7b72',
        green:       '#3fb950',
        yellow:      '#d29922',
        blue:        '#58a6ff',
        magenta:     '#bc8cff',
        cyan:        '#39c5cf',
        white:       '#b1bac4',
        brightBlack: '#6e7681',
        brightGreen: '#56d364',
      },
      allowTransparency: false,
      scrollback: 5000,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    xtermRef.current = term
    fitRef.current   = fit

    // Open xterm into the container *after* a paint frame so the div has
    // real dimensions (otherwise fit() sees 0×0 and renders nothing).
    requestAnimationFrame(() => {
      if (!termRef.current) return
      term.open(termRef.current)
      requestAnimationFrame(() => {
        fit.fit()
        term.focus()
      })
    })

    // Connect WITHOUT credentials in the URL — passwords in query strings end up
    // in server access logs, reverse-proxy logs, and browser history. The backend
    // expects an {type:"auth", ...} message as the very first WS frame instead.
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    // The session token rides in the URL (browsers can't set headers on a
    // WebSocket); the server needs it to pick the instance and check admin.
    const token = localStorage.getItem('chirp_token')
    const wsUrl = `${proto}//${window.location.host}/api/v1/devices/${device.id}/ssh${token ? `?token=${encodeURIComponent(token)}` : ''}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      // First frame MUST be the auth message — backend rejects anything else
      // with "Expected auth message first" and closes the connection.
      ws.send(JSON.stringify({ type: 'auth', username, password, port: Number(port) || 22, via }))
      setStatus('connected')
      // Send initial resize so server PTY matches our window
      setTimeout(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'resize', cols: term.cols || 220, rows: term.rows || 50 }))
        }
      }, 200)
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'output') {
          term.write(msg.data)
        } else if (msg.type === 'error') {
          term.writeln(`\r\n\x1b[31m${msg.data}\x1b[0m\r\n`)
          setStatus('error')
          setErrorMsg(msg.data)
        } else if (msg.type === 'closed') {
          term.writeln('\r\n\x1b[33m[session closed]\x1b[0m')
          setStatus('closed')
        }
      } catch { /* ignore non-JSON */ }
    }

    ws.onerror = () => {
      setStatus('error')
      setErrorMsg('WebSocket connection failed')
    }

    ws.onclose = () => {
      setStatus(s => s === 'connected' ? 'closed' : s)
    }

    // Forward keystrokes → server
    const disposeKey = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'input', data }))
      }
    })

    // Resize
    const handleResize = () => {
      fit.fit()
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      disposeKey.dispose()
      window.removeEventListener('resize', handleResize)
      term.dispose()
      if (ws.readyState < 2) ws.close()
    }
  }, [phase]) // ← ONLY phase — never status

  // Focus password field when credentials form shows
  useEffect(() => {
    if (phase === 'credentials' && passwordRef.current) {
      setTimeout(() => passwordRef.current?.focus(), 50)
    }
  }, [phase])

  const handleConnect = (e) => {
    e.preventDefault()
    if (!password || !username) return
    setStatus('connecting')
    setPhase('terminal')
  }

  const handleReconnect = () => {
    setStatus('connecting')
    setErrorMsg('')
    setPassword('')
    setPhase('credentials')         // triggers cleanup of old session
    setTimeout(() => {}, 0)         // flush
  }

  const handleClose = () => {
    if (wsRef.current?.readyState < 2) wsRef.current.close()
    onClose()
  }

  const statusColor = {
    connecting: '#58a6ff',
    connected:  '#3fb950',
    error:      '#ff7b72',
    closed:     '#6e7681',
  }[status] || '#6e7681'

  const statusBg = {
    connecting: 'rgba(88,166,255,0.15)',
    connected:  'rgba(63,185,80,0.15)',
    error:      'rgba(255,123,114,0.15)',
    closed:     'rgba(110,118,129,0.2)',
  }[status] || 'rgba(110,118,129,0.2)'

  // Portal to <body>: rendered inside the page, an animated ancestor made a
  // stacking context and the app's top bar drew over the terminal.
  return createPortal(
    <div
      className="fixed inset-0 flex flex-col"
      style={{ background: '#0d1117', zIndex: 1000, paddingTop: 'env(safe-area-inset-top)' }}
      onKeyDown={e => e.key === 'Escape' && handleClose()}
    >
      {/* Title bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b flex-shrink-0"
           style={{ borderColor: '#30363d', background: '#161b22' }}>
        <div className="flex items-center gap-3">
          <span className="text-sm font-mono" style={{ color: '#58a6ff' }}>
            SSH — {device.name || device.id?.slice(0, 8)}
          </span>
          {connectIp && (
            <span className="text-xs font-mono" style={{ color: '#6e7681' }}>
              {username}@{connectIp}:{port}
            </span>
          )}
          {phase === 'terminal' && (
            <span className="text-xs px-2 py-0.5 rounded-full font-mono"
                  style={{ background: statusBg, color: statusColor }}>
              {status}
            </span>
          )}
        </div>
        <button onClick={handleClose}
                className="text-xs px-3 py-1 rounded hover:opacity-80 transition-opacity"
                style={{ color: '#6e7681', border: '1px solid #30363d' }}>
          Close (Esc)
        </button>
      </div>

      {/* Credentials form */}
      {phase === 'credentials' && (
        <div className="flex-1 flex items-center justify-center">
          <div className="rounded-xl p-8 w-80 space-y-4"
               style={{ background: '#161b22', border: '1px solid #30363d' }}>
            <h3 className="text-base font-semibold" style={{ color: '#e6edf3' }}>
              SSH credentials
            </h3>
            <p className="text-xs" style={{ color: '#6e7681' }}>
              Connecting to {connectIp || 'unknown IP'}
            </p>

            {device.ip_address && device.tailscale_ip && (
              <div className="flex rounded-lg overflow-hidden" style={{ border: '1px solid #30363d' }}>
                {[['auto', 'Auto'], ['local', 'Local'], ['tailscale', 'Tailscale']].map(([val, label]) => (
                  <button
                    key={val}
                    type="button"
                    onClick={() => setVia(val)}
                    className="flex-1 text-xs py-1.5 font-mono transition-colors"
                    style={{
                      background: via === val ? '#1f6feb' : 'transparent',
                      color: via === val ? '#ffffff' : '#8b949e',
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}

            <form onSubmit={handleConnect} className="space-y-3">
              <div>
                <label className="text-xs mb-1 block" style={{ color: '#8b949e' }}>Username</label>
                <input
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  className="w-full px-3 py-2 rounded text-sm font-mono"
                  style={{ background: '#0d1117', color: '#e6edf3', border: '1px solid #30363d' }}
                  placeholder="joshsalvi"
                />
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: '#8b949e' }}>Password</label>
                <input
                  ref={passwordRef}
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full px-3 py-2 rounded text-sm font-mono"
                  style={{ background: '#0d1117', color: '#e6edf3', border: '1px solid #30363d' }}
                  autoComplete="current-password"
                />
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: '#8b949e' }}>Port</label>
                <input
                  type="number"
                  value={port}
                  onChange={e => setPort(parseInt(e.target.value) || 22)}
                  className="w-full px-3 py-2 rounded text-sm font-mono"
                  style={{ background: '#0d1117', color: '#e6edf3', border: '1px solid #30363d' }}
                />
              </div>
              <button
                type="submit"
                disabled={!password}
                className="w-full py-2 rounded text-sm font-medium transition-opacity disabled:opacity-40"
                style={{ background: '#238636', color: '#fff' }}>
                Connect
              </button>
              {!password && (
                <p className="text-xs text-center" style={{ color: '#6e7681' }}>
                  Enter your SSH password to enable this button
                </p>
              )}
            </form>

            <p className="text-xs" style={{ color: '#6e7681' }}>
              Credentials are not stored on the server.
            </p>
          </div>
        </div>
      )}

      {/* Terminal — always mounted once phase=terminal, never unmounted on status changes */}
      <div
        ref={termRef}
        className="flex-1 overflow-hidden"
        style={{
          display: phase === 'credentials' ? 'none' : 'block',
          padding: '8px',
        }}
      />

      {/* Reconnect / error bar */}
      {phase === 'terminal' && (status === 'closed' || status === 'error') && (
        <div className="flex items-center justify-center gap-3 py-3 flex-shrink-0"
             style={{ borderTop: '1px solid #30363d', background: '#161b22' }}>
          <span className="text-sm" style={{ color: '#6e7681' }}>
            {status === 'error' ? `Error: ${errorMsg}` : 'Session ended'}
          </span>
          <button
            onClick={handleReconnect}
            className="text-xs px-3 py-1 rounded"
            style={{ background: '#21262d', color: '#e6edf3', border: '1px solid #30363d' }}>
            Reconnect
          </button>
        </div>
      )}
    </div>,
    document.body
  )
}
