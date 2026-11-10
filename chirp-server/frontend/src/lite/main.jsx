import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import LiteApp from './LiteApp'
import './lite.css'
import { setupAppShell } from './appShell'

setupAppShell()

ReactDOM.createRoot(document.getElementById('root')).render(
  <BrowserRouter basename="/lite">
    <LiteApp />
  </BrowserRouter>
)

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}))
}
