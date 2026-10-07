/**
 * A rendering test for the app.
 *
 * The UI is the product, and a type-check does not tell you whether a screen
 * renders or what it says. This mounts the real bundle in a DOM, points it at
 * the real API, and walks the journey a traveller would take: land on a result,
 * read the cards, open one, look at the timeline, compare prices, and open the
 * transport filter.
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
    url: 'http://localhost:5173/#/results?from=Nottingham&to=Birmingham&pref=best_value',
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
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }

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
  const settle = async (ms = 120) =>
    act(async () => {
      await new Promise((resolve) => setTimeout(resolve, ms))
    })
  const click = async (node) => {
    await act(async () => {
      node.dispatchEvent(new window.MouseEvent('click', { bubbles: true }))
    })
  }
  const waitFor = async (selector, tries = 90) => {
    for (let i = 0; i < tries; i += 1) {
      await settle(120)
      const found = container.querySelectorAll(selector)
      if (found.length) return found
    }
    return container.querySelectorAll(selector)
  }

  // ---- results screen ----------------------------------------------------
  const cards = await waitFor('.jcard')
  const text = container.textContent

  check('the results screen renders cards', cards.length > 0, `${cards.length} cards`)
  check('the map is drawn from real coordinates', container.querySelector('.map__route') !== null)
  check('the map marks the route ends', container.querySelectorAll('.map__marker').length >= 2)
  check('the bottom sheet is present', container.querySelector('.sheet') !== null)
  check(
    'the sheet names the journey',
    container.querySelector('.results__route')?.textContent?.includes('Nottingham'),
    container.querySelector('.results__route')?.textContent,
  )
  check('every card quotes a price', /\£\d+\.\d\d/.test(text))
  check('every card quotes a duration', /\d+h\s\d+m|\d+m/.test(text))
  check('the cards offer a way in', text.includes('View journey'))
  check('walking is stated on the card', /min walk|no walking/.test(text))

  const chips = Array.from(container.querySelectorAll('.chip')).map((c) => c.textContent.trim())
  check('the four trade-off chips are offered', ['Recommended', 'Cheapest', 'Fastest'].every((label) => chips.some((c) => c.includes(label))), chips.join(' | '))
  check('there is a filter entry point', chips.some((c) => c.includes('Filters') || c.includes('More')))
  check(
    'cards wear their trade-off badge',
    /Best value|Cheapest|Fastest|Fewest changes|Least walking/.test(text),
  )

  // ---- journey detail ----------------------------------------------------
  const viewButton = Array.from(container.querySelectorAll('.jcard button')).find((b) =>
    b.textContent.includes('View journey'),
  )
  if (viewButton) {
    await click(viewButton)
    const timeline = await waitFor('.timeline__stage')
    check('the detail screen shows a timeline', timeline.length > 0, `${timeline.length} stages`)
    check('stages are numbered', container.querySelector('.timeline__index') !== null)
    check('the detail quotes times', container.querySelectorAll('.timeline__time').length > 0)
    check('the detail names the places', container.querySelectorAll('.timeline__place').length > 0)
    check(
      'the detail offers to start the journey',
      Array.from(container.querySelectorAll('button')).some((b) =>
        b.textContent.includes('Start journey'),
      ),
    )

    // ---- live journey ----------------------------------------------------
    const start = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Start journey'),
    )
    if (start) {
      await click(start)
      await waitFor('.live__next')
      check('live mode says you are on your way', container.textContent.includes('You’re on your way'))
      check('live mode lists the steps', container.querySelectorAll('.step').length > 0)
      check('live mode shows the next vehicle', container.querySelector('.live__next') !== null)
      window.history.back
      await act(async () => {
        window.location.hash = '#/results?from=Nottingham&to=Birmingham&pref=best_value'
        window.dispatchEvent(new window.Event('hashchange'))
      })
      await settle(200)
    }

    // ---- compare ---------------------------------------------------------
    const compareFromDetail = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Compare'),
    )
    if (compareFromDetail) {
      await click(compareFromDetail)
      const rows = await waitFor('.compare__row')
      check('the comparison lists options', rows.length > 0, `${rows.length} rows`)
      check(
        'the comparison highlights the cheapest',
        container.querySelector('.compare__row--best') !== null,
      )
      check('the comparison quotes prices', /\£\d+\.\d\d/.test(container.textContent))
      const back = Array.from(container.querySelectorAll('button')).find((b) =>
        b.textContent.includes('Back to results'),
      )
      if (back) await click(back)
      await settle(200)
    }
  }

  // ---- the transport filter ---------------------------------------------
  const filterButton = Array.from(container.querySelectorAll('button')).find(
    (b) => b.textContent.trim() === 'Filters' || b.textContent.includes('More'),
  )
  if (filterButton) {
    await click(filterButton)
    await settle(200)
    const tiles = container.querySelectorAll('.mode-tile')
    check('the filter sheet offers every mode', tiles.length >= 8, `${tiles.length} mode tiles`)
    check('the filter sheet offers preferences', container.querySelectorAll('.chip').length > 4)
    check('the filter sheet has a walking limit', container.querySelectorAll('input[type=range]').length >= 2)
    const apply = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Apply'),
    )
    check('the filter sheet can be applied', Boolean(apply))
    if (apply) await click(apply)
    await settle(200)
  }

  // ---- home --------------------------------------------------------------
  await act(async () => {
    window.location.hash = '#/home'
    window.dispatchEvent(new window.Event('hashchange'))
  })
  await settle(300)
  check('the home screen asks where you are going', container.textContent.includes('Where are you going?'))
  check('the search card has from and to', container.querySelectorAll('.place__input').length === 2)
  check(
    'the home screen offers the primary action',
    Array.from(container.querySelectorAll('button')).some((b) =>
      b.textContent.includes('Find my journey'),
    ),
  )
  check('the bottom navigation is present', container.querySelectorAll('.tabbar__item').length === 4)
  check('saved places are offered', container.textContent.includes('Saved places'))

  console.log(checks.join('\n'))
  console.log(`\n${checks.length - failures}/${checks.length} render checks passed`)
  process.exit(failures ? 1 : 0)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
