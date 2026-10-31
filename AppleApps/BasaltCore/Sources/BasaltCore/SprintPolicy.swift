import Foundation

public enum ShieldLevel: Int, Codable, CaseIterable, Sendable {
  case soft = 1
  case firm = 2
  case sealed = 3
}
public enum ShieldCopy {
  public static func name(_ shield: ShieldLevel) -> String {
    switch shield {
    case .soft: "Soft"
    case .firm: "Firm"
    case .sealed: "Sealed"
    }
  }
  public static func promise(_ shield: ShieldLevel) -> String {
    switch shield {
    case .soft: "Notes distractions and nudges you."
    case .firm: "Closes blocked apps."
    case .sealed: "Closes apps and locks the list until the sprint ends."
    }
  }
  public static func bestFor(_ shield: ShieldLevel) -> String {
    switch shield {
    case .soft: "Best for classes or light work."
    case .firm: "Best for homework."
    case .sealed: "Best for exams and deep work."
    }
  }
}
public enum SprintLength {
  public static let presets = [15, 25, 45, 60, 90]
  public static let minimum = 5
  public static let maximum = 240
  public static let validationCopy = "Choose between 5 and 240 minutes."
  public static func isValid(_ minutes: Int) -> Bool { (minimum...maximum).contains(minutes) }
  public static func parse(_ text: String) -> Int? {
    guard let value = Int(trimmed(text)), isValid(value) else { return nil }
    return value
  }
  public static func summary(minutes: Int, shield: ShieldLevel, cycleSprints: Int) -> String {
    let length = minutes > 0 ? "\(minutes) min" : "Custom length"
    let cycle = cycleSprints > 1 ? "\(cycleSprints) sprints with breaks" : "One sprint"
    return "\(length) · \(ShieldCopy.name(shield)) shield · \(cycle)"
  }
}
public enum EndFlow: Sendable { case cancel, immediate, confirm, sealed }
public struct EndSprintPolicy: Sendable {
  public static let sealedPhrase = "end my sprint"
  public var testTimings: Bool
  public init(testTimings: Bool = false) { self.testTimings = testTimings }
  public var gracePeriod: TimeInterval { testTimings ? 15 : 120 }
  public func flow(shield: ShieldLevel, elapsed: TimeInterval) -> EndFlow {
    if elapsed < gracePeriod { return .cancel }
    switch shield {
    case .soft: return .immediate
    case .firm: return .confirm
    case .sealed: return .sealed
    }
  }
  public func delay(_ flow: EndFlow) -> TimeInterval {
    switch flow {
    case .confirm: testTimings ? 6 : 5
    case .sealed: testTimings ? 8 : 30
    default: 0
    }
  }
  public static func phraseMatches(_ text: String) -> Bool {
    text.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ").lowercased()
      == sealedPhrase
  }
  public static func momentumAfterEndingEarly(_ score: Double, shield: ShieldLevel) -> Double {
    roundEven(max(0, shield == .sealed ? score * 0.7 - 5 : score * 0.85 - 2), digits: 1)
  }
  public func canEndAnyway(flow: EndFlow, unlocksAt: Date, now: Date, phrase: String) -> Bool {
    now >= unlocksAt && (flow != .sealed || Self.phraseMatches(phrase))
  }
  public func buttonLabel(shield: ShieldLevel, elapsed: TimeInterval) -> String {
    switch flow(shield: shield, elapsed: elapsed) {
    case .cancel: "Cancel sprint"
    case .immediate: "End sprint"
    case .confirm: "End sprint…"
    case .sealed: "I need to stop"
    }
  }
}
public enum GracefulClose {
  public static func delay(testTimings: Bool = false) -> TimeInterval { testTimings ? 2 : 10 }
  public static func shouldWarn(shield: ShieldLevel, hardKill: Bool) -> Bool {
    !hardKill && shield.rawValue >= 2
  }
  public static func warning(_ name: String, testTimings: Bool = false) -> String {
    "\(name) is blocked — closing in \(Int(delay(testTimings: testTimings))) s. Save your work."
  }
}
