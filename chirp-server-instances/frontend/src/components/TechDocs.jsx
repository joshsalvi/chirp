/**
 * TechDocs — internal, admin-only technical documentation, served from
 * app/techdocs_content/ (see app/api/techdocs.py and
 * scripts/sync-techdocs.py). This mirrors the standalone techdocs/
 * MkDocs project so an admin can read it directly from the WebGUI
 * without running `mkdocs serve` locally.
 *
 * Internal technical detail, not meant for general users — every
 * request here goes through the backend's require_admin check (a
 * 403 for anyone else, not just a hidden nav link), and this page
 * itself has no route-level guard beyond that shared backend
 * enforcement, matching how every other admin page in this app works.
 */
import { useEffect, useState, useRef } from 'react'
import { createPortal } from 'react-dom'
import { FileText, ChevronRight, X, Maximize2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSlug from 'rehype-slug'
import { api } from '../lib/api'

// The source docs use MkDocs-Material's "!!! type \"Title\"" admonition
// syntax (see techdocs/docs/index.md, detection-pipeline.md) — plain
// react-markdown + remark-gfm has no idea what that means and would
// render it as a literal "!!! danger..." line followed by what markdown
// would likely mistake for an indented code block. Converted here into a
// blockquote with a bold title line instead, which renders correctly
// with the blockquote styling already added to index.css — simpler than
// writing a custom remark plugin for what's currently just two blocks.
const ADMONITION_ICON = { danger: '\u26a0\ufe0f', warning: '\u26a0\ufe0f', note: '\ud83d\udcdd', info: '\u2139\ufe0f' }
function convertAdmonitions(md) {
  const lines = md.split('\n')
  const out = []
  let i = 0
  while (i < lines.length) {
    const m = lines[i].match(/^!!! (\w+)\s+"([^"]+)"\s*$/)
    if (!m) { out.push(lines[i]); i++; continue }
    const [, type, title] = m
    const icon = ADMONITION_ICON[type] || '\u2139\ufe0f'
    out.push(`> **${icon} ${title}**`)
    out.push('>')
    i++
    while (i < lines.length && (lines[i].startsWith('    ') || lines[i].trim() === '')) {
      if (lines[i].trim() === '') { out.push('>') } else { out.push(`> ${lines[i].slice(4)}`) }
      i++
    }
    out.push('')
  }
  return out.join('\n')
}

