"""The fare engine: the cheapest combination of tickets, not the sum of singles."""

from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.domain.models import Mode
from backend.app.domain.network_spec import _ENGLAND_BUS_CAP
from backend.app.engine.fares import FareEngine, PricedLeg, TravellerProfile, _is_offpeak

WEDNESDAY = datetime(2026, 10, 7, 9, 0)


def _rail_route(planner):
    return next(r for r in planner.net.routes.values() if r.mode is Mode.RAIL)


def _price(engine, route, *, distance_m, when, traveller=None, index=0):
    return engine.price_leg(
        index=index,
        route_id=route.id,
        operator_code=route.operator_code,
        mode=route.mode,
        distance_m=distance_m,
        when=when,
        traveller=traveller or TravellerProfile(),
    )


# --- time-of-day pricing --------------------------------------------------


@pytest.mark.parametrize(
    "hour,minute,offpeak",
    [
        (5, 0, True),
        (6, 29, True),
        (6, 30, False),   # peak starts
        (9, 29, False),
        (9, 30, True),    # peak ends
        (12, 0, True),
        (16, 0, False),   # afternoon peak
        (19, 0, True),
        (23, 30, True),
    ],
)
def test_peak_hours_match_the_rail_network(hour, minute, offpeak):
    when = datetime(2026, 10, 7, hour, minute)  # a Wednesday
    assert _is_offpeak(when) is offpeak


def test_weekends_are_off_peak_all_day():
    saturday = datetime(2026, 10, 10, 8, 0)
    sunday = datetime(2026, 10, 11, 17, 0)
    assert _is_offpeak(saturday) and _is_offpeak(sunday)


def test_offpeak_costs_less_than_peak_on_rail(planner):
    """If off-peak did not undercut peak, the ticket type would be a lie."""
    engine = planner.fare_engine
    route = _rail_route(planner)
    peak = _price(engine, route, distance_m=120_000, when=WEDNESDAY.replace(hour=8))
    offpeak = _price(engine, route, distance_m=120_000, when=WEDNESDAY.replace(hour=12))
    assert offpeak.paid <= peak.paid


def test_rail_fares_rise_with_distance(planner):
    engine = planner.fare_engine
    route = _rail_route(planner)
    fares = [
        _price(engine, route, distance_m=d, when=WEDNESDAY).paid
        for d in (5_000, 50_000, 200_000, 400_000)
    ]
    assert fares == sorted(fares), "a longer train journey must not be cheaper"


# --- discounts ------------------------------------------------------------


def test_a_railcard_never_costs_more(planner):
    engine = planner.fare_engine
    route = _rail_route(planner)
    plain = _price(engine, route, distance_m=200_000, when=WEDNESDAY)
    card = _price(
        engine, route, distance_m=200_000, when=WEDNESDAY,
        traveller=TravellerProfile(railcard=True),
    )
    assert card.paid <= plain.paid + 0.01


def test_child_fares_are_a_discount_on_adult_fares(planner):
    engine = planner.fare_engine
    route = _rail_route(planner)
    adult = _price(engine, route, distance_m=100_000, when=WEDNESDAY)
    with_child = _price(
        engine, route, distance_m=100_000, when=WEDNESDAY,
        traveller=TravellerProfile(adults=1, children=1),
    )
    assert with_child.base_price >= adult.base_price
    assert with_child.base_price < adult.base_price * 2


def test_a_season_ticket_makes_the_leg_free(planner):
    """Someone who has already paid for a season ticket should not be charged again."""
    engine = planner.fare_engine
    route = _rail_route(planner)
    priced = _price(
        engine, route, distance_m=80_000, when=WEDNESDAY,
        traveller=TravellerProfile(season_operator=route.operator_code),
    )
    assert priced.paid == 0


# --- journey-level optimisation ------------------------------------------


def test_price_journey_never_exceeds_the_sum_of_singles(planner, departure):
    """The whole point of the engine: it must find a combination, not add up."""
    result = planner.plan(origin="Nottingham", destination="Leeds", departure=departure)
    assert result.journeys
    for journey in result.journeys:
        assert journey.fare.total <= journey.fare.singles_total + 0.01


def test_price_journey_reports_what_each_leg_costs(planner, departure):
    result = planner.plan(origin="Nottingham", destination="Sheffield", departure=departure)
    assert result.journeys
    for journey in result.journeys:
        breakdown = journey.fare
        assert breakdown.legs, "a journey should price at least one leg"
        assert all(isinstance(leg, PricedLeg) for leg in breakdown.legs)
        assert all(leg.paid >= 0 for leg in breakdown.legs)
        # A day ticket or a cap can cover several legs at once, so the total is
        # what the tickets cost -- never more than the sum of the leg prices.
        assert breakdown.total == pytest.approx(
            sum(ticket["price"] for ticket in breakdown.tickets), abs=0.02
        )
        assert breakdown.total <= sum(leg.paid for leg in breakdown.legs) + 0.02


