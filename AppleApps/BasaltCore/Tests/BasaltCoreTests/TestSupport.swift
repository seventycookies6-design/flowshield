import Foundation

@testable import BasaltCore

let utc = TimeZone(secondsFromGMT: 0)!
var utcCalendar: Calendar { ScheduleMatcher.calendar(utc) }
func instant(_ text: String = "2026-10-26T12:00:00Z") -> Date {
  ISO8601DateFormatter().date(from: text)!
}
func session(
  day: Int = 26, minutes: Double = 25, planned: Int = 25, completed: Bool = true,
  interrupted: Bool = false, shield: ShieldLevel = .firm
) -> FocusSession {
  var s = FocusSession()
  s.startedUtc = instant(String(format: "2026-10-%02dT12:00:00Z", day))
  s.endedUtc = s.startedUtc.addingTimeInterval(minutes * 60)
  s.plannedMinutes = planned
  s.completed = completed
  s.interrupted = interrupted
  s.shield = shield
  return s
}
func running(minutes: Int = 25, watched: Double? = 0) -> RunningSprint {
  var r = RunningSprint()
  r.startedUtc = instant()
  r.lastSeenUtc = r.startedUtc
  r.plannedMinutes = minutes
  r.watchedMinutes = watched
  return r
}
func ready() -> AppSettings {
  var s = AppSettings()
  s.isPro = true
  s.firstRunCompleted = true
  s.ensureProfiles()
  LegalTerms.accept(&s, now: instant())
  return s
}
func temporaryDirectory() throws -> URL {
  let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
  return url
}
