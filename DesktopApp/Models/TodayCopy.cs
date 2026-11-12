using System.Globalization;

namespace FlowShield.Models;

/// <summary>
/// The words on Today's Now, Up next and Momentum cards (#431). Pure, so
/// tier 1 checks the wording through the model probe. Times use the
/// customer's own short time format, as the Soft notice does.
///
/// DESIGN_SYSTEM.md Part A, Voice: plain words, no exclamation marks, and no
/// middle dots between facts (the redesign README): facts are joined by
/// commas or written as sentences.
/// </summary>
public static class TodayCopy
{
    /// <summary>"10:49 PM", or "22:49", as the customer's Windows writes a time.</summary>
    public static string Time(DateTime local) => local.ToString("t", CultureInfo.CurrentCulture);

    /// <summary>Under the countdown before a sprint: "ends 10:49 PM", then <see cref="IfYouStartNow"/>.</summary>
    public static string EndsAt(DateTime local) => $"ends {Time(local)}";

    public const string IfYouStartNow = "if you start now";

    /// <summary>The setup panel's line: "Ends 10:49 PM if you start now."</summary>
    public static string PanelEndsAt(DateTime local) => $"Ends {Time(local)} if you start now.";

    /// <summary>Under the countdown while a sprint or break runs: "until 10:19 PM".</summary>
    public static string Until(DateTime local) => $"until {Time(local)}";

    /// <summary>"School blocklist, 3 apps", after the sprint line.</summary>
    public static string BlocklistLine(string name, int apps)
    {
        var count = apps == 1 ? "1 app" : $"{apps} apps";
        return $"{name} blocklist, {count}";
    }

    /// <summary>The apps a blocklist holds, for its row in the setup panel's dropdown.</summary>
    public static string AppNames(IEnumerable<string> names)
    {
        var list = names.Where(n => !string.IsNullOrWhiteSpace(n)).ToList();
        return list.Count == 0 ? "No apps yet" : string.Join(", ", list);
    }

    /// <summary>
    /// The Momentum card's line about today, idle: "No sprint yet today", or
    /// "2 sprints today, 50 minutes focused". Zero counters are not shown.
    /// </summary>
    public static string TodayFacts(int sprints, int minutes)
    {
        if (sprints <= 0 && minutes <= 0) return "No sprint yet today";
        var parts = new List<string>();
        if (sprints > 0) parts.Add(sprints == 1 ? "1 sprint today" : $"{sprints} sprints today");
        if (minutes > 0) parts.Add(minutes == 1 ? "1 minute focused" : $"{minutes} minutes focused");
        if (sprints <= 0) parts[0] += " today";
        return string.Join(", ", parts);
    }

    /// <summary>The Momentum card while a sprint runs.</summary>
    public const string MomentumWhileRunning = "Adds when this sprint finishes";

    /// <summary>"8-day streak"; nothing to say about a streak of none.</summary>
    public static string Streak(int days) => days switch
    {
        <= 0 => "No streak yet",
        1 => "1-day streak",
        _ => $"{days}-day streak",
    };

    /// <summary>At the end of a sprint: "Day 9 of your streak".</summary>
    public static string StreakDay(int days) => $"Day {Math.Max(days, 1)} of your streak";

    /// <summary>
    /// At the end of a sprint, momentum's change over today: "Up 6 today, from
    /// 186". A drop is stated neutrally, with the way back (Part A, Kind).
    /// </summary>
    public static string MomentumChange(int delta, int from) => delta switch
    {
        > 0 => $"Up {delta} today, from {from}",
        < 0 => $"Down {-delta} today, from {from}. It recovers with your next sprint.",
        _ => $"Unchanged today, at {from}",
    };

    /// <summary>"15 minutes focused", the end of a sprint's headline.</summary>
    public static string MinutesFocused(int minutes) =>
        minutes == 1 ? "1 minute focused" : $"{minutes} minutes focused";

