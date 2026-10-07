"""A searchable index over a compiled transport network.

:class:`TransitGraph` is the bridge between the storage-shaped
:class:`~app.domain.models.TransportNetwork` and the routing algorithms.  It
precomputes everything the search needs so that a journey query only does work
proportional to the size of the answer, not the size of the timetable:

* routes as ordered stop sequences, with cumulative distance and cumulative
  riding time along each pattern
* trips sorted by departure, so boarding is a binary search
* stop -> routes, with the position of the stop on each route
* a spatial index over stops for origin/destination access
* a walking-transfer index between nearby stops
"""

from __future__ import annotations

import zlib

import bisect
from dataclasses import dataclass, field
from datetime import date

from ..domain.models import (
    CO2_G_PER_PKM,
    Calendar,
    FareAttribute,
    Mode,
    Route,
    Stop,
    TransportNetwork,
    Trip,
    gtfs_time_to_seconds,
)
from ..ingest.geo import GridIndex, haversine_m, walk_distance_m, walk_duration_s

#: A person will not walk further than this to reach a stop in a city, but will
#: for a long-distance departure -- so the limit is applied per mode.
MODE_ACCESS_WALK_M: dict[Mode, int] = {
    Mode.RAIL: 2500,
    Mode.COACH: 2500,
    Mode.METRO: 1500,
    Mode.TRAM: 1500,
    Mode.BUS: 900,
    Mode.FERRY: 2000,
    Mode.TAXI: 400,
    Mode.RIDEHAIL: 400,
}


@dataclass(slots=True)
class RoutePattern:
    """One route's ordered stop sequence, shared by all its trips."""

    route_id: str
    mode: Mode
    operator_code: str
    stops: tuple[str, ...]
    #: Cumulative distance from the first stop, in metres.
    cum_distance_m: tuple[float, ...]
    #: Trip ids sorted by departure time at the first stop.
    trip_ids: tuple[str, ...]
    #: Departure time at the first stop for each trip, in seconds.
    first_departures: tuple[int, ...]
    #: Position of each stop on the pattern.
    stop_position: dict[str, int] = field(default_factory=dict)

    def position_of(self, stop_id: str) -> int | None:
        return self.stop_position.get(stop_id)

    def distance_between(self, i: int, j: int) -> float:
        return abs(self.cum_distance_m[j] - self.cum_distance_m[i])


@dataclass(slots=True)
class TripProfile:
    """Precomputed times for one trip."""

    trip_id: str
    route_id: str
    service_id: str
    stops: tuple[str, ...]
    arrivals: tuple[int, ...]
    departures: tuple[int, ...]
    last_stop: str
    wheelchair_accessible: bool
    bikes_allowed: bool
    reliability: float
    headsign: str

    def index_of(self, stop_id: str) -> int | None:
        try:
            return self.stops.index(stop_id)
        except ValueError:
            return None


