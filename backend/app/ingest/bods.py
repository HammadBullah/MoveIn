"""DfT Bus Open Data Service adapter.

BODS publishes every English bus timetable, fare and live vehicle position under
the Open Government Licence.  It is the single most valuable open dataset for a
project like this, and it is where the *compiled* timetable layer in
``network_compiler.py`` is designed to be replaced by real data.

The three feeds and what happens to them:

======================  =====================================================
BODS endpoint           MoveIn representation
======================  =====================================================
``/api/v1/dataset/``     GTFS (or TransXChange) → :func:`backend.app.ingest.gtfs.read_gtfs`
``/api/v1/fares/dataset/`` GTFS-Fares → ``fare_attributes`` / ``fare_rules``
``/api/v1/datafeed/``    SIRI-VM XML → :func:`parse_siri_vm` → ``LiveVehicle``
======================  =====================================================

``data.bus-data.dft.gov.uk`` is not reachable from the environment this
prototype was built in, so nothing here has run against the live service.  The
*parsers* are complete and are unit-tested against recorded payloads, which is
the part that would break if the formats changed; only :class:`BodsClient`'s
network calls are unexercised, and those are four lines of ``httpx`` each.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from ..domain.models import Mode, TransportNetwork
from .gtfs import read_gtfs

BODS_BASE_URL = "https://data.bus-data.dft.gov.uk"

#: BODS rate-limits anonymous traffic hard; a key is free on registration.
API_KEY_ENV = "MOVEIN_BODS_API_KEY"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@dataclass
class BodsClient:
    """A thin client for the three BODS endpoints.

    Deliberately thin: it fetches bytes and hands them to a parser.  Everything
    that decides what the bytes *mean* lives in a module-level function so it can
    be tested without a network.
    """

    api_key: str = ""
    base_url: str = BODS_BASE_URL
    timeout_s: float = 60.0

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"bearer {self.api_key}"} if self.api_key else {}

    def _get(self, path: str, **params: Any) -> "Any":
        import httpx  # imported lazily so the adapter is optional

        query = {k: v for k, v in params.items() if v is not None}
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_s) as client:
            response = client.get(
                path, params=query, headers=self._headers(), follow_redirects=True
            )
            response.raise_for_status()
            return response

    # -- discovery --------------------------------------------------------
    def datasets(
        self,
        *,
        region: str | None = None,
        status: str = "published",
        limit: int = 100,
    ) -> list[dict]:
        """Bus timetable datasets, page by page, newest first."""
        out: list[dict] = []
        offset = 0
        while len(out) < limit:
            page = self._get(
                "/api/v1/dataset/",
                limit=min(100, limit - len(out)),
                offset=offset,
                status=status,
                adminArea=region,
            ).json()
            results = page.get("results", [])
            if not results:
                break
            out.extend(results)
            offset += len(results)
        return out

    def fetch_timetable(self, dataset_id: int) -> TransportNetwork:
        """Download one timetable dataset as GTFS and read it.

        ``/api/v1/dataset/{id}/download`` serves a GTFS zip for every dataset
        BODS publishes, which is why MoveIn's reader only had to be written
        once for both GTFS and BODS.
        """
        payload = self._get(f"/api/v1/dataset/{dataset_id}/download").content
        return read_gtfs(io.BytesIO(payload), name=f"bods:{dataset_id}")

    def fetch_fares(self, dataset_id: int) -> TransportNetwork:
        """Download one fares dataset (GTFS-Fares) and read it.

        BODS also publishes NeTEx, which is a much larger format; the GTFS-Fares
        variant carries the same ``fare_attributes``/``fare_rules`` that the fare
        engine already consumes, so it is the one wired up here.
        """
        payload = self._get(f"/api/v1/fares/dataset/{dataset_id}/download").content
        return read_gtfs(io.BytesIO(payload), name=f"bods-fares:{dataset_id}")

    def fetch_vehicle_positions(self, *, bounding_box: str | None = None) -> str:
        """The SIRI-VM document for every currently running vehicle."""
        response = self._get("/api/v1/datafeed/", boundingBox=bounding_box)
        return response.text


# ---------------------------------------------------------------------------
# SIRI-VM
# ---------------------------------------------------------------------------

#: SIRI is namespaced XML, and publishers vary in how they prefix it, so every
#: lookup ignores the namespace rather than hard-coding one.
_SIRI_TAGS = {
    "journey": "MonitoredVehicleJourney",
    "vehicle": "VehicleRef",
    "line_ref": "LineRef",
    "line_name": "PublishedLineName",
    "direction": "DirectionRef",
    "operator": "OperatorRef",
    "origin_ref": "OriginRef",
    "origin_name": "OriginName",
    "destination_ref": "DestinationRef",
    "destination_name": "DestinationName",
    "location": "VehicleLocation",
    "bearing": "Bearing",
    "speed": "Velocity",
    "delay": "Delay",
    "monitored": "Monitored",
    "next_stop": "MonitoredCall",
    "recorded": "RecordedAtTime",
    "valid_until": "ValidUntilTime",
    "block_ref": "BlockRef",
    "occupancy": "Occupancy",
    "framed": "FramedVehicleJourneyRef",
    "dated": "DatedVehicleJourneyRef",
}


def _local(tag: str) -> str:
    """``{namespace}VehicleRef`` -> ``VehicleRef``."""
    return tag.rsplit("}", 1)[-1]


def _find(element: ET.Element, name: str) -> ET.Element | None:
    for child in element.iter():
        if _local(child.tag) == name:
            return child
    return None


def _text(element: ET.Element, name: str) -> str:
    found = _find(element, name)
    if found is None or found.text is None:
        return ""
    return found.text.strip()


def _float(element: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(_text(element, name))
    except (TypeError, ValueError):
        return default


def _uk_zone():
    """UK local time, or a fixed offset if the tz database is unavailable."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Europe/London")
    except Exception:  # pragma: no cover - only on a machine with no tzdata
        from datetime import timedelta, timezone

        return timezone(timedelta(hours=1))


