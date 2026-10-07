import { useEffect, useState } from 'react'
import { Button, Section } from '../components/Controls'
import { Icon } from '../components/Icons'
import { api } from '../lib/api'
import type { CoverageResponse, DataSourcesResponse, NetworkSummary, RealBusCoverage } from '../lib/types'

/**
 * Where the numbers come from.
 *
 * A transport app that hides its sources is asking to be trusted. This screen
 * prints the real files, the compiled layer, and — importantly — how much of
 * each city MoveIn can actually plan through, including the parts it cannot.
 */
export function DataScreen({ onBack, onOpenBus }: { onBack: () => void; onOpenBus?: () => void }) {
  const [sources, setSources] = useState<DataSourcesResponse | null>(null)
  const [network, setNetwork] = useState<NetworkSummary | null>(null)
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null)
  const [realBus, setRealBus] = useState<RealBusCoverage | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      api.dataSources(),
      api.networkSummary(),
      api.networkCoverage(),
      api.realBusCoverage().catch(() => null),
    ])
      .then(([data, summary, cover, bus]) => {
        setSources(data)
        setNetwork(summary)
        setCoverage(cover)
        setRealBus(bus)
      })
      .catch(() => setError('The API is not reachable, so the provenance cannot be shown.'))
  }, [])

  return (
    <div className="screen screen--data">
      <header className="detail__head">
        <button type="button" className="icon-btn" onClick={onBack} aria-label="Back">
          <Icon name="back" size={20} />
        </button>
        <span className="detail__route">Data &amp; sources</span>
        <span className="detail__spacer" />
      </header>

      {error && (
        <div className="notice notice--error">
          <Icon name="alert" size={16} />
          <span>{error}</span>
        </div>
      )}

      {realBus && (
        <Section title="Real UK bus routes">
          <div className="card card--pad">
            <div className="data__figures">
              <span>
                <strong>{realBus.routes.toLocaleString()}</strong>
                <em>routes</em>
              </span>
              <span>
                <strong>{realBus.services.toLocaleString()}</strong>
                <em>services</em>
              </span>
              <span>
                <strong>{realBus.operators}</strong>
                <em>operators</em>
              </span>
              <span>
                <strong>{realBus.named_stops.toLocaleString()}</strong>
                <em>named stops</em>
              </span>
            </div>
            <p className="small">{realBus.note}</p>
            <p className="muted tiny">{realBus.coverage_note}</p>
            <p className="muted tiny">{realBus.attribution}</p>
            {onOpenBus && <Button onClick={onOpenBus}>Browse the bus routes</Button>}
          </div>
        </Section>
      )}

      {sources && (
        <Section title="What MoveIn holds">
          <div className="card card--pad">
            <p className="small">{sources.headline}</p>
            <ul className="source-list">
              {sources.sources.map((source) => (
                <li key={source.key} className={`source source--${source.kind}`}>
                  <span className="source__kind">{source.kind}</span>
                  <span className="source__body">
                    <strong>{source.name}</strong>
                    {source.detail && <em>{source.detail}</em>}
                    {(source.rows || source.licence) && (
                      <span className="source__meta">
                        {source.rows ? `${source.rows.toLocaleString()} rows` : ''}
                        {source.rows && source.licence ? ' · ' : ''}
                        {source.licence ?? ''}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
            {network && (
              <p className="muted tiny">
                Compiled network: {network.stops} stops, {network.patterns} patterns,{' '}
                {network.trips.toLocaleString()} trips, {network.operators} operators
                {network.service_window.start
                  ? ` · ${network.service_window.start} → ${network.service_window.end}`
                  : ''}
              </p>
            )}
          </div>
        </Section>
      )}

      {coverage && (
        <Section title="Coverage, city by city">
          <div className="card card--pad">
            <p className="small">{coverage.headline}</p>
            <div className="coverage">
              <div className="coverage__head">
                <span>City</span>
                <span>Real stops</span>
                <span>Plannable</span>
                <span>Share</span>
              </div>
              {coverage.regions.slice(0, 12).map((row) => (
                <div key={row.region} className="coverage__row">
                  <span className="coverage__city">{row.name}</span>
                  <span>{row.real_stops_held.toLocaleString()}</span>
                  <span>{row.modelled_stops}</span>
                  <span className="coverage__pct">
                    {row.coverage_pct === null ? '—' : `${row.coverage_pct.toFixed(2)}%`}
                  </span>
                </div>
              ))}
            </div>
            <p className="muted tiny">{coverage.note}</p>
          </div>
        </Section>
      )}

      {sources && (
        <Section title="Live feeds">
          <div className="card card--list">
            {sources.live_feeds.map((feed) => (
              <div key={feed.key} className="feed">
                <span className={`feed__dot feed__dot--${feed.status === 'connected' ? 'on' : 'off'}`} />
                <span className="feed__body">
                  <strong>{feed.name}</strong>
                  <em>{feed.provides ?? feed.publisher ?? ''}</em>
                  <span className="feed__status">{feed.status}</span>
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      <p className="muted tiny data__note">
        MoveIn bundles real NaPTAN stops, real rail station records and real operator registers. The timetable
        layer is compiled from published service patterns rather than downloaded wholesale, because the
        national bus feeds are not reachable from this deployment — that difference is stated here rather than
        hidden.
      </p>
    </div>
  )
}
