import 'package:flutter/material.dart';

import 'data/store.dart';
import 'theme.dart';
import 'ui/scope.dart';
import 'ui/screens/confirm/confirm_setup_screen.dart';
import 'ui/screens/onboarding/onboarding_screen.dart';
import 'ui/shell.dart';

class MoveInApp extends StatelessWidget {
  const MoveInApp({super.key, required this.store});

  final AppStore store;

  @override
  Widget build(BuildContext context) {
    return MoveInScope(
      store: store,
      child: MaterialApp(
        title: 'HomeLedger',
        debugShowCheckedModeBanner: false,
        theme: buildAppTheme(Brightness.light),
        darkTheme: buildAppTheme(Brightness.dark),
        themeMode: ThemeMode.system,
        home: const RootGate(),
      ),
    );
  }
}

/// Decides which of the three top-level states the resident is in:
/// no address yet → setup; address but unconfirmed providers → confirmation;
/// otherwise → the dashboard shell.
class RootGate extends StatelessWidget {
  const RootGate({super.key});

  @override
  Widget build(BuildContext context) {
    final AppStore store = MoveInScope.of(context);

    if (!store.isLoaded) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    if (!store.data.hasProperty) {
      return const OnboardingScreen();
    }

    if (!store.data.onboardingComplete) {
      return const ConfirmSetupScreen(isOnboarding: true);
    }

    return const HomeShell();
  }
}
