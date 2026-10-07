import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api } from '../lib/api'
import {
  BASEMAPS,
  basemap as resolveBasemap,
  attributionFor,
  DEFAULT_BASEMAP,
  type BasemapId,
} from '../lib/basemaps'
import { modeColour, modeLabel } from '../lib/format'
import type { Journey, Leg, NetworkMapFeature } from '../lib/types'
import { Icon } from './Icons'

interface Segment {
  mode: string
  kind: Leg['kind']
  colour: string
  points: [number, number][]
  title: string
  transfer: boolean
}

/**
 * The map.
 *
 * Real tiles, real routes, real stops: the base map comes from a tile provider
 * (streets, satellite or terrain) and everything drawn on top of it is MoveIn's
 * own data — the journey as the vehicle actually runs it, through the stops it
 * calls at, and optionally the whole modelled network.
 *
 * It moves and zooms the way a map should: drag, pinch, wheel, double-tap, plus
 * buttons for people who would rather tap.  Nothing here is drawn by hand: if
 * it is on the map, it is either a tile from a provider or a coordinate from
 * the engine.
 */
export function MapCanvas({
  journey,
  height = 'fill',
  interactive = true,
  live = false,
  /** Keep this fraction of the height clear for a sheet drawn over the map. */
  reserveBottom = 0,
  /** Show every route in the modelled network underneath the journey. */
  showNetwork = true,
  /** Show the real published bus routes underneath the journey. */
  showRealBus = false,
  /** Draw one published bus route on its own: its shape and its stops. */
  realBusRoute = null,
}: {
  journey: Journey | null
  height?: number | 'fill'
  interactive?: boolean
  live?: boolean
  reserveBottom?: number
  showNetwork?: boolean
  showRealBus?: boolean
  realBusRoute?: {
    shape: [number, number][]
    stops: [number, number][]
    label: string
  } | null
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const baseRef = useRef<L.TileLayer | null>(null)
  const journeyRef = useRef<L.LayerGroup | null>(null)
  const networkRef = useRef<L.LayerGroup | null>(null)
  const realBusRef = useRef<L.LayerGroup | null>(null)
  const realRouteRef = useRef<L.LayerGroup | null>(null)
  const failCount = useRef(0)

  const [style, setStyle] = useState<BasemapId>(DEFAULT_BASEMAP)
  const [zoom, setZoom] = useState(6)
  const [networkOn, setNetworkOn] = useState(showNetwork)
  const [networkCount, setNetworkCount] = useState<number | null>(null)
  const [realBusOn, setRealBusOn] = useState(showRealBus)
  const [realBusCount, setRealBusCount] = useState<number | null>(null)
  const [realBusTotal, setRealBusTotal] = useState<number | null>(null)
  // The published bus layer follows the viewport: at national scale the country
  // holds 24,000 published route-directions, and drawing an arbitrary 400 of
  // them would be a lie about what is on screen.
  const [viewportTick, setViewportTick] = useState(0)
  const [tilesDown, setTilesDown] = useState(false)
  const [scale, setScale] = useState<{ px: number; label: string } | null>(null)

  const segments = useMemo(() => (journey ? journeySegments(journey) : []), [journey])

  // --- the map itself ------------------------------------------------------
  useEffect(() => {
    const node = wrapRef.current
    if (!node || mapRef.current) return

    const map = L.map(node, {
      zoomControl: false,
      attributionControl: false,
      worldCopyJump: true,
      minZoom: 2,
      maxZoom: 19,
      // A planner's map is a browsing surface, not a data editor: keep it light.
      zoomSnap: 0.25,
      wheelPxPerZoomLevel: 120,
      // Moving and zooming by hand, unless the caller wants a still picture.
      dragging: interactive,
      touchZoom: interactive,
      scrollWheelZoom: interactive,
      doubleClickZoom: interactive,
      keyboard: interactive,
      boxZoom: false,
    })
    map.setView([54.5, -3.5], 6)
    mapRef.current = map

    journeyRef.current = L.layerGroup().addTo(map)
    networkRef.current = L.layerGroup().addTo(map)
    realBusRef.current = L.layerGroup().addTo(map)
    realRouteRef.current = L.layerGroup().addTo(map)

    let moved: ReturnType<typeof setTimeout> | undefined
    const sync = () => {
      setZoom(map.getZoom())
      setScale(scaleFor(map))
      // Debounced: a drag fires moveend repeatedly, and each settle asks the
      // API for the routes in view.
      if (moved) clearTimeout(moved)
      moved = setTimeout(() => setViewportTick((tick) => tick + 1), 400)
    }
    map.on('zoom zoomend moveend', sync)
    sync()

    return () => {
      if (moved) clearTimeout(moved)
      map.off('zoom zoomend moveend', sync)
      map.remove()
      mapRef.current = null
      baseRef.current = null
      journeyRef.current = null
      networkRef.current = null
      realBusRef.current = null
      realRouteRef.current = null
    }
  }, [interactive])

  // The container can change size without the window resizing — the sheet takes
  // half the screen, the phone rotates — and Leaflet needs telling.
  useEffect(() => {
    const node = wrapRef.current
    if (!node || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => mapRef.current?.invalidateSize())
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  // --- the base map --------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const config = resolveBasemap(style)
    if (baseRef.current) map.removeLayer(baseRef.current)

    const layer = L.tileLayer(config.url, {
      subdomains: config.subdomains ?? 'abc',
      maxZoom: config.maxZoom,
      attribution: config.attribution,
      // A tile that never arrives must not leave a grey hole: the provider is a
      // third party, and the route underneath is what actually matters.
      errorTileUrl:
        'data:image/svg+xml;utf8,' +
        encodeURIComponent(
          '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#eef1f7"/></svg>',
        ),
      crossOrigin: false,
      className: `map__tiles map__tiles--${style}`,
    })
    layer.on('tileerror', () => {
      failCount.current += 1
      if (failCount.current > 3) setTilesDown(true)
    })
    layer.on('tileload', () => {
      failCount.current = 0
      setTilesDown(false)
    })
    layer.addTo(map)
    baseRef.current = layer

    // Keep the tiles at the bottom, whatever order they were added in.
    const tilePane = map.getPane('tilePane')
    if (tilePane) tilePane.style.zIndex = '200'
  }, [style])

  // --- the journey ---------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    const group = journeyRef.current
    if (!map || !group) return
    group.clearLayers()
    if (!segments.length) return

    const dark = resolveBasemap(style).dark
    for (const segment of segments) {
      if (segment.points.length < 2) continue
      const casing = segment.kind === 'walk' ? 6 : 9.5
      L.polyline(segment.points, {
        color: '#ffffff',
        // On satellite imagery a white casing glares; on paper it separates.
        opacity: dark ? 0.5 : 0.9,
        weight: casing,
        lineCap: 'round',
        lineJoin: 'round',
        interactive: false,
      }).addTo(group)
      L.polyline(segment.points, {
        color: segment.colour,
        weight: segment.kind === 'walk' ? 3.4 : 5.6,
        opacity: segment.kind === 'walk' ? 0.85 : 1,
        dashArray: segment.kind === 'walk' ? '1 8' : undefined,
        lineCap: 'round',
        lineJoin: 'round',
        className: `map__route map__route--${segment.kind}`,
      })
        .bindTooltip(segment.title, { sticky: true, className: 'map__tip' })
        .addTo(group)
    }

    // The stops the vehicle calls at.
    const seen = new Set<string>()
    for (const segment of segments) {
      for (const [index, point] of segment.points.entries()) {
        const key = `${point[0].toFixed(5)},${point[1].toFixed(5)}`
        if (seen.has(key)) continue
        seen.add(key)
        const terminal = index === 0 || index === segment.points.length - 1
        L.circleMarker(point, {
          radius: terminal ? 5 : 3.2,
          color: segment.colour,
          weight: terminal ? 3 : 2,
          fillColor: '#ffffff',
          fillOpacity: 1,
          className: terminal ? 'map__marker' : 'map__stop',
        }).addTo(group)
      }
    }

    // Named ends, and the interchange dots between legs.
    const first = segments[0]
    const last = segments[segments.length - 1]
    const ends: [string, [number, number] | undefined][] = [
      [journey?.legs[0]?.from.name ?? 'Start', first?.points[0]],
      [
        journey?.legs[journey.legs.length - 1]?.to.name ?? 'Destination',
        last?.points[last.points.length - 1],
      ],
    ]
    for (const [name, point] of ends) {
      if (!name || !point) continue
      L.marker(point, {
        interactive: false,
        icon: L.divIcon({
          className: 'map__terminal',
          html: `<span>${escapeHtml(trimName(name))}</span>`,
          iconSize: undefined,
          iconAnchor: [0, 0],
        }),
      }).addTo(group)
    }
    for (const segment of segments.filter((entry) => entry.transfer)) {
      const point = segment.points[0]
      L.circleMarker(point, {
        radius: 4.4,
        color: '#0b0e16',
        weight: 2,
        fillColor: '#ffffff',
        fillOpacity: 1,
        className: 'map__transfer',
      }).addTo(group)
    }

    if (live) {
      const point = last?.points[last.points.length - 1]
      if (point) {
        L.circleMarker(point, {
          radius: 7,
          color: '#4b3aff',
          weight: 2,
          fillColor: '#4b3aff',
          fillOpacity: 0.9,
          className: 'map__live',
        }).addTo(group)
      }
    }

    // Fit the route into the band the sheet is not covering.
    const points = segments.flatMap((segment) => segment.points)
    fitRoute(map, wrapRef.current, points, reserveBottom, false)
    setZoom(map.getZoom())
    setScale(scaleFor(map))
  }, [segments, live, style, reserveBottom])

  // --- the whole network ---------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    const group = networkRef.current
    if (!map || !group) return
    group.clearLayers()
    if (!networkOn) return

    let cancelled = false
    const pane = map.getPane('network') ? 'network' : map.createPane('network') && 'network'
    if (map.getPane('network')) {
      // Under the journey, over the base map.
      ;(map.getPane('network') as HTMLElement).style.zIndex = '350'
    }

    runWhenIdle(() => {
      api
        .networkMap()
        .then((response) => {
          if (cancelled) return
          setNetworkCount(response.count)
          for (const feature of response.features) {
            drawNetworkLine(feature, pane).addTo(group)
          }
        })
        .catch(() => setNetworkCount(null))
    })

    return () => {
      cancelled = true
    }
  }, [networkOn])

  // --- the real published bus network --------------------------------------
  useEffect(() => {
    const map = mapRef.current
    const group = realBusRef.current
    if (!map || !group) return
    group.clearLayers()
    if (!realBusOn) return

    let cancelled = false
    const pane = map.getPane('network') ? 'network' : map.createPane('network') && 'network'
    // The ground the map is showing, plus a margin, as a point and a radius.
    const centre = map.getCenter()
    const radius = Math.max(1000, Math.min(200_000, centre.distanceTo(map.getBounds().getNorthEast())))

    runWhenIdle(() => {
      // A national payload: trim hard, because at this zoom the difference
      // between a road and a straight line is a few pixels.
      api
        .realBusMap({
          lat: centre.lat,
          lon: centre.lng,
          radius_m: Math.round(radius),
          simplify_m: 120,
        })
        .then((response) => {
          if (cancelled) return
          setRealBusCount(response.count)
          setRealBusTotal(response.total_matching || response.count)
          for (const feature of response.features) {
            L.polyline(feature.coordinates as [number, number][], {
              pane,
              color: '#475569',
              weight: 1.1,
              opacity: 0.5,
              lineCap: 'round',
              className: 'map__realbus',
              interactive: false,
            }).addTo(group)
          }
        })
        .catch(() => {
          setRealBusCount(null)
          setRealBusTotal(null)
        })
    })

    return () => {
      cancelled = true
    }
  }, [realBusOn, viewportTick])

  // --- one published route, drawn properly ---------------------------------
  useEffect(() => {
    const map = mapRef.current
    const group = realRouteRef.current
    if (!map || !group || !realBusRoute) return
    group.clearLayers()
    const pane = map.getPane('network') ? 'network' : map.createPane('network') && 'network'
    L.polyline(realBusRoute.shape, {
      pane,
      color: '#0f766e',
      weight: 3.4,
      opacity: 0.9,
      lineCap: 'round',
      className: 'map__realbus map__realbus--one',
      interactive: false,
    }).addTo(group)
    for (const stop of realBusRoute.stops) {
      L.circleMarker(stop, {
        pane,
        radius: 3,
        color: '#0f766e',
        weight: 1.5,
        fillColor: '#ffffff',
        fillOpacity: 1,
        interactive: false,
      }).addTo(group)
    }
    fitRoute(map, wrapRef.current, realBusRoute.shape, reserveBottom, false)
    setZoom(map.getZoom())
    setScale(scaleFor(map))
  }, [realBusRoute, reserveBottom])

  const bottomOffset = `calc(${(reserveBottom * 100).toFixed(1)}% + 12px)`
  const frameStyle = height === 'fill' ? undefined : { height: `${height}px` }

  return (
    <div className="map" style={frameStyle}>
      <div
        className="map__canvas"
        ref={wrapRef}
        data-map-zoom={Math.round(zoom * 4) / 4}
        data-map-basemap={style}
        aria-label={journey ? `Map of the route from ${journey.legs[0]?.from.name}` : 'Map'}
      />

      {tilesDown && (
        <div className="map__warn" role="status">
          <Icon name="alert" size={14} />
          <span>Base map unavailable — showing the route only</span>
        </div>
      )}

      {interactive && (
        <>
          {/* How the world looks, and what is drawn on it. */}
          <div className="map__styles" role="group" aria-label="Map style">
            {BASEMAPS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                className={`map__style-btn${style === entry.id ? ' map__style-btn--on' : ''}`}
                aria-pressed={style === entry.id}
                aria-label={`${entry.label} map`}
                title={`${entry.label} map`}
                onClick={() => setStyle(entry.id)}
              >
                <Icon
                  name={entry.id === 'satellite' ? 'globe' : entry.id === 'terrain' ? 'layers' : 'map'}
                  size={15}
                />
                <span>{entry.short}</span>
              </button>
            ))}
          </div>

          <div className="map__controls" style={{ bottom: bottomOffset }}>
            <button
              type="button"
              className="map__btn"
              onClick={() => mapRef.current?.zoomIn()}
              aria-label="Zoom in"
            >
              <Icon name="plus" size={18} />
            </button>
            <button
              type="button"
              className="map__btn"
              onClick={() => mapRef.current?.zoomOut()}
              aria-label="Zoom out"
            >
              <span className="map__minus" aria-hidden />
            </button>
            <button
              type="button"
              className="map__btn"
              onClick={() => {
                const points = segments.flatMap((segment) => segment.points)
                const map = mapRef.current
                if (!map) return
                fitRoute(map, wrapRef.current, points, reserveBottom, true)
              }}
              aria-label="Fit the route"
            >
              <Icon name="target" size={18} />
            </button>
          </div>

          <button
            type="button"
            className={`map__layer-toggle map__layer-toggle--bus${realBusOn ? ' map__layer-toggle--on' : ''}`}
            aria-pressed={realBusOn}
            style={{
              bottom: `calc(${(reserveBottom * 100).toFixed(1)}% + 92px)`,
            }}
            onClick={() => setRealBusOn((on) => !on)}
          >
            <Icon name="bus" size={15} />
            <span>
              {realBusOn && realBusCount
                ? realBusTotal && realBusTotal > realBusCount
                  ? `${realBusCount} of ${realBusTotal} published`
                  : `${realBusCount} published routes`
                : 'Published buses'}
            </span>
          </button>

          <button
            type="button"
            className={`map__layer-toggle map__layer-toggle--network${networkOn ? ' map__layer-toggle--on' : ''}`}
            aria-pressed={networkOn}
            // Above the attribution and scale, which sit at the very bottom.
            style={{
              bottom: `calc(${(reserveBottom * 100).toFixed(1)}% + 54px)`,
            }}
            onClick={() => setNetworkOn((on) => !on)}
          >
            <Icon name="layers" size={15} />
            <span>
              {networkOn ? (networkCount ? `All ${networkCount} routes` : 'All routes') : 'Journey only'}
            </span>
          </button>
        </>
      )}

      <div className="map__foot" style={{ bottom: bottomOffset }}>
        {scale && (
          <span className="map__scale" aria-hidden>
            <span className="map__scale-bar" style={{ width: scale.px }} />
            <span className="map__scale-text">{scale.label}</span>
          </span>
        )}
        <span className="map__attribution">{attributionFor(style)}</span>
      </div>
    </div>
  )
}

