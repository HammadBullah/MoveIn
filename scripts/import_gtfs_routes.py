#!/usr/bin/env python3
"""Compile real GTFS bus data into MoveIn's real bus network.

Input: whatever `scripts/fetch_bods_gtfs.py` unpacked (or any GTFS directory),
the national 'all-GB' GTFS from BODS, or a mix.

Output: `backend/data/raw/real_bus_routes/compiled_bods.json.gz`, in exactly the
schema the app already reads -- route number, operator, description, the ordered
stops the service calls at, and the shape it drives.  The loader picks up every
`compiled*.json.gz` in that directory, so this file *adds* to whatever is there
instead of replacing it.

One line per route per direction.  GTFS publishes hundreds of trips per route;
a passenger needs one honest answer to "where does this bus go", so the compiler
picks the longest trip in each direction as the canonical line and records how
many trips ran it, which is real evidence of frequency without pretending to be
a timetable.

Usage::

    python scripts/import_gtfs_routes.py                     # everything fetched
    python scripts/import_gtfs_routes.py --source /path/to/gtfs
    python scripts/import_gtfs_routes.py --tolerance 20 --out .../compiled_bods.json.gz

Stop sequences come from `stop_times.txt`; shapes come from `shapes.txt` when
the feed has one, and fall back to the stops themselves when it does not.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class _Tee:
    """A stream that writes to the terminal and to the run's report file."""

    def __init__(self, stream, handle):
        self.stream = stream
        self.handle = handle

    def write(self, text: str) -> int:
        self.stream.write(text)
        self.handle.write(text)
        self.handle.flush()
        return len(text)

    def flush(self) -> None:
        self.stream.flush()
        self.handle.flush()

    def isatty(self) -> bool:
        return False


def start_report(explicit: str | None = None) -> None:
    """Tee this run's log into a file, when one was asked for.

    A compile that happens on a GitHub runner has to leave its log in the
    repository: that is the only channel back to where the work is read.
    """
    for candidate in (explicit, os.environ.get("MOVEIN_BODS_REPORT"), os.environ.get("REPORT")):
        if not candidate:
            continue
        path = Path(candidate)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a", encoding="utf-8")
        sys.stdout = _Tee(sys.stdout, handle)  # type: ignore[assignment]
        sys.stderr = _Tee(sys.stderr, handle)  # type: ignore[assignment]
        print(f"\n--- compile report opened {datetime.now(timezone.utc).isoformat(timespec='seconds')} ---")
        return
sys.path.insert(0, str(ROOT))

from backend.app.domain.real_bus import simplify_line  # noqa: E402

DEFAULT_SOURCE = ROOT / "backend/data/raw/bods"
DEFAULT_OUT = ROOT / "backend/data/raw/real_bus_routes/compiled_bods.json.gz"

#: A route with fewer named stops than this is a fragment, not a service.
MIN_STOPS = 2

#: Shapes are simplified to 12 m, which is invisible at any zoom a phone uses.
DEFAULT_TOLERANCE_M = 12.0


#: A GTFS table is either a file on disk or a member inside a published zip.
Member = Path | tuple[Path, str]


class _ZipMember:
    """A table inside a zip, opened as text -- without unpacking the zip.

    The national file is 1.7 GB zipped and 11 GB unpacked, which is more disk
    than a runner comfortably has; reading the members where they lie removes
    that ceiling entirely.
    """

    def __init__(self, archive: Path, name: str) -> None:
        self.archive = archive
        self.name = name
        self._zip: zipfile.ZipFile | None = None

    def __enter__(self):
        self._zip = zipfile.ZipFile(self.archive)
        raw = self._zip.open(self.name)
        return io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")

    def __exit__(self, *exc) -> None:
        if self._zip is not None:
            self._zip.close()


def _open_text(member: Member):
    """GTFS files in the wild are UTF-8, UTF-8 with a BOM, or Windows-1252."""
    if isinstance(member, tuple):
        return _ZipMember(*member)
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            handle = member.open(newline="", encoding=encoding)
            handle.readline()
            handle.seek(0)
            return handle
        except UnicodeDecodeError:
            continue
    return member.open(newline="", encoding="utf-8", errors="replace")


def describe(path) -> str:
    """A path for a person to read: relative when it is inside the repo."""
    if isinstance(path, tuple):
        return f"{describe(path[0])}::{path[1]}"
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


WANTED_TABLES = {
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
    "shapes.txt",
    "agency.txt",
}


def gtfs_files(source: Path) -> dict[str, list[Member]]:
    """Every GTFS table in a directory or a published zip, keyed by table name."""
    found: dict[str, list[Member]] = defaultdict(list)
    if source.is_file() and source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            for name in sorted(archive.namelist()):
                leaf = name.rsplit("/", 1)[-1]
                if leaf in WANTED_TABLES and not name.endswith("/"):
                    found[leaf].append((source, name))
        return found
    for path in sorted(source.rglob("*.txt")):
        if path.name in WANTED_TABLES:
            found[path.name].append(path)
    return found


