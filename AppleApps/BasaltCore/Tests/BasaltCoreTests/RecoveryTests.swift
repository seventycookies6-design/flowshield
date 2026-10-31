import Foundation

import Testing

@testable import BasaltCore

struct RecoveryTests {
  @Test func legacyEstimateClampedLow() {
    var r = running(watched: nil)
    r.lastSeenUtc = r.startedUtc.addingTimeInterval(-60)
    #expect(r.watchedSoFar == 0)
  }
  @Test func legacyEstimateClampedHigh() {
    var r = running(watched: nil)
    r.lastSeenUtc = r.endsUtc.addingTimeInterval(900)
    #expect(r.watchedSoFar == 25)
  }
  @Test func explicitWatchedWins() {
    var r = running(watched: 2)
    r.lastSeenUtc = r.endsUtc
    #expect(r.watchedSoFar == 2)
  }
  @Test func heartbeatCapped() {
    var r = running()
    r.noteStillWatching(r.startedUtc.addingTimeInterval(3600))
    #expect(r.watchedMinutes == 1)
    #expect(r.lastSeenUtc == r.startedUtc.addingTimeInterval(3600))
  }
  @Test func heartbeatAccumulates() {
    var r = running()
    r.noteStillWatching(r.startedUtc.addingTimeInterval(30))
    r.noteStillWatching(r.startedUtc.addingTimeInterval(60))
    #expect(r.watchedMinutes == 1)
  }
  @Test func backwardsHeartbeatGivesNoCredit() {
    var r = running(watched: 2)
    r.noteStillWatching(r.startedUtc.addingTimeInterval(-60))
    #expect(r.watchedMinutes == 2)
  }
  @Test func resumeLegacyBeforeAdvancingClock() {
    var r = running(watched: nil)
    r.lastSeenUtc = r.startedUtc.addingTimeInterval(120)
    r.resume(at: r.startedUtc.addingTimeInterval(1200))
    #expect(r.watchedMinutes == 2)
    #expect(r.lastSeenUtc == r.startedUtc.addingTimeInterval(1200))
  }
  @Test func repeatedResumesEarnNoGap() {
    var r = running(watched: 2)
    for n in 1...5 { r.resume(at: r.startedUtc.addingTimeInterval(Double(n) * 100)) }
    #expect(r.watchedSoFar == 2)
  }
  @Test func stillTimeResumesEvenUnwatched() {
    let r = running()
    #expect(r.decide(r.endsUtc.addingTimeInterval(-1)) == .resume)
  }
  @Test func exactHalfCompletes() {
    let r = running(watched: 12.5)
    #expect(r.decide(r.endsUtc) == .recordCompleted)
  }
  @Test func lessThanHalfInterrupts() {
    let r = running(watched: 12.49)
    #expect(r.decide(r.endsUtc) == .recordInterrupted)
  }
  @Test func invalidDurationDiscarded() {
    #expect(running(minutes: 0).decide(instant()) == .discard)
    #expect(running(minutes: -5).decide(instant()) == .discard)
  }
  @Test func interruptedEndUsesWatchedNotLastSeen() {
    let r = running(watched: 3)
    #expect(
      r.session(now: r.endsUtc.addingTimeInterval(999), completed: false, interrupted: true)
        .actualMinutes == 3)
  }
  @Test func lateCompletionCapped() {
    let r = running(watched: 25)
    #expect(r.session(now: r.endsUtc.addingTimeInterval(3600), completed: true).actualMinutes == 25)
  }
  @Test func lateEarlyClickStillEarlyButCapped() {
    let r = running()
    let s = r.session(now: r.endsUtc.addingTimeInterval(3600), completed: false)
    #expect(s.actualMinutes == 25)
    #expect(s.endedEarly)
  }
  @Test func realEarlyEndUsesNow() {
    let r = running()
    #expect(
      r.session(now: r.startedUtc.addingTimeInterval(600), completed: false).actualMinutes == 10)
  }
  @Test func recoverRestoresAllFieldsAndDropsBreak() {
    var s = ready()
    var r = running(watched: 2)
    r.shield = .sealed
    r.intention = "read"
    r.cycleSprintsPlanned = 3
    r.cycleSprintsDone = 1
    r.templateBreakMinutes = 10
    r.activeProfileId = s.activeProfileId
    s.activeSprint = r
    s.activeBreak = RunningBreak()
    #expect(SprintLifecycle.recover(&s, now: r.startedUtc.addingTimeInterval(300)) == .resume)
    #expect(s.activeBreak == nil)
    #expect(s.activeSprint?.shield == .sealed)
    #expect(s.activeSprint?.templateBreakMinutes == 10)
    #expect(s.activeSprint?.cycleSprintsDone == 1)
    #expect(s.activeSprint?.intention == "read")
    #expect(s.activeSprint?.watchedMinutes == 2)
  }
  @Test func interruptedRecoveryCostsNothing() {
    var s = ready()
    s.momentumScore = 40
    s.activeSprint = running(watched: 3)
    s.completedSprintsInARow = 2
    #expect(
      SprintLifecycle.recover(&s, now: instant().addingTimeInterval(3600)) == .recordInterrupted)
    #expect(s.momentumScore == 40)
    #expect(s.sessions[0].interrupted)
    #expect(s.sessions[0].actualMinutes == 3)
    #expect(s.completedSprintsInARow == 0)
  }
  @Test func completedRecoveryKeepsIntentionAndMomentum() {
    var s = ready()
    var r = running(watched: 13)
    r.intention = "read"
    r.momentumAtStart = 20
    s.activeSprint = r
    _ = SprintLifecycle.recover(&s, now: r.endsUtc)
    #expect(s.sessions[0].intention == "read")
    #expect(s.sessions[0].momentumAtStart == 20)
    #expect(s.momentumScore == 10)
  }
}
