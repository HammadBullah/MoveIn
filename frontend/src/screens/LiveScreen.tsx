import { useEffect, useMemo, useState } from 'react'
import { Button, Section } from '../components/Controls'
import { Icon, ModeIcon } from '../components/Icons'
import { MapCanvas } from '../components/MapCanvas'
import { clock, minutesBetween, modeColour, modeLabel, money, secondsOfDay } from '../lib/format'
import { api } from '../lib/api'
import type { Journey, Leg, LiveAlert, TrackResponse } from '../lib/types'

/**
 * How long until a timetable time, in minutes.
 *
 * The times on a journey are wall-clock times on the service day, so the
 * comparison has to be in the same space as the clock on the wall -- parsing
 * them as timestamps yields NaN and a countdown that never appears.
 */
function minutesUntil(value: string | undefined | null, now = secondsOfDay(new Date().toISOString())): number | null {
  const at = secondsOfDay(value)
  if (at === null || now === null) return null
  let delta = at - now
  if (delta < -12 * 3600) delta += 86_400
  return Math.round(delta / 60)
}

/**
 * The screen for once the traveller is on their way.
 *
 * A journey planner normally stops being useful the moment it is followed, so
 * this screen exists to keep being useful: where they are, what happens next,
 * and — when something goes wrong — what the alternatives are, without making
 * them start the search again.
 */
