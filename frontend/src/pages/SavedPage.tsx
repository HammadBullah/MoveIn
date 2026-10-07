import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../lib/api'
import { Banner, Empty, Loading, Pill } from '../components/Primitives'
import { money, relativeTime, titleCase } from '../lib/format'
import type { PriceAlert, SavedJourney, SearchHistoryEntry } from '../lib/types'

export function SavedPage({ onPlan }: { onPlan: (origin: string, destination: string) => void }) {
  const [saved, setSaved] = useState<SavedJourney[]>([])
  const [alerts, setAlerts] = useState<PriceAlert[]>([])
  const [history, setHistory] = useState<SearchHistoryEntry[]>([])
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    setBusy(true)
    try {
      const [savedData, alertData, historyData] = await Promise.all([
        api.saved(),
        api.alerts(),
        api.history(15),
      ])
      setSaved(savedData.saved)
      setAlerts(alertData.alerts)
      setHistory(historyData.history)
      setError(null)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not load your journeys.')
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const checkPrices = async () => {
    try {
      const result = await api.checkAlerts()
      setNotice(
        result.triggered > 0
          ? `${result.triggered} of your watched routes got cheaper.`
          : `Checked ${result.checked} routes — nothing cheaper yet.`,
      )
      await load()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not check prices.')
    }
  }

  if (busy) return <Loading rows={3} />

  return (
    <div className="stack" style={{ gap: '1.1rem' }}>
      <div>
        <h1>Your journeys</h1>
        <p className="muted small" style={{ margin: 0 }}>
          Saved on this device. Phase 1 has no accounts — identities are a random key
          the browser keeps.
        </p>
      </div>

      {error && <Banner kind="error">{error}</Banner>}
      {notice && <Banner kind="info">{notice}</Banner>}

      <div className="section-title">Saved</div>
      {saved.length === 0 ? (
        <Empty
          title="Nothing saved yet"
          hint="Plan a journey and press Save to keep it here."
        />
      ) : (
        <div className="stack" style={{ gap: '0.5rem' }}>
          {saved.map((journey) => (
            <div key={journey.id} className="card card--pad row row--between">
              <div>
                <strong>
                  {journey.origin.label} → {journey.destination.label}
                </strong>
                <div className="muted small">
                  {titleCase(journey.preference.replace('_', ' '))} · saved{' '}
                  {relativeTime(journey.created_at)}
                </div>
              </div>
              <div className="row">
                <button
                  className="btn btn--sm btn--primary"
                  onClick={() => onPlan(journey.origin.label, journey.destination.label)}
                >
                  Plan again
                </button>
                <button
                  className="btn btn--sm btn--ghost"
                  onClick={async () => {
                    await api.unsave(journey.id)
                    await load()
                  }}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="row row--between">
        <div className="section-title" style={{ margin: 0 }}>
          Price watches
        </div>
        <button className="btn btn--sm" onClick={() => void checkPrices()}>
          Check prices now
        </button>
      </div>
      {alerts.length === 0 ? (
        <Empty
          title="No price watches"
          hint="Watch a route and MoveIn will tell you when it gets cheaper."
        />
      ) : (
        <div className="card" style={{ overflow: 'hidden' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Route</th>
                <th>Preference</th>
                <th style={{ textAlign: 'right' }}>Now</th>
                <th style={{ textAlign: 'right' }}>Target</th>
                <th>Checked</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.id}>
                  <td>
                    <strong>
                      {alert.origin} → {alert.destination}
                    </strong>
                    {alert.triggered_at && (
                      <>
                        {' '}
                        <Pill tone="green">dropped</Pill>
                      </>
                    )}
                  </td>
                  <td>{titleCase(alert.preference.replace('_', ' '))}</td>
                  <td style={{ textAlign: 'right' }} className="mono">
                    {alert.last_price != null ? money(alert.last_price) : '—'}
                  </td>
                  <td style={{ textAlign: 'right' }} className="mono">
                    {alert.target_price != null ? money(alert.target_price) : 'any drop'}
                  </td>
                  <td className="tiny muted">{relativeTime(alert.last_checked_at)}</td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      className="btn btn--sm btn--ghost"
                      onClick={async () => {
                        await api.unwatch(alert.id)
                        await load()
                      }}
                    >
                      Stop
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="section-title">Recent searches</div>
      {history.length === 0 ? (
        <Empty title="No searches yet" />
      ) : (
        <div className="card" style={{ overflow: 'hidden' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Journey</th>
                <th>Preference</th>
                <th>Departure</th>
                <th style={{ textAlign: 'right' }}>Options</th>
                <th style={{ textAlign: 'right' }}>Best price</th>
              </tr>
            </thead>
            <tbody>
              {history.map((entry, index) => (
                <tr key={index}>
                  <td>
                    <button
                      className="btn btn--ghost btn--sm"
                      onClick={() => onPlan(entry.origin, entry.destination)}
                    >
                      {entry.origin} → {entry.destination}
                    </button>
                  </td>
                  <td>{titleCase(entry.preference.replace('_', ' '))}</td>
                  <td className="tiny muted">
                    {new Date(entry.when).toLocaleString('en-GB', {
                      weekday: 'short',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </td>
                  <td style={{ textAlign: 'right' }}>{entry.results}</td>
                  <td style={{ textAlign: 'right' }} className="mono">
                    {entry.best_price != null ? money(entry.best_price) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
