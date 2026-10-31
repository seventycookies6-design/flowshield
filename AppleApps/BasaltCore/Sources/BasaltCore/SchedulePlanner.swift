import Foundation

public enum ScheduleActionKind: Sendable { case headsUp, start, offerMissed }
public struct ScheduleAction: Sendable {
  public let kind: ScheduleActionKind
  public let schedule: SprintSchedule
  public let startUtc: Date
}
public struct SchedulePlanner: Sendable {
  public var testTimings: Bool
  public init(testTimings: Bool = false) { self.testTimings = testTimings }
  public var headsUpLead: TimeInterval { testTimings ? 15 : 300 }
  public var lateWindow: TimeInterval { testTimings ? 30 : 1800 }
  public var tickInterval: TimeInterval { testTimings ? 1 : 15 }
  public var onTime: TimeInterval { testTimings ? 3 : 60 }
  public static func headsUpKey(_ s: SprintSchedule, start: Date) -> String {
    s.id + "@"
      + formatted(
        start, "yyyy-MM-dd'T'HH:mm:ss'Z'",
        calendar: ScheduleMatcher.calendar(TimeZone(secondsFromGMT: 0)!))
  }
  public static func seedLastTick(_ last: Date?, now: Date) -> Date {
    last.map { clamp($0, now.addingTimeInterval(-ScheduleMatcher.lookBackLimit), now) } ?? now
  }
  public func cardHasExpired(start: Date, now: Date) -> Bool {
    now.timeIntervalSince(start) > lateWindow
  }
  public func decide(
    _ schedules: [SprintSchedule], lastTick: Date, now: Date, zone: TimeZone,
    headsUpShown: Set<String> = []
  ) -> [ScheduleAction] {
    var actions: [ScheduleAction] = []
    var latest: ScheduleAction?
    let gap = now.timeIntervalSince(lastTick) > onTime
    let c = ScheduleMatcher.calendar(zone)
    for s in schedules.filter(\.enabled).sorted(by: { $0.id < $1.id }) {
      if s.askFirst, let next = ScheduleMatcher.nextStart(s, after: now, zone: zone),
        next.timeIntervalSince(now) <= headsUpLead,
        !s.isSkipped(LocalDay(next, calendar: c)),
        !headsUpShown.contains(Self.headsUpKey(s, start: next))
      {
        actions.append(ScheduleAction(kind: .headsUp, schedule: s, startUtc: next))
      }
      for start in ScheduleMatcher.startsBetween(s, from: lastTick, to: now, zone: zone)
      where !s.isSkipped(LocalDay(start, calendar: c)) {
        if !gap {
          actions.append(ScheduleAction(kind: .start, schedule: s, startUtc: start))
        } else if now.timeIntervalSince(start) <= lateWindow
          && (latest == nil || start > latest!.startUtc)
        {
          latest = ScheduleAction(kind: .offerMissed, schedule: s, startUtc: start)
        }
      }
    }
    if let latest { actions.append(latest) }
    return actions.sorted {
      $0.startUtc == $1.startUtc ? $0.schedule.id < $1.schedule.id : $0.startUtc < $1.startUtc
    }
  }
}
