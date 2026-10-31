import Foundation

public enum ScheduleStartPolicy {
  public static func mustOffer(kind: ScheduleActionKind, askFirst: Bool, matchingHeadsUp: Bool) -> Bool {
    kind != .start || (askFirst && !matchingHeadsUp)
  }
}
