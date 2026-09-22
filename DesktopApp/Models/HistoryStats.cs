namespace FlowShield.Models;

/// <summary>
/// Everything the History page counts (launch checklist F16, roadmap 3.1 and
/// 3.6): the current week's figures and the focus-minutes heatmap.
///
/// Nothing new is recorded to draw any of it. Sprints have been written to
/// <see cref="AppSettings.Sessions"/> since F3, so the whole page is a
/// projection of what is already on disk — the same choice
/// <see cref="MomentumTrend"/> made, and for the same reason: a stored weekly
/// roll-up would start the day this shipped and could disagree with the
/// sessions it claims to summarise.
///
/// Deliberately free of any UI, clock or file system. The rules below are the
/// ones tier 1 pins by reading this file, so they live here rather than in the
/// view model.
/// </summary>
public static class HistoryStats
{
    // ------------------------------------------------------- week boundaries

    /// <summary>
    /// The Monday that starts the week <paramref name="localDay"/> falls in, at
    /// midnight local time.
    ///
    /// Monday-first is fixed rather than taken from the current culture: the
    /// week label, the figures and the heatmap's rows must agree with each
    /// other, and a customer who changes their regional format should not see
    /// last week's hours move. Sunday is the awkward case — .NET's
    /// <see cref="DayOfWeek"/> numbers it 0, so it needs the full six days back.
    /// </summary>
    public static DateTime WeekStart(DateTime localDay)
    {
        var day = localDay.Date;
        var back = day.DayOfWeek == DayOfWeek.Sunday ? 6 : (int)day.DayOfWeek - 1;
        return day.AddDays(-back);
    }

    /// <summary>The Sunday that ends that week, as a date (inclusive).</summary>
    public static DateTime WeekEnd(DateTime localDay) => WeekStart(localDay).AddDays(6);

    /// <summary>The local calendar day a sprint belongs to: the day it started.</summary>
    /// <remarks>
    /// Local, not UTC, and the start rather than the end: a sprint begun at
    /// 11:30pm belongs to the evening the customer remembers, not to tomorrow.
    /// <see cref="JournalExport.InRange"/> already groups exports this way.
    /// </remarks>
    public static DateTime DayOf(FocusSession session) => session.StartedUtc.ToLocalTime().Date;

    // ------------------------------------------------------------- this week

    /// <summary>One week's figures, as the cards at the top of History show them.</summary>
    public readonly record struct Week(
        DateTime Start,
        DateTime End,
        double FocusMinutes,
        int SprintsCompleted,
        int Distractions);

    /// <summary>
    /// The week containing <paramref name="nowLocal"/>.
    ///
    /// Focus minutes are the minutes sprints actually ran, whatever their
    /// outcome, which is the same sum the Today card shows for one day — a
    /// sprint ended after 20 of its 25 minutes really was 20 minutes of focus,
    /// and counting only finished ones would make the week's hours disagree
    /// with today's. "Sprints completed" counts only the finished ones, because
    /// that is what it says.
    /// </summary>
    public static Week ForWeek(IEnumerable<FocusSession> sessions, DateTime nowLocal)
    {
        var start = WeekStart(nowLocal);
        var end = WeekEnd(nowLocal);

        var inWeek = sessions
            .Where(s => DayOf(s) >= start && DayOf(s) <= end)
            .ToList();

        return new Week(
            start,
            end,
            Math.Round(inWeek.Sum(s => s.ActualMinutes), 1),
            inWeek.Count(s => s.Completed),
            inWeek.Sum(s => s.BlocksEnforced));
    }

    // --------------------------------------------------------------- heatmap

    /// <summary>Days the heatmap covers.</summary>
    public const int HeatmapDays = 30;

    /// <summary>Colour steps, `surface-2` through `primary` (DESIGN_SYSTEM.md §7).</summary>
    public const int Steps = 5;

    /// <summary>One day of the heatmap.</summary>
    /// <param name="Day">The local date.</param>
    /// <param name="Minutes">Focus minutes on it, rounded.</param>
    /// <param name="Step">0 for nothing at all, then 1–4 by share of the busiest day.</param>
    public readonly record struct Cell(DateTime Day, int Minutes, int Step);

    /// <summary>
    /// The last <paramref name="days"/> days, oldest first, always exactly that
    /// many cells so the grid never changes shape.
    /// </summary>
    public static IReadOnlyList<Cell> Heatmap(
        IEnumerable<FocusSession> sessions, DateTime todayLocal, int days = HeatmapDays)
    {
        var start = todayLocal.Date.AddDays(-(days - 1));

        var byDay = sessions
            .Where(s => DayOf(s) >= start && DayOf(s) <= todayLocal.Date)
            .GroupBy(DayOf)
            .ToDictionary(g => g.Key, g => (int)Math.Round(g.Sum(s => s.ActualMinutes)));

        var peak = byDay.Count == 0 ? 0 : byDay.Values.Max();

        var cells = new List<Cell>(days);
        for (var i = 0; i < days; i++)
        {
            var day = start.AddDays(i);
            var minutes = byDay.TryGetValue(day, out var m) ? m : 0;
            cells.Add(new Cell(day, minutes, Step(minutes, peak)));
        }
        return cells;
    }

    /// <summary>
    /// Which of the five steps a day's minutes fall in.
    ///
    /// Scaled against the window's own busiest day rather than a fixed minute
    /// count: a customer doing 25-minute sprints and one doing three hours a day
    /// should both see a readable range instead of one flat block. Step 0 means
    /// *no* focus at all, so one minute is always visibly different from none,
    /// and the remaining four steps split the rest evenly.
    /// </summary>
    public static int Step(int minutes, int peak)
    {
        if (minutes <= 0) return 0;
        if (peak <= 0) return 1;
        var share = Math.Ceiling(minutes / (double)peak * (Steps - 1));
        return Math.Clamp((int)share, 1, Steps - 1);
    }

    // -------------------------------------------------- the most-blocked app

    /// <summary>
    /// The blocklist entry the shield has stepped in over most often, or an
    /// empty string when nothing has been blocked yet.
    ///
    /// This one figure cannot come from the sessions: a sprint records *how
    /// many* distractions it caught, never which app they were, and adding a
    /// per-app-per-sprint tally would be new stored data for one line of text.
    /// So it is the running count FlowShield already keeps per blocklist entry,
    /// and History labels it as the whole time you have been blocking, not as
    /// this week.
    ///
    /// Ties break on the display name, case-insensitively, so the card shows
    /// the same app every time it is drawn instead of whichever happened to be
    /// first in the list.
    /// </summary>
    public static string MostBlocked(IEnumerable<BlockedApp> apps) =>
        apps
            .Where(a => a.BlockCount > 0)
            .OrderByDescending(a => a.BlockCount)
            .ThenBy(a => a.DisplayName, StringComparer.OrdinalIgnoreCase)
            .Select(a => a.DisplayName)
            .FirstOrDefault() ?? "";
}
