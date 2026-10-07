import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Banner, Loading, Pill, Stat } from '../components/Primitives'
import { modeIcon, occupancyLabel, relativeTime } from '../lib/format'
import type { LiveAlert, LiveVehicle } from '../lib/types'

export function LivePage() {
  const [vehicles, setVehicles] = useState<LiveVehicle[]>([])
  const [alerts, setAlerts] = useState<LiveAlert[]>([])
  const [source, setSource] = useState('')
  const [generatedAt, setGeneratedAt] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)
  const [modeFilter, setModeFilter] = useState<string>('all')

  const load = useCallback(async () => {
    setBusy(true)
    try {
      const [live, disruption] = await Promise.all([
        api.liveVehicles(300),
        api.liveAlerts(),
      ])
      setVehicles(live.vehicles)
      setSource(live.source)
      setGeneratedAt(live.generated_at)
      setAlerts(disruption.alerts)
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load live data.')
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    void load()
    // The live pictures moves; refresh it once a minute while the page is open.
    const timer = window.setInterval(() => void load(), 60_000)
    return () => window.clearInterval(timer)
  }, [load])

  const modes = Array.from(new Set(vehicles.map((v) => v.mode))).sort()

  const visible =
    modeFilter === 'all'
      ? vehicles
      : vehicles.filter((vehicle) => vehicle.mode === modeFilter)

  const onTime = vehicles.filter((v) => Math.abs(v.delay_s) < 120).length
  const late = vehicles.filter((v) => v.delay_s >= 120).length
  const disrupted = vehicles.filter((v) => v.delay_s >= 420).length

  return (
    <div className="stack" style={{ gap: '1.1rem' }}>
      <div className="row row--between">
        <div>
          <h1>Running now</h1>
          <p className="muted small" style={{ margin: 0 }}>
            {vehicles.length} vehicles reported
            {generatedAt ? ` at ${new Date(generatedAt).toLocaleTimeString('en-GB')}` : ''} ·{' '}
            {source}
          </p>
        </div>
        <button className="btn btn--sm" onClick={() => void load()} disabled={busy}>
          ↻ Refresh
        </button>
      </div>

      {error && <Banner kind="error">{error}</Banner>}
      {busy && vehicles.length === 0 && <Loading rows={2} />}

      {vehicles.length > 0 && (
        <div className="stat-grid">
          <Stat value={vehicles.length} label="In service" />
          <Stat value={onTime} label="On time" />
          <Stat value={late} label="Late" />
          <Stat value={disrupted} label="Over 7 min late" />
        </div>
      )}

      {alerts.length > 0 && (
        <>
          <div className="section-title">Disruptions</div>
          <div className="stack">
            {alerts.map((alert) => (
              <div className={`alert-strip alert-strip--${alert.severity}`} key={alert.id}>
                <span aria-hidden style={{ fontSize: '1.1rem' }}>
                  {alert.severity === 'severe' ? '⛔' : alert.severity === 'warning' ? '⚠️' : 'ℹ️'}
                </span>
                <div>
                  <strong>{alert.header}</strong>
                  <div className="muted small">{alert.description}</div>
                  <div className="row" style={{ marginTop: '0.3rem', gap: '0.3rem' }}>
                    {alert.mode && <Pill tone="navy">{alert.mode}</Pill>}
                    {alert.regions.map((region) => (
                      <Pill key={region}>{region}</Pill>
                    ))}
                    {alert.route_ids.map((route) => (
                      <Pill key={route} tone="amber">
                        {route}
                      </Pill>
                    ))}
                    <Pill tone="amber">{alert.source}</Pill>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="section-title">Vehicles</div>
      <div className="row">
        <button
          className={`when-tab${modeFilter === 'all' ? ' when-tab--active' : ''}`}
          onClick={() => setModeFilter('all')}
        >
          All
        </button>
        {modes.map((mode) => (
          <button
            key={mode}
            className={`when-tab${modeFilter === mode ? ' when-tab--active' : ''}`}
            onClick={() => setModeFilter(mode)}
          >
            {modeIcon(mode)} {mode}
          </button>
        ))}
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        <table className="table">
          <thead>
            <tr>
              <th>Route</th>
              <th>Vehicle</th>
              <th>Next stop</th>
              <th>Occupancy</th>
              <th>Status</th>
              <th style={{ textAlign: 'right' }}>Reported</th>
            </tr>
          </thead>
          <tbody>
            {visible.slice(0, 60).map((vehicle) => (
              <tr key={vehicle.vehicle_id}>
                <td>
                  <span className="row" style={{ gap: '0.35rem' }}>
                    <span aria-hidden>{modeIcon(vehicle.mode)}</span>
                    <strong>{vehicle.route_name}</strong>
                  </span>
                </td>
                <td className="mono tiny">{vehicle.vehicle_id}</td>
                <td>
                  {vehicle.next_stop.name}
                  <div className="tiny muted">
                    {Math.round(vehicle.progress * 100)}% through the trip
                  </div>
                </td>
                <td>{occupancyLabel(vehicle.occupancy)}</td>
                <td>
                  <Pill
                    tone={
                      Math.abs(vehicle.delay_s) < 120
                        ? 'green'
                        : vehicle.delay_s >= 420
                          ? 'red'
                          : 'amber'
                    }
                  >
                    {vehicle.delay_label}
                  </Pill>
                </td>
                <td style={{ textAlign: 'right' }} className="tiny muted">
                  {relativeTime(vehicle.recorded_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Banner>
        These positions are derived from each trip’s real schedule rather than a live
        feed: the BODS SIRI-VM host is not reachable from this deployment. The tracking
        endpoint, the delay handling and the re-planning above them are the same code
        that will run against live data.
      </Banner>
    </div>
  )
}