/** The journey as drawable segments: one per leg, through every stop it calls at. */
export function journeySegments(journey: Journey): Segment[] {
  return journey.legs
    .map((leg, index) => {
      const points: [number, number][] = []
      const push = (lat: number | null | undefined, lon: number | null | undefined) => {
        if (lat === null || lat === undefined || lon === null || lon === undefined) return
        const previous = points[points.length - 1]
        if (previous && Math.abs(previous[0] - lat) < 1e-6 && Math.abs(previous[1] - lon) < 1e-6) {
          return
        }
        points.push([lat, lon])
      }

      push(leg.from.lat, leg.from.lon)
      for (const stop of leg.intermediate_stops ?? []) push(stop.lat, stop.lon)
      push(leg.to.lat, leg.to.lon)

      return {
        mode: leg.mode,
        kind: leg.kind,
        colour: modeColour(leg.mode),
        points,
        transfer: index > 0 && leg.kind !== 'walk',
        title:
          leg.kind === 'walk'
            ? `Walk ${Math.round((leg.distance_m ?? 0) / 10) * 10} m`
            : `${leg.route_name ?? modeLabel(leg.mode)}${leg.headsign ? ` to ${leg.headsign}` : ''}`,
      }
    })
    .filter((segment) => segment.points.length >= 2)
}

