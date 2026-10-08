namespace FlowShield.Models;

/// <summary>
/// The words beside Blocked Apps' big number. The number is printed as it is
/// ("1", not "01"), and the label agrees with it: one app is "app on the
/// shield", any other count is "apps on the shield" (#347).
/// </summary>
public static class BlocklistCopy
{
    public static string AppsOnShield(int count) =>
        count == 1 ? "app on the shield" : "apps on the shield";
}
