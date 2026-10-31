import AppKit
import SwiftUI
import BasaltCore

@main
struct BasaltApp: App {
  @NSApplicationDelegateAdaptor(BasaltDelegate.self) private var delegate
  @State private var model = AppModel()
  var body: some Scene {
    Window("Basalt", id: "main") {
      EngineView(model: model).onOpenURL { model.handleURL($0) }
        .preferredColorScheme(model.settings.theme == .system ? nil : model.settings.theme == .dark ? .dark : .light)
    }
    .defaultSize(width: 560, height: 620)
    .defaultLaunchBehavior(.suppressed)
    .commands {
      CommandGroup(replacing: .appTermination) { Button("Quit Basalt") { Task { await model.requestQuit() } }.keyboardShortcut("q") }
      CommandMenu("Sprint") {
        Button("Start last sprint") { Task { await model.start() } }.disabled(!model.canStart)
        Button("End sprint") { Task { await model.requestEnd() } }.disabled(!model.isRunning)
      }
    }
    MenuBarExtra { MenuContent(model: model) } label: { EngineMenuLabel(model: model, delegate: delegate) }
      .menuBarExtraStyle(.window)
  }
}

@MainActor final class BasaltDelegate: NSObject, NSApplicationDelegate {
  private var pendingURLs: [URL] = []
  var model: AppModel? {
    didSet {
      guard let model else { return }
      for url in pendingURLs { model.handleURL(url) }
      pendingURLs.removeAll()
    }
  }
  private(set) var launchedAtLogin = false
  func applicationDidFinishLaunching(_ notification: Notification) { launchedAtLogin = LoginItemService.launchedAtLogin }
  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
  func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
    guard let model else { return .terminateNow }
    if model.isRunning { Task { await model.requestQuit() }; return .terminateCancel }
    Task { await model.shutdown(); sender.reply(toApplicationShouldTerminate: true) }
    return .terminateLater
  }
  func application(_ application: NSApplication, open urls: [URL]) {
    if let model { for url in urls { model.handleURL(url) } } else { pendingURLs += urls }
  }
  func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
    if !flag { model?.openWindowRequested?() }
    return true
  }
}

struct EngineMenuLabel: View {
  let model: AppModel
  let delegate: BasaltDelegate
  @Environment(\.openWindow) private var openWindow
  var body: some View {
    Label(model.isRunning || model.isOnBreak ? model.remainingText : "Basalt", systemImage: "shield")
      .task {
        model.openWindowRequested = { openWindow(id: "main"); NSApp.activate(ignoringOtherApps: true) }
        delegate.model = model
        #if DEBUG
        // A hosted test runner must never load the person's normal data directory.
        if NSClassFromString("XCTestCase") != nil { return }
        #endif
        await model.load()
        for arg in CommandLine.arguments where arg.lowercased().hasPrefix("flowshield:") {
          if let url = URL(string: arg) { model.handleURL(url) }
        }
        if !delegate.launchedAtLogin { openWindow(id: "main") }
      }
  }
}

struct MenuContent: View {
  let model: AppModel
  @Environment(\.openWindow) private var openWindow
  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text(model.isRunning ? "\(ShieldCopy.name(model.activeSprint!.shield)) · \(model.remainingText)" : model.isOnBreak ? "Break · \(model.remainingText)" : "No sprint running").font(.headline)
      Button("Start last sprint") { Task { await model.start() } }.disabled(!model.canStart)
      Button("End sprint") { Task { await model.requestEnd() } }.disabled(!model.isRunning)
      Button("Open Basalt") { openWindow(id: "main"); NSApp.activate(ignoringOtherApps: true) }
      Divider()
      Button("Quit") { Task { await model.requestQuit() } }
    }.padding().frame(width: 260)
  }
}
