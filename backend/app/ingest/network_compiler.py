"""Compiles the Phase 1 network onto real UK geography.

The compiler takes real stop geography (NaPTAN named stops and Network Rail
TIPLOCs) plus the real service corridors in :mod:`app.domain.network_spec` and
produces a complete, internally consistent transport network:

* a :class:`~app.domain.models.TransportNetwork` for the journey engine
* a spec-conformant GTFS feed for interoperability
* a compact JSON index the API serves directly

Running times are *derived*, not invented: every inter-stop duration comes from
the real great-circle distance between two real stop coordinates, divided by a
per-mode commercial speed from the corridor's service pattern.  Change the
geography and the timetables change with it.

Departure times are compiled deterministically from a seeded generator, because
the authoritative timetables live in feeds the build environment cannot reach
(see ``docs/DATA_SOURCES.md``).  Re-running the compiler with the same seed
always produces byte-identical output.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from ..config import get_settings
from ..domain.models import (
    Calendar,
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
    uk_today,
)
from ..domain.network_spec import (
    ALL_CORRIDORS,
    STOP_ALIASES,
    Corridor,
    FareRule,
    ServicePattern,
)
from ..domain.regions import REGIONS, REGIONS_BY_SLUG
from . import naptan
from .geo import GridIndex, haversine_m, walk_distance_m, walk_duration_s
from .registry import get_operator

#: Seed for the deterministic departure generator.  Changing it changes the
#: compiled timetable but never its statistical shape.
COMPILE_SEED = 20250311

#: Days spanned by the compiled calendar.
#: The compiled timetable covers a rolling window: a month of history so
#: yesterday's journeys still plan, and eleven months forward so "next summer"
#: does too.  A timetable feed is inherently time-bound, so the window is
#: computed when the feed is compiled rather than pinned to a date.
SERVICE_WINDOW_BACK_DAYS = 30
SERVICE_WINDOW_FORWARD_DAYS = 335


def _service_window(today: date | None = None) -> tuple[date, date]:
    today = today or uk_today()
    # Snap to a Monday so the weekday/weekend service split lines up cleanly.
    start = today - timedelta(days=SERVICE_WINDOW_BACK_DAYS)
    start -= timedelta(days=start.weekday())
    return start, start + timedelta(days=SERVICE_WINDOW_BACK_DAYS + SERVICE_WINDOW_FORWARD_DAYS)


SERVICE_START, SERVICE_END = _service_window()

#: Peak windows, in seconds after midnight.
PEAK_WINDOWS = ((7 * 3600, 9 * 3600 + 1800), (16 * 3600, 18 * 3600 + 1800))


def _uk_bank_holidays(start: date, end: date) -> tuple[date, ...]:
    """England & Wales bank holidays inside a window, to the standard rules.

    New Year's Day, Good Friday, Easter Monday, the early May and spring bank
    holidays, the summer bank holiday, Christmas Day and Boxing Day -- plus the
    substitute days when those fall on a weekend.
    """
    import calendar as _calendar

    out: set[date] = set()

    def substitute(day: date) -> date:
        if day.weekday() == 5:
            return day + timedelta(days=2)
        if day.weekday() == 6:
            return day + timedelta(days=1)
        return day

    for year in range(start.year, end.year + 1):
        easter = _easter_sunday(year)
        days = [
            date(year, 1, 1),
            easter - timedelta(days=2),  # Good Friday
            easter + timedelta(days=1),  # Easter Monday
            _first_weekday(year, 5, 0),  # early May
            _last_weekday(year, 5, 0),  # spring
            _last_weekday(year, 8, 0),  # summer
            date(year, 12, 25),
            date(year, 12, 26),
        ]
        for day in days:
            fixed = substitute(day)
            if start <= fixed <= end:
                out.add(fixed)
            if day == date(year, 12, 26) and day.weekday() >= 5:
                pass
    return tuple(sorted(out))


def _first_weekday(year: int, month: int, weekday: int) -> date:
    day = date(year, month, 1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


def _last_weekday(year: int, month: int, weekday: int) -> date:
    import calendar as _calendar

    last = date(year, month, _calendar.monthrange(year, month)[1])
    while last.weekday() != weekday:
        last -= timedelta(days=1)
    return last


def _easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


BANK_HOLIDAYS: tuple[date, ...] = _uk_bank_holidays(SERVICE_START, SERVICE_END)


def _clock(value: str) -> int:
    """Parse ``HH:MM`` into seconds after midnight."""
    hh, mm = value.split(":")
    return int(hh) * 3600 + int(mm) * 60


def _is_peak(seconds: int) -> bool:
    return any(lo <= seconds < hi for lo, hi in PEAK_WINDOWS)


def _slug(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


@dataclass
class CompiledNetwork:
    """Result of a compile run."""

    network: TransportNetwork
    #: stop_id -> {corridors it appears on}
    stop_corridors: dict[str, set[str]] = field(default_factory=dict)
    #: corridor code -> {trip ids by direction}
    corridor_trips: dict[str, list[str]] = field(default_factory=dict)
    #: human-readable notes about the compile
    warnings: list[str] = field(default_factory=list)
    #: statistics for the manifest
    stats: dict[str, object] = field(default_factory=dict)


# ==========================================================================
# Stop resolution
# ==========================================================================


class StopResolver:
    """Resolves real stop references to :class:`Stop` records.

    The reference grammar is deliberately tiny:

    * ``R:NOT`` -- CRS code of a real railway station
    * ``N:Victoria Centre`` -- a real NaPTAN stop name
    """

    def __init__(self, raw_dir: Path) -> None:
        self.raw_dir = raw_dir
        self.stops: dict[str, Stop] = {}
        self._by_crs: dict[str, str] = {}
        #: Matching key -> the stop ids that answer to it.  A name can exist in
        #: several cities and one stop area answers to several published labels.
        self.keys: dict[str, set[str]] = {}
        self._by_name: dict[str, list[str]] = {}
        self._name_index: list[tuple[str, str]] = []
        self._missing: set[str] = set()
        self._load_rail_stations()
        self._load_named_stops()
        # Sorted so that the compiled network does not depend on dict order:
        # the same seed must always produce the same timetable.
        for key in sorted(self.keys):
            sids = sorted(self.keys[key])
            self._by_name[key] = sids
            self._name_index.extend((key, sid) for sid in sids)

    # -- loading -----------------------------------------------------------
    def _load_rail_stations(self) -> None:
        path = self.raw_dir / "rail_stations.csv"
        if not path.exists():
            return
        import csv

        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                crs = (row.get("crs") or "").strip()
                name = (row.get("name") or "").strip()
                if not crs or not name or crs == "NA":
                    continue
                try:
                    lon = float(row["lon"])
                    lat = float(row["lat"])
                except (KeyError, TypeError, ValueError):
                    continue
                # Skip non-station timing points that have no CRS.
                clean = name.replace(" Rail Station", "").strip()
                sid = f"rail:{crs}"
                if sid in self.stops:
                    continue
                self.stops[sid] = Stop(
                    id=sid,
                    name=display_stop_name(clean),
                    lat=lat,
                    lon=lon,
                    mode=Mode.RAIL,
                    crs_code=crs,
                    interchange=True,
                    source="rail_tiploc",
                    region=naptan.region_for_point(lat, lon) or "",
                )
                self._by_crs[crs.upper()] = sid

    def _load_named_stops(self) -> None:
        """Group the real NaPTAN named stops into stop areas.

        NaPTAN publishes one node per physical bay; passengers think in terms of
        a *stop area* -- all the bays outside Victoria Centre are "Victoria
        Centre".  Grouping by name within a modelled region reproduces the
        downstream behaviour operators publish in TransXchange.

        Nodes are grouped by the name a *passenger* would use, not the published
        node label, so ``Kings Cross St Pancras-Entrance-1`` and
        ``...-Entrance-9`` become one stop at the station rather than nine stops
        a few metres apart.  The published labels are still what the mode of the
        area is inferred from, because "Underground" only appears in them.
        """
        path = self.raw_dir / "naptan_named_stops.csv"
        if not path.exists():
            return
        import csv

        #: (region, passenger-facing name) -> the nodes behind that stop area.
        groups: dict[tuple[str, str], list[tuple[float, float, str, str]]] = {}
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                name = (row.get("name") or "").strip()
                if not name:
                    continue
                try:
                    lat = float(row["lat"])
                    lon = float(row["lon"])
                except (KeyError, TypeError, ValueError):
                    continue
                region = naptan.region_for_point(lat, lon)
                if region is None:
                    continue
                clean = display_stop_name(_normalise_stop_name(name))
                # "COLMORE ROW Aa>Ae, Birmingham" is a Birmingham stop; the town
                # suffix only repeats what the region already says.
                locality = (REGIONS_BY_SLUG.get(region).name if region in REGIONS_BY_SLUG else "")
                if locality and clean.lower().endswith(f", {locality.lower()}"):
                    clean = clean[: -len(locality) - 2].strip(" ,-")
                    clean = _title_case_if_shouting(clean)
                if not clean:
                    continue
                groups.setdefault((region, clean), []).append(
                    (lat, lon, row.get("atco_code", ""), name)
                )

        for (region, name), members in groups.items():
            lat = sum(m[0] for m in members) / len(members)
            lon = sum(m[1] for m in members) / len(members)
            sid = f"naptan:{region}:{_slug(name)}"
            self.stops[sid] = Stop(
                id=sid,
                name=name,
                lat=lat,
                lon=lon,
                mode=_infer_mode(" ".join(m[3] for m in members), members),
                atco_code=members[0][2],
                region=region,
                interchange=len(members) >= 4,
                wheelchair_boarding=1,
                source="naptan",
            )
            # A stop area answers to its passenger-facing name and to every
            # published node label behind it, so a corridor may reference either.
            for label in {name, *(m[3] for m in members)}:
                key = _name_key(label)
                if key:
                    self.keys.setdefault(key, set()).add(sid)

    # -- resolution --------------------------------------------------------
    def resolve(
        self, ref: str, regions: tuple[str, ...] = (), mode: Mode | None = None
    ) -> Stop | None:
        """Resolve a stop reference, preferring stops in ``regions``.

        Corridors carry a region hint because UK stop names collide constantly
        -- there is a Victoria in London, Manchester and Preston, a Cathedral in
        Sheffield and Cardiff, and a Moorgate in the City and in Liverpool.  The
        hint makes resolution deterministic instead of relying on whichever
        match happened to come first.
        """
        if ref.startswith("R:"):
            return self._resolve_rail(ref[2:])
        if ref.startswith("N:"):
            return self._resolve_named(ref[2:], regions, mode)
        return None

    def _resolve_rail(self, code: str) -> Stop | None:
        sid = self._by_crs.get(code.strip().upper())
        return self.stops.get(sid) if sid else None

    def _pick(
        self,
        candidates: list[tuple[int, str]],
        regions: tuple[str, ...],
        mode: Mode | None = None,
    ) -> str | None:
        """Choose the best candidate stop.

        Ranking order, most significant first:

        1. **match quality** -- exact beats prefix beats substring, so a
           precise name is never beaten by a loose one;
        2. **mode agreement** -- a Piccadilly line corridor should resolve
           ``Stratford`` to the Underground station, not to the ``Stratford
           Way`` bus stop that happens to share the prefix;
        3. **modelled region**, in the corridor's own order;
        4. **name brevity** -- the plainer name is the one passengers use.
        """
        if not candidates:
            return None
        ranked = {slug: i for i, slug in enumerate(regions)}
        transit = {Mode.RAIL, Mode.METRO, Mode.TRAM, Mode.BUS, Mode.COACH, Mode.FERRY}
        #: Modes that call at stations rather than at kerbsides.
        guideway = {Mode.RAIL, Mode.METRO, Mode.TRAM, Mode.FERRY}

        def sort_key(item: tuple[int, str]) -> tuple[int, int, int, int, int, int]:
            quality, sid = item
            stop = self.stops[sid]
            if mode is None:
                mode_rank = 0
            elif stop.mode == mode:
                mode_rank = 0
            elif stop.mode in transit:
                mode_rank = 1
            else:
                mode_rank = 2
            # A tube corridor asking for "Hammersmith" must get the station, not
            # the bus stop called "Hammersmith Road" that happens to sit nearer
            # the name.  Station-ness is therefore decided before match quality
            # -- but only for modes that actually have stations, so a bus
            # corridor keeps preferring the exact kerbside match.
            station_rank = 0
            if mode in guideway:
                station_rank = 0 if _STATION_MARKER_RE.search(stop.name) else 1
            unmodelled = 0 if stop.region else 1
            region_rank = ranked.get(stop.region, len(ranked))
            return (
                station_rank, quality, mode_rank, unmodelled, region_rank,
                len(stop.name),
            )

        best_quality, best = min(candidates, key=sort_key)
        if regions and self.stops[best].region not in ranked:
            # Nothing matched inside the corridor's geography; fall back to the
            # best-quality candidate that is at least in a modelled region.
            in_region = [
                (q, sid) for q, sid in candidates if self.stops[sid].region in ranked
            ]
            if in_region:
                return min(in_region, key=sort_key)[1]
        return best

    def _resolve_named(
        self, name: str, regions: tuple[str, ...] = (), mode: Mode | None = None
    ) -> Stop | None:
        # Canonical names that differ from the published NaPTAN spelling.
        alias = STOP_ALIASES.get(name.strip())
        if alias:
            name = alias

        wanted = _name_key(name)

        # Collect every candidate with a match-quality score:
        #   0 exact      "Old Market Square" -> "Old Market Square"
        #   1 prefix     "Hucknall"          -> "Hucknall Tram"
        #   2 substring  "Kings Cross St Pancras" -> "...St.Pancras-Entrance-9"
        scored: list[tuple[int, str]] = []
        padded = f" {wanted} "
        for candidate, csid in self._name_index:
            if candidate == wanted:
                scored.append((0, csid))
            elif candidate.startswith(wanted) and (
                len(candidate) == len(wanted) or not candidate[len(wanted)].isalpha()
            ):
                scored.append((1, csid))
            elif padded in f" {candidate} ":
                scored.append((2, csid))

        sid = self._pick(scored, regions, mode)
        if sid:
            return self.stops[sid]

        # Last resort, region-restricted: match on the first significant token,
        # but only when it is unambiguous inside the corridor's geography.
        if regions:
            toks = [
                t for t in wanted.replace(",", " ").replace(".", " ").split()
                if len(t) > 3
            ]
            for token in toks:
                hits = [
                    csid
                    for candidate, csid in self._name_index
                    if candidate.startswith(token)
                    and self.stops[csid].region in regions
                ]
                if len(hits) == 1:
                    return self.stops[hits[0]]
        return None

    def resolve_near(
        self,
        ref: str,
        lat: float,
        lon: float,
        max_km: float,
        regions: tuple[str, ...] = (),
        mode: Mode | None = None,
    ) -> Stop | None:
        """Resolve a reference, rejecting matches implausibly far from ``lat/lon``.

        Without this guard a fuzzy name match can silently place a stop at the
        wrong end of the country -- "Loughton" (Essex) matching "Cloughton"
        (North Yorkshire).  Corridors are resolved left to right and each stop
        is checked against the previously resolved one.
        """
        stop = self.resolve(ref, regions, mode)
        if stop is None:
            return None
        if haversine_m(lat, lon, stop.lat, stop.lon) > max_km * 1000:
            return None
        return stop

    def add_derived_stop(
        self, stop_id: str, name: str, lat: float, lon: float, mode: Mode
    ) -> Stop:
        """Create a stop that is not present in NaPTAN (e.g. a taxi rank point)."""
        stop = Stop(
            id=stop_id, name=name, lat=lat, lon=lon, mode=mode,
            source="derived",
            region=naptan.region_for_point(lat, lon) or "",
        )
        self.stops[stop_id] = stop
        return stop


def _name_key(name: str) -> str:
    """The key a stop name is *matched* on.

    NaPTAN writes "St John's Wood" where a corridor may write "St Johns Wood",
    and a reference may carry the node suffix the published label has
    ("Tottenham Court Road-Entrance-4").  Matching ignores case, apostrophes and
    the other punctuation that varies between the two, while the name shown to
    the traveller keeps its published spelling.
    """
    out = _normalise_stop_name(name).lower().replace("&", " and ")
    out = re.sub(r"[^a-z0-9]+", " ", out)
    return " ".join(out.split())


def _normalise_stop_name(name: str) -> str:
    """Strip NaPTAN's real-time-ish and traveline suffixes from a stop name."""
    out = name
    for suffix in (
        " (Travelling )", "(Travelling )", " (Travelling)", "(Travelling)",
        " (Manchester Metrolink)", "(Nottingham Express Transit)",
        " (Sheffield Supertram)", " (West Midlands Metro)",
        " Rail Station", " Rail Station (Entrance)",
    ):
        out = out.replace(suffix, "")
    return " ".join(out.split()).strip(" ,")


