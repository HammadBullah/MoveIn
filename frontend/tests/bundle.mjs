/**
 * Bundle the app for the rendering test.
 *
 * The browser build is produced by Vite; this is the same sources through
 * esbuild, into a temporary file Node can import. Both are configured as ESM so
 * React resolves to the module build, which is what a browser gets.
 */
import { build } from 'esbuild'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))

export async function bundle() {
  const dir = await mkdtemp(path.join(tmpdir(), 'movein-render-'))
  const outfile = path.join(dir, 'app.mjs')
  await build({
    entryPoints: [path.join(here, '..', 'src', 'main.tsx')],
    outfile,
    bundle: true,
    format: 'esm',
    platform: 'browser',
    target: 'es2020',
    jsx: 'automatic',
    define: { 'process.env.NODE_ENV': '"development"' },
    // Leaflet's stylesheet points at marker images, which Vite emits as assets
    // and esbuild has no loader for.  Inline them: this bundle is for a DOM
    // without a network, and the app draws its own markers anyway.
    loader: { '.png': 'dataurl', '.gif': 'dataurl', '.svg': 'dataurl' },
    logLevel: 'error',
  })
  return outfile
}
