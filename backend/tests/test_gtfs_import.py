"""The GTFS compiler, tested on a feed small enough to check by eye.

The national import cannot run where this code is developed -- the sandbox has
no route to the Bus Open Data Service -- so the compiler that consumes those
downloads has to be provable without them.  This is that proof: a five-stop feed
whose correct answer is known, compiled through the same functions the national
run uses.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gtfs_mini"


def _compiler():
    """Load scripts/import_gtfs_routes.py as a module."""
    spec = importlib.util.spec_from_file_location(
        "import_gtfs_routes", REPO_ROOT / "scripts" / "import_gtfs_routes.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def compiled(tmp_path_factory) -> dict:
    out = tmp_path_factory.mktemp("gtfs") / "compiled_bods.json.gz"
    compiler = _compiler()
    compiler.compile_gtfs(
        FIXTURE,
        tolerance_m=1.0,
        out=out,
        agency_names=compiler.load_agencies(compiler.gtfs_files(FIXTURE)["agency.txt"]),
    )
    with gzip.open(out, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def test_both_directions_are_compiled(compiled):
    identifiers = {route["id"] for route in compiled["routes"]}
    assert identifiers == {"R1~0", "R1~1"}, identifiers


def test_the_stop_sequence_is_the_order_the_bus_drives(compiled):
    forward = next(route for route in compiled["routes"] if route["id"] == "R1~0")
    assert [stop["name"] for stop in forward["stops"]] == [
        "Alpha Street",
        "Beta Road",
        "Gamma Lane",
        "Delta Close",
    ]


def test_stops_carry_real_coordinates(compiled):
    forward = next(route for route in compiled["routes"] if route["id"] == "R1~0")
    for stop in forward["stops"]:
        assert 49.0 < stop["lat"] < 61.5
        assert -8.5 < stop["lon"] < 2.5


def test_the_shape_is_drawn_from_shapes_txt(compiled):
    forward = next(route for route in compiled["routes"] if route["id"] == "R1~0")
    assert len(forward["shape"]) >= 2
    # The shape runs between the ends of the route.
    assert forward["shape"][0][0] == pytest.approx(52.4000, abs=1e-4)
    assert forward["shape"][-1][0] == pytest.approx(52.4300, abs=1e-4)


def test_a_route_with_one_stop_is_not_a_route(compiled):
    assert all(route["number"] != "X1" for route in compiled["routes"])


def test_a_rail_replacement_service_is_not_a_bus(compiled):
    assert all(route["number"] != "900" for route in compiled["routes"])


def test_the_operator_name_comes_from_agency_txt(compiled):
    assert {route["operator"] for route in compiled["routes"]} == {"Fixture Buses"}


def test_the_frequency_evidence_is_kept(compiled):
    """Trip counts are how many times a day the route runs -- real, if not a timetable."""
    forward = next(route for route in compiled["routes"] if route["id"] == "R1~0")
    assert forward["trips"] == 3


def test_the_compiled_file_keeps_its_attribution(compiled):
    assert "Open Government Licence" in compiled["attribution"]
    assert compiled["generated_by"].endswith("import_gtfs_routes.py")
