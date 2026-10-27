/// Shared enumerations for the HomeLedger domain.
///
/// Everything in this file is deliberately dependency-free so it can be
/// reused by tests and by a future shared package.
library;

/// The household services HomeLedger knows how to reason about.
///
/// A [ServiceKind] describes a *slot* for a property ("this home has an
/// electricity supply"), not a confirmed account.
enum ServiceKind {
  electricity,
  gas,
  water,
  wastewater,
  councilTax,
  broadband,
  tvLicence,
  homeInsurance,
  other,
}

extension ServiceKindInfo on ServiceKind {
  String get label => switch (this) {
        ServiceKind.electricity => 'Electricity',
        ServiceKind.gas => 'Gas',
        ServiceKind.water => 'Water',
        ServiceKind.wastewater => 'Wastewater',
        ServiceKind.councilTax => 'Council tax',
        ServiceKind.broadband => 'Broadband',
        ServiceKind.tvLicence => 'TV Licence',
        ServiceKind.homeInsurance => 'Home insurance',
        ServiceKind.other => 'Other',
      };

  /// How this service can be matched to a property, in plain language.
  ///
  /// This text is shown in the UI next to the provenance chip so the resident
  /// can see *why* something is only a suggestion.
  String get discoveryHint => switch (this) {
        ServiceKind.electricity =>
          'Supplier is per property and per account. Use the official supplier '
              'lookup if you do not know it.',
        ServiceKind.gas =>
          'Gas supplier can usually be found with the official gas supplier '
              'lookup, but it is not published with the address.',
        ServiceKind.water =>
          'Water is supplied by a regional company that can normally be found '
              'from the postcode.',
        ServiceKind.wastewater =>
          'Wastewater is often handled by a different company from your water '
              'supplier, even in the same region.',
        ServiceKind.councilTax =>
          'Your council follows from the property location. The band, balance '
              'and instalment dates do not.',
        ServiceKind.broadband =>
          'Broadband is chosen by the resident, so it cannot be derived from '
              'the address. Add it from a bill.',
        ServiceKind.tvLicence =>
          'TV Licence is one provider for the whole UK. One payment per home.',
        ServiceKind.homeInsurance =>
          'Buildings and contents insurance are private arrangements. Add them '
              'from a policy or statement.',
        ServiceKind.other => 'Anything else you pay for at this home.',
      };

  bool get isEnergy =>
      this == ServiceKind.electricity || this == ServiceKind.gas;

  /// The slots every UK home is normally offered during setup.
  static const List<ServiceKind> onboardingDefaults = <ServiceKind>[
    ServiceKind.electricity,
    ServiceKind.gas,
    ServiceKind.water,
    ServiceKind.wastewater,
    ServiceKind.councilTax,
  ];

  static List<ServiceKind> get selectable => ServiceKind.values;
}

/// How often a recurring amount is charged.
enum PaymentFrequency {
  weekly,
  fortnightly,
  monthly,
  quarterly,
  annually,
  oneOff,
}

extension PaymentFrequencyInfo on PaymentFrequency {
  String get label => switch (this) {
        PaymentFrequency.weekly => 'Weekly',
        PaymentFrequency.fortnightly => 'Every 2 weeks',
        PaymentFrequency.monthly => 'Monthly',
        PaymentFrequency.quarterly => 'Quarterly',
        PaymentFrequency.annually => 'Yearly',
        PaymentFrequency.oneOff => 'One-off',
      };

  /// Number of charges per year. Returns 0 for one-off amounts.
  double get perYear => switch (this) {
        PaymentFrequency.weekly => 52,
        PaymentFrequency.fortnightly => 26,
        PaymentFrequency.monthly => 12,
        PaymentFrequency.quarterly => 4,
        PaymentFrequency.annually => 1,
        PaymentFrequency.oneOff => 0,
      };

  /// Monthly equivalent of an amount charged at this frequency.
  ///
  /// One-off amounts have no monthly equivalent, so they return 0 and callers
  /// must not treat the result as a recurring cost.
  int monthlyEquivalent(int amountMinor) {
    if (perYear == 0) return 0;
    return (amountMinor * perYear / 12).round();
  }
}

/// Rent or own. Asked at onboarding because it changes who pays council tax
/// and who can act on the account.
enum Tenure { renting, owning, other }

extension TenureInfo on Tenure {
  String get label => switch (this) {
        Tenure.renting => 'I rent this home',
        Tenure.owning => 'I own this home',
        Tenure.other => 'Something else',
      };
}

/// Permission levels for a shared household.
enum MemberRole { owner, tenant, housemate, viewer }

extension MemberRoleInfo on MemberRole {
  String get label => switch (this) {
        MemberRole.owner => 'Owner',
        MemberRole.tenant => 'Tenant',
        MemberRole.housemate => 'Housemate',
        MemberRole.viewer => 'Viewer',
      };

  bool get canEditBills =>
      this == MemberRole.owner ||
      this == MemberRole.tenant ||
      this == MemberRole.housemate;

  bool get canManageHousehold => this == MemberRole.owner;

  bool get canSeeAmounts => this != MemberRole.viewer;
}

enum ReminderKind { payment, contractRenewal, meterReading, custom }

extension ReminderKindInfo on ReminderKind {
  String get label => switch (this) {
        ReminderKind.payment => 'Payment due',
        ReminderKind.contractRenewal => 'Contract renewal',
        ReminderKind.meterReading => 'Meter reading',
        ReminderKind.custom => 'Reminder',
      };
}

enum DocumentKind { bill, statement, meterReading, receipt, policy, other }

extension DocumentKindInfo on DocumentKind {
  String get label => switch (this) {
        DocumentKind.bill => 'Bill',
        DocumentKind.statement => 'Statement',
        DocumentKind.meterReading => 'Meter reading',
        DocumentKind.receipt => 'Receipt',
        DocumentKind.policy => 'Policy',
        DocumentKind.other => 'Document',
      };
}

/// Whether a bill has been paid, and whether we actually know that.
enum PaymentStatus {
  /// No evidence either way. The default, and the honest default.
  unknown,
  scheduled,
  paid,
}
