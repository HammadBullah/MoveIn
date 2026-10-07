"""Every HTTP endpoint MoveIn serves.

The route set follows the product's four questions -- where can I go from here,
what are my options, what will it cost, and is it running -- plus the small
amount of state a Phase 1 user gets: saved journeys, price alerts and a journey
they are currently on.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from ..db import repository as repo
from ..db.models import (
    DataSourceRow,
    JourneySearchRow,
    PriceAlertRow,
    SavedJourneyRow,
    ServiceAlertRow,
    TrackedJourneyRow,
    VehiclePositionRow,
)
from ..domain.models import CO2_G_PER_PKM, Mode, to_uk_naive, uk_now
from ..domain.real_bus import get_real_bus_network
from ..domain.regions import REGIONS, region_for_point
from ..engine.fares import TravellerProfile
from ..engine.journeys import Preference
from ..ingest.registry import ALL_OPERATORS, get_operator
from ..schemas.requests import (
    JourneySearchRequest,
    PriceAlertRequest,
    SaveJourneyRequest,
    TrackJourneyRequest,
)
from ..services import realtime
from .deps import DbDep, DeviceDep, OptionalDeviceDep, PlannerDep, resolve_device
from .serializers import clock, journey_payload, money, stop_payload

meta = APIRouter(tags=["meta"])
stops = APIRouter(prefix="/stops", tags=["stops"])
journeys = APIRouter(prefix="/journeys", tags=["journeys"])
network = APIRouter(prefix="/network", tags=["network"])
fares = APIRouter(prefix="/fares", tags=["fares"])
live = APIRouter(prefix="/live", tags=["live"])
user = APIRouter(prefix="/me", tags=["saved journeys and alerts"])


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


@meta.get("/health", summary="Liveness and readiness")
def health(planner: PlannerDep, db: DbDep) -> dict:
    counts = repo.count_rows(db)
    return {
        "status": "ok" if counts["stops"] else "degraded",
        "version": planner.settings.version,
        "network": planner.graph.stats(),
        "database": counts,
    }


@meta.get("/preferences", summary="The preferences a traveller can choose")
def preferences() -> dict:
    """Describe every optimisation target, with the weights behind it.

    The UI renders this list directly, so adding a preference is a backend
    change alone.
    """
    descriptions = {
        Preference.CHEAPEST: "Lowest total fare, whatever it costs you in time.",
        Preference.FASTEST: "Shortest door-to-door journey time.",
        Preference.BEST_VALUE: "The best balance of price, time, changes and walking.",
        Preference.FEWEST_CHANGES: "Stay on the same vehicle as long as possible.",
        Preference.LEAST_WALKING: "Minimise walking, including to and from stops.",
        Preference.LOWEST_EMISSIONS: "Lowest carbon dioxide per passenger.",
        Preference.ACCESSIBLE: "Step-free throughout, with no stairs or steps.",
        Preference.BALANCED: "An even weighting across every criterion.",
    }
    icons = {
        Preference.CHEAPEST: "pound",
        Preference.FASTEST: "clock",
        Preference.BEST_VALUE: "star",
        Preference.FEWEST_CHANGES: "shuffle",
        Preference.LEAST_WALKING: "walk",
        Preference.LOWEST_EMISSIONS: "leaf",
        Preference.ACCESSIBLE: "accessible",
        Preference.BALANCED: "scales",
    }
    return {
        "default": Preference.BEST_VALUE.value,
        "preferences": [
            {
                "id": p.value,
                "label": p.label,
                "description": descriptions[p],
                "icon": icons[p],
                "weights": p.weights,
            }
            for p in Preference
        ],
    }


@meta.get("/data-sources", summary="What data is real and what is compiled")
def data_sources(db: DbDep, planner: PlannerDep) -> dict:
    """The honest provenance of everything the planner is running on.

    The geography, the stops and the operators are real published datasets.  The
    timetable layer is compiled from them.  This endpoint exists so the UI can
    say so on screen rather than burying it in a README.
    """
    from ..ingest.real_sources import LIVE_FEEDS

    STATUS_NOT_REACHABLE = (
        "adapter implemented and unit-tested; the host is not reachable from "
        "this deployment, so the compiled layer is in use"
    )

    rows = list(
        db.execute(select(DataSourceRow).order_by(DataSourceRow.kind, DataSourceRow.key)).scalars()
    )
    sources = [
            {
                "key": row.key,
                "name": row.name,
                "url": row.url,
                "licence": row.licence,
                "kind": row.kind,
                "rows": row.rows,
                "detail": row.detail,
            }
            for row in rows
    ]

    # The real bus network is not in the database -- it is a compiled file the
    # API loads directly -- so it is added here rather than being invisible on
    # the screen that exists to make provenance visible.
    real_bus = get_real_bus_network()
    if real_bus is not None and real_bus.routes:
        stats = real_bus.stats()
        sources.insert(
            0,
            {
                "key": "real-bus-routes",
                "name": "Operator bus routes (real, published)",
                "url": "https://data.bus-data.dft.gov.uk/",
                "licence": "Open Government Licence v3.0 (DfT Bus Open Data Service)",
                "kind": "real",
                "rows": stats["routes"],
                "detail": (
                    f"{stats['routes']} real route variations of {stats['services']} "
                    f"services from {stats['operators']} operators, "
                    f"{stats['named_stops']:,} named stops. No departure times: "
                    "route shapes, not timetables."
                ),
            },
        )

    return {
        "headline": (
            "Real GB stop, station and operator data, including the bus routes "
            "operators publish. The timetable layer is compiled from it, not "
            "downloaded — live national feeds are not reachable from this "
            "deployment."
        ),
        "sources": sources,
        "live_feeds": [
            {
                "key": key,
                "name": feed.get("name") or key,
                "provides": feed.get("provides", ""),
                "publisher": feed.get("publisher"),
                "licence": feed.get("licence"),
                "adapter": feed.get("adapter"),
                "format": feed.get("format"),
                "auth": feed.get("auth"),
                "status": feed.get("status", STATUS_NOT_REACHABLE),
            }
            for key, feed in LIVE_FEEDS.items()
        ],
        "network": planner.graph.stats(),
        "service_window": {
            "start": planner.net.feed_info.start_date.isoformat()
            if planner.net.feed_info.start_date
            else None,
            "end": planner.net.feed_info.end_date.isoformat()
            if planner.net.feed_info.end_date
            else None,
        },
    }


@network.get("/map", summary="Every route, as the line it actually runs")
def network_map(
    planner: PlannerDep,
    mode: str | None = Query(default=None, description="Only lines of this mode"),
    region: str | None = Query(default=None, description="Only lines touching this region"),
    precision: int = Query(default=5, ge=3, le=6, description="Decimal places for coordinates"),
) -> dict:
    """The whole modelled network as drawable polylines.

    One line per route, each a list of the stops it calls at in order, at their
    real coordinates -- so the map draws the service, not a straight line between
    its ends.  Coordinates are rounded, because five decimal places is a metre
    and nobody can see a metre on a phone.
    """
    features: list[dict] = []
    for route_id in sorted(planner.graph.routes):
        route = planner.graph.routes[route_id]
        if mode and route.mode.value != mode:
            continue
        # A route's stops are the union of its patterns; the longest pattern is
        # the one that shows where the line goes.
        patterns = [p for p in planner.graph.patterns.values() if p.route_id == route_id]
        if not patterns:
            continue
        longest = max(patterns, key=lambda p: len(p.stops))
        coordinates: list[list[float]] = []
        regions: set[str] = set()
        for stop_id in longest.stops:
            stop = planner.graph.stops.get(stop_id)
            if stop is None:
                continue
            coordinates.append([round(stop.lat, precision), round(stop.lon, precision)])
            if stop.region:
                regions.add(stop.region)
        if len(coordinates) < 2:
            continue
        if region and region not in regions:
            continue
        operator = get_operator(route.operator_code)
        features.append(
            {
                "id": route.id,
                "name": route.short_name or route.long_name or route.id,
                "long_name": route.long_name,
                "mode": route.mode.value,
                "mode_label": route.mode.label,
                "colour": f"#{route.colour.lstrip('#')}" if route.colour else "#4b5563",
                "operator": operator.name if operator else route.operator_code,
                "coordinates": coordinates,
                "stops": len(coordinates),
            }
        )
    return {
        "count": len(features),
        "features": features,
        "attribution": "MoveIn modelled network: real NaPTAN stops and real operators, compiled timetable.",
    }


@network.get("/coverage", summary="How much of the real network is modelled")
def network_coverage(planner: PlannerDep) -> dict:
    """What MoveIn models against what the country actually has.

    The single most important honesty figure in the product. MoveIn holds the
    real NaPTAN register for its regions -- tens of thousands of stops -- and
    compiles a few hundred of them into corridors. Every city therefore has a
    coverage figure well under 100%, and the app says so rather than letting a
    traveller assume the other 99% is there.
    """
    import json

    from ..config import get_settings

    manifest_path = get_settings().data_raw_dir / "SOURCES.json"
    real_by_region: dict[str, int] = {}
    named_total = 0
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        real_by_region = manifest.get("naptan", {}).get("by_region", {})
        named_total = manifest.get("named_stops", 0)

    net = planner.net
    modelled: dict[str, int] = {}
    routes: dict[str, set[str]] = {}
    operators: dict[str, set[str]] = {}
    for stop in net.stops.values():
        key = stop.region or ""
        modelled[key] = modelled.get(key, 0) + 1
    for trip in net.trips.values():
        route = net.routes.get(trip.route_id)
        if route is None:
            continue
        seen: set[str] = set()
        for stop_time in net.stop_times[trip.id]:
            stop = net.stops.get(stop_time.stop_id)
            if stop and stop.region:
                seen.add(stop.region)
        for region in seen:
            routes.setdefault(region, set()).add(route.id)
            operators.setdefault(region, set()).add(route.operator_code)

    rows = []
    for region in REGIONS:
        slug = region.slug
        real = real_by_region.get(slug, 0)
        on_network = modelled.get(slug, 0)
        rows.append(
            {
                "region": slug,
                "name": region.name,
                "real_stops_held": real,
                "modelled_stops": on_network,
                "coverage_pct": round(100 * on_network / real, 2) if real else None,
                "routes": len(routes.get(slug, ())),
                "operators": len(operators.get(slug, ())),
            }
        )
    rows.sort(key=lambda row: (-(row["real_stops_held"] or 0), row["name"]))

    return {
        "headline": (
            "MoveIn plans on a modelled network built from real stops, not on "
            "the whole national one: city bus timetables are not downloadable "
            "from this deployment, so a handful of corridors per city stand in "
            "for the hundreds of real services."
        ),
        "named_stops_held": named_total,
        "named_stops_searchable": planner.named_stop_count,
        "modelled_stops": len(net.stops),
        "modelled_routes": len(net.routes),
        "regions": rows,
        "note": (
            "Every stop is real and at its real coordinates, and every service "
            "is run by the real operator, but only the modelled stops are served "
            "through. Stops off the network can still be typed in as a start or "
            "finish: MoveIn walks you to the nearest modelled stop, and says so."
        ),
    }


# ---------------------------------------------------------------------------
# Stops and places
# ---------------------------------------------------------------------------


@stops.get("/search", summary="Search stops, stations and towns")
def search_stops(
    planner: PlannerDep,
    q: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=12, ge=1, le=40),
) -> dict:
    results = planner.search_stops(q, limit=limit)
    return {"query": q, "count": len(results), "results": results}


@stops.get("/regions", summary="The cities and towns MoveIn models")
def list_regions() -> dict:
    return {
        "count": len(REGIONS),
        "regions": [
            {
                "slug": r.slug,
                "name": r.name,
                "lat": r.lat,
                "lon": r.lon,
                "radius_m": r.radius_m,
            }
            for r in sorted(REGIONS, key=lambda r: r.name)
        ],
    }


@stops.get("/nearby", summary="Stops near a coordinate")
def nearby(
    planner: PlannerDep,
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    radius_m: int = Query(default=800, ge=50, le=5000),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    found = planner.graph.stops_near(lat, lon, radius_m, limit=limit)
    region = region_for_point(lat, lon)
    return {
        "origin": {"lat": lat, "lon": lon},
        "region": region.slug if region else None,
        "count": len(found),
        "stops": [
            {**stop_payload(stop, graph=planner.graph), "distance_m": round(distance)}
            for stop, distance in found
        ],
    }


@stops.get("/{stop_id:path}", summary="One stop, with the routes that serve it")
def get_stop(planner: PlannerDep, stop_id: str) -> dict:
    stop = planner.graph.stops.get(stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"unknown stop {stop_id!r}")
    return stop_payload(stop, graph=planner.graph)


# ---------------------------------------------------------------------------
# Journey planning
# ---------------------------------------------------------------------------


def _traveller(payload) -> TravellerProfile:  # type: ignore[no-untyped-def]
    return TravellerProfile(
        adults=payload.adults,
        children=payload.children,
        railcard=payload.railcard,
        student=payload.student,
        step_free=payload.step_free,
        max_walk_m=payload.max_walk_m,
    )


@journeys.post("/search", summary="Plan a journey")
def search_journeys(
    planner: PlannerDep,
    db: DbDep,
    device: OptionalDeviceDep,
    request: JourneySearchRequest,
) -> dict:
    """The product's core call: From / To / When / Preference in, journeys out."""
    departure = request.departure or uk_now().replace(second=0, microsecond=0)
    origin = planner.resolve_place(request.origin)
    destination = planner.resolve_place(request.destination)
    if origin is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"could not find {request.origin!r}. Try a town name such as "
            "'Nottingham', a station such as 'Nottingham Station', or 'lat,lon'.",
        )
    if destination is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"could not find {request.destination!r}. Try a town name such as "
            "'Birmingham', a station such as 'Birmingham New Street', or 'lat,lon'.",
        )

    options = request.options
    wanted_modes = {m.strip().lower() for m in (options.modes or []) if m.strip()}

    def plan(max_walk_s: int | None):
        return planner.plan(
            origin=origin,
            destination=destination,
            departure=departure,
            preference=request.preference,
            traveller=_traveller(request.traveller),
            max_legs=options.max_legs,
            step_free_only=options.step_free_only or request.traveller.step_free,
            include_walking_only=options.include_walking_only,
            departure_sweep=options.departure_sweep,
            allow_on_demand=options.allow_on_demand,
            limit=request.limit,
            max_walk_s=max_walk_s,
            allowed_modes=wanted_modes or None,
            max_price=options.max_price,
            latest_arrival=request.arrive_by,
        )

    walk_limit_s = request.max_walk_minutes * 60 if request.max_walk_minutes else None
    result = plan(walk_limit_s)
    walk_notice = None
    if walk_limit_s is not None and not result.journeys:
        # "Nothing within a 10 minute walk" is an answer, but a useless one on
        # its own.  If the traveller's limit is what emptied the screen, show
        # them what it would cost to relax it, labelled as exactly that.
        relaxed = plan(None)
        if relaxed.journeys:
            result = relaxed
            result.diagnostics["walk_limit_relaxed"] = request.max_walk_minutes
            shortest = min(
                j.longest_walk_s for j in result.journeys
            )
            walk_notice = {
                "kind": "walk_limit_relaxed",
                "requested_walk_minutes": request.max_walk_minutes,
                "shortest_walk_minutes": max(1, round(shortest / 60)),
                "message": (
                    f"Nothing connects {origin.label} and {destination.label} "
                    f"within a {request.max_walk_minutes} minute walk. These are "
                    f"the options if you can walk up to "
                    f"{max(1, round(shortest / 60))} minutes."
                ),
            }

    if not result.journeys and wanted_modes:
        result.diagnostics["modes_filtered"] = sorted(wanted_modes)
        walk_notice = {
            "kind": "modes",
            "modes": sorted(wanted_modes),
            "message": (
                "Nothing connects these places using only "
                + ", ".join(sorted(wanted_modes))
                + ". Try allowing another mode."
            ),
        }

    if not result.journeys and options.max_price is not None:
        dropped = int(result.diagnostics.get("over_budget") or 0)
        result.diagnostics["max_price"] = options.max_price
        walk_notice = {
            "kind": "max_price",
            "max_price": options.max_price,
            "dropped": dropped,
            "message": (
                f"Nothing gets there for £{options.max_price:.2f} or less"
                + (f" — {dropped} journeys missed the budget." if dropped else ".")
            ),
        }

    if not result.journeys and request.arrive_by is not None:
        dropped = int(result.diagnostics.get("late_arrivals") or 0)
        result.diagnostics["arrive_by"] = request.arrive_by.isoformat()
        walk_notice = {
            "kind": "arrive_by",
            "arrive_by": request.arrive_by.isoformat(),
            "dropped": dropped,
            "message": (
                f"Nothing arrives by {to_uk_naive(request.arrive_by).strftime('%H:%M')}"
                + (f" — the {dropped} journeys found all got in later." if dropped else ".")
            ),
        }

    if not result.journeys:
        # A stop MoveIn holds but does not serve: say which end is off the
        # network and how far the nearest modelled stop is, rather than leaving
        # an empty screen that reads like "no such place".
        for end, place in (("origin", origin), ("destination", destination)):
            if end not in (result.diagnostics.get("off_network") or []):
                continue
            nearest = place.nearest_served or {}
            walk_notice = {
                "kind": "off_network",
                "end": end,
                "label": place.label,
                "nearest_served": nearest,
                "message": (
                    f"{place.label} is a real stop, but no MoveIn route reaches it. "
                    + (
                        f"The nearest modelled stop is {nearest['name']}, "
                        + (
                            f"{nearest['walk_minutes']} minutes' walk away."
                            if nearest.get("reachable")
                            else "further away than anybody would walk."
                        )
                        if nearest.get("name")
                        else "No modelled stop is within walking distance."
                    )
                    + " Try a town centre, or raise the walk limit."
                ),
            }
            break
            break
    if False:
        # "Nothing within a 10 minute walk" is an answer, but a useless one on
        # its own.  If the traveller's limit is what emptied the screen, show
        # them what it would cost to relax it, labelled as exactly that.
        relaxed = plan(None)
        if relaxed.journeys:
            result = relaxed
            result.diagnostics["walk_limit_relaxed"] = request.max_walk_minutes
            shortest = min(
                j.longest_walk_s for j in result.journeys
            )
            walk_notice = {
                "kind": "walk_limit_relaxed",
                "requested_walk_minutes": request.max_walk_minutes,
                "shortest_walk_minutes": max(1, round(shortest / 60)),
                "message": (
                    f"Nothing connects {origin.label} and {destination.label} "
                    f"within a {request.max_walk_minutes} minute walk. These are "
                    f"the options if you can walk up to "
                    f"{max(1, round(shortest / 60))} minutes."
                ),
            }

    payloads = [
        journey_payload(
            journey, planner.graph, rank=index + 1, origin=origin, destination=destination
        )
        for index, journey in enumerate(result.journeys)
    ]
    archetypes = {
        label: payload["id"]
        for payload in payloads
        for label in payload["archetypes"]
    }

    # The search history belongs to the client that asked, and the client may
    # identify itself either way round; a missing key just means no history.
    device = (device or (request.device_key or "").strip()) or None
    db.add(
        JourneySearchRow(
            device_key=device or "",
            origin_label=origin.label,
            destination_label=destination.label,
            preference=request.preference.value,
            departure_at=departure,
            results=len(payloads),
            best_price=payloads[0]["price"] if payloads else None,
            fastest_duration_s=min(
                (p["duration_s"] for p in payloads), default=None
            ),
            search_ms=result.diagnostics.get("search_ms"),
        )
    )
    db.commit()

    return {
        "origin": _place_payload(origin),
        "destination": _place_payload(destination),
        "departure": departure.isoformat(timespec="seconds"),
        "preference": request.preference.value,
        "preference_label": request.preference.label,
        "traveller": request.traveller.model_dump(),
        "count": len(payloads),
        "journeys": payloads,
        "archetypes": archetypes,
        "typical": _typical_summary(payloads),
        "nearby_destinations": result.alternatives,
        "notice": walk_notice,
        "diagnostics": result.diagnostics,
    }


