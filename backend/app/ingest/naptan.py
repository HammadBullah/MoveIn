"""NaPTAN ingestion.

NaPTAN (National Public Transport Access Nodes) is the DfT's authoritative
register of every point where a passenger can board or alight public transport
in Great Britain.

Two real extracts are combined here:

* ``naptan_access_points.csv`` -- ODI Leeds' geography-only extract of the full
  NaPTAN register (ATCO code, coordinates, NPTG locality, administrative
  geography).  This is the *complete* register, ~433k nodes.
* ``naptan_names.csv`` -- real stop names, which the geography extract omits.

In production the same records arrive through the DfT's NaPTAN distribution
(NaptanXML / CSV) and through the BODS reference-data service; this module's
:func:`parse_access_point` is written against the union of those schemas so the
loader does not change when the live source is switched on.
"""

from __future__ import annotations

import csv
import gzip
import io
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from ..domain.regions import REGIONS

# --- NaPTAN area codes ------------------------------------------------------
#: The first three characters of an ATCO code identify the issuing local
#: authority.  900+ are national/regional numbering schemes.
ATCO_AREA_NAMES: dict[str, str] = {
    "080": "Cheshire",
    "100": "Cumbria",
    "110": "Derbyshire",
    "120": "Devon",
    "130": "Dorset",
    "150": "East Sussex",
    "160": "Essex",
    "180": "Greater London (outer)",
    "190": "Gloucestershire",
    "200": "Hampshire",
    "210": "Herefordshire",
    "240": "Kent",
    "250": "Lancashire",
    "258": "Leicestershire",
    "259": "Leicester City",
    "260": "Leicestershire (district)",
    "280": "Merseyside",
    "290": "Greater Manchester",
    "300": "Nottinghamshire",
    "310": "Nottingham City",
    "320": "Derby & Derbyshire",
    "330": "Birmingham",
    "340": "West Midlands (Coventry & Solihull)",
    "360": "Norfolk",
    "370": "Northamptonshire",
    "380": "Northumberland",
    "390": "Oxfordshire",
    "400": "Staffordshire",
    "410": "Suffolk",
    "430": "Surrey",
    "440": "Warwickshire",
    "450": "West Yorkshire",
    "490": "London Buses",
    "650": "Wiltshire",
    "680": "North Yorkshire",
    "900": "National (coach/air)",
    "910": "National Rail",
    "940": "Metro / tram / light rail",
}

#: NaPTAN StopType values (from the NaPTAN schema guide).
STOP_TYPE_NAMES: dict[str, str] = {
    "AIR": "airport",
    "BCE": "bus/coach interchange",
    "BCQ": "bus/coach bay",
    "BCS": "bus/coach stop",
    "BCT": "bus/coach terminus",
    "BPL": "bus/coach pick-up / set-down",
    "FER": "ferry terminal",
    "FTD": "ferry dock",
    "GAT": "gate",
    "MET": "metro station",
    "PLT": "platform",
    "RSE": "railway station entrance",
    "RLY": "railway station",
    "RPL": "railway platform",
    "TAX": "taxi rank",
    "TXR": "taxi rank",
    "TMU": "tram/metro stop",
}


@dataclass(slots=True)
class AccessPoint:
    """A single NaPTAN access node."""

    atco_code: str
    name: str
    lat: float
    lon: float
    locality_code: str = ""
    lad_code: str = ""
    stop_type: str = ""
    naptan_code: str = ""
    #: True when the name was resolved from a real named-stops extract.
    has_real_name: bool = False

    @property
    def area_code(self) -> str:
        return self.atco_code[:3]

    @property
    def area_name(self) -> str:
        return ATCO_AREA_NAMES.get(self.area_code, f"ATCO area {self.area_code}")

    @property
    def transport_type(self) -> str:
        """Coarse mode inferred from the ATCO area and stop type."""
        if self.area_code == "910" or self.stop_type in ("RLY", "RPL", "RSE"):
            return "rail"
        if self.area_code == "940" or self.stop_type in ("TMU", "MET"):
            return "tram"
        if self.stop_type in ("FER", "FTD"):
            return "ferry"
        if self.stop_type == "AIR":
            return "air"
        if self.area_code == "900":
            return "coach"
        return "bus"


def _clean_atco(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip())


def parse_access_point(row: dict[str, str]) -> AccessPoint | None:
    """Parse one row of the ODI Leeds NaPTAN geography extract."""
    atco = _clean_atco(row.get("ATCOCode") or row.get("atco_code") or "")
    if not atco:
        return None
    try:
        lat = float((row.get("Latitude") or "").strip())
        lon = float((row.get("Longitude") or "").strip())
    except (TypeError, ValueError):
        return None
    if not (-7.6 < lon < 2.2 and 49.8 < lat < 61.0):
        # Outside Great Britain -- reject bad rows rather than pollute the index.
        return None
    return AccessPoint(
        atco_code=atco,
        name="",
        lat=lat,
        lon=lon,
        locality_code=(row.get("NptgLocalityCode") or "").strip(),
        lad_code=(row.get("lad17cd") or "").strip(),
        naptan_code=(row.get("NaptanCode") or "").strip(),
    )


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return open(path, encoding="utf-8-sig", newline="")


