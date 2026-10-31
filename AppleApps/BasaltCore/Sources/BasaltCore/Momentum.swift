import Foundation

public enum Momentum {
  public static func gain(plannedMinutes: Int) -> Double {
    10 * clamp(Double(plannedMinutes) / 25, 0.5, 3)
  }
  public static func after(_ score: Double, session: FocusSession) -> Double {
    if session.interrupted { return score }
    return session.completed
      ? roundEven(score + gain(plannedMinutes: session.plannedMinutes), digits: 1)
      : EndSprintPolicy.momentumAfterEndingEarly(score, shield: session.shield)
  }
}
public enum MomentumTrend {
  public static let days = 30
  public struct Point: Equatable, Sendable {
    public let day: LocalDay
    public let score: Double
  }
  public static func points(
    _ sessions: [FocusSession], today: LocalDay, days: Int = 30, calendar: Calendar = .current
  ) -> [Point] {
    guard days > 0 else { return [] }
    let start = today.adding(-(days - 1))
    var score = 0.0
    var byDay: [LocalDay: Double] = [:]
    var opening = 0.0
    for s in sessions.sorted(by: { $0.startedUtc < $1.startedUtc }) {
      score = Momentum.after(score, session: s)
      let day = LocalDay(s.startedUtc, calendar: calendar)
      byDay[day] = score
      if day < start { opening = score }
    }
    var running = opening
    return (0..<days).map { i in
      let day = start.adding(i)
      running = byDay[day] ?? running
      return Point(day: day, score: running)
    }
  }
  public static func ceiling(_ points: [Point]) -> Double {
    let peak = points.map(\.score).max() ?? 0
    return peak <= 0 ? 10 : peak
  }
  public static let explanation = [
    "Finishing a sprint adds 10 points for a 25-minute one, scaled by how long it was: 5 points at the least, 30 at the most.",
    "Ending a sprint early takes a share of what you have, plus a little: about 15% and 2 points at Soft or Firm, 30% and 5 at Sealed. It never goes below zero.",
    "Nothing happens while you are away. Momentum does not decay overnight and it never resets, so a quiet week costs you nothing and a bad day is not the end of anything.",
  ]
}
