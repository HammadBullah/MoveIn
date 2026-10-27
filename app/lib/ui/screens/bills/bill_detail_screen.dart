import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../domain/bill.dart';
import '../../../domain/enums.dart';
import '../../../theme.dart';
import '../../scope.dart';
import '../../widgets/layout.dart';
import '../../widgets/provenance.dart';
import 'add_bill_screen.dart';

class BillDetailScreen extends StatelessWidget {
  const BillDetailScreen({super.key, required this.billId});

  final String billId;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final store = MoveInScope.of(context);
    final DateTime now = today();

    Bill? bill;
    for (final Bill candidate in store.data.bills) {
      if (candidate.id == billId) bill = candidate;
    }

    if (bill == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Bill')),
        body: const EmptyState(
          icon: Icons.receipt_long_outlined,
          title: 'This bill is no longer recorded',
          message: 'It may have been deleted from another device or reset.',
        ),
      );
    }

    final Bill current = bill;
    final BillState state = current.stateFor(now);
    final bool canEdit = store.data.canEditBills;
    final bool canSeeAmounts = store.data.canSeeAmounts;

    return Scaffold(
      appBar: AppBar(
        title: Text(current.kind.label),
        actions: <Widget>[
          if (canEdit)
            IconButton(
              tooltip: 'Edit bill',
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => AddBillScreen(editBill: current),
                ),
              ),
              icon: const Icon(Icons.edit_outlined),
            ),
          if (canEdit)
            IconButton(
              tooltip: 'Delete bill',
              onPressed: () async {
                final bool ok = await confirmAction(
                  context,
                  title: 'Delete this bill?',
                  message: 'The bill and its reminder link will be removed. Any '
                      'document you attached stays in your records.',
                  confirmLabel: 'Delete',
                  destructive: true,
                );
                if (!ok) return;
                await store.deleteBill(current.id);
                if (context.mounted) Navigator.of(context).pop();
              },
              icon: const Icon(Icons.delete_outline),
            ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
          children: <Widget>[
            AppCard(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      StatusPill.forBill(state),
                      const Spacer(),
                      Text(
                        current.frequency.label,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    canSeeAmounts ? formatMinor(current.amountMinor.value) : '••••',
                    style: theme.textTheme.displaySmall?.merge(moneyStyle),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    current.dueDate.hasValue
                        ? relativeDueLabel(current.dueDate.value!, now: now)
                        : 'No payment date recorded',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  if (current.isEstimate) ...<Widget>[
                    const SizedBox(height: 12),
                    const NoticeBanner(
                      tone: NoticeTone.attention,
                      icon: Icons.trending_up,
                      message: 'This is an estimate, not a bill. It is excluded '
                          'from monthly totals and from "still to pay".',
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 12),
            SectionCard(
              title: 'Where these values came from',
              child: Column(
                children: <Widget>[
                  FieldRow(label: 'Provider', field: current.provider),
                  FieldRow(
                    label: 'Amount',
                    field: current.amountMinor,
                    valueBuilder: (Object? value) => value is int
                        ? formatMinor(value)
                        : 'Not recorded',
                  ),
                  FieldRow(
                    label: 'Due date',
                    field: current.dueDate,
                    valueBuilder: (Object? value) =>
                        value is DateTime ? formatDateLong(value) : 'Not recorded',
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        SizedBox(
                          width: 128,
                          child: Text(
                            'Payment',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ),
                        Expanded(
                          child: Text(
                            switch (current.paymentStatus) {
                              PaymentStatus.paid => 'Marked as paid by you',
                              PaymentStatus.scheduled => 'Scheduled',
                              PaymentStatus.unknown => 'No evidence recorded',
                            },
                            style: theme.textTheme.bodyMedium,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            if (current.notes != null && current.notes!.isNotEmpty)
              SectionCard(
                title: 'Notes',
                child: Text(current.notes!, style: theme.textTheme.bodyMedium),
              ),
            if (current.notes != null && current.notes!.isNotEmpty)
              const SizedBox(height: 12),
            if (!current.isPaid && current.isActionable)
              FilledButton.tonalIcon(
                onPressed: canEdit
                    ? () => store.setBillPaid(current.id, true)
                    : null,
                icon: const Icon(Icons.check_circle_outline),
                label: const Text('Mark as paid'),
              ),
            if (current.isPaid)
              OutlinedButton.icon(
                onPressed: canEdit
                    ? () => store.setBillPaid(current.id, false)
                    : null,
                icon: const Icon(Icons.undo),
                label: const Text('Mark as not paid'),
              ),
            if (!current.isPaid) ...<Widget>[
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: canEdit
                    ? () async {
                        final DateTime? due = current.dueDate.value;
                        final DateTime when = due == null
                            ? today()
                            : due.subtract(const Duration(days: 3));
                        await store.addReminder(
                          kind: ReminderKind.payment,
                          title: '${current.kind.label} payment',
                          dueAt: when.isBefore(today()) ? today() : when,
                          note: 'Set from the bill due date.',
                          billId: current.id,
                        );
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(
                                'Reminder added for ${formatDateCompact(when)}.',
                              ),
                            ),
                          );
                        }
                      }
                    : null,
                icon: const Icon(Icons.notifications_active_outlined),
                label: const Text('Remind me before it is due'),
              ),
            ],
            if (!current.isActionable) ...<Widget>[
              const SizedBox(height: 8),
              NoticeBanner(
                tone: NoticeTone.attention,
                message: current.dueDate.hasValue
                    ? 'This bill has no confirmed amount, so it is excluded from '
                        'totals.'
                    : 'This bill has no payment date, so no reminder can be '
                        'scheduled until you add one.',
                action: canEdit
                    ? TextButton(
                        onPressed: () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => AddBillScreen(editBill: current),
                          ),
                        ),
                        child: const Text('Add the missing details'),
                      )
                    : null,
              ),
            ],
            const SizedBox(height: 20),
            Text(
              'HomeLedger only knows what you have recorded. Marking a bill paid '
              'means you told the app; it does not confirm money left your bank.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
