import AppKit
import SwiftUI
import UniformTypeIdentifiers
import BasaltCore

enum SettingsPane: String, CaseIterable, Identifiable {
  case focus = "Focus", app = "App", notifications = "Notifications", data = "Data", license = "License", about = "About"
  var id: String { rawValue }
  var symbol: String {
    switch self { case .focus: "timer"; case .app: "app"; case .notifications: "bell"; case .data: "externaldrive"; case .license: "key"; case .about: "info.circle" }
  }
  var automationID: String { "SettingsNav_" + (self == .license ? "Licence" : rawValue) }
}

struct SettingsView: View {
  @Bindable var model: AppModel
  var body: some View {
    // A TabView in the Settings scene is the standard Mac settings window: pane icons in
    // the toolbar, the pane's name as the window title.
    TabView(selection: $model.settingsPane) {
      ForEach(SettingsPane.allCases) { pane in
        SettingsPaneView(model: model, pane: pane)
          .tabItem { Label(pane.rawValue, systemImage: pane.symbol) }
          .tag(pane)
          .accessibilityIdentifier(pane.automationID)
      }
    }.frame(width: 600)
      .preferredColorScheme(model.settings.theme == .system ? nil : model.settings.theme == .dark ? .dark : .light)
  }
}

struct SettingsPaneView: View {
  let model: AppModel
  let pane: SettingsPane
  var body: some View {
    Group {
      switch pane {
      case .focus: FocusSettings(model: model)
      case .app: AppSettingsView(model: model)
      case .notifications: NotificationSettings(model: model)
      case .data: DataSettings(model: model)
      case .license: LicenseSettings(model: model)
      case .about: AboutSettings(model: model)
      }
    }.frame(minHeight: 420)
  }
}

struct FocusSettings: View {
  let model: AppModel
  @State private var target = "90"
  @State private var short = "5"
  @State private var long = "15"
  var body: some View {
    Form {
      Section("Daily goal") {
        Text("With a goal set, a day counts towards your streak only once you reach it.").font(.caption).foregroundStyle(.secondary)
        Picker("Goal", selection: Binding(get: { model.settings.dailyGoalKind }, set: { kind in Task { await model.setDailyGoal(kind: kind, target: DailyGoal.defaultTarget(kind)); target = "\(model.settings.dailyGoalTarget)" } })) {
          Text("No goal").tag(DailyGoalKind.none).accessibilityIdentifier("GoalOffRadio")
          Text("Minutes focused").tag(DailyGoalKind.minutes).accessibilityIdentifier("GoalMinutesRadio")
          Text("Sprints completed").tag(DailyGoalKind.sprints).accessibilityIdentifier("GoalSprintsRadio")
        }.accessibilityIdentifier("DailyGoalPicker")
        if model.settings.dailyGoalKind != .none {
          TextField("Target", text: $target).accessibilityIdentifier("GoalTargetInput").onChange(of: target) { _, text in
            if let value = Int(text), DailyGoal.clampTarget(model.settings.dailyGoalKind, value) == value { Task { await model.setDailyGoal(kind: model.settings.dailyGoalKind, target: value) } }
          }
          if Int(target).map({ DailyGoal.clampTarget(model.settings.dailyGoalKind, $0) == $0 }) != true { Text(model.settings.dailyGoalKind == .minutes ? "Choose between 5 and 720 minutes." : "Choose between 1 and 20 sprints.").foregroundStyle(Color("Rose")).accessibilityIdentifier("GoalTargetError") }
        }
        Text("A planned day off keeps your streak without counting as focus.").font(.caption)
        let today = LocalDay(model.now)
        let skipped = DailyGoal.isSkipped(model.settings, day: today)
        Button(skipped ? "Undo planned day off" : "Plan today off") { Task { await model.setDayOff(today, skipped: !skipped) } }.disabled(!skipped && !DailyGoal.canSkip(model.settings, day: today)).accessibilityIdentifier("SkipTodayButton")
        Text("\(max(0, 1 - DailyGoal.skipsUsed(model.settings, day: today))) planned day off available in seven days.").font(.caption).foregroundStyle(.secondary)
      }
      Section("Breaks") {
        Text("A break is offered after a sprint finishes. The sprint's shield is down while one runs, and a break changes nothing about your momentum, streak or daily goal.").font(.caption).foregroundStyle(.secondary)
        TextField("Break length (minutes)", text: $short).accessibilityIdentifier("ShortBreakMinutesInput")
        TextField("Longer break (minutes)", text: $long).accessibilityIdentifier("LongBreakMinutesInput")
        Text("A longer break is offered after four sprints in a row.").font(.caption).foregroundStyle(.secondary)
        if !validBreaks { Text("Choose between 1 and 60 minutes.").foregroundStyle(Color("Rose")).accessibilityIdentifier("ShortBreakMinutesError") }
      }
      Section("Shields") {
        Toggle("Show a notice at Soft", isOn: Binding(get: { model.settings.showSoftOverlayEnabled }, set: { value in Task { await model.setSoftNotice(value) } })).accessibilityIdentifier("SoftOverlayToggle")
        Text("Nothing is closed unless you choose to.").font(.caption).foregroundStyle(.secondary)
        Toggle("Hard kill mode", isOn: Binding(get: { model.settings.hardKillModeEnabled }, set: { value in Task { await model.setHardKill(value) } })).disabled(model.listIsLocked || !model.hasAccess).accessibilityIdentifier("HardKillModeToggle")
        Text("Terminate blocked apps the moment they launch — no grace period.").font(.caption).foregroundStyle(Color("Amber"))
      }
    }.formStyle(.grouped)
      .onAppear { target = "\(model.settings.dailyGoalTarget)"; short = "\(model.settings.shortBreakMinutes)"; long = "\(model.settings.longBreakMinutes)" }
      .onChange(of: short) { _, _ in saveBreaks() }.onChange(of: long) { _, _ in saveBreaks() }
  }
  private var validBreaks: Bool { CycleState.isValidBreakMinutes(Int(short) ?? 0) && CycleState.isValidBreakMinutes(Int(long) ?? 0) }
  private func saveBreaks() { if validBreaks { Task { await model.setBreakMinutes(short: Int(short)!, long: Int(long)!) } } }
}

