# HomeLedger — Flutter App

> Part of [MoveIn](../README.md) · UK-first household bill tracker

Local-first Flutter app. No backend required to run the whole journey — all data lives on-device in `SharedPreferences` as a single JSON document (`AppData`).

## Quick start

```bash
flutter pub get
flutter test
flutter run
```

Requirements: Flutter ≥ 3.22.0 / Dart ≥ 3.3.0. Dependencies: `shared_preferences`, `url_launcher` only.

## Flow

Postcode → pick address → tenure + services → **confirmation screen** (provider discovery with provenance badges) → dashboard (Home / Bills / Calendar / Reminders / More).

Try **"Explore the example household instead"** on the address screen for a complete demo household (confirmed provider, pending suggestion, bill with no date, estimate, 3 roles — all marked `(demo)`).

## Key files

| File | Purpose |
|------|---------|
| `lib/domain/field.dart` | `Field<T>` provenance primitive — the core idea |
| `lib/domain/household_summary.dart` | Dashboard totals from recorded data only |
| `lib/data/store.dart` | `AppStore` — single source of truth + persistence |
| `lib/data/extraction/bill_text_parser.dart` | Rule-based bill parser (OCR seam) |
| `lib/ui/screens/confirm/` | Confirmation screen — heart of the product |

## Tests

```bash
flutter test
flutter test test/summary_test.dart test/extraction_test.dart  # start here
```

See the [root README](../README.md) for the full project description, architecture, and roadmap.
