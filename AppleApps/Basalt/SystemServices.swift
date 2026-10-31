import AppKit
import Carbon
import CryptoKit
import IOKit
import ServiceManagement
import UserNotifications
import BasaltCore

enum MacDeviceIdentity {
  static func values() -> (id: String, name: String) {
    let service = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("IOPlatformExpertDevice"))
    var uuid = ""
    if service != 0 {
      uuid = IORegistryEntryCreateCFProperty(service, "IOPlatformUUID" as CFString, kCFAllocatorDefault, 0)?.takeRetainedValue() as? String ?? ""
      IOObjectRelease(service)
    }
    let computer = Host.current().localizedName ?? ProcessInfo.processInfo.hostName
    let user = NSUserName()
    let seed = "Basalt.mac.device.v1|\(uuid)|\(computer)|\(user)"
    let id = SHA256.hash(data: Data(seed.utf8)).prefix(16).map { String(format: "%02x", $0) }.joined()
    return (id, computer.isEmpty ? "Mac" : "\(computer) (\(user))")
  }
}

@MainActor
final class MacNotifications: NSObject, UNUserNotificationCenterDelegate {
  enum Destination: String { case app, journal, license, today }
  var onOpen: ((Destination) -> Void)?
  private let center = UNUserNotificationCenter.current()
  override init() {
    super.init()
    center.delegate = self
    center.setNotificationCategories(Set(NotificationKind.allCases.map {
      UNNotificationCategory(identifier: $0.rawValue, actions: [], intentIdentifiers: [])
    }))
  }
  func requestAuthorization() async -> Bool {
    (try? await center.requestAuthorization(options: [.alert, .sound])) ?? false
  }
  @discardableResult func send(_ kind: NotificationKind, title: String, body: String,
    settings: AppSettings, destination: Destination = .app) -> Bool {
    guard NotificationPolicy.shouldShow(kind, settings, sprintRunning: settings.activeSprint != nil) else { return false }
    let content = UNMutableNotificationContent()
    content.title = title; content.body = body
    content.categoryIdentifier = kind.rawValue
    content.userInfo = ["destination": destination.rawValue]
    content.sound = .default
    center.add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
    return true
  }
  nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter,
    willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
    completionHandler([.banner, .sound])
  }
  nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter,
    didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
    let raw = response.notification.request.content.userInfo["destination"] as? String ?? "app"
    Task { @MainActor [weak self] in self?.onOpen?(Destination(rawValue: raw) ?? .app) }
    completionHandler()
  }
}

@MainActor
final class LoginItemService {
  var status: SMAppService.Status { SMAppService.mainApp.status }
  func setEnabled(_ enabled: Bool) throws {
    if enabled { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
  }
  func openApprovalSettings() { SMAppService.openSystemSettingsLoginItems() }
  static var launchedAtLogin: Bool {
    guard let event = NSAppleEventManager.shared().currentAppleEvent else { return false }
    return event.eventID == kAEOpenApplication
      && event.paramDescriptor(forKeyword: keyAEPropData)?.enumCodeValue == keyAELaunchedAsLogInItem
  }
}

@MainActor
final class GlobalHotkey {
  private var reference: EventHotKeyRef?
  private var handler: EventHandlerRef?
  var onPress: (() -> Void)?
  func register() -> Bool {
    unregister()
    var type = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
    let result = InstallEventHandler(GetApplicationEventTarget(), { _, _, context in
      guard let context else { return OSStatus(eventNotHandledErr) }
      let owner = Unmanaged<GlobalHotkey>.fromOpaque(context).takeUnretainedValue()
      Task { @MainActor in owner.onPress?() }
      return noErr
    }, 1, &type, Unmanaged.passUnretained(self).toOpaque(), &handler)
    guard result == noErr else { return false }
    let id = EventHotKeyID(signature: 0x42534C54, id: 1)
    let status = RegisterEventHotKey(UInt32(kVK_ANSI_F), UInt32(controlKey | optionKey), id, GetApplicationEventTarget(), 0, &reference)
    if status != noErr { unregister(); return false }
    return true
  }
  func unregister() {
    if let reference { UnregisterEventHotKey(reference) }
    if let handler { RemoveEventHandler(handler) }
    reference = nil; handler = nil
  }
}
