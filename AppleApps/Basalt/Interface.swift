import AppKit
import SwiftUI
import BasaltCore

enum MainPage: String, CaseIterable, Identifiable {
  case today = "Today", history = "History", blockedApps = "Blocked Apps", schedule = "Schedule"
  var id: String { rawValue }
  var symbol: String {
    switch self { case .today: "timer"; case .history: "chart.xyaxis.line"; case .blockedApps: "app.badge"; case .schedule: "calendar" }
  }
  var automationID: String {
    switch self { case .today: "Tab_Today"; case .history: "Tab_History"; case .blockedApps: "Tab_BlockedApps"; case .schedule: "Tab_SleepBlocking" }
  }
}

extension ShieldLevel {
  var symbol: String { self == .soft ? "shield" : self == .firm ? "shield.lefthalf.filled" : "lock.shield.fill" }
}

struct ContentPage<Content: View>: View {
  let title: String
  let subtitle: String
  @ViewBuilder var content: Content
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        VStack(alignment: .leading, spacing: 6) {
          Text(title).font(.largeTitle).accessibilityIdentifier("PageTitle")
          if !subtitle.isEmpty { Text(subtitle).foregroundStyle(.secondary) }
        }
        content
      }.padding(28).frame(maxWidth: 1000, alignment: .leading).frame(maxWidth: .infinity)
    }.background(Color(nsColor: .windowBackgroundColor))
  }
}

struct Card<Content: View>: View {
  let title: String
  @ViewBuilder var content: Content
  init(_ title: String = "", @ViewBuilder content: () -> Content) { self.title = title; self.content = content() }
  var body: some View {
    GroupBox {
      VStack(alignment: .leading, spacing: 14) {
        if !title.isEmpty { Text(title).font(.headline) }
        content
      }.frame(maxWidth: .infinity, alignment: .leading).padding(12)
    }
  }
}

struct Stat: View {
  let value: String
  let label: String
  var body: some View {
    VStack(alignment: .leading, spacing: 5) { Text(value).font(.title2).monospacedDigit(); Text(label).font(.caption).foregroundStyle(.secondary) }
      .frame(maxWidth: .infinity, alignment: .leading).accessibilityElement(children: .combine)
  }
}

struct MainView: View {
  @Bindable var model: AppModel
  @SceneStorage("mainPage") private var pageRaw = MainPage.today.rawValue
  @State private var onboardingStep = 1
  var snapshotPage: MainPage?
  private var page: MainPage { snapshotPage ?? MainPage(rawValue: pageRaw) ?? .today }
  var body: some View {
    NavigationSplitView {
      SidebarView(model: model, page: Binding(get: { page }, set: { pageRaw = $0.rawValue }))
        .navigationTitle("Basalt").navigationSplitViewColumnWidth(min: 170, ideal: 205, max: 260)
    } detail: {
      Group {
        switch page {
        case .today: TodayView(model: model)
        case .history: HistoryView(model: model)
        case .blockedApps: BlockedAppsView(model: model)
        case .schedule: ScheduleView(model: model)
        }
      }.navigationTitle(page.rawValue)
        .toolbar {
          if page == .today {
            ToolbarItem(placement: .primaryAction) {
              if model.isRunning {
                Button(model.endButtonLabel, systemImage: "stop") { Task { await model.requestEnd() } }.accessibilityIdentifier("ToolbarEndSprint")
              } else {
                Button("Start sprint", systemImage: "play.fill") { Task { await model.start() } }.disabled(!model.canStart).accessibilityIdentifier("ToolbarStartSprint")
              }
            }
          }
        }
    }
    .frame(minWidth: 800, minHeight: 540)
    .accessibilityIdentifier("FlowShieldMainWindow")
    .onChange(of: model.selectedPage) { _, new in pageRaw = new.rawValue }
    .onChange(of: pageRaw) { _, value in if let page = MainPage(rawValue: value) { model.selectedPage = page } }
    .onAppear { if snapshotPage == nil { model.selectedPage = page } }
    .background(WindowKeyboardHandler(enabled: page == .today && !model.hasModal) {
      Task { if model.isRunning { await model.requestEnd() } else if model.canStart { await model.start() } }
    })
    .sheet(isPresented: Binding(get: { snapshotPage == nil && model.isReady && model.hasModal }, set: { if !$0 { model.dismissModal() } })) {
      if model.termsRequired { TermsView(model: model) }
      else if model.licensePromptVisible { ActivationView(model: model) }
      else if model.firstRunVisible { FirstRunView(model: model, step: $onboardingStep) }
      else if model.trialLocked { TrialEndedView(model: model) }
      else if model.pendingStart != nil { RunningAppsView(model: model) }
      else if model.endConfirmation.flow != nil { EndSprintView(model: model) }
    }
    .alert("Basalt couldn't finish that action", isPresented: Binding(get: { model.errorMessage != nil }, set: { if !$0 { model.errorMessage = nil } })) {
      Button("Dismiss", role: .cancel) { model.errorMessage = nil }
    } message: { Text(model.errorMessage ?? "") }
    .safeAreaInset(edge: .bottom) {
      if !model.toast.isEmpty { Text(model.toast).font(.callout).padding(8).accessibilityIdentifier("ToastText") }
    }
  }
}

struct SidebarView: View {
  let model: AppModel
  @Binding var page: MainPage
  var body: some View {
    List(selection: Binding<MainPage?>(get: { page }, set: { if let value = $0 { page = value } })) {
      ForEach(MainPage.allCases) { item in
        Label(item.rawValue, systemImage: item.symbol).tag(item).accessibilityIdentifier(item.automationID)
      }
    }.listStyle(.sidebar).safeAreaInset(edge: .bottom) {
      VStack(alignment: .leading, spacing: 10) {
        Label(model.settings.isPro ? "Purchased" : model.trialDaysLeft > 0 ? "\(model.trialDaysLeft) days left on free trial" : "Trial ended", systemImage: model.settings.isPro ? "checkmark.seal" : "circle")
          .font(.caption).accessibilityIdentifier("TierBadge")
        if !model.settings.isPro && !model.isRunning {
          Link("Buy Basalt — $4.99", destination: model.buyURL).accessibilityIdentifier("GetProNavButton")
        }
      }.padding()
    }
  }
}

// A local monitor leaves Space to text editors, buttons, sheets, and other windows.
struct WindowKeyboardHandler: NSViewRepresentable {
  var enabled: Bool
  var action: () -> Void
  func makeNSView(context: Context) -> NSView { context.coordinator.view }
  func updateNSView(_ nsView: NSView, context: Context) { context.coordinator.parent = self }
  func makeCoordinator() -> Coordinator { Coordinator(self) }
  @MainActor final class Coordinator {
    var parent: WindowKeyboardHandler
    let view = NSView()
    var monitor: Any?
    init(_ parent: WindowKeyboardHandler) {
      self.parent = parent
      monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
        guard let self, parent.enabled, event.window === view.window, event.keyCode == 49,
          event.modifierFlags.intersection([.command, .control, .option, .shift]).isEmpty,
          !event.isARepeat, let window = view.window, window.attachedSheet == nil else { return event }
        if window.firstResponder is NSTextView || window.firstResponder is NSControl { return event }
        parent.action(); return nil
      }
    }
  }
  static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
    if let monitor = coordinator.monitor { NSEvent.removeMonitor(monitor) }
  }
}
