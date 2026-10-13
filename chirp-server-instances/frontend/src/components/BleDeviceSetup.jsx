import { useState, useEffect, useRef } from 'react'

// Must exactly match chirp-device/chirp/ble_provisioning.py's UUIDs —
// this is how the app finds and talks to the right service on the Pi.
const SETUP_SERVICE_UUID = '7e9a9a00-9d1c-4a3a-8f5e-9b6c7d8e9f01'
const NETWORKS_CHAR_UUID = '7e9a9a01-9d1c-4a3a-8f5e-9b6c7d8e9f01'
const CREDENTIALS_CHAR_UUID = '7e9a9a02-9d1c-4a3a-8f5e-9b6c7d8e9f01'
const STATUS_CHAR_UUID = '7e9a9a03-9d1c-4a3a-8f5e-9b6c7d8e9f01'

/**
 * First-time WiFi setup for a brand-new Pi over Bluetooth — only useful
 * (and only possible) before the Pi has a network connection at all.
 * Once it's online, every other setting in this app reaches the device
 * over the network the normal way; this screen exists specifically for
 * the "it has no network yet" gap that nothing else here can bridge.
 *
 * Native app only — iOS Safari (and Safari in general) doesn't implement
 * Web Bluetooth, so this can't work in a regular browser tab the way
 * almost everything else in Chirp does. Checked via Capacitor's own
 * platform detection below; the component renders a plain explanation
 * instead of the setup flow when not running as the native app.
 *
 * NOT YET VALIDATED against a real device. Built against
 * @capacitor-community/bluetooth-le's documented API and bluezero's
 * documented API on the Pi side, but BLE is genuinely finicky in
 * practice — this needs real hardware testing, most likely some
 * back-and-forth fixing whatever the first real attempt reveals.
 */
