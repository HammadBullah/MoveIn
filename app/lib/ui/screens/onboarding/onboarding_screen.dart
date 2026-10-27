import 'package:flutter/material.dart';

import '../../../data/lookup/address_lookup_service.dart';
import '../../../data/lookup/demo_address_catalogue.dart';
import '../../../domain/enums.dart';
import '../../../domain/property.dart';
import '../../scope.dart';
import '../../widgets/layout.dart';

/// Step 1 of the promise: "enter your address once".
///
/// Three pages on one screen: address, tenure/name, services. Creating the
/// household does *not* guess any providers; that is the next screen's job.
class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({
    super.key,
    this.addressLookup = const DemoAddressLookupService(),
  });

  final AddressLookupService addressLookup;

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  int _step = 0;
static const List<ServiceKind> _onboardingDefaults = <ServiceKind>[
    ServiceKind.electricity,
    ServiceKind.gas,
    ServiceKind.water,
    ServiceKind.councilTax,
    ServiceKind.broadband,
  ];

  final TextEditingController _postcode = TextEditingController();
  final TextEditingController _name = TextEditingController();

  bool _searching = false;
  String? _lookupError;
  List<AddressCandidate> _candidates = const <AddressCandidate>[];
  AddressCandidate? _selected;

  Tenure _tenure = Tenure.renting;
  final Set<ServiceKind> kinds = ServiceKind.values.toSet();
  final Set<ServiceKind> _services = <ServiceKind>{};

  bool _saving = false;

  @override
  void dispose() {
    _postcode.dispose();
    _name.dispose();
    super.dispose();
  }

  Future<void> _search() async {
    final String input = _postcode.text.trim();
    if (input.isEmpty) {
      setState(() => _lookupError = 'Enter a postcode to search.');
      return;
    }
    if (!looksLikeUkPostcode(input)) {
      setState(() => _lookupError =
          'That does not look like a UK postcode. Try a format like BS1 4DJ.');
      return;
    }

    setState(() {
      _searching = true;
      _lookupError = null;
      _candidates = const <AddressCandidate>[];
      _selected = null;
    });

    try {
      final List<AddressCandidate> results =
          await widget.addressLookup.searchPostcode(input);
      if (!mounted) return;
      setState(() {
        _candidates = results;
        _lookupError = results.isEmpty
            ? 'No addresses found for that postcode. You can enter one manually.'
            : null;
      });
    } on AddressLookupException catch (error) {
      if (!mounted) return;
      setState(() => _lookupError = error.message);
    } catch (error) {
      if (!mounted) return;
      setState(() => _lookupError = 'Address search failed: $error');
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  Future<void> _enterManually() async {
    final AddressCandidate? candidate = await showDialog<AddressCandidate>(
      context: context,
      builder: (BuildContext context) => _ManualAddressDialog(
        postcode: normalisePostcode(_postcode.text),
      ),
    );
    if (candidate != null) {
      setState(() {
        _selected = candidate;
        _lookupError = null;
      });
    }
  }

  Future<void> _finish() async {
    final AddressCandidate? address = _selected;
    if (address == null || _services.isEmpty) return;

    const Map<ServiceKind, int> serviceOrder = <ServiceKind, int>{
      ServiceKind.electricity: 0,
      ServiceKind.gas: 1,
      ServiceKind.water: 2,
      ServiceKind.councilTax: 3,
      ServiceKind.broadband: 4,
    };

    setState(() => _saving = true);
    await MoveInScope.read(context).createHousehold(
      address: address,
      tenure: _tenure,
      services: _services.toList()
        ..sort((ServiceKind a, ServiceKind b) {
          final int aOrder = serviceOrder[a] ?? serviceOrder.length;
          final int bOrder = serviceOrder[b] ?? serviceOrder.length;
          return aOrder.compareTo(bOrder);
        }),
      residentName: _name.text,
    );
    // RootGate swaps to the confirmation screen once the property exists.
    if (mounted) setState(() => _saving = false);
  }


  bool get _canContinue {
    if (_step == 0) return _selected != null;
    if (_step == 1) return true;
    return _services.isNotEmpty;
  }

  void _next() {
    if (_step < 2) {
      setState(() => _step++);
    } else {
      _finish();
    }
  }

  void _back() {
    if (_step == 0) return;
    setState(() => _step--);
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        leading: _step == 0 ? null : IconButton(
          onPressed: _back,
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back',
        ),
        title: Text(switch (_step) {
          0 => 'Your address',
          1 => 'About your household',
          _ => 'What do you pay for?',
        }),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(4),
          child: LinearProgressIndicator(value: (_step + 1) / 3, minHeight: 4),
        ),
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                children: <Widget>[
                  if (_step == 0) ..._addressStep(theme),
                  if (_step == 1) ..._householdStep(theme),
                  if (_step == 2) ..._servicesStep(theme),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
              child: Row(
                children: <Widget>[
                  Expanded(
                    child: FilledButton(
                      onPressed: _canContinue && !_saving ? _next : null,
                      child: _saving
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Text(_step == 2 ? 'Create my household' : 'Continue'),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _addressStep(ThemeData theme) {
    return <Widget>[
      Text(
        'Enter your address once. We will work out which household services '
        'apply, then ask you to confirm the details only you can know.',
        style: theme.textTheme.bodyMedium,
      ),
      const SizedBox(height: 16),
      NoticeBanner(
        message: widget.addressLookup.isLive
            ? 'Addresses come from a licensed address data provider. Your '
                'postcode is sent to the server to look it up.'
            : 'Demo address list. Nothing is looked up online and no real '
                'property data is used. In production this screen calls a '
                'licensed address provider through the HomeLedger API.',
      ),
      const SizedBox(height: 16),
      TextField(
        controller: _postcode,
        textCapitalization: TextCapitalization.characters,
        textInputAction: TextInputAction.search,
        onSubmitted: (_) => _search(),
        decoration: InputDecoration(
          labelText: 'Postcode',
          hintText: 'e.g. BS1 4DJ',
          prefixIcon: const Icon(Icons.location_on_outlined),
          errorText: _lookupError,
          suffixIcon: _searching
              ? const Padding(
                  padding: EdgeInsets.all(12),
                  child: SizedBox(
                    height: 16,
                    width: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                )
              : IconButton(
                  onPressed: _search,
                  icon: const Icon(Icons.search),
                  tooltip: 'Search',
                ),
        ),
      ),
      const SizedBox(height: 8),
      Row(
        children: <Widget>[
          TextButton.icon(
            onPressed: _enterManually,
            icon: const Icon(Icons.edit_outlined, size: 18),
            label: const Text('Enter address manually'),
          ),
        ],
      ),
      Align(
        alignment: Alignment.centerLeft,
        child: TextButton.icon(
          onPressed: () => MoveInScope.read(context).loadDemoHousehold(),
          icon: const Icon(Icons.science_outlined, size: 18),
          label: const Text('Explore the example household instead'),
        ),
      ),
      if (_candidates.isNotEmpty) ...<Widget>[
        const SizedBox(height: 8),
        Text('Select your property', style: theme.textTheme.titleSmall),
        const SizedBox(height: 8),
        AppCard(
          child: Column(
            children: <Widget>[
              for (int i = 0; i < _candidates.length; i++) ...<Widget>[
                ListTile(
                  title: Text(_candidates[i].line1),
                  subtitle: Text(
                    '${_candidates[i].town}, ${_candidates[i].postcode}'
                    '${_candidates[i].uprn == null ? '' : ' · UPRN ${_candidates[i].uprn}'}',
                  ),
                  trailing: _selected == _candidates[i]
                      ? Icon(Icons.check_circle, color: theme.colorScheme.primary)
                      : const Icon(Icons.circle_outlined),
                  onTap: () => setState(() => _selected = _candidates[i]),
                ),
                if (i != _candidates.length - 1) const Divider(height: 1),
              ],
            ],
          ),
        ),
      ],
      if (_selected != null) ...<Widget>[
        const SizedBox(height: 12),
        SectionCard(
          title: 'Selected property',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(_selected!.label, style: theme.textTheme.bodyMedium),
              const SizedBox(height: 4),
              Text(
                _selected!.uprn == null
                    ? 'No property identifier available. You can still track '
                        'bills for this home.'
                    : 'Property identifier (UPRN): ${_selected!.uprn}',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ],
    ];
  }

  List<Widget> _householdStep(ThemeData theme) {
    return <Widget>[
      Text(
        'Who lives here, and do you rent or own? This changes who pays council '
        'tax and who can act on an account.',
        style: theme.textTheme.bodyMedium,
      ),
      const SizedBox(height: 16),
      AppCard(
        child: Column(
          children: <Widget>[
            for (final Tenure tenure in Tenure.values) ...<Widget>[
              ListTile(
                leading: Icon(switch (tenure) {
  Tenure.renting => Icons.key_outlined,
  Tenure.owning => Icons.house_outlined,
  Tenure.other => Icons.help_outline,
}),
                title: Text(tenure.label),
                trailing: _tenure == tenure
                    ? Icon(Icons.check_circle, color: theme.colorScheme.primary)
                    : const Icon(Icons.circle_outlined),
                onTap: () => setState(() => _tenure = tenure),
              ),
              if (tenure != Tenure.values.last) const Divider(height: 1),
            ],
          ],
        ),
      ),
      const SizedBox(height: 16),
      TextField(
        controller: _name,
        textCapitalization: TextCapitalization.words,
        decoration: const InputDecoration(
          labelText: 'Your name (optional)',
          hintText: 'Used for the household member list',
          prefixIcon: Icon(Icons.person_outline),
        ),
      ),
      const SizedBox(height: 16),
      const NoticeBanner(
        message: 'You can invite other members of the household later and give '
            'them their own permissions.',
      ),
    ];
  }

  List<Widget> _servicesStep(ThemeData theme) {
    return <Widget>[
      Text(
        'Choose the services you want to track. Every one of them starts as '
        '"provider not confirmed": a property does not tell us who bills you.',
        style: theme.textTheme.bodyMedium,
      ),
      const SizedBox(height: 16),
      AppCard(
        child: Column(
          children: <Widget>[
            for (final ServiceKind kind in _onboardingDefaults) ...<Widget>[
              CheckboxListTile(
                value: _services.contains(kind),
                onChanged: (bool? value) {
                  setState(() {
                    if (value == true) {
                      _services.add(kind);
                    } else {
                      _services.remove(kind);
                    }
                  });
                },
                title: Text(kind.label),
                subtitle: Text(
                  kind.onboardingDiscoveryHint,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                controlAffinity: ListTileControlAffinity.leading,
              ),
              if (kind != _onboardingDefaults.last) const Divider(height: 1),
            ],
          ],
        ),
      ),
      const SizedBox(height: 16),
      const NoticeBanner(
        tone: NoticeTone.warning,
        message: 'Amounts and payment dates are never inferred from your '
            'address. You will add them from a bill, a statement or by typing '
            'them in.',
      ),
    ];
  }
}



class _ManualAddressDialog extends StatefulWidget {
  const _ManualAddressDialog({required this.postcode});

  final String postcode;

  @override
  State<_ManualAddressDialog> createState() => _ManualAddressDialogState();
}

class _ManualAddressDialogState extends State<_ManualAddressDialog> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  late final TextEditingController _line1 =
      TextEditingController(text: '');
  final TextEditingController _line2 = TextEditingController();
  final TextEditingController _town = TextEditingController();
  late final TextEditingController _postcode =
      TextEditingController(text: widget.postcode);

  @override
  void dispose() {
    _line1.dispose();
    _line2.dispose();
    _town.dispose();
    _postcode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Enter address manually'),
      content: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              TextFormField(
                controller: _line1,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'Address line 1'),
                validator: (String? value) =>
                    (value == null || value.trim().isEmpty) ? 'Required' : null,
              ),
              const SizedBox(height: 8),
              TextFormField(
                controller: _line2,
                decoration: const InputDecoration(labelText: 'Address line 2 (optional)'),
              ),
              const SizedBox(height: 8),
              TextFormField(
                controller: _town,
                decoration: const InputDecoration(labelText: 'Town or city'),
                validator: (String? value) =>
                    (value == null || value.trim().isEmpty) ? 'Required' : null,
              ),
              const SizedBox(height: 8),
              TextFormField(
                controller: _postcode,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(labelText: 'Postcode'),
                validator: (String? value) {
                  if (value == null || !looksLikeUkPostcode(value)) {
                    return 'Enter a valid UK postcode';
                  }
                  return null;
                },
              ),
            ],
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            if (_formKey.currentState?.validate() != true) return;
            Navigator.of(context).pop(
              AddressCandidate(
                line1: _line1.text.trim(),
                line2: _line2.text.trim().isEmpty ? null : _line2.text.trim(),
                town: _town.text.trim(),
                postcode: normalisePostcode(_postcode.text),
                source: 'Entered manually',
              ),
            );
          },
          child: const Text('Use this address'),
        ),
      ],
    );
  }
}
