#!/usr/bin/env bash
#
# Fetch the published national bus data, where there is a network.
#
# This script is what the GitHub workflow runs.  It exists because the sandbox
# MoveIn is developed in cannot reach the DfT Bus Open Data Service at all: the
# TLS handshake is dropped before a request is sent, and no API key changes that.
# A runner has ordinary internet access, so the download happens there and the
# compiled result is committed back to the repository.
#
# How the data is fetched
# -----------------------
#
# BODS publishes its converted GTFS as one file per region, with no key needed:
#
#   https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/{region}/
#
# The per-operator datasets behind the API are richer, but listing them needs an
# API key, and a runner cannot be given one here (the repository is public and
# this environment cannot write repository secrets).  The regional files are the
# published data too -- same service, same licence, converted by the same
# pipeline -- and they need no credentials at all, so they are what this uses.
#
# Each region is compiled on its own into `compiled_bods_<region>.json.gz`, so a
# run that runs out of time still commits everything it managed to do, and the
# next run adds the next region.
#
#   Usage: ops/fetch-bods.sh [budget-minutes]
#
# Everything it prints is also written to the report file the workflow commits
# (ops/last-run.txt), because a log on a runner is otherwise unreadable from
# where this work is done.

set -uo pipefail

BUDGET_MIN=100
FORCE=""
ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    --only) ONLY="${2:-}"; shift 2 ;;
    *) BUDGET_MIN="$1"; shift ;;
  esac
done
STARTED=$(date +%s)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RAW="backend/data/raw/bulk_gtfs"
OUT_DIR="backend/data/raw/real_bus_routes"
BASE="https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file"

# `all` is Great Britain: every stop, route and trip the operators publish,
# converted once by BODS.  The regional files are its subsets, so the default is
# the single national file -- smaller to hold, no route held twice.  Name
# regions explicitly when a targeted run is wanted:
#
#   bash ops/fetch-bods.sh 60 --only east_midlands,north_west --force
#
# (before the parser below, this line used to be the list all regions were
# fetched from, which is why the first national run brought back thirteen
# files, twelve of them duplicates.)
REGIONS=(all)
if [ -n "$ONLY" ]; then
  IFS=', ' read -r -a REGIONS <<< "$ONLY"
fi

elapsed() { echo $(( ($(date +%s) - STARTED) / 60 )); }
left() { echo $(( BUDGET_MIN - $(elapsed) )); }

echo "=== $(date -u +%FT%TZ) fetching published UK bus data ==="
echo "budget: ${BUDGET_MIN} minutes; compiling: ${REGIONS[*]}"
echo "disk free: $(df -h / | tail -1 | awk '{print $4}')"
echo

echo "--- can this machine reach BODS, and does anything need a key? ---"
getent hosts data.bus-data.dft.gov.uk | head -2
echo -n "catalogue without a key: "
curl -sS -o /tmp/catalogue.json -w 'HTTP %{http_code}\n' \
  'https://data.bus-data.dft.gov.uk/api/v1/dataset/?limit=1' || echo "request failed"
head -c 120 /tmp/catalogue.json 2>/dev/null; echo

echo
echo "--- what regional files exist, and how big are they? ---"
declare -A AVAILABLE
for region in "${REGIONS[@]}"; do
  headers=$(curl -sSIL --max-time 60 "$BASE/$region/" 2>&1 | tr -d '\r')
  status=$(echo "$headers" | grep -oE '^HTTP/[0-9.]+ [0-9]{3}' | tail -1 | awk '{print $2}')
  length=$(echo "$headers" | grep -i '^content-length:' | tail -1 | awk '{print $2}')
  if [ "$status" = "200" ]; then
    AVAILABLE["$region"]=1
    printf '  %-14s HTTP 200  %s bytes (%.1f MB)\n' "$region" "${length:-?}" \
      "$(awk -v b="${length:-0}" 'BEGIN { print b / 1048576 }')"
  else
    printf '  %-14s HTTP %s -- skipping\n' "$region" "${status:-?}"
  fi
done

mkdir -p "$RAW" "$OUT_DIR"
echo
echo "--- download, compile, one region at a time ---"

for region in "${REGIONS[@]}"; do
  [ -n "${AVAILABLE[$region]:-}" ] || continue
  if [ "$(left)" -le 8 ]; then
    echo "budget almost gone ($(elapsed) min elapsed), stopping before $region"
    break
  fi

  zip="$RAW/$region.zip"
  out="$OUT_DIR/compiled_bods_$region.json.gz"

  if [ -f "$out" ] && [ -z "$FORCE" ]; then
    echo "== $region: already compiled ($(du -h "$out" | cut -f1)) -- skipping"
    continue
  fi
  [ -n "$FORCE" ] && echo "== $region: recompiling (--force) over $(du -h "$out" 2>/dev/null | cut -f1 || echo 'nothing')"


  echo
  echo "== $region: downloading"
  if ! curl -L --fail --retry 3 --retry-delay 5 --max-time 5400 -o "$zip" \
      -w '   %{size_download} bytes in %{time_total}s\n' "$BASE/$region/"; then
    echo "   download failed -- moving on"
    rm -f "$zip"
    continue
  fi
  echo "   on disk: $(du -h "$zip" | cut -f1)"

  echo "   disk free: $(df -h / | tail -1 | awk '{print $4}')"
  echo "== $region: compiling real routes into MoveIn's schema, straight from the zip"
  # The compiler reads the GTFS tables out of the zip itself.  Unpacking first
  # needs 11 GB for the national file, which once killed a run at the commit
  # step on a full disk; this needs the 1.7 GB download and nothing more.
  # Twelve evenly spread trips per direction is plenty to find the trunk of a
  # day.  Memory no longer follows the sample: the compiler keeps one trip's
  # stop calls at a time (see Sampler in scripts/import_gtfs_routes.py).
  sample=12
  if python scripts/import_gtfs_routes.py \
      --source "$zip" \
      --out "$out" \
      --prefix "$region" \
      --region "$region" \
      --sample "$sample"; then
    echo "   compiled: $(du -h "$out" | cut -f1)"
  else
    echo "   compile failed -- leaving the feed for the next run"
    continue
  fi

  # The published feed is big and reproducible; only the compiled result is kept.
  rm -f "$zip"
  echo "   elapsed: $(elapsed) min, budget left: $(left) min"
done

echo
echo "--- published timetables, through the DfT's own extractor ---"
# BODSDataExtractor is the client the Department for Transport publishes for
# this.  It reads the API catalogue -- which is key-gated -- and parses the
# TransXChange inside each dataset, so it needs a key this runner can only get
# as a repository secret.
if [ -z "${MOVEIN_BODS_API_KEY:-}" ]; then
  echo "no BODS key available to this runner, so the API-keyed extraction is skipped."
  echo "the regional files above need no key; the catalogue and the per-operator"
  echo "datasets do.  to enable this phase, add a repository secret named"
  echo "BODS_API_KEY (Settings -> Secrets and variables -> Actions -> New secret)."
else
  echo "key present: yes (never printed)"
  if python -m pip install --quiet BODSDataExtractor; then
    python scripts/extract_bods_cities.py --limit 200 || echo "extraction failed"
  else
    echo "could not install BODSDataExtractor -- skipping the extraction"
  fi
fi

echo
echo "=== $(date -u +%FT%TZ) result ==="
ls -l "$OUT_DIR"/compiled_bods_*.json.gz 2>/dev/null || echo "nothing compiled"
ls -l backend/data/raw/bods_extract/ 2>/dev/null || echo "no extractor output"
