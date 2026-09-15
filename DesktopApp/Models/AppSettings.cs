using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json.Serialization;

namespace FlowShield.Models;

/// <summary>How hard FlowShield pushes back when a blocked app appears.</summary>
public enum ShieldLevel
{
    /// <summary>Brief notice inside FlowShield; the blocked app keeps running.</summary>
    Soft = 1,

    /// <summary>Blocked apps are closed on sight. Blocklist stays editable.</summary>
    Firm = 2,

    /// <summary>Closed on sight and the blocklist locks for the sprint.</summary>
    Sealed = 3,
}

/// <summary>
/// One entry on the blocklist.
///
/// Implements INotifyPropertyChanged because the counts change while the list
/// is on screen — without it the "blocked N ×" label renders once and then lies
/// for the rest of the session.
/// </summary>
public class BlockedApp : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;

    private void Raise([CallerMemberName] string? name = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

    public string Name { get; set; } = "";

    /// <summary>Process name without extension, e.g. "slack". Matched case-insensitively.</summary>
    public string ProcessName { get; set; } = "";

    /// <summary>
    /// The app's other processes, e.g. steamwebhelper for Steam (F8). Without
    /// them, blocking Steam left its helper running. Empty in older settings files.
    /// </summary>
    public List<string> ExtraProcessNames { get; set; } = new();

    /// <summary>Where the icon came from, if known. Display only.</summary>
    public string? IconPath { get; set; }

    /// <summary>Every process name this entry blocks.</summary>
    [JsonIgnore]
    public IEnumerable<string> AllProcessNames =>
        new[] { ProcessName }.Concat(ExtraProcessNames)
            .Where(n => !string.IsNullOrWhiteSpace(n))
            .Select(n => n.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase);

    [JsonIgnore]
    public string ProcessSummary => string.Join(", ", AllProcessNames.Select(n => n + ".exe"));

    private bool _isEnabled = true;
    public bool IsEnabled
    {
        get => _isEnabled;
        set { if (_isEnabled != value) { _isEnabled = value; Raise(); } }
    }

    private int _blockCount;
    /// <summary>Times this app was closed by the shield. Feeds the Today view.</summary>
    public int BlockCount
    {
        get => _blockCount;
        set { if (_blockCount != value) { _blockCount = value; Raise(); } }
    }

    public DateTime AddedUtc { get; set; } = DateTime.UtcNow;

    [JsonIgnore]
    public string DisplayName => string.IsNullOrWhiteSpace(Name) ? ProcessName : Name;
}

/// <summary>A completed or abandoned focus sprint.</summary>
public class FocusSession
{
    public DateTime StartedUtc { get; set; }
    public DateTime? EndedUtc { get; set; }
    public int PlannedMinutes { get; set; }
    public ShieldLevel Shield { get; set; } = ShieldLevel.Firm;
    public bool Completed { get; set; }
    public int BlocksEnforced { get; set; }

    /// <summary>The one-line "what moved?" answer captured when a sprint ends.</summary>
    public string Journal { get; set; } = "";

    /// <summary>
    /// FlowShield was closed for most of this sprint (a crash, a reboot, or
    /// quitting from Task Manager), so it was neither finished nor given up.
    /// Interrupted sprints don't change momentum.
    /// </summary>
    public bool Interrupted { get; set; }

    /// <summary>Ended by the user before its time was up (after the grace period).</summary>
    [JsonIgnore]
    public bool EndedEarly => EndedUtc.HasValue && !Completed && !Interrupted;

    [JsonIgnore]
    public double ActualMinutes =>
        EndedUtc.HasValue ? Math.Round((EndedUtc.Value - StartedUtc).TotalMinutes, 1) : 0;
}

