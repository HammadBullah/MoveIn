#!/usr/bin/env python3
"""Download the real open-data sources MoveIn is built on and build the seed files.

Usage
-----
    python scripts/fetch_real_data.py            # fetch + build seed files
    python scripts/fetch_real_data.py --check    # report what is already bundled

Sources (all genuinely public UK open data):

* NaPTAN  -- every GB public transport access point (DfT / ODI Leeds)
* Named stops + railway TIPLOCs + TOC registry (DfT / Network Rail via UK2GTFS)

Outputs land in ``backend/data/raw/``.  The rail/operator/named-stop files are
kept whole; the 433k-row NaPTAN register is trimmed to the regions MoveIn
models so the repository stays lean.  Pass ``--full-naptan`` to keep all of GB.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.domain.regions import REGIONS  # noqa: E402
from app.ingest import real_sources as src  # noqa: E402
from app.ingest.geo import haversine_m  # noqa: E402

RAW_DIR = REPO_ROOT / "backend" / "data" / "raw"
CACHE_DIR = REPO_ROOT / ".cache" / "movein-sources"

USER_AGENT = "MoveIn/0.1 (+https://github.com/HammadBullah/MoveIn)"


def _auth_headers() -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _gh_token() -> str | None:
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        out = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=15
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return None


def http_get(url: str, *, accept: str | None = None, timeout: int = 120) -> bytes:
    """GET with retries.  Falls back to a bearer token when GitHub rate-limits."""
    headers = _auth_headers()
    if accept:
        headers["Accept"] = accept

    last_error: Exception | None = None
    for attempt in range(4):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (403, 429):
                token = _gh_token()
                if token and "Authorization" not in headers:
                    headers["Authorization"] = f"Bearer {token}"
                    continue
            if exc.code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def fetch_remote_file(remote: src.RemoteFile, dest: Path) -> Path:
    """Fetch one :class:`RemoteFile`, caching it under ``.cache/``."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / remote.name
    if cached.exists() and cached.stat().st_size > 0:
        print(f"  [cache]  {remote.name} ({cached.stat().st_size/1024:.0f} KB)")
        if cached.resolve() != dest.resolve():
            shutil.copyfile(cached, dest)
        return dest

    print(f"  [fetch]  {remote.name}  <- {remote.repo}/{remote.path}")
    url = f"https://api.github.com/repos/{remote.repo}/contents/{remote.path}?ref={remote.ref}"
    data = http_get(url, accept="application/vnd.github.raw")
    cached.write_bytes(data)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"           {len(data)/1024:.0f} KB")
    return dest


