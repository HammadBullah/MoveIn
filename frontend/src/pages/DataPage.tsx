import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Banner, Loading, Pill, Stat } from '../components/Primitives'
import type { DataSourcesResponse, NetworkSummary } from '../lib/types'

/**
 * The provenance page.
 *
 * MoveIn's whole pitch is that it merges data sources, so it would be dishonest
 * to hide which parts are real published data and which parts are compiled.
 * This page says so plainly, in the product itself rather than only in a README.
 */
export function DataPage() {
  const [data, setData] = useState<DataSourcesResponse | null>(null)
  const [network, setNetwork] = useState<NetworkSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.dataSources(), api.networkSummary()])
      .then(([sources, summary]) => {
        setData(sources)
        setNetwork(summary)
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Unavailable'))
  }, [])

  if (error) return <Banner kind="error">{error}</Banner>
  if (!data || !network) return <Loading rows={3} />

  const real = data.sources.filter((source) => source.kind === 'real')
  const compiled = data.sources.filter((source) => source.kind !== 'real')

  return (
    <div className="stack" style={{ gap: '1.1rem' }}>
      <div>
        <h1>Where this data comes from</h1>
        <p className="muted" style={{ margin: 0, maxWidth: '70ch' }}>
          {data.headline}
        </p>
      </div>

      <Banner kind="info">
        <strong>Read this first.</strong> The stop geography, the railway stations and the
        operator registry are real published datasets, bundled unmodified. The{' '}
        <em>timetable</em> — departure times, frequencies, journey times and fare products —
        is <strong>compiled deterministically</strong> from that real geography, because the
        live national timetable hosts are not reachable from this deployment. Nothing here is
        invented: every stop is a real stop at its real coordinates, served by a real operator.
        Swapping in live GTFS/BODS feeds is a configuration change, not a rewrite.
      </Banner>

      <div className="stat-grid">
        <Stat value={network.stops.toLocaleString()} label="Stops & stations" />
        <Stat value={network.routes_by_mode.rail ?? 0} label="Rail routes" />
        <Stat value={(network.routes_by_mode.bus ?? 0) + (network.routes_by_mode.coach ?? 0)} label="Bus & coach routes" />
        <Stat value={network.trips.toLocaleString()} label="Daily trips" />
        <Stat value={network.operators} label="Operators" />
        <Stat value={Object.keys(network.stops_by_region).length} label="Regions" />
      </div>

      <div className="section-title">Real, published datasets</div>
      <div className="stack" style={{ gap: '0.5rem' }}>
        {real.map((source) => (
          <div className="card card--pad" key={source.key}>
            <div className="row row--between">
              <strong>{source.name}</strong>
              <Pill tone="green">real data</Pill>
            </div>
            <div className="muted small">{source.detail}</div>
            {source.rows != null && (
              <div className="tiny muted" style={{ marginTop: '0.3rem' }}>
                {source.rows.toLocaleString()} rows bundled in{' '}
                <code>{source.name}</code>
              </div>
            )}
            <div className="row small" style={{ marginTop: '0.4rem' }}>
              {source.licence && <Pill tone="navy">{source.licence}</Pill>}
              {source.url && (
                <a href={source.url} target="_blank" rel="noreferrer" className="tiny">
                  view source ↗
                </a>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="section-title">Compiled from the above</div>
      <div className="stack" style={{ gap: '0.5rem' }}>
        {compiled.map((source) => (
          <div className="card card--pad" key={source.key}>
            <div className="row row--between">
              <strong>{source.name}</strong>
              <Pill tone="amber">compiled</Pill>
            </div>
            <div className="muted small">{source.detail}</div>
            {source.rows != null && (
              <div className="tiny muted" style={{ marginTop: '0.3rem' }}>
                {source.rows.toLocaleString()} trips in the compiled feed
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="section-title">Live feeds: adapters ready, hosts unreachable</div>
      <p className="muted small" style={{ marginTop: 0 }}>
        Each of these has a working adapter path in <code>backend/app/ingest/</code> and is
        wired into the same interface the running system uses. Point MoveIn at them and the
        compiled layer is replaced end to end.
      </p>
      <div className="card" style={{ overflow: 'hidden' }}>
        <table className="table">
          <thead>
            <tr>
              <th>Feed</th>
              <th>Publisher</th>
              <th>Format</th>
              <th>Adapter</th>
            </tr>
          </thead>
          <tbody>
            {data.live_feeds.map((feed) => (
              <tr key={feed.key}>
                <td>
                  <strong>{feed.name}</strong>
                  <div className="tiny muted">{feed.provides}</div>
                </td>
                <td className="small">{feed.publisher}</td>
                <td className="tiny muted">
                  {feed.format}
                  {feed.auth && <div>auth: {feed.auth}</div>}
                </td>
                <td className="tiny mono">
                  {feed.adapter}
                  <div className="tiny muted" style={{ fontFamily: 'inherit' }}>
                    {feed.status}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">Service window in the loaded feed</div>
      <p className="muted small" style={{ margin: 0 }}>
        {data.service_window.start} → {data.service_window.end}
      </p>
    </div>
  )
}
