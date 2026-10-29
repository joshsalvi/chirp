# Theme app icons

One Home Screen icon per theme: the theme's logo (ThemedChirpLogos.jsx, or the
default mark with the theme's ink and accent bars) on its panel colour, placed
exactly like ios-icons/icon-1024.png. Forest is the main icon.

Run from a scratch folder after `npm run build` in chirp-server-instances/frontend:

1. `node 1-theme-colors.mjs` reads each theme's colours from the built CSS (edit the CSS path) into vars.json.
2. Copy `2-logos-entry.jsx` into frontend/scripts/, bundle it with
   `node_modules/.bin/esbuild scripts/2-logos-entry.jsx --bundle --platform=node --jsx=automatic --loader:.js=jsx --outfile=out.cjs`,
   then `LOGO_SIZE=40 node out.cjs > logos.json`.
3. `node 3-render-icons.mjs` writes out2/<theme>.png (1024 px).

Copy the PNGs (all but forest) to ios-icons/themes/ and 120 px versions to
frontend/public/app-icons/ in both forks. build-ios.sh bundles each as AppIcon-<theme>.
