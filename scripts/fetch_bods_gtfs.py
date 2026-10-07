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
import socket
import ssl
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class _Tee:
    """A stream that writes to the terminal and to the run's report file.

    The BODS key travels in a query string, so any error message that quotes a
    URL can quote the key with it.  This log is committed to a public
    repository, so the key is masked on the way through.
    """

    def __init__(self, stream, handle, secret: str = ""):
        self.stream = stream
        self.handle = handle
        self.secret = secret.strip()

    def _mask(self, text: str) -> str:
        if self.secret and self.secret in text:
            return text.replace(self.secret, "***")
        return text

    def write(self, text: str) -> int:
        text = self._mask(text)
        self.stream.write(text)
        self.handle.write(text)
        self.handle.flush()
        return len(text)

    def flush(self) -> None:
        self.stream.flush()
        self.handle.flush()

    def isatty(self) -> bool:
        return False


def report_path(explicit: str | None = None) -> Path | None:
    """Where to write this run's log, if anywhere.

    A fetch that happens somewhere else -- on a GitHub runner, say -- leaves its
    log behind in the repository, because that is the only channel back.
    """
    for candidate in (explicit, os.environ.get("MOVEIN_BODS_REPORT"), os.environ.get("REPORT")):
        if candidate:
            path = Path(candidate)
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
    return None


def start_report(explicit: str | None = None, secret: str = "") -> None:
    path = report_path(explicit)
    if path is None:
        return
    handle = path.open("a", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, handle, secret)  # type: ignore[assignment]
    sys.stderr = _Tee(sys.stderr, handle, secret)  # type: ignore[assignment]
    print(f"\n--- report opened {datetime.now(timezone.utc).isoformat(timespec='seconds')} ---")


def probe(key: str = "") -> None:
    """Say, in the log, exactly what this machine can reach.

    MoveIn's own sandbox cannot reach BODS at all, so when a fetch fails it is
    worth being able to tell "this machine has no route" apart from "the request
    was wrong".
    """
    host = "data.bus-data.dft.gov.uk"
    print("--- network probe ---")
    try:
        print(f"dns: {host} -> {socket.gethostbyname(host)}")
    except OSError as error:
        print(f"dns: FAILED ({error}) -- nothing else will work")
        return

    try:
        with socket.create_connection((host, 443), timeout=15):
            print("tcp 443: connected")
    except OSError as error:
        print(f"tcp 443: FAILED ({error})")
        return

    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=15) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                print(f"tls: {tls.version()}")
    except (OSError, ssl.SSLError) as error:
        print(f"tls: FAILED ({error})")
        return

    for label, suffix in (("without a key", ""), ("with the key", f"&api_key={key}" if key else "")):
        url = f"{BODS_BASE_URL}/api/v1/dataset/?limit=1{suffix}"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                body = response.read(200).decode("utf-8", "replace")
                print(f"catalogue {label}: HTTP {response.status}, {body[:160]}")
        except urllib.error.HTTPError as error:
            print(f"catalogue {label}: HTTP {error.code} {error.reason}")
        except OSError as error:
            print(f"catalogue {label}: FAILED ({error})")

    url = "https://data.bus-data.dft.gov.uk/timetable/dataset/465/download/"
    try:
        request = urllib.request.Request(url, headers={"Range": "bytes=0-1023"})
        with urllib.request.urlopen(request, timeout=60) as response:
            chunk = response.read()
            print(f"one dataset download: HTTP {response.status}, first {len(chunk)} bytes {chunk[:4]!r}")
    except urllib.error.HTTPError as error:
        print(f"one dataset download: HTTP {error.code} {error.reason}")
    except OSError as error:
        print(f"one dataset download: FAILED ({error})")
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
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Download at most this many datasets, after filtering (the catalogue is always listed in full)",
    )
    parser.add_argument("--list", action="store_true", help="Only list what exists; download nothing")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched")
    parser.add_argument(
        "--report",
        default=None,
        help="Also write this run's log here (else $MOVEIN_BODS_REPORT or $REPORT)",
    )
    parser.add_argument(
        "--no-probe", action="store_true", help="Skip the network probe this script prints first"
    )
    args = parser.parse_args()

    key = api_key(args.api_key)
    start_report(args.report, secret=key)
    print(f"fetch_bods_gtfs.py {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    if not args.no_probe:
        probe(key)
    print("Asking BODS what exists...")
    datasets = fetch_datasets(key)
    print(f"{len(datasets)} published datasets available")

    wanted = [
        dataset
        for dataset in datasets
        if args.all
        or matches(dataset, areas=args.area, nocs=args.noc, text=args.text)
    ]
    print(f"{len(wanted)} match the filter")
    if args.limit and len(wanted) > args.limit:
        print(f"downloading the first {args.limit} of them (--limit)")
        wanted = wanted[: args.limit]

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
        areas = sorted(
            {
                (area.get("name") or "").strip()
                for dataset in datasets
                for area in (dataset.get("adminAreas") or [])
                if (area.get("name") or "").strip()
            }
        )
        print(f"the catalogue names {len(areas)} local authority areas, for example:")
        print("  " + ", ".join(areas[:60]))
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
