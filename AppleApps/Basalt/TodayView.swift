import SwiftUI
import BasaltCore

struct TodayView: View {
  @Bindable var model: AppModel
  var body: some View {
    ContentPage(title: "Today", subtitle: model.isRunning ? "One thing at a time." : "Ready when you are.") {
      if let schedule = model.pendingSchedule {
        Card("Scheduled sprint · \(schedule.startUtc.formatted(date: .omitted, time: .shortened))") {
          Text(model.scheduleClosingText)
          HStack {
            Button("Start now") { Task { await model.startScheduledSprint() } }.accessibilityIdentifier("HeadsUpStartNowButton")
            Button("Skip today") { Task { await model.skipScheduledSprint() } }.accessibilityIdentifier("HeadsUpSkipButton")
          }
        }.onAppear { model.markScheduleHeadsUpSeen() }
      }
      if model.isRunning || model.isOnBreak {
        VStack(spacing: 18) {
          TimerRing(model: model)
          if let sprint = model.activeSprint {
            Label("\(ShieldCopy.name(sprint.shield)) shield engaged", systemImage: sprint.shield.symbol).foregroundStyle(Color("Primary"))
            if !sprint.intention.isEmpty { Text("You planned: \(sprint.intention)").accessibilityIdentifier("SprintIntentionText") }
            if model.cycle.inCycle { Text(model.cycle.cycleLabel).foregroundStyle(.secondary).accessibilityIdentifier("CycleProgressText") }
            Button(model.endButtonLabel) { Task { await model.requestEnd() } }.accessibilityIdentifier("StopSprintButton")
          }
        }.frame(maxWidth: .infinity).padding(.vertical, 24)
      }
      if model.isOnBreak { BreakView(model: model) }
      if let summary = model.summary { SummaryView(model: model, session: summary) }
      if model.breakOffered { BreakView(model: model) }
      if !model.isRunning && !model.isOnBreak {
        SprintSetupView(model: model)
        Button("Start sprint", systemImage: "play.fill") { Task { await model.start() } }
          .buttonStyle(.borderedProminent).controlSize(.large).disabled(!model.canStart).accessibilityIdentifier("StartSprintButton")
      }
      if let warning = model.firmWarning { FirmWarningView(message: warning) { model.dismissFirmWarning() } }
      if !model.isRunning {
        if let milestone = model.settings.earnedMilestones.first(where: { !$0.shown }), let kind = MilestoneKind(rawValue: milestone.id) {
          Card("Milestone") {
            Label(Milestones.title(kind), systemImage: "checkmark.seal").accessibilityIdentifier("MilestoneNoticeText")
            Text(Milestones.sentence(kind))
            Button("Dismiss") { Task { await model.markMilestoneShown(milestone.id) } }.accessibilityIdentifier("MilestoneDismissButton")
          }
        }
        Card {
          HStack { Stat(value: model.settings.momentumScore.formatted(.number.precision(.fractionLength(0...1))), label: "Momentum").accessibilityIdentifier("MomentumValue"); Stat(value: "\(model.settings.currentStreak)", label: "Day streak").accessibilityIdentifier("StreakText") }
          if DailyGoal.isSet(model.settings) {
            Text("Daily goal · \(model.goalProgress)").accessibilityIdentifier("DailyGoalProgressText")
            ProgressView(value: DailyGoal.fraction(model.settings, day: LocalDay(model.now))).accessibilityLabel("Daily goal").accessibilityIdentifier("DailyGoalBar")
          }
        }
      }
    }
  }
}