def iter_access_points(path: Path) -> Iterator[AccessPoint]:
    """Stream :class:`AccessPoint` records from a NaPTAN CSV (optionally gzipped)."""
    with _open_text(path) as fh:
        for row in csv.DictReader(fh):
            ap = parse_access_point(row)
            if ap is not None:
                yield ap


def load_name_lookup(paths: Iterable[Path]) -> dict[str, tuple[str, float, float]]:
    """Build an ATCO -> (name, lat, lon) lookup from real named-stop extracts."""
    lookup: dict[str, tuple[str, float, float]] = {}
    for path in paths:
        if not path.exists():
            continue
        with _open_text(path) as fh:
            for row in csv.DictReader(fh):
                sid = _clean_atco(row.get("stop_id", ""))
                name = (row.get("stop_name") or "").strip()
                if not sid or not name:
                    continue
                try:
                    lon = float((row.get("stop_lon") or "NA").strip())
                    lat = float((row.get("stop_lat") or "NA").strip())
                except (TypeError, ValueError):
                    continue
                lookup.setdefault(sid, (name, lat, lon))
    return lookup


def in_modelled_regions(lat: float, lon: float, slack_m: float = 0.0) -> bool:
    """True when a point falls inside any modelled region disc."""
    from .geo import haversine_m

    for region in REGIONS:
        if abs(lat - region.lat) > 0.35 or abs(lon - region.lon) > 0.55:
            continue
        if haversine_m(lat, lon, region.lat, region.lon) <= region.radius_m + slack_m:
            return True
    return False


def region_for_point(lat: float, lon: float) -> str | None:
    """Slug of the nearest modelled region containing a point (if any)."""
    from .geo import haversine_m

    best: tuple[float, str] | None = None
    for region in REGIONS:
        d = haversine_m(lat, lon, region.lat, region.lon)
        if d <= region.radius_m and (best is None or d < best[0]):
            best = (d, region.slug)
    return best[1] if best else None


def titlecase_stop_name(raw: str) -> str:
    """Normalise NaPTAN's SHOUTING STOP NAMES into readable title case.

    NaPTAN names are published upper-case.  Blind ``str.title()`` mangles
    apostrophes and small words, so this does a controlled job and preserves
    known abbreviations (St, Rd, Ave, Mt, NE, etc.).
    """
    if not raw:
        return raw
    if raw != raw.upper():
        return raw  # already mixed case, leave alone

    preserve = {
        "ST": "St", "STA": "Sta", "RD": "Rd", "AVE": "Ave", "MT": "Mt",
        "NTH": "Nth", "SCH": "Sch", "UNI": "Uni", "HOSP": "Hosp",
        "CTR": "Ctr", "OPP": "Opp", "ADJ": "Adj", "NR": "Nr", "SW": "SW",
        "SE": "SE", "NW": "NW", "NE": "NE", "PO": "PO", "RAIL": "Rail",
        "BUS": "Bus", "STN": "Stn", "WO": "WO", "FC": "FC",
    }
    small_words = {"AND", "OF", "THE", "ON", "AT", "IN", "TO", "FOR", "BY"}

    # Split on whitespace but keep bracket/slash punctuation attached.
    tokens = re.split(r"(\s+)", raw)
    words = [t for t in tokens if t.strip()]
    out: list[str] = []
    for i, token in enumerate(tokens):
        if not token.strip():
            out.append(token)
            continue
        m = re.match(r"^([^\w]*)(.*?)([^\w]*)$", token)
        pre, core, post = m.group(1), m.group(2), m.group(3)
        if not core:
            out.append(token)
            continue
        upper = core.upper()
        if upper in preserve:
            cased = preserve[upper]
        elif upper in small_words and 0 < words.index(core) < len(words) - 1:
            cased = core.lower()
        else:
            # Handle hyphenated and apostrophised names.
            parts = re.split(r"([-/])", core)
            cased_parts = []
            for part in parts:
                if part in "-/":
                    cased_parts.append(part)
                    continue
                if "'" in part:
                    head, _, tail = part.partition("'")
                    cased_parts.append(
                        head.capitalize() + "'" + (tail.lower() if tail else "")
                    )
                else:
                    cased_parts.append(part.capitalize())
            cased = "".join(cased_parts)
        out.append(pre + cased + post)
    return "".join(out)


def classify_stop(
    ap: AccessPoint, *, is_rail_hub: bool = False
) -> str:
    """Assign a MoveIn stop class: rail, tram, metro, ferry, airport, coach, bus."""
    base = ap.transport_type
    if base == "rail" and is_rail_hub:
        return "rail_interchange"
    return base


def summarise(points: Iterable[AccessPoint]) -> dict[str, int]:
    """Count access points by inferred mode (used by the ingest CLI)."""
    counts: dict[str, int] = {}
    for ap in points:
        counts[ap.transport_type] = counts.get(ap.transport_type, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def normalise_name_key(name: str) -> str:
    """Key used to deduplicate stops that differ only by punctuation/case."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def local_metres(lat: float, lat0: float) -> float:
    """Small helper: metres per degree of longitude at a given latitude."""
    return 111_320.0 * math.cos(math.radians(lat0))
