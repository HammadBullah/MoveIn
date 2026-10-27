"""Ordnance Survey Places address lookup.

Called only from the server so the API key never ships in the mobile app.

Things to check before commercial use:
  * the current licensing terms and price for the Places API;
  * whether storing a UPRN and the formatted address is permitted (it is the
    usual pattern, but confirm with the licence);
  * whether results may be cached, and for how long.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests


class AddressLookupError(RuntimeError):
    """Raised when the address provider is unreachable or rejects the request."""


@dataclass(frozen=True)
class AddressResult:
    line1: str
    town: str
    postcode: str
    uprn: Optional[str] = None
    line2: Optional[str] = None
    source: str = "OS Places"

    def to_dict(self) -> dict[str, Optional[str]]:
        return {
            "line1": self.line1,
            "line2": self.line2,
            "town": self.town,
            "postcode": self.postcode,
            "uprn": self.uprn,
            "source": self.source,
        }


def search_postcode(
    postcode: str,
    *,
    api_key: str,
    url: str,
    timeout: float = 6.0,
) -> list[AddressResult]:
    if not api_key:
        raise AddressLookupError("No address provider key is configured.")

    try:
        response = requests.get(
            url,
            params={
                "postcode": postcode,
                "key": api_key,
                "maxresults": 100,
                "dataset": "DPA",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:  # network, DNS, timeout
        raise AddressLookupError(f"Address provider unreachable: {exc}") from exc

    if response.status_code == 401:
        raise AddressLookupError("Address provider rejected the API key.")
    if response.status_code == 404:
        return []
    if not response.ok:
        raise AddressLookupError(
            f"Address provider returned {response.status_code}."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise AddressLookupError("Address provider returned invalid JSON.") from exc

    results: list[AddressResult] = []
    for item in payload.get("results", []):
        dpa = item.get("DPA") or {}
        if not dpa:
            continue
        line1 = dpa.get("ADDRESS", "").split(",")[0].strip()
        building = (dpa.get("BUILDING_NAME") or dpa.get("BUILDING_NUMBER") or "").strip()
        thoroughfare = (dpa.get("THOROUGHFARE_NAME") or "").strip()
        if not line1:
            line1 = " ".join(part for part in (building, thoroughfare) if part)
        results.append(
            AddressResult(
                line1=line1 or "Address",
                line2=None,
                town=(dpa.get("POST_TOWN") or "").strip(),
                postcode=(dpa.get("POSTCODE") or postcode).strip(),
                uprn=(dpa.get("UPRN") or None),
            )
        )
    return results
