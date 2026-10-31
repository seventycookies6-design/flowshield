import AppKit
import BasaltCore

@MainActor
final class BlockerLog {
  let url: URL
  private(set) var error: String?
  init(directory: URL) { url = directory.appendingPathComponent("blocker.log") }
  func write(_ action: String, app: NSRunningApplication? = nil) {
    let safe: (String) -> String = { $0.replacingOccurrences(of: "\n", with: " ").replacingOccurrences(of: "\t", with: " ") }
    let line = "\(ISO8601DateFormatter().string(from: Date()))\t\(safe(app?.localizedName ?? "Basalt"))\t\(safe(app?.bundleIdentifier ?? ""))\t\(action)\n"
    do {
      let fm = FileManager.default
      try fm.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
      if !fm.fileExists(atPath: url.path) {
        guard fm.createFile(atPath: url.path, contents: nil, attributes: [.posixPermissions: 0o600]) else { throw CocoaError(.fileWriteUnknown) }
      }
      try fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
      let handle = try FileHandle(forWritingTo: url)
      defer { try? handle.close() }
      try handle.seekToEnd()
      try handle.write(contentsOf: Data(line.utf8))
    } catch { self.error = "Couldn't write the blocker log." }
  }
}

@MainActor
final class BlockerService {
  enum Event { case noted, closing, turnedBack }
  private let log: BlockerLog
  private let testTimings: Bool
  private var settings = AppSettings()
  private var task: Task<Void, Never>?
  private var observers: [NSObjectProtocol] = []
  private var deadlines: [pid_t: Date] = [:]
  private var present: Set<pid_t> = []
  private var soft = SoftOverlayPolicy()
  private var panel: SoftNoticeController?
  private var sprintStart: Date?
  var onEvent: ((Event, Int) -> Void)?
  var onWarning: ((String, String) -> Void)?

