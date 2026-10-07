import { useEffect, useState } from 'react'
import { Button, Section } from '../components/Controls'
import { Icon } from '../components/Icons'
import { api } from '../lib/api'
import { money, relativeTime } from '../lib/format'
import { loadRecents } from '../lib/storage'
import type { SavedJourney, SearchHistoryEntry } from '../lib/types'

export function TripsScreen({
  active,
  onPlan,
}: {
  active: boolean
  onPlan: (from: string, to: string) => void
}) {
  const [saved, setSaved] = useState<SavedJourney[]>([])
  const [history, setHistory] = useState<SearchHistoryEntry[]>([])
  const [recents, setRecents] = useState(loadRecents)

  useEffect(() => {
    if (!active) return
    setRecents(loadRecents())
    api
      .saved()
      .then((response) => setSaved(response.saved))
      .catch(() => setSaved([]))
    api
      .history(12)
      .then((response) => setHistory(response.history))
      .catch(() => setHistory([]))
  }, [active])

  const remove = async (id: number) => {
    try {
      await api.unsave(id)
      setSaved((current) => current.filter((entry) => entry.id !== id))
    } catch {
      /* keep the row if the API refused */
    }
  }

  return (
    <div className="screen screen--trips">
      <header className="page__head">
        <h1>Trips</h1>
      </header>

      <Section title="Saved journeys">
        {saved.length === 0 ? (
          <p className="muted small">
            Journeys you save from a result appear here, ready to plan again in one tap.
          </p>
        ) : (
          <div className="card card--list">
            {saved.map((entry) => (
              <div key={entry.id} className="trip">
                <button
                  type="button"
                  className="trip__body"
                  onClick={() => onPlan(entry.origin.label, entry.destination.label)}
                >
                  <strong>
                    {entry.label || `${entry.origin.label} → ${entry.destination.label}`}
                  </strong>
                  <em>
                    {entry.origin.label} → {entry.destination.label}
                  </em>
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="Remove"
                  onClick={() => remove(entry.id)}
                >
                  <Icon name="trash" size={17} />
                </button>
              </div>
            ))}
          </div>
        )}
      </Section>

      {recents.length > 0 && (
        <Section title="Recent on this device">
          <div className="card card--list">
            {recents.map((recent) => (
              <button
                key={recent.id}
                type="button"
                className="list-row list-row--tap"
                onClick={() => onPlan(recent.origin, recent.destination)}
              >
                <span className="list-row__icon">
                  <Icon name="clock" size={18} />
                </span>
                <span className="list-row__label">
                  {recent.origin} → {recent.destination}
                </span>
                <Icon name="chevron" size={16} className="list-row__chevron" />
              </button>
            ))}
          </div>
        </Section>
      )}

      {history.length > 0 && (
        <Section title="Searches">
          <div className="card card--list">
            {history.map((entry, index) => (
              <button
                key={`${entry.origin}-${entry.destination}-${index}`}
                type="button"
                className="trip"
                onClick={() => onPlan(entry.origin, entry.destination)}
              >
                <span className="trip__body">
                  <strong>
                    {entry.origin} → {entry.destination}
                  </strong>
                  <em>
                    {entry.results} results
                    {entry.best_price !== null ? ` · from ${money(entry.best_price)}` : ''} ·{' '}
                    {relativeTime(entry.searched_at)}
                  </em>
                </span>
              </button>
            ))}
          </div>
        </Section>
      )}

      <div className="trips__footer">
        <Button variant="quiet" full icon="search" onClick={() => onPlan('', '')}>
          Plan something new
        </Button>
      </div>
    </div>
  )
}