def _place_payload(place) -> dict:  # type: ignore[no-untyped-def]
    alternatives = getattr(place, "alternatives", None) or []
    return {
        "id": place.id,
        "label": place.label,
        "lat": round(place.lat, 6),
        "lon": round(place.lon, 6),
        "kind": place.kind,
        "mode": getattr(place, "mode", ""),
        "region": getattr(place, "region", ""),
        "alternatives": alternatives,
        # A real stop that no modelled corridor calls at: usable as an origin,
        # but the answer must not imply the network reaches it.
        "served": getattr(place, "served", True),
        "nearest_served": getattr(place, "nearest_served", {}),
    }


def _typical_summary(payloads: list[dict]) -> dict:
    """A one-line "what to expect" for the top of the results screen."""
    if not payloads:
        return {}
    cheapest = min(payloads, key=lambda p: p["price"])
    fastest = min(payloads, key=lambda p: p["duration_s"])
    greenest = min(payloads, key=lambda p: p["co2_g"])
    return {
        "cheapest": {"id": cheapest["id"], "price": cheapest["price"],
                     "price_label": cheapest["price_label"]},
        "fastest": {"id": fastest["id"], "duration_s": fastest["duration_s"],
                    "duration_label": fastest["duration_label"]},
        "lowest_emissions": {"id": greenest["id"], "co2_g": greenest["co2_g"],
                             "co2_label": greenest["co2_label"]},
    }


