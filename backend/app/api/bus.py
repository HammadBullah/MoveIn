"""The real UK bus network, as its own API.

A separate router from `/api/network`, because it serves a different kind of
truth.  `/api/network` describes the timetable MoveIn plans with; `/api/bus`
describes the bus routes the operators themselves publish — route numbers,
operators, the stops each service calls at, and the shape it drives — with no
departure times at all, because a published route shape is not a timetable.

Split that way, the API can never accidentally present a modelled service as a
published one, or the other way round.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ..domain.real_bus import PLACE_RADIUS_M, get_real_bus_network
from .deps import PlannerDep

bus = APIRouter(prefix="/bus", tags=["bus routes"])

#: Drawing every route in one payload is a megabyte of JSON nobody asked for.
#: Callers filter by operator or by area; this is the backstop.
MAX_MAP_ROUTES = 400


def network_or_404():
    """The real bus network, or a 404 that says how to build it."""
    net = get_real_bus_network()
    if net is None or not net.routes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "the real bus network has not been imported; run "
                "scripts/fetch_real_bus_routes.py then scripts/import_real_bus_routes.py"
            ),
        )
    return net


def _route_summary(route) -> dict:
    return {
        "id": route.id,
        "service": route.service or route.id,
        "number": route.number,
        "operator": route.operator,
        "description": route.description,
        "stop_count": len(route.stops),
        "from": route.stops[0].name if route.stops else "",
        "to": route.stops[-1].name if route.stops else "",
        "source": route.source,
    }


@bus.get("/coverage", summary="What real bus data MoveIn holds")
def bus_coverage() -> dict:
    """The honest headline: how many real routes, from how many operators.

    Also says what this is *not*: there are no times in it.  A traveller who
    reads "514 real bus routes" must not conclude the app knows when they run.
    """
    net = network_or_404()
    stats = net.stats()
    return {
        **stats,
        "has_times": False,
        "note": (
            "Real published bus routes with their real stops and shapes, imported "
            "from operator TransXChange data via the DfT Bus Open Data Service. "
            "This layer carries no departure times: timetables in MoveIn are the "
            "separate compiled layer, and journey planning uses that."
        ),
        "coverage_note": (
            "This is a real, growing slice of the national bus network -- not all "
            "of it. It holds the services of the operators whose published route "
            "data is mirrored in a machine-readable form MoveIn can ingest, and "
            "only those whose stops fall inside MoveIn's NaPTAN stop register. "
            "The UK has around 1,700 bus operators; /api/network/coverage reports "
            "the modelled network alongside this."
        ),
    }


@bus.get("/operators", summary="Operators in the real bus network")
def bus_operators() -> dict:
    net = network_or_404()
    stats = net.stats()
    return {
        "count": stats["operators"],
        "operators": [
            {
                "name": name,
                "routes": routes,
                "services": stats["services_per_operator"].get(name, 0),
            }
            for name, routes in stats["routes_per_operator"].items()
        ],
        "attribution": net.attribution,
    }


@bus.get("/routes", summary="Browse real bus routes")
def bus_routes(
    operator: str | None = Query(default=None, description="Only this operator"),
    q: str | None = Query(default=None, description="Match route number, place or operator"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Route list, longest first is meaningless — so: operator, then number.

    Each entry names the two ends of the line, because "Route 148 · Leicester -
    Nuneaton - Coventry" is what tells a passenger whether it is their bus.
    """
    net = network_or_404()
    rows = list(net.routes.values())
    if operator:
        rows = [route for route in rows if route.operator.lower() == operator.lower()]
    if q:
        needle = q.strip().lower()
        rows = [
            route
            for route in rows
            if needle in route.number.lower()
            or needle in route.operator.lower()
            or needle in route.description.lower()
            or any(needle in stop.name.lower() for stop in route.stops)
        ]
    rows.sort(key=lambda route: (route.operator, route.number, route.id))
    window = rows[offset : offset + limit]
    return {
        "count": len(rows),
        "offset": offset,
        "limit": limit,
        "routes": [_route_summary(route) for route in window],
        "has_times": False,
        "attribution": net.attribution,
    }


