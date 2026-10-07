/** Shapes returned by the MoveIn API. */

export type Mode =
  | 'walk'
  | 'cycle'
  | 'bus'
  | 'coach'
  | 'rail'
  | 'tram'
  | 'metro'
  | 'ferry'
  | 'taxi'
  | 'ridehail'
  | 'air'

export interface Place {
  id: string
  label: string
  lat: number
  lon: number
  kind: 'region' | 'stop' | 'coordinate' | string
  mode?: string
  region?: string
  alternatives?: StopSuggestion[]
}

export interface StopSuggestion {
  id: string
  name: string
  mode: string
  region?: string
  lat?: number
  lon?: number
  interchange?: boolean
  distance_m?: number
  route_count?: number
}

export interface OperatorRef {
  code: string
  name: string
  colour: string
  mode?: string
  url?: string
}

export interface LegEndpoint {
  id: string
  name: string
  lat: number | null
  lon: number | null
  mode?: string
  region?: string
  interchange?: boolean
  step_free?: boolean
}

export interface Leg {
  kind: 'transit' | 'walk' | 'on_demand'
  mode: Mode
  mode_label: string
  instruction: string
  from: LegEndpoint
  to: LegEndpoint
  // transit
  route_id?: string
  route_name?: string
  route_long_name?: string
  headsign?: string
  trip_id?: string
  operator?: OperatorRef
  departure?: string
  arrival?: string
  departure_s?: number
  arrival_s?: number
  duration_s?: number
  distance_km?: number
  stops_count?: number
  intermediate_stops?: { id: string; name: string }[]
  fare?: string
  fare_amount?: number
  co2_g?: number
  step_free?: boolean
  colour?: string
  delay_s?: number
  live?: boolean
  // walk / on demand
  distance_m?: number
  start_time?: string
  end_time?: string
  direction?: string
}

export interface Ticket {
  operator: string
  operator_name: string
  label: string
  price: number
  price_label: string
  covers_legs: number[]
  saving: number
}

export interface FareBreakdown {
  total: number
  total_label: string
  currency: string
  tickets: Ticket[]
  leg_prices: {
    index: number
    mode: string
    operator: string
    distance_km: number
    base_price: number
    paid: number
    product: string
    product_label: string
    covered_by: string
  }[]
  saving_vs_singles: number
  notes: string[]
}

export interface Journey {
  id: string
  rank: number
  departure: string
  arrival: string
  departure_time: string
  arrival_time: string
  arrival_day_offset: number
  duration_s: number
  duration_label: string
  price: number
  price_label: string
  changes: number
  changes_label: string
  walking_m: number
  walking_s: number
  walking_label: string
  /** The worst single walk in the journey: the number that decides if it is doable. */
  longest_walk_s: number
  longest_walk_label: string
  walk_comfort: 'comfortable' | 'long'
  walk_warning: boolean
  co2_g: number
  co2_label: string
  reliability: number
  reliability_label: string
  step_free: boolean
  modes: string[]
  mode_label: string
  route_label: string
  operators: OperatorRef[]
  transit_legs: number
  is_walk_only: boolean
  archetypes: string[]
  archetype_labels: string[]
  notes: string[]
  scores: Record<string, number>
  score: number
  legs: Leg[]
  fare: FareBreakdown
  summary: string
  polyline: [number, number][]
}

export interface Preference {
  id: string
  label: string
  description: string
  icon: string
  weights: Record<string, number>
}

export interface SearchResponse {
  origin: Place
  destination: Place
  departure: string
  preference: string
  preference_label: string
  traveller: Record<string, unknown>
  count: number
  journeys: Journey[]
  archetypes: Record<string, string>
  typical: {
    cheapest?: { id: string; price: number; price_label: string }
    fastest?: { id: string; duration_s: number; duration_label: string }
    lowest_emissions?: { id: string; co2_g: number; co2_label: string }
  }
  nearby_destinations: StopSuggestion[]
  /** Set when the app had to stretch a limit to show anything at all. */
  notice: {
    kind: string
    message: string
    requested_walk_minutes?: number
    shortest_walk_minutes?: number
  } | null
  diagnostics: Record<string, number | string>
}

export interface NetworkSummary {
  stops: number
  patterns: number
  trips: number
  stop_routes: number
  transfers: number
  routes_by_mode: Record<string, number>
  stops_by_region: Record<string, number>
  operators: number
  service_window: { start: string | null; end: string | null }
}

export interface LiveVehicle {
  vehicle_id: string
  trip_id: string
  route_id: string
  route_name: string
  mode: string
  headsign: string
  operator_code: string
  lat: number
  lon: number
  bearing: number
  speed_mps: number
  delay_s: number
  delay_label: string
  occupancy: string
  next_stop: { id: string; name: string }
  progress: number
  recorded_at: string
  source: string
}

export interface LiveAlert {
  id: string
  header: string
  description: string
  severity: 'info' | 'warning' | 'severe'
  mode: string | null
  route_ids: string[]
  stop_ids: string[]
  regions: string[]
  starts_at: string
  ends_at: string
  source: string
}

export interface DataSource {
  key: string
  name: string
  url: string | null
  licence: string | null
  kind: 'real' | 'compiled' | 'generated'
  rows: number | null
  detail: string | null
}

export interface DataSourcesResponse {
  headline: string
  sources: DataSource[]
  live_feeds: {
    key: string
    name: string
    provides?: string
    publisher?: string
    licence?: string
    adapter?: string
    format?: string
    auth?: string
    status: string
  }[]
  network: Record<string, number>
  service_window: { start: string | null; end: string | null }
}

export interface SavedJourney {
  id: number
  label: string
  origin: { id: string; label: string; lat: number; lon: number }
  destination: { id: string; label: string; lat: number; lon: number }
  preference: string
  created_at: string
}

export interface PriceAlert {
  id: number
  origin: string
  destination: string
  preference: string
  target_price: number | null
  baseline_price: number | null
  last_price: number | null
  last_checked_at: string | null
  triggered_at: string | null
  active: boolean
}

export interface SearchHistoryEntry {
  origin: string
  destination: string
  preference: string
  when: string
  results: number
  best_price: number | null
  searched_at: string
}

export interface TrackResponse {
  journey_id: string
  checked_at: string
  status: string
  delay_s: number
  delay_label: string
  legs: {
    trip_id: string
    route_name: string
    scheduled_departure: string
    expected_departure: string
    scheduled_arrival: string
    expected_arrival: string
    delay_s: number
    delay_label: string
    status: string
  }[]
  advice: string
}
