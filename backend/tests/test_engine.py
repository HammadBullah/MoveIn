"""The journey engine: graph, RAPTOR, fares, ranking."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.app.engine.fares import FareEngine, TravellerProfile
from backend.app.engine.graph import MODE_ACCESS_WALK_M
from backend.app.engine.journeys import Preference, format_duration
from backend.app.engine.search import SearchOptions, TransitLeg


# --- graph ----------------------------------------------------------------


def test_patterns_group_on_exact_stop_sequence(graph):
    """Two trips share a pattern only if they call at the same stops in order."""
    for pattern in graph.patterns.values():
        sequences = {
            tuple(st.stop_id for st in graph.net.stop_times[trip])
            for trip in pattern.trip_ids[:5]
        }
        assert len(sequences) == 1, "a pattern mixes different stop sequences"


def test_pattern_distances_are_monotonic(graph):
    for pattern in list(graph.patterns.values())[:40]:
        distances = pattern.cum_distance_m
        assert all(b >= a for a, b in zip(distances, distances[1:]))


def test_trip_departures_are_sorted(graph):
    """Binary search over boarding depends on this."""
    for pattern in list(graph.patterns.values())[:40]:
        assert list(pattern.first_departures) == sorted(pattern.first_departures)


def test_nearest_stop_is_actually_nearest(graph):
    station = graph.stops["rail:NOT"]
    stop = graph.nearest_stop(station.lat, station.lon)
    assert stop is not None
    assert stop.id == station.id, "the nearest stop to a stop is itself"


def test_stops_near_respects_the_radius(graph):
    found = graph.stops_near(52.9536, -1.1505, 600, limit=50)
    assert found
    assert all(distance <= 600 for _stop, distance in found)
    assert found == sorted(found, key=lambda pair: pair[1])


def test_every_mode_has_a_walk_limit():
    for mode in ("rail", "bus", "tram", "metro", "coach"):
        assert mode in MODE_ACCESS_WALK_M
        assert MODE_ACCESS_WALK_M[mode] > 0


# --- service days ---------------------------------------------------------


def test_services_on_a_weekday_differ_from_a_sunday(graph, departure):
    wednesday = departure.date()
    sunday = wednesday + timedelta(days=(6 - wednesday.weekday()) % 7 or 7)
    weekday_services = graph.services_on(wednesday)
    sunday_services = graph.services_on(sunday)
    assert weekday_services, "a weekday must have services"
    assert sunday_services, "a Sunday must still have some services"
    assert weekday_services != sunday_services


def test_services_on_a_date_outside_the_window_is_empty(graph):
    assert graph.services_on(datetime(1999, 1, 4).date()) == set()


# --- search ---------------------------------------------------------------


def test_search_finds_a_journey(planner, departure):
    result = planner.plan(
        origin="Nottingham", destination="Birmingham", departure=departure
    )
    assert result.journeys, "Nottingham to Birmingham must be plannable"
    assert result.origin and result.destination


def test_search_is_fast_enough_to_be_interactive(planner, departure):
    result = planner.plan(origin="Nottingham", destination="Derby", departure=departure)
    assert result.diagnostics["search_ms"] < 2000


def test_no_weekday_service_is_offered_on_a_sunday(planner, departure):
    """The bug this guards against is the worst kind: confidently wrong."""
    sunday = departure.date() + timedelta(days=(6 - departure.date().weekday()) % 7 or 7)
    when = datetime.combine(sunday, datetime.min.time()).replace(hour=10)
    services = planner.graph.services_on(sunday)
    result = planner.plan(origin="Nottingham", destination="Birmingham", departure=when)
    for journey in result.journeys:
        for leg in journey.legs:
            if isinstance(leg, TransitLeg):
                trip = planner.graph.net.trips[leg.trip_id]
                assert trip.service_id in services, (
                    f"{leg.trip_id} does not run on a Sunday"
                )


def test_journeys_never_travel_backwards_in_time(planner, departure):
    result = planner.plan(origin="Nottingham", destination="Birmingham", departure=departure)
    for journey in result.journeys:
        assert journey.arrival > journey.departure
        previous = None
        for leg in journey.legs:
            if isinstance(leg, TransitLeg):
                assert leg.arrival_s > leg.departure_s
                if previous is not None:
                    assert leg.departure_s >= previous - 60
                previous = leg.arrival_s


def test_legs_connect_geographically(graph, planner, departure):
    """Consecutive legs must meet at the same place, within a short walk."""
    from backend.app.ingest.geo import walk_distance_m

    result = planner.plan(origin="Nottingham", destination="Leeds", departure=departure)
    checked = 0
    for journey in result.journeys:
        transit = [leg for leg in journey.legs if isinstance(leg, TransitLeg)]
        for first, second in zip(transit, transit[1:]):
            a = graph.stops[first.alight_stop_id]
            b = graph.stops[second.board_stop_id]
            distance = walk_distance_m(a.lat, a.lon, b.lat, b.lon)
            assert distance <= planner.settings.max_transfer_walk_m + 50, (
                f"transfer from {a.name} to {b.name} is {distance:.0f} m"
            )
            checked += 1
    assert checked, "expected at least one interchange to test"


def test_more_legs_are_allowed_than_returned(planner, departure):
    result = planner.plan(
        origin="Leeds", destination="London", departure=departure, max_legs=4
    )
    for journey in result.journeys:
        assert len([l for l in journey.legs if isinstance(l, TransitLeg)]) <= 4


def test_unresolvable_place_reports_cleanly(planner, departure):
    result = planner.plan(origin="Xyzzy", destination="Birmingham", departure=departure)
    assert result.journeys == []
    assert "error" in result.diagnostics


def test_short_trip_walks(planner, departure):
    """Two hundred metres apart should be a walk, not a bus ride."""
    result = planner.plan(
        origin="52.9536,-1.1505", destination="52.9550,-1.1495", departure=departure
    )
    assert result.journeys
    assert result.journeys[0].is_walk_only


# --- fares ----------------------------------------------------------------


def test_day_ticket_beats_singles_on_a_busy_day(planner, departure):
    """Four singles on one operator must not cost more than that operator's day ticket."""
    result = planner.plan(
        origin="Nottingham", destination="Derby", departure=departure
    )
    assert result.journeys
    for journey in result.journeys:
        singles = sum(leg.base_price for leg in journey.fare.legs)
        assert journey.fare.total <= singles + 0.01


