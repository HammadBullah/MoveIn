"""GTFS schedule reader and writer.

GTFS (General Transit Feed Specification) is MoveIn's internal interchange
format, as set out in the project brief.  Anything that can be expressed as
GTFS -- a bus operator's TransXChange export, a national rail CIF feed, a tram
system's open data -- can be loaded through :func:`read_gtfs` and is then
indistinguishable to the journey engine from any other source.

The writer emits a spec-conformant feed including the fare extension tables,
so the compiled Phase 1 network can be handed to any third-party GTFS consumer
(OpenTripPlanner, MobilityData validators, Google Transit) for verification.
"""

from __future__ import annotations

import csv
import gzip
import io
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import IO, Iterable, Iterator, TextIO

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
    gtfs_time_to_seconds,
    seconds_to_gtfs_time,
)

# --------------------------------------------------------------------------
# Low-level CSV helpers
# --------------------------------------------------------------------------


def _open_text(path: Path | str) -> TextIO:
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return open(path, encoding="utf-8-sig", newline="")


def _rows(path: Path) -> Iterator[dict[str, str]]:
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield {(k or "").strip(): (v or "").strip() for k, v in row.items()}


def _int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "y")


def _gtfs_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value or len(value) != 8:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def _fmt_date(value: date | None) -> str:
    return value.strftime("%Y%m%d") if value else ""


# --------------------------------------------------------------------------
# Reader
# --------------------------------------------------------------------------


def read_gtfs(source: Path | str | IO[bytes], *, name: str = "") -> TransportNetwork:
    """Read a GTFS feed from a directory or a ``.zip`` archive.

    Unknown columns are ignored and missing optional files are tolerated, which
    is what real-world feeds require -- published feeds routinely omit
    ``transfers.txt`` or carry extra vendor columns.
    """
    source = Path(source) if not hasattr(source, "read") else source
    if isinstance(source, Path) and source.is_dir():
        return _read_directory(source)
    if isinstance(source, Path) and source.suffix == ".zip":
        with zipfile.ZipFile(source) as zf:
            return _read_zip(zf)
    if hasattr(source, "read"):
        with zipfile.ZipFile(source) as zf:  # type: ignore[arg-type]
            return _read_zip(zf)
    raise ValueError(f"{source!r} is neither a directory nor a GTFS zip")


class _FeedFiles:
    """Uniform access to files inside a GTFS directory or zip archive."""

    def __init__(self) -> None:
        self._inner: dict[str, bytes] = {}
        self._dir: Path | None = None

    def add_bytes(self, filename: str, payload: bytes) -> None:
        self._inner[filename] = payload

    def set_dir(self, path: Path) -> None:
        self._dir = path

    def has(self, filename: str) -> bool:
        if filename in self._inner:
            return True
        return self._dir is not None and (self._dir / filename).exists()

    def rows(self, filename: str) -> Iterator[dict[str, str]]:
        if filename in self._inner:
            text = self._inner[filename].decode("utf-8-sig")
            yield from _dict_rows(io.StringIO(text))
            return
        if self._dir is not None and (self._dir / filename).exists():
            yield from _rows(self._dir / filename)


def _dict_rows(fh) -> Iterator[dict[str, str]]:
    for row in csv.DictReader(fh):
        yield {(k or "").strip(): (v or "").strip() for k, v in row.items() if k}


def _read_zip(zf: zipfile.ZipFile) -> TransportNetwork:
    files = _FeedFiles()
    for info in zf.infolist():
        base = Path(info.filename).name
        if info.is_dir() or not base.endswith(".txt"):
            continue
        files.add_bytes(base, zf.read(info))
    return _build_network(files)


def _read_directory(path: Path) -> TransportNetwork:
    files = _FeedFiles()
    files.set_dir(path)
    return _build_network(files)


