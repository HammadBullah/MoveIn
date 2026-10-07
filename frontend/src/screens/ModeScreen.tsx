import { useState } from 'react'
import { Button, Chip, Section, Toggle } from '../components/Controls'
import { Icon } from '../components/Icons'
import { PlaceList } from '../components/PlaceList'
import { modeLabel, money, whenLabel } from '../lib/format'
import { ALL_MODES } from '../lib/storage'

/**
 * The dedicated "cheapest" and "fastest" searches.
 *
 * They are the two questions people actually ask out loud — "what is the
 * cheapest way there?" and "what is the quickest, within reason?" — and both
 * deserve their own constraints rather than a chip on a results list.
 */
export function ModeScreen({
  mode,
  from,
  to,
  onBack,
  onRun,
  initialModes,
}: {
  mode: 'cheapest' | 'fastest'
  from: string
  to: string
  onBack: () => void
  onRun: (input: {
    origin: string
    destination: string
    originLabel: string
    destinationLabel: string
    preference: string
    maxWalkMinutes: number
    maxChanges: number
    maxPrice: number | null
    arriveBy: string | null
    modes: string[]
  }) => void
  initialModes: string[]
}) {
  const [origin, setOrigin] = useState(from)
  const [destination, setDestination] = useState(to)
  const [originLabel, setOriginLabel] = useState(from)
  const [destinationLabel, setDestinationLabel] = useState(to)
  const [maxWalk, setMaxWalk] = useState(mode === 'cheapest' ? 15 : 10)
  const [maxChanges, setMaxChanges] = useState(3)
  const [maxPrice, setMaxPrice] = useState<number | null>(mode === 'fastest' ? 50 : null)
  const [arriveBy, setArriveBy] = useState('')
  const [modes, setModes] = useState<string[]>(initialModes)

  const cheapest = mode === 'cheapest'

  return (
    <div className="screen screen--mode">
      <header className="detail__head">
        <button type="button" className="icon-btn" onClick={onBack} aria-label="Back">
          <Icon name="back" size={20} />
        </button>
        <span className="detail__route">{cheapest ? 'Cheapest way' : 'Fastest way'}</span>
        <span className="detail__spacer" />
      </header>

      <div className="mode__intro">
        <span className={`mode__glyph mode__glyph--${cheapest ? 'cheap' : 'fast'}`}>
          <Icon name={cheapest ? 'coin' : 'bolt'} size={22} />
        </span>
        <h1>{cheapest ? 'Find the cheapest way' : 'Get me there fastest'}</h1>
        <p className="muted small">
          {cheapest
            ? 'MoveIn will put price first and everything else second — you decide how much walking and how many changes you will accept.'
            : 'Tell MoveIn what you will spend and which modes you will use, and it will find the quickest way that still fits.'}
        </p>
      </div>

      <div className="card card--pad">
        <PlaceList
          query={origin}
          placeholder="From"
          label="From"
          icon="target"
          onPick={(next, label) => {
            setOrigin(next)
            setOriginLabel(label)
          }}
          onFreeText={(text) => {
            setOrigin(text)
            setOriginLabel(text)
          }}
        />
        <PlaceList
          query={destination}
          placeholder="To"
          label="To"
          icon="search"
          onPick={(next, label) => {
            setDestination(next)
            setDestinationLabel(label)
          }}
          onFreeText={(text) => {
            setDestination(text)
            setDestinationLabel(text)
          }}
        />
      </div>

      <Section title={cheapest ? 'Your limits' : 'Your budget'}>
        <div className="card card--pad">
          {!cheapest && (
            <label className="slider">
              <span className="slider__head">
                <span>Maximum price</span>
                <strong>{maxPrice ? money(maxPrice) : 'Any'}</strong>
              </span>
              <input
                type="range"
                min={0}
                max={150}
                step={5}
                value={maxPrice ?? 0}
                onChange={(event) => setMaxPrice(Number(event.target.value) || null)}
              />
            </label>
          )}

          <label className="slider">
            <span className="slider__head">
              <span>Maximum walking</span>
              <strong>{maxWalk} min</strong>
            </span>
            <input
              type="range"
              min={2}
              max={45}
              step={1}
              value={maxWalk}
              onChange={(event) => setMaxWalk(Number(event.target.value))}
            />
          </label>

          <label className="slider">
            <span className="slider__head">
              <span>Maximum changes</span>
              <strong>{maxChanges}</strong>
            </span>
            <input
              type="range"
              min={0}
              max={5}
              step={1}
              value={maxChanges}
              onChange={(event) => setMaxChanges(Number(event.target.value))}
            />
          </label>

          {cheapest && (
            <label className="slider slider--time">
              <span className="slider__head">
                <span>Latest arrival</span>
                <strong>
                  {arriveBy ? whenLabel(`${arriveBy}:00`).split(' · ')[1] : 'Any time'}
                </strong>
              </span>
              <input
                type="time"
                value={arriveBy}
                onChange={(event) => setArriveBy(event.target.value)}
              />
            </label>
          )}
        </div>
      </Section>

      <Section title="Modes allowed">
        <div className="chips chips--wrap">
          {ALL_MODES.map((item) => (
            <Chip
              key={item}
              compact
              active={modes.includes(item)}
              onClick={() =>
                setModes((current) =>
                  current.includes(item) ? current.filter((m) => m !== item) : [...current, item],
                )
              }
            >
              {modeLabel(item)}
            </Chip>
          ))}
        </div>
      </Section>

      <Section>
        <Toggle
          checked={modes.length > 1}
          onChange={(next) => setModes(next ? [...ALL_MODES] : ['rail'])}
          label={modes.length > 1 ? 'Mix as many modes as it takes' : 'Trains only'}
          hint={modes.length > 1 ? `Using ${modes.length} modes` : 'Rail only'}
          icon="layers"
        />
      </Section>

      <div className="mode__actions">
        <Button
          full
          size="lg"
          icon={cheapest ? 'coin' : 'bolt'}
          disabled={!origin.trim() || !destination.trim()}
          onClick={() =>
            onRun({
              origin,
              destination,
              originLabel,
              destinationLabel,
              preference: cheapest ? 'cheapest' : 'fastest',
              maxWalkMinutes: maxWalk,
              maxChanges,
              maxPrice,
              arriveBy: arriveBy ? `${arriveBy}:00` : null,
              modes,
            })
          }
        >
          {cheapest ? 'Find cheapest' : 'Find fastest'}
        </Button>
      </div>
    </div>
  )
}
