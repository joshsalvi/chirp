/**
 * Changelog page — in-app release notes so users can see what's new
 * without requiring a public GitHub repository.
 *
 * Reads /api/v1/changelog (which serves CHANGELOG.md as plain text)
 * and renders it with basic markdown parsing.
 */
import { useState, useEffect } from 'react'
import { iosVersionFor, atLeast, FIRST_PER_RELEASE, useAppInfo } from '../lib/appVersion'

// Escape raw HTML before applying our own markdown-style tags below, so a
// literal "<" or "&" in the changelog text can't be interpreted as markup
// (defense in depth — this content is developer-authored today, not
// user-submitted, but the renderer itself shouldn't assume that forever).
function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
import { Tag, Mail, GitBranch, ChevronDown, ChevronRight } from 'lucide-react'

// Short, plain-language summary per minor version (0.1.X) — hand-written,
// not generated from the changelog text. Older groups get a brief note;
// nothing invented for series with too little context to summarize honestly.
const GROUP_BLURBS = {
  '0.1.0':  'First release — detection, recordings, and the life list.',
  '0.1.1':  'Settings rework plus early bugfixes.',
  '0.1.2':  'iNaturalist connection fixes and audio pipeline work.',
  '0.1.3':  'SSH terminal fixes.',
  '0.1.4':  'One-click eBird export, notification bugfixes.',
  '0.1.5':  'Fixed European species showing up — a missing location filter let them through.',
  '0.1.6':  'Fixed device audio-test crashes (ALSA errors).',
  '0.1.7':  'Recordings list cleanup, device location defaults.',
  '0.1.8':  'Fixed a Field Guide duplicate bug and a Settings crash. Haikubox support added.',
  '0.1.9':  'Three new themes, an OLED display fix, and a Dashboard date bug (was using UTC midnight instead of local).',
  '0.1.10': 'Fixed missing legends on two range map sources.',
  '0.1.11': 'Fixed missing breeding-season bands on eBird range maps; tutorial updates.',
  '0.1.12': 'Range map tabs no longer re-fetch data they already have.',
  '0.1.13': 'Photo gallery layout fixes.',
  '0.1.14': 'Mic-level and changelog display fixes; fixed a broken bird-profile link.',
  '0.1.15': 'Bat species classification built (not yet wired in); fixed a real caching bug behind "I deployed but nothing changed."',
  '0.1.16': 'Bat detection wired into recordings; two crash-causing hotfixes shipped and fixed same-day.',
  '0.1.17': 'The big one: Bird Buddy and Haikubox integrations, bat pipeline fixes, a critical data-loss bug (purge was deleting bat recordings), device uploads not saving their device ID, Settings reorganized, new themes, and a Dashboard diversity/streaks section.',
  '0.2.0':  'Started actually following the versioning scheme below. A critical fix for pages failing to load after a deploy (stale cached JS chunks), bat-recording interference flagging, a real seasonal-presence staleness bug fixed in the Field Guide, a new "no detections" filter, Dashboard mode-picker fixes, Recordings thumbnails decluttered (including a real browser-cache bug found while fixing it), Yard Diversity redesigned into a consistent 3-row layout with a plain-language summary, and several small consistency fixes.',
  '0.3.0':  'Experimental AI features: Daily Journal, Bird Profile presence summaries, and Call Re-analysis, across four providers (Anthropic/OpenAI/Gemini/Ollama, the last one self-hosted with no API key needed) with per-feature assignment, key testing, and real API usage tracking. Plus real device push notifications, a persistent Settings save bar, an OAuth-app-free iNaturalist token refresh option, and a critical fix for an invalid Anthropic model name that was silently breaking every AI feature.',
  '0.4.0':  'Bluetooth-based first-time device setup (iOS/Android app only) — provision a brand-new Pi\'s WiFi before it has any network connection at all.',
  '1.2':    'Multi-target upload fixes on the device side: a secondary server never paired at all, so its own Devices page never showed anything even though recordings were landing and being analyzed correctly; and Live Detect\'s device mode failed outright with a 401 against any server but the first one configured.',
  '0.5.0':  'AudioMoth crash recovery, iNaturalist comment posting for AI second opinions, and the dedicated Cloudflare Tunnel container removed, plus fixes for 11 secretly-single-hue themes, a dozen hardcoded-white-text bugs on light themes, a heatmap species selector unreachable on narrow phones, and vague diagnostic-panel error messages.',
  '0.5.1':  'Added the At a Glance card (habitat/food/nesting/behavior, later redesigned into four symbol cards), found and fixed why Cool Facts were missing for many species (a Cloudflare block silently disabling retries), and several smaller bird-profile and iNaturalist fixes.',
  '0.5.2':  'Added a bird size-comparison ruler (heavily refined across many follow-ups — licensed silhouettes, log scale, measured-range display), a bats-exclusion toggle for Statistics, an admin-only Tech Docs page, and a Settings sidebar redesign.',
  '0.5.3':  'Added a Life History card (full AAB paragraphs) and expanded Tech Docs from every project README. AI Second Opinion extended to bat calls, then to multiple species per recording, then reworked to group by species instead of listing every detection. Added a Listen button to mic check (later extended to the AudioMoth, downshifted into hearing range) using a new device-side status endpoint. Dashboard got a loading skeleton, a rolling 30-day diversity window, count-up stat cards, and a time-of-day greeting; Statistics gained a 12/24-month/all-time diversity window with server-side caching. Found and fixed a bug where every skeleton loader in the app was silently static instead of animating.',
  '0.5.4':  'Live Detect gained the ability to save a full session as one continuous recording, admins can now choose which Dashboard cards load at all (not just show/hide), and several rounds of diagnostics tooling arrived — automatic SQLite maintenance, a VACUUM button, and a query-plan checker to verify database health directly. Also: Settings tab alignment, log/report downloads that could silently fail in some browsers, a Tutorial section for Live Detect, and assorted smaller fixes.',
  '0.5.5':  'The biggest arc: this location\'s own database import feature, a membership-count mismatch fix, per-instance sync fixes for Bird Buddy/Haikubox/iNaturalist and the dashboard cache warmer, then a long push to get remote access working — server-side Tailscale, a bundled self-hosted Headscale (through several build/restart/networking fixes), Global Admin diagnostics per-location, register-with-invite-code in one step, and finally replacing Cloudflare Tunnel entirely with a dedicated Caddy reverse proxy plus automatic Dynamic DNS once Cloudflare\'s own proxying turned out unable to carry Tailscale\'s protocol at all. A new Tech Docs page covers the whole setup. Also: a full parity audit against chirp-server, and a Devices-page mobile layout fix.',
  '0.5.6':  'Version numbers reconciled with chirp-server, so both projects move together from here. Fixed the Daily Journal, Weekly Journal, and Bird Profile AI summaries never running for any real location — a scheduler bug found while auditing all eight of them. Live Detect\'s capture loop no longer pauses for analysis between clips, gained an adjustable sensitivity slider, then two overlapping listening lanes with an adjustable window length on top of that. New Mic Frequency Response diagnostic comparing phone and device mics side by side, and a way to dismiss a "Config pending" state on the Devices page that doesn\'t reflect anything actually pending.',
}

