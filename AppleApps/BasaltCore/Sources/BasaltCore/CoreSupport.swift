import Foundation

func clamp<T: Comparable>(_ value: T, _ low: T, _ high: T) -> T { min(max(value, low), high) }
func roundEven(_ value: Double, digits: Int = 0) -> Double {
  let scale = pow(10.0, Double(digits))
  return (value * scale).rounded(.toNearestOrEven) / scale
}
func trimmed(_ value: String) -> String { value.trimmingCharacters(in: .whitespacesAndNewlines) }
func newID() -> String { UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased() }
func cutUTF16(_ text: String, _ maximum: Int) -> String {
  var units = Array(text.utf16.prefix(max(0, maximum)))
  if let last = units.last, (0xD800...0xDBFF).contains(last) { units.removeLast() }
  return String(decoding: units, as: UTF16.self)
}

/// A civil date, deliberately independent of UTC offsets (schedule skips survive travel).
public struct LocalDay: Codable, Hashable, Comparable, Sendable {
  public var year: Int
  public var month: Int
  public var day: Int
  public init(_ year: Int, _ month: Int, _ day: Int) {
    self.year = year
    self.month = month
    self.day = day
  }
  public init(_ date: Date, calendar: Calendar = .current) {
    let c = calendar.dateComponents([.year, .month, .day], from: date)
    self.init(c.year!, c.month!, c.day!)
  }
  public static func < (a: Self, b: Self) -> Bool {
    (a.year, a.month, a.day) < (b.year, b.month, b.day)
  }
  public func date(calendar: Calendar = .current) -> Date {
    calendar.date(from: DateComponents(year: year, month: month, day: day))!
  }
  public func adding(_ days: Int) -> Self {
    var c = Calendar(identifier: .gregorian)
    c.timeZone = TimeZone(secondsFromGMT: 0)!
    return Self(c.date(byAdding: .day, value: days, to: date(calendar: c))!, calendar: c)
  }
  public var iso: String { String(format: "%04d-%02d-%02d", year, month, day) }
}

func formatted(_ date: Date, _ format: String, calendar: Calendar) -> String {
  let f = DateFormatter()
  f.locale = Locale(identifier: "en_US_POSIX")
  f.calendar = calendar
  f.timeZone = calendar.timeZone
  f.dateFormat = format
  return f.string(from: date)
}
