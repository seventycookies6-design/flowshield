namespace FlowShield.Models;

/// <summary>One night's window, as the instants it opens and closes (roadmap 3.7).</summary>
/// <param name="StartUtc">When the shield goes up.</param>
/// <param name="EndUtc">When it comes down.</param>
/// <param name="StartLocal">The wall-clock reading of <paramref name="StartUtc"/> in the zone that was asked.</param>
/// <param name="EndLocal">The wall-clock reading of <paramref name="EndUtc"/>.</param>
public sealed record SleepOccurrence(DateTime StartUtc, DateTime EndUtc, DateTime StartLocal, DateTime EndLocal);

/// <summary>
/// The nightly sleep window (roadmap 3.7): a start time, an end time that may
/// fall after midnight, and the nights it starts on. Pure: no UI, no timer and
/// no clock of its own. Every question takes the time as a UTC instant, so
/// enforcement, the ten-minute warning and the page's "Tonight 23:00" all
/// read the same answer, and a test can ask about any moment.
///
/// A night is named by the day the window STARTS on. A Friday window that runs
/// to 06:30 belongs to Friday, so early Saturday morning is inside it even when
/// Saturday itself is not a chosen night.
///
/// Daylight saving is <see cref="ScheduleMatcher.ToUtc"/>'s rule, the one the
/// schedules use: a time that doesn't exist moves to the first minute that
/// does, and one that happens twice means the first. Start and end are
/// converted separately, so on the night clocks go back the window is an hour
/// longer than it reads, and on the night they go forward an hour shorter.
/// A night whose converted end isn't after its converted start has no window.
/// </summary>
public sealed class SleepWindow
{
    /// <summary>How long before the window opens the warning goes out.</summary>
    public static readonly TimeSpan WarningLead = TimeSpan.FromMinutes(10);

    public static readonly IReadOnlyList<DayOfWeek> EveryNight = new[]
    {
        DayOfWeek.Monday, DayOfWeek.Tuesday, DayOfWeek.Wednesday, DayOfWeek.Thursday,
        DayOfWeek.Friday, DayOfWeek.Saturday, DayOfWeek.Sunday,
    };

    private readonly HashSet<DayOfWeek> _nights;
    private readonly TimeZoneInfo _zone;

    public SleepWindow(TimeSpan start, TimeSpan end, IEnumerable<DayOfWeek>? nights, TimeZoneInfo zone)
    {
        Start = Clamp(start);
        End = Clamp(end);
        _nights = nights is null ? new HashSet<DayOfWeek>(EveryNight) : nights.Where(d => Enum.IsDefined(d)).ToHashSet();
        _zone = zone;
    }

    /// <summary>The window the settings describe. Whether it is switched on is the caller's question.</summary>
    public static SleepWindow From(AppSettings settings, TimeZoneInfo? zone = null) =>
        new(settings.SleepBlockStartTime, settings.SleepBlockEndTime, settings.SleepBlockDays, zone ?? TimeZoneInfo.Local);

    public TimeSpan Start { get; }
    public TimeSpan End { get; }

    /// <summary>The nights it starts on, Monday first.</summary>
    public IReadOnlyList<DayOfWeek> Nights => EveryNight.Where(_nights.Contains).ToList();

    /// <summary>
    /// False when no night is chosen or start equals end: the window never opens.
    /// An explicitly empty list of nights stays empty; only a settings file that
    /// has no list at all (written before nights existed) means every night.
    /// </summary>
    public bool CanOpen => _nights.Count > 0 && Start != End;

    /// <summary>The window that starts on this local date, or null when that night isn't chosen.</summary>
    public SleepOccurrence? OnDate(DateTime localDate)
    {
        var date = localDate.Date;
        if (!CanOpen || !_nights.Contains(date.DayOfWeek)) return null;

        var endDate = End > Start ? date : date.AddDays(1);
        var startUtc = ScheduleMatcher.ToUtc(date + Start, _zone);
        var endUtc = ScheduleMatcher.ToUtc(endDate + End, _zone);
        if (endUtc <= startUtc) return null;
        return new SleepOccurrence(startUtc, endUtc, ToLocal(startUtc), ToLocal(endUtc));
    }

    /// <summary>The window that is open at this instant, or null.</summary>
    public SleepOccurrence? Current(DateTime nowUtc)
    {
        if (!CanOpen) return null;
        var today = ToLocal(nowUtc).Date;
        // A window is under 25 hours long, so the one that is open started yesterday or today.
        for (var i = -1; i <= 1; i++)
        {
            if (OnDate(today.AddDays(i)) is { } w && w.StartUtc <= nowUtc && nowUtc < w.EndUtc) return w;
        }
        return null;
    }

    public bool Contains(DateTime nowUtc) => Current(nowUtc) is not null;

    /// <summary>The first window that opens strictly after this instant, or null when none ever does.</summary>
    public SleepOccurrence? Next(DateTime nowUtc)
    {
        if (!CanOpen) return null;
        var today = ToLocal(nowUtc).Date;
        // Two weeks: a one-night window lost to the skipped spring hour opens the week after.
        for (var i = -1; i <= 15; i++)
        {
            if (OnDate(today.AddDays(i)) is { } w && w.StartUtc > nowUtc) return w;
        }
        return null;
    }

