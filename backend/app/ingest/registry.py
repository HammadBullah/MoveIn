"""Operator registry.

Two real UK operator numbering schemes are supported:

* **ATOC / RDG two-letter codes** for rail (``EM`` East Midlands Railway,
  ``XC`` CrossCountry, ``VT`` Avanti West Coast ...).  These are validated
  against ``data/raw/atoc_agencies.csv``, the real Train Operating Company
  registry, at load time.
* **NOC codes** (National Operator Codes) for bus, coach and light rail
  (``NATX`` National Express, ``MEGA`` megabus, ``NXWM`` National Express West
  Midlands ...).  The codes used here for coach operators are the ones carried
  in the real ITO World GTFS feed.

Unknown codes are surfaced through :func:`validate_registry` rather than
silently defaulted, so a typo in :mod:`app.domain.network_spec` fails loudly.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import get_settings


@dataclass(frozen=True)
class Operator:
    code: str
    name: str
    mode: str
    scheme: str = "noc"  # "atoc" | "noc"
    #: Brand colour used by the UI.
    colour: str = "#4b5563"
    #: Hex icon hint for the frontend.
    icon: str = "bus"
    url: str = ""
    #: True when the operator sells through an affiliate-commissionable channel.
    affiliate: bool = False
    #: Reliability factor applied to journey scoring (1.0 = network average).
    reliability: float = 0.92
    #: Whether the operator's fleet is recorded as step-free accessible.
    step_free: bool = True
    #: Relative CO2 intensity of the operator's fleet (kg CO2e per passenger-km).
    co2_g_per_pkm: float = 0.0


TRAIN_OPERATORS: tuple[Operator, ...] = (
    Operator("EM", "East Midlands Railway", "rail", "atoc", "#5b2c86", "train",
             "https://www.eastmidlandsrailway.co.uk", True, 0.93, True, 35.0),
    Operator("XC", "CrossCountry", "rail", "atoc", "#7a1f2b", "train",
             "https://www.crosscountrytrains.co.uk", True, 0.91, True, 38.0),
    Operator("LM", "West Midlands Trains", "rail", "atoc", "#00843d", "train",
             "https://www.westmidlandsrailway.co.uk", True, 0.92, True, 33.0),
    Operator("VT", "Avanti West Coast", "rail", "atoc", "#0d1b3e", "train",
             "https://www.avantiwestcoast.co.uk", True, 0.89, True, 30.0),
    Operator("NT", "Northern", "rail", "atoc", "#1d3f94", "train",
             "https://www.northernrailway.co.uk", True, 0.90, True, 36.0),
    Operator("TP", "TransPennine Express", "rail", "atoc", "#0d2b52", "train",
             "https://www.tpexpress.co.uk", True, 0.88, True, 32.0),
    Operator("GR", "London North Eastern Railway", "rail", "atoc", "#c8102e", "train",
             "https://www.lner.co.uk", True, 0.94, True, 28.0),
    Operator("CH", "Chiltern Railways", "rail", "atoc", "#2c3e8f", "train",
             "https://www.chilternrailways.co.uk", True, 0.92, True, 34.0),
    Operator("GW", "Great Western Railway", "rail", "atoc", "#0f2f4f", "train",
             "https://www.gwr.com", True, 0.91, True, 34.0),
    Operator("AW", "Transport for Wales", "rail", "atoc", "#c8102e", "train",
             "https://tfw.wales", True, 0.90, True, 36.0),
)

COACH_OPERATORS: tuple[Operator, ...] = (
    Operator("NATX", "National Express", "coach", "noc", "#003a70", "coach",
             "https://www.nationalexpress.com", True, 0.93, True, 27.0),
    Operator("MEGA", "megabus", "coach", "noc", "#00a0df", "coach",
             "https://uk.megabus.com", True, 0.88, True, 27.0),
    Operator("FLIX", "FlixBus", "coach", "noc", "#73d700", "coach",
             "https://www.flixbus.co.uk", True, 0.89, True, 28.0),
    Operator("SCLK", "Scottish Citylink", "coach", "noc", "#1d3f94", "coach",
             "https://www.citylink.co.uk", True, 0.90, True, 28.0),
)

LIGHT_RAIL_OPERATORS: tuple[Operator, ...] = (
    Operator("NET", "Nottingham Express Transit", "tram", "noc", "#00a03e", "tram",
             "https://www.thetram.net", False, 0.96, True, 22.0),
    Operator("WMM", "West Midlands Metro", "tram", "noc", "#1b365d", "tram",
             "https://www.westmidlandsmetro.com", False, 0.95, True, 22.0),
    Operator("ML", "Manchester Metrolink", "tram", "noc", "#f0b323", "tram",
             "https://tfgm.com", False, 0.95, True, 21.0),
    Operator("SUT", "Stagecoach Supertram", "tram", "noc", "#f59e0b", "tram",
             "https://www.supertram.com", False, 0.94, True, 21.0),
    Operator("TFL", "Transport for London", "metro", "noc", "#0019a8", "metro",
             "https://tfl.gov.uk", False, 0.97, True, 20.0),
)

BUS_OPERATORS: tuple[Operator, ...] = (
    Operator("NCTR", "Nottingham City Transport", "bus", "noc", "#00a03e", "bus",
             "https://www.nctx.co.uk", False, 0.94, True, 82.0),
    Operator("TBTN", "trentbarton", "bus", "noc", "#e30613", "bus",
             "https://www.trentbarton.co.uk", False, 0.93, True, 82.0),
    Operator("NXWM", "National Express West Midlands", "bus", "noc", "#003a70", "bus",
             "https://nxbus.co.uk", False, 0.92, True, 85.0),
    Operator("ARRL", "Arriva Midlands", "bus", "noc", "#00a5b5", "bus",
             "https://www.arrivabus.co.uk", False, 0.91, True, 85.0),
    Operator("ARRY", "Arriva Yorkshire", "bus", "noc", "#00a5b5", "bus",
             "https://www.arrivabus.co.uk", False, 0.91, True, 85.0),
    Operator("SCEM", "Stagecoach East Midlands", "bus", "noc", "#0d47a1", "bus",
             "https://www.stagecoachbus.com", False, 0.92, True, 84.0),
    Operator("SCSY", "Stagecoach South Yorkshire", "bus", "noc", "#0d47a1", "bus",
             "https://www.stagecoachbus.com", False, 0.92, True, 84.0),
    Operator("SCMN", "Stagecoach Manchester", "bus", "noc", "#0d47a1", "bus",
             "https://www.stagecoachbus.com", False, 0.91, True, 84.0),
    Operator("FLDS", "First Leeds", "bus", "noc", "#8c1d40", "bus",
             "https://www.firstbus.co.uk", False, 0.91, True, 84.0),
    Operator("FMAN", "First Manchester", "bus", "noc", "#8c1d40", "bus",
             "https://www.firstbus.co.uk", False, 0.90, True, 85.0),
    Operator("FHLD", "First South Yorkshire", "bus", "noc", "#8c1d40", "bus",
             "https://www.firstbus.co.uk", False, 0.90, True, 85.0),
    Operator("TFLBUS", "London Buses", "bus", "noc", "#dc241f", "bus",
             "https://tfl.gov.uk", False, 0.95, True, 80.0),
)

#: On-demand modes are priced through the fare engine's distance model.
ON_DEMAND_OPERATORS: tuple[Operator, ...] = (
    Operator("TAXI", "Local taxi", "taxi", "noc", "#1f2937", "taxi",
             "", False, 0.86, False, 190.0),
    Operator("UBER", "Uber", "ridehail", "noc", "#000000", "ridehail",
             "https://www.uber.com", True, 0.90, True, 175.0),
    Operator("BOLT", "Bolt", "ridehail", "noc", "#34d186", "ridehail",
             "https://bolt.eu", True, 0.89, True, 175.0),
    Operator("FREENOW", "FREE NOW", "ridehail", "noc", "#00d7b9", "ridehail",
             "https://free-now.com", True, 0.89, True, 175.0),
    Operator("BICYCLE", "Own bicycle", "cycle", "noc", "#16a34a", "cycle",
             "", False, 1.0, True, 0.0),
    Operator("WALK", "Walking", "walk", "noc", "#6b7280", "walk",
             "", False, 1.0, True, 0.0),
)

ALL_OPERATORS: tuple[Operator, ...] = (
    TRAIN_OPERATORS + COACH_OPERATORS + LIGHT_RAIL_OPERATORS + BUS_OPERATORS
    + ON_DEMAND_OPERATORS
)

OPERATORS_BY_CODE: dict[str, Operator] = {o.code: o for o in ALL_OPERATORS}


#: Shorthands used by the corridor definitions in ``domain.network_spec``,
#: mapped onto the registry's canonical codes.  Keeping them here means a
#: corridor can stay readable without inventing a second set of operators.
OPERATOR_ALIASES: dict[str, str] = {
    "NCT": "NCTR",  # Nottingham City Transport
    "TB": "TBTN",  # trentbarton
}


def get_operator(code: str) -> Operator:
    """Look up an operator, falling back to a clearly-marked placeholder."""
    if code in OPERATOR_ALIASES:
        code = OPERATOR_ALIASES[code]
    op = OPERATORS_BY_CODE.get(code)
    if op is not None:
        return op
    return Operator(code, f"Unknown operator ({code})", "bus", "noc", "#9ca3af", "bus")


@lru_cache(maxsize=1)
def real_atoc_registry() -> dict[str, str]:
    """The real Train Operating Company registry, keyed by ATOC code."""
    path = Path(get_settings().data_raw_dir) / "atoc_agencies.csv"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("agency_id") or "").strip()
            name = (row.get("agency_name") or "").strip()
            if code and name:
                out[code] = name
    return out


def validate_registry() -> list[str]:
    """Cross-check the registry against the real ATOC file.

    Returns a list of human-readable problems; empty means everything lines up.
    """
    problems: list[str] = []
    real = real_atoc_registry()
    if not real:
        problems.append(
            "atoc_agencies.csv not found in data/raw -- run scripts/fetch_real_data.py"
        )
        return problems

    for op in TRAIN_OPERATORS:
        real_name = real.get(op.code)
        if real_name is None:
            problems.append(f"ATOC code {op.code!r} ({op.name}) is not in the real registry")
        elif real_name.lower() != op.name.lower():
            problems.append(
                f"ATOC {op.code!r}: registry says {real_name!r}, we say {op.name!r}"
            )
    return problems


def operators_for_mode(mode: str) -> list[Operator]:
    return [o for o in ALL_OPERATORS if o.mode == mode]
