"""Multi-criteria RAPTOR journey search.

RAPTOR (Round-Based Public Transit Routing, Delling et al.) expands a journey
one *leg* at a time.  Each round scans every route it can currently reach, so
the algorithm's cost depends on the number of legs in the answer rather than the
number of stops in the network -- which is what makes it suitable for the
national-scale networks MoveIn is built for.

This implementation is **multi-criteria**: rather than optimising travel time
alone, every stop keeps a Pareto frontier over

    (arrival time, fare, interchanges, walking distance)

so a slower-but-cheaper journey is never discarded in favour of a faster one.
That is what makes the product's headline question -- "what is the *best* way
from A to B" -- answerable at all, because "best" differs by traveller.

Fare is accumulated during the search using the same pricing function the fare
engine uses, so the cheapest journey RAPTOR returns is the cheapest journey the
engine can actually sell.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from ..domain.models import CO2_G_PER_PKM, Mode, Stop
from ..domain.network_spec import FareRule
from ..ingest.network_compiler import price_for
from .fares import MODE_TARIFFS
from .graph import MODE_ACCESS_WALK_M, RoutePattern, TransitGraph, TripProfile
from ..ingest.geo import (
    bearing_deg,
    cycle_distance_m,
    cycle_duration_s,
    haversine_m,
    relative_direction,
    walk_distance_m,
    walk_duration_s,
)

#: How many Pareto-optimal labels to retain per stop.  Keeping more gives
#: marginally better journeys at a superlinear cost; 8 is the knee of the curve
#: for networks of this size.
MAX_LABELS_PER_STOP = 8


@dataclass(slots=True)
class TransitLeg:
    """One ride on one vehicle."""

    pattern_key: str
    trip_id: str
    route_id: str
    mode: Mode
    operator_code: str
    board_stop_id: str
    alight_stop_id: str
    board_index: int
    alight_index: int
    departure_s: int
    arrival_s: int
    distance_m: float
    fare_p: int
    co2_g: float
    reliability: float
    headsign: str
    accessible: bool
    #: Live delay in seconds, filled in by the realtime layer when available.
    delay_s: int = 0

    @property
    def duration_s(self) -> int:
        return self.arrival_s - self.departure_s


@dataclass(slots=True)
class WalkLeg:
    """A walking connection: access, egress, or an interchange."""

    from_stop_id: str
    to_stop_id: str
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    distance_m: float
    duration_s: int
    #: "access" | "transfer" | "egress"
    kind: str = "transfer"

    @property
    def instruction(self) -> str:
        if self.distance_m < 30:
            return "continue on foot"
        return relative_direction(
            bearing_deg(self.from_lat, self.from_lon, self.to_lat, self.to_lon)
        )


@dataclass(slots=True)
class OnDemandLeg:
    """A taxi or ride-hailing leg, priced per kilometre rather than scheduled."""

    operator_code: str
    mode: Mode
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    distance_m: float
    duration_s: int
    fare_p: int
    co2_g: float


@dataclass(slots=True)
class Label:
    """A Pareto-optimal way of having reached a stop at a point in the journey."""

    stop_id: str
    arrival_s: int
    fare_p: int
    transfers: int
    walk_m: int
    legs: tuple[TransitLeg | WalkLeg | OnDemandLeg, ...] = ()
    access_walk_m: float = 0.0
    access_walk_s: int = 0
    origin_stop_id: str = ""
    #: Number of transit legs taken to get here.
    leg_count: int = 0
    co2_g: float = 0.0

    def signature(self) -> tuple:
        """Identity used to deduplicate labels that reach the same state."""
        if not self.legs:
            return ("access", self.stop_id, self.arrival_s)
        last = self.legs[-1]
        # The last leg may be the walk that reached this stop, so identity comes
        # from whichever kind of leg it is.
        return (
            getattr(last, "trip_id", ""),
            getattr(last, "alight_stop_id", None) or getattr(last, "to_stop_id", ""),
            self.arrival_s,
        )


def _boardable(labels: list[Label], limit: int) -> list[Label]:
    """Pick the labels worth boarding a vehicle from.

    Because every trip on a pattern is priced identically, the cheapest label at
    a stop and the earliest one can both lead to Pareto-optimal journeys.  A
    single min-arrival label would quietly drop the cheaper alternative, so keep
    the best label by each criterion that the traveller cares about.
    """
    if limit <= 1 or len(labels) == 1:
        return list(labels[:1])
    chosen: list[Label] = []
    for key in (
        lambda l: (l.arrival_s, l.fare_p),
        lambda l: (l.fare_p, l.arrival_s),
        lambda l: (l.transfers, l.arrival_s, l.fare_p),
        lambda l: (l.walk_m, l.arrival_s, l.fare_p),
    ):
        best = min(labels, key=key)
        if not any(best.signature() == c.signature() for c in chosen):
            chosen.append(best)
        if len(chosen) >= limit:
            break
    return chosen


def _dominates(a: Label, b: Label) -> bool:
    """True when label ``a`` is at least as good as ``b`` on every criterion."""
    if (
        a.arrival_s <= b.arrival_s
        and a.fare_p <= b.fare_p
        and a.transfers <= b.transfers
        and a.walk_m <= b.walk_m
    ):
        return (
            a.arrival_s < b.arrival_s
            or a.fare_p < b.fare_p
            or a.transfers < b.transfers
            or a.walk_m < b.walk_m
        )
    return False


class _Frontier:
    """Pareto frontier of labels for one stop, with a hard size cap."""

    __slots__ = ("labels", "_seen")

    def __init__(self) -> None:
        self.labels: list[Label] = []
        self._seen: set[tuple] = set()

    def offer(self, label: Label) -> bool:
        """Try to add a label.  Returns True when the frontier changed."""
        sig = label.signature()
        if sig in self._seen:
            return False
        for existing in self.labels:
            if _dominates(existing, label):
                return False
        self._seen.add(sig)
        self.labels = [l for l in self.labels if not _dominates(label, l)]
        self.labels.append(label)
        if len(self.labels) > MAX_LABELS_PER_STOP:
            # Keep the labels that are best at something: earliest, cheapest,
            # fewest changes, least walking -- then fill by generalised cost.
            keep: list[Label] = []
            for key in (
                lambda l: l.arrival_s,
                lambda l: l.fare_p,
                lambda l: l.transfers,
                lambda l: l.walk_m,
            ):
                best = min(self.labels, key=key)
                if best not in keep:
                    keep.append(best)
            remaining = sorted(
                (l for l in self.labels if l not in keep),
                key=lambda l: (l.arrival_s + l.fare_p * 2 + l.transfers * 300),
            )
            self.labels = keep + remaining[: max(0, MAX_LABELS_PER_STOP - len(keep))]
        return True


@dataclass
class SearchOptions:
    """Tunables for one search."""

    max_legs: int = 5
    max_access_walk_m: int = 2000
    #: Waive the per-mode walk-to-stop limit at an end the traveller named.
    per_mode_access_limit: bool = True
    max_transfer_walk_m: int = 900
    #: How many different departures to ride simultaneously out of one stop.
    #: More than one keeps both the earliest and the cheapest option alive.
    boardings_per_position: int = 3
    min_connection_s: int = 180
    #: Stop expanding once a journey would exceed this.
    max_journey_duration_s: int = 8 * 3600
    #: Include taxi / ride-hailing as a first/last mile option.
    allow_on_demand: bool = True
    #: Require every leg to be step-free.
    require_step_free: bool = False
    #: Cap on how many alternative departure times to explore.
    departure_sweep: int = 3
    #: Sweep interval, in seconds.
    departure_interval_s: int = 1800
    #: No single walk in a returned journey may take longer than this.  MoveIn
    #: treats a long walk as a decision the traveller makes, not one made for
    #: them, so this is a hard ceiling that the request can tighten.
    max_walk_s: int | None = None
    #: Transit modes the traveller will use, by ``Mode`` value.  ``None`` means
    #: every mode is allowed; walking is always allowed, because refusing to
    #: walk does not remove the walk from the pavement.
    allowed_modes: frozenset[str] | None = None
    #: Walking beyond this stops being a stroll and starts being the reason a
    #: journey was rejected.  Journeys that cross it are returned, labelled, and
    #: kept out of the headline trade-offs unless nothing else competes.
    comfortable_walk_s: int = 900


@dataclass
class SearchResult:
    """Everything the search found, ready to be assembled into journeys."""

    #: Reached stops and the best labels that got there.
    labels: dict[str, list[Label]] = field(default_factory=dict)
    #: Access walks from the origin to each seeded stop.
    access: dict[str, WalkLeg] = field(default_factory=dict)
    #: On-demand legs from the origin, keyed by the stop they reach.
    on_demand: dict[str, OnDemandLeg] = field(default_factory=dict)
    origins: list[Stop] = field(default_factory=list)
    destinations: list[Stop] = field(default_factory=list)
    origin_point: tuple[float, float] | None = None
    destination_point: tuple[float, float] | None = None
    rounds_used: int = 0
    stops_scanned: int = 0
    duration_ms: int = 0


class Raptor:
    """Multi-criteria RAPTOR over a :class:`TransitGraph`."""

    def __init__(self, graph: TransitGraph, fare_rules: dict[str, FareRule]) -> None:
        self.graph = graph
        #: route_id -> the pricing rule for that route's corridor.
        self.fare_rules = fare_rules
        self._pattern_keys = list(graph.patterns.keys())
        self._pattern_stop_routes: dict[str, list[tuple[str, int]]] = graph.stop_routes
        #: (pattern key, position) -> departure times at that stop, in order.
        self._boards: dict[
            tuple[str, int], tuple[tuple[int, ...], tuple[int, ...]]
        ] = {}

    # -- public API --------------------------------------------------------
    def search(
        self,
        *,
        origin: tuple[float, float],
        destination: tuple[float, float],
        departure_s: int,
        services: set[str],
        options: SearchOptions | None = None,
    ) -> SearchResult:
        from time import perf_counter

        started = perf_counter()
        options = options or SearchOptions()

        origins = self.graph.stops_near(
            origin[0], origin[1], options.max_access_walk_m, limit=12,
            per_mode_limit=options.per_mode_access_limit,
        )
        destinations = self.graph.stops_near(
            destination[0], destination[1], options.max_access_walk_m, limit=12,
            per_mode_limit=options.per_mode_access_limit,
        )
        result = SearchResult(
            origin_point=origin,
            destination_point=destination,
            origins=[s for s, _ in origins],
            destinations=[s for s, _ in destinations],
        )
        if not origins or not destinations:
            result.duration_ms = int((perf_counter() - started) * 1000)
            return result

        frontier: dict[str, _Frontier] = {}
        for stop, distance in origins:
            walk_s = walk_duration_s(distance)
            leg = WalkLeg(
                from_stop_id="__origin__",
                to_stop_id=stop.id,
                from_lat=origin[0],
                from_lon=origin[1],
                to_lat=stop.lat,
                to_lon=stop.lon,
                distance_m=distance,
                duration_s=walk_s,
                kind="access",
            )
            result.access[stop.id] = leg
            frontier.setdefault(stop.id, _Frontier()).offer(
                Label(
                    stop_id=stop.id,
                    arrival_s=departure_s + walk_s,
                    fare_p=0,
                    transfers=0,
                    walk_m=int(distance),
                    access_walk_m=distance,
                    access_walk_s=walk_s,
                    origin_stop_id=stop.id,
                )
            )

        if options.allow_on_demand and (
            options.allowed_modes is None
            or {"taxi", "ridehail"} & set(options.allowed_modes)
        ):
            self._seed_on_demand(origin, destinations, departure_s, result, frontier)

        marked = set(frontier.keys())
        rounds = 0
        for round_index in range(1, options.max_legs + 1):
            if not marked:
                break
            rounds = round_index
            newly_marked = self._round(
                marked, frontier, options, services, departure_s
            )
            marked = newly_marked
            result.stops_scanned += len(marked)
            if not marked:
                break

        result.labels = {sid: f.labels for sid, f in frontier.items() if f.labels}
        result.rounds_used = rounds
        result.duration_ms = int((perf_counter() - started) * 1000)
        return result

    # -- internals ---------------------------------------------------------
    def _departure_table(
        self, pattern_key: str, pattern: RoutePattern, position: int
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """Departure times at one stop of a pattern, and which trip each is.

        Boarding has to be decided from the time the vehicle leaves *this* stop.
        Searching the pattern's origin departures instead is off by the running
        time from the origin -- hours on a long-distance corridor -- and makes
        the planner skip every train that had already started its journey by the
        time the traveller reached the interchange.  (That bug is why
        Nottingham to Leeds went via a two-and-a-half hour wait at Long Eaton
        instead of an eight-minute change at Chesterfield.)
        """
        key = (pattern_key, position)
        table = self._boards.get(key)
        if table is None:
            profiles = self.graph.trip_profiles
            pairs = sorted(
                (profiles[trip_id].departures[position], index)
                for index, trip_id in enumerate(pattern.trip_ids)
            )
            table = (
                tuple(time for time, _ in pairs),
                tuple(index for _, index in pairs),
            )
            self._boards[key] = table
        return table

    def _next_active_trip(
        self,
        pattern_key: str,
        pattern: RoutePattern,
        position: int,
        after_s: int,
        services: set[str],
    ) -> int | None:
        """Index of the first trip that leaves ``position`` late enough, today.

        Without the service filter the planner would happily sell a Sunday
        traveller a weekday timetable, which is the single most embarrassing
        bug a journey planner can have.
        """
        times, order = self._departure_table(pattern_key, pattern, position)
        idx = bisect.bisect_left(times, after_s)
        profiles = self.graph.trip_profiles
        while idx < len(times):
            trip_index = order[idx]
            if profiles[pattern.trip_ids[trip_index]].service_id in services:
                return trip_index
            idx += 1
        return None

    def _seed_on_demand(
        self,
        origin: tuple[float, float],
        destinations: list[tuple[Stop, float]],
        departure_s: int,
        result: SearchResult,
        frontier: dict[str, _Frontier],
    ) -> None:
        """Offer a taxi/ride-hailing hop from the origin to nearby hubs.

        Taxis are how many real journeys actually start, and leaving them out
        would make MoveIn's answers worse than the apps it replaces.
        """
        # Only worth it to reach a hub the traveller cannot comfortably walk to.
        hubs = self.graph.stops_near(origin[0], origin[1], 6000, limit=6)
        for stop, _ in hubs:
            straight = haversine_m(origin[0], origin[1], stop.lat, stop.lon)
            if straight < 1200:
                continue  # walkable: a taxi would never win
            road_m = straight * 1.28 + 250
            duration = int(road_m / (28_000 / 3600)) + 180
            # One tariff, one place: the meter lives in the fare engine, so a
            # taxi quoted here costs the same as a taxi priced anywhere else.
            for code, mode in (("TAXI", Mode.TAXI), ("UBER", Mode.RIDEHAIL)):
                if (
                    options.allowed_modes is not None
                    and mode.value not in options.allowed_modes
                ):
                    continue
                tariff = MODE_TARIFFS[mode]
                fare_p = int(
                    round((tariff.base + tariff.rate_per_km * road_m / 1000) * 100)
                )
                leg = OnDemandLeg(
                    operator_code=code,
                    mode=mode,
                    from_lat=origin[0],
                    from_lon=origin[1],
                    to_lat=stop.lat,
                    to_lon=stop.lon,
                    distance_m=road_m,
                    duration_s=duration,
                    fare_p=fare_p,
                    co2_g=CO2_G_PER_PKM[Mode.TAXI] * road_m / 1000,
                )
                result.on_demand.setdefault(stop.id, leg)
                frontier.setdefault(stop.id, _Frontier()).offer(
                    Label(
                        stop_id=stop.id,
                        arrival_s=departure_s + duration,
                        fare_p=fare_p,
                        transfers=0,
                        walk_m=0,
                        origin_stop_id=stop.id,
                        co2_g=leg.co2_g,
                    )
                )

    def _round(
        self,
        marked: set[str],
        frontier: dict[str, _Frontier],
        options: SearchOptions,
        services: set[str],
        departure_s: int,
    ) -> set[str]:
        """One RAPTOR round: ride one more vehicle from every marked stop."""
        newly_marked: set[str] = set()
        # Which patterns can we board, and from where?
        boardings: dict[str, list[tuple[int, Label]]] = {}
        for stop_id in marked:
            for pattern_key, position in self._pattern_stop_routes.get(stop_id, ()):
                boardings.setdefault(pattern_key, []).append((position, stop_id))

        for pattern_key, stops_and_positions in boardings.items():
            pattern = self.graph.patterns[pattern_key]
            if (
                options.allowed_modes is not None
                and pattern.mode.value not in options.allowed_modes
            ):
                # The traveller said which modes they will use.  Riding a mode
                # they excluded is not an alternative, it is a different journey.
                continue
            rule = self.fare_rules.get(pattern.route_id)

            # The labels worth boarding from, per stop on this pattern.
            candidates: dict[int, list[Label]] = {}
            for position, stop_id in stops_and_positions:
                labels = frontier.get(stop_id, _Frontier()).labels
                if labels:
                    candidates[position] = _boardable(
                        labels, options.boardings_per_position
                    )
            if not candidates:
                continue

            # Walk the pattern left to right while riding at most
            # `boardings_per_position` vehicles at once.  Riding several at once
            # matters: the earliest label at a stop and the cheapest one are
            # often different labels, and a single "best" ride would silently
            # throw away the money-saving journey.
            active: list[tuple[TripProfile, int, Label, str]] = []
            min_pos = min(candidates)
            for position in range(min_pos, len(pattern.stops)):
                # 1. Anyone still aboard may get off here.
                for profile, board_position, board_label, _trip in list(active):
                    if board_position < position:
                        self._try_alight(
                            pattern, pattern_key, profile,
                            (board_position, board_label), position,
                            frontier, newly_marked, rule, options, departure_s,
                        )

                # 2. Board the earliest trip each candidate label makes.
                for label in candidates.get(position, ()):
                    needed = label.arrival_s + (
                        options.min_connection_s if label.legs else 0
                    )
                    if needed - departure_s > options.max_journey_duration_s:
                        continue
                    idx = self._next_active_trip(
                        pattern_key, pattern, position, needed, services
                    )
                    if idx is None:
                        continue
                    trip_id = pattern.trip_ids[idx]
                    if any(ride[3] == trip_id for ride in active):
                        continue
                    profile = self.graph.trip_profiles[trip_id]
                    # Drop rides this one beats: every trip on a pattern is
                    # priced identically, so a ride that leaves this stop no
                    # later and boarded from no dearer a label dominates.
                    active = [
                        ride
                        for ride in active
                        if not (
                            ride[0].departures[position] >= profile.departures[position]
                            and ride[2].fare_p >= label.fare_p
                        )
                    ]
                    active.append((profile, position, label, trip_id))
                    if len(active) > options.boardings_per_position:
                        active.sort(key=lambda r: r[0].departures[position])
                        active = active[: options.boardings_per_position]

            # 3. Alight at the terminus.
            last = len(pattern.stops) - 1
            for profile, board_position, board_label, _trip in list(active):
                if board_position < last:
                    self._try_alight(
                        pattern, pattern_key, profile, (board_position, board_label),
                        last, frontier, newly_marked, rule, options, departure_s,
                    )
        return newly_marked

    def _try_alight(
        self,
        pattern: RoutePattern,
        pattern_key: str,
        profile: TripProfile,
        riding_from: tuple[int, Label],
        position: int,
        frontier: dict[str, _Frontier],
        newly_marked: set[str],
        rule: FareRule | None,
        options: SearchOptions,
        departure_s: int,
    ) -> None:
        board_position, board_label = riding_from
        if position <= board_position:
            return
        alight_stop = pattern.stops[position]
        if alight_stop == board_label.stop_id:
            return

        departure = profile.departures[board_position]
        arrival = profile.arrivals[position]
        if arrival <= board_label.arrival_s:
            return  # not a forward move; refuse to board a vehicle going backwards
        if arrival - departure_s > options.max_journey_duration_s:
            return

        distance = pattern.distance_between(board_position, position)
        fare_p = self._leg_fare_pence(rule, distance)
        co2 = CO2_G_PER_PKM.get(pattern.mode, 0.0) * distance / 1000.0

        # Interchange walking is already folded into the label when the
        # transfer is made (see _offer_transfers), so the ride itself adds none.
        access_walk = board_label.access_walk_m if not board_label.legs else 0.0

        leg = TransitLeg(
            pattern_key=pattern_key,
            trip_id=profile.trip_id,
            route_id=pattern.route_id,
            mode=pattern.mode,
            operator_code=pattern.operator_code,
            board_stop_id=board_label.stop_id,
            alight_stop_id=alight_stop,
            board_index=board_position,
            alight_index=position,
            departure_s=departure,
            arrival_s=arrival,
            distance_m=distance,
            fare_p=fare_p,
            co2_g=co2,
            reliability=profile.reliability,
            headsign=profile.headsign or self.graph.stops[alight_stop].name,
            accessible=profile.wheelchair_accessible,
        )

        new_label = Label(
            stop_id=alight_stop,
            arrival_s=arrival,
            fare_p=board_label.fare_p + fare_p,
            transfers=board_label.transfers + (1 if board_label.legs else 0),
            walk_m=board_label.walk_m,
            legs=board_label.legs + (leg,),
            access_walk_m=access_walk,
            access_walk_s=board_label.access_walk_s,
            origin_stop_id=board_label.origin_stop_id,
            leg_count=board_label.leg_count + 1,
            co2_g=board_label.co2_g + co2,
        )

        if options.require_step_free and not profile.wheelchair_accessible:
            return

        f = frontier.setdefault(alight_stop, _Frontier())
        if f.offer(new_label):
            newly_marked.add(alight_stop)

        # Now allow walking interchanges from the newly reached stop.
        self._offer_transfers(new_label, frontier, newly_marked, options, departure_s)

    def _offer_transfers(
        self,
        label: Label,
        frontier: dict[str, _Frontier],
        newly_marked: set[str],
        options: SearchOptions,
        departure_s: int,
    ) -> None:
        """Let a traveller walk from the stop they just reached to a nearby one."""
        for transfer in self.graph.transfers.get(label.stop_id, ()):
            if transfer.distance_m > options.max_transfer_walk_m:
                continue
            target = self.graph.stops.get(transfer.to_stop_id)
            if target is None:
                continue
            if options.require_step_free and not (
                target.wheelchair_boarding == 1
                and self.graph.stops[label.stop_id].wheelchair_boarding == 1
            ):
                continue
            duration = transfer.min_transfer_s
            arrival = label.arrival_s + duration
            if arrival - departure_s > options.max_journey_duration_s:
                continue
            # The walk is a step in the journey, so it is recorded as one: a
            # traveller who is told to get off at New Street and onto a coach at
            # Moor Street needs to see the four minutes between them.
            walk_leg = WalkLeg(
                from_stop_id=label.stop_id,
                to_stop_id=target.id,
                from_lat=self.graph.stops[label.stop_id].lat,
                from_lon=self.graph.stops[label.stop_id].lon,
                to_lat=target.lat,
                to_lon=target.lon,
                distance_m=transfer.distance_m,
                duration_s=duration,
                kind="transfer",
            )
            walk_label = replace(
                label,
                stop_id=target.id,
                arrival_s=arrival,
                walk_m=label.walk_m + int(transfer.distance_m),
                transfers=label.transfers,
                legs=label.legs + (walk_leg,),
            )
            f = frontier.setdefault(target.id, _Frontier())
            if f.offer(walk_label):
                newly_marked.add(target.id)

    def _leg_fare_pence(self, rule: FareRule | None, distance_m: float) -> int:
        if rule is None:
            return 0
        return int(round(price_for(rule, distance_m / 1000.0) * 100))
