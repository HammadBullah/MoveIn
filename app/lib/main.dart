import 'package:flutter/material.dart';

import 'app.dart';
import 'data/store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Local-first: everything is loaded before the first frame so the resident
  // never sees an empty dashboard flash over real data.
  final AppStore store = AppStore();
  await store.load();

  runApp(MoveInApp(store: store));
}
