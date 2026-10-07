import { useMemo } from 'react'
import { Button, Chip, Sheet } from '../components/Controls'
import { Icon } from '../components/Icons'
import { JourneyCard } from '../components/JourneyCards'
import { MapCanvas } from '../components/MapCanvas'
import { bigDuration, clock, explainBestValue, money, whenLabel } from '../lib/format'
import type { Journey, SearchResponse } from '../lib/types'

const CHIPS = [
  { id: 'best_value', label: 'Recommended', icon: 'star' },
  { id: 'cheapest', label: 'Cheapest', icon: 'coin' },
  { id: 'fastest', label: 'Fastest', icon: 'bolt' },
  { id: 'fewest_changes', label: 'Fewest changes', icon: 'changes' },
]

export function ResultsScreen({
  result,
  loading,
  error,
  fromLabel,
  toLabel,
  when,
  preference,
  sheetHeight,
  longWalkCount,
  onPreference,
  onSheetHeight,
  onBack,
  onOpenJourney,
  onCompare,
  onFilters,
  onRetry,
}: {
  result: SearchResponse | null
  loading: boolean
  error: string | null
  fromLabel: string
  toLabel: string
  when: string
  preference: string
  sheetHeight: 'half' | 'full'
  longWalkCount: number
  onPreference: (next: string) => void
  onSheetHeight: (next: 'half' | 'full') => void
  onBack: () => void
  onOpenJourney: (journey: Journey) => void
  onCompare: () => void
  onFilters: () => void
  onRetry: () => void
}) {
  const journeys = result?.journeys ?? []
  const cheapest = useMemo(
    () => journeys.reduce<Journey | null>((best, j) => (!best || j.price < best.price ? j : best), null),
    [journeys],
  )
  const bestValue = useMemo(
    () => journeys.find((j) => j.archetypes?.includes('best_value')) ?? null,
    [journeys],
  )
  const fastest = useMemo(
    () => journeys.reduce<Journey | null>((best, j) => (!best || j.duration_s < best.duration_s ? j : best), null),
    [journeys],
  )
  const savings = cheapest && fastest ? fastest.price - cheapest.price : 0
  const valueLine =
    bestValue && cheapest && bestValue.id !== cheapest.id
      ? explainBestValue(bestValue, cheapest)
      : null

  return (
    <div className="screen screen--results">
      <div className="results__map">
        <MapCanvas journey={journeys[0] ?? null} height={sheetHeight === 'full' ? 200 : 320} />
        <button type="button" className="map__back" onClick={onBack} aria-label="Back">
          <Icon name="back" size={20} />
        </button>
        <div className="results__map-actions">
          <button type="button" className="map__chip" onClick={onFilters}>
            <Icon name="filter" size={16} />
            Filters
          </button>
        </div>
      </div>

      <Sheet
        height={sheetHeight}
        onHeightChange={onSheetHeight}
        header={
          <div className="results__head">
            <div className="results__route">
              <strong>
                {fromLabel} → {toLabel}
              </strong>
              <span>
                {whenLabel(when === 'now' ? new Date().toISOString() : when)} ·{' '}
                {loading ? 'searching…' : `${journeys.length} options`}
              </span>
            </div>
          </div>
        }
      >
        <div className="chips chips--scroll">
          {CHIPS.map((chip) => (
            <Chip
              key={chip.id}
              icon={chip.icon}
              active={preference === chip.id}
              onClick={() => onPreference(chip.id)}
            >
              {chip.label}
            </Chip>
          ))}
          <Chip icon="filter" onClick={onFilters}>
            More
          </Chip>
        </div>

        {result?.notice && (
          <div className="notice">
            <Icon name="info" size={16} />
            <span>{result.notice.message}</span>
          </div>
        )}

        {error && (
          <div className="notice notice--error">
            <Icon name="alert" size={16} />
            <span>{error}</span>
            <Button size="sm" variant="quiet" onClick={onRetry}>
              Retry
            </Button>
          </div>
        )}

        {loading && (
          <div className="loading">
            <div className="loading__route" aria-hidden>
              <span className="loading__dot" />
              <span className="loading__line" />
              <span className="loading__dot" />
            </div>
            <p>Working out your options…</p>
          </div>
        )}

        {!loading && journeys.length === 0 && !error && (
          <div className="empty">
            <Icon name="map" size={26} />
            <h3>No journeys found</h3>
            <p className="muted small">
              Nothing connects these two places with the current filters. Try a nearby town,
              another departure time, or loosen the filters.
            </p>
            <Button variant="quiet" onClick={onFilters} icon="filter">
              Change filters
            </Button>
          </div>
        )}

        {!loading && journeys.length > 0 && (
          <>
            {savings > 1 && cheapest && fastest && (
              <button type="button" className="saving" onClick={onCompare}>
                <Icon name="wallet" size={16} />
                <span>
                  Take the {cheapest.mode_label.toLowerCase()} and save {money(savings)} — you’d
                  arrive {bigDuration(cheapest.duration_s - fastest.duration_s)} later
                </span>
                <Icon name="chevron" size={16} />
              </button>
            )}

            {valueLine && (
              <p className="results__value">
                <Icon name="star" size={14} /> {valueLine}
              </p>
            )}

            <div className="jlist">
              {journeys.map((journey) => (
                <JourneyCard
                  key={journey.id}
                  journey={journey}
                  cheapestPrice={cheapest?.price}
                  onOpen={() => onOpenJourney(journey)}
                  onCompare={onCompare}
                />
              ))}
            </div>

            {longWalkCount > 0 && (
              <p className="results__longwalk">
                <Icon name="walk" size={14} />
                {longWalkCount} of these include a walk of more than 15 minutes.
              </p>
            )}

            <div className="results__footer">
              <Button variant="quiet" full icon="wallet" onClick={onCompare}>
                Compare all prices
              </Button>
              <p className="muted tiny">
                Prices are the fares MoveIn can compute from published tickets; a walk-up fare
                can differ. Last checked {clock(new Date().toISOString())}.
              </p>
            </div>
          </>
        )}
      </Sheet>
    </div>
  )
}
