import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../data/store.dart';
import '../../../domain/bill.dart';
import '../../../domain/enums.dart';
import '../../../domain/field.dart';
import '../../../theme.dart';
import '../../scope.dart';
import '../../widgets/form_fields.dart';
import '../../widgets/layout.dart';

/// Manual bill entry, and the edit form for an existing bill.
///
/// Deliberately allows "amount known, date not known": that is the honest state
/// for a lot of bills, and the dashboard handles it instead of making a date up.
class AddBillScreen extends StatefulWidget {
  const AddBillScreen({super.key, this.editBill, this.prefillKind});

  final Bill? editBill;
  final ServiceKind? prefillKind;

  bool get isEditing => editBill != null;

  @override
  State<AddBillScreen> createState() => _AddBillScreenState();
}

class _AddBillScreenState extends State<AddBillScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _provider = TextEditingController();
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _notes = TextEditingController();

  late ServiceKind _kind;
  late PaymentFrequency _frequency;
  DateTime? _dueDate;
  bool _dateKnown = true;
  bool _isEstimate = false;

  @override
  void initState() {
    super.initState();
    final Bill? existing = widget.editBill;
    _kind = existing?.kind ?? widget.prefillKind ?? ServiceKind.electricity;
    _frequency = existing?.frequency ?? PaymentFrequency.monthly;
    _dueDate = existing?.dueDate.value;
    _dateKnown = existing == null || existing.dueDate.hasValue;
    _isEstimate = existing?.isEstimate ?? false;
    _provider.text = existing?.provider.value ?? '';
    _notes.text = existing?.notes ?? '';
    if (existing?.amountMinor.value != null) {
      _amount.text = (existing!.amountMinor.value! / 100).toStringAsFixed(2);
    }
  }

  @override
  void dispose() {
    _provider.dispose();
    _amount.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_formKey.currentState?.validate() != true) return;
    if (_dateKnown && _dueDate == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Pick the payment date, or mark it as unknown.')),
      );
      return;
    }

    final int? minor = parseMoneyToMinor(_amount.text);
    if (minor == null) return;

    final AppStore store = MoveInScope.read(context);
    final String provider = _provider.text.trim();

    final Field<String> providerField = provider.isEmpty
        ? const Field<String>.missing()
        : Field<String>.confirmed(
            provider,
            source: widget.editBill?.provider.source ?? FieldSource.userEntered,
          );
    final Field<int> amountField = Field<int>.confirmed(
      minor,
      source: _isEstimate ? FieldSource.estimate : FieldSource.userEntered,
    );
    final Field<DateTime> dueField = _dateKnown && _dueDate != null
        ? Field<DateTime>.confirmed(_dueDate!)
        : const Field<DateTime>.missing();

    final Bill? existing = widget.editBill;
    if (existing != null) {
      await store.updateBill(
        existing.copyWith(
          provider: providerField,
          amountMinor: amountField,
          dueDate: dueField,
          frequency: _frequency,
          notes: _notes.text.trim().isEmpty ? null : _notes.text.trim(),
        ),
      );
    } else {
      await store.addBill(
        Bill(
          id: 'bill-${DateTime.now().microsecondsSinceEpoch}',
          propertyId: store.data.property?.id ?? 'unknown',
          kind: _kind,
          provider: providerField,
          amountMinor: amountField,
          dueDate: dueField,
          frequency: _frequency,
          notes: _notes.text.trim().isEmpty ? null : _notes.text.trim(),
        ),
      );
    }

    // Keep the service slot aligned with the latest confirmed bill.
    if (!_isEstimate) {
      if (provider.isNotEmpty) {
        await store.setProviderManually(_kind, provider);
      }
      await store.setServiceAmount(
        _kind,
        amountMinor: minor,
        frequency: _frequency,
      );
      if (_dateKnown && _dueDate != null) {
        await store.setServiceDueDate(_kind, _dueDate!);
      }
    }

    if (!mounted) return;
    final ScaffoldMessengerState messenger = ScaffoldMessenger.of(context);
    Navigator.of(context).pop();
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          widget.isEditing
              ? 'Bill updated.'
              : '${_kind.label} bill of ${formatMinor(minor)} recorded.',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool canEdit = MoveInScope.of(context).data.canEditBills;

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.isEditing ? 'Edit bill' : 'Record a bill'),
      ),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
            children: <Widget>[
              if (!canEdit)
                const Padding(
                  padding: EdgeInsets.only(bottom: 12),
                  child: NoticeBanner(
                    tone: NoticeTone.warning,
                    message: 'Your household role is view-only, so bills cannot '
                        'be changed. Ask the household owner for access.',
                  ),
                ),
              const NoticeBanner(
                message: 'Record what a bill or statement actually says. If you '
                    'do not know the payment date, say so — the dashboard will '
                    'show the bill as needing details rather than invent one.',
              ),
              const SizedBox(height: 16),
              _ServicePicker(
                value: _kind,
                onChanged: (ServiceKind next) => setState(() => _kind = next),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _provider,
                textCapitalization: TextCapitalization.words,
                decoration: appInputDecoration(
                  context,
                  labelText: 'Provider (optional)',
                  prefixIcon: Icons.business_outlined,
                ),
              ),
              const SizedBox(height: 12),
              MoneyField(
                controller: _amount,
                label: 'Amount',
                helper: 'The total on the bill you are recording.',
              ),
              const SizedBox(height: 12),
              FrequencySelector(
                value: _frequency,
                onChanged: (PaymentFrequency next) =>
                    setState(() => _frequency = next),
                includeOneOff: true,
              ),
              const SizedBox(height: 12),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: _dateKnown,
                onChanged: (bool value) => setState(() => _dateKnown = value),
                title: const Text('I know the payment date'),
                subtitle: const Text(
                  'Turn this off if the bill does not show a date yet.',
                ),
              ),
              if (_dateKnown) ...<Widget>[
                DatePickerField(
                  label: 'Payment due date',
                  value: _dueDate,
                  helper: 'Reminders use this date and nothing else.',
                  onChanged: (DateTime next) =>
                      setState(() => _dueDate = next),
                ),
              ],
              const SizedBox(height: 8),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: _isEstimate,
                onChanged: (bool value) => setState(() => _isEstimate = value),
                title: const Text('This is an estimate'),
                subtitle: const Text(
                  'Estimates are shown but never counted in totals or treated as '
                  'money you owe.',
                ),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _notes,
                maxLines: 3,
                decoration: appInputDecoration(
                  context,
                  labelText: 'Notes (optional)',
                  hintText: 'e.g. "Direct debit, first payment after move-in"',
                ),
              ),
              const SizedBox(height: 16),
              if (_isEstimate)
                const Padding(
                  padding: EdgeInsets.only(bottom: 12),
                  child: NoticeBanner(
                    tone: NoticeTone.attention,
                    icon: Icons.trending_up,
                    message: 'Marked as an estimate. It will appear on the '
                        'dashboard as a forecast and will not change "still to '
                        'pay" or your monthly total.',
                  ),
                ),
              FilledButton(
                onPressed: canEdit ? _save : null,
                child: Text(widget.isEditing ? 'Save changes' : 'Save bill'),
              ),
              const SizedBox(height: 8),
              Center(
                child: Text(
                  'Saved as entered by you. Source and date are kept with every '
                  'value.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ServicePicker extends StatelessWidget {
  const _ServicePicker({required this.value, required this.onChanged});

  final ServiceKind value;
  final ValueChanged<ServiceKind> onChanged;

  @override
  Widget build(BuildContext context) {
    return InputDecorator(
      decoration: appInputDecoration(
        context,
        labelText: 'Service',
        prefixIcon: Icons.receipt_long_outlined,
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<ServiceKind>(
          value: value,
          isExpanded: true,
          isDense: true,
          items: ServiceKind.values
              .map(
                (ServiceKind kind) => DropdownMenuItem<ServiceKind>(
                  value: kind,
                  child: Text(kind.label),
                ),
              )
              .toList(),
          onChanged: (ServiceKind? next) {
            if (next != null) onChanged(next);
          },
        ),
      ),
    );
  }
}
