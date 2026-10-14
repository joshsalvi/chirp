import { Routes, Route, NavLink, useNavigate, Navigate, useLocation } from 'react-router-dom'
import { useState, useEffect, useLayoutEffect, useCallback, useRef, lazy, Suspense } from 'react'
import {
  LayoutDashboard, Mic, MapPin, Settings,
  Activity, BarChart2, Bell, Upload, Award, Users, LogOut,
  User, Radio, ChevronLeft, ChevronRight, Menu, X,
  Feather, Terminal, ChevronDown, BookOpen, MessageSquare, GitBranch, FileText, AudioLines, Shield
} from 'lucide-react'
import { createWebSocket, api, tokenStore, markNavigation } from './lib/api'
import { getStoredTheme, applyTheme } from './lib/theme'
import { native, isNative, otherServerUrl } from './native'
import { useUnread, refreshUnread } from './lib/unread'
import { installHaptics, hapticEvent } from './lib/haptics'
import { appPath } from './lib/appPath'
import Dashboard from './components/Dashboard'
import ErrorBoundary from './components/ErrorBoundary'
import ChirpLogo from './components/ChirpLogo'
import Login from './components/Login'
import InstancePicker from './components/InstancePicker'
import WhatsNewModal from './components/WhatsNewModal'
import HomeIconNotice from './components/HomeIconNotice'
import AppPermissions from './components/AppPermissions'
import AppNative from './components/AppNative'
import { WHATS_NEW } from './lib/whatsNew'
import ScrollToTop from './components/ScrollToTop'
// lazy() that can be loaded ahead of time: once preload() has finished, the
// page renders straight away instead of flashing the Suspense fallback.
function lazyPage(factory) {
  let Loaded = null
  const preload = () => factory().then(m => { Loaded = m.default; return m })
  const Lazy = lazy(preload)
  function Page(props) { return Loaded ? <Loaded {...props}/> : <Lazy {...props}/> }
  Page.preload = preload
  return Page
}

// Every other page below is lazy-loaded — same pattern already established
// for SSHTerminal (Devices.jsx). Bundling all 19 routes' code together
// regardless of which single page a visit actually needs is exactly why
// vite's build has flagged a 1.24MB single JS chunk on every build this
// session ("Some chunks are larger than 500 kB after minification"). A
// typical session only ever touches a handful of these routes — Settings
// alone pulls in a large amount of form/integration code that a viewer
// checking Recordings never needs to download at all.
const RecordingsList     = lazyPage(() => import('./components/RecordingsList'))
const HaikuboxDetections = lazyPage(() => import('./components/HaikuboxDetections'))
const RecordingDetail    = lazyPage(() => import('./components/RecordingDetail'))
const BirdProfilePage    = lazyPage(() => import('./components/BirdProfile'))
const SettingsPage       = lazyPage(() => import('./components/Settings'))
const ManualUpload       = lazyPage(() => import('./components/ManualUpload'))
const LifeList           = lazyPage(() => import('./components/LifeList'))
const RegionalLibrary    = lazyPage(() => import('./components/RegionalLibrary'))
const UserManagement     = lazyPage(() => import('./components/UserManagement'))
const GlobalAdmin        = lazyPage(() => import('./components/GlobalAdmin'))
const UserProfile        = lazyPage(() => import('./components/UserProfile'))
const AllNotes           = lazyPage(() => import('./components/AllNotes'))
const Notifications      = lazyPage(() => import('./components/Notifications'))
const Journal            = lazyPage(() => import('./components/Journal'))
const Statistics         = lazyPage(() => import('./components/Statistics'))
const Devices            = lazyPage(() => import('./components/Devices'))
const Changelog          = lazyPage(() => import('./components/Changelog'))
const Tutorial           = lazyPage(() => import('./components/Tutorial'))
const Logs               = lazyPage(() => import('./components/Logs'))
const TechDocs           = lazyPage(() => import('./components/TechDocs'))
const UserActivity       = lazyPage(() => import('./components/UserActivity'))
const LiveDetect         = lazyPage(() => import('./components/LiveDetect'))
const Digest             = lazyPage(() => import('./components/Digest'))

// Page code fetched in the background once the app is up, so the first tap
// on a tab doesn't wait for its chunk. Most-used pages first.
const PREFETCH = [RecordingsList, RecordingDetail, LiveDetect, LifeList, Notifications,
                  BirdProfilePage, RegionalLibrary, SettingsPage, Journal]
