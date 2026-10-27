import 'package:flutter/material.dart';

/// A calm, trustworthy palette. Money is never colour-coded as "good" or
/// "bad" beyond the status pills, so the dashboard stays readable.
///
/// Note: this theme deliberately avoids the `ThemeData` sub-theme objects that
/// were renamed during Flutter's component-theme normalisation (CardTheme →
/// CardThemeData, AppBarTheme → AppBarThemeData, InputDecorationTheme →
/// InputDecorationThemeData, ...), so the same source compiles across stable
/// SDKs. Card and input styling live in `AppCard` and `appInputDecoration`.
ThemeData buildAppTheme(Brightness brightness) {
  final ColorScheme scheme = ColorScheme.fromSeed(
    seedColor: const Color(0xFF0B6B5B),
    brightness: brightness,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: brightness == Brightness.light
        ? const Color(0xFFF6F7F5)
        : scheme.surface,
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(0, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(0, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    ),
    listTileTheme: const ListTileThemeData(
      contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
    ),
    dividerTheme: DividerThemeData(
      color: scheme.outlineVariant,
      space: 1,
      thickness: 1,
    ),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
  );
}

/// Shared input decoration so text fields look the same everywhere.
InputDecoration appInputDecoration(
  BuildContext context, {
  String? labelText,
  String? hintText,
  String? helperText,
  String? errorText,
  IconData? prefixIcon,
  Widget? suffixIcon,
  String? prefixText,
}) {
  return InputDecoration(
    labelText: labelText,
    hintText: hintText,
    helperText: helperText,
    helperMaxLines: 3,
    errorText: errorText,
    prefixIcon: prefixIcon == null ? null : Icon(prefixIcon),
    prefixText: prefixText,
    suffixIcon: suffixIcon,
    filled: true,
    fillColor: Theme.of(context).brightness == Brightness.light
        ? Colors.white
        : Theme.of(context).colorScheme.surfaceContainer,
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(12),
      borderSide: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
    ),
  );
}

/// Tabular figures, so columns of money line up.
const TextStyle moneyStyle = TextStyle(
  fontFeatures: <FontFeature>[FontFeature.tabularFigures()],
  fontWeight: FontWeight.w600,
);
