import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../lib/api'
import { ArchetypeRow, JourneyCard, JourneyDetail } from '../components/JourneyViews'
import { Banner, Empty, Loading, Pill } from '../components/Primitives'
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
    maxWalk: null,
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
  const [selected, setSelected] = useState<Journey | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tracking, setTracking] = useState<TrackResponse | null>(null)
  const [saved, setSaved] = useState(false)

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
          max_walk_m: search.maxWalk,
        },
        options: { step_free_only: search.stepFree },
        limit: 12,
      })
      setResult(response)
      setSelected(response.journeys[0] ?? null)
      localStorage.setItem(LAST_SEARCH, JSON.stringify(search))
    } catch (cause) {
      setResult(null)
      setSelected(null)
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

  const save = async (journey: Journey) => {
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
    <div className="stack" style={{ gap: '1.25rem' }}>
      <SearchPanel
        values={values}
        onChange={setValues}
        onSubmit={runSearch}
        preferences={preferences}
        busy={busy}
      />

      {error && <Banner kind="error">{error}</Banner>}

      {busy && <Loading rows={4} />}

      {!busy && result && result.journeys.length === 0 && (
        <Empty
          title="No journeys found"
          hint={`MoveIn could not connect ${result.origin.label} and ${result.destination.label}. Try a nearby town or a different time of day.`}
        />
      )}

      {!busy && result && result.journeys.length > 0 && (
        <>
          <div className="row row--between">
            <div>
              <h2 style={{ marginBottom: '0.1rem' }}>
                {result.origin.label} → {result.destination.label}
              </h2>
              <div className="muted small">
                {result.count} options for “{result.preference_label}” ·{' '}
                {result.diagnostics?.search_ms
                  ? `searched in ${result.diagnostics.search_ms} ms`
                  : ''}
              </div>
            </div>
            <div className="row">
              {result.typical?.cheapest && (
                <Pill tone="teal">from {result.typical.cheapest.price_label}</Pill>
              )}
              {result.typical?.fastest && (
                <Pill tone="navy">from {result.typical.fastest.duration_label}</Pill>
              )}
              {result.typical?.lowest_emissions && (
                <Pill tone="green">
                  as low as {result.typical.lowest_emissions.co2_label}
                </Pill>
              )}
            </div>
          </div>

          <ArchetypeRow
            journeys={result.journeys}
            labels={result.archetypes}
            selectedId={selected?.id}
            onSelect={(journey) => setSelected(journey)}
          />

          <div className="stack" style={{ gap: '0.6rem' }}>
            {result.journeys.map((journey) => (
              <JourneyCard
                key={journey.id}
                journey={journey}
                highlighted={journey.id === selected?.id}
                onSelect={() => setSelected(journey)}
              />
            ))}
          </div>

          {selected && (
            <>
              <div className="section-title">Journey detail</div>
              <JourneyDetail
                journey={selected}
                onTrack={() => track(selected)}
                tracked={
                  tracking
                    ? `${tracking.delay_label} · ${tracking.advice}`
                    : null
                }
                onSave={() => save(selected)}
                saved={saved}
              />
            </>
          )}

          {result.nearby_destinations.length > 0 && (
            <>
              <div className="section-title">Try a nearby stop</div>
              <div className="row">
                {result.nearby_destinations.map((stop) => (
                  <button
                    key={stop.id}
                    className="btn btn--sm"
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
            </>
          )}
        </>
      )}
    </div>
  )
}