@journeys.post("/compare-emissions", summary="Compare modes on one trip")
def compare_emissions(planner: PlannerDep, request: JourneySearchRequest) -> dict:
    """How each mode that connects two places compares on carbon."""
    origin = planner.resolve_place(request.origin)
    destination = planner.resolve_place(request.destination)
    if origin is None or destination is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown place")

    from ..ingest.geo import haversine_m

    distance_km = haversine_m(origin.lat, origin.lon, destination.lat, destination.lon) / 1000
    rows = []
    for mode in (Mode.RAIL, Mode.COACH, Mode.BUS, Mode.TRAM, Mode.METRO, Mode.TAXI):
        factor = CO2_G_PER_PKM.get(mode, 0.0)
        if factor <= 0:
            continue
        rows.append(
            {
                "mode": mode.value,
                "mode_label": mode.label,
                "g_per_km": factor,
                "co2_g": round(factor * distance_km),
                "co2_label": f"{factor * distance_km / 1000:.2f} kg CO₂e",
            }
        )
    rows.sort(key=lambda r: r["co2_g"])
    walking = {
        "mode": "walk",
        "mode_label": "Walk",
        "g_per_km": 0.0,
        "co2_g": 0,
        "co2_label": "0.00 kg CO₂e",
    }
    return {
        "distance_km": round(distance_km, 1),
        "origin": _place_payload(origin),
        "destination": _place_payload(destination),
        "modes": [walking, *rows],
        "greenest": rows[0]["mode"] if rows else "walk",
        "note": "Figures use UK Government (DESNZ) average-occupancy factors.",
    }


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


