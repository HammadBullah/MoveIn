import '../../core/format.dart';
import '../../domain/enums.dart';
import '../../domain/field.dart';

/// The result of reading a bill's text.
///
/// Every field is a *suggestion*: the resident confirms each one before it is
/// saved. Nothing here is ever treated as an obligation on its own.
class ExtractedBill {
  const ExtractedBill({
    required this.provider,
    required this.amountMinor,
    required this.dueDate,
    required this.kind,
    required this.frequency,
    required this.warnings,
    required this.rawText,
  });

  final Field<String> provider;
  final Field<int> amountMinor;
  final Field<DateTime> dueDate;
  final ServiceKind? kind;
  final PaymentFrequency? frequency;
  final List<String> warnings;
  final String rawText;

  bool get hasAnything =>
      provider.hasValue || amountMinor.hasValue || dueDate.hasValue;

  int get confirmedFieldCount {
    var count = 0;
    if (provider.hasValue) count++;
    if (amountMinor.hasValue) count++;
    if (dueDate.hasValue) count++;
    return count;
  }
}

/// Rule-based extraction for pasted bill text.
///
/// This is intentionally a plain, explainable set of rules rather than a
/// black box: it runs offline, it is testable, and each value it produces
/// carries [FieldSource.billExtraction] so the UI can ask for confirmation.
/// When OCR lands, its output is fed through exactly this function; a hosted
/// OCR/LLM step can replace [BillTextParser.parse] behind the same interface.
class BillTextParser {
  static ExtractedBill parse(
    String text, {
    ServiceKind? hintedKind,
    DateTime? now,
  }) {
    final String normalised = text.replaceAll('\r\n', '\n');
    final List<String> lines = normalised
        .split('\n')
        .map((String line) => line.trim())
        .where((String line) => line.isNotEmpty)
        .toList();

    final List<String> warnings = <String>[];

    final ServiceKind? kind = hintedKind ?? _detectKind(normalised);
    final Field<String> provider = _detectProvider(normalised, lines, warnings);
    final Field<int> amount = _detectAmount(lines, warnings);
    final Field<DateTime> due = _detectDueDate(normalised, now, warnings);
    final PaymentFrequency? frequency = _detectFrequency(normalised);

    if (!provider.hasValue) {
      warnings.add('No provider name was recognised. Enter it yourself.');
    }
    if (!amount.hasValue) {
      warnings.add('No amount was found. Type the amount from the bill.');
    }
    if (!due.hasValue) {
      warnings.add('No due date was found. Enter the date from the bill.');
    }

    return ExtractedBill(
      provider: provider,
      amountMinor: amount,
      dueDate: due,
      kind: kind,
      frequency: frequency,
      warnings: warnings,
      rawText: normalised,
    ); // Ensure this line is correctly placed
  }

  // ---------------------------------------------------------------------------
  // Provider
  // ---------------------------------------------------------------------------

  /// Illustrative list only. The real product should match against the
  /// provider directory returned by the backend.
  static const List<String> knownProviders = <String>[
    'British Gas',
    'EDF Energy',
    'E.ON Next',
    'E.ON',
    'Octopus Energy',
    'OVO Energy',
    'Scottish Power',
    'SSE',
    'Shell Energy',
    'Utilita',
    'Ecotricity',
    'Co-operative Energy',
    'Wessex Water',
    'Thames Water',
    'Yorkshire Water',
    'United Utilities',
    'Severn Trent',
    'Anglian Water',
    'Dŵr Cymru',
    'Welsh Water',
    'Northumbrian Water',
    'South West Water',
    'Scottish Water',
    'Bristol City Council',
    'Leeds City Council',
    'Cardiff Council',
    'Manchester City Council',
    'TV Licensing',
    'BT',
    'Virgin Media',
    'Sky',
    'TalkTalk',
    'Vodafone',
    'EE',
  ];

  static Field<String> _detectProvider(
    String text,
    List<String> lines,
    List<String> warnings,
  ) {
    for (final String known in knownProviders) {
      final RegExp pattern = RegExp(RegExp.escape(known), caseSensitive: false);
      if (pattern.hasMatch(text)) {
        return Field<String>.suggested(
          known,
          source: FieldSource.billExtraction,
          note: 'Matched against the provider name list.',
        );
      }
    }

    // "Provider: Octopus" / "Supplier - Octopus" style labels.
    final RegExp labelled = RegExp(r'Provider:\s*(\w+)'); // Example pattern for matching provider labels
    final RegExpMatch? match = labelled.firstMatch(text);
    if (match != null) {
      final String candidate = match.group(1)!.trim();
      if (candidate.length >= 3) {
        warnings.add('Provider taken from a label on the page — please check it.');
        return Field<String>.suggested(
          candidate,
          source: FieldSource.billExtraction,
          note: 'Taken from a labelled field.',
        );
      }
    }
    return const Field<String>.missing();
  }

