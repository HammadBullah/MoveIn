import type { ReactNode } from 'react'

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
