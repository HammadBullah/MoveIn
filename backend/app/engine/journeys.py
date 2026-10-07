"""Journey assembly, optimisation and ranking.

The search in :mod:`app.engine.search` works in terms of Pareto-optimal ways of
*reaching a stop*.  This module turns those into complete, presentable journeys --
origin to front door -- and then answers the question the product is really
about: given this traveller's priorities, which of these is best?

Ranking follows the brief's model.  Each journey is scored on four criteria
and combined with weights that depend on the traveller's preference:

=================  ======  ====  =======  =======
Preference         Price   Time  Changes  Walking
=================  ======  ====  =======  =======
Cheapest              80%   10%       5%      5%
Fastest               10%   80%       5%      5%
Best value            40%   30%      15%     15%
Fewest changes        15%   20%      55%     10%
Least walking         15%   20%      10%     55%
Lowest emissions      45%   25%      10%     20%
=================  ======  ====  =======  =======

Scores are *normalised within the candidate set*, so the weights are meaningful
even when every option is expensive or every option is slow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum

from ..domain.models import CO2_G_PER_PKM, Mode
from .fares import FareBreakdown, FareEngine, PricedLeg, TravellerProfile
from .graph import MODE_ACCESS_WALK_M, TransitGraph
from .search import Label, OnDemandLeg, SearchResult, TransitLeg, WalkLeg
from ..ingest.geo import (
    bearing_deg,
    cycle_distance_m,
    cycle_duration_s,
    haversine_m,
    relative_direction,
    walk_distance_m,
    walk_duration_s,
)


class Preference(str, Enum):
    """What the traveller is optimising for."""

    CHEAPEST = "cheapest"
    FASTEST = "fastest"
    BEST_VALUE = "best_value"
    FEWEST_CHANGES = "fewest_changes"
    LEAST_WALKING = "least_walking"
    LOWEST_EMISSIONS = "lowest_emissions"
    ACCESSIBLE = "accessible"
    BALANCED = "balanced"

    @property
    def label(self) -> str:
        return {
            Preference.CHEAPEST: "Cheapest",
            Preference.FASTEST: "Fastest",
            Preference.BEST_VALUE: "Best value",
            Preference.FEWEST_CHANGES: "Fewest changes",
            Preference.LEAST_WALKING: "Least walking",
            Preference.LOWEST_EMISSIONS: "Lowest emissions",
            Preference.ACCESSIBLE: "Step-free",
            Preference.BALANCED: "Balanced",
        }[self]

    @property
    def weights(self) -> dict[str, float]:
        """Weights over price, time, changes and walking."""
        return {
            Preference.CHEAPEST: {"price": 0.80, "time": 0.10, "changes": 0.05, "walking": 0.05},
            Preference.FASTEST: {"price": 0.10, "time": 0.80, "changes": 0.05, "walking": 0.05},
            Preference.BEST_VALUE: {"price": 0.40, "time": 0.30, "changes": 0.15, "walking": 0.15},
            Preference.FEWEST_CHANGES: {"price": 0.15, "time": 0.20, "changes": 0.55, "walking": 0.10},
            Preference.LEAST_WALKING: {"price": 0.15, "time": 0.20, "changes": 0.10, "walking": 0.55},
            Preference.LOWEST_EMISSIONS: {"price": 0.45, "time": 0.25, "changes": 0.10, "walking": 0.20},
            Preference.ACCESSIBLE: {"price": 0.30, "time": 0.35, "changes": 0.25, "walking": 0.10},
            Preference.BALANCED: {"price": 0.40, "time": 0.30, "changes": 0.15, "walking": 0.15},
        }[self]


# --------------------------------------------------------------------------
# Journey shape
# --------------------------------------------------------------------------


@dataclass
class Journey:
    """A complete, presentable journey from the traveller's origin to destination."""

    id: str
    departure: datetime
    arrival: datetime
    legs: list[object] = field(default_factory=list)
    price: float = 0.0
    fare: FareBreakdown | None = None
    changes: int = 0
    walking_m: float = 0.0
    walking_s: int = 0
    co2_g: float = 0.0
    #: Mean reliability of the transit legs, 0-1.
    reliability: float = 1.0
    step_free: bool = True
    #: Per-criterion quality, 0-100; higher is better.
    scores: dict[str, float] = field(default_factory=dict)
    #: Weighted composite score for the requested preference; 0-100, higher is better.
    score: float = 0.0
    #: Set when this journey is the best example of an archetype.
    archetypes: list[str] = field(default_factory=list)
    #: Which operators the journey uses.
    operators: list[str] = field(default_factory=list)
    #: Modes used, in order, deduplicated.
    modes: list[str] = field(default_factory=list)
    #: Notes such as ticket-combination advice.
    notes: list[str] = field(default_factory=list)
    #: Number of vehicles boarded.
    transit_legs: int = 0
    #: The longest single walk in the journey, in seconds.
    longest_walk_s: int = 0
    #: "comfortable" | "long" -- whether any single walk exceeds the threshold.
    walk_comfort: str = "comfortable"

    @property
    def duration_s(self) -> int:
        return int((self.arrival - self.departure).total_seconds())

    @property
    def duration_label(self) -> str:
        return format_duration(self.duration_s)

    @property
    def route_label(self) -> str:
        """A compact summary such as ``Bus + Train``."""
        labels: list[str] = []
        for leg in self.legs:
            if isinstance(leg, TransitLeg):
                name = leg.mode.label
                if not labels or labels[-1] != name:
                    labels.append(name)
            elif isinstance(leg, OnDemandLeg):
                name = leg.mode.label
                if not labels or labels[-1] != name:
                    labels.append(name)
        return " + ".join(labels) if labels else "Walk"

    @property
    def is_walk_only(self) -> bool:
        return self.transit_legs == 0


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours}h {minutes:02d}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def _walk_leg_between(
    frm, to, kind: str, *, from_stop_id: str = "", to_stop_id: str = ""
) -> WalkLeg:
    """A walk between two points, optionally anchored to the stops at each end.

    The stop ids matter to the traveller: "walk 13 min from Birmingham New
    Street to Birmingham" tells them where they are, and "walk 13 min" does not.
    """
    distance = walk_distance_m(frm[0], frm[1], to[0], to[1])
    return WalkLeg(
        from_stop_id=from_stop_id,
        to_stop_id=to_stop_id,
        from_lat=frm[0],
        from_lon=frm[1],
        to_lat=to[0],
        to_lon=to[1],
        distance_m=distance,
        duration_s=walk_duration_s(distance),
        kind=kind,
    )


