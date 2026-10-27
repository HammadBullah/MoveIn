import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../data/extraction/bill_text_parser.dart';
import '../../../data/store.dart';
import '../../../domain/bill.dart';
import '../../../domain/document.dart';
import '../../../domain/enums.dart';
import '../../../theme.dart';
import '../../scope.dart';
import '../../widgets/form_fields.dart';
import '../../widgets/layout.dart';
import '../../widgets/provenance.dart';

/// Read a bill and confirm every field before it is saved.
///
/// In this build the "document" is text the resident pastes or types. When real
/// uploads land, OCR produces the same text and this screen does not change:
/// [BillTextParser] is the seam.
class ReadBillScreen extends StatefulWidget {
  const ReadBillScreen({super.key, this.prefillKind});

  final ServiceKind? prefillKind;

  @override
  State<ReadBillScreen> createState() => _ReadBillScreenState();
}

class _ReadBillScreenState extends State<ReadBillScreen> {
  final TextEditingController _text = TextEditingController();
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  late ServiceKind _kind = widget.prefillKind ?? ServiceKind.electricity;

  ExtractedBill? _extracted;
  bool _reading = false;

  // Values under review. They start from the extraction and the resident can
  // overwrite any of them before saving.
  final TextEditingController _provider = TextEditingController();
  final TextEditingController _amount = TextEditingController();
  DateTime? _dueDate;
  PaymentFrequency _frequency = PaymentFrequency.monthly;
  bool _saving = false;

  @override
  void dispose() {
    _text.dispose();
    _provider.dispose();
    _amount.dispose();
    super.dispose();
  }

  void _read() {
    final String raw = _text.text.trim();
    if (raw.length < 20) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Paste a bit more of the bill so the fields can be found.'),
        ),
      );
      return;
    }

    setState(() {
      _reading = true;
      _extracted = null;
    });

    final ExtractedBill extracted = BillTextParser.parse(
      raw,
      hintedKind: _kind,
      now: DateTime.now(),
    );
    final ServiceKind? detected = extracted.kind;

    setState(() {
      _reading = false;
      _extracted = extracted;
      _provider.text = extracted.provider.value ?? '';
      _amount.text = extracted.amountMinor.value == null
          ? ''
          : (extracted.amountMinor.value! / 100).toStringAsFixed(2);
      _dueDate = extracted.dueDate.value;
      _frequency = extracted.frequency ?? PaymentFrequency.monthly;
      if (detected != null) _kind = detected;
    });
  }

  Future<void> _save() async {
    if (_formKey.currentState?.validate() != true) {
      return;
    }
    final int? minor = parseMoneyToMinor(_amount.text);
    if (minor == null || _dueDate == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('An amount and a payment date are needed.')),
      );
      return;
    }

    setState(() => _saving = true);
    final AppStore store = MoveInScope.read(context);
    final String provider = _provider.text.trim();

    final DocumentRecord document = await store.addDocument(
      kind: DocumentKind.bill,
      title: '${_kind.label} bill',
      providerName: provider.isEmpty ? null : provider,
      extractedText: _text.text.trim(),
      notes: 'Captured from bill text. Fields confirmed by the resident.',
    );

    final Bill bill = await store.recordBill(
      kind: _kind,
      amountMinor: minor,
      dueDate: _dueDate!,
      providerName: provider.isEmpty ? null : provider,
      frequency: _frequency,
      documentId: document.id,
    );

    // Keep the service slot in step with what was just confirmed.
    if (provider.isNotEmpty) {
      await store.setProviderManually(_kind, provider);
    }
    await store.setServiceAmount(
      _kind,
      amountMinor: minor,
      frequency: _frequency,
    );
    await store.setServiceDueDate(_kind, _dueDate!);

    if (!mounted) return;
    final ScaffoldMessengerState messenger = ScaffoldMessenger.of(context);
    Navigator.of(context).pop();
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          'Saved ${_kind.label.toLowerCase()} bill of ${formatMinor(minor)} '
          'due ${formatDateCompact(bill.dueDate.value!)}.',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ExtractedBill? extracted = _extracted;

    return Scaffold(
      appBar: AppBar(title: const Text('Add a bill')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
          children: <Widget>[
            const NoticeBanner(
              icon: Icons.document_scanner_outlined,
              message: 'This build reads text you paste or type, so the whole '
                  'flow can be tested offline. File upload and OCR drop in at '
                  'the same place: the text is parsed, then you confirm every '
                  'field before it is saved.',
            ),
            const SizedBox(height: 16),
            _ServiceKindPicker(
              value: _kind,
              onChanged: (ServiceKind next) => setState(() => _kind = next),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _text,
              minLines: 8,
              maxLines: 16,
              keyboardType: TextInputType.multiline,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 13),
              decoration: appInputDecoration(
                context,
                labelText: 'Bill text',
                hintText: 'Paste the text from your bill or statement.\n\n'
                    'Example:\nOctopus Energy\nAmount due: £92.50\n'
                    'Payment due date: 28/10/2026\nMonthly direct debit',
              ),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: _reading ? null : _read,
              icon: const Icon(Icons.manage_search),
              label: Text(_reading ? 'Reading…' : 'Find the fields'),
            ),
            if (extracted != null) ...<Widget>[
              const SizedBox(height: 24),
              Text('Confirm what was found', style: theme.textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(
                'Nothing is saved until you press Save. Each value is recorded '
                'as read from a bill and confirmed by you.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 12),
              if (extracted.warnings.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: NoticeBanner(
                    tone: NoticeTone.warning,
                    icon: Icons.warning_amber_outlined,
                    message: extracted.warnings.join('\n'),
                  ),
                ),
              Form(
                key: _formKey,
                child: Column(
                  children: <Widget>[
                    TextFormField(
                      controller: _provider,
                      textCapitalization: TextCapitalization.words,
                      decoration: appInputDecoration(
                        context,
                        labelText: 'Provider',
                        prefixIcon: Icons.business_outlined,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: ProvenanceBadge(field: extracted.provider),
                    ),
                    const SizedBox(height: 16),
                    MoneyField(
                      controller: _amount,
                      label: 'Amount on this bill',
                      helper: 'The total the provider is asking for.',
                    ),
                    const SizedBox(height: 6),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: ProvenanceBadge(field: extracted.amountMinor),
                    ),
                    const SizedBox(height: 16),
                    DatePickerField(
                      label: 'Payment due date',
                      value: _dueDate,
                      helper: 'Used for reminders. Never guessed.',
                      onChanged: (DateTime next) =>
                          setState(() => _dueDate = next),
                    ),
                    const SizedBox(height: 6),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: ProvenanceBadge(field: extracted.dueDate),
                    ),
                    const SizedBox(height: 16),
                    FrequencySelector(
                      value: _frequency,
                      onChanged: (PaymentFrequency next) =>
                          setState(() => _frequency = next),
                    ),
                    const SizedBox(height: 20),
                    Row(
                      children: <Widget>[
                        Expanded(
                          child: OutlinedButton(
                            onPressed: () => setState(() {
                              _extracted = null;
                              _provider.clear();
                              _amount.clear();
                              _dueDate = null;
                            }),
                            child: const Text('Start again'),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: FilledButton(
                            onPressed: _saving ? null : _save,
                            child: Text(_saving ? 'Saving…' : 'Save bill'),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ServiceKindPicker extends StatelessWidget {
  const _ServiceKindPicker({required this.value, required this.onChanged});

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
