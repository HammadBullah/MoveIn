"""The real bus network: the routes operators publish, and what they answer.

Every test here is about a claim the product makes out loud, so each one checks
the claim rather than the implementation: that the numbers on the screen are the
numbers in the data, that a route's stops are the ones its operator publishes,
that a corridor question returns real service numbers, and that the layer never
pretends to know a departure time it does not have.
"""

from __future__ import annotations

from backend.app.domain.real_bus import get_real_bus_network


def test_the_real_bus_network_is_loaded():
    net = get_real_bus_network()
    assert net is not None, "compile it with scripts/import_real_bus_routes.py"
    assert net.routes, "the real bus network is empty"


def test_coverage_counts_what_is_actually_there(client):
    payload = client.get("/api/bus/coverage").json()
    net = get_real_bus_network()
    assert payload["routes"] == len(net.routes)
    assert payload["named_stops"] == len(net.stops())
    assert payload["operators"] >= 5
    # The route counts per operator must add up to the total, or the figures on
    # the data screen would contradict the list behind them.
    assert sum(payload["routes_per_operator"].values()) == payload["routes"]


def test_the_layer_says_which_routes_carry_published_times(client):
    """Say plainly how much of the layer is a timetable and how much a shape.

    The compiled layer carries a departure time at every stop of the sampled
    trip, taken from the published feed, so `has_times` is true and `routes`
    says how many routes have one.  The note must match that, in either
    direction -- if the day ever comes when the compiler drops times, the note
    has to go back to saying so.
    """
    coverage = client.get("/api/bus/coverage").json()
    detail = client.get("/api/bus/routes", params={"limit": 1}).json()
    for body in (coverage, detail):
        assert isinstance(body["has_times"], bool)
    with_times = coverage.get("routes_with_times", 0)
    if with_times:
        assert coverage["has_times"] is True
        assert "no departure times" not in coverage["note"].lower()
        route = client.get(f"/api/bus/routes/{detail['routes'][0]['id']}").json()
        assert route["has_times"] is True
        assert all(stop["time"] for stop in route["stops"]), "a timed route has a time at every stop"
    else:
        assert coverage["has_times"] is False
        assert "no departure times" in coverage["note"].lower()




def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    from math import asin, cos, radians, sin, sqrt

    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


def _assert_options_connect(body: dict, *, near: float = 3.0) -> None:
    """Every option must board at the origin and alight at the destination.

    This is the assertion that catches a stop *name* being used as a stop
    *identity*: with names as keys, a route hundreds of miles away that happens
    to call at a stop of the same name looks like it serves this corridor, and
    the board and alight points give it away.
    """
    for option in body["options"]:
        board_km = _km(
            body["origin"]["lat"],
            body["origin"]["lon"],
            option["board"]["lat"],
            option["board"]["lon"],
        )
        alight_km = _km(
            body["destination"]["lat"],
            body["destination"]["lon"],
            option["alight"]["lat"],
            option["alight"]["lon"],
        )
        assert board_km <= near, (
            f"{option['number']} boards {board_km:.0f} km from {body['origin']['label']}"
        )
        assert alight_km <= near, (
            f"{option['number']} alights {alight_km:.0f} km from {body['destination']['label']}"
        )

def test_a_route_number_finds_the_real_route(client):
    found = client.get("/api/bus/routes?q=148&limit=500").json()
    assert found["count"] >= 1
    long_ones = [
        item
        for item in found["routes"]
        if item["number"] == "148"
        and "Stagecoach" in item["operator"]
        and item["stop_count"] > 50
    ]
    assert long_ones, "the 148 between Coventry and Leicester is a long Stagecoach route"
    assert all(item["from"] and item["to"] for item in long_ones)


def test_a_routes_stops_are_named_real_stops_in_order(client):
    listing = client.get("/api/bus/routes?q=148").json()
    detail = client.get(f"/api/bus/routes/{listing['routes'][0]['id']}").json()
    assert len(detail["stops"]) == detail["stop_count"] > 2
    assert len(detail["shape"]) == detail["shape_points"] >= 2
    names = [stop["name"] for stop in detail["stops"]]
    assert all(name.strip() for name in names), "a stop with no name is not a stop"
    assert all(stop["atco"] for stop in detail["stops"])
    # Every stop is a real NaPTAN point, so its coordinates are real.
    for stop in detail["stops"]:
        assert 49.0 < stop["lat"] < 61.5 and -8.5 < stop["lon"] < 2.5


