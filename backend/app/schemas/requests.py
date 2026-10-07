"""Request bodies accepted by the API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..engine.journeys import Preference


class TravellerIn(BaseModel):
    """Who is travelling, which is what fares actually depend on."""

    adults: int = Field(default=1, ge=0, le=9)
    children: int = Field(default=0, ge=0, le=9)
    #: Railcard, Network Railcard or 16-25/26-30 Railcard.
    railcard: bool = False
    #: NUS/student status, which some operators discount.
    student: bool = False
    #: Traveller cannot use steps or stairs.
    step_free: bool = False
    #: Hard ceiling on the walking distance they will accept, in metres.
    max_walk_m: int | None = Field(default=None, ge=0, le=8000)


class SearchOptionsIn(BaseModel):
    max_legs: int | None = Field(default=None, ge=1, le=8)
    #: Transit modes the traveller will use (``bus``, ``rail``, ``coach``,
    #: ``tram``, ``metro``, ``taxi``, ``ridehail``, ``ferry``).  Omit for all.
    modes: list[str] | None = Field(default=None, max_length=12)
    #: Hard budget on the total fare, in pounds.
    max_price: float | None = Field(default=None, ge=0, le=5000)
    step_free_only: bool = False
    #: How many half-hourly departure slots to explore from the requested time.
    departure_sweep: int | None = Field(default=None, ge=1, le=12)
    #: Include a taxi/ride-hail first mile when the walk to a hub is long.
    allow_on_demand: bool = True
    #: Include journeys that are entirely walked, when the trip is short.
    include_walking_only: bool = True


class JourneySearchRequest(BaseModel):
    """``POST /api/journeys/search``."""

    origin: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=200)
    #: ISO 8601.  When omitted the search uses "now".
    departure: datetime | None = None
    #: Journey must arrive by this time (reverse search).
    arrive_by: datetime | None = None
    preference: Preference = Preference.BEST_VALUE
    traveller: TravellerIn = Field(default_factory=TravellerIn)
    options: SearchOptionsIn = Field(default_factory=SearchOptionsIn)
    #: Longest walk, in minutes, the traveller will accept in one go.  Tightening
    #: this is the difference between "plan me a journey" and "plan me a journey
    #: I will actually take": nobody walks 25 minutes between two vehicles.
    max_walk_minutes: int | None = Field(default=None, ge=2, le=60)
    #: Optional opaque client id, used to scope saved journeys and alerts.
    device_key: str | None = Field(default=None, max_length=64)
    #: How many journeys to return, after ranking.
    limit: int = Field(default=12, ge=1, le=40)

    @field_validator("preference", mode="before")
    @classmethod
    def _coerce_preference(cls, value):  # type: ignore[no-untyped-def]
        if isinstance(value, str):
            key = value.strip().lower().replace("-", "_").replace(" ", "_")
            aliases = {
                "best": "best_value",
                "value": "best_value",
                "balanced": "best_value",
                "green": "lowest_emissions",
                "eco": "lowest_emissions",
                "co2": "lowest_emissions",
                "walking": "least_walking",
                "accessible": "accessible",
                "step_free": "accessible",
                "fewest_interchanges": "fewest_changes",
                "changes": "fewest_changes",
                "cheap": "cheapest",
                "quickest": "fastest",
            }
            key = aliases.get(key, key)
            try:
                return Preference(key)
            except ValueError as exc:  # pragma: no cover - guarded by FastAPI too
                raise ValueError(f"unknown preference: {value!r}") from exc
        return value


class SaveJourneyRequest(BaseModel):
    label: str | None = Field(default=None, max_length=180)
    origin: str
    destination: str
    preference: Preference = Preference.BEST_VALUE
    #: Optional: the X-Device-Key header is the usual way to say this, and
    #: wins when both are sent.
    device_key: str | None = Field(default=None, max_length=64)


class PriceAlertRequest(BaseModel):
    origin: str
    destination: str
    preference: Preference = Preference.CHEAPEST
    target_price: float | None = Field(default=None, ge=0, le=2000)
    #: Optional: the X-Device-Key header is the usual way to say this, and
    #: wins when both are sent.
    device_key: str | None = Field(default=None, max_length=64)


class TrackJourneyRequest(BaseModel):
    #: Optional: the X-Device-Key header is the usual way to say this, and
    #: wins when both are sent.
    device_key: str | None = Field(default=None, max_length=64)
    journey_id: str = Field(max_length=80)
    #: The serialised journey the traveller is on, as returned by the search.
    payload: dict
    preference: Preference = Preference.BEST_VALUE


class Coordinate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


LegKind = Literal["transit", "walk", "on_demand"]
