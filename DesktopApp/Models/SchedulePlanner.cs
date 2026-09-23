using System.Globalization;

namespace FlowShield.Models;

public enum ScheduleActionKind { HeadsUp, Start, OfferMissed }

public sealed record ScheduleAction(ScheduleActionKind Kind, SprintSchedule Schedule, DateTime StartUtc);

/// <summary>
/// What the scheduler does on one tick (F6). Pure: given the last tick and
/// now, it says which heads-ups, starts and missed offers are due. The service
/// only carries them out. Its one side effect is a log line for a start
/// missed by more than the late window (spec 3.3).
///
/// A start more than a minute old when first seen was missed (the PC slept,
/// FlowShield was closed, the clock jumped). Missed starts are offered, never
/// started, and only the latest one inside the late window, so a long gap is
/// one question rather than a burst of sprints.
/// </summary>
public static class SchedulePlanner
{
    /// <summary>
    /// Set by <c>--short-schedules</c> so the UI suite doesn't wait minutes.
    /// Every window shrinks with the tick, so each rule can still happen:
    /// tick &lt; lead, tick &lt; on time &lt; late window.
    /// </summary>
    public static bool UseShortSchedules { get; set; }

    public static TimeSpan HeadsUpLead => UseShortSchedules ? TimeSpan.FromSeconds(5) : TimeSpan.FromMinutes(5);
    public static TimeSpan LateWindow => UseShortSchedules ? TimeSpan.FromSeconds(10) : TimeSpan.FromMinutes(30);

    /// <summary>How often the service ticks.</summary>
    public static TimeSpan TickInterval => UseShortSchedules ? TimeSpan.FromSeconds(1) : TimeSpan.FromSeconds(15);

    /// <summary>
    /// How late a start may be seen and still count as on time: a few ticks,
    /// so a tick the busy UI thread runs late still starts it.
    /// </summary>
    public static TimeSpan OnTime => UseShortSchedules ? TimeSpan.FromSeconds(3) : TimeSpan.FromMinutes(1);

    /// <summary>"s1@2026-09-28T21:00:00Z": one heads-up per schedule and start.</summary>
    public static string HeadsUpKey(SprintSchedule s, DateTime startUtc) =>
        $"{s.Id}@{startUtc.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture)}";

    /// <summary>
    /// The actions due between <paramref name="lastTickUtc"/> (exclusive) and
    /// <paramref name="nowUtc"/>, oldest first, ties by schedule id.
    /// </summary>
    public static IReadOnlyList<ScheduleAction> Decide(
        IEnumerable<SprintSchedule> schedules, DateTime lastTickUtc, DateTime nowUtc,
        TimeZoneInfo zone, ISet<string> headsUpShown)
    {
        var actions = new List<ScheduleAction>();
        ScheduleAction? latestMissed = null;
        (SprintSchedule Schedule, DateTime StartUtc)? tooLate = null;

        foreach (var s in schedules.Where(x => x.Enabled).OrderBy(x => x.Id, StringComparer.Ordinal))
        {
            // Heads-up: the next start is within the lead and not yet announced.
            if (s.AskFirst && ScheduleMatcher.NextStartUtc(s, nowUtc, zone) is { } next
                && next - nowUtc <= HeadsUpLead
                && !IsSkipped(s, next, zone)
                && !headsUpShown.Contains(HeadsUpKey(s, next)))
            {
                actions.Add(new ScheduleAction(ScheduleActionKind.HeadsUp, s, next));
            }

            foreach (var start in ScheduleMatcher.StartsBetweenUtc(s, lastTickUtc, nowUtc, zone))
            {
                if (IsSkipped(s, start, zone)) continue;
                var late = nowUtc - start;
                if (late <= OnTime)
                {
                    actions.Add(new ScheduleAction(ScheduleActionKind.Start, s, start));
                }
                else if (late <= LateWindow)
                {
                    if (latestMissed is null || start > latestMissed.StartUtc)
                        latestMissed = new ScheduleAction(ScheduleActionKind.OfferMissed, s, start);
                }
                else if (tooLate is null || start > tooLate.Value.StartUtc)
                {
                    tooLate = (s, start);
                }
            }
        }

        if (latestMissed is not null) actions.Add(latestMissed);

        // One line however long the gap was (TimeSpan's default format is invariant).
        if (tooLate is { } old)
        {
            Services.Log.Info($"schedule {old.Schedule.Id} not offered: its start at "
                + old.StartUtc.ToString("yyyy-MM-dd HH:mm'Z'", CultureInfo.InvariantCulture)
                + $" was missed by more than {LateWindow}");
        }

        return actions.OrderBy(a => a.StartUtc).ThenBy(a => a.Schedule.Id, StringComparer.Ordinal).ToList();
    }

    private static bool IsSkipped(SprintSchedule s, DateTime startUtc, TimeZoneInfo zone) =>
        s.IsSkipped(TimeZoneInfo.ConvertTimeFromUtc(startUtc, zone).Date);
}
