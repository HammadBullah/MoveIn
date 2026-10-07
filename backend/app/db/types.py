"""Portable spatial column types.

MoveIn's production target is PostgreSQL + PostGIS, but the prototype has to run
on an embedded database with no external services.  These column types keep the
schema identical in both cases:

* on PostgreSQL with ``geoalchemy2`` installed they become real PostGIS
  ``geography`` columns, so ``ST_DWithin`` and GiST indexes work as designed;
* everywhere else they degrade to WKT text, and the engine's in-process
  :class:`~app.ingest.geo.GridIndex` does the same job.

Switching storage therefore never changes the domain model or the engine.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


class Geography(TypeDecorator):
    """A WGS84 point or line, stored as PostGIS geography or WKT text."""

    impl = Text
    cache_ok = True

    def __init__(self, geometry_type: str = "POINT", srid: int = 4326) -> None:
        super().__init__()
        self.geometry_type = geometry_type.upper()
        self.srid = srid

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            try:  # pragma: no cover - only runs against a PostGIS deployment
                from geoalchemy2 import Geography as PostgisGeography

                return dialect.type_descriptor(
                    PostgisGeography(geometry_type=self.geometry_type, srid=self.srid)
                )
            except ImportError:
                pass
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return None
        if isinstance(value, (tuple, list)) and len(value) == 2:
            lon, lat = value
            return f"SRID={self.srid};POINT({lon} {lat})"
        return value

    def process_result_value(self, value: Any, dialect):  # type: ignore[no-untyped-def]
        return value
