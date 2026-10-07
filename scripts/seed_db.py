#!/usr/bin/env python3
"""Load the compiled network into the database.

    python scripts/seed_db.py            # create tables, load, skip if current
    python scripts/seed_db.py --rebuild  # force a reload
    python scripts/seed_db.py --status   # report what is stored

The script is idempotent: it compares a content fingerprint of the feed with
the one recorded in the database and does nothing when they already match.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from backend.app.config import get_settings  # noqa: E402
from backend.app.db import repository as repo  # noqa: E402
from backend.app.db.models import DataSourceRow  # noqa: E402
from backend.app.db.session import init_db, session_scope  # noqa: E402
from backend.app.engine.service import read_feed  # noqa: E402


def _source_rows(net) -> list[dict]:
    """Record where every part of the bundled dataset came from."""
    from backend.app.ingest.real_sources import BUNDLED_FILES, count_rows

    raw_dir = get_settings().data_raw_dir
    rows: list[dict] = []
    for source in BUNDLED_FILES:
        # Count the file on disk rather than trusting a constant: a provenance
        # screen that disagrees with the data it is describing is worse than none.
        rows.append(
            {
                "key": Path(source.name).stem.split(".")[0],
                "name": source.name,
                "url": source.url,
                "licence": source.licence,
                "kind": "real",
                "rows": count_rows(raw_dir / source.name),
                "detail": f"{source.publisher} — {source.description}",
            }
        )
    rows.append(
        {
            "key": "compiled_timetable",
            "name": "MoveIn compiled timetable layer",
            "url": None,
            "licence": "Derived from the real datasets above",
            "kind": "compiled",
            "rows": len(net.trips),
            "detail": (
                "Departure times, headways, run times and fare products are "
                "compiled deterministically from the real stop geography and the "
                "real operator registry. They are not a downloaded feed. Swap in "
                "live BODS/GTFS data by pointing MOVEIN_* at the adapters in "
                "app.ingest."
            ),
        }
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="reload regardless")
    parser.add_argument("--status", action="store_true", help="report and exit")
    args = parser.parse_args()

    settings = get_settings()
    init_db()

    if args.status:
        with session_scope() as session:
            counts = repo.count_rows(session)
            fingerprint, version = repo.stored_fingerprint(session)
        print(f"database : {settings.database_url}")
        print(f"version  : {version or '(empty)'}")
        print(f"fingerprint: {fingerprint or '(empty)'}")
        for key, value in counts.items():
            print(f"  {key:12s} {value:>9,}")
        return 0

    started = time.time()
    # Read the compiled feed from disk.  load_network() would happily return the
    # rows already in the database, which would make seeding a no-op.
    net = read_feed(settings)
    fingerprint = repo.network_fingerprint(net)
    print(f"feed loaded in {time.time() - started:.2f}s  fingerprint={fingerprint}")

    with session_scope() as session:
        if not args.rebuild and repo.network_is_current(session, fingerprint):
            print("database is already up to date; nothing to do (use --rebuild)")
            return 0

        started = time.time()
        counts = repo.store_network(session, net, fingerprint)
        session.execute(DataSourceRow.__table__.delete())
        session.execute(DataSourceRow.__table__.insert(), _source_rows(net))
        print(f"loaded into the database in {time.time() - started:.2f}s")
        for key, value in counts.items():
            print(f"  {key:12s} {value:>9,}")

    with session_scope() as session:
        row = session.execute(
            select(DataSourceRow.kind, DataSourceRow.key)
        ).all()
    kinds: dict[str, int] = {}
    for kind, _key in row:
        kinds[kind] = kinds.get(kind, 0) + 1
    print("data sources recorded:", ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
