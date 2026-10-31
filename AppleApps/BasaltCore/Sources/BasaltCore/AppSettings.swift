import Foundation

public enum AppTheme: String, Codable, Sendable { case system, light, dark }
public struct AppSettings: Codable, Equatable, Sendable {
  public static let currentSchemaVersion = 1
  public var schemaVersion: Int = 1
  public var profiles: [BlocklistProfile] = []
  public var activeProfileId: String = ""
  public var templates: [StudyTemplate] = []
  public var schedules: [SprintSchedule] = []
  public var templatesSeeded: Bool = false
  public var isSleepBlockEnabled: Bool = false
  public var sleepBlockStartMinute: Int = 1320
  public var sleepBlockEndMinute: Int = 360
  public var openAtLogin: Bool = false
  public var hardKillModeEnabled: Bool = false
  public var keepRunningOnClose: Bool = true
  public var globalHotkeyEnabled: Bool = false
  public var showSoftOverlayEnabled: Bool = true
  public var theme: AppTheme = .system
  public var firstRunCompleted: Bool = false
  public var termsAcceptedVersion: String = ""
  public var termsAcceptedUtc: Date? = nil
  public var notificationsEnabled: Bool = true
  public var notificationKinds: [String: Bool] = [:]
  public var trialEndingNotifiedLocal: LocalDay? = nil
  public var scheduleLastCheckUtc: Date? = nil
  public var licenseKey: String = ""
  public var licenseEmail: String = ""
  public var isPro: Bool = false
  public var trialStartedUtc: Date? = nil
  public var licenseServerUrl: String = "https://flowshield-license-server.onrender.com"
  public var websiteUrl: String = "https://seventycookies6-design.github.io/flowshield"
  public var licenseCheckedUtc: Date? = nil
  public var licenseStatus: String = ""
  public var deviceCount: Int = 0
  public var deviceLimit: Int = 0
  public var defaultSprintMinutes: Int = 25
  public var lastCustomSprintMinutes: Int = 30
  public var defaultShield: ShieldLevel = .firm
  public var sessions: [FocusSession] = []
  public var activeSprint: RunningSprint? = nil
  public var activeBreak: RunningBreak? = nil
  public var shortBreakMinutes: Int = 5
  public var longBreakMinutes: Int = 15
  public var completedSprintsInARow: Int = 0
  public var cycleSprints: Int = 0
  public var momentumScore: Double = 0
  public var currentStreak: Int = 0
  public var lastSessionDayLocal: LocalDay? = nil
  public var dailyGoalKind: DailyGoalKind = .none
  public var dailyGoalTarget: Int = 0
  public var streakSettledDayLocal: LocalDay? = nil
  public var goalMetDayLocal: LocalDay? = nil
  public var skipDatesLocal: [LocalDay] = []
  public var earnedMilestones: [MilestoneRecord] = []
  public var milestonesSeeded: Bool = false
  public var blocksToday: Int = 0
  public var blocksTodayDateLocal: LocalDay? = nil
  public init() {}
  public var activeProfile: BlocklistProfile {
    profiles.first { $0.id == activeProfileId } ?? profiles.first ?? BlocklistProfile()
  }
  public var blockedApps: [BlockedApp] { activeProfile.apps }
  public var listIsLocked: Bool { activeSprint?.shield == .sealed }
  public static let suggestedProfileNames = ["School", "Gaming break", "Everything"]
  @discardableResult public mutating func ensureProfiles(legacyApps: [BlockedApp] = []) -> Bool {
    let before = self
    if profiles.isEmpty {
      var p = BlocklistProfile()
      p.apps = legacyApps
      profiles = [p]
    }
    for i in profiles.indices where profiles[i].id.isEmpty { profiles[i].id = newID() }
    if !profiles.contains(where: { $0.id == activeProfileId }) { activeProfileId = profiles[0].id }
    return self != before
  }
  public func findProfile(_ id: String) -> BlocklistProfile? {
    id.isEmpty ? nil : profiles.first { $0.id == id }
  }
  public func profile(for template: StudyTemplate) -> BlocklistProfile {
    findProfile(template.profileId) ?? activeProfile
  }
  public static func cleanProfileName(_ name: String) -> String {
    trimmed(name).isEmpty ? "Default" : trimmed(cutUTF16(trimmed(name), 40))
  }
  public func uniqueProfileName(_ wanted: String, except: String? = nil) -> String {
    let taken = profiles.filter { $0.id != except }.map { $0.name.lowercased() }
    if !taken.contains(wanted.lowercased()) { return wanted }
    for n in 2..<100 {
      let candidate = "\(wanted) \(n)"
      if !taken.contains(candidate.lowercased()) { return candidate }
    }
    return wanted
  }
  @discardableResult public mutating func addProfile(name: String, copying: BlocklistProfile? = nil)
    -> BlocklistProfile?
  {
    guard !listIsLocked else { return nil }
    let name = uniqueProfileName(Self.cleanProfileName(name))
    var profile = copying?.copy(name: name) ?? BlocklistProfile()
    profile.name = name
    profiles.append(profile)
    return profile
  }
  @discardableResult public mutating func renameProfile(_ id: String, name: String) -> Bool {
    guard !listIsLocked, let i = profiles.firstIndex(where: { $0.id == id }) else { return false }
    let clean = uniqueProfileName(Self.cleanProfileName(name), except: id)
    guard profiles[i].name != clean else { return false }
    profiles[i].name = clean
    return true
  }
  @discardableResult public mutating func deleteProfile(_ id: String) -> Bool {
    guard !listIsLocked, profiles.count > 1, let i = profiles.firstIndex(where: { $0.id == id })
    else { return false }
    profiles.remove(at: i)
    if activeProfileId == id { activeProfileId = profiles[0].id }
    return true
  }
  @discardableResult public mutating func setActiveProfile(_ id: String) -> Bool {
    guard !listIsLocked, id != activeProfileId, findProfile(id) != nil else { return false }
    activeProfileId = id
    return true
  }
  public func uniqueTemplateName(_ wanted: String, except: String? = nil) -> String {
    let taken = templates.filter { $0.id != except }.map { $0.name.lowercased() }
    if !taken.contains(wanted.lowercased()) { return wanted }
    for n in 2..<100 {
      let suffix = " \(n)"
      let candidate = trimmed(cutUTF16(wanted, 40 - suffix.utf16.count)) + suffix
      if !taken.contains(candidate.lowercased()) { return candidate }
    }
    return wanted
  }
  @discardableResult public mutating func restoreBuiltInTemplates() -> Int {
    let keys = Set(templates.map(\.builtInKey))
    let missing = StudyTemplate.builtIns().filter { !keys.contains($0.builtInKey) }
    for var t in missing {
      t.name = uniqueTemplateName(t.name)
      templates.append(t)
    }
    return missing.count
  }
  @discardableResult public mutating func ensureTemplates() -> Bool {
    let before = self
    for i in templates.indices { templates[i].normalize() }
    for i in schedules.indices { schedules[i].normalize() }
    if !templatesSeeded {
      restoreBuiltInTemplates()
      templatesSeeded = true
    }
    var seen: Set<String> = []
    for i in templates.indices {
      if !seen.insert(templates[i].name.lowercased()).inserted {
        templates[i].name = uniqueTemplateName(templates[i].name, except: templates[i].id)
      }
    }
    schedules.removeAll { s in !templates.contains { $0.id == s.templateId } }
    return self != before
  }
  @discardableResult public mutating func deleteTemplate(_ id: String) -> Int {
    guard templates.contains(where: { $0.id == id }) else { return 0 }
    templates.removeAll { $0.id == id }
    let old = schedules.count
    schedules.removeAll { $0.templateId == id }
    return old - schedules.count
  }
  public mutating func recordBlock(day: LocalDay) {
    if blocksTodayDateLocal != day {
      blocksTodayDateLocal = day
      blocksToday = 0
    }
    blocksToday += 1
  }
  public func blocksTodayCurrent(_ day: LocalDay) -> Int {
    blocksTodayDateLocal == day ? blocksToday : 0
  }
  public func inSleepWindow(minute: Int) -> Bool {
    guard isSleepBlockEnabled else { return false }
    let a = sleepBlockStartMinute
    let b = sleepBlockEndMinute
    return a <= b ? minute >= a && minute < b : minute >= a || minute < b
  }
}

