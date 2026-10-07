"""Modelled service regions for the Phase 1 network.

MoveIn Phase 1 covers a connected multi-city corridor across the Midlands, the
North of England and London.  Regions are defined as a centre point plus a
radius; every real NaPTAN access point that falls inside one of these discs is
pulled into the bundled seed dataset.

The region set is deliberately shaped as a *network* rather than a pile of
unrelated cities: Nottingham-Derby-Leicester-Birmingham-Coventry is the
headline corridor from the product brief, and Sheffield/Leeds/Manchester/York
plus London extend it to the intercity journeys the platform is built for.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    """A modelled service region: a disc around a city centre."""

    slug: str
    name: str
    lat: float
    lon: float
    radius_m: int
    #: GB National Grid / administrative hint used for locality resolution.
    country: str = "England"

    def bbox(self) -> tuple[float, float, float, float]:
        """Return (min_lat, min_lon, max_lat, max_lon) for cheap pre-filtering."""
        import math

        dlat = self.radius_m / 111_320.0
        dlon = self.radius_m / (111_320.0 * max(math.cos(math.radians(self.lat)), 1e-6))
        return (self.lat - dlat, self.lon - dlon, self.lat + dlat, self.lon + dlon)


#: The Phase 1 modelled network.
#:
#: Radii are sized to enclose the *transport networks* MoveIn models, not just
#: the city centres.  London's disc has to reach Cockfosters, Loughton,
#: Heathrow and Shenfield for the Underground corridors to resolve; Manchester's
#: has to reach Bury, Rochdale and Altrincham for Metrolink, and so on.
REGIONS: tuple[Region, ...] = (
    # --- East Midlands core corridor (the brief's worked example) ---
    Region("nottingham", "Nottingham", 52.9536, -1.1505, 16_000),
    Region("beeston", "Beeston", 52.9250, -1.2160, 6_000),
    Region("long-eaton", "Long Eaton", 52.8960, -1.2740, 6_000),
    Region("derby", "Derby", 52.9227, -1.4746, 13_000),
    Region("loughborough", "Loughborough", 52.7721, -1.2062, 7_000),
    Region("leicester", "Leicester", 52.6369, -1.1398, 14_000),
    Region("grantham", "Grantham", 52.9110, -0.6420, 7_000),
    Region("east-midlands-parkway", "East Midlands Parkway", 52.8625, -1.2632, 6_000),
    # --- East & West Midlands ---
    Region("birmingham", "Birmingham", 52.4862, -1.8904, 20_000),
    Region("coventry", "Coventry", 52.4068, -1.5197, 12_000),
    Region("wolverhampton", "Wolverhampton", 52.5870, -2.1288, 15_000),
    Region("tamworth", "Tamworth", 52.6340, -1.6940, 7_000),
    Region("nuneaton", "Nuneaton", 52.5225, -1.4675, 7_000),
    Region("rugby", "Rugby", 52.3705, -1.2640, 7_000),
    Region("burton-on-trent", "Burton upon Trent", 52.8070, -1.6320, 7_000),
    Region("lichfield", "Lichfield", 52.6820, -1.8260, 7_000),
    # --- South Yorkshire / Yorkshire ---
    Region("sheffield", "Sheffield", 53.3811, -1.4701, 15_000),
    Region("chesterfield", "Chesterfield", 53.2350, -1.4210, 9_000),
    Region("doncaster", "Doncaster", 53.5228, -1.1285, 10_000),
    Region("leeds", "Leeds", 53.8008, -1.5491, 16_000),
    Region("bradford", "Bradford", 53.7960, -1.7594, 10_000),
    Region("wakefield", "Wakefield", 53.6833, -1.4977, 9_000),
    Region("york", "York", 53.9600, -1.0873, 10_000),
    # --- North West ---
    Region("manchester", "Manchester", 53.4808, -2.2426, 18_000),
    Region("stockport", "Stockport", 53.4106, -2.1575, 9_000),
    Region("crewe", "Crewe", 53.0886, -2.4420, 7_000),
    Region("stoke-on-trent", "Stoke-on-Trent", 53.0027, -2.1810, 11_000),
    # --- South East / London ---
    Region("milton-keynes", "Milton Keynes", 52.0406, -0.7594, 9_000),
    Region("peterborough", "Peterborough", 52.5730, -0.2480, 10_000),
    # London's disc spans the whole Underground network, from Heathrow in the
    # west to Shenfield and Loughton in the east.
    Region("london", "London", 51.5074, -0.1278, 32_000),
    # Thames Valley, for the Elizabeth line's western branches.
    Region("slough", "Slough", 51.5110, -0.5900, 10_000),
    Region("reading", "Reading", 51.4584, -0.9719, 9_000),
)

REGIONS_BY_SLUG: dict[str, Region] = {r.slug: r for r in REGIONS}


def all_bboxes() -> tuple[tuple[float, float, float, float], ...]:
    return tuple(r.bbox() for r in REGIONS)


def region_for_point(lat: float, lon: float, *, padding_m: int = 0) -> Region | None:
    """Return the region whose disc contains a point, nearest centre first.

    ``padding_m`` widens every disc, which is useful for attributing stops that
    sit just outside a modelled area (an airport, a park-and-ride) to the city
    they actually serve.
    """
    from ..ingest.geo import haversine_m

    best: tuple[float, Region] | None = None
    for region in REGIONS:
        distance = haversine_m(lat, lon, region.lat, region.lon)
        if distance <= region.radius_m + padding_m:
            if best is None or distance < best[0]:
                best = (distance, region)
    return best[1] if best else None