def _build_network(files: _FeedFiles) -> TransportNetwork:
    net = TransportNetwork()

    # --- feed_info ---------------------------------------------------------
    if files.has("feed_info.txt"):
        for row in files.rows("feed_info.txt"):
            net.feed_info = FeedInfo(
                publisher=row.get("feed_publisher_name", ""),
                publisher_url=row.get("feed_publisher_url", ""),
                lang=row.get("feed_lang", "en"),
                start_date=_gtfs_date(row.get("feed_start_date", "")),
                end_date=_gtfs_date(row.get("feed_end_date", "")),
                version=row.get("feed_version", ""),
            )
            break

    # --- stops -------------------------------------------------------------
    if files.has("stops.txt"):
        for row in files.rows("stops.txt"):
            sid = row.get("stop_id", "")
            if not sid:
                continue
            location_type = _int(row.get("location_type", "0"))
            net.stops[sid] = Stop(
                id=sid,
                name=row.get("stop_name", "") or sid,
                lat=_float(row.get("stop_lat", "0")),
                lon=_float(row.get("stop_lon", "0")),
                mode=(
                    Mode(row["movein_mode"])
                    if row.get("movein_mode")
                    else (Mode.RAIL if location_type == 1 else Mode.BUS)
                ),
                atco_code=row.get("movein_atco_code") or row.get("stop_code", ""),
                crs_code=row.get("movein_crs_code", ""),
                locality_code=row.get("movein_locality_code", ""),
                region=row.get("movein_region", ""),
                parent_id=row.get("parent_station", "") or None,
                wheelchair_boarding=_int(row.get("wheelchair_boarding", "0")),
                interchange=location_type == 1,
                source=row.get("movein_source") or "gtfs",
            )

    # --- routes ------------------------------------------------------------
    route_meta: dict[str, dict[str, str]] = {}
    if files.has("routes.txt"):
        for row in files.rows("routes.txt"):
            rid = row.get("route_id", "")
            if not rid:
                continue
            # A MoveIn feed states the mode explicitly; a third-party feed only
            # has the GTFS route type, which the reader falls back to.
            declared = (row.get("movein_mode") or "").strip()
            if declared:
                try:
                    mode = Mode(declared)
                except ValueError:
                    mode = Mode.from_gtfs(_int(row.get("route_type", "3"), 3))
            else:
                mode = Mode.from_gtfs(_int(row.get("route_type", "3"), 3))
            net.routes[rid] = Route(
                id=rid,
                operator_code=row.get("agency_id", ""),
                mode=mode,
                short_name=row.get("route_short_name", ""),
                long_name=row.get("route_long_name", ""),
                colour=row.get("route_color", "") or "#4b5563",
                brand=row.get("movein_brand", "") or "",
            )
            route_meta[rid] = row

    # --- calendar ----------------------------------------------------------
    if files.has("calendar.txt"):
        for row in files.rows("calendar.txt"):
            sid = row.get("service_id", "")
            if not sid:
                continue
            net.calendars[sid] = Calendar(
                id=sid,
                days=tuple(
                    _bool(row.get(day, "0"))
                    for day in (
                        "monday", "tuesday", "wednesday", "thursday",
                        "friday", "saturday", "sunday",
                    )
                ),
                start_date=_gtfs_date(row.get("start_date", "")),
                end_date=_gtfs_date(row.get("end_date", "")),
            )

    if files.has("calendar_dates.txt"):
        for row in files.rows("calendar_dates.txt"):
            d = _gtfs_date(row.get("date", ""))
            sid = row.get("service_id", "")
            if d and sid:
                net.calendar_dates.append(
                    CalendarDate(sid, d, _int(row.get("exception_type", "1"), 1))
                )

    # --- trips -------------------------------------------------------------
    if files.has("trips.txt"):
        for row in files.rows("trips.txt"):
            tid = row.get("trip_id", "")
            if not tid:
                continue
            net.trips[tid] = Trip(
                id=tid,
                route_id=row.get("route_id", ""),
                service_id=row.get("service_id", ""),
                headsign=row.get("trip_headsign", ""),
                direction=_int(row.get("direction_id", "0")),
                wheelchair_accessible=_int(row.get("wheelchair_accessible", "0")),
                bikes_allowed=_int(row.get("bikes_allowed", "0")),
                reliability=_float(row.get("movein_reliability", "0.92"), 0.92),
            )

    # --- stop_times --------------------------------------------------------
    if files.has("stop_times.txt"):
        for row in files.rows("stop_times.txt"):
            tid = row.get("trip_id", "")
            sid = row.get("stop_id", "")
            if not tid or not sid:
                continue
            try:
                arrival = gtfs_time_to_seconds(row.get("arrival_time", "") or "00:00:00")
                departure = gtfs_time_to_seconds(
                    row.get("departure_time", "") or row.get("arrival_time", "") or "00:00:00"
                )
            except ValueError:
                continue
            net.stop_times.setdefault(tid, []).append(
                StopTime(
                    trip_id=tid,
                    stop_id=sid,
                    stop_sequence=_int(row.get("stop_sequence", "0")),
                    arrival_s=arrival,
                    departure_s=departure,
                    pickup_type=_int(row.get("pickup_type", "0")),
                    dropoff_type=_int(row.get("dropoff_type", "0")),
                    headsign=row.get("stop_headsign", ""),
                    same_station=_bool(row.get("movein_same_station", "0")),
                )
            )

    # --- transfers ---------------------------------------------------------
    if files.has("transfers.txt"):
        for row in files.rows("transfers.txt"):
            frm, to = row.get("from_stop_id", ""), row.get("to_stop_id", "")
            if not frm or not to:
                continue
            net.transfers.append(
                Transfer(
                    from_stop_id=frm,
                    to_stop_id=to,
                    transfer_type=_int(row.get("transfer_type", "2"), 2),
                    min_transfer_s=_int(row.get("min_transfer_time", "120"), 120),
                    distance_m=_float(
                        row.get("movein_distance_m") or row.get("distance_m", "0")
                    ),
                    within_station=_bool(row.get("movein_within_station", "0")),
                )
            )

    # --- fares -------------------------------------------------------------
    if files.has("fare_attributes.txt"):
        for row in files.rows("fare_attributes.txt"):
            fid = row.get("fare_id", "")
            if not fid:
                continue
            net.fares[fid] = FareAttribute(
                fare_id=fid,
                price=_float(row.get("price", "0")),
                currency_type=row.get("currency_type", "GBP"),
                payment_method=_int(row.get("payment_method", "0")),
                transfers=(
                    _int(row["transfers"]) if row.get("transfers", "") != "" else None
                ),
                transfer_duration_s=(
                    _int(row["transfer_duration"])
                    if row.get("transfer_duration", "") != ""
                    else None
                ),
                label=row.get("fare_label", ""),
                product_type=row.get("product_type", "single") or "single",
                operator_code=row.get("operator_code", ""),
                offpeak_only=_bool(row.get("offpeak_only", "0")),
                advance_only=_bool(row.get("advance_only", "0")),
                railcard_eligible=_bool(row.get("railcard_eligible", "0")),
                student_eligible=_bool(row.get("student_eligible", "0")),
            )

    if files.has("fare_rules.txt"):
        for row in files.rows("fare_rules.txt"):
            fid = row.get("fare_id", "")
            if fid:
                net.fare_rules.append(
                    FareRuleRow(
                        fare_id=fid,
                        route_id=row.get("route_id", ""),
                        origin_id=row.get("origin_id", ""),
                        destination_id=row.get("destination_id", ""),
                        contains_id=row.get("contains_id", ""),
                    )
                )

    # --- indices -----------------------------------------------------------
    for tid, times in net.stop_times.items():
        times.sort(key=lambda st: st.stop_sequence)

    return net


