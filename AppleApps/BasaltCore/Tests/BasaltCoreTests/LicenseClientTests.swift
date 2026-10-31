import Foundation

import Testing

@testable import BasaltCore

actor FakeTransport: HTTPTransport {
  struct Request: Sendable {
    let url: URL
    let json: Data
    let timeout: TimeInterval
  }
  enum Failure: Error { case offline }
  var replies: [HTTPResponse]
  var requests: [Request] = []
  let delay: TimeInterval
  init(_ bodies: [(Int, String)] = [], delay: TimeInterval = 0) {
    replies = bodies.map { HTTPResponse(status: $0.0, body: Data($0.1.utf8)) }
    self.delay = delay
  }
  func post(url: URL, json: Data, timeout: TimeInterval) async throws -> HTTPResponse {
    requests.append(Request(url: url, json: json, timeout: timeout))
    if delay > 0 { try await Task.sleep(for: .seconds(delay)) }
    guard !replies.isEmpty else { throw Failure.offline }
    return replies.removeFirst()
  }
  func count() -> Int { requests.count }
  func fields(_ index: Int = 0) throws -> [String: String] {
    try JSONDecoder().decode([String: String].self, from: requests[index].json)
  }
  func timeouts() -> [TimeInterval] { requests.map(\.timeout) }
  func paths() -> [String] { requests.map(\.url.path) }
}
actor DelayRecorder {
  var values: [TimeInterval] = []
  func record(_ value: TimeInterval) { values.append(value) }
  func all() -> [TimeInterval] { values }
}
final class ProgressRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private var values: [String] = []
  func append(_ text: String) {
    lock.lock()
    defer { lock.unlock() }
    values.append(text)
  }
  func all() -> [String] {
    lock.lock()
    defer { lock.unlock() }
    return values
  }
}
struct LicenseClientTests {
  let server = "https://example.invalid/"
  func client(_ fake: FakeTransport, delays: DelayRecorder = DelayRecorder()) -> LicenseClient {
    LicenseClient(
      transport: fake, deviceId: "test-device-hash", deviceName: "Test Mac (test)",
      sleep: { await delays.record($0) })
  }
  @Test func emptyCredentialsDoNotCallNetwork() async {
    let f = FakeTransport()
    let r = await client(f).validate(key: " ", email: "", server: server)
    #expect(!r.definitive)
    #expect(await f.count() == 0)
  }
  @Test func validateSendsOnlyDisclosedFourFields() async throws {
    let f = FakeTransport([(200, "{\"isPro\":true}")])
    let r = await client(f).validate(
      key: " fixture ", email: " person@example.invalid ", server: server)
    #expect(r.isPro)
    #expect(
      try await f.fields() == [
        "licenseKey": "fixture", "email": "person@example.invalid", "deviceId": "test-device-hash",
        "deviceName": "Test Mac (test)",
      ])
    #expect(await f.paths() == ["/validate"])
  }
  @Test func retriesOnlyTransportWithExactBudget() async {
    let f = FakeTransport([(503, ""), (500, ""), (200, "{\"isPro\":true}")])
    let d = DelayRecorder()
    let r = await client(f, delays: d).validate(key: "fixture", email: "", server: server)
    #expect(r.isPro)
    #expect(await f.timeouts() == [35, 15, 15])
    #expect(await d.all() == [2, 5])
  }
  @Test func offlineNeverRevokesCache() async {
    let f = FakeTransport()
    let r = await client(f).validate(key: "fixture", email: "", server: server)
    var s = ready()
    s.licenseKey = "fixture"
    r.applyRefresh(to: &s, now: instant())
    #expect(!r.definitive)
    #expect(s.isPro)
    #expect(s.licenseKey == "fixture")
    #expect(await f.count() == 3)
  }
  @Test func rejectionIsNotRetried() async {
    let f = FakeTransport([(400, "{\"reason\":\"malformed_key\"}")])
    let r = await client(f).validate(key: "bad", email: "", server: server)
    #expect(r.definitive)
    #expect(r.status == "malformed_key")
    #expect(await f.count() == 1)
  }
  @Test func unreadableResponseNonDefinitiveNoRetry() async {
    let f = FakeTransport([(200, "not JSON")])
    let r = await client(f).validate(key: "fixture", email: "", server: server)
    #expect(!r.definitive)
    #expect(await f.count() == 1)
    #expect(r.message == "The license server returned an unreadable response.")
  }
  @Test func serverIsProWinsOverValidField() async {
    let f = FakeTransport([(200, "{\"valid\":false,\"isPro\":true}")])
    #expect(await client(f).validate(key: "fixture", email: "", server: server).isPro)
  }
  @Test func activationCachesOnlyLicenceFields() async {
    let f = FakeTransport([
      (
        200,
        "{\"isPro\":true,\"status\":\"active\",\"licenseKey\":\"fixture-returned\",\"email\":\"returned@example.invalid\",\"deviceCount\":2,\"deviceLimit\":3}"
      )
    ])
    let r = await client(f).validate(key: "fixture", email: "", server: server)
    var s = AppSettings()
    s.sessions = [session()]
    r.applyActivation(to: &s, now: instant())
    #expect(s.isPro)
    #expect(s.deviceCount == 2)
    #expect(s.deviceLimit == 3)
    #expect(s.licenseKey == "fixture-returned")
    #expect(s.sessions.count == 1)
    #expect(s.licenseCheckedUtc == instant())
  }
  @Test func emailOnlyDoesNotInventReturnedKey() async {
    let f = FakeTransport([(200, "{\"isPro\":true}")])
    let r = await client(f).validate(key: "", email: "person@example.invalid", server: server)
    #expect(r.licenseKey == "")
    #expect(r.email == "person@example.invalid")
  }
  @Test func anyDefinitiveRejectionRevokesOnRefresh() async {
    let f = FakeTransport([(200, "{\"reason\":\"subscription_new_status\"}")])
    let r = await client(f).validate(key: "fixture", email: "", server: server)
    var s = ready()
    r.applyRefresh(to: &s, now: instant())
    #expect(!s.isPro)
    #expect(s.licenseStatus == "subscription_new_status")
  }
  @Test func manualRejectionDoesNotDowngradeExistingCache() async {
    let f = FakeTransport([(200, "{\"reason\":\"not_found\"}")])
    let r = await client(f).validate(key: "fixture", email: "", server: server)
    var s = ready()
    r.applyActivation(to: &s, now: instant())
    #expect(s.isPro)
  }
  @Test func seatLimitUpdatesCountsOnly() async {
    let f = FakeTransport([
      (200, "{\"reason\":\"device_limit_reached\",\"deviceCount\":3,\"deviceLimit\":3}")
    ])
    let r = await client(f).validate(key: "fixture", email: "", server: server)
    var s = ready()
    s.licenseStatus = "cached"
    r.applyActivation(to: &s, now: instant())
    #expect(s.deviceCount == 3)
    #expect(s.isPro)
    #expect(s.licenseStatus == "cached")
  }
  @Test func customServerMessagePreserved() async {
    let f = FakeTransport([(400, "{\"reason\":\"not_found\",\"message\":\"Custom reply\"}")])
    #expect(
      await client(f).validate(key: "fixture", email: "", server: server).message == "Custom reply")
  }
  @Test func noCredentialsRefreshIsNoOp() async {
    let f = FakeTransport()
    #expect(await client(f).refresh(AppSettings()) == nil)
    #expect(await f.count() == 0)
  }
  @Test func listDevicesUsesOpaqueTokensAndEpochSeconds() async throws {
    let f = FakeTransport([
      (
        200,
        "{\"ok\":true,\"deviceCount\":1,\"deviceLimit\":3,\"devices\":[{\"name\":\" \",\"isCurrent\":true,\"deviceToken\":\"opaque\",\"lastSeen\":100}]}"
      )
    ])
    let r = await client(f).listDevices(key: "fixture", server: server)
    #expect(r.ok)
    #expect(r.devices[0].name == "Unnamed device")
    #expect(r.devices[0].deviceToken == "opaque")
    #expect(r.devices[0].lastSeenUtc == Date(timeIntervalSince1970: 100))
    #expect(try await f.fields() == ["licenseKey": "fixture", "deviceId": "test-device-hash"])
  }
  @Test func listWithoutKeyDoesNotCall() async {
    let f = FakeTransport()
    #expect(!(await client(f).listDevices(key: "", server: server)).ok)
    #expect(await f.count() == 0)
  }
  @Test func listOfflineFailsHonestly() async {
    let f = FakeTransport()
    let r = await client(f).listDevices(key: "fixture", server: server)
    #expect(!r.ok)
    #expect(r.message == "Couldn't reach the license server.")
    #expect(await f.count() == 1)
  }
  @Test func releaseOtherUsesTokenNotDeviceId() async throws {
    let f = FakeTransport([(200, "{}")])
    #expect(await client(f).releaseDevice(key: "fixture", token: "opaque", server: server))
    #expect(
      try await f.fields() == [
        "licenseKey": "fixture", "action": "release", "releaseToken": "opaque",
      ])
  }
  @Test func emptyReleaseDoesNotCall() async {
    let f = FakeTransport()
    #expect(!(await client(f).releaseDevice(key: "fixture", token: "", server: server)))
    #expect(await f.count() == 0)
  }
  @Test func failedReleaseReturnsFalse() async {
    let f = FakeTransport([(403, "{}")])
    #expect(!(await client(f).releaseDevice(key: "fixture", token: "opaque", server: server)))
  }
  @Test func deactivateReleasesOwnSeat() async throws {
    let f = FakeTransport([(200, "{}")])
    await client(f).deactivate(key: "fixture", server: server)
    #expect(
      try await f.fields() == [
        "licenseKey": "fixture", "action": "release", "deviceId": "test-device-hash",
      ])
  }
  @Test func deactivationClearsLocallyEvenOffline() async {
    let f = FakeTransport()
    await client(f).deactivate(key: "fixture", server: server)
    var s = ready()
    s.licenseKey = "fixture"
    s.licenseEmail = "test@example.invalid"
    s.deviceCount = 3
    LicenseClient.clearLocalLicense(&s)
    #expect(!s.isPro)
    #expect(s.licenseKey.isEmpty)
    #expect(s.licenseEmail.isEmpty)
    #expect(s.deviceCount == 0)
    #expect(s.licenseCheckedUtc == nil)
  }
  @Test func progressStartsContacting() async {
    let f = FakeTransport([(200, "{\"isPro\":true}")])
    let p = ProgressRecorder()
    _ = await client(f).validate(
      key: "fixture", email: "", server: server, progress: { p.append($0) })
    #expect(p.all() == [LicenseWaitCopy.contactingMessage])
  }
  @Test func progressChangesWhileFirstRequestStillRunning() async {
    let f = FakeTransport([(200, "{\"isPro\":true}")], delay: 8.2)
    let p = ProgressRecorder()
    _ = await client(f).validate(
      key: "fixture", email: "", server: server, progress: { p.append($0) })
    #expect(p.all() == [LicenseWaitCopy.contactingMessage, LicenseWaitCopy.wakingUpMessage])
  }
  @Test func waitCopyBoundaryAndBudget() {
    #expect(LicenseWaitCopy.messageFor(7.999) == "Contacting the license server…")
    #expect(
      LicenseWaitCopy.messageFor(8) == "The server is waking up. This can take up to a minute.")
    #expect(LicenseWaitCopy.totalBudgetSeconds == 35 + 2 + 15 + 5 + 15)
  }
}