extension AppSettings {
  private enum CodingKeys: String, CodingKey {
    case schemaVersion, profiles, activeProfileId, templates, schedules, templatesSeeded,
      isSleepBlockEnabled, sleepBlockStartMinute, sleepBlockEndMinute, openAtLogin,
      hardKillModeEnabled, keepRunningOnClose, globalHotkeyEnabled, showSoftOverlayEnabled, theme,
      firstRunCompleted, termsAcceptedVersion, termsAcceptedUtc, notificationsEnabled,
      notificationKinds, trialEndingNotifiedLocal, scheduleLastCheckUtc, licenseKey, licenseEmail,
      isPro, trialStartedUtc, licenseServerUrl, websiteUrl, licenseCheckedUtc, licenseStatus,
      deviceCount, deviceLimit, defaultSprintMinutes, lastCustomSprintMinutes, defaultShield,
      sessions, activeSprint, activeBreak, shortBreakMinutes, longBreakMinutes,
      completedSprintsInARow, cycleSprints, momentumScore, currentStreak, lastSessionDayLocal,
      dailyGoalKind, dailyGoalTarget, streakSettledDayLocal, goalMetDayLocal, skipDatesLocal,
      earnedMilestones, milestonesSeeded, blocksToday, blocksTodayDateLocal
  }
  public init(from decoder: any Decoder) throws {
    self.init()
    let c = try decoder.container(keyedBy: CodingKeys.self)
    schemaVersion = try c.decodeIfPresent(Int.self, forKey: .schemaVersion) ?? schemaVersion
    profiles = try c.decodeIfPresent([BlocklistProfile].self, forKey: .profiles) ?? profiles
    activeProfileId =
      try c.decodeIfPresent(String.self, forKey: .activeProfileId) ?? activeProfileId
    templates = try c.decodeIfPresent([StudyTemplate].self, forKey: .templates) ?? templates
    schedules = try c.decodeIfPresent([SprintSchedule].self, forKey: .schedules) ?? schedules
    templatesSeeded = try c.decodeIfPresent(Bool.self, forKey: .templatesSeeded) ?? templatesSeeded
    isSleepBlockEnabled =
      try c.decodeIfPresent(Bool.self, forKey: .isSleepBlockEnabled) ?? isSleepBlockEnabled
    sleepBlockStartMinute =
      try c.decodeIfPresent(Int.self, forKey: .sleepBlockStartMinute) ?? sleepBlockStartMinute
    sleepBlockEndMinute =
      try c.decodeIfPresent(Int.self, forKey: .sleepBlockEndMinute) ?? sleepBlockEndMinute
    openAtLogin = try c.decodeIfPresent(Bool.self, forKey: .openAtLogin) ?? openAtLogin
    hardKillModeEnabled =
      try c.decodeIfPresent(Bool.self, forKey: .hardKillModeEnabled) ?? hardKillModeEnabled
    keepRunningOnClose =
      try c.decodeIfPresent(Bool.self, forKey: .keepRunningOnClose) ?? keepRunningOnClose
    globalHotkeyEnabled =
      try c.decodeIfPresent(Bool.self, forKey: .globalHotkeyEnabled) ?? globalHotkeyEnabled
    showSoftOverlayEnabled =
      try c.decodeIfPresent(Bool.self, forKey: .showSoftOverlayEnabled) ?? showSoftOverlayEnabled
    theme = try c.decodeIfPresent(AppTheme.self, forKey: .theme) ?? theme
    firstRunCompleted =
      try c.decodeIfPresent(Bool.self, forKey: .firstRunCompleted) ?? firstRunCompleted
    termsAcceptedVersion =
      try c.decodeIfPresent(String.self, forKey: .termsAcceptedVersion) ?? termsAcceptedVersion
    termsAcceptedUtc =
      try c.decodeIfPresent(Date.self, forKey: .termsAcceptedUtc) ?? termsAcceptedUtc
    notificationsEnabled =
      try c.decodeIfPresent(Bool.self, forKey: .notificationsEnabled) ?? notificationsEnabled
    notificationKinds =
      try c.decodeIfPresent([String: Bool].self, forKey: .notificationKinds) ?? notificationKinds
    trialEndingNotifiedLocal =
      try c.decodeIfPresent(LocalDay.self, forKey: .trialEndingNotifiedLocal)
      ?? trialEndingNotifiedLocal
    scheduleLastCheckUtc =
      try c.decodeIfPresent(Date.self, forKey: .scheduleLastCheckUtc) ?? scheduleLastCheckUtc
    licenseKey = try c.decodeIfPresent(String.self, forKey: .licenseKey) ?? licenseKey
    licenseEmail = try c.decodeIfPresent(String.self, forKey: .licenseEmail) ?? licenseEmail
    isPro = try c.decodeIfPresent(Bool.self, forKey: .isPro) ?? isPro
    trialStartedUtc = try c.decodeIfPresent(Date.self, forKey: .trialStartedUtc) ?? trialStartedUtc
    licenseServerUrl =
      try c.decodeIfPresent(String.self, forKey: .licenseServerUrl) ?? licenseServerUrl
    websiteUrl = try c.decodeIfPresent(String.self, forKey: .websiteUrl) ?? websiteUrl
    licenseCheckedUtc =
      try c.decodeIfPresent(Date.self, forKey: .licenseCheckedUtc) ?? licenseCheckedUtc
    licenseStatus = try c.decodeIfPresent(String.self, forKey: .licenseStatus) ?? licenseStatus
    deviceCount = try c.decodeIfPresent(Int.self, forKey: .deviceCount) ?? deviceCount
    deviceLimit = try c.decodeIfPresent(Int.self, forKey: .deviceLimit) ?? deviceLimit
    defaultSprintMinutes =
      try c.decodeIfPresent(Int.self, forKey: .defaultSprintMinutes) ?? defaultSprintMinutes
    lastCustomSprintMinutes =
      try c.decodeIfPresent(Int.self, forKey: .lastCustomSprintMinutes) ?? lastCustomSprintMinutes
    defaultShield =
      (try? c.decodeIfPresent(ShieldLevel.self, forKey: .defaultShield)) ?? defaultShield
    sessions = try c.decodeIfPresent([FocusSession].self, forKey: .sessions) ?? sessions
    activeSprint = try c.decodeIfPresent(RunningSprint.self, forKey: .activeSprint) ?? activeSprint
    activeBreak = try c.decodeIfPresent(RunningBreak.self, forKey: .activeBreak) ?? activeBreak
    shortBreakMinutes =
      try c.decodeIfPresent(Int.self, forKey: .shortBreakMinutes) ?? shortBreakMinutes
    longBreakMinutes =
      try c.decodeIfPresent(Int.self, forKey: .longBreakMinutes) ?? longBreakMinutes
    completedSprintsInARow =
      try c.decodeIfPresent(Int.self, forKey: .completedSprintsInARow) ?? completedSprintsInARow
    cycleSprints = try c.decodeIfPresent(Int.self, forKey: .cycleSprints) ?? cycleSprints
    momentumScore = try c.decodeIfPresent(Double.self, forKey: .momentumScore) ?? momentumScore
    currentStreak = try c.decodeIfPresent(Int.self, forKey: .currentStreak) ?? currentStreak
    lastSessionDayLocal =
      try c.decodeIfPresent(LocalDay.self, forKey: .lastSessionDayLocal) ?? lastSessionDayLocal
    dailyGoalKind =
      try c.decodeIfPresent(DailyGoalKind.self, forKey: .dailyGoalKind) ?? dailyGoalKind
    dailyGoalTarget = try c.decodeIfPresent(Int.self, forKey: .dailyGoalTarget) ?? dailyGoalTarget
    streakSettledDayLocal =
      try c.decodeIfPresent(LocalDay.self, forKey: .streakSettledDayLocal) ?? streakSettledDayLocal
    goalMetDayLocal =
      try c.decodeIfPresent(LocalDay.self, forKey: .goalMetDayLocal) ?? goalMetDayLocal
    skipDatesLocal =
      try c.decodeIfPresent([LocalDay].self, forKey: .skipDatesLocal) ?? skipDatesLocal
    earnedMilestones =
      try c.decodeIfPresent([MilestoneRecord].self, forKey: .earnedMilestones) ?? earnedMilestones
    milestonesSeeded =
      try c.decodeIfPresent(Bool.self, forKey: .milestonesSeeded) ?? milestonesSeeded
    blocksToday = try c.decodeIfPresent(Int.self, forKey: .blocksToday) ?? blocksToday
    blocksTodayDateLocal =
      try c.decodeIfPresent(LocalDay.self, forKey: .blocksTodayDateLocal) ?? blocksTodayDateLocal
  }
}