@network.get("/summary", summary="What the loaded network contains")
def network_summary(planner: PlannerDep) -> dict:
    stats = planner.graph.stats()
    modes: dict[str, int] = {}
    regions: dict[str, int] = {}
    for route in planner.graph.routes.values():
        modes[route.mode.value] = modes.get(route.mode.value, 0) + 1
    for stop in planner.graph.stops.values():
        if stop.region:
            regions[stop.region] = regions.get(stop.region, 0) + 1
    return {
        **stats,
        "routes": len(planner.graph.routes),
        "routes_by_mode": dict(sorted(modes.items(), key=lambda kv: -kv[1])),
        "stops_by_region": dict(sorted(regions.items(), key=lambda kv: -kv[1])),
        "operators": len(
            {r.operator_code for r in planner.graph.routes.values() if r.operator_code}
        ),
        "service_window": {
            "start": planner.net.feed_info.start_date.isoformat()
            if planner.net.feed_info.start_date
            else None,
            "end": planner.net.feed_info.end_date.isoformat()
            if planner.net.feed_info.end_date
            else None,
        },
    }


@network.get("/operators", summary="Every operator in the network")
def network_operators(planner: PlannerDep) -> dict:
    codes = sorted({r.operator_code for r in planner.graph.routes.values() if r.operator_code})
    out = []
    for code in codes:
        operator = get_operator(code)
        routes = [r for r in planner.graph.routes.values() if r.operator_code == code]
        modes = sorted({r.mode.value for r in routes})
        out.append(
            {
                "code": code,
                "name": operator.name if operator else code,
                "modes": modes,
                "colour": operator.colour if operator else "#4b5563",
                "website": operator.url if operator else None,
                "source": getattr(operator, "scheme", None),
                "routes": len(routes),
                "affiliate": bool(getattr(operator, "affiliate", False)),
            }
        )
    return {"count": len(out), "operators": out}


