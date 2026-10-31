import Foundation

public struct BlockedApp: Codable, Equatable, Sendable {
  public var name: String = ""
  public var processName: String = ""
  public var bundleIdentifier: String = ""
  public var extraProcessNames: [String] = []
  public var iconPath: String? = nil
  public var isEnabled: Bool = true
  public var blockCount: Int = 0
  public var addedUtc: Date = Date()
  public init() {}
  public var displayName: String { trimmed(name).isEmpty ? processName : name }
  public var allProcessNames: [String] {
    var seen: Set<String> = []
    return ([processName] + extraProcessNames).map(trimmed).filter {
      !$0.isEmpty && seen.insert($0.lowercased()).inserted
    }
  }
  public func copy() -> Self {
    var a = self
    a.blockCount = 0
    return a
  }
}
public struct BlocklistProfile: Codable, Equatable, Sendable {
  public var id: String = newID()
  public var name: String = "Default"
  public var apps: [BlockedApp] = []
  public var sites: [String] = []
  public init() {}
  public func copy(name: String) -> Self {
    var p = self
    p.id = newID()
    p.name = name
    p.apps = apps.map { $0.copy() }
    return p
  }
}

extension BlockedApp {
  private enum CodingKeys: String, CodingKey {
    case name, processName, bundleIdentifier, extraProcessNames, iconPath, isEnabled, blockCount,
      addedUtc
  }
  public init(from decoder: any Decoder) throws {
    self.init()
    let c = try decoder.container(keyedBy: CodingKeys.self)
    name = try c.decodeIfPresent(String.self, forKey: .name) ?? name
    processName = try c.decodeIfPresent(String.self, forKey: .processName) ?? processName
    bundleIdentifier =
      try c.decodeIfPresent(String.self, forKey: .bundleIdentifier) ?? bundleIdentifier
    extraProcessNames =
      try c.decodeIfPresent([String].self, forKey: .extraProcessNames) ?? extraProcessNames
    iconPath = try c.decodeIfPresent(String.self, forKey: .iconPath) ?? iconPath
    isEnabled = try c.decodeIfPresent(Bool.self, forKey: .isEnabled) ?? isEnabled
    blockCount = try c.decodeIfPresent(Int.self, forKey: .blockCount) ?? blockCount
    addedUtc = try c.decodeIfPresent(Date.self, forKey: .addedUtc) ?? addedUtc
  }
}

extension BlocklistProfile {
  private enum CodingKeys: String, CodingKey { case id, name, apps, sites }
  public init(from decoder: any Decoder) throws {
    self.init()
    let c = try decoder.container(keyedBy: CodingKeys.self)
    id = try c.decodeIfPresent(String.self, forKey: .id) ?? id
    name = try c.decodeIfPresent(String.self, forKey: .name) ?? name
    apps = try c.decodeIfPresent([BlockedApp].self, forKey: .apps) ?? apps
    sites = try c.decodeIfPresent([String].self, forKey: .sites) ?? sites
  }
}
