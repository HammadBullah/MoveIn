import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../data/store.dart';
import '../../../domain/enums.dart';
import '../../../domain/household_service.dart';
import '../../../theme.dart';
import '../../scope.dart';
import '../../widgets/layout.dart';
import '../../widgets/provenance.dart';
import '../bills/read_bill_screen.dart';
import '../lookup/lookup_sheet.dart';
import 'service_details_sheet.dart';

/// One service slot on the confirmation screen.
///
/// The card always answers three questions separately:
///   1. is there a provider, and where did we get it from?
///   2. has the resident confirmed it?
///   3. do we have an account, an amount and a payment date?
class ProviderConfirmCard extends StatelessWidget {
  const ProviderConfirmCard({super.key, required this.service});

  final HouseholdService service;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final AppStore store = MoveInScope.read(context);

    final bool isSuggested = service.provider.needsConfirmation;
    final bool isConfirmed = service.provider.isConfirmed;

    return AppCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: scheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(iconForServiceName(service.kind.name), size: 18),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(service.kind.label, style: theme.textTheme.titleMedium),
              ),
              StatusPill(
                label: service.readiness.label,
                tone: switch (service.readiness) {
                  ServiceReadiness.ready => StatusTone.positive,
                  ServiceReadiness.needsConfirmation => StatusTone.warning,
                  ServiceReadiness.needsDetails => StatusTone.attention,
                  ServiceReadiness.notFound => StatusTone.neutral,
                },
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            service.provider.value ?? 'Provider not confirmed',
            style: theme.textTheme.bodyLarge?.copyWith(
              fontWeight: isConfirmed ? FontWeight.w600 : FontWeight.w500,
              color: service.provider.value == null
                  ? theme.colorScheme.onSurfaceVariant
                  : null,
            ),
          ),
          const SizedBox(height: 6),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              ProvenanceBadge(field: service.provider, compact: true),
              if (service.provider.note != null) ...<Widget>[
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    service.provider.note!,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                      height: 1.3,
                    ),
                  ),
                ),
              ],
            ],
          ),
          if (isSuggested) ...<Widget>[
            const SizedBox(height: 12),
            Text(
              'Is this the provider for your property?',
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: <Widget>[
                FilledButton.tonalIcon(
                  onPressed: () async {
                    await store.confirmProvider(service.kind);
                    if (context.mounted) {
                      _snack(context, '${service.kind.label} provider confirmed.');
                    }
                  },
                  icon: const Icon(Icons.check, size: 18),
                  label: const Text('Yes, this is correct'),
                ),
                OutlinedButton.icon(
                  onPressed: () async {
                    await store.rejectProvider(service.kind);
                    if (context.mounted) {
                      _snack(
                        context,
                        'Thanks — removed. Enter the provider yourself or use '
                        'the official lookup.',
                      );
                    }
                  },
                  icon: const Icon(Icons.close, size: 18),
                  label: const Text('No, not correct'),
                ),
                TextButton(
                  onPressed: () => _snack(
                    context,
                    'Kept as a suggestion. It stays marked as unconfirmed until '
                    'you say it is right.',
                  ),
                  child: const Text("I'm not sure yet"),
                ),
              ],
            ),
          ],
          if (!isSuggested && !isConfirmed) ...<Widget>[
            const SizedBox(height: 12),
            Text(
              'An address cannot tell us who supplies this. Use the official '
              'lookup, add a bill, or type the provider in.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: scheme.onSurfaceVariant,
                height: 1.3,
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: <Widget>[
                OutlinedButton.icon(
                  onPressed: () => showLookupSheet(
                    context,
                    title: 'Find your ${service.kind.label.toLowerCase()} provider',
                    keys: service.lookupKeys.isEmpty
                        ? AppStore.lookupKeysFor(service.kind)
                        : service.lookupKeys,
                    kind: service.kind,
                  ),
                  icon: const Icon(Icons.search, size: 18),
                  label: const Text('Find provider'),
                ),
                OutlinedButton.icon(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => ReadBillScreen(prefillKind: service.kind),
                    ),
                  ),
                  icon: const Icon(Icons.upload_file, size: 18),
                  label: const Text('Add a bill'),
                ),
                TextButton(
                  onPressed: () => _enterManually(context, store),
                  child: const Text('Type it in'),
                ),
              ],
            ),
          ],
          if (isConfirmed) ...<Widget>[
            const SizedBox(height: 12),
            const Divider(),
            const SizedBox(height: 4),
            FieldRow(
              label: 'Account number',
              field: service.accountNumber,
            ),
            FieldRow(
              label: 'Amount',
              field: service.amountMinor,
              valueBuilder: (Object? value) => value is int
                  ? '${formatMinor(value)} · ${service.frequency.label.toLowerCase()}'
                  : '—',
            ),
            FieldRow(
              label: 'Next payment',
              field: service.nextDueDate,
              valueBuilder: (Object? value) =>
                  value is DateTime ? formatDateLong(value) : '—',
            ),
            const SizedBox(height: 8),
            Row(
              children: <Widget>[
                OutlinedButton.icon(
                  onPressed: () => showServiceDetailsSheet(
                    context,
                    kind: service.kind,
                  ),
                  icon: const Icon(Icons.edit_outlined, size: 18),
                  label: Text(
                    service.readiness == ServiceReadiness.ready
                        ? 'Edit details'
                        : 'Add account details',
                  ),
                ),
                const SizedBox(width: 8),
                TextButton.icon(
                  onPressed: () => showLookupSheet(
                    context,
                    title: 'Official lookup',
                    keys: service.lookupKeys,
                    kind: service.kind,
                  ),
                  icon: const Icon(Icons.open_in_new, size: 16),
                  label: const Text('Lookup'),
                ),
              ],
            ),
          ],
          if (service.readiness == ServiceReadiness.needsDetails) ...<Widget>[
            const SizedBox(height: 10),
            NoticeBanner(
              tone: NoticeTone.attention,
              message: service.amountMinor.value == null
                  ? 'Provider confirmed. The amount you pay and the payment '
                      'date are still unknown — add them from a bill.'
                  : 'Amount recorded, but the payment date is not. Reminders '
                      'stay off until you add a date.',
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _enterManually(BuildContext context, AppStore store) async {
    final String? name = await showDialog<String>(
      context: context,
      builder: (BuildContext context) => _ManualProviderDialog(
        kind: service.kind,
      ),
    );
    if (name == null || name.trim().isEmpty) return;
    await store.setProviderManually(service.kind, name);
    if (context.mounted) {
      _snack(context, 'Saved as entered by you — not a full confirmation of '
          'your account or bills.');
    }
  }

  static void _snack(BuildContext context, String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }
}

class _ManualProviderDialog extends StatefulWidget {
  const _ManualProviderDialog({required this.kind});

  final ServiceKind kind;

  @override
  State<_ManualProviderDialog> createState() => _ManualProviderDialogState();
}

class _ManualProviderDialogState extends State<_ManualProviderDialog> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('${widget.kind.label} provider'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          TextField(
            controller: _controller,
            autofocus: true,
            textCapitalization: TextCapitalization.words,
            decoration: appInputDecoration(
              context,
              labelText: 'Provider name',
              hintText: 'As printed on your bill',
            ),
          ),
          const SizedBox(height: 12),
          const NoticeBanner(
            message: 'Type the name exactly as it appears on a bill or '
                'statement. This records a provider, not a bill amount.',
          ),
        ],
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(_controller.text),
          child: const Text('Save'),
        ),
      ],
    );
  }
}
