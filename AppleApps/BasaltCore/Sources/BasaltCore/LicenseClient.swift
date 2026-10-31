import Foundation

public struct HTTPResponse: Sendable {
  public var status: Int
  public var body: Data
  public init(status: Int, body: Data) {
    self.status = status
    self.body = body
  }
}
public protocol HTTPTransport: Sendable {
  func post(url: URL, json: Data, timeout: TimeInterval) async throws -> HTTPResponse
}
public struct URLSessionTransport: HTTPTransport {
  public init() {}
  public func post(url: URL, json: Data, timeout: TimeInterval) async throws -> HTTPResponse {
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.httpBody = json
    request.timeoutInterval = timeout
    request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
    let config = URLSessionConfiguration.ephemeral
    config.timeoutIntervalForRequest = timeout
    config.timeoutIntervalForResource = timeout
    config.httpShouldSetCookies = false
    let session = URLSession(configuration: config)
    defer { session.invalidateAndCancel() }
    let (data, response) = try await session.data(for: request)
    return HTTPResponse(status: (response as? HTTPURLResponse)?.statusCode ?? 0, body: data)
  }
}
public enum LicenseWaitCopy {
  public static let contactingMessage = "Contacting the license server…"
  public static let wakingUpMessage = "The server is waking up. This can take up to a minute."
  public static let wakingUpAfterSeconds = 8.0
  public static let retryDelays: [TimeInterval] = [2, 5]
  public static let totalAttempts = 3
  public static let totalBudgetSeconds = 72.0
  public static func timeoutForAttempt(_ attempt: Int) -> TimeInterval { attempt <= 1 ? 35 : 15 }
  public static func messageFor(_ elapsed: TimeInterval) -> String {
    elapsed < 8 ? contactingMessage : wakingUpMessage
  }
}
public struct LicenseResult: Sendable, Equatable {
  public var ok: Bool = false
  public var isPro: Bool = false
  public var status: String = "error"
  public var message: String = ""
  public var email: String? = nil
  public var licenseKey: String? = nil
  public var definitive: Bool = true
  public var deviceCount: Int = 0
  public var deviceLimit: Int = 0
  public static func failure(_ message: String) -> Self {
    Self(message: message, definitive: false)
  }
  /// Apply on the caller's settings owner after await, never replace a stale settings snapshot.
  public func applyActivation(to s: inout AppSettings, now: Date) {
    if isPro {
      s.isPro = true
      s.licenseKey = licenseKey ?? ""
      s.licenseEmail = email ?? ""
      s.licenseStatus = status
      s.licenseCheckedUtc = now
      s.deviceCount = deviceCount
      s.deviceLimit = deviceLimit
    } else if status == "device_limit_reached" {
      s.deviceCount = deviceCount
      s.deviceLimit = deviceLimit
    }
  }
  public func applyRefresh(to s: inout AppSettings, now: Date) {
    applyActivation(to: &s, now: now)
    if definitive && !isPro && s.isPro {
      s.isPro = false
      s.licenseStatus = status
    }
  }
}
public struct DeviceInfo: Sendable, Equatable {
  public let name: String
  public let deviceToken: String
  public let isCurrent: Bool
  public let lastSeenUtc: Date?
}
public struct DeviceListResult: Sendable {
  public let ok: Bool
  public let devices: [DeviceInfo]
  public let deviceCount: Int
  public let deviceLimit: Int
  public let message: String?
}
private struct ValidateResponse: Decodable {
  var isPro: Bool?
  var status: String?
  var reason: String?
  var message: String?
  var email: String?
  var licenseKey: String?
  var deviceCount: Int?
  var deviceLimit: Int?
}
private struct DeviceRow: Decodable {
  var name: String?
  var deviceToken: String?
  var isCurrent: Bool?
  var lastSeen: Double?
}
private struct DevicesResponse: Decodable {
  var ok: Bool?
  var devices: [DeviceRow]?
  var deviceCount: Int?
  var deviceLimit: Int?
  var message: String?
}

