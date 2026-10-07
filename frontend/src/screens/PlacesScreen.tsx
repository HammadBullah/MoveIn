import { useState } from 'react'
import { Button, Section } from '../components/Controls'
import { Icon } from '../components/Icons'
import { PlaceList } from '../components/PlaceList'
import { loadPlaces, removePlace, upsertPlace, type SavedPlace } from '../lib/storage'

const ICONS: SavedPlace['icon'][] = ['home', 'work', 'study', 'heart']
const ICON_LABELS: Record<SavedPlace['icon'], string> = {
  home: 'Home',
  work: 'Work',
  study: 'University',
  heart: 'Other',
}

/**
 * Saved places.
 *
 * They are the shortcut that makes the home screen worth opening twice: two
 * taps and the search is filled in, without typing an address again.
 */
export function PlacesScreen({ onBack, onPlan }: { onBack: () => void; onPlan: (from: string, to: string) => void }) {
  const [places, setPlaces] = useState<SavedPlace[]>(loadPlaces)
  const [editing, setEditing] = useState<SavedPlace | null>(null)
  const [draftName, setDraftName] = useState('')
  const [draftQuery, setDraftQuery] = useState('')

  const refresh = (next: SavedPlace[]) => {
    setPlaces(next)
    window.dispatchEvent(new Event('movein:places'))
  }

  const beginEdit = (place: SavedPlace) => {
    setEditing(place)
    setDraftName(place.name)
    setDraftQuery(place.query)
  }

  const save = () => {
    if (!editing) return
    refresh(
      upsertPlace({
        ...editing,
        name: draftName.trim() || editing.name,
        query: draftQuery.trim(),
      }),
    )
    setEditing(null)
  }

  return (
    <div className="screen screen--places">
      <header className="detail__head">
        <button type="button" className="icon-btn" onClick={onBack} aria-label="Back">
          <Icon name="back" size={20} />
        </button>
        <span className="detail__route">Saved places</span>
        <span className="detail__spacer" />
      </header>

      <Section title="Your places">
        <div className="card card--list">
          {places.map((place) => (
            <div key={place.id} className="place-row">
              <span className="place-row__icon">
                <Icon name={place.icon} size={18} />
              </span>
              <span className="place-row__body">
                <strong>{place.name}</strong>
                <em>{place.query || 'No address yet'}</em>
              </span>
              <button type="button" className="icon-btn" onClick={() => beginEdit(place)} aria-label={`Edit ${place.name}`}>
                <Icon name="edit" size={17} />
              </button>
              <button
                type="button"
                className="icon-btn"
                aria-label={`Delete ${place.name}`}
                onClick={() => refresh(removePlace(place.id))}
              >
                <Icon name="trash" size={17} />
              </button>
            </div>
          ))}
        </div>
      </Section>

      {editing && (
        <Section title={`Edit ${editing.name}`}>
          <div className="card card--pad">
            <label className="field">
              <span className="field__body">
                <span className="field__label">Name</span>
                <input
                  className="field__input"
                  value={draftName}
                  onChange={(event) => setDraftName(event.target.value)}
                />
              </span>
            </label>
            <PlaceList
              query={draftQuery}
              placeholder="Search for a stop or town"
              label="Address"
              icon="search"
              onPick={(next) => setDraftQuery(next)}
              onFreeText={setDraftQuery}
            />
            <div className="route-fields__row">
              {ICONS.map((icon) => (
                <button
                  key={icon}
                  type="button"
                  className={`icon-btn${editing.icon === icon ? ' icon-btn--on' : ''}`}
                  onClick={() => setEditing({ ...editing, icon })}
                  aria-label={ICON_LABELS[icon]}
                >
                  <Icon name={icon} size={18} />
                </button>
              ))}
            </div>
            <div className="place-edit__actions">
              <Button variant="quiet" onClick={() => setEditing(null)}>
                Cancel
              </Button>
              <Button onClick={save} icon="check">
                Save place
              </Button>
            </div>
          </div>
        </Section>
      )}

      <Section title="Quick plan">
        <div className="card card--pad quick">
          <div className="quick__row">
            {places
              .filter((place) => place.query)
              .map((place) => (
                <Button
                  key={place.id}
                  size="sm"
                  variant="quiet"
                  icon={place.icon}
                  onClick={() => onPlan(place.query, '')}
                >
                  From {place.name}
                </Button>
              ))}
          </div>
          <p className="muted tiny">
            Tapping a place fills the search with its address. Edit a place to change where it
            points.
          </p>
        </div>
      </Section>
    </div>
  )
}
