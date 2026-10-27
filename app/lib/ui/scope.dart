import 'package:flutter/widgets.dart';

import '../data/store.dart';

/// Makes the single [AppStore] available to the widget tree and rebuilds
/// dependants whenever it changes.
class MoveInScope extends InheritedNotifier<AppStore> {
  const MoveInScope({
    super.key,
    required AppStore store,
    required super.child,
  }) : super(notifier: store);

  /// Subscribes the calling widget to store changes.
  static AppStore of(BuildContext context) {
    final MoveInScope? scope =
        context.dependOnInheritedWidgetOfExactType<MoveInScope>();
    assert(scope != null, 'MoveInScope is missing from the widget tree.');
    return scope!.notifier!;
  }

  /// Reads the store without subscribing (for callbacks).
  static AppStore read(BuildContext context) {
    final MoveInScope? scope =
        context.getInheritedWidgetOfExactType<MoveInScope>();
    assert(scope != null, 'MoveInScope is missing from the widget tree.');
    return scope!.notifier!;
  }
}
