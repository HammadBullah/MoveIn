import 'package:flutter_test/flutter_test.dart';
import 'package:home_ledger/domain/app_data.dart';
import 'package:home_ledger/domain/bill.dart';
import 'package:home_ledger/domain/enums.dart';
import 'package:home_ledger/domain/field.dart';
import 'package:home_ledger/domain/household_service.dart';
import 'package:home_ledger/domain/household_summary.dart';

void main() {
  final DateTime now = DateTime(2026, 10, 27);

  Bill makeBill({
    required String id,
    required int amountMinor,
    DateTime? due,
    bool estimate = false,
    bool amountConfirmed = true,
    PaymentStatus status = PaymentStatus.unknown,
  }) {
    return Bill(
      id: id,
      propertyId: 'p1',
      kind: ServiceKind.electricity,
      amountMinor: estimate
          ? Field<int>.suggested(amountMinor, source: FieldSource.estimate)
          : amountConfirmed
              ? Field<int>.confirmed(amountMinor)
              : Field<int>.suggested(amountMinor, source: FieldSource.billExtraction),
      dueDate: due == null
          ? const Field<DateTime>.missing()
          : Field<DateTime>.confirmed(due),
      paymentStatus: status,
    );
  }

  group('HouseholdSummary', () {
    test('counts confirmed bills due soon and nothing else', () {
      final AppData data = AppData(
        bills: <Bill>[
          makeBill(id: 'due-soon', amountMinor: 9250, due: DateTime(2026, 10, 28)),
          makeBill(id: 'later', amountMinor: 14500, due: DateTime(2027, 1, 1)),
          makeBill(
            id: 'paid',
            amountMinor: 3200,
            due: DateTime(2026, 10, 29),
            status: PaymentStatus.paid,
          ),
        ],
      );

      final HouseholdSummary summary =
          HouseholdSummary.compute(data, now: now);

      expect(summary.stillToPayMinor, 9250);
      expect(summary.stillToPayCount, 1);
      expect(summary.excludedFromTotals, 0);
      expect(
        summary.upcoming.map((Bill b) => b.id),
        isNot(contains('paid')),
        reason: 'paid bills belong to the bills list, not the upcoming payments',
      );
    });

    test('an estimate is shown but never counted as money owed', () {
      final AppData data = AppData(
        bills: <Bill>[
          makeBill(
            id: 'estimate',
            amountMinor: 5400,
            due: DateTime(2026, 10, 30),
            estimate: true,
          ),
        ],
      );

      final HouseholdSummary summary =
          HouseholdSummary.compute(data, now: now);

      expect(summary.stillToPayMinor, 0);
      expect(summary.stillToPayCount, 0);
      expect(summary.excludedFromTotals, 0);
      expect(summary.needsDetails, isEmpty);
      // Still visible to the resident, just never in a total.
      expect(summary.estimates.single.id, 'estimate');
    });

    test('a bill without a payment date is excluded and reported', () {
      final AppData data = AppData(
        bills: <Bill>[
          makeBill(id: 'water', amountMinor: 9000),
        ],
      );

      final HouseholdSummary summary =
          HouseholdSummary.compute(data, now: now);

      expect(summary.stillToPayMinor, 0);
      expect(summary.excludedFromTotals, 1);
      expect(summary.missingDateCount, 1);
    });

    test('overdue bills are counted and flagged', () {
      final AppData data = AppData(
        bills: <Bill>[
          makeBill(id: 'late', amountMinor: 5000, due: DateTime(2026, 10, 20)),
        ],
      );

      final HouseholdSummary summary =
          HouseholdSummary.compute(data, now: now);

      expect(summary.overdueCount, 1);
      expect(summary.stillToPayMinor, 5000);
      expect(summary.upcoming.single.stateFor(now), BillState.overdue);
    });

    test('monthly recurring uses confirmed service amounts only', () {
      final List<HouseholdService> services = <HouseholdService>[
        HouseholdService(
          id: 's1',
          propertyId: 'p1',
          kind: ServiceKind.electricity,
          provider: Field<String>.confirmed('Octopus Energy'),
          amountMinor: Field<int>.confirmed(9250),
          frequency: PaymentFrequency.monthly,
          nextDueDate: Field<DateTime>.confirmed(DateTime(2026, 10, 28)),
        ),
        // Suggested amount: not counted.
        HouseholdService(
          id: 's2',
          propertyId: 'p1',
          kind: ServiceKind.water,
          provider: Field<String>.suggested(
            'Wessex Water',
            source: FieldSource.postcodeLookup,
          ),
          amountMinor: Field<int>.suggested(
            9000,
            source: FieldSource.billExtraction,
          ),
          frequency: PaymentFrequency.monthly,
        ),
        // Confirmed quarterly amount: counted as a third per month.
        HouseholdService(
          id: 's3',
          propertyId: 'p1',
          kind: ServiceKind.councilTax,
          provider: Field<String>.confirmed('Bristol City Council'),
          amountMinor: Field<int>.confirmed(36000),
          frequency: PaymentFrequency.quarterly,
          nextDueDate: Field<DateTime>.confirmed(DateTime(2026, 11, 1)),
        ),
        // No provider at all.
        HouseholdService(
          id: 's4',
          propertyId: 'p1',
          kind: ServiceKind.gas,
        ),
      ];

      final HouseholdSummary summary = HouseholdSummary.compute(
        AppData(services: services),
        now: now,
      );

      expect(summary.monthlyRecurringMinor, 9250 + 12000);
      expect(summary.monthlyRecurringCount, 2);
      expect(summary.unresolvedProviderCount, 2);
    });

    test('nothing recorded means no misleading zero totals', () {
      final HouseholdSummary summary =
          HouseholdSummary.compute(AppData.empty, now: now);

      expect(summary.hasReliableTotals, isFalse);
      expect(summary.attentionCount, 0);
      expect(summary.upcoming, isEmpty);
    });
  });

  group('monthlySpend', () {
    test('groups by due month and ignores estimates', () {
      final List<Bill> bills = <Bill>[
        makeBill(id: 'a', amountMinor: 1000, due: DateTime(2026, 10, 5)),
        makeBill(id: 'b', amountMinor: 2000, due: DateTime(2026, 10, 25)),
        makeBill(id: 'c', amountMinor: 3000, due: DateTime(2026, 9, 25)),
        makeBill(
          id: 'd',
          amountMinor: 4000,
          due: DateTime(2026, 10, 26),
          estimate: true,
        ),
      ];

      final List<MonthlySpend> spend = monthlySpend(bills);

      expect(spend.length, 2);
      expect(spend.first.month, DateTime(2026, 10));
      expect(spend.first.totalMinor, 3000);
      expect(spend.first.billCount, 2);
      expect(spend.last.month, DateTime(2026, 9));
      expect(spend.last.totalMinor, 3000);
    });
  });
}
