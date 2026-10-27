import '../core/json.dart';
import 'enums.dart';

/// A single property. [uprn] is the Unique Property Reference Number from the
/// address-data provider, when one was available.
///
/// We keep the UPRN because it is the only stable identifier we can use to say
/// "these two records are about the same home". It is *not* a bill identifier
/// and it tells us nothing about accounts.
class Property {
  const Property({
    required this.id,
    required this.line1,
    required this.town,
    required this.postcode,
    required this.tenure,
    this.line2,
    this.uprn,
    this.addressSource = 'Manual entry',
    this.isDemoData = false,
  });

  final String id;
  final String line1;
  final String? line2;
  final String town;
  final String postcode;
  final String? uprn;
  final Tenure tenure;
  final String addressSource;
  final bool isDemoData;

  String get displayAddress {
    final List<String> parts = <String>[
      line1,
      if (line2 != null && line2!.isNotEmpty) line2!,
      town,
      postcode,
    ];
    return parts.join(', ');
  }

  String get shortAddress => '$line1, $postcode';

  Property copyWith({Tenure? tenure, String? uprn, String? addressSource}) {
    return Property(
      id: id,
      line1: line1,
      line2: line2,
      town: town,
      postcode: postcode,
      uprn: uprn ?? this.uprn,
      tenure: tenure ?? this.tenure,
      addressSource: addressSource ?? this.addressSource,
      isDemoData: isDemoData,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'line1': line1,
        'line2': line2,
        'town': town,
        'postcode': postcode,
        'uprn': uprn,
        'tenure': tenure.name,
        'addressSource': addressSource,
        'isDemoData': isDemoData,
      };

  static Property? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final String id = asString(json['id']);
    if (id.isEmpty) return null;
    return Property(
      id: id,
      line1: asString(json['line1']),
      line2: asStringOrNull(json['line2']),
      town: asString(json['town']),
      postcode: asString(json['postcode']),
      uprn: asStringOrNull(json['uprn']),
      tenure: _tenureFromName(json['tenure']),
      addressSource: asString(json['addressSource'], 'Manual entry'),
      isDemoData: asBool(json['isDemoData']),
    );
  }
}

Tenure _tenureFromName(Object? value) {
  final String name = asString(value);
  for (final Tenure tenure in Tenure.values) {
    if (tenure.name == name) return tenure;
  }
  return Tenure.other;
}

/// An address candidate returned by an address lookup service.
class AddressCandidate {
  const AddressCandidate({
    required this.line1,
    required this.town,
    required this.postcode,
    this.line2,
    this.uprn,
    this.source = 'Address lookup',
  });

  final String line1;
  final String? line2;
  final String town;
  final String postcode;
  final String? uprn;
  final String source;

  String get label {
    final List<String> parts = <String>[
      line1,
      if (line2 != null && line2!.isNotEmpty) line2!,
      town,
      postcode,
    ];
    return parts.join(', ');
  }
}
