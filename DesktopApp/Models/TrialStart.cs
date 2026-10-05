using System.Globalization;

namespace FlowShield.Models;

/// <summary>
/// When the free trial began, kept in two places: <c>settings.json</c> and a
/// small registry value outside it (<c>Services.TrialRecord</c>).
///
/// Delete everything removes <c>settings.json</c>, and before this the next
/// launch saw no start date and handed out a fresh 7-day trial (found on the
/// 1.0.11 VM run). The earlier of the two dates wins, so removing either copy
/// never restarts the trial, and the missing copy is written back.
/// </summary>
public static class TrialStart
{
    /// <summary>The earlier of two known starts, or null when neither is known.</summary>
    public static DateTime? Earliest(DateTime? fromSettings, DateTime? fromRecord) =>
        (fromSettings, fromRecord) switch
        {
            ({ } a, { } b) => a <= b ? a : b,
            ({ } a, null) => a,
            (null, { } b) => b,
            _ => null,
        };

    /// <summary>The registry form: round-trip ISO 8601 in UTC.</summary>
    public static string Format(DateTime startUtc) =>
        DateTime.SpecifyKind(startUtc, DateTimeKind.Utc).ToString("o", CultureInfo.InvariantCulture);

    /// <summary>
    /// Reads the registry form back. Anything unreadable is treated as no
    /// record, so a damaged value can only fall back to settings, never lock
    /// anyone out on its own.
    /// </summary>
    public static DateTime? Parse(string? text) =>
        DateTime.TryParse(text, CultureInfo.InvariantCulture,
            DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out var parsed)
            ? parsed
            : null;
}
