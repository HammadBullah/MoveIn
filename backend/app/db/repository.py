"""Reading and writing MoveIn's data.

Two responsibilities live here:

* moving the compiled transport network between the database and the engine's
  in-memory :class:`~app.domain.models.TransportNetwork`, with a content
  fingerprint so the API can tell when the files on disk have moved on; and
* the product queries the API needs -- stop lookup, saved journeys, price
  alerts, live vehicle positions and service alerts.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..domain.models import (
    Calendar,
    CalendarDate,
    FareAttribute,
    FareRuleRow,
    FeedInfo,
    Mode,
    Route,
    Stop,
    StopTime,
    Transfer,
    TransportNetwork,
    Trip,
)
from ..domain.regions import region_for_point
from .models import (
    CalendarDateRow,
    CalendarRow,
    FareAttributeRow,
    FareRuleRow as FareRuleModel,
    FeedInfoRow,
    JourneySearchRow,
    OperatorRow,
    PriceAlertRow,
    RouteRow,
    SavedJourneyRow,
    ServiceAlertRow,
    StopRow,
    StopTimeRow,
    TrackedJourneyRow,
    TransferRow,
    TripRow,
    VehiclePositionRow,
)
from .session import session_scope

#: Bumped whenever the stored schema's meaning changes, so a stale database is
#: rebuilt rather than silently misread.
SCHEMA_VERSION = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunks(items: list[dict], size: int = 5000):  # type: ignore[type-arg]
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _insert_all(session: Session, table, rows: list[dict], chunk: int = 5000) -> None:  # type: ignore[no-untyped-def]
    for part in _chunks(rows, chunk):
        session.execute(insert(table), part)


# ---------------------------------------------------------------------------
# Network -> database
# ---------------------------------------------------------------------------


def network_fingerprint(net: TransportNetwork) -> str:
    """A digest of the feed's contents, used to detect stale databases."""
    digest = hashlib.blake2b(digest_size=16)
    for stop in sorted(net.stops.values(), key=lambda s: s.id):
        digest.update(f"{stop.id}|{stop.name}|{stop.lat:.6f}|{stop.lon:.6f}|".encode())
    for route in sorted(net.routes.values(), key=lambda r: r.id):
        digest.update(
            f"{route.id}|{route.mode.value}|{route.operator_code}|"
            f"{route.short_name}|{route.long_name}|".encode()
        )
    for trip_id in sorted(net.trips):
        for st in net.stop_times.get(trip_id, ()):
            digest.update(
                f"{trip_id}{st.stop_id}{st.arrival_s}{st.departure_s}".encode()
            )
    return digest.hexdigest()[:16]


def _route_regions(net: TransportNetwork) -> dict[str, str]:
    """Attribute each route to the region most of its stops sit in.

    Routes are stored with a region so the API can answer "what runs in Leeds?"
    without walking the whole network.  A corridor's stops are the authority.
    """
    from collections import Counter

    by_route: dict[str, Counter] = {}
    for trip_id, trip in net.trips.items():
        counter = by_route.setdefault(trip.route_id, Counter())
        for st in net.stop_times.get(trip_id, ()):
            stop = net.stops.get(st.stop_id)
            if stop is not None and stop.region:
                counter[stop.region] += 1
    return {
        route_id: counter.most_common(1)[0][0]
        for route_id, counter in by_route.items()
        if counter
    }


def _route_description(net: TransportNetwork, route_id: str, region: str) -> str:
    """A human sentence describing where a route runs, built from its stops."""
    for trip_id, trip in net.trips.items():
        if trip.route_id != route_id:
            continue
        times = net.stop_times.get(trip_id, ())
        if not times:
            continue
        first = net.stops.get(times[0].stop_id)
        last = net.stops.get(times[-1].stop_id)
        if first and last:
            return f"{first.name} to {last.name}"
    return region.title() if region else ""


