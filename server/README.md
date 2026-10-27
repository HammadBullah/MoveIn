# HomeLedger API

Flask scaffold for the HomeLedger app. Its job is narrow and deliberate:

1. keep the licensed address-provider key **off the device**;
2. turn a postcode into the providers that can honestly be inferred from it;
3. store households, services, bills, documents and reminders **with
   provenance attached to every value**.

It does not scrape utility websites, does not log in to provider accounts, and
does not invent amounts or payment dates.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python run.py            # http://0.0.0.0:5000
pytest -q                # 14 passed
```

Every request except `/api/health` needs the header:

```
X-API-Key: dev-local-key
```

Set `API_KEY` in the environment to change it. This is a placeholder: real
authentication (sessions, per-household authorisation, audit log) is Phase 2.

## Live address lookup

```bash
export ADDRESS_PROVIDER=os_places
export OS_PLACES_API_KEY=...
python run.py
```

`POST /api/v1/addresses/search {"postcode": "BS1 4DJ"}` will then call Ordnance
Survey Places from the server. Without a key, or with `ADDRESS_PROVIDER=demo`,
it returns the built-in sample catalogue and reports `"isLive": false` so the
client can label it.

Before commercial use, check the OS Places licence terms, price, caching rules
and whether storing a UPRN + formatted address is permitted.

## Example session

```bash
KEY='X-API-Key: dev-local-key'

curl -s -X POST localhost:5000/api/v1/households -H "$KEY" -H 'Content-Type: application/json' -d '{
  "address": {"line1": "12 Example Street", "town": "Bristol", "postcode": "BS1 4DJ", "uprn": "DEMO-0000000012"},
  "tenure": "renting",
  "services": ["electricity", "gas", "water", "wastewater", "councilTax"],
  "residentName": "Sam"
}'

# every provider is empty at this point, on purpose
curl -s -X POST localhost:5000/api/v1/households/<id>/discover -H "$KEY"

# water/council come back as "suggested"; electricity/gas as unknown
# confirm exactly one provider and watch the amount/date stay missing
curl -s -X PATCH localhost:5000/api/v1/services/<service-id> -H "$KEY" \
  -H 'Content-Type: application/json' -d '{"provider": {"action": "confirm"}}'

# a bill needs an amount; a payment date is optional
curl -s -X POST localhost:5000/api/v1/households/<id>/bills -H "$KEY" \
  -H 'Content-Type: application/json' -d '{"kind": "water", "amountMinor": 9000, "provider": "Wessex Water"}'
```

## Layout

```
home_ledger/
  __init__.py     app factory, health, DB bootstrap
  config.py       environment configuration
  extensions.py   SQLAlchemy instance
  models.py       Household, Property, Member, ServiceSlot, Bill, Document, Reminder
  provenance.py   server mirror of the Flutter Field type
  api.py          HTTP routes and serialisation
  lookups/
    os_places.py  licensed address lookup (server-side key)
    providers.py  honest provider discovery + official lookup links
  tests/test_api.py
```

`ServiceSlot` and `Bill` store `provider`, `account_number`, `amount_minor` and
`next_due_date` as JSON `Field` documents (`{value, source, status, recordedAt,
note}`). That keeps the API and the app in lockstep and makes "how do you know
this?" answerable for every number on screen.

## Must land before real households use this

- Real authentication and per-household authorisation on every route.
- Encrypted document upload (streaming, size limits, virus scanning) and a
  retention/erasure policy for documents and transcripts.
- Alembic migrations instead of `db.create_all()`.
- Rate limiting on address lookups (they cost money).
- Audit log of who changed which value, and when.
- A licence-reviewed provider reference dataset to replace the sample tables.
- A reminder scheduler (Celery/RQ or a cron worker) with idempotent delivery.

## Tests

```bash
pytest -q
```

They assert the product rules, not just the plumbing: suggestions are never
confirmed implicitly, discovery never overwrites a resident's answer, confirming
a provider leaves amounts missing, and a bill cannot be created without an
amount.
