import { useEffect, useState } from 'react'
import { ALL_MODES } from '../lib/storage'
import { modeLabel } from '../lib/format'
import { Button, Chip, Sheet } from './Controls'
import { ModeIcon } from './Icons'

export interface Filters {
  modes: string[]
  maxWalkMinutes: number
  maxChanges: number
  maxPrice: number | null
  preferences: string[]
  accessible: boolean
}

export const DEFAULT_FILTERS: Filters = {
  modes: [...ALL_MODES],
  maxWalkMinutes: 15,
  maxChanges: 3,
  maxPrice: null,
  preferences: ['best_value'],
  accessible: false,
}

const PREFERENCES = [
  { id: 'cheapest', label: 'Cheapest', icon: 'coin' },
  { id: 'fastest', label: 'Fastest', icon: 'bolt' },
  { id: 'fewest_changes', label: 'Fewest changes', icon: 'changes' },
  { id: 'least_walking', label: 'Least walking', icon: 'walk' },
  { id: 'accessible', label: 'Accessible', icon: 'wheelchair' },
  { id: 'lowest_emissions', label: 'Lower emissions', icon: 'leaf' },
]

/**
 * The transport sheet.
 *
 * Everything that changes what the planner is allowed to offer lives here, in
 * one place, so the results screen can stay a list of answers rather than a
 * wall of controls.
 */
export function FilterSheet({
  open,
  filters,
  onClose,
  onApply,
}: {
  open: boolean
  filters: Filters
  onClose: () => void
  onApply: (next: Filters) => void
}) {
  const [draft, setDraft] = useState(filters)

  useEffect(() => {
    if (open) setDraft(filters)
  }, [open, filters])

  if (!open) return null

  const toggleMode = (mode: string) => {
    setDraft((current) => ({
      ...current,
      modes: current.modes.includes(mode)
        ? current.modes.filter((m) => m !== mode)
        : [...current.modes, mode],
    }))
  }

  const allOn = draft.modes.length === ALL_MODES.length

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Transport filters">
      <button type="button" className="overlay__scrim" aria-label="Close" onClick={onClose} />
      <Sheet height="full" className="sheet--filter">
        <header className="sheet__title">
          <h2>Transport</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        <div className="filter__block">
          <div className="filter__head">
            <h3>Modes you will use</h3>
            <button
              type="button"
              className="link"
              onClick={() =>
                setDraft((current) => ({
                  ...current,
                  modes: allOn ? ['rail'] : [...ALL_MODES],
                }))
              }
            >
              {allOn ? 'Trains only' : 'All modes'}
            </button>
          </div>
          <div className="mode-grid">
            {ALL_MODES.map((mode) => {
              const on = draft.modes.includes(mode)
              return (
                <button
                  key={mode}
                  type="button"
                  className={`mode-tile${on ? ' mode-tile--on' : ''}`}
                  onClick={() => toggleMode(mode)}
                  aria-pressed={on}
                >
                  <ModeIcon mode={mode} size={22} />
                  <span>{modeLabel(mode)}</span>
                  {on && <span className="mode-tile__tick">✓</span>}
                </button>
              )
            })}
          </div>
        </div>

        <div className="filter__block">
          <h3>Preferences</h3>
          <div className="chips chips--wrap">
            {PREFERENCES.map((preference) => (
              <Chip
                key={preference.id}
                icon={preference.icon}
                active={draft.preferences.includes(preference.id)}
                onClick={() =>
                  setDraft((current) => ({
                    ...current,
                    preferences: current.preferences.includes(preference.id)
                      ? current.preferences.filter((p) => p !== preference.id)
                      : [...current.preferences, preference.id],
                  }))
                }
              >
                {preference.label}
              </Chip>
            ))}
          </div>
        </div>

        <div className="filter__block">
          <label className="slider">
            <span className="slider__head">
              <span>Maximum walking</span>
              <strong>{draft.maxWalkMinutes} min</strong>
            </span>
            <input
              type="range"
              min={2}
              max={60}
              step={1}
              value={draft.maxWalkMinutes}
              onChange={(event) =>
                setDraft((current) => ({ ...current, maxWalkMinutes: Number(event.target.value) }))
              }
            />
          </label>

          <label className="slider">
            <span className="slider__head">
              <span>Maximum changes</span>
              <strong>{draft.maxChanges}</strong>
            </span>
            <input
              type="range"
              min={0}
              max={5}
              step={1}
              value={draft.maxChanges}
              onChange={(event) =>
                setDraft((current) => ({ ...current, maxChanges: Number(event.target.value) }))
              }
            />
          </label>

          <label className="slider">
            <span className="slider__head">
              <span>Budget</span>
              <strong>{draft.maxPrice ? `£${draft.maxPrice}` : 'Any'}</strong>
            </span>
            <input
              type="range"
              min={0}
              max={120}
              step={5}
              value={draft.maxPrice ?? 0}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  maxPrice: Number(event.target.value) || null,
                }))
              }
            />
          </label>
        </div>

        <div className="filter__actions">
          <Button
            variant="quiet"
            onClick={() => setDraft({ ...DEFAULT_FILTERS, modes: [...ALL_MODES] })}
          >
            Reset
          </Button>
          <Button onClick={() => onApply(draft)} iconRight="check">
            Apply
          </Button>
        </div>
      </Sheet>
    </div>
  )
}
