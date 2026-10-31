import Foundation

enum PrivateFile {
  static func write(_ data: Data, to url: URL) throws {
    let fm = FileManager.default
    let directory = url.deletingLastPathComponent()
    try fm.createDirectory(
      at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    let temporary = directory.appendingPathComponent(".\(UUID().uuidString).tmp")
    defer { try? fm.removeItem(at: temporary) }
    guard
      fm.createFile(atPath: temporary.path, contents: nil, attributes: [.posixPermissions: 0o600])
    else { throw CocoaError(.fileWriteUnknown) }
    try data.write(to: temporary)
    if fm.fileExists(atPath: url.path) {
      _ = try fm.replaceItemAt(url, withItemAt: temporary)
    } else {
      try fm.moveItem(at: temporary, to: url)
    }
    try fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
  }
}
public enum SettingsCoding {
  public static func encoder() -> JSONEncoder {
    let e = JSONEncoder()
    e.outputFormatting = [.prettyPrinted, .sortedKeys]
    e.dateEncodingStrategy = .custom { date, encoder in
      let f = ISO8601DateFormatter()
      f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
      var c = encoder.singleValueContainer()
      try c.encode(f.string(from: date))
    }
    return e
  }
  public static func decoder() -> JSONDecoder {
    let d = JSONDecoder()
    d.dateDecodingStrategy = .custom { decoder in
      let text = try decoder.singleValueContainer().decode(String.self)
      let f = ISO8601DateFormatter()
      f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
      if let date = f.date(from: text) ?? ISO8601DateFormatter().date(from: text) { return date }
      throw DecodingError.dataCorrupted(
        .init(codingPath: decoder.codingPath, debugDescription: "Invalid UTC date"))
    }
    return d
  }
}
public enum SettingsStoreError: Error { case unsupportedSchema(Int) }
/// Serializes file access. App state stays with the app's main-actor owner.
public actor SettingsStore {
  public let url: URL
  public init(url: URL) { self.url = url }
  public func save(_ settings: AppSettings) throws {
    guard settings.schemaVersion == AppSettings.currentSchemaVersion else {
      throw SettingsStoreError.unsupportedSchema(settings.schemaVersion)
    }
    try PrivateFile.write(SettingsCoding.encoder().encode(settings), to: url)
  }
  public func load() throws -> AppSettings {
    guard FileManager.default.fileExists(atPath: url.path) else { return AppSettings() }
    do {
      var s = try SettingsCoding.decoder().decode(AppSettings.self, from: Data(contentsOf: url))
      guard s.schemaVersion == AppSettings.currentSchemaVersion else {
        throw SettingsStoreError.unsupportedSchema(s.schemaVersion)
      }
      s.ensureProfiles()
      s.ensureTemplates()
      return s
    } catch let error as SettingsStoreError { throw error } catch {
      let quarantine = url.deletingLastPathComponent().appendingPathComponent(
        "settings.corrupt-\(UUID().uuidString).json")
      try FileManager.default.moveItem(at: url, to: quarantine)
      return AppSettings()
    }
  }
  public func reset() throws {
    if FileManager.default.fileExists(atPath: url.path) {
      try FileManager.default.removeItem(at: url)
    }
  }
}
public enum DataPrivacy {
  public static func export(_ s: AppSettings, now: Date) throws -> Data {
    // Explicit allowlist: adding a credential to settings cannot silently add it to exports.
    let e = SettingsCoding.encoder()
    func json<T: Encodable>(_ value: T) throws -> Any {
      try JSONSerialization.jsonObject(with: e.encode(value), options: [.fragmentsAllowed])
    }
    let payload: [String: Any] = [
      "exportedUtc": try json(now), "blockedApps": try json(s.blockedApps),
      "blocklistProfiles": try json(s.profiles), "activeProfileId": s.activeProfileId,
      "studyTemplates": try json(s.templates), "sprintSchedules": try json(s.schedules),
      "sleepBlocking": [
        "enabled": s.isSleepBlockEnabled, "start": s.sleepBlockStartMinute,
        "end": s.sleepBlockEndMinute,
      ],
      "sessions": try json(s.sessions), "activeSprint": try json(s.activeSprint),
      "momentumScore": s.momentumScore, "currentStreak": s.currentStreak,
      "earnedMilestones": try json(s.earnedMilestones),
      "dailyGoal": [
        "kind": s.dailyGoalKind == .minutes
          ? "Minutes" : s.dailyGoalKind == .sprints ? "Sprints" : "None",
        "target": s.dailyGoalTarget,
      ],
      "licence": ["email": s.licenseEmail, "status": s.licenseStatus, "isPro": s.isPro],
    ]
    return try JSONSerialization.data(
      withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
  }
}