#: Names that identify a station rather than a kerbside stop.
_STATION_MARKER_RE = re.compile(
    r"\b(?:underground|tube|overground|station|railway|tram(?:stop)?|"
    r"metrolink|supertram|dlr|metro|interchange|platform)\b",
    re.IGNORECASE,
)


#: Regexes that strip NaPTAN node-suffixes which are meaningless to a passenger.
_NODE_SUFFIX_RE = re.compile(
    r"\s*[-,]?\s*(?:"
    r"Entrance(?:[\s-]*\d+)?|Underground(?:[\s-]*\d+)?|Rail Station Entrance|"
    r"(?:DLR|Overground|Tram|Metrolink)(?:[\s-]*\d+)?|"
    r"Underground Station|Railway Station|Rail Station|"
    r"Train Station Entrance|Station Entrance|"
    r"(?:platform|stand|stop|bay)[\s-]*[A-Z0-9]+"
    r")\s*$",
    re.IGNORECASE,
)
_TRAILING_NUM_RE = re.compile(r"[,\s]+[A-Z0-9]{1,3}$")


#: Bay ranges in a NaPTAN label: "COLMORE ROW Aa>Ae" is one kerbside.
_BAY_RANGE_RE = re.compile(r"\b[A-Za-z]{1,2}>[A-Za-z]{1,2}\b")
#: A trailing bay group after the word a passenger looks for.
_BAY_LETTERS_RE = re.compile(
    r"(\b(?:Station|Stop|Terminus|Interchange|Platform))\s+[A-Z]{1,2}"
    r"(?:\s+[A-Z]{1,2})*$"
)
#: Initials and road numbers: "PH" is a place, not the start of a word.
_INITIALS_RE = re.compile(r"^(?:[A-Z]{1,3}|M\d+|A\d+)$")
_PARTICLES = {"On", "In", "Under", "Upon", "By", "Near", "Le", "La", "De", "And"}


