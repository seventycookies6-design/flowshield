namespace FlowShield.Models;

/// <summary>
/// "Homework evening, Mon-Thu at 17:00" (launch checklist F6).
///
/// A start time only. The template's length decides when the sprint ends,
/// which avoids the midnight-spanning windows other blockers get wrong.
/// </summary>
public class SprintSchedule
{
    /// <summary>How long a "Skip today" is remembered. Older dates can't matter again.</summary>
    public const int SkipMemoryDays = 14;

    /// <summary>Empty until <see cref="Normalize"/> assigns one and reports the change, for the same reason as <see cref="StudyTemplate.Id"/>.</summary>
    public string Id { get; set; } = "";
    public string TemplateId { get; set; } = "";
    public List<DayOfWeek> Days { get; set; } = new();

    /// <summary>Minutes after local midnight, 0 to 1439.</summary>
    public int StartMinuteOfDay { get; set; } = 17 * 60;

    /// <summary>Heads-up five minutes before, with Start now / Skip today. On by default.</summary>
    public bool AskFirst { get; set; } = true;

    public bool Enabled { get; set; } = true;

    /// <summary>
    /// Local dates the user chose Skip today. Stored with
    /// <see cref="DateTimeKind.Unspecified"/>: a Local kind is written to the
    /// file with the PC's offset and converted back on load, so a skip
    /// recorded before a westward time-zone change would read as the day before.
    /// </summary>
    public List<DateTime> SkippedDatesLocal { get; set; } = new();

    public bool IsSkipped(DateTime localDate) =>
        SkippedDatesLocal.Any(d => d.Date == localDate.Date);

    public void Skip(DateTime localDate)
    {
        var date = DateTime.SpecifyKind(localDate.Date, DateTimeKind.Unspecified);
        if (!IsSkipped(date)) SkippedDatesLocal.Add(date);
        SkippedDatesLocal.RemoveAll(d => d.Date < date.AddDays(-SkipMemoryDays));
        SkippedDatesLocal.Sort();
    }

    /// <summary>Brings a hand-edited or older record into range. True if anything changed.</summary>
    public bool Normalize()
    {
        var changed = false;
        if (string.IsNullOrWhiteSpace(Id)) { Id = StudyTemplate.NewId(); changed = true; }
        if (TemplateId is null) { TemplateId = ""; changed = true; }

        var minute = Math.Clamp(StartMinuteOfDay, 0, 24 * 60 - 1);
        if (minute != StartMinuteOfDay) { StartMinuteOfDay = minute; changed = true; }

        var days = (Days ?? new List<DayOfWeek>())
            .Where(d => Enum.IsDefined(d)).Distinct().OrderBy(d => d).ToList();
        if (Days is null || !days.SequenceEqual(Days)) { Days = days; changed = true; }

        if (SkippedDatesLocal is null) { SkippedDatesLocal = new List<DateTime>(); changed = true; }
        return changed;
    }
}
