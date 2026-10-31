import Testing
import BasaltCore

@Test func appLinksCoreWithWindowsDefaults() {
    #expect(AppSettings().defaultSprintMinutes == 25)
    #expect(AppSettings().defaultShield == .firm)
}
