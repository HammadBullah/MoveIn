#!/usr/bin/env python3
"""Re-fetch the operator route geometries the real bus network is built from.

Six operator areas of real UK bus network, traced from the operators' own
TransXChange publications on the DfT Bus Open Data Service and mirrored as
GeoJSON.  Each file's properties name the BODS XML it came from, which is why
this source is worth holding even though it is a mirror: it is traceable.

The raw files are ~47 MB, so they are not committed -- this script puts them
back, and `scripts/import_real_bus_routes.py` turns them into the 0.2 MB
compiled file the app actually reads.

Usage::

    python scripts/fetch_real_bus_routes.py            # into backend/data/raw/real_bus_routes
    python scripts/fetch_real_bus_routes.py --force    # re-download everything
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "backend/data/raw/real_bus_routes"

REPO = "ukinteractivebusmap/ukinteractivebusmap.github.io"
RAW = f"https://raw.githubusercontent.com/{REPO}/HEAD/data"

#: The operator areas the mirror holds.  The trailing file is the big one.
FILES = (
    "Redline_OP71.geojson",
    "Arriva_Beds_and_Bucks_OP58.geojson",
    "Arriva_Herts_and_Essex_OP50.geojson",
    "Red_Rose_Travel_OP362.geojson",
    "stagecoach_oxford_routes.geojson",
    "stagecoach_midlands_routes.geojson",
)


def fetch(name: str, out_dir: Path, *, force: bool) -> bool:
    target = out_dir / name
    if target.exists() and not force:
        print(f"  {name:44} already here")
        return False
    print(f"  {name:44} downloading...")
    # raw.githubusercontent is not always reachable; the GitHub API serves the
    # same bytes and is the endpoint that works in restricted environments.
    api = f"https://api.github.com/repos/{REPO}/contents/data/{name}"
    request = urllib.request.Request(api, headers={"Accept": "application/vnd.github.raw"})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = response.read()
    except Exception as error:  # noqa: BLE001 - reported, not swallowed
        print(f"  {name:44} FAILED: {error}")
        return False
    target.write_bytes(payload)
    size_mb = len(payload) / 1_048_576
    print(f"  {name:44} {size_mb:.1f} MB")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"Fetching operator route geometry into {args.out.relative_to(ROOT)}")
    fetched = sum(1 for name in FILES if fetch(name, args.out, force=args.force))

    (args.out / "SOURCES.json").write_text(
        json.dumps(
            {
                "mirror": f"https://github.com/{REPO}",
                "upstream": (
                    "Operator TransXChange publications on the DfT Bus Open Data "
                    "Service (data.bus-data.dft.gov.uk), traced to GTFS stop sequences"
                ),
                "licence": "Open Government Licence v3.0",
                "files": list(FILES),
                "note": (
                    "Raw geometry, not committed: it is 47 MB and derivable. "
                    "scripts/import_real_bus_routes.py compiles it to "
                    "compiled.json.gz, which is committed."
                ),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\n{fetched} file(s) fetched.  Next: scripts/import_real_bus_routes.py")
    if fetched == 0:
        sys.exit(0)


if __name__ == "__main__":
    main()
