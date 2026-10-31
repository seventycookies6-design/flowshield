import Foundation

public enum ExportFormat: Int, Codable, Sendable {
  case csv = 0
  case markdown = 1
}
public enum JournalExport {
  public static let csvHeader = [
    "date (local)", "start (local)", "planned minutes", "actual minutes", "shield", "completed",
    "ended early", "interrupted", "distractions blocked", "intention", "journal",
  ]
  public static func inRange(
    _ sessions: [FocusSession], from: LocalDay, to: LocalDay, calendar: Calendar = .current
  ) -> [FocusSession] {
    sessions.filter {
      let d = LocalDay($0.startedUtc, calendar: calendar)
      return d >= min(from, to) && d <= max(from, to)
    }.sorted { $0.startedUtc < $1.startedUtc }
  }
  public static func defuse(_ value: String) -> String {
    guard let first = value.unicodeScalars.first else { return value }
    return [61, 43, 45, 64, 9, 13].contains(first.value) ? "'" + value : value
  }
  public static func escapeCSV(_ value: String) -> String {
    let text = defuse(value)
    return text.unicodeScalars.contains(where: { [44, 34, 13, 10].contains($0.value) })
      ? "\"" + text.replacingOccurrences(of: "\"", with: "\"\"") + "\"" : text
  }
  public static func number(_ value: Double) -> String {
    let f = NumberFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.minimumFractionDigits = 0
    f.maximumFractionDigits = 1
    f.usesGroupingSeparator = false
    return f.string(from: NSNumber(value: value))!
  }
  public static func csv(_ sessions: [FocusSession], calendar: Calendar = .current) -> String {
    func yes(_ value: Bool) -> String { value ? "yes" : "no" }
    let rows = sessions.map { s in
      [
        LocalDay(s.startedUtc, calendar: calendar).iso,
        formatted(s.startedUtc, "HH:mm", calendar: calendar), String(s.plannedMinutes),
        number(s.actualMinutes), ShieldCopy.name(s.shield), yes(s.completed), yes(s.endedEarly),
        yes(s.interrupted), String(s.blocksEnforced), s.intention, s.journal,
      ]
    }
    return ([csvHeader] + rows).map { $0.map(escapeCSV).joined(separator: ",") + "\r\n" }.joined()
  }
  public static func escapeMarkdown(_ value: String) -> String {
    let text = trimmed(
      value.replacingOccurrences(of: "\r", with: " ").replacingOccurrences(of: "\n", with: " "))
    guard let first = text.first else { return text }
    return "#-*>+|`".contains(first) ? "\\" + text : text
  }
  public static func markdown(
    _ sessions: [FocusSession], from: LocalDay, to: LocalDay, calendar: Calendar = .current
  ) -> String {
    var text =
      "# Basalt journal\r\n\r\n\(min(from, to).iso) to \(max(from, to).iso). Times are local.\r\n\r\n"
    let days = Dictionary(grouping: sessions) { LocalDay($0.startedUtc, calendar: calendar) }
    for day in days.keys.sorted(by: >) {
      text += "## \(day.iso)\r\n\r\n"
      for s in days[day]!.sorted(by: { $0.startedUtc < $1.startedUtc }) {
        text +=
          "- \(formatted(s.startedUtc, "HH:mm", calendar: calendar)) · \(number(s.actualMinutes)) min · \(ShieldCopy.name(s.shield)) · \(s.outcome)\r\n"
        if !trimmed(s.intention).isEmpty {
          text += "  - Intention: \(escapeMarkdown(s.intention))\r\n"
        }
        if !trimmed(s.journal).isEmpty { text += "  - \(escapeMarkdown(s.journal))\r\n" }
        text += "\r\n"
      }
    }
    if days.isEmpty { text += "No sprints in this range.\r\n" }
    return text
  }
  public static func suggestedFileName(from: LocalDay, to: LocalDay, format: ExportFormat) -> String
  {
    "Basalt journal \(min(from, to).iso) to \(max(from, to).iso).\(format == .csv ? "csv" : "md")"
  }
  public static func data(
    _ sessions: [FocusSession], from: LocalDay, to: LocalDay, format: ExportFormat,
    calendar: Calendar = .current
  ) -> Data {
    let rows = inRange(sessions, from: from, to: to, calendar: calendar)
    let text =
      format == .csv
      ? csv(rows, calendar: calendar) : markdown(rows, from: from, to: to, calendar: calendar)
    return (format == .csv ? Data([0xEF, 0xBB, 0xBF]) : Data()) + Data(text.utf8)
  }
  public static func write(
    to url: URL, sessions: [FocusSession], from: LocalDay, to: LocalDay, format: ExportFormat,
    calendar: Calendar = .current
  ) throws {
    try data(sessions, from: from, to: to, format: format, calendar: calendar).write(
      to: url, options: .atomic)
  }
}
