import '../core/json.dart';
import 'enums.dart';
import 'field.dart';

class HouseholdService {
  HouseholdService({
    required this.id,
    required this.propertyId,
    required this.kind,
    this.provider = const Field<String>.missing(),
    this.accountNumber = const Field<String>.missing(),
    this.amountMinor = const Field<int>.missing(),
    this.frequency = PaymentFrequency.monthly,
    this.nextDueDate = const Field<DateTime>.missing(),
    this.lookupKeys = const <String>[],
    this.note,
  });

  final String id;
  final String propertyId;
  final ServiceKind kind;
  final Field<String> provider;
  final Field<String> accountNumber;

  /// The most recent confirmed recurring charge, in pence.
  final Field<int> amountMinor;
  final PaymentFrequency frequency;

  /// Next instalment / direct-debit date, when the resident has confirmed it.
  final Field<DateTime> nextDueDate;

  /// Keys into [LookupLinks] for the official pages that can resolve this.
  final List<String> lookupKeys;
  final String? note;

  ServiceReadiness get readiness {
    if (provider.value == null) return ServiceReadiness.notFound;
    if (provider.needsConfirmation) return ServiceReadiness.needsConfirmation;
    if (amountMinor.value == null || nextDueDate.value == null) {
      return ServiceReadiness.needsDetails;
    }
    return ServiceReadiness.ready;
  }

  /// What still has to happen before this service can drive reminders.
  String get nextActionLabel => switch (readiness) {
        ServiceReadiness.notFound => 'Find your provider',
        ServiceReadiness.needsConfirmation => 'Confirm your provider',
        ServiceReadiness.needsDetails => amountMinor.value == null
            ? 'Add the amount you pay'
            : 'Add the payment date',
        ServiceReadiness.ready => 'Up to date',
      };

  int get monthlyEquivalentMinor {
    final int? amount = amountMinor.value;
    if (amount == null) return 0;
    return frequency.monthlyEquivalent(amount);
  }

  HouseholdService copyWith({
    Field<String>? provider,
    Field<String>? accountNumber,
    Field<int>? amountMinor,
    PaymentFrequency? frequency,
    Field<DateTime>? nextDueDate,
    List<String>? lookupKeys,
    String? note,
  }) {
    return HouseholdService(
      id: id,
      propertyId: propertyId,
      kind: kind,
      provider: provider ?? this.provider,
      accountNumber: accountNumber ?? this.accountNumber,
      amountMinor: amountMinor ?? this.amountMinor,
      frequency: frequency ?? this.frequency,
      nextDueDate: nextDueDate ?? this.nextDueDate,
      lookupKeys: lookupKeys ?? this.lookupKeys,
      note: note ?? this.note,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'propertyId': propertyId,
        'kind': kind.name,
        'provider': provider.toJson((String value) => value),
        'accountNumber': accountNumber.toJson((String value) => value),
        'amountMinor': amountMinor.toJson((int value) => value),
        'frequency': frequency.name,
        'nextDueDate': nextDueDate.toJson((DateTime value) => value.toIso8601String()),
        'lookupKeys': lookupKeys,
        'note': note,
      };

  static HouseholdService? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final String id = asString(json['id']);
    if (id.isEmpty) return null;
    return HouseholdService(
      id: id,
      propertyId: asString(json['propertyId']),
      kind: serviceKindFromName(json['kind']),
      provider: Field<String>.fromJson(asMap(json['provider']), (Object? raw) => asString(raw)),
      accountNumber: Field<String>.fromJson(asMap(json['accountNumber']), (Object? raw) => asString(raw)),
      amountMinor: Field<int>.fromJson(asMap(json['amountMinor']), (Object? raw) => asInt(raw) ?? 0),
      frequency: paymentFrequencyFromName(json['frequency']),
      nextDueDate: Field<DateTime>.fromJson(asMap(json['nextDueDate']), (Object? raw) => asDateTime(raw) ?? DateTime(1970)),
      lookupKeys: asStringList(json['lookupKeys']),
      note: asStringOrNull(json['note']),
    );
  }
}

/// How far along a household service is. Deliberately separate from any
/// provider name: "we found the water company" is not "we know your bill".
enum ServiceReadiness { notFound, needsConfirmation, needsDetails, ready }

extension ServiceReadinessInfo on ServiceReadiness {
  String get label => switch (this) {
        ServiceReadiness.notFound => 'Provider not found',
        ServiceReadiness.needsConfirmation => 'Provider needs confirming',
        ServiceReadiness.needsDetails => 'Account details needed',
        ServiceReadiness.ready => 'Confirmed',
      };
}

ServiceKind serviceKindFromName(Object? value) {
  final String name = asString(value);
  for (final ServiceKind kind in ServiceKind.values) {
    if (kind.name == name) return kind;
  }
  return ServiceKind.other;
}

PaymentFrequency paymentFrequencyFromName(Object? value) {
  final String name = asString(value);
  for (final PaymentFrequency frequency in PaymentFrequency.values) {
    if (frequency.name == name) return frequency;
  }
  return PaymentFrequency.monthly;
}