public struct LicenseClient: Sendable {
  private let transport: any HTTPTransport
  private let sleep: @Sendable (TimeInterval) async throws -> Void
  public let deviceId: String
  public let deviceName: String
  public init(
    transport: any HTTPTransport = URLSessionTransport(), deviceId: String, deviceName: String,
    sleep: @escaping @Sendable (TimeInterval) async throws -> Void = {
      try await Task.sleep(for: .seconds($0))
    }
  ) {
    self.transport = transport
    self.deviceId = deviceId
    self.deviceName = deviceName
    self.sleep = sleep
  }
  private func post(
    _ path: String, server: String, fields: [String: String], timeout: TimeInterval = 35
  ) async throws -> HTTPResponse {
    guard
      let url = URL(string: server.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + path)
    else { throw URLError(.badURL) }
    return try await transport.post(url: url, json: JSONEncoder().encode(fields), timeout: timeout)
  }
  public func validate(
    key: String, email: String, server: String, progress: (@Sendable (String) -> Void)? = nil
  ) async -> LicenseResult {
    let key = trimmed(key)
    let email = trimmed(email)
    guard !key.isEmpty || !email.isEmpty else {
      return .failure("Enter your license key (or the email you used at checkout).")
    }
    let start = ContinuousClock.now
    // Independent of attempts: the waking-up line arrives at eight seconds even during a 35-second request.
    let reporter = Task {
      do {
        try await Task.sleep(for: .seconds(8))
        try Task.checkCancellation()
        progress?(LicenseWaitCopy.wakingUpMessage)
      } catch {}
    }
    defer { reporter.cancel() }
    var response: HTTPResponse?
    for attempt in 1...3 {
      let elapsed = start.duration(to: .now).components
      progress?(LicenseWaitCopy.messageFor(Double(elapsed.seconds)))
      do {
        let r = try await post(
          "/validate", server: server,
          fields: [
            "licenseKey": key, "email": email, "deviceId": deviceId, "deviceName": deviceName,
          ], timeout: LicenseWaitCopy.timeoutForAttempt(attempt))
        if r.status < 500 {
          response = r
          break
        }
      } catch {}
      if attempt < 3 {
        do { try await sleep(LicenseWaitCopy.retryDelays[attempt - 1]) } catch { break }
      }
    }
    guard let response else {
      return .failure(
        "Couldn't reach the license server at \(server). It may still be waking up — check it's running, then try again."
      )
    }
    guard let body = try? JSONDecoder().decode(ValidateResponse.self, from: response.body) else {
      return .failure("The license server returned an unreadable response.")
    }
    if body.isPro == true {
      return LicenseResult(
        ok: true, isPro: true, status: body.status ?? "active",
        message: "Basalt activated. Every feature is yours to keep.", email: body.email ?? email,
        licenseKey: body.licenseKey ?? key, deviceCount: body.deviceCount ?? 0,
        deviceLimit: body.deviceLimit ?? 0)
    }
    let reason = body.reason ?? "invalid"
    return LicenseResult(
      status: reason, message: body.message ?? Self.rejectionMessage(reason),
      deviceCount: body.deviceCount ?? 0, deviceLimit: body.deviceLimit ?? 0)
  }
  public static func rejectionMessage(_ reason: String) -> String {
    switch reason {
    case "malformed_key": "That key isn't in the FS-XXXX-XXXX-XXXX-XXXX format."
    case "not_found": "We couldn't find a purchase for those details."
    case "device_limit_reached": "This license is already active on the maximum number of devices."
    case "license_refunded": "That purchase was refunded, so the license is no longer active."
    case "license_pending": "That purchase hasn't been paid yet."
    default:
      reason.hasPrefix("license_")
        ? "That license is \(reason.dropFirst(8))."
        : reason.hasPrefix("subscription_")
          ? "That subscription is \(reason.dropFirst(13))." : "That license could not be validated."
    }
  }
  public func refresh(_ s: AppSettings) async -> LicenseResult? {
    guard !trimmed(s.licenseKey).isEmpty || !trimmed(s.licenseEmail).isEmpty else { return nil }
    return await validate(key: s.licenseKey, email: s.licenseEmail, server: s.licenseServerUrl)
  }
  public func listDevices(key: String, server: String) async -> DeviceListResult {
    func failure(_ message: String) -> DeviceListResult {
      DeviceListResult(ok: false, devices: [], deviceCount: 0, deviceLimit: 0, message: message)
    }
    guard !trimmed(key).isEmpty else { return failure("No license key to look up.") }
    do {
      let r = try await post(
        "/devices", server: server, fields: ["licenseKey": key, "deviceId": deviceId])
      let b = try JSONDecoder().decode(DevicesResponse.self, from: r.body)
      guard b.ok == true else { return failure(b.message ?? "Couldn't load your devices.") }
      let rows = (b.devices ?? []).map {
        DeviceInfo(
          name: trimmed($0.name ?? "").isEmpty ? "Unnamed device" : $0.name!,
          deviceToken: $0.deviceToken ?? "", isCurrent: $0.isCurrent ?? false,
          lastSeenUtc: $0.lastSeen.map { Date(timeIntervalSince1970: $0) })
      }
      return DeviceListResult(
        ok: true, devices: rows, deviceCount: b.deviceCount ?? 0, deviceLimit: b.deviceLimit ?? 0,
        message: nil)
    } catch { return failure("Couldn't reach the license server.") }
  }
  public func releaseDevice(key: String, token: String, server: String) async -> Bool {
    guard !trimmed(key).isEmpty, !trimmed(token).isEmpty else { return false }
    do {
      let r = try await post(
        "/devices", server: server,
        fields: ["licenseKey": key, "action": "release", "releaseToken": token])
      return (200..<300).contains(r.status)
    } catch { return false }
  }
  public func deactivate(key: String, server: String) async {
    if !trimmed(key).isEmpty {
      _ = try? await post(
        "/devices", server: server,
        fields: ["licenseKey": key, "action": "release", "deviceId": deviceId])
    }
  }
  public static func clearLocalLicense(_ s: inout AppSettings) {
    s.isPro = false
    s.licenseKey = ""
    s.licenseEmail = ""
    s.licenseStatus = ""
    s.licenseCheckedUtc = nil
    s.deviceCount = 0
    s.deviceLimit = 0
  }
}
