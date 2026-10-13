import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'
import './lib/theme'  // apply theme before first render
import { migrateLegacySettingsCollapse } from './lib/cardState'
import { installViewportFix } from './lib/viewportFix'
import { installExternalLinkGuard } from './native'

migrateLegacySettingsCollapse()
installViewportFix()
installExternalLinkGuard()

ReactDOM.createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
)
