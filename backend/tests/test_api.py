"""The HTTP surface: every endpoint the web app calls.

The assertions here are deliberately about *meaning* rather than exact key
names where a value could reasonably be renamed, but every payload the frontend
reads is asserted at least once, so a rename that breaks the app fails here.
"""

from __future__ import annotations

import pytest

DEVICE = {"X-Device-Key": "test-device-0001"}


def _search(client, origin="Nottingham", destination="Birmingham", **extra):
    body = {"origin": origin, "destination": destination, **extra}
    response = client.post("/api/journeys/search", json=body, headers=extra.pop("_headers", DEVICE))
    assert response.status_code == 200, response.text
    return response.json()


# --- meta -----------------------------------------------------------------


def test_health_reports_the_loaded_network(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    network = body["network"]
    assert network["stops"] > 300
    assert network["routes"] >= 78
    assert network["trips"] > 10_000
    assert network["operators"] > 20
    # The database holds the same network, so the two views must agree.
    assert body["database"]["stops"] == network["stops"]
    assert body["database"]["routes"] == network["routes"]


def test_preferences_list_their_weights(client):
    """The UI builds its preference chips from this, so the weights must add up."""
    body = client.get("/api/preferences").json()
    assert body["preferences"]
    assert body["default"]
    keys = {preference["id"] for preference in body["preferences"]}
    assert {"cheapest", "fastest", "best_value"} <= keys
    for preference in body["preferences"]:
        assert preference["label"] and preference["description"]
        assert sum(preference["weights"].values()) == pytest.approx(1.0, abs=0.01)


def test_data_sources_separate_real_from_compiled(client):
    """The brief's honesty requirement, enforced by the API itself."""
    body = client.get("/api/data-sources").json()
    assert body["headline"]
    kinds = {source["kind"] for source in body["sources"]}
    assert "real" in kinds
    assert "compiled" in kinds
    for source in body["sources"]:
        assert source["name"] and source["licence"]
    compiled = next(s for s in body["sources"] if s["kind"] == "compiled")
    assert "not a downloaded feed" in compiled["detail"].lower()
    assert body["network"]["stops"] > 300
    assert body["service_window"]["start"] <= body["service_window"]["end"]


def test_live_feeds_are_declared_with_an_adapter(client):
    """The datasets MoveIn cannot reach are documented, not pretend-fetched."""
    body = client.get("/api/data-sources").json()
    assert body["live_feeds"]
    for feed in body["live_feeds"]:
        assert feed["publisher"] and feed["licence"] and feed["adapter"]
        assert feed["status"]


def test_index_lists_the_endpoints(client):
    body = client.get("/api").json()
    assert body["name"] and body["version"]
    assert len(body["endpoints"]) >= 20


# --- stops ----------------------------------------------------------------


def test_stop_search_finds_a_station(client):
    body = client.get("/api/stops/search", params={"q": "Nottingham Station"}).json()
    assert body["results"]
    top = body["results"][0]
    assert "Nottingham" in top["name"]
    assert top["mode"] in {
        "rail", "bus", "coach", "tram", "metro", "ferry", "taxi", "ridehail", "walk", "cycle", "air",
    }
    assert top["id"] and top["lat"] and top["lon"]


def test_stop_search_respects_its_limit(client):
    body = client.get("/api/stops/search", params={"q": "Street", "limit": 5}).json()
    assert 0 < len(body["results"]) <= 5


def test_stop_search_handles_a_missing_name(client):
    body = client.get("/api/stops/search", params={"q": "Zzzzzz"}).json()
    assert body["results"] == []


def test_nearby_returns_distance_sorted_stops(client):
    body = client.get(
        "/api/stops/nearby", params={"lat": 52.9536, "lon": -1.1505, "radius_m": 800}
    ).json()
    assert body["stops"]
    distances = [item["distance_m"] for item in body["stops"]]
    assert distances == sorted(distances)
    assert distances[-1] <= 800
    assert all(item["route_count"] >= 1 for item in body["stops"])


def test_stop_detail_resolves_operator_names(client):
    """The corridor spec's short codes must resolve to the real companies."""
    stop = client.get("/api/stops/rail:NOT").json()
    body = client.get(f"/api/stops/{stop['id']}").json()
    assert body["name"] == stop["name"] == "Nottingham"
    assert body["crs_code"] == "NOT"
    assert body["routes"], "a station should have routes serving it"
    assert body["route_count"] == len(body["routes"])
    for route in body["routes"]:
        assert route["mode"]
        assert route["operator"]["name"]
        assert not route["operator"]["name"].startswith("Unknown"), route


def test_unknown_stop_is_a_404_not_a_crash(client):
    assert client.get("/api/stops/rail:NOT_A_STOP").status_code == 404


def test_regions_are_the_modelled_cities(client):
    body = client.get("/api/stops/regions").json()
    names = {region["name"] for region in body["regions"]}
    for expected in ("Nottingham", "Birmingham", "Leeds", "Manchester"):
        assert expected in names
    for region in body["regions"]:
        assert region["lat"] and region["lon"] and region["radius_m"] > 0


# --- journeys -------------------------------------------------------------


def test_journey_search_returns_ranked_options(client):
    body = _search(client)
    assert body["journeys"]
    assert body["origin"]["label"] and body["destination"]["label"]
    assert body["diagnostics"]["search_ms"] >= 0
    assert body["diagnostics"]["services"] > 0

    scores = [journey["score"] for journey in body["journeys"]]
    assert scores == sorted(scores, reverse=True), "results come back best first"
    for journey in body["journeys"]:
        assert journey["departure"] < journey["arrival"]
        assert journey["price"] >= 0
        assert journey["legs"]
        assert journey["duration_label"]
        assert 0 <= journey["score"] <= 100
        assert journey["summary"]


def test_journey_legs_are_fully_described(client):
    """The UI renders instructions and a map straight from the payload."""
    body = _search(client, "Nottingham", "Leeds")
    assert body["journeys"]
    for journey in body["journeys"]:
        for leg in journey["legs"]:
            assert leg["kind"] in {"transit", "walk", "on_demand"}
            assert leg["mode"] and leg["mode_label"]
            assert leg["from"]["lat"] is not None
            assert leg["to"]["lat"] is not None
            if leg["kind"] == "transit":
                assert leg["instruction"]
                assert leg["operator"]["name"]
                assert leg["route_name"]
                assert leg["headsign"]
                assert leg["departure"] < leg["arrival"]
                assert leg["distance_km"] > 0
                assert leg["stops_count"] >= 2
                assert leg["trip_id"]


def test_transit_legs_follow_the_real_corridor(client):
    """A leg with no intermediate geometry is a leg whose stops did not resolve."""
    body = _search(client, "Nottingham", "London")
    transit = [
        leg
        for journey in body["journeys"]
        for leg in journey["legs"]
        if leg["kind"] == "transit"
    ]
    assert transit
    long_legs = [leg for leg in transit if leg["stops_count"] > 2]
    assert long_legs, "expected at least one leg calling at intermediate stops"
    for leg in long_legs:
        assert leg["intermediate_stops"], "a multi-stop leg must carry its stops"
        for stop in leg["intermediate_stops"]:
            assert stop["name"] and stop["lat"] and stop["lon"]


def test_journey_polyline_is_drawable(client):
    body = _search(client, "Nottingham", "Leeds")
    for journey in body["journeys"]:
        polyline = journey["polyline"]
        assert len(polyline) >= 2
        assert all(len(point) == 2 for point in polyline)
        assert all(-90 <= lat <= 90 and -180 <= lon <= 180 for lat, lon in polyline)


def test_fare_breakdown_is_explained_to_the_traveller(client):
    journey = _search(client)["journeys"][0]
    fare = journey["fare"]
    assert fare["currency"] == "GBP"
    assert fare["total"] >= 0
    assert fare["tickets"]
    assert fare["leg_prices"]
    for ticket in fare["tickets"]:
        assert ticket["label"] and ticket["price"] >= 0
        assert ticket["covers_legs"], "a ticket that covers nothing explains nothing"
    singles = sum(leg["base_price"] for leg in fare["leg_prices"])
    assert fare["total"] <= singles + 0.01


def test_archetypes_are_labelled(client):
    body = _search(client)
    known = {
        "cheapest", "fastest", "fewest_changes", "least_walking",
        "lowest_emissions", "best_value", "accessible",
    }
    seen = set()
    for journey in body["journeys"]:
        assert len(journey["archetypes"]) == len(journey["archetype_labels"])
        for archetype in journey["archetypes"]:
            assert archetype in known
            seen.add(archetype)
    assert {"cheapest", "fastest"} <= seen


def test_preference_changes_the_answer(client):
    cheap = _search(client, "Nottingham", "Leeds", preference="cheapest")["journeys"][0]
    fast = _search(client, "Nottingham", "Leeds", preference="fastest")["journeys"][0]
    assert cheap["price"] <= fast["price"] + 0.01
    assert fast["duration_s"] <= cheap["duration_s"] + 60


def test_step_free_search_is_enforced(client):
    body = _search(client, options={"step_free_only": True})
    for journey in body["journeys"]:
        assert journey["step_free"]
        for leg in journey["legs"]:
            assert leg["step_free"]


def test_traveller_options_are_accepted(client):
    """Regression: the API once passed the wrong field names and 500'd on every search."""
    body = _search(
        client,
        traveller={"railcard": True, "student": True, "children": 2, "max_walk_m": 900},
    )
    assert body["journeys"]


def test_an_unknown_place_is_reported_not_guessed(client):
    response = client.post(
        "/api/journeys/search", json={"origin": "Xyzzy", "destination": "Birmingham"}
    )
    assert response.status_code == 422
    assert "could not find" in response.json()["detail"]


def test_coordinates_work_as_a_place(client):
    body = _search(client, "52.9536,-1.1505", "52.4862,-1.8904")
    assert body["journeys"]


def test_missing_departure_means_now(client):
    response = client.post(
        "/api/journeys/search", json={"origin": "Nottingham", "destination": "Derby"}
    )
    assert response.status_code == 200
    assert response.json()["journeys"]


def test_search_accepts_a_natural_language_preference(client):
    """The API is forgiving about how a preference is spelled."""
    for value in ("cheap", "quickest", "green", "fewest changes"):
        response = client.post(
            "/api/journeys/search",
            json={"origin": "Nottingham", "destination": "Derby", "preference": value},
        )
        assert response.status_code == 200, value
        assert response.json()["preference"] == {
            "cheap": "cheapest",
            "quickest": "fastest",
            "green": "lowest_emissions",
            "fewest changes": "fewest_changes",
        }[value]


def test_emissions_comparison_ranks_the_modes(client):
    body = client.post(
        "/api/journeys/compare-emissions",
        json={"origin": "Nottingham", "destination": "London"},
    ).json()
    assert body["modes"]
    co2 = [option["co2_g"] for option in body["modes"]]
    assert co2 == sorted(co2), "the greenest option should be listed first"
    assert body["modes"][0]["mode"] == "walk"
    assert body["greenest"]
    assert body["distance_km"] > 100
    for option in body["modes"]:
        assert option["mode_label"] and option["g_per_km"] >= 0


# --- network --------------------------------------------------------------


def test_network_summary_is_internally_consistent(client):
    body = client.get("/api/network/summary").json()
    assert sum(body["routes_by_mode"].values()) == body["routes"]
    assert body["stops"] == sum(body["stops_by_region"].values()) or body["stops"] > 0
    assert body["trips"] > 10_000
    assert body["operators"] >= 20
    assert body["service_window"]["start"] <= body["service_window"]["end"]
    # Every mode a passenger can board is represented.
    assert {"rail", "bus", "coach"} <= set(body["routes_by_mode"])


def test_network_operators_resolve_to_real_names(client):
    body = client.get("/api/network/operators").json()
    assert body["count"] >= 20
    assert len(body["operators"]) == body["count"]
    for operator in body["operators"]:
        assert operator["name"] and operator["code"]
        assert not operator["name"].startswith("Unknown"), operator
        assert operator["modes"] and operator["routes"] >= 1


def test_network_routes_filter_by_mode(client):
    for mode in ("rail", "coach"):
        body = client.get("/api/network/routes", params={"mode": mode}).json()
        assert body["routes"]
        assert all(route["mode"] == mode for route in body["routes"])

    rail = client.get("/api/network/routes", params={"mode": "rail"}).json()
    assert len(rail["routes"]) >= 15


def test_network_routes_filter_by_region(client):
    body = client.get("/api/network/routes", params={"region": "london"}).json()
    assert body["routes"]


# --- fares ----------------------------------------------------------------


def test_fare_products_are_listed_with_prices(client):
    body = client.get("/api/fares/products").json()
    assert body["count"] >= 100
    assert body["products"]
    assert body["note"]
    for product_type, products in body["products"].items():
        assert products
        for product in products:
            assert product["label"] and product["price"] >= 0
            assert product["operator_name"]
            assert not product["operator_name"].startswith("Unknown"), product


def test_fare_operators_are_listed(client):
    body = client.get("/api/fares/operators").json()
    assert body["count"] >= 20
    for operator in body["operators"]:
        assert operator["name"] and operator["mode"]


# --- live -----------------------------------------------------------------


def test_live_vehicles_are_between_real_stops(client):
    body = client.get("/api/live/vehicles").json()
    assert body["vehicles"], "the simulator should be running some vehicles"
    assert body["count"] == len(body["vehicles"])
    assert body["source"] and body["note"]
    for vehicle in body["vehicles"]:
        assert vehicle["trip_id"] and vehicle["route_id"]
        assert vehicle["mode"] and vehicle["route_name"] and vehicle["headsign"]
        assert -90 <= vehicle["lat"] <= 90
        assert -180 <= vehicle["lon"] <= 180
        assert vehicle["next_stop"]["name"]
        assert 0 <= vehicle["progress"] <= 1
        assert vehicle["speed_mps"] >= 0
        assert vehicle["delay_label"]


def test_live_vehicles_can_be_filtered_by_route(client):
    everything = client.get("/api/live/vehicles", params={"limit": 200}).json()["vehicles"]
    route_id = everything[0]["route_id"]
    filtered = client.get("/api/live/vehicles", params={"route_id": route_id}).json()
    assert filtered["vehicles"]
    assert all(v["route_id"] == route_id for v in filtered["vehicles"])


def test_live_alerts_are_scoped_and_severe(client):
    body = client.get("/api/live/alerts").json()
    assert body["count"] == len(body["alerts"])
    for alert in body["alerts"]:
        assert alert["severity"] in {"info", "warning", "severe"}
        assert alert["header"] and alert["description"]
        assert alert["route_ids"] is not None
        assert alert["stop_ids"] is not None
        assert alert["regions"] is not None
        assert alert["source"]


def test_alerts_can_be_filtered_by_region(client):
    body = client.get("/api/live/alerts", params={"region": "nottingham"}).json()
    for alert in body["alerts"]:
        assert "nottingham" in alert["regions"]


def test_tracking_a_journey_needs_a_device_key(client):
    vehicles = client.get("/api/live/vehicles").json()["vehicles"]
    trip = vehicles[0]
    payload = {
        "journey_id": "test-journey",
        "payload": {
            "legs": [
                {
                    "kind": "transit",
                    "trip_id": trip["trip_id"],
                    "route_name": trip["route_name"],
                    "departure": "08:00",
                    "arrival": "09:00",
                    "departure_s": 28800,
                    "arrival_s": 32400,
                }
            ]
        },
    }
    assert client.post("/api/live/track", json=payload).status_code == 401

    tracked = client.post("/api/live/track", json=payload, headers=DEVICE)
    assert tracked.status_code == 200, tracked.text
    body = tracked.json()
    assert body["journey_id"] == "test-journey"
    assert body["status"] and body["advice"]
    assert len(body["legs"]) == 1
    leg = body["legs"][0]
    assert leg["trip_id"] == trip["trip_id"]
    assert leg["status"] in {"on_time", "delayed", "early"}
    assert leg["expected_departure"] and leg["expected_arrival"]


# --- saved journeys and alerts -------------------------------------------


def test_saving_a_journey_round_trips(client):
    saved = client.post(
        "/api/me/saved",
        json={"origin": "Nottingham", "destination": "Birmingham", "label": "Weekly trip"},
        headers=DEVICE,
    )
    assert saved.status_code == 201, saved.text
    saved_id = saved.json()["id"]

    listed = client.get("/api/me/saved", headers=DEVICE).json()
    assert listed["count"] == len(listed["saved"])
    entry = next(item for item in listed["saved"] if item["id"] == saved_id)
    assert entry["label"] == "Weekly trip"
    assert entry["origin"]["label"] and entry["origin"]["lat"]
    assert entry["destination"]["label"] and entry["destination"]["lat"]
    assert entry["preference"]

    removed = client.delete(f"/api/me/saved/{saved_id}", headers=DEVICE)
    assert removed.status_code == 200
    assert removed.json()["deleted"] is True
    remaining = client.get("/api/me/saved", headers=DEVICE).json()["saved"]
    assert all(item["id"] != saved_id for item in remaining)


def test_saved_journeys_are_per_device(client):
    """One device must never see another's saved journeys."""
    client.post(
        "/api/me/saved",
        json={"origin": "Nottingham", "destination": "Derby", "label": "Private"},
        headers={"X-Device-Key": "device-a"},
    )
    other = client.get("/api/me/saved", headers={"X-Device-Key": "device-b"}).json()
    assert all(item["label"] != "Private" for item in other["saved"])


def test_a_device_key_can_arrive_in_the_body(client):
    """Clients that cannot set headers are still able to save a journey."""
    response = client.post(
        "/api/me/saved",
        json={"origin": "Nottingham", "destination": "Leeds", "device_key": "body-key"},
    )
    assert response.status_code == 201, response.text
    listed = client.get("/api/me/saved", headers={"X-Device-Key": "body-key"}).json()
    assert listed["saved"]


def test_device_key_is_required_for_personal_data(client):
    assert client.get("/api/me/saved").status_code == 401
    assert client.get("/api/me/alerts").status_code == 401
    assert client.get("/api/me/history").status_code == 401


def test_saving_an_unknown_place_is_rejected(client):
    response = client.post(
        "/api/me/saved",
        json={"origin": "Xyzzy", "destination": "Birmingham"},
        headers=DEVICE,
    )
    assert response.status_code == 422


def test_search_history_records_what_was_searched(client):
    headers = {"X-Device-Key": "history-device"}
    client.post(
        "/api/journeys/search",
        json={"origin": "Nottingham", "destination": "Leeds"},
        headers=headers,
    )
    body = client.get("/api/me/history", headers=headers).json()
    assert body["count"] == len(body["history"]) >= 1
    entry = body["history"][0]
    assert entry["origin"] == "Nottingham"
    assert entry["destination"] == "Leeds"
    assert entry["best_price"] > 0
    assert entry["searched_at"]


def test_history_is_bounded(client):
    headers = {"X-Device-Key": "chatty-device"}
    for _ in range(2):
        client.post(
            "/api/journeys/search",
            json={"origin": "Nottingham", "destination": "Derby"},
            headers=headers,
        )
    body = client.get("/api/me/history", params={"limit": 1}, headers=headers).json()
    assert len(body["history"]) == 1


def test_price_alerts_can_be_watched_and_triggered(client):
    headers = {"X-Device-Key": "alert-device"}
    created = client.post(
        "/api/me/alerts",
        json={"origin": "Nottingham", "destination": "London", "target_price": 999},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["watching"] == "Nottingham to London"
    assert body["current_best_price"] > 0, "an alert should know today's price"
    alert_id = body["id"]

    listed = client.get("/api/me/alerts", headers=headers).json()["alerts"]
    assert any(alert["id"] == alert_id for alert in listed)

    checked = client.get("/api/me/alerts/check", headers=headers)
    assert checked.status_code == 200
    report = checked.json()
    assert report["checked"] >= 1
    # The target is higher than any real fare, so it must have triggered.
    assert report["triggered"] >= 1
    assert report["results"][0]["price_label"].startswith("£")

    removed = client.delete(f"/api/me/alerts/{alert_id}", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["deleted"] is True


# --- the edge cases a real user will find --------------------------------


def test_identical_origin_and_destination(client):
    response = client.post(
        "/api/journeys/search",
        json={"origin": "Nottingham", "destination": "Nottingham"},
    )
    assert response.status_code == 200


def test_a_past_departure_still_answers(client):
    """Asking for a train that has gone must explain itself, not 500."""
    response = client.post(
        "/api/journeys/search",
        json={
            "origin": "Nottingham",
            "destination": "Birmingham",
            "departure": "2026-09-14T09:00:00",
        },
    )
    assert response.status_code == 200
    assert response.json()["journeys"]


def test_nonsense_preference_is_rejected_cleanly(client):
    response = client.post(
        "/api/journeys/search",
        json={"origin": "Nottingham", "destination": "Derby", "preference": "teleport"},
    )
    assert response.status_code == 422


def test_empty_search_is_rejected_cleanly(client):
    assert (
        client.post("/api/journeys/search", json={"origin": "", "destination": ""}).status_code
        == 422
    )


def test_every_request_reports_its_duration(client):
    response = client.get("/api/health")
    assert "x-movein-duration-ms" in {key.lower() for key in response.headers}


def test_the_departure_on_the_card_is_the_departure_of_the_first_leg(client):
    """The journey headline and its own itinerary must agree about the start.

    A card that says "departs 11:07" above a first leg that starts at 11:36 is
    the kind of thing nobody notices in a demo and everybody notices when they
    are standing on a platform.
    """
    body = client.post(
        "/api/journeys/search",
        json={"origin": "Nottingham", "destination": "Leeds", "limit": 6},
    ).json()
    assert body["journeys"]
    for journey in body["journeys"]:
        first = journey["legs"][0]
        start = first.get("start_time") or first.get("departure")
        assert start == journey["departure_time"], (
            f"{journey['summary']}: first leg starts {start} "
            f"but the journey says {journey['departure_time']}"
        )
        assert journey["duration_s"] >= 0
        assert journey["arrival"] >= journey["departure"]


# --- walking ---------------------------------------------------------------


def test_a_journey_says_how_long_its_longest_walk_is(client):
    """The number that matters is the worst single walk, not the total."""
    body = client.post(
        "/api/journeys/search",
        json={"origin": "Nottingham", "destination": "Birmingham", "limit": 8},
    ).json()
    assert body["journeys"]
    for journey in body["journeys"]:
        assert journey["longest_walk_s"] >= 0
        assert journey["longest_walk_s"] <= journey["walking_s"] + 1
        assert journey["walk_comfort"] in ("comfortable", "long")
        assert journey["walk_warning"] is (journey["walk_comfort"] != "comfortable")
        if journey["longest_walk_s"] > 15 * 60:
            assert journey["walk_comfort"] == "long", (
                "a walk over the comfort threshold must be flagged"
            )


def test_a_walk_limit_is_respected_and_reported(client):
    """Ask for a 20 minute maximum and no option may need more."""
    body = client.post(
        "/api/journeys/search",
        json={
            "origin": "Nottingham",
            "destination": "Birmingham",
            "limit": 10,
            "max_walk_minutes": 20,
        },
    ).json()
    assert body["journeys"]
    for journey in body["journeys"]:
        assert journey["longest_walk_s"] <= 20 * 60


def test_an_impossible_walk_limit_says_why_instead_of_showing_nothing(client):
    """An empty screen is not an answer: show what relaxing the limit buys."""
    body = client.post(
        "/api/journeys/search",
        json={
            "origin": "Nottingham",
            "destination": "Birmingham",
            "limit": 10,
            "max_walk_minutes": 4,
        },
    ).json()

    assert body["journeys"], "the traveller is shown the options anyway, labelled"
    assert body["diagnostics"]["walk_limit_relaxed"] == 4
    assert body["notice"]["kind"] == "walk_limit_relaxed"
    assert "4 minute walk" in body["notice"]["message"]
    assert body["notice"]["shortest_walk_minutes"] >= 4


def test_the_walk_limit_is_optional(client):
    """No limit means the network default applies, and nothing is announced."""
    body = client.post(
        "/api/journeys/search",
        json={"origin": "Nottingham", "destination": "Birmingham", "limit": 5},
    ).json()
    assert body["notice"] is None
    assert "walk_limit_relaxed" not in body["diagnostics"]


# ---------------------------------------------------------------------------
# Coverage: the register versus the corridors
# ---------------------------------------------------------------------------


def test_a_real_stop_off_the_modelled_network_can_still_be_searched(client):
    """The register is searchable, not just the 400-odd modelled stops."""
    body = client.get("/api/stops/search", params={"q": "Mapperley", "limit": 5}).json()
    assert body["results"], "Mapperley is a real place with real stops"
    hit = body["results"][0]
    assert hit["id"].startswith("naptan:")
    assert hit["served"] is False
    assert hit["nearest_served"]["name"], "an off-network stop still points at somewhere served"


def test_a_search_only_returns_stops_near_the_cities_movein_models(client):
    """The register is national with no locality column, so region anchoring decides."""
    body = client.get("/api/stops/search", params={"q": "Mapperley", "limit": 8}).json()
    regions = {hit["region"] for hit in body["results"]}
    assert regions == {"nottingham"}, regions
    # Every hit is a real stop at a real coordinate in reach of the network.
    for hit in body["results"]:
        if hit["served"] is False:
            assert hit["nearest_served"]["distance_m"] > 0


def test_planning_from_an_off_network_stop_says_so(client):
    """The traveller can start anywhere; the answer must not pretend otherwise."""
    body = client.post(
        "/api/journeys/search",
        json={"origin": "Mapperley", "destination": "Birmingham", "limit": 3},
    ).json()
    assert body["origin"]["served"] is False
    assert body["origin"]["nearest_served"]["name"]
    assert body["journeys"], "walking to the nearest served stop is a journey"
    assert body["diagnostics"]["off_network"] == ["origin"]
    # The walk to the network is longer than a bus-stop amble would normally be
    # allowed to be, which is exactly the point: it is not optional here.
    assert body["diagnostics"]["access_walk_widened_m"] > 2000
    assert any(j["longest_walk_s"] > 900 for j in body["journeys"])


def test_a_stop_no_modelled_route_reaches_is_answered_not_ignored(client):
    """A real stop 11 km from the network gets an explanation, not an empty list.

    Syerston is a real Nottinghamshire village served by real buses; it is just
    not on a corridor MoveIn compiles.  Silently returning nothing would look
    like the place does not exist.
    """
    body = client.post(
        "/api/journeys/search",
        json={"origin": "Syerston", "destination": "Birmingham", "limit": 3},
    ).json()
    assert body["journeys"] == []
    assert body["origin"]["served"] is False
    assert body["notice"]["kind"] == "off_network"
    assert body["notice"]["end"] == "origin"
    assert body["notice"]["label"] == body["origin"]["label"]
    assert "real stop" in body["notice"]["message"]


def test_the_register_has_no_placeholder_names(client):
    body = client.get("/api/stops/search", params={"q": "Na", "limit": 8}).json()
    assert all(hit["name"].strip().casefold() not in {"na", "n/a"} for hit in body["results"])


def test_a_served_stop_is_marked_served(client):
    body = client.post(
        "/api/journeys/search",
        json={"origin": "Nottingham", "destination": "Birmingham", "limit": 2},
    ).json()
    assert body["origin"]["served"] is True
    assert body["origin"]["nearest_served"] == {}


def test_coverage_reports_the_gap_rather_than_hiding_it(client):
    body = client.get("/api/network/coverage").json()
    assert body["modelled_stops"] > 0
    assert body["named_stops_held"] > body["modelled_stops"] * 10, "coverage is genuinely partial"
    assert body["named_stops_searchable"] > 0
    nottingham = next(row for row in body["regions"] if row["region"] == "nottingham")
    assert nottingham["modelled_stops"] > 0
    assert nottingham["real_stops_held"] > nottingham["modelled_stops"]
    assert 0 < nottingham["coverage_pct"] < 5
    assert nottingham["routes"] > 0 and nottingham["operators"] > 0
    # Cities MoveIn does not model are listed too -- a zero is information.
    assert any(row["modelled_stops"] == 0 for row in body["regions"])


# ---------------------------------------------------------------------------
# The traveller's own limits: modes, budget, deadline
# ---------------------------------------------------------------------------


def test_a_mode_filter_returns_only_journeys_using_those_modes(client):
    """The transport sheet says which modes you will use, and is believed."""
    body = client.post(
        "/api/journeys/search",
        json={
            "origin": "Nottingham",
            "destination": "Birmingham",
            "limit": 6,
            "options": {"modes": ["rail"]},
        },
    ).json()

    assert body["journeys"], "there is a train between these two"
    for journey in body["journeys"]:
        used = {leg["mode"] for leg in journey["legs"] if leg["kind"] == "transit"}
        assert used == {"rail"}, used


def test_a_mode_filter_with_no_answer_says_which_filter_did_it(client):
    body = client.post(
        "/api/journeys/search",
        json={
            "origin": "Nottingham",
            "destination": "Birmingham",
            "limit": 4,
            "options": {"modes": ["ferry"]},
        },
    ).json()

    assert body["journeys"] == []
    assert body["notice"]["kind"] == "modes"
    assert "ferry" in body["notice"]["message"].lower()


def test_a_budget_is_a_ceiling_not_a_suggestion(client):
    generous = client.post(
        "/api/journeys/search",
        json={"origin": "Nottingham", "destination": "Birmingham", "limit": 8},
    ).json()
    cheapest = min(j["price"] for j in generous["journeys"])

    body = client.post(
        "/api/journeys/search",
        json={
            "origin": "Nottingham",
            "destination": "Birmingham",
            "limit": 8,
            "options": {"max_price": cheapest + 0.5},
        },
    ).json()

    assert body["journeys"]
    for journey in body["journeys"]:
        assert journey["price"] <= cheapest + 0.5 + 0.005


def test_a_budget_that_buys_nothing_is_explained(client):
    body = client.post(
        "/api/journeys/search",
        json={
            "origin": "Nottingham",
            "destination": "Birmingham",
            "limit": 4,
            "options": {"max_price": 0.5},
        },
    ).json()

    assert body["journeys"] == []
    assert body["notice"]["kind"] == "max_price"
    assert body["diagnostics"]["over_budget"] > 0


def test_arrive_by_returns_journeys_that_make_the_deadline(client):
    body = client.post(
        "/api/journeys/search",
        json={
            "origin": "Nottingham",
            "destination": "Birmingham",
            "limit": 6,
            "arrive_by": "2026-10-07T23:30:00+01:00",
        },
    ).json()

    assert body["journeys"]
    for journey in body["journeys"]:
        assert journey["arrival_time"] <= "23:30"


def test_arrive_by_in_the_past_reports_the_deadline_it_missed(client):
    body = client.post(
        "/api/journeys/search",
        json={
            "origin": "Nottingham",
            "destination": "Birmingham",
            "limit": 4,
            "departure": "2026-10-07T20:00:00+01:00",
            "arrive_by": "2026-10-07T20:05:00+01:00",
        },
    ).json()

    assert body["journeys"] == []
    assert body["notice"]["kind"] == "arrive_by"


# ---------------------------------------------------------------------------
# The map's data
# ---------------------------------------------------------------------------


def test_every_route_can_be_drawn(client):
    """The map overlay is the whole network, not a sample of it."""
    body = client.get("/api/network/map").json()

    assert body["count"] >= 80
    assert len(body["features"]) == body["count"]
    for feature in body["features"]:
        assert len(feature["coordinates"]) >= 2, f"{feature['id']} has no line to draw"
        for lat, lon in feature["coordinates"]:
            assert 49.0 < lat < 61.5, f"{feature['id']} has a latitude off the map: {lat}"
            assert -8.5 < lon < 2.5, f"{feature['id']} has a longitude off the map: {lon}"


def test_the_map_payload_is_small_enough_to_send(client):
    """It is fetched on every results screen, so it has to be a small download."""
    response = client.get("/api/network/map")

    assert len(response.content) < 120_000, f"{len(response.content)} bytes for the overlay"


def test_a_route_on_the_map_really_stops_where_it_stops(client):
    """A line drawn through the wrong places is worse than no line."""
    features = client.get("/api/network/map?mode=rail").json()["features"]
    assert features
    line = next(f for f in features if len(f["coordinates"]) > 3)

    # The first drawable point is the first stop the pattern calls at, so there
    # must be a modelled stop there -- a line that starts in a field is a bug.
    first_lat, first_lon = line["coordinates"][0]
    nearby = client.get(
        "/api/stops/nearby",
        params={"lat": first_lat, "lon": first_lon, "radius_m": 60, "limit": 5},
    ).json()
    assert nearby["stops"], f"no modelled stop within 60 m of {line['id']}'s first point"


def test_the_map_can_be_asked_for_one_mode(client):
    body = client.get("/api/network/map", params={"mode": "tram"}).json()

    assert body["count"] > 0
    assert {feature["mode"] for feature in body["features"]} == {"tram"}