  // ---------------------------------------------------------------------------
  // Amount
  // ---------------------------------------------------------------------------

  static const List<String> _amountLabels = <String>[
    'total amount due',
    'amount due',
    'total due',
    'balance due',
    'please pay',
    'new balance',
    'total charges',
    'amount payable',
    'total',
  ];

  static Field<int> _detectAmount(List<String> lines, List<String> warnings) {
    final RegExp money = RegExp(r'£\s?([0-9][0-9,]*\.?[0-9]{0,2})');

    int? best;
    String? bestLabel;
    final List<int> allAmounts = <int>[];

    for (final String line in lines) {
      final String lower = line.toLowerCase();
      for (final RegExpMatch match in money.allMatches(line)) {
        final int? minor = parseMoneyToMinor(match.group(1)!);
        if (minor == null) continue;
        allAmounts.add(minor);
        for (final String label in _amountLabels) {
          if (lower.contains(label)) {
            if (best == null || _labelPriority(label) < _labelPriority(bestLabel ?? '')) {
              best = minor;
              bestLabel = label;
            }
          }
        }
      }
    }

    if (best != null) {
      return Field<int>.suggested(
        best,
        source: FieldSource.billExtraction,
        note: 'Read from the "${_titleCase(bestLabel ?? 'total')}" line.',
      );
    }

    if (allAmounts.isNotEmpty) {
      allAmounts.sort();
      final int largest = allAmounts.last;
      if (allAmounts.length > 1) {
        warnings.add(
          'Several amounts were found. The largest (£${formatMinor(largest, withPence: true)}) '
          'is a guess — please check it against the bill.',
        );
      } else {
        warnings.add('Only one amount was found, with no clear "total" label.');
      }
      return Field<int>.suggested(
        largest,
        source: FieldSource.billExtraction,
        note: 'Largest amount on the page; no total label found.',
      );
    }

    return const Field<int>.missing();
  }

  static int _labelPriority(String label) {
    final int index = _amountLabels.indexOf(label);
    return index == -1 ? _amountLabels.length : index;
  }

  // ---------------------------------------------------------------------------
  // Due date
  // ---------------------------------------------------------------------------

  static const List<String> _monthNames = <String>[
    'january',
    'february',
    'march',
    'april',
    'may',
    'june',
    'july',
    'august',
    'september',
    'october',
    'november',
    'december',
  ];

  static Field<DateTime> _detectDueDate(
    String text,
    DateTime? now,
    List<String> warnings,
  ) {
    final DateTime reference = now ?? today();

    // Only look near "due"/"pay by"/"instalment" so we do not pick up the
    // billing period start.
    final RegExp dueContext = RegExp(
      r'(?:due date|due on|due by|payment due|please pay by|pay by|instalment due|next payment|due\b)\s*[^0-9]{0,24}'
      r'([0-9]{1,2}[\/\-\.][0-9]{1,2}[\/\-\.][0-9]{2,4}'
      r'|[0-9]{4}-[0-9]{2}-[0-9]{2}'
      r'|[0-9]{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?[A-Za-z]{3,9}\s+[0-9]{2,4}'
      r'|[A-Za-z]{3,9}\s+[0-9]{1,2}(?:st|nd|rd|th)?,?\s+[0-9]{2,4})',
      caseSensitive: false,
    );

    final RegExpMatch? match = dueContext.firstMatch(text);
    if (match != null) {
      final DateTime? parsed = parseFlexibleDate(match.group(1)!, reference: reference);
      if (parsed != null) {
        return Field<DateTime>.suggested(
          parsed,
          source: FieldSource.billExtraction,
          note: 'Read from a due-date line.',
        );
      }
      warnings.add('A date was found but could not be read. Check the date field.');
    }

    // Fall back: any explicit "due 28 October 2026" style phrase anywhere.
    final RegExp loose = RegExp(
      r'due[^0-9A-Za-z]{0,8}([0-9]{1,2}[\/\-\.][0-9]{1,2}[\/\-\.][0-9]{2,4})',
      caseSensitive: false,
    );
    final RegExpMatch? looseMatch = loose.firstMatch(text);
    if (looseMatch != null) {
      final DateTime? parsed =
          parseFlexibleDate(looseMatch.group(1)!, reference: reference);
      if (parsed != null) {
        return Field<DateTime>.suggested(
          parsed,
          source: FieldSource.billExtraction,
          note: 'Read from a loose "due" match.',
        );
      }
    }

    return const Field<DateTime>.missing();
  }