# --------------------------------------------------------------------------
# Writer
# --------------------------------------------------------------------------

#: Column order for each table, matching the GTFS reference.
_TABLE_HEADERS: dict[str, list[str]] = {
    "agency.txt": [
        "agency_id", "agency_name", "agency_url", "agency_timezone",
        "agency_lang", "agency_phone",
    ],
    "stops.txt": [
        "stop_id", "stop_code", "stop_name", "stop_lat", "stop_lon",
        "location_type", "parent_station", "wheelchair_boarding", "stop_timezone",
        # MoveIn extensions.  Unknown columns are ignored by other GTFS
        # consumers, which is what lets this feed stay a strict superset.
        "movein_mode", "movein_region", "movein_source",
        "movein_crs_code", "movein_atco_code", "movein_locality_code",
    ],
    "routes.txt": [
        "route_id", "agency_id", "route_short_name", "route_long_name",
        "route_type", "route_color", "route_text_color", "route_desc",
        "movein_brand", "movein_mode",
    ],
    "trips.txt": [
        "route_id", "service_id", "trip_id", "trip_headsign", "direction_id",
        "wheelchair_accessible", "bikes_allowed", "movein_reliability",
    ],
    "stop_times.txt": [
        "trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence",
        "pickup_type", "dropoff_type", "stop_headsign", "timepoint",
        "movein_same_station",
    ],
    "calendar.txt": [
        "service_id", "monday", "tuesday", "wednesday", "thursday", "friday",
        "saturday", "sunday", "start_date", "end_date",
    ],
    "calendar_dates.txt": ["service_id", "date", "exception_type"],
    "transfers.txt": [
        "from_stop_id", "to_stop_id", "transfer_type", "min_transfer_time",
        "movein_distance_m", "movein_within_station",
    ],
    "fare_attributes.txt": [
        "fare_id", "price", "currency_type", "payment_method", "transfers",
        "transfer_duration", "agency_id",
        "fare_label", "product_type", "operator_code",
        "offpeak_only", "advance_only", "railcard_eligible", "student_eligible",
    ],
    "fare_rules.txt": [
        "fare_id", "route_id", "origin_id", "destination_id", "contains_id",
    ],
    "feed_info.txt": [
        "feed_publisher_name", "feed_publisher_url", "feed_lang",
        "feed_start_date", "feed_end_date", "feed_version",
    ],
}


