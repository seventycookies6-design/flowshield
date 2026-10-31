import Foundation
import Testing
import BasaltCore
@testable import Basalt

private actor EngineTransport: HTTPTransport {
  var requests = 0
  func post(url: URL, json: Data, timeout: TimeInterval) async throws -> HTTPResponse {
    requests += 1
    return HTTPResponse(status: 200, body: Data(#"{"isPro":true,"status":"active","licenseKey":"test-key","email":"test@example.invalid","deviceCount":1,"deviceLimit":3}"#.utf8))
  }
}

@Suite(.serialized) @MainActor
struct AppModelTests {
  func readySettings() -> AppSettings {
    var s = AppSettings(); s.ensureProfiles(); s.ensureTemplates()
    s.notificationsEnabled = false; s.firstRunCompleted = true
    LegalTerms.accept(&s, now: Date()); return s
  }
  private func withModel(_ input: AppSettings? = nil,
    _ body: (AppModel, URL, EngineTransport) async throws -> Void) async throws {
    let dir = FileManager.default.temporaryDirectory.appendingPathComponent("basalt-e2e-unit-\(UUID().uuidString)")
    defer { try? FileManager.default.removeItem(at: dir) }
    var s = input ?? readySettings(); s.notificationsEnabled = false
    try await SettingsStore(url: dir.appendingPathComponent("settings.json")).save(s)
    let transport = EngineTransport()
    let client = LicenseClient(transport: transport, deviceId: "test-device", deviceName: "Test Mac", sleep: { _ in })
    let model = AppModel(options: LaunchOptions(arguments: ["Basalt", "--data-dir", dir.path, "--test-timings"]), licenseClient: client)
    await model.load()
    #expect(model.isReady)
    do { try await body(model, dir, transport) }
    catch { await model.shutdown(); throw error }
    await model.shutdown()
  }
  @Test func startIsDurableAndFreeCancelRecordsNothing() async throws {
    try await withModel { model, dir, _ in
      model.intention = "  Read chapter 3  "
      #expect(await model.start(minutes: 5, shield: .firm) == .started)
      let stored = try await SettingsStore(url: dir.appendingPathComponent("settings.json")).load()
      #expect(stored.activeSprint?.shield == .firm)
      #expect(stored.activeSprint?.intention == "Read chapter 3")
      await model.requestEnd()
      #expect(!model.isRunning)
      #expect(model.settings.sessions.isEmpty)
      #expect(model.settings.momentumScore == 0)
    }
  }
  @Test func termsAndFirstRunGateCommands() async throws {
    var s = readySettings(); s.termsAcceptedVersion = ""; s.firstRunCompleted = false
    try await withModel(s) { model, _, _ in
      #expect(await model.start() == .termsRequired)
      await model.acceptTerms()
      #expect(await model.start() == .firstRunRequired)
    }
  }
  @Test func sealedRejectsAllListMutationsAndProfilesCopyTheCurrentList() async throws {
    try await withModel { model, _, _ in
      var app = BlockedApp(); app.name = "Test app"; app.bundleIdentifier = "invalid.basalt.unit-test"
      #expect(await model.addBlockedApp(app))
      let original = model.settings.activeProfileId
      let copy = await model.addProfile(name: "School")
      #expect(copy != original)
      #expect(model.settings.activeProfileId == copy)
      #expect(model.settings.blockedApps == [app])
      #expect(await model.start(minutes: 5, shield: .sealed) == .started)
      let before = model.settings.profiles
      await model.removeBlockedApp(at: 0)
      await model.toggleBlockedApp(at: 0, enabled: false)
      await model.selectProfile(original)
      await model.renameProfile(copy!, name: "Changed")
      await model.deleteProfile(copy!)
      #expect(await model.addProfile(name: "Refused") == nil)
      #expect(model.settings.profiles == before)
      await model.cancel()
      #expect(model.canEditBlocklist)
    }
  }
  @Test func recoveryRestoresShieldAndEndAnywayRechecksWaitAndPhrase() async throws {
    var s = readySettings(); s.momentumScore = 50
    var sprint = RunningSprint(); sprint.startedUtc = Date().addingTimeInterval(-30)
    sprint.plannedMinutes = 5; sprint.shield = .sealed; sprint.activeProfileId = s.activeProfileId
    sprint.lastSeenUtc = Date(); sprint.watchedMinutes = 0.5; sprint.intention = "Keep reading"
    s.activeSprint = sprint
    try await withModel(s) { model, _, _ in
      #expect(model.activeSprint?.shield == .sealed)
      #expect(model.settings.defaultShield == .sealed)
      #expect(model.intention == "Keep reading")
      await model.cancel(); #expect(model.isRunning)
      await model.requestEnd()
      model.endConfirmation.phrase = "end my sprint"
      await model.endAnyway(); #expect(model.isRunning)
      try await Task.sleep(for: .seconds(8.1))
      model.endConfirmation.phrase = "wrong words"
      await model.endAnyway(); #expect(model.isRunning)
      model.endConfirmation.phrase = "END   my sprint"
      await model.endAnyway()
      #expect(!model.isRunning)
      #expect(model.settings.sessions.last?.endedEarly == true)
      #expect(model.settings.momentumScore == 30)
      model.journalText = "  Three pages.  "; await model.saveJournal()
      #expect(model.settings.sessions.last?.journal == "Three pages.")
    }
  }
  @Test func expiredTrialCannotStartOrEditProfiles() async throws {
    var s = readySettings(); s.trialStartedUtc = Date().addingTimeInterval(-8 * 86400)
    try await withModel(s) { model, _, _ in
      #expect(model.trialLocked)
      #expect(await model.start() == .accessLocked)
      #expect(await model.addProfile(name: "Refused") == nil)
    }
  }
  @Test func completedCycleRunsBreakThenNextSprint() async throws {
    var s = readySettings(); s.cycleSprints = 2
    var sprint = RunningSprint(); sprint.startedUtc = Date().addingTimeInterval(-299)
    sprint.plannedMinutes = 5; sprint.shield = .soft; sprint.activeProfileId = s.activeProfileId
    sprint.lastSeenUtc = Date(); sprint.watchedMinutes = 4.9; sprint.cycleSprintsPlanned = 2
    s.activeSprint = sprint
    try await withModel(s) { model, _, _ in
      try await Task.sleep(for: .seconds(2))
      await model.tick()
      #expect(model.isOnBreak)
      #expect(model.settings.sessions.last?.completed == true)
      #expect(model.settings.momentumScore == 5)
      await model.skipBreak()
      #expect(model.isRunning)
      #expect(model.cycle.sprintsDone == 1)
      #expect(model.activeSprint?.shield == .soft)
    }
  }
  @Test func activationLinkOnlyPrefillsAndLicenseUsesInjectedTransport() async throws {
    try await withModel { model, _, transport in
      model.handleURL(URL(string: "flowshield://activate?key=FS-1234-5678-9ABC-DEFG")!)
      #expect(model.licensePromptVisible)
      #expect(await transport.requests == 0)
      #expect(!model.settings.isPro)
      await model.activateLicense(key: "test-key", email: "test@example.invalid")
      #expect(model.settings.isPro)
      #expect(await transport.requests == 1)
      await model.deactivateLicense()
      #expect(!model.settings.isPro)
      #expect(model.settings.licenseKey.isEmpty)
    }
  }
  @Test func templateScheduleCrudAndExportStayLocal() async throws {
    try await withModel { model, dir, _ in
      var t = StudyTemplate(); t.name = "Reading"; t.sprintMinutes = 15; t.shield = .soft
      await model.saveTemplate(t)
      let template = try #require(model.settings.templates.first { $0.name == "Reading" })
      #expect(await model.applyTemplate(template.id))
      #expect(model.settings.defaultSprintMinutes == 15)
      var schedule = SprintSchedule(); schedule.templateId = template.id; schedule.days = [1, 2]
      await model.saveSchedule(schedule)
      #expect(model.settings.schedules.count == 1)
      await model.deleteTemplate(template.id)
      #expect(model.settings.schedules.isEmpty)
      let file = dir.appendingPathComponent("export.json")
      try model.exportAllData(to: file)
      let text = try String(contentsOf: file, encoding: .utf8)
      #expect(!text.contains("licenseKey"))
      #expect(text.contains("blocklistProfiles"))
    }
  }
  @Test func failedLoadCannotOverwriteAnUnsupportedSchemaThroughIntentMethods() async throws {
    let dir = FileManager.default.temporaryDirectory.appendingPathComponent("basalt-e2e-unit-schema-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }
    let file = dir.appendingPathComponent("settings.json")
    var future = readySettings(); future.schemaVersion = 999
    let original = try SettingsCoding.encoder().encode(future)
    try original.write(to: file)
    let transport = EngineTransport()
    let model = AppModel(options: LaunchOptions(arguments: ["Basalt", "--data-dir", dir.path]),
      licenseClient: LicenseClient(transport: transport, deviceId: "test", deviceName: "Test", sleep: { _ in }))
    await model.load()
    #expect(!model.isReady)
    await model.acceptTerms()
    await model.setSprintMinutes(45)
    await model.setTheme(.dark)
    #expect(try Data(contentsOf: file) == original)
    await model.shutdown()
  }
}
