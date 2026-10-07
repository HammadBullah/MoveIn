import { modeColour, modeLabel, archetypeMeta, bigDuration, clock, duration, metres, money } from '../lib/format'
import type { Journey, Leg } from '../lib/types'
import { Icon, ModeIcon } from './Icons'

/** The arrow-separated row of modes that tells you how you would get there. */
export function ModeTrail({ legs, showLabels = false }: { legs: Leg[]; showLabels?: boolean }) {
  const transit = legs.filter((leg) => leg.kind !== 'walk' || legs.length === 1)
  return (
    <span className="trail">
      {transit.map((leg, index) => (
        <span key={index} className="trail__item">
          {index > 0 && <span className="trail__arrow">→</span>}
          <span className="trail__icon" style={{ color: modeColour(leg.mode) }}>
            <ModeIcon mode={leg.mode} size={18} />
          </span>
          {showLabels && (
            <span className="trail__label">
              {leg.kind === 'transit' ? leg.route_name || modeLabel(leg.mode) : modeLabel(leg.mode)}
            </span>
          )}
        </span>
      ))}
    </span>
  )
}

export function Badge({ kind, label }: { kind: string; label?: string }) {
  const meta = archetypeMeta(kind)
  return (
    <span className={`badge badge--${meta.tone}`}>
      <Icon name={meta.icon} size={13} />
      {label ?? meta.label}
    </span>
  )
}

/**
 * One journey, as a traveller decides between them.
 *
 * Price and duration are the two numbers that answer "should I?"; everything
 * else on the card exists to explain them.  The badges are the trade-offs the
 * engine found, and the card only wears one: the best of them.
 */
export function JourneyCard({
  journey,
  cheapestPrice,
  onOpen,
  onCompare,
  onSelect,
  expanded = false,
  selected = false,
}: {
  journey: Journey
  cheapestPrice?: number
  onOpen: () => void
  onCompare?: () => void
  /** Tapping the card shows it on the map. */
  onSelect?: () => void
  expanded?: boolean
  selected?: boolean
}) {
  const badge = pickBadge(journey)
  const operators = journey.operators?.map((op) => op.name).filter(Boolean) ?? []
  const saving =
    cheapestPrice !== undefined && cheapestPrice < journey.price
      ? journey.price - cheapestPrice
      : null

  return (
    <article
      className={`jcard${expanded ? ' jcard--open' : ''}${selected ? ' jcard--selected' : ''}`}
      data-journey={journey.id}
      onClick={onSelect}
    >
      <header className="jcard__top">
        <span className="jcard__badges">
          {badge && <Badge kind={badge} />}
          {!badge && journey.is_walk_only && <Badge kind="least_walking" label="Walk only" />}
        </span>
        <span className="jcard__price">
          <strong>{money(journey.price)}</strong>
          {saving !== null && <em className="jcard__saving">+{money(saving)}</em>}
        </span>
      </header>

      <div className="jcard__middle">
        <ModeTrail legs={journey.legs} />
        <span className="jcard__duration">{bigDuration(journey.duration_s)}</span>
      </div>

      <div className="jcard__times">
        <span>{clock(journey.departure_time)}</span>
        <span className="jcard__rule" aria-hidden>
          <span className="jcard__dot" />
          <span className="jcard__line" />
          <span className="jcard__dot" />
        </span>
        <span>
          {clock(journey.arrival_time)}
          {journey.arrival_day_offset > 0 && <sup>+{journey.arrival_day_offset}</sup>}
        </span>
      </div>

      <ul className="jcard__facts">
        <li>
          <Icon name="changes" size={14} />
          {journey.changes === 0 ? 'No changes' : `${journey.changes} change${journey.changes > 1 ? 's' : ''}`}
        </li>
        <li>
          <Icon name="walk" size={14} />
          {journey.walking_m ? `${journey.longest_walk_label}` : 'no walking'}
        </li>
        {operators.length > 0 && (
          <li>
            <Icon name="layers" size={14} />
            {operators.slice(0, 2).join(' · ')}
          </li>
        )}
        <li className={journey.walk_comfort === 'long' ? 'jcard__fact--warn' : ''}>
          <Icon name={journey.walk_comfort === 'long' ? 'alert' : 'leaf'} size={14} />
          {journey.walk_comfort === 'long' ? 'Long walk' : journey.co2_label}
        </li>
      </ul>

      {expanded && (
        <div className="jcard__expand">
          <ul className="jcard__stages">
            {journey.legs.map((leg, index) => (
              <li key={index}>
                <span className="jcard__stage-icon" style={{ color: modeColour(leg.mode) }}>
                  <ModeIcon mode={leg.mode} size={16} />
                </span>
                <span className="jcard__stage-text">
                  {leg.kind === 'walk'
                    ? `Walk ${metres(leg.distance_m ?? 0)}`
                    : `${leg.route_name ?? modeLabel(leg.mode)}${leg.headsign ? ` → ${leg.headsign}` : ''}`}
                </span>
                <span className="jcard__stage-time">
                  {leg.kind === 'walk' ? clock(leg.start_time) : clock(leg.departure)}
                </span>
              </li>
            ))}
          </ul>
          <div className="jcard__actions">
            <button type="button" className="btn btn--primary btn--sm" onClick={onOpen}>
              View journey
            </button>
            {onCompare && (
              <button type="button" className="btn btn--quiet btn--sm" onClick={onCompare}>
                Compare prices
              </button>
            )}
          </div>
        </div>
      )}

      {!expanded && (
        <footer className="jcard__footer">
          <span className="jcard__summary">{journey.summary}</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onOpen}>
            View journey
          </button>
        </footer>
      )}
    </article>
  )
}