/// <summary>
/// The sprint that is running right now, saved the moment it starts.
///
/// A sprint used to live only in memory, so a crash, a reboot or ending
/// FlowShield from Task Manager quietly ended it, which made even a Sealed
/// sprint trivially escapable. On the next launch this is read back and the
/// sprint resumes with its shield (and a Sealed blocklist lock) intact.
/// </summary>
public class RunningSprint
{
    public DateTime StartedUtc { get; set; }
    public int PlannedMinutes { get; set; }
    public ShieldLevel Shield { get; set; } = ShieldLevel.Firm;

    /// <summary>Last time FlowShield confirmed it was still running this sprint.</summary>
    public DateTime LastSeenUtc { get; set; }

    [JsonIgnore]
    public DateTime EndsUtc => StartedUtc.AddMinutes(PlannedMinutes);

    /// <summary>What to do with this sprint when FlowShield starts again.</summary>
    public SprintResume Decide(DateTime nowUtc)
    {
        if (PlannedMinutes <= 0) return SprintResume.Discard;
        if (nowUtc < EndsUtc) return SprintResume.Resume;

        // The time ran out while FlowShield was closed. It counts as finished
        // only if FlowShield was watching for at least half of it; otherwise
        // nothing was actually enforced, so it's recorded as interrupted.
        var watched = (Min(LastSeenUtc, EndsUtc) - StartedUtc).TotalMinutes;
        return watched >= PlannedMinutes * CompletedIfWatchedFraction
            ? SprintResume.RecordCompleted
            : SprintResume.RecordInterrupted;
    }

    /// <summary>Share of a sprint FlowShield must have been running for it to count as finished.</summary>
    public const double CompletedIfWatchedFraction = 0.5;

    private static DateTime Min(DateTime a, DateTime b) => a < b ? a : b;
}

public enum SprintResume
{
    /// <summary>Time is left: carry on with the same shield and lock.</summary>
    Resume,
    /// <summary>Ended while closed, but FlowShield ran for most of it.</summary>
    RecordCompleted,
    /// <summary>Ended while closed, and FlowShield wasn't running for most of it.</summary>
    RecordInterrupted,
    /// <summary>Unreadable record; drop it.</summary>
    Discard,
}

public class AppSettings
{
    // ---- blocking -------------------------------------------------------
    public List<BlockedApp> BlockedApps { get; set; } = new();

    public bool IsSleepBlockEnabled { get; set; }
    public TimeSpan SleepBlockStartTime { get; set; } = new(22, 0, 0);
    public TimeSpan SleepBlockEndTime { get; set; } = new(6, 0, 0);

    // ---- preferences ----------------------------------------------------
    public bool StartWithWindows { get; set; }
    public bool HardKillModeEnabled { get; set; }
    public bool MinimizeToTrayOnClose { get; set; } = true;

    /// <summary>The first-run welcome (F18) has been shown, finished or skipped.</summary>
    public bool FirstRunCompleted { get; set; }

    // ---- licensing ------------------------------------------------------
    public string LicenseKey { get; set; } = "";
    public string LicenseEmail { get; set; } = "";

    /// <summary>
    /// True once a licence has been activated: FlowShield was bought. The name
    /// predates the one-time purchase (it meant "Pro subscriber") and is kept so
    /// existing settings files still load.
    /// </summary>
    public bool IsPro { get; set; }

    /// <summary>When the free trial began: the first launch of a build that has one.</summary>
    public DateTime? TrialStartedUtc { get; set; }
    /// <summary>
    /// Where licence validation goes. Points at the deployed service so a
    /// shipped build works without configuration; override it in Settings, or
    /// with --server= on the command line, to test against a local server.
    /// </summary>
    public string LicenseServerUrl { get; set; } = "https://flowshield-license-server.onrender.com";

    public string WebsiteUrl { get; set; } = "https://seventycookies6-design.github.io/flowshield";
    public DateTime? LicenseCheckedUtc { get; set; }
    public string LicenseStatus { get; set; } = "";

    /// <summary>Seats in use and allowed, as last reported by the server.</summary>
    public int DeviceCount { get; set; }

