# HomeLedger

A UK-first household bill tracker, built around one rule:

> **An address tells you which services a home has. It cannot tell you who bills
> you, how much you pay, or when it is due.**

HomeLedger enters an address once, works out which household services apply,
suggests the providers it can honestly suggest, and then asks the resident to
confirm. Money only appears in the dashboard when it comes from a bill, a
statement or the resident's own words.

This repository contains:

```
app/      Flutter app (local-first; no backend required to run the whole journey)
server/   Flask API scaffold: address lookup proxy, provider discovery, records
```

---

## The design decision that shapes everything

Every value in the app is stored as a `Field<T>` (see
`app/lib/domain/field.dart`) which is nothing more than:

| Part | Meaning |
|---|---|
| `value` | the value itself |
| `source` | `userEntered`, `userConfirmed`, `postcodeLookup`, `officialLookup`, `billExtraction`, `estimate` |
| `status` | `missing`, `suggested`, `confirmed` |
| `note` / `recordedAt` | why it exists, and when |

Consequences you can see throughout the code:

* A **postcode-derived water company** is `suggested` + `postcodeLookup`. It
  renders with a "Suggested · postcode lookup" badge and a Yes / No / Not sure
  prompt. It is never displayed as fact.
* **Electricity and gas suppliers are never inferred from an address.** The
  discovery service returns "not found" and offers the official lookup, a bill,
  or manual entry.
* **Confirming a provider does not confirm an account, an amount or a date.**
  They are separate fields with separate sources. Confirming the water company
  leaves "Amount" and "Next payment" empty.
* **Missing dates stay missing.** A bill with an amount but no date is listed
  under "Needs details", excluded from totals, and generates no reminder.
* **Estimates are quarantined.** `FieldSource.estimate` amounts are shown in an
  "Estimates (not counted)" section and never touch "Monthly bills" or "Still to
  pay".
* **The dashboard totals are computed from recorded data only**
  (`app/lib/domain/household_summary.dart`), so the headline figure always
  reconciles with the list underneath it.

The confirmation screen (`app/lib/ui/screens/confirm/`) is the heart of the
product, not the dashboard.

---

## Running the Flutter app

```bash
cd app
flutter pub get
flutter test          # unit + widget tests
flutter run
```

Requirements: Flutter 3.22+ / Dart 3.3+. Two dependencies only:
`shared_preferences` (local storage) and `url_launcher` (open official lookup
pages).

First launch → enter a postcode (any valid UK format works, e.g. `BS1 4DJ`) →
pick an address → choose services → the confirmation screen runs discovery.

There is also **"Explore the example household instead"** on the address screen
(and in *More → Load the example household*), which loads a complete worked
example: one confirmed provider, one suggestion awaiting an answer, one bill
with no payment date, one estimate, three household roles. All of it is marked
`(demo)` and "Illustrative example, not a live address lookup".

### Where the data lives

The whole app state is one JSON document in `SharedPreferences`
(`AppData` in `app/lib/domain/app_data.dart`). The same shape is what the API
returns, so moving to a server-backed repository is a contained change.

---

## Running the API

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python run.py                 # http://0.0.0.0:5000
pytest                        # 14 tests, all passing
```

Environment variables (see `server/home_ledger/config.py`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLite locally, PostgreSQL in deployment |
| `ADDRESS_PROVIDER` | `demo` (default) or `os_places` |
| `OS_PLACES_API_KEY` | Ordnance Survey Places key — **server-side only** |
| `API_KEY` | placeholder shared key; replace with real auth before deploying |
| `CORS_ORIGINS` | allowed origins for the web build |
| `DOCUMENT_BUCKET` | encrypted document storage target |

Endpoints and their contracts are documented at the top of
`server/home_ledger/api.py`. The important behaviours:

* `POST /api/v1/households` creates every service slot with an **empty**
  provider, amount and date. Nothing is pre-filled.
* `POST /api/v1/households/<id>/discover` returns water/council suggestions at
  `status: "suggested"`, and explicit `confidence: "unknown"` entries for
  electricity and gas. It never overwrites a value the resident entered.
* `PATCH /api/v1/services/<id>` with `{"provider": {"action": "confirm"}}`
  confirms only the provider. Amount and date remain `missing`.
* Bills require an amount (`400` otherwise). A bill may be stored **without** a
  payment date — that is a valid, honest state.

The API is a scaffold, not a production service. It has no real
authentication, no per-household ownership checks and no encrypted file upload
yet. Those are listed below as work that must land before real households.

---

## Project layout

```
app/lib/
  main.dart, app.dart          bootstrap, root gate (setup → confirm → dashboard)
  theme.dart                   M3 theme (deliberately avoids volatile sub-themes)
  core/                        money/date formatting, forgiving JSON helpers
  domain/                      Field, Property, HouseholdService, Bill, Document,
                               Reminder, Member, AppData, HouseholdSummary
  data/
    store.dart                 single ChangeNotifier source of truth + persistence
    demo_data.dart             the worked example household
    lookup/                    address service interface + demo catalogue,
                               provider discovery + official lookup links
    extraction/                rule-based bill text parser (the OCR seam)
  ui/
    scope.dart                 InheritedNotifier for the store
    widgets/                   AppCard, provenance badges, field rows, bill tile
    screens/
      onboarding/              address → tenure → services
      confirm/                 the confirmation screen and detail sheets
      dashboard/               totals, upcoming, attention, estimates
      bills/                   list, detail, manual entry, read-a-bill
      calendar/ reminders/ more/ (documents, members, spending, privacy)
