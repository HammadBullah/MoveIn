import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../domain/bill.dart';
import '../../domain/enums.dart';
import '../../theme.dart';
import 'layout.dart';

/// One bill row. Shows "Needs details" instead of inventing a date, and shows
/// estimates with their own label rather than mixing them into real amounts.
class BillTile extends StatelessWidget {
  const BillTile({
    super.key,
    required this.bill,
    required this.now,
    this.canSeeAmounts = true,
    this.onTap,
  });

  final Bill bill;
  final DateTime now;
  final bool canSeeAmounts;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final BillState state = bill.stateFor(now);
    final String provider = bill.provider.value ?? 'Provider not recorded';

    final String whenLabel = switch (state) {
      BillState.needsDetails => bill.dueDate.hasValue
          ? 'Amount not confirmed'
          : 'Payment date not confirmed',
      BillState.paid => 'Paid',
      _ => relativeDueLabel(bill.dueDate.value!, now: now),
    };

    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Row(
        children: <Widget>[
          Container(
            padding: const EdgeInsets.all(9),
            decoration: BoxDecoration(
              color: scheme.surfaceContainerHighest,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(iconForServiceName(bill.kind.name), size: 18),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  bill.kind.label,
                  style: theme.textTheme.bodyLarge?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  provider,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 6),
                Row(
                  children: <Widget>[
                    StatusPill.forBill(
                      bill.isEstimate && state != BillState.paid
                          ? BillState.needsDetails
                          : state,
                    ),
                    const SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        bill.isEstimate ? 'Estimate · $whenLabel' : whenLabel,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: <Widget>[
              Text(
                canSeeAmounts
                    ? formatMinor(bill.amountMinor.value)
                    : '••••',
                style: theme.textTheme.bodyLarge?.merge(moneyStyle),
              ),
              if (bill.dueDate.hasValue) ...<Widget>[
                const SizedBox(height: 4),
                Text(
                  formatDateShort(bill.dueDate.value!),
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}
