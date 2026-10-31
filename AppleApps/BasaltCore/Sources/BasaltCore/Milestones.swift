import Foundation

public enum MilestoneKind: String, Codable, CaseIterable, Sendable {
  case firstSealed = "FirstSealed"
  case tenHours = "TenHours"
  case sevenDayStreak = "SevenDayStreak"
  case momentumHundred = "MomentumHundred"
}
public struct MilestoneRecord: Codable, Equatable, Sendable {
  public var id: String = ""
  public var earnedUtc: Date = .distantPast
  public var shown: Bool = false
  public init() {}
}
public enum Milestones {
  public static let tenHoursMinutes = 600.0
  public static let streakDays = 7
  public static let momentumTarget = 100.0
  public static func reached(_ kind: MilestoneKind, _ s: AppSettings) -> Bool {
    switch kind {
    case .firstSealed: s.sessions.contains { $0.completed && $0.shield == .sealed }
    case .tenHours: s.sessions.filter { !$0.interrupted }.reduce(0) { $0 + $1.actualMinutes } >= 600
    case .sevenDayStreak: s.currentStreak >= 7
    case .momentumHundred: s.momentumScore >= 100
    }
  }
  public static func title(_ kind: MilestoneKind) -> String {
    switch kind {
    case .firstSealed: "First Sealed sprint"
    case .tenHours: "Ten hours focused"
    case .sevenDayStreak: "Seven days in a row"
    case .momentumHundred: "Momentum at 100"
    }
  }
  public static func sentence(_ kind: MilestoneKind) -> String {
    switch kind {
    case .firstSealed: "You finished a sprint on Sealed, the strictest shield."
    case .tenHours: "Ten hours of sprints that really ran."
    case .sevenDayStreak: "Seven days in a row with a finished focus day."
    case .momentumHundred: "Finished sprints have built your momentum to 100."
    }
  }
  public static func seed(_ s: inout AppSettings, now: Date) {
    guard !s.milestonesSeeded else { return }
    s.milestonesSeeded = true
    for kind in MilestoneKind.allCases where reached(kind, s) {
      var r = MilestoneRecord()
      r.id = kind.rawValue
      r.earnedUtc = now
      r.shown = true
      s.earnedMilestones.append(r)
    }
  }
  @discardableResult public static func record(_ s: inout AppSettings, now: Date)
    -> [MilestoneRecord]
  {
    var fresh: [MilestoneRecord] = []
    for kind in MilestoneKind.allCases
    where reached(kind, s) && !s.earnedMilestones.contains(where: { $0.id == kind.rawValue }) {
      var r = MilestoneRecord()
      r.id = kind.rawValue
      r.earnedUtc = now
      s.earnedMilestones.append(r)
      fresh.append(r)
    }
    return fresh
  }
  public static func history(_ records: [MilestoneRecord]) -> [MilestoneRecord] {
    records.filter { MilestoneKind(rawValue: $0.id) != nil }.sorted { $0.earnedUtc > $1.earnedUtc }
  }
}

extension MilestoneRecord {
  private enum CodingKeys: String, CodingKey { case id, earnedUtc, shown }
  public init(from decoder: any Decoder) throws {
    self.init()
    let c = try decoder.container(keyedBy: CodingKeys.self)
    id = try c.decodeIfPresent(String.self, forKey: .id) ?? id
    earnedUtc = try c.decodeIfPresent(Date.self, forKey: .earnedUtc) ?? earnedUtc
    shown = try c.decodeIfPresent(Bool.self, forKey: .shown) ?? shown
  }
}
