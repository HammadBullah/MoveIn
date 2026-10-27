import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../domain/bill.dart';
import '../../../theme.dart';
import '../../scope.dart';
import '../../widgets/bill_tile.dart';
import '../../widgets/layout.dart';
import '../bills/bill_detail_screen.dart';

/// Bills on a calendar, because "when is it going out?" is the question people
/// actually ask. Only confirmed due dates get a marker.
class CalendarScreen extends StatefulWidget {
  const CalendarScreen({super.key});

  @override
  State<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends State<CalendarScreen> {
  late DateTime _month = DateTime(today().year, today().month);
  late DateTime _selected = today();

  void _changeMonth(int delta) {
    setState(() {
      final DateTime next = DateTime(_month.year, _month.month + delta);
      _month = next;
      final DateTime now = today();
      _selected = (now.year == next.year && now.month == next.month)
          ? now
          : DateTime(next.year, next.month, 1);
    });
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final store = MoveInScope.of(context);
    final DateTime now = today();
    final bool canSeeAmounts = store.data.canSeeAmounts;

    final Map<int, List<Bill>> byDay = <int, List<Bill>>{};
    int monthTotal = 0;
    int monthUnconfirmed = 0;

    for (final Bill bill in store.data.bills) {
      final DateTime? due = bill.dueDate.value;
      if (due == null) continue;
      if (due.year != _month.year || due.month != _month.month) continue;
      byDay.putIfAbsent(due.day, () => <Bill>[]).add(bill);
      if (bill.isPaid) continue;
      if (bill.isEstimate || !bill.amountMinor.isConfirmed) {
        monthUnconfirmed++;
      } else {
        monthTotal += bill.amountMinor.value ?? 0;
      }
    }

    final List<Bill> selectedBills = (byDay[_selected.day] ?? <Bill>[])
        .where((Bill bill) =>
            bill.dueDate.value?.year == _selected.year &&
            bill.dueDate.value?.month == _selected.month)
        .toList();

    final List<Bill> nextSeven = store.data.bills
        .where((Bill bill) => bill.isDueWithin(now, 7))
        .toList()
      ..sort((Bill a, Bill b) =>
          a.dueDate.value!.compareTo(b.dueDate.value!));

    final int daysInMonth = DateTime(_month.year, _month.month + 1, 0).day;
    final int leadingBlanks = DateTime(_month.year, _month.month, 1).weekday - 1;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Calendar'),
        actions: <Widget>[
          TextButton(
            onPressed: () => setState(() {
              final DateTime n = today();
              _month = DateTime(n.year, n.month);
              _selected = n;
            }),
            child: const Text('Today'),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
          children: <Widget>[
            AppCard(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      IconButton(
                        tooltip: 'Previous month',
                        onPressed: () => _changeMonth(-1),
                        icon: const Icon(Icons.chevron_left),
                      ),
                      Expanded(
                        child: Center(
                          child: Text(
                            formatMonthYear(_month),
                            style: theme.textTheme.titleMedium,
                          ),
                        ),
                      ),
                      IconButton(
                        tooltip: 'Next month',
                        onPressed: () => _changeMonth(1),
                        icon: const Icon(Icons.chevron_right),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: <Widget>[
                      for (final String label in <String>[
                        'Mon',
                        'Tue',
                        'Wed',
                        'Thu',
                        'Fri',
                        'Sat',
                        'Sun',
                      ])
                        Expanded(
                          child: Center(
                            child: Text(
                              label,
                              style: theme.textTheme.labelSmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  GridView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: leadingBlanks + daysInMonth,
                    gridDelegate:
                        const SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 7,
                      childAspectRatio: 0.92,
                    ),
                    itemBuilder: (BuildContext context, int index) {
                      if (index < leadingBlanks) return const SizedBox.shrink();
                      final int day = index - leadingBlanks + 1;
                      return _DayCell(
                        day: day,
                        bills: byDay[day] ?? const <Bill>[],
                        isSelected: _selected.year == _month.year &&
                            _selected.month == _month.month &&
                            _selected.day == day,
                        isToday: now.year == _month.year &&
                            now.month == _month.month &&
                            now.day == day,
                        onTap: () => setState(
                          () => _selected = DateTime(_month.year, _month.month, day),
                        ),
                      );
                    },
                  ),
                  const Divider(height: 20),
                  Row(
                    children: <Widget>[
                      Expanded(
                        child: Text(
                          'Confirmed due this month',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ),
                      Text(
                        canSeeAmounts ? formatMinor(monthTotal) : '••••',
                        style: theme.textTheme.bodyMedium?.merge(moneyStyle),
                      ),
                    ],
                  ),
                  if (monthUnconfirmed > 0)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Row(
                        children: <Widget>[
                          Expanded(
                            child: Text(
                              '$monthUnconfirmed not counted (estimate or '
                              'unconfirmed amount)',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Text(
              '${weekdayShort(_selected)} ${formatDateLong(_selected)}',
              style: theme.textTheme.titleSmall,
            ),
            const SizedBox(height: 8),
            if (selectedBills.isEmpty)
              Text(
                'Nothing recorded for this day.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              )
            else
              for (final Bill bill in selectedBills)
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
            const SizedBox(height: 16),
            Text('Due in the next 7 days', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            if (nextSeven.isEmpty)
              Text(
                'Nothing due in the next week.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              )
            else
              for (final Bill bill in nextSeven)
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
          ],
        ),
      ),
    );
  }
}

class _DayCell extends StatelessWidget {
  const _DayCell({
    required this.day,
    required this.bills,
    required this.isSelected,
    required this.isToday,
    required this.onTap,
  });

  final int day;
  final List<Bill> bills;
  final bool isSelected;
  final bool isToday;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final bool hasConfirmed = bills.any(
      (Bill bill) => !bill.isEstimate && bill.amountMinor.isConfirmed,
    );
    final bool hasOther = bills.isNotEmpty && !hasConfirmed;

    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.all(2),
        decoration: BoxDecoration(
          color: isSelected ? scheme.primaryContainer : null,
          borderRadius: BorderRadius.circular(10),
          border: isToday && !isSelected
              ? Border.all(color: scheme.primary)
              : null,
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Text(
              '$day',
              style: theme.textTheme.bodySmall?.copyWith(
                fontWeight: isToday ? FontWeight.w700 : FontWeight.w400,
                color: isSelected ? scheme.onPrimaryContainer : null,
              ),
            ),
            const SizedBox(height: 2),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                if (hasConfirmed)
                  _dot(scheme.primary)
                else if (hasOther)
                  _dot(scheme.tertiary)
                else
                  const SizedBox(height: 5),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _dot(Color color) => Container(
        height: 5,
        width: 5,
        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      );
}
