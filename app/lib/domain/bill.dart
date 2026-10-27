import '../core/json.dart';
import 'enums.dart';
import 'field.dart';
import 'household_service.dart';

/// A single recorded charge.
///
/// A bill is only ever created from evidence: something the resident typed,
/// something read from a document they uploaded, or a provider integration.
/// It is never inferred from an address.
class Bill {
  Bill({
    required this.id,
    required this.propertyId,
    required this.kind,
    this.provider = const Field<String>.missing(),
    this.amountMinor = const Field<int>.missing(),
    this.dueDate = const Field<DateTime>.missing(),
    this.periodStart,
    this.periodEnd,
    this.frequency = PaymentFrequency.monthly,
    this.paymentStatus = PaymentStatus.unknown,
    this.documentId,
    this.notes,
    DateTime? createdAt,
    DateTime? updatedAt,
  })  : createdAt = createdAt ?? DateTime.now(),
        updatedAt = updatedAt ?? DateTime.now();

  final String id;
  final String propertyId;
  final ServiceKind kind;
  final Field<String> provider;
  final Field<int> amountMinor;
  final Field<DateTime> dueDate;
  final DateTime? periodStart;
  final DateTime? periodEnd;
  final PaymentFrequency frequency;
  final PaymentStatus paymentStatus;
  final String? documentId;
  final String? notes;
  final DateTime createdAt;
  final DateTime updatedAt;

  bool get isPaid => paymentStatus == PaymentStatus.paid;

  /// An estimated amount is a forecast, never an obligation.
  bool get isEstimate => amountMinor.source == FieldSource.estimate;

  /// True when we can show a real amount and a real date.
  bool get hasConfirmedAmount =>
      amountMinor.isConfirmed && !isEstimate;

  bool get isActionable => amountMinor.hasValue && dueDate.hasValue;

  bool isOverdue(DateTime now) {
    final DateTime? due = dueDate.value;
    if (due == null || isPaid) return false;
    return due.isBefore(DateTime(now.year, now.month, now.day));
  }

  bool isDueWithin(DateTime now, int days) {
    final DateTime? due = dueDate.value;
    if (due == null || isPaid) return false;
    final int delta = due
        .difference(DateTime(now.year, now.month, now.day))
        .inDays;
    return delta >= 0 && delta <= days;
  }

  BillState stateFor(DateTime now) {
    if (isPaid) return BillState.paid;
    if (!isActionable) return BillState.needsDetails;
    if (isOverdue(now)) return BillState.overdue;
    if (isDueWithin(now, 7)) return BillState.dueSoon;
    return BillState.upcoming;
  }

  Bill copyWith({
    Field<String>? provider,
    Field<int>? amountMinor,
    Field<DateTime>? dueDate,
    DateTime? periodStart,
    DateTime? periodEnd,
    PaymentFrequency? frequency,
    PaymentStatus? paymentStatus,
    String? documentId,
    String? notes,
  }) {
    return Bill(
      id: id,
      propertyId: propertyId,
      kind: kind,
      provider: provider ?? this.provider,
      amountMinor: amountMinor ?? this.amountMinor,
      dueDate: dueDate ?? this.dueDate,
      periodStart: periodStart ?? this.periodStart,
      periodEnd: periodEnd ?? this.periodEnd,
      frequency: frequency ?? this.frequency,
      paymentStatus: paymentStatus ?? this.paymentStatus,
      documentId: documentId ?? this.documentId,
      notes: notes ?? this.notes,
      createdAt: createdAt,
      updatedAt: DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'propertyId': propertyId,
        'kind': kind.name,
        'provider': provider.toJson((String value) => value),
        'amountMinor': amountMinor.toJson((int value) => value),
        'dueDate': dueDate.toJson((DateTime value) => value.toIso8601String()),
        'periodStart': periodStart?.toIso8601String(),
        'periodEnd': periodEnd?.toIso8601String(),
        'frequency': frequency.name,
        'paymentStatus': paymentStatus.name,
        'documentId': documentId,
        'notes': notes,
        'createdAt': createdAt.toIso8601String(),
        'updatedAt': updatedAt.toIso8601String(),
      };

  static Bill? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final String id = asString(json['id']);
    if (id.isEmpty) return null;
    return Bill(
      id: id,
      propertyId: asString(json['propertyId']),
      kind: serviceKindFromName(json['kind']),
      provider: Field<String>.fromJson(
        asMap(json['provider']),
        (Object? raw) => asString(raw),
      ),
      amountMinor: Field<int>.fromJson(
        asMap(json['amountMinor']),
        (Object? raw) => asInt(raw) ?? 0,
      ),
      dueDate: Field<DateTime>.fromJson(
        asMap(json['dueDate']),
        (Object? raw) => asDateTime(raw) ?? DateTime(1970),
      ),
      periodStart: asDateTime(json['periodStart']),
      periodEnd: asDateTime(json['periodEnd']),
      frequency: paymentFrequencyFromName(json['frequency']),
      paymentStatus: _paymentStatusFromName(json['paymentStatus']),
      documentId: asStringOrNull(json['documentId']),
      notes: asStringOrNull(json['notes']),
      createdAt: asDateTime(json['createdAt']) ?? DateTime.now(),
      updatedAt: asDateTime(json['updatedAt']) ?? DateTime.now(),
    );
  }
}

enum BillState { paid, overdue, dueSoon, upcoming, needsDetails }

extension BillStateInfo on BillState {
  String get label => switch (this) {
        BillState.paid => 'Paid',
        BillState.overdue => 'Overdue',
        BillState.dueSoon => 'Due soon',
        BillState.upcoming => 'Upcoming',
        BillState.needsDetails => 'Needs details',
      };
}

PaymentStatus _paymentStatusFromName(Object? value) {
  final String name = asString(value);
  for (final PaymentStatus status in PaymentStatus.values) {
    if (status.name == name) return status;
  }
  return PaymentStatus.unknown;
}