struct AppSettingsView: View {
  let model: AppModel
  var body: some View {
    Form {
      Section("Preferences") {
        Toggle("Open at login", isOn: Binding(get: { model.settings.openAtLogin }, set: { value in Task { await model.setOpenAtLogin(value) } })).accessibilityIdentifier("StartWithWindowsToggle")
        Text("Opens quietly in the menu bar when you sign in, so a sprint survives a restart.").font(.caption).foregroundStyle(.secondary)
        if model.loginStatus == .requiresApproval {
          Text("Allow Basalt in System Settings › General › Login Items.").foregroundStyle(Color("Amber"))
          Button("Open Login Items") { model.openLoginApprovalSettings() }.accessibilityIdentifier("OpenLoginItemsButton")
        }
        Toggle("Keep running in menu bar on close", isOn: Binding(get: { model.settings.keepRunningOnClose }, set: { value in Task { await model.setKeepRunningOnClose(value) } })).accessibilityIdentifier("MinimizeToTrayToggle")
        Text("Closing the window keeps the shield running in the background.").font(.caption).foregroundStyle(.secondary)
        Toggle("Start the last sprint from anywhere", isOn: Binding(get: { model.settings.globalHotkeyEnabled }, set: { value in Task { await model.setGlobalHotkey(value) } })).accessibilityIdentifier("GlobalHotkeyToggle")
        Text("Off by default. Press Control-Option-F from any app to start your last sprint, even while Basalt is in the menu bar. Turns itself off if another app already uses that combination.").font(.caption).foregroundStyle(.secondary)
      }
      Section("Appearance") {
        Picker("Appearance", selection: Binding(get: { model.settings.theme }, set: { value in Task { await model.setTheme(value) } })) {
          Text("System").tag(AppTheme.system).accessibilityIdentifier("ThemeSystemRadio")
          Text("Light").tag(AppTheme.light).accessibilityIdentifier("ThemeLightRadio")
          Text("Dark").tag(AppTheme.dark).accessibilityIdentifier("ThemeDarkRadio")
        }.pickerStyle(.segmented).accessibilityIdentifier("AppearancePicker")
        Text("System follows the light or dark setting macOS is on, and changes with it.").font(.caption).foregroundStyle(.secondary)
      }
    }.formStyle(.grouped)
  }
}

