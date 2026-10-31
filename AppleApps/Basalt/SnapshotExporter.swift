#if DEBUG
import AppKit
import SwiftUI
import BasaltCore

@MainActor enum SnapshotExporter {
  enum Failure: Error { case isolatedDirectoryRequired, renderFailed(String) }
  static func run(directory: URL, options: LaunchOptions) async throws {
    guard options.isIsolated else { throw Failure.isolatedDirectoryRequired }
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    try? FileManager.default.removeItem(at: directory.appendingPathComponent("complete.txt"))
    for scheme in [ColorScheme.light, .dark] {
      let model = AppModel(options: options)
      model.prepareSnapshot("idle")
      try await render(SidebarView(model: model, page: .constant(.today)), name: "sidebar", scheme: scheme, directory: directory, width: 205, height: 720)
      for page in MainPage.allCases {
        try await render(MainView(model: model, snapshotPage: page), name: page == .today ? "today-idle" : page == .blockedApps ? "blocked-apps" : page.rawValue.lowercased(), scheme: scheme, directory: directory, width: 1100, height: 720)
      }
      try await render(MainView(model: model, snapshotPage: .today), name: "today-narrow", scheme: scheme, directory: directory, width: 800, height: 540)
      try await render(AppPickerView(model: model), name: "app-picker", scheme: scheme, directory: directory, width: 668, height: 590)
      for pane in SettingsPane.allCases {
        try await render(SettingsPaneView(model: model, pane: pane), name: "settings-\(pane.rawValue.lowercased())", scheme: scheme, directory: directory, width: 650, height: 540)
      }
      try await render(MainView(model: model, snapshotPage: .history), name: "history-full", scheme: scheme, directory: directory, width: 1100, height: 1500)
      try await render(SettingsPaneView(model: model, pane: .focus), name: "settings-focus-full", scheme: scheme, directory: directory, width: 650, height: 1000)
      try await render(SettingsPaneView(model: model, pane: .data), name: "settings-data-full", scheme: scheme, directory: directory, width: 650, height: 850)
      try await render(SettingsView(model: model), name: "settings-window", scheme: scheme, directory: directory, width: 650, height: 540)
      var schedule = SprintSchedule(); schedule.templateId = model.settings.templates[0].id; schedule.days = [1, 2, 3, 4, 5]
      try await render(SleepWindowView(model: model).padding(24), name: "sleep-window", scheme: scheme, directory: directory)
      try await render(ScheduleEditor(model: model, initial: schedule, close: {}), name: "schedule-editor", scheme: scheme, directory: directory)
      try await render(TemplateEditor(model: model, initial: model.settings.templates[0], close: {}), name: "template-editor", scheme: scheme, directory: directory)
      for step in 1...3 {
        try await render(FirstRunView(model: model, step: .constant(step)), name: "first-run-\(step)", scheme: scheme, directory: directory, width: 650, height: 580)
      }
      try await render(TermsView(model: model), name: "terms-gate", scheme: scheme, directory: directory)
      model.prepareSnapshot("trial-ended")
      try await render(TrialEndedView(model: model), name: "trial-ended", scheme: scheme, directory: directory, width: 600, height: 750)
      model.activationKey = "FS-1234-5678-9ABC-DEFG"
      try await render(ActivationView(model: model), name: "license-prompt", scheme: scheme, directory: directory)
      for state in ["running", "end-firm", "end-sealed", "summary", "break-offer", "break"] {
        model.prepareSnapshot(state)
        if state.hasPrefix("end-") {
          try await render(EndSprintView(model: model), name: state, scheme: scheme, directory: directory)
        } else {
          try await render(MainView(model: model, snapshotPage: .today), name: "today-\(state)", scheme: scheme, directory: directory, width: 1100, height: 720)
        }
      }
      model.prepareSnapshot("running")
      try await render(MainView(model: model, snapshotPage: .today), name: "today-running-narrow", scheme: scheme, directory: directory, width: 800, height: 540)
      try await render(SoftNoticeView(name: "Discord", sprint: model.activeSprint!, tryNumber: 3, unlocksAt: Date().addingTimeInterval(20), answer: { _ in }), name: "soft-notice", scheme: scheme, directory: directory, width: 640, height: 520)
      try await render(FirmWarningView(message: GracefulClose.warning("Discord")).padding(28), name: "firm-warning", scheme: scheme, directory: directory)
      try await render(VStack(alignment: .leading, spacing: 8) { MenuContent(model: model) }.padding(), name: "menu-bar", scheme: scheme, directory: directory, width: 300, height: 320)
      model.prepareSnapshot("running-apps")
      try await render(RunningAppsView(model: model), name: "open-apps-confirmation", scheme: scheme, directory: directory)
    }
    try Data("Snapshots complete\n".utf8).write(to: directory.appendingPathComponent("complete.txt"))
  }
  static func render<V: View>(_ view: V, name: String, scheme: ColorScheme, directory: URL, width: CGFloat = 620, height: CGFloat = 520) async throws {
    let nativeImage = try await capture(view, scheme: scheme, width: width, height: height)
    var sidebar: NSImage?
    if let main = view as? MainView {
      // macOS promotes this shared subtree into its compositor-owned glass surface.
      // Cache it separately so the snapshot includes the same List and license footer.
      sidebar = try await capture(SidebarView(model: main.model, page: .constant(main.snapshotPage ?? .today)),
        scheme: scheme, width: 205, height: height - 16, framed: false)
    }
    let renderer = ImageRenderer(content: ZStack(alignment: .topLeading) {
      Image(nsImage: nativeImage).resizable().frame(width: width, height: height)
      if let sidebar { Image(nsImage: sidebar).resizable().frame(width: 205, height: height - 16).offset(x: 8, y: 8) }
    }.frame(width: width, height: height))
    renderer.scale = 1
    guard let cgImage = renderer.cgImage else { throw Failure.renderFailed(name) }
    let bitmap = NSBitmapImageRep(cgImage: cgImage)
    guard let data = bitmap.representation(using: .png, properties: [:]) else { throw Failure.renderFailed(name) }
    try data.write(to: directory.appendingPathComponent("\(name)-\(scheme == .dark ? "dark" : "light").png"))
  }
  private static func capture<V: View>(_ view: V, scheme: ColorScheme, width: CGFloat, height: CGFloat, framed: Bool = false) async throws -> NSImage {
    let content = view.environment(\.colorScheme, scheme).frame(width: width, height: height).background(Color(nsColor: .windowBackgroundColor))
    // ImageRenderer cannot draw AppKit-backed split views, forms, and text fields.
    // Lay out those real controls in a temporary host, then export the composed
    // bitmap through ImageRenderer. No screen recording or capture API is used.
    let host = NSHostingView(rootView: content)
    host.appearance = NSAppearance(named: scheme == .dark ? .darkAqua : .aqua)
    let window = NSWindow(contentRect: NSRect(x: 40, y: 40, width: width, height: height),
      styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    window.appearance = NSAppearance(named: scheme == .dark ? .darkAqua : .aqua)
    window.contentView = host
    window.makeKeyAndOrderFront(nil)
    host.frame = NSRect(x: 0, y: 0, width: width, height: height)
    host.layoutSubtreeIfNeeded()
    try await Task.sleep(for: .milliseconds(180))
    host.layoutSubtreeIfNeeded()
    host.display()
    let captureView = framed ? (window.contentView?.superview ?? host) : host
    guard let nativeBitmap = captureView.bitmapImageRepForCachingDisplay(in: captureView.bounds) else { throw Failure.renderFailed("native host") }
    captureView.cacheDisplay(in: captureView.bounds, to: nativeBitmap)
    window.orderOut(nil)
    window.close()
    let nativeImage = NSImage(size: host.bounds.size)
    nativeImage.addRepresentation(nativeBitmap)
    return nativeImage
  }
}
#endif
