import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../domain/bill.dart';
import '../../../domain/enums.dart';
import '../../../domain/household_service.dart';
import '../../../domain/household_summary.dart';
import '../../../domain/property.dart';
import '../../../theme.dart';
import '../../scope.dart';
import '../../widgets/bill_tile.dart';
import '../../widgets/layout.dart';
import '../bills/add_bill_screen.dart';
import '../bills/bill_detail_screen.dart';
import '../bills/read_bill_screen.dart';
import '../confirm/confirm_setup_screen.dart';
import '../more/spending_screen.dart';

/// After setup: what is due, what is missing, and nothing that was invented.
class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final store = MoveInScope.of(context);
    final DateTime now = today();
    final Property? property = store.data.property;
    final HouseholdSummary summary = HouseholdSummary.compute(store.data, now: now);
    final bool canSeeAmounts = store.data.canSeeAmounts;

    final List<Bill> realUpcoming = summary.upcoming
        .where((Bill bill) => !bill.isEstimate)
        .take(5)
        .toList();
    final List<Bill> estimates = summary.estimates;

    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () async {
            // Local-first for now; this is where a sync with the API will go.
            await Future<void>.delayed(const Duration(milliseconds: 300));
          },
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text('My Home', style: theme.textTheme.headlineSmall),
                        const SizedBox(height: 2),
                        Text(
                          '${formatMonthYear(now)} · '
                          '${property?.isDemoData == true ? 'Example household' : property?.shortAddress ?? 'Your household'}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: 'Household setup',
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => const ConfirmSetupScreen(),
                      ),
                    ),
                    icon: const Icon(Icons.tune),
                  ),
                ],
              ),
              if (property != null) ...<Widget>[
                const SizedBox(height: 4),
                Text(
                  property.displayAddress,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
              const SizedBox(height: 16),
              IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    Expanded(
                      child: _MetricCard(
                        label: 'Monthly bills',
                        value: summary.monthlyRecurringCount == 0
                            ? '—'
                            : canSeeAmounts
                                ? formatMinor(summary.monthlyRecurringMinor)
                                : '••••',
                        caption: summary.monthlyRecurringCount == 0
                            ? 'No recurring amounts recorded'
                            : '${summary.monthlyRecurringCount} recorded '
                                'recurring '
                                '${summary.monthlyRecurringCount == 1 ? 'cost' : 'costs'}',
                        icon: Icons.calendar_view_month,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _MetricCard(
                        label: 'Still to pay',
                        value: summary.stillToPayCount == 0
                            ? '—'
                            : canSeeAmounts
                                ? formatMinor(summary.stillToPayMinor)
                                : '••••',
                        caption: summary.stillToPayCount == 0
                            ? 'Nothing due in the next 30 days'
                            : '${summary.stillToPayCount} confirmed '
                                '${summary.stillToPayCount == 1 ? 'bill' : 'bills'} '
                                'due soon',
                        icon: Icons.schedule,
                        emphasise: summary.overdueCount > 0,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
              if (summary.attentionCount > 0) ...<Widget>[
                _AttentionSection(summary: summary),
                const SizedBox(height: 20),
              ],
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text('Upcoming payments',
                        style: theme.textTheme.titleMedium),
                  ),
                  TextButton(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(builder: (_) => const SpendingScreen()),
                    ),
                    child: const Text('Spending'),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              if (realUpcoming.isEmpty)
                EmptyState(
                  icon: Icons.event_available_outlined,
                  title: 'No confirmed payments coming up',
                  message: 'Add a bill with an amount and a date and it will '
                      'appear here. Estimated amounts are kept separate.',
                  action: FilledButton.icon(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(builder: (_) => const AddBillScreen()),
                    ),
                    icon: const Icon(Icons.add),
                    label: const Text('Add a bill'),
                  ),
                )
              else
                for (final Bill bill in realUpcoming)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: BillTile(
                      bill: bill,
                      now: now,
                      canSeeAmounts: canSeeAmounts,
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => BillDetailScreen(billId: bill.id),
                        ),
                      ),
                    ),
                  ),
              if (estimates.isNotEmpty) ...<Widget>[
                const SizedBox(height: 8),
                SectionCard(
                  title: 'Estimates (not counted)',
                  subtitle: 'Forecasts you recorded. They never change your '
                      'totals and are not money you owe.',
                  child: Column(
                    children: <Widget>[
                      for (final Bill bill in estimates)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: BillTile(
                            bill: bill,
                            now: now,
                            canSeeAmounts: canSeeAmounts,
                            onTap: () => Navigator.of(context).push(
                              MaterialPageRoute<void>(
                                builder: (_) =>
                                    BillDetailScreen(billId: bill.id),
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 20),
              Row(
                children: <Widget>[
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => const AddBillScreen(),
                        ),
                      ),
                      icon: const Icon(Icons.add, size: 18),
                      label: const Text('Add a bill'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton.tonalIcon(
                      onPressed: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => const ReadBillScreen(),
                        ),
                      ),
                      icon: const Icon(Icons.document_scanner_outlined, size: 18),
                      label: const Text('Read a bill'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              _ServicesSection(services: store.data.services),
              const SizedBox(height: 16),
              Text(
                'All figures come from bills you have recorded or details you '
                'have confirmed. Anything missing is shown as missing.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                  height: 1.35,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.label,
    required this.value,
    required this.caption,
    required this.icon,
    this.emphasise = false,
  });

  final String label;
  final String value;
  final String caption;
  final IconData icon;
  final bool emphasise;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AppCard(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(icon, size: 16, color: theme.colorScheme.onSurfaceVariant),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  label,
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              value,
              style: theme.textTheme.headlineSmall?.merge(moneyStyle).copyWith(
                    color: emphasise ? theme.colorScheme.error : null,
                  ),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            caption,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              height: 1.3,
            ),
          ),
        ],
      ),
    );
  }
}

