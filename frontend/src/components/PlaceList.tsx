import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import type { StopSuggestion } from '../lib/types'
import { Icon, ModeIcon } from './Icons'

/**
 * The type-ahead used by every place field in the app.
 *
 * It searches stops, then towns, then — because MoveIn holds the whole real
 * NaPTAN register — stops that no modelled route calls at, which are shown with
 * an honest label rather than silently dropped.  A suggestion list that hides
 * the difference between "we can plan from here" and "we can walk you to
 * somewhere we can" is worse than no list at all.
 */
export function PlaceList({
  query,
  onPick,
  onFreeText,
  autoFocus = false,
  placeholder = 'Where to?',
  label,
  icon = 'search',
}: {
  query: string
  onPick: (value: string, label: string) => void
  onFreeText?: (value: string) => void
  autoFocus?: boolean
  placeholder?: string
  label?: string
  icon?: string
}) {
  const [value, setValue] = useState(query)
  const [results, setResults] = useState<StopSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [cursor, setCursor] = useState(-1)
  const wrapRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    setValue(query)
  }, [query])

  useEffect(() => {
    if (value.trim().length < 2 || !open) {
      setResults([])
      return
    }
    let cancelled = false
    setLoading(true)
    const timer = window.setTimeout(() => {
      api
        .searchStops(value.trim(), 8)
        .then((response) => {
          if (!cancelled) setResults(response.results)
        })
        .catch(() => {
          if (!cancelled) setResults([])
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }, 160)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [value, open])

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const choose = (hit: StopSuggestion) => {
    const label = hit.name
    setValue(label)
    setOpen(false)
    setResults([])
    onPick(hit.id.startsWith('region:') ? label : label, label)
  }

  return (
    <div className="place" ref={wrapRef}>
      <div className="place__field">
        <span className="place__icon">
          <Icon name={icon} size={18} />
        </span>
        <input
          className="place__input"
          value={value}
          placeholder={placeholder}
          aria-label={label ?? placeholder}
          autoFocus={autoFocus}
          onChange={(event) => {
            setValue(event.target.value)
            setOpen(true)
            setCursor(-1)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') {
              event.preventDefault()
              setCursor((c) => Math.min(c + 1, results.length - 1))
            } else if (event.key === 'ArrowUp') {
              event.preventDefault()
              setCursor((c) => Math.max(-1, c - 1))
            } else if (event.key === 'Enter') {
              if (cursor >= 0 && results[cursor]) {
                choose(results[cursor])
              } else if (value.trim()) {
                setOpen(false)
                onFreeText?.(value.trim())
              }
            } else if (event.key === 'Escape') {
              setOpen(false)
            }
          }}
        />
        {loading && <span className="place__spinner" aria-hidden />}
        {!!value && !loading && (
          <button
            type="button"
            className="place__clear"
            aria-label="Clear"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              setValue('')
              setResults([])
              onFreeText?.('')
            }}
          >
            <Icon name="close" size={15} />
          </button>
        )}
      </div>

      {open && (results.length > 0 || value.trim().length >= 2) && (
        <ul className="place__list" role="listbox">
          {results.map((hit, index) => {
            const served = hit.served !== false
            return (
              <li key={`${hit.id}-${index}`}>
                <button
                  type="button"
                  role="option"
                  aria-selected={index === cursor}
                  className={`place__option${index === cursor ? ' place__option--on' : ''}`}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(hit)}
                >
                  <span className="place__option-icon" style={{ color: 'var(--muted)' }}>
                    <ModeIcon mode={hit.mode || 'bus'} size={17} />
                  </span>
                  <span className="place__option-body">
                    <span className="place__option-name">{hit.name}</span>
                    <span className="place__option-meta">
                      {hit.region ? hit.region.replace('-', ' ') : ''}
                      {!served && hit.nearest_served?.reachable
                        ? `${hit.region ? ' · ' : ''}walk ${hit.nearest_served.walk_minutes} min to ${hit.nearest_served.name}`
                        : ''}
                      {!served && !hit.nearest_served?.reachable
                        ? `${hit.region ? ' · ' : ''}no modelled route here`
                        : ''}
                    </span>
                  </span>
                  {hit.mode === 'town' && <span className="tiny muted">Town</span>}
                </button>
              </li>
            )
          })}
          {!loading && results.length === 0 && (
            <li className="place__none">No stop matches “{value.trim()}”. Try a town name.</li>
          )}
        </ul>
      )}
    </div>
  )
}