struct NotificationSettings: View {
  let model: AppModel
  static let labels: [NotificationKind: String] = [.sprintStarted: "Sprint started", .fiveMinutesLeft: "5 minutes left", .sprintComplete: "Sprint complete", .sprintInterrupted: "Sprint interrupted", .breakOver: "Break over", .scheduledSprint: "Scheduled sprint", .trialEnding: "Free trial ending", .appClosing: "A blocked app is closing", .updateReady: "Update ready"]
  var body: some View {
    Form {
      Section {
      Toggle("Notifications", isOn: Binding(get: { model.settings.notificationsEnabled }, set: { value in Task { await model.setNotifications(value) } })).accessibilityIdentifier("NotificationsToggle")
      Text("Basalt notifies from the menu bar, and never about buying while a sprint is running.").font(.caption).foregroundStyle(.secondary)
      }
      Section("Notify me about") {
      ForEach(NotificationKind.allCases, id: \.self) { kind in
        Toggle(Self.labels[kind] ?? kind.rawValue, isOn: Binding(get: { model.settings.notificationKinds[kind.rawValue, default: true] }, set: { value in Task { await model.setNotifications(value, kind: kind) } })).disabled(!model.settings.notificationsEnabled || kind == .updateReady).accessibilityIdentifier("Notify\(kind.rawValue)Toggle")
        if kind == .trialEnding { Text("Once, on the last day. Never during a sprint.").font(.caption).foregroundStyle(.secondary) }
        if kind == .updateReady { Text("Automatic updates aren't available on Mac yet.").font(.caption).foregroundStyle(.secondary) }
      }
      }
    }.formStyle(.grouped)
  }
}

struct DataSettings: View {
  let model: AppModel
  @State private var from = Calendar.current.date(byAdding: .day, value: -30, to: Date())!
  @State private var through = Date()
  @State private var format = ExportFormat.csv
  @State private var status = ""
  @State private var deleting = false
  var body: some View {
    Form {
      Section("Export your journal") {
        Text("Save your sprints and journal lines as a file you keep. It is written only where you choose — nothing is uploaded.").font(.caption).foregroundStyle(.secondary)
        DatePicker("From", selection: $from, displayedComponents: .date).accessibilityIdentifier("ExportFromDate")
        DatePicker("To", selection: $through, displayedComponents: .date).accessibilityIdentifier("ExportToDate")
        Picker("Format", selection: $format) { Text("CSV (spreadsheet)").tag(ExportFormat.csv).accessibilityIdentifier("ExportCsvRadio"); Text("Markdown").tag(ExportFormat.markdown).accessibilityIdentifier("ExportMarkdownRadio") }.pickerStyle(.segmented).accessibilityIdentifier("ExportFormatPicker")
        Button("Export…") { save(journal: true) }.disabled(!model.canManageData || LocalDay(from) > LocalDay(through)).accessibilityIdentifier("ExportJournalButton")
      }
      Section("Your data") {
        LabeledContent("Stored on this Mac") {
          Text(model.options.dataDirectory.path).font(.caption).textSelection(.enabled).multilineTextAlignment(.trailing)
        }
        Text("Sprints, journal, blocklist, momentum and your license are kept in a private JSON file in that folder.").font(.caption).foregroundStyle(.secondary)
        Text("A license check sends your license key, the email you used at checkout, a salted device identifier, and your device name to the license server to confirm your purchase.").font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("WhatLeavesText")
        HStack {
          Button("Export everything…") { save(journal: false) }.disabled(!model.canManageData).accessibilityIdentifier("ExportDataButton")
          Button("Delete everything", role: .destructive) { deleting = true }.disabled(!model.canManageData || model.licenseBusy).accessibilityIdentifier("DeleteEverythingButton")
        }
        if !model.canManageData { Text("Finish your sprint first — deleting everything restarts the app, which would end it.").foregroundStyle(.secondary).accessibilityIdentifier("DeleteEverythingBlockedText") }
      }
      if !status.isEmpty { Text(status).font(.caption).accessibilityIdentifier("ExportStatusText") }
    }.formStyle(.grouped).confirmationDialog("Delete everything?", isPresented: $deleting, titleVisibility: .visible) {
      Button("Delete everything", role: .destructive) { Task { await model.deleteEverything() } }
      Button("Keep my data", role: .cancel) {}
    } message: { Text("Your sprints, journal, blocklists, templates, schedules and settings will be removed from this Mac. This cannot be undone.") }
  }
  private func save(journal: Bool) {
    let panel = NSSavePanel()
    let ext = journal ? (format == .csv ? "csv" : "md") : "json"
    panel.nameFieldStringValue = "basalt-\(journal ? "journal" : "data").\(ext)"
    panel.allowedContentTypes = [UTType(filenameExtension: ext) ?? .plainText]
    if panel.runModal() == .OK, let url = panel.url {
      do {
        if journal { try model.exportJournal(to: url, from: LocalDay(from), through: LocalDay(through), format: format) }
        else { try model.exportAllData(to: url) }
        status = "Exported to \(url.lastPathComponent)."
      } catch { status = "Couldn't export: \(error.localizedDescription)" }
    }
  }
}

