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

interface Waypoint {
  lat: number
  lon: number
  name: string
  mode: string
  kind: Leg['kind']
  /** The vehicle calls here but the traveller does not get off. */
  via: boolean
}

/**
 * The map.
 *
 * MoveIn draws its own map from the coordinates it already has instead of
 * pulling raster tiles: it renders identically offline, behind the preview
 * proxy and on a bad connection, and it never hands a traveller's journey to a
 * third party.
 *
 * The important consequence is that everything on it is *real data*: the line
 * is the vehicle's actual path through the stops it calls at, not a ruler
 * between the ends. A coach from Nottingham to Birmingham bends through Derby
 * because that is where it goes; a train draws the shape of its route because
 * that is where the railway runs. Geography the engine does not know — streets,
 * fields — is left out rather than invented, so the frame carries a scale bar,
 * a graticule and the places the network actually serves.
 */
export function MapCanvas({
  journey,
  height = 300,
  interactive = true,
  live = false,
  /** Keep this fraction of the height clear for a sheet drawn over the map. */
  reserveBottom = 0,
}: {
  journey: Journey | null
  /** A pixel height, or the word `fill` to take the height of the container. */
  height?: number | 'fill'
  interactive?: boolean
  live?: boolean
  reserveBottom?: number
}) {
  const [zoom, setZoom] = useState(0)
  const [pan, setPan] = useState<{ x: number; y: number } | null>(null)
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const [box, setBox] = useState({ width: 0, height: 0 })

  // Measuring, not sizing.  In `fill` mode the element's height comes from CSS
  // (it is inset in its container); this only reads the result to build the
  // viewBox.  Setting the height from the measurement would be circular, and
  // would leave the map stuck at whatever it measured first.
  const fill = height === 'fill'
  useEffect(() => {
    const node = wrapRef.current
    if (!node) return
    const measure = () => setBox({ width: node.clientWidth, height: node.clientHeight })
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  // A map that fills its frame stays a map whatever the frame is: the sheet
  // over it can be half open or full, and the route keeps its own room.
  const width = box.width || 720
  // The height actually drawn: the measured frame, or a sane default before the
  // first measurement lands (and if the container is ever hidden).
  const measured = fill ? box.height : height
  const drawHeight = measured >= 80 ? measured : 300

  // A new journey is a new frame: never leave the previous route's zoom behind.
  useEffect(() => {
    setZoom(0)
    setPan(null)
  }, [journey?.id])

  const geometry = useMemo(
    () => (journey ? project(journey, width, drawHeight, zoom, pan, reserveBottom) : null),
    [journey, width, drawHeight, zoom, pan, reserveBottom],
  )

  if (!journey || !geometry) {
    return (
      <div
        className={`map map--empty${fill ? ' map--fill' : ''}`}
        style={fill ? undefined : { height: drawHeight }}
        ref={wrapRef}
      >
        <div className="map__base" aria-hidden>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none">
            <defs>
              <pattern id="movein-empty-streets" width="4" height="6" patternUnits="userSpaceOnUse">
                <path d="M4 0H0v6" fill="none" stroke="var(--map-street)" strokeWidth="0.5" />
              </pattern>
            </defs>
            <rect width="100" height="100" fill="var(--map-land)" />
            <rect width="100" height="100" fill="url(#movein-empty-streets)" />
          </svg>
        </div>
        <div className="map__empty-note">
          <Icon name="map" size={22} />
          <span>Your route appears here</span>
        </div>
      </div>
    )
  }

  const {
    anchors,
    positions,
    segments,
    waypoints,
    waypointPositions,
    graticule,
    scaleBar,
    baseline,
  } = geometry
  const last = positions[positions.length - 1]

  // Name the places on the map, but never into each other: three names stacked
  // on one dot is worse than two names.  The ends are laid out first -- they are
  // the two names the traveller is looking for -- then the stops in between,
  // each given a side that does not collide, and dropped if neither does.
  const entries = waypoints.map((point, index) => ({
    point,
    position: waypointPositions[index],
    terminal: !point.via,
    offset: point.via ? (index % 2 ? 15 : -11) : 30,
    priority: point.via ? 1 : 0,
  }))
  // The end markers are obstacles in their own right: a stop name printed over
  // the dot it belongs to is unreadable.
  const obstacles = entries
    .filter((entry) => entry.terminal)
    .map((entry) => circleBox(entry.position[0], entry.position[1], 13))
  const namedWaypoints = layoutLabels(entries, obstacles)

  return (
    <div
      className={`map${fill ? ' map--fill' : ''}`}
      style={fill ? undefined : { height: drawHeight }}
      ref={wrapRef}
    >
      {/* The base layer.  This is a stylised frame, not a claim about roads:
          the engine's geography is stops and coordinates, so the texture is
          deliberately abstract -- a regular grid at two scales plus a wash, to
          give the route something to be a route across. */}
      <div className="map__base" aria-hidden>
        <svg viewBox={`0 0 ${width} ${drawHeight}`} preserveAspectRatio="none">
          <defs>
            <pattern id="movein-streets" width="30" height="30" patternUnits="userSpaceOnUse">
              <path d="M30 0H0v30" fill="none" stroke="var(--map-street)" strokeWidth="1.3" />
            </pattern>
            <pattern id="movein-roads" width="150" height="150" patternUnits="userSpaceOnUse">
              <path d="M150 0H0v150" fill="none" stroke="var(--map-road)" strokeWidth="2.6" />
            </pattern>
            <radialGradient id="movein-vignette" cx="50%" cy="38%" r="78%">
              <stop offset="55%" stopColor="#ffffff" stopOpacity="0" />
              <stop offset="100%" stopColor="#c9d0e4" stopOpacity="0.34" />
            </radialGradient>
          </defs>
          <rect width={width} height={drawHeight} fill="var(--map-land)" />
          <rect width={width} height={drawHeight} fill="url(#movein-streets)" />
          <rect width={width} height={drawHeight} fill="url(#movein-roads)" />
          <rect width={width} height={drawHeight} fill="url(#movein-vignette)" />
        </svg>
      </div>

      <svg
        className="map__canvas"
        viewBox={`0 0 ${width} ${drawHeight}`}
        role="img"
        aria-label={`Route from ${anchors[0]?.name} to ${anchors[anchors.length - 1]?.name}`}
        onWheel={
          interactive
            ? (event) => {
                event.preventDefault()
                setZoom((z) => Math.max(0, Math.min(2.4, z - event.deltaY / 600)))
              }
            : undefined
        }
      >
        {/* The graticule is the only invented thing on the map, and it is
            labelled, so it reads as a frame rather than as geography. */}
        <g className="map__graticule" aria-hidden>
          {graticule.meridians.map((line) => (
            <line key={`m${line.value}`} x1={line.x} y1={0} x2={line.x} y2={drawHeight} />
          ))}
          {graticule.parallels.map((line) => (
            <line key={`p${line.value}`} x1={0} y1={line.y} x2={width} y2={line.y} />
          ))}
        </g>

        <g className="map__grid-labels" aria-hidden>
          {graticule.meridians.map((line) => (
            <text key={`ml${line.value}`} x={line.x + 4} y={baseline - 7} className="map__grid-label">
              {formatLon(line.value)}
            </text>
          ))}
          {graticule.parallels.slice(0, 4).map((line) => (
            <text
              key={`pl${line.value}`}
              x={6}
              y={line.y - 5}
              className="map__grid-label"
            >
              {formatLat(line.value)}
            </text>
          ))}
        </g>

        {/* Every stop the vehicle calls at, so the line has something to be a
            path through. */}
        <g aria-hidden>
          {waypoints.map((stop, index) => {
            const [x, y] = waypointPositions[index]
            return (
              <circle
                key={`${stop.name}-${index}`}
                cx={x}
                cy={y}
                r={stop.via ? 3.1 : 4.4}
                className="map__stop"
                stroke={modeColour(stop.mode)}
              />
            )
          })}
        </g>

        {/* The places the vehicle calls at, named.  A route with unlabelled
            dots is a diagram; a route with names on it is a map. */}
        <g aria-hidden>
          {namedWaypoints.map((entry, index) => (
            <text
              key={`${entry.point.name}-${index}`}
              x={entry.position[0]}
              y={entry.position[1] + entry.offset}
              textAnchor="middle"
              className={entry.terminal ? 'map__label' : 'map__stop-label'}
            >
              {entry.point.name.length > 22 ? `${entry.point.name.slice(0, 21)}…` : entry.point.name}
            </text>
          ))}
        </g>

        {/* The line itself: a white casing under the mode colour, so where two
            legs share a road the later one still reads. */}
        <g>
          {segments.map((segment, index) => (
            <path
              key={`casing-${index}`}
              className="map__route-casing"
              d={segment.path}
              fill="none"
              strokeWidth={segment.kind === 'walk' ? 6 : 9}
            />
          ))}
          {segments.map((segment, index) => (
            <path
              key={`route-${index}`}
              className="map__route"
              d={segment.path}
              fill="none"
              stroke={modeColour(segment.mode)}
              strokeWidth={segment.kind === 'walk' ? 3.4 : 5.6}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={dashFor(segment.mode, segment.kind)}
              opacity={segment.kind === 'walk' ? 0.8 : 1}
            >
              <title>{segment.title}</title>
            </path>
          ))}
        </g>

        {segments
          .filter((segment) => segment.transfer)
          .map((segment, index) => (
            <circle
              key={`transfer-${index}`}
              cx={segment.to[0]}
              cy={segment.to[1]}
              r={4.6}
              fill="#ffffff"
              stroke="var(--ink)"
              strokeWidth={2}
            />
          ))}

        {anchors.map((anchor, index) => (
          <Marker key={`${anchor.name}-${index}`} anchor={anchor} position={positions[index]} />
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

      {/* How far, on the map, in units a person uses. */}
      <div
        className="map__scale"
        style={{ bottom: `calc(${(reserveBottom * 100).toFixed(1)}% + 12px)` }}
        aria-hidden
      >
        <span className="map__scale-bar" style={{ width: scaleBar.px }} />
        <span className="map__scale-text">{scaleBar.label}</span>
      </div>

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

/** A bus stop is a stop; a ferry is a crossing; a walk is a dotted line. */
function dashFor(mode: string, kind: Leg['kind']): string | undefined {
  if (kind === 'walk') return '1 8'
  if (kind === 'on_demand') return '10 6'
  if (mode === 'ferry' || mode === 'air') return '14 7'
  return undefined
}

/**
 * Give each label a place on the map, or leave it off.
 *
 * Labels are rectangles at this point: estimate the box the text will occupy
 * and refuse to draw one that would sit on top of another.  Terminal names go
 * down first so that, when space runs out, it is the intermediate stops that
 * give way.
 */
function layoutLabels<
  T extends {
    point: { name: string }
    position: [number, number]
    offset: number
    priority: number
    terminal: boolean
  },
>(entries: T[], obstacles: Box[] = []): T[] {
  const placed: Box[] = [...obstacles]
  const kept: T[] = []
  const ordered = [...entries].sort((a, b) => a.priority - b.priority)

  for (const entry of ordered) {
    const text = entry.point.name
    if (!text) continue
    const shown = text.length > 22 ? `${text.slice(0, 21)}…` : text
    const halfWidth = (shown.length * 4.9) / 2
    let offset = entry.offset
    let box = boxFor(entry.position, halfWidth, offset)

    if (overlaps(box, placed) && entry.priority > 0) {
      // An intermediate stop tries the other side before giving up its name.
      offset = -offset
      box = boxFor(entry.position, halfWidth, offset)
    }
    if (overlaps(box, placed)) continue

    placed.push(box)
    kept.push({ ...entry, offset })
  }
  return kept
}

interface Box {
  x0: number
  y0: number
  x1: number
  y1: number
}

function circleBox(x: number, y: number, radius: number): Box {
  return { x0: x - radius, y0: y - radius, x1: x + radius, y1: y + radius }
}

function boxFor(position: [number, number], halfWidth: number, offset: number): Box {
  const [x, y] = position
  return { x0: x - halfWidth, x1: x + halfWidth, y0: y + offset - 9, y1: y + offset + 3 }
}

function overlaps(a: Box, placed: Box[]): boolean {
  return placed.some(
    (b) => a.x0 < b.x1 + 3 && a.x1 > b.x0 - 3 && a.y0 < b.y1 + 3 && a.y1 > b.y0 - 3,
  )
}

function formatLat(value: number): string {
  return `${Math.abs(value).toFixed(1)}°${value >= 0 ? 'N' : 'S'}`
}

function formatLon(value: number): string {
  return `${Math.abs(value).toFixed(1)}°${value >= 0 ? 'E' : 'W'}`
}

function Marker({ anchor, position }: { anchor: Anchor; position: [number, number] }) {
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
    </g>
  )
}

/**
 * Project a journey into SVG space.
 *
 * The route is the vehicle's own path: the line runs from stop to stop through
 * every place it calls at, which is what makes a coach route bend through Derby
 * and a railway hold the shape of its line. Only walking legs get a little
 * curvature, because a walk is off-network and the straight line is the honest
 * approximation.
 */
function project(
  journey: Journey,
  width: number,
  height: number,
  zoom: number,
  pan: { x: number; y: number } | null,
  reserveBottom = 0,
) {
  const anchors: Anchor[] = []
  const waypoints: Waypoint[] = []
  const legPaths: Waypoint[][] = []

  journey.legs.forEach((leg, index) => {
    const isLast = index === journey.legs.length - 1
    const points: Waypoint[] = []

    const push = (lat: number | null | undefined, lon: number | null | undefined, way: Waypoint) => {
      if (lat === null || lat === undefined || lon === null || lon === undefined) return
      const previous = points[points.length - 1]
      if (previous && Math.abs(previous.lat - lat) < 1e-6 && Math.abs(previous.lon - lon) < 1e-6) {
        return
      }
      points.push({ ...way, lat, lon })
    }

    push(leg.from.lat, leg.from.lon, {
      lat: 0,
      lon: 0,
      name: leg.from.name || 'Start',
      mode: leg.mode,
      kind: leg.kind,
      via: false,
    })

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

    // The stops in between are the route.  A vehicle calls at each of them, so
    // drawing straight past them would be a drawing of a journey nobody takes.
    for (const stop of leg.intermediate_stops ?? []) {
      if (!stop.name) continue
      push(stop.lat, stop.lon, {
        lat: 0,
        lon: 0,
        name: stop.name,
        mode: leg.mode,
        kind: leg.kind,
        via: true,
      })
    }

    push(leg.to.lat, leg.to.lon, {
      lat: 0,
      lon: 0,
      name: leg.to.name || 'Destination',
      mode: leg.mode,
      kind: leg.kind,
      via: false,
    })

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

    legPaths.push(points)
    for (const point of points) {
      const previous = waypoints[waypoints.length - 1]
      if (
        previous &&
        Math.abs(previous.lat - point.lat) < 1e-6 &&
        Math.abs(previous.lon - point.lon) < 1e-6
      ) {
        continue
      }
      waypoints.push(point)
    }
  })

  if (anchors.length < 2 || waypoints.length < 2) return null

  const lats = waypoints.map((w) => w.lat)
  const lons = waypoints.map((w) => w.lon)
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

  // Whatever is drawn at the bottom of the frame is behind the sheet, so the
  // route is fitted into the band that is actually visible -- and the padding
  // is a share of that band, or a short band has no room left for a route.
  const reserved = Math.round(height * Math.max(0, Math.min(0.9, reserveBottom)))
  const usableHeight = Math.max(96, height - reserved)
  const padX = Math.max(14, Math.round(Math.min(46, width * 0.07)))
  const padY = Math.max(13, Math.round(Math.min(58, usableHeight * 0.17)))
  const meanLat = (minLat + maxLat) / 2
  const lonScale = Math.cos((meanLat * Math.PI) / 180)
  const spanLat = maxLat - minLat
  const spanLon = (maxLon - minLon) * lonScale
  const base = Math.min((width - padX * 2) / spanLon, (usableHeight - padY * 2) / spanLat)
  const scale = base * (1 + zoom * 0.6)
  const centreLon = (minLon + maxLon) / 2
  const centreLat = (minLat + maxLat) / 2
  const drift = pan ?? { x: 0, y: 0 }

  // Latitude drives the y axis, so this is pixels per degree of latitude --
  // and one degree of latitude is 111.32 km anywhere on Earth.
  const projectPoint = (lat: number, lon: number): [number, number] => [
    width / 2 + (lon - centreLon) * lonScale * scale + drift.x,
    usableHeight / 2 - (lat - centreLat) * scale + drift.y,
  ]

  const positions: [number, number][] = anchors.map((anchor) =>
    projectPoint(anchor.lat, anchor.lon),
  )
  const waypointPositions: [number, number][] = waypoints.map((point) =>
    projectPoint(point.lat, point.lon),
  )

  // Paths are built from the projected stop positions, in order.
  let cursor = 0
  const segments = journey.legs.map((leg, index) => {
    const points = legPaths[index].map((point) => projectPoint(point.lat, point.lon))
    cursor += legPaths[index].length
    const path =
      leg.kind === 'walk' || points.length === 2
        ? polyline(points, leg.kind === 'walk' ? 0.06 : 0)
        : polyline(points, 0)
    return {
      path,
      mode: leg.mode,
      kind: leg.kind,
      to: positions[index + 1] ?? positions[index],
      transfer: index > 0 && index < journey.legs.length - 1 && leg.kind !== 'walk',
      title:
        leg.kind === 'walk'
          ? `Walk ${Math.round((leg.distance_m ?? 0) / 10) * 10} m`
          : `${leg.route_name ?? modeLabel(leg.mode)}${leg.headsign ? ` to ${leg.headsign}` : ''}`,
    }
  })

  return {
    anchors,
    positions,
    segments,
    waypoints,
    waypointPositions,
    /** Where the visible band ends: labels and the scale bar live above it. */
    baseline: usableHeight,
    graticule: buildGraticule(minLon, maxLon, minLat, maxLat, projectPoint, width, height),
    scaleBar: buildScaleBar(scale, width),
  }
}

/** A straight polyline through the stops, with optional gentle bowing. */
function polyline(points: [number, number][], bend: number): string {
  if (!points.length) return ''
  if (points.length === 1) return `M${points[0][0]},${points[0][1]}`
  if (points.length === 2 && bend) {
    const [x0, y0] = points[0]
    const [x1, y1] = points[1]
    const dx = x1 - x0
    const dy = y1 - y0
    const length = Math.hypot(dx, dy) || 1
    const offset = length * bend
    const cx = (x0 + x1) / 2 + (-dy / length) * offset
    const cy = (y0 + y1) / 2 + (dx / length) * offset
    return `M${x0},${y0} Q${cx},${cy} ${x1},${y1}`
  }
  return points.map(([x, y], index) => `${index ? 'L' : 'M'}${x},${y}`).join(' ')
}

function niceStep(span: number): number {
  const raw = span / 4
  const steps = [0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1, 2, 5]
  return steps.find((step) => step >= raw) ?? 5
}

function buildGraticule(
  minLon: number,
  maxLon: number,
  minLat: number,
  maxLat: number,
  projectPoint: (lat: number, lon: number) => [number, number],
  width: number,
  height: number,
) {
  const lonStep = niceStep(maxLon - minLon)
  const latStep = niceStep(maxLat - minLat)
  const meridians: { value: number; x: number }[] = []
  const parallels: { value: number; y: number }[] = []

  for (let lon = Math.ceil(minLon / lonStep) * lonStep; lon <= maxLon; lon += lonStep) {
    const [x] = projectPoint((minLat + maxLat) / 2, lon)
    if (x >= 0 && x <= width) meridians.push({ value: Number(lon.toFixed(4)), x })
  }
  for (let lat = Math.ceil(minLat / latStep) * latStep; lat <= maxLat; lat += latStep) {
    const [, y] = projectPoint(lat, (minLon + maxLon) / 2)
    if (y >= 0 && y <= height) parallels.push({ value: Number(lat.toFixed(4)), y })
  }
  return { meridians, parallels }
}

/** A scale bar in whole kilometres, at a width a person can read. */
function buildScaleBar(pxPerDegree: number, width: number) {
  const pxPerKm = pxPerDegree / 111.32
  const target = width * 0.26
  const candidates = [1, 2, 5, 10, 20, 25, 50, 100]
  const km = candidates.find((value) => value * pxPerKm >= target * 0.55) ?? 100
  return { px: Math.round(km * pxPerKm), label: `${km} km` }
}