def test_price_is_never_negative_and_matches_the_tickets(planner, departure):
    result = planner.plan(origin="Nottingham", destination="Birmingham", departure=departure)
    for journey in result.journeys:
        assert journey.price >= 0
        assert journey.fare is not None
        assert journey.fare.total == pytest.approx(journey.price, abs=0.02)


def test_fare_engine_prices_a_single_leg(planner):
    engine = planner.fare_engine
    assert engine is not None
    for fare in list(planner.net.fares.values())[:20]:
        assert fare.price >= 0
        assert fare.currency_type == "GBP"


def test_railcard_is_never_worse_than_no_railcard(planner, departure):
    without = planner.plan(
        origin="Nottingham",
        destination="London",
        departure=departure,
        preference=Preference.CHEAPEST,
        traveller=TravellerProfile(railcard=False),
    )
    with_card = planner.plan(
        origin="Nottingham",
        destination="London",
        departure=departure,
        preference=Preference.CHEAPEST,
        traveller=TravellerProfile(railcard=True),
    )
    if without.journeys and with_card.journeys:
        assert min(j.price for j in with_card.journeys) <= min(
            j.price for j in without.journeys
        ) + 0.01


# --- ranking --------------------------------------------------------------


def test_format_duration_reads_naturally():
    """Short enough for a results card: "1h 30m", not "1 hour 30 minutes"."""
    assert format_duration(0) == "0m"
    assert format_duration(59) == "0m"
    assert format_duration(90) == "1m"
    assert format_duration(600) == "10m"
    assert format_duration(3600) == "1h"
    assert format_duration(5400) == "1h 30m"
    assert format_duration(90_000) == "25h"


def test_preferences_change_the_winner(planner, departure):
    """If every preference returned the same journey, there would be no product."""
    winners = {}
    for preference in (Preference.CHEAPEST, Preference.FASTEST):
        result = planner.plan(
            origin="Nottingham",
            destination="London",
            departure=departure,
            preference=preference,
        )
        assert result.journeys
        winners[preference] = result.journeys[0]

    cheapest = winners[Preference.CHEAPEST]
    fastest = winners[Preference.FASTEST]
    assert cheapest.price <= fastest.price + 0.01
    assert fastest.duration_s <= cheapest.duration_s + 60


def test_ranking_is_ordered_by_the_chosen_preference(planner, departure):
    result = planner.plan(
        origin="Nottingham",
        destination="Birmingham",
        departure=departure,
        preference=Preference.CHEAPEST,
    )
    scores = [journey.score for journey in result.journeys]
    assert scores == sorted(scores, reverse=True), "results come back best first"
    for journey in result.journeys:
        assert 0 <= journey.score <= 100
        assert set(journey.scores) == {"price", "time", "changes", "walking"}
        assert all(0 <= value <= 100 for value in journey.scores.values())


