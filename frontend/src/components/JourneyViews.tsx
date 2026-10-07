import { useState } from 'react'
import { co2, metres, modeColour, modeIcon, minutes } from '../lib/format'
import type { Journey } from '../lib/types'
import { MapView } from './MapView'
import { Pill } from './Primitives'

/**
 * One journey, as one row.
 *
 * The row is the unit of decision, so it carries only what a person compares:
 * when they arrive, how long it takes, what it costs, and how far they have to
 * walk. Everything else is behind the tap.
 */
export function RideRow({
  journey,
  selected,
  onSelect,
}: {
  journey: Journey
  selected: boolean
  onSelect: () => void
}) {
  const tags = journey.archetype_labels.slice(0, 2)
  return (
    <button
      type="button"
      className={`ride${selected ? ' ride--selected' : ''}${
        journey.walk_warning ? ' ride--walking' : ''
      }`}
      onClick={onSelect}
      aria-expanded={selected}
      aria-label={`${journey.departure_time} to ${journey.arrival_time}, ${journey.duration_label}, ${journey.price_label}`}
    >
      <span className="ride__rail" aria-hidden>
        {journey.modes.slice(0, 3).map((mode, index) => (
          <span
            key={`${mode}-${index}`}
            className="ride__mode"
            style={{
              background: `${modeColour(mode)}1f`,
              borderColor: `${modeColour(mode)}66`,
              color: modeColour(mode),
            }}
          >
            {modeIcon(mode)}
          </span>
        ))}
        {journey.is_walk_only && <span className="ride__mode">🚶</span>}
      </span>

      <span className="ride__body">
        <span className="ride__times">
          <strong>{journey.arrival_time}</strong>
          <span className="ride__duration">{journey.duration_label}</span>
        </span>
        <span className="ride__meta">
          {journey.departure_time} · {journey.route_label} ·{' '}
          {journey.changes === 0 ? 'direct' : journey.changes_label}
        </span>
        <span className="ride__tags">
          {journey.walk_warning && (
            <Pill tone="amber">🚶 {journey.longest_walk_label}</Pill>
          )}
          {!journey.walk_warning && journey.walking_m > 50 && (
            <span className="tag tag--quiet">🚶 {journey.longest_walk_label}</span>
          )}
          {journey.step_free && <span className="tag tag--quiet">♿ step-free</span>}
          <span className="tag tag--quiet">{journey.reliability_label}</span>
          {tags.map((label) => (
            <span className="tag tag--win" key={label}>
              {label}
            </span>
          ))}
        </span>
      </span>

      <span className="ride__price">
        <strong>{journey.price_label}</strong>
        <span className="tiny muted">
          {journey.fare.tickets.length} ticket
          {journey.fare.tickets.length === 1 ? '' : 's'}
        </span>
      </span>
    </button>
  )
}