    /// <summary>When the warning for this window goes out.</summary>
    public static DateTime WarningUtc(SleepOccurrence occurrence) => occurrence.StartUtc - WarningLead;

    private DateTime ToLocal(DateTime utc) => TimeZoneInfo.ConvertTimeFromUtc(
        DateTime.SpecifyKind(utc, DateTimeKind.Utc), _zone);

    private static TimeSpan Clamp(TimeSpan t) =>
        t < TimeSpan.Zero ? TimeSpan.Zero
        : t >= TimeSpan.FromDays(1) ? TimeSpan.FromDays(1) - TimeSpan.FromMinutes(1)
        : t;
}

/// <summary>
/// Decides when the "Wind down" warning goes out (roadmap 3.7), once per
/// window. Pure, like <see cref="SleepWindow"/>: the caller supplies the time,
/// the settings and a way to list the running apps, and gets back the notice
/// or null. It remembers the windows it has warned about, by their start, so a
/// tick every 15 seconds raises one notice, a clock set back doesn't raise a
/// second, and a window that has already opened is never warned about late.
/// </summary>
public sealed class SleepWarningPlanner
{
    private readonly HashSet<DateTime> _warned = new();

    /// <summary>
    /// The notice due at <paramref name="nowUtc"/>, or null: the window is off,
    /// the trial has ended, the user switched this notice off, it is not yet
    /// ten minutes before the next window, the window is already open, or this
    /// window has been warned about. <paramref name="runningApps"/> is only
    /// asked when a notice is going out.
    /// </summary>
    public Notification? Due(AppSettings settings, bool locked, DateTime nowUtc,
                             Func<IReadOnlyList<string>> runningApps, bool sprintRunning = false,
                             TimeZoneInfo? zone = null)
    {
        if (!settings.IsSleepBlockEnabled || locked) return null;
        if (!NotificationPolicy.ShouldShow(NotificationKind.SleepWindowWarning, settings, sprintRunning)) return null;

        var window = SleepWindow.From(settings, zone);
        if (window.Contains(nowUtc)) return null;
        if (window.Next(nowUtc) is not { } next || nowUtc < SleepWindow.WarningUtc(next)) return null;
        if (!_warned.Add(next.StartUtc)) return null;
        _warned.RemoveWhere(start => start < nowUtc - TimeSpan.FromDays(2));

        var (title, message) = SleepWindowCopy.Warning(runningApps(), next.StartLocal.TimeOfDay);
        return new Notification(NotificationKind.SleepWindowWarning, title, message, NotificationAction.OpenSchedule);
    }
}

/// <summary>How the sleep window reads on screen and in its notice. Pure, so tier 1 checks the wording.</summary>
public static class SleepWindowCopy
{
    private const int NamesShown = 3;

    public static string Time(TimeSpan t) => $"{(int)t.TotalHours:00}:{t.Minutes:00}";

    /// <summary>
    /// "Wind down" and "Steam and Discord close at 23:00." Only apps that are
    /// running are named, the ones enforcement would close; with none running
    /// the notice says when the shield goes up and promises nothing about apps.
    /// </summary>
    public static (string Title, string Message) Warning(IReadOnlyList<string> apps, TimeSpan start)
    {
        const string title = "Wind down";
        var at = Time(start);
        if (apps.Count == 0) return (title, $"Your sleep shield goes up at {at}.");

        var verb = apps.Count == 1 ? "closes" : "close";
        return (title, $"{JoinNames(apps)} {verb} at {at}.");
    }

    /// <summary>"Steam", "Steam and Discord", "Steam, Discord and Slack", "Steam, Discord, Slack and 2 more".</summary>
    public static string JoinNames(IReadOnlyList<string> names)
    {
        if (names.Count <= 1) return names.Count == 1 ? names[0] : "";
        if (names.Count <= NamesShown) return $"{string.Join(", ", names.Take(names.Count - 1))} and {names[^1]}";
        return $"{string.Join(", ", names.Take(NamesShown))} and {names.Count - NamesShown} more";
    }

    /// <summary>
    /// "Tonight 23:00 → 06:30", "Tomorrow 23:00 → 06:30", "Friday 23:00 → 06:30",
    /// or "Next Friday" once a week or more away, when "Friday" alone would read
    /// as today. Compared by the start's local date; a start between 17:00 and
    /// 05:00 today is "Tonight", an earlier one "Today".
    /// </summary>
    public static string Next(SleepOccurrence next, DateTime nowUtc, TimeZoneInfo zone)
    {
        var nowLocal = TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(nowUtc, DateTimeKind.Utc), zone);
        var days = (next.StartLocal.Date - nowLocal.Date).Days;
        var hour = next.StartLocal.Hour;
        var name = next.StartLocal.DayOfWeek.ToString();
        var when = days switch
        {
            <= 0 => hour >= 17 || hour < 5 ? "Tonight" : "Today",
            1 => "Tomorrow",
            >= 7 => $"Next {name}",
            _ => name,
        };
        return $"{when} {Time(next.StartLocal.TimeOfDay)} → {Time(next.EndLocal.TimeOfDay)}";
    }
}
