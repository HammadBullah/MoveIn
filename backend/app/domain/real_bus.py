"""The real UK bus network: actual routes, actual stops, actual shapes.

This is a different class of data from the compiled timetable layer, and the
distinction matters enough to be the first thing in the module.

* **This module** holds real bus routes as their operators publish them: route
  number, operator, the ordered stops the service calls at, and the shape the
  bus drives -- all taken from the operators' own TransXChange publications on
  the DfT Bus Open Data Service.
* **The compiled network** (`ingest/network_compiler.py`) holds the timetable
  MoveIn plans journeys with, compiled from the real NaPTAN register and the
  real operator list.

The real bus network therefore answers "which bus runs between these two towns,
through which stops?" with complete confidence, and answers "when?" not at all --
it carries no departure times, because a route shape is not a timetable.  The
API says so in every payload rather than letting a caller assume otherwise.

Loaded from `data/raw/real_bus_routes/compiled.json.gz`, built by
`scripts/import_real_bus_routes.py`.
"""

from __future__ import annotations

import gzip
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Coordinates are rounded to this many places on the way out.  Five decimal
#: places is about a metre, and nobody can see a metre on a phone.
DEFAULT_PRECISION = 5

#: How close a place must be to a route's stop to count as "on" that route.
#: Wide enough for a town centre, tight enough not to swallow the next village.
PLACE_RADIUS_M = 3_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def simplify_line(
    points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    tolerance_m: float,
) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker in degrees, iteratively: these lines are long.

    The compiled shapes are already simplified for a phone at city zoom; a
    caller asking for the whole country can ask for a coarser trim again rather
    than paying for detail nobody can see.
    """
    if tolerance_m <= 0 or len(points) <= 2:
        return list(points)
    degrees = tolerance_m / 111_320.0
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        ax, ay = points[start]
        bx, by = points[end]
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        farthest, farthest_distance = -1, -1.0
        for index in range(start + 1, end):
            px, py = points[index]
            if length_sq == 0:
                distance = math.hypot(px - ax, py - ay)
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
                distance = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if distance > farthest_distance:
                farthest, farthest_distance = index, distance
        if farthest_distance > degrees:
            keep[farthest] = True
            stack.append((start, farthest))
            stack.append((farthest, end))
    return [point for point, kept in zip(points, keep) if kept]


@dataclass(frozen=True)
class RealBusStop:
    """A stop a real service calls at, named by the NaPTAN register."""

    atco: str
    name: str
    lat: float
    lon: float
    #: The departure time the published feed gives this stop for the one trip
    #: MoveIn keeps, as HH:MM.  Empty when the feed carries no times.
    time: str = ""

    def payload(self, precision: int = DEFAULT_PRECISION) -> dict:
        payload = {
            "atco": self.atco,
            "name": self.name,
            "lat": round(self.lat, precision),
            "lon": round(self.lon, precision),
        }
        if self.time:
            payload["time"] = self.time
        return payload


@dataclass(frozen=True)
class RealBusRoute:
    """One real registered bus route, with the stops it calls at in order."""

    id: str
    number: str
    operator: str
    description: str
    source: str
    stops: tuple[RealBusStop, ...]
    shape: tuple[tuple[float, float], ...]
    #: The BODS service code this line belongs to.  One service publishes many
    #: variations -- both directions, branches, school-day extras -- and they
    #: are different lines on the ground, so each is its own route record.
    service: str = ""

    @property
    def has_times(self) -> bool:
        """Whether the published feed gave this line any clock times."""
        return any(stop.time for stop in self.stops)

    @property
    def name(self) -> str:
        """How a passenger would name the service."""
        parts = [f"Route {self.number}" if self.number else self.id]
        if self.description:
            parts.append(self.description)
        return " · ".join(parts)

    def payload(self, *, precision: int = DEFAULT_PRECISION, shape: bool = False) -> dict:
        body = {
            "id": self.id,
            "service": self.service or self.id,
            "number": self.number,
            "operator": self.operator,
            "description": self.description,
            "stops": [stop.payload(precision) for stop in self.stops],
            "stop_count": len(self.stops),
            "shape_points": len(self.shape),
        }
        if shape:
            body["shape"] = [
                [round(lat, precision), round(lon, precision)] for lat, lon in self.shape
            ]
        return body


def _interleave(routes: list[RealBusRoute]) -> list[RealBusRoute]:
    """Order routes so a capped list still shows every operator.

    Taking the first N of an alphabetical list draws one company's network and
    calls it the country.  Round-robin by operator spends a limited budget
    across all of them.
    """
    by_operator: dict[str, list[RealBusRoute]] = {}
    for route in sorted(routes, key=lambda route: (route.operator, route.number, route.id)):
        by_operator.setdefault(route.operator, []).append(route)
    queues = list(by_operator.values())
    ordered: list[RealBusRoute] = []
    while queues:
        for queue in list(queues):
            ordered.append(queue.pop(0))
            if not queue:
                queues.remove(queue)
    return ordered


def _rank(journey: dict) -> tuple:
    """Sort key for a corridor option: fewest stops, then fewest before, then number."""
    return (
        0 if journey.get("direction") == "forward" else 1,
        journey["stops_travelled"],
        journey["stops_before"],
        journey["route"].number,
        journey["route"].operator,
    )


class RealBusNetwork:
    """Every real bus route MoveIn holds, indexed for the questions asked of it."""

    def __init__(self, payload: dict) -> None:
        self.attribution: str = payload.get("attribution", "")
        self.routes: dict[str, RealBusRoute] = {}
        for raw in payload.get("routes", []):
            route = RealBusRoute(
                id=str(raw["id"]),
                number=str(raw.get("number", "")),
                operator=str(raw.get("operator", "")),
                description=str(raw.get("description", "")),
                source=str(raw.get("source", "")),
                service=str(raw.get("service", "")),
                stops=tuple(
                    RealBusStop(
                        atco=str(stop["atco"]),
                        name=str(stop["name"]),
                        lat=float(stop["lat"]),
                        lon=float(stop["lon"]),
                        time=str(stop.get("time") or ""),
                    )
                    for stop in raw.get("stops", [])
                ),
                shape=tuple(
                    (float(point[0]), float(point[1])) for point in raw.get("shape", [])
                ),
            )
            self.routes[route.id] = route
        self._stats: dict | None = None
        self._cities: list[dict] | None = None
        self._by_operator: dict[str, list[str]] = {}
        self._by_stop: dict[str, list[str]] = {}
        for route in self.routes.values():
            self._by_operator.setdefault(route.operator, []).append(route.id)
            for stop in route.stops:
                self._by_stop.setdefault(stop.atco, []).append(route.id)
        self._place_index: dict[tuple[int, int], list[RealBusStop]] = {}
        for route in self.routes.values():
            for stop in route.stops:
                self._place_index.setdefault(self._cell(stop.lat, stop.lon), []).append(stop)

    # -- indexing ---------------------------------------------------------

    @staticmethod
    def _cell(lat: float, lon: float, size: float = 0.05) -> tuple[int, int]:
        return (int(math.floor(lat / size)), int(math.floor(lon / size)))

    def operators(self) -> dict[str, int]:
        """Route (variation) count per operator, biggest first."""
        return dict(sorted(((op, len(ids)) for op, ids in self._by_operator.items()), key=lambda kv: (-kv[1], kv[0])))

    def services(self) -> dict[str, list[RealBusRoute]]:
        """Routes grouped by the service they belong to, operator-then-number."""
        grouped: dict[str, list[RealBusRoute]] = {}
        for route in self.routes.values():
            grouped.setdefault(route.service or route.id, []).append(route)
        return dict(
            sorted(
                grouped.items(),
                key=lambda kv: (kv[1][0].operator, kv[1][0].number, kv[0]),
            )
        )

    def stops(self) -> dict[str, RealBusStop]:
        """Every named stop any real route calls at."""
        seen: dict[str, RealBusStop] = {}
        for route in self.routes.values():
            for stop in route.stops:
                seen.setdefault(stop.atco, stop)
        return seen

    def routes_at_stop(self, atco: str) -> list[RealBusRoute]:
        return [self.routes[rid] for rid in self._by_stop.get(atco, [])]

    # -- proximity --------------------------------------------------------

    def _stops_near(self, lat: float, lon: float, radius_m: float) -> list[RealBusStop]:
        found: list[RealBusStop] = []
        span = max(1, math.ceil(radius_m / (0.05 * 111_320.0)))
        base = self._cell(lat, lon)
        for dlat in range(-span, span + 1):
            for dlon in range(-span, span + 1):
                for stop in self._place_index.get((base[0] + dlat, base[1] + dlon), ()):
                    if haversine_m(lat, lon, stop.lat, stop.lon) <= radius_m:
                        found.append(stop)
        return found

    def routes_near(self, lat: float, lon: float, radius_m: float = PLACE_RADIUS_M) -> list[RealBusRoute]:
        """Every real route that calls within `radius_m` of a point."""
        ids: list[str] = []
        seen: set[str] = set()
        for stop in self._stops_near(lat, lon, radius_m):
            for route_id in self._by_stop.get(stop.atco, []):
                if route_id not in seen:
                    seen.add(route_id)
                    ids.append(route_id)
        return [self.routes[rid] for rid in ids]

    @staticmethod
    def _find_both_ends(
        route: "RealBusRoute",
        boarding: dict[str, RealBusStop],
        alighting: dict[str, RealBusStop],
    ) -> tuple[tuple[int, RealBusStop], tuple[int, RealBusStop]] | None:
        """(first boarding stop, last alighting stop) when the route serves the pair in order."""
        first: tuple[int, RealBusStop] | None = None
        last: tuple[int, RealBusStop] | None = None
        for index, stop in enumerate(route.stops):
            if stop.atco in boarding and first is None:
                first = (index, stop)
            if stop.atco in alighting:
                last = (index, stop)
        if first is None or last is None or last[0] <= first[0]:
            return None
        return first, last

    # -- the interesting question: which real service links these two places?

    def routes_between(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        radius_m: float = PLACE_RADIUS_M,
    ) -> list[dict]:
        """Real routes that call near the origin *and then* near the destination.

        Direction is respected: a route that only serves the pair the other way
        round is not a way to make this journey today, so it is left out.  The
        payload names the two stops the service uses at each end, because that
        is what tells a traveller whether it actually helps them.
        """
        origin_stops = {stop.atco: stop for stop in self._stops_near(*origin, radius_m)}
        destination_stops = {
            stop.atco: stop for stop in self._stops_near(*destination, radius_m)
        }
        if not origin_stops or not destination_stops:
            return []

        best_per_service: dict[str, dict] = {}
        for route in self.routes.values():
            boarding = self._find_both_ends(route, origin_stops, destination_stops)
            direction = "forward"
            if boarding is None:
                # Operators publish some services in one direction only -- the
                # 148 into Leicester is registered, the 148 back is not.  A bus
                # that runs one way runs both, so the reverse shape is still an
                # answer, as long as the payload says which way round it is.
                boarding = self._find_both_ends(route, destination_stops, origin_stops)
                direction = "reverse"
            if boarding is None:
                continue
            first, last = boarding
            travelled = route.stops[first[0] : last[0] + 1]
            straight_m = haversine_m(first[1].lat, first[1].lon, last[1].lat, last[1].lon)
            if direction == "reverse":
                # Boarding and alighting read the other way round in reality.
                first, last = last, first
            candidate = {
                "route": route,
                "direction": direction,
                "board": first[1],
                "alight": last[1],
                "stops_travelled": len(travelled),
                "stops_before": first[0],
                "stops_after": len(route.stops) - last[0] - 1,
                "straight_m": straight_m,
                "stops_travelled_names": [stop.name for stop in travelled],
            }
            key = route.service or route.id
            current = best_per_service.get(key)
            # One service, many variations: show the one that gets a passenger
            # from here to there with the fewest stops.
            if current is None or _rank(candidate) < _rank(current):
                best_per_service[key] = candidate
        journeys = sorted(best_per_service.values(), key=_rank)
        return journeys

    # -- drawing ----------------------------------------------------------

    def features(
        self,
        *,
        operator: str | None = None,
        near: tuple[float, float] | None = None,
        radius_m: float = PLACE_RADIUS_M,
        limit: int | None = None,
        precision: int = DEFAULT_PRECISION,
        simplify_m: float = 0.0,
    ) -> list[dict]:
        """Drawable polylines, optionally filtered to one operator or one area."""
        routes: list[RealBusRoute]
        if operator:
            routes = [self.routes[rid] for rid in self._by_operator.get(operator, [])]
        else:
            routes = list(self.routes.values())
        if near is not None:
            close = {route.id for route in self.routes_near(*near, radius_m)}
            routes = [route for route in routes if route.id in close]
        routes = [route for route in routes if len(route.shape) >= 2]
        routes = _interleave(routes)
        if limit is not None:
            routes = routes[:limit]
        shapes = {
            route.id: (
                simplify_line(route.shape, simplify_m) if simplify_m > 0 else list(route.shape)
            )
            for route in routes
        }
        return [
            {
                "id": route.id,
                "number": route.number,
                "operator": route.operator,
                "description": route.description,
                "coordinates": [
                    [round(lat, precision), round(lon, precision)] for lat, lon in shapes[route.id]
                ],
                "stops": [
                    [round(stop.lat, precision), round(stop.lon, precision)]
                    for stop in route.stops
                ],
                "stop_count": len(route.stops),
            }
            for route in routes
        ]

    # -- honesty ----------------------------------------------------------

    def city_report(
        self,
        cities: list[tuple[str, float, float]],
        *,
        radius_m: float = 6000.0,
        internal_km: float = 8.0,
    ) -> list[dict]:
        """For each city: how many published routes serve it, and how many stay in it.

        "City-internal" means both ends of the line are within `internal_km` of
        the city centre -- that is the difference between a city bus and an
        inter-city one, measured from the published routes rather than guessed.
        Computed once and kept: it walks the whole network per city.
        """
        if self._cities is not None:
            return self._cities
        rows: list[dict] = []
        for name, lat, lon in cities:
            nearby = self.routes_near(lat, lon, radius_m)
            internal = 0
            operators: dict[str, int] = {}
            for route in nearby:
                operators[route.operator] = operators.get(route.operator, 0) + 1
                if len(route.stops) < 2:
                    continue
                first, last = route.stops[0], route.stops[-1]
                if (
                    haversine_m(lat, lon, first.lat, first.lon) <= internal_km * 1000
                    and haversine_m(lat, lon, last.lat, last.lon) <= internal_km * 1000
                ):
                    internal += 1
            top = max(operators.items(), key=lambda item: item[1])[0] if operators else ""
            rows.append(
                {
                    "name": name,
                    "lat": round(lat, 5),
                    "lon": round(lon, 5),
                    "published": len(nearby),
                    "city_internal": internal,
                    "operators": len(operators),
                    "top_operator": top,
                }
            )
        rows.sort(key=lambda row: (-row["city_internal"], row["name"]))
        self._cities = rows
        return rows

    def stats(self) -> dict:
        """The counts the product quotes, computed from the data, never guessed.

        Computed once: the network is immutable after loading, and on the
        national file the stop counts walk 24,000 routes and 900,000 stop calls,
        which is a second of work every screen would otherwise pay again.
        """
        if self._stats is not None:
            return self._stats
        operators = self.operators()
        services = self.services()
        stops = self.stops()
        self._stats = {
            "routes": len(self.routes),
            "services": len(services),
            "operators": len(operators),
            "operator_names": list(operators),
            "routes_per_operator": operators,
            "services_per_operator": {
                operator: len({(route.service or route.id) for route in self.routes.values() if route.operator == operator})
                for operator in operators
            },
            "named_stops": len(stops),
            "routes_with_times": sum(1 for route in self.routes.values() if route.has_times),
            "stop_calls": sum(len(route.stops) for route in self.routes.values()),
            "shape_points": sum(len(route.shape) for route in self.routes.values()),
            "attribution": self.attribution,
        }
        return self._stats


def load_real_bus_network(path: Path) -> RealBusNetwork:
    """Read one compiled real-network file."""
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return RealBusNetwork(json.load(handle))


def load_real_bus_sources(paths: list[Path]) -> RealBusNetwork:
    """Merge every compiled file, so a new import adds to the network.

    The GeoJSON import and the BODS/GTFS import arrive separately and cover
    different operators, so the app reads all of them rather than asking which
    one is "the" dataset.
    """
    merged: dict = {"routes": [], "attribution": ""}
    seen: set[str] = set()
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        for route in payload.get("routes", []):
            identifier = str(route.get("id") or "")
            if identifier in seen:
                continue
            seen.add(identifier)
            merged["routes"].append(route)
        if payload.get("attribution"):
            merged["attribution"] = (
                f"{merged['attribution']} {payload['attribution']}".strip()
                if merged["attribution"]
                else payload["attribution"]
            )
    return RealBusNetwork(merged)


@lru_cache(maxsize=4)
def _cached(key: str) -> RealBusNetwork:
    # The key carries every source path and its mtime, so a rebuild during
    # development is picked up without a restart while normal serving stays a
    # single load.
    paths = [Path(part.rsplit(":", 1)[0]) for part in key.split("|")]
    return load_real_bus_sources(paths)


def get_real_bus_network(path: Path | None = None) -> RealBusNetwork | None:
    """The process-wide real bus network, or None when it has not been built.

    Every `compiled*.json.gz` in the directory is loaded: the operator GeoJSON
    import and the BODS/GTFS import are separate files and separate sources, and
    the app is better off holding both than choosing between them.
    """
    if path is not None:
        paths = [path] if path.exists() else []
    else:
        from ..config import get_settings

        directory = get_settings().data_raw_dir / "real_bus_routes"
        paths = sorted(directory.glob("compiled*.json.gz"))
    if not paths:
        return None
    key = "|".join(f"{path}:{path.stat().st_mtime_ns}" for path in paths)
    return _cached(key)
