import Foundation

import Testing

// Boundary fixtures mirror tier1/tier5 and Android core policy cases.
@testable import BasaltCore

struct PolicyBoundaryTests {
  @Test func sprintLength0() { #expect(SprintLength.isValid(-1) == false) }
  @Test func sprintLength1() { #expect(SprintLength.isValid(0) == false) }
  @Test func sprintLength2() { #expect(SprintLength.isValid(4) == false) }
  @Test func sprintLength3() { #expect(SprintLength.isValid(5) == true) }
  @Test func sprintLength4() { #expect(SprintLength.isValid(15) == true) }
  @Test func sprintLength5() { #expect(SprintLength.isValid(25) == true) }
  @Test func sprintLength6() { #expect(SprintLength.isValid(90) == true) }
  @Test func sprintLength7() { #expect(SprintLength.isValid(240) == true) }
  @Test func sprintLength8() { #expect(SprintLength.isValid(241) == false) }
  @Test func parseLength0() { #expect(SprintLength.parse("five") == nil) }
  @Test func parseLength1() { #expect(SprintLength.parse("5.5") == nil) }
  @Test func parseLength2() { #expect(SprintLength.parse(" 25 ") == 25) }
  @Test func parseLength3() { #expect(SprintLength.parse("+5") == 5) }
  @Test func parseLength4() { #expect(SprintLength.parse("") == nil) }
  @Test func parseLength5() { #expect(SprintLength.parse("241") == nil) }
  @Test func softFlow0() { #expect(EndSprintPolicy().flow(shield: .soft, elapsed: 0) == .cancel) }
  @Test func softFlow119_999() {
    #expect(EndSprintPolicy().flow(shield: .soft, elapsed: 119.999) == .cancel)
  }
  @Test func softFlow120() {
    #expect(EndSprintPolicy().flow(shield: .soft, elapsed: 120) == .immediate)
  }
  @Test func firmFlow0() { #expect(EndSprintPolicy().flow(shield: .firm, elapsed: 0) == .cancel) }
  @Test func firmFlow119_999() {
    #expect(EndSprintPolicy().flow(shield: .firm, elapsed: 119.999) == .cancel)
  }
  @Test func firmFlow120() {
    #expect(EndSprintPolicy().flow(shield: .firm, elapsed: 120) == .confirm)
  }
  @Test func sealedFlow0() {
    #expect(EndSprintPolicy().flow(shield: .sealed, elapsed: 0) == .cancel)
  }
  @Test func sealedFlow119_999() {
    #expect(EndSprintPolicy().flow(shield: .sealed, elapsed: 119.999) == .cancel)
  }
  @Test func sealedFlow120() {
    #expect(EndSprintPolicy().flow(shield: .sealed, elapsed: 120) == .sealed)
  }
  @Test func sealedPhrase0() { #expect(EndSprintPolicy.phraseMatches("end my sprint") == true) }
  @Test func sealedPhrase1() { #expect(EndSprintPolicy.phraseMatches(" END  MY\nsprint ") == true) }
  @Test func sealedPhrase2() { #expect(EndSprintPolicy.phraseMatches("end sprint") == false) }
  @Test func sealedPhrase3() { #expect(EndSprintPolicy.phraseMatches("end my sprints") == false) }
  @Test func sealedPhrase4() { #expect(EndSprintPolicy.phraseMatches("") == false) }
  @Test func sealedPhrase5() { #expect(EndSprintPolicy.phraseMatches("end my sprint!") == false) }
  @Test func sealedPhrase6() { #expect(EndSprintPolicy.phraseMatches("end\tmy\rsprint") == true) }
  @Test func momentumGain5() { #expect(Momentum.gain(plannedMinutes: 5) == 5) }
  @Test func momentumGain10() { #expect(Momentum.gain(plannedMinutes: 10) == 5) }
  @Test func momentumGain15() { #expect(Momentum.gain(plannedMinutes: 15) == 6) }
  @Test func momentumGain25() { #expect(Momentum.gain(plannedMinutes: 25) == 10) }
  @Test func momentumGain45() { #expect(Momentum.gain(plannedMinutes: 45) == 18) }
  @Test func momentumGain60() { #expect(Momentum.gain(plannedMinutes: 60) == 24) }
  @Test func momentumGain90() { #expect(Momentum.gain(plannedMinutes: 90) == 30) }
  @Test func momentumGain240() { #expect(Momentum.gain(plannedMinutes: 240) == 30) }
  @Test func earlyMomentumsoft100() {
    #expect(EndSprintPolicy.momentumAfterEndingEarly(100, shield: .soft) == 83)
  }
  @Test func earlyMomentumfirm100() {
    #expect(EndSprintPolicy.momentumAfterEndingEarly(100, shield: .firm) == 83)
  }
  @Test func earlyMomentumsealed100() {
    #expect(EndSprintPolicy.momentumAfterEndingEarly(100, shield: .sealed) == 65)
  }
  @Test func earlyMomentumsoft0() {
    #expect(EndSprintPolicy.momentumAfterEndingEarly(0, shield: .soft) == 0)
  }
  @Test func earlyMomentumsealed1() {
    #expect(EndSprintPolicy.momentumAfterEndingEarly(1, shield: .sealed) == 0)
  }
  @Test func earlyMomentumfirm10() {
    #expect(EndSprintPolicy.momentumAfterEndingEarly(10, shield: .firm) == 6.5)
  }
  @Test func allowWait0() {
    #expect(SoftOverlayPolicy.allowWait(-1) == 5)
    #expect(SoftOverlayPolicy.allowWait(-1, testTimings: true) == 3)
  }
  @Test func allowWait1() {
    #expect(SoftOverlayPolicy.allowWait(0) == 5)
    #expect(SoftOverlayPolicy.allowWait(0, testTimings: true) == 3)
  }
  @Test func allowWait2() {
    #expect(SoftOverlayPolicy.allowWait(1) == 5)
    #expect(SoftOverlayPolicy.allowWait(1, testTimings: true) == 3)
  }
  @Test func allowWait3() {
    #expect(SoftOverlayPolicy.allowWait(2) == 10)
    #expect(SoftOverlayPolicy.allowWait(2, testTimings: true) == 3)
  }
  @Test func allowWait4() {
    #expect(SoftOverlayPolicy.allowWait(3) == 20)
    #expect(SoftOverlayPolicy.allowWait(3, testTimings: true) == 3)
  }
  @Test func allowWait5() {
    #expect(SoftOverlayPolicy.allowWait(4) == 30)
    #expect(SoftOverlayPolicy.allowWait(4, testTimings: true) == 3)
  }
  @Test func allowWait6() {
    #expect(SoftOverlayPolicy.allowWait(100) == 30)
    #expect(SoftOverlayPolicy.allowWait(100, testTimings: true) == 3)
  }
  @Test func ordinal1() { #expect(SoftOverlayCopy.tryLine(1) == "1st try this sprint") }
  @Test func ordinal2() { #expect(SoftOverlayCopy.tryLine(2) == "2nd try this sprint") }
  @Test func ordinal3() { #expect(SoftOverlayCopy.tryLine(3) == "3rd try this sprint") }
  @Test func ordinal4() { #expect(SoftOverlayCopy.tryLine(4) == "4th try this sprint") }
  @Test func ordinal11() { #expect(SoftOverlayCopy.tryLine(11) == "11th try this sprint") }
  @Test func ordinal12() { #expect(SoftOverlayCopy.tryLine(12) == "12th try this sprint") }
  @Test func ordinal13() { #expect(SoftOverlayCopy.tryLine(13) == "13th try this sprint") }
  @Test func ordinal21() { #expect(SoftOverlayCopy.tryLine(21) == "21st try this sprint") }
  @Test func ordinal112() { #expect(SoftOverlayCopy.tryLine(112) == "112th try this sprint") }
  @Test func heatmapStep0() { #expect(HistoryStats.step(minutes: 0, peak: 100) == 0) }
  @Test func heatmapStep1() { #expect(HistoryStats.step(minutes: 1, peak: 100) == 1) }
  @Test func heatmapStep2() { #expect(HistoryStats.step(minutes: 25, peak: 100) == 1) }
  @Test func heatmapStep3() { #expect(HistoryStats.step(minutes: 26, peak: 100) == 2) }
  @Test func heatmapStep4() { #expect(HistoryStats.step(minutes: 50, peak: 100) == 2) }
  @Test func heatmapStep5() { #expect(HistoryStats.step(minutes: 51, peak: 100) == 3) }
  @Test func heatmapStep6() { #expect(HistoryStats.step(minutes: 75, peak: 100) == 3) }
  @Test func heatmapStep7() { #expect(HistoryStats.step(minutes: 76, peak: 100) == 4) }
  @Test func heatmapStep8() { #expect(HistoryStats.step(minutes: 100, peak: 100) == 4) }
  @Test func heatmapStep9() { #expect(HistoryStats.step(minutes: 1, peak: 0) == 1) }
  @Test func trialBoundary0() {
    let start = instant()
    let now = start.addingTimeInterval(-86401)
    #expect(TrialPolicy.isActive(start: start, now: now) == false)
    #expect(TrialPolicy.daysLeft(start: start, now: now) == 0)
  }
  @Test func trialBoundary1() {
    let start = instant()
    let now = start.addingTimeInterval(-86400)
    #expect(TrialPolicy.isActive(start: start, now: now) == true)
    #expect(TrialPolicy.daysLeft(start: start, now: now) == 7)
  }
  @Test func trialBoundary2() {
    let start = instant()
    let now = start.addingTimeInterval(0)
    #expect(TrialPolicy.isActive(start: start, now: now) == true)
    #expect(TrialPolicy.daysLeft(start: start, now: now) == 7)
  }
  @Test func trialBoundary3() {
    let start = instant()
    let now = start.addingTimeInterval(1)
    #expect(TrialPolicy.isActive(start: start, now: now) == true)
    #expect(TrialPolicy.daysLeft(start: start, now: now) == 7)
  }
  @Test func trialBoundary4() {
    let start = instant()
    let now = start.addingTimeInterval(518400)
    #expect(TrialPolicy.isActive(start: start, now: now) == true)
    #expect(TrialPolicy.daysLeft(start: start, now: now) == 1)
  }
  @Test func trialBoundary5() {
    let start = instant()
    let now = start.addingTimeInterval(604799)
    #expect(TrialPolicy.isActive(start: start, now: now) == true)
    #expect(TrialPolicy.daysLeft(start: start, now: now) == 1)
  }
  @Test func trialBoundary6() {
    let start = instant()
    let now = start.addingTimeInterval(604800)
    #expect(TrialPolicy.isActive(start: start, now: now) == false)
    #expect(TrialPolicy.daysLeft(start: start, now: now) == 0)
  }
  @Test func csvFormula0() { #expect(JournalExport.defuse("=formula") == "'=formula") }
  @Test func csvFormula1() { #expect(JournalExport.defuse("+formula") == "'+formula") }
  @Test func csvFormula2() { #expect(JournalExport.defuse("-formula") == "'-formula") }
  @Test func csvFormula3() { #expect(JournalExport.defuse("@formula") == "'@formula") }
  @Test func csvFormula4() { #expect(JournalExport.defuse("\tformula") == "'\tformula") }
  @Test func csvFormula5() { #expect(JournalExport.defuse("\rformula") == "'\rformula") }
  @Test func breakBounds0() { #expect(CycleState.isValidBreakMinutes(0) == false) }
  @Test func breakBounds1() { #expect(CycleState.isValidBreakMinutes(1) == true) }
  @Test func breakBounds2() { #expect(CycleState.isValidBreakMinutes(60) == true) }
  @Test func breakBounds3() { #expect(CycleState.isValidBreakMinutes(61) == false) }
  @Test func menuIcon0() { #expect(NotificationPolicy.iconText(-1) == "0") }
  @Test func menuIcon1() { #expect(NotificationPolicy.iconText(1) == "1") }
  @Test func menuIcon2() { #expect(NotificationPolicy.iconText(60) == "1") }
  @Test func menuIcon3() { #expect(NotificationPolicy.iconText(61) == "2") }
  @Test func menuIcon4() { #expect(NotificationPolicy.iconText(5940) == "99") }
  @Test func menuIcon5() { #expect(NotificationPolicy.iconText(6000) == "1h") }
  @Test func menuIcon6() { #expect(NotificationPolicy.iconText(14400) == "4h") }
}
