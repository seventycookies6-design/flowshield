import Foundation

public struct FocusSession: Codable, Equatable, Sendable {
  public var startedUtc: Date = .distantPast
  public var endedUtc: Date? = nil
  public var plannedMinutes: Int = 0
  public var shield: ShieldLevel = .firm
  public var completed: Bool = false
  public var blocksEnforced: Int = 0
  public var appsClosed: Int = 0
  public var nudgesSent: Int = 0
  public var turnedBack: Int = 0
  public var momentumAtStart: Double = 0
  public var intention: String = ""
  public var journal: String = ""
  public var interrupted: Bool = false
  public init() {}
  public var endedEarly: Bool { endedUtc != nil && !completed && !interrupted }
  public var actualMinutes: Double {
    endedUtc.map { roundEven($0.timeIntervalSince(startedUtc) / 60, digits: 1) } ?? 0
  }
  public var journalPrompt: String {
    trimmed(intention).isEmpty ? "What moved?" : "You planned: \(trimmed(intention)). What moved?"
  }
  public var outcome: String {
    completed
      ? "completed" : interrupted ? "interrupted" : endedEarly ? "ended early" : "unfinished"
  }
  public var distractionSummary: String {
    if appsClosed > 0 || nudgesSent > 0 {
      return "\(appsClosed) closed · \(nudgesSent) \(nudgesSent == 1 ? "nudge" : "nudges")"
    }
    if blocksEnforced > 0 {
      return "\(blocksEnforced) distraction\(blocksEnforced == 1 ? "" : "s") caught"
    }
    return "No distractions caught"
  }
  public func summaryTitle(momentum: Double) -> String {
    if completed { return "Sprint complete" }
    let delta = Int(roundEven(momentum - momentumAtStart))
    return delta < 0
      ? "Ended early — momentum −\(abs(delta)). It'll recover." : "Ended early. It'll recover."
  }
}

extension FocusSession {
  private enum CodingKeys: String, CodingKey {
    case startedUtc, endedUtc, plannedMinutes, shield, completed, blocksEnforced, appsClosed,
      nudgesSent, turnedBack, momentumAtStart, intention, journal, interrupted
  }
  public init(from decoder: any Decoder) throws {
    self.init()
    let c = try decoder.container(keyedBy: CodingKeys.self)
    startedUtc = try c.decodeIfPresent(Date.self, forKey: .startedUtc) ?? startedUtc
    endedUtc = try c.decodeIfPresent(Date.self, forKey: .endedUtc) ?? endedUtc
    plannedMinutes = try c.decodeIfPresent(Int.self, forKey: .plannedMinutes) ?? plannedMinutes
    shield = (try? c.decodeIfPresent(ShieldLevel.self, forKey: .shield)) ?? shield
    completed = try c.decodeIfPresent(Bool.self, forKey: .completed) ?? completed
    blocksEnforced = try c.decodeIfPresent(Int.self, forKey: .blocksEnforced) ?? blocksEnforced
    appsClosed = try c.decodeIfPresent(Int.self, forKey: .appsClosed) ?? appsClosed
    nudgesSent = try c.decodeIfPresent(Int.self, forKey: .nudgesSent) ?? nudgesSent
    turnedBack = try c.decodeIfPresent(Int.self, forKey: .turnedBack) ?? turnedBack
    momentumAtStart =
      try c.decodeIfPresent(Double.self, forKey: .momentumAtStart) ?? momentumAtStart
    intention = try c.decodeIfPresent(String.self, forKey: .intention) ?? intention
    journal = try c.decodeIfPresent(String.self, forKey: .journal) ?? journal
    interrupted = try c.decodeIfPresent(Bool.self, forKey: .interrupted) ?? interrupted
  }
}
