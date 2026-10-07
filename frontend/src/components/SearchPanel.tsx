import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../lib/api'
import { modeIcon } from '../lib/format'
import type { Preference, StopSuggestion } from '../lib/types'

export interface SearchValues {
  origin: string
  destination: string
  /** ISO local datetime, or null for "leave now". */
  departure: string | null
  preference: string
  stepFree: boolean
  railcard: boolean
  student: boolean
  /** Longest walk the traveller will accept, in minutes. Null means "any". */
  maxWalkMinutes: number | null
}

interface Props {
  values: SearchValues
  onChange: (values: SearchValues) => void
  onSubmit: (values: SearchValues) => void
  preferences: Preference[]
  busy?: boolean
}

/** The walk limits a person might actually choose. */
const WALK_CHOICES: { value: number | null; label: string }[] = [
  { value: null, label: 'Any walk' },
  { value: 10, label: '10 min' },
  { value: 15, label: '15 min' },
  { value: 20, label: '20 min' },
]

/**
 * Where to?
 *
 * The shape follows the app everyone already knows how to use: two places, one
 * above the other, with the swap arrow between them; a single row of choices
 * underneath rather than a form. Nothing here is a field the traveller has to
 * understand before they can get an answer.
 */
export function SearchPanel({ values, onChange, onSubmit, preferences, busy }: Props) {
  const [when, setWhen] = useState<'now' | 'later'>(values.departure ? 'later' : 'now')
  const [more, setMore] = useState(false)

  const set = (patch: Partial<SearchValues>) => onChange({ ...values, ...patch })

  const submit = (event?: React.FormEvent) => {
    event?.preventDefault()
    if (!values.origin.trim() || !values.destination.trim()) return
    onSubmit({ ...values, departure: when === 'later' ? values.departure : null })
  }

  /**
   * A filter applies the moment it is chosen.
   *
   * "How far will you walk?" and "what matters most?" are choices between
   * results, not fields in a form: making somebody change one and then press
   * Plan again hides the answer they just asked for.
   */
  const apply = (patch: Partial<SearchValues>) => {
    const next = { ...values, ...patch }
    onChange(next)
    if (next.origin.trim() && next.destination.trim()) {
      onSubmit({ ...next, departure: when === 'later' ? next.departure : null })
    }
  }

  return (
    <form className="where" onSubmit={submit}>
      <div className="where__fields">
        <div className="where__field">
          <PlaceField
            role="origin"
            value={values.origin}
            placeholder="Your starting point"
            onChange={(origin) => set({ origin })}
            onSubmit={() => submit()}
          />
        </div>

        <div className="where__divider" aria-hidden />

        <div className="where__field">
          <PlaceField
            role="destination"
            value={values.destination}
            placeholder="Where to?"
            onChange={(destination) => set({ destination })}
            onSubmit={() => submit()}
          />
        </div>

        <button
          type="button"
          className="where__swap"
          title="Swap origin and destination"
          aria-label="Swap origin and destination"
          onClick={() => set({ origin: values.destination, destination: values.origin })}
        >
          ⇅
        </button>
      </div>

      <div className="chip-row chip-row--scroll" role="group" aria-label="When">
        <Chip
          active={when === 'now'}
          onClick={() => {
            setWhen('now')
            set({ departure: null })
          }}
        >
          Leave now
        </Chip>
        <Chip
          active={when === 'later'}
          onClick={() => {
            setWhen('later')
            if (!values.departure) set({ departure: defaultDeparture() })
          }}
        >
          Leave at
        </Chip>
        {when === 'later' && (
          <input
            className="input input--chip"
            type="datetime-local"
            aria-label="Departure time"
            value={values.departure ?? defaultDeparture()}
            onChange={(event) => set({ departure: event.target.value })}
          />
        )}
      </div>

      <div className="where__label">
        What matters most?
        <span className="muted tiny"> — this changes the order, never the options</span>
      </div>
      <div className="chip-row chip-row--scroll" role="group" aria-label="Preference">
        {preferences.map((preference) => (
          <Chip
            key={preference.id}
            active={values.preference === preference.id}
            title={preference.description}
            onClick={() => apply({ preference: preference.id })}
          >
            <span aria-hidden>{iconFor(preference.icon)}</span> {preference.label}
          </Chip>
        ))}
      </div>

      <div className="where__label">
        How far will you walk?
        <span className="muted tiny"> — nobody walks for half an hour</span>
      </div>
      <div className="chip-row" role="group" aria-label="Maximum walking">
        {WALK_CHOICES.map((choice) => (
          <Chip
            key={choice.label}
            active={values.maxWalkMinutes === choice.value}
            onClick={() => apply({ maxWalkMinutes: choice.value })}
          >
            {choice.label}
          </Chip>
        ))}
        <button
          type="button"
          className="chip chip--ghost"
          aria-expanded={more}
          onClick={() => setMore((v) => !v)}
        >
          {more ? '▾' : '▸'} Traveller
          {values.stepFree || values.railcard || values.student ? ' •' : ''}
        </button>
      </div>

      {more && (
        <div className="where__more">
          <label>
            <input
              type="checkbox"
              checked={values.stepFree}
              onChange={(event) => apply({ stepFree: event.target.checked })}
            />
            Step-free only
          </label>
          <label>
            <input
              type="checkbox"
              checked={values.railcard}
              onChange={(event) => apply({ railcard: event.target.checked })}
            />
            Railcard
          </label>
          <label>
            <input
              type="checkbox"
              checked={values.student}
              onChange={(event) => apply({ student: event.target.checked })}
            />
            Student
          </label>
        </div>
      )}

      <button className="btn btn--primary where__go" type="submit" disabled={busy}>
        {busy ? 'Planning…' : 'Plan journey'}
      </button>
    </form>
  )
}

