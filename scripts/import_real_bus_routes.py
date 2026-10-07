#!/usr/bin/env python3
"""Turn real UK bus route geometries into MoveIn's own route records.

Where the data comes from
-------------------------

Six operator areas of real bus network, traced from the operators' own
TransXChange publications on the DfT Bus Open Data Service, mirrored as GeoJSON
by `ukinteractivebusmap/ukinteractivebusmap.github.io`.  The properties in those
files say so themselves: ``source_file`` names the BODS TransXChange XML each
line came from.

What this script does
---------------------

Two things the GeoJSON does not give us, recovered from data MoveIn already
holds:

1. **Stop sequences.**  A line is geometry, not a timetable.  Every vertex is
   tested against the real NaPTAN register (42,502 named stops, already
   committed) and runs of matches become the ordered stops the service calls at.
   Dense road geometry passes within a few metres of each stop, so this
   recovers the stop sequence the operator published even when the line itself
   has a vertex every five metres.
2. **Simplification.**  A phone cannot draw 195,000 vertices 152 times over, and
   neither should a payload.  Ramer-Douglas-Peucker at a metre-scale tolerance
   keeps the shape on screen and throws away the noise.

Output: one gzipped JSON file that is the network definition -- routes, numbers,
operators, descriptions, matched stop ids and simplified shapes -- plus a stats
file, so the app can say precisely how much of the country it is drawing.

Usage::

    .venv/bin/python scripts/import_real_bus_routes.py [--source DIR] [--tolerance 12]
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_named_stops(path: Path) -> dict[str, tuple[str, float, float]]:
    """The committed NaPTAN named-stop register: ATCO -> (name, lat, lon).

    Read here rather than through the ingest module's GTFS-shaped loader,
    because this file is the register as published: `atco_code,name,lat,lon`.
    """
    import csv

    lookup: dict[str, tuple[str, float, float]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            atco = (row.get("atco_code") or "").strip()
            name = (row.get("name") or "").strip()
            if not atco or not name:
                continue
            try:
                lat, lon = float(row["lat"]), float(row["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if -8.5 < lon < 2.5 and 49.0 < lat < 61.5:
                lookup[atco] = (name, lat, lon)
    return lookup

#: How close a line has to pass a named stop to count as calling at it.  NaPTAN
#: gives a stop's centroid; a road centre-line can be 15-20 m off it in a town.
MATCH_RADIUS_M = 40.0

#: Two matches closer together than this are the same stop, not a new call.
DEDUPE_M = 45.0

#: Ramer-Douglas-Peucker tolerance, in metres.  At phone zoom, 12 m is invisible.
DEFAULT_TOLERANCE_M = 12.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


class StopIndex:
    """Nearest-named-stop lookup over the whole NaPTAN register.

    A grid of 0.01 degree cells (about 1.1 km by 0.7 km) keeps this to a handful
    of candidates per vertex, which matters: the six files carry a quarter of a
    million vertices between them.
    """

    CELL = 0.01

    def __init__(self, lookup: dict[str, tuple[str, float, float]]) -> None:
        self.cells: dict[tuple[int, int], list[tuple[str, str, float, float]]] = defaultdict(list)
        self.count = 0
        for atco, (name, lat, lon) in lookup.items():
            self.cells[self._key(lat, lon)].append((atco, name, lat, lon))
            self.count += 1

    def _key(self, lat: float, lon: float) -> tuple[int, int]:
        return (int(math.floor(lat / self.CELL)), int(math.floor(lon / self.CELL)))

    def nearest(self, lat: float, lon: float, radius_m: float) -> tuple[str, str, float] | None:
        """(atco, name, distance_m) for the closest named stop within radius."""
        best: tuple[str, str, float] | None = None
        span = max(1, math.ceil(radius_m / (self.CELL * 111_320.0)))
        base = self._key(lat, lon)
        for dlat in range(-span, span + 1):
            for dlon in range(-span, span + 1):
                for atco, name, stop_lat, stop_lon in self.cells.get(
                    (base[0] + dlat, base[1] + dlon), ()
                ):
                    distance = haversine_m(lat, lon, stop_lat, stop_lon)
                    if distance <= radius_m and (best is None or distance < best[2]):
                        best = (atco, name, distance)
        return best


def simplify(points: list[tuple[float, float]], tolerance_m: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker, iteratively (no recursion: these lines are long)."""
    if len(points) <= 2:
        return list(points)
    degrees = tolerance_m / 111_320.0
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        ax, ay = points[start]
        bx, by = points[end]
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        farthest, farthest_distance = -1, -1.0
        for index in range(start + 1, end):
            px, py = points[index]
            if length_sq == 0:
                distance = math.hypot(px - ax, py - ay)
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
                distance = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if distance > farthest_distance:
                farthest, farthest_distance = index, distance
        if farthest_distance > degrees:
            keep[farthest] = True
            stack.append((start, farthest))
            stack.append((farthest, end))
    return [point for point, kept in zip(points, keep) if kept]


def stops_along(points: list[tuple[float, float]], index: StopIndex) -> list[dict]:
    """The named stops a line passes, in order, without repeating neighbours."""
    sequence: list[dict] = []
    for lat, lon in points:
        hit = index.nearest(lat, lon, MATCH_RADIUS_M)
        if not hit:
            continue
        atco, name, distance = hit
        if sequence:
            if sequence[-1]["atco"] == atco:
                # Same stop, another vertex beside it -- keep the closest sample.
                if distance < sequence[-1]["distance_m"]:
                    sequence[-1].update(lat=lat, lon=lon, distance_m=distance, name=name)
                continue
            previous = sequence[-1]
            if haversine_m(previous["lat"], previous["lon"], lat, lon) < DEDUPE_M:
                continue
        sequence.append(
            {
                "atco": atco,
                "name": name,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "distance_m": round(distance, 1),
            }
        )
    return sequence


