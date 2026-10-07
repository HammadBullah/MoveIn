import { useState } from 'react'
import { co2, metres, modeColour, modeIcon, minutes } from '../lib/format'
import type { Journey } from '../lib/types'
import { MapView } from './MapView'
import { ModeChain, Pill } from './Primitives'

export function JourneyCard({
  journey,
  onSelect,
  highlighted,
}: {
  journey: Journey
  onSelect: () => void
  highlighted?: boolean
}) {
  return (
    <button
      type="button"
      className={`journey${highlighted ? ' journey--best' : ''}`}
      onClick={onSelect}
      aria-label={`Journey departing ${journey.departure_time}, arriving ${journey.arrival_time}, ${journey.price_label}`}
    >
      <div>
        <div className="journey__times">
          {journey.departure_time}
          <div className="journey__arrow">↓</div>
          {journey.arrival_time}
          {journey.arrival_day_offset > 0 && (
            <span className="tiny muted"> +{journey.arrival_day_offset}d</span>
          )}
        </div>
        <div className="journey__duration">{journey.duration_label}</div>
      </div>

      <div>
        <div className="journey__legs">
          <ModeChain modes={journey.modes} />
          <span className="pill">{journey.changes_label}</span>
          {journey.walking_m > 50 && <Pill tone="navy">🚶 {journey.walking_label}</Pill>}
          {journey.step_free && <Pill tone="teal">♿</Pill>}
          {journey.archetype_labels.slice(0, 2).map((label) => (
            <Pill key={label} tone="teal">
              {label}
            </Pill>
          ))}
        </div>
        <div className="journey__meta">
          {journey.route_label} · {journey.operators.map((o) => o.name).join(', ')} ·{' '}
          {journey.reliability_label} · {co2(journey.co2_g)} CO₂e
        </div>
      </div>

      <div className="journey__price">
        <div className="journey__price-value">{journey.price_label}</div>
        <div className="journey__meta">
          {journey.fare.tickets.length} ticket{journey.fare.tickets.length === 1 ? '' : 's'}
        </div>
      </div>
    </button>
  )
}

/** The cheapest / fastest / greenest summaries above the result list. */
export function ArchetypeRow({
  journeys,
  labels,
  onSelect,
  selectedId,
}: {
  journeys: Journey[]
  labels: Record<string, string>
  onSelect: (journey: Journey) => void
  selectedId?: string
}) {
  const byId = new Map(journeys.map((j) => [j.id, j]))
  const entries = Object.entries(labels)
    .map(([key, id]) => ({ key, journey: byId.get(id) }))
    .filter((entry): entry is { key: string; journey: Journey } => Boolean(entry.journey))

  if (!entries.length) return null

  return (
    <div className="archetype-row">
      {entries.map(({ key, journey }) => (
        <button
          key={key}
          type="button"
          className={`archetype${selectedId === journey.id ? ' archetype--selected' : ''}`}
          onClick={() => onSelect(journey)}
        >
          <div className="archetype__label">
            <span aria-hidden>{archetypeGlyph(key)}</span>
            {humanise(key)}
          </div>
          <div className="archetype__headline">{headlineFor(key, journey)}</div>
          <div className="archetype__sub">{subtitleFor(key, journey)}</div>
        </button>
      ))}
    </div>
  )
}

function archetypeGlyph(key: string): string {
  return (
    {
      cheapest: '£',
      fastest: '⏱',
      best_value: '★',
      fewest_changes: '⇄',
      least_walking: '🚶',
      lowest_emissions: '🌱',
      accessible: '♿',
    }[key] ?? '•'
  )
}

function humanise(key: string): string {
  return (
    {
      cheapest: 'Cheapest',
      fastest: 'Fastest',
      best_value: 'Best value',
      fewest_changes: 'Fewest changes',
      least_walking: 'Least walking',
      lowest_emissions: 'Lowest emissions',
      accessible: 'Step-free',
    }[key] ?? key
  )
}

function headlineFor(key: string, journey: Journey): string {
  switch (key) {
    case 'cheapest':
      return journey.price_label
    case 'fastest':
      return journey.duration_label
    case 'lowest_emissions':
      return co2(journey.co2_g)
    case 'fewest_changes':
      return journey.changes_label
    case 'least_walking':
      return journey.walking_label
    default:
      return `${journey.price_label} · ${journey.duration_label}`
  }
}

function subtitleFor(key: string, journey: Journey): string {
  switch (key) {
    case 'cheapest':
      return `arrives ${journey.arrival_time} · ${journey.duration_label}`
    case 'fastest':
      return `arrives ${journey.arrival_time} · ${journey.price_label}`
    case 'lowest_emissions':
      return `${journey.mode_label} · ${journey.duration_label}`
    case 'fewest_changes':
      return `${journey.duration_label} · ${journey.price_label}`
    case 'least_walking':
      return `${journey.duration_label} · ${journey.price_label}`
    case 'accessible':
      return `${journey.duration_label} · ${journey.price_label}`
    default:
      return `arrives ${journey.arrival_time} · ${journey.price_label}`
  }
}

