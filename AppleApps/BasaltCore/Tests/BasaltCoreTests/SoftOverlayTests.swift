import Foundation

import Testing

@testable import BasaltCore

struct SoftOverlayTests {
  @Test func repeatedSweepsShowOnce() {
    var p = SoftOverlayPolicy()
    let observed1 = p.shouldShow("Discord", now: instant())
    #expect(observed1)
    let observed2 = !p.shouldShow("discord", now: instant().addingTimeInterval(60))
    #expect(observed2)
    #expect(p.tries == 1)
    let observed3 = p.leftTheForeground()
    #expect(observed3)
    let observed4 = !p.leftTheForeground()
    #expect(observed4)
    let observed5 = p.shouldShow("Discord", now: instant().addingTimeInterval(61))
    #expect(observed5)
  }
  @Test func switchingAppsCountsSprintWideTries() {
    var p = SoftOverlayPolicy()
    for a in ["A", "B", "A"] {
      let observed6 = p.shouldShow(a, now: instant())
      #expect(observed6)
    }
    #expect(p.tries == 3)
    #expect(p.turnedBack == 0)
  }
  @Test func allowancePerAppExpiresExactly() {
    var p = SoftOverlayPolicy()
    p.allowFiveMinutes("A", now: instant())
    #expect(p.isQuiet("a", now: instant().addingTimeInterval(299.99)))
    #expect(!p.isQuiet("B", now: instant()))
    #expect(!p.isQuiet("A", now: instant().addingTimeInterval(300)))
    #expect(p.turnedBack == 0)
  }
  @Test func allowancePollingRequiresLeavingAgain() {
    var p = SoftOverlayPolicy()
    _ = p.shouldShow("A", now: instant())
    p.allowFiveMinutes("A", now: instant())
    let observed7 = !p.shouldShow("A", now: instant().addingTimeInterval(1))
    #expect(observed7)
    let observed8 = !p.shouldShow("A", now: instant().addingTimeInterval(300))
    #expect(observed8)
    p.leftTheForeground()
    let observed9 = p.shouldShow("A", now: instant().addingTimeInterval(301))
    #expect(observed9)
  }
  @Test func backToWorkIsFiveQuietSeconds() {
    var p = SoftOverlayPolicy()
    _ = p.shouldShow("A", now: instant())
    p.backToWork("A", now: instant())
    #expect(p.turnedBack == 1)
    let observed10 = !p.leftTheForeground()
    #expect(observed10)
    #expect(p.isQuiet("a", now: instant().addingTimeInterval(4.99)))
    let observed11 = p.shouldShow("A", now: instant().addingTimeInterval(5))
    #expect(observed11)
  }
  @Test func closeDoesNotCoverSaveDialog() {
    var p = SoftOverlayPolicy()
    _ = p.shouldShow("A", now: instant())
    p.closeIt("A", now: instant())
    #expect(p.turnedBack == 1)
    let observed12 = !p.shouldShow("A", now: instant().addingTimeInterval(60))
    #expect(observed12)
    p.leftTheForeground()
    let observed13 = p.shouldShow("A", now: instant().addingTimeInterval(61))
    #expect(observed13)
  }
  @Test func resetForgetsEverything() {
    var p = SoftOverlayPolicy()
    _ = p.shouldShow("A", now: instant())
    p.backToWork("A", now: instant())
    p.allowFiveMinutes("B", now: instant())
    p.reset()
    #expect(p.tries == 0)
    #expect(p.turnedBack == 0)
    #expect(!p.isQuiet("A", now: instant()))
    #expect(!p.isQuiet("B", now: instant()))
    let observed14 = p.shouldShow("B", now: instant())
    #expect(observed14)
  }
  @Test func sentenceRotatesFourWays() {
    #expect(
      SoftOverlayCopy.sentence("A", until: "5:45 PM") == "A is on your blocklist until 5:45 PM")
    #expect(
      SoftOverlayCopy.sentence("A", until: "5:45 PM", tryNumber: 2)
        == "You set this time aside until 5:45 PM")
    #expect(
      SoftOverlayCopy.sentence("A", until: "5:45 PM", tryNumber: 3) == "A can wait until 5:45 PM")
    #expect(
      SoftOverlayCopy.sentence("A", until: "5:45 PM", tryNumber: 4)
        == "A will still be there after 5:45 PM")
    #expect(
      SoftOverlayCopy.sentence("A", until: "x", tryNumber: 5)
        == SoftOverlayCopy.sentence("A", until: "x"))
  }
  @Test func intentionCopy() {
    #expect(SoftOverlayCopy.intention(" \n") == "")
    #expect(SoftOverlayCopy.intention(" read ") == "You planned: read")
  }
  @Test func allowCountdownCeils() {
    #expect(SoftOverlayCopy.allowLabel(7.1) == "Allow 5 minutes · 0:08")
    #expect(SoftOverlayCopy.allowLabel(0) == "Allow 5 minutes")
    #expect(SoftOverlayCopy.allowLabel(61) == "Allow 5 minutes · 1:01")
  }
  @Test func timeLeftCopy() {
    #expect(SoftOverlayCopy.timeLeft(0) == "This sprint is ending")
    #expect(SoftOverlayCopy.timeLeft(1) == "1 minute left in this sprint")
    #expect(SoftOverlayCopy.timeLeft(61) == "2 minutes left in this sprint")
  }
  @Test func honestCloseCopy() {
    #expect(SoftOverlayCopy.closeNote == "Nothing is closed unless you choose to.")
    #expect(
      SoftOverlayCopy.allowed("A") == "A allowed for 5 minutes. It still counted as a distraction.")
  }
}
