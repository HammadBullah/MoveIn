"""Relational schema for MoveIn.

Every table mirrors an entity in :mod:`app.domain.models` one-to-one, so the
network can be written to the database and read back without translation
losses.  On top of the domain entities the schema carries what a *service*
needs: realtime vehicle reports, service alerts, feed provenance, and the
Phase 1 product tables (saved journeys, price alerts, tracked journeys).

Coordinate columns go through :class:`~app.db.types.Geography`, so the same
schema runs against PostGIS in production and SQLite in the prototype.

Columns marked "derived" are filled when the feed is loaded.  They are not part
of the domain model; they exist so the API can filter and group without loading
the whole network into memory.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .types import Geography


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


# ---------------------------------------------------------------------------
# Network entities (mirror of app.domain.models)
# ---------------------------------------------------------------------------


class StopRow(Base):
    """A place where a passenger can board or alight."""

    __tablename__ = "stops"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(220), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    #: PostGIS geography, or WKT text on SQLite.  Derived from lat/lon.
    location: Mapped[str | None] = mapped_column(Geography("POINT"), nullable=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    #: NaPTAN ATCO code, where the stop came from NaPTAN.
    atco_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Three-letter CRS code, for railway stations.
    crs_code: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    locality_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    region: Mapped[str] = mapped_column(String(64), index=True, default="")
    parent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: GTFS ``wheelchair_boarding``: 0 unknown, 1 accessible, 2 not accessible.
    wheelchair_boarding: Mapped[int] = mapped_column(Integer, default=1)
    interchange: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Provenance: "naptan" | "rail_tiploc" | "derived".
    source: Mapped[str] = mapped_column(String(24), default="naptan")

    __table_args__ = (
        Index("ix_stops_lat_lon", "lat", "lon"),
        Index("ix_stops_region_mode", "region", "mode"),
    )


class RouteRow(Base):
    """A named service pattern operated by one operator."""

    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    operator_code: Mapped[str] = mapped_column(
        ForeignKey("operators.code"), index=True, default=""
    )
    mode: Mapped[str] = mapped_column(String(16), index=True)
    short_name: Mapped[str] = mapped_column(String(64), default="")
    long_name: Mapped[str] = mapped_column(String(240), default="")
    colour: Mapped[str] = mapped_column(String(9), default="#4b5563")
    #: Marketing brand, e.g. "NCT Navy Line".
    brand: Mapped[str] = mapped_column(String(120), default="")
    # --- derived (filled on load, useful for filtering) -------------------
    region: Mapped[str] = mapped_column(String(64), index=True, default="")
    corridor_code: Mapped[str] = mapped_column(String(24), index=True, default="")
    text_colour: Mapped[str] = mapped_column(String(9), default="#ffffff")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    operator: Mapped[OperatorRow | None] = relationship(back_populates="routes")
    trips: Mapped[list["TripRow"]] = relationship(back_populates="route")


class OperatorRow(Base):
    """A transport operator: a train company, bus company, tram operator, ..."""

    __tablename__ = "operators"

    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    noc: Mapped[str | None] = mapped_column(String(24), nullable=True)
    atoc_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    website: Mapped[str | None] = mapped_column(String(220), nullable=True)
    colour: Mapped[str | None] = mapped_column(String(9), nullable=True)
    #: "atoc" | "nac" | "synthetic"
    source: Mapped[str | None] = mapped_column(String(24), nullable=True, default="atoc")

    routes: Mapped[list[RouteRow]] = relationship(back_populates="operator")


class CalendarRow(Base):
    """GTFS ``calendar``: which weekdays a service runs, over a date range."""

    __tablename__ = "calendars"

    #: ``service_id`` in the domain model.
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    #: Seven characters, Monday first: "1111100" is a weekday-only service.
    days: Mapped[str] = mapped_column(String(7), default="1111100")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class CalendarDateRow(Base):
    """A GTFS ``calendar_dates`` exception."""

    __tablename__ = "calendar_dates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_id: Mapped[str] = mapped_column(String(128), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    #: 1 = service added on this date, 2 = service removed.
    exception_type: Mapped[int] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("service_id", "date", name="uq_caldate"),)


class TripRow(Base):
    """One vehicle run over a route on a service day."""

    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    route_id: Mapped[str] = mapped_column(ForeignKey("routes.id"), index=True)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("calendars.id"), index=True, default=""
    )
    headsign: Mapped[str] = mapped_column(String(220), default="")
    direction: Mapped[int] = mapped_column(Integer, default=0)
    wheelchair_accessible: Mapped[int] = mapped_column(Integer, default=1)
    bikes_allowed: Mapped[int] = mapped_column(Integer, default=1)
    #: Reliability factor for this run (1.0 = runs to timetable).
    reliability: Mapped[float] = mapped_column(Float, default=0.92)

    route: Mapped[RouteRow] = relationship(back_populates="trips")
    stop_times: Mapped[list["StopTimeRow"]] = relationship(
        back_populates="trip", order_by="StopTimeRow.stop_sequence"
    )


class StopTimeRow(Base):
    """Arrival and departure of a trip at a stop, in seconds after midnight."""

    __tablename__ = "stop_times"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), index=True)
    stop_id: Mapped[str] = mapped_column(ForeignKey("stops.id"), index=True)
    stop_sequence: Mapped[int] = mapped_column(Integer)
    arrival_s: Mapped[int] = mapped_column(Integer)
    departure_s: Mapped[int] = mapped_column(Integer)
    pickup_type: Mapped[int] = mapped_column(Integer, default=0)
    dropoff_type: Mapped[int] = mapped_column(Integer, default=0)
    headsign: Mapped[str] = mapped_column(String(220), default="")
    same_station: Mapped[bool] = mapped_column(Boolean, default=False)

    trip: Mapped[TripRow] = relationship(back_populates="stop_times")

    __table_args__ = (
        Index("ix_stop_times_trip_seq", "trip_id", "stop_sequence"),
        Index("ix_stop_times_stop_dep", "stop_id", "departure_s"),
    )


class TransferRow(Base):
    """A walking connection between two stops (GTFS ``transfers``)."""

    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_stop_id: Mapped[str] = mapped_column(ForeignKey("stops.id"), index=True)
    to_stop_id: Mapped[str] = mapped_column(ForeignKey("stops.id"), index=True)
    #: GTFS transfer_type: 1 = timed, 2 = minimum time, 3 = not possible.
    transfer_type: Mapped[int] = mapped_column(Integer, default=2)
    min_transfer_s: Mapped[int] = mapped_column(Integer, default=120)
    distance_m: Mapped[float] = mapped_column(Float, default=0.0)
    #: True when the transfer happens inside one station, with no street walking.
    within_station: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("from_stop_id", "to_stop_id", name="uq_transfer_pair"),
    )


class FareAttributeRow(Base):
    """GTFS ``fare_attributes`` -- a ticket product."""

    __tablename__ = "fare_attributes"

    fare_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    price: Mapped[float] = mapped_column(Float)
    currency_type: Mapped[str] = mapped_column(String(3), default="GBP")
    payment_method: Mapped[int] = mapped_column(Integer, default=0)
    transfers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transfer_duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # --- MoveIn extensions ------------------------------------------------
    label: Mapped[str] = mapped_column(String(120), default="")
    #: "single" | "return" | "day" | "season" | "advance" | "cap"
    product_type: Mapped[str] = mapped_column(String(24), index=True, default="single")
    operator_code: Mapped[str] = mapped_column(String(24), index=True, default="")
    offpeak_only: Mapped[bool] = mapped_column(Boolean, default=False)
    advance_only: Mapped[bool] = mapped_column(Boolean, default=False)
    railcard_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    student_eligible: Mapped[bool] = mapped_column(Boolean, default=False)


class FareRuleRow(Base):
    """GTFS ``fare_rules`` -- links a fare product to the services it covers."""

    __tablename__ = "fare_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fare_id: Mapped[str] = mapped_column(
        ForeignKey("fare_attributes.fare_id"), index=True
    )
    route_id: Mapped[str] = mapped_column(String(80), index=True, default="")
    origin_id: Mapped[str] = mapped_column(String(128), default="")
    destination_id: Mapped[str] = mapped_column(String(128), default="")
    contains_id: Mapped[str] = mapped_column(String(64), default="")


# ---------------------------------------------------------------------------
# Realtime
# ---------------------------------------------------------------------------


class VehiclePositionRow(Base):
    """A live vehicle observation, as pushed by SIRI-VM or GTFS-Realtime."""

    __tablename__ = "vehicle_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[str] = mapped_column(String(64), index=True)
    trip_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    route_id: Mapped[str] = mapped_column(String(80), index=True, default="")
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    location: Mapped[str | None] = mapped_column(Geography("POINT"), nullable=True)
    bearing: Mapped[float] = mapped_column(Float, default=0.0)
    speed_mps: Mapped[float] = mapped_column(Float, default=0.0)
    #: Positive means running late.
    delay_s: Mapped[int] = mapped_column(Integer, default=0)
    timestamp: Mapped[str] = mapped_column(String(40), default="")
    occupancy: Mapped[str] = mapped_column(String(24), default="unknown")
    #: "siri-vm" | "gtfs-rt" | "tfl" | "simulated"
    source: Mapped[str] = mapped_column(String(24), default="simulated")
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class ServiceAlertRow(Base):
    """A realtime or planned disruption."""

    __tablename__ = "service_alerts"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    header: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    #: "info" | "warning" | "severe"
    severity: Mapped[str] = mapped_column(String(24), default="warning", index=True)
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    route_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    stop_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    starts_at: Mapped[str] = mapped_column(String(40), default="")
    ends_at: Mapped[str] = mapped_column(String(40), default="")
    source: Mapped[str] = mapped_column(String(32), default="synthetic")
    regions: Mapped[list | None] = mapped_column(JSON, nullable=True)


class FeedInfoRow(Base):
    """Provenance for the loaded feed, so a stale database can be detected."""

    __tablename__ = "feed_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    publisher: Mapped[str] = mapped_column(String(180))
    publisher_url: Mapped[str] = mapped_column(String(240), default="")
    lang: Mapped[str] = mapped_column(String(8), default="en")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    version: Mapped[str] = mapped_column(String(80), default="")
    #: Content digest of the loaded feed.
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    is_live_feed: Mapped[bool] = mapped_column(Boolean, default=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class DataSourceRow(Base):
    """Where a dataset came from, and whether it is real or generated.

    MoveIn is explicit about this everywhere it is shown: the geography, the
    stops and the operators are real published data, while the timetable layer
    is compiled.  Recording that here means the API can tell the user.
    """

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(180))
    url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    licence: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: "real" | "compiled" | "generated"
    kind: Mapped[str] = mapped_column(String(24))
    rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Product tables (Phase 1)
# ---------------------------------------------------------------------------


class SavedJourneyRow(Base, TimestampMixin):
    """A journey the traveller asked MoveIn to remember.

    Phase 1 has no accounts, so rows are scoped by an opaque device key that the
    client generates.  Phase 2 replaces it with a real user id without touching
    the rest of the schema.
    """

    __tablename__ = "saved_journeys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_key: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(180), default="")
    origin_id: Mapped[str] = mapped_column(String(128), default="")
    origin_label: Mapped[str] = mapped_column(String(220))
    origin_lat: Mapped[float] = mapped_column(Float)
    origin_lon: Mapped[float] = mapped_column(Float)
    destination_id: Mapped[str] = mapped_column(String(128), default="")
    destination_label: Mapped[str] = mapped_column(String(220))
    destination_lat: Mapped[float] = mapped_column(Float)
    destination_lon: Mapped[float] = mapped_column(Float)
    preference: Mapped[str] = mapped_column(String(32), default="best_value")


class PriceAlertRow(Base, TimestampMixin):
    """A watch on a route: tell me when this trip gets cheaper."""

    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_key: Mapped[str] = mapped_column(String(64), index=True)
    origin_label: Mapped[str] = mapped_column(String(220))
    destination_label: Mapped[str] = mapped_column(String(220))
    origin_lat: Mapped[float] = mapped_column(Float)
    origin_lon: Mapped[float] = mapped_column(Float)
    destination_lat: Mapped[float] = mapped_column(Float)
    destination_lon: Mapped[float] = mapped_column(Float)
    preference: Mapped[str] = mapped_column(String(32), default="cheapest")
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class JourneySearchRow(Base):
    """An audit row for every search, which doubles as the analytics feed."""

    __tablename__ = "journey_searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_key: Mapped[str] = mapped_column(String(64), index=True, default="")
    origin_label: Mapped[str] = mapped_column(String(220))
    destination_label: Mapped[str] = mapped_column(String(220))
    preference: Mapped[str] = mapped_column(String(32))
    departure_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    results: Mapped[int] = mapped_column(Integer, default=0)
    best_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fastest_duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    search_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class TrackedJourneyRow(Base, TimestampMixin):
    """A journey the traveller is on right now, for live re-planning."""

    __tablename__ = "tracked_journeys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_key: Mapped[str] = mapped_column(String(64), index=True)
    journey_id: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    #: "on_time" | "delayed" | "disrupted" | "completed"
    status: Mapped[str] = mapped_column(String(24), default="on_time")
    delay_s: Mapped[int] = mapped_column(Integer, default=0)
