import Foundation

import Testing

@testable import BasaltCore

struct CycleTemplateScheduleTests {
  @Test func cycleChoices() {
    #expect(CycleState.choices == [0, 2, 3, 4])
    #expect(!CycleState().inCycle)
  }
  @Test func cycleRunsSprintBreakSprint() {
    var c = CycleState().onSprintStarted(3)
    #expect(c.cycleLabel == "Sprint 1 of 3")
    c = c.onSprintCompleted()
    #expect(c.startsNextSprint)
    c = c.onBreakStarted()
    #expect(c.phase == .break)
    c = c.onBreakEnded().onSprintStarted(4)
    #expect(c.sprintsPlanned == 3)
    #expect(c.cycleLabel == "Sprint 2 of 3")
    c = c.onSprintCompleted().onSprintStarted(4).onSprintCompleted()
    #expect(c.cycleFinished)
    #expect(!c.startsNextSprint)
    #expect(c.onCycleFinished() == CycleState())
  }
  @Test func abandonedCycleEnds() {
    let c = CycleState().onSprintStarted(3)
    #expect(c.onSprintAbandoned() == CycleState())
  }
  @Test func singleSprintDoesNotAutoStart() {
    let c = CycleState().onSprintStarted(0).onSprintCompleted()
    #expect(!c.startsNextSprint)
    #expect(!c.cycleFinished)
  }
  @Test func breakOnlyOnCompleted() {
    #expect(CycleState.offersBreak(completed: true))
    #expect(!CycleState.offersBreak(completed: false))
  }
  @Test func breakEveryFourth() {
    #expect(CycleState.breakMinutes(completedInARow: 0) == 5)
    for n in 1...12 {
      #expect(CycleState.breakMinutes(completedInARow: n) == (n % 4 == 0 ? 15 : 5))
    }
  }
  @Test func breakAndSprintTimings() {
    #expect(CycleState.breakLength(5) == 300)
    #expect(CycleState.breakLength(-1) == 0)
    #expect(CycleState.breakLength(5, testTimings: true) == 3)
    #expect(CycleState.sprintLength(25) == 1500)
    #expect(CycleState.sprintLength(90, shortSprints: true) == 5)
    #expect(!CycleState.sprintCountsAsProgress(shortSprints: true))
  }
  @Test func breakResumeAtBoundary() {
    var b = RunningBreak()
    b.endsUtc = instant()
    b.sprintsPlanned = 3
    b.sprintsDone = 1
    #expect(b.decide(instant().addingTimeInterval(-1)) == .resume)
    #expect(b.decide(instant()) == .endQuietly)
    #expect(b.cycle.cycleLabel == "Sprint 2 of 3")
  }
  @Test func sleepBreakCopyHonest() {
    #expect(
      BreakCopy.panelText(
        inSleepWindow: false, onBreak: true, isLong: false, minutes: 5, sleepEndsText: "06:00")
        == "The shield is down. Blocked apps are allowed until the break ends.")
    #expect(
      BreakCopy.panelText(
        inSleepWindow: true, onBreak: true, isLong: false, minutes: 5, sleepEndsText: "06:00"
      ).contains("still closed"))
    #expect(
      BreakCopy.endingSoon(inSleepWindow: true, sleepEndsText: "06:00").contains(
        "sleep shield stays up until 06:00"))
    #expect(
      BreakCopy.caption(inSleepWindow: false, resumed: true)
        == "Break resumed —\nthe shield is down")
  }
  @Test func builtInsMatchCSharpNotInventory() {
    let b = StudyTemplate.builtIns()
    #expect(b.map(\.name) == ["Homework evening", "Exam prep", "Light study"])
    #expect(b.map(\.sprintMinutes) == [45, 90, 25])
    #expect(b.map(\.shield) == [.firm, .sealed, .soft])
    #expect(b.map(\.cycleSprints) == [3, 0, 0])
    #expect(b.map(\.breakMinutes) == [10, 5, 5])
    #expect(Set(b.map(\.id)).count == 3)
  }
  @Test func builtInsFreshIds() {
    #expect(StudyTemplate.builtIns().map(\.id) != StudyTemplate.builtIns().map(\.id))
  }
  @Test func templateNormalization() {
    var t = StudyTemplate()
    t.sprintMinutes = -9
    t.breakMinutes = 100
    t.cycleSprints = 1
    let observed1 = t.normalize()
    #expect(observed1)
    #expect(!t.id.isEmpty)
    #expect(t.name == "Untitled template")
    #expect(t.sprintMinutes == 5)
    #expect(t.breakMinutes == 60)
    #expect(t.cycleSprints == 0)
    let observed2 = !t.normalize()
    #expect(observed2)
  }
  @Test func templateNameDoesNotCutSurrogate() {
    var t = StudyTemplate()
    t.name = String(repeating: "a", count: 39) + "😀"
    t.normalize()
    #expect(t.name.utf16.count == 39)
    #expect(!t.name.contains("�"))
  }
  @Test func templatesSeedOnceAndRestoreMissing() {
    var s = ready()
    let observed3 = s.ensureTemplates()
    #expect(observed3)
    #expect(s.templates.count == 3)
    s.templates = []
    let observed4 = !s.ensureTemplates()
    #expect(observed4)
    #expect(s.templates.isEmpty)
    let observed5 = s.restoreBuiltInTemplates() == 3
    #expect(observed5)
    let observed6 = s.restoreBuiltInTemplates() == 0
    #expect(observed6)
  }
  @Test func duplicateTemplateNamesStayWithinCap() {
    var s = ready()
    s.templatesSeeded = true
    var a = StudyTemplate()
    a.id = "a"
    a.name = String(repeating: "x", count: 40)
    var b = a
    b.id = "b"
    s.templates = [a, b]
    s.ensureTemplates()
    #expect(s.templates[1].name.hasSuffix(" 2"))
    #expect(s.templates[1].name.utf16.count == 40)
    let observed7 = !s.ensureTemplates()
    #expect(observed7)
  }
  @Test func danglingScheduleRemoved() {
    var s = ready()
    var schedule = SprintSchedule()
    schedule.templateId = "missing"
    s.schedules = [schedule]
    s.ensureTemplates()
    #expect(s.schedules.isEmpty)
  }
  @Test func deletingTemplateDeletesSchedules() {
    var s = ready()
    s.ensureTemplates()
    let id = s.templates[0].id
    var r = SprintSchedule()
    r.templateId = id
    s.schedules = [r, r]
    let observed8 = s.deleteTemplate(id) == 2
    #expect(observed8)
    #expect(s.schedules.isEmpty)
    #expect(s.templates.count == 2)
  }
  @Test func profileFallback() {
    let s = ready()
    var t = StudyTemplate()
    t.profileId = "gone"
    #expect(s.profile(for: t).id == s.activeProfileId)
  }
  @Test func scheduleDefaultsAndNormalization() {
    var s = SprintSchedule()
    #expect(s.startMinuteOfDay == 1020)
    #expect(s.askFirst && s.enabled)
    s.startMinuteOfDay = 9999
    s.days = [9, 1, 1, -1, 0]
    let observed9 = s.normalize()
    #expect(observed9)
    #expect(s.days == [0, 1])
    #expect(s.startMinuteOfDay == 1439)
    let observed10 = !s.normalize()
    #expect(observed10)
  }
  @Test func scheduleSkipRetains14Days() {
    var s = SprintSchedule()
    let d = LocalDay(2026, 10, 26)
    s.skip(d.adding(-15))
    s.skip(d.adding(-14))
    s.skip(d)
    s.skip(d)
    #expect(s.skippedDatesLocal == [d.adding(-14), d])
  }
  func scheduled(minute: Int = 17 * 60) -> SprintSchedule {
    var s = SprintSchedule()
    s.id = "a"
    s.days = [0, 1, 2, 3, 4, 5, 6]
    s.startMinuteOfDay = minute
    return s
  }
  @Test func scheduleNoDaysNoStart() {
    #expect(ScheduleMatcher.nextStart(SprintSchedule(), after: instant(), zone: utc) == nil)
  }
  @Test func scheduleRangeExclusiveInclusive() {
    let s = scheduled()
    let start = instant("2026-10-26T17:00:00Z")
    #expect(
      ScheduleMatcher.startsBetween(s, from: start.addingTimeInterval(-1), to: start, zone: utc)
        == [start])
    #expect(
      ScheduleMatcher.startsBetween(s, from: start, to: start.addingTimeInterval(1), zone: utc)
        .isEmpty)
  }
  @Test func nextStartStrictlyAfter() {
    let s = scheduled()
    let start = instant("2026-10-26T17:00:00Z")
    #expect(
      ScheduleMatcher.nextStart(s, after: start, zone: utc) == start.addingTimeInterval(86400))
  }
  @Test func springForwardFirstRealMinute() {
    let zone = TimeZone(identifier: "America/New_York")!
    #expect(
      ScheduleMatcher.startOnDate(scheduled(minute: 150), day: LocalDay(2026, 3, 8), zone: zone)
        == instant("2026-03-08T07:00:00Z"))
  }
  @Test func fallBackFirstOccurrenceOnly() {
    let zone = TimeZone(identifier: "America/New_York")!
    let s = scheduled(minute: 90)
    #expect(
      ScheduleMatcher.startOnDate(s, day: LocalDay(2026, 11, 1), zone: zone)
        == instant("2026-11-01T05:30:00Z"))
    #expect(
      ScheduleMatcher.startsBetween(
        s, from: instant("2026-11-01T00:00:00Z"), to: instant("2026-11-02T00:00:00Z"), zone: zone
      ).count == 1)
  }
  @Test func lookBackBounded() {
    #expect(
      ScheduleMatcher.startsBetween(scheduled(), from: .distantPast, to: instant(), zone: utc).count
        <= 8)
  }
  @Test func headsUpFiveMinutesBefore() {
    let start = instant("2026-10-26T17:00:00Z")
    let actions = SchedulePlanner().decide(
      [scheduled()], lastTick: start.addingTimeInterval(-310), now: start.addingTimeInterval(-300),
      zone: utc)
    #expect(actions.count == 1)
    #expect(actions[0].kind == .headsUp)
  }
  @Test func headsUpDeduped() {
    let s = scheduled()
    let start = instant("2026-10-26T17:00:00Z")
    #expect(
      SchedulePlanner().decide(
        [s], lastTick: start.addingTimeInterval(-310), now: start.addingTimeInterval(-300),
        zone: utc, headsUpShown: [SchedulePlanner.headsUpKey(s, start: start)]
      ).isEmpty)
  }
  @Test func onTimeStarts() {
    let start = instant("2026-10-26T17:00:00Z")
    let a = SchedulePlanner().decide(
      [scheduled()], lastTick: start.addingTimeInterval(-15), now: start, zone: utc)
    #expect(a.count == 1)
    #expect(a[0].kind == .start)
  }
  @Test func evenRecentStartAfterGapOnlyOffered() {
    let start = instant("2026-10-26T17:00:00Z")
    let a = SchedulePlanner().decide(
      [scheduled()], lastTick: start.addingTimeInterval(-61), now: start, zone: utc)
    #expect(a.count == 1)
    #expect(a[0].kind == .offerMissed)
  }
  @Test func lateWindowBoundaryInclusive() {
    let start = instant("2026-10-26T17:00:00Z")
    let p = SchedulePlanner()
    #expect(!p.cardHasExpired(start: start, now: start.addingTimeInterval(1800)))
    #expect(p.cardHasExpired(start: start, now: start.addingTimeInterval(1800.01)))
    #expect(
      p.decide(
        [scheduled()], lastTick: start.addingTimeInterval(-100),
        now: start.addingTimeInterval(1801), zone: utc
      ).isEmpty)
  }
  @Test func disabledAndSkippedSchedulesDoNothing() {
    let start = instant("2026-10-26T17:00:00Z")
    var s = scheduled()
    s.enabled = false
    let p = SchedulePlanner()
    #expect(p.decide([s], lastTick: start.addingTimeInterval(-15), now: start, zone: utc).isEmpty)
    s.enabled = true
    s.skip(LocalDay(2026, 10, 26))
    #expect(p.decide([s], lastTick: start.addingTimeInterval(-15), now: start, zone: utc).isEmpty)
  }
  @Test func onlyLatestMissedWithStableTie() {
    let start = instant("2026-10-26T17:00:00Z")
    var a = scheduled(minute: 16 * 60 + 59)
    a.id = "b"
    var b = scheduled()
    b.id = "c"
    var c = b
    c.id = "a"
    let actions = SchedulePlanner().decide(
      [a, b, c], lastTick: start.addingTimeInterval(-600), now: start, zone: utc)
    #expect(actions.count == 1)
    #expect(actions[0].schedule.id == "a")
  }
  @Test func lastTickSeedClamps() {
    #expect(SchedulePlanner.seedLastTick(nil, now: instant()) == instant())
    #expect(
      SchedulePlanner.seedLastTick(instant().addingTimeInterval(1), now: instant()) == instant())
    #expect(
      SchedulePlanner.seedLastTick(.distantPast, now: instant())
        == instant().addingTimeInterval(-8 * 86400))
  }
  @Test func scheduleTestTimings() {
    let p = SchedulePlanner(testTimings: true)
    #expect(p.tickInterval == 1)
    #expect(p.onTime == 3)
    #expect(p.headsUpLead == 15)
    #expect(p.lateWindow == 30)
  }
}