def read_table(paths: list[Member], needed: tuple[str, ...]):
    """Stream rows from one or more files of the same table, keeping `needed`."""
    for path in paths:
        with _open_text(path) as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                yield {key: (row.get(key) or "").strip() for key in needed}


def load_stops(paths: list[Member]) -> dict[str, dict]:
    """stop_id -> {atco, name, lat, lon} for every stop the feed names.

    The feed's own `stop_id` is kept as the stop's identity.  It matters: a stop
    *name* is shared across the country -- there is a Bus Station in most towns
    -- so keying stops by name would make "routes passing this point" answer
    with every route that calls at any stop of that name anywhere in Britain.
    """
    stops: dict[str, dict] = {}
    for row in read_table(
        paths, ("stop_id", "stop_name", "stop_lat", "stop_lon", "location_type")
    ):
        if not row["stop_id"] or not row["stop_name"]:
            continue
        if row.get("location_type") in {"2", "3", "4"}:  # entrances, nodes, boarding areas
            continue
        try:
            lat, lon = float(row["stop_lat"]), float(row["stop_lon"])
        except ValueError:
            continue
        if not (49.0 < lat < 61.5 and -8.5 < lon < 2.5):
            continue
        stops[row["stop_id"]] = {
            "atco": row["stop_id"],
            "name": row["stop_name"],
            "lat": lat,
            "lon": lon,
        }
    return stops


def route_type_is_bus(value: str) -> bool:
    """GTFS route types 3 (bus), 11 (trolleybus), 200-209 (coach) are road vehicles."""
    try:
        code = int(float(value or "3"))
    except ValueError:
        return True
    return code == 3 or code == 11 or 200 <= code <= 209


def compile_gtfs(
    source: Path,
    *,
    tolerance_m: float,
    out: Path,
    agency_names: dict[str, str],
    prefix: str = "",
    region: str = "",
):
    files = gtfs_files(source)
    if not files.get("trips.txt") or not files.get("stop_times.txt"):
        raise SystemExit(
            f"no GTFS under {source}: expected at least trips.txt and stop_times.txt.\n"
            "Fetch some with scripts/fetch_bods_gtfs.py."
        )

    print("Reading stops...")
    stops = load_stops(files["stops.txt"])
    print(f"  {len(stops):,} named stops")

    print("Reading routes...")
    routes: dict[str, dict] = {}
    for row in read_table(
        files["routes.txt"],
        ("route_id", "route_short_name", "route_long_name", "agency_id", "route_type"),
    ):
        if not row["route_id"] or not route_type_is_bus(row["route_type"]):
            continue
        routes[row["route_id"]] = {
            "number": row["route_short_name"] or row["route_long_name"],
            "description": row["route_long_name"] if row["route_short_name"] else "",
            "agency_id": row["agency_id"],
        }
    print(f"  {len(routes):,} bus routes")

    # One trip per route per direction: the longest, decided after stop_times is
    # read, so collect candidate trips first and count them as we go.
    print("Reading trips...")
    candidates: dict[tuple[str, str], list[str]] = defaultdict(list)
    trips_per_route: dict[str, int] = defaultdict(int)
    trip_shape: dict[str, str] = {}
    for row in read_table(files["trips.txt"], ("route_id", "trip_id", "direction_id", "shape_id")):
        if row["route_id"] not in routes or not row["trip_id"]:
            continue
        direction = row["direction_id"] or "0"
        candidates[(row["route_id"], direction)].append(row["trip_id"])
        trips_per_route[row["route_id"]] += 1
        if row["shape_id"]:
            trip_shape[row["trip_id"]] = row["shape_id"]
    wanted_trips = {
        trip for trips in candidates.values() for trip in _sample(trips)
    }
    print(f"  {sum(trips_per_route.values()):,} trips; reading stop_times for {len(wanted_trips):,}")

    print("Reading stop_times...")
    sequences: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for row in read_table(
        files["stop_times.txt"], ("trip_id", "stop_id", "stop_sequence", "departure_time")
    ):
        if row["trip_id"] not in wanted_trips or row["stop_id"] not in stops:
            continue
        try:
            sequence = int(float(row["stop_sequence"] or 0))
        except ValueError:
            sequence = 0
        sequences[row["trip_id"]].append(
            (sequence, row["stop_id"], _clock(row["departure_time"]))
        )

    print("Reading shapes...")
    shapes: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in read_table(files["shapes.txt"], ("shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence")):
        try:
            lat, lon = float(row["shape_pt_lat"]), float(row["shape_pt_lon"])
            order = int(float(row["shape_pt_sequence"] or 0))
        except ValueError:
            continue
        shapes[row["shape_id"]].append((order, lat, lon))

    compiled: list[dict] = []
    # Two directions of one route are two different lines on the ground, so the
    # direction is part of the identity -- only genuine duplicates are dropped.
    seen: set[tuple] = set()
    for (route_id, direction), trip_ids in sorted(candidates.items()):
        route = routes[route_id]
        best: tuple[int, str, list[dict], list[str]] | None = None
        for trip_id in trip_ids:
            sequence = sorted(sequences.get(trip_id, ()))
            called = [stops[stop_id] for _, stop_id, _ in sequence]
            if len(called) < MIN_STOPS:
                continue
            if best is None or len(called) > best[0]:
                best = (len(called), trip_id, called, [time for _, _, time in sequence])
        if best is None:
            continue
        _, trip_id, called, times = best
        shape = [
            (lat, lon)
            for _, lat, lon in sorted(shapes.get(trip_shape.get(trip_id, ""), []))
        ]
        if len(shape) < MIN_STOPS:
            shape = [(stop["lat"], stop["lon"]) for stop in called]
        shape = simplify_line(shape, tolerance_m)

        fingerprint = (
            route["number"],
            route["agency_id"],
            direction,
            tuple(stop["name"] for stop in called),
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)

        agency = route["agency_id"] or "unknown"
        compiled.append(
            {
                "id": f"{prefix}{route_id}~{direction}",
                "service": route_id,
                "number": route["number"],
                "operator": agency_names.get(agency, agency),
                "description": route["description"],
                "source": f"GTFS route {route_id} direction {direction}",
                "stops": [
                    {
                        "atco": stop["atco"],
                        "name": stop["name"],
                        "lat": round(stop["lat"], 5),
                        "lon": round(stop["lon"], 5),
                        "time": times[index] if index < len(times) else "",
                    }
                    for index, stop in enumerate(called)
                ],
                "has_times": any(times),
                "sample_trip": trip_id,
                "shape": [[round(lat, 5), round(lon, 5)] for lat, lon in shape],
                "trips": trips_per_route[route_id],
            }
        )

    compiled.sort(key=lambda item: (item["operator"], item["number"], item["id"]))
    payload = {
        "schema": 1,
        "generated_by": "scripts/import_gtfs_routes.py",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "attribution": (
            "Bus routes, stops and shapes from operator TransXChange/GTFS data "
            "published on the DfT Bus Open Data Service (Open Government Licence v3.0)."
        ),
        "region": region or source.name,
        "routes": compiled,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), ensure_ascii=False)
    size_mb = out.stat().st_size / 1_048_576
    print()
    print(f"routes:     {len(compiled):,}")
    print(f"operators:  {len({route['operator'] for route in compiled})}")
    print(f"stops:      {len({stop['atco'] for route in compiled for stop in route['stops']}):,}")
    print(f"wrote {describe(out)} ({size_mb:.1f} MB gzipped)")


