import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../domain/app_data.dart';
import '../domain/bill.dart';
import '../domain/document.dart';
import '../domain/enums.dart';
import '../domain/field.dart';
import '../domain/household_service.dart';
import '../domain/member.dart';
import '../domain/property.dart';
import 'demo_data.dart';
import 'lookup/lookup_links.dart';
import 'lookup/provider_lookup_service.dart';

/// Single source of truth for the app.
///
/// Local-first: everything is stored as one JSON document in
/// `SharedPreferences`. The same [AppData] shape is what the Flask API will
/// return, so swapping this for an HTTP-backed repository is a contained change
/// (see `AppRepository` in `server/README.md`).
class AppStore extends ChangeNotifier {
  AppStore({SharedPreferences? preferences}) : _preferences = preferences;

  static const String storageKey = 'home_ledger.state.v1';

  SharedPreferences? _preferences;
  AppData _data = AppData.empty;
  bool _loaded = false;
  final Random _random = Random();

  AppData get data => _data;
  bool get isLoaded => _loaded;

  /// Set once a save has failed, so the UI can warn rather than silently
  /// losing the resident's data.
  String? lastPersistenceError;

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  Future<void> load() async {
    if (_loaded) return;
    _preferences ??= await SharedPreferences.getInstance();
    final String? raw = _preferences!.getString(storageKey);
    if (raw != null && raw.isNotEmpty) {
      try {
        final Object? decoded = jsonDecode(raw);
        if (decoded is Map<String, dynamic>) {
          _data = AppData.fromJson(decoded);
        }
      } catch (error) {
        // Corrupt local state must not brick the app: start clean and tell the
        // resident rather than throwing on launch.
        lastPersistenceError = 'Saved data could not be read ($error).';
        _data = AppData.empty;
      }
    }
    _loaded = true;
    notifyListeners();
  }

  Future<void> _persist() async {
    _preferences ??= await SharedPreferences.getInstance();
    try {
      final bool ok = await _preferences!
          .setString(storageKey, jsonEncode(_data.toJson()));
      lastPersistenceError = ok ? null : 'Changes could not be saved.';
    } catch (error) {
      lastPersistenceError = 'Changes could not be saved ($error).';
    }
  }

  Future<void> _commit(AppData next) async {
    _data = next;
    notifyListeners();
    await _persist();
  }

  String _newId(String prefix) {
    final int stamp = DateTime.now().microsecondsSinceEpoch;
    final int noise = _random.nextInt(1 << 20);
    return '$prefix-$stamp-$noise';
  }

  // ---------------------------------------------------------------------------
  // Onboarding
  // ---------------------------------------------------------------------------

  /// Creates the household from a confirmed property and the service slots the
  /// resident wants to track. Providers start unknown: on purpose.
  Future<void> createHousehold({
    required AddressCandidate address,
    required Tenure tenure,
    required List<ServiceKind> services,
    required String residentName,
    bool isDemoData = false,
  }) async {
    final String propertyId = _newId('prop');
    final Property property = Property(
      id: propertyId,
      line1: address.line1,
      line2: address.line2,
      town: address.town,
      postcode: address.postcode,
      uprn: address.uprn,
      tenure: tenure,
      addressSource: address.source,
      isDemoData: isDemoData,
    );

    final List<HouseholdService> slots = services
        .map(
          (ServiceKind kind) => HouseholdService(
            id: _newId('svc'),
            propertyId: propertyId,
            kind: kind,
            lookupKeys: lookupKeysFor(kind),
          ),
        )
        .toList();

    final Member owner = Member(
      id: _newId('member'),
      name: residentName.trim().isEmpty ? 'You' : residentName.trim(),
      role: MemberRole.owner,
      isCurrentUser: true,
    );

    await _commit(
      AppData(
        property: property,
        services: slots,
        members: <Member>[owner],
        currentMemberId: owner.id,
        isDemoData: isDemoData,
        onboardingComplete: false,
      ),
    );
  }

  Future<void> replaceProperty({
    required AddressCandidate address,
    required Tenure tenure,
  }) async {
    final Property? current = _data.property;
    if (current == null) return;
    await _commit(
      _data.copyWith(
        property: Property(
          id: current.id,
          line1: address.line1,
          line2: address.line2,
          town: address.town,
          postcode: address.postcode,
          uprn: address.uprn,
          tenure: tenure,
          addressSource: address.source,
          isDemoData: current.isDemoData,
        ),
      ),
    );
  }

  Future<void> setTenure(Tenure tenure) async {
    final Property? current = _data.property;
    if (current == null) return;
    await _commit(_data.copyWith(property: current.copyWith(tenure: tenure)));
  }

  Future<void> completeOnboarding() async {
    await _commit(_data.copyWith(onboardingComplete: true));
  }

