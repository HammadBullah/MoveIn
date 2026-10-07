"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..db.session import session_scope
from ..engine.service import JourneyPlanner, get_planner


def planner() -> JourneyPlanner:
    """The process-wide journey planner.

    Loading the compiled feed takes a couple of seconds, so it is built once and
    reused; the engine itself is read-only and safe to share.
    """
    try:
        return get_planner()
    except Exception as exc:  # pragma: no cover - only when the feed is absent
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "the transport network is not loaded; run "
                "scripts/fetch_real_data.py then scripts/seed_db.py"
            ),
        ) from exc


def db() -> Iterator[Session]:
    """A database session, committed on success."""
    with session_scope() as session:
        yield session


#: The device key identifies a client, not a person: Phase 1 has no accounts, so
#: anything stored on a traveller's behalf is keyed by a random id the client
#: generates and keeps.  Phase 2 swaps this for a real authenticated user without
#: changing any of the call sites.
MAX_DEVICE_KEY_LEN = 64


def device_key(
    x_device_key: Annotated[str | None, Header(alias="X-Device-Key")] = None,
) -> str:
    """The client id, from the header.  Missing credentials are a 401."""
    if not x_device_key or not x_device_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Device-Key header is required for this endpoint",
        )
    return _validated_device_key(x_device_key)


def optional_device_key(
    x_device_key: Annotated[str | None, Header(alias="X-Device-Key")] = None,
) -> str | None:
    """The client id when a request body also carries one.

    Two ways of saying the same thing is one too many, so the header wins when
    both are present and the body field is the fallback for clients that cannot
    set headers.
    """
    return _validated_device_key(x_device_key) if x_device_key else None


def _validated_device_key(value: str) -> str:
    key = value.strip()
    if len(key) > MAX_DEVICE_KEY_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"X-Device-Key must be {MAX_DEVICE_KEY_LEN} characters or fewer",
        )
    return key


def resolve_device(header_key: str | None, body_key: str | None) -> str:
    """The device a write applies to, or a 401 when neither says."""
    key = header_key or (body_key or "").strip() or None
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="a device key is required (X-Device-Key header or device_key body)",
        )
    return key


PlannerDep = Annotated[JourneyPlanner, Depends(planner)]
DbDep = Annotated[Session, Depends(db)]
DeviceDep = Annotated[str, Depends(device_key)]
OptionalDeviceDep = Annotated[str | None, Depends(optional_device_key)]
