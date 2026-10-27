import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../domain/member.dart';
import '../../../domain/enums.dart';
import '../../../domain/property.dart';
import '../../scope.dart';
import '../../widgets/layout.dart';
import '../confirm/confirm_setup_screen.dart';
import 'documents_screen.dart';
import 'members_screen.dart';
import 'privacy_screen.dart';
import 'spending_screen.dart';

class MoreScreen extends StatelessWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final store = MoveInScope.of(context);
    final Property? property = store.data.property;
    final Member? current = store.data.currentMember;

    return Scaffold(
      appBar: AppBar(title: const Text('More')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
          children: <Widget>[
            if (property != null)
              AppCard(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        const Icon(Icons.house_outlined),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            property.shortAddress,
                            style: theme.textTheme.titleMedium,
                          ),
                        ),
                        if (property.isDemoData)
                          const StatusPill(
                            label: 'Demo data',
                            tone: StatusTone.warning,
                          ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      property.displayAddress,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      <String>[
                        property.tenure.label,
                        if (current != null)
                          'Acting as ${current.name} (${current.role.label})',
                        'Source: ${property.addressSource}',
                      ].join(' · '),
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
            if (store.lastPersistenceError != null) ...<Widget>[
              const SizedBox(height: 12),
              NoticeBanner(
                tone: NoticeTone.warning,
                icon: Icons.save_outlined,
                message: store.lastPersistenceError!,
              ),
            ],
            const SizedBox(height: 16),
            AppCard(
              child: Column(
                children: <Widget>[
                  _NavTile(
                    icon: Icons.tune,
                    title: 'Household setup',
                    subtitle: 'Confirm providers and fill in missing details',
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => const ConfirmSetupScreen(),
                      ),
                    ),
                  ),
                  const Divider(height: 1),
                  _NavTile(
                    icon: Icons.group_outlined,
                    title: 'Household members',
                    subtitle: '${store.data.members.length} people · roles and access',
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(builder: (_) => const MembersScreen()),
                    ),
                  ),
                  const Divider(height: 1),
                  _NavTile(
                    icon: Icons.folder_outlined,
                    title: 'Documents',
                    subtitle: '${store.data.documents.length} stored records',
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(builder: (_) => const DocumentsScreen()),
                    ),
                  ),
                  const Divider(height: 1),
                  _NavTile(
                    icon: Icons.insights_outlined,
                    title: 'Spending summary',
                    subtitle: 'Monthly and yearly totals from recorded bills',
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(builder: (_) => const SpendingScreen()),
                    ),
                  ),
                  const Divider(height: 1),
                  _NavTile(
                    icon: Icons.lock_outline,
                    title: 'Data and privacy',
                    subtitle: 'Where every value comes from',
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(builder: (_) => const PrivacyScreen()),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            SectionCard(
              title: 'Try it out',
              subtitle: 'Demo helpers, so the whole journey can be explored offline.',
              child: Column(
                children: <Widget>[
                  _NavTile(
                    icon: Icons.science_outlined,
                    title: 'Load the example household',
                    subtitle: 'Fictional address, demo providers, mixed '
                        'confirmation states',
                    onTap: () async {
                      final bool ok = await confirmAction(
                        context,
                        title: 'Load the example household?',
                        message: 'This replaces what is currently stored on this '
                            'device with the demo household.',
                        confirmLabel: 'Load example',
                        destructive: true,
                      );
                      if (!ok) return;
                      await store.loadDemoHousehold();
                    },
                  ),
                  const Divider(height: 1),
                  _NavTile(
                    icon: Icons.restart_alt,
                    title: 'Start over',
                    subtitle: 'Clear everything and return to address entry',
                    onTap: () async {
                      final bool ok = await confirmAction(
                        context,
                        title: 'Start over?',
                        message: 'The household, bills, documents and reminders '
                            'on this device will be deleted.',
                        confirmLabel: 'Delete and start over',
                        destructive: true,
                      );
                      if (!ok) return;
                      await store.resetAll();
                    },
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            Text(
              'HomeLedger 0.1.0 · local-first preview\n'
              'A record-keeping tool. It does not pay bills, and it never '
              'invents an amount or a payment date.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
                height: 1.4,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Center(
              child: Text(
                'Last saved ${formatDateCompact(DateTime.now())}',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NavTile extends StatelessWidget {
  const _NavTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return ListTile(
      leading: Icon(icon, size: 20),
      title: Text(title, style: theme.textTheme.bodyLarge),
      subtitle: Text(
        subtitle,
        style: theme.textTheme.bodySmall?.copyWith(
          color: theme.colorScheme.onSurfaceVariant,
        ),
      ),
      trailing: const Icon(Icons.chevron_right, size: 18),
      onTap: onTap,
    );
  }
}
