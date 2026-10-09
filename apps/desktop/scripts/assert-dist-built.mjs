// Build-time guard: refuse to hand a half-built renderer to electron-builder.
//
// `npm run pack` / `npm run dist*` are `npm run build && npm run builder`.
// If the `build` step (tsc -b && vite build) fails but packaging proceeds
// anyway — a stale checkout that fails typecheck, an interrupted vite build,
// or npm not short-circuiting `&&` in some shells — electron-builder happily
// packages an app with an empty or missing `dist/`. The result launches but
// blank-pages with `ERR_FILE_NOT_FOUND` for dist/index.html, with no clue why.
//
// This runs at the tail of `build`, after vite build, so any packaging path
// inherits it. It fails loud and early instead of shipping a broken bundle.
// See issues #39484 (renderer blank page) and #41327 / #39472 (dashboard 404).

import { existsSync, statSync, readdirSync, readFileSync } from "fs"
import { dirname, isAbsolute, join, relative, resolve, sep } from "path"
import { isMain } from "./utils.mjs"

// Pure check — returns { ok: true } or { ok: false, error: "..." }.
// Kept side-effect-free so it can be unit tested without spawning a process.
export function checkDistBuilt(distDir) {
  if (!existsSync(distDir) || !statSync(distDir).isDirectory()) {
    return { ok: false, error: `no dist directory at ${distDir}` }
  }

  const indexHtml = join(distDir, "index.html")
  if (!existsSync(indexHtml) || !statSync(indexHtml).isFile()) {
    return { ok: false, error: `dist/index.html is missing at ${indexHtml}` }
  }
  if (statSync(indexHtml).size === 0) {
    return { ok: false, error: `dist/index.html is empty at ${indexHtml}` }
  }

  // index.html alone isn't enough — vite emits hashed JS into dist/assets.
  // An index.html with no script bundle still blank-pages.
  const assetsDir = join(distDir, "assets")
  const hasAssets =
    existsSync(assetsDir) &&
    statSync(assetsDir).isDirectory() &&
    readdirSync(assetsDir).some(name => name.endsWith(".js"))
  if (!hasAssets) {
    return { ok: false, error: `dist/assets has no built JS bundle (expected vite output under ${assetsDir})` }
  }

  // CSS assets must be inside the packaged renderer, not a node_modules path
  // that happened to exist on the build machine. Vite can warn about an
  // unresolved url() and still report a successful build.
  for (const name of readdirSync(assetsDir).filter(name => name.endsWith(".css"))) {
    const cssPath = join(assetsDir, name)
    const css = readFileSync(cssPath, "utf8")
    for (const match of css.matchAll(/url\(\s*['"]?([^'"\)]+)['"]?\s*\)/g)) {
      const url = match[1].split(/[?#]/, 1)[0]
      if (!url.startsWith("./") && !url.startsWith("../")) continue
      const asset = resolve(dirname(cssPath), url)
      const withinDist = relative(distDir, asset)
      if (isAbsolute(withinDist) || withinDist === ".." || withinDist.startsWith(`..${sep}`) || !existsSync(asset)) {
        return { ok: false, error: `CSS asset is missing from dist: ${url} (in ${name})` }
      }
    }
  }

  return { ok: true }
}

function main() {
  const desktopRoot = resolve(import.meta.dirname, "..")
  const distDir = join(desktopRoot, "dist")
  const result = checkDistBuilt(distDir)

  if (!result.ok) {
    console.error(`\n✗ assert-dist-built: ${result.error}`)
    console.error("  The renderer bundle is missing or incomplete, so packaging")
    console.error("  would produce an app that launches to a blank page.")
    console.error("  Re-run the build and check the tsc/vite output above for the")
    console.error("  real failure, then package again:")
    console.error(`    cd ${desktopRoot} && npm run build\n`)
    process.exit(1)
  }

  console.log("✓ assert-dist-built: dist/index.html + assets present")
}

if (isMain(import.meta.url)) {
  main()
}

export default { checkDistBuilt }
