"""Geospatial primitives used across MoveIn.

Deliberately dependency-free (no shapely / GEOS) so the engine runs on a plain
Python install.  Everything here operates on WGS84 lat/lon degrees.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def walk_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Estimated *walking* distance between two points.

    NaPTAN coordinates are straight-line; real footpaths detour around
    buildings, rivers and railway lines.  We apply a detour factor derived from
    published pedestrian-network studies (circuity ~1.30 in dense urban areas,
    with a small fixed penalty to account for entering/leaving a site).
    """
    straight = haversine_m(lat1, lon1, lat2, lon2)
    return straight * 1.30 + 15.0


def walk_duration_s(distance_m: float, speed_mps: float = 1.35) -> int:
    """Walking time for a distance, using a default 4.86 km/h pedestrian speed.

    1.35 m/s is the planning-standard average walking speed used for UK
    accessibility modelling.  A short fixed setup time is added so that
    very short hops are not modelled as instantaneous.
    """
    if distance_m <= 0:
        return 0
    return int(round(15.0 + distance_m / speed_mps))


def cycle_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Estimated cycling distance (lower circuity than walking)."""
    return haversine_m(lat1, lon1, lat2, lon2) * 1.15 + 20.0


def cycle_duration_s(distance_m: float, speed_mps: float = 4.2) -> int:
    """Cycling time at a default 15 km/h."""
    if distance_m <= 0:
        return 0
    return int(round(45.0 + distance_m / speed_mps))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, in degrees clockwise from north."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def compass_16(bearing: float) -> str:
    """16-point compass label for a bearing (used for walking instructions)."""
    labels = (
        "north", "north-east", "east", "south-east",
        "south", "south-west", "west", "north-west",
    )
    return labels[int((bearing % 360) / 45.0 + 0.5) % 8]


def relative_direction(bearing: float) -> str:
    """Human instruction for a walking leg ('head north-east')."""
    return f"head {compass_16(bearing)}"


class GridIndex:
    """A lat/lon bucketed spatial index for fast radius queries.

    Buckets are sized in degrees so that a query only touches the cells
    overlapping its bounding box.  This replaces the PostGIS ``ST_DWithin``
    query used in production; the interface is intentionally identical so the
    storage backend can be swapped without touching the engine.
    """

    __slots__ = ("cell_deg", "_cells", "_points")

    def __init__(self, cell_deg: float = 0.01) -> None:
        self.cell_deg = cell_deg
        self._cells: dict[tuple[int, int], list[int]] = {}
        self._points: list[tuple[float, float]] = []

    def _key(self, lat: float, lon: float) -> tuple[int, int]:
        return (int(math.floor(lat / self.cell_deg)), int(math.floor(lon / self.cell_deg)))

    def add(self, lat: float, lon: float) -> int:
        idx = len(self._points)
        self._points.append((lat, lon))
        self._cells.setdefault(self._key(lat, lon), []).append(idx)
        return idx

    def bulk_add(self, points: Iterable[tuple[float, float]]) -> None:
        for lat, lon in points:
            self.add(lat, lon)

    def query_radius(
        self, lat: float, lon: float, radius_m: float, limit: int | None = None
    ) -> list[tuple[int, float]]:
        """Return ``(index, distance_m)`` pairs inside ``radius_m``, nearest first."""
        dlat = radius_m / 111_320.0
        dlon = radius_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
        k0 = self._key(lat - dlat, lon - dlon)
        k1 = self._key(lat + dlat, lon + dlon)

        out: list[tuple[int, float]] = []
        for ci in range(k0[0], k1[0] + 1):
            for cj in range(k0[1], k1[1] + 1):
                for idx in self._cells.get((ci, cj), ()):
                    plat, plon = self._points[idx]
                    d = haversine_m(lat, lon, plat, plon)
                    if d <= radius_m:
                        out.append((idx, d))
        out.sort(key=lambda t: t[1])
        return out[:limit] if limit else out

    def __len__(self) -> int:
        return len(self._points)


def simplify_path(
    points: Sequence[tuple[float, float]], tolerance_m: float = 25.0
) -> list[tuple[float, float]]:
    """Douglas-Peucker simplification sized in metres (for map polylines)."""
    if len(points) < 3:
        return list(points)

    def perp_distance(p, a, b) -> float:
        if a == b:
            return haversine_m(p[0], p[1], a[0], a[1])
        # Project in a local equirectangular frame for simplicity.
        lat0 = math.radians(a[0])
        kx = 111_320.0 * math.cos(lat0)
        ky = 110_540.0
        px, py = (p[1] - a[1]) * kx, (p[0] - a[0]) * ky
        bx, by = (b[1] - a[1]) * kx, (b[0] - a[0]) * ky
        denom = bx * bx + by * by
        t = 0.0 if denom == 0 else max(0.0, min(1.0, (px * bx + py * by) / denom))
        dx, dy = px - t * bx, py - t * by
        return math.hypot(dx, dy)

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi <= lo + 1:
            continue
        max_d, max_i = 0.0, lo
        for i in range(lo + 1, hi):
            d = perp_distance(points[i], points[lo], points[hi])
            if d > max_d:
                max_d, max_i = d, i
        if max_d > tolerance_m:
            keep[max_i] = True
            stack.append((lo, max_i))
            stack.append((max_i, hi))
    return [p for p, k in zip(points, keep) if k]
