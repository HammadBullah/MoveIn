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
  maxWalk: number | null
}

interface Props {
  values: SearchValues
  onChange: (values: SearchValues) => void
  onSubmit: (values: SearchValues) => void
  preferences: Preference[]
  busy?: boolean
  compact?: boolean
}

export function SearchPanel({
  values,
  onChange,
  onSubmit,
  preferences,
  busy,
  compact,
}: Props) {
  const [when, setWhen] = useState<'now' | 'later'>(
    values.departure ? 'later' : 'now',
  )
  const [more, setMore] = useState(false)

  const set = (patch: Partial<SearchValues>) => onChange({ ...values, ...patch })

  const submit = (event?: React.FormEvent) => {
    event?.preventDefault()
    if (!values.origin.trim() || !values.destination.trim()) return
    onSubmit({ ...values, departure: when === 'later' ? values.departure : null })
  }

  return (
    <form className="search-panel" onSubmit={submit}>
      <div className="search-grid">
        <PlaceField
          label="From"
          value={values.origin}
          placeholder="Town, station or postcode"
          onChange={(origin) => set({ origin })}
        />

        <button
          type="button"
          className="btn btn--ghost swap"
          title="Swap origin and destination"
          onClick={() => set({ origin: values.destination, destination: values.origin })}
          aria-label="Swap origin and destination"
        >
          ⇄
        </button>

        <PlaceField
          label="To"
          value={values.destination}
          placeholder="Where are you going?"
          onChange={(destination) => set({ destination })}
        />
      </div>

      <div className="row row--between" style={{ marginTop: '1rem' }}>
        <div className="field" style={{ flex: '0 0 auto' }}>
          <span className="field__label">When</span>
          <div className="when-tabs">
            <button
              type="button"
              className={`when-tab${when === 'now' ? ' when-tab--active' : ''}`}
              onClick={() => {
                setWhen('now')
                set({ departure: null })
              }}
            >
              Leave now
            </button>
            <button
              type="button"
              className={`when-tab${when === 'later' ? ' when-tab--active' : ''}`}
              onClick={() => {
                setWhen('later')
                if (!values.departure) set({ departure: defaultDeparture() })
              }}
            >
              Choose a time
            </button>
          </div>
        </div>

        {when === 'later' && (
          <div className="field" style={{ flex: '1 1 220px', maxWidth: 280 }}>
            <label className="field__label" htmlFor="departure">
              Departure time
            </label>
            <input
              id="departure"
              className="input"
              type="datetime-local"
              value={values.departure ?? defaultDeparture()}
              onChange={(event) => set({ departure: event.target.value })}
            />
          </div>
        )}

        <div className="spacer" />

        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? 'Planning…' : 'Plan journey'}
        </button>
      </div>

      <div className="section-title" style={{ marginTop: '1.1rem' }}>
        Preference
      </div>
      <div className="preference-grid">
        {preferences.map((preference) => (
          <button
            key={preference.id}
            type="button"
            className={`preference-chip${
              values.preference === preference.id ? ' preference-chip--active' : ''
            }`}
            onClick={() => set({ preference: preference.id })}
            title={preference.description}
          >
            <span className="preference-chip__icon" aria-hidden>
              {iconFor(preference.icon)}
            </span>
            <span>
              <span className="preference-chip__label">{preference.label}</span>
              {!compact && (
                <span className="preference-chip__desc">{preference.description}</span>
              )}
            </span>
          </button>
        ))}
      </div>

      <div className="row" style={{ marginTop: '0.85rem' }}>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={() => setMore((v) => !v)}
          aria-expanded={more}
        >
          {more ? '▾' : '▸'} Traveller options
        </button>
        {values.stepFree && <span className="pill pill--teal">♿ Step-free only</span>}
        {values.railcard && <span className="pill pill--violet">Railcard</span>}
        {values.student && <span className="pill pill--violet">Student</span>}
        {values.maxWalk !== null && (
          <span className="pill pill--amber">Max {values.maxWalk} m walk</span>
        )}
      </div>

      {more && (
        <div
          className="row"
          style={{
            marginTop: '0.6rem',
            padding: '0.75rem 0.9rem',
            background: 'var(--surface-2)',
            borderRadius: 'var(--radius-sm)',
            gap: '1.25rem',
          }}
        >
          <label className="row small" style={{ gap: '0.4rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={values.stepFree}
              onChange={(event) => set({ stepFree: event.target.checked })}
            />
            Step-free journeys only
          </label>
          <label className="row small" style={{ gap: '0.4rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={values.railcard}
              onChange={(event) => set({ railcard: event.target.checked })}
            />
            I have a railcard
          </label>
          <label className="row small" style={{ gap: '0.4rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={values.student}
              onChange={(event) => set({ student: event.target.checked })}
            />
            Student
          </label>
          <label className="row small" style={{ gap: '0.4rem' }}>
            Max walk
            <select
              className="input"
              style={{ padding: '0.25rem 0.5rem', width: 'auto' }}
              value={values.maxWalk === null ? '' : String(values.maxWalk)}
              onChange={(event) =>
                set({ maxWalk: event.target.value ? Number(event.target.value) : null })
              }
            >
              <option value="">No limit</option>
              <option value="400">400 m</option>
              <option value="800">800 m</option>
              <option value="1200">1.2 km</option>
              <option value="2000">2 km</option>
            </select>
          </label>
        </div>
      )}
    </form>
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
      shuffle: '⇄',
      walk: '🚶',
      leaf: '🌱',
      accessible: '♿',
      scales: '⚖',
    }[icon] ?? '•'
  )
}

/** A text field that suggests real stops as you type. */
function PlaceField({
  label,
  value,
  placeholder,
  onChange,
}: {
  label: string
  value: string
  placeholder: string
  onChange: (value: string) => void
}) {
  const [results, setResults] = useState<StopSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!value || value.trim().length < 2) {
      setResults([])
      return
    }
    let cancelled = false
    const timer = window.setTimeout(async () => {
      try {
        const data = await api.searchStops(value, 8)
        if (!cancelled) {
          setResults(data.results)
          // Opening only matters while the field has focus.
          setOpen(document.activeElement === box.current?.querySelector('input'))
        }
      } catch {
        if (!cancelled) setResults([])
      }
    }, 180)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [value])

  useEffect(() => {
    const onClickAway = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickAway)
    return () => document.removeEventListener('mousedown', onClickAway)
  }, [])

  const visible = useMemo(() => (open ? results : []), [open, results])

  return (
    <div className="field" ref={box}>
      <label className="field__label">{label}</label>
      <input
        className="input input--lg"
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          onChange(event.target.value)
          setActive(-1)
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            event.preventDefault()
            setActive((i) => Math.min(i + 1, visible.length - 1))
          } else if (event.key === 'ArrowUp') {
            event.preventDefault()
            setActive((i) => Math.max(i - 1, 0))
          } else if (event.key === 'Enter' && active >= 0 && visible[active]) {
            event.preventDefault()
            onChange(visible[active].name)
            setOpen(false)
          } else if (event.key === 'Escape') {
            setOpen(false)
          }
        }}
      />
      {visible.length > 0 && (
        <div className="suggestions" role="listbox">
          {visible.map((item, index) => (
            <button
              type="button"
              key={`${item.id}-${index}`}
              role="option"
              aria-selected={index === active}
              className={`suggestion${index === active ? ' suggestion--active' : ''}`}
              onMouseEnter={() => setActive(index)}
              onClick={() => {
                onChange(item.name)
                setOpen(false)
              }}
            >
              <span className="suggestion__icon" aria-hidden>
                {item.mode === 'town' ? '🏙' : modeIcon(item.mode)}
              </span>
              <span>
                <span className="suggestion__name">{item.name}</span>
                <br />
                <span className="suggestion__meta">
                  {item.mode === 'town' ? 'Town centre' : item.mode}
                  {item.region ? ` · ${item.region}` : ''}
                  {item.interchange ? ' · interchange' : ''}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
