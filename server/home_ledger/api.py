"""HTTP API.

Deliberately boring: JSON in, JSON out, and every value carries provenance.

Endpoints
---------
GET    /api/health
GET    /api/v1/lookups
POST   /api/v1/addresses/search          {postcode}
POST   /api/v1/households                {address, tenure, services[], residentName}
GET    /api/v1/households/<id>
POST   /api/v1/households/<id>/discover
PATCH  /api/v1/services/<id>
POST   /api/v1/households/<id>/bills
PATCH  /api/v1/bills/<id>
DELETE /api/v1/bills/<id>
POST   /api/v1/households/<id>/reminders
PATCH  /api/v1/reminders/<id>
DELETE /api/v1/reminders/<id>
POST   /api/v1/households/<id>/documents
GET    /api/v1/households/<id>/documents
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional

from flask import Blueprint, current_app, jsonify, request

from .extensions import db
from .lookups import os_places, providers
from .models import (
    Bill,
    Document,
    Household,
    Member,
    Property,
    Reminder,
    ServiceSlot,
    new_id,
    parse_date,
)
from .provenance import Field, confirmed, missing

bp = Blueprint("api", __name__, url_prefix="/api/v1")

VALID_TENURES = {"renting", "owning", "other"}
VALID_SERVICE_KINDS = {
    "electricity",
    "gas",
    "water",
    "wastewater",
    "councilTax",
    "broadband",
    "tvLicence",
    "homeInsurance",
    "other",
}
VALID_ROLES = {"owner", "tenant", "housemate", "viewer"}

DEFAULT_LOOKUP_KEYS = {
    "electricity": ["electricity_supplier"],
    "gas": ["gas_supplier"],
    "water": ["water_provider"],
    "wastewater": ["water_provider"],
    "councilTax": ["council_tax", "find_council"],
    "tvLicence": ["tv_licence"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def error(message: str, status: int = 400):
    return jsonify({"error": {"message": message}}), status


def require_key(view: Callable[..., Any]) -> Callable[..., Any]:
    """Shared-key guard.

    A single key is fine for a development scaffold and nothing more. Real auth
    needs a user session, household membership checks on every read and write,
    and an audit trail.
    """

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        expected = current_app.config.get("API_KEY")
        provided = request.headers.get("X-API-Key", "")
        if not expected or provided != expected:
            return error("Not authorised.", 401)
        return view(*args, **kwargs)

    return wrapper


def normalise_postcode(value: str) -> str:
    compact = "".join(value.split()).upper()
    if len(compact) < 5:
        return compact
    return f"{compact[:-3]} {compact[-3:]}"


def _household(household_id: str) -> Optional[Household]:
    return db.session.get(Household, household_id)


def _field_from(payload: Any, *, default_source: str, coerce: Callable[[Any], Any]):
    """Accept either a bare value or a full Field dict.

    A bare value is treated as confirmed-by-resident, because the client only
    sends a bare value when the resident entered it.
    """
    if payload is None:
        return missing()
    if isinstance(payload, dict) and "status" in payload:
        field = Field.from_dict(payload)
        value = coerce(field.value) if field.value is not None else None
        return Field(
            value=value,
            source=field.source,
            status=field.status,
            recorded_at=field.recorded_at,
            note=field.note,
        )
    value = coerce(payload)
    if value is None:
        return missing()
    return confirmed(value, default_source)


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_date(value: Any) -> Optional[str]:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else None


# ---------------------------------------------------------------------------
# Health and reference data
# ---------------------------------------------------------------------------


@bp.get("/lookups")
@require_key
def lookups():
    """Official lookup links, so the client does not hardcode them."""
    return jsonify({"lookups": providers.LOOKUP_LINKS})


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------


@bp.post("/addresses/search")
@require_key
def address_search():
    body = request.get_json(silent=True) or {}
    postcode = normalise_postcode(str(body.get("postcode", "")))
    if not postcode:
        return error("A postcode is required.")

    mode = current_app.config.get("ADDRESS_PROVIDER", "demo")
    if mode == "os_places":
        try:
            results = os_places.search_postcode(
                postcode,
                api_key=current_app.config["OS_PLACES_API_KEY"],
                url=current_app.config["OS_PLACES_URL"],
                timeout=current_app.config["ADDRESS_LOOKUP_TIMEOUT_SECONDS"],
            )
        except os_places.AddressLookupError as exc:
            return error(str(exc), 502)
        return jsonify(
            {
                "source": "OS Places",
                "isLive": True,
                "results": [result.to_dict() for result in results],
            }
        )

    # Demo mode: same shape, obviously fake provenance.
    return jsonify(
        {
            "source": "Demo address catalogue",
            "isLive": False,
            "results": [
                {
                    "line1": "12 Example Street",
                    "line2": None,
                    "town": "Bristol",
                    "postcode": postcode,
                    "uprn": "DEMO-0000000012",
                    "source": "Demo address catalogue",
                },
                {
                    "line1": "14 Example Street",
                    "line2": None,
                    "town": "Bristol",
                    "postcode": postcode,
                    "uprn": "DEMO-0000000014",
                    "source": "Demo address catalogue",
                },
            ],
        }
    )


# ---------------------------------------------------------------------------
# Households
# ---------------------------------------------------------------------------


@bp.post("/households")
@require_key
def create_household():
    body = request.get_json(silent=True) or {}
    address = body.get("address") or {}
    if not isinstance(address, dict):
        return error("address must be an object.")

    for key in ("line1", "town", "postcode"):
        if not str(address.get(key, "")).strip():
            return error(f"address.{key} is required.")

    tenure = str(body.get("tenure", "other"))
    if tenure not in VALID_TENURES:
        return error("tenure must be renting, owning or other.")

    requested = body.get("services") or ["electricity", "gas", "water", "councilTax"]
    unknown = [kind for kind in requested if kind not in VALID_SERVICE_KINDS]
    if unknown:
        return error(f"unknown service kinds: {', '.join(unknown)}")

    household = Household(name=str(body.get("name") or "My Home"))
    property_ = Property(
        id=new_id("prop"),
        line1=str(address["line1"]).strip(),
        line2=(str(address.get("line2")).strip() if address.get("line2") else None),
        town=str(address["town"]).strip(),
        postcode=normalise_postcode(str(address["postcode"])),
        uprn=(str(address["uprn"]).strip() if address.get("uprn") else None),
        tenure=tenure,
        address_source=str(address.get("source") or "Manual entry"),
        is_demo_data=bool(address.get("isDemoData", False)),
    )
    household.property = property_

    resident_name = str(body.get("residentName") or "").strip() or "You"
    household.members.append(Member(name=resident_name, role="owner"))

    for kind in dict.fromkeys(requested):  # de-duplicate, keep order
        household.services.append(
            ServiceSlot(
                id=new_id("svc"),
                kind=kind,
                provider=missing().to_dict(),
                account_number=missing().to_dict(),
                amount_minor=missing().to_dict(),
                next_due_date=missing().to_dict(),
                lookup_keys=DEFAULT_LOOKUP_KEYS.get(kind, []),
            )
        )

    db.session.add(household)
    db.session.commit()
    return jsonify(_household_payload(household)), 201


@bp.get("/households/<household_id>")
@require_key
def get_household(household_id: str):
    household = _household(household_id)
    if household is None:
        return error("Household not found.", 404)
    return jsonify(_household_payload(household))


@bp.post("/households/<household_id>/discover")
@require_key
def discover_providers(household_id: str):
    """Apply provider suggestions without touching confirmed values."""
    household = _household(household_id)
    if household is None:
        return error("Household not found.", 404)
    if household.property is None:
        return error("Household has no property.", 409)

    suggestions = providers.discover(household.property.postcode)
    by_kind = {slot.kind: slot for slot in household.services}

    applied = 0
    for suggestion in suggestions:
        slot = by_kind.get(suggestion.kind)
        if slot is None:
            continue
        existing = Field.from_dict(slot.provider)
        # A resident's own answer always wins over a lookup.
        if existing.is_confirmed or existing.source in {"userEntered", "userConfirmed"}:
            continue
        slot.provider = suggestion.provider.to_dict()
        merged = list(dict.fromkeys(list(slot.lookup_keys or []) + suggestion.lookup_keys))
        slot.lookup_keys = merged
        applied += 1

    db.session.commit()
    return jsonify(
        {
            "applied": applied,
            "suggestions": [suggestion.to_dict() for suggestion in suggestions],
            "household": _household_payload(household),
        }
    )


@bp.patch("/services/<service_id>")
@require_key
def update_service(service_id: str):
    """Update one service slot.

    Allowed bodies (any combination):
      {"provider": {"action": "confirm"}}
      {"provider": {"action": "reject"}}
      {"provider": {"value": "Octopus Energy"}}
      {"accountNumber": "A-DEMO-3821"}
      {"amountMinor": 9250, "frequency": "monthly"}
      {"nextDueDate": "2026-10-28"}
    """
    slot = db.session.get(ServiceSlot, service_id)
    if slot is None:
        return error("Service not found.", 404)

    body = request.get_json(silent=True) or {}

    if "provider" in body:
        provider_payload = body["provider"]
        current = Field.from_dict(slot.provider)
        if isinstance(provider_payload, dict) and provider_payload.get("action"):
            action = provider_payload["action"]
            if action == "confirm":
                if current.value is None:
                    return error("There is no suggested provider to confirm.", 409)
                slot.provider = current.confirm().to_dict()
            elif action == "reject":
                slot.provider = missing(
                    note=f'Resident said "{current.value}" is not correct.'
                ).to_dict()
            else:
                return error("provider.action must be confirm or reject.")
        else:
            name = _as_str(
                provider_payload.get("value")
                if isinstance(provider_payload, dict)
                else provider_payload
            )
            if not name:
                return error("provider value cannot be empty.")
            slot.provider = confirmed(name, "userEntered").to_dict()

    if "accountNumber" in body:
        account = _as_str(body["accountNumber"])
        slot.account_number = (
            confirmed(account, "userEntered").to_dict() if account else missing().to_dict()
        )

    if "amountMinor" in body:
        amount = _as_int(body["amountMinor"])
        if amount is None or amount <= 0:
            return error("amountMinor must be a positive integer (pence).")
        slot.amount_minor = confirmed(amount, "userEntered").to_dict()

    if "frequency" in body:
        slot.frequency = str(body["frequency"])

    if "nextDueDate" in body:
        due = _as_date(body["nextDueDate"])
        slot.next_due_date = (
            confirmed(due, "userEntered").to_dict() if due else missing().to_dict()
        )

    db.session.commit()
    return jsonify({"service": slot.to_dict()})


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------


@bp.post("/households/<household_id>/bills")
@require_key
def create_bill(household_id: str):
    household = _household(household_id)
    if household is None:
        return error("Household not found.", 404)

    body = request.get_json(silent=True) or {}
    kind = str(body.get("kind", ""))
    if kind not in VALID_SERVICE_KINDS:
        return error("kind is required and must be a known service.")

    amount = _field_from(body.get("amountMinor"), default_source="userEntered", coerce=_as_int)
    if amount.value is None:
        return error("An amount is required. HomeLedger will not estimate one for you.")
    if amount.value <= 0:
        return error("Amount must be greater than zero.")

    due = _field_from(body.get("dueDate"), default_source="userEntered", coerce=_as_date)
    provider = _field_from(body.get("provider"), default_source="userEntered", coerce=_as_str)

    bill = Bill(
        id=new_id("bill"),
        household_id=household.id,
        kind=kind,
        provider=provider.to_dict(),
        amount_minor=amount.to_dict(),
        due_date=due.to_dict(),
        period_start=parse_date(body.get("periodStart")),
        period_end=parse_date(body.get("periodEnd")),
        frequency=str(body.get("frequency", "monthly")),
        notes=_as_str(body.get("notes")),
        document_id=_as_str(body.get("documentId")),
    )
    db.session.add(bill)
    db.session.commit()
    return jsonify({"bill": bill.to_dict()}), 201


@bp.patch("/bills/<bill_id>")
@require_key
def update_bill(bill_id: str):
    bill = db.session.get(Bill, bill_id)
    if bill is None:
        return error("Bill not found.", 404)

    body = request.get_json(silent=True) or {}

    if "paymentStatus" in body:
        status = str(body["paymentStatus"])
        if status not in {"unknown", "scheduled", "paid"}:
            return error("paymentStatus must be unknown, scheduled or paid.")
        bill.payment_status = status

    if "amountMinor" in body:
        amount = _field_from(body["amountMinor"], default_source="userEntered", coerce=_as_int)
        if amount.value is None or amount.value <= 0:
            return error("Amount must be greater than zero.")
        bill.amount_minor = amount.to_dict()

    if "dueDate" in body:
        bill.due_date = _field_from(
            body["dueDate"], default_source="userEntered", coerce=_as_date
        ).to_dict()

    if "provider" in body:
        bill.provider = _field_from(
            body["provider"], default_source="userEntered", coerce=_as_str
        ).to_dict()

    if "notes" in body:
        bill.notes = _as_str(body["notes"])

    db.session.commit()
    return jsonify({"bill": bill.to_dict()})


@bp.delete("/bills/<bill_id>")
@require_key
def delete_bill(bill_id: str):
    bill = db.session.get(Bill, bill_id)
    if bill is None:
        return error("Bill not found.", 404)
    db.session.delete(bill)
    db.session.commit()
    return jsonify({"deleted": bill_id})


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------


@bp.post("/households/<household_id>/reminders")
@require_key
def create_reminder(household_id: str):
    household = _household(household_id)
    if household is None:
        return error("Household not found.", 404)

    body = request.get_json(silent=True) or {}
    title = _as_str(body.get("title"))
    due_at = parse_date(body.get("dueAt"))
    if not title:
        return error("title is required.")
    if due_at is None:
        return error("dueAt must be an ISO date. Reminders are never guessed.")

    reminder = Reminder(
        id=new_id("rem"),
        household_id=household.id,
        kind=str(body.get("kind", "custom")),
        title=title,
        due_at=due_at,
        note=_as_str(body.get("note")),
        bill_id=_as_str(body.get("billId")),
    )
    db.session.add(reminder)
    db.session.commit()
    return jsonify({"reminder": reminder.to_dict()}), 201


@bp.patch("/reminders/<reminder_id>")
@require_key
def update_reminder(reminder_id: str):
    reminder = db.session.get(Reminder, reminder_id)
    if reminder is None:
        return error("Reminder not found.", 404)

    body = request.get_json(silent=True) or {}
    if "isDone" in body:
        reminder.is_done = bool(body["isDone"])
    if "title" in body:
        title = _as_str(body["title"])
        if not title:
            return error("title cannot be empty.")
        reminder.title = title
    if "dueAt" in body:
        due = parse_date(body["dueAt"])
        if due is None:
            return error("dueAt must be an ISO date.")
        reminder.due_at = due

    db.session.commit()
    return jsonify({"reminder": reminder.to_dict()})


@bp.delete("/reminders/<reminder_id>")
@require_key
def delete_reminder(reminder_id: str):
    reminder = db.session.get(Reminder, reminder_id)
    if reminder is None:
        return error("Reminder not found.", 404)
    db.session.delete(reminder)
    db.session.commit()
    return jsonify({"deleted": reminder_id})


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@bp.post("/households/<household_id>/documents")
@require_key
def create_document(household_id: str):
    """Register document metadata.

    File bytes are NOT accepted here yet. When uploads land, stream to encrypted
    storage, set `storage_key`, and keep the transcript separate so it can be
    erased independently.
    """
    household = _household(household_id)
    if household is None:
        return error("Household not found.", 404)

    body = request.get_json(silent=True) or {}
    title = _as_str(body.get("title"))
    if not title:
        return error("title is required.")

    document = Document(
        id=new_id("doc"),
        household_id=household.id,
        kind=str(body.get("kind", "bill")),
        title=title,
        provider_name=_as_str(body.get("providerName")),
        file_name=_as_str(body.get("fileName")),
        content_type=_as_str(body.get("contentType")),
        byte_size=_as_int(body.get("byteSize")),
        extracted_text=_as_str(body.get("extractedText")),
        notes=_as_str(body.get("notes")),
        bill_id=_as_str(body.get("billId")),
    )
    db.session.add(document)
    db.session.commit()
    return jsonify({"document": document.to_dict(include_text=True)}), 201


@bp.get("/households/<household_id>/documents")
@require_key
def list_documents(household_id: str):
    household = _household(household_id)
    if household is None:
        return error("Household not found.", 404)
    include_text = request.args.get("include") == "text"
    return jsonify(
        {
            "documents": [
                document.to_dict(include_text=include_text)
                for document in sorted(
                    household.documents, key=lambda doc: doc.created_at, reverse=True
                )
            ]
        }
    )


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _household_payload(household: Household) -> dict[str, Any]:
    return {
        "id": household.id,
        "name": household.name,
        "property": household.property.to_dict() if household.property else None,
        "members": [member.to_dict() for member in household.members],
        "services": [slot.to_dict() for slot in household.services],
        "bills": [bill.to_dict() for bill in household.bills],
        "documents": [document.to_dict() for document in household.documents],
        "reminders": [reminder.to_dict() for reminder in household.reminders],
    }
