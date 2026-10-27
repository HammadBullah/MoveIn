import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/format.dart';
import '../../domain/enums.dart';
import '../../theme.dart';

/// A tappable field that opens the platform date picker and shows the chosen
/// date in the app's long format.
class DatePickerField extends StatelessWidget {
  const DatePickerField({
    super.key,
    required this.label,
    required this.value,
    required this.onChanged,
    this.helper,
    this.firstDate,
    this.lastDate,
    this.errorText,
  });

  final String label;
  final DateTime? value;
  final ValueChanged<DateTime> onChanged;
  final String? helper;
  final DateTime? firstDate;
  final DateTime? lastDate;
  final String? errorText;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () async {
        final DateTime now = today();
        final DateTime initial = value ?? now;
        final DateTime first = firstDate ?? DateTime(now.year - 5);
        final DateTime last = lastDate ?? DateTime(now.year + 5);
        final DateTime? picked = await showDatePicker(
          context: context,
          initialDate: initial.isBefore(first) ? first : initial,
          firstDate: first,
          lastDate: last,
          helpText: label,
        );
        if (picked != null) onChanged(picked);
      },
      child: InputDecorator(
        decoration: appInputDecoration(
          context,
          labelText: label,
          helperText: helper,
          errorText: errorText,
          prefixIcon: Icons.event_outlined,
        ),
        child: Text(
          value == null ? 'Not set' : formatDateLong(value!),
          style: theme.textTheme.bodyMedium?.copyWith(
            color: value == null ? theme.colorScheme.onSurfaceVariant : null,
          ),
        ),
      ),
    );
  }
}

/// Money input that behaves itself: digits and one decimal point, stored as
/// integer pence.
class MoneyField extends StatelessWidget {
  const MoneyField({
    super.key,
    required this.controller,
    this.label = 'Amount',
    this.helper,
    this.validator,
    this.autofocus = false,
  });

  final TextEditingController controller;
  final String label;
  final String? helper;
  final String? Function(String?)? validator;
  final bool autofocus;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      autofocus: autofocus,
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      inputFormatters: <TextInputFormatter>[
        FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
      ],
      decoration: appInputDecoration(
        context,
        labelText: label,
        helperText: helper,
        prefixText: '£ ',
        prefixIcon: Icons.payments_outlined,
      ),
      validator: validator ??
          (String? value) {
            final int? minor = parseMoneyToMinor(value ?? '');
            if (minor == null) return 'Enter an amount, for example 92.50';
            if (minor <= 0) return 'Amount must be more than zero';
            if (minor > 100000000) return 'That looks too large';
            return null;
          },
    );
  }
}

/// Frequency selector that reads clearly ("Every 2 weeks" not "fortnightly").
///
/// Hand-rolled on top of [DropdownButton] rather than
/// [DropdownButtonFormField], whose value parameter was renamed in a recent
/// Flutter release.
class FrequencySelector extends StatelessWidget {
  const FrequencySelector({
    super.key,
    required this.value,
    required this.onChanged,
    this.includeOneOff = false,
    this.label = 'How often is it charged?',
  });

  final PaymentFrequency value;
  final ValueChanged<PaymentFrequency> onChanged;
  final bool includeOneOff;
  final String label;

  static List<PaymentFrequency> options({bool includeOneOff = false}) {
    return PaymentFrequency.values
        .where((PaymentFrequency f) => includeOneOff || f != PaymentFrequency.oneOff)
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    return InputDecorator(
      decoration: appInputDecoration(
        context,
        labelText: label,
        prefixIcon: Icons.repeat,
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<PaymentFrequency>(
          value: value,
          isExpanded: true,
          isDense: true,
          items: options(includeOneOff: includeOneOff)
              .map(
                (PaymentFrequency frequency) => DropdownMenuItem<PaymentFrequency>(
                  value: frequency,
                  child: Text(frequency.label),
                ),
              )
              .toList(),
          onChanged: (PaymentFrequency? next) {
            if (next != null) onChanged(next);
          },
        ),
      ),
    );
  }
}
