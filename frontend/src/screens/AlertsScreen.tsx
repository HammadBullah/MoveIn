import { useEffect, useState } from 'react'
import { Button, Section, Toggle } from '../components/Controls'
import { Icon } from '../components/Icons'
import { PlaceList } from '../components/PlaceList'
import { api, ApiError } from '../lib/api'
import { money, relativeTime } from '../lib/format'
import type { PriceAlert } from '../lib/types'

/**
 * Price alerts.
 *
 * The screen has one job beyond listing alerts: making the price history
 * legible, because "£27, was £34" is the only sentence that makes a traveller
 * trust the number.
 */
export function AlertsScreen({ active }: { active: boolean }) {
  const [alerts, setAlerts] = useState<PriceAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [target, setTarget] = useState('25')
  const [creating, setCreating] = useState(false)
  const [checking, setChecking] = useState(false)

  const load = () => {
    setLoading(true)
    api
      .alerts()
      .then((response) => {
        setAlerts(response.alerts)
        setError(null)
      })
      .catch((cause) =>
        setError(cause instanceof ApiError ? cause.message : 'Could not load your alerts.'),
      )
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (active) load()
  }, [active])

  const create = async () => {
    if (!origin.trim() || !destination.trim()) return
    setCreating(true)
    try {
      await api.watch({
        origin,
        destination,
        preference: 'cheapest',
        target_price: Number(target) || null,
      })
      setOrigin('')
      setDestination('')
      load()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not create that alert.')
    } finally {
      setCreating(false)
    }
  }

  const checkNow = async () => {
    setChecking(true)
    try {
      await api.checkAlerts()
      load()
    } catch {
      /* the list still shows the last known prices */
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="screen screen--alerts">
      <header className="page__head">
        <h1>Price alerts</h1>
        <button type="button" className="link" onClick={checkNow} disabled={checking}>
          {checking ? 'Checking…' : 'Check now'}
        </button>
      </header>

      <Section title="New alert">
        <div className="card card--pad">
          <PlaceList
            query={origin}
            placeholder="From"
            label="From"
            icon="target"
            onPick={(next) => setOrigin(next)}
            onFreeText={setOrigin}
          />
          <PlaceList
            query={destination}
            placeholder="To"
            label="To"
            icon="search"
            onPick={(next) => setDestination(next)}
            onFreeText={setDestination}
          />
          <div className="alert-make__row">
            <span className="alert-make__prefix">Tell me below</span>
            <span className="alert-make__input">
              £
              <input
                value={target}
                inputMode="decimal"
                aria-label="Target price"
                onChange={(event) => setTarget(event.target.value)}
              />
            </span>
          </div>
          <Button
            full
            icon="bell"
            disabled={creating || !origin.trim() || !destination.trim()}
            onClick={create}
          >
            {creating ? 'Creating…' : 'Alert me'}
          </Button>
        </div>
      </Section>

      <Section title="Watching">
        {loading && <p className="muted small">Loading your alerts…</p>}
        {error && (
          <div className="notice notice--error">
            <Icon name="alert" size={16} />
            <span>{error}</span>
          </div>
        )}
        {!loading && alerts.length === 0 && (
          <div className="empty">
            <Icon name="bell" size={24} />
            <h3>No alerts yet</h3>
            <p className="muted small">
              Watch a route and MoveIn will tell you when the price drops.
            </p>
          </div>
        )}
        <div className="card card--list">
          {alerts.map((alert) => {
            const previous = alert.baseline_price
            const current = alert.last_price
            const dropped =
              previous !== null && current !== null && current < previous ? previous - current : 0
            return (
              <div key={alert.id} className="alert">
                <div className="alert__top">
                  <span className="alert__route">
                    {alert.origin} → {alert.destination}
                  </span>
                  <Toggle
                    checked={alert.active}
                    onChange={async (next) => {
                      if (next) return
                      try {
                        await api.unwatch(alert.id)
                        setAlerts((current) => current.filter((a) => a.id !== alert.id))
                      } catch {
                        /* leave the row as it was */
                      }
                    }}
                    label=""
                  />
                </div>
                <div className="alert__prices">
                  <span className="alert__price">
                    <em>Now</em>
                    {current !== null ? money(current) : '—'}
                  </span>
                  <span className="alert__price alert__price--was">
                    <em>Was</em>
                    {previous !== null ? money(previous) : '—'}
                  </span>
                  <span className="alert__target">
                    <em>Target</em>
                    {alert.target_price !== null ? money(alert.target_price) : 'any drop'}
                  </span>
                </div>
                {dropped > 0 && (
                  <p className="alert__drop">
                    <Icon name="coin" size={14} /> Down {money(dropped)} since you started
                    watching
                  </p>
                )}
                <p className="alert__meta">
                  {alert.triggered_at
                    ? `Triggered ${relativeTime(alert.triggered_at)}`
                    : `Last checked ${relativeTime(alert.last_checked_at)}`}
                </p>
              </div>
            )
          })}
        </div>
      </Section>
    </div>
  )
}
