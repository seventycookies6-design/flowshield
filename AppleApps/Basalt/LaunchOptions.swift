import Foundation
import BasaltCore

struct LaunchOptions: Sendable {
  var dataDirectory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    .appendingPathComponent("Basalt", isDirectory: true)
  var testTimings = false
  var skipOnboarding = false
  var snapshotDirectory: URL?
  var sprint: DebugSprint?
  var isIsolated = false
  struct DebugSprint: Sendable {
    var shield: ShieldLevel
    var minutes: Int
    var bundles: [String]
  }
  init(arguments: [String] = CommandLine.arguments) {
    #if DEBUG
    func value(_ flag: String) -> String? {
      guard let i = arguments.firstIndex(of: flag), i + 1 < arguments.count else { return nil }
      return arguments[i + 1].hasPrefix("--") ? nil : arguments[i + 1]
    }
    if let path = value("--data-dir"), path.hasPrefix("/"), !path.isEmpty {
      let candidate = URL(fileURLWithPath: path, isDirectory: true).standardizedFileURL
      if candidate.resolvingSymlinksInPath() != dataDirectory.standardizedFileURL.resolvingSymlinksInPath() {
        dataDirectory = candidate
        isIsolated = true
      }
    }
    testTimings = arguments.contains("--test-timings")
    skipOnboarding = isIsolated && arguments.contains("--skip-onboarding")
    if let path = value("--snapshot-dir") { snapshotDirectory = URL(fileURLWithPath: path) }
    if let i = arguments.firstIndex(of: "--start-sprint") {
      var fields: [String: String] = [:]
      for arg in arguments.dropFirst(i + 1).prefix(while: { !$0.hasPrefix("--") }) {
        let pair = arg.split(separator: "=", maxSplits: 1).map(String.init)
        if pair.count == 2 { fields[pair[0]] = pair[1] }
      }
      let shields: [String: ShieldLevel] = ["soft": .soft, "firm": .firm, "sealed": .sealed]
      if let shield = shields[fields["shield", default: ""]],
        let minutes = Int(fields["minutes", default: ""]), SprintLength.isValid(minutes), isIsolated {
        sprint = DebugSprint(shield: shield, minutes: minutes,
          bundles: fields["block", default: ""].split(separator: ",").map(String.init))
      }
    }
    #endif
  }
}
