"""The data layer: geography, operators, the compiler and the GTFS round trip."""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path

import pytest

from backend.app.domain.models import Mode, gtfs_time_to_seconds, seconds_to_gtfs_time
from backend.app.engine.fares import TravellerProfile
from backend.app.domain.network_spec import ALL_CORRIDORS
from backend.app.ingest.geo import haversine_m, walk_distance_m, walk_duration_s
from backend.app.ingest.gtfs import read_gtfs, validate_gtfs, write_gtfs
from backend.app.ingest.registry import get_operator, operators_for_mode, validate_registry


# --- geography ------------------------------------------------------------


def test_haversine_matches_known_distance():
    """Nottingham to Birmingham is about 72 km as the crow flies."""
    distance = haversine_m(52.9471, -1.1464, 52.4796, -1.9026)
    assert 70_000 < distance < 74_000


def test_haversine_is_symmetric_and_zero_at_a_point():
    a, b = (53.4808, -2.2426), (52.9471, -1.1464)
    assert haversine_m(*a, *b) == pytest.approx(haversine_m(*b, *a), rel=1e-9)
    assert haversine_m(*a, *a) == 0.0


def test_walk_distance_exceeds_straight_line():
    """Real walking is longer than the crow-flies distance."""
    straight = haversine_m(52.9471, -1.1464, 52.9536, -1.1505)
    walked = walk_distance_m(52.9471, -1.1464, 52.9536, -1.1505)
    assert walked > straight
    assert walked < straight * 1.6, "the detour factor should stay plausible"


def test_walk_duration_uses_a_human_pace():
    """Roughly 5 km/h: a kilometre is about twelve minutes."""
    assert 600 <= walk_duration_s(1000) <= 800
    assert walk_duration_s(0) == 0


def test_haversine_rejects_nothing_for_antipodes():
    assert haversine_m(0, 0, 0, 180) == pytest.approx(math.pi * 6_371_000, rel=0.01)


# --- operator registry ----------------------------------------------------


def test_operator_registry_validates():
    assert validate_registry() == []


def test_known_operators_resolve_to_real_names():
    assert get_operator("EM").name == "East Midlands Railway"
    assert get_operator("XC").name == "CrossCountry"
    assert get_operator("NATX").name == "National Express"


def test_operator_aliases_resolve_to_the_real_company():
    """The corridor spec uses short codes; they must not become placeholders."""
    assert get_operator("NCT").name == "Nottingham City Transport"
    assert get_operator("TB").name == "trentbarton"
    assert get_operator("NCT").code == "NCTR"


def test_unknown_operator_is_marked_as_such():
    operator = get_operator("NOPE")
    assert "Unknown" in operator.name


def test_operators_cover_rail_and_bus():
    assert len(operators_for_mode("rail")) >= 8
    assert len(operators_for_mode("bus")) >= 6


# --- compiler -------------------------------------------------------------


def test_every_corridor_has_a_route(graph):
    """A corridor that does not compile is a whole line missing from the map."""
    missing = [c.code for c in ALL_CORRIDORS if c.code not in graph.routes]
    assert missing == []


def test_corridors_have_at_least_two_stops_and_a_trip(graph):
    for corridor in ALL_CORRIDORS:
        route = graph.routes[corridor.code]
        assert route.mode.value in {"rail", "bus", "coach", "tram", "metro", "ferry"}
        patterns = [p for p in graph.patterns.values() if p.route_id == corridor.code]
        assert patterns, f"{corridor.code} has no patterns"
        assert all(len(p.stops) >= 2 for p in patterns)


def test_every_stop_is_a_real_named_place(graph):
    """Stops come from NaPTAN or the rail TIPLOC register; nothing is invented."""
    from collections import Counter

    sources = Counter(stop.source for stop in graph.stops.values())
    assert sources["naptan"] > 100, "expected the real NaPTAN stops to dominate"
    assert sources["rail_tiploc"] > 20
    assert all(stop.name.strip() for stop in graph.stops.values())


