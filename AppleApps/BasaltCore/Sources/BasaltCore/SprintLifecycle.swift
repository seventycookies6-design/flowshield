import Foundation

public enum SprintStartResult: Equatable, Sendable {
  case started, termsRequired, firstRunRequired, invalidLength, accessLocked, alreadyRunning,
    confirmRunningApps
}
public enum SprintLifecycle {
  /// The caller saves the returned active record before starting enforcement.
  public static func start(
    _ s: inout AppSettings, now: Date, minutes: Int, shield: ShieldLevel, intention: String = "",
    firstRunVisible: Bool = false, runningBlockedApps: Bool = false, confirmed: Bool = false,
    cycle: CycleState = CycleState(), templateBreak: Int? = nil
  ) -> SprintStartResult {
    guard LegalTerms.accepted(s) else { return .termsRequired }
    guard !firstRunVisible else { return .firstRunRequired }
    guard s.activeSprint == nil else { return .alreadyRunning }
    guard SprintLength.isValid(minutes) else { return .invalidLength }
    guard TrialPolicy.hasAccess(s, now: now) else { return .accessLocked }
    guard !runningBlockedApps || confirmed else { return .confirmRunningApps }
    s.ensureProfiles()
    var r = RunningSprint()
    r.startedUtc = now
    r.lastSeenUtc = now
    r.watchedMinutes = 0
    r.plannedMinutes = minutes
    r.shield = shield
    r.momentumAtStart = s.momentumScore
    r.intention = trimmed(cutUTF16(intention, 80))
    r.activeProfileId = s.activeProfile.id
    let next = cycle.onSprintStarted(s.cycleSprints)
    r.cycleSprintsPlanned = next.sprintsPlanned
    r.cycleSprintsDone = next.sprintsDone
    r.templateBreakMinutes = templateBreak
    s.activeBreak = nil
    s.activeSprint = r
    return .started
  }
  public static func cancel(_ s: inout AppSettings) {
    s.activeSprint = nil
  }
  @discardableResult public static func finish(
    _ s: inout AppSettings, now: Date, completed: Bool, interrupted: Bool = false,
    appsClosed: Int = 0, nudges: Int = 0, blocks: Int = 0, turnedBack: Int = 0,
    shortSprints: Bool = false, calendar: Calendar = .current
  ) -> FocusSession? {
    guard let r = s.activeSprint else { return nil }
    var session = r.session(now: now, completed: completed, interrupted: interrupted)
    session.appsClosed = appsClosed
    session.nudgesSent = nudges
    session.blocksEnforced = blocks
    session.turnedBack = turnedBack
    if CycleState.sprintCountsAsProgress(shortSprints: shortSprints) {
      s.sessions.append(session)
      s.momentumScore = Momentum.after(s.momentumScore, session: session)
      if completed && !interrupted {
        DailyGoal.noteProgress(&s, today: LocalDay(now, calendar: calendar), calendar: calendar)
        s.lastSessionDayLocal = LocalDay(now, calendar: calendar)
      }
    }
    s.completedSprintsInARow = completed ? s.completedSprintsInARow + 1 : 0
    s.activeSprint = nil
    Milestones.record(&s, now: now)
    DailyGoal.settle(&s, today: LocalDay(now, calendar: calendar), calendar: calendar)
    return session
  }
  @discardableResult public static func recover(
    _ s: inout AppSettings, now: Date, calendar: Calendar = .current
  ) -> SprintResume? {
    guard var r = s.activeSprint else { return nil }
    let decision = r.decide(now)
    switch decision {
    case .resume:
      if s.findProfile(r.activeProfileId) != nil { s.activeProfileId = r.activeProfileId }
      r.resume(at: now)
      s.activeSprint = r
      s.activeBreak = nil
    case .discard: s.activeSprint = nil
    case .recordCompleted, .recordInterrupted:
      // Recovery records quietly: no summary, break, cycle continuation or milestone cards.
      let completed = decision == .recordCompleted
      let session = r.session(now: now, completed: completed, interrupted: !completed)
      s.sessions.append(session)
      if completed {
        s.momentumScore = Momentum.after(s.momentumScore, session: session)
        DailyGoal.noteProgress(&s, today: LocalDay(now, calendar: calendar), calendar: calendar)
        s.lastSessionDayLocal = LocalDay(now, calendar: calendar)
      }
      s.completedSprintsInARow = completed ? s.completedSprintsInARow + 1 : 0
      s.activeSprint = nil
      DailyGoal.settle(&s, today: LocalDay(now, calendar: calendar), calendar: calendar)
    }
    return decision
  }
  public static func saveJournal(_ s: inout AppSettings, text: String) {
    if !s.sessions.isEmpty { s.sessions[s.sessions.count - 1].journal = trimmed(text) }
  }
}
