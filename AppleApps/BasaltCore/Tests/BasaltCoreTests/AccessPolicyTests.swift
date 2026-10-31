import Foundation
import Testing

@testable import BasaltCore

struct AccessPolicyTests {
  @Test func trialNoStartInactive() {
    #expect(!TrialPolicy.isActive(start: nil, now: instant()))
    #expect(TrialPolicy.daysLeft(start: nil, now: instant()) == 0)
  }
  @Test func earliestTrialDateWinsEitherCopy() {
    var s = AppSettings()
    s.trialStartedUtc = instant()
    #expect(
      !TrialPolicy.ensureStarted(&s, recorded: instant().addingTimeInterval(-86400), now: instant())
    )
    #expect(s.trialStartedUtc == instant().addingTimeInterval(-86400))
    #expect(!TrialPolicy.ensureStarted(&s, recorded: instant(), now: instant()))
    #expect(s.trialStartedUtc == instant().addingTimeInterval(-86400))
  }
  @Test func purchaseOrTrialGrantsAccess() {
    var s = AppSettings()
    #expect(!TrialPolicy.hasAccess(s, now: instant()))
    s.trialStartedUtc = instant()
    #expect(TrialPolicy.hasAccess(s, now: instant()))
    s.trialStartedUtc = .distantPast
    s.isPro = true
    #expect(TrialPolicy.hasAccess(s, now: instant()))
  }
  @Test func expiryWaitsForSprintSummaryAndJournal() {
    let s = AppSettings()
    #expect(
      !TrialPolicy.shouldLock(
        s, now: instant(), sprintRunning: true, summaryVisible: false, journalVisible: false))
    #expect(
      !TrialPolicy.shouldLock(
        s, now: instant(), sprintRunning: false, summaryVisible: true, journalVisible: false))
    #expect(
      !TrialPolicy.shouldLock(
        s, now: instant(), sprintRunning: false, summaryVisible: false, journalVisible: true))
    #expect(
      TrialPolicy.shouldLock(
        s, now: instant(), sprintRunning: false, summaryVisible: false, journalVisible: false))
  }
  @Test func trialTomorrowNoNagWhileFocusingOrAlreadyNotified() {
    var s = AppSettings()
    let today = LocalDay(2026, 10, 26)
    s.trialStartedUtc = instant().addingTimeInterval(-6 * 86400)
    #expect(TrialPolicy.shouldWarnTomorrow(s, now: instant(), today: today, sprintRunning: false))
    #expect(!TrialPolicy.shouldWarnTomorrow(s, now: instant(), today: today, sprintRunning: true))
    s.trialEndingNotifiedLocal = today
    #expect(!TrialPolicy.shouldWarnTomorrow(s, now: instant(), today: today, sprintRunning: false))
  }
  @Test func firstRunOnlyNewWithAccessAndNoSprint() {
    var s = AppSettings()
    #expect(FirstRunPolicy.shouldShow(s, hasAccess: true, sprintRunning: false))
    #expect(!FirstRunPolicy.shouldShow(s, hasAccess: false, sprintRunning: false))
    #expect(!FirstRunPolicy.shouldShow(s, hasAccess: true, sprintRunning: true))
    #expect(
      !FirstRunPolicy.shouldShow(s, hasAccess: true, sprintRunning: false, skipForTests: true))
    s.firstRunCompleted = true
    #expect(!FirstRunPolicy.shouldShow(s, hasAccess: true, sprintRunning: false))
  }
  @Test func existingBlocklistHistoryOrActiveSprintSuppressesFirstRun() {
    var s = AppSettings()
    s.sessions = [session()]
    #expect(FirstRunPolicy.isExistingUser(s))
    s.sessions = []
    s.activeSprint = running()
    #expect(FirstRunPolicy.isExistingUser(s))
    s.activeSprint = nil
    s.ensureProfiles(legacyApps: [BlockedApp()])
    #expect(FirstRunPolicy.isExistingUser(s))
  }
  @Test func browsersNeverPretickedAndOnlyInstalledSuggestions() {
    #expect(!FirstRunPolicy.preTicked(isSuggested: true, installedPath: "app", group: "bRoWsErS"))
    #expect(!FirstRunPolicy.preTicked(isSuggested: true, installedPath: nil, group: "Chat"))
    #expect(!FirstRunPolicy.preTicked(isSuggested: false, installedPath: "app", group: "Chat"))
    #expect(FirstRunPolicy.preTicked(isSuggested: true, installedPath: "app", group: "Chat"))
    #expect(FirstRunPolicy.sprintLengths == [25, 45])
    #expect(FirstRunPolicy.defaultShield == .firm)
  }
  @Test func notificationDefaultsAllOnButFocusProtected() {
    let s = AppSettings()
    for kind in NotificationKind.allCases {
      #expect(NotificationPolicy.shouldShow(kind, s, sprintRunning: false))
    }
    #expect(!NotificationPolicy.shouldShow(.trialEnding, s, sprintRunning: true))
    #expect(!NotificationPolicy.shouldShow(.updateReady, s, sprintRunning: true))
    #expect(NotificationPolicy.shouldShow(.appClosing, s, sprintRunning: true))
  }
  @Test func notificationMasterAndKindSwitches() {
    var s = AppSettings()
    s.notificationsEnabled = false
    #expect(
      NotificationKind.allCases.allSatisfy {
        !NotificationPolicy.shouldShow($0, s, sprintRunning: false)
      })
    s.notificationsEnabled = true
    s.notificationKinds[NotificationKind.sprintComplete.rawValue] = false
    #expect(!NotificationPolicy.shouldShow(.sprintComplete, s, sprintRunning: false))
    #expect(NotificationPolicy.shouldShow(.sprintStarted, s, sprintRunning: false))
  }
  @Test func shortSprintNoImmediateEndingSoon() {
    #expect(NotificationPolicy.tooShortForEndingSoon(6))
    #expect(!NotificationPolicy.tooShortForEndingSoon(7))
  }
  @Test func menuBarBreakAndIdleCopy() {
    #expect(
      NotificationPolicy.menuBarText(running: false, shield: .firm, remaining: 0)
        == "Basalt — no sprint running")
    #expect(
      NotificationPolicy.menuBarText(running: false, shield: .sealed, remaining: 299, onBreak: true)
        == "Basalt — Break · 4:59")
    #expect(
      NotificationPolicy.menuBarText(running: true, shield: .firm, remaining: 1)
        == "Basalt — Firm shield, 1 minute left")
  }
  @Test func termsAcceptanceVersionAndURLs() {
    var s = AppSettings()
    #expect(!LegalTerms.accepted(s))
    LegalTerms.accept(&s, now: instant())
    #expect(LegalTerms.accepted(s))
    #expect(s.termsAcceptedUtc == instant())
    s.termsAcceptedVersion = "old"
    #expect(!LegalTerms.accepted(s))
    #expect(LegalTerms.termsURL(s).hasSuffix("/legal.html#terms"))
    #expect(LegalTerms.privacyURL(s).hasSuffix("/legal.html#privacy"))
  }
  @Test func keyServerChecksumFixtureAndNormalization() {
    #expect(LicenseKey.isWellFormed("FS-0123-4567-89AB-CDEQ"))
    #expect(LicenseKey.normalize(" \tfs-0123-_4567-89ab-cdeq\r\n") == "FS-0123-4567-89AB-CDEQ")
    #expect(
      LicenseKey.normalize("\u{feff}fs-0123-\u{a0}4567-89ab-cdeq\u{3000}")
        == "FS-0123-4567-89AB-CDEQ")
    #expect(LicenseKey.normalize("fs-00\u{85}00") == "FS-00\u{85}00")
  }
  @Test func everyAlphabetSymbolFixturePasses() {
    for char in LicenseKey.alphabet {
      let group = String(repeating: String(char), count: 4)
      #expect(
        LicenseKey.isWellFormed("FS-" + Array(repeating: group, count: 4).joined(separator: "-")))
    }
  }
  @Test func everyChecksumPositionUsesOddWeight() {
    let checks = Array("13579BDFHKNQSVX")
    for i in 0..<15 {
      var body = Array(repeating: Character("0"), count: 16)
      body[i] = "1"
      body[15] = checks[i]
      let key =
        "FS-"
        + stride(from: 0, to: 16, by: 4).map { String(body[$0..<$0 + 4]) }.joined(separator: "-")
      #expect(LicenseKey.isWellFormed(key))
    }
  }
  @Test func everySingleSymbolSubstitutionRejected() {
    let body = Array("0123456789ABCDEQ")
    for i in 0..<16 {
      for char in LicenseKey.alphabet where char != body[i] {
        var changed = body
        changed[i] = char
        let key =
          "FS-"
          + stride(from: 0, to: 16, by: 4).map { String(changed[$0..<$0 + 4]) }.joined(
            separator: "-")
        #expect(!LicenseKey.isWellFormed(key))
      }
    }
  }
  @Test func malformedKeysRejected() {
    for key in [
      "", "FS", "FS0123456789ABCDEQ", "FS-0123-4567-89AB-CDEI", "FS-0123-4567-89AB-CDEL",
      "FS-0123-4567-89AB-CDEO", "FS-0123-4567-89AB-CDEU", "FS-0123-4567-89AB-CDEQ!",
      "FS-0123-4567-89AB-CDE0",
    ] { #expect(!LicenseKey.isWellFormed(key)) }
  }
  @Test func deepLinkOnlyOffersShapedKeys() {
    #expect(
      DeepLink.parseActivationKey("flowshield://activate?key=fs-0123-4567-89ab-cdeq")
        == "FS-0123-4567-89AB-CDEQ")
    #expect(
      DeepLink.parseActivationKey("FLOWSHIELD://activate/?key=FS-0000-0000-0000-0001")
        == "FS-0000-0000-0000-0001")
    #expect(DeepLink.parseActivationKey("https://activate?key=FS-0123-4567-89AB-CDEQ") == nil)
    #expect(DeepLink.parseActivationKey("flowshield://start?key=FS-0123-4567-89AB-CDEQ") == nil)
    #expect(DeepLink.parseActivationKey("flowshield://activate?key=garbage") == nil)
  }
  @Test func deepLinkLastKeyAndFirstLaunchLink() {
    #expect(
      DeepLink.parseActivationKey("flowshield://activate?key=FS-0000-0000-0000-0000&KEY=bad") == nil
    )
    #expect(
      DeepLink.findLink(["--other", "FLOWshield://activate?key=bad"])
        == "FLOWshield://activate?key=bad")
  }
  @Test func dailyBlockCountRollsOver() {
    var s = AppSettings()
    let d = LocalDay(2026, 10, 26)
    s.recordBlock(day: d)
    s.recordBlock(day: d)
    #expect(s.blocksTodayCurrent(d) == 2)
    #expect(s.blocksTodayCurrent(d.adding(1)) == 0)
    s.recordBlock(day: d.adding(1))
    #expect(s.blocksToday == 1)
  }
  @Test func sleepWindowCrossesMidnightAndEndExclusive() {
    var s = AppSettings()
    s.isSleepBlockEnabled = true
    #expect(s.inSleepWindow(minute: 1320))
    #expect(s.inSleepWindow(minute: 0))
    #expect(s.inSleepWindow(minute: 359))
    #expect(!s.inSleepWindow(minute: 360))
    #expect(!s.inSleepWindow(minute: 900))
    s.sleepBlockStartMinute = 600
    s.sleepBlockEndMinute = 900
    #expect(s.inSleepWindow(minute: 600))
    #expect(!s.inSleepWindow(minute: 900))
    s.sleepBlockStartMinute = 900
    #expect(!s.inSleepWindow(minute: 900))
  }
}
