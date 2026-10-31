import Foundation
import Testing
@testable import BasaltCore

struct SourceParityRegressionTests {
  @Test func cancellationPreservesCompletedRunForLongBreak() {
    var s = ready()
    s.completedSprintsInARow = 3
    s.activeSprint = running()
    SprintLifecycle.cancel(&s)
    #expect(s.completedSprintsInARow == 3)
  }
  @Test func recoveryRestoresSavedProfileEvenWhenSealed() {
    var s = ready()
    let original = s.activeProfileId
    let other = s.addProfile(name: "Other")!
    var r = running(watched: 2)
    r.shield = .sealed
    r.activeProfileId = original
    s.activeProfileId = other.id
    s.activeSprint = r
    _ = SprintLifecycle.recover(&s, now: instant().addingTimeInterval(60))
    #expect(s.activeProfileId == original)
  }
  @Test func earlyMinutesSettleGoalAtSameEnd() {
    var s = ready()
    s.dailyGoalKind = .minutes
    s.dailyGoalTarget = 5
    s.activeSprint = running()
    _ = SprintLifecycle.finish(&s, now: instant().addingTimeInterval(600), completed: false, calendar: utcCalendar)
    #expect(s.currentStreak == 1)
  }
}
