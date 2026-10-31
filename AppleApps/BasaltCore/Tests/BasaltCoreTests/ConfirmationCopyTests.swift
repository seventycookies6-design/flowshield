import Foundation

import Testing

@testable import BasaltCore

struct ConfirmationCopyTests {
  @Test func firmDeadlineCannotBeRestartedAndKeepGoingClearsIt() {
    var p = EndConfirmation()
    let now = instant()
    let observed1 = p.request(shield: .firm, elapsed: 120, now: now) == .confirm
    #expect(observed1)
    let observed2 = !p.endAnyway(now: now.addingTimeInterval(4.9))
    #expect(observed2)
    _ = p.request(shield: .firm, elapsed: 122, now: now.addingTimeInterval(2))
    #expect(p.unlocksAt == now.addingTimeInterval(5))
    #expect(p.countdownText(now: now.addingTimeInterval(4.1)) == "You can end it in 1 s.")
    #expect(
      p.text(remaining: 60, momentum: 100, shield: .firm)
        == "1 minute left. Ending now counts as ended early: momentum 100 → 83.")
    let observed3 = p.endAnyway(now: now.addingTimeInterval(5))
    #expect(observed3)
    #expect(!p.canEndAnyway(now: now.addingTimeInterval(6)))
  }
  @Test func sealedWaitThenPhraseBothRechecked() {
    var p = EndConfirmation()
    let now = instant()
    _ = p.request(shield: .sealed, elapsed: 120, now: now)
    p.phrase = "end my sprint"
    let observed4 = !p.endAnyway(now: now.addingTimeInterval(29))
    #expect(observed4)
    p.phrase = "wrong"
    let observed5 = !p.endAnyway(now: now.addingTimeInterval(30))
    #expect(observed5)
    #expect(p.countdownText(now: now.addingTimeInterval(30)) == "Type the phrase to confirm.")
    #expect(p.title == "This sprint is sealed")
    #expect(
      p.text(remaining: 120, momentum: 100, shield: .sealed).hasSuffix("type \"end my sprint\"."))
    p.phrase = " END  my sprint "
    let observed6 = p.endAnyway(now: now.addingTimeInterval(30))
    #expect(observed6)
  }
  @Test func keepGoingDoesNotLeaveConfirmationEnabled() {
    var p = EndConfirmation()
    _ = p.request(shield: .sealed, elapsed: 120, now: instant())
    p.phrase = "end my sprint"
    p.keepGoing()
    #expect(p.flow == nil)
    #expect(p.phrase.isEmpty)
    let observed7 = !p.endAnyway(now: instant().addingTimeInterval(60))
    #expect(observed7)
  }
  @Test func scheduleDayAndTimeCopy() {
    #expect(ScheduleText.days([]) == "No days")
    #expect(ScheduleText.days([0, 1, 2, 3, 4, 5, 6]) == "Every day")
    #expect(ScheduleText.days([1, 2, 3, 4, 5]) == "Weekdays")
    #expect(ScheduleText.days([0, 6]) == "Weekends")
    #expect(ScheduleText.days([1, 2, 3, 4]) == "Mon–Thu")
    #expect(ScheduleText.days([5, 1, 3, 3]) == "Mon, Wed, Fri")
    #expect(ScheduleText.time(-1) == "00:00")
    #expect(ScheduleText.time(1020) == "17:00")
    #expect(ScheduleText.time(1500) == "23:59")
  }
  @Test func scheduleNextUpCopy() {
    #expect(
      ScheduleText.nextUp(
        template: "Homework evening", start: instant("2026-10-26T17:00:00Z"), now: instant(),
        calendar: utcCalendar) == "Next: tonight 17:00 · Homework evening")
    #expect(
      ScheduleText.nextUp(
        template: "Study", start: instant("2026-10-27T09:00:00Z"), now: instant(),
        calendar: utcCalendar) == "Next: tomorrow 09:00 · Study")
  }
}