def test_an_unknown_route_is_a_404(client):
    assert client.get("/api/bus/routes/no-such-route~1").status_code == 404


def test_a_corridor_returns_the_service_that_runs_it(client):
    body = client.get("/api/bus/between?origin=Coventry&destination=Leicester&limit=100").json()
    assert body["count"] >= 1
    _assert_options_connect(body)
    numbers = {option["number"] for option in body["options"]}
    assert "148" in numbers, numbers
    option = next(item for item in body["options"] if item["number"] == "148")
    assert option["stops_travelled"] > 10
    assert option["direction"] in {"forward", "reverse"}
    assert option["calls_at"], "a service between two places calls at places"


def test_a_corridor_works_the_other_way_round(client):
    """The operator publishes the 148 into Leicester; the return must still answer."""
    back = client.get("/api/bus/between?origin=Leicester&destination=Coventry&limit=100").json()
    assert back["count"] >= 1
    _assert_options_connect(back)
    assert any(option["number"] == "148" for option in back["options"])


def test_the_oxford_banbury_corridor_is_found(client):
    """The bug that started this: "Banbury" once meant a street in Coventry.

    With the town naming fixed, the real S4 between Oxford and Banbury is
    findable, which is the difference between a coverage claim and a wrong one.
    """
    body = client.get("/api/bus/between?origin=Oxford&destination=Banbury&limit=100").json()
    assert body["count"] >= 1, body
    assert body["origin"]["label"] == "Oxford"
    assert body["destination"]["label"] == "Banbury"
    assert body["destination"]["lat"] > 51.9, "Banbury is in Oxfordshire, not Coventry"
    _assert_options_connect(body)
    assert any(option["number"] == "S4" for option in body["options"])


def test_a_corridor_with_no_service_says_so_instead_of_guessing(client):
    body = client.get("/api/bus/between?origin=Whitby&destination=Penzance&limit=100").json()
    # A local bus does not run Whitby to Penzance; if anything is returned it
    # must still be a service that really boards at one and alights at the other.
    _assert_options_connect(body)
    assert body["count"] == 0, body["options"][:1]


def test_an_unresolvable_place_is_an_error_not_a_guess(client):
    response = client.get("/api/bus/between?origin=Nowhere-at-all&destination=Leicester")
    assert response.status_code == 404
    assert "Nowhere-at-all" in response.json()["detail"]


def test_the_map_payload_is_drawable(client):
    body = client.get("/api/bus/map?operator=Redline").json()
    assert body["count"] == body["total_matching"] >= 1
    assert body["truncated"] is False
    for feature in body["features"]:
        assert len(feature["coordinates"]) >= 2
        assert feature["stop_count"] >= 2
        for lat, lon in feature["coordinates"]:
            assert 49.0 < lat < 61.5 and -8.5 < lon < 2.5


def test_the_map_simplifies_when_asked(client):
    raw = client.get("/api/bus/map").json()
    trimmed = client.get("/api/bus/map?simplify_m=150").json()
    raw_points = sum(len(f["coordinates"]) for f in raw["features"])
    trimmed_points = sum(len(f["coordinates"]) for f in trimmed["features"])
    assert trimmed_points < raw_points
    # Trimming is for the phone; it must not change which routes are drawn.
    assert trimmed["count"] == raw["count"]


def test_a_capped_map_still_shows_every_operator(client):
    """A capped list must not be one company's network presented as the country."""
    body = client.get("/api/bus/map?limit=20").json()
    assert body["truncated"] is True
    operators = {feature["operator"] for feature in body["features"]}
    assert len(operators) >= 3


def test_bus_routes_filter_by_operator(client):
    operators = client.get("/api/bus/operators").json()
    assert operators["count"] >= 5
    name = operators["operators"][0]["name"]
    listed = client.get(f"/api/bus/routes?operator={name}&limit=100").json()
    assert listed["count"] >= 1
    assert {route["operator"] for route in listed["routes"]} == {name}


def test_every_operator_knows_its_own_route_count(client):
    body = client.get("/api/bus/operators").json()
    for entry in body["operators"]:
        assert entry["routes"] >= entry["services"] >= 1
