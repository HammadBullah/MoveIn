/**
 * The base maps.
 *
 * A journey planner is only as convincing as its map, and hand-drawing
 * geography is not something a routing engine can honestly do: the engine knows
 * stops and coordinates, not streets, fields and coastlines.  So the base map
 * is real tiles from real providers, and the thing MoveIn draws on top of it is
 * its own data — the stops, the routes, the journey.
 *
 * Three styles, because people plan differently: streets to find a bus stop,
 * satellite to see where they actually are, terrain to understand a walk.
 * Everything else on the map (the route, the stops, the whole network) is
 * MoveIn's own data, drawn over whichever base is chosen.
 *
 * Attribution is not optional: every provider here is used under a licence that
 * requires it, and it is shown on the map itself rather than buried in a config
 * file.  Swap in a self-hosted or API-keyed provider by adding an entry here --
 * nothing else in the app knows where tiles come from.
 */

export type BasemapId = 'streets' | 'satellite' | 'terrain'

export interface Basemap {
  id: BasemapId
  label: string
  /** Short label for the switcher, which has no room for prose. */
  short: string
  url: string
  /** Subdomains, where the provider shards tiles across them. */
  subdomains?: string[]
  attribution: string
  maxZoom: number
  /** A dark base needs lighter route lines drawn over it. */
  dark?: boolean
}

export const BASEMAPS: Basemap[] = [
  {
    id: 'streets',
    label: 'Streets',
    short: 'Map',
    // OpenStreetMap's standard tiles: every road, path and railway in the
    // world, and the only base that shows bus stops and place names.
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19,
  },
  {
    id: 'satellite',
    label: 'Satellite',
    short: 'Satellite',
    // Esri's World Imagery: aerial photography, so a traveller can see the
    // street they are standing on.
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
    maxZoom: 19,
    dark: true,
  },
  {
    id: 'terrain',
    label: 'Terrain',
    short: 'Terrain',
    // OpenTopoMap: contours and relief, for the part of a journey that happens
    // on foot.
    url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    subdomains: ['a', 'b', 'c'],
    attribution: '© OpenStreetMap contributors, SRTM · © OpenTopoMap (CC-BY-SA)',
    maxZoom: 17,
  },
]

export const DEFAULT_BASEMAP: BasemapId = 'streets'

export function basemap(id: BasemapId): Basemap {
  return BASEMAPS.find((entry) => entry.id === id) ?? BASEMAPS[0]
}

/** Everything the map must credit, for the base currently in use. */
export function attributionFor(id: BasemapId): string {
  return `${basemap(id).attribution} · Routes and stops © MoveIn`
}
