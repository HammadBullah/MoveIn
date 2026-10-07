#!/usr/bin/env python3
"""Fetch real UK bus data from the DfT Bus Open Data Service.

Why this is a separate script
-----------------------------

MoveIn's sandbox has no route to the internet: the only hosts it can reach are
GitHub, npm and PyPI.  BODS is *not* one of them, and no API key changes that --
the connection is refused before a request is ever sent.  So the national
download cannot happen where the app is developed; it has to happen where there
is a network, which is what this script is for.

What it does
------------

BODS publishes one dataset per operator (and sometimes per region), each a zip
of TransXChange XML **and** GTFS.  This script:

1. asks the dataset API what exists, with your key;
2. filters to the operators or local authority areas you asked for;
3. downloads each dataset's zip, unpacks it, and records what arrived.

Everything is resumable: a dataset already unpacked is left alone, so a broken
connection costs one dataset, not the evening.

Usage::

    export MOVEIN_BODS_API_KEY=...            # or BODS_API_KEY
    python scripts/fetch_bods_gtfs.py --list                     # what exists
    python scripts/fetch_bods_gtfs.py --area Nottingham --area Leicester
    python scripts/fetch_bods_gtfs.py --noc NCTR --noc TBTN
    python scripts/fetch_bods_gtfs.py --all --limit 50           # first 50 datasets
    python scripts/fetch_bods_gtfs.py --area "Milton Keynes" --dry-run

Then compile what you fetched::

    python scripts/import_gtfs_routes.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.ingest.bods import BODS_BASE_URL  # noqa: E402

DEFAULT_OUT = ROOT / "backend/data/raw/bods"


def api_key(explicit: str | None = None) -> str:
    """The key, from the argument, the environment, or a local .env file.

    Returns "" when none is configured and anonymous use was allowed, because
    the BODS catalogue is readable without one -- only some feeds are not.
    """
    if explicit:
        return explicit.strip()
    if os.environ.get("MOVEIN_BODS_ALLOW_ANONYMOUS") == "1":
        for name in ("MOVEIN_BODS_API_KEY", "BODS_API_KEY"):
            if os.environ.get(name):
                return os.environ[name].strip()
    for name in ("MOVEIN_BODS_API_KEY", "BODS_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value.strip()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() in {"MOVEIN_BODS_API_KEY", "BODS_API_KEY"}:
                return value.strip().strip("'\"")
    if os.environ.get("MOVEIN_BODS_ALLOW_ANONYMOUS") == "1":
        return ""
    raise SystemExit(
        "No API key.  Set MOVEIN_BODS_API_KEY in the environment or a .env file,\n"
        "or pass --api-key.  Keys are free from https://data.bus-data.dft.gov.uk/\n"
        "(or set MOVEIN_BODS_ALLOW_ANONYMOUS=1 to try without one)"
    )


class Unreachable(SystemExit):
    """The machine running this cannot reach BODS, and says so like a person."""


def _connect_guard(exc: Exception) -> "Unreachable":
    return Unreachable(
        "\n".join(
            [
                f"Could not reach {BODS_BASE_URL}: {exc}",
                "",
                "The key is not the problem -- the network is.  Some sandboxes and",
                "corporate networks block all outbound traffic except a short list of",
                "hosts.  Run this where BODS is reachable (a laptop, a CI runner), or",
                "check that nothing is intercepting TLS.",
            ]
        )
    )


def fetch_datasets(key: str, *, limit: int | None = None, page: int = 100) -> list[dict]:
    """Every published dataset the key can see."""
    import httpx

    datasets: list[dict] = []
    offset = 0
    try:
        client = httpx.Client(timeout=60.0, follow_redirects=True)
        while True:
            params = {"limit": page, "offset": offset}
            if key:
                params["api_key"] = key
            response = client.get(f"{BODS_BASE_URL}/api/v1/dataset/", params=params)
            response.raise_for_status()
            body = response.json()
            results = body.get("results", [])
            datasets.extend(results)
            print(f"  ... {len(datasets)}/{body.get('count', '?')} datasets listed")
            if not results or (limit is not None and len(datasets) >= limit):
                break
            if not body.get("next"):
                break
            offset += page
    except Exception as exc:  # connection, DNS, TLS, timeout -- all the same story
        if exc.__class__.__module__.startswith("httpx"):
            raise _connect_guard(exc) from exc
        raise
    finally:
        try:
            client.close()
        except NameError:  # pragma: no cover - client never constructed
            pass
    return datasets[:limit] if limit else datasets


def matches(dataset: dict, *, areas: list[str], nocs: list[str], text: str | None) -> bool:
    """Does this dataset belong to what the caller asked for?"""
    if nocs:
        published = {code.upper() for code in (dataset.get("noc") or [])}
        if not published.intersection({code.upper() for code in nocs}):
            return False
    if areas:
        names = {
            (area.get("name") or "").lower() for area in (dataset.get("adminAreas") or [])
        }
        codes = {str(area.get("atco_code") or "") for area in (dataset.get("adminAreas") or [])}
        wanted = {area.lower() for area in areas}
        if not (wanted & names) and not (wanted & codes):
            return False
    if text:
        needle = text.lower()
        haystack = " ".join(
            [
                dataset.get("operatorName") or "",
                " ".join(dataset.get("lines") or []),
                " ".join(
                    (area.get("name") or "") for area in (dataset.get("adminAreas") or [])
                ),
            ]
        ).lower()
        if needle not in haystack:
            return False
    return True


def download(dataset: dict, key: str, out_dir: Path, *, timeout: float = 600.0) -> dict:
    """Fetch and unpack one dataset.  Returns a manifest entry."""
    import httpx

    identifier = str(dataset["id"])
    target = out_dir / identifier
    marker = target / "manifest.json"
    if marker.exists():
        entry = json.loads(marker.read_text())
        if entry.get("unpacked"):
            print(f"  [{identifier}] already fetched -- skipping")
            return entry

    url = dataset.get("url") or f"{BODS_BASE_URL}/timetable/dataset/{identifier}/download/"
    target.mkdir(parents=True, exist_ok=True)
    archive = target / "download.zip"
    print(f"  [{identifier}] {dataset.get('operatorName', '?')} -> {url}")
    try:
        params = {"api_key": key} if key else {}
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            with client.stream("GET", url, params=params) as response:
                response.raise_for_status()
                with archive.open("wb") as handle:
                    for chunk in response.iter_bytes(1 << 20):
                        handle.write(chunk)
    except Exception as exc:
        if exc.__class__.__module__.startswith("httpx"):
            archive.unlink(missing_ok=True)
            raise _connect_guard(exc) from exc
        raise

    files: list[str] = []
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.namelist():
            # Datasets nest their files one directory deep; flatten that away.
            name = Path(member).name
            if not name or member.endswith("/"):
                continue
            with bundle.open(member) as source, (target / name).open("wb") as sink:
                sink.write(source.read())
            files.append(name)

    # The archive is only needed until it is unpacked, and it is large.
    archive.unlink(missing_ok=True)

    entry = {
        "id": dataset["id"],
        "operator": dataset.get("operatorName"),
        "noc": dataset.get("noc"),
        "lines": dataset.get("lines"),
        "admin_areas": [area.get("name") for area in (dataset.get("adminAreas") or [])],
        "modified": dataset.get("modified"),
        "files": files,
        "unpacked": True,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": url,
        "licence": "Open Government Licence v3.0 (Bus Open Data Service, DfT)",
    }
    marker.write_text(json.dumps(entry, indent=2) + "\n")
    print(f"  [{identifier}] {len(files)} files unpacked into {target.relative_to(ROOT)}")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", default=None, help="BODS API key (else the environment)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--area", action="append", default=[], help="Local authority area name or code")
    parser.add_argument("--noc", action="append", default=[], help="Operator licence code, e.g. NCTR")
    parser.add_argument("--text", default=None, help="Match operator name, route number or area")
    parser.add_argument("--all", action="store_true", help="Every published dataset")
    parser.add_argument("--limit", type=int, default=None, help="Stop after this many datasets")
    parser.add_argument("--list", action="store_true", help="Only list what exists; download nothing")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched")
    args = parser.parse_args()

    key = api_key(args.api_key)
    print("Asking BODS what exists...")
    datasets = fetch_datasets(key, limit=args.limit)
    print(f"{len(datasets)} published datasets available")

    wanted = [
        dataset
        for dataset in datasets
        if args.all
        or matches(dataset, areas=args.area, nocs=args.noc, text=args.text)
    ]
    print(f"{len(wanted)} match the filter")

    if args.list:
        for dataset in wanted[:200]:
            areas = ", ".join(
                (area.get("name") or "") for area in (dataset.get("adminAreas") or [])[:3]
            )
            print(
                f"  {dataset['id']:>5}  {dataset.get('operatorName', '?')[:34]:34} "
                f"{len(dataset.get('lines') or []):>3} lines  {areas}"
            )
        if len(wanted) > 200:
            print(f"  ... and {len(wanted) - 200} more")
        return

    if args.dry_run:
        for dataset in wanted:
            print(f"  would fetch {dataset['id']}: {dataset.get('operatorName')}")
        return

    if not wanted:
        raise SystemExit("Nothing matched.  Try --list to see what is there.")

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, dataset in enumerate(wanted, start=1):
        print(f"[{index}/{len(wanted)}]")
        manifest.append(download(dataset, key, args.out))
    (args.out / "manifest.json").write_text(
        json.dumps(
            {
                "fetched": len(manifest),
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "datasets": manifest,
                "licence": "Open Government Licence v3.0 (Bus Open Data Service, DfT)",
                "note": (
                    "Raw published bus data, fetched from the DfT Bus Open Data Service. "
                    "Compile it with scripts/import_gtfs_routes.py."
                ),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\n{len(manifest)} datasets under {args.out.relative_to(ROOT)}")
    print("Next: .venv/bin/python scripts/import_gtfs_routes.py")


if __name__ == "__main__":
    main()
