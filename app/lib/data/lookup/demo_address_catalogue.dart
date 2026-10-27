import '../../domain/property.dart';
import 'address_lookup_service.dart';

/// A tiny, offline stand-in for a licensed address data provider.
///
/// It exists so the whole journey can be demonstrated and tested without an
/// API key. Every address it returns is clearly flagged as demo data, and the
/// UPRNs below are illustrative sequences, **not** real UPRNs.
class DemoAddressLookupService implements AddressLookupService {
  const DemoAddressLookupService();

  @override
  String get sourceName => 'Demo address list (offline)';

  @override
  bool get isLive => false;

  static const List<AddressCandidate> _catalogue = <AddressCandidate>[
    AddressCandidate(
      line1: '12 Example Street',
      town: 'Bristol',
      postcode: 'BS1 4DJ',
      uprn: 'DEMO-0000000012',
      source: 'Demo address list (offline)',
    ),
    AddressCandidate(
      line1: '14 Example Street',
      town: 'Bristol',
      postcode: 'BS1 4DJ',
      uprn: 'DEMO-0000000014',
      source: 'Demo address list (offline)',
    ),
    AddressCandidate(
      line1: 'Flat 3, 25 Harbour Road',
      town: 'Leeds',
      postcode: 'LS1 2AB',
      uprn: 'DEMO-0000000025',
      source: 'Demo address list (offline)',
    ),
    AddressCandidate(
      line1: '8 Meadow Close',
      town: 'Cardiff',
      postcode: 'CF10 1AA',
      uprn: 'DEMO-0000000008',
      source: 'Demo address list (offline)',
    ),
    AddressCandidate(
      line1: '31 Riverside Walk',
      town: 'Manchester',
      postcode: 'M1 1AE',
      uprn: 'DEMO-0000000031',
      source: 'Demo address list (offline)',
    ),
  ];

  /// Additional, generic candidates so any valid-looking postcode returns
  /// something. They are marked invented rather than pretending to be real.
  static const List<String> _streets = <String>[
    '1 Demo Terrace',
    '2 Demo Terrace',
    '3 Demo Terrace',
  ];

  @override
  Future<List<AddressCandidate>> searchPostcode(String postcode) async {
    final String normalised = normalisePostcode(postcode);
    if (!looksLikeUkPostcode(normalised)) {
      throw AddressLookupException(
        'That does not look like a UK postcode. Try a format like BS1 4DJ.',
      );
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));

    final List<AddressCandidate> matches = _catalogue
        .where((AddressCandidate c) => c.postcode == normalised)
        .toList(growable: true);

    if (matches.isEmpty) {
      for (final String street in _streets) {
        matches.add(
          AddressCandidate(
            line1: street,
            town: outwardCode(normalised),
            postcode: normalised,
            uprn: null,
            source: 'Demo address list (offline)',
          ),
        );
      }
    }
    return matches;
  }

  @override
  Future<AddressCandidate?> byUprn(String uprn) async {
    for (final AddressCandidate candidate in _catalogue) {
      if (candidate.uprn == uprn) return candidate;
    }
    return null;
  }
}
