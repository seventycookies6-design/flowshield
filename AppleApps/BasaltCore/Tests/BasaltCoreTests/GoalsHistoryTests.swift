import Foundation

import Testing

@testable import BasaltCore

struct GoalsHistoryTests {
  let today = LocalDay(2026, 10, 26)
  @Test func minutesIncludeEarlyAndInterrupted() {
    var s = AppSettings()
    s.dailyGoalKind = .minutes
    s.dailyGoalTarget = 90
    s.sessions = [
      session(minutes: 20, completed: false),
      session(minutes: 3, completed: false, interrupted: true),
    ]
    #expect(DailyGoal.progress(s, day: today, calendar: utcCalendar).done == 23)
  }
  @Test func sprintsOnlyCompleted() {
    var s = AppSettings()
    s.dailyGoalKind = .sprints
    s.dailyGoalTarget = 3
    s.sessions = [
      session(), session(completed: false), session(completed: false, interrupted: true),
    ]
    #expect(DailyGoal.progress(s, day: today, calendar: utcCalendar).done == 1)
  }
  @Test func noGoalReturnsNothing() {
    let s = AppSettings()
    #expect(DailyGoal.progress(s, day: today).target == 0)
    #expect(DailyGoal.progressText(s, day: today) == "")
    #expect(DailyGoal.fraction(s, day: today) == 0)
    #expect(!DailyGoal.canSkip(s, day: today))
  }
  @Test func skipRollingWindow() {
    var s = AppSettings()
    s.dailyGoalKind = .minutes
    s.dailyGoalTarget = 90
    #expect(DailyGoal.skip(&s, day: today))
    #expect(!DailyGoal.skip(&s, day: today))
    #expect(!DailyGoal.canSkip(s, day: today.adding(6)))
    #expect(DailyGoal.canSkip(s, day: today.adding(7)))
    #expect(DailyGoal.unskip(&s, day: today))
    #expect(!DailyGoal.unskip(&s, day: today))
  }
  @Test func skipWinsOverCompleted() {
    var s = AppSettings()
    s.sessions = [session()]
    s.skipDatesLocal = [today]
    #expect(DailyGoal.judge(s, day: today, calendar: utcCalendar) == .skipped)
  }
  @Test func todayNeverBreaksStreak() {
    var s = AppSettings()
    s.currentStreak = 4
    s.streakSettledDayLocal = today.adding(-1)
    DailyGoal.settle(&s, today: today, calendar: utcCalendar)
    #expect(s.currentStreak == 4)
  }
  @Test func missedYesterdayBreaksOnLaunch() {
    var s = AppSettings()
    s.currentStreak = 4
    s.streakSettledDayLocal = today.adding(-2)
    DailyGoal.settle(&s, today: today, calendar: utcCalendar)
    #expect(s.currentStreak == 0)
  }
  @Test func skippedYesterdayHoldsStreak() {
    var s = AppSettings()
    s.currentStreak = 4
    s.streakSettledDayLocal = today.adding(-2)
    s.skipDatesLocal = [today.adding(-1)]
    DailyGoal.settle(&s, today: today, calendar: utcCalendar)
    #expect(s.currentStreak == 4)
  }
  @Test func laterSprintCountsAfterLaunchSettlement() {
    var s = AppSettings()
    s.currentStreak = 4
    DailyGoal.settle(&s, today: today, calendar: utcCalendar)
    s.sessions = [session()]
    #expect(DailyGoal.noteProgress(&s, today: today, calendar: utcCalendar))
    #expect(s.currentStreak == 5)
    #expect(!DailyGoal.noteProgress(&s, today: today, calendar: utcCalendar))
    #expect(s.currentStreak == 5)
  }
  @Test func clockBackDoesNotWalkNegativeRange() {
    var s = AppSettings()
    s.currentStreak = 4
    s.streakSettledDayLocal = today.adding(1)
    #expect(!DailyGoal.settle(&s, today: today, calendar: utcCalendar))
    #expect(s.currentStreak == 4)
  }
  @Test func goalRequiresFullTarget() {
    var s = AppSettings()
    s.dailyGoalKind = .sprints
    s.dailyGoalTarget = 2
    s.sessions = [session()]
    #expect(DailyGoal.judge(s, day: today, calendar: utcCalendar) == .missed)
    s.sessions.append(session())
    #expect(DailyGoal.judge(s, day: today, calendar: utcCalendar) == .counted)
  }
  @Test func progressCapsBarAndText() {
    var s = AppSettings()
    s.dailyGoalKind = .sprints
    s.dailyGoalTarget = 1
    s.sessions = [session(), session()]
    #expect(DailyGoal.progressText(s, day: today, calendar: utcCalendar) == "1 / 1 sprint")
    #expect(DailyGoal.fraction(s, day: today, calendar: utcCalendar) == 1)
  }
  @Test func goalBoundsAndDefaults() {
    #expect(DailyGoal.clampTarget(.minutes, 0) == 5)
    #expect(DailyGoal.clampTarget(.minutes, 999) == 720)
    #expect(DailyGoal.clampTarget(.sprints, 0) == 1)
    #expect(DailyGoal.clampTarget(.sprints, 99) == 20)
    #expect(DailyGoal.clampTarget(.none, 99) == 0)
    #expect(DailyGoal.defaultTarget(.minutes) == 90)
    #expect(DailyGoal.defaultTarget(.sprints) == 3)
  }
  @Test func localStartDayWinsOverEndOrUTC() {
    var c = utcCalendar
    c.timeZone = TimeZone(secondsFromGMT: -7 * 3600)!
    var x = session()
    x.startedUtc = instant("2026-10-27T01:00:00Z")
    x.endedUtc = x.startedUtc.addingTimeInterval(1500)
    var s = AppSettings()
    s.dailyGoalKind = .sprints
    s.dailyGoalTarget = 1
    s.sessions = [x]
    #expect(DailyGoal.met(s, day: today, calendar: c))
  }
  @Test func mondayToSunday() {
    #expect(HistoryStats.weekStart(LocalDay(2026, 10, 25)) == LocalDay(2026, 10, 19))
    #expect(HistoryStats.weekEnd(LocalDay(2026, 10, 25)) == LocalDay(2026, 10, 25))
    #expect(HistoryStats.weekStart(today) == today)
  }
  @Test func allWeekDaysAgree() {
    for i in 0..<7 { #expect(HistoryStats.weekStart(today.adding(i)) == today) }
  }
  @Test func weeklyCountsAllOutcomesButOnlyCompleted() {
    var a = session()
    a.blocksEnforced = 4
    a.turnedBack = 2
    let rows = [
      a, session(minutes: 20, completed: false),
      session(minutes: 3, completed: false, interrupted: true), session(day: 25),
    ]
    let w = HistoryStats.forWeek(rows, day: today, calendar: utcCalendar)
    #expect(w.focusMinutes == 48)
    #expect(w.sprintsCompleted == 1)
    #expect(w.distractions == 4)
    #expect(w.turnedBack == 2)
  }
  @Test func emptyWeekIsZero() {
    let w = HistoryStats.forWeek([], day: today)
    #expect(w.focusMinutes == 0)
    #expect(w.sprintsCompleted == 0)
  }
  @Test func heatmapFullWindow() {
    let cells = HistoryStats.heatmap([], today: today)
    #expect(cells.count == 30)
    #expect(cells.first?.day == today.adding(-29))
    #expect(cells.last?.day == today)
    #expect(cells.allSatisfy { $0.step == 0 })
  }
  @Test func heatmapSumsPerDayAndExcludesOutsidePeak() {
    let cells = HistoryStats.heatmap(
      [session(minutes: 10), session(minutes: 10), session(day: 1, minutes: 200)], today: today,
      days: 2, calendar: utcCalendar)
    #expect(cells.last?.minutes == 20)
    #expect(cells.last?.step == 4)
    #expect(cells.first?.minutes == 0)
  }
  @Test func heatmapBankersRounding() {
    #expect(
      HistoryStats.heatmap([session(minutes: 2.5)], today: today, calendar: utcCalendar).last?
        .minutes == 2)
  }
  @Test func mostBlockedLifetimeCaseInsensitiveTie() {
    var a = BlockedApp()
    a.name = "zebra"
    a.blockCount = 2
    var b = a
    b.name = "Alpha"
    #expect(HistoryStats.mostBlocked([a, b]) == "Alpha")
    b.blockCount = 0
    #expect(HistoryStats.mostBlocked([a, b]) == "zebra")
    #expect(HistoryStats.mostBlocked([b]) == "")
  }
  @Test func turnedBackCopy() {
    #expect(HistoryStats.turnedBackText(0) == "")
    #expect(HistoryStats.turnedBackText(1) == "Turned back 1 time")
    #expect(HistoryStats.turnedBackText(4) == "Turned back 4 times")
  }
  @Test func trendQuietDaysCarryForward() {
    let p = MomentumTrend.points([session(day: 24)], today: today, calendar: utcCalendar)
    #expect(p.count == 30)
    #expect(p.suffix(3).allSatisfy { $0.score == 10 })
  }
  @Test func trendReplaysBeforeWindow() {
    let p = MomentumTrend.points([session(day: 1)], today: today, days: 2, calendar: utcCalendar)
    #expect(p.map(\.score) == [10, 10])
  }
  @Test func trendEarlyEndDips() {
    let p = MomentumTrend.points(
      [session(day: 24), session(day: 25, completed: false)], today: today, days: 3,
      calendar: utcCalendar)
    #expect(p.map(\.score) == [10, 6.5, 6.5])
  }
  @Test func trendInterruptedDoesNothing() {
    let p = MomentumTrend.points(
      [session(day: 24), session(day: 25, completed: false, interrupted: true)], today: today,
      days: 3, calendar: utcCalendar)
    #expect(p.map(\.score) == [10, 10, 10])
  }
  @Test func allEarlyTrendStaysAtFloor() {
    let p = MomentumTrend.points([session(completed: false)], today: today, calendar: utcCalendar)
    #expect(p.allSatisfy { $0.score == 0 })
    #expect(MomentumTrend.ceiling(p) == 10)
  }
  @Test func milestoneThresholds() {
    var s = AppSettings()
    s.sessions = [session(minutes: 600, shield: .sealed)]
    s.currentStreak = 7
    s.momentumScore = 100
    #expect(MilestoneKind.allCases.allSatisfy { Milestones.reached($0, s) })
  }
  @Test func milestoneInterruptedTimeExcluded() {
    var s = AppSettings()
    s.sessions = [session(minutes: 600, completed: false, interrupted: true)]
    #expect(!Milestones.reached(.tenHours, s))
    #expect(!Milestones.reached(.firstSealed, s))
  }
  @Test func milestonesSeedQuietAndRecordOnce() {
    var s = AppSettings()
    s.momentumScore = 100
    Milestones.seed(&s, now: instant())
    #expect(s.earnedMilestones.count == 1)
    #expect(s.earnedMilestones[0].shown)
    Milestones.seed(&s, now: instant())
    #expect(s.earnedMilestones.count == 1)
    s.currentStreak = 7
    let fresh = Milestones.record(&s, now: instant())
    #expect(fresh.count == 1)
    #expect(!fresh[0].shown)
    #expect(Milestones.record(&s, now: instant()).isEmpty)
    s.currentStreak = 0
    #expect(s.earnedMilestones.count == 2)
  }
  @Test func milestoneUnknownOmitted() {
    var r = MilestoneRecord()
    r.id = "unknown"
    #expect(Milestones.history([r]).isEmpty)
  }
}