  /// Parses the date formats that actually turn up on UK bills.
  ///
  /// Ambiguous `01/02/2026` is read as day-first (UK convention).
  static DateTime? parseFlexibleDate(String input, {DateTime? reference}) {
    final String value = input.trim().toLowerCase().replaceAll(',', '');
    if (value.isEmpty) return null;

    // ISO: 2026-10-28
    final RegExp iso = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$');
    final RegExpMatch? isoMatch = iso.firstMatch(value);
    if (isoMatch != null) {
      return _build(
        int.parse(isoMatch.group(1)!),
        int.parse(isoMatch.group(2)!),
        int.parse(isoMatch.group(3)!),
      );
    }

    // Numeric: 28/10/2026, 28-10-26, 28.10.2026
    final RegExp numeric = RegExp(r'^(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})$');
    final RegExpMatch? numericMatch = numeric.firstMatch(value);
    if (numericMatch != null) {
      final int day = int.parse(numericMatch.group(1)!);
      final int month = int.parse(numericMatch.group(2)!);
      int year = int.parse(numericMatch.group(3)!);
      if (year < 100) {
        final int currentYear = (reference ?? today()).year;
        year += (currentYear ~/ 100) * 100;
        if (year < currentYear - 5) year += 100;
      }
      return _build(year, month, day);
    }

    // "28 october 2026" / "28th of oct 26"
    final RegExp dayFirst = RegExp(
      r'^(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]{3,9})\.?\s+(\d{2,4})$',
    );
    final RegExpMatch? dayFirstMatch = dayFirst.firstMatch(value);
    if (dayFirstMatch != null) {
      final int? month = _monthFromName(dayFirstMatch.group(2)!);
      if (month == null) return null;
      int year = int.parse(dayFirstMatch.group(3)!);
      if (year < 100) {
        year += ((reference ?? today()).year ~/ 100) * 100;
      }
      return _build(year, month, int.parse(dayFirstMatch.group(1)!));
    }

    // "october 28 2026"
    final RegExp monthFirst = RegExp(r'^([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{2,4})$');
    final RegExpMatch? monthFirstMatch = monthFirst.firstMatch(value);
    if (monthFirstMatch != null) {
      final int? month = _monthFromName(monthFirstMatch.group(1)!);
      if (month == null) return null;
      int year = int.parse(monthFirstMatch.group(3)!);
      if (year < 100) {
        year += ((reference ?? today()).year ~/ 100) * 100;
      }
      return _build(year, month, int.parse(monthFirstMatch.group(2)!));
    }

    return null;
  }

  static int? _monthFromName(String name) {
    final String key = name.toLowerCase();
    for (int i = 0; i < _monthNames.length; i++) {
      final String full = _monthNames[i];
      if (key == full || key == full.substring(0, 3)) return i + 1;
    }
    // September is often abbreviated "sept".
    if (key == 'sept') return 9;
    return null;
  }

  static DateTime? _build(int year, int month, int day) {
    if (month < 1 || month > 12 || day < 1 || day > 31) return null;
    final DateTime date = DateTime(year, month, day);
    // Reject impossible dates such as 31 February.
    if (date.month != month || date.day != day) return null;
    return date;
  }

  // ---------------------------------------------------------------------------
  // Frequency and kind
  // ---------------------------------------------------------------------------

  static PaymentFrequency? _detectFrequency(String text) {
    final String lower = text.toLowerCase();
    if (lower.contains('per month') ||
        lower.contains('monthly') ||
        lower.contains('each month')) {
      return PaymentFrequency.monthly;
    }
    if (lower.contains('quarterly') || lower.contains('per quarter')) {
      return PaymentFrequency.quarterly;
    }
    if (lower.contains('annually') ||
        lower.contains('per year') ||
        lower.contains('yearly')) {
      return PaymentFrequency.annually;
    }
    if (lower.contains('fortnightly')) return PaymentFrequency.fortnightly;
    if (lower.contains('weekly')) return PaymentFrequency.weekly;
    return null;
  }

  static ServiceKind? _detectKind(String text) {
    final String lower = text.toLowerCase();
    if (lower.contains('council tax')) return ServiceKind.councilTax;
    if (lower.contains('electricity') || lower.contains('mpan')) {
      return ServiceKind.electricity;
    }
    if (lower.contains('gas bill') || lower.contains('mprn')) return ServiceKind.gas;
    if (lower.contains('wastewater') || lower.contains('sewerage')) {
      return ServiceKind.wastewater;
    }
    if (lower.contains('water')) return ServiceKind.water;
    if (lower.contains('broadband') ||
        lower.contains('fibre') ||
        lower.contains('internet')) {
      return ServiceKind.broadband;
    }
    if (lower.contains('tv licence') || lower.contains('tv license')) {
      return ServiceKind.tvLicence;
    }
    if (lower.contains('insurance')) return ServiceKind.homeInsurance;
    return null;
  }

  static String _titleCase(String value) {
    if (value.isEmpty) return value;
    return value[0].toUpperCase() + value.substring(1);
  }
}