struct SprintSetupView: View {
  @Bindable var model: AppModel
  @State private var custom = false
  @State private var customText = "30"
  private var invalid: Bool { custom && SprintLength.parse(customText) == nil }
  var body: some View {
    VStack(alignment: .leading, spacing: 20) {
      if !model.settings.templates.isEmpty {
        ViewThatFits(in: .horizontal) {
          HStack { templateMenu; Text("Choose a template, or set up a sprint below.").foregroundStyle(.secondary) }
          templateMenu
        }
      }
      Card("Sprint length") {
        Picker("Sprint length", selection: lengthChoice) {
          ForEach(SprintLength.presets, id: \.self) { minutes in
            Text("\(minutes) min").tag(minutes).accessibilityIdentifier("SprintLength_\(minutes)")
          }
          Text("Custom").tag(Self.customTag).accessibilityIdentifier("SprintLength_Custom")
        }.pickerStyle(.segmented).labelsHidden().accessibilityIdentifier("SprintLengthPicker")
        if custom {
          HStack { TextField("Minutes", text: $customText).frame(width: 90).accessibilityIdentifier("CustomMinutesInput"); Text("min (5–240)").foregroundStyle(.secondary) }
            .onChange(of: customText) { _, value in
              model.customMinutesValid = SprintLength.parse(value) != nil
              if let minutes = SprintLength.parse(value) { Task { await model.setSprintMinutes(minutes) } }
            }
          if invalid { Text(SprintLength.validationCopy).foregroundStyle(Color("Rose")).accessibilityIdentifier("CustomMinutesError") }
        }
      }
      Card("Shield level") {
        ShieldPicker(model: model)
        Text(ShieldCopy.promise(model.settings.defaultShield)).accessibilityIdentifier("ShieldDescriptionText")
        Text(ShieldCopy.bestFor(model.settings.defaultShield)).foregroundStyle(.secondary).accessibilityIdentifier("ShieldBestForText")
        if model.settings.defaultShield == .sealed {
          Text("If Basalt closes, a Sealed sprint picks up again when it reopens. After a reboot that only happens by itself if Basalt opens at login (Settings → App).")
            .font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("SealedRestartHint")
        }
        if model.settings.hardKillModeEnabled { Text("Hard kill mode is on (Settings), so Soft closes blocked apps instead of nudging.").font(.caption).accessibilityIdentifier("SoftHardKillHint") }
        Picker("Blocklist profile", selection: Binding(get: { model.settings.activeProfileId }, set: { value in Task { await model.selectProfile(value) } })) {
          ForEach(model.settings.profiles, id: \.id) { Text($0.name).tag($0.id) }
        }.accessibilityIdentifier("TodayProfilePicker")
      }
      Card("Cycle") {
        Picker("Sprints in a row", selection: Binding(get: { model.settings.cycleSprints }, set: { value in Task { await model.setCycleSprints(value) } })) {
          Text("One sprint").tag(0).accessibilityIdentifier("Cycle_Off")
          ForEach(2...4, id: \.self) { Text("\($0) sprints").tag($0).accessibilityIdentifier("Cycle_\($0)") }
        }.pickerStyle(.segmented).accessibilityIdentifier("CyclePicker")
        Text("\(model.settings.shortBreakMinutes)-minute breaks between sprints. A longer break after every four.").font(.caption).foregroundStyle(.secondary)
      }
      VStack(alignment: .leading, spacing: 6) {
        TextField("What is this sprint for?", text: $model.intention).textFieldStyle(.roundedBorder).accessibilityLabel("Intention").accessibilityIdentifier("IntentionInput")
        Text("Optional. It's shown on the timer and again when the sprint ends.").font(.caption).foregroundStyle(.secondary)
      }
    }.disabled(model.isRunning || model.isOnBreak)
      .onAppear { custom = !SprintLength.presets.contains(model.settings.defaultSprintMinutes); customText = "\(model.settings.defaultSprintMinutes)" }
  }
  private static let customTag = -1
  private var lengthChoice: Binding<Int> {
    Binding(
      get: { custom ? Self.customTag : model.settings.defaultSprintMinutes },
      set: { choice in
        if choice == Self.customTag {
          custom = true; customText = "\(model.settings.lastCustomSprintMinutes)"
        } else {
          custom = false; model.customMinutesValid = true
          Task { await model.setSprintMinutes(choice) }
        }
      })
  }
  private var templateMenu: some View {
    Menu("Templates") {
      ForEach(model.settings.templates, id: \.id) { template in
        Button(template.name) { custom = false; model.customMinutesValid = true; Task { await model.applyTemplate(template.id) } }.accessibilityIdentifier("TemplateChip_\(template.name)")
      }
    }.accessibilityIdentifier("TodayTemplates")
  }
}

