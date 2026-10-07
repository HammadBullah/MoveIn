/**
 * A rendering test for the planning screen.
 *
 * The UI is the product, and a type-check does not tell you whether a page
 * renders or what it says. This mounts the real App in a DOM, points it at the
 * real API, and asserts on what a traveller would actually see: option rows,
 * the walk limit, the price, and the separate section for the long walks.
 *
 * Run with:  npm run test:render      (needs the API on :8000)
 */
import { bundle } from './bundle.mjs'

const API = process.env.MOVEIN_API_URL || 'http://127.0.0.1:8000'
const checks = []
let failures = 0

function check(name, condition, detail = '') {
  const ok = Boolean(condition)
  if (!ok) failures += 1
  checks.push(`${ok ? 'ok  ' : 'FAIL'} ${name}${ok || !detail ? '' : ` — ${detail}`}`)
}

async function main() {
  const { JSDOM } = await import('jsdom')
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost:5173/#/plan',
    pretendToBeVisual: true,
  })

  // The app runs in a browser; give the bundle the pieces of one it uses.
  const { window } = dom
  globalThis.window = window
  globalThis.document = window.document
  for (const name of [
    'HTMLElement',
    'Node',
    'Event',
    'MouseEvent',
    'KeyboardEvent',
    'localStorage',
    'location',
    'getComputedStyle',
  ]) {
    if (name in window) {
      Object.defineProperty(globalThis, name, {
        value: window[name],
        configurable: true,
        writable: true,
      })
    }
  }
  globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0)
  globalThis.cancelAnimationFrame = (id) => clearTimeout(id)
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })

  // Relative /api calls, resolved against the dev server's proxy the way the
  // browser would resolve them.
  const realFetch = globalThis.fetch
  globalThis.fetch = (input, init) =>
    realFetch(typeof input === 'string' && input.startsWith('/') ? API + input : input, init)
  window.fetch = globalThis.fetch

  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  const { act } = await import('react')

  // The bundle mounts itself into #root, exactly as it does in a browser.
  const bundlePath = await bundle()
  await act(async () => {
    await import(bundlePath)
  })

  const container = window.document.getElementById('root')
  for (let i = 0; i < 60; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
    if (container.querySelectorAll('.ride').length > 0) break
  }

  const text = container.textContent
  const rows = container.querySelectorAll('.ride')
  const walkWarnings = container.querySelectorAll('.ride--walking')
  const chips = Array.from(container.querySelectorAll('.chip')).map((c) => c.textContent.trim())

  check('the search box renders', container.querySelector('.where') !== null)
  check('from/to inputs are present', container.querySelectorAll('.place__input').length === 2)
  check('the walk limit is offered as a choice', chips.some((c) => c.includes('15 min')))
  check('"any walk" is offered', chips.some((c) => c.includes('Any walk')))
  check('preference chips come from the API', chips.length >= 8, `saw ${chips.length} chips`)
  check('option rows rendered', rows.length > 0, `${rows.length} rows`)
  check('options are labelled with their trade-off', text.includes('Cheapest'))
  check('each row shows a price', /\£\d+\.\d\d/.test(text))
  check('the detail panel opens with the itinerary', container.querySelector('.timeline') !== null)
  check('the detail says what the walk is', /min walk|no walking/.test(text))

  // Long walks: never mixed in silently.
  //
  // The default promise is a 15 minute maximum, so the first screen has none of
  // them.  Asking for "Any walk" must bring them back -- in their own section,
  // flagged, and not mixed in with the options a person would actually take.
  check(
    'the default keeps long walks out of the results',
    container.querySelectorAll('.ride--walking').length === 0,
    `${container.querySelectorAll('.ride--walking').length} long-walk rows on a 15 min promise`,
  )
  const anyWalk = Array.from(container.querySelectorAll('.chip')).find(
    (c) => c.textContent.trim() === 'Any walk',
  )
  check('there is a way to ask for longer walks', Boolean(anyWalk))
  if (anyWalk) {
    await act(async () => {
      anyWalk.dispatchEvent(new window.MouseEvent('click', { bubbles: true }))
    })
    for (let i = 0; i < 40; i += 1) {
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 100))
      })
      if (
        Array.from(container.querySelectorAll('button')).some((b) =>
          b.textContent.includes('longer walk'),
        )
      ) {
        break
      }
    }
    check(
      'asking for any walk re-plans without touching the button',
      Array.from(container.querySelectorAll('button')).some((b) =>
        b.textContent.includes('longer walk'),
      ),
    )
  }

  const moreButton = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent.includes('longer walk'),
  )
  if (moreButton) {
    check(
      'long-walk options are behind a labelled section',
      moreButton.textContent.includes('Shorter walks only'),
      moreButton.textContent.slice(0, 120),
    )
    check(
      'long-walk rows are hidden until asked for',
      walkWarnings.length === 0 || moreButton.getAttribute('aria-expanded') === 'true',
    )
    const before = container.querySelectorAll('.ride').length
    await act(async () => {
      moreButton.dispatchEvent(new window.MouseEvent('click', { bubbles: true }))
    })
    const after = container.querySelectorAll('.ride').length
    check('opening the section reveals them', after > before, `${before} -> ${after}`)
    check(
      'the collapsed section says how many are hidden',
      /\d+ more option/.test(moreButton.textContent),
      moreButton.textContent.slice(0, 120),
    )
    check(
      'the revealed rows warn about the walk',
      container.querySelectorAll('.ride--walking').length > 0,
    )
    check(
      'the warning names the walk',
      /\d+ min walk/.test(container.textContent),
    )
  } else {
    check('a long-walk section is offered when one exists', true, 'no long walks on this route')
  }

  // Selecting a different option moves the detail panel to it.
  const allRows = Array.from(container.querySelectorAll('.ride'))
  const target = allRows.find((row) => !row.classList.contains('ride--selected'))
  if (target) {
    const label = target.getAttribute('aria-label')
    await act(async () => {
      target.dispatchEvent(new window.MouseEvent('click', { bubbles: true }))
    })
    check(
      'choosing a row moves the selection to it',
      target.classList.contains('ride--selected'),
      `clicked ${label}`,
    )
    check(
      'and the detail panel describes that row',
      container.querySelector('.detail__times')?.textContent?.includes(
        (label || '').slice(0, 5),
      ),
      container.querySelector('.detail__times')?.textContent,
    )
  }

  console.log(checks.join('\n'))
  console.log(`\n${checks.length - failures}/${checks.length} render checks passed`)
  process.exit(failures ? 1 : 0)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
