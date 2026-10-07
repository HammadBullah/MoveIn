import type {
  DataSourcesResponse,
  LiveAlert,
  LiveVehicle,
  NetworkSummary,
  Place,
  Preference,
  PriceAlert,
  SavedJourney,
  SearchHistoryEntry,
  SearchResponse,
  StopSuggestion,
  TrackResponse,
} from './types'

/**
 * Every call is relative, so the app works identically behind the Vite dev
 * proxy, the sandbox preview host, or the FastAPI process serving the bundle.
 */
const BASE = '/api'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    })
  } catch (cause) {
    throw new ApiError(
      'Could not reach the MoveIn API. Is the backend running on port 8000?',
      0,
    )
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      /* the body was not JSON; keep the status line */
    }
    throw new ApiError(detail, response.status)
  }
  return (await response.json()) as T
}

// --- device identity ------------------------------------------------------

const DEVICE_KEY_STORAGE = 'movein.deviceKey'

/** A stable, opaque client id, so Phase 1 can store things without accounts. */
export function deviceKey(): string {
  let key = localStorage.getItem(DEVICE_KEY_STORAGE)
  if (!key) {
    key = `web-${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`
    localStorage.setItem(DEVICE_KEY_STORAGE, key)
  }
  return key
}

function withDevice(init?: RequestInit): RequestInit {
  return {
    ...init,
    headers: { ...(init?.headers || {}), 'X-Device-Key': deviceKey() },
  }
}

// --- meta -----------------------------------------------------------------

export const api = {
  health: () => request<Record<string, unknown>>('/health'),

  preferences: () =>
    request<{ default: string; preferences: Preference[] }>('/preferences'),

  dataSources: () => request<DataSourcesResponse>('/data-sources'),

  networkSummary: () => request<NetworkSummary>('/network/summary'),

  searchStops: (q: string, limit = 10) =>
    request<{ query: string; count: number; results: StopSuggestion[] }>(
      `/stops/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),

  nearbyStops: (lat: number, lon: number, radius = 700, limit = 20) =>
    request<{
      region: string | null
      count: number
      stops: (StopSuggestion & { distance_m: number })[]
    }>(`/stops/nearby?lat=${lat}&lon=${lon}&radius_m=${radius}&limit=${limit}`),

  // --- journeys -----------------------------------------------------------

  search: (body: {
    origin: string
    destination: string
    departure?: string | null
    preference: string
    traveller?: Record<string, unknown>
    options?: Record<string, unknown>
    limit?: number
  }) =>
    request<SearchResponse>('/journeys/search', {
      method: 'POST',
      body: JSON.stringify({ ...body, device_key: deviceKey() }),
    }),

  compareEmissions: (origin: string, destination: string) =>
    request<{
      distance_km: number
      origin: Place
      destination: Place
      modes: { mode: string; mode_label: string; g_per_km: number; co2_g: number; co2_label: string }[]
      greenest: string
      note: string
    }>('/journeys/compare-emissions', {
      method: 'POST',
      body: JSON.stringify({ origin, destination }),
    }),

  // --- live ---------------------------------------------------------------

  liveVehicles: (limit = 150, routeId?: string) =>
    request<{
      generated_at: string
      source: string
      note: string
      count: number
      vehicles: LiveVehicle[]
    }>(
      `/live/vehicles?limit=${limit}${routeId ? `&route_id=${encodeURIComponent(routeId)}` : ''}`,
    ),

  liveAlerts: (region?: string) =>
    request<{ count: number; source: string; alerts: LiveAlert[] }>(
      `/live/alerts${region ? `?region=${encodeURIComponent(region)}` : ''}`,
    ),

  track: (body: { journey_id: string; payload: unknown; preference: string }) =>
    request<TrackResponse>(
      '/live/track',
      withDevice({ method: 'POST', body: JSON.stringify({ ...body, device_key: deviceKey() }) }),
    ),

  // --- saved journeys and alerts ------------------------------------------

  saved: () => request<{ count: number; saved: SavedJourney[] }>('/me/saved', withDevice()),

  save: (body: { origin: string; destination: string; preference: string; label?: string }) =>
    request<{ id: number; label: string }>(
      '/me/saved',
      withDevice({ method: 'POST', body: JSON.stringify({ ...body, device_key: deviceKey() }) }),
    ),

  unsave: (id: number) =>
    request<{ deleted: boolean }>(`/me/saved/${id}`, withDevice({ method: 'DELETE' })),

  alerts: () => request<{ count: number; alerts: PriceAlert[] }>('/me/alerts', withDevice()),

  watch: (body: {
    origin: string
    destination: string
    preference: string
    target_price?: number | null
  }) =>
    request<{ id: number; watching: string; current_best_price: number | null }>(
      '/me/alerts',
      withDevice({ method: 'POST', body: JSON.stringify({ ...body, device_key: deviceKey() }) }),
    ),

  unwatch: (id: number) =>
    request<{ deleted: boolean }>(`/me/alerts/${id}`, withDevice({ method: 'DELETE' })),

  checkAlerts: () =>
    request<{
      checked: number
      triggered: number
      results: {
        id: number
        route: string
        price: number
        price_label: string
        previous_price: number | null
        change: number | null
      }[]
      drops: { id: number; route: string; price_label: string }[]
    }>('/me/alerts/check', withDevice()),

  history: (limit = 20) =>
    request<{ count: number; history: SearchHistoryEntry[] }>(
      `/me/history?limit=${limit}`,
      withDevice(),
    ),
}
