import { useEffect, useState } from 'react'
import { Button, Chip, Section } from '../components/Controls'
import { Icon } from '../components/Icons'
import { PlaceList } from '../components/PlaceList'
import { currentLocation, loadPlaces, loadRecents } from '../lib/storage'
import { clock, datetimeLocalValue, whenLabel } from '../lib/format'

const PREFERENCE_CHIPS = [
  { id: 'best_value', label: 'Best value', icon: 'star' },
  { id: 'cheapest', label: 'Cheapest', icon: 'coin' },
  { id: 'fastest', label: 'Fastest', icon: 'bolt' },
  { id: 'fewest_changes', label: 'Fewest changes', icon: 'changes' },
]

export interface HomeValue {
  origin: string
  originLabel: string
  destination: string
  destinationLabel: string
  when: 'now' | string
  preference: string
}

export function HomeScreen({
  value,
  onChange,
  onSearch,
  onOpenMode,
  onOpenPlaces,
}: {
  value: HomeValue
  onChange: (next: Partial<HomeValue>) => void
  onSearch: () => void
  onOpenMode: (mode: 'cheapest' | 'fastest') => void
  onOpenPlaces: () => void
}) {
  const [places, setPlaces] = useState(loadPlaces)
  const [recents, setRecents] = useState(loadRecents)
  const [locating, setLocating] = useState(false)
  const [locationNote, setLocationNote] = useState<string | null>(null)

  useEffect(() => {
    const refresh = () => {
      setPlaces(loadPlaces())
      setRecents(loadRecents())
    }
    window.addEventListener('movein:places', refresh)
    window.addEventListener('movein:recents', refresh)
    return () => {
      window.removeEventListener('movein:places', refresh)
      window.removeEventListener('movein:recents', refresh)
    }
  }, [])

  const detect = async () => {
    setLocating(true)
    setLocationNote(null)
    try {
      const position = await currentLocation()
      onChange({ origin: position.query, originLabel: position.label })
    } catch (error) {
      setLocationNote(error instanceof Error ? error.message : 'Location unavailable.')
    } finally {
      setLocating(false)
    }
  }

  const swap = () =>
    onChange({
      origin: value.destination,
      originLabel: value.destinationLabel,
      destination: value.origin,
      destinationLabel: value.originLabel,
    })

  const ready = value.origin.trim().length > 0 && value.destination.trim().length > 0

  return (
    <div className="screen screen--home">
      <header className="home__top">
        <div className="brand">
          <span className="brand__mark" aria-hidden>
            <Icon name="sparkle" size={18} />
          </span>
          <span className="brand__text">
            <strong>MoveIn</strong>
            <em>Every way to get there</em>
          </span>
        </div>
        <button type="button" className="avatar" onClick={onOpenPlaces} aria-label="Saved places">
          <Icon name="user" size={18} />
        </button>
      </header>

      <h1 className="home__question">Where are you going?</h1>

      <div className="card card--search">
        <div className="route-fields">
          <span className="route-fields__rail" aria-hidden>
            <span className="route-fields__dot route-fields__dot--start" />
            <span className="route-fields__line" />
            <span className="route-fields__dot route-fields__dot--end" />
          </span>
          <div className="route-fields__fields">
            <PlaceList
              query={value.originLabel || value.origin}
              placeholder="Current location"
              label="From"
              icon="target"
              onPick={(next, label) => onChange({ origin: next, originLabel: label })}
              onFreeText={(text) => onChange({ origin: text, originLabel: text })}
            />
            <PlaceList
              query={value.destinationLabel || value.destination}
              placeholder="Where to?"
              label="To"
              icon="search"
              onPick={(next, label) => onChange({ destination: next, destinationLabel: label })}
              onFreeText={(text) => onChange({ destination: text, destinationLabel: text })}
            />
          </div>
          <button type="button" className="route-fields__swap" onClick={swap} aria-label="Swap">
            <Icon name="swap" size={18} />
          </button>
        </div>

        <div className="home__row">
          <button
            type="button"
            className="home__row-value"
            onClick={() => {
              onChange({ when: 'now' })
            }}
          >
            <Icon name="clock" size={16} />
            {value.when === 'now' ? 'Leave now' : whenLabel(value.when)}
          </button>
          <input
            className="home__when-input"
            type="datetime-local"
            aria-label="Departure time"
            value={value.when === 'now' ? '' : value.when.slice(0, 16)}
            onChange={(event) => {
              const next = event.target.value
              onChange({ when: next ? `${next}:00` : 'now' })
            }}
          />
        </div>

        <div className="home__prefs">
          {PREFERENCE_CHIPS.map((chip) => (
            <Chip
              key={chip.id}
              icon={chip.icon}
              compact
              active={value.preference === chip.id}
              onClick={() => onChange({ preference: chip.id })}
            >
              {chip.label}
            </Chip>
          ))}
        </div>

        <Button full size="lg" icon="search" onClick={onSearch} disabled={!ready}>
          Find my journey
        </Button>

        <div className="home__shortcuts">
          <button type="button" className="shortcut" onClick={() => onOpenMode('cheapest')}>
            <Icon name="coin" size={18} />
            <span>
              <strong>Cheapest way</strong>
              <em>I don’t mind how long it takes</em>
            </span>
          </button>
          <button type="button" className="shortcut" onClick={() => onOpenMode('fastest')}>
            <Icon name="bolt" size={18} />
            <span>
              <strong>Get me there fastest</strong>
              <em>With a budget and a mode list</em>
            </span>
          </button>
        </div>

        <button type="button" className="home__detect" onClick={detect} disabled={locating}>
          <Icon name="pin" size={16} />
          {locating ? 'Finding you…' : 'Use current location'}
        </button>
        {locationNote && <p className="home__note">{locationNote}</p>}
      </div>

      <Section
        title="Recent journeys"
        action={
          recents.length > 0 ? <span className="section__hint">{recents.length}</span> : undefined
        }
      >
        {recents.length === 0 ? (
          <p className="muted small">Journeys you search for appear here.</p>
        ) : (
          <div className="card card--list">
            {recents.slice(0, 4).map((recent) => (
              <button
                key={recent.id}
                type="button"
                className="recent"
                onClick={() => {
                  onChange({
                    origin: recent.origin,
                    originLabel: recent.origin,
                    destination: recent.destination,
                    destinationLabel: recent.destination,
                  })
                  onSearch()
                }}
              >
                <Icon name="clock" size={16} />
                <span className="recent__text">
                  {recent.origin} → {recent.destination}
                </span>
                <Icon name="chevron" size={16} />
              </button>
            ))}
          </div>
        )}
      </Section>

      <Section
        title="Saved places"
        action={
          <button type="button" className="link" onClick={onOpenPlaces}>
            Edit
          </button>
        }
      >
        <div className="card card--list">
          {places.map((place) => (
            <div key={place.id} className="place-row">
              <span className="place-row__icon">
                <Icon name={place.icon} size={18} />
              </span>
              <span className="place-row__body">
                <strong>{place.name}</strong>
                <em>{place.query || 'Not set — tap to choose'}</em>
              </span>
              <button
                type="button"
                className="btn btn--quiet btn--sm"
                // An unset place is not a dead end: "Set" takes the traveller
                // straight to the editor rather than sitting there greyed out.
                onClick={() => {
                  if (!place.query) {
                    onOpenPlaces()
                    return
                  }
                  onChange({ destination: place.query, destinationLabel: place.name })
                }}
              >
                {place.query ? 'Go' : 'Set'}
              </button>
            </div>
          ))}
        </div>
      </Section>

      <p className="home__footer">
        {clock(datetimeLocalValue(new Date()))} · Real GB stops and operators · timetable
        compiled from published services
      </p>
    </div>
  )
}
