/**
 * Write the journey map out as a standalone SVG, so the geometry can be looked
 * at outside a browser.  The render suite asserts on the map; this is for
 * seeing it -- a `2`-vertex line and a `14`-vertex line both pass a DOM query,
 * and only one of them is a route.
 *
 *   npm run map:preview                     # Nottingham -> Birmingham, first option
 *   SHOT_CARD=3 npm run map:preview         # the fourth option in the list
 *   SHOT_HASH='#/results?from=Leeds&to=Manchester' npm run map:preview
 *
 * Not part of `npm test`: it needs the API up, like the render suite.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { bundle } from './bundle.mjs'
const API = 'http://127.0.0.1:8000'
const out = process.env.SHOT_OUT || '.cache/map-preview.svg'
const hash = process.env.SHOT_HASH || '#/results?from=Nottingham&to=Birmingham&pref=best_value'
const { JSDOM } = await import('jsdom')
const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: `http://localhost:5173/${hash}`,
  pretendToBeVisual: true,
})
const { window } = dom
globalThis.window = window
globalThis.document = window.document
for (const n of ['HTMLElement', 'Node', 'Event', 'MouseEvent', 'localStorage', 'location', 'getComputedStyle']) {
  if (n in window) Object.defineProperty(globalThis, n, { value: window[n], configurable: true, writable: true })
}
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0)
window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })
window.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} }
const realFetch = globalThis.fetch
globalThis.fetch = (i, init) => realFetch(typeof i === 'string' && i.startsWith('/') ? API + i : i, init)
window.fetch = globalThis.fetch
// jsdom has no layout, so give the map the frame a phone would give it.
const FRAME_W = Number(process.env.SHOT_W ?? '452')
const FRAME_H = Number(process.env.SHOT_H ?? '780')
for (const prop of ['clientWidth', 'clientHeight']) {
  const original = Object.getOwnPropertyDescriptor(window.Element.prototype, prop)
  Object.defineProperty(window.Element.prototype, prop, {
    configurable: true,
    get() {
      if (this.classList?.contains('map') || this.classList?.contains('results__map')) {
        return prop === 'clientWidth' ? FRAME_W : FRAME_H
      }
      return original?.get?.call(this) ?? 0
    },
  })
}

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const { act } = await import('react')
await act(async () => { await import(await bundle()) })
const container = window.document.getElementById('root')
for (let i = 0; i < 90 && !container.querySelector('.map__route'); i++) {
  await act(async () => { await new Promise((r) => setTimeout(r, 120)) })
}
// Optional: select the Nth card so the map follows the tapped journey.
const pick = Number(process.env.SHOT_CARD ?? '-1')
const cards = Array.from(container.querySelectorAll('.jcard'))
if (pick >= 0 && cards[pick]) {
  await act(async () => { cards[pick].dispatchEvent(new window.MouseEvent('click', { bubbles: true })) })
  await act(async () => { await new Promise((r) => setTimeout(r, 400)) })
}
const svg = container.querySelector('svg.map__canvas')
if (!svg) { console.error('no map found'); process.exit(1) }
const w = Number(svg.getAttribute('viewBox').split(' ')[2])
const h = Number(svg.getAttribute('viewBox').split(' ')[3])
// The app styles its SVG with classes; resolve them literally for the rasteriser.
const style = `
  <style>
    .map__graticule line { stroke: #c9ced9; stroke-width: 1; stroke-dasharray: 3 5; }
    .map__grid-label { font-size: 8.5px; font-weight: 600; fill: #9aa1b1; font-family: Helvetica, Arial, sans-serif; }
    .map__stop-label { font-size: 9.5px; font-weight: 600; fill: #202534; font-family: Helvetica, Arial, sans-serif; }
    .map__label { font-size: 11px; font-weight: 650; fill: #0b0e16; stroke: #fff; stroke-width: 3.2px; paint-order: stroke; font-family: Helvetica, Arial, sans-serif; }
    .map__stop { fill: #ffffff; stroke-width: 2; }
    .map__route-casing { stroke: #ffffff; stroke-linecap: round; stroke-linejoin: round; }
    .map__route { stroke-linecap: round; stroke-linejoin: round; }
  </style>`
const header = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" xmlns:xlink="http://www.w3.org/1999/xlink">${style}<rect width="${w}" height="${h}" fill="#eef1fb"/>`
let body = svg.innerHTML
body = body.replace(/ stroke="var\([^)]*\)"/g, ' stroke="#0b0e16"').replace(/ fill="var\([^)]*\)"/g, ' fill="#4b3aff"')
mkdirSync(dirname(out), { recursive: true })
writeFileSync(out, `${header}${body}</svg>`)
console.log('wrote', out, `${w}x${h}`, 'cards:', cards.length)
process.exit(0)
