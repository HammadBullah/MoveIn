"""Database models.

Provenance is stored as JSON columns shaped exactly like the Flutter ``Field``
type, so a record can move between client and server without translation.

Not production ready on its own: see README.md for the access-control, audit and
retention work that must land before real households use it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from .extensions import db


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Household(db.Model, TimestampMixin):
    __tablename__ = "households"

    id = db.Column(db.String(40), primary_key=True, default=lambda: new_id("hh"))
    name = db.Column(db.String(120), nullable=False, default="My Home")

    # The property link lives on this side (households.property_id) so the two
    # tables never reference each other in a cycle.
    property_id = db.Column(db.String(40), db.ForeignKey("properties.id"))
    property = db.relationship("Property", uselist=False)

    members = db.relationship(
        "Member", back_populates="household", cascade="all, delete-orphan"
    )
    bills = db.relationship(
        "Bill", back_populates="household", cascade="all, delete-orphan"
    )
    services = db.relationship(
        "ServiceSlot", back_populates="household", cascade="all, delete-orphan"
    )
    documents = db.relationship(
        "Document", back_populates="household", cascade="all, delete-orphan"
    )
    reminders = db.relationship(
        "Reminder", back_populates="household", cascade="all, delete-orphan"
    )


class Property(db.Model, TimestampMixin):
    __tablename__ = "properties"

    id = db.Column(db.String(40), primary_key=True, default=lambda: new_id("prop"))

    line1 = db.Column(db.String(200), nullable=False)
    line2 = db.Column(db.String(200))
    town = db.Column(db.String(120), nullable=False)
    postcode = db.Column(db.String(12), nullable=False, index=True)

    # Unique Property Reference Number from the address provider. Stable, but it
    # says nothing about accounts or bills.
    uprn = db.Column(db.String(20), index=True)
    tenure = db.Column(db.String(20), nullable=False, default="other")

    # Where the address itself came from ("OS Places", "Entered manually", ...).
    address_source = db.Column(db.String(80), nullable=False, default="Manual entry")
    is_demo_data = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "line1": self.line1,
            "line2": self.line2,
            "town": self.town,
            "postcode": self.postcode,
            "uprn": self.uprn,
            "tenure": self.tenure,
            "addressSource": self.address_source,
            "isDemoData": self.is_demo_data,
        }


class Member(db.Model, TimestampMixin):
    __tablename__ = "members"

    id = db.Column(db.String(40), primary_key=True, default=lambda: new_id("member"))
    household_id = db.Column(
        db.String(40), db.ForeignKey("households.id"), nullable=False, index=True
    )
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(200))

    # owner | tenant | housemate | viewer  (see lib/domain/enums.dart)
    role = db.Column(db.String(20), nullable=False, default="owner")
    has_accepted_invite = db.Column(db.Boolean, nullable=False, default=True)

    household = db.relationship("Household", back_populates="members")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "hasAcceptedInvite": self.has_accepted_invite,
        }


class ServiceSlot(db.Model, TimestampMixin):
    """One household service at a property: electricity, water, council tax...

    Provider, account number, amount and next due date are separate provenance
    fields on purpose. Confirming one never confirms the others.
    """

    __tablename__ = "service_slots"
    __table_args__ = (db.UniqueConstraint("household_id", "kind"),)

    id = db.Column(db.String(40), primary_key=True, default=lambda: new_id("svc"))
    household_id = db.Column(
        db.String(40), db.ForeignKey("households.id"), nullable=False, index=True
    )
    kind = db.Column(db.String(30), nullable=False)

    provider = db.Column(db.JSON, nullable=False, default=dict)
    account_number = db.Column(db.JSON, nullable=False, default=dict)
    amount_minor = db.Column(db.JSON, nullable=False, default=dict)
    next_due_date = db.Column(db.JSON, nullable=False, default=dict)
    frequency = db.Column(db.String(20), nullable=False, default="monthly")

    # Keys into the client's official-lookup table.
    lookup_keys = db.Column(db.JSON, nullable=False, default=list)

    household = db.relationship("Household", back_populates="services")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "provider": self.provider,
            "accountNumber": self.account_number,
            "amountMinor": self.amount_minor,
            "nextDueDate": self.next_due_date,
            "frequency": self.frequency,
            "lookupKeys": self.lookup_keys or [],
        }


class Bill(db.Model, TimestampMixin):
    __tablename__ = "bills"

    id = db.Column(db.String(40), primary_key=True, default=lambda: new_id("bill"))
    household_id = db.Column(
        db.String(40), db.ForeignKey("households.id"), nullable=False, index=True
    )
    kind = db.Column(db.String(30), nullable=False)

    provider = db.Column(db.JSON, nullable=False, default=dict)
    amount_minor = db.Column(db.JSON, nullable=False, default=dict)
    due_date = db.Column(db.JSON, nullable=False, default=dict)

    period_start = db.Column(db.Date)
    period_end = db.Column(db.Date)
    frequency = db.Column(db.String(20), nullable=False, default="monthly")

    # unknown | scheduled | paid
    payment_status = db.Column(db.String(20), nullable=False, default="unknown")

    document_id = db.Column(db.String(40), db.ForeignKey("documents.id"))
    notes = db.Column(db.Text)

    household = db.relationship("Household", back_populates="bills")
    document = db.relationship("Document", foreign_keys=[document_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "provider": self.provider,
            "amountMinor": self.amount_minor,
            "dueDate": self.due_date,
            "periodStart": self.period_start.isoformat() if self.period_start else None,
            "periodEnd": self.period_end.isoformat() if self.period_end else None,
            "frequency": self.frequency,
            "paymentStatus": self.payment_status,
            "documentId": self.document_id,
            "notes": self.notes,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class Document(db.Model, TimestampMixin):
    __tablename__ = "documents"

    id = db.Column(db.String(40), primary_key=True, default=lambda: new_id("doc"))
    household_id = db.Column(
        db.String(40), db.ForeignKey("households.id"), nullable=False, index=True
    )
    kind = db.Column(db.String(30), nullable=False, default="bill")
    title = db.Column(db.String(200), nullable=False)
    provider_name = db.Column(db.String(200))

    file_name = db.Column(db.String(255))
    content_type = db.Column(db.String(100))
    byte_size = db.Column(db.Integer)

    # Object key in encrypted storage. Never a public URL.
    storage_key = db.Column(db.String(400))

    # Searchable transcript. Treat as personal data: it contains addresses,
    # account numbers and amounts.
    extracted_text = db.Column(db.Text)
    notes = db.Column(db.Text)
    bill_id = db.Column(db.String(40))

    household = db.relationship("Household", back_populates="documents")

    def to_dict(self, include_text: bool = False) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "providerName": self.provider_name,
            "fileName": self.file_name,
            "storageKey": self.storage_key,
            "notes": self.notes,
            "billId": self.bill_id,
            "addedAt": self.created_at.isoformat() if self.created_at else None,
        }
        if include_text:
            payload["extractedText"] = self.extracted_text
        return payload


class Reminder(db.Model, TimestampMixin):
    __tablename__ = "reminders"

    id = db.Column(db.String(40), primary_key=True, default=lambda: new_id("rem"))
    household_id = db.Column(
        db.String(40), db.ForeignKey("households.id"), nullable=False, index=True
    )
    kind = db.Column(db.String(30), nullable=False, default="custom")
    title = db.Column(db.String(200), nullable=False)
    due_at = db.Column(db.Date, nullable=False)
    note = db.Column(db.Text)
    bill_id = db.Column(db.String(40))
    is_done = db.Column(db.Boolean, nullable=False, default=False)

    household = db.relationship("Household", back_populates="reminders")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "dueAt": self.due_at.isoformat() if self.due_at else None,
            "note": self.note,
            "billId": self.bill_id,
            "isDone": self.is_done,
        }


def parse_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