server/home_ledger/
  config.py extensions.py models.py api.py provenance.py
  lookups/os_places.py lookups/providers.py
  tests/test_api.py
```

---

## Data sources, honestly stated

| Information | Where it comes from | Automatic? |
|---|---|---|
| Exact address + UPRN | Licensed address provider (OS Places) **via the API** | Yes |
| Water / sewerage company | Postcode lookup (regional) | Often (still needs confirming) |
| Local council / band | Postcode lookup, GOV.UK | Usually (band only) |
| Electricity / gas supplier | Official supplier lookup, network operator, or a bill | **No** — not from the address |
| Council tax account, balance, instalments | Council, bill upload, manual entry | No |
| Bill amounts and dates | Bill upload, provider integration, manual entry | Only with evidence |
| Payment status | Bill evidence or authorised financial data | Partly |
| Bank payment dates | Open Banking, with explicit consent | Later version, with an FCA-authorised provider |

Sample tables live in `server/home_ledger/lookups/providers.py` and
`app/lib/data/lookup/provider_lookup_service.dart`. They exist to demo the flow
and are labelled sample/demo. Do not ship them as a real mapping.

The Open Banking path is deliberately not implemented: a bank transaction is not
proof a bill was paid, and matching it correctly is a product of its own.

---

## What is deliberately not implemented

* **File upload and OCR.** The "read a bill" screen takes pasted or typed text,
  parses it with `BillTextParser`, and asks the resident to confirm each field.
  Real uploads plug in at exactly that seam: OCR → text → the same review screen.
  `DocumentRecord.storageKey` is the hook for encrypted server storage.
* **Push/local notifications.** Reminders are in-app and the UI says so.
  Delivery needs a platform plugin, plus a server-side scheduler for a shared
  household.
* **Authentication and access control.** Roles are enforced in the UI
  (`MemberRole`) and must be re-enforced server-side. The API's shared key is a
  development placeholder.
* **Open Banking.** Phase 4, with consent, an authorised provider, and careful
  transaction matching.

---

## Roadmap

1. **Phase 1 (done here):** address selection, manual bills, confirmation
   states, dashboard, calendar, reminders, roles, documents.
2. **Phase 2:** wire the API, live address lookup (server-side key), provider
   discovery with a licensed reference dataset, magic-link auth + per-household
   authorisation.
3. **Phase 3:** bill upload, OCR, field-by-field confirmation, document history.
4. **Phase 4:** shared households across devices, recurring-payment matching,
   authorised Open Banking with consent.
5. **Phase 5:** broader regional support, provider partnerships, carefully
   validated automation.

---

## Verification status

* `server/`: `pytest` — 14 tests, passing in this repository (provenance rules,
  discovery honesty, confirmation semantics, API guards).
* `app/`: unit and widget tests are included (`app/test/`): field provenance,
  bill states, summary arithmetic, bill-text parsing, JSON round-trips and three
  widget flows. **They have not been executed in this workspace** — no Flutter
  SDK was available. Run `flutter test` before relying on them.

Tests to read first, because they encode the product rules:

```bash
cd app && flutter test test/summary_test.dart test/extraction_test.dart
```

---

## Notes on naming and compliance

* "HomeLedger" is a working name: check domain, app-store and trademark
  availability before launch.
* Ordnance Survey Places terms and pricing must be checked before commercial use.
* UK GDPR duties apply as soon as real households use this: lawful basis,
  minimal collection, retention/erasure, and an audit log of who changed what.
* HomeLedger is not affiliated with any energy, water or council provider, and it
  does not pay bills.