  static List<String> lookupKeysFor(ServiceKind kind) {
    switch (kind) {
      case ServiceKind.electricity:
        return <String>[LookupLinks.electricitySupplier.key];
      case ServiceKind.gas:
        return <String>[LookupLinks.gasSupplier.key];
      case ServiceKind.water:
      case ServiceKind.wastewater:
        return <String>[LookupLinks.waterAndSewerage.key];
      case ServiceKind.councilTax:
        return <String>[LookupLinks.councilTax.key, LookupLinks.findCouncil.key];
      case ServiceKind.tvLicence:
        return <String>[LookupLinks.tvLicence.key];
      case ServiceKind.broadband:
      case ServiceKind.homeInsurance:
      case ServiceKind.other:
        return const <String>[];
    }
  }

  // ---------------------------------------------------------------------------
  // Services
  // ---------------------------------------------------------------------------

  Future<void> addService(ServiceKind kind) async {
    final Property? property = _data.property;
    if (property == null) return;
    if (_data.serviceFor(kind) != null) return;
    final HouseholdService service = HouseholdService(
      id: _newId('svc'),
      propertyId: property.id,
      kind: kind,
      lookupKeys: lookupKeysFor(kind),
    );
    await _commit(
      _data.copyWith(services: <HouseholdService>[..._data.services, service]),
    );
  }

  Future<void> removeService(ServiceKind kind) async {
    await _commit(
      _data.copyWith(
        services: _data.services
            .where((HouseholdService s) => s.kind != kind)
            .toList(),
      ),
    );
  }

  Future<void> _updateService(
    ServiceKind kind,
    HouseholdService Function(HouseholdService service) transform,
  ) async {
    final List<HouseholdService> next = _data.services.map((HouseholdService s) {
      if (s.kind != kind) return s;
      return transform(s);
    }).toList();
    await _commit(_data.copyWith(services: next));
  }

  /// Applies lookup results. Anything already confirmed by the resident is
  /// never overwritten by a suggestion.
  Future<void> applySuggestions(List<ProviderSuggestion> suggestions) async {
    final List<HouseholdService> next = _data.services.map((HouseholdService s) {
      for (final ProviderSuggestion suggestion in suggestions) {
        if (suggestion.kind != s.kind) continue;
        if (s.provider.isConfirmed || s.provider.source.isHumanConfirmed) {
          return s;
        }
        return s.copyWith(
          provider: suggestion.toField(),
          lookupKeys: suggestion.lookupKey == null
              ? s.lookupKeys
              : <String>{...s.lookupKeys, suggestion.lookupKey!}.toList(),
        );
      }
      return s;
    }).toList();
    await _commit(_data.copyWith(services: next));
  }

  Future<void> confirmProvider(ServiceKind kind) => _updateService(
        kind,
        (HouseholdService s) => s.copyWith(provider: s.provider.confirm()),
      );

  Future<void> rejectProvider(ServiceKind kind) => _updateService(
        kind,
        (HouseholdService s) => s.copyWith(
          provider: s.provider.reject(
            note: 'Resident said "${s.provider.value}" is not correct.',
          ),
        ),
      );

  Future<void> setProviderManually(ServiceKind kind, String name) =>
      _updateService(
        kind,
        (HouseholdService s) => s.copyWith(
          provider: s.provider.edited(name.trim()),
        ),
      );

  Future<void> setAccountNumber(ServiceKind kind, String value) =>
      _updateService(
        kind,
        (HouseholdService s) => s.copyWith(
          accountNumber: s.accountNumber.edited(value.trim()),
        ),
      );

  Future<void> setServiceAmount(
    ServiceKind kind, {
    required int amountMinor,
    required PaymentFrequency frequency,
  }) =>
      _updateService(
        kind,
        (HouseholdService s) => s.copyWith(
          amountMinor: s.amountMinor.edited(amountMinor),
          frequency: frequency,
        ),
      );

  Future<void> setServiceDueDate(ServiceKind kind, DateTime date) =>
      _updateService(
        kind,
        (HouseholdService s) => s.copyWith(
          nextDueDate: s.nextDueDate.edited(date),
        ),
      );

  // ---------------------------------------------------------------------------
  // Bills
  // ---------------------------------------------------------------------------

  Future<void> addBill(Bill bill) async {
    await _commit(_data.copyWith(bills: <Bill>[..._data.bills, bill]));
  }

  /// Convenience wrapper that builds a bill from values the resident confirmed
  /// in the UI.
  Future<Bill> recordBill({
    required ServiceKind kind,
    required int amountMinor,
    required DateTime dueDate,
    String? providerName,
    PaymentFrequency? frequency,
    String? documentId,
    bool isEstimate = false,
    String? notes,
  }) async {
    final Property? property = _data.property;
    final Bill bill = Bill(
      id: _newId('bill'),
      propertyId: property?.id ?? 'unknown',
      kind: kind,
      provider: providerName == null || providerName.trim().isEmpty
          ? const Field<String>.missing()
          : Field<String>.confirmed(providerName.trim()),
      amountMinor: Field<int>.confirmed(
        amountMinor,
        source: isEstimate ? FieldSource.estimate : FieldSource.userEntered,
      ),
      dueDate: Field<DateTime>.confirmed(dueDate),
      frequency: frequency ?? PaymentFrequency.monthly,
      documentId: documentId,
      notes: notes,
    );
    await addBill(bill);
    return bill;
  }

