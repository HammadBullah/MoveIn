"""NPTG (National Public Transport Gazetteer) adapter.

NPTG is the DfT's register of the localities, administrative areas and
settlements that NaPTAN stop records point at.  NaPTAN gives every stop a
``LocalityCode``; NPTG is what turns that code into "Nottingham", "Beeston" or
"Long Eaton" with a centre point.

MoveIn uses it for two things:

* **Region attribution** -- which modelled region a stop belongs to, so a
  "Victoria" in London is not confused with the one in Manchester.
* **Place search** -- a locality centre is what a traveller means when they type
  a town, rather than whichever stop happens to sort first.

The files are small CSVs published by the DfT under the Open Government
Licence.  ``beta-naptan.dft.gov.uk`` is not reachable from this environment, so
the parser is tested against a recorded extract.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

NPTG_BASE_URL = "https://beta-naptan.dft.gov.uk"


@dataclass(frozen=True)
class Locality:
    """One NPTG locality: a place a traveller would name."""

    code: str
    name: str
    lat: float
    lon: float
    admin_area: str = ""
    district: str = ""
    #: NPTG's locality type: "Settlement", "Locality", "Uncodisted" ...
    type: str = ""

    @property
    def slug(self) -> str:
        from ..ingest.network_compiler import _slug

        return _slug(self.name)


def _f(row: dict, *names: str) -> str:
    for name in names:
        for key, value in row.items():
            if key.strip().lower() == name.lower():
                return (value or "").strip()
    return ""


def parse_localities(csv_text: str) -> dict[str, Locality]:
    """``LocalityCode -> Locality`` from an NPTG Localities CSV."""
    out: dict[str, Locality] = {}
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    for row in reader:
        code = _f(row, "LocalityCode")
        name = _f(row, "LocalityName", "Name")
        if not code or not name:
            continue
        try:
            lat = float(_f(row, "Latitude", "Lat"))
            lon = float(_f(row, "Longitude", "Long"))
        except ValueError:
            continue
        out[code] = Locality(
            code=code,
            name=name,
            lat=lat,
            lon=lon,
            admin_area=_f(row, "AdministrativeAreaCode", "AdminAreaCode"),
            district=_f(row, "DistrictCode", "NptgDistrictCode"),
            type=_f(row, "LocalityType", "Type"),
        )
    return out


def parse_adjacent_localities(csv_text: str) -> dict[str, set[str]]:
    """``LocalityCode -> neighbouring LocalityCodes``.

    NPTG publishes this so a search for a village can also match the town next
    to it, which is how "Long Eaton" finds journeys from Nottingham.
    """
    out: dict[str, set[str]] = {}
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    for row in reader:
        code = _f(row, "LocalityCode")
        neighbour = _f(row, "AdjacentLocalityCode")
        if code and neighbour:
            out.setdefault(code, set()).add(neighbour)
    return out


def parse_admin_areas(csv_text: str) -> dict[str, str]:
    """``AdministrativeAreaCode -> name`` (counties, unitary authorities)."""
    out: dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    for row in reader:
        code = _f(row, "AdministrativeAreaCode", "AdminAreaCode")
        name = _f(row, "AdministrativeAreaName", "Name")
        if code and name:
            out[code] = name
    return out
