import { useEffect, useState } from 'react'
import { Button, Chip, Field, Row, Section, Segmented } from '../components/Controls'
import { Icon } from '../components/Icons'
import { MapCanvas } from '../components/MapCanvas'
import { api } from '../lib/api'
import type { RealBusBetween, RealBusCoverage, RealBusRouteDetail, RealBusRouteSummary } from '../lib/types'

type Tab = 'routes' | 'between'

/**
 * The real bus network.
 *
 * Everything here comes from what bus operators publish about their own
 * services: the route number, the operator, the stops it calls at in order, and
 * the shape it drives. What it does not have is times — a published route shape
 * is not a timetable — so this screen never shows a departure time, and says so
 * once, plainly, instead.
 *
 * Two questions, side by side: *which routes are there* (browse and search the
 * whole set) and *what runs between these two places* (the corridor answer,
 * with the stop to board at).
 */
export function BusScreen({ onBack, from, to }: { onBack: () => void; from?: string; to?: string }) {
  const [tab, setTab] = useState<Tab>('routes')
  const [coverage, setCoverage] = useState<RealBusCoverage | null>(null)
  const [routes, setRoutes] = useState<RealBusRouteSummary[]>([])
  const [total, setTotal] = useState(0)
  const [operator, setOperator] = useState<string>('')
  const [query, setQuery] = useState('')
  const [detail, setDetail] = useState<RealBusRouteDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [origin, setOrigin] = useState(from || 'Coventry')
  const [destination, setDestination] = useState(to || 'Leicester')
  const [between, setBetween] = useState<RealBusBetween | null>(null)
  const [betweenError, setBetweenError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .realBusCoverage()
      .then(setCoverage)
      .catch(() => setError('The API is not reachable, so the bus network cannot be shown.'))
  }, [])

  useEffect(() => {
    let cancelled = false
    const timer = window.setTimeout(
      () => {
        api
          .realBusRoutes({
            operator: operator || undefined,
            q: query || undefined,
            limit: 60,
          })
          .then((response) => {
            if (cancelled) return
            setRoutes(response.routes)
            setTotal(response.count)
          })
          .catch(() => {
            if (!cancelled) setError('The bus network could not be read.')
          })
      },
      query ? 180 : 0,
    )
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [operator, query])

  function askBetween() {
    setBusy(true)
    setBetweenError(null)
    api
      .realBusBetween(origin, destination)
      .then(setBetween)
      .catch(() => {
        setBetween(null)
        setBetweenError('One of those places could not be resolved to a real stop.')
      })
      .finally(() => setBusy(false))
  }

  return (
    <div className="screen screen--bus">
      <header className="detail__head">
        <button type="button" className="icon-btn" onClick={onBack} aria-label="Back">
          <Icon name="back" size={20} />
        </button>
        <span className="detail__route">UK bus routes</span>
        <span className="detail__spacer" />
      </header>

      {error && (
        <div className="notice notice--error">
          <Icon name="alert" size={16} />
          <span>{error}</span>
        </div>
      )}

      {coverage && (
        <div className="bus__banner">
          <strong>
            {coverage.routes} real routes · {coverage.services} services · {coverage.operators} operators
          </strong>
          <span className="muted tiny">
            {coverage.named_stops} named stops, straight from the operators' own published data.{' '}
            {coverage.routes_with_times
              ? `${coverage.routes_with_times} of these routes also carry the departure times the ` +
                `operator published for one representative trip.`
              : 'No departure times in this layer — timetables are compiled separately, and the planning ' +
                'engine uses those.'}
          </span>
        </div>
      )}

      <Segmented<Tab>
        value={tab}
        onChange={setTab}
        options={[
          { value: 'routes', label: 'Routes' },
          { value: 'between', label: 'Between places' },
        ]}
      />

      {tab === 'routes' && (
        <>
          <Section title="Find a route">
            <Field
              label="Route number, town or operator"
              value={query}
              onChange={setQuery}
              placeholder="148, Leicester, Stagecoach…"
            />
            <div className="bus__chips">
              <Chip active={operator === ''} onClick={() => setOperator('')}>
                All operators
              </Chip>
              {coverage?.operator_names.map((name) => (
                <Chip key={name} active={operator === name} onClick={() => setOperator(name)}>
                  {name}
                </Chip>
              ))}
            </div>
          </Section>

          <p className="muted tiny bus__count">
            Showing {routes.length} of {total} routes
            {operator ? ` for ${operator}` : ''}
          </p>

          <ul className="bus__list">
            {routes.map((route) => (
              <li key={route.id}>
                <button
                  type="button"
                  className={`bus__row${detail?.id === route.id ? ' bus__row--on' : ''}`}
                  onClick={() =>
                    api
                      .realBusRoute(route.id)
                      .then(setDetail)
                      .catch(() => setError('That route could not be read.'))
                  }
                >
                  <span className="bus__number">{route.number || '—'}</span>
                  <span className="bus__body">
                    <strong>{route.from}</strong>
                    <em>
                      <Icon name="pin" size={11} /> to {route.to}
                    </em>
                    <span className="muted tiny">
                      {route.operator} · {route.stop_count} stops
                      {route.description ? ` · ${route.description}` : ''}
                    </span>
                    {route.first_time ? (
                      <span className="bus__times tiny">
                        <Icon name="clock" size={11} /> {route.first_time} → {route.last_time}
                      </span>
                    ) : null}
                  </span>
                  <Icon name="back" size={16} />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {tab === 'between' && (
        <>
          <Section title="Which buses run between two places?">
            <Field label="From" value={origin} onChange={setOrigin} placeholder="Coventry" />
            <Field label="To" value={destination} onChange={setDestination} placeholder="Leicester" />
            <Button onClick={askBetween} disabled={busy}>
              {busy ? 'Looking…' : 'Find real services'}
            </Button>
          </Section>

          {betweenError && (
            <div className="notice notice--error">
              <Icon name="alert" size={16} />
              <span>{betweenError}</span>
            </div>
          )}

          {between && (
            <>
              <p className="muted tiny bus__count">
                {between.count === 0
                  ? `No published service links ${between.origin.label} and ${between.destination.label} in the data MoveIn holds.`
                  : `${between.count} service${between.count === 1 ? '' : 's'} between ${between.origin.label} and ${between.destination.label}`}
              </p>
              <ul className="bus__options">
                {between.options.map((option) => (
                  <li key={option.route_id} className="card card--pad bus__option">
                    <div className="bus__option-head">
                      <span className="bus__number bus__number--lg">{option.number}</span>
                      <span className="bus__body">
                        <strong>{option.operator}</strong>
                        <span className="muted tiny">{option.description}</span>
                      </span>
                      <span className="bus__stops">{option.stops_travelled} stops</span>
                    </div>
                    <Row
                      label="Board at"
                      value={
                        option.board.time
                          ? `${option.board.time} · ${option.board.name}`
                          : option.board.name
                      }
                    />
                    <Row
                      label="Get off at"
                      value={
                        option.alight.time
                          ? `${option.alight.time} · ${option.alight.name}`
                          : option.alight.name
                      }
                    />
                    <Row
                      label="Direction"
                      value={
                        option.direction === 'forward'
                          ? 'Published this way round'
                          : 'Same service, published the other way round'
                      }
                    />
                    {option.calls_at.length > 2 && (
                      <p className="muted tiny">
                        Calls at {option.calls_at.slice(1, 6).join(' → ')}
                        {option.calls_at.length > 7
                          ? ` … ${option.calls_at[option.calls_at.length - 2]}`
                          : ''}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}

      {detail && (
        <Section title={`Route ${detail.number} · ${detail.operator}`}>
          <div className="card bus__detail">
            <MapCanvas
              journey={null}
              height={220}
              interactive={false}
              showNetwork={false}
              realBusRoute={{
                shape: detail.shape,
                stops: detail.stops.map((s) => [s.lat, s.lon] as [number, number]),
                label: `Route ${detail.number}`,
              }}
            />
            <div className="card--pad">
              <p className="small">
                {detail.stops.length} stops, {detail.shape_points} shape points
                {detail.description ? ` · ${detail.description}` : ''}
              </p>
              {detail.has_times && (
                <p className="muted tiny bus__times-note">
                  {detail.times_note ||
                    'The times are the schedule the operator published for one representative trip.'}
                </p>
              )}
              <ol className="bus__stops-list">
                {detail.stops.map((stop, index) => (
                  <li key={`${stop.atco}-${index}`}>
                    <span className="bus__stop-dot" aria-hidden />
                    <span className="bus__stop-name">{stop.name}</span>
                    {stop.time ? <span className="bus__stop-time">{stop.time}</span> : null}
                  </li>
                ))}
              </ol>
              <p className="muted tiny">Source: {detail.source || 'operator TransXChange publication'}</p>
            </div>
          </div>
        </Section>
      )}

      {coverage && <p className="muted tiny bus__attribution">{coverage.attribution}</p>}
    </div>
  )
}
