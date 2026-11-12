namespace FlowShield.Models;

/// <summary>
/// The one place the app states Basalt's price (#442).
///
/// $14.99 once is the early-adopter price: it rises as features are added, and
/// everyone who bought before a rise keeps getting every new feature. Change
/// the price here, in the Mac app's <c>Pricing.swift</c> and on the site
/// together; tier 5's single-price test fails if any customer surface is left
/// showing another amount.
/// </summary>
public static class Pricing
{
    public const string Price = "$14.99";

    public const string BuyLabel = "Buy Basalt — " + Price;

    public const string KeepTitle = "Keep Basalt for " + Price;

    public const string KeepSleepShield = "Buy Basalt once for " + Price + " to keep your nightly shield.";
}
