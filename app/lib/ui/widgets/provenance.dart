import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../domain/field.dart';

/// The little badge that tells the resident where a value came from.
///
/// This is the single most important widget in the app: it is what stops a
/// postcode guess looking like a confirmed bill.
class ProvenanceBadge extends StatelessWidget {
  const ProvenanceBadge({super.key, required this.field, this.compact = false});

  final Field<Object?> field;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;

    late final Color background;
    late final Color foreground;
    late final IconData icon;
    late final String text;

    if (!field.hasValue) {
      background = scheme.surfaceContainerHighest;
      foreground = scheme.onSurfaceVariant;
      icon = Icons.help_outline;
      text = 'Not recorded';
    } else if (field.source == FieldSource.estimate) {
      background = scheme.tertiaryContainer;
      foreground = scheme.onTertiaryContainer;
      icon = Icons.trending_up;
      text = 'Estimate';
    } else if (field.needsConfirmation) {
      background = scheme.secondaryContainer;
      foreground = scheme.onSecondaryContainer;
      icon = Icons.help_outline;
      text = 'Suggested · ${field.source.label.toLowerCase()}';
    } else {
      background = scheme.primaryContainer;
      foreground = scheme.onPrimaryContainer;
      icon = Icons.verified_outlined;
      text = field.source.label;
    }

    final Widget badge = Container(
      padding: EdgeInsets.symmetric(horizontal: compact ? 6 : 8, vertical: compact ? 2 : 4),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: compact ? 11 : 13, color: foreground),
          const SizedBox(width: 4),
          Text(
            text,
            style: theme.textTheme.labelSmall?.copyWith(
              color: foreground,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );

    if (field.note == null || field.note!.isEmpty) return badge;
    return Tooltip(message: field.note!, child: badge);
  }
}

/// "Amount  £92.50  [Entered by you]"
class FieldRow extends StatelessWidget {
  const FieldRow({
    super.key,
    required this.label,
    required this.field,
    this.valueBuilder,
    this.trailing,
  });

  final String label;
  final Field<Object?> field;
  final String Function(Object? value)? valueBuilder;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Object? value = field.value;
    final String text = value == null
        ? 'Not recorded'
        : (valueBuilder?.call(value) ?? value.toString());

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          SizedBox(
            width: 128,
            child: Text(
              label,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(text, style: theme.textTheme.bodyMedium),
                const SizedBox(height: 4),
                Row(
                  children: <Widget>[
                    ProvenanceBadge(field: field, compact: true),
                    if (field.note != null && field.note!.isNotEmpty) ...<Widget>[
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(
                          field.note!,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
          if (trailing != null) ...<Widget>[const SizedBox(width: 8), trailing!],
        ],
      ),
    );
  }
}

/// Helper so money fields read consistently.
Widget moneyField(Field<int> field, {bool withPence = true}) {
  return FieldRow(
    label: '',
    field: field,
    valueBuilder: (Object? value) =>
        formatMinor(value is int ? value : null, withPence: withPence),
  );
}
