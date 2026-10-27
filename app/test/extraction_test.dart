import 'package:flutter_test/flutter_test.dart';
import 'package:home_ledger/data/extraction/bill_text_parser.dart';
import 'package:home_ledger/domain/enums.dart';
import 'package:home_ledger/domain/field.dart';

void main() {
  group('parseFlexibleDate', () {
    test('reads day-first UK dates', () {
      expect(
        BillTextParser.parseFlexibleDate('28/10/2026'),
        DateTime(2026, 10, 28),
      );
      expect(
        BillTextParser.parseFlexibleDate('01/02/2026'),
        DateTime(2026, 2, 1),
        reason: 'UK bills are day-first',
      );
    });

    test('reads written dates and ISO dates', () {
      expect(
        BillTextParser.parseFlexibleDate('28 October 2026'),
        DateTime(2026, 10, 28),
      );
      expect(
        BillTextParser.parseFlexibleDate('28th of Oct 2026'),
        DateTime(2026, 10, 28),
      );
      expect(
        BillTextParser.parseFlexibleDate('October 28, 2026'),
        DateTime(2026, 10, 28),
      );
      expect(
        BillTextParser.parseFlexibleDate('2026-10-28'),
        DateTime(2026, 10, 28),
      );
    });

    test('rejects impossible dates', () {
      expect(BillTextParser.parseFlexibleDate('31/02/2026'), isNull);
      expect(BillTextParser.parseFlexibleDate('not a date'), isNull);
    });

    test('expands two-digit years', () {
      expect(
        BillTextParser.parseFlexibleDate(
          '28/10/26',
          reference: DateTime(2026, 1, 1),
        ),
        DateTime(2026, 10, 28),
      );
    });
  });

  group('BillTextParser.parse', () {
    test('finds provider, amount, date and frequency', () {
      const String text = '''
Octopus Energy Ltd
Your electricity bill
Amount due: £92.50
Payment due date: 28/10/2026
Monthly direct debit
''';

      final ExtractedBill bill = BillTextParser.parse(text);

      expect(bill.provider.value, 'Octopus Energy');
      expect(bill.amountMinor.value, 9250);
      expect(bill.dueDate.value, DateTime(2026, 10, 28));
      expect(bill.frequency, PaymentFrequency.monthly);
      expect(bill.kind, ServiceKind.electricity);
    });

    test('every extracted value is only a suggestion', () {
      final ExtractedBill bill = BillTextParser.parse(
        'Thames Water\nTotal amount due: £180.00\nDue 12 November 2026',
      );

      expect(bill.amountMinor.status, FieldStatus.suggested);
      expect(bill.amountMinor.source, FieldSource.billExtraction);
      expect(bill.dueDate.needsConfirmation, isTrue);
      expect(bill.provider.needsConfirmation, isTrue);
    });

    test('prefers a labelled total over a larger unrelated amount', () {
      const String text = '''
British Gas
Balance brought forward: £400.00
Total amount due: £92.50
Payment due date: 28/10/2026
''';

      final ExtractedBill bill = BillTextParser.parse(text);
      expect(bill.amountMinor.value, 9250);
    });

    test('warns instead of guessing when several amounts are unlabelled', () {
      const String text = '''
Scottish Power
Usage charge £40.00
Standing charge £5.00
VAT £2.25
''';

      final ExtractedBill bill = BillTextParser.parse(text);
      expect(bill.amountMinor.value, isNotNull);
      expect(
        bill.warnings.any((String w) => w.contains('Several amounts')),
        isTrue,
      );
    });

    test('does not invent a due date when none is printed', () {
      final ExtractedBill bill = BillTextParser.parse(
        'Thames Water\nTotal amount due: £180.00\nAccount 12345',
      );

      expect(bill.amountMinor.value, 18000);
      expect(bill.dueDate.hasValue, isFalse);
      expect(bill.warnings.any((String w) => w.contains('due date')), isTrue);
    });

    test('detects council tax and quarterly frequency', () {
      final ExtractedBill bill = BillTextParser.parse(
        'Bristol City Council\nCouncil tax instalment\n'
        'Amount due: £145.00\nPayment due: 01/11/2026\nQuarterly',
      );

      expect(bill.kind, ServiceKind.councilTax);
      expect(bill.frequency, PaymentFrequency.quarterly);
    });

    test('keeps a hinted kind when the text is ambiguous', () {
      final ExtractedBill bill = BillTextParser.parse(
        'Demo Fibre Ltd\nAmount due: £32.00\nDue date: 30/10/2026',
        hintedKind: ServiceKind.broadband,
      );
      expect(bill.kind, ServiceKind.broadband);
    });
  });
}
