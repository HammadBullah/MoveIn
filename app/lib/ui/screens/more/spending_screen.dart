import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../domain/bill.dart';
import '../../../domain/enums.dart';
import '../../../domain/household_summary.dart';
import '../../../theme.dart';
import '../../scope.dart';
import '../../widgets/layout.dart';

/// Recorded spending by month.
///
/// Estimates are excluded, and a bill counts in the month it is due, so the
/// figures reconcile with the bills list rather than drifting.
class SpendingScreen extends StatelessWidget {
  const SpendingScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final store = MoveInScope.of(context);
    final List<MonthlySpend> months =
        monthlySpend(store.data.bills, months: 12);
    final bool canSee = store.data.canSeeAmounts;

    final int total = months.fold(
      0,
      (int sum, MonthlySpend month) => sum + month.totalMinor,
    );
    final int max = months.fold(
      0,
      (int value, MonthlySpend month) =>
          month.totalMinor > value ? month.totalMinor : value,
    );

    final Map<ServiceKind, int> byKind = <ServiceKind, int>{};
    for (final Bill bill in store.data.bills) {
      if (bill.isEstimate || !bill.amountMinor.isConfirmed) continue;
      byKind[bill.kind] =
          (byKind[bill.kind] ?? 0) + (bill.amountMinor.value ?? 0);
    }
    final List<MapEntry<ServiceKind, int>> ranked = byKind.entries.toList()
      ..sort((MapEntry<ServiceKind, int> a, MapEntry<ServiceKind, int> b) =>
          b.value.compareTo(a.value));
    final int kindTotal = ranked.fold(
      0,
      (int sum, MapEntry<ServiceKind, int> entry) => sum + entry.value,
    );

    return Scaffold(
      appBar: AppBar(title: const Text('Spending')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
          children: <Widget>[
            AppCard(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'Recorded bills, last 12 months',
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    canSee ? formatMinor(total) : '••••',
                    style: theme.textTheme.headlineMedium?.merge(moneyStyle),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Confirmed amounts only. Estimates are never included.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            if (months.isEmpty)
              const EmptyState(
                icon: Icons.insights_outlined,
                title: 'No spending recorded yet',
                message: 'Add a bill with an amount and it will show up here, '
                    'grouped by month.',
              )
            else ...<Widget>[
              Text('By month', style: theme.textTheme.titleSmall),
              const SizedBox(height: 8),
              AppCard(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: <Widget>[
                    for (final MonthlySpend month in months)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        child: Row(
                          children: <Widget>[
                            SizedBox(
                              width: 74,
                              child: Text(
                                formatMonthYear(month.month),
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ),
                            Expanded(
                              child: ClipRRect(
                                borderRadius: BorderRadius.circular(4),
                                child: LinearProgressIndicator(
                                  value: max == 0
                                      ? 0
                                      : month.totalMinor / max,
                                  minHeight: 8,
                                  backgroundColor:
                                      theme.colorScheme.surfaceContainerHighest,
                                ),
                              ),
                            ),
                            const SizedBox(width: 10),
                            SizedBox(
                              width: 78,
                              child: Text(
                                canSee ? formatMinor(month.totalMinor) : '••••',
                                textAlign: TextAlign.right,
                                style: theme.textTheme.bodySmall
                                    ?.merge(moneyStyle),
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 16),
            if (ranked.isNotEmpty) ...<Widget>[
              Text('By service', style: theme.textTheme.titleSmall),
              const SizedBox(height: 8),
              AppCard(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: <Widget>[
                    for (final MapEntry<ServiceKind, int> entry in ranked)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 5),
                        child: Row(
                          children: <Widget>[
                            Icon(iconForServiceName(entry.key.name), size: 16),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                entry.key.label,
                                style: theme.textTheme.bodyMedium,
                              ),
                            ),
                            Text(
                              canSee
                                  ? '${formatMinor(entry.value)}  ·  '
                                      '${kindTotal == 0 ? 0 : (entry.value * 100 / kindTotal).round()}%'
                                  : '••••',
                              style: theme.textTheme.bodySmall?.merge(moneyStyle),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 16),
            Text(
              'Totals count each recorded bill in the month its payment is due. '
              'Bills without a confirmed amount or with an estimated amount are '
              'left out, which is why this can be lower than what you actually '
              'pay.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
                height: 1.35,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
