import Foundation

public enum HistoryStats {
  public static let heatmapDays = 30
  public static let steps = 5
  public struct Week: Equatable, Sendable {
    public let start: LocalDay
    public let end: LocalDay
    public let focusMinutes: Double
    public let sprintsCompleted: Int
    public let distractions: Int
    public let turnedBack: Int
  }
  public struct Cell: Equatable, Sendable {
    public let day: LocalDay
    public let minutes: Int
    public let step: Int
  }
  public static func weekStart(_ day: LocalDay) -> LocalDay {
    var c = Calendar(identifier: .gregorian)
    c.timeZone = TimeZone(secondsFromGMT: 0)!
    let weekday = c.component(.weekday, from: day.date(calendar: c))
    return day.adding(-((weekday + 5) % 7))
  }
  public static func weekEnd(_ day: LocalDay) -> LocalDay { weekStart(day).adding(6) }
  public static func forWeek(
    _ sessions: [FocusSession], day: LocalDay, calendar: Calendar = .current
  ) -> Week {
    let start = weekStart(day)
    let end = weekEnd(day)
    let rows = sessions.filter {
      let d = LocalDay($0.startedUtc, calendar: calendar)
      return d >= start && d <= end
    }
    return Week(
      start: start, end: end,
      focusMinutes: roundEven(rows.reduce(0) { $0 + $1.actualMinutes }, digits: 1),
      sprintsCompleted: rows.filter(\.completed).count,
      distractions: rows.reduce(0) { $0 + $1.blocksEnforced },
      turnedBack: rows.reduce(0) { $0 + $1.turnedBack })
  }
  public static func turnedBackText(_ n: Int) -> String {
    n <= 0 ? "" : "Turned back \(n) \(n == 1 ? "time" : "times")"
  }
  public static func step(minutes: Int, peak: Int) -> Int {
    if minutes <= 0 { return 0 }
    if peak <= 0 { return 1 }
    return clamp(Int(ceil(Double(minutes) / Double(peak) * 4)), 1, 4)
  }
  public static func heatmap(
    _ sessions: [FocusSession], today: LocalDay, days: Int = 30, calendar: Calendar = .current
  ) -> [Cell] {
    guard days > 0 else { return [] }
    let start = today.adding(-(days - 1))
    var sums: [LocalDay: Double] = [:]
    for s in sessions {
      let d = LocalDay(s.startedUtc, calendar: calendar)
      if d >= start && d <= today { sums[d, default: 0] += s.actualMinutes }
    }
    let minutes = sums.mapValues { Int(roundEven($0)) }
    let peak = minutes.values.max() ?? 0
    return (0..<days).map {
      let d = start.adding($0)
      let m = minutes[d] ?? 0
      return Cell(day: d, minutes: m, step: step(minutes: m, peak: peak))
    }
  }
  public static func mostBlocked(_ apps: [BlockedApp]) -> String {
    apps.filter { $0.blockCount > 0 }.sorted { a, b in
      a.blockCount == b.blockCount
        ? a.displayName.lowercased() < b.displayName.lowercased() : a.blockCount > b.blockCount
    }.first?.displayName ?? ""
  }
  public static func newestSessions(_ sessions: [FocusSession]) -> [FocusSession] {
    sessions.sorted { $0.startedUtc > $1.startedUtc }
  }
}