export default function BleDeviceSetup() {
  const [isNative, setIsNative] = useState(null)  // null = still checking
  const [step, setStep] = useState('idle')  // idle | scanning | connecting | connected | picking | sending | done | error
  const [networks, setNetworks] = useState([])
  const [selectedSsid, setSelectedSsid] = useState('')
  const [password, setPassword] = useState('')
  const [statusText, setStatusText] = useState('')
  const [errorText, setErrorText] = useState('')
  const deviceIdRef = useRef(null)
  const bleRef = useRef(null)

  useEffect(() => {
    (async () => {
      try {
        const { Capacitor } = await import('@capacitor/core')
        setIsNative(Capacitor.isNativePlatform())
      } catch (e) {
        setIsNative(false)
      }
    })()
  }, [])

  const startScan = async () => {
    setErrorText('')
    setStep('scanning')
    try {
      const { BleClient } = await import('@capacitor-community/bluetooth-le')
      bleRef.current = BleClient
      await BleClient.initialize()

      // requestDevice shows the OS's own device picker, pre-filtered to
      // only devices advertising our setup service — the person just
      // taps the one result rather than us building a custom scan list.
      const device = await BleClient.requestDevice({
        services: [SETUP_SERVICE_UUID],
        name: 'Chirp Setup',
      })

      deviceIdRef.current = device.deviceId
      setStep('connecting')
      await BleClient.connect(device.deviceId, () => {
        // Disconnect callback — the Pi tears down advertising once
        // credentials are successfully applied (see ble_provisioning.py),
        // so an unexpected disconnect here after we've already sent
        // credentials is actually the success path, not a failure.
        if (step !== 'done') {
          setStep(prev => (prev === 'sending' ? prev : 'idle'))
        }
      })

      const networksRaw = await BleClient.read(device.deviceId, SETUP_SERVICE_UUID, NETWORKS_CHAR_UUID)
      const networksJson = new TextDecoder().decode(networksRaw)
      const list = JSON.parse(networksJson)
      setNetworks(Array.isArray(list) ? list : [])
      setStep('picking')

      // Subscribe to status updates now, before sending credentials, so
      // we don't miss the "connecting" -> "connected"/"failed" transition
      await BleClient.startNotifications(
        device.deviceId, SETUP_SERVICE_UUID, STATUS_CHAR_UUID,
        (value) => {
          const text = new TextDecoder().decode(value)
          setStatusText(text)
          if (text === 'connected') setStep('done')
          else if (text.startsWith('failed')) {
            setStep('error')
            setErrorText(text.replace(/^failed:\s*/, '') || 'Setup failed for an unknown reason')
          }
        }
      )
    } catch (e) {
      setStep('error')
      setErrorText(e?.message || 'Could not find or connect to a Chirp device in setup mode')
    }
  }

  const sendCredentials = async () => {
    if (!selectedSsid || !deviceIdRef.current || !bleRef.current) return
    setStep('sending')
    setErrorText('')
    try {
      const payload = JSON.stringify({ ssid: selectedSsid, password })
      const bytes = new TextEncoder().encode(payload)
      await bleRef.current.write(
        deviceIdRef.current, SETUP_SERVICE_UUID, CREDENTIALS_CHAR_UUID,
        new DataView(bytes.buffer)
      )
      // Actual success/failure arrives via the status notification
      // subscribed to during startScan — this just confirms the write
      // itself went through, not that the Pi actually connected yet.
    } catch (e) {
      setStep('error')
      setErrorText(e?.message || 'Failed to send WiFi credentials to the device')
    }
  }

  const reset = () => {
    setStep('idle')
    setNetworks([])
    setSelectedSsid('')
    setPassword('')
    setStatusText('')
    setErrorText('')
    if (deviceIdRef.current && bleRef.current) {
      bleRef.current.disconnect(deviceIdRef.current).catch(() => {})
    }
    deviceIdRef.current = null
  }

  if (isNative === null) return null  // still checking, avoid a flash of the wrong state

  if (!isNative) {
    return (
      <div className="card rounded-xl p-5">
        <p className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          Bluetooth device setup
        </p>
        <p className="text-sm" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          This only works from the Chirp iOS or Android app — web browsers (including Safari)
          don't support the Bluetooth features this needs. If the Pi already has a WiFi
          connection, you don't need this at all: every other setting in Chirp already reaches
          the device over the network from here.
        </p>
      </div>
    )
  }

  return (
    <div className="card rounded-xl p-5 space-y-4">
      <div>
        <p className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
          Bluetooth device setup
        </p>
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          For a brand-new Pi with no WiFi connection yet. Make sure the device is powered on
          and within a few feet of your phone before starting.
        </p>
      </div>

      {step === 'idle' && (
        <button onClick={startScan} className="btn-primary w-full py-2.5">
          Find nearby device
        </button>
      )}

      {(step === 'scanning' || step === 'connecting') && (
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          {step === 'scanning' ? 'Looking for a device in setup mode…' : 'Connecting…'}
        </p>
      )}

      {step === 'picking' && (
        <div className="space-y-3">
          <div>
            <label className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
              WiFi network
            </label>
            <select className="input w-full mt-1" value={selectedSsid} onChange={e => setSelectedSsid(e.target.value)}>
              <option value="">Select a network…</option>
              {networks.map(ssid => <option key={ssid} value={ssid}>{ssid}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
              Password
            </label>
            <input type="password" className="input w-full mt-1" value={password}
                   onChange={e => setPassword(e.target.value)} placeholder="WiFi password"/>
          </div>
          <button onClick={sendCredentials} disabled={!selectedSsid} className="btn-primary w-full py-2.5 disabled:opacity-40">
            Connect
          </button>
        </div>
      )}

      {step === 'sending' && (
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          Sending to device{statusText ? ` — ${statusText}` : '…'}
        </p>
      )}

      {step === 'done' && (
        <div>
          <p className="text-sm" style={{ color: '#4ade80' }}>
            Device connected — it should appear in Devices shortly once it finishes joining your network.
          </p>
          <button onClick={reset} className="text-xs mt-3 underline" style={{ color: 'var(--text-tertiary)' }}>
            Set up another device
          </button>
        </div>
      )}

      {step === 'error' && (
        <div>
          <p className="text-sm" style={{ color: '#f87171' }}>{errorText}</p>
          <button onClick={reset} className="btn-secondary mt-3">Try again</button>
        </div>
      )}
    </div>
  )
}