export function LiveScreen({
  journey,
  onBack,
  onSwitch,
  onOpenJourney,
}: {
  journey: Journey
  onBack: () => void
  onSwitch: (journey: Journey) => void
  onOpenJourney: (journey: Journey) => void
}) {
  const [track, setTrack] = useState<TrackResponse | null>(null)
  const [alerts, setAlerts] = useState<LiveAlert[]>([])
  const [alternatives, setAlternatives] = useState<Journey[]>([])
  const [switching, setSwitching] = useState(false)
  const firstLeg: Leg | undefined = journey.legs[0]

  useEffect(() => {
    api
      .track({
        journey_id: journey.id,
        payload: journey,
        preference: 'best_value',
      })
      .then(setTrack)
      .catch(() => setTrack(null))
  }, [journey])

  useEffect(() => {
    api
      .liveAlerts()
      .then((response) => setAlerts(response.alerts))
      .catch(() => setAlerts([]))
  }, [])

  const steps = useMemo(() => {
    const now = secondsOfDay(new Date().toISOString())
    return journey.legs.map((leg, index) => {
      const from = leg.kind === 'walk' ? leg.start_time : leg.departure
      const to = leg.kind === 'walk' ? leg.end_time : leg.arrival
      const start = secondsOfDay(from)
      const end = secondsOfDay(to)
      // Nothing on the journey has a date, so a leg that ends before it starts
      // ended yesterday: it is behind us, not ahead.
      const done = end !== null && now !== null && (end < now || (start !== null && end < start))
      const active = !done && start !== null && now !== null && start <= now
      return {
        index,
        leg,
        done,
        active,
        title:
          leg.kind === 'walk'
            ? `Walk to ${leg.to.name}`
            : leg.kind === 'on_demand'
              ? `${modeLabel(leg.mode)} to ${leg.to.name}`
              : `Board ${leg.route_name ?? modeLabel(leg.mode)}`,
        detail:
          leg.kind === 'walk'
            ? `${Math.round((leg.distance_m ?? 0) / 10) * 10} m`
            : `${leg.from.name} → ${leg.to.name}`,
      }
    })
  }, [journey])

  const activeStep = steps.find((step) => step.active) ?? steps.find((step) => !step.done) ?? steps[steps.length - 1]
  const nextIn = minutesUntil(
    activeStep?.leg.kind === 'walk' ? activeStep.leg.start_time : activeStep?.leg.departure,
  )
  const relevantAlert = alerts.find(
    (alert) =>
      alert.severity !== 'info' &&
      (alert.route_ids?.some((id) => journey.legs.some((leg) => leg.route_id === id)) ||
        alert.mode === activeStep?.leg.mode),
  )

  const switchJourney = async () => {
    setSwitching(true)
    try {
      const response = await api.search({
        origin: journey.legs[0]?.from.name ?? '',
        destination: journey.legs[journey.legs.length - 1]?.to.name ?? '',
        preference: 'fastest',
        max_walk_minutes: 20,
        limit: 4,
      })
      const others = response.journeys.filter((option) => option.id !== journey.id)
      setAlternatives(others)
    } catch {
      setAlternatives([])
    } finally {
      setSwitching(false)
    }
  }

  return (
    <div className="screen screen--live">
      <div className="results__map">
        <MapCanvas journey={journey} height="fill" reserveBottom={0.55} live />
        <button type="button" className="map__back" onClick={onBack} aria-label="Back">
          <Icon name="back" size={20} />
        </button>
      </div>

      <div className="card live__head">
        <span className="live__pill">
          <span className="live__pulse" aria-hidden />
          Live
        </span>
        <h2>You’re on your way</h2>
        <p className="muted small">
          Arriving {clock(journey.arrival_time)} ·{' '}
          {journey.summary}
        </p>
      </div>

      {activeStep && (
        <div className="card live__next">
          <span className="live__next-icon" style={{ color: modeColour(activeStep.leg.mode) }}>
            <ModeIcon mode={activeStep.leg.mode} size={22} />
          </span>
          <div className="live__next-body">
            <em>Next</em>
            <strong>{activeStep.title}</strong>
            <span>{activeStep.detail}</span>
          </div>
          <div className="live__next-eta">
            {nextIn !== null && nextIn > -1 ? (
              <>
                <strong>{nextIn}</strong>
                <em>min</em>
              </>
            ) : (
              <>
                <strong>now</strong>
                <em>&nbsp;</em>
              </>
            )}
          </div>
        </div>
      )}

      <Section title="Steps">
        <div className="card card--list">
          {steps.map((step) => (
            <div
              key={step.index}
              className={`step${step.done ? ' step--done' : ''}${step.active ? ' step--active' : ''}`}
            >
              <span className="step__mark">
                {step.done ? <Icon name="check" size={14} /> : step.active ? <span className="step__dot" /> : null}
              </span>
              <span className="step__body">
                <strong>{step.title}</strong>
                <em>{step.detail}</em>
              </span>
              <span className="step__time">
                {clock(step.leg.kind === 'walk' ? step.leg.start_time : step.leg.departure)}
              </span>
            </div>
          ))}
        </div>
      </Section>

      {track && track.legs?.some((leg) => leg.delay_s > 60) && (
        <div className="card disruption">
          <header className="disruption__head">
            <Icon name="alert" size={18} />
            <strong>
              {track.legs.find((leg) => leg.delay_s > 60)?.route_name} is delayed by{' '}
              {track.legs.find((leg) => leg.delay_s > 60)?.delay_label}
            </strong>
          </header>
          <p className="muted small">{track.advice}</p>
          <Button variant="primary" icon="swap" onClick={switchJourney} disabled={switching}>
            {switching ? 'Finding an alternative…' : 'Switch journey'}
          </Button>
        </div>
      )}

      {relevantAlert && (
        <div className="card disruption">
          <header className="disruption__head">
            <Icon name="alert" size={18} />
            <strong>{relevantAlert.header}</strong>
          </header>
          <p className="muted small">{relevantAlert.description}</p>
          <Button variant="primary" icon="swap" onClick={switchJourney} disabled={switching}>
            {switching ? 'Finding an alternative…' : 'Switch journey'}
          </Button>
        </div>
      )}

      {alternatives.length > 0 && (
        <Section title="Alternative journeys">
          <div className="card card--list">
            {alternatives.map((option) => {
              // What the switch costs, stated before it is made: a traveller
              // stranded at a platform wants the difference, not the price.
              const delta = option.price - journey.price
              const arrivalShift = minutesBetween(journey.arrival_time, option.arrival_time)
              return (
              <div key={option.id} className="alt">
                <span className="alt__body">
                  <strong>
                    {option.mode_label} · {option.price_label}
                    <span
                      className={`alt__delta${delta > 0 ? ' alt__delta--up' : delta < 0 ? ' alt__delta--down' : ''}`}
                    >
                      {delta === 0
                        ? 'same price'
                        : delta > 0
                          ? `+${money(delta)} more`
                          : `${money(-delta)} cheaper`}
                    </span>
                  </strong>
                  <em>
                    {option.duration_label} · arrives {clock(option.arrival_time)}
                    {arrivalShift !== null && arrivalShift !== 0 && (
                      <>
                        {' '}
                        ({arrivalShift > 0 ? '+' : '−'}
                        {Math.abs(arrivalShift)} min)
                      </>
                    )}
                  </em>
                </span>
                <Button size="sm" onClick={() => onSwitch(option)}>
                  Switch
                </Button>
                <button
                  type="button"
                  className="link"
                  onClick={() => onOpenJourney(option)}
                >
                  Details
                </button>
              </div>
              )
            })}
          </div>
        </Section>
      )}

      {firstLeg && (
        <p className="muted tiny live__note">
          Live positions come from operator feeds where MoveIn can reach them; offline, the times
          shown are the timetabled ones.
        </p>
      )}
    </div>
  )
}
