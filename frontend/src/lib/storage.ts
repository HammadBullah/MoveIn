/**
 * The things a traveller tells the app once and expects it to remember.
 *
 * All of it is local to the device.  MoveIn's Phase 1 has no accounts: saved
 * places, recent journeys and preferences are the traveller's own data on their
 * own browser, which is also why they survive a refresh without a login.
 */

export interface SavedPlace {
  id: string
  name: string
  icon: 'home' | 'work' | 'study' | 'heart'
  /** What to type into the search box: a stop, a town, or "lat,lon". */
  query: string
}

export interface RecentJourney {
  id: string
  origin: string
  destination: string
  at: number
}

export interface Profile {
  name: string
  email: string
  preference: string
  maxWalkMinutes: number
  modes: string[]
  accessible: boolean
  notifications: boolean
}

const KEYS = {
  places: 'movein.places',
  recents: 'movein.recents',
  profile: 'movein.profile',
}

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* private mode, or storage full: the app still works for this session */
  }
}

export const ALL_MODES = [
  'rail',
  'bus',
  'coach',
  'tram',
  'metro',
  'taxi',
  'ridehail',
  'ferry',
  'walk',
  'cycle',
] as const

export const DEFAULT_PROFILE: Profile = {
  name: 'Traveller',
  email: '',
  preference: 'best_value',
  maxWalkMinutes: 15,
  modes: [...ALL_MODES],
  accessible: false,
  notifications: true,
}

// --- saved places ---------------------------------------------------------

const SEED_PLACES: SavedPlace[] = [
  { id: 'home', name: 'Home', icon: 'home', query: '' },
  { id: 'work', name: 'Work', icon: 'work', query: '' },
  { id: 'study', name: 'University', icon: 'study', query: '' },
]

export function loadPlaces(): SavedPlace[] {
  const stored = read<SavedPlace[]>(KEYS.places, [])
  if (stored.length) return stored
  return SEED_PLACES
}

export function savePlaces(places: SavedPlace[]) {
  write(KEYS.places, places)
}

export function upsertPlace(place: SavedPlace): SavedPlace[] {
  const places = loadPlaces()
  const index = places.findIndex((p) => p.id === place.id)
  if (index >= 0) places[index] = place
  else places.push(place)
  savePlaces(places)
  return places
}

export function removePlace(id: string): SavedPlace[] {
  const places = loadPlaces().filter((p) => p.id !== id)
  savePlaces(places)
  return places
}

// --- recent journeys ------------------------------------------------------

export function loadRecents(): RecentJourney[] {
  return read<RecentJourney[]>(KEYS.recents, [])
}

export function rememberJourney(origin: string, destination: string): RecentJourney[] {
  if (!origin || !destination) return loadRecents()
  const recents = loadRecents().filter(
    (r) => !(r.origin === origin && r.destination === destination),
  )
  recents.unshift({
    id: `${origin}→${destination}`,
    origin,
    destination,
    at: Date.now(),
  })
  const trimmed = recents.slice(0, 8)
  write(KEYS.recents, trimmed)
  return trimmed
}

// --- profile --------------------------------------------------------------

export function loadProfile(): Profile {
  return { ...DEFAULT_PROFILE, ...read<Partial<Profile>>(KEYS.profile, {}) }
}

export function saveProfile(profile: Profile) {
  write(KEYS.profile, profile)
}

/**
 * Where the traveller is, as a search string the API understands.
 *
 * The API accepts ``lat,lon`` directly, so there is no need to reverse-geocode
 * a position into a street name we would only be guessing at.
 */
export function currentLocation(): Promise<{ query: string; label: string }> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('This browser cannot share a location.'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords
        resolve({
          query: `${latitude.toFixed(5)},${longitude.toFixed(5)}`,
          label: 'Current location',
        })
      },
      () => reject(new Error('Location permission was not granted.')),
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 120000 },
    )
  })
}
