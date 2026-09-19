namespace FlowShield.Models;

/// <summary>
/// The 30-day momentum trend (launch checklist F14, roadmap 3.2), and the
/// plain-words explanation of the rule beside it.
///
/// Nothing new is recorded to draw this. Momentum is entirely event-driven —
/// a finished sprint adds, ending one early takes a slice off, and nothing
/// happens with the passage of time — so the whole history is already in
/// <see cref="AppSettings.Sessions"/> and can simply be replayed. Storing a
/// daily sample instead would have meant a chart that began the day the
/// feature shipped, and a second copy of a number that can disagree with the
/// first.
///
/// Kept free of UI so the shape of the line can be tested on its own.
/// </summary>
public static class MomentumTrend
{
    public const int Days = 30;

    /// <summary>One day of the trend: the score as it stood at the end of it.</summary>
    public readonly record struct Point(DateTime Day, double Score);

    /// <summary>
    /// The score at the end of each of the last <paramref name="days"/> days,
    /// oldest first, always exactly that many points.
    ///
    /// A day with no sprints carries the previous day's score forward rather
    /// than dropping out of the series: momentum genuinely does not move on a
    /// day you did nothing, and a line with gaps in it would imply it did.
    /// </summary>
    public static IReadOnlyList<Point> Points(AppSettings settings, DateTime today, int days = Days)
    {
        var start = today.Date.AddDays(-(days - 1));

        // Replay every session in the order it happened, not just the ones in
        // range: the score on day one of the window is the sum of everything
        // before it.
        var ordered = settings.Sessions.OrderBy(s => s.StartedUtc).ToList();
        var byDay = new Dictionary<DateTime, double>();
        var score = 0.0;

        foreach (var session in ordered)
        {
            score = After(score, session);
            byDay[session.StartedUtc.ToLocalTime().Date] = score;
        }

        // Anything before the window collapses into the opening value.
        var running = ordered
            .Where(s => s.StartedUtc.ToLocalTime().Date < start)
            .Aggregate(0.0, After);

        var points = new List<Point>(days);
        for (var i = 0; i < days; i++)
        {
            var day = start.AddDays(i);
            if (byDay.TryGetValue(day, out var end)) running = end;
            points.Add(new Point(day, running));
        }
        return points;
    }

    /// <summary>The score after one sprint, by the same rules the app applies live.</summary>
    private static double After(double score, FocusSession session) =>
        session.Completed
            ? Math.Round(score + 10 * Math.Clamp(session.PlannedMinutes / 25.0, 0.5, 3.0), 1)
            : EndSprintPolicy.MomentumAfterEndingEarly(score, session.Shield);

    /// <summary>The highest point of the trend, never zero, so the chart has a scale.</summary>
    public static double Ceiling(IReadOnlyList<Point> points)
    {
        var peak = points.Count == 0 ? 0 : points.Max(p => p.Score);
        return peak <= 0 ? 10 : peak;
    }

    /// <summary>
    /// The rule in plain words (F14: "explain the rule").
    ///
    /// Written from the code above rather than from memory, and the numbers in
    /// it are asserted against the code in tier 1 so the explanation cannot
    /// quietly stop being true.
    /// </summary>
    public static readonly string[] Explanation =
    {
        "Finishing a sprint adds 10 points for a 25-minute one, scaled by how long it was: 5 points at the least, 30 at the most.",
        "Ending a sprint early takes a share of what you have, plus a little: about 15% and 2 points at Soft or Firm, 30% and 5 at Sealed. It never goes below zero.",
        "Nothing happens while you are away. Momentum does not decay overnight and it never resets, so a quiet week costs you nothing and a bad day is not the end of anything.",
    };
}