def _clock(value: str) -> str:
    """GTFS times are HH:MM:SS, and run past midnight as 24:15:00.

    A passenger reads a clock, not a service day, so the hour wraps: the 00:15
    departure of a Friday night service is published as 24:15 and shown as
    00:15, which is what the timetable on the bus stop says.
    """
    if not value:
        return ""
    parts = value.strip().split(":")
    if len(parts) < 2:
        return ""
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return ""
    return f"{(hour % 24):02d}:{minute:02d}"


def _sample(trip_ids: list[str], limit: int = 60) -> list[str]:
    """A spread of trips to measure, rather than the first 60 in file order.

    File order groups trips by service pattern, so a straight slice can measure
    one branch and miss the trunk.  Evenly spaced sampling sees the whole day.
    """
    if len(trip_ids) <= limit:
        return trip_ids
    step = len(trip_ids) / limit
    return [trip_ids[int(index * step)] for index in range(limit)]


def load_agencies(paths: list[Member]) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in read_table(paths, ("agency_id", "agency_name")):
        if row["agency_name"]:
            names[row["agency_id"] or "unknown"] = row["agency_name"]
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_M)
    parser.add_argument(
        "--prefix",
        default="",
        help="Short region tag for route ids, so feeds can be merged without colliding",
    )
    parser.add_argument("--region", default="", help="Human name of the feed being compiled")
    parser.add_argument(
        "--report",
        default=None,
        help="Also write this run's log here (else $MOVEIN_BODS_REPORT or $REPORT)",
    )
    args = parser.parse_args()

    start_report(args.report)

    if not args.source.exists():
        raise SystemExit(
            f"{args.source} does not exist.  Fetch some data first:\n"
            "  MOVEIN_BODS_API_KEY=... python scripts/fetch_bods_gtfs.py --area Nottingham"
        )
    print(f"Compiling GTFS from {describe(args.source)}")
    agency_names = load_agencies(gtfs_files(args.source).get("agency.txt", []))
    compile_gtfs(
        args.source,
        tolerance_m=args.tolerance,
        out=args.out,
        agency_names=agency_names,
        prefix=(args.prefix + ":" if args.prefix else ""),
        region=args.region,
    )


if __name__ == "__main__":
    main()
