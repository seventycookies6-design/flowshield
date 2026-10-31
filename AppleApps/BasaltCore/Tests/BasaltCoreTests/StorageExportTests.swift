import Foundation

import Testing

@testable import BasaltCore

struct StorageExportTests {
  @Test func csvCarriageReturnAndCRLF() {
    #expect(JournalExport.escapeCSV("a\rb") == "\"a\rb\"")
    #expect(JournalExport.escapeCSV("a\r\nb") == "\"a\r\nb\"")
    #expect(JournalExport.defuse("\r\nformula") == "'\r\nformula")
  }
  @Test func fractionalTimestampRoundTrips() throws {
    var s = FocusSession()
    s.startedUtc = instant().addingTimeInterval(0.123)
    let data = try SettingsCoding.encoder().encode(s)
    let restored = try SettingsCoding.decoder().decode(FocusSession.self, from: data)
    #expect(abs(restored.startedUtc.timeIntervalSince(s.startedUtc)) < 0.001)
  }
  @Test func emptySettingsDecodeWithAllDefaults() throws {
    let s = try SettingsCoding.decoder().decode(AppSettings.self, from: Data("{}".utf8))
    #expect(s == AppSettings())
    #expect(s.schemaVersion == 1)
    #expect(s.notificationsEnabled)
    #expect(s.showSoftOverlayEnabled)
    #expect(!s.globalHotkeyEnabled)
  }
  @Test func nullFieldsUseDefaults() throws {
    let s = try SettingsCoding.decoder().decode(
      AppSettings.self,
      from: Data("{\"defaultSprintMinutes\":null,\"sessions\":null,\"licenseKey\":null}".utf8))
    #expect(s.defaultSprintMinutes == 25)
    #expect(s.sessions.isEmpty)
    #expect(s.licenseKey == "")
  }
  @Test func modelsDecodeMissingFields() throws {
    let d = SettingsCoding.decoder()
    let b = Data("{}".utf8)
    #expect(try d.decode(RunningSprint.self, from: b).watchedMinutes == nil)
    #expect(try d.decode(FocusSession.self, from: b).intention.isEmpty)
    #expect(try d.decode(BlockedApp.self, from: b).isEnabled)
    #expect(try d.decode(StudyTemplate.self, from: b).sprintMinutes == 25)
    #expect(try d.decode(SprintSchedule.self, from: b).askFirst)
  }
  @Test func unknownShieldNormalizesToFirm() throws {
    #expect(
      try SettingsCoding.decoder().decode(StudyTemplate.self, from: Data("{\"shield\":99}".utf8))
        .shield == .firm)
  }
  @Test func settingsRoundTripEveryOperationalField() throws {
    var s = ready()
    s.ensureTemplates()
    s.lastCustomSprintMinutes = 37
    s.sessions = [session()]
    s.activeSprint = running(watched: 12.5)
    s.activeBreak = RunningBreak()
    s.skipDatesLocal = [LocalDay(2026, 10, 26)]
    s.earnedMilestones = [MilestoneRecord()]
    let data = try SettingsCoding.encoder().encode(s)
    #expect(try SettingsCoding.decoder().decode(AppSettings.self, from: data) == s)
  }
  @Test func fractionalTimestampLoads() throws {
    let s = try SettingsCoding.decoder().decode(
      FocusSession.self, from: Data("{\"startedUtc\":\"2026-10-26T12:00:00.123Z\"}".utf8))
    #expect(abs(s.startedUtc.timeIntervalSince(instant()) - 0.123) < 0.001)
  }
  @Test func fileStoreAtomicRoundTripAndPrivateMode() async throws {
    let dir = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: dir) }
    let url = dir.appendingPathComponent("settings.json")
    let store = SettingsStore(url: url)
    var s = ready()
    s.templatesSeeded = true
    try await store.save(s)
    s.momentumScore = 10
    try await store.save(s)
    #expect(try await store.load() == s)
    let mode =
      try FileManager.default.attributesOfItem(atPath: url.path)[.posixPermissions] as! NSNumber
    #expect(mode.intValue == 0o600)
    #expect(try FileManager.default.contentsOfDirectory(atPath: dir.path) == ["settings.json"])
  }
  @Test func corruptStoreQuarantinesAndDefaults() async throws {
    let dir = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: dir) }
    let url = dir.appendingPathComponent("settings.json")
    try Data("garbage".utf8).write(to: url)
    #expect(try await SettingsStore(url: url).load() == AppSettings())
    let files = try FileManager.default.contentsOfDirectory(atPath: dir.path)
    #expect(files.count == 1)
    #expect(files[0].hasPrefix("settings.corrupt-"))
  }
  @Test func futureSchemaPreservedAndRefused() async throws {
    let dir = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: dir) }
    let url = dir.appendingPathComponent("settings.json")
    let data = Data("{\"schemaVersion\":99}".utf8)
    try data.write(to: url)
    do {
      _ = try await SettingsStore(url: url).load()
      Issue.record("Future schema should fail")
    } catch SettingsStoreError.unsupportedSchema(let v) { #expect(v == 99) }
    #expect(try Data(contentsOf: url) == data)
  }
  @Test func trialRecordKeepsEarliestAndSurvivesReset() async throws {
    let dir = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: dir) }
    let record = TrialRecord(url: dir.appendingPathComponent("trial-start"))
    var s = AppSettings()
    #expect(try record.ensureStarted(&s, now: instant()))
    #expect(!(try record.ensureStarted(&s, now: instant().addingTimeInterval(86400))))
    let store = SettingsStore(url: dir.appendingPathComponent("settings.json"))
    try await store.save(s)
    try await store.reset()
    var fresh = AppSettings()
    #expect(!(try record.ensureStarted(&fresh, now: instant().addingTimeInterval(86400))))
    #expect(fresh.trialStartedUtc == instant())
    try record.saveEarliest(instant().addingTimeInterval(-86400))
    #expect(record.load() == instant().addingTimeInterval(-86400))
  }
  @Test func privacyExportExplicitAllowlistExcludesCredential() throws {
    var s = ready()
    s.licenseKey = "PRIVATE-TEST-CREDENTIAL"
    s.sessions = [session()]
    s.activeSprint = running()
    let data = try DataPrivacy.export(s, now: instant())
    let text = String(decoding: data, as: UTF8.self)
    #expect(!text.contains("PRIVATE-TEST-CREDENTIAL"))
    #expect(!text.contains("licenseKey"))
    let object = try JSONSerialization.jsonObject(with: data) as! [String: Any]
    #expect(
      Set(object.keys)
        == Set([
          "exportedUtc", "blockedApps", "blocklistProfiles", "activeProfileId", "studyTemplates",
          "sprintSchedules", "sleepBlocking", "sessions", "activeSprint", "momentumScore",
          "currentStreak", "earnedMilestones", "dailyGoal", "licence",
        ]))
  }
  @Test func csvExactHeaderAndOutcomeColumns() {
    var s = session(minutes: 20, completed: false)
    s.intention = "read"
    s.journal = "done"
    let text = JournalExport.csv([s], calendar: utcCalendar)
    #expect(
      text
        == "date (local),start (local),planned minutes,actual minutes,shield,completed,ended early,interrupted,distractions blocked,intention,journal\r\n2026-10-26,12:00,25,20,Firm,no,yes,no,0,read,done\r\n"
    )
  }
  @Test func csvInterruptedDistinctFromEarly() {
    let text = JournalExport.csv(
      [session(completed: false, interrupted: true)], calendar: utcCalendar)
    #expect(text.contains(",Firm,no,no,yes,"))
  }
  @Test func csvQuotesCommaNewlineAndQuote() {
    #expect(JournalExport.escapeCSV("a,b") == "\"a,b\"")
    #expect(JournalExport.escapeCSV("a\"b") == "\"a\"\"b\"")
    #expect(JournalExport.escapeCSV("a\nb") == "\"a\nb\"")
  }
  @Test func csvHasBOMMarkdownDoesNot() {
    let day = LocalDay(2026, 10, 26)
    #expect(
      Array(JournalExport.data([], from: day, to: day, format: .csv).prefix(3)) == [239, 187, 191])
    #expect(
      String(decoding: JournalExport.data([], from: day, to: day, format: .markdown), as: UTF8.self)
        .hasPrefix("# Basalt journal"))
  }
  @Test func dateRangeInclusiveReversedAndSorted() {
    let rows = [session(day: 27), session(day: 25), session(day: 26)]
    #expect(
      JournalExport.inRange(
        rows, from: LocalDay(2026, 10, 27), to: LocalDay(2026, 10, 26), calendar: utcCalendar
      ).map { LocalDay($0.startedUtc, calendar: utcCalendar).day } == [26, 27])
  }
  @Test func markdownGroupsNewestDayFirstChronologicalWithinDay() {
    var a = session()
    a.intention = "# plan"
    a.journal = "- done\nnext"
    let text = JournalExport.markdown(
      [session(day: 25), a], from: LocalDay(2026, 10, 25), to: LocalDay(2026, 10, 26),
      calendar: utcCalendar)
    #expect(
      text.hasPrefix(
        "# Basalt journal\r\n\r\n2026-10-25 to 2026-10-26. Times are local.\r\n\r\n## 2026-10-26"))
    #expect(text.contains("  - Intention: \\# plan\r\n"))
    #expect(text.contains("  - \\- done next\r\n"))
    #expect(text.contains("- 12:00 · 25 min · Firm · completed\r\n"))
  }
  @Test func emptyMarkdownAndFilename() {
    let d = LocalDay(2026, 10, 26)
    #expect(JournalExport.markdown([], from: d, to: d).hasSuffix("No sprints in this range.\r\n"))
    #expect(
      JournalExport.suggestedFileName(from: d, to: d.adding(-1), format: .csv)
        == "Basalt journal 2026-10-25 to 2026-10-26.csv")
  }
  @Test func exportOnlyWritesChosenPath() throws {
    let dir = try temporaryDirectory()
    defer { try? FileManager.default.removeItem(at: dir) }
    let d = LocalDay(2026, 10, 26)
    try JournalExport.write(
      to: dir.appendingPathComponent("chosen.csv"), sessions: [session()], from: d, to: d,
      format: .csv)
    #expect(try FileManager.default.contentsOfDirectory(atPath: dir.path) == ["chosen.csv"])
  }
  @Test func profileMigrationKeepsCountsAndSwitches() {
    var a = BlockedApp()
    a.name = "A"
    a.blockCount = 12
    a.isEnabled = false
    var s = AppSettings()
    let observed1 = s.ensureProfiles(legacyApps: [a])
    #expect(observed1)
    #expect(s.activeProfile.name == "Default")
    #expect(s.blockedApps == [a])
    let observed2 = !s.ensureProfiles()
    #expect(observed2)
  }
  @Test func duplicateProfilesResetOnlyCounts() {
    var a = BlockedApp()
    a.blockCount = 12
    a.name = "A"
    a.isEnabled = false
    var p = BlocklistProfile()
    p.apps = [a]
    p.sites = ["example.invalid"]
    let copy = p.copy(name: "School")
    #expect(copy.id != p.id)
    #expect(copy.apps[0].blockCount == 0)
    #expect(!copy.apps[0].isEnabled)
    #expect(copy.sites == p.sites)
  }
  @Test func profileNamesUniqueAndLastCannotDelete() {
    var s = ready()
    let observed3 = !s.deleteProfile(s.activeProfileId)
    #expect(observed3)
    let a = s.addProfile(name: "School")!
    let b = s.addProfile(name: "school")!
    #expect(b.name == "school 2")
    let observed4 = s.setActiveProfile(a.id)
    #expect(observed4)
    let observed5 = s.deleteProfile(a.id)
    #expect(observed5)
    #expect(s.activeProfileId == s.profiles[0].id)
  }
  @Test func sealedRejectsProfileEditsAtModelBoundary() {
    var s = ready()
    var r = running()
    r.shield = .sealed
    s.activeSprint = r
    let observed6 = s.addProfile(name: "new") == nil
    #expect(observed6)
    let observed7 = !s.renameProfile(s.activeProfileId, name: "new")
    #expect(observed7)
    let observed8 = !s.deleteProfile(s.activeProfileId)
    #expect(observed8)
    let observed9 = !s.setActiveProfile("anything")
    #expect(observed9)
  }
  @Test func processNamesTrimDeduplicateCaseInsensitive() {
    var a = BlockedApp()
    a.processName = " A "
    a.extraProcessNames = ["a", "B", " "]
    #expect(a.allProcessNames == ["A", "B"])
  }
}