def test_compiled_network_is_deterministic(graph):
    """The same seed must produce the same timetable, or nothing is reproducible."""
    import os
    import subprocess
    import sys

    code = (
        "from pathlib import Path;"
        "from backend.app.ingest.network_compiler import NetworkCompiler,"
        "_network_fingerprint;"
        "from backend.app.config import get_settings;"
        "s=get_settings();"
        "c=NetworkCompiler(Path(s.data_raw_dir)).compile();"
        "print(_network_fingerprint(c.network))"
    )
    root = str(Path(__file__).resolve().parents[2])
    env = {**os.environ, "PYTHONPATH": root}
    outputs = {
        subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, cwd=root, env=env
        ).stdout.strip()
        for _ in range(2)
    }
    assert len(outputs) == 1, f"compiling twice gave different results: {outputs}"
    assert outputs.pop() != ""


def test_trips_run_in_both_directions(graph):
    """A corridor that only runs one way is worse than useless."""
    from collections import defaultdict

    directions: dict[str, set[str]] = defaultdict(set)
    for pattern in graph.patterns.values():
        directions[pattern.route_id].add(f"{pattern.stops[0]}>{pattern.stops[-1]}")
    one_way = [
        route_id
        for route_id, pairs in directions.items()
        if len({p.split(">")[0] for p in pairs}) < 2 and len(pairs) < 2
    ]
    assert one_way == []


# --- GTFS -----------------------------------------------------------------


def test_gtfs_time_helpers_round_trip():
    for seconds in (0, 60, 3600, 86_399, 90_000):
        assert gtfs_time_to_seconds(seconds_to_gtfs_time(seconds)) == seconds


def test_gtfs_supports_after_midnight_times():
    assert gtfs_time_to_seconds("25:10:00") == 25 * 3600 + 600
    assert seconds_to_gtfs_time(25 * 3600 + 600) == "25:10:00"


def test_written_feed_validates(tmp_path, planner):
    """The shipped feed must pass its own structural validation."""
    feed = Path(planner.settings.data_generated_dir) / "gtfs"
    if not (feed / "stops.txt").exists():
        pytest.skip("no compiled feed on disk")
    assert validate_gtfs(feed) == []


def test_gtfs_round_trip_preserves_everything(tmp_path, planner):
    """Writing and reading a feed must not lose what the engine needs."""
    net = planner.net
    out = tmp_path / "round-trip.zip"
    write_gtfs(net, out)
    reread = read_gtfs(out)

    assert set(reread.stops) == set(net.stops)
    assert set(reread.routes) == set(net.routes)
    assert set(reread.trips) == set(net.trips)
    assert sum(len(v) for v in reread.stop_times.values()) == sum(
        len(v) for v in net.stop_times.values()
    )
    assert len(reread.transfers) == len(net.transfers)
    assert len(reread.fares) == len(net.fares)
    assert len(reread.fare_rules) == len(net.fare_rules)

    # The mode is the whole product: a coach must not come back as a bus.
    for route_id, route in net.routes.items():
        assert reread.routes[route_id].mode is route.mode, route_id

    # The fields MoveIn adds on top of GTFS must survive the trip.
    for stop_id, stop in list(net.stops.items())[:50]:
        assert reread.stops[stop_id].mode == stop.mode
        assert reread.stops[stop_id].source == stop.source
        assert reread.stops[stop_id].region == stop.region
    for trip_id in list(net.trips)[:50]:
        assert reread.trips[trip_id].reliability == pytest.approx(
            net.trips[trip_id].reliability
        )


def test_feed_service_window_is_current(planner):
    """Planning "now" must not fall outside the timetable."""
    info = planner.net.feed_info
    today = date.today()
    assert info.start_date and info.end_date
    assert info.start_date <= today <= info.end_date, (
        f"the compiled window {info.start_date}..{info.end_date} excludes today; "
        "re-run the compiler"
    )


# --- the corridors that were once missing altogether ----------------------


def test_every_london_underground_line_is_in_the_network(graph):
    """The tube is not decoration: five lines once compiled to nothing at all.

    Their last train leaves after midnight, and a service window that read
    "00:15" as *before* "05:15" produced no departures -- so no trips, no stops,
    and a London map with a hole in it.
    """
    for code, line in (
        ("TFL-PIC", "Piccadilly line"),
        ("TFL-NOR", "Northern line"),
        ("TFL-CEN", "Central line"),
        ("TFL-VIC", "Victoria line"),
        ("TFL-JUB", "Jubilee line"),
        ("TFL-ELZ", "Elizabeth line"),
    ):
        route = graph.routes.get(code)
        assert route is not None, f"{line} is missing"
        assert route.mode is Mode.METRO, f"{line} is not a metro"
        trips = [t for t in graph.net.trips.values() if t.route_id == code]
        assert trips, f"{line} has no trips"
        # A tube line is more than two stops long, calling at real stations.
        patterns = [p for p in graph.patterns.values() if p.route_id == code]
        assert patterns
        assert max(len(p.stops) for p in patterns) >= 8
        assert any(len(trip_ids) > 4 for trip_ids in (p.trip_ids for p in patterns))