@network.get("/routes", summary="Routes, optionally filtered by mode or region")
def network_routes(
    planner: PlannerDep,
    mode: str | None = Query(default=None),
    region: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    out = []
    for route in sorted(planner.graph.routes.values(), key=lambda r: (r.mode.value, r.id)):
        if mode and route.mode.value != mode:
            continue
        operator = get_operator(route.operator_code)
        out.append(
            {
                "id": route.id,
                "short_name": route.short_name,
                "long_name": route.long_name,
                "mode": route.mode.value,
                "mode_label": route.mode.label,
                "colour": route.colour,
                "brand": route.brand,
                "operator": {
                    "code": route.operator_code,
                    "name": operator.name if operator else route.operator_code,
                },
                "source": getattr(operator, "scheme", None),
            }
        )
        if len(out) >= limit:
            break
    return {"count": len(out), "routes": out}


# ---------------------------------------------------------------------------
# Fares
# ---------------------------------------------------------------------------


@fares.get("/products", summary="Every ticket product in the fare table")
def fare_products(planner: PlannerDep) -> dict:
    products: dict[str, list[dict]] = {}
    for fare in sorted(planner.net.fares.values(), key=lambda f: (f.product_type, f.fare_id)):
        products.setdefault(fare.product_type, []).append(
            {
                "id": fare.fare_id,
                "label": fare.label or fare.fare_id,
                "price": fare.price,
                "price_label": money(fare.price),
                "operator_code": fare.operator_code,
                "operator_name": (
                    get_operator(fare.operator_code).name
                    if get_operator(fare.operator_code)
                    else fare.operator_code
                ),
                "offpeak_only": fare.offpeak_only,
                "advance_only": fare.advance_only,
                "railcard_eligible": fare.railcard_eligible,
                "student_eligible": fare.student_eligible,
                "transfers": fare.transfers,
                "transfer_duration_s": fare.transfer_duration_s,
            }
        )
    return {
        "count": len(planner.net.fares),
        "products": products,
        "note": (
            "Fares follow the real published structures of each mode: a flat "
            "urban bus fare, TfL tube pricing, tapered rail fares with off-peak "
            "and advance products, and per-operator coach pricing."
        ),
    }


@fares.get("/operators", summary="Operators MoveIn knows how to price")
def fare_operators() -> dict:
    return {
        "count": len(ALL_OPERATORS),
        "operators": [
            {
                "code": op.code,
                "name": op.name,
                "mode": op.mode,
                "scheme": getattr(op, "scheme", None),
                "colour": op.colour,
                "reliability": getattr(op, "reliability", None),
                "step_free": getattr(op, "step_free", None),
                "affiliate": getattr(op, "affiliate", False),
            }
            for op in sorted(ALL_OPERATORS, key=lambda o: (o.mode, o.name))
        ],
    }


# ---------------------------------------------------------------------------
# Live
# ---------------------------------------------------------------------------


@live.get("/vehicles", summary="Where the vehicles are right now")
def live_vehicles(
    planner: PlannerDep,
    db: DbDep,
    route_id: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
) -> dict:
    now = uk_now()
    services = planner.graph.services_on(now.date())
    vehicles = realtime.simulate_positions(
        planner.graph, at=now, services=services, limit=limit
    )
    if route_id:
        vehicles = [v for v in vehicles if v.route_id == route_id]
    realtime.store_positions(db, vehicles)
    db.commit()
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "source": "simulated from the compiled timetable",
        "note": (
            "Positioned from each trip's real schedule. Point the SIRI-VM "
            "adapter at a BODS feed to replace this with live reports."
        ),
        "count": len(vehicles),
        "vehicles": [v.as_dict() for v in vehicles],
    }


