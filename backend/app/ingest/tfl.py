"""Transport for London Unified API adapter.

TfL's Unified API is the authoritative source for London: tube, DLR, Overground,
Elizabeth line, buses and cycle hire, with arrivals and line status.  It is not
reachable from the environment this prototype was built in, so the parsers are
complete and fixture-tested while the HTTP calls are not.

What MoveIn takes from TfL, and why:

* **Stations and their coordinates** -- so the tube network is built from TfL's
  own station list rather than name-matching NaPTAN labels.
* **Line routes** -- the ordered stop sequence of a line, which is exactly what
  a MoveIn corridor needs (``Corridor.stops``).
* **Line status** -- disruptions for ``/api/live/alerts``.

The Unified API needs no key for light use; a key raises the rate limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

TFL_BASE_URL = "https://api.tfl.gov.uk"
TFL_APP_KEY_ENV = "MOVEIN_TFL_APP_KEY"

#: TfL's ``modeName`` values, mapped onto MoveIn's modes.
MODE_BY_TFL_NAME = {
    "tube": "metro",
    "elizabeth-line": "metro",
    "overground": "metro",
    "dlr": "metro",
    "tram": "tram",
    "bus": "bus",
    "coach": "coach",
    "national-rail": "rail",
    "river-bus": "ferry",
    "cable-car": "metro",
    "walking": "walk",
    "cycle": "cycle",
    "cycle-hire": "cycle",
}


@dataclass
class TflClient:
    """A thin client for the Unified API."""

    app_key: str = ""
    base_url: str = TFL_BASE_URL
    timeout_s: float = 30.0

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"app_key": self.app_key} if self.app_key else {}
        params.update(extra or {})
        return params

    def _get(self, path: str, **params: Any) -> Any:
        import httpx

        with httpx.Client(base_url=self.base_url, timeout=self.timeout_s) as client:
            response = client.get(
                path, params=self._params(params), follow_redirects=True
            )
            response.raise_for_status()
            return response.json()

    def stop_points(self, modes: str = "tube,dlr,overground,elizabeth-line,tram") -> list[dict]:
        """Every stop of the given modes, with coordinates."""
        payload = self._get("/StopPoint/Mode/" + modes)
        return [parse_stop_point(item) for item in payload.get("stopPoints", [])]

    def line_stops(self, line_id: str) -> list[str]:
        """The ordered stop-point ids of a line, in each direction."""
        payload = self._get(f"/Line/{line_id}/Route/Sequence/Inbound")
        return parse_route_sequence(payload)

    def line_status(self) -> list[dict]:
        return [parse_line_status(item) for item in self._get("/Line/Mode/tube/Status")]


def parse_stop_point(item: dict) -> dict:
    """One ``StopPoint`` payload as a MoveIn stop-shaped dict."""
    return {
        "id": item.get("id") or item.get("naptanId") or "",
        "naptan_id": item.get("naptanId", ""),
        "name": item.get("commonName", ""),
        "lat": item.get("lat"),
        "lon": item.get("lon"),
        "modes": [
            MODE_BY_TFL_NAME.get(mode, mode)
            for mode in item.get("modes", [])
            if mode in MODE_BY_TFL_NAME
        ],
        "zone": item.get("zone"),
        "interchange": bool(item.get("children")) or item.get("stopType") == "CompactStation",
        "step_free": any(
            prop.get("key") == "StepFreeAccess" and prop.get("value") == "true"
            for prop in item.get("additionalProperties", [])
        ),
    }


def parse_route_sequence(payload: dict) -> list[str]:
    """The ordered stop ids of a line, de-duplicated while staying in order."""
    ordered: list[str] = []
    for section in payload.get("stopPointSequences", []):
        for stop in section.get("stopPoint", []):
            stop_id = stop.get("id") or stop.get("naptanId")
            if stop_id and stop_id not in ordered:
                ordered.append(stop_id)
    return ordered


def parse_line_status(item: dict) -> dict:
    """A line status as a MoveIn disruption."""
    statuses = item.get("lineStatuses") or [{}]
    status = statuses[0]
    # TfL grades 10 = good service down to 0 = suspended; below 6 is a real
    # disruption rather than a planned closure note.
    severity_code = status.get("statusSeverity", 10)
    if severity_code >= 10:
        level = "info"
    elif severity_code >= 6:
        level = "warning"
    else:
        level = "severe"
    return {
        "line": item.get("id", ""),
        "line_name": item.get("name", ""),
        "severity": level,
        "reason": status.get("reason") or status.get("statusSeverityDescription", ""),
        "valid_from": _iso(status.get("validityPeriod", {}).get("fromDate")),
        "valid_to": _iso(status.get("validityPeriod", {}).get("toDate")),
    }


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
