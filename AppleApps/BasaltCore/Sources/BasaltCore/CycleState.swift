import Foundation

public enum CyclePhase: String, Codable, Sendable { case idle, sprint, `break` }
public struct CycleState: Codable, Equatable, Sendable {
  public static let choices = [0, 2, 3, 4]
  public static let longBreakEvery = 4
  public static let defaultShortBreakMinutes = 5
  public static let defaultLongBreakMinutes = 15
  public var phase: CyclePhase = .idle
  public var sprintsPlanned: Int = 0
  public var sprintsDone: Int = 0
  public init(phase: CyclePhase = .idle, sprintsPlanned: Int = 0, sprintsDone: Int = 0) {
    self.phase = phase
    self.sprintsPlanned = sprintsPlanned
    self.sprintsDone = sprintsDone
  }
  public var inCycle: Bool { sprintsPlanned > 1 }
  public var sprintNumber: Int { min(sprintsDone + 1, max(sprintsPlanned, 1)) }
  public var cycleLabel: String { inCycle ? "Sprint \(sprintNumber) of \(sprintsPlanned)" : "" }
  public var cycleFinished: Bool { inCycle && sprintsDone >= sprintsPlanned }
  public var startsNextSprint: Bool { inCycle && sprintsDone < sprintsPlanned }
  public static func offersBreak(completed: Bool) -> Bool { completed }
  public static func breakMinutes(completedInARow: Int, short: Int = 5, long: Int = 15) -> Int {
    completedInARow > 0 && completedInARow % 4 == 0 ? long : short
  }
  public static func isValidBreakMinutes(_ value: Int) -> Bool { (1...60).contains(value) }
  public static func breakLength(_ minutes: Int, testTimings: Bool = false) -> TimeInterval {
    testTimings ? 3 : Double(max(0, minutes)) * 60
  }
  public static func sprintLength(_ minutes: Int, shortSprints: Bool = false) -> TimeInterval {
    shortSprints ? 5 : Double(max(0, minutes)) * 60
  }
  public static func sprintCountsAsProgress(shortSprints: Bool = false) -> Bool { !shortSprints }
  public func onSprintStarted(_ planned: Int) -> Self {
    inCycle && !cycleFinished
      ? Self(phase: .sprint, sprintsPlanned: sprintsPlanned, sprintsDone: sprintsDone)
      : Self(phase: .sprint, sprintsPlanned: max(0, planned))
  }
  public func onSprintCompleted() -> Self {
    Self(sprintsPlanned: sprintsPlanned, sprintsDone: sprintsDone + 1)
  }
  public func onSprintAbandoned() -> Self { Self() }
  public func onBreakStarted() -> Self {
    Self(phase: .break, sprintsPlanned: sprintsPlanned, sprintsDone: sprintsDone)
  }
  public func onBreakEnded() -> Self {
    Self(sprintsPlanned: sprintsPlanned, sprintsDone: sprintsDone)
  }
  public func onCycleFinished() -> Self { Self() }
}
public enum BreakResume: Sendable { case resume, endQuietly }
public struct RunningBreak: Codable, Equatable, Sendable {
  public var startedUtc: Date = .distantPast
  public var endsUtc: Date = .distantPast
  public var minutes: Int = 0
  public var sprintsPlanned: Int = 0
  public var sprintsDone: Int = 0
  public var templateBreakMinutes: Int? = nil
  public init() {}
  public func decide(_ now: Date) -> BreakResume { endsUtc <= now ? .endQuietly : .resume }
  public var cycle: CycleState {
    CycleState(phase: .break, sprintsPlanned: sprintsPlanned, sprintsDone: sprintsDone)
  }
}

extension RunningBreak {
  private enum CodingKeys: String, CodingKey {
    case startedUtc, endsUtc, minutes, sprintsPlanned, sprintsDone, templateBreakMinutes
  }
  public init(from decoder: any Decoder) throws {
    self.init()
    let c = try decoder.container(keyedBy: CodingKeys.self)
    startedUtc = try c.decodeIfPresent(Date.self, forKey: .startedUtc) ?? startedUtc
    endsUtc = try c.decodeIfPresent(Date.self, forKey: .endsUtc) ?? endsUtc
    minutes = try c.decodeIfPresent(Int.self, forKey: .minutes) ?? minutes
    sprintsPlanned = try c.decodeIfPresent(Int.self, forKey: .sprintsPlanned) ?? sprintsPlanned
    sprintsDone = try c.decodeIfPresent(Int.self, forKey: .sprintsDone) ?? sprintsDone
    templateBreakMinutes =
      try c.decodeIfPresent(Int.self, forKey: .templateBreakMinutes) ?? templateBreakMinutes
  }
}
