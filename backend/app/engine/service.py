"""The journey planning service.

Owns the loaded network and answers the product's core question:

    "What is the best way for me to get from A to B?"

Places are resolved from free text, the search runs, journeys are assembled and
priced, and the results come back with the trade-offs labelled -- cheapest,
fastest, best value, fewest changes, least walking, lowest emissions -- plus the
ranked list for the traveller's stated preference.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from ..config import Settings, get_settings
from ..domain.models import Mode, Stop, TransportNetwork
from ..domain.network_spec import ALL_CORRIDORS, FareRule
from ..domain.regions import REGIONS, REGIONS_BY_SLUG
from ..ingest.geo import haversine_m, walk_distance_m, walk_duration_s
from ..ingest.gtfs import read_gtfs
from ..ingest.network_compiler import _normalise_stop_name
from .fares import FareEngine, TravellerProfile
from .graph import TransitGraph
from .journeys import (
    Journey,
    JourneyAssembler,
    JourneyRanker,
    Preference,
    format_duration,
)
from .search import Raptor, SearchOptions, SearchResult


@dataclass
class Place:
    """A resolved origin or destination."""

    id: str
    label: str
    lat: float
    lon: float
    #: "region" | "stop" | "coordinate"
    kind: str = "stop"
    mode: str = ""
    region: str = ""
    #: Any other stops the label could have meant.
    alternatives: list[dict] = field(default_factory=list)


@dataclass
class PlanResult:
    journeys: list[Journey] = field(default_factory=list)
    origin: Place | None = None
    destination: Place | None = None
    preference: Preference = Preference.BEST_VALUE
    departure: datetime | None = None
    #: Diagnostics: how long the search took and how much it explored.
    diagnostics: dict = field(default_factory=dict)
    alternatives: list[dict] = field(default_factory=list)


class JourneyPlanner:
    """Loads the network once and answers journey queries against it."""

    def __init__(self, net: TransportNetwork, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.net = net
        self.graph = TransitGraph(net)
        self.fare_rules: dict[str, FareRule] = {
            corridor.code: corridor.fare for corridor in ALL_CORRIDORS
        }
        self.raptor = Raptor(self.graph, self.fare_rules)
        self.fare_engine = FareEngine(
            fares=net.fares,
            route_fares=self.graph.route_fares,
            operator_day_fares=self.graph.operator_day_fares,
            fare_rules=self.fare_rules,
        )
        self.assembler = JourneyAssembler(self.graph, self.fare_engine)
        self.ranker = JourneyRanker(self.settings)
        self._name_index: list[tuple[str, Stop]] = [
            (_normalise_stop_name(s.name).lower(), s) for s in net.stops.values()
        ]

    # -- places ------------------------------------------------------------
    def resolve_place(self, query: str, *, near: tuple[float, float] | None = None) -> Place | None:
        """Resolve free text to a place.

        Accepted forms:

        * a town or city name ("Nottingham", "Milton Keynes") -> its centre
        * a specific stop ("Nottingham Station", "Victoria Centre") -> that stop
        * ``lat,lon`` -> an exact coordinate
        """
        text = (query or "").strip()
        if not text:
            return None

        # Coordinates.
        m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", text)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            if 49.0 < lat < 61.5 and -8.5 < lon < 2.5:
                return Place(
                    id=f"coord:{lat:.5f},{lon:.5f}",
                    label="Your location",
                    lat=lat,
                    lon=lon,
                    kind="coordinate",
                )

        key = _normalise_stop_name(text).lower()

        # Exact stop name.
        exact = [s for name, s in self._name_index if name == key]
        if exact:
            stop = self._best_stop(exact, near)
            return Place(
                id=stop.id, label=stop.name, lat=stop.lat, lon=stop.lon,
                kind="stop", mode=stop.mode.value, region=stop.region,
                alternatives=self._alternatives(exact, stop),
            )

        # Region / town name -- prefer the longest matching region name so
        # "Milton Keynes" beats a bare "Milton".
        region = REGIONS_BY_SLUG.get(key.replace(" ", "-"))
        if region is None:
            candidates = [
                r for r in REGIONS
                if key == r.name.lower() or r.name.lower().startswith(key)
            ]
            if candidates:
                region = max(candidates, key=lambda r: len(r.name))
        if region is not None:
            return Place(
                id=f"region:{region.slug}",
                label=region.name,
                lat=region.lat,
                lon=region.lon,
                kind="region",
                region=region.slug,
            )

        # Prefix / substring on stop names.
        prefix = [s for name, s in self._name_index if name.startswith(key)]
        if not prefix:
            prefix = [s for name, s in self._name_index if key in name]
        if prefix:
            stop = self._best_stop(prefix, near)
            return Place(
                id=stop.id, label=stop.name, lat=stop.lat, lon=stop.lon,
                kind="stop", mode=stop.mode.value, region=stop.region,
                alternatives=self._alternatives(prefix, stop),
            )
        return None

    def _best_stop(self, stops: list[Stop], near: tuple[float, float] | None) -> Stop:
        if near is None:
            # Prefer interchanges, then the stop nearest a town centre.
            return max(
                stops,
                key=lambda s: (s.interchange, -min(
                    haversine_m(s.lat, s.lon, r.lat, r.lon) for r in REGIONS
                )),
            )
        return min(stops, key=lambda s: walk_distance_m(near[0], near[1], s.lat, s.lon))

    @staticmethod
    def _alternatives(stops: list[Stop], chosen: Stop, limit: int = 5) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for stop in stops:
            if stop.id == chosen.id or stop.name.lower() in seen:
                continue
            seen.add(stop.name.lower())
            out.append({
                "id": stop.id,
                "name": stop.name,
                "mode": stop.mode.value,
                "region": stop.region,
                "lat": stop.lat,
                "lon": stop.lon,
            })
            if len(out) >= limit:
                break
        return out

    def search_stops(self, query: str, *, limit: int = 12) -> list[dict]:
        """Stop autocomplete for the From/To fields."""
        text = (query or "").strip().lower()
        if not text:
            return []
        key = _normalise_stop_name(text).lower()
        scored: list[tuple[int, int, Stop]] = []
        for name, stop in self._name_index:
            if name == key:
                scored.append((0, 0, stop))
            elif name.startswith(key) and (
                len(name) == len(key) or not name[len(key)].isalpha()
            ):
                scored.append((1, 0, stop))
            elif key in name:
                scored.append((2, 0, stop))
        for region in REGIONS:
            if region.name.lower().startswith(key) or key == region.name.lower():
                scored.append((1, 1, Stop(
                    id=f"region:{region.slug}",
                    name=region.name,
                    lat=region.lat,
                    lon=region.lon,
                    mode=Mode.RAIL,
                    region=region.slug,
                    interchange=True,
                    source="region",
                )))
        # Rank by quality, then prefer interchanges, then shorter names.
        scored.sort(key=lambda t: (t[0], 0 if t[2].interchange else 1, len(t[2].name)))
        out: list[dict] = []
        seen: set[str] = set()
        for _quality, _kind, stop in scored:
            dedupe = stop.name.lower()
            if dedupe in seen:
                continue
            seen.add(dedupe)
            out.append({
                "id": stop.id,
                "name": stop.name,
                "mode": "town" if stop.id.startswith("region:") else stop.mode.value,
                "region": stop.region,
                "lat": round(stop.lat, 6),
                "lon": round(stop.lon, 6),
                "interchange": stop.interchange,
            })
            if len(out) >= limit:
                break
        return out

    # -- planning ----------------------------------------------------------
    def plan(
        self,
        *,
        origin: str | Place,
        destination: str | Place,
        departure: datetime | None = None,
        preference: Preference | str = Preference.BEST_VALUE,
        traveller: TravellerProfile | None = None,
        max_legs: int | None = None,
        step_free_only: bool = False,
        earliest_arrival: bool = False,
        include_walking_only: bool = True,
        departure_sweep: int | None = None,
        allow_on_demand: bool = True,
        max_access_walk_m: int | None = None,
        limit: int | None = None,
    ) -> PlanResult:
        settings = self.settings
        if isinstance(preference, str):
            preference = Preference(preference)
        traveller = traveller or TravellerProfile()

        origin_place = origin if isinstance(origin, Place) else self.resolve_place(origin)
        dest_place = (
            destination if isinstance(destination, Place) else self.resolve_place(destination)
        )
        result = PlanResult(origin=origin_place, destination=dest_place,
                            preference=preference)

        if origin_place is None or dest_place is None:
            result.diagnostics = {
                "error": "origin or destination could not be resolved",
                "origin_resolved": origin_place is not None,
                "destination_resolved": dest_place is not None,
            }
            return result

        if departure is None:
            departure = datetime.now().replace(second=0, microsecond=0)
        result.departure = departure

        service_day = departure.replace(hour=0, minute=0, second=0, microsecond=0)
        base_s = departure.hour * 3600 + departure.minute * 60
        services = self.graph.services_on(departure.date())

        # A traveller who says they cannot manage steps also cannot manage a
        # long walk, so their stated limit wins over the network default.
        access_walk_m = max_access_walk_m or (
            min(traveller.max_walk_m, settings.max_access_walk_m)
            if traveller.max_walk_m
            else settings.max_access_walk_m
        )
        options = SearchOptions(
            max_legs=max_legs or settings.max_legs,
            max_access_walk_m=access_walk_m,
            max_transfer_walk_m=settings.max_transfer_walk_m,
            min_connection_s=settings.min_connection_s,
            max_journey_duration_s=settings.max_journey_duration_s,
            allow_on_demand=allow_on_demand,
            require_step_free=step_free_only,
            departure_sweep=departure_sweep or settings.departure_sweep,
        )

        origin_point = (origin_place.lat, origin_place.lon)
        dest_point = (dest_place.lat, dest_place.lon)

        # Straight-line feasibility guard: never search for something absurd.
        direct_km = haversine_m(*origin_point, *dest_point) / 1000.0
        if direct_km < 0.35 and include_walking_only:
            walk_m = walk_distance_m(*origin_point, *dest_point)
            walk_s = walk_duration_s(walk_m)
            journey = Journey(
                id="walk-only",
                departure=departure,
                arrival=departure + timedelta(seconds=walk_s),
                legs=[],
                walking_m=round(walk_m, 1),
                walking_s=walk_s,
                co2_g=0.0,
            )
            result.journeys = [journey]
            result.diagnostics = {"mode": "walk-only", "distance_m": round(walk_m)}
            return result

        # Sweep several departure times so the traveller sees the shape of the
        # day, not just the next vehicle.
        sweeps: list[int] = [base_s]
        for i in range(1, max(1, options.departure_sweep)):
            sweeps.append(base_s + i * 1800)

        collected: list[Journey] = []
        diagnostics: dict = {
            "sweeps": len(sweeps),
            "rounds": 0,
            "stops_scanned": 0,
            "search_ms": 0,
            "services": len(services),
            "direct_km": round(direct_km, 1),
        }
        seen_signatures: set[tuple] = set()

        for sweep in sweeps:
            if sweep >= 27 * 3600:
                break
            search: SearchResult = self.raptor.search(
                origin=origin_point,
                destination=dest_point,
                departure_s=sweep,
                services=services,
                options=options,
            )
            diagnostics["rounds"] = max(diagnostics["rounds"], search.rounds_used)
            diagnostics["stops_scanned"] += search.stops_scanned
            diagnostics["search_ms"] += search.duration_ms

            for stop_id, labels in search.labels.items():
                dest_stop = self.graph.stops.get(stop_id)
                if dest_stop is None:
                    continue
                # Egress must be plausible.
                if walk_distance_m(
                    dest_stop.lat, dest_stop.lon, *dest_point
                ) > options.max_access_walk_m:
                    continue
                for label in labels:
                    if not label.legs and not include_walking_only:
                        continue
                    journey = self.assembler.assemble(
                        label,
                        destination=dest_point,
                        destination_stop_id=stop_id,
                        search=search,
                        departure_s=sweep,
                        service_day=service_day,
                        traveller=traveller,
                        settings_discounts=(
                            settings.railcard_discount,
                            settings.student_discount,
                        ),
                        max_egress_walk_m=options.max_access_walk_m,
                    )
                    if journey is None:
                        continue
                    signature = self._journey_signature(journey)
                    if signature in seen_signatures:
                        continue
                    seen_signatures.add(signature)
                    collected.append(journey)

        # Keep the best-ranked handful of distinct options.
        ranked = self.ranker.rank(collected, preference)

        # Deduplicate by the itinerary shape the traveller can perceive.
        deduped: list[Journey] = []
        shapes: set[tuple] = set()
        for journey in ranked:
            shape = (
                journey.route_label,
                journey.departure.hour,
                journey.departure.minute // 10,
                round(journey.duration_s / 600),
            )
            if shape in shapes:
                continue
            shapes.add(shape)
            deduped.append(journey)
            if len(deduped) >= settings.max_candidates:
                break

        # Archetypes are chosen from the journeys that are actually returned:
        # tagging the pool and then dropping a winner as a duplicate would leave
        # the results screen with no "Cheapest" card at all.
        deduped = self.ranker.select_archetypes(deduped)

        if limit is not None and len(deduped) > limit:
            # The results screen shows one card per trade-off, so a journey that
            # wins an archetype is always returned even when it ranks below the
            # cut.  Everything else is the top of the ranking, in rank order.
            winners = {id(journey) for journey in deduped if journey.archetypes}
            chosen = [journey for journey in deduped if id(journey) in winners][:limit]
            for journey in deduped:
                if len(chosen) >= limit:
                    break
                if id(journey) not in {id(c) for c in chosen}:
                    chosen.append(journey)
            order = {id(journey): index for index, journey in enumerate(deduped)}
            deduped = sorted(chosen, key=lambda journey: order[id(journey)])

        for i, journey in enumerate(deduped):
            journey.id = f"j{i + 1}"

        result.journeys = deduped
        result.diagnostics = diagnostics
        result.alternatives = self._suggest_alternatives(dest_place)
        return result

    @staticmethod
    def _journey_signature(journey: Journey) -> tuple:
        from .search import TransitLeg

        return (
            journey.departure,
            tuple(
                (l.trip_id, l.board_stop_id, l.alight_stop_id)
                for l in journey.legs
                if isinstance(l, TransitLeg)
            ),
        )

    def _suggest_alternatives(self, destination: Place, limit: int = 6) -> list[dict]:
        """Nearby stops, so the results screen can offer "try instead" options."""
        nearby = self.graph.stops_near(destination.lat, destination.lon, 1500, limit=limit + 1)
        out: list[dict] = []
        for stop, distance in nearby:
            if stop.id == destination.id:
                continue
            out.append({
                "id": stop.id,
                "name": stop.name,
                "mode": stop.mode.value,
                "distance_m": round(distance),
            })
            if len(out) >= limit:
                break
        return out


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def read_feed(settings: Settings) -> TransportNetwork:
    """Read the compiled feed from disk, compiling in memory as a last resort."""
    generated = Path(settings.data_generated_dir)
    feed_zip = generated / "movein-gtfs.zip"
    if feed_zip.exists():
        return read_gtfs(feed_zip)
    feed_dir = generated / "gtfs"
    if (feed_dir / "stops.txt").exists():
        return read_gtfs(feed_dir)

    from ..ingest.network_compiler import NetworkCompiler

    return NetworkCompiler(Path(settings.data_raw_dir)).compile().network


def load_network(settings: Settings | None = None) -> TransportNetwork:
    """Load the network, preferring the database over the feed files.

    Order of preference:

    1. the database, when it has been seeded and its stored fingerprint still
       matches the feed on disk -- the production path;
    2. the compiled GTFS zip or directory;
    3. compiling in memory from the raw data, so a fresh clone works before
       anything has been generated.
    """
    settings = settings or get_settings()

    from ..db import repository as db_repo

    try:
        with db_repo.session_scope() as session:
            fingerprint = db_repo.network_fingerprint(read_feed(settings))
            if db_repo.network_is_current(session, fingerprint):
                return db_repo.load_network(session)
    except Exception:
        # A missing or unreadable database must never stop the planner from
        # starting: fall through to the feed files.
        pass
    return read_feed(settings)


_PLANNER_LOCK = threading.Lock()
_PLANNER: JourneyPlanner | None = None


def get_planner(settings: Settings | None = None) -> JourneyPlanner:
    """Process-wide singleton planner (loading the feed takes ~2 s)."""
    global _PLANNER
    with _PLANNER_LOCK:
        if _PLANNER is None:
            settings = settings or get_settings()
            _PLANNER = JourneyPlanner(load_network(settings), settings)
        return _PLANNER


def reset_planner() -> None:
    global _PLANNER
    with _PLANNER_LOCK:
        _PLANNER = None
