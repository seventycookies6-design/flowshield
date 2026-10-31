import Foundation

public enum TrialPolicy {
  public static let days = 7
  public static let endedCopy = "Your free trial has ended. Buy Basalt to start a sprint."
  public static func earliest(_ a: Date?, _ b: Date?) -> Date? { [a, b].compactMap { $0 }.min() }
  @discardableResult public static func ensureStarted(
    _ s: inout AppSettings, recorded: Date?, now: Date
  ) -> Bool {
    if let known = earliest(s.trialStartedUtc, recorded) {
      s.trialStartedUtc = known
      return false
    }
    s.trialStartedUtc = now
    return true
  }
  public static func isActive(start: Date?, now: Date) -> Bool {
    guard let start else { return false }
    return now >= start.addingTimeInterval(-86400) && now < start.addingTimeInterval(7 * 86400)
  }
  public static func daysLeft(start: Date?, now: Date) -> Int {
    guard let start, isActive(start: start, now: now) else { return 0 }
    return clamp(
      Int(ceil(start.addingTimeInterval(7 * 86400).timeIntervalSince(now) / 86400)), 1, 7)
  }
  public static func hasAccess(_ s: AppSettings, now: Date) -> Bool {
    s.isPro || isActive(start: s.trialStartedUtc, now: now)
  }
  public static func shouldLock(
    _ s: AppSettings, now: Date, sprintRunning: Bool, summaryVisible: Bool, journalVisible: Bool
  ) -> Bool {
    !hasAccess(s, now: now) && !sprintRunning && !summaryVisible && !journalVisible
  }
  public static func shouldWarnTomorrow(
    _ s: AppSettings, now: Date, today: LocalDay, sprintRunning: Bool
  ) -> Bool {
    !s.isPro && daysLeft(start: s.trialStartedUtc, now: now) == 1
      && s.trialEndingNotifiedLocal != today
      && NotificationPolicy.shouldShow(.trialEnding, s, sprintRunning: sprintRunning)
  }
}

/// Independent date-only record; delete-everything deliberately leaves it in place.
public struct TrialRecord: Sendable {
  public let url: URL
  public init(url: URL) { self.url = url }
  public func load() -> Date? {
    guard let data = try? Data(contentsOf: url), let text = String(data: data, encoding: .utf8)
    else { return nil }
    return ISO8601DateFormatter().date(from: trimmed(text))
  }
  public func saveEarliest(_ start: Date) throws {
    let date = TrialPolicy.earliest(load(), start)!
    try PrivateFile.write(Data(ISO8601DateFormatter().string(from: date).utf8), to: url)
  }
  @discardableResult public func ensureStarted(_ settings: inout AppSettings, now: Date) throws
    -> Bool
  {
    let started = TrialPolicy.ensureStarted(&settings, recorded: load(), now: now)
    try saveEarliest(settings.trialStartedUtc!)
    return started
  }
}