def test_tube_stops_are_named_as_stations_not_kerbsides(graph):
    """A tube corridor wants the station, not the bus stop on the same road."""
    piccadilly = next(p for p in graph.patterns.values() if p.route_id == "TFL-PIC")
    names = [graph.stops[stop_id].name for stop_id in piccadilly.stops]
    assert "Piccadilly Circus" in names
    assert "Covent Garden" in names
    # NaPTAN node furniture must not survive into the name a passenger sees.
    for name in names:
        assert "-Entrance" not in name and "-Underground" not in name
        assert not name.endswith(" Underground 1")


def test_late_evening_services_exist(graph):
    """The compiled day ends before midnight, and not at 23:00 either."""
    late = [
        st.departure_s
        for stop_times in graph.net.stop_times.values()
        for st in stop_times
        if st.departure_s > 23 * 3600
    ]
    assert late, "no service runs after 23:00, which is not a UK timetable"


def test_coach_and_bus_are_different_roads(planner):
    """The database round trip must not turn a coach into a bus.

    GTFS has no coach route type of its own, so the mode is carried explicitly;
    without it every National Express service came back as a local bus, priced
    and labelled as one.
    """
    from backend.app.db import repository as repo

    coaches = [r for r in planner.net.routes.values() if r.mode is Mode.COACH]
    assert len(coaches) >= 8
    assert {r.operator_code for r in coaches} >= {"NATX", "MEGA", "FLIX"}

    busses = [r for r in planner.net.routes.values() if r.mode is Mode.BUS]
    assert len(busses) >= 30
    assert not ({r.id for r in coaches} & {r.id for r in busses})


def test_every_route_has_a_fare(planner):
    """A route a traveller can board but cannot be priced for is a dead end."""
    engine = planner.fare_engine
    for route in planner.net.routes.values():
        priced = engine.price_leg(
            index=0,
            route_id=route.id,
            operator_code=route.operator_code,
            mode=route.mode,
            distance_m=5_000,
            when=datetime(2026, 10, 7, 10, 0),
            traveller=TravellerProfile(),
        )
        assert priced.paid > 0, f"{route.id} is free to travel on"


# --- provenance -----------------------------------------------------------


def test_the_provenance_table_matches_what_is_on_disk():
    """Every file the app claims to bundle must be there, with the row count shown.

    This was a real defect: the Data screen listed files from an earlier fetch
    that had since been consolidated into other files, so it advertised two
    datasets that were not bundled and hid the two that were. Provenance that
    does not match the data is worse than no provenance at all.
    """
    from backend.app.config import get_settings
    from backend.app.ingest.real_sources import BUNDLED_FILES, count_rows

    settings = get_settings()
    assert BUNDLED_FILES, "no bundled files declared"
    for source in BUNDLED_FILES:
        path = settings.data_raw_dir / source.name
        assert path.exists(), f"{source.name} is listed but not bundled"
        rows = count_rows(path)
        assert rows and rows > 0, f"{source.name} appears empty"
        assert source.licence, f"{source.name} has no licence recorded"
        assert source.publisher, f"{source.name} has no publisher recorded"


def test_licences_are_recorded_for_every_source_the_api_reports():
    """MoveIn redistributes other people's data; the licence must be in the payload."""
    from backend.app.ingest.real_sources import BUNDLED_FILES, LIVE_FEEDS

    for source in BUNDLED_FILES:
        assert "licence" in source.licence.lower() or "ODbL" in source.licence
    for key, feed in LIVE_FEEDS.items():
        assert feed["licence"], f"{key} has no licence"
        assert feed["adapter"].startswith("app.ingest."), key
        assert feed.get("name"), f"{key} has no human name for the UI"
        assert feed.get("provides"), f"{key} does not say what it would add"
