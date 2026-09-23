namespace FlowShield.Models;

/// <summary>
/// When a <see cref="SprintSchedule"/> starts (F6). Pure: no timers, no clock
/// of its own. Every answer is a UTC instant, so a comparison never depends
/// on what the wall clock was doing.
///
/// Daylight saving, written down once:
///   * Spring forward: the start time doesn't exist that day (02:30 on the
///     day clocks jump to 03:00). The sprint starts at the first minute that
///     does exist.
///   * Fall back: the start time happens twice. The sprint starts once, at
///     the first occurrence. Each local date yields one instant, so a second
///     start is impossible.
/// </summary>
public static class ScheduleMatcher
{
    /// <summary>A local wall-clock time in <paramref name="zone"/> as one UTC instant, per the rules above.</summary>
    public static DateTime ToUtc(DateTime local, TimeZoneInfo zone)
    {
        local = DateTime.SpecifyKind(local, DateTimeKind.Unspecified);

        // Spring forward. Bounded, so a malformed zone can't loop forever.
        for (var guard = 0; zone.IsInvalidTime(local) && guard < 24 * 60; guard++)
            local = local.AddMinutes(1);

        if (zone.IsAmbiguousTime(local))
        {
            // Fall back. The earlier instant is the one with the larger offset.
            var offset = zone.GetAmbiguousTimeOffsets(local).Max();
            return DateTime.SpecifyKind(local - offset, DateTimeKind.Utc);
        }

        return TimeZoneInfo.ConvertTimeToUtc(local, zone);
    }

    /// <summary>The start on this local date, or null when the schedule doesn't run that day.</summary>
    public static DateTime? StartOnDateUtc(SprintSchedule schedule, DateTime localDate, TimeZoneInfo zone)
    {
        var date = localDate.Date;
        if (!schedule.Days.Contains(date.DayOfWeek)) return null;
        var minute = Math.Clamp(schedule.StartMinuteOfDay, 0, 24 * 60 - 1);
        return ToUtc(date.AddMinutes(minute), zone);
    }

    /// <summary>Every start after <paramref name="fromUtcExclusive"/> and at or before <paramref name="toUtcInclusive"/>, oldest first.</summary>
    public static IReadOnlyList<DateTime> StartsBetweenUtc(
        SprintSchedule schedule, DateTime fromUtcExclusive, DateTime toUtcInclusive, TimeZoneInfo zone)
    {
        var found = new List<DateTime>();
        if (toUtcInclusive <= fromUtcExclusive || schedule.Days.Count == 0) return found;

        // One day either side: a UTC window can start or end on a different local date.
        var first = TimeZoneInfo.ConvertTimeFromUtc(fromUtcExclusive, zone).Date.AddDays(-1);
        var last = TimeZoneInfo.ConvertTimeFromUtc(toUtcInclusive, zone).Date.AddDays(1);
        for (var day = first; day <= last; day = day.AddDays(1))
        {
            if (StartOnDateUtc(schedule, day, zone) is { } start
                && start > fromUtcExclusive && start <= toUtcInclusive)
            {
                found.Add(start);
            }
        }
        return found;
    }

    /// <summary>The first start strictly after <paramref name="afterUtc"/>, or null when no day is chosen.</summary>
    public static DateTime? NextStartUtc(SprintSchedule schedule, DateTime afterUtc, TimeZoneInfo zone)
    {
        if (schedule.Days.Count == 0) return null;
        var today = TimeZoneInfo.ConvertTimeFromUtc(afterUtc, zone).Date;
        for (var i = 0; i <= 8; i++)
        {
            if (StartOnDateUtc(schedule, today.AddDays(i), zone) is { } start && start > afterUtc)
                return start;
        }
        return null;
    }
}
