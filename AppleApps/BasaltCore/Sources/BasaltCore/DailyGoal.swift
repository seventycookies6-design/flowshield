import Foundation

public enum DailyGoalKind: Int, Codable, Sendable {
  case none = 0
  case minutes = 1
  case sprints = 2
}
public enum DailyGoal {
  public enum DayVerdict: Sendable { case counted, skipped, missed }
  public static let skipsPerWeek = 1
  public static let skipWindowDays = 7
  public static func isSet(_ s: AppSettings) -> Bool {
    s.dailyGoalKind != .none && s.dailyGoalTarget > 0
  }
  public static func clampTarget(_ kind: DailyGoalKind, _ target: Int) -> Int {
    switch kind {
    case .none: 0
    case .minutes: clamp(target, 5, 720)
    case .sprints: clamp(target, 1, 20)
    }
  }
  public static func defaultTarget(_ kind: DailyGoalKind) -> Int {
    kind == .minutes ? 90 : kind == .sprints ? 3 : 0
  }
  public static func progress(_ s: AppSettings, day: LocalDay, calendar: Calendar = .current) -> (
    done: Int, target: Int
  ) {
    guard isSet(s) else { return (0, 0) }
    let sessions = s.sessions.filter { LocalDay($0.startedUtc, calendar: calendar) == day }
    let done =
      s.dailyGoalKind == .minutes
      ? Int(roundEven(sessions.reduce(0) { $0 + $1.actualMinutes }))
      : sessions.filter(\.completed).count
    return (done, s.dailyGoalTarget)
  }
  public static func met(_ s: AppSettings, day: LocalDay, calendar: Calendar = .current) -> Bool {
    let p = progress(s, day: day, calendar: calendar)
    return isSet(s) && p.done >= p.target
  }
  public static func isSkipped(_ s: AppSettings, day: LocalDay) -> Bool {
    s.skipDatesLocal.contains(day)
  }
  public static func skipsUsed(_ s: AppSettings, day: LocalDay) -> Int {
    s.skipDatesLocal.filter { $0 >= day.adding(-6) && $0 <= day }.count
  }
  public static func canSkip(_ s: AppSettings, day: LocalDay) -> Bool {
    isSet(s) && !isSkipped(s, day: day) && skipsUsed(s, day: day) < 1
  }
  @discardableResult public static func skip(_ s: inout AppSettings, day: LocalDay) -> Bool {
    guard canSkip(s, day: day) else { return false }
    s.skipDatesLocal.append(day)
    return true
  }
  @discardableResult public static func unskip(_ s: inout AppSettings, day: LocalDay) -> Bool {
    let n = s.skipDatesLocal.count
    s.skipDatesLocal.removeAll { $0 == day }
    return n != s.skipDatesLocal.count
  }
  public static func judge(_ s: AppSettings, day: LocalDay, calendar: Calendar = .current)
    -> DayVerdict
  {
    if isSkipped(s, day: day) { return .skipped }
    let counted =
      isSet(s)
      ? met(s, day: day, calendar: calendar)
      : s.sessions.contains { $0.completed && LocalDay($0.startedUtc, calendar: calendar) == day }
    return counted ? .counted : .missed
  }
  private static func countIfNew(_ s: inout AppSettings, day: LocalDay, calendar: Calendar) {
    if s.goalMetDayLocal != day && judge(s, day: day, calendar: calendar) == .counted {
      s.goalMetDayLocal = day
      s.currentStreak += 1
    }
  }
  @discardableResult public static func settle(
    _ s: inout AppSettings, today: LocalDay, calendar: Calendar = .current
  ) -> Bool {
    let old = s
    guard let settled = s.streakSettledDayLocal else {
      s.streakSettledDayLocal = today
      countIfNew(&s, day: today, calendar: calendar)
      return s != old
    }
    if today <= settled {
      if today == settled { countIfNew(&s, day: today, calendar: calendar) }
      return s.currentStreak != old.currentStreak
    }
    var day = settled.adding(1)
    while day <= today {
      if day == today {
        countIfNew(&s, day: today, calendar: calendar)
        break
      }
      switch judge(s, day: day, calendar: calendar) {
      case .counted: s.currentStreak += 1
      case .skipped: break
      case .missed: s.currentStreak = 0
      }
      day = day.adding(1)
    }
    s.streakSettledDayLocal = today
    return s != old
  }
  @discardableResult public static func noteProgress(
    _ s: inout AppSettings, today: LocalDay, calendar: Calendar = .current
  ) -> Bool {
    let old = s.goalMetDayLocal
    settle(&s, today: today, calendar: calendar)
    return old != today && s.goalMetDayLocal == today
  }
  public static func fraction(_ s: AppSettings, day: LocalDay, calendar: Calendar = .current)
    -> Double
  {
    let p = progress(s, day: day, calendar: calendar)
    return p.target <= 0 ? 0 : clamp(Double(p.done) / Double(p.target), 0, 1)
  }
  public static func progressText(_ s: AppSettings, day: LocalDay, calendar: Calendar = .current)
    -> String
  {
    guard isSet(s) else { return "" }
    let p = progress(s, day: day, calendar: calendar)
    let unit = s.dailyGoalKind == .minutes ? "minutes" : p.target == 1 ? "sprint" : "sprints"
    return "\(min(p.done, p.target)) / \(p.target) \(unit)"
  }
}