/** The quick picks: the trade-offs, as a strip of one-tap shortcuts. */
export function QuickPicks({
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
    <div className="quick-picks">
      {entries.map(({ key, journey }) => (
        <button
          key={key}
          type="button"
          className={`quick-pick${selectedId === journey.id ? ' quick-pick--on' : ''}`}
          onClick={() => onSelect(journey)}
        >
          <span className="quick-pick__icon" aria-hidden>
            {archetypeGlyph(key)}
          </span>
          <span>
            <span className="quick-pick__label">{humanise(key)}</span>
            <span className="quick-pick__value">{headlineFor(key, journey)}</span>
          </span>
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
      return journey.longest_walk_label
    default:
      return `${journey.price_label} · ${journey.duration_label}`
  }
}

/**
 * The chosen journey, opened out: the step-by-step itinerary, where you walk,
 * and what you are buying.
 */
export function JourneyDetail({
  journey,
  onTrack,
  tracked,
  onSave,
  saved,
  originLabel,
  destinationLabel,
}: {
  journey: Journey
  onTrack?: () => void
  tracked?: string | null
  onSave?: () => void
  saved?: boolean
  originLabel?: string
  destinationLabel?: string
}) {
  const [showAllStops, setShowAllStops] = useState(false)

  return (
    <div className="detail">
      <div className="detail__head">
        <div>
          <div className="detail__times">
            {journey.departure_time} → {journey.arrival_time}
            {journey.arrival_day_offset > 0 && (
              <span className="muted small"> +{journey.arrival_day_offset}d</span>
            )}
          </div>
          <div className="muted small">
            {journey.duration_label} · {journey.route_label} · {journey.changes_label}
          </div>
        </div>
        <div className="detail__price">
          <strong>{journey.price_label}</strong>
          {onSave && (
            <button className="btn btn--ghost btn--sm" onClick={onSave} disabled={saved}>
              {saved ? '★ Saved' : '☆ Save'}
            </button>
          )}
        </div>
      </div>

      {journey.walk_warning ? (
        <div className="banner banner--warn">
          <strong>This one needs a {journey.longest_walk_label}.</strong> The other
          options on this page keep you closer to a stop — this is here because you
          asked to see it, not because MoveIn recommends it.
        </div>
      ) : (
        <div className="banner banner--info">
          Walking: {metres(journey.walking_m)} in total, {journey.longest_walk_label} in
          one go.
        </div>
      )}

      <MapView journey={journey} />

      {tracked && (
        <div className="banner banner--info">
          <strong>Live: {tracked}</strong>
        </div>
      )}

      <div className="timeline">
        {journey.legs.map((leg, index) => (
          <div className="leg" key={index}>
            <span
              className={`leg__dot${leg.kind === 'transit' ? ' leg__dot--transit' : ''}`}
              aria-hidden
              style={leg.kind === 'transit' ? { borderColor: modeColour(leg.mode) } : undefined}
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
                  {leg.stops_count} stops · {leg.fare} · {leg.operator?.name}
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
                  onClick={() => setShowAllStops((v) => !v)}
                >
                  {showAllStops ? '▾' : '▸'} {leg.stops_count} stops
                </button>
                {showAllStops && (
                  <ul className="stop-list">
                    <li>
                      <strong>{leg.from.name}</strong>
                    </li>
                    {leg.intermediate_stops?.map((stop) => (
                      <li key={stop.id}>{stop.name}</li>
                    ))}
                    <li>
                      <strong>{leg.to.name}</strong>
                    </li>
                  </ul>
                )}
              </>
            )}
          </div>
        ))}

        <div className="leg leg--end">
          <span className="leg__dot leg__dot--end" aria-hidden>
            ◎
          </span>
          <div className="leg__head">
            <span className="leg__time">{journey.arrival_time}</span>
            <span className="leg__instruction">
              Arrive {destinationLabel ?? journey.legs.at(-1)?.to.name}
            </span>
          </div>
          {originLabel && (
            <div className="leg__detail">
              Left {originLabel} at {journey.departure_time}
            </div>
          )}
        </div>
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
              <td>
                {ticket.label}
                <div className="tiny muted">
                  covers leg{ticket.covers_legs.length === 1 ? '' : 's'}{' '}
                  {ticket.covers_legs.map((i) => i + 1).join(', ')}
                </div>
              </td>
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
        <div className="banner banner--info">
          Buying this combination saves £{journey.fare.saving_vs_singles.toFixed(2)} against
          separate singles.
        </div>
      )}
      {journey.fare.notes.map((note, index) => (
        <div className="banner" key={index}>
          {note}
        </div>
      ))}

      <div className="stat-grid">
        <div className="stat">
          <div className="stat__value">{co2(journey.co2_g)}</div>
          <div className="stat__label">CO₂e</div>
        </div>
        <div className="stat">
          <div className="stat__value">{journey.reliability_label}</div>
          <div className="stat__label">Punctuality</div>
        </div>
        <div className="stat">
          <div className="stat__value">{journey.longest_walk_label}</div>
          <div className="stat__label">Longest walk</div>
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
