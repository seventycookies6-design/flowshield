import SwiftUI
import BasaltCore

@main
struct BasaltApp: App {
    var body: some Scene {
        WindowGroup {
            VStack(spacing: 12) {
                Text("Basalt").font(.largeTitle)
                Text(ShieldCopy.promise(AppSettings().defaultShield)).foregroundStyle(.secondary)
            }
            .padding(40)
            .frame(minWidth: 400, minHeight: 240)
        }
    }
}
