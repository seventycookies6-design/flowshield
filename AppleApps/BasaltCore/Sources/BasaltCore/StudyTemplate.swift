import Foundation

public struct StudyTemplate: Codable, Equatable, Sendable {
  public static let maxNameLength = 40
  public var id: String = ""
  public var name: String = ""
  public var sprintMinutes: Int = 25
  public var shield: ShieldLevel = .firm
  public var cycleSprints: Int = 0
  public var breakMinutes: Int = 5
  public var profileId: String = ""
  public var builtInKey: String = ""
  public init() {}
  public var isBuiltIn: Bool { !builtInKey.isEmpty }
  @discardableResult public mutating func normalize() -> Bool {
    let before = self
    if trimmed(id).isEmpty { id = newID() }
    name = trimmed(cutUTF16(trimmed(name).isEmpty ? "Untitled template" : trimmed(name), 40))
    sprintMinutes = clamp(sprintMinutes, 5, 240)
    if !CycleState.choices.contains(cycleSprints) { cycleSprints = 0 }
    breakMinutes = clamp(breakMinutes, 1, 60)
    return self != before
  }
  public static func builtIns() -> [Self] {
    [
      ("Homework evening", 45, ShieldLevel.firm, 3, 10, "homework"),
      ("Exam prep", 90, .sealed, 0, 5, "exam"), ("Light study", 25, .soft, 0, 5, "light"),
    ].map {
      var t = Self()
      t.id = newID()
      t.name = $0.0
      t.sprintMinutes = $0.1
      t.shield = $0.2
      t.cycleSprints = $0.3
      t.breakMinutes = $0.4
      t.builtInKey = $0.5
      return t
    }
  }
}

extension StudyTemplate {
  private enum CodingKeys: String, CodingKey {
    case id, name, sprintMinutes, shield, cycleSprints, breakMinutes, profileId, builtInKey
  }
  public init(from decoder: any Decoder) throws {
    self.init()
    let c = try decoder.container(keyedBy: CodingKeys.self)
    id = try c.decodeIfPresent(String.self, forKey: .id) ?? id
    name = try c.decodeIfPresent(String.self, forKey: .name) ?? name
    sprintMinutes = try c.decodeIfPresent(Int.self, forKey: .sprintMinutes) ?? sprintMinutes
    shield = (try? c.decodeIfPresent(ShieldLevel.self, forKey: .shield)) ?? shield
    cycleSprints = try c.decodeIfPresent(Int.self, forKey: .cycleSprints) ?? cycleSprints
    breakMinutes = try c.decodeIfPresent(Int.self, forKey: .breakMinutes) ?? breakMinutes
    profileId = try c.decodeIfPresent(String.self, forKey: .profileId) ?? profileId
    builtInKey = try c.decodeIfPresent(String.self, forKey: .builtInKey) ?? builtInKey
  }
}
