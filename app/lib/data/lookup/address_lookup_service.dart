import '../../domain/property.dart';

/// Contract for address search.
///
/// The real implementation talks to Ordnance Survey Places (or any other
/// licensed address provider) **through the Flask backend**, never directly
/// from the phone:
///
///  * the API key must not ship inside the app binary;
///  * the provider's terms and pricing need to be accepted once, server-side.
///
/// See `server/home_ledger/lookups/os_places.py` for the server-side client.
abstract class AddressLookupService {
  /// Human-readable name shown in the UI next to the result.
  String get sourceName;

  /// True when this implementation queries a live licensed service.
  bool get isLive;

  /// Search by full or partial postcode. Returns an empty list when nothing
  /// matches; throws [AddressLookupException] on transport or auth failures.
  Future<List<AddressCandidate>> searchPostcode(String postcode);

  /// Resolve a UPRN back to an address candidate, if supported.
  Future<AddressCandidate?> byUprn(String uprn);
}

class AddressLookupException implements Exception {
  AddressLookupException(this.message);
  final String message;

  @override
  String toString() => message;
}

/// Validates UK postcodes well enough to avoid pointless API calls.
///
/// This is a *format* check only: it does not mean the postcode exists.
final RegExp ukPostcodePattern = RegExp(
  r'^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$',
  caseSensitive: false,
);

bool looksLikeUkPostcode(String input) =>
    ukPostcodePattern.hasMatch(input.trim());

/// Normalise to the canonical "OUTWARD INWARD" form with a single space.
String normalisePostcode(String input) {
  final String compact = input.replaceAll(RegExp(r'\s+'), '').toUpperCase();
  if (compact.length < 5) return compact;
  return '${compact.substring(0, compact.length - 3)} '
      '${compact.substring(compact.length - 3)}';
}

String outwardCode(String postcode) {
  final String normalised = normalisePostcode(postcode);
  final int space = normalised.indexOf(' ');
  return space == -1 ? normalised : normalised.substring(0, space);
}
