"""MoveIn's internal transport model.

This is the common representation every source is normalised into.  It is
deliberately a superset of the GTFS schedule spec (which the brief names as the
internal standard) plus the extra fields the optimisation engine needs:
reliability, accessibility, emissions and per-leg fare products.

``app.ingest.gtfs`` maps this model to and from real GTFS files, so any of the
thousands of published GTFS feeds can be loaded without touching the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Mode(str, Enum):
    """Transport modes, aligned with the GTFS ``route_type`` taxonomy."""

    WALK = "walk"
    CYCLE = "cycle"
    BUS = "bus"
    COACH = "coach"
    RAIL = "rail"
    TRAM = "tram"
    METRO = "metro"
    FERRY = "ferry"
    TAXI = "taxi"
    RIDEHAIL = "ridehail"
    AIR = "air"

    @property
    def gtfs_route_type(self) -> int:
        """The GTFS ``route_type`` for this mode.

        GTFS's original route types have no coach: a coach is "3" (bus) and a
        round trip through the feed turns every National Express service into a
        local bus.  The extended route types -- widely supported, and what
        operators publish -- give coaches their own code, so the distinction the
        whole product is built on survives the file format.
        """
        return {
            Mode.TRAM: 0,
            Mode.METRO: 1,
            Mode.RAIL: 2,
            Mode.BUS: 3,
            Mode.FERRY: 4,
            Mode.COACH: 200,  # extended GTFS: coach service
            Mode.WALK: 3,
            Mode.CYCLE: 3,
            Mode.TAXI: 3,
            Mode.RIDEHAIL: 3,
            Mode.AIR: 3,
        }[self]

    @classmethod
    def from_gtfs(cls, route_type: int) -> "Mode":
        code = int(route_type)
        if 200 <= code <= 209:  # extended route types: coach services
            return cls.COACH
        if 700 <= code <= 799:  # extended route types: bus services
            return cls.BUS
        if 100 <= code <= 117:  # extended route types: rail services
            return cls.RAIL
        if 400 <= code <= 405:  # extended route types: urban rail / metro
            return cls.METRO
        if 900 <= code <= 906:  # extended route types: tram
            return cls.TRAM
        if 1000 <= code <= 1200:  # extended route types: water transport
            return cls.FERRY
        return {
            0: cls.TRAM,
            1: cls.METRO,
            2: cls.RAIL,
            3: cls.BUS,
            4: cls.FERRY,
            5: cls.TRAM,
            6: cls.METRO,
            7: cls.BUS,
            11: cls.BUS,
            12: cls.RAIL,
        }.get(code, cls.BUS)

    @property
    def is_transit(self) -> bool:
        return self not in (Mode.WALK, Mode.CYCLE, Mode.TAXI, Mode.RIDEHAIL)

    @property
    def label(self) -> str:
        return {
            Mode.WALK: "Walk",
            Mode.CYCLE: "Cycle",
            Mode.BUS: "Bus",
            Mode.COACH: "Coach",
            Mode.RAIL: "Train",
            Mode.TRAM: "Tram",
            Mode.METRO: "Metro",
            Mode.FERRY: "Ferry",
            Mode.TAXI: "Taxi",
            Mode.RIDEHAIL: "Ride-hailing",
            Mode.AIR: "Air",
        }[self]


#: Grams of CO2e per passenger-kilometre, by mode.
#: Derived from UK Government (DESNZ) greenhouse-gas conversion factors for
#: passenger transport, using average vehicle occupancy rather than a
#: full-vehicle figure so a coach compares fairly against a car.
CO2_G_PER_PKM: dict[Mode, float] = {
    Mode.WALK: 0.0,
    Mode.CYCLE: 0.0,
    Mode.BUS: 82.0,
    Mode.COACH: 27.0,
    Mode.RAIL: 35.0,
    Mode.TRAM: 22.0,
    Mode.METRO: 20.0,
    Mode.FERRY: 190.0,
    Mode.TAXI: 190.0,
    Mode.RIDEHAIL: 175.0,
    Mode.AIR: 245.0,
}


@dataclass(slots=True)
class Stop:
    """A place where a passenger can board or alight."""

    id: str
    name: str
    lat: float
    lon: float
    mode: Mode = Mode.BUS
    #: NaPTAN ATCO code, where the stop came from NaPTAN.
    atco_code: str = ""
    #: Three-letter CRS code, for railway stations.
    crs_code: str = ""
    #: NaPTAN NPTG locality code.
    locality_code: str = ""
    #: Modelled region slug.
    region: str = ""
    #: Parent station/stop-area id, mirroring GTFS ``parent_station``.
    parent_id: str | None = None
    #: GTFS ``wheelchair_boarding``: 0 unknown, 1 accessible, 2 not accessible.
    wheelchair_boarding: int = 1
    #: True when the stop is a major interchange (used for transfer rules).
    interchange: bool = False
    #: Provenance: "naptan", "rail_tiploc", "derived".
    source: str = "naptan"

    @property
    def is_transit(self) -> bool:
        return True


@dataclass(slots=True)
class Route:
    """A named service pattern operated by one operator."""

    id: str
    operator_code: str
    mode: Mode
    short_name: str
    long_name: str = ""
    colour: str = "#4b5563"
    #: Marketing brand (e.g. "NCT Navy Line").
    brand: str = ""


@dataclass(slots=True)
class Calendar:
    """GTFS ``calendar``: which weekdays a service runs, over a date range."""

    id: str
    days: tuple[bool, ...] = (True, True, True, True, True, True, False)
    start_date: date | None = None
    end_date: date | None = None

    def runs_on_weekday(self, weekday: int) -> bool:
        return bool(self.days[weekday])


@dataclass(slots=True)
class CalendarDate:
    """A GTFS ``calendar_dates`` exception."""

    service_id: str
    date: date
    exception_type: int  # 1 = added, 2 = removed


@dataclass(slots=True)
class Trip:
    """One vehicle run over a route on a service day."""

    id: str
    route_id: str
    service_id: str
    headsign: str = ""
    direction: int = 0
    #: GTFS ``wheelchair_accessible``: 0 unknown, 1 accessible, 2 not.
    wheelchair_accessible: int = 1
    #: GTFS ``bikes_allowed``: 0 unknown, 1 allowed, 2 not.
    bikes_allowed: int = 1
    #: Reliability factor for this specific run (1.0 = perfect).
    reliability: float = 0.92


@dataclass(slots=True)
class StopTime:
    """Arrival/departure of a trip at a stop.

    Times are stored as **seconds after midnight of the service day**, matching
    GTFS semantics where the value may exceed 24:00:00 for overnight services.
    """

    trip_id: str
    stop_id: str
    stop_sequence: int
    arrival_s: int
    departure_s: int
    #: GTFS pickup/dropoff type: 0 regular, 1 none, 2 phone, 3 coordinate.
    pickup_type: int = 0
    dropoff_type: int = 0
    headsign: str = ""
    #: True when the stop is part of the same station as the previous one.
    same_station: bool = False


@dataclass(slots=True)
class Transfer:
    """A walking connection between two stops (GTFS ``transfers``)."""

    from_stop_id: str
    to_stop_id: str
    #: GTFS transfer_type: 1 = timed, 2 = minimum time, 3 = not possible.
    transfer_type: int = 2
    min_transfer_s: int = 120
    distance_m: float = 0.0
    #: True when the transfer is inside a single station and needs no street
    #: walking (a "same station" interchange).
    within_station: bool = False


@dataclass(slots=True)
class FareAttribute:
    """GTFS ``fare_attributes`` -- a ticket product."""

    fare_id: str
    price: float
    currency_type: str = "GBP"
    payment_method: int = 0  # 0 = on board, 1 = before boarding
    transfers: int | None = None  # None = unlimited
    transfer_duration_s: int | None = None
    #: MoveIn extensions -------------------------------------------------
    #: Human label, e.g. "Off-Peak Single".
    label: str = ""
    #: "single" | "return" | "day" | "season" | "advance" | "cap"
    product_type: str = "single"
    #: Operator the product is valid on ("" = network-wide).
    operator_code: str = ""
    #: When true the ticket is only valid outside the peak.
    offpeak_only: bool = False
    #: When true the ticket must be bought in advance.
    advance_only: bool = False
    #: Railcard/student discounts this product accepts.
    railcard_eligible: bool = False
    student_eligible: bool = False


@dataclass(slots=True)
class FareRuleRow:
    """GTFS ``fare_rules`` -- links a fare product to the services it covers."""

    fare_id: str
    route_id: str = ""
    origin_id: str = ""
    destination_id: str = ""
    contains_id: str = ""


@dataclass(slots=True)
class ServiceAlert:
    """A real-time or planned disruption."""

    id: str
    header: str
    description: str = ""
    severity: str = "warning"
    mode: Mode | None = None
    route_ids: tuple[str, ...] = ()
    stop_ids: tuple[str, ...] = ()
    starts_at: str = ""
    ends_at: str = ""
    source: str = "synthetic"

    @property
    def is_disruption(self) -> bool:
        return self.severity in ("severe", "warning")


@dataclass(slots=True)
class VehiclePosition:
    """A live vehicle observation (GTFS-Realtime ``VehiclePosition``)."""

    vehicle_id: str
    trip_id: str
    route_id: str
    lat: float
    lon: float
    bearing: float = 0.0
    speed_mps: float = 0.0
    #: Seconds late (positive) or early (negative).
    delay_s: int = 0
    timestamp: str = ""
    occupancy: str = "unknown"
    source: str = "synthetic"


@dataclass(slots=True)
class FeedInfo:
    publisher: str = "MoveIn"
    publisher_url: str = ""
    lang: str = "en"
    start_date: date | None = None
    end_date: date | None = None
    version: str = ""


@dataclass(slots=True)
class TransportNetwork:
    """Everything the journey engine needs, in one in-memory object."""

    stops: dict[str, Stop] = field(default_factory=dict)
    routes: dict[str, Route] = field(default_factory=dict)
    trips: dict[str, Trip] = field(default_factory=dict)
    stop_times: dict[str, list[StopTime]] = field(default_factory=dict)
    calendars: dict[str, Calendar] = field(default_factory=dict)
    calendar_dates: list[CalendarDate] = field(default_factory=list)
    transfers: list[Transfer] = field(default_factory=list)
    fares: dict[str, FareAttribute] = field(default_factory=dict)
    fare_rules: list[FareRuleRow] = field(default_factory=list)
    feed_info: FeedInfo = field(default_factory=FeedInfo)
    #: corridor code -> list of trip ids, for cheap schedule lookups
    corridor_trips: dict[str, list[str]] = field(default_factory=dict)

    # --- convenience ------------------------------------------------------
    def stops_for_trip(self, trip_id: str) -> list[StopTime]:
        return self.stop_times.get(trip_id, [])

    def route_of_trip(self, trip_id: str) -> Route | None:
        trip = self.trips.get(trip_id)
        return self.routes.get(trip.route_id) if trip else None

    def stats(self) -> dict[str, int]:
        mode_counts: dict[str, int] = {}
        for route in self.routes.values():
            mode_counts[route.mode.value] = mode_counts.get(route.mode.value, 0) + 1
        return {
            "stops": len(self.stops),
            "routes": len(self.routes),
            "trips": len(self.trips),
            "stop_times": sum(len(v) for v in self.stop_times.values()),
            "transfers": len(self.transfers),
            "fares": len(self.fares),
            **{f"routes_{k}": v for k, v in sorted(mode_counts.items())},
        }


def seconds_to_gtfs_time(seconds: int) -> str:
    """Format seconds-after-midnight as GTFS ``HH:MM:SS`` (may exceed 24:00)."""
    seconds = int(seconds)
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    return f"{sign}{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def gtfs_time_to_seconds(value: str) -> int:
    """Parse GTFS ``HH:MM:SS`` (including hours beyond 24) into seconds."""
    value = value.strip()
    if not value:
        raise ValueError("empty GTFS time")
    negative = value.startswith("-")
    if negative:
        value = value[1:]
    parts = value.split(":")
    if len(parts) == 2:
        parts.append("0")
    if len(parts) != 3:
        raise ValueError(f"malformed GTFS time: {value!r}")
    hours, minutes, secs = (int(p) for p in parts)
    total = hours * 3600 + minutes * 60 + secs
    return -total if negative else total
