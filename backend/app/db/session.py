"""Database engine, sessions and schema creation.

The connection string comes from settings, so the same code runs against
PostgreSQL (``MOVEIN_DATABASE_URL=postgresql+psycopg://...``) or the embedded
SQLite file the prototype ships with.  SQLite gets a few pragmas that matter for
a read-heavy workload: WAL journalling, foreign keys, and an in-memory page
cache measured in megabytes rather than pages.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from .models import Base


def _configure_sqlite(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")  # 64 MB page cache
        cursor.execute("PRAGMA temp_store=MEMORY")
    finally:
        cursor.close()


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    """Return a cached engine for the configured database."""
    settings = get_settings()
    url = url or settings.database_url
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _configure_sqlite)
    return engine


@lru_cache(maxsize=4)
def get_sessionmaker(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(url), expire_on_commit=False, future=True)


def init_db(url: str | None = None) -> None:
    """Create every table that does not exist yet."""
    Base.metadata.create_all(get_engine(url))


def drop_db(url: str | None = None) -> None:
    """Drop every table.  Only ever used by tests and the seed script."""
    Base.metadata.drop_all(get_engine(url))


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    """Transactional scope: commits on success, rolls back on failure."""
    session = get_sessionmaker(url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def health(url: str | None = None) -> dict:
    """A cheap readiness probe for the API's ``/health`` endpoint."""
    engine = get_engine(url)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"database": engine.dialect.name, "url": engine.url.render_as_string()}
