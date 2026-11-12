namespace FlowShield.Models;

/// <summary>
/// Every status line Today shows beside "Now" at the top of the Now card
/// (#431). Until the redesign these sat inside the timer ring, where tier 5
/// laid each one out to prove it fit (#304); the card's status line wraps
/// freely, but the lines still come from one list so none is typed straight
/// into the view model. The break's lines live in <see cref="BreakCopy.Caption"/>,
/// beside the rest of the break's wording.
///
/// Each idle line ends by saying what is blocked right now, which is nothing
/// unless the nightly sleep window is open (<see cref="Status"/>): "Nothing is
/// blocked" would be untrue at 23:00 with sleep blocking on.
/// </summary>
public static class RingCaption
{
    /// <summary>Idle, before anything has happened: the status is the whole line.</summary>
    public const string Ready = "";
    public const string Cancelled = "Sprint cancelled.";
    public const string BreakOver = "Break over.";
    public const string Complete = "Sprint complete.";
    public const string Interrupted = "Sprint interrupted.";
    public const string EndedEarly = "Sprint ended early.";

    /// <summary>F3: the sprint ran out while Basalt was closed.</summary>
    public const string FinishedWhileClosed = "Sprint finished while Basalt was closed.";

    /// <summary>What is blocked while no sprint runs and the sleep window is shut.</summary>
    public const string NothingBlocked = "Nothing is blocked.";

    /// <summary>What is blocked while no sprint runs and the sleep window is open.</summary>
    public const string SleepShieldUp = "Sleep blocking is on.";

    /// <summary>
    /// An idle line: <paramref name="lead"/> (one of the constants above, or
    /// <see cref="Ready"/>) followed by what is blocked right now.
    /// </summary>
    public static string Status(string lead, bool inSleepWindow)
    {
        var blocked = inSleepWindow ? SleepShieldUp : NothingBlocked;
        return lead.Length == 0 ? blocked : $"{lead} {blocked}";
    }

    /// <summary>A sprint running: "Basalt is holding. 3 apps blocked at Firm."</summary>
    public static string Engaged(ShieldLevel shield, int apps = 0) =>
        apps > 0 ? $"Basalt is holding. {Apps(apps)} blocked at {shield}." : $"Basalt is holding at {shield}.";

    /// <summary>A sprint picked up again after Basalt restarted.</summary>
    public static string Resumed(ShieldLevel shield, int apps = 0) =>
        apps > 0 ? $"Sprint resumed. {Apps(apps)} blocked at {shield}." : $"Sprint resumed at {shield}.";

    private static string Apps(int count) => count == 1 ? "1 app" : $"{count} apps";

    /// <summary>
    /// Every line, each with whether a sprint is running beside it. Kept so
    /// tier 5 can check no line is missing from the list.
    /// </summary>
    public static IReadOnlyList<(string Text, bool Running)> Every()
    {
        var every = new List<(string Text, bool Running)>();
        foreach (var lead in new[] { Ready, Cancelled, BreakOver, Complete, Interrupted, EndedEarly, FinishedWhileClosed })
            foreach (var sleep in new[] { false, true })
                every.Add((Status(lead, sleep), false));
        foreach (var shield in Enum.GetValues<ShieldLevel>())
        {
            every.Add((Engaged(shield, 3), true));
            every.Add((Resumed(shield, 3), true));
        }
        foreach (var inSleepWindow in new[] { false, true })
            foreach (var resumed in new[] { false, true })
                every.Add((BreakCopy.Caption(inSleepWindow, resumed), false));
        // NothingBlocked and SleepShieldUp are in every Status line above.
        _ = NothingBlocked + SleepShieldUp;
        return every;
    }
}
