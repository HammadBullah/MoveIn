import { modeColour, modeIcon } from '../lib/format'
import type { Journey, Leg } from '../lib/types'

interface Point {
  lat: number
  lon: number
  label: string
  mode: string
  kind: 'transit' | 'walk' | 'on_demand'
}

/**
 * A self-contained schematic map.
 *
 * It draws the journey from the real coordinates MoveIn already has rather than
 * pulling raster tiles, so it renders identically offline, behind the sandbox
 * preview proxy, and on a slow connection — and it never leaks a request to a
 * third-party tile server.
 */
export function MapView({ journey, width = 720, height = 320 }: { journey: Journey; width?: number; height?: number }) {
  const points: Point[] = []
  for (const leg of journey.legs) {
    pushPoint(points, leg.from.lat, leg.from.lon, leg.from.name, leg.mode, leg.kind)
    pushPoint(points, leg.to.lat, leg.to.lon, leg.to.name, leg.mode, leg.kind)
  }

  if (points.length < 2) {
    return (
      <div className="map" style={{ padding: '2rem', textAlign: 'center' }}>
        <span className="muted small">Nothing to draw for this journey.</span>
      </div>
    )
  }

  const pad = 34
  const lats = points.map((p) => p.lat)
  const lons = points.map((p) => p.lon)
  let minLat = Math.min(...lats)
  let maxLat = Math.max(...lats)
  let minLon = Math.min(...lons)
  let maxLon = Math.max(...lons)

  // Keep the aspect ratio honest: longitude degrees are shorter than latitude
  // ones at UK latitudes, so scale x by cos(mean latitude).
  const meanLat = (minLat + maxLat) / 2
  const lonScale = Math.cos((meanLat * Math.PI) / 180)
  const spanLat = Math.max(maxLat - minLat, 1e-4)
  const spanLon = Math.max((maxLon - minLon) * lonScale, 1e-4)
  const scale = Math.min((width - pad * 2) / spanLon, (height - pad * 2) / spanLat)

  const project = (lat: number, lon: number): [number, number] => {
    const x = pad + ((lon - minLon) * lonScale) * scale + ((width - pad * 2) - spanLon * scale) / 2
    const y =
      height - pad - (lat - minLat) * scale - ((height - pad * 2) - spanLat * scale) / 2
    return [x, y]
  }

  const paths = journey.legs.map((leg) => {
    const from = project(leg.from.lat ?? 0, leg.from.lon ?? 0)
    const to = project(leg.to.lat ?? 0, leg.to.lon ?? 0)
    return { from, to, mode: leg.mode, kind: leg.kind, label: leg.instruction }
  })

  const markers = dedupe(points).map((point) => {
    const [x, y] = project(point.lat, point.lon)
    return { x, y, point }
  })

  return (
    <div className="map">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Map of the journey from ${points[0].label} to ${points[points.length - 1].label}`}
      >
        <defs>
          <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
            <path d="M 32 0 L 0 0 0 32" fill="none" stroke="currentColor" strokeOpacity="0.07" />
          </pattern>
        </defs>
        <rect width={width} height={height} fill="url(#grid)" />

        {paths.map((path, index) => (
          <line
            key={index}
            x1={path.from[0]}
            y1={path.from[1]}
            x2={path.to[0]}
            y2={path.to[1]}
            stroke={modeColour(path.mode)}
            strokeWidth={path.kind === 'walk' ? 3 : 5}
            strokeLinecap="round"
            strokeDasharray={path.kind === 'walk' ? '2 6' : undefined}
            opacity={path.kind === 'walk' ? 0.75 : 0.95}
          >
            <title>{path.label}</title>
          </line>
        ))}

        {markers.map(({ x, y, point }, index) => (
          <g key={`${point.label}-${index}`}>
            <circle
              cx={x}
              cy={y}
              r={12}
              fill="var(--surface)"
              stroke={modeColour(point.mode)}
              strokeWidth={2.5}
            />
            <text x={x} y={y + 4} textAnchor="middle" fontSize="11">
              {modeIcon(point.mode)}
            </text>
            <text
              x={x}
              y={y - 17}
              textAnchor="middle"
              fontSize="11"
              fontWeight="650"
              fill="currentColor"
            >
              {trim(point.label)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

function pushPoint(
  list: Point[],
  lat: number | null,
  lon: number | null,
  label: string,
  mode: string,
  kind: Leg['kind'],
) {
  if (lat === null || lon === null) return
  list.push({ lat, lon, label, mode, kind })
}

function dedupe(points: Point[]): Point[] {
  const out: Point[] = []
  for (const point of points) {
    const last = out[out.length - 1]
    if (last && Math.abs(last.lat - point.lat) < 1e-5 && Math.abs(last.lon - point.lon) < 1e-5) {
      continue
    }
    out.push(point)
  }
  return out
}

function trim(label: string, max = 22): string {
  if (!label) return ''
  return label.length > max ? `${label.slice(0, max - 1)}…` : label
}