class _AttentionSection extends StatelessWidget {
  const _AttentionSection({required this.summary});

  final HouseholdSummary summary;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return SectionCard(
      title: 'Needs your attention',
      subtitle: 'The app will not fill these gaps for you.',
      child: Column(
        children: <Widget>[
          if (summary.overdueCount > 0)
            _AttentionRow(
              icon: Icons.error_outline,
              tone: NoticeTone.warning,
              title: '${summary.overdueCount} overdue '
                  '${summary.overdueCount == 1 ? 'bill' : 'bills'}',
              subtitle: 'Mark as paid, or update the due date from the bill.',
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const ConfirmSetupScreen(),
                ),
              ),
            ),
          if (summary.unresolvedProviderCount > 0)
            _AttentionRow(
              icon: Icons.help_outline,
              tone: NoticeTone.warning,
              title: '${summary.unresolvedProviderCount} '
                  '${summary.unresolvedProviderCount == 1 ? 'service needs' : 'services need'} '
                  'a provider confirmed',
              subtitle: 'Suggestions stay suggestions until you accept them.',
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const ConfirmSetupScreen(),
                ),
              ),
            ),
          if (summary.excludedFromTotals > 0)
            _AttentionRow(
              icon: Icons.receipt_long_outlined,
              tone: NoticeTone.attention,
              title: '${summary.excludedFromTotals} '
                  '${summary.excludedFromTotals == 1 ? 'bill is' : 'bills are'} '
                  'missing details',
              subtitle: summary.missingDateCount > 0
                  ? '${summary.missingDateCount} without a payment date. They are '
                      'not counted in totals.'
                  : 'Their amounts or dates are not confirmed, so they are not '
                      'counted in totals.',
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute<void>(builder: (_) => const AddBillScreen()),
              ),
            ),
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              'Missing information is listed here instead of being estimated.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _AttentionRow extends StatelessWidget {
  const _AttentionRow({
    required this.icon,
    required this.tone,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final NoticeTone tone;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Color iconColor = tone == NoticeTone.attention
        ? theme.colorScheme.onTertiaryContainer
        : theme.colorScheme.onSecondaryContainer;
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          children: <Widget>[
            Icon(icon, size: 18, color: iconColor),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(title, style: theme.textTheme.bodyMedium),
                  Text(
                    subtitle,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                      height: 1.3,
                    ),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right, size: 18),
          ],
        ),
      ),
    );
  }
}

class _ServicesSection extends StatelessWidget {
  const _ServicesSection({required this.services});

  final List<HouseholdService> services;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return SectionCard(
      title: 'Your household services',
      subtitle: 'Provider, amount and date are tracked separately for each one.',
      action: IconButton(
        tooltip: 'Manage services',
        onPressed: () => Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => const ConfirmSetupScreen(),
          ),
        ),
        icon: const Icon(Icons.chevron_right),
      ),
      child: Column(
        children: <Widget>[
          for (final HouseholdService service in services)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
                children: <Widget>[
                  Icon(iconForServiceName(service.kind.name), size: 16),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      service.kind.label,
                      style: theme.textTheme.bodyMedium,
                    ),
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
            ),
        ],
      ),
    );
  }
}
