import type { ReactNode } from 'react'
import { modeColour, modeIcon } from '../lib/format'

export function ModeBadge({ mode, label }: { mode: string; label?: string }) {
  return (
    <span
      className="pill"
      style={{
        background: `${modeColour(mode)}22`,
        color: modeColour(mode),
      }}
      title={label}
    >
      <span aria-hidden>{modeIcon(mode)}</span>
      {label ?? null}
    </span>
  )
}

/** A row of mode icons joined by arrows, e.g. Walk › Train › Bus. */
export function ModeChain({ modes }: { modes: string[] }) {
  if (!modes.length) return <span className="pill">Walk</span>
  return (
    <div className="mode-chain">
      {modes.map((mode, index) => (
        <span key={`${mode}-${index}`} className="row" style={{ gap: '0.25rem' }}>
          {index > 0 && (
            <span className="mode-chain__arrow" aria-hidden>
              ›
            </span>
          )}
          <span
            title={mode}
            style={{
              display: 'grid',
              placeItems: 'center',
              width: 26,
              height: 26,
              borderRadius: 8,
              background: `${modeColour(mode)}1f`,
              border: `1px solid ${modeColour(mode)}55`,
              fontSize: '0.85rem',
            }}
          >
            {modeIcon(mode)}
          </span>
        </span>
      ))}
    </div>
  )
}

export function Stat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div className="stat">
      <div className="stat__value">{value}</div>
      <div className="stat__label">{label}</div>
    </div>
  )
}

export function Banner({
  kind = 'info',
  children,
}: {
  kind?: 'info' | 'error'
  children: ReactNode
}) {
  return <div className={`banner banner--${kind}`}>{children}</div>
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-label="Loading journeys">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton" />
      ))}
    </div>
  )
}

export function Pill({
  tone = 'default',
  children,
}: {
  tone?: 'default' | 'teal' | 'green' | 'amber' | 'red' | 'violet' | 'navy'
  children: ReactNode
}) {
  return <span className={`pill${tone === 'default' ? '' : ` pill--${tone}`}`}>{children}</span>
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="card card--pad center" style={{ padding: '2.5rem 1.5rem' }}>
      <div style={{ fontSize: '2rem' }} aria-hidden>
        🧭
      </div>
      <h3 style={{ marginTop: '0.5rem' }}>{title}</h3>
      {hint && <p className="muted small">{hint}</p>}
    </div>
  )
}
