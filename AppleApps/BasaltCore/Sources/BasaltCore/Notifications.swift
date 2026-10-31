import Foundation

public enum NotificationKind: String, Codable, CaseIterable, Sendable {
  case sprintStarted = "SprintStarted"
  case fiveMinutesLeft = "FiveMinutesLeft"
  case sprintComplete = "SprintComplete"
  case sprintInterrupted = "SprintInterrupted"
  case breakOver = "BreakOver"
  case scheduledSprint = "ScheduledSprint"
  case trialEnding = "TrialEnding"
  case appClosing = "AppClosing"
  case updateReady = "UpdateReady"
}
public enum NotificationPolicy {
  public static let endingSoon: TimeInterval = 300
  public static func interruptsFocus(_ kind: NotificationKind) -> Bool {
    kind == .trialEnding || kind == .updateReady
  }
  public static func shouldShow(
    _ kind: NotificationKind, _ settings: AppSettings, sprintRunning: Bool
  ) -> Bool {
    settings.notificationsEnabled && settings.notificationKinds[kind.rawValue, default: true]
      && !(sprintRunning && interruptsFocus(kind))
  }
  public static func tooShortForEndingSoon(_ minutes: Int) -> Bool { minutes <= 6 }
  public static func breakLabel(_ remaining: TimeInterval) -> String {
    let n = Int(max(0, remaining))
    return String(format: "Break · %d:%02d", n / 60, n % 60)
  }
  public static func iconText(_ remaining: TimeInterval) -> String {
    guard remaining > 0 else { return "0" }
    let n = Int(ceil(remaining / 60))
    return n >= 100 ? "\(n / 60)h" : "\(n)"
  }
  public static func menuBarText(
    running: Bool, shield: ShieldLevel, remaining: TimeInterval, onBreak: Bool = false
  ) -> String {
    if onBreak { return "Basalt — \(breakLabel(remaining))" }
    if !running { return "Basalt — no sprint running" }
    let n = max(1, Int(ceil(remaining / 60)))
    return "Basalt — \(ShieldCopy.name(shield)) shield, \(n) minute\(n == 1 ? "" : "s") left"
  }
}