class GtfsWriter:
    """Writes a :class:`TransportNetwork` out as a spec-conformant GTFS feed."""

    def __init__(self, net: TransportNetwork) -> None:
        self.net = net
        self._agency_ids: set[str] = set()

    # -- table builders ----------------------------------------------------
    def _agency_rows(self, agencies: Iterable[dict[str, str]]) -> list[list[str]]:
        rows: list[list[str]] = []
        for a in agencies:
            self._agency_ids.add(a["agency_id"])
            rows.append(
                [
                    a["agency_id"], a["agency_name"], a.get("agency_url", ""),
                    a.get("agency_timezone", "Europe/London"), a.get("agency_lang", "en"),
                    a.get("agency_phone", ""),
                ]
            )
        return rows

    def _stop_rows(self) -> list[list[str]]:
        rows = []
        for stop in sorted(self.net.stops.values(), key=lambda s: s.id):
            rows.append([
                stop.id,
                stop.crs_code or stop.atco_code,
                stop.name,
                f"{stop.lat:.6f}",
                f"{stop.lon:.6f}",
                "1" if stop.interchange else "0",
                stop.parent_id or "",
                str(stop.wheelchair_boarding),
                "Europe/London",
                stop.mode.value,
                stop.region or "",
                stop.source or "",
                stop.crs_code or "",
                stop.atco_code or "",
                stop.locality_code or "",
            ])
        return rows

    def _route_rows(self) -> list[list[str]]:
        rows = []
        for route in sorted(self.net.routes.values(), key=lambda r: r.id):
            rows.append([
                route.id,
                route.operator_code,
                route.short_name,
                route.long_name,
                str(route.mode.gtfs_route_type),
                route.colour.lstrip("#").upper(),
                "FFFFFF",
                "",
                getattr(route, "brand", "") or "",
                route.mode.value,
            ])
        return rows

    def _trip_rows(self) -> list[list[str]]:
        rows = []
        for trip in sorted(self.net.trips.values(), key=lambda t: t.id):
            rows.append([
                trip.route_id, trip.service_id, trip.id, trip.headsign,
                str(trip.direction), str(trip.wheelchair_accessible),
                str(trip.bikes_allowed), f"{trip.reliability:.4f}",
            ])
        return rows

    def _stop_time_rows(self) -> list[list[str]]:
        rows = []
        for tid in sorted(self.net.stop_times):
            for st in self.net.stop_times[tid]:
                rows.append([
                    st.trip_id,
                    seconds_to_gtfs_time(st.arrival_s),
                    seconds_to_gtfs_time(st.departure_s),
                    st.stop_id,
                    str(st.stop_sequence),
                    str(st.pickup_type),
                    str(st.dropoff_type),
                    st.headsign,
                    "1",
                    "1" if st.same_station else "0",
                ])
        return rows

    def _calendar_rows(self) -> list[list[str]]:
        rows = []
        for cal in sorted(self.net.calendars.values(), key=lambda c: c.id):
            rows.append(
                [cal.id]
                + ["1" if d else "0" for d in cal.days]
                + [_fmt_date(cal.start_date), _fmt_date(cal.end_date)]
            )
        return rows

    def _calendar_date_rows(self) -> list[list[str]]:
        return [
            [cd.service_id, _fmt_date(cd.date), str(cd.exception_type)]
            for cd in sorted(self.net.calendar_dates, key=lambda c: (c.service_id, c.date))
        ]

    def _transfer_rows(self) -> list[list[str]]:
        return [
            [
                t.from_stop_id, t.to_stop_id, str(t.transfer_type),
                str(t.min_transfer_s),
                f"{t.distance_m:.1f}",
                "1" if t.within_station else "0",
            ]
            for t in self.net.transfers
        ]

    def _fare_attribute_rows(self) -> list[list[str]]:
        rows = []
        for fare in sorted(self.net.fares.values(), key=lambda f: f.fare_id):
            rows.append([
                fare.fare_id,
                f"{fare.price:.2f}",
                fare.currency_type,
                str(fare.payment_method),
                "" if fare.transfers is None else str(fare.transfers),
                "" if fare.transfer_duration_s is None else str(fare.transfer_duration_s),
                fare.operator_code,
                fare.label,
                fare.product_type,
                fare.operator_code,
                "1" if fare.offpeak_only else "0",
                "1" if fare.advance_only else "0",
                "1" if fare.railcard_eligible else "0",
                "1" if fare.student_eligible else "0",
            ])
        return rows

    def _fare_rule_rows(self) -> list[list[str]]:
        return [
            [fr.fare_id, fr.route_id, fr.origin_id, fr.destination_id, fr.contains_id]
            for fr in self.net.fare_rules
        ]

    def _feed_info_rows(self) -> list[list[str]]:
        fi = self.net.feed_info
        return [[
            fi.publisher, fi.publisher_url, fi.lang,
            _fmt_date(fi.start_date), _fmt_date(fi.end_date), fi.version,
        ]]

    # -- drivers -----------------------------------------------------------
    def write_directory(
        self, out_dir: Path, *, agencies: Iterable[dict[str, str]] = ()
    ) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        agencies = list(agencies) or [{
            "agency_id": "MOVEIN",
            "agency_name": "MoveIn compiled network",
            "agency_url": "https://github.com/HammadBullah/MoveIn",
            "agency_timezone": "Europe/London",
            "agency_lang": "en",
        }]
        tables = {
            "agency.txt": self._agency_rows(agencies),
            "stops.txt": self._stop_rows(),
            "routes.txt": self._route_rows(),
            "trips.txt": self._trip_rows(),
            "stop_times.txt": self._stop_time_rows(),
            "calendar.txt": self._calendar_rows(),
            "calendar_dates.txt": self._calendar_date_rows(),
            "transfers.txt": self._transfer_rows(),
            "fare_attributes.txt": self._fare_attribute_rows(),
            "fare_rules.txt": self._fare_rule_rows(),
            "feed_info.txt": self._feed_info_rows(),
        }
        for filename, rows in tables.items():
            with (out_dir / filename).open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh, lineterminator="\n")
                writer.writerow(_TABLE_HEADERS[filename])
                writer.writerows(rows)
        return out_dir

    def write_zip(
        self, out_path: Path, *, agencies: Iterable[dict[str, str]] = ()
    ) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.write_directory(Path(tmp), agencies=agencies)
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in sorted(Path(tmp).iterdir()):
                    zf.write(file, file.name)
        return out_path


