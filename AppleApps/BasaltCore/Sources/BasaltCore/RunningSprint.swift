import Foundation

public enum SprintResume: Sendable { case resume, recordCompleted, recordInterrupted, discard }
public struct RunningSprint: Codable, Equatable, Sendable {
  public static let completedIfWatchedFraction = 0.5
  public static let heartbeatInterval: TimeInterval = 30
  public static let heartbeatCap: TimeInterval = 60
  public var startedUtc: Date = .distantPast
  public var plannedMinutes: Int = 0
  public var shield: ShieldLevel = .firm
  public var momentumAtStart: Double = 0
  public var intention: String = ""
  public var activeProfileId: String = ""
  public var cycleSprintsPlanned: Int = 0
  public var cycleSprintsDone: Int = 0
  public var templateBreakMinutes: Int? = nil
  public var lastSeenUtc: Date = .distantPast
  public var watchedMinutes: Double? = nil
  public init() {}
  public var endsUtc: Date { startedUtc.addingTimeInterval(Double(plannedMinutes) * 60) }
  public var watchedSoFar: Double {
    clamp(
      watchedMinutes ?? min(lastSeenUtc, endsUtc).timeIntervalSince(startedUtc) / 60, 0,
      Double(max(plannedMinutes, 0)))
  }
  public mutating func noteStillWatching(_ now: Date, cap: TimeInterval = heartbeatCap) {
    let stretch = now.timeIntervalSince(lastSeenUtc)
    if stretch > 0 { watchedMinutes = (watchedMinutes ?? 0) + min(stretch, cap) / 60 }
    lastSeenUtc = now
  }
  public mutating func resume(at now: Date) {
    // Capture the legacy estimate before advancing LastSeen: the closed gap earns nothing.
    watchedMinutes = watchedSoFar
    lastSeenUtc = now
  }
  public func decide(_ now: Date) -> SprintResume {
    if plannedMinutes <= 0 { return .discard }
    if now < endsUtc { return .resume }
    return watchedSoFar >= Double(plannedMinutes) * Self.completedIfWatchedFraction
      ? .recordCompleted : .recordInterrupted
  }
  public static func recordedEnd(
    start: Date, plannedEnd: Date, watchedMinutes: Double, now: Date, interrupted: Bool
  ) -> Date {
    interrupted ? start.addingTimeInterval(watchedMinutes * 60) : min(now, plannedEnd)
  }
  public func session(now: Date, completed: Bool, interrupted: Bool = false) -> FocusSession {
    var s = FocusSession()
    s.startedUtc = startedUtc
    s.plannedMinutes = plannedMinutes
    s.shield = shield
    s.momentumAtStart = momentumAtStart
    s.intention = intention
    s.completed = completed
    s.interrupted = interrupted
    s.endedUtc = Self.recordedEnd(
      start: startedUtc, plannedEnd: endsUtc, watchedMinutes: watchedSoFar, now: now,
      interrupted: interrupted)
    return s
  }
}

extension RunningSprint {
  private enum CodingKeys: String, CodingKey {
    case startedUtc, plannedMinutes, shield, momentumAtStart, intention, activeProfileId,
      cycleSprintsPlanned, cycleSprintsDone, templateBreakMinutes, lastSeenUtc, watchedMinutes
  }
  public init(from decoder: any Decoder) throws {
    self.init()
    let c = try decoder.container(keyedBy: CodingKeys.self)
    startedUtc = try c.decodeIfPresent(Date.self, forKey: .startedUtc) ?? startedUtc
    plannedMinutes = try c.decodeIfPresent(Int.self, forKey: .plannedMinutes) ?? plannedMinutes
    shield = (try? c.decodeIfPresent(ShieldLevel.self, forKey: .shield)) ?? shield
    momentumAtStart =
      try c.decodeIfPresent(Double.self, forKey: .momentumAtStart) ?? momentumAtStart
    intention = try c.decodeIfPresent(String.self, forKey: .intention) ?? intention
    activeProfileId =
      try c.decodeIfPresent(String.self, forKey: .activeProfileId) ?? activeProfileId
    cycleSprintsPlanned =
      try c.decodeIfPresent(Int.self, forKey: .cycleSprintsPlanned) ?? cycleSprintsPlanned
    cycleSprintsDone =
      try c.decodeIfPresent(Int.self, forKey: .cycleSprintsDone) ?? cycleSprintsDone
    templateBreakMinutes =
      try c.decodeIfPresent(Int.self, forKey: .templateBreakMinutes) ?? templateBreakMinutes
    lastSeenUtc = try c.decodeIfPresent(Date.self, forKey: .lastSeenUtc) ?? lastSeenUtc
    watchedMinutes = try c.decodeIfPresent(Double.self, forKey: .watchedMinutes) ?? watchedMinutes
  }
}