function prefetchPages() {
  let i = 0
  const next = () => {
    if (i >= PREFETCH.length) return
    PREFETCH[i++].preload().catch(() => {}).finally(() => setTimeout(next, 50))
  }
  if (window.requestIdleCallback) window.requestIdleCallback(next, { timeout: 3000 })
  else setTimeout(next, 1200)
}

// Last verified sign-in, so a returning person sees the app right away
// while /auth/me confirms it in the background. Tied to the token: a new
// sign-in or another site never reuses it.
const ME_CACHE_KEY = 'chirp_me_cache'
const tokenTag = () => (tokenStore.get() || '').slice(-24)
function readMeCache() {
  try {
    const c = JSON.parse(localStorage.getItem(ME_CACHE_KEY) || 'null')
    return c && c.tag === tokenTag() ? c : null
  } catch { return null }
}
function writeMeCache(patch) {
  try {
    const prev = readMeCache() || {}
    localStorage.setItem(ME_CACHE_KEY, JSON.stringify({ ...prev, ...patch, tag: tokenTag() }))
  } catch { /* storage unavailable: start without the cache next time */ }
}
function clearMeCache() {
  try { localStorage.removeItem(ME_CACHE_KEY) } catch {}
}

const NAV = [
  { to: '/',            icon: LayoutDashboard, label: 'Dashboard',    adminOnly: false },
  { to: '/recordings',  icon: Mic,             label: 'Recordings',   adminOnly: false },
  { to: '/live-detect', icon: AudioLines,      label: 'Live Detect',  adminOnly: false },
  { to: '/library',     icon: Award,           label: 'Life List',    adminOnly: false },
  { to: '/regional',    icon: BookOpen,        label: 'Field Guide',  adminOnly: false },
  { to: '/notifications', icon: Bell,          label: 'Notifications', adminOnly: false },
  { to: '/notes',       icon: MessageSquare,   label: 'Notes',        adminOnly: false },
  { to: '/statistics',  icon: BarChart2,       label: 'Statistics',   adminOnly: false },
  { to: '/devices',     icon: Radio,           label: 'Devices',      adminOnly: true  },
  { to: '/activity',    icon: Activity,        label: 'Activity',     adminOnly: true  },
  { to: '/users',       icon: Users,           label: 'Users',        adminOnly: true  },
  { to: '/logs',        icon: Terminal,        label: 'Logs',         adminOnly: true  },
  { to: '/techdocs',    icon: FileText,        label: 'Tech Docs',    adminOnly: true  },
  // globalAdminOnly, not adminOnly — a per-instance admin role says
  // nothing about server-wide access; see registry_models.py's own
  // is_global_admin field. Filtered separately from the adminOnly
  // entries above, against isGlobalAdmin rather than currentUser.role.
  { to: '/global-admin', icon: Shield,         label: 'Global Admin', adminOnly: false, globalAdminOnly: true },
  // Not admin-gated — matches the mobile ⋮ menu's own Settings entry
  // below, which every logged-in user sees (a viewer still needs to
  // reach Settings to change their own theme, even with most of the
  // page itself locked down there). This entry previously said
  // adminOnly: true, which meant non-admin users had no sidebar path
  // to Settings at all on desktop, despite being able to reach it fine
  // through the mobile menu or a typed URL — an inconsistency between
  // the two, not an intentional restriction.
  { to: '/settings',    icon: Settings,        label: 'Settings',     adminOnly: false },
  { to: '/changelog',   icon: GitBranch,       label: "What's New",   adminOnly: false },
  { to: '/profile',     icon: User,            label: 'My Profile',   adminOnly: false },
]

function LiveBadge({ event, onClick }) {
  if (!event) return null
  return (
    <button onClick={onClick}
      className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium
                 transition-all hover:scale-105 cursor-pointer"
      style={{
        background: 'var(--nav-active-bg)',
        color: 'var(--nav-active-text)',
        border: '1px solid var(--border-default)',
      }}>
      <span className="w-1.5 h-1.5 rounded-full live-dot" style={{ background: 'var(--accent-400)' }}/>
      <Feather size={11}/>
      Listening
    </button>
  )
}