@live.get("/alerts", summary="Disruptions")
def live_alerts(
    planner: PlannerDep,
    db: DbDep,
    region: str | None = Query(default=None),
) -> dict:
    realtime.seed_alerts(db, planner.net)
    db.commit()
    rows = repo.active_alerts(db, region=region)
    return {
        "count": len(rows),
        "source": "sample disruptions (live feeds unreachable from this sandbox)",
        "alerts": [
            {
                "id": row.id,
                "header": row.header,
                "description": row.description,
                "severity": row.severity,
                "mode": row.mode,
                "route_ids": row.route_ids or [],
                "stop_ids": row.stop_ids or [],
                "regions": row.regions or [],
                "starts_at": row.starts_at,
                "ends_at": row.ends_at,
                "source": row.source,
            }
            for row in rows
        ],
    }


@live.post("/track", summary="Track the journey you are on")
def track_journey(
    planner: PlannerDep,
    db: DbDep,
    device: OptionalDeviceDep,
    request: TrackJourneyRequest,
) -> dict:
    device = resolve_device(device, request.device_key)
    now = uk_now()
    vehicles = realtime.simulate_positions(planner.graph, at=now)
    legs = request.payload.get("legs", [])
    transit_legs = [leg for leg in legs if leg.get("kind") == "transit"]

    updates = []
    for leg in transit_legs:
        delay = realtime.delay_for_trip(vehicles, leg.get("trip_id", ""))
        updates.append(
            {
                "trip_id": leg.get("trip_id"),
                "route_name": leg.get("route_name"),
                "scheduled_departure": leg.get("departure"),
                "expected_departure": clock(
                    realtime.adjust_time(leg.get("departure_s", 0), delay)
                ),
                "scheduled_arrival": leg.get("arrival"),
                "expected_arrival": clock(
                    realtime.adjust_time(leg.get("arrival_s", 0), delay)
                ),
                "delay_s": delay,
                "delay_label": realtime._delay_label(delay),
                "status": (
                    "on_time" if abs(delay) < 120 else ("delayed" if delay > 0 else "early")
                ),
            }
        )

    worst = max((u["delay_s"] for u in updates), default=0)
    status = "on_time" if abs(worst) < 120 else ("delayed" if worst > 0 else "early")

    existing = db.execute(
        select(TrackedJourneyRow)
        .where(
            TrackedJourneyRow.device_key == device,
            TrackedJourneyRow.journey_id == request.journey_id,
        )
        .order_by(TrackedJourneyRow.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            TrackedJourneyRow(
                device_key=device,
                journey_id=request.journey_id,
                payload=request.payload,
                status=status,
                delay_s=worst,
            )
        )
    else:
        existing.status = status
        existing.delay_s = worst
        existing.payload = request.payload
    db.commit()

    return {
        "journey_id": request.journey_id,
        "checked_at": now.isoformat(timespec="seconds"),
        "status": status,
        "delay_s": worst,
        "delay_label": realtime._delay_label(worst),
        "legs": updates,
        "advice": (
            "You are on time."
            if abs(worst) < 120
            else (
                f"Running {realtime._delay_label(worst).lower()}. "
                "Leave later for your connection, or re-plan to avoid it."
            )
        ),
    }


# ---------------------------------------------------------------------------
# Saved journeys, alerts, history
# ---------------------------------------------------------------------------


@user.get("/saved", summary="Saved journeys")
def list_saved(db: DbDep, device: DeviceDep) -> dict:
    rows = repo.list_saved_journeys(db, device)
    return {
        "count": len(rows),
        "saved": [
            {
                "id": row.id,
                "label": row.label,
                "origin": {"id": row.origin_id, "label": row.origin_label,
                           "lat": row.origin_lat, "lon": row.origin_lon},
                "destination": {"id": row.destination_id,
                                "label": row.destination_label,
                                "lat": row.destination_lat, "lon": row.destination_lon},
                "preference": row.preference,
                "created_at": row.created_at.isoformat(timespec="seconds"),
            }
            for row in rows
        ],
    }


@user.post("/saved", status_code=status.HTTP_201_CREATED, summary="Save a journey")
def save_journey(
    planner: PlannerDep, db: DbDep, device: OptionalDeviceDep, request: SaveJourneyRequest
) -> dict:
    device = resolve_device(device, request.device_key)
    origin = planner.resolve_place(request.origin)
    destination = planner.resolve_place(request.destination)
    if origin is None or destination is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown place")
    row = SavedJourneyRow(
        device_key=device,
        label=request.label or f"{origin.label} to {destination.label}",
        origin_id=origin.id,
        origin_label=origin.label,
        origin_lat=origin.lat,
        origin_lon=origin.lon,
        destination_id=destination.id,
        destination_label=destination.label,
        destination_lat=destination.lat,
        destination_lon=destination.lon,
        preference=request.preference.value,
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "label": row.label, "saved": True}


@user.delete("/saved/{journey_id}", summary="Forget a saved journey")
def delete_saved(db: DbDep, device: DeviceDep, journey_id: int) -> dict:
    if not repo.delete_saved_journey(db, device, journey_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such saved journey")
    db.commit()
    return {"deleted": True, "id": journey_id}


@user.get("/alerts", summary="Price alerts")
def list_alerts(db: DbDep, device: DeviceDep) -> dict:
    rows = repo.list_price_alerts(db, device)
    return {
        "count": len(rows),
        "alerts": [
            {
                "id": row.id,
                "origin": row.origin_label,
                "destination": row.destination_label,
                "preference": row.preference,
                "target_price": row.target_price,
                "baseline_price": row.baseline_price,
                "last_price": row.last_price,
                "last_checked_at": row.last_checked_at.isoformat(timespec="seconds")
                if row.last_checked_at
                else None,
                "triggered_at": row.triggered_at.isoformat(timespec="seconds")
                if row.triggered_at
                else None,
                "active": row.active,
            }
            for row in rows
        ],
    }


@user.post("/alerts", status_code=status.HTTP_201_CREATED, summary="Watch a route price")
def create_alert(
    planner: PlannerDep, db: DbDep, device: OptionalDeviceDep, request: PriceAlertRequest
) -> dict:
    device = resolve_device(device, request.device_key)
    origin = planner.resolve_place(request.origin)
    destination = planner.resolve_place(request.destination)
    if origin is None or destination is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown place")

    # Price it now, so the alert has a baseline to improve on.
    baseline = None
    try:
        result = planner.plan(
            origin=origin,
            destination=destination,
            preference=Preference.CHEAPEST,
            departure_sweep=1,
        )
        if result.journeys:
            baseline = min(j.price for j in result.journeys)
    except Exception:  # pragma: no cover - planning must not block a watch
        baseline = None

    row = PriceAlertRow(
        device_key=device,
        origin_label=origin.label,
        destination_label=destination.label,
        origin_lat=origin.lat,
        origin_lon=origin.lon,
        destination_lat=destination.lat,
        destination_lon=destination.lon,
        preference=request.preference.value,
        target_price=request.target_price,
        baseline_price=baseline,
        last_price=baseline,
        last_checked_at=uk_now(),
    )
    db.add(row)
    db.commit()
    return {
        "id": row.id,
        "watching": f"{origin.label} to {destination.label}",
        "current_best_price": baseline,
        "target_price": request.target_price,
    }


@user.delete("/alerts/{alert_id}", summary="Stop watching a route")
def delete_alert(db: DbDep, device: DeviceDep, alert_id: int) -> dict:
    row = db.get(PriceAlertRow, alert_id)
    if row is None or row.device_key != device:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such alert")
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": alert_id}


@user.get("/alerts/check", summary="Re-price watches and report drops")
def check_alerts(planner: PlannerDep, db: DbDep, device: DeviceDep) -> dict:
    """Re-price every active watch and report anything that got cheaper."""
    rows = repo.list_price_alerts(db, device)
    checked, triggered = [], []
    now = uk_now()
    for row in rows:
        if not row.active:
            continue
        try:
            result = planner.plan(
                origin=planner.resolve_place(row.origin_label) or row.origin_label,
                destination=planner.resolve_place(row.destination_label)
                or row.destination_label,
                preference=Preference(row.preference),
                departure_sweep=1,
            )
        except Exception:  # pragma: no cover
            continue
        if not result.journeys:
            continue
        best = min(j.price for j in result.journeys)
        previous = row.last_price
        row.last_price = best
        row.last_checked_at = now
        entry = {
            "id": row.id,
            "route": f"{row.origin_label} to {row.destination_label}",
            "price": best,
            "price_label": money(best),
            "previous_price": previous,
            "change": round(best - previous, 2) if previous is not None else None,
        }
        checked.append(entry)
        if (previous is not None and best < previous - 0.01) or (
            row.target_price is not None and best <= row.target_price
        ):
            row.triggered_at = now
            triggered.append(entry)
    db.commit()
    return {"checked": len(checked), "triggered": len(triggered),
            "results": checked, "drops": triggered}


@user.get("/history", summary="Your recent searches")
def search_history(db: DbDep, device: DeviceDep, limit: int = Query(default=20, ge=1, le=100)) -> dict:
    rows = list(
        db.execute(
            select(JourneySearchRow)
            .where(JourneySearchRow.device_key == device)
            .order_by(JourneySearchRow.id.desc())
            .limit(limit)
        ).scalars()
    )
    return {
        "count": len(rows),
        "history": [
            {
                "origin": row.origin_label,
                "destination": row.destination_label,
                "preference": row.preference,
                "when": row.departure_at.isoformat(timespec="minutes"),
                "results": row.results,
                "best_price": row.best_price,
                "searched_at": row.created_at.isoformat(timespec="seconds"),
            }
            for row in rows
        ],
    }