def _merge_walks(legs: list) -> list:
    """Collapse consecutive walks into one.

    Walking from a coach station to a nearby stop and then on to the destination
    is a single walk: the stop in between is a waypoint, not a place the
    traveller asked to go, and showing "walk 8 min" twice for one continuous
    walk reads as two errands.
    """
    merged: list = []
    for leg in legs:
        if isinstance(leg, WalkLeg) and merged and isinstance(merged[-1], WalkLeg):
            previous = merged[-1]
            kinds = {previous.kind, leg.kind}
            merged[-1] = replace(
                previous,
                to_stop_id=leg.to_stop_id,
                to_lat=leg.to_lat,
                to_lon=leg.to_lon,
                distance_m=previous.distance_m + leg.distance_m,
                duration_s=previous.duration_s + leg.duration_s,
                kind=(
                    "egress" if "egress" in kinds
                    else "access" if "access" in kinds
                    else "transfer"
                ),
            )
            continue
        merged.append(leg)
    return merged


class JourneyAssembler:
    """Turns search labels into complete journeys."""

    def __init__(self, graph: TransitGraph, fare_engine: FareEngine) -> None:
        self.graph = graph
        self.fares = fare_engine

    def assemble(
        self,
        label: Label,
        *,
        destination: tuple[float, float],
        destination_stop_id: str,
        search: SearchResult,
        departure_s: int,
        service_day: datetime,
        traveller: TravellerProfile,
        settings_discounts: tuple[float, float] = (0.34, 0.25),
        max_egress_walk_m: int = 2000,
        max_walk_s: int | None = None,
        comfortable_walk_s: int = 900,
    ) -> Journey | None:
        """Build one journey from a search label plus access and egress legs."""
        dest_stop = self.graph.stops.get(destination_stop_id)
        if dest_stop is None:
            return None

        legs: list[object] = []

        # --- access ------------------------------------------------------
        access = search.access.get(label.origin_stop_id)
        if access is not None and access.distance_m > 40:
            legs.append(access)
        on_demand = search.on_demand.get(label.origin_stop_id)
        if on_demand is not None and not label.legs:
            legs.append(on_demand)

        # --- the transit legs the search found ---------------------------
        for leg in label.legs:
            legs.append(leg)

        # --- egress ------------------------------------------------------
        reach_lat, reach_lon = dest_stop.lat, dest_stop.lon
        egress = _walk_leg_between(
            (reach_lat, reach_lon), destination, "egress", from_stop_id=dest_stop.id
        )
        if egress.distance_m > 40:
            legs.append(egress)

        if not label.legs and egress.distance_m <= 40 and not on_demand:
            return None  # nothing but a trivial walk; not a journey worth showing

        # A walk into a walk is one walk; see _merge_walks.
        legs = _merge_walks(legs)

        # Walking is the one part of a journey a traveller cannot opt out of
        # midway, so it is bounded before anything else: nobody plans a journey
        # around a 25 minute walk, and offering one as if it were normal
        # buries the options they would actually take.
        walk_legs = [leg for leg in legs if isinstance(leg, WalkLeg)]
        longest_walk_s = max((leg.duration_s for leg in walk_legs), default=0)
        if max_walk_s is not None and longest_walk_s > max_walk_s:
            return None
        walk_comfort = (
            "long" if longest_walk_s > comfortable_walk_s else "comfortable"
        )

        # --- timing ------------------------------------------------------
        access_s = access.duration_s if access is not None and access.distance_m > 40 else 0
        on_demand_s = on_demand.duration_s if (on_demand and not label.legs) else 0

        # A journey starts when the traveller does, not when they asked for it.
        # If the first step is the walk to the stop, "departing" at the requested
        # minute would credit the journey with a wait spent standing in the
        # street -- and the itinerary would disagree with its own first leg.
        departure = service_day + timedelta(seconds=departure_s)
        if legs:
            first_transit = next(
                (leg for leg in legs if isinstance(leg, (TransitLeg, OnDemandLeg))), None
            )
            if first_transit is not None and isinstance(legs[0], WalkLeg):
                departure = service_day + timedelta(
                    seconds=first_transit.departure_s - legs[0].duration_s
                )
            elif first_transit is not None and first_transit is legs[0]:
                departure = service_day + timedelta(seconds=first_transit.departure_s)

        arrival_seconds = label.arrival_s
        # The label's own arrival is the latest thing that happened, whether the
        # last step was a vehicle or the walk to this stop.
        if label.legs:
            last = label.legs[-1]
            if isinstance(last, (TransitLeg, OnDemandLeg)):
                arrival_seconds = max(arrival_seconds, last.arrival_s)
        arrival = service_day + timedelta(seconds=arrival_seconds + egress.duration_s)

        # --- pricing -----------------------------------------------------
        fare_inputs: list[dict] = []
        for leg in legs:
            if isinstance(leg, TransitLeg):
                fare_inputs.append({
                    "route_id": leg.route_id,
                    "operator_code": leg.operator_code,
                    "mode": leg.mode,
                    "distance_m": leg.distance_m,
                })
            elif isinstance(leg, OnDemandLeg):
                fare_inputs.append({
                    "route_id": "",
                    "operator_code": leg.operator_code,
                    "mode": leg.mode,
                    "distance_m": leg.distance_m,
                    "fare": leg.fare_p / 100.0,
                })

        when = departure
        fare = self.fares.price_journey(
            fare_inputs,
            when=when,
            traveller=traveller,
            settings_discounts=settings_discounts,
        )

        transit_legs = [l for l in legs if isinstance(l, TransitLeg)]
        changes = max(0, len(transit_legs) - 1)
        walking_m = sum(
            getattr(l, "distance_m", 0.0)
            for l in legs
            if isinstance(l, WalkLeg)
        )
        walking_s = sum(
            getattr(l, "duration_s", 0)
            for l in legs
            if isinstance(l, WalkLeg)
        )
        co2 = sum(getattr(l, "co2_g", 0.0) for l in legs)
        reliability = (
            sum(l.reliability for l in transit_legs) / len(transit_legs)
            if transit_legs
            else 1.0
        )
        step_free = all(
            getattr(l, "accessible", True) for l in legs if isinstance(l, TransitLeg)
        ) and all(
            self.graph.stops.get(getattr(l, "alight_stop_id", ""), dest_stop).wheelchair_boarding == 1
            for l in transit_legs
        )

        operators: list[str] = []
        modes: list[str] = []
        for leg in legs:
            if isinstance(leg, (TransitLeg, OnDemandLeg)):
                if leg.operator_code not in operators:
                    operators.append(leg.operator_code)
                if leg.mode.value not in modes:
                    modes.append(leg.mode.value)

        journey = Journey(
            id="",
            departure=departure,
            arrival=arrival,
            legs=legs,
            price=fare.total,
            fare=fare,
            changes=changes,
            walking_m=round(walking_m, 1),
            walking_s=walking_s,
            co2_g=round(co2, 1),
            reliability=round(reliability, 3),
            step_free=step_free,
            operators=operators,
            modes=modes,
            notes=list(fare.notes),
            transit_legs=len(transit_legs),
            longest_walk_s=longest_walk_s,
            walk_comfort=walk_comfort,
        )
        return journey


