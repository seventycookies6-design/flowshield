import Foundation

public enum FirstRunPolicy {
  public static let sprintLengths = [25, 45]
  public static let defaultShield = ShieldLevel.firm
  public static func isExistingUser(_ s: AppSettings) -> Bool {
    !s.blockedApps.isEmpty || !s.sessions.isEmpty || s.activeSprint != nil
  }
  public static func shouldShow(
    _ s: AppSettings, hasAccess: Bool, sprintRunning: Bool, skipForTests: Bool = false
  ) -> Bool {
    !skipForTests && !s.firstRunCompleted && !isExistingUser(s) && hasAccess && !sprintRunning
  }
  public static func preTicked(isSuggested: Bool, installedPath: String?, group: String) -> Bool {
    isSuggested && installedPath != nil && group.lowercased() != "browsers"
  }
}
public enum LegalTerms {
  public static let version = "1.1 (23 September 2026)"
  public static let headline = "Before you start"
  public static let dataLossWarning =
    "Basalt closes programs you put on your block list. Any unsaved work in them can be lost. It never closes macOS system processes, shells or common developer tools."
  public static let agreementLine =
    "By continuing you agree to the Terms of Service and the Privacy Policy, and you accept that Basalt is provided as is."
  public static func accepted(_ s: AppSettings) -> Bool { s.termsAcceptedVersion == version }
  public static func accept(_ s: inout AppSettings, now: Date) {
    s.termsAcceptedVersion = version
    s.termsAcceptedUtc = now
  }
  public static func termsURL(_ s: AppSettings) -> String {
    s.websiteUrl.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/legal.html#terms"
  }
  public static func privacyURL(_ s: AppSettings) -> String {
    s.websiteUrl.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/legal.html#privacy"
  }
}