// ── Center nav dropdown (desktop top bar) ─────────────────────────────────
function NavDropdown({ navItems, currentPath }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const current = navItems.find(n => n.to === currentPath) ||
                  navItems.find(n => currentPath.startsWith(n.to) && n.to !== '/') ||
                  navItems[0]
  const Icon = current?.icon || LayoutDashboard

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={ref} className="relative hidden md:block">
      <button onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-sm font-medium transition-all"
        style={{ background: 'var(--bg-raised)', color: 'var(--text-primary)', border: '1px solid var(--border-default)' }}>
        <Icon size={14} style={{ color: 'var(--accent-400)' }}/>
        <span>{current?.label}</span>
        <ChevronDown size={12} style={{ color: 'var(--text-tertiary)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .15s' }}/>
      </button>
      {open && (
        <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 z-50 rounded-xl overflow-hidden animate-slide-up"
             style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', minWidth: 180, boxShadow: '0 8px 32px rgba(0,0,0,.4)' }}>
          {navItems.map(({ to, icon: NIcon, label }) => (
            <NavLink key={to} to={to} end={to === '/'}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-colors ${isActive ? '' : 'hover:bg-raised'}`
              }
              style={({ isActive }) => ({
                color: isActive ? 'var(--nav-active-text)' : 'var(--text-primary)',
                background: isActive ? 'var(--nav-active-bg)' : undefined,
              })}>
              <NIcon size={15} style={{ flexShrink: 0 }}/> {label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )
}

function Sidebar({ sidebarOpen, setSidebarOpen, currentUser, requiresAuth, onLogout, connected, liveEvent, onUpload, navItems }) {
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [appVersion, setAppVersion] = useState('')
  useEffect(() => {
    fetch('/api/v1/health').then(r => r.json()).then(d => setAppVersion(d.version || '')).catch(() => {})
  }, [])

  return (
    <aside
      className="hidden md:flex flex-col flex-shrink-0 transition-all duration-300"
      style={{
        width: sidebarOpen ? 224 : 64,
        background: 'var(--bg-panel)',
        borderRight: '1px solid var(--border-subtle)',
      }}>

      {/* Logo area */}
      <div className="flex items-center px-4 border-b"
           style={{ borderColor: 'var(--border-subtle)', minHeight: 60 }}>
        <NavLink to="/" className="flex items-center gap-3 min-w-0" style={{ textDecoration: 'none' }}>
          <ChirpLogo size={sidebarOpen ? 32 : 26}/>
          {sidebarOpen && (
            <div className="min-w-0 animate-fade-in">
              <p className="font-display font-semibold text-sm leading-none" style={{ color: 'var(--text-primary)' }}>Chirp</p>

            </div>
          )}
        </NavLink>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} end={to === '/'}
            className={({ isActive }) =>
              `nav-item ${isActive ? 'active' : ''} ${!sidebarOpen ? 'justify-center px-0' : ''}`
            }>
            <span className="relative flex-shrink-0 flex">
              <Icon size={17}/>
              {to === '/notifications' && <SidebarUnread/>}
            </span>
            {sidebarOpen && <span className="truncate">{label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-2 pb-3 space-y-1.5 border-t" style={{ borderColor: 'var(--border-subtle)', paddingTop: 12 }}>

        {/* Live status */}
        {sidebarOpen && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg"
               style={{ background: 'var(--bg-raised)' }}>
            <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${connected ? 'live-dot' : ''}`}
                 style={{ background: connected ? 'var(--accent-400)' : 'var(--text-tertiary)' }}/>
            <span className="text-xs truncate" style={{ color: 'var(--text-secondary)' }}>
              {connected ? 'Live' : 'Disconnected'}
            </span>
          </div>
        )}

        {/* Version + support links */}
        {sidebarOpen && (
          <div className="px-3 pb-1 space-y-0.5">
            <NavLink to="/changelog"
               className="block text-xs hover:opacity-80 transition-opacity"
               style={{ color: 'var(--text-tertiary)', textDecoration: 'none' }}>
              What&#39;s New
            </NavLink>
          </div>
        )}

        {/* User */}
        <div className="relative">
          <button onClick={() => setShowUserMenu(m => !m)}
            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg transition-all
                       hover:bg-raised text-left ${!sidebarOpen ? 'justify-center' : ''}`}
            style={{ color: 'var(--text-secondary)' }}>
            <div className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0"
                 style={{ background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)' }}>
              <User size={12}/>
            </div>
            {sidebarOpen && currentUser && (
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium truncate" style={{ color: 'var(--text-primary)' }}>{currentUser.username}</p>
                <p className="text-xs truncate" style={{ color: 'var(--text-tertiary)' }}>{currentUser.role}</p>
              </div>
            )}
          </button>
          {showUserMenu && (
            <div className="absolute bottom-full left-0 right-0 mb-1 rounded-xl overflow-hidden z-50 animate-slide-up"
                 style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', boxShadow: '0 8px 32px rgba(0,0,0,.5)' }}>
              {requiresAuth && (
                <button onMouseDown={onLogout}
                  className="w-full flex items-center gap-2.5 px-4 py-3 text-sm transition-colors hover:bg-raised"
                  style={{ color: '#fca5a5' }}>
                  <LogOut size={14}/> Sign out
                </button>
              )}
            </div>
          )}
        </div>

        {/* Collapse toggle */}
        <button onClick={() => setSidebarOpen(s => !s)}
          className="w-full flex items-center justify-center py-2 rounded-lg transition-all btn-ghost"
          style={{ color: 'var(--text-tertiary)' }}>
          {sidebarOpen ? <ChevronLeft size={15}/> : <ChevronRight size={15}/>}
        </button>
      </div>
    </aside>
  )
}


function UnreadBadge({ n }) {
  return (
    <span className="absolute font-semibold flex items-center justify-center"
          style={{ top: -1, right: 0, minWidth: 16, height: 16, padding: '0 4px', borderRadius: 8, fontSize: 10,
                   background: 'var(--accent-400)', color: '#111', boxShadow: '0 0 0 2px var(--bg-panel)' }}>
      {n > 99 ? '99+' : n}
    </span>
  )
}

function SidebarUnread() {
  const n = useUnread()
  if (!n) return null
  return <span className="absolute -top-1 -right-1.5 w-2 h-2 rounded-full" style={{ background: 'var(--accent-400)' }}/>
}

function MobileNav({ currentUser, location, isGlobalAdmin }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const isAdmin      = currentUser?.role === 'admin'
  const hasMenu      = !!currentUser  // all logged-in users get triple-dot
  const unread       = useUnread()

  // Primary 5 tabs visible in bottom bar for all users
  // Primary 5 tabs visible in bottom bar for all users. Notes/Comments
  // moved into the overflow menu below to make room — requested
  // directly: Live Detect (a new, likely much more frequently used
  // mobile feature, matching Merlin Bird ID's own primary flow) takes
  // Notes' bottom-bar slot rather than the two competing for a 6th slot
  // this bar was never designed to hold.
  const primaryNav = [
    { to: '/',            icon: LayoutDashboard },
    { to: '/recordings',  icon: Mic             },
    { to: '/live-detect', icon: AudioLines      },
    { to: '/library',     icon: Award           },
    { to: '/notifications', icon: Bell          },
  ]

  // Overflow menu — admin-only items first, then shared items
  const menuItems = [
    { to: '/regional',   icon: BookOpen,      label: 'Field Guide' },
    { to: '/notes',      icon: MessageSquare, label: 'Notes'       },
    { to: '/statistics', icon: BarChart2,     label: 'Statistics'  },
    ...(isAdmin ? [
      { to: '/devices',  icon: Radio,    label: 'Devices'   },
      { to: '/activity', icon: Activity, label: 'Activity'  },
      { to: '/users',    icon: Users,    label: 'Users'     },
      { to: '/logs',     icon: Terminal, label: 'Logs'      },
      { to: '/techdocs', icon: FileText, label: 'Tech Docs' },
    ] : []),
    ...(isGlobalAdmin ? [
      { to: '/global-admin', icon: Shield, label: 'Global Admin' },
    ] : []),
    { to: '/settings',   icon: Settings,      label: 'Settings'    },
    { to: '/changelog',  icon: GitBranch,     label: "What's New", adminOnly: false  },
    { to: '/profile',    icon: User,          label: 'My Profile'  },
  ]

  useEffect(() => { setMenuOpen(false) }, [location.pathname])

  return (
    <>
      {/* Overflow menu */}
      {hasMenu && menuOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)}/>
          <div className="fixed right-3 z-50 rounded-xl overflow-hidden shadow-modal animate-slide-up"
               style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', minWidth: 172,
                        bottom: 'calc(56px + max(env(safe-area-inset-bottom), 8px) + 8px)' }}>
            {menuItems.map(({ to, icon: Icon, label }) => (
              <NavLink key={to} to={to} onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 text-sm font-medium transition-colors ${isActive ? '' : 'hover:bg-raised'}`
                }
                style={({ isActive }) => ({
                  color: isActive ? 'var(--nav-active-text)' : 'var(--text-primary)',
                  background: isActive ? 'var(--nav-active-bg)' : undefined,
                })}>
                <Icon size={16}/> {label}
              </NavLink>
            ))}
          </div>
        </>
      )}

      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 flex items-center"
           style={{
             background: 'var(--bg-panel)',
             borderTop: '1px solid var(--border-subtle)',
             paddingBottom: 'max(env(safe-area-inset-bottom), 8px)',
             height: 'calc(56px + max(env(safe-area-inset-bottom), 0px))',
           }}>
        {primaryNav.map(({ to, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === '/'}
            className={({ isActive }) =>
              `flex-1 flex justify-center items-center py-2 transition-colors ${isActive || (to === '/notifications' && unread) ? '' : 'opacity-40 hover:opacity-70'}`
            }
            style={{ position: 'relative' }}
            aria-label={to === '/notifications' ? `Notifications${unread ? `, ${unread} unread` : ''}` : undefined}>
            {({ isActive }) => (
              <span className="flex items-center justify-center rounded-full transition-all"
                    style={{
                      width: 40, height: 32,
                      background: isActive ? 'var(--nav-active-bg)' : 'transparent',
                      boxShadow: isActive ? '0 0 0 1px var(--border-default), 0 0 12px var(--glow-color, transparent)' : 'none',
                      color: isActive ? 'var(--accent-400)' : 'var(--text-secondary)',
                    }}>
                <Icon size={20}/>
                {to === '/notifications' && unread > 0 && <UnreadBadge n={unread}/>}
              </span>
            )}
          </NavLink>
        ))}
        {hasMenu && (
          <button onClick={() => setMenuOpen(o => !o)}
            className="flex-1 flex justify-center items-center py-2 transition-colors"
            style={{ color: menuOpen ? 'var(--accent-400)' : 'var(--text-secondary)', opacity: menuOpen ? 1 : 0.4 }}>
            <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="12" cy="5" r="1.5" fill="currentColor" stroke="none"/>
              <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/>
              <circle cx="12" cy="19" r="1.5" fill="currentColor" stroke="none"/>
            </svg>
          </button>
        )}
      </nav>
    </>
  )
}

