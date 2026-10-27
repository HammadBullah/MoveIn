import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../domain/document.dart';
import '../../../domain/enums.dart';
import '../../scope.dart';
import '../../widgets/form_fields.dart';
import '../../widgets/layout.dart';

/// Reminders for payments, renewals and meter readings.
///
/// This build keeps them in-app. Delivery (local notifications or a scheduled
/// server job) is a separate concern and is called out in the UI so nobody
/// assumes their phone will buzz.
class RemindersScreen extends StatelessWidget {
  const RemindersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final store = MoveInScope.of(context);
    final DateTime now = today();

    final List<Reminder> open = store.data.reminders
        .where((Reminder r) => !r.isDone)
        .toList()
      ..sort((Reminder a, Reminder b) => a.dueAt.compareTo(b.dueAt));
    final List<Reminder> done =
        store.data.reminders.where((Reminder r) => r.isDone).toList();

    return Scaffold(
      appBar: AppBar(title: const Text('Reminders')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _showAddReminder(context),
        icon: const Icon(Icons.add_alert_outlined),
        label: const Text('Add reminder'),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 96),
          children: <Widget>[
            const NoticeBanner(
              icon: Icons.notifications_off_outlined,
              message: 'Reminders are shown in the app. Push notifications and '
                  'email digests need a platform plugin and a scheduled job; '
                  'they are not enabled in this build.',
            ),
            const SizedBox(height: 16),
            if (open.isEmpty)
              const EmptyState(
                icon: Icons.notifications_none,
                title: 'No reminders set',
                message: 'Add reminders for payment dates, contract renewals and '
                    'meter readings. A reminder needs a date you have confirmed.',
              )
            else
              for (final Reminder reminder in open)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _ReminderCard(
                    reminder: reminder,
                    now: now,
                    onToggle: () => store.setReminderDone(reminder.id, true),
                    onDelete: () => store.deleteReminder(reminder.id),
                  ),
                ),
            if (done.isNotEmpty) ...<Widget>[
              const SizedBox(height: 16),
              Text('Done', style: theme.textTheme.titleSmall),
              const SizedBox(height: 8),
              for (final Reminder reminder in done)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _ReminderCard(
                    reminder: reminder,
                    now: now,
                    onToggle: () => store.setReminderDone(reminder.id, false),
                    onDelete: () => store.deleteReminder(reminder.id),
                  ),
                ),
            ],
            const SizedBox(height: 20),
            Text(
              'Bills without a payment date cannot generate reminders. Add the '
              'date from the bill first; HomeLedger will not guess it.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
                height: 1.35,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showAddReminder(BuildContext context) async {
    final ReminderDraft? draft = await showModalBottomSheet<ReminderDraft>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => const _AddReminderSheet(),
    );
    if (draft == null || !context.mounted) return;
    await MoveInScope.read(context).addReminder(
      kind: draft.kind,
      title: draft.title,
      dueAt: draft.dueAt,
      note: draft.note,
    );
  }
}

class _ReminderCard extends StatelessWidget {
  const _ReminderCard({
    required this.reminder,
    required this.now,
    required this.onToggle,
    required this.onDelete,
  });

  final Reminder reminder;
  final DateTime now;
  final VoidCallback onToggle;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool overdue = !reminder.isDone && reminder.dueAt.isBefore(now);

    return AppCard(
      padding: const EdgeInsets.fromLTRB(12, 10, 4, 10),
      child: Row(
        children: <Widget>[
          IconButton(
            tooltip: reminder.isDone ? 'Mark as not done' : 'Mark as done',
            onPressed: onToggle,
            icon: Icon(
              reminder.isDone
                  ? Icons.check_circle
                  : Icons.radio_button_unchecked,
              color: reminder.isDone ? theme.colorScheme.primary : null,
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  reminder.title,
                  style: theme.textTheme.bodyLarge?.copyWith(
                    decoration: reminder.isDone ? TextDecoration.lineThrough : null,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${reminder.kind.label} · ${formatDateCompact(reminder.dueAt)}'
                  '${overdue ? ' · overdue' : ''}',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: overdue
                        ? theme.colorScheme.error
                        : theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                if (reminder.note != null && reminder.note!.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 2),
                  Text(
                    reminder.note!,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ],
            ),
          ),
          IconButton(
            tooltip: 'Delete reminder',
            onPressed: onDelete,
            icon: const Icon(Icons.close, size: 18),
          ),
        ],
      ),
    );
  }
}

class ReminderDraft {
  const ReminderDraft({
    required this.title,
    required this.kind,
    required this.dueAt,
    this.note,
  });

  final String title;
  final ReminderKind kind;
  final DateTime dueAt;
  final String? note;
}

class _AddReminderSheet extends StatefulWidget {
  const _AddReminderSheet();

  @override
  State<_AddReminderSheet> createState() => _AddReminderSheetState();
}

class _AddReminderSheetState extends State<_AddReminderSheet> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _title = TextEditingController();
  final TextEditingController _note = TextEditingController();
  ReminderKind _kind = ReminderKind.payment;
  DateTime _date = today().add(const Duration(days: 7));

  @override
  void dispose() {
    _title.dispose();
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          child: Form(
            key: _formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('New reminder', style: theme.textTheme.titleMedium),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _title,
                  autofocus: true,
                  textCapitalization: TextCapitalization.sentences,
                  decoration: const InputDecoration(labelText: 'Reminder'),
                  validator: (String? value) =>
                      (value == null || value.trim().isEmpty)
                          ? 'Give the reminder a name'
                          : null,
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  children: <Widget>[
                    for (final ReminderKind kind in ReminderKind.values)
                      ChoiceChip(
                        label: Text(kind.label),
                        selected: _kind == kind,
                        onSelected: (_) => setState(() => _kind = kind),
                      ),
                  ],
                ),
                const SizedBox(height: 12),
                DatePickerField(
                  label: 'When',
                  value: _date,
                  onChanged: (DateTime next) => setState(() => _date = next),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _note,
                  maxLines: 2,
                  decoration: const InputDecoration(labelText: 'Note (optional)'),
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: () {
                    if (_formKey.currentState?.validate() != true) return;
                    Navigator.of(context).pop(
                      ReminderDraft(
                        title: _title.text.trim(),
                        kind: _kind,
                        dueAt: _date,
                        note: _note.text.trim().isEmpty
                            ? null
                            : _note.text.trim(),
                      ),
                    );
                  },
                  child: const Text('Add reminder'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
