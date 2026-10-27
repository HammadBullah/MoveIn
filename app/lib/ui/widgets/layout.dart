import 'package:flutter/material.dart';

import '../../domain/bill.dart';

/// The app's card. A thin wrapper over [Material] so the look is owned here
/// rather than through a `ThemeData` sub-theme (whose type name has moved
/// between Flutter releases).
class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.padding = EdgeInsets.zero,
    this.onTap,
  });

  final Widget child;
  final EdgeInsets padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final Widget content = Padding(padding: padding, child: child);

    return Material(
      color: theme.brightness == Brightness.light
          ? Colors.white
          : scheme.surfaceContainerHigh,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: scheme.outlineVariant),
      ),
      child: onTap == null
          ? content
          : InkWell(onTap: onTap, child: content),
    );
  }
}

class SectionCard extends StatelessWidget {
  const SectionCard({
    super.key,
    required this.child,
    this.title,
    this.subtitle,
    this.action,
    this.padding = const EdgeInsets.all(16),
  });

  final Widget child;
  final String? title;
  final String? subtitle;
  final Widget? action;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AppCard(
      child: Padding(
        padding: padding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            if (title != null)
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(title!, style: theme.textTheme.titleMedium),
                        if (subtitle != null) ...<Widget>[
                          const SizedBox(height: 2),
                          Text(
                            subtitle!,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  if (action != null) action!,
                ],
              ),
            if (title != null) const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }
}

/// A deliberately visible explanation of what the app does *not* know.
class NoticeBanner extends StatelessWidget {
  const NoticeBanner({
    super.key,
    required this.message,
    this.icon = Icons.info_outline,
    this.tone = NoticeTone.info,
    this.action,
  });

  final String message;
  final IconData icon;
  final NoticeTone tone;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final (Color bg, Color fg) = switch (tone) {
      NoticeTone.info => (scheme.surfaceContainerHighest, scheme.onSurfaceVariant),
      NoticeTone.warning => (scheme.secondaryContainer, scheme.onSecondaryContainer),
      NoticeTone.attention => (scheme.tertiaryContainer, scheme.onTertiaryContainer),
      NoticeTone.positive => (scheme.primaryContainer, scheme.onPrimaryContainer),
    };

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(icon, size: 18, color: fg),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  message,
                  style: theme.textTheme.bodySmall?.copyWith(color: fg, height: 1.35),
                ),
                if (action != null) ...<Widget>[const SizedBox(height: 6), action!],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

enum NoticeTone { info, warning, attention, positive }

class StatusPill extends StatelessWidget {
  const StatusPill({super.key, required this.label, required this.tone});

  factory StatusPill.forBill(BillState state) {
    return StatusPill(
      label: state.label,
      tone: switch (state) {
        BillState.paid => StatusTone.positive,
        BillState.overdue => StatusTone.danger,
        BillState.dueSoon => StatusTone.warning,
        BillState.upcoming => StatusTone.neutral,
        BillState.needsDetails => StatusTone.attention,
      },
    );
  }

  final String label;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final (Color bg, Color fg) = switch (tone) {
      StatusTone.positive => (scheme.primaryContainer, scheme.onPrimaryContainer),
      StatusTone.warning => (scheme.secondaryContainer, scheme.onSecondaryContainer),
      StatusTone.danger => (scheme.errorContainer, scheme.onErrorContainer),
      StatusTone.attention => (scheme.tertiaryContainer, scheme.onTertiaryContainer),
      StatusTone.neutral => (scheme.surfaceContainerHighest, scheme.onSurfaceVariant),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: fg,
              fontWeight: FontWeight.w600,
            ),
      ),
    );
  }
}

enum StatusTone { positive, warning, danger, attention, neutral }

class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.message,
    this.action,
  });

  final IconData icon;
  final String title;
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(icon, size: 40, color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(height: 12),
            Text(title, style: theme.textTheme.titleMedium, textAlign: TextAlign.center),
            const SizedBox(height: 6),
            Text(
              message,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
              textAlign: TextAlign.center,
            ),
            if (action != null) ...<Widget>[const SizedBox(height: 16), action!],
          ],
        ),
      ),
    );
  }
}

/// Small "What can't this do?" expander used on setup and dashboard.
class HonestyExpander extends StatelessWidget {
  const HonestyExpander({
    super.key,
    required this.points,
    this.title = 'What this screen cannot know',
  });

  final String title;
  final List<String> points;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: const EdgeInsets.only(bottom: 8),
      shape: const Border(),
      collapsedShape: const Border(),
      leading: Icon(
        Icons.visibility_outlined,
        size: 18,
        color: theme.colorScheme.onSurfaceVariant,
      ),
      title: Text(title, style: theme.textTheme.bodyMedium),
      children: points
          .map(
            (String point) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const Text('•  '),
                  Expanded(
                    child: Text(
                      point,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                        height: 1.35,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          )
          .toList(),
    );
  }
}

/// Shared confirmation dialog used before destructive actions.
Future<bool> confirmAction(
  BuildContext context, {
  required String title,
  required String message,
  String confirmLabel = 'Confirm',
  bool destructive = false,
}) async {
  final bool? result = await showDialog<bool>(
    context: context,
    builder: (BuildContext context) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          style: destructive
              ? FilledButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.error,
                  foregroundColor: Theme.of(context).colorScheme.onError,
                )
              : null,
          onPressed: () => Navigator.of(context).pop(true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
  return result ?? false;
}

/// Chip showing how a service slot is doing ("Provider needs confirming").
class ReadinessChip extends StatelessWidget {
  const ReadinessChip({super.key, required this.label, required this.tone});

  final String label;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) =>
      StatusPill(label: label, tone: tone);
}