def _parse_iso(value: str) -> datetime | None:
    """A SIRI timestamp as naive UK local time, matching the timetable.

    Converting with ``astimezone()`` and no argument would use the *machine's*
    timezone -- which is how "09:14 London" becomes 08:14 on a UTC server and
    every live vehicle appears an hour early.  MoveIn is a UK product, so the
    conversion is explicit.
    """
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_uk_zone()).replace(tzinfo=None)
    return parsed


def _parse_iso_duration(value: str) -> int | None:
    """``PT2M30S`` -> 150 seconds; ``-PT45S`` -> -45.

    SIRI reports delay as a duration, and a vehicle *ahead* of schedule reports
    the negative one.  Reading the sign after the ``PT`` test -- or not at all --
    turns "running early" into "running late", which is the opposite advice.
    """
    if not value:
        return None
    text = value.strip().upper()
    sign = -1 if text.startswith("-") else 1
    text = text.lstrip("+-")
    if not text.startswith("PT"):
        return None
    total = 0.0
    number = ""
    for char in text[2:]:
        if char.isdigit() or char == ".":
            number += char
            continue
        if not number:
            continue
        amount = float(number)
        number = ""
        if char == "H":
            total += amount * 3600
        elif char == "M":
            total += amount * 60
        elif char == "S":
            total += amount
    return int(round(total * sign))


def iter_vehicle_activities(xml_text: str) -> Iterator[ET.Element]:
    """Every ``VehicleActivity`` in a SIRI-VM document."""
    root = ET.fromstring(xml_text)
    for element in root.iter():
        if _local(element.tag) == "VehicleActivity":
            yield element


