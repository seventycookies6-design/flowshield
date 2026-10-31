import AppKit
import SwiftUI
import BasaltCore

enum SoftAnswer { case back, allow, close }

@MainActor
final class SoftNoticeController {
  private let panel: NSPanel
  init(app: NSRunningApplication, sprint: RunningSprint, tryNumber: Int, testTimings: Bool,
    answer: @escaping (SoftAnswer) -> Void) {
    panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    panel.level = .floating
    panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
    panel.isReleasedWhenClosed = false
    panel.hidesOnDeactivate = false
    panel.contentView = NSHostingView(rootView: SoftNoticeView(name: app.localizedName ?? "App", sprint: sprint,
      tryNumber: tryNumber, unlocksAt: Date().addingTimeInterval(SoftOverlayPolicy.allowWait(tryNumber, testTimings: testTimings)), answer: answer))
  }
  func show(on screen: NSScreen) { panel.setFrame(screen.frame, display: true); panel.orderFrontRegardless() }
  func close() { panel.orderOut(nil) }
}

struct SoftNoticeView: View {
  let name: String
  let sprint: RunningSprint
  let tryNumber: Int
  let unlocksAt: Date
  let answer: (SoftAnswer) -> Void
  var body: some View {
    TimelineView(.periodic(from: .now, by: 1)) { context in
      let wait = unlocksAt.timeIntervalSince(context.date)
      VStack(spacing: 20) {
        Image(systemName: "shield").font(.system(size: 48)).foregroundStyle(Color("Primary"))
        Text(SoftOverlayCopy.sentence(name, until: sprint.endsUtc.formatted(date: .omitted, time: .shortened), tryNumber: tryNumber)).font(.largeTitle).multilineTextAlignment(.center)
        Text(SoftOverlayCopy.tryLine(tryNumber)).foregroundStyle(.secondary)
        Text(SoftOverlayCopy.timeLeft(sprint.endsUtc.timeIntervalSince(context.date)))
        if !sprint.intention.isEmpty { Text(SoftOverlayCopy.intention(sprint.intention)) }
        Button("Back to work") { answer(.back) }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
        Button(SoftOverlayCopy.allowLabel(wait)) { if Date() >= unlocksAt { answer(.allow) } }.disabled(wait > 0)
        Button("Close \(name)") { answer(.close) }
        Text(SoftOverlayCopy.closeNote).font(.footnote).foregroundStyle(.secondary)
      }
      .padding(48).frame(maxWidth: .infinity, maxHeight: .infinity)
      .background(.background)
    }
  }
}
