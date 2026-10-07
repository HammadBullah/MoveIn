"""Turning engine objects into API payloads.

The engine's dataclasses are built for computation: stop ids, seconds after
midnight, pence.  The API is built for a user interface: stop names, clock
times, "£4.85", and an instruction for every step.  Everything the UI needs to
draw a journey without a second round trip is assembled here.
"""

from __future__ import annotations

import math

from datetime import datetime, timedelta

from ..domain.models import Mode, Stop
from ..engine.fares import FareBreakdown
from ..engine.graph import TransitGraph
from ..engine.journeys import Journey
from ..engine.search import OnDemandLeg, TransitLeg, WalkLeg
from ..ingest.registry import get_operator
from ..ingest.geo import bearing_deg, relative_direction


def clock(seconds: int) -> str:
    """Render seconds-after-midnight as ``HH:MM``, wrapping past midnight."""
    seconds = int(seconds) % 86400
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"


def money(pence_or_pounds: float, *, pence: bool = False) -> str:
    value = pence_or_pounds / 100.0 if pence else pence_or_pounds
    return f"£{value:,.2f}"


def _stop_payload(stop: Stop | None, stop_id: str, graph: TransitGraph) -> dict:
    if stop is None:
        stop = graph.stops.get(stop_id)
    if stop is None:
        return {"id": stop_id, "name": stop_id, "lat": None, "lon": None, "mode": ""}
    return {
        "id": stop.id,
        "name": stop.name,
        "lat": stop.lat,
        "lon": stop.lon,
        "mode": stop.mode.value,
        "region": stop.region,
        "interchange": bool(stop.interchange),
        "step_free": stop.wheelchair_boarding != 2,
    }


def _operator_payload(code: str) -> dict:
    operator = get_operator(code)
    if operator is None:
        return {"code": code, "name": code, "colour": "#4b5563", "mode": ""}
    return {
        "code": operator.code,
        "name": operator.name,
        "colour": operator.colour,
        "mode": operator.mode,
        "url": operator.url,
    }


def _endpoint_payload(place, stop_id: str, graph: TransitGraph) -> dict:
    """The traveller's own origin or destination, when it is not a stop.

    The first and last walks start and end at a *place* -- a town, a postcode,
    a pair of coordinates -- rather than at a bus stop, and the itinerary has to
    say so: "Walk 12 min to Birmingham" is what the traveller asked about.
    """
    if place is None:
        return _stop_payload(None, stop_id, graph)
    label = getattr(place, "label", None) or getattr(place, "name", None) or stop_id
    return {
        "id": getattr(place, "id", stop_id),
        "name": label,
        "label": label,
        "lat": getattr(place, "lat", None),
        "lon": getattr(place, "lon", None),
        "mode": "",
    }


def walk_leg_payload(
    leg: WalkLeg,
    graph: TransitGraph,
    *,
    start: datetime,
    from_place=None,
    to_place=None,
) -> dict:
    """A walking step, with a plain-English instruction."""
    from_stop = graph.stops.get(leg.from_stop_id)
    to_stop = graph.stops.get(leg.to_stop_id)
    minutes = max(1, round(leg.duration_s / 60))
    if leg.kind == "access":
        instruction = f"Walk {minutes} min to {to_stop.name if to_stop else 'the stop'}"
    elif leg.kind == "egress":
        destination = getattr(to_place, "label", None) or getattr(to_place, "name", None)
        instruction = (
            f"Walk {minutes} min to {destination}" if destination
            else f"Walk {minutes} min to your destination"
        )
    else:
        instruction = (
            f"Walk {minutes} min to {to_stop.name if to_stop else 'the next stop'}"
        )
    payload = {
        "kind": "walk",
        "mode": "walk",
        "mode_label": "Walk",
        "instruction": instruction,
        "distance_m": round(leg.distance_m),
        "duration_s": leg.duration_s,
        "from": (
            _endpoint_payload(from_place, leg.from_stop_id, graph)
            if from_place is not None
            else _stop_payload(from_stop, leg.from_stop_id, graph)
        ),
        "to": (
            _endpoint_payload(to_place, leg.to_stop_id, graph)
            if to_place is not None
            else _stop_payload(to_stop, leg.to_stop_id, graph)
        ),
        "start_time": start.strftime("%H:%M"),
        "end_time": (start + timedelta(seconds=leg.duration_s)).strftime("%H:%M"),
        "step_free": True,
        "direction": relative_direction(
            bearing_deg(leg.from_lat, leg.from_lon, leg.to_lat, leg.to_lon)
        ),
    }
    return payload


