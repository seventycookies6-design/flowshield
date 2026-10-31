import SwiftUI
import Charts
import BasaltCore

struct HistoryView: View {
  let model: AppModel
  @State private var weekOffset = 0
  @State private var explanation = false
  @State private var selectedDay: LocalDay?
  @Environment(\.openSettings) private var openSettings
  private var week: HistoryStats.Week { HistoryStats.forWeek(model.settings.sessions, day: LocalDay(model.now).adding(weekOffset * 7)) }
  private var rows: [FocusSession] {
    HistoryStats.newestSessions(model.settings.sessions).filter {
      let day = LocalDay($0.startedUtc)
      return selectedDay.map { $0 == day } ?? true
    }
  }
  var body: some View {
    ContentPage(title: "History", subtitle: "Your focus, over time.") {
      HStack {
        Button("Previous week", systemImage: "chevron.left") { weekOffset -= 1; selectedDay = nil }.labelStyle(.iconOnly).accessibilityIdentifier("PreviousWeekButton")
        Text("\(week.start.date().formatted(date: .abbreviated, time: .omitted)) – \(week.end.date().formatted(date: .abbreviated, time: .omitted))").accessibilityIdentifier("WeekRangeText")
        Button("Next week", systemImage: "chevron.right") { weekOffset += 1; selectedDay = nil }.labelStyle(.iconOnly).disabled(weekOffset >= 0).accessibilityIdentifier("NextWeekButton")
        Spacer()
        Button("This week") { weekOffset = 0; selectedDay = nil }.accessibilityIdentifier("ThisWeekButton")
      }
      Card {
        HStack {
          Stat(value: (week.focusMinutes / 60).formatted(.number.precision(.fractionLength(1))), label: "Hours focused this week").accessibilityIdentifier("WeekFocusHours")
          Stat(value: "\(week.sprintsCompleted)", label: "Sprints completed").accessibilityIdentifier("WeekSprintsValue")
          Stat(value: "\(week.distractions)", label: "Distractions caught").accessibilityIdentifier("WeekDistractionsValue")
        }
        if week.turnedBack > 0 { Text(HistoryStats.turnedBackText(week.turnedBack)).font(.caption) }
        let most = HistoryStats.mostBlocked(model.settings.profiles.flatMap(\.apps))
        Text(most.isEmpty ? "Nothing has needed blocking yet." : "Most-blocked app · \(most)").font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("MostBlockedApp")
      }
      Card("Focus minutes, last 30 days") {
        let cells = HistoryStats.heatmap(model.settings.sessions, today: LocalDay(model.now))
        LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 10), spacing: 8) {
          ForEach(cells, id: \.day) { cell in
            Button { selectedDay = cell.day } label: {
              VStack(spacing: 4) {
                Text(cell.day.date().formatted(.dateTime.weekday(.abbreviated))).font(.caption2)
                Text("\(cell.day.day)").font(.caption)
                Text("\(cell.minutes)m").font(.caption2).monospacedDigit()
              }.frame(maxWidth: .infinity).padding(.vertical, 6)
            }.buttonStyle(.bordered).background(cell.step == 0 ? Color.clear : Color("Primary").opacity(Double(cell.step) * 0.10), in: RoundedRectangle(cornerRadius: 8))
              .help("\(cell.day.iso): \(cell.minutes) focus minutes")
              .accessibilityLabel("\(cell.day.iso), \(cell.minutes) focus minutes")
              .accessibilityIdentifier("HeatCell_\(cell.day.iso)")
          }
        }.accessibilityIdentifier("FocusHeatmap")
        HStack { Text("Less"); ForEach(0..<5) { step in RoundedRectangle(cornerRadius: 2).fill(step == 0 ? Color("Track") : Color("Primary").opacity(Double(step) / 4)).frame(width: 18, height: 12).accessibilityHidden(true) }; Text("More"); Spacer(); Text("Minutes shown on each day") }.font(.caption).foregroundStyle(.secondary)
      }
      Card("Momentum") {
        Text("Finished sprints compound. Abandoned ones decay — they don't reset.").foregroundStyle(.secondary)
        let points = MomentumTrend.points(model.settings.sessions, today: LocalDay(model.now))
        Chart(points, id: \.day) { point in
          LineMark(x: .value("Day", point.day.date()), y: .value("Momentum", point.score)).foregroundStyle(Color("Primary"))
        }.chartYScale(domain: 0...max(10, MomentumTrend.ceiling(points))).frame(height: 160)
          .accessibilityLabel("Momentum over the last 30 days").accessibilityIdentifier("MomentumTrendChart")
        DisclosureGroup("How momentum works", isExpanded: $explanation) {
          ForEach(MomentumTrend.explanation, id: \.self) { Text($0).padding(.top, 6) }
        }.accessibilityIdentifier("MomentumExplainerButton")
      }
      Card("Milestones") {
        let milestones = Milestones.history(model.settings.earnedMilestones)
        if milestones.isEmpty { Text("None yet. A first Sealed sprint, ten hours focused, seven days in a row and momentum at 100 are listed here as you reach them.").foregroundStyle(.secondary).accessibilityIdentifier("MilestonesEmptyText") }
        ForEach(milestones, id: \.id) { record in
          if let kind = MilestoneKind(rawValue: record.id) {
            LabeledContent { Text(record.earnedUtc.formatted(date: .abbreviated, time: .omitted)).foregroundStyle(.secondary) } label: {
              Label(Milestones.title(kind), systemImage: "checkmark.seal")
              Text(Milestones.sentence(kind)).font(.caption).foregroundStyle(.secondary)
            }
          }
        }
      }
      Card("Every sprint") {
        HStack {
          Text("Newest first. Everything here is stored on this Mac only.").font(.caption).foregroundStyle(.secondary)
          Spacer()
          Button("Export your journal") { model.settingsPane = .data; openSettings() }.accessibilityIdentifier("HistoryExportButton")
        }
        if selectedDay != nil { Button("Show this week") { selectedDay = nil } }
        if rows.isEmpty { Text("No sprints yet. Start one on Today and it will show up here, with whatever you write down afterwards.").foregroundStyle(.secondary).accessibilityIdentifier("HistoryEmptyText") }
        ForEach(Array(rows.enumerated()), id: \.offset) { _, session in
          VStack(alignment: .leading, spacing: 7) {
            HStack {
              Text("\(session.startedUtc.formatted(date: .abbreviated, time: .shortened)) · \(Int(session.actualMinutes.rounded())) min · \(ShieldCopy.name(session.shield))").font(.headline).accessibilityIdentifier("HistoryRowHeading")
              Spacer(); Text(session.outcome.capitalized).font(.caption).accessibilityIdentifier("HistoryRowOutcome")
            }
            if !session.intention.isEmpty { Text("You planned: \(session.intention)").accessibilityIdentifier("HistoryRowIntention") }
            if !session.journal.isEmpty { Text(session.journal).textSelection(.enabled).accessibilityIdentifier("HistoryRowJournal") }
            Text(session.distractionSummary).font(.caption).foregroundStyle(.secondary)
          }.padding(.vertical, 8)
          Divider()
        }
      }
    }
  }
}
