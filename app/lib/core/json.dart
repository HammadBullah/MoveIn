/// Small, forgiving JSON helpers.
///
/// Persisted data lives on the resident's device and is eventually going to
/// arrive from a backend, so decoding must never throw on a missing or
/// slightly wrong field.
library;

String asString(Object? value, [String fallback = '']) {
  if (value is String) return value;
  if (value is num || value is bool) return value.toString();
  return fallback;
}

String? asStringOrNull(Object? value) {
  final String text = asString(value);
  return text.isEmpty ? null : text;
}

int? asInt(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}

int asIntOr(Object? value, int fallback) => asInt(value) ?? fallback;

double? asDouble(Object? value) {
  if (value is double) return value;
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value);
  return null;
}

bool asBool(Object? value, [bool fallback = false]) {
  if (value is bool) return value;
  if (value is String) return value == 'true';
  if (value is num) return value != 0;
  return fallback;
}

DateTime? asDateTime(Object? value) {
  if (value is String && value.isNotEmpty) return DateTime.tryParse(value);
  return null;
}

Map<String, dynamic>? asMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map<Object?, Object?>) {
    return value.map<String, dynamic>(
      (Object? key, Object? item) => MapEntry<String, dynamic>(key.toString(), item),
    );
  }
  return null;
}

List<Map<String, dynamic>> asMapList(Object? value) {
  if (value is! List<Object?>) return const <Map<String, dynamic>>[];
  return value
      .map<Map<String, dynamic>?>(asMap)
      .whereType<Map<String, dynamic>>()
      .toList();
}

List<String> asStringList(Object? value) {
  if (value is! List<Object?>) return const <String>[];
  return value.map<String>(asString).where((String s) => s.isNotEmpty).toList();
}
