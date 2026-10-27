import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../domain/enums.dart';
import '../../../domain/household_service.dart';
import '../../../data/store.dart';
import '../../scope.dart';
import '../../widgets/form_fields.dart';
import '../../widgets/layout.dart';
import '../../../theme.dart';

/// Collects the account-specific facts that an address can never provide:
/// amount, frequency, payment date and account number.
///
/// Every saved value is recorded as [FieldSource.userEntered], so it is clearly
/// the resident's own statement rather than something the app inferred.
Future<bool> showServiceDetailsSheet(
  BuildContext context, {
  required ServiceKind kind,
}) async {
  // Capture the current values before pushing the sheet route; the sheet builds
  // in its own route, so it starts from a snapshot rather than rebuilding
  // underneath the resident's typing.
  final AppStore store = MoveInScope.read(context);
  final HouseholdService? service = store.data.serviceFor(kind);

  final bool? saved = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (BuildContext sheetContext) => _ServiceDetailsForm(
      kind: kind,
      service: service,
      initialProvider: service?.provider.value ?? '',
    ),
  );
  return saved ?? false;
}

class _ServiceDetailsForm extends StatefulWidget {
  const _ServiceDetailsForm({
    required this.kind,
    required this.service,
    required this.initialProvider,
  });

  final ServiceKind kind;
  final HouseholdService? service;
  final String initialProvider;

  @override
  State<_ServiceDetailsForm> createState() => _ServiceDetailsFormState();
}

class _ServiceDetailsFormState extends State<_ServiceDetailsForm> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  late final TextEditingController _provider =
      TextEditingController(text: widget.initialProvider);
  late final TextEditingController _account = TextEditingController(
    text: widget.service?.accountNumber.value ?? '',
  );
  late final TextEditingController _amount = TextEditingController(
    text: widget.service?.amountMinor.value == null
        ? ''
        : (widget.service!.amountMinor.value! / 100).toStringAsFixed(2),
  );

  late PaymentFrequency _frequency =
      widget.service?.frequency ?? PaymentFrequency.monthly;
  late DateTime? _dueDate = widget.service?.nextDueDate.value;
  bool _saving = false;

  @override
  void dispose() {
    _provider.dispose();
    _account.dispose();
    _amount.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_formKey.currentState?.validate() != true) return;
    setState(() => _saving = true);

    final AppStore store = MoveInScope.read(context);
    final String provider = _provider.text.trim();
    if (provider.isNotEmpty) {
      await store.setProviderManually(widget.kind, provider);
    }
    final String account = _account.text.trim();
    if (account.isNotEmpty) {
      await store.setAccountNumber(widget.kind, account);
    }
    final int? minor = parseMoneyToMinor(_amount.text);
    if (minor != null && minor > 0) {
      await store.setServiceAmount(
        widget.kind,
        amountMinor: minor,
        frequency: _frequency,
      );
    }
    if (_dueDate != null) {
      await store.setServiceDueDate(widget.kind, _dueDate!);
    }

    if (!mounted) return;
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);

    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  '${widget.kind.label} details',
                  style: theme.textTheme.titleMedium,
                ),
                const SizedBox(height: 4),
                Text(
                  'Enter only what you can see on a bill, a statement or your '
                  'provider account.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _provider,
                  textCapitalization: TextCapitalization.words,
                  decoration: appInputDecoration(
                    context,
                    labelText: 'Provider name',
                    prefixIcon: Icons.business_outlined,
                  ),
                ),
                const SizedBox(height: 12),
                MoneyField(
                  controller: _amount,
                  label: 'Amount you pay',
                  helper: 'Use the total on your most recent bill. Leave blank '
                      'if you only know the provider or the date.',
                  validator: (String? value) {
                    if (value == null || value.trim().isEmpty) return null;
                    final int? minor = parseMoneyToMinor(value);
                    if (minor == null || minor <= 0) {
                      return 'Enter an amount, for example 92.50';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 12),
                FrequencySelector(
                  value: _frequency,
                  onChanged: (PaymentFrequency next) =>
                      setState(() => _frequency = next),
                ),
                const SizedBox(height: 12),
                DatePickerField(
                  label: 'Next payment date',
                  value: _dueDate,
                  helper: 'Leave unset if you do not know it. The app will ask '
                      'rather than guess.',
                  onChanged: (DateTime next) => setState(() => _dueDate = next),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _account,
                  decoration: appInputDecoration(
                    context,
                    labelText: 'Account number (optional)',
                    prefixIcon: Icons.tag,
                  ),
                ),
                const SizedBox(height: 16),
                const NoticeBanner(
                  message: 'Confirmation of a provider does not confirm an '
                      'account, an amount or a payment date. Each of these is '
                      'stored separately, with its own source.',
                ),
                const SizedBox(height: 16),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () => Navigator.of(context).pop(false),
                        child: const Text('Cancel'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: FilledButton(
                        onPressed: _saving ? null : _save,
                        child: _saving
                            ? const SizedBox(
                                height: 18,
                                width: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Text('Save details'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