/** The step-by-step itinerary, with the fare breakdown underneath. */
export function JourneyDetail({
  journey,
  onTrack,
  tracked,
  onSave,
  saved,
}: {
  journey: Journey
  onTrack?: () => void
  tracked?: string | null
  onSave?: () => void
  saved?: boolean
}) {
  const [showAllStops, setShowAllStops] = useState(false)

  return (
    <div className="card card--pad">
      <div className="row row--between" style={{ alignItems: 'flex-start' }}>
        <div>
          <h2 style={{ marginBottom: '0.15rem' }}>
            {journey.departure_time} → {journey.arrival_time}
            {journey.arrival_day_offset > 0 && (
              <span className="muted small"> (+{journey.arrival_day_offset} day)</span>
            )}
          </h2>
          <div className="muted small">
            {journey.duration_label} · {journey.route_label} · {journey.changes_label} ·{' '}
            {journey.walking_label}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '1.6rem', fontWeight: 750 }}>{journey.price_label}</div>
          {onSave && (
            <button className="btn btn--ghost btn--sm" onClick={onSave} disabled={saved}>
              {saved ? '★ Saved' : '☆ Save'}
            </button>
          )}
        </div>
      </div>

      {journey.archetype_labels.length > 0 && (
        <div className="row" style={{ marginTop: '0.6rem' }}>
          {journey.archetype_labels.map((label) => (
            <Pill key={label} tone="teal">
              {label}
            </Pill>
          ))}
        </div>
      )}

      <div style={{ margin: '1rem 0' }}>
        <MapView journey={journey} />
      </div>

      {tracked && (
        <div className="banner banner--info" style={{ marginBottom: '0.9rem' }}>
          <strong>Live: {tracked}</strong>
        </div>
      )}

      <div className="timeline">
        {journey.legs.map((leg, index) => (
          <div className="leg" key={index}>
            <span
              className={`leg__dot${leg.kind === 'transit' ? ' leg__dot--transit' : ''}`}
              aria-hidden
              style={
                leg.kind === 'transit'
                  ? { borderColor: modeColour(leg.mode) }
                  : undefined
              }
            >
              {modeIcon(leg.mode)}
            </span>

            <div className="leg__head">
              <span className="leg__time">
                {leg.kind === 'transit' ? leg.departure : leg.start_time}
              </span>
              <span className="leg__instruction">{leg.instruction}</span>
              {leg.kind === 'transit' && leg.delay_s ? (
                <Pill tone={leg.delay_s > 120 ? 'red' : 'green'}>
                  {leg.delay_s > 0 ? `${Math.round(leg.delay_s / 60)} min late` : 'on time'}
                </Pill>
              ) : null}
            </div>

            <div className="leg__detail">
              {leg.kind === 'transit' ? (
                <>
                  {leg.from.name} → {leg.to.name} · {minutes(leg.duration_s ?? 0)} ·{' '}
                  {leg.distance_km} km · {leg.stops_count} stops · {leg.fare} ·{' '}
                  {leg.operator?.name}
                </>
              ) : (
                <>
                  {metres(leg.distance_m ?? 0)} · {minutes(leg.duration_s ?? 0)}
                  {leg.direction ? ` · head ${leg.direction}` : ''}
                </>
              )}
            </div>

            {leg.kind === 'transit' && (leg.intermediate_stops?.length ?? 0) > 0 && (
              <>
                <button
                  className="btn btn--ghost btn--sm"
                  style={{ marginTop: '0.25rem' }}
                  onClick={() => setShowAllStops((v) => !v)}
                >
                  {showAllStops ? '▾' : '▸'} {leg.intermediate_stops?.length} stops
                </button>
                {showAllStops && (
                  <ul className="stop-list">
                    {leg.intermediate_stops?.map((stop) => (
                      <li key={stop.id}>{stop.name}</li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        ))}
      </div>

      <div className="section-title">Your tickets</div>
      <table className="table">
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Operator</th>
            <th style={{ textAlign: 'right' }}>Price</th>
          </tr>
        </thead>
        <tbody>
          {journey.fare.tickets.map((ticket, index) => (
            <tr key={index}>
              <td>{ticket.label}</td>
              <td>{ticket.operator_name}</td>
              <td style={{ textAlign: 'right' }} className="mono">
                {ticket.price_label}
              </td>
            </tr>
          ))}
          <tr>
            <td colSpan={2}>
              <strong>Total</strong>
            </td>
            <td style={{ textAlign: 'right' }} className="mono">
              <strong>{journey.fare.total_label}</strong>
            </td>
          </tr>
        </tbody>
      </table>

      {journey.fare.saving_vs_singles > 0.01 && (
        <div className="banner banner--info" style={{ marginTop: '0.6rem' }}>
          Buying this combination saves £{journey.fare.saving_vs_singles.toFixed(2)} against
          separate singles.
        </div>
      )}
      {journey.fare.notes.map((note, index) => (
        <div className="banner" style={{ marginTop: '0.6rem' }} key={index}>
          {note}
        </div>
      ))}

      <div className="stat-grid" style={{ marginTop: '1rem' }}>
        <div className="stat">
          <div className="stat__value">{co2(journey.co2_g)}</div>
          <div className="stat__label">CO₂e</div>
        </div>
        <div className="stat">
          <div className="stat__value">{journey.reliability_label}</div>
          <div className="stat__label">Punctuality</div>
        </div>
        <div className="stat">
          <div className="stat__value">{metres(journey.walking_m)}</div>
          <div className="stat__label">Walking</div>
        </div>
        <div className="stat">
          <div className="stat__value">{journey.step_free ? 'Yes' : 'Limited'}</div>
          <div className="stat__label">Step-free</div>
        </div>
      </div>

      {onTrack && (
        <button className="btn btn--teal" style={{ marginTop: '1rem' }} onClick={onTrack}>
          📍 Track this journey
        </button>
      )}
    </div>
  )
}