// While the app shell is mounted, only <main> scrolls. The page itself is
// locked so dragging the top or bottom bar on iOS can't shift or bounce the
// whole layout (see html.app-shell in index.css). Login and the instance
// picker keep normal page scrolling.
function AppShellLock() {
  useEffect(() => {
    document.documentElement.classList.add('app-shell')
    return () => document.documentElement.classList.remove('app-shell')
  }, [])
  return null
}

export default function App() {
  const [liveEvents, setLiveEvents] = useState([])
  const [connected, setConnected] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [showUpload, setShowUpload] = useState(false)
  const [currentUser, setCurrentUser] = useState(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [requiresAuth, setRequiresAuth] = useState(false)
  const [needsInstance, setNeedsInstance] = useState(false)
  // Separate from currentUser.role (that's a per-INSTANCE role, from the
  // instance's own local User row) — is_global_admin lives on the
  // registry's GlobalUser instead, so it needs its own, separate check.
  // A quiet probe rather than surfacing any error: a 403 here just means
  // "not a global admin," the normal case for almost everyone, not a
  // problem worth showing.
  const [isGlobalAdmin, setIsGlobalAdmin] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  const checkAuth = useCallback(() => {
    // Multi-instance addition (see ARCHITECTURE.md): a stored token
    // with no active_instance_id claim means /me would fail (it needs
    // a per-instance database session, which requires one to already
    // be selected) — checked here, locally, before ever calling it,
    // rather than letting that call happen and produce a broken,
    // half-populated currentUser from its error response.
    const token = tokenStore.get()
    if (token && !tokenStore.getActiveInstanceId()) {
      setNeedsInstance(true)
      setRequiresAuth(true)
      setAuthChecked(true)
      return
    }
    setNeedsInstance(false)
    const cached = readMeCache()
    if (cached?.user !== undefined) {
      setRequiresAuth(!!cached.requiresAuth)
      setCurrentUser(cached.user)
      setIsGlobalAdmin(!!cached.globalAdmin)
      setAuthChecked(true)
    }
    api.auth.me().then(r => {
      if (r.status === 401) {
        clearMeCache()
        setRequiresAuth(true); setCurrentUser(null)
        tokenStore.clear(); setAuthChecked(true)
      } else {
        r.json().then(u => {
          let user, needsAuth
          if (!u || u.auth_required === false) {
            needsAuth = false
            user = u?.username ? { username: u.username, role: u.role, dashboard_mode: u.dashboard_mode } : null
          } else {
            needsAuth = true
            user = { username: u.username, role: u.role || 'user', dashboard_mode: u.dashboard_mode }
          }
          setRequiresAuth(needsAuth)
          setCurrentUser(prev => (JSON.stringify(prev) === JSON.stringify(user) ? prev : user))
          writeMeCache({ user, requiresAuth: needsAuth })
          setAuthChecked(true)
        }).catch(() => setAuthChecked(true))
      }
    }).catch(() => setAuthChecked(true))
    api.admin.overview()
      .then(() => { setIsGlobalAdmin(true); writeMeCache({ globalAdmin: true }) })
      .catch(() => { setIsGlobalAdmin(false); writeMeCache({ globalAdmin: false }) })
  }, [])

  const handleWsMessage = useCallback((msg) => {
    if (msg.type === 'new_recording') {
      setLiveEvents(prev => [{ ...msg.data, ts: Date.now() }, ...prev].slice(0, 5))
      window.dispatchEvent(new Event('chirp-new-detection'))
    }
  }, [])

  // iOS app: drop the launch screen as soon as anything (app or sign-in) is
  // on screen, not after the sign-in check.
  useEffect(() => { if (isNative()) native.splash.hide(0) }, [])
  // Haptic feedback across the iOS app (lib/haptics.js); no-op in a browser.
  useEffect(() => installHaptics(), [])

  // Runs before the new page's own effects, so its first data requests can
  // be answered from the short-lived GET cache in lib/api.js.
  useLayoutEffect(() => { markNavigation() }, [location.key])

  const signedIn = authChecked && (!requiresAuth || !!currentUser)
  useEffect(() => { if (signedIn) prefetchPages() }, [signedIn])

  useEffect(() => {
    checkAuth()
    const h = () => checkAuth()
    window.addEventListener('chirp-settings-saved', h)
    return () => window.removeEventListener('chirp-settings-saved', h)
  }, [checkAuth])

  // Apple Watch: give it a Live Detect sign-in for this account and site, or
  // sign it out. Only does anything in the iPhone app with a paired watch.
  const watchKey = currentUser ? `${currentUser.username || ''}|${tokenStore.getActiveInstanceId() || ''}` : ''
  useEffect(() => {
    if (!authChecked) return
    if (signedIn && watchKey) native.watch.sync({ key: watchKey, getToken: () => api.auth.watchToken() })
    else if (!signedIn) native.watch.clear()
  }, [authChecked, signedIn, watchKey])

  // Native push registration (APNs, via Capacitor) — the native-app
  // counterpart to the PWA's Web Push subscribe flow (see
  // components/Settings.jsx's notification settings for that side).
  // native.push.register() itself no-ops immediately on web (isNative()
  // check inside it), so this is safe to call unconditionally rather
  // than needing its own platform check here too. Registers once per
  // app launch — Capacitor's own 'registration' event only fires again
  // if the token actually changes (a real but infrequent occurrence,
  // e.g. after a fresh install), so there's no need to re-register on
  // every render or on every auth-state change.
  useEffect(() => {
    native.push.register({
      onRegistration: (token) => {
        api.push.registerNative(token.value).catch(() => {
          // Best-effort — same "a failed push registration shouldn't
          // block anything else in the app" principle as the PWA's own
          // subscribe flow. The person can still use every other
          // feature; they just won't get native push until this
          // succeeds on a later launch.
        })
      },
      onReceived: () => {
        hapticEvent('success')
        window.dispatchEvent(new Event('chirp-notification'))
      },
      onNotification: (notification) => {
        window.dispatchEvent(new Event('chirp-notification'))
        const data = notification?.data || notification?.notification?.data || {}
        const elsewhere = otherServerUrl(data, appPath(data.url))
        if (elsewhere) { window.location.href = elsewhere; return }
        navigate(appPath(data.url) || '/notifications')
      },
    })
  }, [navigate])

  useEffect(() => {
    let ws, retry, pingInterval
    const connect = () => {
      try {
        ws = createWebSocket(handleWsMessage)
        ws.onopen = () => {
          setConnected(true)
          // Send a ping every 25 s to keep the connection alive through
          // reverse proxies (nginx/Cloudflare default idle timeout is 60–120 s)
          pingInterval = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) ws.send('ping')
          }, 25000)
        }
        ws.onclose = () => {
          setConnected(false)
          clearInterval(pingInterval)
          retry = setTimeout(connect, 5000)
        }
        ws.onerror = () => ws.close()
      } catch {}
    }
    connect()
    // Back from the background (iOS app): a socket iOS closed while
    // suspended reconnects now instead of after the 5 s retry.
    const onResume = () => {
      if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
        clearTimeout(retry)
        connect()
      }
    }
    window.addEventListener('chirp-resume', onResume)
    return () => {
      window.removeEventListener('chirp-resume', onResume)
      clearTimeout(retry)
      clearInterval(pingInterval)
      ws?.close()
    }
  }, [handleWsMessage])

  const handleLogout = () => {
    // Best-effort activity-log event — must never block or fail the actual
    // logout, which always proceeds regardless of network outcome.
    api.auth.logoutEvent().catch(() => {})
    localStorage.removeItem('chirp_token')
    clearMeCache()
    sessionStorage.clear()
    window.location.replace('/')
  }

  // Page-view activity beacon: fires on every route change once auth state
  // is known, so the admin Activity page has real browsing data to show.
  // Fire-and-forget (server-side failures are swallowed inside
  // log_activity itself; a network failure here must never affect
  // navigation). Deduped against the immediately-previous path via a ref —
  // React can re-render the same route multiple times (e.g. a state update
  // that doesn't change location), and each of those isn't a new "page
  // view." Skipped entirely when auth is required but the user isn't
  // logged in yet (no point logging pre-login navigation, and the ping
  // endpoint would just no-op with user=None anyway).
  const lastPingedPath = useRef(null)
  useEffect(() => {
    if (!authChecked) return
    if (requiresAuth && !currentUser) return
    if (lastPingedPath.current === location.pathname) return
    lastPingedPath.current = location.pathname
    api.auth.activity.ping(location.pathname).catch(() => {})
  }, [authChecked, requiresAuth, currentUser, location.pathname])

  // Tutorial auto-redirect: must be before any conditional returns (Rules of Hooks)
  useEffect(() => {
    if (!authChecked || (requiresAuth && !currentUser)) return
    if (location.pathname !== '/') return

    // Two independent guards — both must be clear to trigger a redirect.
    // This is intentionally redundant: iOS Safari evicts localStorage after
    // ~7 days of inactivity, so relying on a single key is not reliable.
    const disabled  = localStorage.getItem('chirp_tutorial_disabled') === '1'
    const lastShown = parseInt(localStorage.getItem('chirp_tutorial_shown') || '0', 10)
    const twelveHours = 12 * 60 * 60 * 1000

    if (disabled) return
    if (Date.now() - lastShown < twelveHours) return

    localStorage.setItem('chirp_tutorial_shown', String(Date.now()))
    navigate('/tutorial')
  }, [authChecked, requiresAuth, currentUser, location.pathname])

  if (!authChecked) return (
    <div className="flex items-center justify-center min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <div className="flex flex-col items-center gap-4">
        <ChirpLogo size={48} animate="draw"/>
        <p className="text-sm font-display" style={{ color: 'var(--accent-400)' }}>Loading…</p>
      </div>
    </div>
  )

  if (location.pathname === '/login') {
    if (currentUser) return <Navigate to="/" replace/>
    return <Login onLogin={(data) => { setCurrentUser({ username: data.username, role: data.role }); setRequiresAuth(true); window.location.replace('/') }}/>
  }
  if (requiresAuth && !currentUser && !needsInstance) {
    return <Login onLogin={(data) => { setCurrentUser({ username: data.username, role: data.role }); setRequiresAuth(true); checkAuth() }}/>
  }
  if (needsInstance) {
    return <InstancePicker onReady={() => checkAuth()}/>
  }

  const navItems = NAV.filter(i =>
    (!i.adminOnly || currentUser?.role === 'admin') &&
    (!i.globalAdminOnly || isGlobalAdmin)
  )
  const liveEvent = liveEvents[0] || null

  return (
    <div className="flex" style={{ height: '100dvh', background: 'var(--bg-base)', overflow: 'hidden' }}>

      <AppShellLock/>
      <WhatsNewModal/>
      <HomeIconNotice version={WHATS_NEW.version}/>
      <AppPermissions/>
      <AppNative version={WHATS_NEW.version}/>

      <ScrollToTop/>

      <Sidebar
        sidebarOpen={sidebarOpen} setSidebarOpen={setSidebarOpen}
        currentUser={currentUser} requiresAuth={requiresAuth}
        onLogout={handleLogout} connected={connected}
        liveEvent={liveEvent} onUpload={() => setShowUpload(true)}
        navItems={navItems}
      />

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Top bar */}
        <header className="flex items-center justify-between px-5 flex-shrink-0"
                style={{
                  // sticky + opaque: iOS 26 Safari treats it as a fixed top
                  // bar and tints its glass to match, instead of blurring it.
                  position: 'sticky', top: 0, zIndex: 40,
                  minHeight: 60,
                  background: 'var(--bg-panel)',
                  borderBottom: '1px solid var(--border-subtle)',
                  paddingTop: 'var(--inset-top)',
                }}>
          {/* Left */}
          <div className="flex items-center gap-3">
            {/* Mobile logo */}
            <NavLink to="/" className="flex md:hidden items-center gap-2" style={{ textDecoration: 'none' }}>
              <ChirpLogo size={26}/>
              <span className="font-display font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Chirp</span>
            </NavLink>
            {/* Desktop status */}
            <div className="hidden md:flex items-center gap-2">
              <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${connected ? 'live-dot' : ''}`}
                   style={{ background: connected ? 'var(--accent-400)' : 'var(--text-tertiary)' }}/>
              <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {connected ? 'Live' : 'Offline'}
              </span>
            </div>
            <LiveBadge event={liveEvent} onClick={() => navigate('/recordings')}/>
          </div>

          {/* Center nav */}
          <NavDropdown navItems={navItems} currentPath={location.pathname}/>

          {/* Right */}
          <div className="flex items-center gap-2">
            {liveEvent && (
              <button onClick={() => navigate('/recordings')}
                className="md:hidden flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
                style={{ background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)', border: '1px solid var(--border-default)' }}>
                <Feather size={10}/>
                Listening
              </button>
            )}
            <button onClick={() => setShowUpload(true)} className="btn-primary" style={{ padding: '7px 14px', fontSize: 13 }}>
              <Upload size={13}/> <span className="hidden sm:inline">Upload</span>
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto pb-16 md:pb-0" style={{ overscrollBehavior: 'contain' }} key={location.pathname}>
          <ErrorBoundary label="this page">
            <Suspense fallback={
              <div className="flex items-center justify-center py-24">
                <div className="text-sm" style={{ color: 'var(--text-tertiary)' }}>Loading…</div>
              </div>
            }>
              <Routes>
                <Route path="/"               element={<Dashboard currentUser={currentUser} requiresAuth={requiresAuth} onDashboardModeChange={mode => setCurrentUser(u => u ? { ...u, dashboard_mode: mode } : u)}/>}/>
                <Route path="/recordings"     element={<RecordingsList/>}/>
                <Route path="/recordings/:id" element={<RecordingDetail/>}/>
                <Route path="/haikubox"       element={<HaikuboxDetections/>}/>
                <Route path="/library"        element={<LifeList/>}/>
                <Route path="/library/:id"    element={<BirdProfilePage/>}/>
                <Route path="/bird"           element={<BirdProfilePage/>}/>
                <Route path="/regional"       element={<RegionalLibrary/>}/>
                <Route path="/likely"         element={<Navigate to="/regional" replace/>}/>
                <Route path="/settings"       element={<SettingsPage currentUser={currentUser}/>}/>
                <Route path="/users"          element={<UserManagement/>}/>
                <Route path="/global-admin"   element={<GlobalAdmin/>}/>
                <Route path="/profile"        element={<UserProfile/>}/>
                <Route path="/notes"          element={<AllNotes/>}/>
                <Route path="/notifications"  element={<Notifications/>}/>
                <Route path="/journal"        element={<Journal/>}/>
                <Route path="/digest"         element={<Digest/>}/>
                <Route path="/live-detect"    element={<LiveDetect/>}/>
                <Route path="/statistics"     element={<Statistics/>}/>
                <Route path="/devices"        element={<Devices/>}/>
                <Route path="/activity"       element={<UserActivity/>}/>
                <Route path="/tutorial"       element={<Tutorial/>}/>
                <Route path="/changelog"      element={<Changelog/>}/>
                <Route path="/logs"          element={<Logs/>}/>
                <Route path="/techdocs"      element={<TechDocs/>}/>
                <Route path="/share/:token"   element={<RecordingDetail shared/>}/>
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>

      {/* Mobile bottom nav */}
      <MobileNav currentUser={currentUser} location={location} isGlobalAdmin={isGlobalAdmin}/>

      {showUpload && (
        <Suspense fallback={
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="text-sm text-gray-400">Loading upload…</div>
          </div>
        }>
          <ManualUpload onClose={() => setShowUpload(false)}/>
        </Suspense>
      )}
    </div>
  )
}