class TransitGraph:
    """Searchable index over a compiled network."""

    def __init__(self, net: TransportNetwork) -> None:
        self.net = net
        #: Local aliases so the hot loops read well.
        self.stops: dict[str, Stop] = net.stops
        self.routes: dict[str, Route] = net.routes

        self.patterns: dict[str, RoutePattern] = {}
        self.trip_profiles: dict[str, TripProfile] = {}
        self.stop_routes: dict[str, list[tuple[str, int]]] = {}
        self.transfers: dict[str, list] = {}

        self._build_patterns()
        self._build_spatial_index()
        self._build_transfer_index()
        self._build_fare_index()

    # -- construction ------------------------------------------------------
    def _build_patterns(self) -> None:
        # Group trips by the exact stop sequence *and the route that runs it*.
        #
        # The sequence alone is not enough: two different operators can call at
        # the same stops in the same order -- Megabus and National Express both
        # run Nottingham to Birmingham via Derby -- and merging their trips into
        # one pattern would label a Megabus coach as a National Express one and
        # price it on the wrong operator's fare scale.  Trips on one corridor
        # that skip different stops are still separate patterns, or the search
        # would invent calls at stops a service does not serve.
        by_run: dict[tuple[str, tuple[str, ...]], list[str]] = {}
        for trip_id, stop_times in self.net.stop_times.items():
            seq = tuple(st.stop_id for st in stop_times)
            if len(seq) < 2:
                continue
            route_id = self.net.trips[trip_id].route_id
            by_run.setdefault((route_id, seq), []).append(trip_id)

        for (route_id, seq), trip_ids in by_run.items():
            trip_ids.sort(key=lambda t: self.net.stop_times[t][0].departure_s)
            route = self.net.routes.get(route_id)
            if route is None:
                continue

            # Cumulative distance uses the real coordinates of the real stops.
            cum: list[float] = [0.0]
            for a, b in zip(seq, seq[1:]):
                sa, sb = self.stops.get(a), self.stops.get(b)
                d = haversine_m(sa.lat, sa.lon, sb.lat, sb.lon) if sa and sb else 0.0
                cum.append(cum[-1] + d)

            pattern = RoutePattern(
                route_id=route_id,
                mode=route.mode,
                operator_code=route.operator_code,
                stops=seq,
                cum_distance_m=tuple(cum),
                trip_ids=tuple(trip_ids),
                first_departures=tuple(
                    self.net.stop_times[t][0].departure_s for t in trip_ids
                ),
                stop_position={sid: i for i, sid in enumerate(seq)},
            )
            # A stable digest: Python's hash() is salted per process, so
            # pattern keys built from it change on every run and cannot be
            # cached, stored, or compared across processes.
            key = (
                f"{route_id}|{seq[0]}>{seq[-1]}|"
                f"{zlib.crc32('|'.join(seq).encode()) & 0xFFFF:04x}"
            )
            self.patterns[key] = pattern
            for i, sid in enumerate(seq):
                self.stop_routes.setdefault(sid, []).append((key, i))

            for trip_id in trip_ids:
                times = self.net.stop_times[trip_id]
                trip = self.net.trips[trip_id]
                self.trip_profiles[trip_id] = TripProfile(
                    trip_id=trip_id,
                    route_id=route_id,
                    service_id=trip.service_id,
                    stops=seq,
                    arrivals=tuple(st.arrival_s for st in times),
                    departures=tuple(st.departure_s for st in times),
                    last_stop=seq[-1],
                    wheelchair_accessible=trip.wheelchair_accessible == 1,
                    bikes_allowed=trip.bikes_allowed == 1,
                    reliability=trip.reliability,
                    headsign=trip.headsign,
                )

    def _build_spatial_index(self) -> None:
        self._grid = GridIndex(cell_deg=0.01)
        self._grid_ids: list[str] = []
        for stop in self.stops.values():
            self._grid.add(stop.lat, stop.lon)
            self._grid_ids.append(stop.id)

    def _build_transfer_index(self) -> None:
        for transfer in self.net.transfers:
            self.transfers.setdefault(transfer.from_stop_id, []).append(transfer)

    def _build_fare_index(self) -> None:
        #: route_id -> fare ids that cover it.
        self.route_fares: dict[str, list[str]] = {}
        for rule in self.net.fare_rules:
            if rule.route_id:
                self.route_fares.setdefault(rule.route_id, []).append(rule.fare_id)
        #: operator_code -> fare ids valid across that operator's network.
        self.operator_fares: dict[str, list[str]] = {}
        for fare in self.net.fares.values():
            if fare.operator_code:
                self.operator_fares.setdefault(fare.operator_code, []).append(fare.fare_id)
        #: operator day tickets, usable across a multi-leg journey.
        self.operator_day_fares: dict[str, FareAttribute] = {}
        for fare in self.net.fares.values():
            if fare.product_type in ("day", "cap") and fare.operator_code:
                existing = self.operator_day_fares.get(fare.operator_code)
                if existing is None or fare.price < existing.price:
                    self.operator_day_fares[fare.operator_code] = fare

    # -- queries -----------------------------------------------------------
    def stops_near(
        self, lat: float, lon: float, radius_m: int, *, limit: int = 20
    ) -> list[tuple[Stop, float]]:
        """Stops within ``radius_m`` of a point, nearest first."""
        hits = self._grid.query_radius(lat, lon, radius_m, limit=limit * 3)
        out: list[tuple[Stop, float]] = []
        for idx, _dist in hits:
            stop = self.stops[self._grid_ids[idx]]
            # Per-mode willingness to walk.
            allowed = MODE_ACCESS_WALK_M.get(stop.mode, radius_m)
            distance = walk_distance_m(lat, lon, stop.lat, stop.lon)
            if distance <= min(radius_m, allowed):
                out.append((stop, distance))
        out.sort(key=lambda t: t[1])
        return out[:limit]

    def nearest_stop(self, lat: float, lon: float, radius_m: int = 3000) -> Stop | None:
        hits = self.stops_near(lat, lon, radius_m, limit=1)
        return hits[0][0] if hits else None

    def next_departure_index(self, pattern: RoutePattern, after_s: int) -> int:
        """Index of the first trip on ``pattern`` departing at or after ``after_s``."""
        return bisect.bisect_left(pattern.first_departures, after_s)

    def services_on(self, day: date) -> set[str]:
        """Service ids active on a calendar date (GTFS calendar + exceptions)."""
        weekday = day.weekday()
        active: set[str] = set()
        for cal in self.net.calendars.values():
            if cal.start_date and day < cal.start_date:
                continue
            if cal.end_date and day > cal.end_date:
                continue
            if cal.runs_on_weekday(weekday):
                active.add(cal.id)
        for cd in self.net.calendar_dates:
            if cd.date != day:
                continue
            if cd.exception_type == 1:
                active.add(cd.service_id)
            elif cd.exception_type == 2:
                active.discard(cd.service_id)
        return active

    # -- derived -----------------------------------------------------------
    def leg_emissions_g(self, mode: Mode, distance_m: float) -> float:
        return CO2_G_PER_PKM.get(mode, 0.0) * (distance_m / 1000.0)

    def stats(self) -> dict[str, int]:
        """Headline counts, for the status endpoint and the data page."""
        return {
            "stops": len(self.stops),
            "routes": len(self.routes),
            "patterns": len(self.patterns),
            "trips": len(self.trip_profiles),
            "stop_routes": sum(len(v) for v in self.stop_routes.values()),
            "transfers": sum(len(v) for v in self.transfers.values()),
            "operators": len(
                {r.operator_code for r in self.routes.values() if r.operator_code}
            ),
        }
