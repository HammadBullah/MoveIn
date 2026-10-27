import '../domain/app_data.dart';
import '../domain/bill.dart';
import '../domain/document.dart';
import '../domain/enums.dart';
import '../domain/field.dart';
import '../domain/household_service.dart';
import '../domain/member.dart';
import '../domain/property.dart';

/// Builds the worked example household.
///
/// Everything is marked as demo data, provider names end in "(demo)", and the
/// dates are relative to today so the dashboard always has something to show.
/// The point is to demonstrate the *rules*: suggestions that need confirming,
/// a bill with no payment date, and an estimate that is excluded from totals.
abstract final class DemoData {
  static AppData build({required DateTime now, required String idSeed}) {
    final String propertyId = '$idSeed-prop';
    final DateTime today = DateTime(now.year, now.month, now.day);

    final Property property = Property(
      id: propertyId,
      line1: '12 Example Street',
      town: 'Bristol',
      postcode: 'BS1 4DJ',
      uprn: 'DEMO-0000000012',
      tenure: Tenure.renting,
      addressSource: 'Demo address list (offline)',
      isDemoData: true,
    );

    final HouseholdService electricity = HouseholdService(
      id: '$idSeed-svc-elec',
      propertyId: propertyId,
      kind: ServiceKind.electricity,
      provider: Field<String>.confirmed(
        'Octopus Energy (demo)',
        source: FieldSource.userConfirmed,
      ),
      accountNumber: Field<String>.confirmed('A-DEMO-3821'),
      amountMinor: Field<int>.confirmed(9250, source: FieldSource.userEntered),
      frequency: PaymentFrequency.monthly,
      nextDueDate: Field<DateTime>.confirmed(today.add(const Duration(days: 1))),
      lookupKeys: const <String>['electricity_supplier', 'meter_points'],
    );

    final HouseholdService water = HouseholdService(
      id: '$idSeed-svc-water',
      propertyId: propertyId,
      kind: ServiceKind.water,
      // Suggested from the postcode, not yet accepted by the resident.
      provider: Field<String>.suggested(
        'Wessex Water (demo)',
        source: FieldSource.postcodeLookup,
        note: 'Postcode-based demo lookup. Nobody has confirmed this yet.',
      ),
      // An amount is on file, but there is no payment date: the dashboard must
      // show this as "needs details" rather than inventing a date.
      amountMinor: Field<int>.confirmed(9000, source: FieldSource.userEntered),
      frequency: PaymentFrequency.monthly,
      lookupKeys: const <String>['water_provider'],
    );

    final HouseholdService councilTax = HouseholdService(
      id: '$idSeed-svc-council',
      propertyId: propertyId,
      kind: ServiceKind.councilTax,
      provider: Field<String>.suggested(
        'Bristol City Council (demo)',
        source: FieldSource.postcodeLookup,
        note: 'Council follows from the property location; the account does not.',
      ),
      lookupKeys: const <String>['council_tax', 'find_council'],
    );

    final HouseholdService broadband = HouseholdService(
      id: '$idSeed-svc-broadband',
      propertyId: propertyId,
      kind: ServiceKind.broadband,
      provider: Field<String>.confirmed(
        'Demo Fibre Ltd',
        source: FieldSource.userEntered,
      ),
      amountMinor: Field<int>.confirmed(3200, source: FieldSource.userEntered),
      frequency: PaymentFrequency.monthly,
      nextDueDate: Field<DateTime>.confirmed(today.add(const Duration(days: 3))),
    );

    final HouseholdService gas = HouseholdService(
      id: '$idSeed-svc-gas',
      propertyId: propertyId,
      kind: ServiceKind.gas,
      // Deliberately empty: an address cannot tell us the gas supplier.
      lookupKeys: const <String>['gas_supplier'],
    );

    final List<Bill> bills = <Bill>[
      Bill(
        id: '$idSeed-bill-elec',
        propertyId: propertyId,
        kind: ServiceKind.electricity,
        provider: Field<String>.confirmed('Octopus Energy (demo)'),
        amountMinor: Field<int>.confirmed(9250),
        dueDate: Field<DateTime>.confirmed(today.add(const Duration(days: 1))),
        frequency: PaymentFrequency.monthly,
        documentId: '$idSeed-doc-elec',
        notes: 'Demo direct debit.',
      ),
      Bill(
        id: '$idSeed-bill-broadband',
        propertyId: propertyId,
        kind: ServiceKind.broadband,
        provider: Field<String>.confirmed('Demo Fibre Ltd'),
        amountMinor: Field<int>.confirmed(3200),
        dueDate: Field<DateTime>.confirmed(today.add(const Duration(days: 3))),
        frequency: PaymentFrequency.monthly,
      ),
      Bill(
        id: '$idSeed-bill-water',
        propertyId: propertyId,
        kind: ServiceKind.water,
        provider: Field<String>.suggested(
          'Wessex Water (demo)',
          source: FieldSource.postcodeLookup,
        ),
        amountMinor: Field<int>.confirmed(9000),
        // No due date: the bill exists, the payment date does not.
        dueDate: const Field<DateTime>.missing(),
        frequency: PaymentFrequency.monthly,
        notes: 'Add the date from your statement to get a reminder.',
      ),
      Bill(
        id: '$idSeed-bill-council',
        propertyId: propertyId,
        kind: ServiceKind.councilTax,
        provider: Field<String>.suggested(
          'Bristol City Council (demo)',
          source: FieldSource.postcodeLookup,
        ),
        amountMinor: Field<int>.confirmed(14500),
        dueDate: Field<DateTime>.confirmed(today.add(const Duration(days: 5))),
        frequency: PaymentFrequency.monthly,
        notes: 'Demo instalment. Check your own instalment plan.',
      ),
      Bill(
        id: '$idSeed-bill-gas-estimate',
        propertyId: propertyId,
        kind: ServiceKind.gas,
        provider: const Field<String>.missing(),
        // An estimate: shown, clearly labelled, and excluded from totals.
        amountMinor: Field<int>.suggested(
          5400,
          source: FieldSource.estimate,
          note: 'Typical usage forecast, not a bill.',
        ),
        dueDate: Field<DateTime>.suggested(
          today.add(const Duration(days: 12)),
          source: FieldSource.estimate,
          note: 'Forecast date, not a confirmed obligation.',
        ),
        frequency: PaymentFrequency.monthly,
        notes: 'Estimate only. Add your real bill to replace this.',
      ),
    ];

    final List<DocumentRecord> documents = <DocumentRecord>[
      DocumentRecord(
        id: '$idSeed-doc-elec',
        propertyId: propertyId,
        kind: DocumentKind.bill,
        title: 'Electricity bill (demo)',
        providerName: 'Octopus Energy (demo)',
        fileName: 'demo-electricity.pdf',
        extractedText:
            'Octopus Energy (demo)\nAmount due: £92.50\nPayment due date: '
                '${today.add(const Duration(days: 1)).toIso8601String().split('T').first}\nMonthly direct debit',
        billId: '$idSeed-bill-elec',
        addedAt: today.subtract(const Duration(days: 4)),
      ),
    ];

    final List<Reminder> reminders = <Reminder>[
      Reminder(
        id: '$idSeed-rem-meter',
        propertyId: propertyId,
        kind: ReminderKind.meterReading,
        title: 'Submit a gas meter reading',
        dueAt: today.add(const Duration(days: 6)),
        note: 'Keeps the next bill accurate. Demo reminder.',
      ),
      Reminder(
        id: '$idSeed-rem-broadband',
        propertyId: propertyId,
        kind: ReminderKind.contractRenewal,
        title: 'Demo Fibre contract ends',
        dueAt: today.add(const Duration(days: 45)),
        note: 'Check the renewal price before it rolls over.',
      ),
    ];

    final List<Member> members = <Member>[
      Member(
        id: '$idSeed-member-owner',
        name: 'You (demo)',
        role: MemberRole.owner,
        isCurrentUser: true,
      ),
      Member(
        id: '$idSeed-member-housemate',
        name: 'Sam (housemate, demo)',
        role: MemberRole.housemate,
        hasAcceptedInvite: true,
      ),
      Member(
        id: '$idSeed-member-viewer',
        name: 'Alex (viewer, demo)',
        role: MemberRole.viewer,
        hasAcceptedInvite: true,
      ),
    ];

    return AppData(
      property: property,
      services: <HouseholdService>[
        electricity,
        gas,
        water,
        councilTax,
        broadband,
      ],
      bills: bills,
      documents: documents,
      reminders: reminders,
      members: members,
      currentMemberId: members.first.id,
      isDemoData: true,
      onboardingComplete: true,
    );
  }
}
