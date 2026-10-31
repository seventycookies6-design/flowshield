import AppKit
import SwiftUI
import BasaltCore

enum SoftAnswer { case back, allow, close }

private final class SoftNoticePanel: NSPanel {
  override var canBecomeKey: Bool { true }
  override var canBecomeMain: Bool { false }
}

@MainActor
final class SoftNoticeController {
  private let panel: NSPanel
  init(app: NSRunningApplication, sprint: RunningSprint, tryNumber: Int, testTimings: Bool,
    answer: @escaping (SoftAnswer) -> Void) {
    panel = SoftNoticePanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    panel.level = .floating
    panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
    panel.isReleasedWhenClosed = false
    panel.hidesOnDeactivate = false
    panel.isOpaque = false
    panel.backgroundColor = .clear
    panel.hasShadow = true
    panel.contentView = NSHostingView(rootView: SoftNoticeView(name: app.localizedName ?? "App", sprint: sprint,
      tryNumber: tryNumber, unlocksAt: Date().addingTimeInterval(SoftOverlayPolicy.allowWait(tryNumber, testTimings: testTimings)), answer: answer))
  }
  func show(on screen: NSScreen) {
    let frame = screen.visibleFrame
    panel.setFrame(NSRect(x: frame.midX - 320, y: frame.midY - 260, width: 640, height: 520), display: true)
    panel.makeKeyAndOrderFront(nil)
  }
  func close() { panel.orderOut(nil) }
}

struct SoftNoticeView: View {
  let name: String
  let sprint: RunningSprint
  let tryNumber: Int
  let unlocksAt: Date
  let answer: (SoftAnswer) -> Void
  @FocusState private var backFocused: Bool
  var body: some View {
    TimelineView(.periodic(from: .now, by: 1)) { context in
      let wait = unlocksAt.timeIntervalSince(context.date)
      VStack(spacing: 20) {
        Image(systemName: "shield").font(.system(size: 48)).foregroundStyle(Color("Primary"))
        Text(SoftOverlayCopy.sentence(name, until: sprint.endsUtc.formatted(date: .omitted, time: .shortened), tryNumber: tryNumber)).font(.title2).multilineTextAlignment(.center).accessibilityIdentifier("SoftOverlayText")
        Text(SoftOverlayCopy.tryLine(tryNumber)).foregroundStyle(.secondary)
        Text(SoftOverlayCopy.timeLeft(sprint.endsUtc.timeIntervalSince(context.date)))
        if !sprint.intention.isEmpty { Text(SoftOverlayCopy.intention(sprint.intention)) }
        Button("Back to work") { answer(.back) }.keyboardShortcut(.defaultAction).controlSize(.large).focused($backFocused).accessibilityIdentifier("SoftOverlayBackToWorkButton")
        HStack(spacing: 12) {
          Button(SoftOverlayCopy.allowLabel(wait)) { if Date() >= unlocksAt { answer(.allow) } }.disabled(wait > 0).accessibilityIdentifier("SoftOverlayAllowButton")
          Button("Close \(name)") { answer(.close) }.accessibilityIdentifier("SoftOverlayCloseButton")
        }
        Text(SoftOverlayCopy.closeNote).font(.footnote).foregroundStyle(.secondary)
      }
      .padding(48).frame(maxWidth: .infinity, maxHeight: .infinity)
      .background(.background, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
      .onExitCommand { answer(.back) }
      .onAppear { backFocused = true }
    }
  }
}
