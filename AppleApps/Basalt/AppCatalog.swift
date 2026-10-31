import AppKit
import BasaltCore

struct AppPickerEntry: Identifiable {
  enum Source: Int { case suggested, installed, running }
  var id: String { bundleIdentifier.isEmpty ? executableName.lowercased() : bundleIdentifier.lowercased() }
  var name: String
  var bundleIdentifier: String
  var executableName: String
  var url: URL?
  var icon: NSImage?
  var source: Source
  var group = ""
  var note = ""
  var isAutomaticSuggestion: Bool { source == .suggested && group != "Browsers" }
  var blockedApp: BlockedApp {
    var a = BlockedApp(); a.name = name; a.bundleIdentifier = bundleIdentifier
    a.processName = executableName; a.iconPath = url?.path; return a
  }
}

@MainActor
enum AppCatalog {
  private static let suggestions: [String: (String, String)] = [
    "com.hnc.discord": ("Discord", "Chat"), "com.tinyspeck.slackmacgap": ("Slack", "Chat"),
    "net.whatsapp.whatsapp": ("WhatsApp", "Chat"), "ru.keepcoder.telegram": ("Telegram", "Chat"),
    "org.telegram.desktop": ("Telegram", "Chat"),
    "com.valvesoftware.steam": ("Steam", "Games & launchers"),
    "com.epicgames.epicgameslauncher": ("Epic Games Launcher", "Games & launchers"),
    "net.battle.battle.net": ("Battle.net", "Games & launchers"),
    "com.riotgames.riotclient": ("Riot Client", "Games & launchers"),
    "com.riotgames.leagueoflegends": ("League of Legends", "Games & launchers"),
    "com.mojang.minecraftlauncher": ("Minecraft Launcher", "Games & launchers"),
    "com.roblox.robloxplayer": ("Roblox", "Games & launchers"),
    "com.epicgames.fortnite": ("Fortnite", "Games & launchers"),
    "com.ea.mac.eadesktop": ("EA app", "Games & launchers"),
    "com.spotify.client": ("Spotify", "Video & music"),
    "com.google.chrome": ("Google Chrome", "Browsers"), "com.microsoft.edgemac": ("Microsoft Edge", "Browsers"),
    "org.mozilla.firefox": ("Firefox", "Browsers"), "com.operasoftware.operagx": ("Opera GX", "Browsers"),
    "com.brave.browser": ("Brave", "Browsers"),
  ]
  static func discover() -> [AppPickerEntry] {
    let fm = FileManager.default
    var urls: [URL] = []
    for root in [URL(fileURLWithPath: "/Applications"), fm.homeDirectoryForCurrentUser.appendingPathComponent("Applications"), URL(fileURLWithPath: "/System/Applications")] {
      for child in (try? fm.contentsOfDirectory(at: root, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles])) ?? [] {
        if child.pathExtension.lowercased() == "app" { urls.append(child) }
        else if (try? child.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true {
          urls += ((try? fm.contentsOfDirectory(at: child, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])) ?? []).filter { $0.pathExtension.lowercased() == "app" }
        }
      }
    }
    var result: [String: AppPickerEntry] = [:]
    for url in urls {
      guard let bundle = Bundle(url: url), let id = bundle.bundleIdentifier else { continue }
      let exe = bundle.executableURL?.lastPathComponent ?? url.deletingPathExtension().lastPathComponent
      let identity = RunningAppIdentity(bundleIdentifier: id, executableName: exe, isRegular: true)
      guard !MacBlockerPolicy.isProtected(identity) else { continue }
      let name = bundle.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String
        ?? bundle.object(forInfoDictionaryKey: "CFBundleName") as? String ?? url.deletingPathExtension().lastPathComponent
      let entry = decorate(AppPickerEntry(name: name, bundleIdentifier: id, executableName: exe, url: url, icon: NSWorkspace.shared.icon(forFile: url.path), source: .installed))
      result[entry.id] = entry
    }
    for app in NSWorkspace.shared.runningApplications where app.activationPolicy == .regular {
      guard !MacBlockerPolicy.isProtected(BlockerService.identity(app)) else { continue }
      let entry = decorate(AppPickerEntry(name: app.localizedName ?? "App", bundleIdentifier: app.bundleIdentifier ?? "",
        executableName: app.executableURL?.lastPathComponent ?? "", url: app.bundleURL, icon: app.icon, source: .running))
      if result[entry.id] == nil { result[entry.id] = entry }
    }
    return result.values.sorted { $0.source.rawValue == $1.source.rawValue ? $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending : $0.source.rawValue < $1.source.rawValue }
  }
  private static func decorate(_ entry: AppPickerEntry) -> AppPickerEntry {
    var entry = entry
    if let (name, group) = suggestions[entry.bundleIdentifier.lowercased()] {
      entry.name = name; entry.group = group; entry.source = .suggested
      if group == "Browsers" { entry.note = "Closes the whole browser, every tab and window." }
    }
    return entry
  }
}
