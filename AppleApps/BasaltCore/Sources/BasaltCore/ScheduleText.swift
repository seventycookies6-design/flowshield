import Foundation

public enum ScheduleText {
  private static let order = [1, 2, 3, 4, 5, 6, 0]
  private static let short = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
  public static func days(_ days: [Int]) -> String {
    let ordered = order.filter(Set(days).contains)
    if ordered.isEmpty { return "No days" }
    if ordered.count == 7 { return "Every day" }
    if ordered == [1, 2, 3, 4, 5] { return "Weekdays" }
    if ordered == [6, 0] { return "Weekends" }
    if ordered.count >= 3,
      order.firstIndex(of: ordered.last!)! - order.firstIndex(of: ordered.first!)! == ordered.count
        - 1
    {
      return short[ordered.first!] + "–" + short[ordered.last!]
    }
    return ordered.map { short[$0] }.joined(separator: ", ")
  }
  public static func time(_ minute: Int) -> String {
    let m = clamp(minute, 0, 1439)
    return String(format: "%02d:%02d", m / 60, m % 60)
  }
  public static func nextUp(template: String, start: Date, now: Date, calendar: Calendar = .current)
    -> String
  {
    let startDay = LocalDay(start, calendar: calendar)
    let today = LocalDay(now, calendar: calendar)
    let hour = calendar.component(.hour, from: start)
    let minute = calendar.component(.minute, from: start)
    let weekday = short[calendar.component(.weekday, from: start) - 1]
    let when =
      startDay <= today
      ? (hour >= 17 ? "tonight" : "today")
      : startDay == today.adding(1)
        ? "tomorrow" : startDay >= today.adding(7) ? "next \(weekday)" : weekday
    return "Next: \(when) \(time(hour * 60 + minute)) · \(template)"
  }
}
