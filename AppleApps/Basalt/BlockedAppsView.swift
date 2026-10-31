import AppKit
import SwiftUI
import BasaltCore

struct BlockedAppsView: View {
  let model: AppModel
  @State private var name = ""
  @State private var deleting = false
  @State private var picker = false
  var body: some View {
    ContentPage(title: "Blocked Apps", subtitle: "Choose what stays outside your sprint.") {
      if model.listIsLocked { Label("Sealed — the blocklist is locked until the sprint ends.", systemImage: "lock.shield.fill") }
      Card("Blocklist profile") {
        Picker("Profile", selection: Binding(get: { model.settings.activeProfileId }, set: { id in Task { await model.selectProfile(id) } })) {
          ForEach(model.settings.profiles, id: \.id) { Text($0.name).tag($0.id).accessibilityIdentifier("Profile_\($0.name)") }
        }.accessibilityIdentifier("BlocklistProfilePicker")
        HStack {
          TextField("School, Gaming break, Everything", text: $name).accessibilityLabel("Profile name").accessibilityIdentifier("ProfileNameInput")
          Button("Rename") { Task { await model.renameProfile(model.settings.activeProfileId, name: name) } }.disabled(name.trimmingCharacters(in: .whitespaces).isEmpty).accessibilityIdentifier("RenameProfileButton")
        }
        HStack {
          Button("New profile") { Task { _ = await model.addProfile(name: name.isEmpty ? "New profile" : name) } }.accessibilityIdentifier("NewProfileButton")
          Button("Duplicate") { Task { _ = await model.addProfile(name: model.settings.activeProfile.name + " copy", copying: model.settings.activeProfileId) } }.accessibilityIdentifier("DuplicateProfileButton")
          Button("Delete", role: .destructive) { deleting = true }.disabled(model.settings.profiles.count <= 1).accessibilityIdentifier("DeleteProfileButton")
        }
        if deleting {
          Text("Delete \(model.settings.activeProfile.name)? Its blocklist will be removed. Templates will use the current profile instead.").accessibilityIdentifier("DeleteProfileConfirmText")
          HStack {
            Button("Delete profile", role: .destructive) { Task { await model.deleteProfile(model.settings.activeProfileId); deleting = false } }.accessibilityIdentifier("ConfirmDeleteProfileButton")
            Button("Keep it") { deleting = false }.accessibilityIdentifier("CancelDeleteProfileButton")
          }
        }
        Text("A profile is a named blocklist. A new one starts from the list you are looking at, so “School” or “Gaming break” is a copy with a few apps changed.").font(.caption).foregroundStyle(.secondary)
      }.disabled(!model.canEditBlocklist)
      Card("\(model.settings.blockedApps.count) apps on your shield") {
        if model.settings.blockedApps.isEmpty { Text("Nothing blocked yet. Add the app that pulls you away most.").foregroundStyle(.secondary).accessibilityIdentifier("BlockedAppsEmptyText") }
        ForEach(Array(model.settings.blockedApps.enumerated()), id: \.offset) { index, app in
          HStack {
            AppIcon(path: app.iconPath)
            Toggle(app.displayName, isOn: Binding(get: { app.isEnabled }, set: { value in Task { await model.toggleBlockedApp(at: index, enabled: value) } }))
              .accessibilityIdentifier("AppEnabledSwitch_\(app.processName.isEmpty ? app.bundleIdentifier : app.processName)")
            Spacer()
            Button("Remove", role: .destructive) { Task { await model.removeBlockedApp(at: index) } }.accessibilityLabel("Remove \(app.displayName)").accessibilityIdentifier("RemoveApp_\(app.processName.isEmpty ? app.bundleIdentifier : app.processName)")
          }.disabled(!model.canEditBlocklist)
          Divider()
        }
        Button("Add apps…", systemImage: "plus") { model.refreshAppPicker(); picker = true }.buttonStyle(.borderedProminent).disabled(!model.canEditBlocklist).accessibilityIdentifier("AddAppButton")
      }
      Label("The Mac version blocks apps only. Website notices aren't available on Mac yet.", systemImage: "info.circle").font(.callout).foregroundStyle(.secondary).accessibilityIdentifier("SitesHint")
    }.sheet(isPresented: $picker) { AppPickerView(model: model) }
      .onAppear { name = model.settings.activeProfile.name }
      .onChange(of: model.settings.activeProfileId) { _, _ in name = model.settings.activeProfile.name; deleting = false }
  }
}

struct AppIcon: View {
  let path: String?
  var body: some View {
    if let path { Image(nsImage: NSWorkspace.shared.icon(forFile: path)).resizable().frame(width: 28, height: 28).accessibilityHidden(true) }
    else { Image(systemName: "app").frame(width: 28, height: 28).accessibilityHidden(true) }
  }
}

struct AppPickerView: View {
  let model: AppModel
  @Environment(\.dismiss) private var dismiss
  @State private var query = ""
  @State private var custom = ""
  @State private var status = ""
  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      HStack { Text("Add apps to your blocklist").font(.title2); Spacer(); Button("Done") { dismiss() }.keyboardShortcut(.cancelAction).accessibilityIdentifier("CloseAppPickerButton") }
      TextField("Search installed and running apps", text: $query).textFieldStyle(.roundedBorder).accessibilityIdentifier("AppSearchInput")
      ScrollView {
        LazyVStack(alignment: .leading, spacing: 12) {
          ForEach(model.pickerEntries.filter { query.isEmpty || $0.name.localizedCaseInsensitiveContains(query) || $0.bundleIdentifier.localizedCaseInsensitiveContains(query) }) { entry in
            HStack {
              AppIcon(path: entry.url?.path)
              VStack(alignment: .leading) {
                Text(entry.name)
                Text(entry.isAutomaticSuggestion ? "Suggested · \(entry.group)" : entry.source == .running ? "Running" : "Installed").font(.caption).foregroundStyle(.secondary)
                if !entry.note.isEmpty { Text(entry.note).font(.caption).foregroundStyle(.secondary) }
              }
              Spacer()
              let added = model.settings.blockedApps.contains { $0.bundleIdentifier == entry.bundleIdentifier && !$0.bundleIdentifier.isEmpty }
              Button(added ? "Added" : "Add") { Task { _ = await model.addBlockedApp(entry.blockedApp) } }.disabled(added || !model.canEditBlocklist).accessibilityLabel("Add \(entry.name)").accessibilityIdentifier("AddPickerApp_\(entry.id)")
            }
            Divider()
          }
        }
      }.frame(minHeight: 230).accessibilityIdentifier("AppPickerList")
      Divider()
      Text("Add by bundle identifier or app path").font(.headline)
      HStack {
        TextField("com.example.app or /Applications/App.app", text: $custom).accessibilityLabel("Bundle identifier or app path").accessibilityIdentifier("NewAppNameInput")
        Button("Add") { Task { status = await model.addCustomBlockedApp(custom) ? "Added." : "Choose an app bundle or a bundle identifier that can be blocked." } }.disabled(custom.isEmpty || !model.canEditBlocklist).accessibilityIdentifier("AddCustomAppButton")
        Button("Browse…") {
          let panel = NSOpenPanel(); panel.canChooseDirectories = false; panel.allowedContentTypes = [.applicationBundle]
          if panel.runModal() == .OK, let url = panel.url { custom = url.path }
        }.accessibilityIdentifier("BrowseAppButton")
      }
      HStack { Text(status).font(.caption); Spacer(); Button("Refresh") { model.refreshAppPicker() }.accessibilityIdentifier("RefreshProcessesButton") }
    }.padding(24).frame(width: 620, height: 540)
  }
}
