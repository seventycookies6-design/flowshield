import SwiftUI
import BasaltCore

struct EngineView: View {
  @Bindable var model: AppModel
  @State private var licenseEmail = ""
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        Text("Basalt").font(.largeTitle)
        if !model.isReady { ProgressView("Loading…") }
        if let error = model.errorMessage { Text(error).foregroundStyle(Color("Rose")) }
        if model.termsRequired {
          Text(LegalTerms.headline).font(.headline)
          Text(LegalTerms.dataLossWarning)
          Text(LegalTerms.agreementLine)
          HStack {
            Link("Terms of Service", destination: URL(string: LegalTerms.termsURL(model.settings))!)
            Link("Privacy Policy", destination: URL(string: LegalTerms.privacyURL(model.settings))!)
          }
          Button("I agree") { Task { await model.acceptTerms() } }
        } else if model.firstRunVisible {
          Text("Choose your sprint and blocked apps, then start when you're ready.")
          Button("Finish setup") { Task { await model.completeOnboarding() } }
        }
        if model.trialLocked { Text(TrialPolicy.endedCopy) }
        Text(model.isRunning ? model.remainingText : model.isOnBreak ? "Break · \(model.remainingText)" : "Ready when you are.")
          .font(.system(.largeTitle, design: .monospaced))
        Picker("Shield", selection: Binding(get: { model.settings.defaultShield }, set: { value in Task { await model.selectShield(value) } })) {
          ForEach(ShieldLevel.allCases, id: \.self) { Text(ShieldCopy.name($0)).tag($0) }
        }.disabled(model.isRunning)
        Picker("Minutes", selection: Binding(get: { model.settings.defaultSprintMinutes }, set: { value in Task { await model.setSprintMinutes(value) } })) {
          ForEach(Array(Set(SprintLength.presets + [model.settings.defaultSprintMinutes])).sorted(), id: \.self) { Text("\($0)").tag($0) }
        }.disabled(model.isRunning)
        TextField("What are you working on?", text: $model.intention).disabled(model.isRunning)
        HStack {
          Button("Start last sprint") { Task { await model.start() } }.disabled(!model.canStart).buttonStyle(.borderedProminent)
          Button(model.endButtonLabel) { Task { await model.requestEnd() } }.disabled(!model.isRunning)
        }
        if let warning = model.firmWarning {
          GroupBox("Save your work") { VStack(alignment: .leading) { Text(warning); Button("Dismiss") { model.dismissFirmWarning() } } }
        }
        if model.pendingStart != nil {
          GroupBox("These apps will close") {
            VStack(alignment: .leading) {
              Text(model.runningAppsToClose.joined(separator: ", "))
              Text("Save your work before starting.")
              Button("Start sprint") { Task { await model.confirmStart() } }
              Button("Cancel") { model.dismissStart() }
            }
          }
        }
        if model.endConfirmation.flow != nil {
          GroupBox(model.endConfirmation.title) {
            VStack(alignment: .leading) {
              Text(model.endConfirmation.text(remaining: model.remaining, momentum: model.settings.momentumScore, shield: model.activeSprint?.shield ?? .firm))
              Text(model.endConfirmation.countdownText(now: model.now))
              if model.endConfirmation.flow == .sealed { TextField("end my sprint", text: $model.endConfirmation.phrase) }
              Button("End anyway") { Task { await model.endAnyway() } }.disabled(!model.canEndAnyway)
              Button("Keep going") { model.keepGoing() }
            }
          }
        }
        if model.breakOffered { Button("Start break") { Task { await model.startBreak() } } }
        if model.isOnBreak || model.breakOffered { Button("Skip break") { Task { await model.skipBreak() } } }
        if model.journalVisible {
          Text("What moved?").font(.headline)
          TextEditor(text: $model.journalText).frame(height: 70)
          Button("Save journal") { Task { await model.saveJournal() } }
        }
        if let summary = model.summary {
          GroupBox(summary.completed ? "Sprint complete" : "Ended early. It'll recover.") {
            VStack(alignment: .leading) {
              Text("\(Int(summary.actualMinutes.rounded())) minutes focused")
              Button("Dismiss summary") { model.dismissSummary() }
            }
          }
        }
        if let schedule = model.pendingSchedule {
          Text("Scheduled sprint · \(schedule.startUtc.formatted())")
            .id(SchedulePlanner.headsUpKey(schedule.schedule, start: schedule.startUtc))
            .onAppear { model.markScheduleHeadsUpSeen() }
          Text(model.scheduleClosingText)
          HStack {
            Button("Start now") { Task { await model.startScheduledSprint() } }
            Button("Skip today") { Task { await model.skipScheduledSprint() } }
          }
        }
        Divider()
        Text("Blocked apps\(model.listIsLocked ? " · sealed" : "")").font(.headline)
        Text("The Mac version blocks apps only.").foregroundStyle(.secondary)
        ForEach(Array(model.settings.blockedApps.enumerated()), id: \.offset) { index, app in
          HStack { Text(app.displayName); Spacer(); Button("Remove") { Task { await model.removeBlockedApp(at: index) } }.disabled(model.listIsLocked) }
        }
        Button("Find apps") { model.refreshAppPicker() }
        ForEach(model.pickerEntries) { entry in
          HStack {
            if let icon = entry.icon { Image(nsImage: icon).resizable().frame(width: 24, height: 24) }
            VStack(alignment: .leading) { Text(entry.name); if !entry.note.isEmpty { Text(entry.note).font(.caption) } }
            Spacer()
            Button("Block") { Task { await model.addBlockedApp(entry.blockedApp) } }.disabled(model.listIsLocked)
          }
        }
        Button("Notification permissions") { Task { await model.setNotifications(true) } }
        Button("Activate Basalt…") { model.licensePromptVisible = true }
        if !model.toast.isEmpty { Text(model.toast).foregroundStyle(.secondary) }
      }.padding(24)
    }
    .frame(minWidth: 480, minHeight: 440)
    .disabled(!model.isReady)
    .sheet(isPresented: $model.licensePromptVisible) {
      VStack(alignment: .leading, spacing: 12) {
        Text("Activate Basalt").font(.title)
        TextField("License key", text: $model.activationKey)
        TextField("Email", text: $licenseEmail)
        Text(model.licenseMessage)
        Button("Activate") { Task { await model.activateLicense(key: model.activationKey, email: licenseEmail) } }.disabled(model.licenseBusy)
        Button("Close") { model.licensePromptVisible = false }
      }.padding(24).frame(width: 420)
    }
  }
}
