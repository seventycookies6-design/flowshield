namespace FlowShield.Models;

/// <summary>
/// Every state line Today shows under the timer ring. The ring leaves the line
/// about 177 px, so tier 5 lays each one out in the real view to prove it fits
/// (#304); a line typed straight into the view model would never be measured.
/// The break's four lines live in <see cref="BreakCopy.Caption"/>, beside the
/// rest of the break's wording.
/// </summary>
public static class RingCaption
{
    public const string Ready = "Ready when you are";
    public const string Cancelled = "Sprint cancelled";
    public const string BreakOver = "Break over";
    public const string Complete = "Sprint complete";
    public const string Interrupted = "Sprint interrupted";
    public const string EndedEarly = "Sprint ended early";

    /// <summary>F3: the sprint ran out while FlowShield was closed.</summary>
    public const string FinishedWhileClosed = "Sprint finished while FlowShield was closed";

    /// <summary>A sprint starting. The shield glyph sits beside it.</summary>
    public static string Engaged(ShieldLevel shield) => $"Shield {Roman(shield)} engaged";

    /// <summary>A sprint picked up again after FlowShield restarted. The shield glyph sits beside it.</summary>
    public static string Resumed(ShieldLevel shield) => $"Sprint resumed — shield {Roman(shield)}";

    private static string Roman(ShieldLevel level) => level switch
    {
        ShieldLevel.Soft => "I",
        ShieldLevel.Firm => "II",
        _ => "III",
    };

    /// <summary>
    /// Every line, each with whether a sprint is running beside it (the shield
    /// glyph shows then, and takes 22 px of the line).
    /// </summary>
    public static IReadOnlyList<(string Text, bool Running)> Every()
    {
        var every = new List<(string Text, bool Running)>
        {
            (Ready, false), (Cancelled, false), (BreakOver, false), (Complete, false),
            (Interrupted, false), (EndedEarly, false), (FinishedWhileClosed, false),
        };
        foreach (var shield in Enum.GetValues<ShieldLevel>())
        {
            every.Add((Engaged(shield), true));
            every.Add((Resumed(shield), true));
        }
        foreach (var inSleepWindow in new[] { false, true })
            foreach (var resumed in new[] { false, true })
                every.Add((BreakCopy.Caption(inSleepWindow, resumed), false));
        return every;
    }
}
