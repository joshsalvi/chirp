import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

// Version stamping actually happens in scripts/stamp-sw-version.mjs (npm
// `prebuild` hook), which writes public/sw.js's CACHE constant *before*
// Vite runs; Vite's static-copy of public/ then carries that stamped
// value into dist/sw.js unchanged. This plugin is a closeBundle-time
// VERIFICATION only — it does not re-stamp dist/sw.js itself. (It used
// to also perform the replace, but that raced with the prebuild step:
// once both existed, dist/sw.js already held the correct value by the
// time this ran, so `sw.replace()` was a genuine no-op — matched fine,
// nothing left to change — yet the old check couldn't tell that apart
// from "the regex never matched at all," and threw on every single
// build. Fixed here by checking the actual expected string is present,
// not by diffing before/after.)
function verifyServiceWorkerVersion() {
  return {
    name: 'verify-sw-version',
    closeBundle() {
      const versionPath = path.resolve(__dirname, '../VERSION')
      const swPath = path.resolve(__dirname, 'dist/sw.js')
      if (!fs.existsSync(versionPath) || !fs.existsSync(swPath)) {
        console.warn(`[verify-sw-version] Skipped — missing ${!fs.existsSync(versionPath) ? 'VERSION file' : 'dist/sw.js'}`)
        return
      }
      const version = fs.readFileSync(versionPath, 'utf-8').trim()
      const sw = fs.readFileSync(swPath, 'utf-8')
      const expected = `const CACHE = 'chirp-v${version}'`
      if (!sw.includes(expected)) {
        throw new Error(
          `[verify-sw-version] dist/sw.js does not contain "${expected}" — ` +
          `prebuild stamping (scripts/stamp-sw-version.mjs) did not take effect, ` +
          `or public/sw.js's format has changed. Refusing to silently ship an ` +
          `un-versioned service worker.`
        )
      }
      console.log(`[verify-sw-version] dist/sw.js confirmed at 'chirp-v${version}'`)
    },
  }
}

export default defineConfig({
  plugins: [react(), verifyServiceWorkerVersion()],
  server: {
    proxy: {
      '/api': 'http://localhost:8765',
      '/ws': { target: 'ws://localhost:8765', ws: true },
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // Vite preloads every chunk reachable from a chunk being loaded.
    // Recharts (vendor-charts) is only needed by the Statistics page and the
    // Dashboard's two bar charts (DashboardBarChart, lazy), and Markdown
    // (vendor-markdown) only by pages that render notes or docs, so other
    // chunks drop those preloads.
    modulePreload: {
      resolveDependencies: (filename, deps) => {
        const charts = /Statistics|DashboardBarChart|UserActivity|BirdProfile/.test(filename)
        const markdown = /RecordingDetail|TechDocs|BirdProfile/.test(filename)
        return deps.filter(dep => (charts || !dep.includes('vendor-charts'))
                              && (markdown || !dep.includes('vendor-markdown')))
      },
    },
    rollupOptions: {
      output: {
        // Vendor chunks change only with package.json, so browsers keep
        // them cached across releases. Named vendor chunks for the three big dependency groups; the
        // rest follow the code that uses them. The old catch-all "vendor"
        // chunk (504 kB) put Recharts' and Markdown's dependencies on every
        // page's critical path.
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          const pkg = id.split('node_modules/').pop().split('/')
          const name = pkg[0].startsWith('@') ? `${pkg[0]}/${pkg[1]}` : pkg[0]
          if (name === 'xterm' || name.startsWith('@xterm/')) return  // SSHTerminal's own chunk
          if (/^(react|react-dom|scheduler|react-router|react-router-dom|@remix-run\/router)$/.test(name)) return 'vendor-react'
          if (/^(recharts|recharts-scale|react-smooth|victory-vendor|d3-.*|lodash|decimal\.js-light|fast-equals|eventemitter3|tiny-invariant|internmap|react-transition-group|dom-helpers|clsx|react-is)$/.test(name)) return 'vendor-charts'
          if (/^(react-markdown|remark-.*|rehype-.*|unified|micromark.*|mdast-.*|hast-.*|hast|unist-.*|vfile.*|property-information|space-separated-tokens|comma-separated-tokens|html-url-attributes|devlop|bail|trough|is-plain-obj|decode-named-character-reference|character-entities.*|character-reference-invalid|zwitch|longest-streak|ccount|markdown-table|trim-lines|estree-util-.*|style-to-.*|inline-style-parser|github-slugger|extend)$/.test(name)) return 'vendor-markdown'
        },
      },
    },
  }
})