    public int DeviceLimit { get; set; }

    // ---- sessions & momentum -------------------------------------------
    public int DefaultSprintMinutes { get; set; } = 25;
    public ShieldLevel DefaultShield { get; set; } = ShieldLevel.Firm;
    public List<FocusSession> Sessions { get; set; } = new();

    /// <summary>The sprint in progress, or null. See <see cref="RunningSprint"/>.</summary>
    public RunningSprint? ActiveSprint { get; set; }

    /// <summary>
    /// Compounding score: completed sprints add, abandoned ones decay it.
    /// Persisted rather than recomputed so decay is monotonic over time.
    /// </summary>
    public double MomentumScore { get; set; }

    public int CurrentStreak { get; set; }
    public DateTime? LastSessionDayLocal { get; set; }

    /// <summary>
    /// Enforcement actions taken today, with the day they belong to.
    ///
    /// Stored rather than derived: the Today view previously summed every
    /// app's lifetime BlockCount and displayed it under a "TODAY" heading,
    /// which was simply the wrong number.
    /// </summary>
    public int BlocksToday { get; set; }

    public DateTime? BlocksTodayDateLocal { get; set; }

    /// <summary>Adds one of today's blocks, rolling the counter over at midnight.</summary>
    public void RecordBlock(DateTime? nowLocal = null)
    {
        var today = (nowLocal ?? DateTime.Now).Date;
        if (BlocksTodayDateLocal?.Date != today)
        {
            BlocksTodayDateLocal = today;
            BlocksToday = 0;
        }
        BlocksToday++;
    }

    /// <summary>Today's block count, or zero if the stored tally is stale.</summary>
    [JsonIgnore]
    public int BlocksTodayCurrent =>
        BlocksTodayDateLocal?.Date == DateTime.Now.Date ? BlocksToday : 0;

    // ---- trial & access -------------------------------------------------

    /// <summary>
    /// Length of the free trial. Everything is unlocked during it; afterwards the
    /// app is locked until FlowShield is bought. There is no free tier.
    /// </summary>
    public const int TrialDays = 7;

    /// <summary>Starts the trial clock on first launch. Returns true if it was just started.</summary>
    public bool EnsureTrialStarted(DateTime? nowUtc = null)
    {
        if (TrialStartedUtc is not null) return false;
        TrialStartedUtc = nowUtc ?? DateTime.UtcNow;
        return true;
    }

    [JsonIgnore]
    public DateTime? TrialEndsUtc => TrialStartedUtc?.AddDays(TrialDays);

    /// <summary>
    /// Whether the trial is running at <paramref name="nowUtc"/>.
    ///
    /// A clock more than a day behind the recorded start counts as ended:
    /// winding the clock back is the obvious way to stretch a trial, and a
    /// genuinely wrong clock is fixed by correcting it.
    /// </summary>
    public bool IsTrialActiveAt(DateTime nowUtc) =>
        TrialStartedUtc is { } start
        && nowUtc >= start.AddDays(-1)
        && nowUtc < start.AddDays(TrialDays);

    /// <summary>Whole days of trial left, rounded up, so the last day reads "1 day left".</summary>
    public int TrialDaysLeftAt(DateTime nowUtc) =>
        !IsTrialActiveAt(nowUtc) || TrialEndsUtc is not { } end
            ? 0
            : Math.Clamp((int)Math.Ceiling((end - nowUtc).TotalDays), 1, TrialDays);

    /// <summary>Every feature is available: bought, or inside the free trial.</summary>
    public bool HasAccessAt(DateTime nowUtc) => IsPro || IsTrialActiveAt(nowUtc);

    /// <summary>Deep-copy used by the settings service to snapshot before writes.</summary>
    public AppSettings Clone()
    {
        var json = System.Text.Json.JsonSerializer.Serialize(this);
        return System.Text.Json.JsonSerializer.Deserialize<AppSettings>(json) ?? new AppSettings();
    }
}