def _title_case_if_shouting(name: str) -> str:
    """Give an all-capitals NaPTAN label the casing a passenger would type.

    "BULL STREET" is how NaPTAN publishes it and "Bull Street" is how everyone
    reads it.  Initials and road numbers are left alone, so "TWM Garage" and
    "M1 JCT 24" survive, and hyphenated particles stay lowercase, so
    "ASCOTT-UNDER-WYCHWOOD" becomes "Ascott-under-Wychwood".
    """
    letters = [c for c in name if c.isalpha()]
    if not letters or any(c.islower() for c in letters):
        return name

    particles = "|".join(sorted(_PARTICLES))

    def fix(word: str) -> str:
        fixed = re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), word)
        return re.sub(rf"-{particles}\b", lambda m: m.group(0).lower(), fixed)

    return " ".join(
        word if _looks_like_initials(word) else fix(word) for word in name.split()
    )


def _looks_like_initials(word: str) -> bool:
    """True for "PH", "JN", "M1" and "A52" -- strings that are not words."""
    if not word.isalpha():
        return bool(re.fullmatch(r"(?:[A-Z]?\d+[A-Z]?)+", word))
    return word.isupper() and not any(vowel in word for vowel in "AEIOU")


def display_stop_name(name: str) -> str:
    """Turn a NaPTAN node label into the name a passenger would recognise.

    NaPTAN enumerates individual nodes -- ``Baker Street-Underground-4``,
    ``Kings Cross St.Pancras-Entrance-9`` -- where a passenger thinks in terms
    of the station, and publishes bays and kerbsides as ``COLMORE ROW Aa>Ae``.
    Stripping the node, bay and locality furniture gives the published name
    while keeping the underlying node identity and its real coordinates intact.
    The full label is still what the stop is *matched* on, so nothing stops
    resolving just because its display name was tidied.
    """
    out = name.strip()
    out = _BAY_RANGE_RE.sub(" ", out)
    out = re.sub(r"\s+([,;])", r"\1", out)
    for _ in range(3):
        stripped = _NODE_SUFFIX_RE.sub("", out).strip(" ,-")
        if stripped == out or not stripped:
            break
        out = stripped
    out = _BAY_LETTERS_RE.sub(r"\1", out)
    # Tidy the abbreviations NaPTAN uses.
    out = re.sub(r"\bSt\.", "St ", out)
    out = _title_case_if_shouting(out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip(" ,-")


def _infer_mode(name: str, members: list[tuple[float, float, str]]) -> Mode:
    """Infer the mode of a named NaPTAN stop area from its ATCO codes."""
    codes = [m[2] for m in members]
    atco_areas = {c[:3] for c in codes if len(c) >= 3}
    if "940" in atco_areas or "910" in {c[:3] for c in codes}:
        lowered = name.lower()
        if "metrolink" in lowered or "supertram" in lowered or "metro" in lowered:
            return Mode.TRAM
        if any(k in lowered for k in ("underground", "tube", "dlr", "overground")):
            return Mode.METRO
        return Mode.TRAM
    if "910" in atco_areas:
        return Mode.RAIL
    if "900" in atco_areas:
        return Mode.COACH
    return Mode.BUS


# ==========================================================================
# Timetable compilation
# ==========================================================================


def _leg_times(corridor: Corridor, stops: list[Stop], pattern: ServicePattern) -> list[int]:
    """Cumulative offset from the first departure for each stop on the corridor."""
    offsets = [0]
    for prev, cur in zip(stops, stops[1:]):
        distance_m = haversine_m(prev.lat, prev.lon, cur.lat, cur.lon)
        # Rail and coach run on the actual alignment, which is longer than the
        # straight line; light rail and bus follow streets.
        detour = {
            Mode.RAIL: 1.16,
            Mode.COACH: 1.22,
            Mode.TRAM: 1.18,
            Mode.METRO: 1.16,
            Mode.BUS: 1.32,
            Mode.FERRY: 1.10,
        }.get(Mode(corridor.mode), 1.25)
        run_s = (distance_m * detour) / (pattern.speed_kph * 1000 / 3600)
        dwell = (
            pattern.major_dwell_s
            if (prev.interchange and cur.interchange)
            else pattern.dwell_s
        )
        offsets.append(offsets[-1] + int(round(run_s)) + dwell)
    return offsets


def _departure_times(
    corridor: Corridor, rng: random.Random, *, weekday: int
) -> list[int]:
    """Compile the departure clock for one corridor on one weekday.

    Services are laid out at the pattern's peak and off-peak headways.  A small
    seeded jitter keeps the compiled timetable from looking mechanically
    perfect, exactly as a real one does not.
    """
    pattern = corridor.pattern
    if weekday not in pattern.days:
        return []

    first = _clock(pattern.first_departure)
    last = _clock(pattern.last_departure)
    if last < first:
        # A service that closes "at 00:15" runs into the next morning.  The
        # compiled day stops just before midnight, because the search plans
        # within one service day: a 00:15 departure belongs to that day's
        # timetable, and MoveIn does not yet carry service days across midnight.
        last = min(last + 24 * 3600, 24 * 3600 - 60)
    out: list[int] = []
    t = first
    while t <= last:
        headway = pattern.peak_headway if _is_peak(t) else pattern.offpeak_headway
        # Weekend and late-evening services thin out further.
        if weekday >= 5:
            headway = max(headway, int(headway * 1.35))
        if t > 20 * 3600:
            headway = int(headway * 1.5)
        # Seeded jitter of up to a quarter of the headway.
        jitter = rng.randint(0, max(1, headway * 15))
        out.append(t + jitter)
        t += headway * 60 + rng.randint(-30, 30)
    return sorted(set(out))


def compile_corridor(
    corridor: Corridor,
    stops: list[Stop],
    *,
    rng: random.Random,
) -> tuple[list[Trip], dict[str, list[StopTime]], list[str]]:
    """Compile both directions of one corridor into trips and stop times."""
    pattern = corridor.pattern
    mode = Mode(corridor.mode)
    operator = get_operator(corridor.operator)
    route_id = f"{corridor.code}"
    trips: list[Trip] = []
    times: dict[str, list[StopTime]] = {}
    trip_ids: list[str] = []

    offsets_out = _leg_times(corridor, stops, pattern)
    stops_in = list(reversed(stops))
    offsets_back = _leg_times(corridor, stops_in, pattern)

    # A timetable is defined once per *service type*, not once per weekday: the
    # Monday-Friday service is one pattern that runs five times, which is how
    # GTFS models it and how operators publish it.  Generating per weekday
    # instead would multiply the feed by five for no added information.
    service_variants = (
        (f"{corridor.code}-WK", 0),  # Monday to Friday
        (f"{corridor.code}-WE", 5),  # Saturday
        (f"{corridor.code}-SU", 6),  # Sunday
    )

    for service_id, weekday in service_variants:
        if weekday not in pattern.days:
            continue
        deps = _departure_times(corridor, rng, weekday=weekday)
        if not deps:
            continue
        for i, dep in enumerate(deps):
            for direction, ordered, offsets in (
                (0, stops, offsets_out),
                (1, stops_in, offsets_back),
            ):
                trip_id = f"{corridor.code}-{weekday}-{direction}-{i:03d}"
                trips.append(
                    Trip(
                        id=trip_id,
                        route_id=route_id,
                        service_id=service_id,
                        headsign=ordered[-1].name,
                        direction=direction,
                        wheelchair_accessible=1 if operator.step_free else 0,
                        bikes_allowed=1 if mode in (Mode.RAIL, Mode.TRAM) else 0,
                        reliability=operator.reliability,
                    )
                )
                rows: list[StopTime] = []
                for seq, (stop, offset) in enumerate(zip(ordered, offsets)):
                    arr = dep + offset
                    dwell = (
                        pattern.major_dwell_s
                        if stop.interchange
                        else pattern.dwell_s
                    )
                    rows.append(
                        StopTime(
                            trip_id=trip_id,
                            stop_id=stop.id,
                            stop_sequence=seq,
                            arrival_s=arr,
                            departure_s=arr + (dwell if seq < len(ordered) - 1 else 0),
                            pickup_type=0,
                            dropoff_type=0,
                            headsign=ordered[-1].name if seq < len(ordered) - 1 else "",
                        )
                    )
                times[trip_id] = rows
                trip_ids.append(trip_id)

    return trips, times, trip_ids


# ==========================================================================
# Transfers
# ==========================================================================


def build_transfers(
    stops: list[Stop],
    *,
    max_walk_m: int,
    max_per_stop: int = 12,
) -> list[Transfer]:
    """Walking connections between nearby stops.

    Real interchanges matter more than volume here: a passenger will change
    from a bus onto a train across a station forecourt, and the engine must know
    how long that takes.  We therefore emit transfers between every pair of
    modelled stops within the walking radius, nearest first, capped per stop.
    """
    index = GridIndex(cell_deg=0.01)
    for stop in stops:
        index.add(stop.lat, stop.lon)

    out: list[Transfer] = []
    seen: set[tuple[str, str]] = set()
    per_stop: dict[str, int] = {}

    for i, stop in enumerate(stops):
        hits = index.query_radius(stop.lat, stop.lon, max_walk_m, limit=max_per_stop * 3)
        for j, _dist in hits:
            if i == j:
                continue
            other = stops[j]
            if per_stop.get(stop.id, 0) >= max_per_stop:
                break
            key = (stop.id, other.id)
            if key in seen:
                continue
            seen.add(key)
            distance = walk_distance_m(stop.lat, stop.lon, other.lat, other.lon)
            duration = walk_duration_s(distance)
            within_station = (
                stop.interchange
                and other.interchange
                and haversine_m(stop.lat, stop.lon, other.lat, other.lon) < 250
            )
            out.append(
                Transfer(
                    from_stop_id=stop.id,
                    to_stop_id=other.id,
                    transfer_type=1 if within_station else 2,
                    min_transfer_s=(
                        max(duration, 120) if within_station else duration
                    ),
                    distance_m=round(distance, 1),
                    within_station=within_station,
                )
            )
            per_stop[stop.id] = per_stop.get(stop.id, 0) + 1
    return out


# ==========================================================================
# Fares
# ==========================================================================


def _corridor_length_km(stops: list[Stop]) -> float:
    total = 0.0
    for prev, cur in zip(stops, stops[1:]):
        total += haversine_m(prev.lat, prev.lon, cur.lat, cur.lon)
    return total / 1000.0


def price_for(rule: FareRule, length_km: float) -> float:
    """Apply a corridor's pricing rule to a journey length (rounded to 5p)."""
    if rule.kind == "flat":
        price = rule.base
    elif rule.kind == "tapered":
        # First 40 km at the headline rate, then a reducing marginal rate --
        # mirroring how UK rail fares taper over longer distances.
        near = min(length_km, 40.0)
        far = max(0.0, length_km - 40.0)
        price = rule.base + near * rule.rate_per_km + far * rule.rate_per_km * 0.55
    else:  # distance
        price = rule.base + length_km * rule.rate_per_km
    if rule.cap is not None:
        price = min(price, rule.cap)
    return round(max(price, 0.50) * 20) / 20  # nearest 5p


def build_fares(corridors: list[tuple[Corridor, list[Stop]]]) -> tuple[
    dict[str, FareAttribute], list[FareRuleRow]
]:
    """Build GTFS fare products for every compiled corridor."""
    fares: dict[str, FareAttribute] = {}
    rules: list[FareRuleRow] = []
    operator_codes = {c.operator for c, _ in corridors}

    for corridor, stops in corridors:
        rule = corridor.fare
        length_km = _corridor_length_km(stops)
        single = price_for(rule, length_km)
        anytime = round(single * rule.anytime_multiplier * 20) / 20
        offpeak = round(single * rule.offpeak_multiplier * 20) / 20
        advance = round(single * rule.advance_multiplier * 20) / 20

        products = [
            (f"{corridor.code}-ANY", anytime, "Anytime Single", "single", False, False, True, False),
        ]
        if rule.offpeak_multiplier != 1.0:
            products.append(
                (f"{corridor.code}-OFF", offpeak, "Off-Peak Single", "single", True, False, True, False)
            )
        if rule.advance_multiplier != 1.0 and rule.advance_multiplier < 1.0:
            products.append(
                (f"{corridor.code}-ADV", advance, "Advance Single", "advance", False, True, True, False)
            )
        if rule.offers_returns:
            products.append(
                (
                    f"{corridor.code}-RTN",
                    round(single * rule.return_multiplier * 20) / 20,
                    "Return",
                    "return",
                    False,
                    False,
                    True,
                    False,
                )
            )
        if rule.day_ticket is not None:
            products.append(
                (f"{corridor.code}-DAY", rule.day_ticket, "Day Ticket", "day", False, False, False, True)
            )
        if rule.day_cap is not None:
            products.append(
                (f"{corridor.code}-CAP", rule.day_cap, "Daily Cap", "cap", False, False, False, True)
            )

        for fare_id, price, label, ptype, offpeak_only, advance_only, rail_ok, student_ok in products:
            fares[fare_id] = FareAttribute(
                fare_id=fare_id,
                price=price,
                currency_type="GBP",
                payment_method=1 if advance_only else 0,
                transfers=None if ptype in ("day", "cap", "return") else 0,
                transfer_duration_s=86400 if ptype in ("day", "cap") else None,
                label=label,
                product_type=ptype,
                operator_code=corridor.operator,
                offpeak_only=offpeak_only,
                advance_only=advance_only,
                railcard_eligible=rail_ok,
                student_eligible=student_ok,
            )
            rules.append(FareRuleRow(fare_id=fare_id, route_id=corridor.code))

    # Operator-wide day tickets, valid across every corridor the operator runs.
    for code in sorted(operator_codes):
        op_corridors = [c for c, _ in corridors if c.operator == code]
        if len(op_corridors) < 2:
            continue
        flat_rules = [c.fare for c in op_corridors if c.fare.kind == "flat"]
        if not flat_rules:
            continue
        day_price = flat_rules[0].day_cap or flat_rules[0].day_ticket
        if day_price is None:
            continue
        fare_id = f"OPDAY-{code}"
        fares[fare_id] = FareAttribute(
            fare_id=fare_id,
            price=round(day_price * 20) / 20,
            payment_method=0,
            transfers=None,
            transfer_duration_s=86400,
            label=f"{get_operator(code).name} day ticket",
            product_type="day",
            operator_code=code,
            railcard_eligible=False,
            student_eligible=True,
        )
        for corridor in op_corridors:
            rules.append(FareRuleRow(fare_id=fare_id, route_id=corridor.code))

    return fares, rules


# ==========================================================================
# Top-level compile
# ==========================================================================


class NetworkCompiler:
    def __init__(self, raw_dir: Path | None = None) -> None:
        settings = get_settings()
        self.raw_dir = Path(raw_dir or settings.data_raw_dir)
        self.resolver = StopResolver(self.raw_dir)
        self.warnings: list[str] = []

    # -- public API --------------------------------------------------------
    def compile(self, *, seed: int = COMPILE_SEED) -> CompiledNetwork:
        rng = random.Random(seed)
        routes: dict[str, Route] = {}
        trips: dict[str, Trip] = {}
        stop_times: dict[str, list[StopTime]] = {}
        calendars: dict[str, Calendar] = {}
        used_stops: dict[str, Stop] = {}
        stop_corridors: dict[str, set[str]] = {}
        corridor_trips: dict[str, list[str]] = {}
        resolved: list[tuple[Corridor, list[Stop]]] = []

        for corridor in ALL_CORRIDORS:
            stops = self._resolve_corridor(corridor)
            if stops is None:
                continue
            resolved.append((corridor, stops))
            operator = get_operator(corridor.operator)
            mode = Mode(corridor.mode)
            headline = corridor.name or f"{stops[0].name} to {stops[-1].name}"
            # Buses, trams and metros are known by their line number, which is
            # how a passenger reads a stop.  Trains and coaches are known by
            # where they go: "train 1" would be meaningless on a departure board.
            short_name = (
                corridor.code.split("-")[-1]
                if mode in (Mode.BUS, Mode.TRAM, Mode.METRO)
                else headline
            )
            routes[corridor.code] = Route(
                id=corridor.code,
                operator_code=corridor.operator,
                mode=mode,
                short_name=short_name,
                long_name=headline,
                colour=operator.colour,
                brand=corridor.name or headline,
            )
            for stop in stops:
                used_stops[stop.id] = stop
                stop_corridors.setdefault(stop.id, set()).add(corridor.code)

            c_trips, c_times, trip_ids = compile_corridor(corridor, stops, rng=rng)
            trips.update({t.id: t for t in c_trips})
            stop_times.update(c_times)
            corridor_trips[corridor.code] = trip_ids

            # Calendar rows, one per service id actually produced.
            for suffix, days in (
                ("WK", (True, True, True, True, True, False, False)),
                ("WE", (False, False, False, False, False, True, False)),
                ("SU", (False, False, False, False, False, False, True)),
            ):
                sid = f"{corridor.code}-{suffix}"
                if sid in calendars:
                    continue
                if not any(t.service_id == sid for t in c_trips):
                    continue
                calendars[sid] = Calendar(
                    id=sid,
                    days=days,
                    start_date=SERVICE_START,
                    end_date=SERVICE_END,
                )

        # --- taxi / ride-hailing pseudo-stops at every rail station ---------
        self._add_on_demand_stops(used_stops)

        transfers = build_transfers(
            list(used_stops.values()),
            max_walk_m=get_settings().max_transfer_walk_m,
        )
        fares, fare_rules = build_fares(resolved)

        net = TransportNetwork(
            stops=used_stops,
            routes=routes,
            trips=trips,
            stop_times=stop_times,
            calendars=calendars,
            transfers=transfers,
            fares=fares,
            fare_rules=fare_rules,
            feed_info=FeedInfo(
                publisher="MoveIn",
                publisher_url="https://github.com/HammadBullah/MoveIn",
                lang="en",
                start_date=SERVICE_START,
                end_date=SERVICE_END,
                version=f"movein-phase1-{seed}",
            ),
            corridor_trips=corridor_trips,
        )

        stats = net.stats()
        stats["corridors"] = len(corridor_trips)
        stats["corridors_unresolved"] = len(
            {c.code for c in ALL_CORRIDORS} - set(corridor_trips)
        )
        stats["operators"] = len({r.operator_code for r in routes.values()})
        stats["service_days"] = sum(1 for _ in (SERVICE_START, SERVICE_END))

        return CompiledNetwork(
            network=net,
            stop_corridors=stop_corridors,
            corridor_trips=corridor_trips,
            warnings=self.warnings,
            stats=stats,
        )

    # -- internals ---------------------------------------------------------
    #: Longest plausible distance between two consecutive stops, by mode.
    MAX_LEG_KM: dict[Mode, float] = {
        Mode.RAIL: 300.0,
        Mode.COACH: 400.0,
        Mode.TRAM: 25.0,
        Mode.METRO: 25.0,
        Mode.BUS: 45.0,
        Mode.FERRY: 60.0,
    }

    def _corridor_regions(self, corridor: Corridor) -> tuple[str, ...]:
        """Infer which modelled regions a corridor runs through.

        The corridor's own unambiguous stops define its geography: every CRS
        code and every exact stop-name match pins a region.  Fuzzy name matches
        are then resolved *inside* that geography, which is what stops
        "Victoria" resolving to Preston rather than London.  An explicit
        ``regions=`` on the corridor always wins.
        """
        if corridor.regions:
            return corridor.regions

        counts: dict[str, int] = {}
        for ref in corridor.stops:
            if ref.startswith("R:"):
                stop = self.resolver._resolve_rail(ref[2:])
                if stop and stop.region:
                    counts[stop.region] = counts.get(stop.region, 0) + 1
                continue
            if not ref.startswith("N:"):
                continue
            key = _name_key(ref[2:])
            for sid in self.resolver._by_name.get(key, ()):
                region = self.resolver.stops[sid].region
                if region:
                    counts[region] = counts.get(region, 0) + 1
                    break
        # A genuine corridor touches its regions repeatedly; a stray match in a
        # distant city touches it once.  Rank by how often the corridor is
        # actually there and drop the singletons when there is a clear leader.
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if ranked and len(ranked) > 1:
            top = ranked[0][1]
            ranked = [kv for kv in ranked if kv[1] >= max(2, top * 0.25)]
        return tuple(slug for slug, _ in ranked)

    def _resolve_corridor(self, corridor: Corridor) -> list[Stop] | None:
        """Resolve every stop reference, guarding against geographically absurd matches."""
        max_leg_km = self.MAX_LEG_KM.get(Mode(corridor.mode), 100.0)
        regions = self._corridor_regions(corridor)

        # Pass 1 -- resolve with the region hint, but defer the distance guard
        # so a single bad stop cannot cascade into every subsequent one.
        provisional: list[tuple[str, Stop | None]] = [
            (ref, self.resolver.resolve(ref, regions, Mode(corridor.mode)))
            for ref in corridor.stops
        ]

        # Pass 2 -- walk the corridor, applying the distance guard only where it
        # is the *reference* that is suspicious, not the whole remainder.
        stops: list[Stop] = []
        missing: list[str] = []
        for ref, stop in provisional:
            if stop is None:
                missing.append(ref)
                continue
            if stops:
                prev = stops[-1]
                if haversine_m(prev.lat, prev.lon, stop.lat, stop.lon) > max_leg_km * 1000:
                    # Try again constrained to the corridor's own regions.
                    retry = self.resolver.resolve_near(
                        ref, prev.lat, prev.lon, max_leg_km, regions,
                        Mode(corridor.mode),
                    )
                    if retry is None:
                        missing.append(ref)
                        continue
                    stop = retry
            if stops and stops[-1].id == stop.id:
                continue
            stops.append(stop)

        if missing:
            self.warnings.append(
                f"{corridor.code}: unresolved or implausible stop references {missing}"
            )
            return None
        if len(stops) < 2:
            self.warnings.append(f"{corridor.code}: fewer than two distinct stops")
            return None
        return stops

    def _add_on_demand_stops(self, used_stops: dict[str, Stop]) -> None:
        """Add a taxi/ride-hailing pickup point beside every rail station.

        Taxis do not have timetables, so they are not ''stops'' in the GTFS
        sense -- but they are pickup points, and the engine needs a node to
        attach the on-demand leg to.
        """
        for stop in list(used_stops.values()):
            if stop.mode != Mode.RAIL:
                continue
            sid = f"ondemand:{stop.id}"
            used_stops[sid] = Stop(
                id=sid,
                name=f"{stop.name} station forecourt",
                lat=stop.lat + 0.00018,
                lon=stop.lon + 0.00018,
                mode=Mode.TAXI,
                parent_id=stop.id,
                region=stop.region,
                interchange=False,
                source="derived",
            )


# ==========================================================================
# Persistence
# ==========================================================================


def _network_fingerprint(net: TransportNetwork) -> str:
    h = hashlib.sha256()
    for tid in sorted(net.stop_times)[:2000]:
        h.update(tid.encode())
        for st in net.stop_times[tid]:
            h.update(f"{st.stop_id}{st.arrival_s}{st.departure_s}".encode())
    return h.hexdigest()[:16]


def save_compiled(
    compiled: CompiledNetwork,
    out_dir: Path,
    *,
    write_gtfs_zip: bool = True,
) -> dict[str, object]:
    """Persist a compiled network as GTFS plus a REST-friendly JSON index."""
    from .gtfs import write_gtfs

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    net = compiled.network

    feed_dir = out_dir / "gtfs"
    agencies = []
    seen_ops: set[str] = set()
    for route in net.routes.values():
        if route.operator_code in seen_ops:
            continue
        seen_ops.add(route.operator_code)
        op = get_operator(route.operator_code)
        agencies.append({
            "agency_id": op.code,
            "agency_name": op.name,
            "agency_url": op.url or "https://github.com/HammadBullah/MoveIn",
            "agency_timezone": "Europe/London",
            "agency_lang": "en",
            "agency_phone": "",
        })
    write_gtfs(net, feed_dir, agencies=agencies)
    if write_gtfs_zip:
        write_gtfs(net, out_dir / "movein-gtfs.zip", agencies=agencies)

    # --- REST index -------------------------------------------------------
    stops_payload = [
        {
            "id": s.id,
            "name": s.name,
            "lat": round(s.lat, 6),
            "lon": round(s.lon, 6),
            "mode": s.mode.value,
            "region": s.region,
            "crs": s.crs_code,
            "atco": s.atco_code,
            "interchange": s.interchange,
            "step_free": bool(s.wheelchair_boarding == 1),
            "corridors": sorted(compiled.stop_corridors.get(s.id, ())),
        }
        for s in sorted(net.stops.values(), key=lambda s: (s.region, s.name))
    ]
    corridors_payload = []
    for code, trip_ids in compiled.corridor_trips.items():
        if not trip_ids:
            continue
        route = net.routes[code]
        sample = net.stop_times[trip_ids[0]]
        corridors_payload.append({
            "code": code,
            "name": route.brand or route.long_name,
            "operator": route.operator_code,
            "operator_name": get_operator(route.operator_code).name,
            "mode": route.mode.value,
            "colour": route.colour,
            "stops": [net.stops[st.stop_id].name for st in sample],
            "stop_ids": [st.stop_id for st in sample],
            "trips": len(trip_ids),
            "first_departure": min(
                net.stop_times[t][0].departure_s for t in trip_ids
            ),
            "last_departure": max(
                net.stop_times[t][0].departure_s for t in trip_ids
            ),
        })
    corridors_payload.sort(key=lambda c: (c["mode"], c["code"]))

    index = {
        "feed_version": net.feed_info.version,
        "service": {
            "start": net.feed_info.start_date.isoformat() if net.feed_info.start_date else "",
            "end": net.feed_info.end_date.isoformat() if net.feed_info.end_date else "",
        },
        "fingerprint": _network_fingerprint(net),
        "stats": compiled.stats,
        "warnings": compiled.warnings,
        "regions": [
            {"slug": r.slug, "name": r.name, "lat": r.lat, "lon": r.lon, "radius_m": r.radius_m}
            for r in REGIONS
        ],
        "stops": stops_payload,
        "corridors": corridors_payload,
    }
    (out_dir / "network.json").write_text(
        json.dumps(index, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    return {
        **compiled.stats,
        "feed_dir": str(feed_dir),
        "network_json_bytes": (out_dir / "network.json").stat().st_size,
        "fingerprint": index["fingerprint"],
        "warnings": compiled.warnings,
    }
