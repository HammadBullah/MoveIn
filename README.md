# MoveIn

One place to plan a journey across every UK mode — rail, bus, coach, tram,
metro, ferry, taxi — with the trade-offs made explicit instead of hidden.

Type where you are, where you are going, when, and what you care about. MoveIn
returns real options priced properly: the National Express coach that is £3.25
rather than the £7.70 train, the train that gets you there two hours earlier,
the route that keeps you dry, and the one that emits a tenth of the carbon.

**Phase 1 prototype.** Everything described here is implemented and running:
the data pipeline, the journey engine, the fare engine, the ranking model, the
HTTP API, the web app, the tests and the documentation. Accounts, social
features and national-scale deployment are deliberately out of scope (see
[Roadmap](#roadmap)).

---

## What is in the box

| Area | What exists |
| --- | --- |
| Data | 42,502 real NaPTAN named stops, 10,009 real rail TIPLOCs, 69 real train operating companies, 116,104 real regional access points, 83 compiled corridors over 403 modelled stops |
| Engine | Multi-criteria RAPTOR with Pareto labelling, walking access and interchange, on-demand first/last mile, and a service-day filter |
| Fares | Ticket-combination optimiser: singles, off-peak, advance, operator day tickets, contactless caps, railcard/student/child/season discounts |
| Ranking | Seven traveller preferences, four normalised criteria, archetype labelling (Cheapest, Fastest, Fewest changes, Least walking, Lowest emissions, Best value, Step-free) |
| Walking | A 15-minute promise by default, a stated limit the traveller can tighten (10 / 15 / 20 minutes), and longer walks returned as a labelled choice rather than as the answer |
| API | 25 endpoints over FastAPI, OpenAPI documented at `/api/docs` |
| App | React + TypeScript, built mobile-first: Home, Results, Journey details, Live, Cheapest/Fastest, price comparison, Saved places, Trips, Price alerts, Profile and Data — a map-first layout with a draggable sheet and a bottom nav, drawn from real coordinates with no map tile dependency |
| Quality | 171 tests covering ingestion, the compiler, the graph, the engine, fares, ranking and every endpoint, plus a DOM render test that mounts the real app against the real API |

---

## Running it

Two processes: the API and the web app. The web app proxies `/api` to the API,
so the browser only ever talks to one origin.

```bash
# 1. Backend
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

# 2. Real source data (already committed under backend/data/raw; this re-fetches it)
.venv/bin/python scripts/fetch_real_data.py

# 3. Compile the network and load the database
.venv/bin/python -c "
from backend.app.ingest.network_compiler import NetworkCompiler, save_compiled
from backend.app.config import get_settings
s = get_settings()
save_compiled(NetworkCompiler(s.data_raw_dir).compile(), s.data_generated_dir)
"
.venv/bin/python scripts/seed_db.py --rebuild

# 4. Serve
.venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

```bash
# 5. Frontend, in a second shell
cd frontend
npm install
npm run dev            # http://localhost:5173, proxying /api to :8000
```

Useful commands:

```bash
.venv/bin/python -m pytest backend/tests -q     # the whole suite
.venv/bin/python scripts/seed_db.py --status    # what is in the database
cd frontend && npm run build                    # production bundle into frontend/dist
cd frontend && npm run test:render             # renders the real app in a DOM (API must be up)
```

The API serves the built SPA from `frontend/dist` when it exists, so a single
process can serve the whole product in a deployment.

---

## Data: what is real and what is compiled

This matters more than any other paragraph in this file, so it is stated plainly
in the product too (`/api/data-sources`, and the **Data** screen in the app).

**Real, downloaded, and used as published:**

* **NaPTAN** (DfT, Open Government Licence v3.0) — 42,502 named stops and
  116,104 regional access points. Coordinates, names and stop identities are
  exactly as published; MoveIn groups the individual bays into the stop area a
  passenger thinks in and tidies the node labels for display.
* **Rail TIPLOC register** (via `itsleeds/UK2GTFS-data`) — 10,009 real timing
  points with real coordinates, and the CRS codes for 74 stations in the
  modelled network.
* **ATOC agency list** — 69 real train operating companies: names, codes,
  colours and websites.

**Compiled, and not presented as anything else:**

* **The timetable layer.** There is no complete, openly downloadable UK GTFS
  feed that this environment can reach, so departure times, headways, run times
  and dwell times are compiled deterministically from the real stop geography
  and the real operator registry. The service window rolls with the compile
  date (30 days back, 335 forward), bank holidays are computed by rule, and the
  same seed always produces the same timetable — but it is a *generated*
  timetable, not a downloaded one.
* **Fares** follow the real published structures of each mode (the England £3
  bus cap, TfL tube pricing, tapered rail fares with off-peak and advance
  products, per-operator coach pricing, taxi meters) at the level of policy,
  not at the level of every fare record.

`docs/DATA_SOURCES.md` lists every file, licence, publisher and adapter in
detail. The live feeds MoveIn cannot reach from this sandbox (BODS
timetables/fares/SIRI-VM, TfL Unified API, NPTG, OSM) each have a named adapter
in `backend/app/ingest/` and a fixture-driven contract test, so switching to
live data is a configuration change rather than a rewrite.

---

## How it works

```
                       ┌──────────────────────────────────────────┐
   real CSV sources ──▶│ backend/app/ingest                       │
   (NaPTAN, TIPLOC,    │  naptan.py  registry.py  geo.py          │
    ATOC agencies)     │  network_compiler.py  ──▶ GTFS + JSON    │
                       └───────────────┬──────────────────────────┘
                                       ▼
                       ┌──────────────────────────────────────────┐
                       │ backend/app/db  (SQLAlchemy + SQLite)    │
                       │  stops routes trips stop_times fares ... │
                       └───────────────┬──────────────────────────┘
                                       ▼
   POST /api/journeys/search ──▶ app/engine
                                  graph.py    patterns, transfers, index
                                  search.py   multi-criteria RAPTOR
                                  fares.py    ticket combination optimiser
                                  journeys.py assembly + ranking
                                       │
                                       ▼
                       ┌──────────────────────────────────────────┐
                       │ FastAPI routes + serialisers             │
                       └───────────────┬──────────────────────────┘
                                       ▼
                       ┌──────────────────────────────────────────┐
                       │ React app: mobile, map-first, shell      │
                       └──────────────────────────────────────────┘
```

**Search** is RAPTOR generalised to several criteria at once. Rather than one
"earliest arrival" label per stop it keeps a Pareto frontier of up to eight
labels — arrival, fare, changes, walking — so the cheapest journey is never
discarded because a faster one existed. Boarding is decided by the time the
vehicle leaves *this* stop, the service-day filter means a Sunday search cannot
sell a weekday timetable, and interchanges are the real walking connections
between stops from NaPTAN geography, recorded as visible steps in the itinerary.

**Fares** price the journey, not just the legs: the optimiser compares every
single on its own ticket, an operator day ticket, a contactless cap, and the
mixed combination, then reports the tickets bought and which legs each covers.
The breakdown always reconciles to the total.

**Ranking** min-max normalises price, time, changes and walking across the
candidate set, weights them by the traveller's preference, and scores the result
out of 100 where higher is better. Each journey is labelled with the trade-off
it wins, so the results screen is a set of genuine choices rather than one
"best" answer.

**Walking is a decision, not a footnote.** In practice nobody accepts a long
walk to save 20 minutes, so MoveIn promises a 15-minute maximum by default, lets
the traveller tighten it to 10 minutes (or open it up entirely), and measures
the *longest single walk* rather than the total — because a 30-minute stroll in
four pieces is fine and one 25-minute march to a coach stop is not. Options
beyond the promise are still returned, flagged, in their own collapsed section;
they never take a headline label such as "Cheapest" while a comfortable journey
could have it.

**The traveller's own limits are honoured, and explained.** `options.modes`
restricts the search to the vehicles you are willing to take, `options.max_price`
is a ceiling rather than a suggestion, and `arrive_by` answers "I must be there
by six" by sweeping back through the day's departures instead of pretending the
clock stands still. A departure you name is kept: the search does not quietly
move your 20:00 to 17:51 to satisfy a deadline. When a filter removes everything,
the response carries a `notice` naming the filter that did it rather than an
empty list.

### Why the compiled timetable is still worth planning on

Every journey the engine produces is a real route between real places: the
stations are the actual stations, the coordinates are the actual coordinates,
the operators are the actual companies, the fares follow the actual policy. What
is synthetic is *when* each service runs. That is the part a feed replaces, and
the feed plumbing is already built and tested.

---

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api` | Endpoint index |
| GET | `/api/health` | Liveness, network and database counts |
| GET | `/api/preferences` | The optimisation targets and their weights |
| GET | `/api/data-sources` | Real vs compiled provenance, live-feed adapters |
| GET | `/api/stops/search` | Stop, station and town autocomplete |
| GET | `/api/stops/nearby` | Stops near a coordinate |
| GET | `/api/stops/regions` | The modelled cities and towns |
| GET | `/api/stops/{stop_id}` | One stop with its routes and operators |
| POST | `/api/journeys/search` | **Plan a journey** — `preference`, `traveller`, `max_walk_minutes`, `limit`, `arrive_by`, and `options` (`modes`, `max_price`, `max_legs`, `step_free_only`) |
| POST | `/api/journeys/compare-emissions` | Compare modes on one trip |
| GET | `/api/network/summary` · `/operators` · `/routes` · `/coverage` | What the network contains, and how much of each city's real stop register it models |
| GET | `/api/fares/products` · `/operators` | The fare table |
| GET | `/api/live/vehicles` · `/alerts` | Where the vehicles are, what is disrupted |
| POST | `/api/live/track` | Follow the journey you are on |
| GET/POST/DELETE | `/api/me/saved` | Saved journeys (per device) |
| GET/POST/DELETE | `/api/me/alerts` | Price watches (per device) |
| GET | `/api/me/history` | Recent searches |

Interactive documentation: <http://localhost:8000/api/docs>.

Endpoints under `/api/me` and `/api/live/track` identify the client with an
`X-Device-Key` header (a `device_key` field in the body is accepted for clients
that cannot set headers). Phase 1 has no accounts; Phase 2 swaps this dependency
for a real authenticated user without changing any call site.

---

## Testing

```bash
.venv/bin/python -m pytest backend/tests -q     # the engine, the pipeline, every endpoint
cd frontend && npm run test:render             # the planning screen, rendered and asserted on
```

The render test mounts the real app in a DOM against the real API and walks the
journey a traveller would take: the results sheet and its option cards, the map
drawn from real coordinates, the numbered timeline behind "View journey", live
mode, the price comparison, the transport filter, and the Home screen with its
bottom navigation. It asserts on prices, durations, walking and badges — what a
person actually reads. A type-check does not tell you whether a page renders or
what it says.

The suite runs against the real compiled feed rather than a synthetic fixture,
because the bugs worth catching are in the data: a corridor that does not
resolve, a route whose trips merged with another operator's, a tube line whose
last train leaves after midnight and therefore vanished, a feed window that has
moved past. Several of those are now regression tests with the reasoning in the
docstring, and every one of them was a real defect found by running the thing.

---

## Roadmap

Phase 1 (this prototype) is journey planning from real data with a real engine.
The next phases, in the order they unlock value:

1. **Phase 2 — live and personal.** Live BODS/TransXchange timetables and
   SIRI-VM vehicle positions instead of the simulator; accounts and synced
   saved journeys; push notifications when a watched fare drops; maps with real
   cartography instead of the schematic view.
2. **Phase 3 — national scale.** PostgreSQL/PostGIS (the schema is already
   modelled for it), partitions per region, a Redis-backed cache, and the full
   national NaPTAN stop set rather than the modelled network.
3. **Phase 4 — multi-leg commerce.** Through-ticketing across operators,
   split-ticketing that is legal to sell, seat reservations, and disruption
   replanning while a traveller is en route.
4. **Phase 5 — the app.** Flutter clients for iOS and Android over the same
   API, offline timetables, and accessibility certification.

---

## Licence and attribution

MoveIn's own code is provided as a prototype. The bundled data remains under its
publishers' licences — Department for Transport (NaPTAN, Open Government Licence
v3.0), the ATOC/National Rail operator register, and the open datasets listed in
`docs/DATA_SOURCES.md`. Copyright in the source data stays with its publishers.
