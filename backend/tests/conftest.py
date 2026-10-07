"""Shared fixtures.

The suite runs against the compiled feed that ships in ``backend/data``.  The
whole point of MoveIn is that the network is data, so testing it against a
synthetic fixture would miss exactly the class of bug that matters -- a corridor
that does not resolve, a timetable with no Sunday service, a fare that cannot be
sold.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.engine.service import JourneyPlanner, load_network  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def planner(settings) -> JourneyPlanner:
    """One planner for the whole session: building it costs a couple of seconds."""
    return JourneyPlanner(load_network(settings), settings)


@pytest.fixture(scope="session")
def graph(planner):
    return planner.graph


@pytest.fixture(scope="session")
def departure() -> datetime:
    """A Wednesday inside the compiled feed's service window."""
    window_start = None
    try:
        from backend.app.ingest.network_compiler import SERVICE_START

        window_start = SERVICE_START
    except Exception:  # pragma: no cover
        pass
    base = window_start or datetime.now().date()
    day = base + timedelta(days=(2 - base.weekday()) % 7 or 7)
    if day <= base:
        day += timedelta(days=7)
    return datetime.combine(day, datetime.min.time()).replace(hour=9)


@pytest.fixture(scope="session")
def client(planner):
    """A TestClient bound to the real app, with the planner already warm."""
    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as test_client:
        yield test_client
