import Foundation

/// The confirmation owns its deadline: opening it again cannot restart the wait.
public struct EndConfirmation: Sendable {
  public private(set) var flow: EndFlow?
  public private(set) var unlocksAt: Date?
  public var phrase = ""
  public init() {}
  @discardableResult public mutating func request(
    shield: ShieldLevel, elapsed: TimeInterval, now: Date,
    policy: EndSprintPolicy = EndSprintPolicy()
  ) -> EndFlow {
    if let flow { return flow }
    let next = policy.flow(shield: shield, elapsed: elapsed)
    if next == .confirm || next == .sealed {
      flow = next
      unlocksAt = now.addingTimeInterval(policy.delay(next))
      phrase = ""
    }
    return next
  }
  public func canEndAnyway(now: Date) -> Bool {
    guard let flow, let unlocksAt else { return false }
    return EndSprintPolicy().canEndAnyway(
      flow: flow, unlocksAt: unlocksAt, now: now, phrase: phrase)
  }
  @discardableResult public mutating func endAnyway(now: Date) -> Bool {
    guard canEndAnyway(now: now) else { return false }
    keepGoing()
    return true
  }
  public mutating func keepGoing() {
    flow = nil
    unlocksAt = nil
    phrase = ""
  }
  public var title: String { flow == .sealed ? "This sprint is sealed" : "End this sprint early?" }
  public func text(remaining: TimeInterval, momentum: Double, shield: ShieldLevel) -> String {
    let n = Int(ceil(remaining / 60))
    let after = EndSprintPolicy.momentumAfterEndingEarly(momentum, shield: shield)
    let text =
      "\(n) minute\(n == 1 ? "" : "s") left. Ending now counts as ended early: momentum \(Int(roundEven(momentum))) → \(Int(roundEven(after)))."
    return text
      + (flow == .sealed
        ? " If you really need to stop, wait for the countdown, then type \"end my sprint\"." : "")
  }
  public func countdownText(now: Date) -> String {
    guard let flow, let unlocksAt else { return "" }
    let wait = unlocksAt.timeIntervalSince(now)
    if wait > 0 { return "You can end it in \(Int(ceil(wait))) s." }
    return flow == .sealed && !EndSprintPolicy.phraseMatches(phrase)
      ? "Type the phrase to confirm." : ""
  }
}
