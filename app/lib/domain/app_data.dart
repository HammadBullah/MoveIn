import '../core/json.dart';
import 'bill.dart';
import 'document.dart';
import 'enums.dart';
import 'household_service.dart';
import 'member.dart';
import 'property.dart';

/// The whole local state of the app.
///
/// One aggregate, one JSON blob. When the Flask API lands this becomes the
/// shape the client hydrates from `GET /api/households/<id>`.
class AppData {
  const AppData({
    this.property,
    this.services = const <HouseholdService>[],
    this.bills = const <Bill>[],
    this.documents = const <DocumentRecord>[],
    this.reminders = const <Reminder>[],
    this.members = const <Member>[],
    this.currentMemberId,
    this.isDemoData = false,
    this.onboardingComplete = false,
  });

  final Property? property;
  final List<HouseholdService> services;
  final List<Bill> bills;
  final List<DocumentRecord> documents;
  final List<Reminder> reminders;
  final List<Member> members;
  final String? currentMemberId;
  final bool isDemoData;
  final bool onboardingComplete;

  static const AppData empty = AppData();

  bool get hasProperty => property != null;

  Member? get currentMember {
    for (final Member member in members) {
      if (member.id == currentMemberId) return member;
    }
    return members.isEmpty ? null : members.first;
  }

  MemberRole get currentRole => currentMember?.role ?? MemberRole.owner;

  bool get canEditBills => currentRole.canEditBills;
  bool get canManageHousehold => currentRole.canManageHousehold;
  bool get canSeeAmounts => currentRole.canSeeAmounts;

  AppData copyWith({
    Property? property,
    List<HouseholdService>? services,
    List<Bill>? bills,
    List<DocumentRecord>? documents,
    List<Reminder>? reminders,
    List<Member>? members,
    String? currentMemberId,
    bool? isDemoData,
    bool? onboardingComplete,
  }) {
    return AppData(
      property: property ?? this.property,
      services: services ?? this.services,
      bills: bills ?? this.bills,
      documents: documents ?? this.documents,
      reminders: reminders ?? this.reminders,
      members: members ?? this.members,
      currentMemberId: currentMemberId ?? this.currentMemberId,
      isDemoData: isDemoData ?? this.isDemoData,
      onboardingComplete: onboardingComplete ?? this.onboardingComplete,
    );
  }

  HouseholdService? serviceFor(ServiceKind kind) {
    for (final HouseholdService service in services) {
      if (service.kind == kind) return service;
    }
    return null;
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'version': 1,
        'property': property?.toJson(),
        'services': services.map((HouseholdService s) => s.toJson()).toList(),
        'bills': bills.map((Bill b) => b.toJson()).toList(),
        'documents': documents.map((DocumentRecord d) => d.toJson()).toList(),
        'reminders': reminders.map((Reminder r) => r.toJson()).toList(),
        'members': members.map((Member m) => m.toJson()).toList(),
        'currentMemberId': currentMemberId,
        'isDemoData': isDemoData,
        'onboardingComplete': onboardingComplete,
      };

  static AppData fromJson(Map<String, dynamic> json) {
    return AppData(
      property: Property.fromJson(asMap(json['property'])),
      services: asMapList(json['services'])
          .map(HouseholdService.fromJson)
          .whereType<HouseholdService>()
          .toList(),
      bills: asMapList(json['bills'])
          .map(Bill.fromJson)
          .whereType<Bill>()
          .toList(),
      documents: asMapList(json['documents'])
          .map(DocumentRecord.fromJson)
          .whereType<DocumentRecord>()
          .toList(),
      reminders: asMapList(json['reminders'])
          .map(Reminder.fromJson)
          .whereType<Reminder>()
          .toList(),
      members: asMapList(json['members'])
          .map(Member.fromJson)
          .whereType<Member>()
          .toList(),
      currentMemberId: asStringOrNull(json['currentMemberId']),
      isDemoData: asBool(json['isDemoData']),
      onboardingComplete: asBool(json['onboardingComplete']),
    );
  }
}