def transit_leg_payload(
    leg: TransitLeg, graph: TransitGraph, *, service_day: datetime
) -> dict:
    board = graph.stops.get(leg.board_stop_id)
    alight = graph.stops.get(leg.alight_stop_id)
    route = graph.routes.get(leg.route_id)
    operator = _operator_payload(leg.operator_code)
    depart = datetime.combine(service_day.date(), datetime.min.time()) + timedelta(
        seconds=leg.departure_s
    )
    arrive = datetime.combine(service_day.date(), datetime.min.time()) + timedelta(
        seconds=leg.arrival_s
    )
    stops_between = _intermediate_stops(leg, graph)
    return {
        "kind": "transit",
        "mode": leg.mode.value,
        "mode_label": leg.mode.label,
        "instruction": _transit_instruction(leg, graph, route),
        "route_id": leg.route_id,
        "route_name": (route.short_name if route else leg.route_id),
        "route_long_name": (route.long_name if route else ""),
        "headsign": leg.headsign,
        "trip_id": leg.trip_id,
        "operator": operator,
        "from": _stop_payload(board, leg.board_stop_id, graph),
        "to": _stop_payload(alight, leg.alight_stop_id, graph),
        "departure": depart.strftime("%H:%M"),
        "arrival": arrive.strftime("%H:%M"),
        "departure_s": leg.departure_s,
        "arrival_s": leg.arrival_s,
        "duration_s": leg.arrival_s - leg.departure_s,
        "distance_km": round(leg.distance_m / 1000.0, 1),
        # Stops the vehicle calls at on this leg, including boarding and
        # alighting: "12 stops" must mean twelve, not eleven and a bit.
        "stops_count": leg.alight_index - leg.board_index + 1,
        "intermediate_stops": stops_between,
        "fare": money(leg.fare_p, pence=True),
        "fare_amount": leg.fare_p / 100.0,
        "co2_g": round(leg.co2_g),
        "step_free": leg.accessible,
        "colour": (route.colour if route else "#4b5563"),
        "delay_s": leg.delay_s,
        "live": False,
    }


def _intermediate_stops(leg: TransitLeg, graph: TransitGraph, limit: int = 12) -> list[dict]:
    pattern = graph.patterns.get(leg.pattern_key)
    if pattern is None:
        return []
    names: list[dict] = []
    for position in range(leg.board_index + 1, leg.alight_index):
        stop = graph.stops.get(pattern.stops[position])
        if stop is None:
            continue
        names.append(
            {"id": stop.id, "name": stop.name, "lat": stop.lat, "lon": stop.lon}
        )
        if len(names) >= limit:
            break
    return names


def _transit_instruction(leg: TransitLeg, graph: TransitGraph, route) -> str:
    route_name = (route.short_name or route.long_name) if route else leg.route_id
    operator = get_operator(leg.operator_code)
    prefix = "Take the" if leg.mode in (Mode.RAIL, Mode.TRAM, Mode.METRO) else "Take"
    owner = f" {operator.name}" if operator else ""
    destination = leg.headsign or "the terminus"
    return f"{prefix}{owner} {leg.mode.label.lower()} {route_name} towards {destination}"


def on_demand_leg_payload(leg: OnDemandLeg, graph: TransitGraph) -> dict:
    operator = _operator_payload(leg.operator_code)
    minutes = max(1, round(leg.duration_s / 60))
    return {
        "kind": "on_demand",
        "mode": leg.mode.value,
        "mode_label": leg.mode.label,
        "instruction": (
            f"Book a {leg.mode.label.lower()} for the {minutes} min ride to "
            f"{_name_of(leg.to_lat, leg.to_lon, graph)}"
        ),
        "operator": operator,
        "from": {
            "id": "__origin__",
            "name": "Your location",
            "lat": leg.from_lat,
            "lon": leg.from_lon,
            "mode": "",
        },
        "to": {
            "id": "",
            "name": _name_of(leg.to_lat, leg.to_lon, graph),
            "lat": leg.to_lat,
            "lon": leg.to_lon,
            "mode": "",
        },
        "distance_km": round(leg.distance_m / 1000.0, 1),
        "duration_s": leg.duration_s,
        "fare": money(leg.fare_p, pence=True),
        "fare_amount": leg.fare_p / 100.0,
        "co2_g": round(leg.co2_g),
        "step_free": True,
        "colour": operator["colour"],
    }


