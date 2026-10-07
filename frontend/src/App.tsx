import { useEffect, useState } from 'react'
import { PlanPage } from './pages/PlanPage'
import { LivePage } from './pages/LivePage'
import { SavedPage } from './pages/SavedPage'
import { DataPage } from './pages/DataPage'

type Route = 'plan' | 'live' | 'saved' | 'data'

const TITLES: Record<Route, string> = {
  plan: 'Plan',
  live: 'Live',
  saved: 'Saved',
  data: 'Data',
}

export default function App() {
  const [route, setRoute] = useState<Route>(() => {
    const hash = window.location.hash.replace('#/', '') as Route
    return hash in TITLES ? hash : 'plan'
  })
  /** A journey handed over from the Saved tab, planned as soon as Plan opens. */
  const [pending, setPending] = useState<{ origin: string; destination: string } | null>(null)

  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.replace('#/', '') as Route
      if (hash in TITLES) setRoute(hash)
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const go = (next: Route) => {
    window.location.hash = `#/${next}`
    setRoute(next)
  }

  return (
    <div className="app">
      <header className="masthead">
        <div className="masthead__inner">
          <button className="brand" onClick={() => go('plan')}>
            <span className="brand__mark" aria-hidden>
              ↗
            </span>
            <span>
              MoveIn
              <br />
              <span className="brand__tag">every mode, one search</span>
            </span>
          </button>
          <nav className="nav" aria-label="Main">
            {(Object.keys(TITLES) as Route[]).map((key) => (
              <button
                key={key}
                className={`nav__link${route === key ? ' nav__link--active' : ''}`}
                onClick={() => go(key)}
              >
                {TITLES[key]}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="main">
        {route === 'plan' && (
          <PlanPage initial={pending} onInitialConsumed={() => setPending(null)} />
        )}
        {route === 'live' && <LivePage />}
        {route === 'saved' && (
          <SavedPage
            onPlan={(origin, destination) => {
              setPending({ origin, destination })
              go('plan')
            }}
          />
        )}
        {route === 'data' && <DataPage />}
      </main>

      <footer className="footer">
        <div className="footer__inner">
          <span>
            MoveIn Phase 1 prototype · bus, coach, rail, tram, metro and on-demand in one
            search
          </span>
          <span>
            Real GB stop and operator data · compiled timetable layer · see the Data tab
          </span>
        </div>
      </footer>
    </div>
  )
}
