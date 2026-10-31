import AppKit
import SwiftUI
import BasaltCore

@main
struct BasaltApp: App {
  @NSApplicationDelegateAdaptor(BasaltDelegate.self) private var delegate
  @State private var model = AppModel()
  var body: some Scene {
    Window("Basalt", id: "main") {
      MainView(model: model).onOpenURL { model.handleURL($0) }
        .preferredColorScheme(model.settings.theme == .system ? nil : model.settings.theme == .dark ? .dark : .light)
    }
    .defaultSize(width: 1100, height: 720)
    .defaultLaunchBehavior(.suppressed)
    .commands {
      CommandGroup(replacing: .appTermination) { Button("Quit Basalt") { Task { await model.requestQuit() } }.keyboardShortcut("q") }
      CommandMenu("Sprint") {
        Button("Start sprint") { Task { await model.start() } }.keyboardShortcut(.return).disabled(!model.canStart)
        Button("End sprint") { Task { await model.requestEnd() } }.disabled(!model.isRunning)
        Divider()
        ForEach(Array(ShieldLevel.allCases.enumerated()), id: \.offset) { index, shield in
          Button(ShieldCopy.name(shield)) { Task { await model.selectShield(shield) } }.keyboardShortcut(KeyEquivalent(Character("\(index + 1)")), modifiers: [.command, .shift]).disabled(model.isRunning)
        }
      }
      CommandGroup(after: .sidebar) {
        ForEach(Array(MainPage.allCases.enumerated()), id: \.offset) { index, page in
          Button(page.rawValue) { model.selectedPage = page }.keyboardShortcut(KeyEquivalent(Character("\(index + 1)")))
        }
      }
    }
    Settings { SettingsView(model: model) }
    MenuBarExtra { MenuContent(model: model) } label: { BasaltMenuLabel(model: model, delegate: delegate) }
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
  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
    guard let model, !model.settings.keepRunningOnClose else { return false }
    Task { await model.requestQuit() }; return false
  }
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

struct BasaltMenuLabel: View {
  let model: AppModel
  let delegate: BasaltDelegate
  @Environment(\.openWindow) private var openWindow
  @Environment(\.openSettings) private var openSettings
  var body: some View {
    Group {
      if model.isRunning || model.isOnBreak { Text(model.remainingText).monospacedDigit() }
      else { Image(systemName: "shield").accessibilityLabel("Basalt") }
    }
      .task {
        model.openWindowRequested = { openWindow(id: "main"); NSApp.activate(ignoringOtherApps: true) }
        model.openSettingsRequested = { openSettings(); NSApp.activate(ignoringOtherApps: true) }
        delegate.model = model
        #if DEBUG
        // A hosted test runner must never load the person's normal data directory.
        if NSClassFromString("XCTestCase") != nil { return }
        #endif
        #if DEBUG
        if let directory = model.options.snapshotDirectory {
          do { try await SnapshotExporter.run(directory: directory, options: model.options) }
          catch { model.log.write("snapshot failed: \(error.localizedDescription)") }
          NSApp.terminate(nil); return
        }
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
      Button("Start last sprint") { Task { await model.start() } }.disabled(!model.canStart).accessibilityIdentifier("TrayStartSprint")
      Button("End sprint") { Task { await model.requestEnd() } }.disabled(!model.isRunning).accessibilityIdentifier("TrayEndSprint")
      Button("Open Basalt") { openWindow(id: "main"); NSApp.activate(ignoringOtherApps: true) }.accessibilityIdentifier("TrayOpen")
      SettingsLink { Text("Settings…") }.accessibilityIdentifier("TraySettings")
      Divider()
      Button("Quit") { Task { await model.requestQuit() } }.accessibilityIdentifier("TrayQuit")
    }.padding().frame(width: 260)
  }
}
