# capacitor.config.json — why it's JSON, and what each setting is for

## Why JSON, not .ts or .js

Two real, confirmed build failures led here, in order:

1. **`capacitor.config.ts` → `npx cap add ios` failed** with
   `TypeError: Cannot read properties of undefined (reading 'CommonJS')`,
   inside `@capacitor/cli`'s own TypeScript-config-loading code. This
   traces to a known compatibility gap between `@capacitor/cli`'s
   internal use of the TypeScript compiler API and the installed
   `typescript`/Node version combination — not anything wrong with the
   config's own content.

2. **Converted to `capacitor.config.js` → `npx cap add ios` "succeeded"
   but silently produced an app with no appId at all** (`[error]
   Missing appId for new platform`), and `npx cap init` refused to run
   at all with `Cannot run init for a project using a non-JSON
   configuration file`. A plain Node `import()` of the same file
   correctly returned every real setting — confirmed directly — so this
   wasn't a mistake in the file's own content either. `@capacitor/cli`'s
   own internal config loader evidently doesn't reliably read a `.js`
   file's exports the same way Node's own ESM loader does, regardless
   of whether it's written as `module.exports` or `export default`.

Given two different non-JSON formats each hit a real, different
`@capacitor/cli`-internal failure, and `cap init`'s own error message
explicitly points at deleting `capacitor.config.js` as the fix — JSON
is the one format with zero ambiguity: no module system, no TypeScript
compilation, no code execution at all, just parsed data. This is the
config format actually used going forward.

## What each setting is for

Since JSON can't carry comments, the reasoning that used to live inline
in the `.ts`/`.js` versions lives here instead:

- **`server.url`** — in production, this should be your public server
  URL so the app works from anywhere, not just your home network. The
  WKWebView loads your server's real web app directly over HTTPS.
- **`server.cleartext: false`** — don't allow navigating within the app
  without triggering the external browser; keeps navigation contained
  to the real app experience.
- **`server.allowNavigation`** — must include your server's real
  hostname, or API calls from within the app will be blocked.
- **`ios.scheme`** — the scheme used to load the web app locally if the
  server is unreachable.
- **`ios.scrollEnabled: true`** — use web scroll behavior, matching the
  web app exactly rather than a native-feeling scroll.
- **`ios.allowsLinkPreview: false`** — disables the iOS long-press link
  preview, since it doesn't make sense for this kind of app.
- **`ios.contentInset: "always"`** — dark content on our dark background
  looks wrong; this keeps the status bar area properly inset.
- **`ios.preferredContentMode: "mobile"`** — prefer 120Hz on ProMotion
  displays.
- **`plugins.StatusBar.style: "DARK"`** — light (white) status bar text,
  matching the app's dark background (the naming here is the OS's own:
  "DARK" style means light-colored text, suited for a dark background).
- **`plugins.PushNotifications.presentationOptions`** — badge, sound,
  and alert all shown even while the app is in the foreground.

If any of these ever need to change, edit `capacitor.config.json`
directly (it's just data — no rebuild step needed to edit it, though
`npx cap sync` does need to be re-run to apply changes to the native
project).