    /// <summary>The headline's line of facts: "Firm, 10:04 to 10:19 PM."</summary>
    public static string ResultFacts(ShieldLevel shield, DateTime startLocal, DateTime endLocal) =>
        $"{shield}, {Time(startLocal)} to {Time(endLocal)}.";

    /// <summary>
    /// What the shield did, as a sentence: "No blocked app was opened.",
    /// "Basalt closed 2 apps and sent 1 nudge.", or "3 distractions caught."
    /// </summary>
    public static string Distractions(int closed, int nudges, int blocks)
    {
        if (closed > 0 || nudges > 0)
        {
            var parts = new List<string>();
            if (closed > 0) parts.Add(closed == 1 ? "closed 1 app" : $"closed {closed} apps");
            if (nudges > 0) parts.Add(nudges == 1 ? "sent 1 nudge" : $"sent {nudges} nudges");
            return $"Basalt {string.Join(" and ", parts)}.";
        }
        if (blocks > 0) return blocks == 1 ? "1 distraction caught." : $"{blocks} distractions caught.";
        return "No blocked app was opened.";
    }

    /// <summary>The running sprint's Details: what the shield has stopped so far.</summary>
    public static string BlockedSoFar(int blocks) => blocks switch
    {
        <= 0 => "Nothing blocked so far",
        1 => "1 distraction blocked so far",
        _ => $"{blocks} distractions blocked so far",
    };

    /// <summary>The running sprint's Details: "Started 10:04 PM".</summary>
    public static string Started(DateTime local) => $"Started {Time(local)}";

    // ------------------------------------------------------------ Up next

    /// <summary>What Up next shows: a time, and one line about it.</summary>
    public readonly record struct UpNextLine(string When, string What);

    /// <summary>A schedule's next start, already found by <see cref="ScheduleMatcher"/>.</summary>
    public readonly record struct ScheduledStart(DateTime StartLocal, string Name, int Minutes, ShieldLevel Shield);

    public const string NothingScheduled = "Nothing scheduled";
    public const string NothingScheduledHint = "Schedules start a sprint by themselves at a set time.";

    /// <summary>
    /// The next thing that will block something by itself: the next scheduled
    /// sprint, or the nightly sleep window, whichever comes first. Null when
    /// neither is set up.
    /// </summary>
    public static UpNextLine? UpNext(DateTime nowLocal, ScheduledStart? schedule,
        bool sleepEnabled, TimeSpan sleepStart, TimeSpan sleepEnd)
    {
        DateTime? sleepAt = null;
        var inSleepWindow = false;
        if (sleepEnabled)
        {
            var now = nowLocal.TimeOfDay;
            inSleepWindow = sleepStart <= sleepEnd
                ? now >= sleepStart && now < sleepEnd
                : now >= sleepStart || now < sleepEnd;
            if (!inSleepWindow)
            {
                var today = nowLocal.Date + sleepStart;
                sleepAt = today > nowLocal ? today : today.AddDays(1);
            }
        }

        var sleepEndsText = Time(DateTime.Today + sleepEnd);
        if (inSleepWindow)
            return new UpNextLine("Now", $"Sleep blocking until {sleepEndsText}");

        if (schedule is { } s && (sleepAt is null || s.StartLocal <= sleepAt))
            return new UpNextLine(When(s.StartLocal, nowLocal), $"{s.Name}, {s.Minutes} min at {s.Shield}");
        if (sleepAt is { } at)
            return new UpNextLine(When(at, nowLocal), $"Sleep blocking until {sleepEndsText}");
        return null;
    }

    /// <summary>"10:30 PM" today, "Tomorrow, 6:00 PM", or "Mon, 6:00 PM".</summary>
    public static string When(DateTime startLocal, DateTime nowLocal)
    {
        var days = (startLocal.Date - nowLocal.Date).Days;
        var time = Time(startLocal);
        return days switch
        {
            <= 0 => time,
            1 => $"Tomorrow, {time}",
            _ => $"{startLocal.ToString("ddd", CultureInfo.CurrentCulture)}, {time}",
        };
    }
}
