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

    [JsonIgnore]
    public double ActualMinutes =>
        EndedUtc.HasValue ? Math.Round((EndedUtc.Value - StartedUtc).TotalMinutes, 1) : 0;
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
