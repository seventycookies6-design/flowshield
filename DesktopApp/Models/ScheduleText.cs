using System.Globalization;

namespace FlowShield.Models;

/// <summary>How schedules read on screen (F6). Pure, so tier 1 checks the wording.</summary>
public static class ScheduleText
{
    /// <summary>Monday first, the way a school week reads.</summary>
    private static readonly DayOfWeek[] WeekOrder =
    {
        DayOfWeek.Monday, DayOfWeek.Tuesday, DayOfWeek.Wednesday, DayOfWeek.Thursday,
        DayOfWeek.Friday, DayOfWeek.Saturday, DayOfWeek.Sunday,
    };

    private static string Short(DayOfWeek day) =>
        CultureInfo.InvariantCulture.DateTimeFormat.GetAbbreviatedDayName(day);

    /// <summary>
    /// "Weekdays", "Every day", "Weekends", a run of three or more such as
    /// Mon to Thu (joined by an en dash), or a list such as "Mon, Wed, Fri".
    /// </summary>
    public static string Days(IEnumerable<DayOfWeek> days)
    {
        var set = days.ToHashSet();
        var ordered = WeekOrder.Where(set.Contains).ToList();
        if (ordered.Count == 0) return "No days";
        if (ordered.Count == WeekOrder.Length) return "Every day";
        if (ordered.SequenceEqual(WeekOrder.Take(5))) return "Weekdays";
        if (ordered.SequenceEqual(WeekOrder.Skip(5))) return "Weekends";

        // Distinct and in week order, so ends exactly Count - 1 apart means no gaps.
        var span = Array.IndexOf(WeekOrder, ordered[^1]) - Array.IndexOf(WeekOrder, ordered[0]);
        if (ordered.Count >= 3 && span == ordered.Count - 1)
            return $"{Short(ordered[0])}\u2013{Short(ordered[^1])}";

        return string.Join(", ", ordered.Select(Short));
    }

    /// <summary>"17:00". 24-hour, like the sleep window.</summary>
    public static string Time(int minuteOfDay)
    {
        var m = Math.Clamp(minuteOfDay, 0, 24 * 60 - 1);
        return string.Create(CultureInfo.InvariantCulture, $"{m / 60:00}:{m % 60:00}");
    }

    /// <summary>
    /// "Next: tonight 17:00 (middle dot) Homework evening". "Tonight" from 17:00,
    /// "today" before it, then "tomorrow", then the day's short name.
    /// </summary>
    public static string NextUp(string templateName, DateTime startLocal, DateTime nowLocal)
    {
        var time = Time((int)startLocal.TimeOfDay.TotalMinutes);
        var days = (startLocal.Date - nowLocal.Date).Days;
        var when = days switch
        {
            0 => startLocal.Hour >= 17 ? "tonight" : "today",
            1 => "tomorrow",
            _ => Short(startLocal.DayOfWeek),
        };
        return $"Next: {when} {time} \u00B7 {templateName}";
    }
}
