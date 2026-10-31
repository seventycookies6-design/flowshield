import Foundation

public struct RunningAppIdentity: Equatable, Sendable {
  public var bundleIdentifier: String
  public var executableName: String
  public var isRegular: Bool
  public init(bundleIdentifier: String, executableName: String, isRegular: Bool) {
    self.bundleIdentifier = bundleIdentifier
    self.executableName = executableName
    self.isRegular = isRegular
  }
}
public enum MacBlockAction: Equatable, Sendable {
  case notice, requestTermination, wait, forceTerminate
}
public enum MacBlockerPolicy {
  private static let protectedNames: Set<String> = [
    "basalt", "finder", "dock", "loginwindow", "systemuiserver", "windowserver",
    "controlcenter", "notificationcenter", "spotlight", "system settings", "system preferences",
    "activity monitor", "terminal", "xcode", "bash", "zsh", "sh", "fish", "sshd",
    "python", "python3", "node", "dotnet", "msbuild", "code", "visual studio code", "claude", "iterm2",
  ]
  private static let protectedIDs: Set<String> = [
    "com.basaltfocus.mac", "com.apple.finder", "com.apple.dock", "com.apple.loginwindow",
    "com.apple.systemuiserver", "com.apple.windowserver", "com.apple.controlcenter",
    "com.apple.notificationcenterui", "com.apple.spotlight", "com.apple.systempreferences",
    "com.apple.activitymonitor", "com.apple.terminal", "com.apple.dt.xcode",
    "com.microsoft.vscode", "com.googlecode.iterm2",
  ]
  // A regular activation policy alone doesn't make an Apple service safe to close.
  private static let userFacingAppleIDs: Set<String> = [
    "com.apple.calculator", "com.apple.safari", "com.apple.music", "com.apple.news",
    "com.apple.tv", "com.apple.appstore", "com.apple.ichat", "com.apple.facetime",
    "com.apple.mail", "com.apple.podcasts", "com.apple.books", "com.apple.ibooksx",
    "com.apple.photos", "com.apple.quicktimeplayerx", "com.apple.textedit", "com.apple.preview",
    "com.apple.freeform", "com.apple.notes", "com.apple.reminders", "com.apple.ical",
    "com.apple.chess", "com.apple.stocks", "com.apple.weather", "com.apple.maps",
  ]
  public static func isProtected(_ app: RunningAppIdentity) -> Bool {
    let id = app.bundleIdentifier.lowercased()
    return protectedIDs.contains(id) || protectedNames.contains(app.executableName.lowercased())
      || (id.hasPrefix("com.apple.") && (!app.isRegular || !userFacingAppleIDs.contains(id)))
  }
  public static func match(_ app: RunningAppIdentity, targets: [BlockedApp]) -> Int? {
    guard !isProtected(app) else { return nil }
    let id = app.bundleIdentifier.lowercased()
    if !id.isEmpty, let i = targets.firstIndex(where: {
      $0.isEnabled && !$0.bundleIdentifier.isEmpty && $0.bundleIdentifier.lowercased() == id
    }) { return i }
    // Apple apps require an explicit bundle-id entry, never an ambiguous process fallback.
    guard !id.hasPrefix("com.apple.") else { return nil }
    return targets.firstIndex { target in
      target.isEnabled && target.allProcessNames.contains {
        $0.lowercased() == app.executableName.lowercased()
      }
    }
  }
  public static func action(
    shield: ShieldLevel, hardKill: Bool, deadline: Date?, now: Date
  ) -> MacBlockAction {
    if hardKill { return .forceTerminate }
    if shield == .soft { return .notice }
    guard let deadline else { return .requestTermination }
    return now < deadline ? .wait : .forceTerminate
  }
}
