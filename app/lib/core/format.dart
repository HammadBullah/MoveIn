import 'package:flutter/material.dart';

/// Money is stored as integer minor units (pence). Never as a double.
int? parseMoneyToMinor(String input) {
  final String cleaned =
      input.replaceAll('£', '').replaceAll(',', '').replaceAll(' ', '').trim();
  if (cleaned.isEmpty) return null;
  final double? value = double.tryParse(cleaned);
  if (value == null) return null;
  return (value * 100).round();
}

String formatMinor(int? minor, {bool withPence = true, String symbol = '£'}) {
  if (minor == null) return '—';
  final bool negative = minor < 0;
  final int abs = minor.abs();
  final String pounds = (abs ~/ 100).toString();
  final String pence = (abs % 100).toString().padLeft(2, '0');
  final String grouped = _groupThousands(pounds);
  final String body = withPence ? '$grouped.$pence' : grouped;
  return '${negative ? '-' : ''}$symbol$body';
}

String _groupThousands(String digits) {
  final StringBuffer buffer = StringBuffer();
  for (int i = 0; i < digits.length; i++) {
    final int fromEnd = digits.length - i;
    buffer.write(digits[i]);
    if (fromEnd > 1 && fromEnd % 3 == 1) buffer.write(',');
  }
  return buffer.toString();
}

const List<String> _monthNames = <String>[
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

const List<String> _weekdayShort = <String>[
  'Mon',
  'Tue',
  'Wed',
  'Thu',
  'Fri',
  'Sat',
  'Sun',
];

String monthName(int month) => _monthNames[(month - 1).clamp(0, 11)];

String monthShort(int month) => monthName(month).substring(0, 3);

String weekdayShort(DateTime date) => _weekdayShort[date.weekday - 1];

/// "28 October 2026"
String formatDateLong(DateTime date) =>
    '${date.day} ${monthName(date.month)} ${date.year}';

/// "28 Oct"
String formatDateShort(DateTime date) =>
    '${date.day} ${monthShort(date.month)}';

/// "October 2026"
String formatMonthYear(DateTime date) => '${monthName(date.month)} ${date.year}';

/// "28 Oct 2026"
String formatDateCompact(DateTime date) =>
    '${date.day} ${monthShort(date.month)} ${date.year}';

DateTime dateOnly(DateTime value) =>
    DateTime(value.year, value.month, value.day);

DateTime today() => dateOnly(DateTime.now());

int daysBetween(DateTime from, DateTime to) =>
    dateOnly(to).difference(dateOnly(from)).inDays;

/// "today", "in 3 days", "2 days late"
String relativeDueLabel(DateTime dueDate, {DateTime? now}) {
  final int days = daysBetween(now ?? today(), dueDate);
  if (days == 0) return 'Due today';
  if (days == 1) return 'Due tomorrow';
  if (days == -1) return '1 day late';
  if (days < 0) return '${days.abs()} days late';
  if (days < 7) return 'Due in $days days';
  return 'Due ${formatDateShort(dueDate)}';
}

/// ISO-8601 date only, used for keys and API payloads.
String isoDate(DateTime date) {
  final String month = date.month.toString().padLeft(2, '0');
  final String day = date.day.toString().padLeft(2, '0');
  return '${date.year}-$month-$day';
}

/// Builds an [IconData] indirection so screens do not repeat switch blocks.
IconData iconForServiceName(String kind) {
  switch (kind) {
    case 'electricity':
      return Icons.bolt;
    case 'gas':
      return Icons.local_fire_department_outlined;
    case 'water':
      return Icons.water_drop_outlined;
    case 'wastewater':
      return Icons.waves;
    case 'councilTax':
      return Icons.account_balance_outlined;
    case 'broadband':
      return Icons.router_outlined;
    case 'tvLicence':
      return Icons.live_tv_outlined;
    case 'homeInsurance':
      return Icons.shield_outlined;
    default:
      return Icons.receipt_long_outlined;
  }
}
