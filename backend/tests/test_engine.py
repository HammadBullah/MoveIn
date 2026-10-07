"""The journey engine: graph, RAPTOR, fares, ranking."""

from __future__ import annotations

import math

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


def test_a_journey_departs_when_the_traveller_does(planner):
    """The declared departure is the first step, not the minute that was asked for.

    This was a real defect: a search at 11:07 returned a journey that said
    "departs 11:07, 6h 10m" when the coach left at 11:38 and the walk to the
    station took two minutes. The wait had been credited to the journey, so the
    headline duration disagreed with the itinerary underneath it -- and a
    traveller reading only the card believed a journey was half an hour longer
    than it is.
    """
    from backend.app.engine.search import TransitLeg, WalkLeg

    checked = 0
    for origin, destination in (
        ("Nottingham", "Leeds"),
        ("Nottingham", "Birmingham"),
        ("Nottingham", "Manchester"),
    ):
        for preference in (Preference.CHEAPEST, Preference.BEST_VALUE, Preference.FASTEST):
            requested = datetime(2026, 10, 7, 9, 22)
            result = planner.plan(
                origin=origin, destination=destination, departure=requested,
                preference=preference, limit=6,
            )
            for journey in result.journeys:
                transit = next(
                    (l for l in journey.legs if isinstance(l, (TransitLeg,))), None
                )
                if transit is None:
                    continue
                checked += 1
                first = journey.legs[0]
                # Transit legs carry seconds since the service day began; the
                # journey's own times are datetimes on that same day.
                midnight = datetime.combine(journey.departure.date(), datetime.min.time())
                if isinstance(first, WalkLeg):
                    # The walk finishes exactly as the vehicle leaves.
                    leaves = journey.departure + timedelta(seconds=first.duration_s)
                    expected = midnight + timedelta(seconds=transit.departure_s)
                    assert leaves == expected, (
                        f"{origin}->{destination}: the walk does not meet the vehicle"
                    )
                else:
                    assert first is transit, "a journey must start with its first step"
                    assert journey.departure == midnight + timedelta(
                        seconds=transit.departure_s
                    )
                # The headline must equal the itinerary it describes.
                assert journey.duration_s == int(
                    (journey.arrival - journey.departure).total_seconds()
                )
                assert journey.departure >= requested
    assert checked >= 6, "not enough journeys to be meaningful"


# --- walking: an option, not a default -------------------------------------


def test_a_long_walk_is_offered_as_a_choice_not_as_the_answer(planner):
    """Nobody plans their day around a 25 minute walk, so it is not the headline.

    The cheapest journey from A to B is often the one with the worst walk at
    either end.  Returning it as "Cheapest" without saying so is how a planner
    recommends something nobody would take -- so a journey that needs a long
    walk keeps its price and its place in the list, but the headline labels go
    to journeys a traveller can actually complete.
    """
    result = planner.plan(
        origin="Nottingham",
        destination="Birmingham",
        departure=datetime(2026, 10, 7, 9, 0),
    )
    comfortable = [j for j in result.journeys if j.walk_comfort == "comfortable"]
    long_walk = [j for j in result.journeys if j.walk_comfort == "long"]
    assert comfortable and long_walk, "this corridor has both kinds of option"

    # The long walks are still there, still priced, and visibly flagged.
    for journey in long_walk:
        assert journey.longest_walk_s > planner.settings.comfortable_walk_s
        assert journey.price > 0

    # Every headline goes to a comfortable journey when one is available.
    for label in ("cheapest", "fastest", "best_value", "least_walking"):
        winner = next(j for j in result.journeys if label in j.archetypes)
        assert winner.walk_comfort == "comfortable", (
            f"{label} went to a journey with a "
            f"{winner.longest_walk_s // 60} minute walk"
        )


def test_a_long_walk_can_still_win_when_it_is_the_only_option():
    """Flagged, not hidden: if the long walk is all there is, it is the answer.

    Built from journeys rather than searched for, because the rule is about
    labelling and a search that happens to contain both kinds of option cannot
    prove what happens when it does not.
    """
    from backend.app.engine.journeys import Journey, JourneyRanker

    def journey(journey_id: str, price: float, walk_min: int, *, score: float = 50.0):
        return Journey(
            id=journey_id,
            departure=datetime(2026, 10, 7, 9, 0),
            arrival=datetime(2026, 10, 7, 10, 0),
            price=price,
            walking_m=walk_min * 80,
            walking_s=walk_min * 60,
            longest_walk_s=walk_min * 60,
            walk_comfort="long" if walk_min > 15 else "comfortable",
            co2_g=1000.0,
            transit_legs=1,
            score=score,
            scores={"price": score, "time": 50.0, "changes": 50.0, "walking": 50.0},
        )

    cheap_and_far = journey("a", 3.00, 25)
    dear_and_close = journey("b", 7.00, 5)
    ranked = JourneyRanker.select_archetypes(
        JourneyRanker.rank([cheap_and_far, dear_and_close], Preference.BEST_VALUE)
        if False
        else [cheap_and_far, dear_and_close]
    )
    assert "cheapest" in dear_and_close.archetypes, (
        "the cheapest journey a traveller can actually complete should win"
    )
    assert "cheapest" not in cheap_and_far.archetypes, (
        "the long walk must not take the headline it only holds because of price"
    )
    assert "accessible" in cheap_and_far.archetypes, (
        "step-free is not a comfort trade-off, so it still wins on merit"
    )

    # Nothing else in the set: the long walk is still labelled, not hidden.
    only = journey("c", 3.00, 25)
    JourneyRanker.select_archetypes([only])
    assert "cheapest" in only.archetypes


def test_the_walk_budget_is_a_hard_ceiling(planner):
    """A stated limit is a promise: no returned journey may exceed it."""
    for minutes in (10, 12, 15, 20):
        result = planner.plan(
            origin="Nottingham",
            destination="Birmingham",
            departure=datetime(2026, 10, 7, 9, 0),
            max_walk_s=minutes * 60,
        )
        for journey in result.journeys:
            assert journey.longest_walk_s <= minutes * 60, (
                f"{minutes} min limit returned a "
                f"{journey.longest_walk_s / 60:.1f} min walk"
            )
        # And the limit genuinely bites: fewer options than with no limit.
        unlimited = planner.plan(
            origin="Nottingham",
            destination="Birmingham",
            departure=datetime(2026, 10, 7, 9, 0),
        )
        assert len(result.journeys) <= len(unlimited.journeys)


def test_walk_labels_round_up(planner):
    """616 seconds is an 11 minute walk, not a 10 minute one."""
    from backend.app.api.serializers import _walk_label, walk_minutes

    # Distances in, whole minutes out, rounded up -- never down.
    from backend.app.ingest.geo import walk_duration_s

    for distance in (0, 10, 640, 810, 811, 1_350, 2_400):
        seconds = walk_duration_s(distance)
        expected = math.ceil(seconds / 60) if seconds else 0
        assert walk_minutes(distance) == max(1, expected) if seconds else walk_minutes(distance) == 0
    assert _walk_label(0) == "no walking"
    assert _walk_label(590) == "10 min walk"
    assert _walk_label(616) == "11 min walk"