struct LicenseSettings: View {
  @Bindable var model: AppModel
  var trialGate = false
  @State private var email = ""
  @State private var releaseToken: String?
  @State private var server = ""
  var body: some View {
    if trialGate {
      VStack(alignment: .leading, spacing: 16) { fields }.onAppear(perform: load)
    } else {
      Form {
        Section {
          LabeledContent("Status") {
            Text(model.settings.isPro ? "Purchased" : model.trialDaysLeft > 0 ? "\(model.trialDaysLeft) days left on free trial" : "Free trial ended").accessibilityIdentifier("LicenseStatusText")
          }
          if !model.settings.isPro && !model.isRunning { Link("Buy Basalt — $4.99", destination: model.buyURL).accessibilityIdentifier("GetProButton") }
        }
        Section("Activate") { fields }
        if model.settings.isPro { Section("Your devices · \(model.settings.deviceCount) / \(model.settings.deviceLimit)") { devices } }
        Section {
          DisclosureGroup("Advanced") {
            TextField("License server", text: $server).accessibilityIdentifier("LicenseServerUrlInput")
            Button("Save server") { Task { await model.setLicenseServer(server) } }.accessibilityIdentifier("SaveLicenseServerButton")
          }
        }
      }.formStyle(.grouped).onAppear(perform: load)
    }
  }
  private func load() { email = model.settings.licenseEmail; server = model.settings.licenseServerUrl; if model.activationKey.isEmpty { model.activationKey = model.settings.licenseKey } }
  @ViewBuilder private var fields: some View {
      TextField("License key", text: $model.activationKey, prompt: Text("FS-XXXX-XXXX-XXXX-XXXX")).accessibilityIdentifier(trialGate ? "LockLicenseKeyInput" : "LicenseKeyInput")
      TextField("Email", text: $email, prompt: Text("Used at checkout (optional)")).accessibilityIdentifier("LicenseEmailInput")
      HStack {
        Button("Activate license") { Task { await model.activateLicense(key: model.activationKey, email: email) } }.disabled(model.licenseBusy || model.activationKey.isEmpty).accessibilityIdentifier(trialGate ? "LockActivateButton" : "ActivateProButton")
        if model.settings.isPro { Button("Deactivate") { Task { await model.deactivateLicense() } }.disabled(model.licenseBusy).accessibilityIdentifier("DeactivateButton") }
        if model.licenseBusy { ProgressView().controlSize(.small); Text("Checking…").accessibilityIdentifier("LicenseBusyText") }
      }
      if !model.licenseMessage.isEmpty { Text(model.licenseMessage).font(.callout).accessibilityIdentifier("LicenseDetailText") }
  }
  @ViewBuilder private var devices: some View {
        Button("Refresh") { Task { await model.listDevices() } }.disabled(model.licenseBusy).accessibilityIdentifier("DevicesRefreshButton")
        ForEach(model.devices, id: \.deviceToken) { device in
          HStack {
            VStack(alignment: .leading) {
              Text(device.name + (device.isCurrent ? " · This Mac" : ""))
              if let seen = device.lastSeenUtc { Text(seen.formatted(date: .abbreviated, time: .shortened)).font(.caption).foregroundStyle(.secondary) }
            }
            Spacer()
            if releaseToken == device.deviceToken {
              Text("Release this device?").font(.caption)
              Button("Yes, release", role: .destructive) { Task { await model.releaseDevice(device.deviceToken); releaseToken = nil } }.accessibilityIdentifier("ConfirmReleaseDevice_\(device.deviceToken)")
              Button("Cancel") { releaseToken = nil }
            } else { Button("Release") { releaseToken = device.deviceToken }.accessibilityLabel("Release \(device.name)").accessibilityIdentifier("ReleaseDevice_\(device.deviceToken)") }
          }.disabled(model.licenseBusy)
        }
  }
}

struct AboutSettings: View {
  let model: AppModel
  var body: some View {
    Form {
      Section {
        LabeledContent("Version") { Text(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.1.0").accessibilityIdentifier("VersionText") }
        LabeledContent("Updates") { Text("Automatic updates aren't available on Mac yet.") }
      }
      Section("Legal") {
        LabeledContent("Terms accepted") { Text(model.settings.termsAcceptedVersion).accessibilityIdentifier("TermsAcceptedText") }
        Link("Terms of service", destination: URL(string: LegalTerms.termsURL(model.settings))!).accessibilityIdentifier("SettingsTermsButton")
        Link("Privacy policy", destination: URL(string: LegalTerms.privacyURL(model.settings))!).accessibilityIdentifier("SettingsPrivacyButton")
      }
      Section { Button("Open log folder") { NSWorkspace.shared.open(model.options.dataDirectory) }.accessibilityIdentifier("OpenLogButton") }
    }.formStyle(.grouped)
  }
}
