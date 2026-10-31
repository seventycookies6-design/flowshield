// swift-tools-version: 6.2
import PackageDescription

let package = Package(
  name: "BasaltCore",
  platforms: [.macOS(.v26), .iOS(.v26)],
  products: [.library(name: "BasaltCore", targets: ["BasaltCore"])],
  targets: [
    .target(name: "BasaltCore"), .testTarget(name: "BasaltCoreTests", dependencies: ["BasaltCore"]),
  ],
  swiftLanguageModes: [.v6]
)
