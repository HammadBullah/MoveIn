"""Real open-data sources used by MoveIn.

Every source listed here is a genuine, publicly published UK transport dataset.
The download step in ``scripts/fetch_real_data.py`` pulls them and trims them
into the compact seed files that ship in ``backend/data/raw``.

Where a source cannot be reached (the sandbox this repo was built in can only
reach GitHub, npm and PyPI -- not the DfT Bus Open Data Service or the TfL
Unified API), the corresponding *adapter* still exists and is exercised against
recorded fixtures.  See ``docs/DATA_SOURCES.md`` for the full provenance table
and for the one-command switch that replaces the compiled timetable with live
feeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RemoteFile:
    """A single downloadable artefact and where it comes from."""

    name: str
    repo: str
    path: str
    ref: str
    publisher: str
    licence: str
    description: str
    #: Column notes / gotchas worth remembering when parsing.
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def contents_api_url(self) -> str:
        return f"https://api.github.com/repos/{self.repo}/contents/{self.path}?ref={self.ref}"

    @property
    def raw_url(self) -> str:
        return f"https://api.github.com/repos/{self.repo}/contents/{self.path}"


# --- NaPTAN: every public transport access point in Great Britain ------------
NAPTAN_GEO = RemoteFile(
    name="naptan_access_points.csv",
    repo="odileeds/NAPTAN",
    path="NAPTAN.csv",
    ref="main",
    publisher="Department for Transport (via ODI Leeds)",
    licence="Open Government Licence v3.0",
    description=(
        "Every public transport access point in Great Britain (bus stops, rail "
        "stations, tram stops, metro stations, ferry terminals, airports) with "
        "ATCO codes, coordinates, NPTG locality codes and administrative "
        "geography codes."
    ),
    notes=(
        "No stop names -- this extract is geography-only by design.",
        "ATCO code's first three characters are the NaPTAN area code.",
    ),
)

# --- Stop names -------------------------------------------------------------
NAPTAN_NAMES = RemoteFile(
    name="naptan_names.csv",
    repo="itsleeds/UK2GTFS-data",
    path="data/raw/naptan_missing.csv",
    ref="main",
    publisher="Department for Transport (via UK2GTFS / ITS Leeds)",
    licence="Open Government Licence v3.0",
    description=(
        "Real NaPTAN stop names with coordinates, for access points that are "
        "absent from the UK2GTFS working extract."
    ),
    notes=("Some rows carry 'NA' coordinates and must be skipped.",),
)

NAPTAN_REPLACEMENTS = RemoteFile(
    name="naptan_replacements.csv",
    repo="itsleeds/UK2GTFS-data",
    path="data/raw/naptan_replace.csv",
    ref="main",
    publisher="Department for Transport (via UK2GTFS / ITS Leeds)",
    licence="Open Government Licence v3.0",
    description="Corrected/renamed NaPTAN access points with real stop names.",
)

# --- Rail -------------------------------------------------------------------
#: TIPLOC / CRS timing points: the authoritative list of GB railway stations,
#: with their three-letter CRS codes (NOT, BHM, DBY ...) and coordinates.
RAIL_STATIONS = RemoteFile(
    name="rail_stations.csv",
    repo="itsleeds/UK2GTFS-data",
    path="data/raw/tiplocs.csv",
    ref="main",
    publisher="Network Rail / RDG (via UK2GTFS / ITS Leeds)",
    licence="Open Government Licence v3.0",
    description=(
        "GB railway timing points (TIPLOCs) with CRS station codes and "
        "coordinates, used to build the rail layer of the network."
    ),
)

#: Train Operating Company registry (ATOC two-letter codes).
ATOC_AGENCIES = RemoteFile(
    name="atoc_agencies.csv",
    repo="itsleeds/UK2GTFS-data",
    path="data/raw/atoc_agency.csv",
    ref="main",
    publisher="ATOC / RDG (via UK2GTFS / ITS Leeds)",
    licence="Open Government Licence v3.0",
    description="Train Operating Company registry: ATOC codes, names and URLs.",
)

# --- Live feeds (adapter present, network-gated) ----------------------------
LIVE_FEEDS = {
    "bods_timetables": {
        "name": "BODS bus timetables",
        "provides": (
            "The real timetable for every registered English bus service, which "
            "would replace the compiled timetable layer outright."
        ),
        "publisher": "DfT Bus Open Data Service",
        "endpoint": "https://data.bus-data.dft.gov.uk/api/v1/dataset/",
        "format": "TransXChange XML / GTFS",
        "licence": "Open Government Licence v3.0",
        "auth": "BODS_API_KEY (free registration)",
        "adapter": "app.ingest.bods",
    },
    "bods_fares": {
        "name": "BODS bus fares",
        "provides": (
            "NeTEx fare data per service, replacing the modelled fare amounts "
            "with the published ones."
        ),
        "publisher": "DfT Bus Open Data Service",
        "endpoint": "https://data.bus-data.dft.gov.uk/api/v1/fares/dataset/",
        "format": "NeTEx Fares / GTFS-Fares",
        "licence": "Open Government Licence v3.0",
        "auth": "BODS_API_KEY (free registration)",
        "adapter": "app.ingest.bods",
    },
    "bods_siri_vm": {
        "name": "BODS live vehicle positions (SIRI-VM)",
        "provides": (
            "Where the buses actually are right now, replacing the simulated "
            "positions behind /api/live/vehicles."
        ),
        "publisher": "DfT Bus Open Data Service",
        "endpoint": "https://data.bus-data.dft.gov.uk/api/v1/datafeed/",
        "format": "SIRI-VM (live vehicle positions)",
        "licence": "Open Government Licence v3.0",
        "auth": "BODS_API_KEY (free registration)",
        "adapter": "app.ingest.bods",
    },
    "tfl_unified": {
        "name": "TfL Unified API",
        "provides": (
            "London tube, DLR, Overground, Elizabeth line and bus data, with "
            "line status as real disruption alerts."
        ),
        "publisher": "Transport for London",
        "endpoint": "https://api.tfl.gov.uk/",
        "format": "TfL Unified API (JSON) / GTFS",
        "licence": "TfL Open Data Licence",
        "auth": "app_key (optional for low volume)",
        "adapter": "app.ingest.tfl",
    },
    "nptg": {
        "name": "NPTG gazetteer",
        "provides": (
            "Localities, adjacent localities and administrative areas, for "
            "place search and region attribution."
        ),
        "publisher": "Department for Transport",
        "endpoint": "https://beta-naptan.dft.gov.uk/",
        "format": "NPTG CSV (Localities, AdjacentLocality, AdminAreas)",
        "licence": "Open Government Licence v3.0",
        "auth": "None",
        "adapter": "app.ingest.nptg",
    },
    "osm_overpass": {
        "name": "OpenStreetMap footways (Overpass)",
        "provides": (
            "The real pedestrian network, replacing the straight-line walk "
            "model with measured routes."
        ),
        "publisher": "OpenStreetMap contributors",
        "endpoint": "https://overpass-api.de/api/interpreter",
        "format": "Overpass QL (pedestrian/cycle network)",
        "licence": "Open Database Licence (ODbL)",
        "auth": "None (fair-use rate limits)",
        "adapter": "app.ingest.osm",
    },
}

ALL_STATIC_SOURCES: tuple[RemoteFile, ...] = (
    NAPTAN_GEO,
    NAPTAN_NAMES,
    NAPTAN_REPLACEMENTS,
    RAIL_STATIONS,
    ATOC_AGENCIES,
)


# --- What actually ships in backend/data/raw --------------------------------
@dataclass(frozen=True)
class BundledFile:
    """A file that is really in ``backend/data/raw``, and what it came from.

    The provenance screen lists *this*, not the download list above, because
    what a reader needs to know is which dataset the running planner is using.
    ``inputs`` names the upstream inputs; ``rows`` is filled in from the file
    itself at seed time so the count on screen cannot drift from the count on
    disk.
    """

    name: str
    inputs: tuple[RemoteFile, ...]
    description: str
    #: Rows excluding the header, or None when the file is not a table.
    rows: int | None = None

    @property
    def licence(self) -> str:
        for source in self.inputs:
            if source.licence:
                return source.licence
        return ""

    @property
    def publisher(self) -> str:
        return "; ".join(dict.fromkeys(s.publisher for s in self.inputs))

    @property
    def url(self) -> str:
        return self.inputs[0].raw_url if self.inputs else ""


def _bundled() -> tuple[BundledFile, ...]:
    return (
        BundledFile(
            name="naptan_named_stops.csv",
            inputs=(NAPTAN_NAMES, NAPTAN_REPLACEMENTS),
            description=(
                "Named NaPTAN access points with coordinates, merged from the "
                "UK2GTFS 'missing' and 'replace' extracts and trimmed to the "
                "modelled regions. Stop names and coordinates as published."
            ),
        ),
        BundledFile(
            name="naptan_regional.csv.gz",
            inputs=(NAPTAN_GEO,),
            description=(
                "NaPTAN access points for the modelled regions, trimmed from "
                "the full GB register. ATCO codes, coordinates, NPTG locality "
                "codes and administrative geography."
            ),
        ),
        BundledFile(
            name="rail_stations.csv",
            inputs=(RAIL_STATIONS,),
            description=(
                "Network Rail timing points (TIPLOCs) with CRS station codes "
                "and coordinates: the rail layer of the network."
            ),
        ),
        BundledFile(
            name="atoc_agencies.csv",
            inputs=(ATOC_AGENCIES,),
            description="Train Operating Company registry: ATOC codes, names and URLs.",
        ),
    )


BUNDLED_FILES: tuple[BundledFile, ...] = _bundled()


def count_rows(path) -> int | None:
    """Data rows in a bundled CSV (or ``.csv.gz``), excluding the header."""
    import gzip
    from pathlib import Path as _Path

    path = _Path(path)
    if not path.exists():
        return None
    opener = gzip.open if path.suffix == ".gz" else open
    try:
        with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
            return max(0, sum(1 for _ in handle) - 1)
    except OSError:
        return None
