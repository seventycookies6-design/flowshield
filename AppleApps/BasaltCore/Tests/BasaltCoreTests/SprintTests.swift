import Foundation

import Testing

@testable import BasaltCore

struct SprintTests {
  @Test func presets() { #expect(SprintLength.presets == [15, 25, 45, 60, 90]) }
  @Test func validationCopy() {
    #expect(SprintLength.validationCopy == "Choose between 5 and 240 minutes.")
  }
  @Test func defaults() {
    let s = AppSettings()
    #expect(s.defaultSprintMinutes == 25)
    #expect(s.lastCustomSprintMinutes == 30)
    #expect(s.defaultShield == .firm)
  }
  @Test func enumValues() { #expect(ShieldLevel.allCases.map(\.rawValue) == [1, 2, 3]) }
  @Test func firmCopy() {
    #expect(ShieldCopy.promise(.firm) == "Closes blocked apps.")
    #expect(ShieldCopy.bestFor(.firm) == "Best for homework.")
  }
  @Test func softCopy() {
    #expect(ShieldCopy.promise(.soft) == "Notes distractions and nudges you.")
    #expect(ShieldCopy.bestFor(.soft) == "Best for classes or light work.")
  }
  @Test func sealedCopy() {
    #expect(ShieldCopy.promise(.sealed) == "Closes apps and locks the list until the sprint ends.")
    #expect(ShieldCopy.bestFor(.sealed) == "Best for exams and deep work.")
  }
  @Test func optionsSummary() {
    #expect(
      SprintLength.summary(minutes: 25, shield: .firm, cycleSprints: 0)
        == "25 min · Firm shield · One sprint")
  }
  @Test func invalidOptionsSummary() {
    #expect(
      SprintLength.summary(minutes: 0, shield: .sealed, cycleSprints: 3)
        == "Custom length · Sealed shield · 3 sprints with breaks")
  }
  @Test func normalWaits() {
    let p = EndSprintPolicy()
    #expect(p.gracePeriod == 120)
    #expect(p.delay(.confirm) == 5)
    #expect(p.delay(.sealed) == 30)
    #expect(p.delay(.cancel) == 0)
  }
  @Test func testWaits() {
    let p = EndSprintPolicy(testTimings: true)
    #expect(p.gracePeriod == 15)
    #expect(p.delay(.confirm) == 6)
    #expect(p.delay(.sealed) == 8)
  }
  @Test func endAnywayRechecksWait() {
    #expect(
      !EndSprintPolicy().canEndAnyway(
        flow: .confirm, unlocksAt: instant(), now: instant().addingTimeInterval(-0.1), phrase: ""))
  }
  @Test func endAnywayRechecksPhrase() {
    #expect(
      !EndSprintPolicy().canEndAnyway(
        flow: .sealed, unlocksAt: instant(), now: instant(), phrase: "stop"))
  }
  @Test func endAnywayUnlocks() {
    #expect(
      EndSprintPolicy().canEndAnyway(
        flow: .sealed, unlocksAt: instant(), now: instant(), phrase: " END  my\nsprint "))
  }
  @Test func endLabels() {
    let p = EndSprintPolicy()
    #expect(p.buttonLabel(shield: .sealed, elapsed: 0) == "Cancel sprint")
    #expect(p.buttonLabel(shield: .soft, elapsed: 120) == "End sprint")
    #expect(p.buttonLabel(shield: .firm, elapsed: 120) == "End sprint…")
    #expect(p.buttonLabel(shield: .sealed, elapsed: 120) == "I need to stop")
  }
  @Test func missingEndIsZero() {
    #expect(FocusSession().actualMinutes == 0)
    #expect(!FocusSession().endedEarly)
  }
  @Test func actualMinutesEvenRounding() {
    #expect(session(minutes: 2.25).actualMinutes == 2.2)
    #expect(session(minutes: 2.35).actualMinutes == 2.4)
  }
  @Test func interruptedIsNotEarly() {
    #expect(!session(completed: false, interrupted: true).endedEarly)
  }
  @Test func earlyOutcome() { #expect(session(completed: false).outcome == "ended early") }
  @Test func neutralSummary() {
    var s = session(completed: false)
    s.momentumAtStart = 50
    #expect(s.summaryTitle(momentum: 40) == "Ended early — momentum −10. It'll recover.")
    #expect(s.summaryTitle(momentum: 49.8) == "Ended early. It'll recover.")
  }
  @Test func distractionSplit() {
    var s = session()
    s.appsClosed = 2
    s.nudgesSent = 1
    #expect(s.distractionSummary == "2 closed · 1 nudge")
  }
  @Test func distractionLegacy() {
    var s = session()
    s.blocksEnforced = 1
    #expect(s.distractionSummary == "1 distraction caught")
    s.blocksEnforced = 3
    #expect(s.distractionSummary == "3 distractions caught")
  }
  @Test func noDistractions() { #expect(session().distractionSummary == "No distractions caught") }
  @Test func termsGate() {
    var s = AppSettings()
    #expect(SprintLifecycle.start(&s, now: instant(), minutes: 25, shield: .firm) == .termsRequired)
    #expect(s.activeSprint == nil)
  }
  @Test func firstRunGate() {
    var s = ready()
    #expect(
      SprintLifecycle.start(&s, now: instant(), minutes: 25, shield: .firm, firstRunVisible: true)
        == .firstRunRequired)
  }
  @Test func trialGate() {
    var s = ready()
    s.isPro = false
    #expect(SprintLifecycle.start(&s, now: instant(), minutes: 25, shield: .firm) == .accessLocked)
  }
  @Test func invalidLengthGate() {
    var s = ready()
    #expect(
      SprintLifecycle.start(&s, now: instant(), minutes: 241, shield: .firm) == .invalidLength)
  }
  @Test func runningAppsGate() {
    var s = ready()
    #expect(
      SprintLifecycle.start(
        &s, now: instant(), minutes: 25, shield: .firm, runningBlockedApps: true)
        == .confirmRunningApps)
    #expect(s.activeSprint == nil)
  }
  @Test func confirmedStartSnapshotsBeforeEnforcement() {
    var s = ready()
    s.momentumScore = 12
    #expect(
      SprintLifecycle.start(
        &s, now: instant(), minutes: 25, shield: .sealed, intention: "  chapter 3  ",
        runningBlockedApps: true, confirmed: true) == .started)
    #expect(s.activeSprint?.intention == "chapter 3")
    #expect(s.activeSprint?.momentumAtStart == 12)
    #expect(s.listIsLocked)
  }
  @Test func intentionCappedAtUTF16() {
    var s = ready()
    _ = SprintLifecycle.start(
      &s, now: instant(), minutes: 25, shield: .firm, intention: String(repeating: "😀", count: 60))
    #expect(s.activeSprint!.intention.utf16.count == 80)
  }
  @Test func duplicateStartRefused() {
    var s = ready()
    s.activeSprint = running()
    #expect(
      SprintLifecycle.start(&s, now: instant(), minutes: 25, shield: .firm) == .alreadyRunning)
  }
  @Test func cancelRecordsNothing() {
    var s = ready()
    s.activeSprint = running()
    s.momentumScore = 90
    SprintLifecycle.cancel(&s)
    #expect(s.activeSprint == nil)
    #expect(s.sessions.isEmpty)
    #expect(s.momentumScore == 90)
  }
  @Test func completionScoresBeforeGoal() {
    var s = ready()
    s.dailyGoalKind = .sprints
    s.dailyGoalTarget = 1
    s.activeSprint = running(watched: 25)
    _ = SprintLifecycle.finish(
      &s, now: instant().addingTimeInterval(1500), completed: true, calendar: utcCalendar)
    #expect(s.momentumScore == 10)
    #expect(s.currentStreak == 1)
    #expect(s.activeSprint == nil)
    #expect(s.sessions.count == 1)
  }
  @Test func shortSprintsCannotEarnProgress() {
    var s = ready()
    s.activeSprint = running()
    _ = SprintLifecycle.finish(
      &s, now: instant().addingTimeInterval(5), completed: true, shortSprints: true)
    #expect(s.sessions.isEmpty)
    #expect(s.momentumScore == 0)
    #expect(s.currentStreak == 0)
  }
  @Test func journalTrimsLatest() {
    var s = ready()
    s.sessions = [session(day: 25), session()]
    SprintLifecycle.saveJournal(&s, text: "  moved\n")
    #expect(s.sessions[0].journal.isEmpty)
    #expect(s.sessions[1].journal == "moved")
  }
  @Test func journalRepeatsIntention() {
    var s = session()
    #expect(s.journalPrompt == "What moved?")
    s.intention = "read"
    #expect(s.journalPrompt == "You planned: read. What moved?")
  }
}
