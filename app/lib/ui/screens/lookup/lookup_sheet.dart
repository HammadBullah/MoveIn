import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../data/lookup/lookup_links.dart';
import '../../../domain/enums.dart';
import '../../widgets/layout.dart';

/// Shows the official place to find a provider, and explains why we cannot do
/// it for the resident.
Future<void> showLookupSheet(
  BuildContext context, {
  required String title,
  required List<String> keys,
  ServiceKind? kind,
  String? explanation,
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (BuildContext context) {
      final List<LookupLink> links = keys
          .map(LookupLinks.byKey)
          .whereType<LookupLink>()
          .toList();

      return SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              if (kind != null) ...<Widget>[
                const SizedBox(height: 6),
                Text(
                  kind.discoveryHint,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                        height: 1.35,
                      ),
                ),
              ],
              if (explanation != null) ...<Widget>[
                const SizedBox(height: 6),
                Text(
                  explanation,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                ),
              ],
              const SizedBox(height: 16),
              if (links.isEmpty)
                const NoticeBanner(
                  message: 'There is no public lookup for this kind of service. '
                      'Add the provider from a bill, a statement or by typing it '
                      'in yourself.',
                )
              else
                for (final LookupLink link in links)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: AppCard(
                      child: ListTile(
                        leading: const Icon(Icons.open_in_new),
                        title: Text(link.title),
                        subtitle: Text(
                          '${link.operator}\n${link.description}',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        isThreeLine: true,
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () => openLookup(context, link),
                      ),
                    ),
                  ),
              const SizedBox(height: 4),
              const NoticeBanner(
                tone: NoticeTone.info,
                message: 'HomeLedger opens the official page in your browser. '
                    'It does not sign in to provider accounts for you.',
              ),
            ],
          ),
        ),
      );
    },
  );
}

Future<void> openLookup(BuildContext context, LookupLink link) async {
  final Uri uri = Uri.parse(link.url);
  final bool launched =
      await launchUrl(uri, mode: LaunchMode.externalApplication);
  if (!launched && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Could not open ${link.operator}. URL: ${link.url}')),
    );
  }
}