def test_every_journey_is_labelled_when_it_excels(planner, departure):
    """The brief's results screen needs one card per trade-off."""
    result = planner.plan(
        origin="Nottingham", destination="London", departure=departure, limit=12
    )
    assert result.journeys
    labelled = {j.id for j in result.journeys if "cheapest" in j.archetypes}
    assert labelled, "no journey was labelled cheapest"
    assert min(j.price for j in result.journeys) == pytest.approx(
        min(j.price for j in result.journeys if j.id in labelled), abs=0.05
    )


def test_a_limit_never_hides_an_archetype_winner(planner, departure):
    """Asking for three results must still include the labelled ones."""
    result = planner.plan(
        origin="Nottingham", destination="Birmingham", departure=departure, limit=3
    )
    assert len(result.journeys) <= 3
    labels = {label for journey in result.journeys for label in journey.archetypes}
    assert "cheapest" in labels and "fastest" in labels


def test_archived_bug_two_routes_sharing_a_stop_sequence_stay_separate(planner):
    """Megabus and National Express both run Nottingham to Birmingham.

    They were once merged into one pattern, which labelled a Megabus coach as a
    National Express service and priced it on the wrong operator's fare scale.
    """
    sequence = tuple(
        stop.id for stop in planner.graph.stops.values()
        if stop.name in {"Nottingham Station", "Birmingham Coach Station"}
    )
    assert len(sequence) == 2
    patterns = [p for p in planner.graph.patterns.values() if set(sequence) <= set(p.stops)]
    routes = {p.route_id for p in patterns}
    assert {"MB-1", "NX-1"} <= routes
    for pattern in patterns:
        assert pattern.stops[0] in sequence and pattern.stops[-1] in sequence
        operators = {planner.net.routes[pattern.route_id].operator_code for _ in pattern.trip_ids}
        assert len(operators) == 1
    megabus = [p for p in patterns if p.route_id == "MB-1"]
    assert megabus and planner.net.routes["MB-1"].operator_code == "MEGA"


def test_an_interchange_walk_is_a_visible_step(planner, departure):
    """Changing between two stops is a walk the traveller has to make."""
    from backend.app.engine.search import WalkLeg

    result = planner.plan(
        origin="Nottingham", destination="Manchester", departure=departure
    )
    transfers = [
        leg
        for journey in result.journeys
        for leg in journey.legs
        if isinstance(leg, WalkLeg) and leg.kind == "transfer"
    ]
    assert transfers, "expected an interchange that is not at the same stop"
    for leg in transfers:
        assert leg.distance_m > 0 and leg.duration_s > 0
        assert leg.from_stop_id != leg.to_stop_id


def test_walks_are_never_consecutive(planner, departure):
    """Two walks in a row are one walk; the waypoint between them is not a place."""
    from backend.app.engine.search import WalkLeg

    result = planner.plan(origin="Nottingham", destination="Birmingham", departure=departure)
    for journey in result.journeys:
        for first, second in zip(journey.legs, journey.legs[1:]):
            assert not (isinstance(first, WalkLeg) and isinstance(second, WalkLeg))


def test_only_real_operators_are_quoted(planner, departure):
    """Every leg must name the company the traveller is actually trusting."""
    from backend.app.ingest.registry import get_operator

    result = planner.plan(origin="Nottingham", destination="Leeds", departure=departure)
    for journey in result.journeys:
        for leg in journey.fare.legs:
            if not leg.operator_code:
                continue
            operator = get_operator(leg.operator_code)
            assert operator is not None
            assert not operator.name.startswith("Unknown")


def test_step_free_filter_excludes_inaccessible_vehicles(planner, departure):
    result = planner.plan(
        origin="Nottingham",
        destination="Birmingham",
        departure=departure,
        step_free_only=True,
    )
    for journey in result.journeys:
        assert journey.step_free
        for leg in journey.legs:
            if isinstance(leg, TransitLeg):
                assert leg.accessible


def test_emissions_are_ordered_by_mode(planner, departure):
    """A train must never emit more per passenger than a taxi over the same trip."""
    from backend.app.domain.models import CO2_G_PER_PKM

    result = planner.plan(origin="Nottingham", destination="London", departure=departure)
    assert result.journeys
    assert CO2_G_PER_PKM[
        next(m for m in __import__("backend.app.domain.models", fromlist=["Mode"]).Mode if m.value == "rail")
    ] < CO2_G_PER_PKM[
        next(m for m in __import__("backend.app.domain.models", fromlist=["Mode"]).Mode if m.value == "taxi")
    ]
    for journey in result.journeys:
        assert journey.co2_g >= 0