def _wipe_network(session: Session) -> None:
    # Children before parents: stop_times reference trips and stops, trips
    # reference routes and calendars, fare rules reference fare attributes.
    for table in (
        StopTimeRow,
        TripRow,
        TransferRow,
        RouteRow,
        StopRow,
        CalendarDateRow,
        CalendarRow,
        FareRuleModel,
        FareAttributeRow,
        FeedInfoRow,
    ):
        session.execute(delete(table))


def store_network(session: Session, net: TransportNetwork, fingerprint: str) -> dict:
    """Replace the stored network with ``net`` and return the row counts."""
    _wipe_network(session)

    _insert_all(
        session,
        StopRow,
        [
            {
                "id": s.id,
                "name": s.name,
                "lat": s.lat,
                "lon": s.lon,
                "location": f"SRID=4326;POINT({s.lon} {s.lat})",
                "mode": s.mode.value,
                "atco_code": s.atco_code or None,
                "crs_code": s.crs_code or None,
                "locality_code": s.locality_code or None,
                "region": s.region or "",
                "parent_id": s.parent_id or None,
                "wheelchair_boarding": s.wheelchair_boarding,
                "interchange": bool(s.interchange),
                "source": s.source or "naptan",
            }
            for s in net.stops.values()
        ],
    )

    _store_operators(session, {r.operator_code for r in net.routes.values() if r.operator_code})

    route_regions = _route_regions(net)
    _insert_all(
        session,
        RouteRow,
        [
            {
                "id": r.id,
                "operator_code": r.operator_code or "",
                "mode": r.mode.value,
                "short_name": r.short_name,
                "long_name": r.long_name or "",
                "colour": r.colour or "#4b5563",
                "brand": r.brand or "",
                "region": route_regions.get(r.id, ""),
                "corridor_code": r.id,
                "description": _route_description(net, r.id, route_regions.get(r.id, "")),
            }
            for r in net.routes.values()
        ],
    )

    _insert_all(
        session,
        CalendarRow,
        [
            {
                "id": c.id,
                "days": "".join("1" if day else "0" for day in c.days),
                "start_date": c.start_date,
                "end_date": c.end_date,
            }
            for c in net.calendars.values()
        ],
    )

    _insert_all(
        session,
        CalendarDateRow,
        [
            {
                "service_id": cd.service_id,
                "date": cd.date,
                "exception_type": cd.exception_type,
            }
            for cd in net.calendar_dates
        ],
    )

    _insert_all(
        session,
        TripRow,
        [
            {
                "id": t.id,
                "route_id": t.route_id,
                "service_id": t.service_id,
                "headsign": t.headsign or "",
                "direction": t.direction,
                "wheelchair_accessible": t.wheelchair_accessible,
                "bikes_allowed": t.bikes_allowed,
                "reliability": t.reliability,
            }
            for t in net.trips.values()
        ],
    )

    _insert_all(
        session,
        StopTimeRow,
        [
            {
                "trip_id": trip_id,
                "stop_id": st.stop_id,
                "stop_sequence": st.stop_sequence,
                "arrival_s": st.arrival_s,
                "departure_s": st.departure_s,
                "pickup_type": st.pickup_type,
                "dropoff_type": st.dropoff_type,
                "headsign": st.headsign or "",
                "same_station": bool(st.same_station),
            }
            for trip_id, times in net.stop_times.items()
            for st in times
        ],
        chunk=20000,
    )

    _insert_all(
        session,
        TransferRow,
        [
            {
                "from_stop_id": t.from_stop_id,
                "to_stop_id": t.to_stop_id,
                "transfer_type": t.transfer_type,
                "min_transfer_s": t.min_transfer_s,
                "distance_m": t.distance_m,
                "within_station": bool(t.within_station),
            }
            for t in net.transfers
        ],
    )

    _insert_all(
        session,
        FareAttributeRow,
        [
            {
                "fare_id": f.fare_id,
                "price": f.price,
                "currency_type": f.currency_type,
                "payment_method": f.payment_method,
                "transfers": f.transfers,
                "transfer_duration_s": f.transfer_duration_s,
                "label": f.label or "",
                "product_type": f.product_type,
                "operator_code": f.operator_code or "",
                "offpeak_only": bool(f.offpeak_only),
                "advance_only": bool(f.advance_only),
                "railcard_eligible": bool(f.railcard_eligible),
                "student_eligible": bool(f.student_eligible),
            }
            for f in net.fares.values()
        ],
    )

    if net.fare_rules:
        _insert_all(
            session,
            FareRuleModel,
            [
                {
                    "fare_id": r.fare_id,
                    "route_id": r.route_id or "",
                    "origin_id": r.origin_id or "",
                    "destination_id": r.destination_id or "",
                    "contains_id": r.contains_id or "",
                }
                for r in net.fare_rules
            ],
        )

    _insert_all(
        session,
        FeedInfoRow,
        [
            {
                "publisher": net.feed_info.publisher,
                "publisher_url": net.feed_info.publisher_url or "",
                "lang": net.feed_info.lang or "en",
                "start_date": net.feed_info.start_date,
                "end_date": net.feed_info.end_date,
                "version": f"{net.feed_info.version}|schema{SCHEMA_VERSION}",
                "fingerprint": fingerprint,
                "is_live_feed": False,
                "generated_at": datetime.now(timezone.utc).replace(tzinfo=None),
            }
        ],
    )
    session.flush()
    return count_rows(session)


