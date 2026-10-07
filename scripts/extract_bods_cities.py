#!/usr/bin/env python3
"""Extract published BODS timetable data with the DfT's own extractor.

The Bus Open Data Service publishes `BODSDataExtractor`, the client the
Department for Transport writes for this exact job: it reads the BODS API for
the datasets that match a filter and then downloads and parses the
TransXChange files inside them, so what comes out is the operator's published
timetable -- service lines, stops and times -- rather than a shape.

It needs a BODS API key: the dataset *catalogue* is key-gated, even though the
files behind it are not.  So this runs where the key can be supplied and the
network exists -- a GitHub runner, with the key as a repository secret
(`MOVEIN_BODS_API_KEY`).  No key means no extraction; the keyless route in
`ops/fetch-bods.sh` (regional bulk GTFS) still covers route shapes.

Usage::

    MOVEIN_BODS_API_KEY=... python scripts/extract_bods_cities.py \
        --atco 330 --atco 339 --limit 60 --out backend/data/raw/bods_extract

The ATCO prefixes are the first three characters of the stop codes published in
NaPTAN: 330 Nottinghamshire and 339 Nottingham city, for instance.  The list the
runner uses is derived from the NaPTAN extract MoveIn already holds
(`backend/data/raw/naptan_regional.csv.gz`), so the areas asked for are the areas
the app models.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ATCO area prefixes for the cities MoveIn searches: taken from the published
# NaPTAN extract, where every stop's code begins with its area.
CITY_ATCO = [
    "330",  # Nottinghamshire
    "339",  # Nottingham
    "269",  # Leicester
    "260",  # Leicestershire
    "109",  # Derby
    "100",  # Derbyshire
    "430",  # West Midlands (Birmingham, Coventry, Wolverhampton)
    "420",  # Warwickshire (Nuneaton, Rugby)
    "450",  # West Yorkshire (Leeds, Bradford, Wakefield)
    "370",  # South Yorkshire (Sheffield, Doncaster)
    "180",  # Greater Manchester
    "049",  # Milton Keynes
    "059",  # Peterborough
    "360",  # Slough
    "390",  # Reading
    "490",  # London
]


def api_key(explicit: str | None) -> str:
    for candidate in (explicit, os.environ.get("MOVEIN_BODS_API_KEY"), os.environ.get("BODS_API_KEY")):
        if candidate:
            return candidate.strip()
    raise SystemExit(
        "No BODS API key.  The catalogue needs one: set MOVEIN_BODS_API_KEY\n"
        "(on a runner, that is the repository secret of the same name)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", default=None, help="BODS API key (else the environment)")
    parser.add_argument("--atco", action="append", default=[], help="ATCO area prefix, repeatable")
    parser.add_argument("--search", default=None, help="Free-text filter on name, description or area")
    parser.add_argument("--noc", action="append", default=[], help="National operator code, repeatable")
    parser.add_argument("--limit", type=int, default=200, help="How many datasets to read")
    parser.add_argument("--stop-level", action="store_true", help="Also extract per-stop timetables")
    parser.add_argument("--out", type=Path, default=ROOT / "backend/data/raw/bods_extract")
    args = parser.parse_args()

    key = api_key(args.api_key)

    try:
        from BODSDataExtractor.extractor import TimetableExtractor
    except ImportError:
        raise SystemExit(
            "BODSDataExtractor is not installed.  On a runner:\n"
            "  pip install BODSDataExtractor"
        ) from None

    atco = args.atco or CITY_ATCO
    print(f"=== {datetime.now(timezone.utc).isoformat(timespec='seconds')} BODS extraction ===")
    print(f"areas: {len(atco)} ATCO prefixes, {len(set(atco))} unique")
    print(f"limit: {args.limit} datasets, stop level: {args.stop_level}")

    extractor = TimetableExtractor(
        api_key=key,
        limit=args.limit,
        status="published",
        atco_code=atco,
        nocs=args.noc or None,
        search=args.search,
        service_line_level=True,
        stop_level=args.stop_level,
    )

    if extractor.metadata is None:
        raise SystemExit("The API returned no datasets.  A 401 here means the key was rejected.")

    args.out.mkdir(parents=True, exist_ok=True)
    datasets = extractor.metadata
    datasets.to_csv(args.out / "datasets.csv.gz", index=False, compression="gzip")
    print(f"datasets:      {len(datasets):,}")

    summary: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "scripts/extract_bods_cities.py (DfT BODSDataExtractor)",
        "licence": "Open Government Licence v3.0 (Bus Open Data Service, DfT)",
        "source": "BODS API + the TransXChange published with each dataset",
        "filters": {"atco": atco, "nocs": args.noc or None, "search": args.search, "limit": args.limit},
        "datasets": len(datasets),
    }

    for attribute, filename in (
        ("service_line_extract", "service_lines.csv.gz"),
        ("stop_level_extract", "stops.csv.gz"),
    ):
        frame = getattr(extractor, attribute, None)
        if frame is None or getattr(frame, "empty", True):
            continue
        frame.to_csv(args.out / filename, index=False, compression="gzip")
        size_mb = (args.out / filename).stat().st_size / 1_048_576
        print(f"{filename:22} {len(frame):>8,} rows  ({size_mb:.1f} MB gzipped)")
        summary[attribute] = len(frame)

    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {args.out.relative_to(ROOT)}/summary.json")


if __name__ == "__main__":
    main()