function Chip({
  active,
  onClick,
  children,
  title,
}: {
  active?: boolean
  onClick: () => void
  children: React.ReactNode
  title?: string
}) {
  return (
    <button
      type="button"
      title={title}
      className={`chip${active ? ' chip--active' : ''}`}
      onClick={onClick}
      aria-pressed={active}
    >
      {children}
    </button>
  )
}

/** One of the two place inputs, with type-ahead over the real stop list. */
function PlaceField({
  role,
  value,
  placeholder,
  onChange,
  onSubmit,
}: {
  role: 'origin' | 'destination'
  value: string
  placeholder: string
  onChange: (value: string) => void
  onSubmit: () => void
}) {
  const [suggestions, setSuggestions] = useState<StopSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const query = value.trim()
    if (query.length < 2) {
      setSuggestions([])
      return
    }
    const handle = window.setTimeout(() => {
      api
        .searchStops(query, 6)
        .then((data) => setSuggestions(data.results))
        .catch(() => setSuggestions([]))
    }, 180)
    return () => window.clearTimeout(handle)
  }, [value])

  useEffect(() => {
    const onDocumentClick = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocumentClick)
    return () => document.removeEventListener('mousedown', onDocumentClick)
  }, [])

  const visible = useMemo(() => (open ? suggestions : []), [open, suggestions])

  return (
    <div className="place" ref={box}>
      <span className={`place__marker place__marker--${role}`} aria-hidden />
      <input
        className="place__input"
        value={value}
        placeholder={placeholder}
        aria-label={role === 'origin' ? 'From' : 'To'}
        autoComplete="off"
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          onChange(event.target.value)
          setOpen(true)
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            setOpen(false)
            onSubmit()
          }
        }}
      />
      {visible.length > 0 && (
        <ul className="place__list">
          {visible.map((suggestion) => (
            <li key={suggestion.id}>
              <button
                type="button"
                onClick={() => {
                  onChange(suggestion.name)
                  setOpen(false)
                  onSubmit()
                }}
              >
                <span aria-hidden>{modeIcon(suggestion.mode ?? 'bus')}</span>
                <span className="place__list-name">{suggestion.name}</span>
                {suggestion.region && (
                  <span className="tiny muted">{suggestion.region}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function defaultDeparture(): string {
  const date = new Date()
  date.setMinutes(date.getMinutes() + 30)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

function iconFor(icon: string): string {
  return (
    {
      pound: '£',
      clock: '⏱',
      star: '★',
      swap: '⇄',
      leaf: '🌱',
      walk: '🚶',
      accessible: '♿',
    }[icon] ?? '•'
  )
}