def load_sources(source_dir: Path) -> list[tuple[Path, dict]]:
    files = sorted(source_dir.glob("*.geojson"))
    if not files:
        raise SystemExit(
            f"no .geojson in {source_dir} -- run scripts/fetch_real_bus_routes.py first"
        )
    loaded = []
    for path in files:
        data = json.loads(path.read_text())
        loaded.append((path, data))
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "backend/data/raw/real_bus_routes",
        help="directory holding the operator GeoJSON files",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "backend/data/raw/real_bus_routes/compiled.json.gz",
    )
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_M)
    args = parser.parse_args()

    lookup = load_named_stops(ROOT / "backend/data/raw/naptan_named_stops.csv")
    index = StopIndex(lookup)
    print(f"NaPTAN: {index.count:,} named stops indexed")

    routes: list[dict] = []
    seen_shapes: set[tuple] = set()
    stats: dict = {
        "sources": [],
        "routes": 0,
        "routes_with_stops": 0,
        "lines": 0,
        "vertices_in": 0,
        "vertices_out": 0,
        "stops_matched": 0,
        "unique_stops": 0,
        "operators": {},
        "tolerance_m": args.tolerance,
        "match_radius_m": MATCH_RADIUS_M,
    }
    unique_stops: set[str] = set()

    for path, data in load_sources(args.source):
        features = data.get("features", [])
        kept = 0
        for number, feature in enumerate(features):
            geometry = feature.get("geometry") or {}
            if geometry.get("type") != "LineString":
                continue
            raw = [(float(lat), float(lon)) for lon, lat in geometry["coordinates"]]
            if len(raw) < 2:
                continue
            props = feature.get("properties") or {}
            stops = stops_along(raw, index)
            # A bus route with fewer than two named stops is a fragment of
            # another route's geometry, not a service.
            if len(stops) < 2:
                continue
            shape = simplify(raw, args.tolerance)
            operator = props.get("operator") or props.get("agency") or "Unknown operator"
            # A BODS file publishes one line per *variation*: both directions,
            # evening loops, school-day branches.  They share a service code but
            # they are different lines on the ground, so each keeps its own id
            # and the service code is carried alongside for grouping.
            service = str(
                props.get("service_code")
                or f"{props.get('agency_id', 'OP')}:{props.get('route_id') or number}"
            )
            route = {
                "id": f"{service}~{number + 1}",
                "service": service,
                "number": str(props.get("route") or "").strip(),
                "operator": operator,
                "description": (props.get("description") or props.get("route_name") or "").strip(),
                "source": props.get("source_file") or props.get("geometry_source") or "",
                "stops": [
                    {"atco": stop["atco"], "name": stop["name"], "lat": stop["lat"], "lon": stop["lon"]}
                    for stop in stops
                ],
                "shape": [[round(lat, 5), round(lon, 5)] for lat, lon in shape],
            }
            # The same line is sometimes published twice; draw it once.
            fingerprint = (
                route["number"],
                route["operator"],
                route["description"],
                tuple(stop["atco"] for stop in route["stops"]),
            )
            if fingerprint in seen_shapes:
                continue
            seen_shapes.add(fingerprint)
            routes.append(route)
            kept += 1
            stats["vertices_in"] += len(raw)
            stats["vertices_out"] += len(shape)
            stats["stops_matched"] += len(stops)
            unique_stops.update(stop["atco"] for stop in stops)
            stats["operators"][operator] = stats["operators"].get(operator, 0) + 1

        stats["lines"] += len(features)
        stats["sources"].append(
            {
                "file": path.name,
                "lines": len(features),
                "routes_kept": kept,
                "operator": (features[0].get("properties") or {}).get("operator")
                or (features[0].get("properties") or {}).get("agency")
                if features
                else None,
            }
        )
        print(f"{path.name:44} {len(features):5} lines -> {kept:5} routes with named stops")

    routes.sort(key=lambda route: (route["operator"], route["number"], route["id"]))
    stats["routes"] = len(routes)
    stats["services"] = len({route["service"] for route in routes})
    stats["routes_with_stops"] = len(routes)
    stats["unique_stops"] = len(unique_stops)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 1,
        "generated_by": "scripts/import_real_bus_routes.py",
        "attribution": (
            "Route geometry derived from operator TransXChange publications on the "
            "DfT Bus Open Data Service (Open Government Licence v3.0); stop names and "
            "coordinates from NaPTAN (DfT, OGL v3.0)."
        ),
        "routes": routes,
    }
    with gzip.open(args.out, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), ensure_ascii=False)

    stats_path = args.out.with_name("compiled_stats.json")
    stats_path.write_text(json.dumps(stats, indent=2) + "\n")

    size_mb = args.out.stat().st_size / 1_048_576
    print()
    print(f"routes:            {stats['routes']:,} variations of {stats['services']:,} services")
    print(f"named stops used:  {stats['unique_stops']:,}")
    print(f"stop calls:        {stats['stops_matched']:,}")
    print(f"vertices:          {stats['vertices_in']:,} -> {stats['vertices_out']:,}")
    print(f"operators:         {len(stats['operators'])}")
    print(f"wrote {args.out.relative_to(ROOT)} ({size_mb:.1f} MB gzipped)")
    print(f"wrote {stats_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
