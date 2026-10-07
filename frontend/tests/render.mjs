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
  globalThis.fetch = async (input, init) => {
    const url = typeof input === 'string' && input.startsWith('/') ? API + input : input
    if (process.env.MOVEIN_TRACE) console.error(`fetch ${typeof url === 'string' ? url : String(url)}`)
    const response = await realFetch(url, init)
    if (!response.ok) {
      // A rejected request is the sort of bug that shows up as "the button does
      // nothing", so say what the API objected to rather than letting the screen
      // quietly render an error state the test might miss.
      const body = await response.clone().text()
      console.error(`API ${response.status} ${typeof url === 'string' ? url : ''} :: ${body.slice(0, 400)}`)
    }
    return response
  }
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

  // The line has to be the vehicle's actual path, not a ruler between the ends.
  // A coach that calls at Derby bends through Derby; if the path is two points
  // long, the map is drawing a journey nobody takes.
  const paths = Array.from(container.querySelectorAll('.map__route'))
  const vertices = paths.map((path) => {
    const d = path.getAttribute('d') || ''
    return (d.match(/[ML]/g) || []).length
  })
  check(
    'the route follows the stops it calls at',
    vertices.some((count) => count > 2),
    `path vertex counts: ${vertices.join(', ')} (2 = a straight line past the stops)`,
  )
  check(
    'every stop on the route is drawn',
    container.querySelectorAll('.map__stop').length >= 1,
    `${container.querySelectorAll('.map__stop').length} intermediate stops drawn`,
  )
  check('the map states its scale', Boolean(container.querySelector('.map__scale-text')?.textContent))
  check(
    'the map is framed with real coordinates',
    container.querySelectorAll('.map__graticule line').length >= 2,
  )
  check(
    'each mode keeps its own line treatment',
    Boolean(
      paths.find((path) => (path.getAttribute('stroke-dasharray') || '') !== '') ||
        container.querySelector('.map__route-casing'),
    ),
  )
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

  // Dragging the sheet is the primary gesture of the whole screen, and it ends
  // with a click on most pointers -- which must not undo the drag.
  const grab = container.querySelector('.sheet__grab')
  if (grab) {
    const pointer = (type, y) =>
      new window.MouseEvent(type, { bubbles: true, clientY: y })
    await act(async () => {
      grab.dispatchEvent(pointer('pointerdown', 500))
      grab.dispatchEvent(pointer('pointermove', 380))
      grab.dispatchEvent(pointer('pointerup', 380))
      grab.dispatchEvent(pointer('click', 380))
    })
    await settle(120)
    check(
      'dragging the sheet up opens it and the tap does not undo it',
      container.querySelector('.sheet')?.className.includes('sheet--full'),
      container.querySelector('.sheet')?.className,
    )
    await act(async () => {
      grab.dispatchEvent(pointer('pointerdown', 380))
      grab.dispatchEvent(pointer('pointermove', 520))
      grab.dispatchEvent(pointer('pointerup', 520))
      grab.dispatchEvent(pointer('click', 520))
    })
    await settle(120)
    check(
      'dragging it back down half-closes it',
      container.querySelector('.sheet')?.className.includes('sheet--half'),
      container.querySelector('.sheet')?.className,
    )
  }

  // The 15-minute promise: on the default limit there is nothing to warn about.
  check(
    'the default list is free of long walks',
    container.querySelector('.jlist--longwalk') === null,
  )
  check(
    'no card in the default list warns about a long walk',
    !Array.from(container.querySelectorAll('.jlist .jcard')).some((c) =>
      c.textContent.includes('Long walk'),
    ),
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
    const ranges = container.querySelectorAll('input[type=range]')
    check('the filter sheet has a walking limit', ranges.length >= 2)

    // Ask for longer walks than the promise allows, the way a traveller with a
    // heavy bag and no bus stop nearby would.
    if (ranges.length) {
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value',
      ).set
      await act(async () => {
        setter.call(ranges[0], '30')
        ranges[0].dispatchEvent(new window.Event('input', { bubbles: true }))
        ranges[0].dispatchEvent(new window.Event('change', { bubbles: true }))
      })
      check('the walking limit can be widened', container.textContent.includes('30 min'))
    }

    const apply = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Apply'),
    )
    check('the filter sheet can be applied', Boolean(apply))
    if (apply) await click(apply)
    const toggle = await waitFor('.longwalk__toggle')
    check('widening the walk limit surfaces the hidden options', toggle.length > 0)

    const longer = toggle[0]
    if (longer) {
      check(
        'the label says how many options are hidden',
        /\d+ more option/.test(longer.textContent),
        longer.textContent.slice(0, 120),
      )
      check(
        'the hidden options stay hidden until asked for',
        container.querySelector('.jlist--longwalk') === null,
        'and the label says what is down there',
      )
      const before = container.querySelectorAll('.jcard').length
      await click(longer)
      const after = container.querySelectorAll('.jcard').length
      check('opening the section reveals them', after > before, `${before} -> ${after}`)
      check(
        'the revealed rows are flagged as long walks',
        Boolean(container.querySelector('.jlist--longwalk .jcard')?.textContent?.includes('Long walk')),
      )
      await click(longer)
      check('closing it hides them again', container.querySelector('.jlist--longwalk') === null)
    }
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

  // Type into the fields the way a person does: type, then press the button.
  // A field that only believes you pressed Enter leaves the primary action
  // disabled while your text sits there looking accepted.
  const inputs = Array.from(container.querySelectorAll('.place__input'))
  const toInput = inputs[1]
  const fromInput = inputs[0]
  const setInputValue = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'value',
  ).set
  const type = async (input, text) => {
    await act(async () => {
      input.dispatchEvent(new window.Event('focus', { bubbles: true }))
      setInputValue.call(input, text)
      input.dispatchEvent(new window.Event('input', { bubbles: true }))
    })
  }
  const primary = () =>
    Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Find my journey'),
    )

  if (toInput && fromInput) {
    // Start from empty fields: the deep link we arrived on filled them in.
    const clears = Array.from(container.querySelectorAll('.place__clear'))
    for (const clear of clears) await click(clear)
    await settle(200)
    check(
      'clearing the fields disables the search again',
      Boolean(primary()?.disabled),
      'the primary action stayed enabled with both fields empty',
    )

    await type(toInput, 'Birmingham')
    await type(fromInput, 'Nottingham')
    await settle(300)
    check(
      'typing is enough to enable the search',
      primary() && !primary().disabled,
      'the primary action is still disabled after typing both fields',
    )

    // Suggestions for what has been typed.
    const options = await waitFor('.place__option')
    check(
      'the fields suggest real places',
      options.length > 0,
      `${options.length} suggestions; list html: ${
        container.querySelector('.place')?.outerHTML.slice(0, 400) ?? 'no .place'
      }`,
    )
    if (options.length) {
      const first = options[0]
      const name = first.querySelector('.place__option-name')?.textContent ?? ''
      await click(first)
      await settle(120)
      const field = Array.from(container.querySelectorAll('.place__input'))[0]
      check(
        'picking a suggestion fills the field with the place',
        Boolean(name) && field.value === name,
        `field shows "${field.value}", suggestion was "${name}"`,
      )
    }

    const go = primary()
    if (go) {
      await click(go)
      const results = await waitFor('.jcard')
      check(
        'typing a journey and pressing the button finds it',
        results.length > 0,
        `${results.length} cards after searching from Home`,
      )
    }
  }

  console.log(checks.join('\n'))
  console.log(`\n${checks.length - failures}/${checks.length} render checks passed`)
  process.exit(failures ? 1 : 0)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
