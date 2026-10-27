import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../data/lookup/provider_lookup_service.dart';
import '../../../data/store.dart';
import '../../../domain/enums.dart';
import '../../../domain/household_service.dart';
import '../../../domain/property.dart';
import '../../scope.dart';
import '../../widgets/layout.dart';
import 'provider_confirm_card.dart';

/// Step 3 of the promise: "discover the relevant services, then confirm".
///
/// This is the screen that keeps the app honest. It separates:
///  * what a postcode can tell us (water company, council, nothing else);
///  * what only the resident can tell us (their supplier, their account);
///  * what only a bill can tell us (amount, due date).
class ConfirmSetupScreen extends StatefulWidget {
  const ConfirmSetupScreen({
    super.key,
    this.isOnboarding = false,
    this.providerLookup = const DemoProviderLookupService(),
  });

  final bool isOnboarding;
  final ProviderLookupService providerLookup;

  @override
  State<ConfirmSetupScreen> createState() => _ConfirmSetupScreenState();
}

class _ConfirmSetupScreenState extends State<ConfirmSetupScreen> {
  bool _discovering = false;
  bool _autoRan = false;
  String? _status;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_autoRan) return;
    _autoRan = true;
    final AppStore store = MoveInScope.read(context);
    final bool nothingYet = store.data.services
        .every((HouseholdService s) => !s.provider.hasValue);
    if (nothingYet) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _discover());
    }
  }

  Future<void> _discover() async {
    final AppStore store = MoveInScope.read(context);
    final Property? property = store.data.property;
    if (property == null || _discovering) return;

    setState(() {
      _discovering = true;
      _status = null;
    });

    try {
      final List<ProviderSuggestion> suggestions =
          await widget.providerLookup.suggestFor(property);
      await store.applySuggestions(suggestions);
      if (!mounted) return;
      final Set<ServiceKind> found =
          suggestions.map((ProviderSuggestion s) => s.kind).toSet();
      final List<ServiceKind> remaining = store.data.services
          .map((HouseholdService s) => s.kind)
          .where((ServiceKind k) => !found.contains(k))
          .toList();
      setState(() {
        _status = suggestions.isEmpty
            ? 'No providers could be suggested from this address. Use the '
                'official lookups below.'
            : '${found.length} suggestion${found.length == 1 ? '' : 's'} added'
                '${remaining.isEmpty ? '' : ' · still needed: ${remaining.map((ServiceKind k) => k.label).join(', ')}'}';
      });
    } catch (error) {
      if (mounted) setState(() => _status = 'Provider lookup failed: $error');
    } finally {
      if (mounted) setState(() => _discovering = false);
    }
  }

  Future<void> _addService() async {
    final AppStore store = MoveInScope.read(context);
    final List<ServiceKind> available = ServiceKind.values
        .where((ServiceKind kind) =>
            store.data.services.every((HouseholdService s) => s.kind != kind))
        .toList();
    if (available.isEmpty) {
      _snack('Every service HomeLedger knows about is already on this home.');
      return;
    }

    final ServiceKind? picked = await showModalBottomSheet<ServiceKind>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (BuildContext context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.only(bottom: 16),
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Text(
                'Add a service',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            for (final ServiceKind kind in available)
              ListTile(
                leading: Icon(iconForServiceName(kind.name)),
                title: Text(kind.label),
                subtitle: Text(
                  kind.discoveryHint,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                onTap: () => Navigator.of(context).pop(kind),
              ),
          ],
        ),
      ),
    );

    if (picked == null) return;
    await store.addService(picked);
  }

  Future<void> _finish() async {
    final AppStore store = MoveInScope.read(context);
    if (widget.isOnboarding) {
      await store.completeOnboarding();
    } else if (mounted) {
      Navigator.of(context).pop();
    }
  }

  Future<void> _changeAddress() async {
    final bool ok = await confirmAction(
      context,
      title: 'Start setup again?',
      message: 'Choosing a different address starts a new household and clears '
          'the bills, documents and reminders recorded for this one.',
      confirmLabel: 'Choose a new address',
      destructive: true,
    );
    if (!ok || !mounted) return;
    final AppStore store = MoveInScope.read(context);
    await store.resetAll();
  }

  void _snack(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final AppStore store = MoveInScope.of(context);
    final Property? property = store.data.property;
    final List<HouseholdService> services = store.data.services;

    if (property == null) {
      return const Scaffold(body: Center(child: Text('No property recorded.')));
    }

    final int outstanding = services
        .where((HouseholdService s) => s.readiness != ServiceReadiness.ready)
        .length;

    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: !widget.isOnboarding,
        title: const Text('Your household setup'),
        actions: <Widget>[
          IconButton(
            tooltip: 'Add a service',
            onPressed: _addService,
            icon: const Icon(Icons.add_circle_outline),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          children: <Widget>[
            Text(
              'Enter your address once. Discover the relevant household '
              'services. Confirm the information. Track your bills in one '
              'dashboard.',
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            _AddressCard(property: property, onChangeAddress: _changeAddress),
            const SizedBox(height: 12),
            if (property.isDemoData)
              const Padding(
                padding: EdgeInsets.only(bottom: 12),
                child: NoticeBanner(
                  tone: NoticeTone.warning,
                  icon: Icons.science_outlined,
                  message: 'Illustrative example, not a live address lookup. '
                      'Provider names end in "(demo)".',
                ),
              ),
            Row(
              children: <Widget>[
                Expanded(
                  child: FilledButton.icon(
                    onPressed: _discovering ? null : _discover,
                    icon: _discovering
                        ? const SizedBox(
                            height: 16,
                            width: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.travel_explore, size: 18),
                    label: Text(
                      _discovering ? 'Looking for providers…' : 'Look for providers',
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'Uses ${widget.providerLookup.sourceName}. '
              '${widget.providerLookup.isLive ? '' : 'No live data is fetched in this build.'}',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            if (_status != null) ...<Widget>[
              const SizedBox(height: 12),
              NoticeBanner(message: _status!),
            ],
            const SizedBox(height: 20),
            Row(
              children: <Widget>[
                Expanded(
                  child: Text('Services at this property',
                      style: theme.textTheme.titleMedium),
                ),
                Text(
                  outstanding == 0 ? 'All confirmed' : '$outstanding to confirm',
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            for (final HouseholdService service in services) ...<Widget>[
              ProviderConfirmCard(service: service),
              const SizedBox(height: 12),
            ],
            TextButton.icon(
              onPressed: _addService,
              icon: const Icon(Icons.add),
              label: const Text('Add another service'),
            ),
            const SizedBox(height: 8),
            const NoticeBanner(
              tone: NoticeTone.warning,
              icon: Icons.fact_check_outlined,
              message: 'Confirmation of a provider does not confirm an account, '
                  'a bill amount or a payment date. HomeLedger never invents '
                  'those from an address.',
            ),
            const SizedBox(height: 8),
            const HonestyExpander(
              points: <String>[
                'A postcode can identify a water company and a local council. '
                    'It cannot identify your electricity or gas supplier.',
                'Council tax band is public. Your balance and instalment dates '
                    'are not: they come from the council or a bill.',
                'Broadband, insurance and TV Licence are choices or private '
                    'arrangements, not property facts.',
                'Amounts and dates appear only when you add them from a bill, '
                    'a statement or a provider account.',
              ],
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _finish,
              child: Text(widget.isOnboarding ? 'Finish setup' : 'Back to home'),
            ),
            if (widget.isOnboarding) ...<Widget>[
              const SizedBox(height: 8),
              Center(
                child: Text(
                  'You can change any of this later. Nothing is treated as '
                  'confirmed until you say it is.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _AddressCard extends StatelessWidget {
  const _AddressCard({required this.property, required this.onChangeAddress});

  final Property property;
  final VoidCallback onChangeAddress;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return SectionCard(
      title: 'My home',
      subtitle: property.addressSource,
      action: IconButton(
        tooltip: 'Change address',
        onPressed: onChangeAddress,
        icon: const Icon(Icons.edit_location_alt_outlined),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(property.displayAddress, style: theme.textTheme.bodyLarge),
          const SizedBox(height: 6),
          Text(
            <String>[
              property.tenure.label,
              if (property.uprn != null) 'UPRN ${property.uprn}',
              if (property.uprn == null) 'No property identifier',
            ].join(' · '),
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}
