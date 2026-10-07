"""UK town names, from the national station register.

MoveIn models a fixed set of city regions, and its stop register only names the
stops inside them.  That is fine for planning and wrong for *understanding*: a
traveller who types "Banbury" means the town in Oxfordshire, and an app that
answers with "BANBURY ROAD, St Nicholas Park" in Coventry has silently swapped
their origin for a street 60 miles away.

This module gives the resolver somewhere honest to look.  Every UK railway
station is in MoveIn's committed register (10,009 of them, with real
coordinates); the towns they are named after are the towns people type.  So:

* "Banbury" -> Banbury, from Banbury Rail Station's own coordinates
* "Milton Keynes" -> a modelled region, which wins first, as it should
* "BANBURY SIGNAL 12" -> not a town, and not included
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Names that are a station, not a town.  The register is full of signalling and
#: engineering entries, and none of them is somewhere a passenger wants to be.
NOT_A_TOWN = (
    "SIGNAL",
    "JUNCTION",
    "DEPOT",
    "SIDINGS",
    "SIDING",
    "YARD",
    "TUNNEL",
    "CROSSOVER",
    "GROUND FRAME",
    "LEVEL CROSSING",
    "MAIN",
    "LOOP",
    # The abbreviations the register actually uses.
    " JN",
    "JN ",
    " SIG",
    "SIG ",
    "SDGS",
    "SGN",
    " GF",
    " LC",
    "TSC",
    "DEAD SLOW",
)

#: How a station name is reduced to the town it serves.
STATION_SUFFIXES = (
    " rail station",
    " railway station",
    " station",
    " (london)",
    " parkway",
    " international",
    " airport",
    " central",
    " interchange",
)


@dataclass(frozen=True)
class Town:
    """A real UK town, with real coordinates."""

    name: str
    lat: float
    lon: float
    #: Which station's coordinates these are, so the answer can be traced.
    source: str = ""


def normalise(name: str) -> str:
    """Lower-case and strip the noise the register leaves in names."""
    return " ".join(name.strip().lower().replace("&", "and").split())


def _is_station_name(name: str) -> bool:
    """A station a passenger could stand at: no signal, no siding, no digits."""
    upper = name.upper()
    if not name or any(character.isdigit() for character in name):
        return False
    return not any(token in upper for token in NOT_A_TOWN)


#: Stations that are one of several in a city: the city is the town.
MIN_STATIONS_FOR_A_CITY = 3


def load_towns(path: Path) -> dict[str, Town]:
    """Every town the station register knows, keyed by normalised name.

    Two passes, because the register names places two ways:

    * a town with one station is the station's name -- "Banbury Rail Station"
      is Banbury;
    * a city with twenty stations names districts, not itself -- "Manchester
      Piccadilly" and "Manchester Victoria" are both Manchester, and the town
      centre is the middle of them, so the city is added with the coordinates
      of the station nearest the centroid of its own stations.
    """
    towns: dict[str, Town] = {}
    stations: list[tuple[str, str, float, float]] = []
    if not path.exists():
        return towns
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("name") or "").strip()
            if not _is_station_name(name):
                continue
            try:
                lat, lon = float(row["lat"]), float(row["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (49.0 < lat < 61.5 and -8.5 < lon < 2.5):
                continue
            lowered = name.lower()
            for suffix in STATION_SUFFIXES:
                if lowered.endswith(suffix):
                    lowered = lowered[: -len(suffix)]
                    break
            town_name = lowered.strip(" ,()")
            if not town_name or len(town_name) < 3:
                continue
            stations.append((name, town_name, lat, lon))
            key = normalise(town_name)
            if key not in towns:
                towns[key] = Town(name=town_name.title(), lat=lat, lon=lon, source=name)

    # Cities: a first word shared by several stations is a city name.
    by_first: dict[str, list[tuple[str, str, float, float]]] = {}
    for entry in stations:
        by_first.setdefault(entry[1].split()[0], []).append(entry)
    for token, group in by_first.items():
        if len(group) < MIN_STATIONS_FOR_A_CITY or token in towns:
            continue
        centre_lat = sum(item[2] for item in group) / len(group)
        centre_lon = sum(item[3] for item in group) / len(group)
        # A shared first word only means a city if the stations are in one
        # place: "Stoke" is not Stoke-on-Trent plus Stoke Gifford, 200 km apart.
        spread = max(
            (item[2] - centre_lat) ** 2 + (item[3] - centre_lon) ** 2 for item in group
        )
        if spread > 0.25**2:  # about 25 km
            continue
        closest = min(
            group,
            key=lambda item: (item[2] - centre_lat) ** 2 + (item[3] - centre_lon) ** 2,
        )
        towns[token] = Town(
            name=token.title(),
            lat=closest[2],
            lon=closest[3],
            source=closest[0],
        )
    return towns


@lru_cache(maxsize=2)
def _cached(path_str: str, mtime: float) -> dict[str, Town]:
    return load_towns(Path(path_str))


def towns(path: Path | None = None) -> dict[str, Town]:
    """The town gazetteer, loaded once per file version."""
    if path is None:
        from ..config import get_settings

        path = get_settings().data_raw_dir / "rail_stations.csv"
    if not path.exists():
        return {}
    return _cached(str(path), path.stat().st_mtime)


#: Words a traveller may add to a town name without changing what they mean.
QUALIFIERS = (" station", " rail", " stn", " railway", " parkway", " centre", " city", " town")


def exact_town(query: str) -> Town | None:
    """A town whose name *is* the query, and nothing looser than that.

    The resolver must never answer "Victoria Centre" with the town of Victoria,
    so this is the only door the engine uses: exact name, nothing fuzzy.
    """
    key = normalise(query)
    if len(key) < 4 or any(character.isdigit() for character in key):
        return None
    return towns().get(key)


def find_town(query: str, *, minimum: int = 4) -> Town | None:
    """The town a query most likely means, or None if nothing fits.

    Exact match first, then a prefix match so "milton keyn" still finds Milton
    Keynes.  A query that carries signalling noise ("BANBURY SIGNAL 12") is
    refused rather than trimmed: guessing there is how a Coventry street once
    became the town of Banbury.
    """
    key = normalise(query)
    if len(key) < minimum:
        return None
    if any(character.isdigit() for character in key):
        return None
    if any(f" {noise.strip().lower()} " in f" {key} " for noise in NOT_A_TOWN):
        return None
    known = towns()
    if not known:
        return None
    exact = known.get(key)
    if exact is not None:
        return exact
    # "banbury station" is Banbury.
    for qualifier in QUALIFIERS:
        if key.endswith(qualifier) and len(key) - len(qualifier) >= minimum:
            stripped = key[: -len(qualifier)]
            if stripped in known:
                return known[stripped]
    # "london" -> the middle of London, "bicester" -> Bicester, "stoke" ->
    # Stoke-On-Trent.  Stations whose name *extends* the query are the query's
    # own places, so long as they are in one part of the country.
    return _from_extensions(key, known)


def _from_extensions(key: str, known: dict[str, Town]) -> Town | None:
    """Make a town out of the stations named after it.

    Cities name their stations after districts ("London Euston", "Manchester
    Piccadilly"), and small towns often have more than one ("Bicester North",
    "Bicester Village").  Both are the query plus a qualifier, so the group's
    centre is the town centre -- provided the group is in one place, which is
    how "Stoke Gifford" stays out of Stoke-on-Trent.
    """
    candidates = [
        (name, town)
        for name, town in known.items()
        if name.startswith(f"{key}-") or name.startswith(f"{key} ")
    ]
    if not candidates:
        # A prefix of exactly one town, for partial typing.
        matches = [town for name, town in known.items() if name.startswith(key)]
        return matches[0] if len(matches) == 1 else None

    # Single-linkage clusters, 30 km apart meaning different places.
    unvisited = list(candidates)
    clusters: list[list[tuple[str, Town]]] = []
    while unvisited:
        seed = unvisited.pop()
        cluster = [seed]
        for other in list(unvisited):
            if any(
                _rough_km(seed[1], member[1]) <= 30.0
                for member in cluster
            ):
                cluster.append(other)
                unvisited.remove(other)
        clusters.append(cluster)

    def preferred(cluster: list[tuple[str, Town]]) -> tuple:
        hyphenated = any(name.startswith(f"{key}-") for name, _ in cluster)
        return (hyphenated, len(cluster), -len(cluster[0][0]))

    best = max(clusters, key=preferred)
    centre_lat = sum(town.lat for _, town in best) / len(best)
    centre_lon = sum(town.lon for _, town in best) / len(best)
    source_name, source_town = min(
        best,
        key=lambda item: (item[1].lat - centre_lat) ** 2 + (item[1].lon - centre_lon) ** 2,
    )
    return Town(
        name=key.title(),
        lat=source_town.lat,
        lon=source_town.lon,
        source=source_town.source or source_name,
    )


def _rough_km(a: Town, b: Town) -> float:
    """Cheap distance in kilometres: good enough for a 30 km question."""
    import math

    dlat = (a.lat - b.lat) * 111.0
    dlon = (a.lon - b.lon) * 111.0 * max(math.cos(math.radians(a.lat)), 1e-6)
    return math.hypot(dlat, dlon)
