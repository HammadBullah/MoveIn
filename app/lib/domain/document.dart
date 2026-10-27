import '../core/json.dart';
import 'enums.dart';

/// A document the resident has added to the home's records.
///
/// In this build the document is the *text* the resident pasted or typed.
/// When file upload and OCR are wired in, [fileName] and [storageKey] point at
/// the encrypted blob and [extractedText] stays as the searchable transcript.
class DocumentRecord {
  const DocumentRecord({
    required this.id,
    required this.propertyId,
    required this.kind,
    required this.title,
    this.providerName,
    this.fileName,
    this.storageKey,
    this.extractedText,
    this.notes,
    this.billId,
    required this.addedAt,
  });

  final String id;
  final String propertyId;
  final DocumentKind kind;
  final String title;
  final String? providerName;
  final String? fileName;

  /// Server-side object key for the encrypted file, once uploads exist.
  final String? storageKey;
  final String? extractedText;
  final String? notes;
  final String? billId;
  final DateTime addedAt;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'propertyId': propertyId,
        'kind': kind.name,
        'title': title,
        'providerName': providerName,
        'fileName': fileName,
        'storageKey': storageKey,
        'extractedText': extractedText,
        'notes': notes,
        'billId': billId,
        'addedAt': addedAt.toIso8601String(),
      };

  static DocumentRecord? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final String id = asString(json['id']);
    if (id.isEmpty) return null;
    return DocumentRecord(
      id: id,
      propertyId: asString(json['propertyId']),
      kind: _kindFromName(json['kind']),
      title: asString(json['title'], 'Document'),
      providerName: asStringOrNull(json['providerName']),
      fileName: asStringOrNull(json['fileName']),
      storageKey: asStringOrNull(json['storageKey']),
      extractedText: asStringOrNull(json['extractedText']),
      notes: asStringOrNull(json['notes']),
      billId: asStringOrNull(json['billId']),
      addedAt: asDateTime(json['addedAt']) ?? DateTime.now(),
    );
  }
}

DocumentKind _kindFromName(Object? value) {
  final String name = asString(value);
  for (final DocumentKind kind in DocumentKind.values) {
    if (kind.name == name) return kind;
  }
  return DocumentKind.other;
}

/// A reminder the household will see. Delivery (push/local notification) is
/// deliberately not implemented here: it needs a platform plugin and, for a
/// shared household, a server-side scheduler.
class Reminder {
  const Reminder({
    required this.id,
    required this.propertyId,
    required this.kind,
    required this.title,
    required this.dueAt,
    this.note,
    this.billId,
    this.isDone = false,
  });

  final String id;
  final String propertyId;
  final ReminderKind kind;
  final String title;
  final DateTime dueAt;
  final String? note;
  final String? billId;
  final bool isDone;

  Reminder copyWith({bool? isDone, String? title, DateTime? dueAt}) => Reminder(
        id: id,
        propertyId: propertyId,
        kind: kind,
        title: title ?? this.title,
        dueAt: dueAt ?? this.dueAt,
        note: note,
        billId: billId,
        isDone: isDone ?? this.isDone,
      );

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'propertyId': propertyId,
        'kind': kind.name,
        'title': title,
        'dueAt': dueAt.toIso8601String(),
        'note': note,
        'billId': billId,
        'isDone': isDone,
      };

  static Reminder? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final String id = asString(json['id']);
    if (id.isEmpty) return null;
    return Reminder(
      id: id,
      propertyId: asString(json['propertyId']),
      kind: _reminderKindFromName(json['kind']),
      title: asString(json['title'], 'Reminder'),
      dueAt: asDateTime(json['dueAt']) ?? DateTime.now(),
      note: asStringOrNull(json['note']),
      billId: asStringOrNull(json['billId']),
      isDone: asBool(json['isDone']),
    );
  }
}

ReminderKind _reminderKindFromName(Object? value) {
  final String name = asString(value);
  for (final ReminderKind kind in ReminderKind.values) {
    if (kind.name == name) return kind;
  }
  return ReminderKind.custom;
}
