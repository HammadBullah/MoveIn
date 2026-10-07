import { useCallback, useEffect, useMemo, useState } from 'react'
import { FilterSheet, DEFAULT_FILTERS, type Filters } from './components/FilterSheet'
import { Icon } from './components/Icons'
import { HomeScreen, type HomeValue } from './screens/HomeScreen'
import { ResultsScreen } from './screens/ResultsScreen'
import { DetailScreen } from './screens/DetailScreen'
import { LiveScreen } from './screens/LiveScreen'
import { ModeScreen } from './screens/ModeScreen'
import { CompareScreen } from './screens/CompareScreen'
import { AlertsScreen } from './screens/AlertsScreen'
import { ProfileScreen } from './screens/ProfileScreen'
import { PlacesScreen } from './screens/PlacesScreen'
import { TripsScreen } from './screens/TripsScreen'
import { DataScreen } from './screens/DataScreen'
import { api, ApiError } from './lib/api'
import { loadProfile, rememberJourney, saveProfile, type Profile } from './lib/storage'
import type { Journey, SearchResponse } from './lib/types'

type Tab = 'home' | 'trips' | 'alerts' | 'profile'
type View =
  | 'home'
  | 'results'
  | 'detail'
  | 'live'
  | 'compare'
  | 'mode'
  | 'places'
  | 'profile'
  | 'data'

const TABS: { id: Tab; label: string; icon: string; view: View }[] = [
  { id: 'home', label: 'Home', icon: 'home', view: 'home' },
  { id: 'trips', label: 'Trips', icon: 'map', view: 'home' },
  { id: 'alerts', label: 'Alerts', icon: 'bell', view: 'home' },
  { id: 'profile', label: 'Profile', icon: 'user', view: 'home' },
]

const EMPTY_QUERY: HomeValue = {
  origin: '',
  originLabel: '',
  destination: '',
  destinationLabel: '',
  when: 'now',
  preference: 'best_value',
}