def parse_siri_vm(xml_text: str) -> list[dict]:
    """Parse SIRI-VM into plain dicts ready to become ``LiveVehicle`` objects.

    Returns dicts rather than ``LiveVehicle`` so the ingest layer does not depend
    on the service layer; :func:`backend.app.services.realtime.from_siri_vm`
    converts them.
    """
    vehicles: list[dict] = []
    for activity in iter_vehicle_activities(xml_text):
        journey = _find(activity, _SIRI_TAGS["journey"])
        if journey is None:
            continue
        vehicle_ref = _text(journey, _SIRI_TAGS["vehicle"]) or _text(
            activity, _SIRI_TAGS["vehicle"]
        )
        location = _find(journey, _SIRI_TAGS["location"])
        lat = lon = None
        if location is not None:
            lat = _float(location, "Latitude", default=float("nan"))
            lon = _float(location, "Longitude", default=float("nan"))
            if lat != lat or lon != lon:  # NaN: the vehicle has no fix
                lat = lon = None
        if lat is None or lon is None:
            continue

        journey_ref = _find(journey, _SIRI_TAGS["framed"])
        trip_id = _text(journey_ref, _SIRI_TAGS["dated"]) if journey_ref is not None else ""
        next_call = _find(journey, _SIRI_TAGS["next_stop"])
        next_stop_ref = _text(next_call, "StopPointRef") if next_call is not None else ""
        next_stop_name = _text(next_call, "StopPointName") if next_call is not None else ""
        expected = _text(next_call, "ExpectedDepartureTime") if next_call is not None else ""

        speed = _float(journey, _SIRI_TAGS["speed"], default=0.0)
        vehicles.append(
            {
                "vehicle_id": vehicle_ref or trip_id or "unknown",
                "trip_id": trip_id,
                "route_id": _text(journey, _SIRI_TAGS["line_ref"]),
                "route_name": _text(journey, _SIRI_TAGS["line_name"]),
                "operator_code": _text(journey, _SIRI_TAGS["operator"]),
                "direction": _text(journey, _SIRI_TAGS["direction"]),
                "headsign": _text(journey, _SIRI_TAGS["destination_name"])
                or _text(journey, _SIRI_TAGS["destination_ref"]),
                "lat": lat,
                "lon": lon,
                "bearing": _float(journey, _SIRI_TAGS["bearing"]),
                # SIRI reports metres per second; some publishers report km/h.
                "speed_mps": speed / 3.6 if speed > 55 else speed,
                "delay_s": _parse_iso_duration(_text(journey, _SIRI_TAGS["delay"])) or 0,
                "occupancy": _text(journey, _SIRI_TAGS["occupancy"]),
                "next_stop_id": next_stop_ref,
                "next_stop_name": next_stop_name,
                "recorded_at": _parse_iso(
                    _text(activity, _SIRI_TAGS["recorded"])
                    or _text(journey, _SIRI_TAGS["recorded"])
                ),
                "expected_departure": _parse_iso(expected),
                "monitored": _text(journey, _SIRI_TAGS["monitored"]).lower() == "true",
            }
        )
    return vehicles


# ---------------------------------------------------------------------------
# TransXChange
# ---------------------------------------------------------------------------


def parse_transxchange_routes(xml_text: str) -> list[dict]:
    """The routes and their operators out of a TransXChange document.

    TransXChange is what BODS stores natively.  MoveIn consumes GTFS, so this
    exists for the cases where only TransXChange is published: it extracts the
    route identity (line name, operator, origin/destination) without attempting
    the whole timetable model.
    """
    root = ET.fromstring(xml_text)
    operators: dict[str, str] = {}
    for operator in root.iter():
        if _local(operator.tag) != "Operator":
            continue
        code = _text(operator, "NationalOperatorCode") or _text(operator, "OperatorCode")
        name = _text(operator, "OperatorShortName") or _text(operator, "OperatorNameOnLicence")
        if code:
            operators[code] = name or code

    routes: list[dict] = []
    for route in root.iter():
        if _local(route.tag) != "Route":
            continue
        stops = [
            _text(node, "StopPointRef")
            for node in route.iter()
            if _local(node.tag) == "RouteLink"
        ]
        routes.append(
            {
                "route_id": route.attrib.get("id", ""),
                "line_name": _text(route, "LineName"),
                "description": _text(route, "Description"),
                "operator_codes": list(operators),
                "sections": len(stops),
            }
        )
    for section in root.iter():
        if _local(section.tag) != "JourneyPatternSection":
            continue
    return routes


def mode_for_vehicle(route_id: str, route_name: str = "") -> Mode:
    """Guess the mode of a BODS vehicle.

    BODS covers buses and coaches only, and the line name is the giveaway: a
    service numbered in the 900s with a long-distance destination is a coach.
    """
    text = f"{route_id} {route_name}".lower()
    if text.startswith(("nx", "mega", "flix", "900", "9")):
        return Mode.COACH
    return Mode.BUS
