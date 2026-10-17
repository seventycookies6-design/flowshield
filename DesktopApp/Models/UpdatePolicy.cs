namespace FlowShield.Models;

/// <summary>The live routine and shields, sampled again immediately before applying.</summary>
public readonly record struct UpdateActivity(
    bool SprintRunning = false, bool OnBreak = false, bool InStudyCycle = false,
    bool SleepEnforcing = false, bool ScheduledEnforcing = false, bool Sealed = false);

/// <summary>Update timing and safety without I/O or updater dependencies (roadmap 4.1).</summary>
public static class UpdatePolicy
{
    public static bool IsCheckDue(bool enabled, bool installed, DateTime launchedUtc,
        DateTime? lastCheckUtc, DateTime nowUtc) =>
        enabled && installed && nowUtc >= launchedUtc.AddSeconds(60)
        && (lastCheckUtc is null || nowUtc >= lastCheckUtc.Value.AddHours(24));

    public static bool CanApply(UpdateActivity activity) =>
        !activity.SprintRunning && !activity.OnBreak && !activity.InStudyCycle
        && !activity.SleepEnforcing && !activity.ScheduledEnforcing && !activity.Sealed;

    public static bool ShouldShowWhatsNew(string runningVersion, string? lastRunVersion) =>
        lastRunVersion is not null && CompareVersions(runningVersion, lastRunVersion) > 0;

    // Velopack uses semantic versions. Compare numeric components numerically,
    // with prereleases below their stable release; ignore build metadata.
    private static int CompareVersions(string current, string previous)
    {
        static (Version? Number, string? Pre) Parse(string value)
        {
            var parts = value.Split('+')[0].Split('-', 2);
            if (!Version.TryParse(parts[0], out var version)) return (null, null);
            return (new Version(version.Major, version.Minor, Math.Max(0, version.Build),
                Math.Max(0, version.Revision)), parts.Length > 1 ? parts[1] : null);
        }
        var a = Parse(current);
        var b = Parse(previous);
        if (a.Number is null || b.Number is null) return 0;
        var number = a.Number.CompareTo(b.Number);
        if (number != 0) return number;
        if (a.Pre is null) return b.Pre is null ? 0 : 1;
        if (b.Pre is null) return -1;
        var left = a.Pre.Split('.');
        var right = b.Pre.Split('.');
        for (var i = 0; i < Math.Min(left.Length, right.Length); i++)
        {
            var an = long.TryParse(left[i], out var av);
            var bn = long.TryParse(right[i], out var bv);
            var comparison = an && bn ? av.CompareTo(bv)
                : an != bn ? (an ? -1 : 1) : string.CompareOrdinal(left[i], right[i]);
            if (comparison != 0) return comparison;
        }
        return left.Length.CompareTo(right.Length);
    }
}

public record ReleaseNoteLine(string Text, bool IsHeading = false);

/// <summary>An unread update survives another launch. Notes are captured before a later download.</summary>
public sealed class WhatsNewAnnouncement
{
    private readonly string _version;
    public bool Visible { get; private set; }
    public string Title => $"What's new in {_version}";
    public IReadOnlyList<ReleaseNoteLine> Lines { get; }

    public WhatsNewAnnouncement(AppSettings settings, string runningVersion)
    {
        _version = runningVersion;
        Visible = UpdatePolicy.ShouldShowWhatsNew(runningVersion, settings.LastRunVersion);
        if (!Visible) settings.LastRunVersion = runningVersion;
        var notes = settings.PendingReleaseVersion == runningVersion ? settings.PendingReleaseNotes : null;
        Lines = string.IsNullOrWhiteSpace(notes)
            ? new[] { new ReleaseNoteLine($"Basalt was updated to {runningVersion}.") }
            : notes.Replace("\r", "").Split('\n').Where(l => !string.IsNullOrWhiteSpace(l))
                .Select(l => l.Trim()).Select(l => l.StartsWith("- ")
                    ? new ReleaseNoteLine("• " + l[2..])
                    : l.StartsWith('#') ? new ReleaseNoteLine(l.TrimStart('#').TrimStart(), true)
                    : new ReleaseNoteLine(l)).ToArray();
    }

    public void Dismiss(AppSettings settings)
    {
        settings.LastRunVersion = _version;
        Visible = false;
    }
}
