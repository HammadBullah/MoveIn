import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../domain/document.dart';
import '../../../domain/enums.dart';
import '../../scope.dart';
import '../../widgets/layout.dart';

/// The household's document store: bills, statements, meter readings, policies.
///
/// This build keeps the text you paste. Real files need encrypted storage on the
/// server (`storageKey` in [DocumentRecord] is the hook for that) plus a
/// retention policy the resident can see.
class DocumentsScreen extends StatelessWidget {
  const DocumentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final store = MoveInScope.of(context);
    final List<DocumentRecord> documents = store.data.documents;

    return Scaffold(
      appBar: AppBar(title: const Text('Documents')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _addDocument(context),
        icon: const Icon(Icons.note_add_outlined),
        label: const Text('Add'),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 96),
          children: <Widget>[
            const NoticeBanner(
              icon: Icons.lock_outline,
              message: 'Documents are stored on this device in this build. '
                  'Uploaded files will be encrypted at rest server-side, with '
                  'access limited to household members.',
            ),
            const SizedBox(height: 16),
            if (documents.isEmpty)
              const EmptyState(
                icon: Icons.folder_open_outlined,
                title: 'No documents yet',
                message: 'Keep bills, statements, meter readings and policies '
                    'together so the household can find them later.',
              )
            else
              for (final DocumentRecord document in documents)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: AppCard(
                    onTap: () => _showDocument(context, document),
                    padding: const EdgeInsets.all(14),
                    child: Row(
                      children: <Widget>[
                        Icon(
                          switch (document.kind) {
                            DocumentKind.bill => Icons.receipt_long_outlined,
                            DocumentKind.statement => Icons.description_outlined,
                            DocumentKind.meterReading => Icons.speed_outlined,
                            DocumentKind.receipt => Icons.receipt_outlined,
                            DocumentKind.policy => Icons.policy_outlined,
                            DocumentKind.other => Icons.insert_drive_file_outlined,
                          },
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: <Widget>[
                              Text(document.title,
                                  style: theme.textTheme.bodyLarge),
                              const SizedBox(height: 2),
                              Text(
                                <String>[
                                  document.kind.label,
                                  if (document.providerName != null)
                                    document.providerName!,
                                  'Added ${formatDateCompact(document.addedAt)}',
                                ].join(' · '),
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const Icon(Icons.chevron_right, size: 18),
                      ],
                    ),
                  ),
                ),
          ],
        ),
      ),
    );
  }

  Future<void> _showDocument(BuildContext context, DocumentRecord document) async {
    final ThemeData theme = Theme.of(context);
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (BuildContext sheetContext) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(document.title, style: theme.textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(
                <String>[
                  document.kind.label,
                  if (document.providerName != null) document.providerName!,
                  if (document.fileName != null) document.fileName!,
                ].join(' · '),
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 12),
              ConstrainedBox(
                constraints: BoxConstraints(
                  maxHeight: MediaQuery.of(sheetContext).size.height * 0.4,
                ),
                child: SingleChildScrollView(
                  child: Text(
                    document.extractedText?.isNotEmpty == true
                        ? document.extractedText!
                        : (document.notes ?? 'No stored text for this document.'),
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontFamily: 'monospace',
                      height: 1.4,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Row(
                children: <Widget>[
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () async {
                        final bool ok = await confirmAction(
                          sheetContext,
                          title: 'Delete document?',
                          message: 'This removes the stored copy. Bills that were '
                              'created from it stay in your records.',
                          confirmLabel: 'Delete',
                          destructive: true,
                        );
                        if (!ok) return;
                        await MoveInScope.read(sheetContext)
                            .deleteDocument(document.id);
                        if (sheetContext.mounted) {
                          Navigator.of(sheetContext).pop();
                        }
                      },
                      icon: const Icon(Icons.delete_outline, size: 18),
                      label: const Text('Delete'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton(
                      onPressed: () => Navigator.of(sheetContext).pop(),
                      child: const Text('Close'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _addDocument(BuildContext context) async {
    final _DocumentDraft? draft = await showDialog<_DocumentDraft>(
      context: context,
      builder: (_) => const _AddDocumentDialog(),
    );
    if (draft == null || !context.mounted) return;
    await MoveInScope.read(context).addDocument(
      kind: draft.kind,
      title: draft.title,
      providerName: draft.provider,
      extractedText: draft.text,
      notes: 'Added manually.',
    );
  }
}

class _DocumentDraft {
  const _DocumentDraft({
    required this.title,
    required this.kind,
    this.provider,
    this.text,
  });

  final String title;
  final DocumentKind kind;
  final String? provider;
  final String? text;
}

class _AddDocumentDialog extends StatefulWidget {
  const _AddDocumentDialog();

  @override
  State<_AddDocumentDialog> createState() => _AddDocumentDialogState();
}

class _AddDocumentDialogState extends State<_AddDocumentDialog> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _title = TextEditingController();
  final TextEditingController _provider = TextEditingController();
  final TextEditingController _text = TextEditingController();
  DocumentKind _kind = DocumentKind.bill;

  @override
  void dispose() {
    _title.dispose();
    _provider.dispose();
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add a document'),
      content: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              TextFormField(
                controller: _title,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'Title'),
                validator: (String? value) =>
                    (value == null || value.trim().isEmpty) ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              InputDecorator(
                decoration: const InputDecoration(labelText: 'Type'),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<DocumentKind>(
                    value: _kind,
                    isExpanded: true,
                    isDense: true,
                    items: DocumentKind.values
                        .map(
                          (DocumentKind kind) => DropdownMenuItem<DocumentKind>(
                            value: kind,
                            child: Text(kind.label),
                          ),
                        )
                        .toList(),
                    onChanged: (DocumentKind? next) {
                      if (next != null) setState(() => _kind = next);
                    },
                  ),
                ),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _provider,
                decoration:
                    const InputDecoration(labelText: 'Provider (optional)'),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _text,
                maxLines: 5,
                decoration: const InputDecoration(
                  labelText: 'Text or notes (optional)',
                  hintText: 'Paste the key details you want to keep.',
                ),
              ),
            ],
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            if (_formKey.currentState?.validate() != true) return;
            Navigator.of(context).pop(
              _DocumentDraft(
                title: _title.text.trim(),
                kind: _kind,
                provider: _provider.text.trim().isEmpty
                    ? null
                    : _provider.text.trim(),
                text: _text.text.trim().isEmpty ? null : _text.text.trim(),
              ),
            );
          },
          child: const Text('Save'),
        ),
      ],
    );
  }
}
