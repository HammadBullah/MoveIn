import { useState } from 'react'
import { Button, Section } from '../components/Controls'
import { Icon, ModeIcon } from '../components/Icons'
import { Timeline } from '../components/JourneyCards'
import { bigDuration, clock, money } from '../lib/format'
import type { Journey } from '../lib/types'

export function DetailScreen({
  journey,
  onBack,
  onStart,
  onCompare,
  onSaveAlert,
  saved,
  saving = false,
}: {
  journey: Journey
  onBack: () => void
  onStart: () => void
  onCompare: () => void
  onSaveAlert: (target: number | null) => void
  saved?: boolean
  saving?: boolean
}) {
  const [target, setTarget] = useState(String(Math.max(1, Math.floor(journey.price - 2))))

  return (
    <div className="screen screen--detail">
      <header className="detail__head">
        <button type="button" className="icon-btn" onClick={onBack} aria-label="Back">
          <Icon name="back" size={20} />
        </button>
        <span className="detail__route">{journey.summary}</span>
        <span className="detail__spacer" />
      </header>

      <div className="card detail__summary">
        <div className="detail__numbers">
          <strong className="detail__price">{money(journey.price)}</strong>
          <span className="detail__duration">{bigDuration(journey.duration_s)}</span>
        </div>
        <div className="detail__times">
          <span>
            <em>Departs</em>
            {clock(journey.departure_time)}
          </span>
          <span className="detail__arrow">→</span>
          <span>
            <em>Arrives</em>
            {clock(journey.arrival_time)}
            {journey.arrival_day_offset > 0 && <sup>+{journey.arrival_day_offset}</sup>}
          </span>
          <span>
            <em>Changes</em>
            {journey.changes}
          </span>
        </div>
        {journey.walk_comfort === 'long' && (
          <p className="detail__warn">
            <Icon name="alert" size={14} />
            This route includes a {journey.longest_walk_label} — longer than most people would
            walk between vehicles.
          </p>
        )}
      </div>

      <Section title="Your journey">
        <div className="card card--pad">
          <Timeline journey={journey} />
        </div>
      </Section>

      {journey.fare?.tickets?.length > 0 && (
        <Section title="Your tickets">
          <div className="card card--list">
            {journey.fare.tickets.map((ticket, index) => (
              <div key={index} className="ticket">
                <span className="ticket__icon">
                  <ModeIcon mode={journey.legs[ticket.covers_legs?.[0] ?? 0]?.mode ?? 'bus'} size={18} />
                </span>
                <span className="ticket__body">
                  <strong>{ticket.label}</strong>
                  <em>
                    {ticket.operator_name} · covers {ticket.covers_legs.length} leg
                    {ticket.covers_legs.length > 1 ? 's' : ''}
                  </em>
                </span>
                <span className="ticket__price">{money(ticket.price)}</span>
              </div>
            ))}
            {journey.fare.saving_vs_singles > 0.05 && (
              <p className="ticket__saving">
                <Icon name="coin" size={14} />
                Buying it this way saves {money(journey.fare.saving_vs_singles)} against single
                tickets.
              </p>
            )}
          </div>
        </Section>
      )}

      <Section title="Price alert">
        <div className="card card--pad alert-make">
          <p className="muted small">
            MoveIn can watch this route and tell you if it gets cheaper than this price.
          </p>
          <div className="alert-make__row">
            <span className="alert-make__prefix">Notify me below</span>
            <span className="alert-make__input">
              £
              <input
                value={target}
                inputMode="decimal"
                aria-label="Target price"
                onChange={(event) => setTarget(event.target.value)}
              />
            </span>
          </div>
          <Button
            variant={saved ? 'quiet' : 'primary'}
            icon="bell"
            disabled={saving || saved}
            onClick={() => onSaveAlert(Number(target) || null)}
          >
            {saved ? 'Alert created' : 'Create alert'}
          </Button>
        </div>
      </Section>

      <div className="detail__actions">
        <Button variant="quiet" icon="wallet" onClick={onCompare}>
          Compare
        </Button>
        <Button icon="bolt" onClick={onStart}>
          Start journey
        </Button>
      </div>
    </div>
  )
}
