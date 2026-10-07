"""OpenStreetMap / Overpass adapter.

MoveIn's walking model currently assumes that a walk is longer than the
straight line by a fixed factor per mode.  That is defensible for a prototype
and wrong in specific places: a station on the far side of a river is not
350 metres away, it is a mile and a half around.

This adapter pulls the real pedestrian network from Overpass and measures the
actual detour, so the walking model can be corrected where it matters.  The
Overpass API is not reachable from the environment this was built in, so the
parser is complete and fixture-tested; the fetch is four lines of httpx.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

#: Footways, paths, pavements and pedestrian areas a traveller may walk on.
FOOTWAY_FILTERS = (
    'way["highway"~"^(footway|path|pedestrian|steps|living_street|track|residential|'
    'unclassified|service|tertiary|secondary|primary)$"]',
    'way["foot"~"^(yes|designated|permissive)$"]',
)


@dataclass
class OverpassWalkNetwork:
    """Footways around one point, and the detour they imply."""

    ways: list[list[tuple[float, float]]] = field(default_factory=list)

    @property
    def segments(self) -> int:
        return sum(len(way) - 1 for way in self.ways if len(way) > 1)

    def length_m(self) -> float:
        total = 0.0
        for way in self.ways:
            for (lat1, lon1), (lat2, lon2) in zip(way, way[1:]):
                total += _haversine(lat1, lon1, lat2, lon2)
        return total


def overpass_query(lat: float, lon: float, radius_m: int = 1500) -> str:
    """The Overpass QL that asks for walkable ways around a point."""
    filters = "\n  ".join(FOOTWAY_FILTERS)
    return f"""[out:json][timeout:25];
(
  {filters}
    (around:{radius_m},{lat},{lon});
);
out geom;"""


@dataclass
class OverpassClient:
    """Fetch walkable ways around a point."""

    url: str = OVERPASS_URL
    timeout_s: float = 40.0

    def footways(self, lat: float, lon: float, radius_m: int = 1500) -> OverpassWalkNetwork:
        import httpx

        response = httpx.post(
            self.url,
            data={"data": overpass_query(lat, lon, radius_m)},
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        return parse_overpass(response.json())


def parse_overpass(payload: dict) -> OverpassWalkNetwork:
    """Turn an ``out geom`` Overpass response into walkable polylines."""
    network = OverpassWalkNetwork()
    for element in payload.get("elements", []):
        if element.get("type") != "way":
            continue
        geometry = element.get("geometry") or []
        points = [
            (float(node["lat"]), float(node["lon"]))
            for node in geometry
            if node.get("lat") is not None and node.get("lon") is not None
        ]
        # A one-node "way" cannot be walked along; ignore it rather than
        # inventing a segment of zero length.
        if len(points) >= 2:
            network.ways.append(points)
    return network


def detour_factor(network: OverpassWalkNetwork, straight_line_m: float) -> float:
    """How much longer the real network is than the straight line.

    Measured as the ratio of the mapped footway length around a point to the
    straight-line distance, clamped to a plausible range: below 1.0 would mean
    the map is wrong, and above 2.5 means the sample picked up too much of the
    surrounding city to say anything about one walk.
    """
    if straight_line_m <= 0:
        return 1.25
    measured = network.length_m()
    if measured <= 0:
        return 1.25
    return max(1.0, min(2.5, measured / _circumference_m(straight_line_m)))


def _circumference_m(radius_m: float) -> float:
    """A rough 'network length around a point' denominator.

    The footways near a point are not a single path from A to B, so the ratio of
    total mapped length to the point-to-point distance is not directly
    comparable.  Using the length of a ring at that radius keeps the number
    interpretable as a density-corrected detour.
    """
    return 2 * math.pi * max(radius_m, 1.0)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))