def test_tickets_cover_every_paid_leg(planner, departure):
    result = planner.plan(origin="Nottingham", destination="Birmingham", departure=departure)
    assert result.journeys
    for journey in result.journeys:
        covered = {
            index
            for ticket in journey.fare.tickets
            for index in ticket["covers"]
        }
        paid = {leg.index for leg in journey.fare.legs if leg.paid > 0}
        assert paid <= covered, "a paid leg with no ticket behind it is a free ride"


def test_bus_singles_respect_the_national_fare_cap(planner, departure):
    """Nobody in England pays more than the national bus cap for a single."""
    result = planner.plan(origin="Nottingham", destination="Derby", departure=departure)
    assert result.journeys
    for journey in result.journeys:
        for leg in journey.fare.legs:
            if leg.mode is Mode.BUS and leg.product == "single":
                assert leg.base_price <= _ENGLAND_BUS_CAP + 0.01


def test_fares_are_reported_in_pounds(planner, departure):
    result = planner.plan(origin="Nottingham", destination="Leeds", departure=departure)
    assert result.journeys
    assert all(j.fare.currency == "GBP" for j in result.journeys)


def _bus_legs(engine, route, count):
    return [
        {
            "route_id": route.id,
            "operator_code": route.operator_code,
            "mode": Mode.BUS,
            "distance_m": 4_000.0,
            "index": index,
        }
        for index in range(count)
    ]


def test_day_ticket_is_used_when_it_is_cheaper(planner):
    """Four short hops on one operator is exactly the case a day ticket exists for."""
    engine = planner.fare_engine
    route = next(
        r
        for r in planner.net.routes.values()
        if r.mode is Mode.BUS and engine.products_for_route(r.id)
    )
    breakdown = engine.price_journey(
        _bus_legs(engine, route, 4), when=WEDNESDAY, traveller=TravellerProfile()
    )
    assert breakdown.total <= breakdown.singles_total + 0.01
    products = {leg.product for leg in breakdown.legs}
    assert (
        "day" in products or "cap" in products
    ) or breakdown.total < breakdown.singles_total, (
        "a multi-leg bus journey should be covered by a day product"
    )


def test_fare_notes_explain_the_saving(planner):
    engine = planner.fare_engine
    route = next(
        r
        for r in planner.net.routes.values()
        if r.mode is Mode.BUS and engine.products_for_route(r.id)
    )
    breakdown = engine.price_journey(
        _bus_legs(engine, route, 3), when=WEDNESDAY, traveller=TravellerProfile()
    )
    if breakdown.saving_vs_singles > 0:
        assert breakdown.notes, "a saving with no explanation is not trustworthy"


def test_carbon_is_added_up_per_mode(planner):
    """Coach is the lowest-carbon motorised mode in the UK; taxi is the worst."""
    from backend.app.domain.models import CO2_G_PER_PKM

    def carbon(mode, km=200.0):
        return FareEngine.carbon_for_legs(
            [{"mode": mode, "distance_m": km * 1000, "index": 0}]
        )

    assert carbon(Mode.COACH) < carbon(Mode.RAIL) < carbon(Mode.TAXI)
    assert carbon(Mode.WALK) == 0
    assert carbon(Mode.RAIL, km=400) == pytest.approx(carbon(Mode.RAIL, km=200) * 2)
    for mode in (Mode.RAIL, Mode.BUS, Mode.COACH, Mode.TRAM, Mode.METRO):
        assert CO2_G_PER_PKM[mode] > 0, f"{mode.value} must have a published factor"


def test_on_demand_is_priced_per_kilometre(planner):
    """A taxi fare must scale with distance, and Uber must undercut a black cab."""
    engine = planner.fare_engine
    short = engine.price_leg(
        index=0, mode=Mode.TAXI, route_id="TAXI", operator_code="TAXI",
        distance_m=2_000, when=WEDNESDAY, traveller=TravellerProfile(),
    )
    long = engine.price_leg(
        index=0, mode=Mode.TAXI, route_id="TAXI", operator_code="TAXI",
        distance_m=8_000, when=WEDNESDAY, traveller=TravellerProfile(),
    )
    assert long.paid > short.paid
    uber = engine.price_leg(
        index=0, mode=Mode.RIDEHAIL, route_id="UBER", operator_code="UBER",
        distance_m=8_000, when=WEDNESDAY, traveller=TravellerProfile(),
    )
    assert uber.paid < long.paid