export default function TechDocs() {
  const [pages, setPages] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [pageLoading, setPageLoading] = useState(false)
  const [error, setError] = useState(null)
  // filename -> blob object URL, so the same asset isn't re-fetched every
  // time a page referencing it is opened again during this session.
  const assetCache = useRef({})
  const [assetVersion, setAssetVersion] = useState(0)
  // Requested: figures (e.g. the architecture/detection-pipeline diagrams)
  // are read at a fixed inline width and can't be inspected at full
  // resolution without opening the underlying file directly. Click any
  // figure to expand it — { url, alt } of the clicked image, or null.
  const [lightbox, setLightbox] = useState(null)

  useEffect(() => {
    api.techdocs.list()
      .then(d => {
        setPages(d.pages)
        if (d.pages.length) setActiveId(d.pages[0].id)
        setLoading(false)
      })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  useEffect(() => {
    if (!activeId) return
    setPageLoading(true)
    api.techdocs.page(activeId)
      .then(text => { setContent(text); setPageLoading(false) })
      .catch(e => { setError(e.message); setPageLoading(false) })
  }, [activeId])

  // Markdown image sources are plain relative filenames (e.g.
  // "assets/fig1_system_architecture.png", matching the same paths used
  // by the standalone MkDocs site) — an <img> can't carry an
  // Authorization header, so each one gets swapped for an authenticated
  // blob URL after fetch, cached per filename for the rest of this
  // session rather than re-fetched on every page visit.
  function AuthedImage({ src, alt }) {
    const filename = (src || '').split('/').pop()
    const [url, setUrl] = useState(assetCache.current[filename] || null)

    useEffect(() => {
      if (assetCache.current[filename]) { setUrl(assetCache.current[filename]); return }
      let cancelled = false
      api.techdocs.assetUrl(filename)
        .then(objUrl => {
          if (cancelled) return
          assetCache.current[filename] = objUrl
          setUrl(objUrl)
          setAssetVersion(v => v + 1)
        })
        .catch(() => {})
      return () => { cancelled = true }
    }, [filename])

    if (!url) return (
      <div className="rounded-lg flex items-center justify-center text-xs my-4"
           style={{ height: 120, background: 'var(--bg-raised)', color: 'var(--text-tertiary)' }}>
        Loading figure…
      </div>
    )
    return (
      <button type="button" onClick={() => setLightbox({ url, alt })}
              className="relative block w-full my-4 rounded-lg overflow-hidden group cursor-zoom-in"
              style={{ border: '1px solid var(--border-subtle)', padding: 0 }}
              title="Click to expand">
        <img src={url} alt={alt} className="w-full block"/>
        <span className="absolute bottom-2 right-2 rounded-lg p-1.5 opacity-0 group-hover:opacity-100 transition-opacity"
              style={{ background: 'rgba(0,0,0,.55)' }}>
          <Maximize2 size={13} color="#fff"/>
        </span>
      </button>
    )
  }

  if (loading) return (
    <div className="page-root flex items-center justify-center h-64">
      <p className="text-sm animate-pulse" style={{ color: 'var(--text-tertiary)' }}>Loading technical docs…</p>
    </div>
  )

  if (error) return (
    <div className="page-root p-6">
      <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>{error}</p>
    </div>
  )

  return (
    <>
    <div className="page-root">
      <div className="p-4 sm:p-6 max-w-6xl mx-auto">
        <div className="flex items-center gap-2 mb-5">
          <FileText size={22} style={{ color: 'var(--accent-400)' }}/>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>Technical Documentation</h1>
        </div>

        <div className="flex flex-col md:flex-row gap-5">
          {/* Page nav */}
          <nav className="md:w-56 flex-shrink-0 flex md:flex-col gap-1 overflow-x-auto md:overflow-visible pb-2 md:pb-0">
            {pages.map(p => (
              <button key={p.id} onClick={() => setActiveId(p.id)}
                      className="flex items-center justify-between gap-1.5 px-3 py-2 rounded-lg text-sm text-left whitespace-nowrap md:whitespace-normal flex-shrink-0"
                      style={{
                        background: activeId === p.id ? 'var(--bg-raised)' : 'transparent',
                        color: activeId === p.id ? 'var(--accent-400)' : 'var(--text-secondary)',
                        fontWeight: activeId === p.id ? 600 : 400,
                      }}>
                {p.title}
                {activeId === p.id && <ChevronRight size={14} className="hidden md:block"/>}
              </button>
            ))}
          </nav>

          {/* Content */}
          <div className="flex-1 min-w-0 rounded-2xl p-5 sm:p-7"
               style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}>
            {pageLoading ? (
              <p className="text-sm animate-pulse" style={{ color: 'var(--text-tertiary)' }}>Loading…</p>
            ) : (
              <div className="techdocs-markdown">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeSlug]}
                  components={{
                    img: ({ src, alt }) => <AuthedImage src={src} alt={alt}/>,
                    // Reported bug: links between pages (e.g.
                    // "[Detection Pipeline](detection-pipeline.md)") are
                    // correct as written — that's exactly how MkDocs
                    // resolves internal links on the standalone
                    // techdocs/ site. But this in-app renderer isn't
                    // MkDocs; a literal <a href="detection-pipeline.md">
                    // just tries to navigate the SPA to a URL that
                    // doesn't correspond to any route, landing on a
                    // blank page. Internal .md links are intercepted here
                    // and routed through the same activeId switch the
                    // sidebar itself uses instead of letting the browser
                    // navigate; anything else (http/https, mailto, etc.)
                    // still renders as a normal link.
                    //
                    // Second reported bug, same root cause: a same-page
                    // anchor link (e.g. "#bundled-headscale-setup-...",
                    // no ".md" prefix — a heading further down THIS page)
                    // matched neither the .md case above nor looked like
                    // an external URL, but still fell into the "else"
                    // branch below, which force-opens everything in a new
                    // tab. rehypeSlug (added) is what gives headings a
                    // matching id in the first place — without it there's
                    // nothing on the page for even a correct anchor link
                    // to land on. scrollIntoView (not a bare href jump)
                    // because this markdown renders inside a scrollable
                    // card/portal, not the top-level document — a native
                    // anchor jump isn't guaranteed to scroll the right
                    // container in that layout.
                    a: ({ href, children }) => {
                      const m = href && href.match(/^([a-z0-9-]+)\.md(#.*)?$/i)
                      if (m) {
                        const targetId = m[1]
                        return (
                          <a href={`#${targetId}`}
                             onClick={e => { e.preventDefault(); setActiveId(targetId) }}
                             style={{ cursor: 'pointer' }}>
                            {children}
                          </a>
                        )
                      }
                      if (href && href.startsWith('#')) {
                        const anchorId = href.slice(1)
                        return (
                          <a href={href}
                             onClick={e => {
                               e.preventDefault()
                               document.getElementById(anchorId)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                             }}
                             style={{ cursor: 'pointer' }}>
                            {children}
                          </a>
                        )
                      }
                      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
                    },
                    // Reported bug: wide tables (e.g. the microphone
                    // comparison table's 7 columns) overflowed the card
                    // and bled off the right edge of the screen instead
                    // of scrolling — .techdocs-markdown table had no
                    // wrapping element, and a bare <table> with
                    // width:100% still overflows its parent once its
                    // cells' natural content width exceeds the container,
                    // since 100% only bounds the MINIMUM width, not the
                    // maximum. Wrapping in a scrollable div (own
                    // overflow-x, independent of pre's) fixes this
                    // without shrinking cell text or breaking the table's
                    // own layout. Verified against the actual reported
                    // table in a browser at a narrow (390px) viewport.
                    table: ({ children }) => (
                      <div className="techdocs-table-scroll">
                        <table>{children}</table>
                      </div>
                    ),
                  }}
                >
                  {convertAdmonitions(content)}
                </ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>

    {/* Lightbox — rendered via a portal directly into document.body, not
        inline in the component tree, for the same reason InatSubmitButton's
        modal is: a position:fixed element can be clipped/repositioned by
        any ancestor with position:relative + z-index (a documented
        cross-browser WebKit/Chrome/Safari quirk), and this page's own
        two-column flex layout is exactly that kind of ancestor. */}
    {lightbox && createPortal(
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,.85)' }}
           onClick={() => setLightbox(null)}>
        <div className="max-w-4xl w-full" onClick={e => e.stopPropagation()}>
          <div className="flex justify-end mb-2">
            <button onClick={() => setLightbox(null)} className="tactile-press text-gray-300 hover:text-white p-1">
              <X size={20}/>
            </button>
          </div>
          <img src={lightbox.url} alt={lightbox.alt}
               className="w-full rounded-xl max-h-[85vh] object-contain"/>
        </div>
      </div>,
      document.body
    )}
    </>
  )
}
