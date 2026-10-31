import SwiftUI
import BasaltCore

struct ScheduleView: View {
  let model: AppModel
  @State private var schedule: SprintSchedule?
  @State private var template: StudyTemplate?
  var body: some View {
    ContentPage(title: "Schedule", subtitle: "Make room for the work you plan to do.") {
      Card("Your schedules") {
        Text("A template starts by itself at the time you pick. By default Basalt asks five minutes before.").foregroundStyle(.secondary)
        if model.settings.schedules.isEmpty { Text("No schedules yet. Add a schedule to plan your next sprint.").foregroundStyle(.secondary) }
        ForEach(model.settings.schedules, id: \.id) { row in
          HStack {
            Toggle(isOn: Binding(get: { row.enabled }, set: { value in var edited = row; edited.enabled = value; Task { await model.saveSchedule(edited) } })) {
              VStack(alignment: .leading, spacing: 4) {
                Text(model.settings.templates.first { $0.id == row.templateId }?.name ?? "Template").font(.headline)
                Text("\(ScheduleEditor.dayNames(row.days)) · \(String(format: "%02d:%02d", row.startMinuteOfDay / 60, row.startMinuteOfDay % 60))\(row.askFirst ? " · Ask five minutes before" : "")").font(.caption).foregroundStyle(.secondary)
              }
            }.accessibilityIdentifier("ScheduleEnabled_\(row.id)")
            Spacer()
            Button("Edit") { schedule = row }.accessibilityIdentifier("EditSchedule_\(row.id)")
            Button("Delete", role: .destructive) { Task { await model.deleteSchedule(row.id) } }.accessibilityIdentifier("DeleteSchedule_\(row.id)")
          }.padding(.vertical, 5)
        }
        Button("Add schedule", systemImage: "plus") { var value = SprintSchedule(); value.templateId = model.settings.templates.first?.id ?? ""; value.days = [1, 2, 3, 4, 5]; schedule = value }.disabled(model.settings.templates.isEmpty).accessibilityIdentifier("AddScheduleButton")
      }
      Card("Templates") {
        ForEach(model.settings.templates, id: \.id) { row in
          HStack {
            VStack(alignment: .leading, spacing: 4) {
              Text(row.name).font(.headline)
              Text(SprintLength.summary(minutes: row.sprintMinutes, shield: row.shield, cycleSprints: row.cycleSprints)).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Button("Edit") { template = row }.accessibilityIdentifier("EditTemplate_\(row.name)")
            Button("Delete", role: .destructive) { Task { await model.deleteTemplate(row.id) } }.accessibilityIdentifier("DeleteTemplate_\(row.name)")
          }.padding(.vertical, 5)
        }
        HStack {
          Button("New template") { template = StudyTemplate() }.accessibilityIdentifier("NewTemplateButton")
          Button("Restore built-ins") { Task { await model.restoreTemplates() } }.accessibilityIdentifier("RestoreTemplatesButton")
        }
      }
      SleepWindowView(model: model)
    }
    .sheet(isPresented: Binding(get: { schedule != nil }, set: { if !$0 { schedule = nil } })) {
      if let schedule { ScheduleEditor(model: model, initial: schedule) { self.schedule = nil } }
    }
    .sheet(isPresented: Binding(get: { template != nil }, set: { if !$0 { template = nil } })) {
      if let template { TemplateEditor(model: model, initial: template) { self.template = nil } }
    }
  }
}

struct SleepWindowView: View {
  let model: AppModel
  @State private var starts = Date()
  @State private var ends = Date()
  private func minute(_ date: Date) -> Int {
    let parts = Calendar.current.dateComponents([.hour, .minute], from: date)
    return (parts.hour ?? 0) * 60 + (parts.minute ?? 0)
  }
  var body: some View {
    Card("Sleep window") {
      Toggle("Scheduled sleep blocking", isOn: Binding(get: { model.settings.isSleepBlockEnabled }, set: { enabled in Task { await model.setSleepBlock(enabled: enabled, startMinute: model.settings.sleepBlockStartMinute, endMinute: model.settings.sleepBlockEndMinute) } })).accessibilityIdentifier("SleepBlockToggle")
      Text("Blocks your list automatically inside the window below.").font(.caption).foregroundStyle(.secondary)
      Text("Breaks pause the nightly shield on Mac.").font(.caption).foregroundStyle(.secondary)
      HStack {
        DatePicker("Starts", selection: $starts, displayedComponents: .hourAndMinute).accessibilityIdentifier("SleepStartInput")
        DatePicker("Ends", selection: $ends, displayedComponents: .hourAndMinute).accessibilityIdentifier("SleepEndInput")
      }
      if minute(starts) == minute(ends) { Text("Start and end can't be the same time — that window never opens.").foregroundStyle(Color("Rose")).accessibilityIdentifier("SleepStatusText") }
      Button("Save window") { Task { await model.setSleepBlock(enabled: model.settings.isSleepBlockEnabled, startMinute: minute(starts), endMinute: minute(ends)) } }.disabled(minute(starts) == minute(ends)).accessibilityIdentifier("SaveSleepWindowButton")
    }.disabled(!model.hasAccess)
      .onAppear {
        let day = Calendar.current.startOfDay(for: model.now)
        starts = day.addingTimeInterval(Double(model.settings.sleepBlockStartMinute * 60))
        ends = day.addingTimeInterval(Double(model.settings.sleepBlockEndMinute * 60))
      }
  }
}

struct ScheduleEditor: View {
  let model: AppModel
  @State private var value: SprintSchedule
  @State private var time: Date
  let close: () -> Void
  static let days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
  static func dayNames(_ selected: [Int]) -> String { selected.sorted().filter { days.indices.contains($0) }.map { days[$0] }.joined(separator: ", ") }
  init(model: AppModel, initial: SprintSchedule, close: @escaping () -> Void) {
    self.model = model; _value = State(initialValue: initial); self.close = close
    _time = State(initialValue: Calendar.current.startOfDay(for: Date()).addingTimeInterval(Double(initial.startMinuteOfDay * 60)))
  }
  var body: some View {
    VStack(alignment: .leading, spacing: 22) {
      Text(value.id.isEmpty ? "Add schedule" : "Edit schedule").font(.title2)
      Form {
        Picker("Template", selection: $value.templateId) { ForEach(model.settings.templates, id: \.id) { Text($0.name).tag($0.id) } }.accessibilityIdentifier("ScheduleTemplatePicker")
        HStack { ForEach(0..<7) { day in Toggle(Self.days[day], isOn: Binding(get: { value.days.contains(day) }, set: { yes in if yes { value.days.append(day) } else { value.days.removeAll { $0 == day } } })).toggleStyle(.button).accessibilityIdentifier("ScheduleDay_\(day)") } }
        DatePicker("Starts", selection: $time, displayedComponents: .hourAndMinute).accessibilityIdentifier("ScheduleTimeInput")
        Toggle("Ask five minutes before", isOn: $value.askFirst).accessibilityIdentifier("ScheduleAskFirstToggle")
      }
      if value.days.isEmpty { Text("Choose at least one day.").foregroundStyle(Color("Rose")) }
      HStack {
        Button("Cancel", action: close).keyboardShortcut(.cancelAction).accessibilityIdentifier("CancelScheduleButton")
        Spacer()
        Button("Save schedule") {
          let c = Calendar.current.dateComponents([.hour, .minute], from: time)
          value.startMinuteOfDay = (c.hour ?? 0) * 60 + (c.minute ?? 0)
          Task { await model.saveSchedule(value); close() }
        }.buttonStyle(.borderedProminent).disabled(value.days.isEmpty || value.templateId.isEmpty).accessibilityIdentifier("SaveScheduleButton")
      }
    }.padding(28).frame(width: 520)
  }
}

struct TemplateEditor: View {
  let model: AppModel
  @State private var value: StudyTemplate
  @State private var minutes: String
  @State private var breakMinutes: String
  let close: () -> Void
  init(model: AppModel, initial: StudyTemplate, close: @escaping () -> Void) {
    self.model = model; _value = State(initialValue: initial); self.close = close
    _minutes = State(initialValue: "\(initial.sprintMinutes)"); _breakMinutes = State(initialValue: "\(initial.breakMinutes)")
  }
  private var valid: Bool { !value.name.trimmingCharacters(in: .whitespaces).isEmpty && SprintLength.parse(minutes) != nil && CycleState.isValidBreakMinutes(Int(breakMinutes) ?? 0) }
  var body: some View {
    VStack(alignment: .leading, spacing: 20) {
      Text(value.id.isEmpty ? "New template" : "Edit template").font(.title2)
      Form {
        TextField("Name", text: $value.name).accessibilityIdentifier("TemplateNameInput")
        TextField("Sprint minutes (5–240)", text: $minutes).accessibilityIdentifier("TemplateMinutesInput")
        Picker("Shield", selection: $value.shield) { ForEach(ShieldLevel.allCases, id: \.self) { Label(ShieldCopy.name($0), systemImage: $0.symbol).tag($0) } }.accessibilityIdentifier("TemplateShieldPicker")
        Picker("Sprints in a row", selection: $value.cycleSprints) { Text("One sprint").tag(0); ForEach(2...4, id: \.self) { Text("\($0) sprints").tag($0) } }.accessibilityIdentifier("TemplateCyclePicker")
        TextField("Break minutes (1–60)", text: $breakMinutes).accessibilityIdentifier("TemplateBreakInput")
        Picker("Blocklist", selection: $value.profileId) {
          Text("Current profile").tag("")
          ForEach(model.settings.profiles, id: \.id) { Text($0.name).tag($0.id) }
        }.accessibilityIdentifier("TemplateProfilePicker")
      }
      if SprintLength.parse(minutes) == nil { Text(SprintLength.validationCopy).foregroundStyle(Color("Rose")) }
      HStack {
        Button("Cancel", action: close).keyboardShortcut(.cancelAction).accessibilityIdentifier("CancelTemplateButton")
        Spacer()
        Button("Save template") { value.sprintMinutes = Int(minutes) ?? 25; value.breakMinutes = Int(breakMinutes) ?? 5; Task { await model.saveTemplate(value); close() } }.buttonStyle(.borderedProminent).disabled(!valid).accessibilityIdentifier("SaveTemplateButton")
      }
    }.padding(28).frame(width: 480)
  }
}
