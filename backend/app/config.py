"""Application settings.

MoveIn runs against PostgreSQL + PostGIS in production and against an
embedded SQLite database by default so the prototype is runnable with no
external services.  The spatial index is abstracted (see
``app.ingest.geo.GridIndex``) so switching to PostGIS ``ST_DWithin`` only
changes the storage layer, not the engine.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else default


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MOVEIN_", env_file=".env", extra="ignore"
    )

    app_name: str = "MoveIn Journey Planner"
    version: str = "0.1.0"
    debug: bool = False

    # --- Storage ---------------------------------------------------------
    #: SQLAlchemy URL.  Defaults to a SQLite file inside backend/data.
    database_url: str = Field(
        default_factory=lambda: f"sqlite:///{BACKEND_ROOT / 'data' / 'movein.db'}"
    )
    #: When true, PostGIS-specific DDL and queries are used instead of the
    #: portable fallbacks.
    use_postgis: bool = False
    #: Optional Redis URL for the journey-search cache.
    redis_url: str | None = None

    # --- Data ------------------------------------------------------------
    data_raw_dir: Path = Field(default_factory=lambda: BACKEND_ROOT / "data" / "raw")
    data_generated_dir: Path = Field(
        default_factory=lambda: BACKEND_ROOT / "data" / "generated"
    )

    # --- Live feed credentials (all optional; adapters degrade gracefully)
    bods_api_key: str | None = None
    tfl_app_key: str | None = None

    # --- Engine tuning ---------------------------------------------------
    #: Maximum walking distance from an origin/destination to a stop.
    max_access_walk_m: int = 2000
    #: Maximum walking distance when changing between stops.
    max_transfer_walk_m: int = 900
    #: Maximum number of public-transport legs in a returned journey.
    max_legs: int = 5
    #: Minimum connection time at a stop served by more than one operator.
    min_connection_s: int = 180
    #: How many Pareto-optimal journeys to keep before archetype selection.
    max_candidates: int = 40
    #: Departure-window sweep: how many alternative departure times to try.
    departure_sweep: int = 3
    #: Search horizon -- stop expanding after this much elapsed time.
    max_journey_duration_s: int = 8 * 3600
    #: Cache TTL for identical journey searches, in seconds.
    search_cache_ttl_s: int = 900

    # --- Pricing assumptions (documented in docs/FARES.md) ---------------
    #: Railcard / student discount applied when a traveller profile asks for it.
    railcard_discount: float = 0.34
    #: Student discount applied to bus/coach fares.
    student_discount: float = 0.25
    #: Value of one minute of travel time, in GBP, used by the best-value score.
    value_of_time_gbp_per_min: float = 0.12
    #: Value of one interchange, in GBP, used by the best-value score.
    interchange_penalty_gbp: float = 1.40
    #: Value of 100 m of walking, in GBP, used by the best-value score.
    walking_penalty_gbp_per_100m: float = 0.18


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_raw_dir = _env_path("MOVEIN_DATA_RAW_DIR", settings.data_raw_dir)
    settings.data_generated_dir = _env_path(
        "MOVEIN_DATA_GENERATED_DIR", settings.data_generated_dir
    )
    return settings


def reset_settings_cache() -> None:
    """Clear the settings cache (used by tests that patch the environment)."""
    get_settings.cache_clear()