struct ShieldPicker: View {
  let model: AppModel
  var prefix = "Shield_"
  var body: some View {
    Picker("Shield level", selection: Binding(get: { model.settings.defaultShield }, set: { shield in Task { await model.selectShield(shield) } })) {
      ForEach(ShieldLevel.allCases, id: \.self) { shield in
        Label(ShieldCopy.name(shield), systemImage: shield.symbol).tag(shield)
          .accessibilityIdentifier(prefix + ShieldCopy.name(shield))
      }
    }.pickerStyle(.segmented).labelsHidden().disabled(model.isRunning).accessibilityIdentifier(prefix + "Picker")
  }
}

struct TimerRing: View {
  let model: AppModel
  private var fraction: Double {
    let total = Double(model.activeSprint?.plannedMinutes ?? model.settings.activeBreak?.minutes ?? 1) * 60
    return min(1, max(0, model.remaining / max(1, total)))
  }
  var body: some View {
    ZStack {
      Circle().stroke(Color("Track"), lineWidth: 10)
      Circle().trim(from: 0, to: fraction).stroke(Color("Primary"), style: StrokeStyle(lineWidth: 10, lineCap: .round)).rotationEffect(.degrees(-90))
      VStack(spacing: 10) {
        Text(model.remainingText).font(.largeTitle).monospacedDigit().accessibilityIdentifier("SprintTimerText")
        Text(model.isOnBreak ? "Break — the shield is down" : "Time remaining").font(.caption).foregroundStyle(.secondary)
      }
    }.frame(width: 230, height: 230).accessibilityElement(children: .combine)
      .accessibilityLabel("\(model.isOnBreak ? "Break" : "Sprint"), \(model.remainingText) remaining")
  }
}

struct SummaryView: View {
  @Bindable var model: AppModel
  let session: FocusSession
  var body: some View {
    Card {
      Label(session.summaryTitle(momentum: model.settings.momentumScore), systemImage: session.completed ? "checkmark.circle" : "circle").font(.headline).accessibilityIdentifier("SummaryTitle")
      HStack {
        Stat(value: "\(Int(session.actualMinutes.rounded())) min", label: "Focused").accessibilityIdentifier("SummaryMinutesValue")
        Stat(value: "\(session.blocksEnforced)", label: "Distractions caught").accessibilityIdentifier("SummaryDistractionsValue")
        Stat(value: (model.settings.momentumScore - session.momentumAtStart).formatted(.number.sign(strategy: .always()).precision(.fractionLength(0...1))), label: "Momentum change").accessibilityIdentifier("SummaryMomentumText")
      }
      Text(session.distractionSummary).font(.caption).foregroundStyle(.secondary)
      if session.turnedBack > 0 { Text(HistoryStats.turnedBackText(session.turnedBack)).font(.caption).accessibilityIdentifier("SummaryTurnedBackText") }
      if !session.intention.isEmpty { Text("You planned: \(session.intention)").accessibilityIdentifier("SummaryIntentionText") }
      if model.journalVisible {
        Text(session.journalPrompt).font(.headline).accessibilityIdentifier("JournalPromptTitle")
        Text("One line. You'll thank yourself in three months.").font(.caption).foregroundStyle(.secondary)
        TextField("What got done?", text: $model.journalText).textFieldStyle(.roundedBorder).accessibilityIdentifier("JournalInput")
        HStack {
          Button("Save entry") { Task { await model.saveJournal() } }.accessibilityIdentifier("SaveJournalButton")
          Button("Skip") { model.dismissJournal() }.accessibilityIdentifier("SkipJournalButton")
        }
      }
      Button("Dismiss summary") { model.dismissSummary() }.accessibilityIdentifier("DismissSummaryButton")
    }
  }
}