// Versioning scheme, shown at the bottom of this page


export default function Changelog() {
  const [raw, setRaw]     = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('server')
  const appInfo = useAppInfo()

  useEffect(() => {
    fetch('/api/v1/changelog')
      .then(r => r.ok ? r.text() : Promise.reject(r.status))
      .then(text => { setRaw(text); setLoading(false) })
      .catch(e => { setError(`Could not load changelog (${e})`); setLoading(false) })
  }, [])

  if (loading) return (
    <div className="page-root flex items-center justify-center h-64">
      <p className="text-sm animate-pulse" style={{ color: 'var(--text-tertiary)' }}>Loading changelog…</p>
    </div>
  )

  if (error) return (
    <div className="page-root p-6">
      <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>{error}</p>
    </div>
  )

  // Split raw markdown into sections by ## headings
  // Only treat sections whose heading matches a version number (0.X.Y.Z) as version entries
  const allSections = raw.split(/^(?=## )/m).filter(Boolean)
  const versionSections = allSections.filter(s => /^## [\d]+\.[\d]/.test(s))

  // Group by minor version (0.1.17.q -> "0.1.17"). Two version schemes
  // share this one changelog: chirp-server-instances' own four-part
  // MAJOR.MINOR.PATCH.letter (0.5.5.ad), and chirp-device's plain
  // three-part MAJOR.MINOR.PATCH with no letter suffix at all (1.2.17)
  // — found the hard way live: the four-part regex simply never
  // matched chirp-device's entries, so each one fell through to the
  // "no match" branch and used its own entire heading line as the
  // group key, meaning every single chirp-device release rendered as
  // its own ungrouped, single-entry card with the whole changelog
  // paragraph doubling as a title. Grouped by MAJOR.MINOR for that
  // scheme now (1.2.5, 1.2.17, etc. all fall under "1.2"), the same
  // role the letter suffix plays for the other scheme.
  //
  // A THIRD case, found the same way: a minor-version bump's root
  // release (e.g. "0.5.7", the actual AI Enhance debut) has no letter
  // suffix at all — structurally identical (three bare numeric parts)
  // to a chirp-device version like "1.2.17". The three-part fallback
  // above was grouping it by chirp-device's own MAJOR.MINOR convention
  // ("0.5"), landing it in a stray one-entry group completely separate
  // from its own lettered siblings (0.5.7.a...0.5.7.n, which correctly
  // group under "0.5.7" via the four-part match). Distinguish by the
  // "(chirp-device)" tag every chirp-device entry actually carries,
  // rather than by dot-count alone, which the two schemes can share:
  // chirp-device groups by MAJOR.MINOR; anything else groups by its own
  // first three parts if it has a letter, or by itself verbatim if it
  // doesn't — which is exactly the same string its own lettered
  // siblings already reduce to, so a bare root naturally joins them.
  const groups = []
  const groupMap = {}
  versionSections.forEach(sec => {
    const firstLine = sec.split('\n')[0].replace(/^## /, '')
    const isDevice = /\(chirp-device\)/.test(firstLine)
    let key
    if (isDevice) {
      const m3 = firstLine.match(/^(\d+\.\d+)\.\d+/)
      key = m3 ? m3[1] : firstLine
    } else {
      const m4 = firstLine.match(/^(\d+\.\d+\.\d+)\.[a-z]+/)
      const bare = !m4 && firstLine.match(/^(\d+\.\d+\.\d+)\b/)
      key = m4 ? m4[1] : (bare ? bare[1] : firstLine)
    }
    if (!groupMap[key]) {
      groupMap[key] = { key, sections: [] }
      groups.push(groupMap[key])
    }
    groupMap[key].sections.push(sec)
  })

  // Two tabs — server/instances vs device — requested directly, since
  // this file already interleaves two genuinely separate projects with
  // their own independent version schemes and release cadences; showing
  // them as one mixed timeline made it harder to follow either one's
  // own history. A group belongs to "device" if its own first section
  // is tagged "(chirp-device)" in the heading — every chirp-device
  // entry carries that tag consistently, so checking just the first
  // section in each group is enough.
  const isDeviceGroup = (g) => /\(chirp-device\)/.test(g.sections[0].split('\n')[0])
  const serverGroups = groups.filter(g => !isDeviceGroup(g))
  const deviceGroups = groups.filter(isDeviceGroup)

  // Version-scheme legend uses the actual most recent version (versionSections
  // is newest-first) rather than a hardcoded example — so it can't go stale
  // the next time a version ships, the way a fixed "0.1.17.q" example did.
  // Always the server scheme's own latest, regardless of which tab is
  // active — chirp-device's own scheme is plain three-part semver with
  // no letter suffix at all, so this legend (which explains what the
  // letter position means) wouldn't make sense applied to it; shown
  // only on the Server tab for that reason, not hidden by accident.
  const latestVersionStr = serverGroups.length
    ? (serverGroups[0].sections[0].split('\n')[0].match(/^## (\d+\.\d+\.\d+\.[a-z]+)/) || [])[1]
    : null
  const [dMajor, dMinor, dPatch, dLetter] = (latestVersionStr || '0.2.0.a').split('.')
  const VERSION_SCHEME = [
    { part: dMajor,  label: 'Major',  desc: 'Not bumped yet — pre-1.0' },
    { part: dMinor,  label: 'Minor',  desc: 'Bumped for larger feature work' },
    { part: dPatch,  label: 'Patch',  desc: 'One group per batch of related work' },
    { part: dLetter, label: 'Letter', desc: 'Every individual fix or change, a-z then aa, ab…' },
  ]
  const activeGroups = tab === 'device' ? deviceGroups : serverGroups

  return (
    <div className="page-root">
      {/* Header */}
      <div className="mb-6">
        <h1 className="page-title flex items-center gap-3">
          <GitBranch size={22} style={{ color: 'var(--accent-500)' }}/>
          Changelog
        </h1>
        <div className="flex flex-wrap gap-4 mt-2">
          <a href="mailto:josh.salvi@gmail.com"
             className="flex items-center gap-1.5 text-xs hover:opacity-80"
             style={{ color: 'var(--text-tertiary)' }}>
            <Mail size={11}/> josh.salvi@gmail.com
          </a>
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            © 2026 Joshua Salvi — All rights reserved
          </span>
        </div>
      </div>

      {/* Server / Device tabs */}
      <div className="flex gap-2 mb-4">
        {[['server', 'Server'], ['ios', 'iPhone App'], ['device', 'Device']].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
                  className="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
                  style={tab === id
                    ? { background: 'var(--nav-active-bg)', color: 'var(--nav-active-text)' }
                    : { background: 'var(--bg-raised)', color: 'var(--text-secondary)' }}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'ios' && <IosVersions groups={serverGroups} appInfo={appInfo}/>}

      {/* Version groups */}
      {tab !== 'ios' && <div className="space-y-2 mb-8">
        {activeGroups.map((g, i) => (
          <VersionGroup key={g.key} groupKey={g.key} sections={g.sections} defaultOpen={i === 0} isFirstGroup={i === 0}/>
        ))}
        {activeGroups.length === 0 && (
          <p className="text-sm p-4" style={{ color: 'var(--text-tertiary)' }}>Nothing here yet.</p>
        )}
      </div>}

      {/* Versioning scheme visual — server tab only: chirp-device uses
          plain three-part semver with no letter suffix, so a legend
          explaining what the letter position means doesn't apply to it. */}
      {tab === 'server' && (
        <div className="rounded-xl p-4 mb-8" style={{ border: '1px solid var(--border-subtle)', background: 'var(--bg-card)' }}>
          <p className="text-xs font-bold uppercase tracking-widest mb-3" style={{ color: 'var(--accent-500)' }}>
            How version numbers work
          </p>
          <div className="flex items-end gap-1 mb-3 font-mono text-2xl font-bold flex-wrap">
            {VERSION_SCHEME.map((v, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <span style={{ color: 'var(--text-tertiary)' }}>.</span>}
                <span style={{ color: 'var(--accent-400)' }}>{v.part}</span>
              </span>
            ))}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {VERSION_SCHEME.map((v, i) => (
              <div key={i}>
                <p className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>{v.label}</p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{v.desc}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// iPhone app versions: one per Chirp release since 0.5.12.c, plus the
// version installed on this phone when opened in the app.
function IosVersions({ groups, appInfo }) {
  const rows = []
  for (const g of groups) {
    for (const sec of g.sections) {
      const m = sec.split('\n')[0].match(/^## (\d+\.\d+\.\d+\.[a-z]+)\s*[—-]\s*([\d-]+)?\s*(?:[—-]\s*[A-Z]+\s*)?(?:[—-]\s*(.*))?/)
      if (m && atLeast(m[1], FIRST_PER_RELEASE)) {
        rows.push({ chirp: m[1], date: m[2], title: m[3] || '', body: sec.split('\n').slice(1).join('\n') })
      }
    }
  }
  return (
    <div className="space-y-3 mb-8">
      <div className="card p-4">
        {appInfo ? (
          <>
            <p className="text-xs uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>On this iPhone</p>
            <p className="font-mono text-xl font-bold mt-1" style={{ color: 'var(--accent-400)' }}>{appInfo.version}</p>
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>Build {appInfo.build}</p>
          </>
        ) : (
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Open Chirp in the iPhone app to see the version installed on your phone.
          </p>
        )}
        <p className="text-xs mt-3" style={{ color: 'var(--text-tertiary)' }}>
          Each Chirp release has its own iPhone version: the letter becomes part of the last number (0.5.12.e → 0.5.1205).
          Earlier TestFlight builds were 0.5.11 and 0.5.12.
        </p>
      </div>
      {/* Each version opens to that release's changes; the installed one
          (or the newest, outside the app) starts open. */}
      <div className="space-y-2">
        {rows.map((r, i) => {
          const ios = iosVersionFor(r.chirp)
          const installed = appInfo?.version === ios
          return (
            <VersionSection key={r.chirp} ver={ios} date={r.date}
                            note={`Chirp ${r.chirp}${r.title ? ' — ' + r.title : ''}${installed ? ' · installed' : ''}`}
                            isCurrent={installed} body={r.body}
                            defaultOpen={appInfo ? installed : i === 0}/>
          )
        })}
      </div>
    </div>
  )
}

function VersionGroup({ groupKey, sections, defaultOpen, isFirstGroup }) {
  const [open, setOpen] = useState(defaultOpen)
  const blurb = GROUP_BLURBS[groupKey]

  // Date range for the group header
  const dates = sections.map(s => (s.split('\n')[0].match(/(\d{4}-\d{2}-\d{2})/) || [])[1]).filter(Boolean)
  const dateRange = dates.length ? (dates[dates.length - 1] === dates[0] ? dates[0] : `${dates[dates.length - 1]} – ${dates[0]}`) : ''

  return (
    <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--border-subtle)', background: 'var(--bg-panel)' }}>
      <button onClick={() => setOpen(o => !o)}
              className="w-full flex items-center justify-between px-4 py-3 text-left transition-colors hover:bg-black/10">
        <div className="flex items-center gap-3 min-w-0">
          <Tag size={14} style={{ color: 'var(--accent-400)', flexShrink: 0 }}/>
          <span className="font-mono font-bold text-sm" style={{ color: 'var(--text-primary)' }}>{groupKey}</span>
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{sections.length} update{sections.length !== 1 ? 's' : ''}</span>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0 ml-2">
          {dateRange && <span className="text-xs hidden sm:inline" style={{ color: 'var(--text-tertiary)' }}>{dateRange}</span>}
          {open ? <ChevronDown size={13} style={{ color: 'var(--text-tertiary)' }}/> : <ChevronRight size={13} style={{ color: 'var(--text-tertiary)' }}/>}
        </div>
      </button>
      {blurb && (
        <p className="text-sm px-4 pb-3" style={{ color: 'var(--text-secondary)' }}>{blurb}</p>
      )}
      {open && (
        <div className="px-3 pb-3 space-y-2">
          {sections.map((sec, i) => {
            const firstLine = sec.split('\n')[0].replace(/^## /, '')
            const body = sec.split('\n').slice(1).join('\n')
            const parts = firstLine.match(/^(\d+\.\d+\.\d+(?:\.[a-z]+)?)\s*(?:\([^)]*\))?\s*[—-]\s*([\d-]+)(.*)$/)
            const ver      = parts?.[1] || firstLine
            const date     = parts?.[2] || ''
            const notePart = parts?.[3]?.replace(/\*\(current\)\*/, '').trim() || ''
            return (
              <VersionSection key={i} ver={ver} date={date} note={notePart}
                              isCurrent={isFirstGroup && i === 0} body={body}
                              defaultOpen={i === 0}/>
            )
          })}
        </div>
      )}
    </div>
  )
}

function VersionSection({ ver, date, note, isCurrent, body, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen)

  const inline = (s) => escapeHtml(s)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g,
      '<code style="font-family:monospace;font-size:0.8em;background:var(--bg-raised);' +
      'padding:1px 4px;border-radius:3px;color:var(--accent-400)">$1</code>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer" ' +
      'style="color:var(--accent-400);text-decoration:underline">$1</a>')

  const renderBody = () => {
    const lines = body.split('\n')
    const nodes = []
    let listItems = []

    const flushList = () => {
      if (listItems.length) {
        nodes.push(
          <ul key={`ul-${nodes.length}`} className="space-y-1.5 mb-3 ml-2">
            {listItems.map((item, idx) => (
              <li key={idx} className="flex gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--accent-500)', flexShrink: 0 }}>•</span>
                <span dangerouslySetInnerHTML={{ __html: inline(item) }}/>
              </li>
            ))}
          </ul>
        )
        listItems = []
      }
    }

    lines.forEach((line, i) => {
      if (line.startsWith('### ')) {
        flushList()
        nodes.push(
          <p key={i} className="text-xs font-bold uppercase tracking-widest mt-3 mb-1.5"
             style={{ color: 'var(--accent-500)' }}>
            {line.slice(4)}
          </p>
        )
      } else if (line.startsWith('- ') || line.match(/^\s+- /)) {
        listItems.push(line.replace(/^[\s-]+/, ''))
      } else if (line.trim() === '') {
        flushList()
      } else if (/^-{3,}\s*$/.test(line.trim())) {
        // Horizontal-rule divider (---) — used between version blocks in
        // CHANGELOG.md but each version already renders in its own card,
        // so this would otherwise show up as a stray literal "---" line.
        flushList()
      } else if (!line.startsWith('|') && !line.startsWith('#')) {
        flushList()
        nodes.push(
          <p key={i} className="text-sm mb-1" style={{ color: 'var(--text-secondary)' }}
             dangerouslySetInnerHTML={{ __html: inline(line) }}/>
        )
      }
    })
    flushList()
    return nodes
  }

  return (
    <div className="rounded-xl overflow-hidden"
         style={{ border: `1px solid ${isCurrent ? 'rgba(34,197,94,0.4)' : 'var(--border-subtle)'}`,
                  background: isCurrent ? 'rgba(34,197,94,0.03)' : 'var(--bg-card)' }}>
      <button onClick={() => setOpen(o => !o)}
              className="w-full flex items-center justify-between px-4 py-3 text-left transition-colors hover:bg-black/10">
        <div className="flex items-center gap-3 min-w-0">
          <Tag size={13} style={{ color: isCurrent ? 'var(--accent-400)' : 'var(--text-tertiary)', flexShrink: 0 }}/>
          <span className="font-mono font-semibold text-sm"
                style={{ color: isCurrent ? 'var(--accent-400)' : 'var(--text-primary)' }}>
            {ver}
          </span>
          {isCurrent && (
            <span className="text-xs px-2 py-0.5 rounded-full font-semibold flex-shrink-0"
                  style={{ background: 'rgba(34,197,94,0.15)', color: 'var(--accent-400)',
                           border: '1px solid rgba(34,197,94,0.3)' }}>
              current
            </span>
          )}
          {note && <span className="text-xs italic truncate" style={{ color: 'var(--text-tertiary)' }}>{note}</span>}
        </div>
        <div className="flex items-center gap-3 flex-shrink-0 ml-2">
          {date && <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{date}</span>}
          {open
            ? <ChevronDown size={13} style={{ color: 'var(--text-tertiary)' }}/>
            : <ChevronRight size={13} style={{ color: 'var(--text-tertiary)' }}/>}
        </div>
      </button>
      {open && (
        <div className="px-4 pb-4 pt-2 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
          {renderBody()}
        </div>
      )}
    </div>
  )
}
