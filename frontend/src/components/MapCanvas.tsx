import { useEffect, useMemo, useRef, useState } from 'react'
import { modeColour, modeLabel } from '../lib/format'
import type { Journey, Leg } from '../lib/types'
import { Icon, ModeIcon } from './Icons'

interface Anchor {
  lat: number
  lon: number
  name: string
  mode: string
  kind: Leg['kind']
  role: 'start' | 'end' | 'stop'
}

/**
 * The map.
 *
 * MoveIn draws its own map from the coordinates it already has instead of
 * pulling raster tiles: it renders identically offline, behind the preview
 * proxy and on a bad connection, and it never hands a traveller's journey to a
 * third party.  What matters here is the shape of the route and where it
 * changes, so the drawing is deliberately quiet — thin roads, one route line,
 * no icon confetti.
 */
export function MapCanvas({
  journey,
  height = 300,
  interactive = true,
  live = false,
}: {
  journey: Journey | null
  height?: number
  interactive?: boolean
  live?: boolean
}) {
  const [zoom, setZoom] = useState(0)
  const [pan, setPan] = useState<{ x: number; y: number } | null>(null)
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const [width, setWidth] = useState(720)

  useEffect(() => {
    const node = wrapRef.current
    if (!node) return
    const measure = () => setWidth(node.clientWidth || 720)
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const geometry = useMemo(
    () => (journey ? project(journey, width, height, zoom, pan) : null),
    [journey, width, height, zoom, pan],
  )

  if (!journey || !geometry) {
    return (
      <div className="map map--empty" style={{ height }} ref={wrapRef}>
        <div className="map__roads" aria-hidden />
        <div className="map__empty-note">
          <Icon name="map" size={22} />
          <span>Your route appears here</span>
        </div>
      </div>
    )
  }

  const { anchors, positions, segments } = geometry
  const last = positions[positions.length - 1]

  return (
    <div className="map" style={{ height }} ref={wrapRef}>
      <div className="map__roads" aria-hidden>
        <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
          <defs>
            <pattern id="movein-roads" width="46" height="46" patternUnits="userSpaceOnUse">
              <path d="M46 0H0v46" fill="none" stroke="var(--line)" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width={width} height={height} fill="url(#movein-roads)" />
          <rect width={width} height={height} className="map__wash" />
        </svg>
      </div>

      <svg
        className="map__canvas"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Route from ${anchors[0]?.name} to ${anchors[anchors.length - 1]?.name}`}
        onWheel={
          interactive
            ? (event) => {
                event.preventDefault()
                setZoom((z) => Math.max(0, Math.min(2.2, z - event.deltaY / 600)))
              }
            : undefined
        }
      >
        {segments.map((segment, index) => (
          <g key={index}>
            <path
              className="map__route"
              d={segment.path}
              fill="none"
              stroke={modeColour(segment.mode)}
              strokeWidth={segment.kind === 'walk' ? 3.6 : 6}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={segment.kind === 'walk' ? '1 9' : undefined}
              opacity={segment.kind === 'walk' ? 0.85 : 1}
            >
              <title>{segment.title}</title>
            </path>
          </g>
        ))}

        {segments
          .filter((segment) => segment.transfer)
          .map((segment, index) => (
            <circle
              key={`transfer-${index}`}
              cx={segment.to[0]}
              cy={segment.to[1]}
              r={5}
              fill="#ffffff"
              stroke="var(--ink)"
              strokeWidth={2}
            />
          ))}

        {anchors.map((anchor, index) => (
          <Marker
            key={`${anchor.name}-${index}`}
            anchor={anchor}
            position={positions[index]}
            showLabel={index === 0 || index === anchors.length - 1}
          />
        ))}

        {live && (
          <g className="map__live">
            <circle cx={last[0]} cy={last[1]} r={9} fill="var(--accent)" opacity={0.9} />
            <circle cx={last[0]} cy={last[1]} r={9} fill="none" stroke="var(--accent)" strokeWidth={2}>
              <animate attributeName="r" values="9;20;9" dur="2.6s" repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.5;0;0.5" dur="2.6s" repeatCount="indefinite" />
            </circle>
          </g>
        )}
      </svg>

      {interactive && (
        <div className="map__controls">
          <button
            type="button"
            className="map__btn"
            onClick={() => {
              setZoom(0)
              setPan(null)
            }}
            aria-label="Fit the route"
          >
            <Icon name="target" size={18} />
          </button>
          <button
            type="button"
            className="map__btn"
            onClick={() => setZoom((z) => Math.min(2.4, z + 0.35))}
            aria-label="Zoom in"
          >
            <Icon name="plus" size={18} />
          </button>
          <button
            type="button"
            className="map__btn"
            onClick={() => setZoom((z) => Math.max(0, z - 0.35))}
            aria-label="Zoom out"
          >
            <span className="map__minus" aria-hidden />
          </button>
        </div>
      )}
    </div>
  )
}

function Marker({
  anchor,
  position,
  showLabel,
}: {
  anchor: Anchor
  position: [number, number]
  showLabel: boolean
}) {
  const [x, y] = position
  const terminal = anchor.role !== 'stop'
  return (
    <g className="map__marker">
      {terminal ? (
        <>
          <circle cx={x} cy={y} r={11} fill="#ffffff" stroke="var(--ink)" strokeWidth={3} />
          <circle cx={x} cy={y} r={4} fill={anchor.role === 'start' ? 'var(--accent)' : 'var(--ink)'} />
        </>
      ) : (
        <>
          <circle cx={x} cy={y} r={10} fill="#ffffff" stroke={modeColour(anchor.mode)} strokeWidth={2.4} />
          <g transform={`translate(${x - 7}, ${y - 7}) scale(0.58)`}>
            <ModeIcon mode={anchor.mode} size={24} />
          </g>
        </>
      )}
      {showLabel && (
        <text x={x} y={y + 28} textAnchor="middle" className="map__label">
          {anchor.name.length > 26 ? `${anchor.name.slice(0, 25)}…` : anchor.name}
        </text>
      )}
    </g>
  )
}

/**
 * Project a journey into SVG space.
 *
 * Legs are drawn as gentle arcs rather than straight rulers: a hair of curvature
 * is what separates "a line between two dots" from something that reads as a
 * route on a map.
 */
function project(
  journey: Journey,
  width: number,
  height: number,
  zoom: number,
  pan: { x: number; y: number } | null,
) {
  const anchors: Anchor[] = []
  journey.legs.forEach((leg, index) => {
    const isLast = index === journey.legs.length - 1
    if (leg.from.lat !== null && leg.from.lon !== null) {
      anchors.push({
        lat: leg.from.lat,
        lon: leg.from.lon,
        name: leg.from.name || 'Start',
        mode: leg.mode,
        kind: leg.kind,
        role: anchors.length === 0 ? 'start' : 'stop',
      })
    }
    if (isLast && leg.to.lat !== null && leg.to.lon !== null) {
      anchors.push({
        lat: leg.to.lat,
        lon: leg.to.lon,
        name: leg.to.name || 'Destination',
        mode: leg.mode,
        kind: leg.kind,
        role: 'end',
      })
    }
  })
  if (anchors.length < 2) return null

  const lats = anchors.map((a) => a.lat)
  const lons = anchors.map((a) => a.lon)
  let minLat = Math.min(...lats)
  let maxLat = Math.max(...lats)
  let minLon = Math.min(...lons)
  let maxLon = Math.max(...lons)
  if (maxLat - minLat < 1e-4) {
    minLat -= 6e-4
    maxLat += 6e-4
  }
  if (maxLon - minLon < 1e-4) {
    minLon -= 1e-3
    maxLon += 1e-3
  }

  const pad = 52
  const meanLat = (minLat + maxLat) / 2
  const lonScale = Math.cos((meanLat * Math.PI) / 180)
  const spanLat = maxLat - minLat
  const spanLon = (maxLon - minLon) * lonScale
  const base = Math.min((width - pad * 2) / spanLon, (height - pad * 2) / spanLat)
  const scale = base * (1 + zoom * 0.6)
  const centreLon = (minLon + maxLon) / 2
  const centreLat = (minLat + maxLat) / 2
  const drift = pan ?? { x: 0, y: 0 }

  const positions: [number, number][] = anchors.map((anchor) => [
    width / 2 + (anchor.lon - centreLon) * lonScale * scale + drift.x,
    height / 2 - (anchor.lat - centreLat) * scale + drift.y,
  ])

  const segments = journey.legs.map((leg, index) => {
    const from = positions[index]
    const to = positions[index + 1] ?? positions[index]
    return {
      path: arc(from, to, (index % 2 ? -1 : 1) * 0.05),
      mode: leg.mode,
      kind: leg.kind,
      to,
      transfer: index > 0 && index < journey.legs.length - 1 && leg.kind !== 'walk',
      title:
        leg.kind === 'walk'
          ? `Walk ${Math.round((leg.distance_m ?? 0) / 10) * 10} m`
          : `${leg.route_name ?? modeLabel(leg.mode)}${leg.headsign ? ` to ${leg.headsign}` : ''}`,
    }
  })

  return { anchors, positions, segments }
}

function arc(from: [number, number], to: [number, number], bend: number): string {
  const [x0, y0] = from
  const [x1, y1] = to
  const dx = x1 - x0
  const dy = y1 - y0
  const length = Math.hypot(dx, dy) || 1
  const normal: [number, number] = [-dy / length, dx / length]
  const offset = length * bend
  const cx = (x0 + x1) / 2 + normal[0] * offset
  const cy = (y0 + y1) / 2 + normal[1] * offset
  return `M${x0},${y0} Q${cx},${cy} ${x1},${y1}`
}
