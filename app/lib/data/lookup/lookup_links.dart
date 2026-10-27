/// Official places a resident can go to find a provider themselves.
///
/// Deliberately just links. HomeLedger does not scrape these sites and does not
/// log in to provider accounts on anyone's behalf.
library;

class LookupLink {
  const LookupLink({
    required this.key,
    required this.title,
    required this.description,
    required this.url,
    required this.operator,
  });

  final String key;
  final String title;
  final String description;
  final String url;

  /// Who runs the destination, so the resident knows it is official.
  final String operator;
}

abstract final class LookupLinks {
  /// Find the electricity supplier for an address / MPAN.
  static const LookupLink electricitySupplier = LookupLink(
    key: 'electricity_supplier',
    title: 'Find your electricity supplier',
    description:
        'Search by postcode or meter point. If it is not listed, your '
        'distribution network operator can confirm it.',
    url: 'https://www.energynetworks.org/operating-the-networks/'
        'whos-my-network-operator',
    operator: 'Energy Networks Association',
  );

  /// Find the gas supplier for an address / MPRN.
  static const LookupLink gasSupplier = LookupLink(
    key: 'gas_supplier',
    title: 'Find your gas supplier',
    description:
        'Search the gas supplier database by postcode. You may need your '
        'meter point reference number (MPRN) from a previous bill.',
    url: 'https://www.gassupplierdatabase.co.uk/',
    operator: 'Gas supplier database',
  );

  /// Water and sewerage company by postcode.
  static const LookupLink waterAndSewerage = LookupLink(
    key: 'water_provider',
    title: 'Find your water and sewerage company',
    description:
        'The company that supplies your water may be different from the one '
        'that handles your wastewater.',
    url: 'https://www.water.org.uk/customers/find-your-supplier/',
    operator: 'Water UK',
  );

  /// Council tax band and local council.
  static const LookupLink councilTax = LookupLink(
    key: 'council_tax',
    title: 'Check your council tax band',
    description:
        'Confirms the band and the billing authority for the property. Your '
        'account number, balance and instalment dates come from the council.',
    url: 'https://www.gov.uk/council-tax-bands',
    operator: 'GOV.UK',
  );

  /// Find the local authority itself.
  static const LookupLink findCouncil = LookupLink(
    key: 'find_council',
    title: 'Find your local council',
    description: 'Look up the council responsible for council tax and services.',
    url: 'https://www.gov.uk/find-local-council',
    operator: 'GOV.UK',
  );

  /// TV Licence - one provider for the UK.
  static const LookupLink tvLicence = LookupLink(
    key: 'tv_licence',
    title: 'TV Licence',
    description:
        'TV Licensing covers the whole UK, so there is nothing to look up: '
        'either your household has a licence or it does not.',
    url: 'https://www.tvlicensing.co.uk/',
    operator: 'TV Licensing',
  );

  /// Meter point administration number explained (useful for support).
  static const LookupLink meterPoints = LookupLink(
    key: 'meter_points',
    title: 'Understanding MPAN and MPRN',
    description:
        'Your electricity MPAN and gas MPRN identify the supply points at your '
        'property. They are usually printed on a bill.',
    url: 'https://www.ofgem.gov.uk/information-consumers/energy-advice-households/'
        'how-read-your-gas-and-electricity-meter',
    operator: 'Ofgem',
  );

  static const List<LookupLink> all = <LookupLink>[
    electricitySupplier,
    gasSupplier,
    waterAndSewerage,
    councilTax,
    findCouncil,
    tvLicence,
    meterPoints,
  ];

  static LookupLink? byKey(String key) {
    for (final LookupLink link in all) {
      if (link.key == key) return link;
    }
    return null;
  }
}
