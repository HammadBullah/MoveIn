import 'package:flutter_test/flutter_test.dart';
import 'package:home_ledger/core/json.dart';
import 'package:home_ledger/domain/app_data.dart';
import 'package:home_ledger/domain/bill.dart';
import 'package:home_ledger/domain/enums.dart';
import 'package:home_ledger/domain/field.dart';
import 'package:home_ledger/domain/household_service.dart';
import 'package:home_ledger/domain/property.dart';

void main() {
  group('Field', () {
    test('a postcode suggestion is not confirmed', () {
      final Field<String> provider = Field<String>.suggested(
        'Wessex Water',
        source: FieldSource.postcodeLookup,
      );

      expect(provider.hasValue, isTrue);
      expect(provider.isConfirmed, isFalse);
      expect(provider.needsConfirmation, isTrue);
      expect(provider.source.isAutomatic, isTrue);
      expect(provider.source.isHumanConfirmed, isFalse);
    });

    test('confirming promotes a suggestion without losing the value', () {
      final Field<String> provider = Field<String>.suggested(
        'Wessex Water',
        source: FieldSource.postcodeLookup,
      );
      final Field<String> confirmed = provider.confirm();

      expect(confirmed.value, 'Wessex Water');
      expect(confirmed.isConfirmed, isTrue);
      expect(confirmed.needsConfirmation, isFalse);
      expect(confirmed.source, FieldSource.userConfirmed);
    });

    test('rejecting clears the value but keeps a note', () {
      final Field<String> provider = Field<String>.suggested(
        'Wessex Water',
        source: FieldSource.postcodeLookup,
      );
      final Field<String> rejected = provider.reject();

      expect(rejected.hasValue, isFalse);
      expect(rejected.status, FieldStatus.missing);
      expect(rejected.note, isNotNull);
    });

    test('an estimate is never confirmed', () {
      final Field<int> estimate = Field<int>.suggested(
        5400,
        source: FieldSource.estimate,
      );
      expect(estimate.isConfirmed, isFalse);
      expect(estimate.source.isHumanConfirmed, isFalse);
    });

    test('round-trips through JSON', () {
      final Field<DateTime> due = Field<DateTime>.confirmed(
        DateTime(2026, 10, 28),
      );
      final Field<DateTime> restored = Field<DateTime>.fromJson(
        due.toJson((DateTime value) => value.toIso8601String()),
        (Object? raw) => asDateTime(raw) ?? DateTime(1970),
      );

      expect(restored.value, DateTime(2026, 10, 28));
      expect(restored.source, FieldSource.userConfirmed);
      expect(restored.status, FieldStatus.confirmed);
    });
  });

  group('Bill', () {
    Bill bill({
      Field<int>? amount,
      Field<DateTime>? due,
      PaymentStatus status = PaymentStatus.unknown,
    }) {
      return Bill(
        id: 'b1',
        propertyId: 'p1',
        kind: ServiceKind.electricity,
        amountMinor: amount ?? Field<int>.confirmed(9250),
        dueDate: due ?? Field<DateTime>.confirmed(DateTime(2030, 1, 1)),
        paymentStatus: status,
      );
    }

    test('needs details when there is no due date', () {
      final Bill water = bill(due: const Field<DateTime>.missing());
      expect(water.isActionable, isFalse);
      expect(water.stateFor(DateTime(2026, 10, 27)), BillState.needsDetails);
    });

    test('overdue, due soon and upcoming are distinct', () {
      final DateTime now = DateTime(2026, 10, 27);
      expect(
        bill(due: Field<DateTime>.confirmed(DateTime(2026, 10, 20)))
            .stateFor(now),
        BillState.overdue,
      );
      expect(
        bill(due: Field<DateTime>.confirmed(DateTime(2026, 10, 30)))
            .stateFor(now),
        BillState.dueSoon,
      );
      expect(
        bill(due: Field<DateTime>.confirmed(DateTime(2026, 12, 1)))
            .stateFor(now),
        BillState.upcoming,
      );
      expect(
        bill(
          due: Field<DateTime>.confirmed(DateTime(2026, 10, 20)),
          status: PaymentStatus.paid,
        ).stateFor(now),
        BillState.paid,
      );
    });
  });

  group('AppData', () {
    test('survives a JSON round trip', () {
      final AppData original = AppData(
        property: const Property(
          id: 'p1',
          line1: '1 Test Street',
          town: 'Bristol',
          postcode: 'BS1 4DJ',
          uprn: '123',
          tenure: Tenure.renting,
        ),
        services: <HouseholdService>[
          HouseholdService(
            id: 's1',
            propertyId: 'p1',
            kind: ServiceKind.water,
            provider: Field<String>.suggested(
              'Wessex Water',
              source: FieldSource.postcodeLookup,
            ),
            amountMinor: Field<int>.confirmed(9000),
          ),
        ],
        onboardingComplete: true,
      );

      final AppData restored = AppData.fromJson(original.toJson());

      expect(restored.property?.postcode, 'BS1 4DJ');
      expect(restored.property?.tenure, Tenure.renting);
      expect(restored.services.single.provider.value, 'Wessex Water');
      expect(restored.services.single.provider.needsConfirmation, isTrue);
      expect(restored.services.single.amountMinor.value, 9000);
      expect(restored.onboardingComplete, isTrue);
    });

    test('decoding tolerates missing and malformed fields', () {
      final AppData restored = AppData.fromJson(<String, dynamic>{
        'property': <String, dynamic>{'id': 'p1'},
        'services': <Object?>[
          <String, dynamic>{'id': 's1', 'kind': 'not_a_real_kind'},
          'nonsense',
        ],
        'bills': 'not a list',
      });

      expect(restored.property?.line1, '');
      expect(restored.services.single.kind, ServiceKind.other);
      expect(restored.bills, isEmpty);
    });
  });
}
