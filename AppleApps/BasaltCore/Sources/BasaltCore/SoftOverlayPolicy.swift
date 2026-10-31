import Foundation

public struct SoftOverlayPolicy: Sendable {
  public static let allowWindow: TimeInterval = 300
  public static let backToWorkQuiet: TimeInterval = 5
  public private(set) var tries = 0
  public private(set) var turnedBack = 0
  private var quietUntil: [String: Date] = [:]
  private var sighting: String?
  private var showing = false
  public init() {}
  public static func allowWait(_ tryNumber: Int, testTimings: Bool = false) -> TimeInterval {
    if testTimings { return 3 }
    switch tryNumber {
    case ...1: return 5
    case 2: return 10
    case 3: return 20
    default: return 30
    }
  }
  public mutating func shouldShow(_ name: String, now: Date) -> Bool {
    let key = name.lowercased()
    let fresh = sighting != key
    sighting = key
    guard fresh, !isQuiet(name, now: now) else { return false }
    showing = true
    tries += 1
    return true
  }
  @discardableResult public mutating func leftTheForeground() -> Bool {
    sighting = nil
    let old = showing
    showing = false
    return old
  }
  public func isQuiet(_ name: String, now: Date) -> Bool {
    quietUntil[name.lowercased()].map { now < $0 } ?? false
  }
  private mutating func quieten(_ name: String, now: Date, window: TimeInterval) {
    quietUntil[name.lowercased()] = now.addingTimeInterval(window)
    sighting = nil
    showing = false
  }
  public mutating func allowFiveMinutes(_ name: String, now: Date) {
    quieten(name, now: now, window: Self.allowWindow)
  }
  public mutating func backToWork(_ name: String, now: Date) {
    turnedBack += 1
    quieten(name, now: now, window: Self.backToWorkQuiet)
  }
  public mutating func closeIt(_ name: String, now: Date) {
    turnedBack += 1
    quietUntil[name.lowercased()] = now.addingTimeInterval(Self.backToWorkQuiet)
    showing = false
  }
  public mutating func reset() { self = Self() }
}
public enum SoftOverlayCopy {
  public static let closeNote = "Nothing is closed unless you choose to."
  public static func sentence(_ name: String, until: String, tryNumber: Int = 1) -> String {
    switch (max(tryNumber, 1) - 1) % 4 {
    case 0: "\(name) is on your blocklist until \(until)"
    case 1: "You set this time aside until \(until)"
    case 2: "\(name) can wait until \(until)"
    default: "\(name) will still be there after \(until)"
    }
  }
  public static func tryLine(_ number: Int) -> String {
    let n = max(1, number)
    let suffix =
      (11...13).contains(n % 100) ? "th" : [1: "st", 2: "nd", 3: "rd"][n % 10, default: "th"]
    return "\(n)\(suffix) try this sprint"
  }
  public static func intention(_ text: String) -> String {
    trimmed(text).isEmpty ? "" : "You planned: \(trimmed(text))"
  }
  public static func allowLabel(_ remaining: TimeInterval) -> String {
    guard remaining > 0 else { return "Allow 5 minutes" }
    let seconds = Int(ceil(remaining))
    return String(format: "Allow 5 minutes · %d:%02d", seconds / 60, seconds % 60)
  }
  public static func timeLeft(_ remaining: TimeInterval) -> String {
    if remaining <= 0 { return "This sprint is ending" }
    let minutes = Int(ceil(remaining / 60))
    return "\(minutes) minute\(minutes == 1 ? "" : "s") left in this sprint"
  }
  public static func allowed(_ name: String) -> String {
    "\(name) allowed for 5 minutes. It still counted as a distraction."
  }
}
