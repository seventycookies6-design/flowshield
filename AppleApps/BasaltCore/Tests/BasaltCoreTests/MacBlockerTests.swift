import Foundation
import Testing
@testable import BasaltCore

struct MacBlockerTests {
  let now = Date(timeIntervalSince1970: 1_800_000_000)
  func target(_ id: String = "com.apple.calculator", process: String = "Calculator") -> BlockedApp {
    var a = BlockedApp(); a.bundleIdentifier = id; a.processName = process; return a
  }
  @Test func protectedAppsAlwaysWin() {
    for id in ["com.apple.finder", "com.apple.Terminal", "com.apple.dt.Xcode", "com.apple.systempreferences", "com.basaltfocus.mac", "com.apple.unknown.daemon"] {
      let app = RunningAppIdentity(bundleIdentifier: id, executableName: "unknown", isRegular: true)
      #expect(MacBlockerPolicy.isProtected(app))
      #expect(MacBlockerPolicy.match(app, targets: [target(id)]) == nil)
    }
  }
  @Test func explicitlyListedAppleUserAppsCanBeBlocked() {
    for id in ["com.apple.calculator", "com.apple.Safari", "com.apple.Music"] {
      let app = RunningAppIdentity(bundleIdentifier: id, executableName: "Anything", isRegular: true)
      #expect(MacBlockerPolicy.match(app, targets: [target(id)]) == 0)
      #expect(MacBlockerPolicy.match(app, targets: [target("", process: "Anything")]) == nil)
    }
  }
  @Test func bundleMatchPrecedesExecutableFallback() {
    let app = RunningAppIdentity(bundleIdentifier: "org.example.game", executableName: "Game", isRegular: true)
    #expect(MacBlockerPolicy.match(app, targets: [target("", process: "game"), target("ORG.EXAMPLE.GAME")]) == 1)
    #expect(MacBlockerPolicy.match(app, targets: [target("", process: "game")]) == 0)
    var disabled = target("org.example.game"); disabled.isEnabled = false
    #expect(MacBlockerPolicy.match(app, targets: [disabled]) == nil)
  }
  @Test func softNeverClosesAndHardKillIsExplicit() {
    #expect(MacBlockerPolicy.action(shield: .soft, hardKill: false, deadline: nil, now: now) == .notice)
    #expect(MacBlockerPolicy.action(shield: .soft, hardKill: true, deadline: nil, now: now) == .forceTerminate)
  }
  @Test func graceDeadlineIsInclusive() {
    for shield in [ShieldLevel.firm, .sealed] {
      #expect(MacBlockerPolicy.action(shield: shield, hardKill: false, deadline: nil, now: now) == .requestTermination)
      #expect(MacBlockerPolicy.action(shield: shield, hardKill: false, deadline: now.addingTimeInterval(1), now: now) == .wait)
      #expect(MacBlockerPolicy.action(shield: shield, hardKill: false, deadline: now, now: now) == .forceTerminate)
    }
  }
  @Test func systemExecutablesAreProtectedEvenWithoutBundle() {
    for name in ["Finder", "Dock", "loginwindow", "SystemUIServer", "WindowServer", "ControlCenter", "NotificationCenter", "Spotlight", "System Settings", "Activity Monitor", "Terminal", "Xcode", "Basalt", "python3", "node", "dotnet", "code", "claude", "iTerm2"] {
      #expect(MacBlockerPolicy.isProtected(.init(bundleIdentifier: "", executableName: name, isRegular: true)))
    }
  }
  @Test func activationLinkOnlyPrefillsWellShapedKeys() {
    #expect(ActivationLink.key(from: "flowshield://activate/?key=fs-1234-5678-9abc-defg") == "FS-1234-5678-9ABC-DEFG")
    for link in ["https://activate?key=FS-1234-5678-9ABC-DEFG", "flowshield://start", "flowshield://activate/other?key=FS-1234-5678-9ABC-DEFG", "flowshield://activate?key=bad"] {
      #expect(ActivationLink.key(from: link) == nil)
    }
  }
  @Test func schedulesAskBeforeStartingUnlessAHeadsUpWasAlreadyOffered() {
    #expect(ScheduleStartPolicy.mustOffer(kind: .offerMissed, askFirst: false, matchingHeadsUp: true))
    #expect(ScheduleStartPolicy.mustOffer(kind: .headsUp, askFirst: true, matchingHeadsUp: false))
    #expect(ScheduleStartPolicy.mustOffer(kind: .start, askFirst: true, matchingHeadsUp: false))
    #expect(!ScheduleStartPolicy.mustOffer(kind: .start, askFirst: true, matchingHeadsUp: true))
    #expect(!ScheduleStartPolicy.mustOffer(kind: .start, askFirst: false, matchingHeadsUp: false))
  }
}