/** The hash is the address of a screen: shareable, refreshable, testable. */
function parseHash(): { view: View; tab: Tab; params: URLSearchParams } {
  const raw = window.location.hash.replace(/^#\/?/, '')
  const [path, search] = raw.split('?')
  const params = new URLSearchParams(search ?? '')
  if (path === 'trips' || path === 'alerts' || path === 'profile') {
    return { view: 'home', tab: path as Tab, params }
  }
  const known: View[] = ['home', 'results', 'detail', 'live', 'compare', 'mode', 'places', 'profile', 'data']
  const view = (known.includes(path as View) ? path : 'home') as View
  return { view, tab: 'home', params }
}

export default function App() {
  const [tab, setTab] = useState<Tab>(() => parseHash().tab)
  const [view, setView] = useState<View>(() => parseHash().view)
  const [params, setParams] = useState<URLSearchParams>(() => parseHash().params)
  const [query, setQuery] = useState<HomeValue>(EMPTY_QUERY)
  const [filters, setFilters] = useState<Filters>({ ...DEFAULT_FILTERS })
  const [profile, setProfile] = useState<Profile>(loadProfile)
  const [result, setResult] = useState<SearchResponse | null>(null)
  const [selected, setSelected] = useState<Journey | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sheetHeight, setSheetHeight] = useState<'half' | 'full'>('half')
  const [filterOpen, setFilterOpen] = useState(false)
  const [modeKind, setModeKind] = useState<'cheapest' | 'fastest'>('cheapest')
  const [alertMade, setAlertMade] = useState(false)
  const [savingAlert, setSavingAlert] = useState(false)

  // The profile decides the defaults the search starts from.
  useEffect(() => {
    setQuery((current) => ({ ...current, preference: profile.preference }))
    setFilters((current) => ({
      ...current,
      modes: profile.modes.length ? profile.modes : current.modes,
      maxWalkMinutes: profile.maxWalkMinutes,
      accessible: profile.accessible,
    }))
  }, [profile])

  const navigate = useCallback((next: View, nextParams?: Record<string, string>) => {
    const search = nextParams ? `?${new URLSearchParams(nextParams).toString()}` : ''
    window.location.hash = `#/${next}${search}`
    setView(next)
    setParams(new URLSearchParams(nextParams ?? {}))
  }, [])

  const runSearch = useCallback(
    async (input: HomeValue, extra?: { filters?: Filters; arriveBy?: string | null; maxPrice?: number | null; maxChanges?: number }) => {
      const active = extra?.filters ?? filters
      const modes = active.modes.length && active.modes.length < 10 ? active.modes : undefined
      setLoading(true)
      setError(null)
      setView('results')
      window.location.hash = '#/results'
      try {
        const response = await api.search({
          origin: input.origin,
          destination: input.destination,
          departure: input.when === 'now' ? null : input.when,
          arrive_by: extra?.arriveBy ?? null,
          preference: input.preference,
          max_walk_minutes: active.maxWalkMinutes,
          options: {
            modes,
            max_price: extra?.maxPrice ?? active.maxPrice,
            max_legs: Math.min(8, (extra?.maxChanges ?? active.maxChanges) + 1),
            step_free_only: active.accessible,
          },
          limit: 14,
        })
        setResult(response)
        rememberJourney(response.origin.label, response.destination.label)
        window.dispatchEvent(new Event('movein:recents'))
      } catch (cause) {
        setResult(null)
        setError(
          cause instanceof ApiError ? cause.message : 'Something went wrong planning that journey.',
        )
      } finally {
        setLoading(false)
      }
    },
    [filters],
  )

  // Deep links (and the render test) can ask for a search directly.
  useEffect(() => {
    const { view: initialView, params: initialParams } = parseHash()
    if (initialView !== 'results') return
    const from = initialParams.get('from')
    const to = initialParams.get('to')
    if (!from || !to) return
    const next: HomeValue = {
      origin: from,
      originLabel: from,
      destination: to,
      destinationLabel: to,
      when: initialParams.get('when') ?? 'now',
      preference: initialParams.get('pref') ?? 'best_value',
    }
    setQuery(next)
    void runSearch(next)
    // run once on mount: the hash is the entry point
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const onHash = () => {
      const parsed = parseHash()
      setTab(parsed.tab)
      setView(parsed.view)
      setParams(parsed.params)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const goTab = (next: Tab) => {
    setTab(next)
    setView('home')
    window.location.hash = `#/${next}`
  }

  const longWalkCount = useMemo(
    () => (result?.journeys ?? []).filter((journey) => journey.walk_comfort === 'long').length,
    [result],
  )

  const createAlert = async (target: number | null) => {
    if (!result) return
    setSavingAlert(true)
    try {
      await api.watch({
        origin: result.origin.label,
        destination: result.destination.label,
        preference: 'cheapest',
        target_price: target,
      })
      setAlertMade(true)
    } catch {
      /* the detail screen keeps its button state if this fails */
    } finally {
      setSavingAlert(false)
    }
  }

  const body = () => {
    if (view === 'results') {
      return (
        <ResultsScreen
          result={result}
          loading={loading}
          error={error}
          fromLabel={result?.origin.label ?? (query.originLabel || query.origin)}
          toLabel={result?.destination.label ?? (query.destinationLabel || query.destination)}
          when={query.when}
          preference={query.preference}
          sheetHeight={sheetHeight}
          longWalkCount={longWalkCount}
          onPreference={(next) => {
            const updated = { ...query, preference: next }
            setQuery(updated)
            void runSearch(updated)
          }}
          onSheetHeight={setSheetHeight}
          onBack={() => goTab('home')}
          onOpenJourney={(journey) => {
            setSelected(journey)
            setAlertMade(false)
            navigate('detail')
          }}
          onCompare={() => navigate('compare')}
          onFilters={() => setFilterOpen(true)}
          onRetry={() => runSearch(query)}
        />
      )
    }

    if (view === 'detail' && selected) {
      return (
        <DetailScreen
          journey={selected}
          saved={alertMade}
          saving={savingAlert}
          onBack={() => navigate('results')}
          onStart={() => navigate('live')}
          onCompare={() => navigate('compare')}
          onSaveAlert={createAlert}
        />
      )
    }

    if (view === 'live' && selected) {
      return (
        <LiveScreen
          journey={selected}
          onBack={() => navigate('detail')}
          onSwitch={(journey) => {
            setSelected(journey)
            navigate('live')
          }}
          onOpenJourney={(journey) => {
            setSelected(journey)
            navigate('detail')
          }}
        />
      )
    }

    if (view === 'compare') {
      return (
        <CompareScreen
          result={result}
          fromLabel={result?.origin.label ?? query.originLabel}
          toLabel={result?.destination.label ?? query.destinationLabel}
          onBack={() => navigate('results')}
          onOpenJourney={(journey) => {
            setSelected(journey)
            navigate('detail')
          }}
        />
      )
    }

    if (view === 'mode') {
      return (
        <ModeScreen
          mode={modeKind}
          from={query.origin}
          to={query.destination}
          initialModes={filters.modes}
          onBack={() => navigate('home')}
          onRun={(input) => {
            const next: HomeValue = {
              origin: input.origin,
              originLabel: input.originLabel,
              destination: input.destination,
              destinationLabel: input.destinationLabel,
              when: 'now',
              preference: input.preference,
            }
            setQuery(next)
            setFilterOpen(false)
            void runSearch(next, {
              filters: {
                ...filters,
                modes: input.modes,
                maxWalkMinutes: input.maxWalkMinutes,
                maxChanges: input.maxChanges,
              },
              arriveBy: input.arriveBy,
              maxPrice: input.maxPrice,
            })
          }}
        />
      )
    }

    if (view === 'places') {
      return (
        <PlacesScreen
          onBack={() => navigate(tab === 'home' ? 'home' : 'profile')}
          onPlan={(from, to) => {
            setQuery((current) => ({
              ...current,
              origin: from || current.origin,
              originLabel: from || current.originLabel,
              destination: to || current.destination,
              destinationLabel: to || current.destinationLabel,
            }))
            navigate('home')
          }}
        />
      )
    }

    if (view === 'data') {
      return <DataScreen onBack={() => navigate('profile')} />
    }

    if (tab === 'trips') {
      return (
        <TripsScreen
          active
          onPlan={(from, to) => {
            setQuery((current) => ({
              ...current,
              origin: from,
              originLabel: from,
              destination: to,
              destinationLabel: to,
            }))
            if (from && to) {
              const next = { ...query, origin: from, originLabel: from, destination: to, destinationLabel: to }
              void runSearch(next)
            } else {
              goTab('home')
            }
          }}
        />
      )
    }

    if (tab === 'alerts') return <AlertsScreen active />

    if (tab === 'profile') {
      return (
        <ProfileScreen
          profile={profile}
          onChange={(next) => {
            setProfile(next)
            saveProfile(next)
          }}
          onOpenPlaces={() => navigate('places')}
          onOpenData={() => navigate('data')}
        />
      )
    }

    return (
      <HomeScreen
        value={query}
        onChange={(next) => setQuery((current) => ({ ...current, ...next }))}
        onSearch={() => runSearch(query)}
        onOpenMode={(kind) => {
          setModeKind(kind)
          navigate('mode')
        }}
        onOpenPlaces={() => navigate('places')}
      />
    )
  }

  const chrome = view === 'home'

  return (
    <div className="app">
      <div className="phone">
        <main className={`viewport viewport--${view}`} key={`${view}-${params.toString()}`}>
          {body()}
        </main>

        {chrome && (
          <nav className="tabbar" aria-label="Main">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`tabbar__item${tab === item.id ? ' tabbar__item--on' : ''}`}
                onClick={() => goTab(item.id)}
                aria-current={tab === item.id}
              >
                <Icon name={item.icon} size={21} />
                <span>{item.label}</span>
              </button>
            ))}
          </nav>
        )}
      </div>

      {filterOpen && (
        <FilterSheet
          open
          filters={filters}
          onClose={() => setFilterOpen(false)}
          onApply={(next) => {
            setFilters(next)
            setFilterOpen(false)
            const updated = { ...query, preference: next.preferences[0] ?? query.preference }
            setQuery(updated)
            void runSearch(updated, { filters: next })
          }}
        />
      )}
    </div>
  )
}