@bus.get("/routes/{route_id}", summary="One real bus route, stop by stop")
def bus_route(route_id: str, precision: int = Query(default=5, ge=3, le=6)) -> dict:
    net = network_or_404()
    route = net.routes.get(route_id)
    if route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such route")
    payload = route.payload(precision=precision, shape=True)
    payload["has_times"] = False
    payload["attribution"] = net.attribution
    return payload


@bus.get("/map", summary="Real bus routes as drawable lines")
def bus_map(
    operator: str | None = Query(default=None),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    radius_m: float = Query(default=25_000, ge=500, le=200_000),
    limit: int = Query(default=MAX_MAP_ROUTES, ge=1, le=MAX_MAP_ROUTES),
    precision: int = Query(default=5, ge=3, le=6),
    simplify_m: float = Query(
        default=0,
        ge=0,
        le=500,
        description="Trim the shapes to this tolerance before sending them",
    ),
) -> dict:
    """The polyline shapes and stop positions for the map overlay.

    Filter by `operator`, or by a point and radius, or neither to ask for the
    country — in which case `truncated` will say the answer was capped.
    """
    net = network_or_404()
    near = (lat, lon) if lat is not None and lon is not None else None
    total = len(net.routes) if not (operator or near) else None
    features = net.features(
        operator=operator,
        near=near,
        radius_m=radius_m,
        limit=limit,
        precision=precision,
        simplify_m=simplify_m,
    )
    if total is None:
        # Cheap enough: count what the filters would have produced unrestricted.
        total = len(
            net.features(
                operator=operator, near=near, radius_m=radius_m, precision=3, simplify_m=200
            )
        )
    return {
        "count": len(features),
        "total_matching": total,
        "truncated": len(features) < total,
        "features": features,
        "mode": "bus",
        "has_times": False,
        "attribution": net.attribution,
    }


@bus.get("/between", summary="Real bus services between two places")
def bus_between(
    planner: PlannerDep,
    origin: str = Query(description="Place name, stop name, or lat,lon"),
    destination: str = Query(description="Place name, stop name, or lat,lon"),
    radius_m: float = Query(default=PLACE_RADIUS_M, ge=200, le=25_000),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Which *published* bus services link two places, and where to board them.

    This is the question the compiled timetable cannot answer: MoveIn models
    corridors between the cities it covers, while this returns the real service
    numbers a passenger would look for on the roadside — every one of them
    traceable to an operator's own published route data.
    """
    net = network_or_404()
    start = planner.resolve_place(origin)
    end = planner.resolve_place(destination)
    if start is None:
        raise HTTPException(status_code=404, detail=f"could not resolve origin: {origin!r}")
    if end is None:
        raise HTTPException(status_code=404, detail=f"could not resolve destination: {destination!r}")

    found = net.routes_between((start.lat, start.lon), (end.lat, end.lon), radius_m=radius_m)
    options = []
    for item in found[:limit]:
        route = item["route"]
        options.append(
            {
                "route_id": route.id,
                "service": route.service or route.id,
                "number": route.number,
                "operator": route.operator,
                "description": route.description,
                "direction": item["direction"],
                "board": item["board"].payload(),
                "alight": item["alight"].payload(),
                "stops_travelled": item["stops_travelled"],
                "stops_before": item["stops_before"],
                "stops_after": item["stops_after"],
                "straight_m": round(item["straight_m"]),
                "calls_at": item["stops_travelled_names"],
            }
        )
    return {
        "origin": {"id": start.id, "label": start.label, "lat": start.lat, "lon": start.lon},
        "destination": {"id": end.id, "label": end.label, "lat": end.lat, "lon": end.lon},
        "radius_m": radius_m,
        "count": len(found),
        "options": options,
        "has_times": False,
        "note": (
            "Direction is respected where the operators publish it; an option "
            "marked reverse is the same service published the other way round."
        ),
        "attribution": net.attribution,
    }