  init(log: BlockerLog, testTimings: Bool) { self.log = log; self.testTimings = testTimings }
  static func identity(_ app: NSRunningApplication) -> RunningAppIdentity {
    RunningAppIdentity(bundleIdentifier: app.bundleIdentifier ?? "",
      executableName: app.executableURL?.lastPathComponent ?? app.localizedName ?? "",
      isRegular: app.activationPolicy == .regular)
  }
  func startObserving() {
    guard task == nil else { return }
    let center = NSWorkspace.shared.notificationCenter
    for name in [NSWorkspace.didLaunchApplicationNotification, NSWorkspace.didActivateApplicationNotification, NSWorkspace.didTerminateApplicationNotification] {
      observers.append(center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
        Task { @MainActor in self?.sweep() }
      })
    }
    task = Task { [weak self] in
      while !Task.isCancelled {
        self?.sweep()
        do { try await Task.sleep(for: .seconds(2)) } catch { break }
      }
    }
  }
  func shutdown() {
    task?.cancel(); task = nil
    for o in observers { NSWorkspace.shared.notificationCenter.removeObserver(o) }
    observers.removeAll(); clear()
  }
  func update(_ settings: AppSettings) {
    if sprintStart != settings.activeSprint?.startedUtc { clear(); sprintStart = settings.activeSprint?.startedUtc }
    self.settings = settings
    if !isEnforcing { clear() }
    sweep()
  }
  private var sleepActive: Bool {
    let c = Calendar.current.dateComponents([.hour, .minute], from: Date())
    return settings.activeBreak == nil && settings.inSleepWindow(minute: (c.hour ?? 0) * 60 + (c.minute ?? 0))
  }
  private var isEnforcing: Bool {
    settings.activeBreak == nil && ((settings.activeSprint.map { $0.endsUtc > Date() } ?? false) || sleepActive)
  }
  private func clear() {
    deadlines.removeAll(); present.removeAll(); soft.reset(); panel?.close(); panel = nil
  }
  func runningBlockedApps(targets: [BlockedApp]) -> [NSRunningApplication] {
    NSWorkspace.shared.runningApplications.filter { !$0.isTerminated && MacBlockerPolicy.match(Self.identity($0), targets: targets) != nil }
  }
  func sweep() {
    guard isEnforcing else { clear(); return }
    let now = Date()
    let shield = sleepActive ? maxShield(settings.activeSprint?.shield ?? .firm, .firm) : settings.activeSprint!.shield
    let apps = NSWorkspace.shared.runningApplications.filter { !$0.isTerminated }
    var live: Set<pid_t> = []
    for app in apps {
      let identity = Self.identity(app)
      // Log protected matches as well, so safety can be proved without touching a process.
      if MacBlockerPolicy.isProtected(identity) {
        if settings.blockedApps.contains(where: { $0.isEnabled && ((!$0.bundleIdentifier.isEmpty && $0.bundleIdentifier.lowercased() == identity.bundleIdentifier.lowercased()) || $0.allProcessNames.contains(identity.executableName)) }) {
          log.write("protected; never-close", app: app)
        }
        continue
      }
      guard let index = MacBlockerPolicy.match(identity, targets: settings.blockedApps) else { continue }
      let pid = app.processIdentifier
      live.insert(pid)
      let fresh = present.insert(pid).inserted
      switch MacBlockerPolicy.action(shield: shield, hardKill: settings.hardKillModeEnabled, deadline: deadlines[pid], now: now) {
      case .notice:
        if fresh { log.write("noted; Soft leaves app running", app: app); onEvent?(.noted, index) }
      case .requestTermination:
        deadlines[pid] = now.addingTimeInterval(GracefulClose.delay(testTimings: testTimings))
        let accepted = app.terminate()
        log.write("asked to quit; shield=\(ShieldCopy.name(shield)); accepted=\(accepted); grace=\(Int(GracefulClose.delay(testTimings: testTimings)))", app: app)
        onWarning?("\(app.localizedName ?? "App") is closing", GracefulClose.warning(app.localizedName ?? "App", testTimings: testTimings))
        if fresh { onEvent?(.closing, index) }
      case .wait: log.write("waiting for graceful quit", app: app)
      case .forceTerminate:
        let accepted = app.forceTerminate()
        log.write("forceTerminate; accepted=\(accepted)", app: app)
        if fresh { onEvent?(.closing, index) }
      }
    }
    present.formIntersection(live)
    deadlines = deadlines.filter { live.contains($0.key) }
    if shield == .soft && !settings.hardKillModeEnabled && settings.activeSprint != nil {
      inspectForeground(now: now)
    } else { panel?.close(); panel = nil; _ = soft.leftTheForeground() }
  }
  private func maxShield(_ a: ShieldLevel, _ b: ShieldLevel) -> ShieldLevel { a.rawValue >= b.rawValue ? a : b }
  private func inspectForeground(now: Date) {
    guard let app = NSWorkspace.shared.frontmostApplication else { return }
    // Clicking our nonactivating panel must not create another foreground sighting.
    if app.processIdentifier == ProcessInfo.processInfo.processIdentifier { return }
    guard let i = MacBlockerPolicy.match(Self.identity(app), targets: settings.blockedApps) else {
      _ = soft.leftTheForeground(); panel?.close(); panel = nil; return
    }
    let key = app.bundleIdentifier ?? String(app.processIdentifier)
    guard settings.showSoftOverlayEnabled, soft.shouldShow(key, now: now), let sprint = settings.activeSprint else { return }
    panel?.close()
    log.write("notice shown; try=\(soft.tries)", app: app)
    let controller = SoftNoticeController(app: app, sprint: sprint, tryNumber: soft.tries, testTimings: testTimings) { [weak self, weak app] answer in
      guard let self, let app else { return }
      let date = Date()
      switch answer {
      case .back:
        self.soft.backToWork(key, now: date)
        self.onEvent?(.turnedBack, i)
        NSApp.activate(ignoringOtherApps: true)
      case .allow: self.soft.allowFiveMinutes(key, now: date)
      case .close:
        self.soft.closeIt(key, now: date)
        self.onEvent?(.turnedBack, i)
        _ = app.terminate()
      }
      self.log.write("Soft answer=\(answer)", app: app)
      self.panel?.close(); self.panel = nil
    }
    panel = controller
    controller.show(on: Self.screen(for: app))
  }
  private static func screen(for app: NSRunningApplication) -> NSScreen {
    // Bounds are public window metadata; no titles, pixels, or recording permission.
    if let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]],
      let window = windows.first(where: { ($0[kCGWindowOwnerPID as String] as? Int32) == app.processIdentifier && ($0[kCGWindowLayer as String] as? Int) == 0 }),
      let bounds = window[kCGWindowBounds as String] as? [String: CGFloat],
      let x = bounds["X"], let y = bounds["Y"], let w = bounds["Width"], let h = bounds["Height"],
      let main = NSScreen.screens.first {
      let rect = NSRect(x: x, y: main.frame.maxY - y - h, width: w, height: h)
      if let screen = NSScreen.screens.max(by: { $0.frame.intersection(rect).area < $1.frame.intersection(rect).area }) { return screen }
    }
    return NSScreen.main ?? NSScreen.screens[0]
  }
}
private extension NSRect { var area: CGFloat { isNull ? 0 : width * height } }