def fetch_naptan_register(dest: Path) -> Path:
    """Fetch the full NaPTAN register.

    The geography extract is a 40 MB CSV inside a repository tarball on
    ``codeload.github.com``; we stream the tarball and pull out just the member
    we need so we never hold the whole archive in memory.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / "naptan_access_points_full.csv"
    if cached.exists() and cached.stat().st_size > 100_000:
        print(f"  [cache]  naptan_access_points_full.csv ({cached.stat().st_size/1e6:.1f} MB)")
        return cached

    url = f"https://codeload.github.com/{src.NAPTAN_GEO.repo}/tar.gz/refs/heads/{src.NAPTAN_GEO.ref}"
    print(f"  [fetch]  NaPTAN register <- {src.NAPTAN_GEO.repo} (streamed tarball)")
    req = urllib.request.Request(url, headers=_auth_headers())
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        with urllib.request.urlopen(req, timeout=300) as resp:
            shutil.copyfileobj(resp, tmp, length=1 << 20)
    try:
        with tarfile.open(tmp_path, "r:gz") as tar:
            member = next(
                (m for m in tar.getmembers() if m.name.endswith("NAPTAN.csv")), None
            )
            if member is None:
                raise RuntimeError("NAPTAN.csv not found in archive")
            extracted = tar.extractfile(member)
            if extracted is None:
                raise RuntimeError("NAPTAN.csv could not be extracted")
            with cached.open("wb") as out:
                shutil.copyfileobj(extracted, out)
    finally:
        tmp_path.unlink(missing_ok=True)
    print(f"           {cached.stat().st_size/1e6:.1f} MB")
    return cached


def build_regional_naptan(full_csv: Path, out_gz: Path, keep_all: bool) -> dict:
    """Trim the national register to the modelled regions and gzip the result."""
    kept = 0
    total = 0
    by_region: dict[str, int] = {}
    # Pre-compute region bounds once; this is a tight loop over ~430k rows.
    region_bounds = [
        (r.slug, r.lat, r.lon, r.radius_m, r.lat - 0.35, r.lat + 0.35, r.lon - 0.55, r.lon + 0.55)
        for r in REGIONS
    ]

    with open(full_csv, encoding="utf-8-sig", newline="") as fh_in, gzip.open(
        out_gz, "wt", encoding="utf-8", newline=""
    ) as fh_out:
        reader = csv.DictReader(fh_in)
        writer = csv.writer(fh_out)
        writer.writerow(
            ["atco_code", "lat", "lon", "locality_code", "lad_code", "naptan_code", "region"]
        )
        for row in reader:
            total += 1
            atco = (row.get("ATCOCode") or "").strip()
            if not atco:
                continue
            try:
                lat = float(row["Latitude"])
                lon = float(row["Longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (-7.6 < lon < 2.2 and 49.8 < lat < 61.0):
                continue

            match: str | None = None
            if not keep_all:
                for slug, rlat, rlon, radius, la, lb, lo, hi in region_bounds:
                    if not (la <= lat <= lb and lo <= lon <= hi):
                        continue
                    if haversine_m(lat, lon, rlat, rlon) <= radius:
                        match = slug
                        break
                if match is None:
                    continue

            kept += 1
            if match:
                by_region[match] = by_region.get(match, 0) + 1
            writer.writerow(
                [
                    atco,
                    f"{lat:.6f}",
                    f"{lon:.6f}",
                    (row.get("NptgLocalityCode") or "").strip(),
                    (row.get("lad17cd") or "").strip(),
                    (row.get("NaptanCode") or "").strip(),
                    match or "",
                ]
            )

    return {
        "total_scanned": total,
        "kept": kept,
        "by_region": dict(sorted(by_region.items(), key=lambda kv: -kv[1])),
        "gzip_bytes": out_gz.stat().st_size,
    }


def copy_named_stops(names_csv: Path, out_path: Path) -> int:
    """Normalise the named-stop extracts into one compact CSV."""
    count = 0
    with names_csv.open(encoding="utf-8-sig", newline="") as fh_in, out_path.open(
        "w", encoding="utf-8", newline=""
    ) as fh_out:
        reader = csv.DictReader(fh_in)
        writer = csv.writer(fh_out)
        writer.writerow(["atco_code", "name", "lat", "lon", "source"])
        for row in reader:
            atco = (row.get("stop_id") or "").strip()
            name = (row.get("stop_name") or "").strip()
            if not atco or not name:
                continue
            try:
                lat = float(row["stop_lat"])
                lon = float(row["stop_lon"])
            except (KeyError, TypeError, ValueError):
                continue
            writer.writerow([atco, name, f"{lat:.6f}", f"{lon:.6f}", names_csv.name])
            count += 1
    return count


def copy_with_named_header(src_path: Path, out_path: Path, header: list[str]) -> int:
    """Copy a source CSV through with a standardised header row."""
    count = 0
    with src_path.open(encoding="utf-8-sig", newline="") as fh_in, out_path.open(
        "w", encoding="utf-8", newline=""
    ) as fh_out:
        reader = csv.reader(fh_in)
        next(reader, None)
        writer = csv.writer(fh_out)
        writer.writerow(header)
        for row in reader:
            if not row:
                continue
            writer.writerow(row)
            count += 1
    return count


def write_manifest(payload: dict) -> None:
    (RAW_DIR / "SOURCES.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def cmd_check() -> int:
    print("Bundled seed files in", RAW_DIR)
    if not RAW_DIR.exists():
        print("  (none)")
        return 1
    found = False
    for path in sorted(RAW_DIR.iterdir()):
        if path.is_file():
            found = True
            print(f"  {path.name:42s} {path.stat().st_size/1024:9.1f} KB")
    manifest = RAW_DIR / "SOURCES.json"
    if manifest.exists():
        print("\nManifest:")
        print(manifest.read_text(encoding="utf-8"))
    return 0 if found else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report bundled files and exit")
    parser.add_argument(
        "--full-naptan",
        action="store_true",
        help="keep the whole GB register instead of trimming to modelled regions",
    )
    args = parser.parse_args(argv)

    if args.check:
        return cmd_check()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print("MoveIn real-data fetch")
    print("=" * 62)

    manifest: dict = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    # --- Named stops ---------------------------------------------------------
    print("\n[1/4] NaPTAN stop names")
    names_tmp = RAW_DIR / "_names_raw.csv"
    fetch_remote_file(src.NAPTAN_NAMES, names_tmp)
    repl_tmp = RAW_DIR / "_replace_raw.csv"
    fetch_remote_file(src.NAPTAN_REPLACEMENTS, repl_tmp)

    named_out = RAW_DIR / "naptan_named_stops.csv"
    with named_out.open("w", encoding="utf-8", newline="") as fh_out:
        writer = csv.writer(fh_out)
        writer.writerow(["atco_code", "name", "lat", "lon", "source"])
        total_names = 0
        for part in (names_tmp, repl_tmp):
            with part.open(encoding="utf-8-sig", newline="") as fh_in:
                for row in csv.DictReader(fh_in):
                    atco = (row.get("stop_id") or "").strip()
                    name = (row.get("stop_name") or "").strip()
                    if not atco or not name:
                        continue
                    try:
                        lat = float(row["stop_lat"])
                        lon = float(row["stop_lon"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    writer.writerow([atco, name, f"{lat:.6f}", f"{lon:.6f}", part.name])
                    total_names += 1
    names_tmp.unlink(missing_ok=True)
    repl_tmp.unlink(missing_ok=True)
    manifest["named_stops"] = total_names
    print(f"        {total_names} real named stops")

    # --- Rail ----------------------------------------------------------------
    print("\n[2/4] Rail stations + operator registry")
    rail_tmp = RAW_DIR / "_rail_raw.csv"
    fetch_remote_file(src.RAIL_STATIONS, rail_tmp)
    rail_out = RAW_DIR / "rail_stations.csv"
    n_rail = copy_with_named_header(
        rail_tmp, rail_out, ["tiploc", "crs", "name", "lon", "lat"]
    )
    rail_tmp.unlink(missing_ok=True)
    manifest["rail_stations"] = n_rail
    print(f"        {n_rail} railway timing points")

    agency_tmp = RAW_DIR / "_agency_raw.csv"
    fetch_remote_file(src.ATOC_AGENCIES, agency_tmp)
    agency_out = RAW_DIR / "atoc_agencies.csv"
    shutil.copyfile(agency_tmp, agency_out)
    agency_tmp.unlink(missing_ok=True)
    manifest["atoc_agencies"] = agency_out.read_text(encoding="utf-8").count("\n") - 1
    print(f"        {manifest['atoc_agencies']} train operating companies")

    # --- NaPTAN register -----------------------------------------------------
    print("\n[3/4] NaPTAN access-point register")
    full_csv = fetch_naptan_register(RAW_DIR / "naptan_access_points_full.csv")
    out_gz = RAW_DIR / "naptan_regional.csv.gz"
    stats = build_regional_naptan(full_csv, out_gz, keep_all=args.full_naptan)
    manifest["naptan"] = stats
    print(
        f"        scanned {stats['total_scanned']:,} nodes, kept {stats['kept']:,} "
        f"-> {stats['gzip_bytes']/1e6:.2f} MB gzipped"
    )
    if not args.full_naptan:
        print("        by region:")
        for slug, n in list(stats["by_region"].items())[:12]:
            print(f"          {slug:22s} {n:6,}")

    # --- Provenance ----------------------------------------------------------
    print("\n[4/4] Provenance manifest")
    manifest["sources"] = [
        {
            "name": s.name,
            "publisher": s.publisher,
            "licence": s.licence,
            "origin": f"https://github.com/{s.repo}/{s.path}",
            "description": s.description,
        }
        for s in src.ALL_STATIC_SOURCES
    ]
    manifest["live_feeds_not_fetched"] = src.LIVE_FEEDS
    write_manifest(manifest)
    print("        wrote SOURCES.json")

    print("\nDone. Seed data is in", RAW_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
