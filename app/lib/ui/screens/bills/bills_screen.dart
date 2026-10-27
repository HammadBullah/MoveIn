import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../domain/bill.dart';
import '../../scope.dart';
import '../../widgets/bill_tile.dart';
import '../../widgets/layout.dart';
import 'add_bill_screen.dart';
import 'bill_detail_screen.dart';
import 'read_bill_screen.dart';

class BillsScreen extends StatefulWidget {
  const BillsScreen({super.key});

  @override
  State<BillsScreen> createState() => _BillsScreenState();
}

class _BillsScreenState extends State<BillsScreen> {
  _Filter _filter = _Filter.all;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final store = MoveInScope.of(context);
    final DateTime now = today();
    final bool canSeeAmounts = store.data.canSeeAmounts;

    final List<Bill> bills = store.data.bills.toList()
      ..sort((Bill a, Bill b) {
        final DateTime? da = a.dueDate.value;
        final DateTime? db = b.dueDate.value;
        if (da == null && db == null) return 0;
        if (da == null) return 1;
        if (db == null) return -1;
        return da.compareTo(db);
      });

    final List<Bill> filtered = bills.where((Bill bill) {
      return switch (_filter) {
        _Filter.all => true,
        _Filter.toPay => !bill.isPaid && bill.isActionable && !bill.isEstimate,
        _Filter.needsDetails => !bill.isPaid && (!bill.isActionable || bill.isEstimate),
        _Filter.paid => bill.isPaid,
      };
    }).toList();

    final Map<String, List<Bill>> groups = <String, List<Bill>>{
      'Overdue': <Bill>[],
      'Due in the next 7 days': <Bill>[],
      'Later': <Bill>[],
      'Needs details': <Bill>[],
      'Estimates (not counted)': <Bill>[],
      'Paid': <Bill>[],
    };

    for (final Bill bill in filtered) {
      if (bill.isEstimate && !bill.isPaid) {
        groups['Estimates (not counted)']!.add(bill);
        continue;
      }
      switch (bill.stateFor(now)) {
        case BillState.overdue:
          groups['Overdue']!.add(bill);
          break;
        case BillState.dueSoon:
          groups['Due in the next 7 days']!.add(bill);
          break;
        case BillState.upcoming:
          groups['Later']!.add(bill);
          break;
        case BillState.needsDetails:
          groups['Needs details']!.add(bill);
          break;
        case BillState.paid:
          groups['Paid']!.add(bill);
          break;
      }
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Bills'),
        actions: <Widget>[
          IconButton(
            tooltip: 'Read a bill',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const ReadBillScreen()),
            ),
            icon: const Icon(Icons.document_scanner_outlined),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => Navigator.of(context).push(
          MaterialPageRoute<void>(builder: (_) => const AddBillScreen()),
        ),
        icon: const Icon(Icons.add),
        label: const Text('Add bill'),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 96),
          children: <Widget>[
            Text(
              'Only bills you have recorded appear here. Amounts and dates come '
              'from you, a document or a provider — never from the address.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 12),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: <Widget>[
                  for (final _Filter filter in _Filter.values) ...<Widget>[
                    ChoiceChip(
                      label: Text(filter.label),
                      selected: _filter == filter,
                      onSelected: (_) => setState(() => _filter = filter),
                    ),
                    const SizedBox(width: 8),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 16),
            if (filtered.isEmpty)
              EmptyState(
                icon: Icons.receipt_long_outlined,
                title: 'No bills here yet',
                message: _filter == _Filter.all
                    ? 'Add your first bill and HomeLedger will track what is due, '
                        'what is missing and what is already paid.'
                    : 'Nothing matches this filter.',
                action: _filter == _Filter.all
                    ? FilledButton.icon(
                        onPressed: () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => const AddBillScreen(),
                          ),
                        ),
                        icon: const Icon(Icons.add),
                        label: const Text('Add a bill'),
                      )
                    : null,
              )
            else
              for (final MapEntry<String, List<Bill>> group in groups.entries)
                if (group.value.isNotEmpty) ...<Widget>[
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8, top: 4),
                    child: Row(
                      children: <Widget>[
                        Text(group.key, style: theme.textTheme.titleSmall),
                        const SizedBox(width: 8),
                        Text(
                          '${group.value.length}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                  for (final Bill bill in group.value)
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
                  const SizedBox(height: 12),
                ],
          ],
        ),
      ),
    );
  }
}

enum _Filter {
  all,
  toPay,
  needsDetails,
  paid,
}

extension on _Filter {
  String get label => switch (this) {
        _Filter.all => 'All',
        _Filter.toPay => 'To pay',
        _Filter.needsDetails => 'Needs details',
        _Filter.paid => 'Paid',
      };
}
