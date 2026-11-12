/// The one place the Mac app states Basalt's price (#442).
///
/// $14.99 once is the early-adopter price: it rises as features are added, and
/// everyone who bought before a rise keeps getting every new feature. Change
/// it here, in the Windows app's `Pricing.cs` and on the site together; tier
/// 5's single-price test fails if any customer surface shows another amount.
enum Pricing {
  static let price = "$14.99"
  static let buyLabel = "Buy Basalt — \(price)"
}