def _store_operators(session: Session, codes: set[str]) -> None:
    """Insert every operator the routes reference, from the real registry."""
    from ..ingest.registry import get_operator

    rows: list[dict] = []
    for code in sorted(codes):
        op = get_operator(code)
        scheme = getattr(op, "scheme", "") if op else ""
        rows.append(
            {
                "code": code,
                "name": op.name if op else code,
                "mode": op.mode if op else "bus",
                "noc": op.code if op and scheme == "noc" else None,
                "atoc_code": op.code if op and scheme == "atoc" else None,
                "website": (op.url or None) if op else None,
                "colour": op.colour if op else None,
                "source": scheme or "unknown",
            }
        )
    if not rows:
        return
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        session.execute(sqlite_insert(OperatorRow).values(rows).prefix_with("OR REPLACE"))
    else:  # pragma: no cover - Postgres deployment path
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(OperatorRow).values(rows)
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[OperatorRow.code],
                set_={c: stmt.excluded[c] for c in ("name", "mode", "noc", "atoc_code")},
            )
        )


def stored_fingerprint(session: Session) -> tuple[str | None, str | None]:
    """Return ``(fingerprint, version)`` of the stored feed, if any."""
    row = session.execute(
        select(FeedInfoRow.fingerprint, FeedInfoRow.version)
        .order_by(FeedInfoRow.id.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else (None, None)


def network_is_current(session: Session, fingerprint: str) -> bool:
    stored, version = stored_fingerprint(session)
    return bool(
        stored == fingerprint and version and version.endswith(f"|schema{SCHEMA_VERSION}")
    )


# ---------------------------------------------------------------------------
# Database -> network
# ---------------------------------------------------------------------------


def load_network(session: Session) -> TransportNetwork:
    """Rebuild the in-memory network from the database."""
    net = TransportNetwork()

    for row in session.execute(select(StopRow)).scalars():
        net.stops[row.id] = Stop(
            id=row.id,
            name=row.name,
            lat=row.lat,
            lon=row.lon,
            mode=Mode(row.mode),
            atco_code=row.atco_code or "",
            crs_code=row.crs_code or "",
            locality_code=row.locality_code or "",
            region=row.region or "",
            parent_id=row.parent_id or None,
            wheelchair_boarding=row.wheelchair_boarding,
            interchange=bool(row.interchange),
            source=row.source or "",
        )

    for row in session.execute(select(RouteRow)).scalars():
        net.routes[row.id] = Route(
            id=row.id,
            operator_code=row.operator_code or "",
            mode=Mode(row.mode),
            short_name=row.short_name or "",
            long_name=row.long_name or "",
            colour=row.colour or "#4b5563",
            brand=row.brand or "",
        )

    for row in session.execute(select(CalendarRow)).scalars():
        days = tuple(ch == "1" for ch in (row.days or "1111100").ljust(7, "0")[:7])
        net.calendars[row.id] = Calendar(
            id=row.id, days=days, start_date=row.start_date, end_date=row.end_date
        )

    for row in session.execute(select(CalendarDateRow)).scalars():
        net.calendar_dates.append(
            CalendarDate(
                service_id=row.service_id, date=row.date, exception_type=row.exception_type
            )
        )

    for row in session.execute(select(TripRow)).scalars():
        net.trips[row.id] = Trip(
            id=row.id,
            route_id=row.route_id,
            service_id=row.service_id,
            headsign=row.headsign or "",
            direction=row.direction,
            wheelchair_accessible=row.wheelchair_accessible,
            bikes_allowed=row.bikes_allowed,
            reliability=row.reliability,
        )

    for row in session.execute(
        select(StopTimeRow).order_by(StopTimeRow.trip_id, StopTimeRow.stop_sequence)
    ).scalars():
        net.stop_times.setdefault(row.trip_id, []).append(
            StopTime(
                trip_id=row.trip_id,
                stop_id=row.stop_id,
                stop_sequence=row.stop_sequence,
                arrival_s=row.arrival_s,
                departure_s=row.departure_s,
                pickup_type=row.pickup_type,
                dropoff_type=row.dropoff_type,
                headsign=row.headsign or "",
                same_station=bool(row.same_station),
            )
        )

    for row in session.execute(select(TransferRow)).scalars():
        net.transfers.append(
            Transfer(
                from_stop_id=row.from_stop_id,
                to_stop_id=row.to_stop_id,
                transfer_type=row.transfer_type,
                min_transfer_s=row.min_transfer_s,
                distance_m=row.distance_m,
                within_station=bool(row.within_station),
            )
        )

    for row in session.execute(select(FareAttributeRow)).scalars():
        net.fares[row.fare_id] = FareAttribute(
            fare_id=row.fare_id,
            price=row.price,
            currency_type=row.currency_type or "GBP",
            payment_method=row.payment_method,
            transfers=row.transfers,
            transfer_duration_s=row.transfer_duration_s,
            label=row.label or "",
            product_type=row.product_type or "single",
            operator_code=row.operator_code or "",
            offpeak_only=bool(row.offpeak_only),
            advance_only=bool(row.advance_only),
            railcard_eligible=bool(row.railcard_eligible),
            student_eligible=bool(row.student_eligible),
        )

    for row in session.execute(select(FareRuleModel)).scalars():
        net.fare_rules.append(
            FareRuleRow(
                fare_id=row.fare_id,
                route_id=row.route_id or "",
                origin_id=row.origin_id or "",
                destination_id=row.destination_id or "",
                contains_id=row.contains_id or "",
            )
        )

    info = session.execute(
        select(FeedInfoRow).order_by(FeedInfoRow.id.desc()).limit(1)
    ).scalar_one_or_none()
    if info is not None:
        net.feed_info = FeedInfo(
            publisher=info.publisher,
            publisher_url=info.publisher_url or "",
            lang=info.lang or "en",
            start_date=info.start_date,
            end_date=info.end_date,
            version=info.version or "",
        )
    return net


# ---------------------------------------------------------------------------
# Product queries
# ---------------------------------------------------------------------------


def count_rows(session: Session) -> dict[str, int]:
    return {
        "stops": session.scalar(select(func.count()).select_from(StopRow)) or 0,
        "routes": session.scalar(select(func.count()).select_from(RouteRow)) or 0,
        "trips": session.scalar(select(func.count()).select_from(TripRow)) or 0,
        "stop_times": session.scalar(select(func.count()).select_from(StopTimeRow)) or 0,
        "transfers": session.scalar(select(func.count()).select_from(TransferRow)) or 0,
        "fares": session.scalar(select(func.count()).select_from(FareAttributeRow)) or 0,
        "operators": session.scalar(select(func.count()).select_from(OperatorRow)) or 0,
    }


def stops_in_bbox(
    session: Session, *, lat: float, lon: float, radius_deg: float, limit: int = 500
) -> list[StopRow]:
    return list(
        session.execute(
            select(StopRow)
            .where(
                StopRow.lat.between(lat - radius_deg, lat + radius_deg),
                StopRow.lon.between(lon - radius_deg, lon + radius_deg),
            )
            .limit(limit)
        ).scalars()
    )


def bulk_stop_lookup(session: Session, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    rows = session.execute(select(StopRow).where(StopRow.id.in_(ids))).scalars()
    return {
        row.id: {
            "id": row.id,
            "name": row.name,
            "lat": row.lat,
            "lon": row.lon,
            "mode": row.mode,
            "region": row.region,
            "interchange": bool(row.interchange),
        }
        for row in rows
    }


# --- saved journeys -------------------------------------------------------


def list_saved_journeys(session: Session, device_key: str) -> list[SavedJourneyRow]:
    return list(
        session.execute(
            select(SavedJourneyRow)
            .where(SavedJourneyRow.device_key == device_key)
            .order_by(SavedJourneyRow.created_at.desc())
        ).scalars()
    )


def delete_saved_journey(session: Session, device_key: str, journey_id: int) -> bool:
    result = session.execute(
        delete(SavedJourneyRow).where(
            SavedJourneyRow.id == journey_id,
            SavedJourneyRow.device_key == device_key,
        )
    )
    return bool(result.rowcount)


# --- price alerts ---------------------------------------------------------


def list_price_alerts(session: Session, device_key: str) -> list[PriceAlertRow]:
    return list(
        session.execute(
            select(PriceAlertRow)
            .where(PriceAlertRow.device_key == device_key)
            .order_by(PriceAlertRow.created_at.desc())
        ).scalars()
    )


def due_price_alerts(session: Session, limit: int = 25) -> list[PriceAlertRow]:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=6)
    return list(
        session.execute(
            select(PriceAlertRow)
            .where(
                PriceAlertRow.active.is_(True),
                or_(
                    PriceAlertRow.last_checked_at.is_(None),
                    PriceAlertRow.last_checked_at < cutoff,
                ),
            )
            .limit(limit)
        ).scalars()
    )


# --- live -----------------------------------------------------------------


def recent_vehicle_positions(
    session: Session, *, route_ids: list[str] | None = None, limit: int = 200
) -> list[VehiclePositionRow]:
    stmt = select(VehiclePositionRow).order_by(VehiclePositionRow.recorded_at.desc())
    if route_ids:
        stmt = stmt.where(VehiclePositionRow.route_id.in_(route_ids))
    return list(session.execute(stmt.limit(limit)).scalars())


def active_alerts(
    session: Session, *, region: str | None = None, limit: int = 50
) -> list[ServiceAlertRow]:
    rows = list(
        session.execute(select(ServiceAlertRow).limit(limit)).scalars()
    )
    if region:
        rows = [r for r in rows if not r.regions or region in r.regions]
    return rows


def region_of(lat: float, lon: float) -> str:
    """Name the modelled region containing a point, if any."""
    region = region_for_point(lat, lon)
    return region.slug if region else ""


def purge_expired_tracking(session: Session, older_than_hours: int = 12) -> int:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        hours=older_than_hours
    )
    result = session.execute(
        delete(TrackedJourneyRow).where(TrackedJourneyRow.started_at < cutoff)
    )
    return int(result.rowcount or 0)


__all__ = [
    "JourneySearchRow",
    "SCHEMA_VERSION",
    "active_alerts",
    "bulk_stop_lookup",
    "count_rows",
    "delete_saved_journey",
    "due_price_alerts",
    "list_price_alerts",
    "list_saved_journeys",
    "load_network",
    "network_fingerprint",
    "network_is_current",
    "purge_expired_tracking",
    "recent_vehicle_positions",
    "region_of",
    "session_scope",
    "store_network",
    "stored_fingerprint",
]