def _name_of(lat: float, lon: float, graph: TransitGraph) -> str:
    stop, _distance = graph.nearest_stop(lat, lon)
    return stop.name if stop else "your destination"


def fare_payload(fare: FareBreakdown | None) -> dict:
    if fare is None:
        return {"total": 0.0, "tickets": [], "notes": [], "saving": 0.0}
    return {
        "total": round(fare.total, 2),
        "total_label": money(fare.total),
        "currency": fare.currency,
        "tickets": [
            {
                "operator": ticket.get("operator", ""),
                "operator_name": (
                    _operator_payload(ticket["operator"])["name"]
                    if ticket.get("operator")
                    else "All operators"
                ),
                "label": ticket.get("label", "Ticket"),
                "price": round(float(ticket.get("price", 0)), 2),
                "price_label": money(float(ticket.get("price", 0))),
                "covers_legs": ticket.get("covers", []),
                "saving": round(float(ticket.get("saving", 0)), 2),
            }
            for ticket in fare.tickets
        ],
        "leg_prices": [
            {
                "index": priced.index,
                "mode": priced.mode.value,
                "operator": priced.operator_code,
                "distance_km": round(priced.distance_km, 1),
                "base_price": round(priced.base_price, 2),
                "paid": round(priced.paid, 2),
                "product": priced.product,
                "product_label": priced.product_label,
                "covered_by": priced.covered_by,
            }
            for priced in fare.legs
        ],
        "saving_vs_singles": round(fare.saving_vs_singles, 2),
        "notes": list(fare.notes),
    }


def walk_minutes(distance_m: float) -> int:
    """Walking minutes for a distance, rounded up: part of a minute is a minute."""
    from ..ingest.geo import walk_duration_s

    seconds = walk_duration_s(distance_m)
    return max(1, math.ceil(seconds / 60)) if seconds else 0


def _walk_label(seconds: int) -> str:
    """A walk length the way a person would say it: "9 min walk".

    Rounded up, never to nearest: 616 seconds is "11 min walk", not "10 min
    walk", because a traveller who has said they will walk ten minutes has said
    something the journey has to be honest about.
    """
    if not seconds:
        return "no walking"
    return f"{max(1, math.ceil(seconds / 60))} min walk"


def journey_payload(
    journey: Journey,
    graph: TransitGraph,
    *,
    rank: int = 0,
    origin=None,
    destination=None,
) -> dict:
    service_day = journey.departure.replace(hour=0, minute=0, second=0, microsecond=0)
    midnight = datetime.combine(service_day.date(), datetime.min.time())
    # Only transit legs carry absolute times, so the itinerary is walked in
    # order to place the walks that sit between them.
    cursor = journey.departure
    legs: list[dict] = []
    for index, leg in enumerate(journey.legs):
        if isinstance(leg, TransitLeg):
            payload = transit_leg_payload(leg, graph, service_day=service_day)
            cursor = midnight + timedelta(seconds=leg.arrival_s)
        elif isinstance(leg, OnDemandLeg):
            payload = on_demand_leg_payload(leg, graph)
            cursor = cursor + timedelta(seconds=leg.duration_s)
        else:
            # An interchange walk should finish just as the next vehicle
            # leaves, so anchor it to the following departure when there is one.
            following = next(
                (l for l in journey.legs[index + 1:] if isinstance(l, TransitLeg)), None
            )
            if following is not None:
                leaves = midnight + timedelta(seconds=following.departure_s)
                start = max(cursor, leaves - timedelta(seconds=leg.duration_s))
            else:
                start = cursor
            payload = walk_leg_payload(
                leg,
                graph,
                start=start,
                from_place=origin if leg.kind == "access" else None,
                to_place=destination if leg.kind == "egress" else None,
            )
            cursor = start + timedelta(seconds=leg.duration_s)
        legs.append(payload)

    return {
        "id": journey.id,
        "rank": rank,
        "departure": journey.departure.isoformat(timespec="seconds"),
        "arrival": journey.arrival.isoformat(timespec="seconds"),
        "departure_time": journey.departure.strftime("%H:%M"),
        "arrival_time": journey.arrival.strftime("%H:%M"),
        "arrival_day_offset": (journey.arrival.date() - journey.departure.date()).days,
        "duration_s": journey.duration_s,
        "duration_label": journey.duration_label,
        "price": round(journey.price, 2),
        "price_label": money(journey.price),
        "changes": journey.changes,
        "changes_label": (
            "Direct" if journey.changes == 0 else f"{journey.changes} change"
            + ("s" if journey.changes > 1 else "")
        ),
        "walking_m": round(journey.walking_m),
        "walking_s": journey.walking_s,
        # Walking is shown as a decision, not a footnote: the longest single
        # walk is what makes a journey unreasonable, and the app groups by it.
        "longest_walk_s": journey.longest_walk_s,
        "longest_walk_label": _walk_label(journey.longest_walk_s),
        "walk_comfort": journey.walk_comfort,
        "walk_warning": journey.walk_comfort != "comfortable",
        "walking_label": (
            "No walking"
            if journey.walking_m < 50
            else f"{max(1, round(journey.walking_s / 60))} min walk"
        ),
        "co2_g": round(journey.co2_g),
        "co2_label": f"{journey.co2_g / 1000:.2f} kg CO₂e",
        "reliability": round(journey.reliability, 3),
        "reliability_label": f"{journey.reliability * 100:.0f}% on time",
        "step_free": journey.step_free,
        "modes": list(journey.modes),
        "mode_label": journey.route_label,
        "route_label": journey.route_label,
        "operators": [_operator_payload(code) for code in journey.operators],
        "transit_legs": journey.transit_legs,
        "is_walk_only": journey.is_walk_only,
        "archetypes": list(journey.archetypes),
        "archetype_labels": [_ARCHETYPE_LABELS.get(a, a) for a in journey.archetypes],
        "notes": list(journey.notes),
        "scores": journey.scores,
        "score": round(journey.score, 4),
        "legs": legs,
        "fare": fare_payload(journey.fare),
        "summary": (
            f"{journey.departure.strftime('%H:%M')} → "
            f"{journey.arrival.strftime('%H:%M')} · {journey.duration_label} · "
            f"{money(journey.price)} · "
            + ("direct" if journey.changes == 0 else f"{journey.changes} change"
               + ("s" if journey.changes > 1 else ""))
        ),
        "polyline": _polyline(legs),
    }


