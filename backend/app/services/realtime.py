"""Live vehicle tracking.

MoveIn's realtime layer is deliberately pluggable.  In production it consumes
BODS SIRI-VM and GTFS-Realtime feeds (see ``app.ingest.bods``); in the sandbox
those hosts are unreachable, so the same interface is served by a simulator that
drives vehicles along their real schedules.

Everything above this module -- the API, the re-planning logic, the UI -- is
identical either way, so switching to live data is a configuration change.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..db.models import ServiceAlertRow, VehiclePositionRow
from ..domain.models import Mode, TransportNetwork
from ..engine.graph import TransitGraph
from ..ingest.geo import bearing_deg, haversine_m


@dataclass
class LiveVehicle:
    """One vehicle, as reported by the feed."""

    vehicle_id: str
    trip_id: str
    route_id: str
    operator_code: str
    lat: float
    lon: float
    bearing: float
    speed_mps: float
    delay_s: int
    occupancy: str
    next_stop_id: str
    next_stop_name: str
    progress: float
    recorded_at: datetime
    source: str = "simulated"
    #: "rail" | "bus" | "coach" | "tram" | "metro"
    mode: str = "bus"
    route_name: str = ""
    headsign: str = ""

    def as_dict(self) -> dict:
        return {
            "vehicle_id": self.vehicle_id,
            "trip_id": self.trip_id,
            "route_id": self.route_id,
            "route_name": self.route_name,
            "mode": self.mode,
            "headsign": self.headsign,
            "operator_code": self.operator_code,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "bearing": round(self.bearing, 1),
            "speed_mps": round(self.speed_mps, 1),
            "delay_s": self.delay_s,
            "delay_label": _delay_label(self.delay_s),
            "occupancy": self.occupancy,
            "next_stop": {"id": self.next_stop_id, "name": self.next_stop_name},
            "progress": round(self.progress, 3),
            "recorded_at": self.recorded_at.isoformat(timespec="seconds"),
            "source": self.source,
        }


def _delay_label(delay_s: int) -> str:
    if abs(delay_s) < 60:
        return "On time"
    minutes = round(abs(delay_s) / 60)
    return f"{minutes} min late" if delay_s > 0 else f"{minutes} min early"


def _interpolate(graph: TransitGraph, trip_id: str, progress: float) -> tuple[float, float, float, int]:
    """Position along a trip at ``progress`` in [0, 1], by distance travelled."""
    profile = graph.trip_profiles.get(trip_id)
    if profile is None:
        return 0.0, 0.0, 0.0, 0
    points = [graph.stops.get(sid) for sid in profile.stops]
    points = [p for p in points if p is not None]
    if len(points) < 2:
        return 0.0, 0.0, 0.0, 0

    legs = [
        haversine_m(a.lat, a.lon, b.lat, b.lon) for a, b in zip(points, points[1:])
    ]
    total = sum(legs) or 1.0
    target = progress * total
    travelled = 0.0
    for index, leg in enumerate(legs):
        if travelled + leg >= target or index == len(legs) - 1:
            fraction = (target - travelled) / leg if leg else 0.0
            fraction = min(max(fraction, 0.0), 1.0)
            a, b = points[index], points[index + 1]
            lat = a.lat + (b.lat - a.lat) * fraction
            lon = a.lon + (b.lon - a.lon) * fraction
            speed = leg / max(1.0, 60.0)
            return lat, lon, bearing_deg(a.lat, a.lon, b.lat, b.lon), index + 1
        travelled += leg
    return points[-1].lat, points[-1].lon, 0.0, len(points) - 1


def active_trips(
    graph: TransitGraph, *, at: datetime, services: set[str], limit: int = 400
) -> list[str]:
    """Trips that should have a vehicle on the road at ``at``."""
    seconds = at.hour * 3600 + at.minute * 60 + at.second
    running: list[str] = []
    for trip_id, profile in graph.trip_profiles.items():
        trip = graph.net.trips.get(trip_id)
        if trip is None or trip.service_id not in services:
            continue
        if not profile.departures or not profile.arrivals:
            continue
        if profile.departures[0] <= seconds <= profile.arrivals[-1]:
            running.append(trip_id)
            if len(running) >= limit:
                break
    return running


def simulate_positions(
    graph: TransitGraph,
    *,
    at: datetime | None = None,
    services: set[str] | None = None,
    limit: int = 300,
    seed: int | None = None,
) -> list[LiveVehicle]:
    """Build the live picture from the timetable.

    Each running trip gets a vehicle positioned by how far through its schedule
    it should be, plus a deterministic delay so the interface has to cope with
    real-world lateness.
    """
    at = at or datetime.now()
    services = services if services is not None else graph.services_on(at.date())
    seconds = at.hour * 3600 + at.minute * 60 + at.second
    rng = random.Random(seed if seed is not None else int(at.timestamp() // 60))

    out: list[LiveVehicle] = []
    for trip_id in active_trips(graph, at=at, services=services, limit=limit):
        profile = graph.trip_profiles[trip_id]
        trip = graph.net.trips[trip_id]
        route = graph.net.routes.get(trip.route_id)
        if route is None:
            continue
        start, finish = profile.departures[0], profile.arrivals[-1]
        if finish <= start:
            continue
        progress = (seconds - start) / (finish - start)
        progress = min(max(progress, 0.0), 1.0)

        # Delays cluster: most vehicles run roughly to time, a few do not.
        roll = rng.random()
        if roll < 0.72:
            delay = rng.randint(-45, 60)
        elif roll < 0.94:
            delay = rng.randint(60, 420)
        else:
            delay = rng.randint(420, 1500)
        delay = int(delay * (1.0 - 0.5 * progress))  # late running recovers

        lat, lon, bearing, next_index = _interpolate(graph, trip_id, progress)
        next_stop = graph.stops.get(profile.stops[min(next_index, len(profile.stops) - 1)])
        occupancy = rng.choice(
            ["empty", "many_seats", "few_seats", "standing", "full"]
            if route.mode in (Mode.BUS, Mode.TRAM, Mode.METRO)
            else ["empty", "many_seats", "few_seats"]
        )
        out.append(
            LiveVehicle(
                vehicle_id=f"{trip.route_id}-{trip_id.rsplit('-', 1)[-1]}",
                trip_id=trip_id,
                route_id=trip.route_id,
                operator_code=route.operator_code,
                lat=lat,
                lon=lon,
                bearing=bearing,
                speed_mps=max(0.0, 0.0 if progress >= 1.0 else rng.uniform(4.0, 16.0)),
                delay_s=delay,
                occupancy=occupancy,
                next_stop_id=next_stop.id if next_stop else "",
                next_stop_name=next_stop.name if next_stop else "",
                progress=progress,
                recorded_at=at,
                mode=route.mode.value,
                route_name=route.short_name or route.id,
                headsign=profile.headsign or (next_stop.name if next_stop else ""),
            )
        )
    return out


def store_positions(session: Session, vehicles: list[LiveVehicle]) -> int:
    """Replace the stored live picture with the latest sweep."""
    session.execute(delete(VehiclePositionRow))
    if not vehicles:
        return 0
    session.bulk_save_objects(
        [
            VehiclePositionRow(
                vehicle_id=v.vehicle_id,
                trip_id=v.trip_id,
                route_id=v.route_id,
                lat=v.lat,
                lon=v.lon,
                location=f"SRID=4326;POINT({v.lon} {v.lat})",
                bearing=v.bearing,
                speed_mps=v.speed_mps,
                delay_s=v.delay_s,
                timestamp=v.recorded_at.isoformat(timespec="seconds"),
                occupancy=v.occupancy,
                source=v.source,
                recorded_at=v.recorded_at,
            )
            for v in vehicles
        ]
    )
    return len(vehicles)


# ---------------------------------------------------------------------------
# Disruption
# ---------------------------------------------------------------------------

#: Stand-in for the BODS disruption feed while the live hosts are unreachable.
#: These are written from the real operating characteristics of the corridors
#: MoveIn models; they are not live reports, and the API says so.
SEED_ALERTS: tuple[dict, ...] = (
    {
        "id": "demo-mml-1-engineering",
        "header": "Planned engineering work between Derby and Chesterfield",
        "description": (
            "Buses replace trains on some evening services while track renewal "
            "takes place. Allow an extra 30 minutes."
        ),
        "severity": "warning",
        "mode": "rail",
        "route_ids": ["MML-1", "EMR-5"],
        "stop_ids": ["rail:DBY", "rail:CHD"],
        "regions": ["derby", "sheffield"],
        "source": "sample",
    },
    {
        "id": "demo-tfl-b1-diversion",
        "header": "Route 24 diverted via Whitehall",
        "description": "Roadworks at Trafalgar Square; stops at Charing Cross are not served.",
        "severity": "info",
        "mode": "bus",
        "route_ids": ["TFL-B1"],
        "stop_ids": ["naptan:london:charing-cross-underground-1"],
        "regions": ["london"],
        "source": "sample",
    },
    {
        "id": "demo-nxwm-3-congestion",
        "header": "Heavy traffic on the A34 into Birmingham",
        "description": "National Express West Midlands services are running 10 to 15 minutes late.",
        "severity": "warning",
        "mode": "bus",
        "route_ids": ["NXWM-3", "NXWM-1"],
        "stop_ids": [],
        "regions": ["birmingham"],
        "source": "sample",
    },
    {
        "id": "demo-net-1-improvement",
        "header": "NET tram frequencies reduced at the weekend",
        "description": "Trams run every 15 minutes while overhead line work is carried out.",
        "severity": "info",
        "mode": "tram",
        "route_ids": ["NET-1"],
        "stop_ids": [],
        "regions": ["nottingham"],
        "source": "sample",
    },
)


def seed_alerts(session: Session, net: TransportNetwork) -> int:
    """Load the sample disruption set, skipped if real alerts already exist."""
    existing = session.query(ServiceAlertRow).count()
    if existing:
        return 0
    now = datetime.now()
    for alert in SEED_ALERTS:
        session.add(
            ServiceAlertRow(
                id=alert["id"],
                header=alert["header"],
                description=alert["description"],
                severity=alert["severity"],
                mode=alert.get("mode"),
                route_ids=list(alert.get("route_ids", [])),
                stop_ids=list(alert.get("stop_ids", [])),
                starts_at=(now - timedelta(days=1)).isoformat(timespec="seconds"),
                ends_at=(now + timedelta(days=14)).isoformat(timespec="seconds"),
                source=alert.get("source", "sample"),
                regions=list(alert.get("regions", [])),
            )
        )
    return len(SEED_ALERTS)


def from_siri_vm(payloads: list[dict], *, net: TransportNetwork | None = None) -> list[LiveVehicle]:
    """Convert parsed SIRI-VM records into :class:`LiveVehicle` objects.

    ``backend.app.ingest.bods.parse_siri_vm`` produces plain dicts so the ingest
    layer stays free of service-layer imports; this is the other half of that
    seam.  Records whose trip is not in the network are dropped: a vehicle MoveIn
    cannot place on a line is not something it can show a traveller.
    """
    out: list[LiveVehicle] = []
    for record in payloads:
        trip_id = record.get("trip_id", "")
        if net is not None and trip_id and trip_id not in net.trips:
            continue
        route = net.routes.get(record.get("route_id", "")) if net is not None else None
        out.append(
            LiveVehicle(
                vehicle_id=str(record.get("vehicle_id") or "unknown"),
                trip_id=trip_id,
                route_id=record.get("route_id", ""),
                route_name=record.get("route_name") or (route.short_name if route else ""),
                operator_code=record.get("operator_code") or (
                    route.operator_code if route else ""
                ),
                lat=float(record["lat"]),
                lon=float(record["lon"]),
                bearing=float(record.get("bearing") or 0.0),
                speed_mps=float(record.get("speed_mps") or 0.0),
                delay_s=int(record.get("delay_s") or 0),
                occupancy=record.get("occupancy") or "unknown",
                next_stop_id=record.get("next_stop_id", ""),
                next_stop_name=record.get("next_stop_name", ""),
                progress=float(record.get("progress") or 0.0),
                recorded_at=record.get("recorded_at") or datetime.now(),
                source=record.get("source") or "siri-vm",
                mode=(route.mode.value if route else "bus"),
                headsign=record.get("headsign", ""),
            )
        )
    return out


def delay_for_trip(vehicles: list[LiveVehicle], trip_id: str) -> int:
    """Current delay on a trip, or 0 when no vehicle is reporting."""
    for vehicle in vehicles:
        if vehicle.trip_id == trip_id:
            return vehicle.delay_s
    return 0


def adjust_time(seconds: int, delay_s: int) -> int:
    """Shift a scheduled time by a reported delay."""
    return max(0, int(seconds + delay_s))


def services_for(net: TransportNetwork, day: date) -> set[str]:
    """Service ids running on a date -- a thin wrapper for the live layer."""
    out: set[str] = set()
    for service_id, calendar in net.calendars.items():
        if calendar.start_date and calendar.end_date:
            if not (calendar.start_date <= day <= calendar.end_date):
                pass
        if calendar.runs_on_weekday(day.weekday()):
            out.add(service_id)
    return out


def heading_word(bearing: float) -> str:
    """Compass direction for a live vehicle, for the UI label."""
    sectors = [
        "north", "north-east", "east", "south-east",
        "south", "south-west", "west", "north-west",
    ]
    return sectors[int(((bearing % 360) / 45) + 0.5) % 8]