# --------------------------------------------------------------------------
# Ranking
# --------------------------------------------------------------------------


def _normalise(values: list[float]) -> list[float]:
    """Min-max normalise to 0-1, where 0 is the best (lowest) value."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if math.isclose(hi, lo):
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


class JourneyRanker:
    """Scores journeys for a preference and selects the archetypes to show."""

    def __init__(self, settings) -> None:
        self.settings = settings

    def rank(
        self, journeys: list[Journey], preference: Preference
    ) -> list[Journey]:
        if not journeys:
            return journeys

        prices = [j.price for j in journeys]
        durations = [float(j.duration_s) for j in journeys]
        changes = [float(j.changes) for j in journeys]
        walks = [j.walking_m for j in journeys]

        n_price = _normalise(prices)
        n_time = _normalise(durations)
        n_changes = _normalise(changes)
        n_walk = _normalise(walks)

        # The normalised values run 0 (best) to 1 (worst), so the score is
        # flipped to 0-100 where 100 is the best possible journey.  Reporting
        # the raw weighted penalty instead would put every score between 0 and
        # 1, which reads as "zero out of a hundred" on a results card.
        weights = preference.weights
        for i, journey in enumerate(journeys):
            quality = {
                "price": 100.0 * (1.0 - n_price[i]),
                "time": 100.0 * (1.0 - n_time[i]),
                "changes": 100.0 * (1.0 - n_changes[i]),
                "walking": 100.0 * (1.0 - n_walk[i]),
            }
            journey.scores = {
                name: round(value, 1) for name, value in quality.items()
            }
            # Weights are fractions, quality is out of 100, so this lands
            # back on a 0-100 scale.
            journey.score = round(
                weights["price"] * quality["price"]
                + weights["time"] * quality["time"]
                + weights["changes"] * quality["changes"]
                + weights["walking"] * quality["walking"],
                1,
            )

        return sorted(journeys, key=lambda j: (-j.score, j.arrival, j.price))

    @staticmethod
    def select_archetypes(journeys: list[Journey]) -> list[Journey]:
        """Tag each journey with the archetypes it wins.

        The brief's results screen shows a labelled card per trade-off rather
        than one "best" answer, because the whole point of the product is that
        the trade-off is the traveller's to make.
        """
        if not journeys:
            return journeys

        def best(key_fn, *, exclude_walk_only: bool = True):
            pool = [
                j for j in journeys
                if not (exclude_walk_only and j.is_walk_only)
            ] or journeys
            # A journey with a long walk can still win a headline -- sometimes
            # it is the only option -- but it does not win one while a
            # comfortable journey could have.  "Cheapest" should not quietly
            # mean "and a 24 minute walk"
            comfortable = [j for j in pool if j.walk_comfort == "comfortable"]
            return min(comfortable or pool, key=key_fn)

        # Order matters for the display: the headline cards first.
        rules = [
            ("cheapest", lambda j: (j.price, j.duration_s)),
            ("fastest", lambda j: (j.duration_s, j.price)),
            ("fewest_changes", lambda j: (j.changes, j.duration_s, j.price)),
            ("least_walking", lambda j: (j.walking_m, j.duration_s, j.price)),
            ("lowest_emissions", lambda j: (j.co2_g, j.duration_s, j.price)),
            ("best_value", lambda j: (-j.score, j.duration_s)),
        ]
        for name, key in rules:
            winner = best(key)
            if name not in winner.archetypes:
                winner.archetypes.append(name)

        step_free = [j for j in journeys if j.step_free and not j.is_walk_only]
        if step_free:
            winner = min(step_free, key=lambda j: (j.duration_s, j.price))
            winner.archetypes.append("accessible")
        return journeys
