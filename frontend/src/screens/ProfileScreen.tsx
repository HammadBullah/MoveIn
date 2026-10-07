import { useEffect, useState } from 'react'
import { Button, Chip, Section, Toggle } from '../components/Controls'
import { Icon } from '../components/Icons'
import { api } from '../lib/api'
import { modeLabel } from '../lib/format'
import { ALL_MODES, DEFAULT_PROFILE, loadProfile, saveProfile, type Profile } from '../lib/storage'
import type { Preference } from '../lib/types'

const WALK_CHOICES = [5, 10, 15, 20, 30]

export function ProfileScreen({
  profile,
  onChange,
  onOpenPlaces,
  onOpenData,
}: {
  profile: Profile
  onChange: (next: Profile) => void
  onOpenPlaces: () => void
  onOpenData: () => void
}) {
  const [preferences, setPreferences] = useState<Preference[]>([])
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(profile)

  useEffect(() => {
    api
      .preferences()
      .then((response) => setPreferences(response.preferences))
      .catch(() => setPreferences([]))
  }, [])

  const update = (next: Partial<Profile>) => {
    const merged = { ...profile, ...next }
    onChange(merged)
    saveProfile(merged)
  }

  return (
    <div className="screen screen--profile">
      <header className="page__head">
        <h1>Profile</h1>
      </header>

      <div className="card profile__card">
        <span className="profile__avatar">
          {profile.name ? profile.name.charAt(0).toUpperCase() : 'M'}
        </span>
        {editing ? (
          <div className="profile__edit">
            <input
              className="profile__input"
              value={draft.name}
              aria-label="Name"
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            />
            <input
              className="profile__input"
              value={draft.email}
              aria-label="Email"
              placeholder="Email"
              onChange={(event) => setDraft({ ...draft, email: event.target.value })}
            />
            <div className="profile__edit-actions">
              <Button
                size="sm"
                onClick={() => {
                  update({ name: draft.name, email: draft.email })
                  setEditing(false)
                }}
              >
                Save
              </Button>
              <Button size="sm" variant="quiet" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="profile__identity">
            <strong>{profile.name || 'Traveller'}</strong>
            <span className="muted small">{profile.email || 'Add an email for receipts'}</span>
            <button type="button" className="link" onClick={() => setEditing(true)}>
              Edit
            </button>
          </div>
        )}
      </div>

      <Section title="Preferences">
        <div className="card card--pad">
          <div className="pref">
            <span className="pref__label">Default preference</span>
            <div className="chips chips--wrap">
              {(preferences.length
                ? preferences.map((p) => ({ id: p.id, label: p.label }))
                : [
                    { id: 'best_value', label: 'Best value' },
                    { id: 'cheapest', label: 'Cheapest' },
                    { id: 'fastest', label: 'Fastest' },
                    { id: 'least_walking', label: 'Least walking' },
                  ]
              ).map((option) => (
                <Chip
                  key={option.id}
                  compact
                  active={profile.preference === option.id}
                  onClick={() => update({ preference: option.id })}
                >
                  {option.label}
                </Chip>
              ))}
            </div>
          </div>

          <div className="pref">
            <span className="pref__label">Walking</span>
            <div className="chips chips--wrap">
              {WALK_CHOICES.map((minutes) => (
                <Chip
                  key={minutes}
                  compact
                  active={profile.maxWalkMinutes === minutes}
                  onClick={() => update({ maxWalkMinutes: minutes })}
                >
                  Up to {minutes} min
                </Chip>
              ))}
            </div>
          </div>

          <div className="pref">
            <span className="pref__label">Transport modes</span>
            <div className="chips chips--wrap">
              {ALL_MODES.map((mode) => (
                <Chip
                  key={mode}
                  compact
                  active={profile.modes.includes(mode)}
                  onClick={() =>
                    update({
                      modes: profile.modes.includes(mode)
                        ? profile.modes.filter((m) => m !== mode)
                        : [...profile.modes, mode],
                    })
                  }
                >
                  {modeLabel(mode)}
                </Chip>
              ))}
            </div>
          </div>

          <Toggle
            checked={profile.accessible}
            onChange={(next) => update({ accessible: next })}
            label="Step-free journeys only"
            hint="Avoid steps, stairs and escalators"
            icon="wheelchair"
          />
          <Toggle
            checked={profile.notifications}
            onChange={(next) => update({ notifications: next })}
            label="Notifications"
            hint="Price drops and disruption on journeys you follow"
            icon="bell"
          />
        </div>
      </Section>

      <Section title="Your MoveIn">
        <div className="card card--list">
          <button type="button" className="list-row list-row--tap" onClick={onOpenPlaces}>
            <span className="list-row__icon">
              <Icon name="pin" size={18} />
            </span>
            <span className="list-row__label">Saved places</span>
            <Icon name="chevron" size={16} className="list-row__chevron" />
          </button>
          <button type="button" className="list-row list-row--tap" onClick={onOpenData}>
            <span className="list-row__icon">
              <Icon name="layers" size={18} />
            </span>
            <span className="list-row__label">Data &amp; sources</span>
            <Icon name="chevron" size={16} className="list-row__chevron" />
          </button>
        </div>
      </Section>

      <div className="profile__footer">
        <Button
          variant="quiet"
          full
          onClick={() => {
            onChange(DEFAULT_PROFILE)
            saveProfile(DEFAULT_PROFILE)
            setDraft(DEFAULT_PROFILE)
          }}
        >
          Reset preferences
        </Button>
        <p className="muted tiny">
          MoveIn Phase 1 keeps saved places, preferences and alerts on this device. Nothing is
          sent to an account because there isn’t one yet.
          {loadProfile().name ? '' : ''}
        </p>
      </div>
    </div>
  )
}
