"""The server-side mirror of the Flutter ``Field`` type.

A value is never returned bare: it always carries its source and whether the
resident has confirmed it. The API contract is identical to the client model so
the app can round-trip records without translation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generic, Optional, TypeVar

T = TypeVar("T")

# Keep these lists in sync with lib/domain/field.dart
SOURCES = (
    "none",
    "userEntered",
    "userConfirmed",
    "postcodeLookup",
    "officialLookup",
    "billExtraction",
    "estimate",
)

STATUSES = ("missing", "suggested", "confirmed")


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


@dataclass(frozen=True)
class Field(Generic[T]):
    value: Optional[T] = None
    source: str = "none"
    status: str = "missing"
    recorded_at: Optional[datetime] = None
    note: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source not in SOURCES:
            raise ValueError(f"unknown field source: {self.source}")
        if self.status not in STATUSES:
            raise ValueError(f"unknown field status: {self.status}")
        if self.value is None and self.status != "missing":
            raise ValueError("a field without a value must have status 'missing'")
        if self.value is not None and self.status == "missing":
            raise ValueError("a field with a value cannot have status 'missing'")

    @property
    def is_confirmed(self) -> bool:
        return self.status == "confirmed" and self.value is not None

    @property
    def needs_confirmation(self) -> bool:
        return self.status == "suggested" and self.value is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "source": self.source,
            "status": self.status,
            "recordedAt": _iso(self.recorded_at),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls: type["Field"], payload: Optional[dict[str, Any]]) -> "Field":
        if not payload:
            return cls()
        return cls(
            value=payload.get("value"),
            source=payload.get("source", "none"),
            status=payload.get("status", "missing"),
            recorded_at=_parse_dt(payload.get("recordedAt")),
            note=payload.get("note"),
        )

    def confirm(self) -> "Field[T]":
        if self.value is None:
            return self
        return Field(
            value=self.value,
            source="userConfirmed",
            status="confirmed",
            recorded_at=datetime.now(timezone.utc),
            note=self.note,
        )


def suggested(value: T, source: str, note: Optional[str] = None) -> Field[T]:
    return Field(
        value=value,
        source=source,
        status="suggested",
        recorded_at=datetime.now(timezone.utc),
        note=note,
    )


def confirmed(value: T, source: str = "userConfirmed", note: Optional[str] = None) -> Field[T]:
    return Field(
        value=value,
        source=source,
        status="confirmed",
        recorded_at=datetime.now(timezone.utc),
        note=note,
    )


def missing(note: Optional[str] = None) -> Field:
    return Field(note=note)


def _parse_dt(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
