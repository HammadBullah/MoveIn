import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, api } from '../lib/api'
import { JourneyDetail, QuickPicks, RideRow } from '../components/JourneyViews'
import { Banner, Empty, Loading } from '../components/Primitives'
import { SearchPanel, type SearchValues } from '../components/SearchPanel'
import type { Journey, Preference, SearchResponse, TrackResponse } from '../lib/types'

const LAST_SEARCH = 'movein.lastSearch'

function loadLastSearch(): SearchValues {
  try {
    const raw = localStorage.getItem(LAST_SEARCH)
    if (raw) return { ...defaults(), ...(JSON.parse(raw) as SearchValues) }
  } catch {
    /* fall through to the defaults */
  }
  return defaults()
}

function defaults(): SearchValues {
  return {
    origin: 'Nottingham',
    destination: 'Birmingham',
    departure: null,
    preference: 'best_value',
    stepFree: false,
    railcard: false,
    student: false,
    // Fifteen minutes is the point at which a walk stops being a stroll, so
    // that is the promise MoveIn makes unless the traveller says otherwise.
    maxWalkMinutes: 15,
  }
}

export function PlanPage({
  initial,
  onInitialConsumed,
}: {
  initial?: { origin: string; destination: string } | null
  onInitialConsumed?: () => void
}) {
  const [values, setValues] = useState<SearchValues>(() =>
    initial ? { ...loadLastSearch(), ...initial } : loadLastSearch(),
  )
  const [preferences, setPreferences] = useState<Preference[]>([])
  const [result, setResult] = useState<SearchResponse | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tracking, setTracking] = useState<TrackResponse | null>(null)
  const [saved, setSaved] = useState(false)
  const [showLongWalks, setShowLongWalks] = useState(false)

  useEffect(() => {
    api
      .preferences()
      .then((data) => setPreferences(data.preferences))
      .catch(() => setPreferences([]))
  }, [])

  const runSearch = useCallback(async (search: SearchValues) => {
    setBusy(true)
    setError(null)
    setTracking(null)
    setSaved(false)
    try {
      const response = await api.search({
        origin: search.origin,
        destination: search.destination,
        departure: search.departure,
        preference: search.preference,
        traveller: {
          adults: 1,
          children: 0,
          railcard: search.railcard,
          student: search.student,
          step_free: search.stepFree,
        },
        options: {},
        max_walk_minutes: search.maxWalkMinutes,
        limit: 12,
      })
      setResult(response)
      setSelectedId(response.journeys[0]?.id ?? null)
      localStorage.setItem(LAST_SEARCH, JSON.stringify(search))
    } catch (cause) {
      setResult(null)
      setSelectedId(null)
      setError(
        cause instanceof ApiError
          ? cause.message
          : 'Something went wrong planning that journey.',
      )
    } finally {
      setBusy(false)
    }
  }, [])

  // Plan something immediately, so the page is never empty on first load.
  useEffect(() => {
    void runSearch(initial ? { ...values, ...initial } : values)
    if (initial) onInitialConsumed?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const journeys = result?.journeys ?? []
  const { doable, longWalk } = useMemo(() => {
    const doable: Journey[] = []
    const longWalk: Journey[] = []
    for (const journey of journeys) {
      if (journey.walk_warning) longWalk.push(journey)
      else doable.push(journey)
    }
    return { doable, longWalk }
  }, [journeys])

  const selected = journeys.find((journey) => journey.id === selectedId) ?? null

  const track = async (journey: Journey) => {
    try {
      const response = await api.track({
        journey_id: journey.id,
        payload: journey,
        preference: values.preference,
      })
      setTracking(response)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not start tracking.')
    }
  }

  const save = async () => {
    if (!result) return
    try {
      await api.save({
        origin: result.origin.label,
        destination: result.destination.label,
        preference: values.preference,
        label: `${result.origin.label} → ${result.destination.label}`,
      })
      setSaved(true)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not save that journey.')
    }
  }

  return (
    <div className="planner">
      <aside className="planner__panel">
        <SearchPanel
          values={values}
          onChange={setValues}
          onSubmit={runSearch}
          preferences={preferences}
          busy={busy}
        />

        {error && <Banner kind="error">{error}</Banner>}

        {busy && <Loading rows={4} />}

        {!busy && result && journeys.length === 0 && (
          <Empty
            title="No journeys found"
            hint={`MoveIn could not connect ${result.origin.label} and ${result.destination.label}. Try a nearby town, a different time of day, or allow a longer walk.`}
          />
        )}

        {!busy && result && journeys.length > 0 && (
          <div className="options">
            <div className="options__head">
              <div>
                <strong>
                  {result.origin.label} → {result.destination.label}
                </strong>
                <div className="tiny muted">
                  {result.count} options · {result.preference_label}
                  {result.diagnostics?.search_ms
                    ? ` · ${result.diagnostics.search_ms} ms`
                    : ''}
                </div>
              </div>
              {result.typical?.cheapest && (
                <div className="options__from">
                  from <strong>{result.typical.cheapest.price_label}</strong>
                </div>
              )}
            </div>

            {result.notice && (
              <div className="banner banner--warn">{result.notice.message}</div>
            )}

            <QuickPicks
              journeys={journeys}
              labels={result.archetypes}
              selectedId={selectedId ?? undefined}
              onSelect={(journey) => setSelectedId(journey.id)}
            />

            {doable.map((journey) => (
              <RideRow
                key={journey.id}
                journey={journey}
                selected={journey.id === selectedId}
                onSelect={() => setSelectedId(journey.id)}
              />
            ))}

            {longWalk.length > 0 && (
              <>
                <button
                  type="button"
                  className="options__more"
                  aria-expanded={showLongWalks}
                  onClick={() => setShowLongWalks((v) => !v)}
                >
                  {showLongWalks ? '▾' : '▸'} Shorter walks only, or {longWalk.length}{' '}
                  more option{longWalk.length === 1 ? '' : 's'} with a longer walk
                  <span className="tiny muted">
                    the cheapest of these is {cheapestOf(longWalk)}
                  </span>
                </button>
                {showLongWalks &&
                  longWalk.map((journey) => (
                    <RideRow
                      key={journey.id}
                      journey={journey}
                      selected={journey.id === selectedId}
                      onSelect={() => setSelectedId(journey.id)}
                    />
                  ))}
              </>
            )}

            {result.nearby_destinations.length > 0 && (
              <div className="options__nearby">
                <span className="tiny muted">Try a nearby stop</span>
                <div className="chip-row chip-row--scroll">
                  {result.nearby_destinations.map((stop) => (
                    <button
                      key={stop.id}
                      className="chip"
                      onClick={() => {
                        const next = { ...values, destination: stop.name }
                        setValues(next)
                        void runSearch(next)
                      }}
                    >
                      {stop.name} · {Math.round((stop.distance_m ?? 0) / 100) * 100} m
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </aside>

      <section className="planner__detail">
        {selected ? (
          <JourneyDetail
            journey={selected}
            originLabel={result?.origin.label}
            destinationLabel={result?.destination.label}
            onTrack={selected.is_walk_only ? undefined : () => track(selected)}
            tracked={tracking ? `${tracking.delay_label} · ${tracking.advice}` : null}
            onSave={save}
            saved={saved}
          />
        ) : (
          <div className="planner__placeholder card card--pad">
            <strong>Pick an option</strong>
            <p className="muted small" style={{ marginBottom: 0 }}>
              MoveIn returns the trade-offs rather than one answer: the cheapest is
              rarely the fastest, and the one that keeps you driest is rarely either.
              Choose a row to see the step-by-step version and what you would buy.
            </p>
          </div>
        )}
      </section>
    </div>
  )
}

function cheapestOf(journeys: Journey[]): string {
  return journeys.reduce((best, journey) =>
    journey.price < best.price ? journey : best,
  ).price_label
}