struct BreakView: View {
  let model: AppModel
  var body: some View {
    Card(model.isOnBreak ? "Break · \(model.remainingText)" : "Take a break?") {
      Text(BreakCopy.panelText(inSleepWindow: false, onBreak: model.isOnBreak, isLong: model.settings.completedSprintsInARow > 0 && model.settings.completedSprintsInARow % 4 == 0, minutes: model.offeredBreakMinutes, sleepEndsText: "")).accessibilityIdentifier("BreakPanelText")
      HStack {
        if model.breakOffered { Button("Start break") { Task { await model.startBreak() } }.accessibilityIdentifier("StartBreakButton") }
        Button("Skip break") { Task { await model.skipBreak() } }.accessibilityIdentifier("SkipBreakButton")
        Button("Start next sprint") { Task { await model.startNextSprint() } }.accessibilityIdentifier("StartNextSprintButton")
      }
    }
  }
}

struct EndSprintView: View {
  @Bindable var model: AppModel
  var body: some View {
    VStack(alignment: .leading, spacing: 20) {
      Label(model.endConfirmation.title, systemImage: (model.activeSprint?.shield ?? .firm).symbol).font(.title2).accessibilityIdentifier("EndPanelTitle")
      Text(model.endConfirmation.text(remaining: model.remaining, momentum: model.settings.momentumScore, shield: model.activeSprint?.shield ?? .firm)).accessibilityIdentifier("EndPanelText")
      if model.endConfirmation.flow == .sealed {
        TextField("end my sprint", text: $model.endConfirmation.phrase).textFieldStyle(.roundedBorder).accessibilityLabel("Type end my sprint to confirm").accessibilityIdentifier("EndPhraseInput")
      }
      Text(model.endConfirmation.countdownText(now: model.now)).foregroundStyle(.secondary).accessibilityIdentifier("EndCountdownText")
      HStack {
        Button("Keep going") { model.keepGoing() }.buttonStyle(.borderedProminent).keyboardShortcut(.cancelAction).accessibilityIdentifier("KeepGoingButton")
        Spacer()
        Button("End anyway", role: .destructive) { Task { await model.endAnyway() } }.disabled(!model.canEndAnyway).accessibilityIdentifier("EndAnywayButton")
      }
    }.padding(28).frame(width: 470).interactiveDismissDisabled()
  }
}

struct FirmWarningView: View {
  let message: String
  var dismiss: () -> Void = {}
  var body: some View { Card("Save your work") { Label(message, systemImage: "shield.lefthalf.filled"); Button("Dismiss", action: dismiss).accessibilityIdentifier("DismissFirmWarning") } }
}

struct RunningAppsView: View {
  let model: AppModel
  var body: some View {
    VStack(alignment: .leading, spacing: 18) {
      Text(model.runningAppsToClose.count == 1 ? "One blocked app is open" : "\(model.runningAppsToClose.count) blocked apps are open").font(.title2).accessibilityIdentifier("RunningAppsTitle")
      Text(model.settings.hardKillModeEnabled ? "Hard kill mode is on. They will close immediately when the sprint starts — no grace period." : "They will be asked to close when the sprint starts, with 10 seconds to save.").accessibilityIdentifier("RunningAppsExplanation")
      Text(model.runningAppsToClose.joined(separator: ", ")).accessibilityIdentifier("RunningAppsList")
      HStack {
        Button("Close them now") { Task { await model.confirmStart() } }.buttonStyle(.borderedProminent).accessibilityIdentifier("CloseThemNowButton")
        Button("Start anyway") { Task { await model.confirmStart() } }.accessibilityIdentifier("StartAnywayButton")
        Button("Cancel") { model.dismissStart() }.keyboardShortcut(.cancelAction)
      }
    }.padding(28).frame(width: 500)
  }
}
