import Foundation

public enum ScheduleMatcher {
  public static let lookBackLimit: TimeInterval = 8 * 86400
  public static func calendar(_ zone: TimeZone) -> Calendar {
    var c = Calendar(identifier: .gregorian)
    c.timeZone = zone
    return c
  }
  public static func startOnDate(_ s: SprintSchedule, day: LocalDay, zone: TimeZone) -> Date? {
    let c = calendar(zone)
    let midnight = day.date(calendar: c)
    guard s.days.contains(c.component(.weekday, from: midnight) - 1) else { return nil }
    let minute = clamp(s.startMinuteOfDay, 0, 1439)
    // .nextTime advances a nonexistent time to the first real minute, not 03:30;
    // .first selects the first occurrence of a repeated time at fall-back.
    return c.nextDate(
      after: midnight.addingTimeInterval(-1),
      matching: DateComponents(hour: minute / 60, minute: minute % 60, second: 0),
      matchingPolicy: .nextTime, repeatedTimePolicy: .first, direction: .forward)
  }
  public static func startsBetween(_ s: SprintSchedule, from: Date, to: Date, zone: TimeZone)
    -> [Date]
  {
    guard to > from, !s.days.isEmpty else { return [] }
    let from = max(from, to.addingTimeInterval(-lookBackLimit))
    let c = calendar(zone)
    var day = LocalDay(from, calendar: c).adding(-1)
    let last = LocalDay(to, calendar: c).adding(1)
    var result: [Date] = []
    while day <= last {
      if let start = startOnDate(s, day: day, zone: zone), start > from, start <= to {
        result.append(start)
      }
      day = day.adding(1)
    }
    return result
  }
  public static func nextStart(_ s: SprintSchedule, after: Date, zone: TimeZone) -> Date? {
    let day = LocalDay(after, calendar: calendar(zone))
    for n in 0...8 {
      if let start = startOnDate(s, day: day.adding(n), zone: zone), start > after { return start }
    }
    return nil
  }
}
