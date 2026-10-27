import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:home_ledger/app.dart';
import 'package:home_ledger/data/store.dart';
import 'package:home_ledger/domain/member.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<AppStore> emptyStore() async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  final AppStore store = AppStore();
  await store.load();
  return store;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('first launch asks for an address and says it is demo data',
      (WidgetTester tester) async {
    final AppStore store = await emptyStore();

    await tester.pumpWidget(MoveInApp(store: store));
    await tester.pumpAndSettle();

    expect(find.text('Your address'), findsOneWidget);
    expect(find.textContaining('Demo address list'), findsOneWidget);
    expect(find.text('Continue'), findsOneWidget);
  });

  testWidgets('the demo household lands on a dashboard with real totals',
      (WidgetTester tester) async {
    final AppStore store = await emptyStore();
    await store.loadDemoHousehold();

    await tester.pumpWidget(MoveInApp(store: store));
    await tester.pumpAndSettle();

    expect(find.text('My Home'), findsOneWidget);
    expect(find.text('Monthly bills'), findsOneWidget);
    expect(find.text('Still to pay'), findsOneWidget);
    // The water bill has no payment date: it must be surfaced, not invented.
    expect(find.text('Upcoming payments'), findsOneWidget);
    expect(
      find.textContaining('Estimates'),
      findsWidgets,
      reason: 'estimates must be shown separately from real amounts',
    );
  });

  testWidgets('a viewer role does not see amounts', (WidgetTester tester) async {
    final AppStore store = await emptyStore();
    await store.loadDemoHousehold();

    final Member viewer = store.data.members
        .firstWhere((Member m) => m.role.name == 'viewer');
    await store.setCurrentMember(viewer.id);

    await tester.pumpWidget(MoveInApp(store: store));
    await tester.pumpAndSettle();

    expect(find.text('••••'), findsWidgets);
  });
}