_ARCHETYPE_LABELS = {
    "cheapest": "Cheapest",
    "fastest": "Fastest",
    "best_value": "Best value",
    "fewest_changes": "Fewest changes",
    "least_walking": "Least walking",
    "lowest_emissions": "Lowest emissions",
    "accessible": "Step-free",
}


def _polyline(legs: list[dict]) -> list[list[float]]:
    """A [lat, lon] path through every point the journey touches.

    Transit legs contribute their intermediate stops as well as their ends, so
    the line follows the corridor rather than cutting across the map.
    """
    points: list[list[float]] = []

    def push(lat, lon) -> None:  # type: ignore[no-untyped-def]
        if lat is None or lon is None:
            return
        if not points or points[-1] != [lat, lon]:
            points.append([lat, lon])

    for leg in legs:
        for key in ("from", "to"):
            endpoint = leg.get(key) or {}
            push(endpoint.get("lat"), endpoint.get("lon"))
        for stop in leg.get("intermediate_stops") or []:
            push(stop.get("lat"), stop.get("lon"))
        # The final destination of a transit leg belongs at the end of it.
        if leg.get("kind") == "transit":
            endpoint = leg.get("to") or {}
            push(endpoint.get("lat"), endpoint.get("lon"))
    return points


def stop_payload(stop: Stop, *, graph: TransitGraph | None = None) -> dict:
    routes: list[dict] = []
    if graph is not None:
        seen: set[str] = set()
        for pattern_key, _position in graph.stop_routes.get(stop.id, ()):
            route_id = graph.patterns[pattern_key].route_id
            if route_id in seen:
                continue
            seen.add(route_id)
            route = graph.routes.get(route_id)
            routes.append(
                {
                    "id": route_id,
                    "short_name": route.short_name if route else route_id,
                    "long_name": route.long_name if route else "",
                    "mode": route.mode.value if route else "",
                    "colour": route.colour if route else "#4b5563",
                    "operator": _operator_payload(route.operator_code) if route else None,
                }
            )
        routes.sort(key=lambda r: (r["mode"], r["short_name"]))
    return {
        "id": stop.id,
        "name": stop.name,
        "lat": stop.lat,
        "lon": stop.lon,
        "mode": stop.mode.value,
        "mode_label": stop.mode.label,
        "region": stop.region,
        "interchange": bool(stop.interchange),
        "step_free": stop.wheelchair_boarding != 2,
        "atco_code": stop.atco_code or None,
        "crs_code": stop.crs_code or None,
        "source": stop.source,
        "routes": routes,
        "route_count": len(routes),
    }
