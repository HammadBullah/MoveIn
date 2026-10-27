import 'package:flutter/material.dart';

import '../../scope.dart';
import '../../widgets/layout.dart';

/// Where every piece of information comes from, in one place.
///
/// This is the screen to read before trusting the app with anything: it states
/// what is automatic, what is not, and what is never derived.
class PrivacyScreen extends StatelessWidget {
  const PrivacyScreen({super.key});

  static const List<(String, String, String)> _sources = <(String, String, String)>[
    (
      'Exact property address',
      'Address lookup service (Ordnance Survey Places, or another licensed provider) via the HomeLedger API',
      'Automatic, with your postcode'
    ),
    (
      'Electricity supplier',
      'Official supplier lookup; sometimes needs your MPAN or a call to the network operator',
      'Partly'
    ),
    (
      'Gas supplier',
      'Official gas supplier lookup; may need your MPRN',
      'Partly'
    ),
    (
      'Water provider',
      'Postcode-based provider lookup (Water UK)',
      'Often'
    ),
    (
      'Local council',
      'Postcode-based council lookup (GOV.UK)',
      'Usually'
    ),
    (
      'Council tax band, balance and instalments',
      'Council account, bill upload or manual entry. The band is public; the balance is not',
      'Not from the address'
    ),
    (
      'Electricity or gas bill amount',
      'Bill upload, provider integration or manual entry',
      'Only with evidence'
    ),
    (
      'Broadband provider and amount',
      'Bill upload, account connection or your own entry',
      'Not from the address'
    ),
    (
      'Payment status',
      'Bill evidence or authorised financial data',
      'Partly'
    ),
    (
      'Bank payment date',
      'Authorised Open Banking connection, with explicit consent',
      'Only with consent'
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final store = MoveInScope.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Data and privacy')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
          children: <Widget>[
            SectionCard(
              title: 'Where each piece of information comes from',
              subtitle: 'Nothing on this list is guessed, and nothing is scraped.',
              child: Column(
                children: <Widget>[
                  for (final (String, String, String) row in _sources)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(row.$1, style: theme.textTheme.bodyMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                          )),
                          const SizedBox(height: 2),
                          Text(
                            row.$2,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                              height: 1.35,
                            ),
                          ),
                          const SizedBox(height: 4),
                          StatusPill(label: row.$3, tone: StatusTone.neutral),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            const SectionCard(
              title: 'In this build',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    '• Everything stays on this device, in local storage.\n'
                    '• No account, no server, no analytics, no third-party SDKs.\n'
                    '• Addresses and providers come from built-in demo data, '
                    'clearly labelled "(demo)".\n'
                    '• The official lookup links open in your browser; the app '
                    'does not sign in to any provider for you.',
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            SectionCard(
              title: 'What a deployed version must add',
              child: Text(
                '• Address lookups proxied through the API so the licence key '
                'stays server-side.\n'
                '• Encrypted document storage with a retention policy.\n'
                '• Authentication, per-household access control and an audit log '
                'of who changed what.\n'
                '• UK GDPR duties: lawful basis, minimal collection, export and '
                'erasure.\n'
                '• Open Banking only through an FCA-authorised provider, with '
                'explicit consent that can be withdrawn.',
                style: theme.textTheme.bodySmall?.copyWith(height: 1.5),
              ),
            ),
            const SizedBox(height: 20),
            OutlinedButton.icon(
              onPressed: () async {
                final bool ok = await confirmAction(
                  context,
                  title: 'Delete everything?',
                  message: 'This removes the household, bills, documents and '
                      'reminders from this device. It cannot be undone.',
                  confirmLabel: 'Delete my data',
                  destructive: true,
                );
                if (!ok) return;
                await store.resetAll();
                if (context.mounted) Navigator.of(context).pop();
              },
              icon: const Icon(Icons.delete_forever_outlined),
              label: const Text('Delete all my data'),
            ),
            const SizedBox(height: 12),
            Text(
              'HomeLedger is not affiliated with any energy, water or council '
              'provider. It is a record-keeping tool, not a billing service.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