/**
 * Put the route where the traveller can see it.
 *
 * Two things this has to get right.  The sheet covers the bottom of the map, so
 * the route is fitted into what is left rather than into the middle of the
 * frame.  And a frame with no size — a hidden container, a phone mid-rotation,
 * the first paint before CSS lands — cannot be fitted into at all: asking
 * Leaflet to fit bounds into nothing is how a map ends up at zoom Infinity.
 */
function fitRoute(
  map: L.Map,
  node: HTMLElement | null,
  points: [number, number][],
  reserveBottom: number,
  animate: boolean,
) {
  if (!points.length) return
  const width = node?.clientWidth ?? 0
  const height = node?.clientHeight ?? 0
  const bounds = L.latLngBounds(points).pad(0.08).extend(points[0])
  if (width < 80 || height < 120) {
    map.setView(bounds.getCenter(), Math.min(9, map.getZoom()))
    return
  }
  const bottom = Math.round(height * reserveBottom)
  map.fitBounds(bounds, {
    paddingTopLeft: [28, 64],
    paddingBottomRight: [28, bottom + 24],
    maxZoom: 15,
    animate,
  })
}

/** A network line, thin enough to sit under a journey and still read. */
function drawNetworkLine(feature: NetworkMapFeature, pane: string): L.Polyline {
  return L.polyline(feature.coordinates as [number, number][], {
    pane,
    color: feature.colour.startsWith('#') ? feature.colour : `#${feature.colour}`,
    weight: 1.6,
    opacity: 0.5,
    lineCap: 'round',
    className: `map__network map__network--${feature.mode}`,
    interactive: false,
  })
}

/**
 * Tile and overlay work that is not needed for the first paint.
 *
 * A journey should appear the moment it is asked for; the network underneath it
 * can arrive a moment later.
 */
function runWhenIdle(task: () => void) {
  const idle = (window as { requestIdleCallback?: (cb: () => void) => void }).requestIdleCallback
  if (idle) idle(task)
  else window.setTimeout(task, 40)
}

/** Metres per pixel at this zoom and latitude, in whole kilometres. */
function scaleFor(map: L.Map): { px: number; label: string } {
  const centre = map.getCenter()
  const metresPerPixel = (156543.03392 * Math.cos((centre.lat * Math.PI) / 180)) / Math.pow(2, map.getZoom())
  const options = [0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500]
  const target = 78
  const km = options.find((value) => (value * 1000) / metresPerPixel >= target) ?? 500
  return {
    px: Math.round((km * 1000) / metresPerPixel),
    label: km < 1 ? `${km * 1000} m` : `${km} km`,
  }
}

function trimName(name: string): string {
  return name.length > 26 ? `${name.slice(0, 25)}…` : name
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`)
}
