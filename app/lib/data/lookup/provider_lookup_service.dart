import '../../domain/enums.dart';
import '../../domain/field.dart';
import '../../domain/property.dart';

/// One candidate provider for a household service, with provenance attached.
class ProviderSuggestion {
  const ProviderSuggestion({
    required this.kind,
    required this.provider,
    required this.source,
    this.confidence = ProviderConfidence.areaOnly,
    this.lookupKey,
    this.explanation,
  });

  final ServiceKind kind;
  final String provider;
  final FieldSource source;
  final ProviderConfidence confidence;

  /// Key into `LookupLinks` for the official page that can confirm this.
  final String? lookupKey;
  final String? explanation;

  Field<String> toField() => Field<String>.suggested(provider, source: source, note: explanation);
}

/// How much a suggestion is worth.
///
/// The UI shows the same three states as the spec: confirmed / suggested /
/// not found, and this enum is what drives that.
enum ProviderConfidence {
  /// The provider is the only one possible for the address (e.g. the council
  /// that covers the postcode). Still needs the resident to accept it.
  areaCertain,

  /// The provider serves the area but the property could be on another.
  areaOnly,

  /// Only the resident (or an official lookup) can know.
  unknown,
}

extension ProviderConfidenceInfo on ProviderConfidence {
  String get label => switch (this) {
        ProviderConfidence.areaCertain => 'Suggested from postcode',
        ProviderConfidence.areaOnly => 'Suggested provider',
        ProviderConfidence.unknown => 'Not found',
      };
}

/// Contract for "which providers serve this property?".
///
/// Implementations must be honest: gas and electricity suppliers are *not*
/// derivable from an address alone, so they should return null and let the UI
/// offer the official lookup instead.
abstract class ProviderLookupService {
  String get sourceName;
  bool get isLive;

  Future<List<ProviderSuggestion>> suggestFor(Property property);
}

/// Offline provider lookup with a small table of illustrative regions.
///
/// The postcode prefixes below are chosen to make the demo obvious and are
/// **not** an authoritative mapping of water companies to areas. Swap this
/// class out for a server-backed implementation when the real data licence is
/// in place.
class DemoProviderLookupService implements ProviderLookupService {
  const DemoProviderLookupService();

  @override
  String get sourceName => 'Demo postcode lookup (offline)';

  @override
  bool get isLive => false;

  static const Map<String, String> _waterByOutward = <String, String>{
    'BS': 'Wessex Water (demo)',
    'CF': 'Dŵr Cymru Welsh Water (demo)',
    'LS': 'Yorkshire Water (demo)',
    'M': 'United Utilities (demo)',
    'SW': 'Thames Water (demo)',
  };

  static const Map<String, String> _wastewaterByOutward = <String, String>{
    'BS': 'Wessex Water (demo)',
    'CF': 'Dŵr Cymru Welsh Water (demo)',
    'LS': 'Yorkshire Water (demo)',
    'M': 'United Utilities (demo)',
    // Same region, different company: this is the case the app must not hide.
    'SW': 'Thames Water (demo)',
  };

  static const Map<String, String> _councilByOutward = <String, String>{
    'BS': 'Bristol City Council (demo)',
    'CF': 'Cardiff Council (demo)',
    'LS': 'Leeds City Council (demo)',
    'M': 'Manchester City Council (demo)',
    'SW': 'London Borough of Wandsworth (demo)',
  };

  @override
  Future<List<ProviderSuggestion>> suggestFor(Property property) async {
    await Future<void>.delayed(const Duration(milliseconds: 300));
    final String outward = _outward(property.postcode);
    final String prefix = _prefix(outward);
    final List<ProviderSuggestion> suggestions = <ProviderSuggestion>[];

    final String? water = _waterByOutward[prefix];
    if (water != null) {
      suggestions.add(
        ProviderSuggestion(
          kind: ServiceKind.water,
          provider: water,
          source: FieldSource.postcodeLookup,
          confidence: ProviderConfidence.areaCertain,
          lookupKey: 'water_provider',
          explanation:
              'Water supply is regional, so this normally follows from the '
              'postcode. Confirm it is the company that bills you.',
        ),
      );
    }

    final String? wastewater = _wastewaterByOutward[prefix];
    if (wastewater != null) {
      suggestions.add(
        ProviderSuggestion(
          kind: ServiceKind.wastewater,
          provider: wastewater,
          source: FieldSource.postcodeLookup,
          confidence: ProviderConfidence.areaOnly,
          lookupKey: 'water_provider',
          explanation:
              'Wastewater is often billed by a different company from your '
              'water supplier, even at the same address.',
        ),
      );
    }

    final String? council = _councilByOutward[prefix];
    if (council != null) {
      suggestions.add(
        ProviderSuggestion(
          kind: ServiceKind.councilTax,
          provider: council,
          source: FieldSource.postcodeLookup,
          confidence: ProviderConfidence.areaCertain,
          lookupKey: 'council_tax',
          explanation:
              'The billing authority follows from where the property is. The '
              'band, account number and instalments do not.',
        ),
      );
    }

    // Electricity and gas are deliberately absent: an address cannot tell us
    // who supplies them, so the resident is pointed at the official lookup.
    return suggestions;
  }

  String _outward(String postcode) {
    final String trimmed = postcode.trim().toUpperCase();
    final int space = trimmed.indexOf(' ');
    return space == -1 ? trimmed : trimmed.substring(0, space);
  }

  String _prefix(String outward) {
    final StringBuffer letters = StringBuffer();
    for (final String char in outward.split('')) {
      if (RegExp('[A-Z]').hasMatch(char)) {
        letters.write(char);
      } else {
        break;
      }
    }
    return letters.toString();
  }
}
