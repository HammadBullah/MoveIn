"""API and provenance tests.

    pip install -r requirements-dev.txt
    pytest
"""

from __future__ import annotations

import pytest

from home_ledger import create_app
from home_ledger.extensions import db
from home_ledger.lookups import providers
from home_ledger.provenance import Field, confirmed, missing, suggested

HEADERS = {"X-API-Key": "dev-local-key"}


@pytest.fixture()
def client():
    app = create_app("test")
    with app.test_client() as test_client:
        with app.app_context():
            yield test_client
            db.session.remove()


# ---------------------------------------------------------------------------
# Provenance primitives
# ---------------------------------------------------------------------------


def test_field_rejects_value_with_missing_status():
    with pytest.raises(ValueError):
        Field(value="Wessex Water", source="postcodeLookup", status="missing")


def test_suggestion_is_not_confirmed():
    suggestion = suggested("Wessex Water", "postcodeLookup")
    assert suggestion.needs_confirmation
    assert not suggestion.is_confirmed
    assert suggestion.confirm().source == "userConfirmed"


def test_missing_field_serialises_cleanly():
    payload = missing(note="No lookup available").to_dict()
    assert payload["value"] is None
    assert payload["status"] == "missing"


# ---------------------------------------------------------------------------
# Provider discovery honesty
# ---------------------------------------------------------------------------


def test_discovery_never_invents_an_energy_supplier():
    suggestions = {s.kind: s for s in providers.discover("BS1 4DJ")}

    assert suggestions["water"].provider.value is not None
    assert suggestions["water"].provider.status == "suggested"
    assert suggestions["electricity"].provider.value is None
    assert suggestions["electricity"].confidence == "unknown"
    assert suggestions["gas"].provider.value is None
    assert "gas_supplier" in suggestions["gas"].lookup_keys


# ---------------------------------------------------------------------------
# End to end: address -> household -> discovery -> confirmation
# ---------------------------------------------------------------------------


def create_household(client, postcode="BS1 4DJ"):
    response = client.post(
        "/api/v1/households",
        headers=HEADERS,
        json={
            "address": {
                "line1": "12 Example Street",
                "town": "Bristol",
                "postcode": postcode,
                "uprn": "DEMO-0000000012",
            },
            "tenure": "renting",
            "services": ["electricity", "gas", "water", "wastewater", "councilTax"],
            "residentName": "Sam",
        },
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def test_household_starts_with_no_confirmed_providers(client):
    household = create_household(client)

    for service in household["services"]:
        assert service["provider"]["value"] is None
        assert service["provider"]["status"] == "missing"
        assert service["amountMinor"]["value"] is None

    assert household["property"]["uprn"] == "DEMO-0000000012"
    assert household["members"][0]["role"] == "owner"


def test_discovery_suggests_without_confirming(client):
    household = create_household(client)

    response = client.post(
        f"/api/v1/households/{household['id']}/discover", headers=HEADERS
    )
    assert response.status_code == 200
    updated = response.get_json()["household"]
    by_kind = {slot["kind"]: slot for slot in updated["services"]}

    water = by_kind["water"]["provider"]
    assert water["value"] is not None
    assert water["status"] == "suggested"
    assert water["source"] == "postcodeLookup"

    assert by_kind["electricity"]["provider"]["status"] == "missing"


def test_confirming_a_provider_does_not_confirm_amounts(client):
    household = create_household(client)
    client.post(f"/api/v1/households/{household['id']}/discover", headers=HEADERS)

    updated = client.get(f"/api/v1/households/{household['id']}", headers=HEADERS).get_json()
    water_id = next(s["id"] for s in updated["services"] if s["kind"] == "water")

    response = client.patch(
        f"/api/v1/services/{water_id}",
        headers=HEADERS,
        json={"provider": {"action": "confirm"}},
    )
    assert response.status_code == 200
    service = response.get_json()["service"]

    assert service["provider"]["status"] == "confirmed"
    # The account, amount and payment date are still unknown. That is the point.
    assert service["amountMinor"]["status"] == "missing"
    assert service["nextDueDate"]["status"] == "missing"


def test_discovery_does_not_overwrite_a_resident_answer(client):
    household = create_household(client)
    updated = client.get(f"/api/v1/households/{household['id']}", headers=HEADERS).get_json()
    water_id = next(s["id"] for s in updated["services"] if s["kind"] == "water")

    client.patch(
        f"/api/v1/services/{water_id}",
        headers=HEADERS,
        json={"provider": {"value": "Bristol Water (my own answer)"}},
    )
    client.post(f"/api/v1/households/{household['id']}/discover", headers=HEADERS)

    after = client.get(f"/api/v1/households/{household['id']}", headers=HEADERS).get_json()
    water = next(s for s in after["services"] if s["kind"] == "water")
    assert water["provider"]["value"] == "Bristol Water (my own answer)"
    assert water["provider"]["source"] == "userEntered"


def test_bills_require_an_amount(client):
    household = create_household(client)

    response = client.post(
        f"/api/v1/households/{household['id']}/bills",
        headers=HEADERS,
        json={"kind": "electricity", "dueDate": "2026-10-28"},
    )
    assert response.status_code == 400
    assert "amount" in response.get_json()["error"]["message"].lower()


def test_bill_can_be_recorded_without_a_payment_date(client):
    household = create_household(client)

    response = client.post(
        f"/api/v1/households/{household['id']}/bills",
        headers=HEADERS,
        json={
            "kind": "water",
            "amountMinor": 9000,
            "provider": "Wessex Water",
            "notes": "No date on the statement yet.",
        },
    )
    assert response.status_code == 201
    bill = response.get_json()["bill"]
    assert bill["amountMinor"]["status"] == "confirmed"
    assert bill["dueDate"]["status"] == "missing"


def test_estimate_is_marked_as_an_estimate(client):
    household = create_household(client)

    response = client.post(
        f"/api/v1/households/{household['id']}/bills",
        headers=HEADERS,
        json={
            "kind": "gas",
            "amountMinor": {
                "value": 5400,
                "source": "estimate",
                "status": "suggested",
            },
            "dueDate": {"value": "2026-11-08", "source": "estimate", "status": "suggested"},
        },
    )
    assert response.status_code == 201
    bill = response.get_json()["bill"]
    assert bill["amountMinor"]["source"] == "estimate"
    assert bill["amountMinor"]["status"] == "suggested"


def test_endpoints_require_the_key(client):
    response = client.get("/api/v1/lookups")
    assert response.status_code == 401


def test_health_does_not_require_the_key(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_address_search_reports_demo_mode(client):
    response = client.post(
        "/api/v1/addresses/search", headers=HEADERS, json={"postcode": "bs1 4dj"}
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["isLive"] is False
    assert payload["results"][0]["postcode"] == "BS1 4DJ"
    assert payload["results"][0]["uprn"].startswith("DEMO-")
