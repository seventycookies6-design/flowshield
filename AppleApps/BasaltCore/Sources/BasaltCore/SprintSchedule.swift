import Foundation

public struct SprintSchedule: Codable, Equatable, Sendable {
  public static let skipMemoryDays = 14
  public var id: String = ""
  public var templateId: String = ""
  /// Sunday = 0, matching Windows DayOfWeek.
  public var days: [Int] = []
  public var startMinuteOfDay: Int = 1020
  public var askFirst: Bool = true
  public var enabled: Bool = true
  public var skippedDatesLocal: [LocalDay] = []
  public init() {}
  public func isSkipped(_ day: LocalDay) -> Bool { skippedDatesLocal.contains(day) }
  public mutating func skip(_ day: LocalDay) {
    if !isSkipped(day) { skippedDatesLocal.append(day) }
    skippedDatesLocal.removeAll { $0 < day.adding(-14) }
    skippedDatesLocal.sort()
  }
  @discardableResult public mutating func normalize() -> Bool {
    let before = self
    if trimmed(id).isEmpty { id = newID() }
    startMinuteOfDay = clamp(startMinuteOfDay, 0, 1439)
    days = Set(days.filter { (0...6).contains($0) }).sorted()
    return self != before
  }
}

extension SprintSchedule {
  private enum CodingKeys: String, CodingKey {
    case id, templateId, days, startMinuteOfDay, askFirst, enabled, skippedDatesLocal
  }
  public init(from decoder: any Decoder) throws {
    self.init()
    let c = try decoder.container(keyedBy: CodingKeys.self)
    id = try c.decodeIfPresent(String.self, forKey: .id) ?? id
    templateId = try c.decodeIfPresent(String.self, forKey: .templateId) ?? templateId
    days = try c.decodeIfPresent([Int].self, forKey: .days) ?? days
    startMinuteOfDay =
      try c.decodeIfPresent(Int.self, forKey: .startMinuteOfDay) ?? startMinuteOfDay
    askFirst = try c.decodeIfPresent(Bool.self, forKey: .askFirst) ?? askFirst
    enabled = try c.decodeIfPresent(Bool.self, forKey: .enabled) ?? enabled
    skippedDatesLocal =
      try c.decodeIfPresent([LocalDay].self, forKey: .skippedDatesLocal) ?? skippedDatesLocal
  }
}
