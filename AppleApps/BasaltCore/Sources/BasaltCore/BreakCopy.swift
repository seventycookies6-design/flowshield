import Foundation

public enum BreakCopy {
  public static func panelText(
    inSleepWindow: Bool, onBreak: Bool, isLong: Bool, minutes: Int, sleepEndsText: String
  ) -> String {
    if onBreak {
      return inSleepWindow
        ? "The sprint's shield is down, but your nightly sleep shield is still up — blocked apps are still closed until it ends at \(sleepEndsText)."
        : "The shield is down. Blocked apps are allowed until the break ends."
    }
    if isLong {
      return inSleepWindow
        ? "4 sprints in a row, so this break is \(minutes) minutes. The sprint's shield comes down, but your nightly sleep shield stays up until \(sleepEndsText), so blocked apps are still closed."
        : "4 sprints in a row, so this break is \(minutes) minutes. The shield stays down while it runs."
    }
    return inSleepWindow
      ? "\(minutes) minutes with the sprint's shield down, but your nightly sleep shield stays up until \(sleepEndsText), so blocked apps are still closed."
      : "\(minutes) minutes with the shield down. It changes nothing about your momentum."
  }
  public static func caption(inSleepWindow: Bool, resumed: Bool) -> String {
    let prefix = resumed ? "Break resumed —\n" : "Break — "
    return prefix + (inSleepWindow ? "sleep shield still up" : "the shield is down")
  }
  public static func endingSoon(inSleepWindow: Bool, sleepEndsText: String) -> String {
    inSleepWindow
      ? "Nearly there — the sprint's shield comes down when the time is up, but your nightly sleep shield stays up until \(sleepEndsText)."
      : "Nearly there — the shield comes down when the time is up."
  }
}
