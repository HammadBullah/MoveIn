import '../core/json.dart';
import 'enums.dart';

/// A person with access to the household.
///
/// Roles are enforced in the UI today and must be enforced again server-side
/// before this becomes a multi-user product.
class Member {
  const Member({
    required this.id,
    required this.name,
    this.role = MemberRole.owner,
    this.email,
    this.isCurrentUser = false,
    this.hasAcceptedInvite = true,
  });

  final String id;
  final String name;
  final MemberRole role;
  final String? email;
  final bool isCurrentUser;
  final bool hasAcceptedInvite;

  bool can(bool Function(MemberRole role) test) => test(role);

  Member copyWith({String? name, MemberRole? role, String? email}) => Member(
        id: id,
        name: name ?? this.name,
        role: role ?? this.role,
        email: email ?? this.email,
        isCurrentUser: isCurrentUser,
        hasAcceptedInvite: hasAcceptedInvite,
      );

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'name': name,
        'role': role.name,
        'email': email,
        'isCurrentUser': isCurrentUser,
        'hasAcceptedInvite': hasAcceptedInvite,
      };

  static Member? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final String id = asString(json['id']);
    if (id.isEmpty) return null;
    return Member(
      id: id,
      name: asString(json['name'], 'Resident'),
      role: _roleFromName(json['role']),
      email: asStringOrNull(json['email']),
      isCurrentUser: asBool(json['isCurrentUser']),
      hasAcceptedInvite: asBool(json['hasAcceptedInvite'], true),
    );
  }
}

MemberRole _roleFromName(Object? value) {
  final String name = asString(value);
  for (final MemberRole role in MemberRole.values) {
    if (role.name == name) return role;
  }
  return MemberRole.owner;
}