  Future<void> updateBill(Bill bill) async {
    final List<Bill> next = _data.bills
        .map((Bill existing) => existing.id == bill.id ? bill : existing)
        .toList();
    await _commit(_data.copyWith(bills: next));
  }

  Future<void> setBillPaid(String billId, bool paid) async {
    final List<Bill> next = _data.bills.map((Bill bill) {
      if (bill.id != billId) return bill;
      return bill.copyWith(
        paymentStatus: paid ? PaymentStatus.paid : PaymentStatus.unknown,
      );
    }).toList();
    await _commit(_data.copyWith(bills: next));
  }

  Future<void> deleteBill(String billId) async {
    await _commit(
      _data.copyWith(
        bills: _data.bills.where((Bill b) => b.id != billId).toList(),
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Documents, reminders and members
  // ---------------------------------------------------------------------------

  Future<DocumentRecord> addDocument({
    required DocumentKind kind,
    required String title,
    String? providerName,
    String? fileName,
    String? extractedText,
    String? notes,
    String? billId,
  }) async {
    final DocumentRecord record = DocumentRecord(
      id: _newId('doc'),
      propertyId: _data.property?.id ?? 'unknown',
      kind: kind,
      title: title,
      providerName: providerName,
      fileName: fileName,
      extractedText: extractedText,
      notes: notes,
      billId: billId,
      addedAt: DateTime.now(),
    );
    await _commit(
      _data.copyWith(documents: <DocumentRecord>[record, ..._data.documents]),
    );
    return record;
  }

  Future<void> deleteDocument(String id) async {
    await _commit(
      _data.copyWith(
        documents: _data.documents.where((DocumentRecord d) => d.id != id).toList(),
      ),
    );
  }

  Future<void> addReminder({
    required ReminderKind kind,
    required String title,
    required DateTime dueAt,
    String? note,
    String? billId,
  }) async {
    final Reminder reminder = Reminder(
      id: _newId('rem'),
      propertyId: _data.property?.id ?? 'unknown',
      kind: kind,
      title: title,
      dueAt: dueAt,
      note: note,
      billId: billId,
    );
    await _commit(_data.copyWith(reminders: <Reminder>[..._data.reminders, reminder]));
  }

  Future<void> setReminderDone(String id, bool done) async {
    final List<Reminder> next = _data.reminders.map((Reminder r) {
      if (r.id != id) return r;
      return r.copyWith(isDone: done);
    }).toList();
    await _commit(_data.copyWith(reminders: next));
  }

  Future<void> deleteReminder(String id) async {
    await _commit(
      _data.copyWith(
        reminders: _data.reminders.where((Reminder r) => r.id != id).toList(),
      ),
    );
  }

  Future<void> addMember(String name, MemberRole role, {String? email}) async {
    final Member member = Member(
      id: _newId('member'),
      name: name.trim(),
      role: role,
      email: email?.trim(),
      hasAcceptedInvite: false,
    );
    await _commit(_data.copyWith(members: <Member>[..._data.members, member]));
  }

  Future<void> updateMemberRole(String memberId, MemberRole role) async {
    final List<Member> next = _data.members.map((Member m) {
      if (m.id != memberId) return m;
      return m.copyWith(role: role);
    }).toList();
    await _commit(_data.copyWith(members: next));
  }

  Future<void> removeMember(String memberId) async {
    final List<Member> next =
        _data.members.where((Member m) => m.id != memberId).toList();
    await _commit(
      _data.copyWith(
        members: next,
        // Keep a valid current member if the active one was removed.
        currentMemberId: next.any((Member m) => m.id == _data.currentMemberId)
            ? _data.currentMemberId
            : next.firstOrNull?.id,
      ),
    );
  }

  /// Demo aid: switch which role the UI is acting as, so the permission rules
  /// can be demonstrated without a backend.
  Future<void> setCurrentMember(String memberId) async {
    await _commit(_data.copyWith(currentMemberId: memberId));
  }

  // ---------------------------------------------------------------------------
  // Seeding and reset
  // ---------------------------------------------------------------------------

  /// Loads the fully worked example household.
  ///
  /// Everything it creates is flagged [AppData.isDemoData] and every provider
  /// name is suffixed "(demo)" so nobody mistakes it for real data.
  Future<void> loadDemoHousehold() async {
    await _commit(DemoData.build(now: DateTime.now(), idSeed: _newId('demo')));
  }

  Future<void> resetAll() async {
    await _commit(AppData.empty);
  }
}

extension _FirstOrNull<T> on List<T> {
  T? get firstOrNull => isEmpty ? null : first;
}
