namespace FlowShield.Models;

/// <summary>
/// How a blocked app is closed at Firm and above (launch checklist F7,
/// roadmap 1.8).
///
/// The old behaviour was <c>Process.Kill</c> the instant a blocked app was
/// seen, which loses unsaved work and feels like being swatted rather than
/// protected. The app is now asked to close itself first, and only killed if
/// it is still there when the grace period runs out.
///
/// Hard kill mode keeps the old behaviour deliberately: someone who has turned
/// that on has said they want no way round it, and a ten-second window is a
/// way round it.
///
/// Kept free of UI so the rules and the wording can be tested on their own.
/// </summary>
public static class GracefulClose
{
    /// <summary>Set by --short-timers so the UI suite isn't waiting ten seconds a time.</summary>
    public static bool UseShortTimers { get; set; }

    public static TimeSpan Grace => UseShortTimers ? TimeSpan.FromSeconds(2) : TimeSpan.FromSeconds(10);

    /// <summary>
    /// Whether this sighting gets a warning and a grace period at all.
    ///
    /// Soft never closes anything, so it never warns about closing. Hard kill
    /// is instant by definition.
    /// </summary>
    public static bool IsGraceful(ShieldLevel shield, bool hardKill) =>
        !hardKill && shield >= ShieldLevel.Firm;

    /// <summary>
    /// The warning, in the voice DESIGN_SYSTEM.md asks for: states the fact,
    /// says when, and tells you the one useful thing you can do about it.
    /// No apology and no telling-off.
    /// </summary>
    public static string Warning(string displayName, TimeSpan? grace = null)
    {
        var seconds = (int)Math.Round((grace ?? Grace).TotalSeconds);
        return $"{displayName} is blocked — closing in {seconds} s. Save your work.";
    }

    /// <summary>What the toast says once it has actually gone.</summary>
    public static string Closed(string displayName) => $"{displayName} closed by the shield.";

    /// <summary>What the toast says at Soft, where nothing is closed.</summary>
    public static string Noted(string displayName) => $"{displayName} is on your blocklist.";
}
