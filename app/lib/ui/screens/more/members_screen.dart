import 'package:flutter/material.dart';

import '../../../domain/enums.dart';
import '../../../domain/member.dart';
import '../../scope.dart';
import '../../widgets/layout.dart';

/// Shared household access with roles.
///
/// Roles are enforced in the UI here. A real deployment must enforce the same
/// rules in the API, because a client-side check protects nobody.
class MembersScreen extends StatelessWidget {
  const MembersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final store = MoveInScope.of(context);
    final List<Member> members = store.data.members;
    final Member? current = store.data.currentMember;
    final bool canManage = store.data.canManageHousehold;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Household members'),
        actions: <Widget>[
          IconButton(
            tooltip: 'Invite someone',
            onPressed: canManage ? () => _invite(context) : null,
            icon: const Icon(Icons.person_add_alt),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
          children: <Widget>[
            const NoticeBanner(
              message: 'Owner: full control. Tenant: can edit bills and '
                  'documents. Housemate: can add and edit bills. Viewer: can see '
                  'the household but not the amounts.',
            ),
            const SizedBox(height: 16),
            for (final Member member in members)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: AppCard(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    children: <Widget>[
                      Row(
                        children: <Widget>[
                          CircleAvatar(
                            radius: 18,
                            child: Text(
                              member.name.isEmpty
                                  ? '?'
                                  : member.name
                                      .substring(0, 1)
                                      .toUpperCase(),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: <Widget>[
                                Text(member.name, style: theme.textTheme.bodyLarge),
                                const SizedBox(height: 2),
                                Text(
                                  <String>[
                                    member.role.label,
                                    if (member.isCurrentUser) 'you',
                                    if (!member.hasAcceptedInvite)
                                      'invite not accepted',
                                  ].join(' · '),
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: theme.colorScheme.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          if (canManage && !member.isCurrentUser)
                            IconButton(
                              tooltip: 'Remove from household',
                              onPressed: () async {
                                final bool ok = await confirmAction(
                                  context,
                                  title: 'Remove ${member.name}?',
                                  message: 'They lose access to this household '
                                      'immediately.',
                                  confirmLabel: 'Remove',
                                  destructive: true,
                                );
                                if (!ok) return;
                                await store.removeMember(member.id);
                              },
                              icon: const Icon(Icons.person_remove_outlined),
                            ),
                        ],
                      ),
                      if (canManage) ...<Widget>[
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 6,
                          children: <Widget>[
                            for (final MemberRole role in MemberRole.values)
                              ChoiceChip(
                                label: Text(role.label),
                                selected: member.role == role,
                                onSelected: (_) =>
                                    store.updateMemberRole(member.id, role),
                              ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 16),
            SectionCard(
              title: 'Preview a role',
              subtitle: 'Switch the role the app is acting as. Useful for '
                  'checking what a housemate or viewer can see.',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: <Widget>[
                      for (final Member member in members)
                        ChoiceChip(
                          label: Text('${member.name.split(' ').first} · ${member.role.label}'),
                          selected: current?.id == member.id,
                          onSelected: (_) => store.setCurrentMember(member.id),
                        ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'Viewers do not see amounts. This is a preview of the rules; '
                    'the API will enforce the same permissions.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                      height: 1.35,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _invite(BuildContext context) async {
    final MemberDraft? draft = await showDialog<MemberDraft>(
      context: context,
      builder: (_) => const _InviteDialog(),
    );
    if (draft == null || !context.mounted) return;
    await MoveInScope.read(context)
        .addMember(draft.name, draft.role, email: draft.email);
  }
}

class MemberDraft {
  const MemberDraft({required this.name, required this.role, this.email});

  final String name;
  final MemberRole role;
  final String? email;
}

class _InviteDialog extends StatefulWidget {
  const _InviteDialog();

  @override
  State<_InviteDialog> createState() => _InviteDialogState();
}

class _InviteDialogState extends State<_InviteDialog> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _name = TextEditingController();
  final TextEditingController _email = TextEditingController();
  MemberRole _role = MemberRole.housemate;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Invite a household member'),
      content: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              TextFormField(
                controller: _name,
                autofocus: true,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(labelText: 'Name'),
                validator: (String? value) =>
                    (value == null || value.trim().isEmpty) ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(
                  labelText: 'Email (optional)',
                  helperText: 'Used to send the invite when the API is live.',
                ),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 6,
                children: <Widget>[
                  for (final MemberRole role in MemberRole.values)
                    ChoiceChip(
                      label: Text(role.label),
                      selected: _role == role,
                      onSelected: (_) => setState(() => _role = role),
                    ),
                ],
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
              MemberDraft(
                name: _name.text.trim(),
                role: _role,
                email: _email.text.trim().isEmpty ? null : _email.text.trim(),
              ),
            );
          },
          child: const Text('Add member'),
        ),
      ],
    );
  }
}