function pickBadge(journey: Journey): string | null {
  const order = ['best_value', 'cheapest', 'fastest', 'fewest_changes', 'least_walking', 'lowest_emissions', 'accessible']
  for (const key of order) {
    if (journey.archetypes?.includes(key)) return key
  }
  return null
}

/**
 * The journey as a timeline: one numbered stage per leg, on one line.
 *
 * This is the screen that has to answer "how do I get there" without the
 * traveller needing to understand the network, so every stage carries its own
 * time, place and vehicle, and any wait between stages is printed as its own
 * fact rather than hidden inside a duration.
 */
export function Timeline({ journey }: { journey: Journey }) {
  return (
    <ol className="timeline">
      {journey.legs.map((leg, index) => {
        const next = journey.legs[index + 1]
        const wait = next ? transferSeconds(leg, next) : 0
        return (
          <li key={index} className="timeline__stage">
            <span className="timeline__rail" aria-hidden>
              <span className="timeline__dot" style={{ borderColor: modeColour(leg.mode) }}>
                <span className="timeline__index">{index + 1}</span>
              </span>
              {index < journey.legs.length - 1 && <span className="timeline__line" />}
            </span>

            <div className="timeline__body">
              <div className="timeline__head">
                <span className="timeline__mode" style={{ color: modeColour(leg.mode) }}>
                  <ModeIcon mode={leg.mode} size={18} />
                </span>
                <span className="timeline__title">
                  {leg.kind === 'transit'
                    ? `${leg.route_name ?? modeLabel(leg.mode)}${leg.headsign ? ` to ${leg.headsign}` : ''}`
                    : leg.kind === 'on_demand'
                      ? modeLabel(leg.mode)
                      : `Walk ${metres(leg.distance_m ?? 0)}`}
                </span>
                <span className="timeline__time">
                  {leg.kind === 'walk' ? clock(leg.start_time) : clock(leg.departure)} –{' '}
                  {leg.kind === 'walk' ? clock(leg.end_time) : clock(leg.arrival)}
                </span>
              </div>

              <div className="timeline__route">
                <span className="timeline__place">{leg.from.name}</span>
                <Icon name="chevron" size={14} className="timeline__arrow" />
                <span className="timeline__place">{leg.to.name}</span>
              </div>

              <ul className="timeline__meta">
                <li>{leg.kind === 'walk' ? duration(leg.duration_s ?? 0) : `${leg.stops_count ?? 0} stops`}</li>
                {leg.operator?.name && <li>{leg.operator.name}</li>}
                {leg.live && <li className="timeline__live">Live</li>}
              </ul>
            </div>

            {wait > 0 && (
              <div className="timeline__wait">
                <Icon name="clock" size={13} />
                {Math.round(wait / 60)} min transfer
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}

function transferSeconds(leg: Leg, next: Leg): number {
  const arriveRaw = leg.kind === 'walk' ? leg.end_time : leg.arrival
  const departRaw = next.kind === 'walk' ? next.start_time : next.departure
  if (!arriveRaw || !departRaw) return 0
  const arrive = Date.parse(arriveRaw)
  const depart = Date.parse(departRaw)
  if (Number.isNaN(arrive) || Number.isNaN(depart)) return 0
  return Math.max(0, (depart - arrive) / 1000)
}