def write_gtfs(
    net: TransportNetwork, out_path: Path, *, agencies: Iterable[dict[str, str]] = ()
) -> Path:
    """Write ``net`` to a directory or ``.zip`` depending on the suffix."""
    writer = GtfsWriter(net)
    out_path = Path(out_path)
    if out_path.suffix == ".zip":
        return writer.write_zip(out_path, agencies=agencies)
    return writer.write_directory(out_path, agencies=agencies)


def validate_gtfs(path: Path) -> list[str]:
    """Lightweight structural validation of a written feed.

    Checks referential integrity across tables -- the class of error that makes
    a feed unusable in a consumer even though every individual file parses.
    """
    problems: list[str] = []
    path = Path(path)

    # Materialise every table up front.  A zip file must stay open to be read,
    # so a lazy reader closure would break as soon as the `with` block exits.
    tables: dict[str, list[dict[str, str]]] = {}
    wanted = (
        "stops.txt", "routes.txt", "trips.txt", "stop_times.txt",
        "fare_attributes.txt", "fare_rules.txt",
    )
    if path.is_dir():
        for name in wanted:
            target = path / name
            tables[name] = list(_rows(target)) if target.exists() else []
    else:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            for name in wanted:
                if name not in names:
                    tables[name] = []
                    continue
                text = zf.read(name).decode("utf-8-sig")
                tables[name] = list(_dict_rows(io.StringIO(text)))

    def open_rows(name: str) -> list[dict[str, str]]:
        return tables.get(name, [])

    stops = {r["stop_id"] for r in open_rows("stops.txt")}
    routes = {r["route_id"] for r in open_rows("routes.txt")}
    trips = open_rows("trips.txt")
    stop_times = open_rows("stop_times.txt")
    fares = {r["fare_id"] for r in open_rows("fare_attributes.txt")}

    trip_ids = {r["trip_id"] for r in trips}
    for row in trips:
        if row["route_id"] not in routes:
            problems.append(f"trips.txt: unknown route_id {row['route_id']!r}")

    seen_seq: dict[str, list[int]] = defaultdict(list)
    for row in stop_times:
        if row["trip_id"] not in trip_ids:
            problems.append(f"stop_times.txt: unknown trip_id {row['trip_id']!r}")
        if row["stop_id"] not in stops:
            problems.append(f"stop_times.txt: unknown stop_id {row['stop_id']!r}")
        seen_seq[row["trip_id"]].append(_int(row["stop_sequence"]))
        for col in ("arrival_time", "departure_time"):
            try:
                gtfs_time_to_seconds(row[col])
            except ValueError:
                problems.append(f"stop_times.txt: bad {col} {row[col]!r}")

    for tid, seqs in seen_seq.items():
        if seqs != sorted(seqs):
            problems.append(f"stop_times.txt: stop_sequence not increasing for trip {tid!r}")
    if not stop_times:
        problems.append("stop_times.txt: no service times at all")
    if not trips:
        problems.append("trips.txt: no trips")
    for row in open_rows("fare_rules.txt"):
        if row["fare_id"] not in fares:
            problems.append(f"fare_rules.txt: unknown fare_id {row['fare_id']!r}")

    # GTFS requires trips to be time-monotonic within a stop_sequence run.
    return problems
