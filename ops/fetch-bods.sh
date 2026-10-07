#!/usr/bin/env bash
#
# Fetch the national bus data where there is a network.
#
# This script is what the GitHub workflow runs, on a runner, because the sandbox
# MoveIn is developed in cannot reach the DfT Bus Open Data Service at all: the
# TLS handshake is dropped before a request is sent, and no API key changes that.
#
# It is a script rather than a pile of YAML so that it can be read, reviewed and
# syntax-checked like any other code -- and so the workflow file stays small
# enough that a mistake in it is obvious.
#
# Everything it learns goes to stdout; the workflow tees that into
# ops/last-run.txt and commits it, because the only channel out of a runner that
# this environment can read is the repository itself.
#
#   Usage: ops/fetch-bods.sh [limit]
#
# Environment:
#   MOVEIN_BODS_API_KEY          optional; the catalogue is readable without one
#   MOVEIN_BODS_ALLOW_ANONYMOUS  1 to carry on without a key

set -uo pipefail

LIMIT="${1:-60}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== $(date -u +%FT%TZ) fetching real bus data ==="
echo "key present: $([ -n "${MOVEIN_BODS_API_KEY:-}" ] && echo yes || echo no)"
echo "limit: $LIMIT datasets"

echo
echo "--- can this machine reach BODS? ---"
getent hosts data.bus-data.dft.gov.uk || echo "no DNS for data.bus-data.dft.gov.uk"
curl -sS -o /tmp/bods-catalogue.json -w 'catalogue (no key): HTTP %{http_code}, %{size_download} bytes\n' \
  'https://data.bus-data.dft.gov.uk/api/v1/dataset/?limit=1' || echo "catalogue request failed"
head -c 300 /tmp/bods-catalogue.json 2>/dev/null
echo
curl -sSL -o /tmp/bods-one.zip -w 'one dataset (no key): HTTP %{http_code}, %{size_download} bytes\n' \
  'https://data.bus-data.dft.gov.uk/timetable/dataset/465/download/' || echo "download failed"
ls -l /tmp/bods-one.zip 2>/dev/null || true

echo
echo "--- python dependencies ---"
python -m pip install --quiet httpx || echo "pip install failed"
python -c 'import httpx, sys; print("httpx", httpx.__version__, "on", sys.version.split()[0])' || true

echo
echo "--- fetch: the cities MoveIn models, and their operators ---"
python scripts/fetch_bods_gtfs.py \
  --out backend/data/raw/bods \
  --limit "$LIMIT" \
  --area Nottingham --area Leicester --area Derby --area Coventry \
  --area Birmingham --area Sheffield --area Leeds --area Manchester \
  --area Milton Keynes --area Peterborough --area Slough --area Reading
echo "fetch exit: $?"
echo "datasets unpacked: $(find backend/data/raw/bods -name manifest.json 2>/dev/null | wc -l)"
echo "gtfs tables: $(find backend/data/raw/bods -name '*.txt' 2>/dev/null | wc -l)"

echo
echo "--- compile: published routes into MoveIn's own schema ---"
python scripts/import_gtfs_routes.py \
  --source backend/data/raw/bods \
  --out backend/data/raw/real_bus_routes/compiled_bods.json.gz
echo "compile exit: $?"
ls -l backend/data/raw/real_bus_routes/compiled_bods.json.gz 2>/dev/null || echo "no compiled file"

echo
echo "=== done $(date -u +%FT%TZ) ==="
