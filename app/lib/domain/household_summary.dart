import '../core/format.dart';
import 'app_data.dart';
import 'bill.dart';
import 'field.dart';
import 'household_service.dart';

/// Every number the dashboard shows is computed here, from recorded data only.
///
/// Rules that the rest of the app must not break:
///  * an estimated amount never contributes to "monthly bills" or "still to pay";
///  * a bill without a confirmed amount or a confirmed date is excluded from
///    totals and surfaced in [needsDetails] instead;
///  * "still to pay" only counts unpaid bills that are actually due inside the
///    horizon, so the figure always matches the list underneath it.
class HouseholdSummary {
  const HouseholdSummary({
    required this.monthlyRecurringMinor,
    required this.monthlyRecurringCount,
    required this.stillToPayMinor,
    required this.stillToPayCount,
    required this.excludedFromTotals,
    required this.upcoming,
    required this.needsDetails,
    required this.estimates,
    required this.unresolvedProviderCount,
    required this.missingDateCount,
    required this.overdueCount,
  });

  final int monthlyRecurringMinor;
  final int monthlyRecurringCount;
  final int stillToPayMinor;
  final int stillToPayCount;
  final int excludedFromTotals;
  final List<Bill> upcoming;
  final List<Bill> needsDetails;

  /// Forecasts the resident chose to record. Shown separately, never totalled.
  final List<Bill> estimates;
  final int unresolvedProviderCount;
  final int missingDateCount;
  final int overdueCount;

  bool get hasReliableTotals => monthlyRecurringCount > 0 || stillToPayCount > 0;

  /// Number of things the resident could act on right now.
  int get attentionCount =>
      excludedFromTotals + unresolvedProviderCount + overdueCount;

  static HouseholdSummary compute(
    AppData data, {
    DateTime? now,
    int stillToPayHorizonDays = 30,
  }) {
    final DateTime reference = now ?? today();

    int monthlyRecurring = 0;
    int monthlyRecurringCount = 0;
    int unresolvedProviders = 0;

    for (final HouseholdService service in data.services) {
      if (service.readiness == ServiceReadiness.notFound) {
        unresolvedProviders++;
        continue;
      }
      if (service.readiness == ServiceReadiness.needsConfirmation) {
        unresolvedProviders++;
      }
      // Only a confirmed, non-estimated amount feeds the recurring total.
      if (service.amountMinor.isConfirmed &&
          service.amountMinor.source != FieldSource.estimate &&
          service.amountMinor.value != null) {
        final int monthly = service.monthlyEquivalentMinor;
        if (monthly > 0) {
          monthlyRecurring += monthly;
          monthlyRecurringCount++;
        }
      }
    }

    int stillToPay = 0;
    int stillToPayCount = 0;
    int excluded = 0;
    int missingDate = 0;
    int overdue = 0;

    final List<Bill> upcoming = <Bill>[];
    final List<Bill> needsDetails = <Bill>[];
    final List<Bill> estimates = <Bill>[];

    for (final Bill bill in data.bills) {
      if (bill.isPaid) continue;

      if (bill.isEstimate) {
        // Forecasts are shown in their own section and never counted as money
        // owed. They are not "missing details" either: the resident chose to
        // record an estimate.
        estimates.add(bill);
        continue;
      }

      if (!bill.isActionable) {
        needsDetails.add(bill);
        excluded++;
        if (!bill.dueDate.hasValue) missingDate++;
        continue;
      }

      if (bill.isOverdue(reference)) {
        overdue++;
        upcoming.add(bill);
        stillToPay += bill.amountMinor.value!;
        stillToPayCount++;
        continue;
      }

      if (bill.isDueWithin(reference, stillToPayHorizonDays)) {
        upcoming.add(bill);
        if (bill.amountMinor.isConfirmed) {
          stillToPay += bill.amountMinor.value!;
          stillToPayCount++;
        } else {
          excluded++;
        }
        continue;
      }

      upcoming.add(bill);
    }

    upcoming.sort((Bill a, Bill b) {
      final DateTime? da = a.dueDate.value;
      final DateTime? db = b.dueDate.value;
      if (da == null && db == null) return 0;
      if (da == null) return 1;
      if (db == null) return -1;
      return da.compareTo(db);
    });
    needsDetails.sort((Bill a, Bill b) => a.kind.index.compareTo(b.kind.index));
    estimates.sort((Bill a, Bill b) {
      final DateTime? da = a.dueDate.value;
      final DateTime? db = b.dueDate.value;
      if (da == null && db == null) return 0;
      if (da == null) return 1;
      if (db == null) return -1;
      return da.compareTo(db);
    });

    return HouseholdSummary(
      monthlyRecurringMinor: monthlyRecurring,
      monthlyRecurringCount: monthlyRecurringCount,
      stillToPayMinor: stillToPay,
      stillToPayCount: stillToPayCount,
      excludedFromTotals: excluded,
      upcoming: upcoming,
      needsDetails: needsDetails,
      estimates: estimates,
      unresolvedProviderCount: unresolvedProviders,
      missingDateCount: missingDate,
      overdueCount: overdue,
    );
  }
}

/// A row in the monthly spend table.
class MonthlySpend {
  const MonthlySpend({required this.month, required this.totalMinor, required this.billCount});

  final DateTime month;
  final int totalMinor;
  final int billCount;
}

/// Recorded spend per calendar month, newest first.
///
/// Only confirmed, non-estimated amounts are included, and a bill is counted in
/// the month of its due date (falling back to the billing period start).
List<MonthlySpend> monthlySpend(List<Bill> bills, {int months = 6}) {
  final Map<String, int> totals = <String, int>{};
  final Map<String, int> counts = <String, int>{};
  final Map<String, DateTime> keys = <String, DateTime>{};

  for (final Bill bill in bills) {
    if (bill.isEstimate) continue;
    if (!bill.amountMinor.isConfirmed) continue;
    final int? amount = bill.amountMinor.value;
    if (amount == null) continue;
    final DateTime? anchor = bill.dueDate.value ?? bill.periodStart;
    if (anchor == null) continue;
    final String key = '${anchor.year}-${anchor.month.toString().padLeft(2, '0')}';
    keys[key] = DateTime(anchor.year, anchor.month);
    totals[key] = (totals[key] ?? 0) + amount;
    counts[key] = (counts[key] ?? 0) + 1;
  }

  final List<String> sorted = keys.keys.toList()
    ..sort((String a, String b) => b.compareTo(a));

  return sorted
      .take(months)
      .map(
        (String key) => MonthlySpend(
          month: keys[key]!,
          totalMinor: totals[key] ?? 0,
          billCount: counts[key] ?? 0,
        ),
      )
      .toList();
}
