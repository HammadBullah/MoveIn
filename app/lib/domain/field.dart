/// The provenance primitive the whole app is built on.
///
/// A [Field] never carries a bare value: it always carries *where the value
/// came from* and *who, if anyone, has confirmed it*. That is what stops the
/// app from presenting a postcode-derived guess as a real bill amount.
library;

/// Where a value came from.
enum FieldSource {
  /// Nothing recorded.
  none,

  /// The resident typed it in.
  userEntered,

  /// The resident told us a suggestion was right.
  userConfirmed,

  /// Inferred from the postcode / property location, e.g. the water company.
  postcodeLookup,

  /// Retrieved from an official lookup service (supplier finder, council
  /// directory, UPRN register).
  officialLookup,

  /// Read out of a document the resident uploaded.
  billExtraction,

  /// A forecast, never a confirmed obligation.
  estimate,
}

extension FieldSourceInfo on FieldSource {
  String get label => switch (this) {
        FieldSource.none => 'Not recorded',
        FieldSource.userEntered => 'Entered by you',
        FieldSource.userConfirmed => 'Confirmed by you',
        FieldSource.postcodeLookup => 'Postcode lookup',
        FieldSource.officialLookup => 'Official lookup',
        FieldSource.billExtraction => 'Read from a bill',
        FieldSource.estimate => 'Estimate',
      };

  /// True when the value was produced without the resident confirming it.
  bool get isAutomatic =>
      this == FieldSource.postcodeLookup ||
      this == FieldSource.officialLookup ||
      this == FieldSource.billExtraction ||
      this == FieldSource.estimate;

  /// True when a human has stood behind the value.
  bool get isHumanConfirmed =>
      this == FieldSource.userEntered || this == FieldSource.userConfirmed;
}

/// How much we trust a [Field].
enum FieldStatus {
  /// We do not have the value at all.
  missing,

  /// We have a candidate value that nobody has confirmed.
  suggested,

  /// The value is recorded and confirmed by the resident (or entered by them).
  confirmed,
}

class Field<T> {
  const Field({
    this.value,
    this.source = FieldSource.none,
    this.status = FieldStatus.missing,
    this.recordedAt,
    this.note,
  });

  const Field.missing({this.note})
      : value = null,
        source = FieldSource.none,
        status = FieldStatus.missing,
        recordedAt = null;

  /// A value we found but that the resident has not confirmed yet.
  factory Field.suggested(
    T value, {
    required FieldSource source,
    String? note,
    DateTime? recordedAt,
  }) {
    return Field<T>(
      value: value,
      source: source,
      status: FieldStatus.suggested,
      note: note,
      recordedAt: recordedAt ?? DateTime.now(),
    );
  }

  factory Field.confirmed(
    T value, {
    FieldSource source = FieldSource.userConfirmed,
    String? note,
    DateTime? recordedAt,
  }) {
    return Field<T>(
      value: value,
      source: source,
      status: FieldStatus.confirmed,
      note: note,
      recordedAt: recordedAt ?? DateTime.now(),
    );
  }

  final T? value;
  final FieldSource source;
  final FieldStatus status;
  final DateTime? recordedAt;
  final String? note;

  bool get hasValue => value != null && status != FieldStatus.missing;

  /// True when this value may be shown as fact without a warning badge.
  bool get isConfirmed => status == FieldStatus.confirmed && value != null;

  bool get needsConfirmation =>
      status == FieldStatus.suggested && value != null;

  /// Promote a suggestion to a confirmed value.
  Field<T> confirm({FieldSource? source, DateTime? at}) {
    return Field<T>(
      value: value,
      source: source ?? FieldSource.userConfirmed,
      status: value == null ? FieldStatus.missing : FieldStatus.confirmed,
      recordedAt: at ?? DateTime.now(),
      note: note,
    );
  }

  /// The resident said the suggestion is wrong: forget the value but keep an
  /// audit trail in [note].
  Field<T> reject({String note = 'Rejected by resident'}) {
    return Field<T>.missing(note: note);
  }

  /// The resident supplied their own value.
  Field<T> edited(T newValue, {FieldSource source = FieldSource.userEntered}) {
    return Field<T>.confirmed(newValue, source: source);
  }

  Field<T> withNote(String? newNote) => Field<T>(
        value: value,
        source: source,
        status: status,
        recordedAt: recordedAt,
        note: newNote,
      );

  Map<String, dynamic> toJson(Object? Function(T value) encode) {
    return <String, dynamic>{
      'value': value == null ? null : encode(value as T),
      'source': source.name,
      'status': status.name,
      'recordedAt': recordedAt?.toIso8601String(),
      'note': note,
    };
  }

  static Field<T> fromJson<T>(
    Map<String, dynamic>? json,
    T Function(Object? raw) decode,
  ) {
    if (json == null) return Field<T>.missing();
    final Object? raw = json['value'];
    return Field<T>(
      value: raw == null ? null : decode(raw),
      source: _sourceFromName(json['source'] as String?),
      status: _statusFromName(json['status'] as String?),
      recordedAt: json['recordedAt'] == null
          ? null
          : DateTime.tryParse(json['recordedAt'] as String),
      note: json['note'] as String?,
    );
  }

  @override
  String toString() => 'Field($value, ${source.name}, ${status.name})';
}

FieldSource _sourceFromName(String? name) {
  for (final FieldSource source in FieldSource.values) {
    if (source.name == name) return source;
  }
  return FieldSource.none;
}

FieldStatus _statusFromName(String? name) {
  for (final FieldStatus status in FieldStatus.values) {
    if (status.name == name) return status;
  }
  return FieldStatus.missing;
}
