using System.Text.Json.Serialization;

namespace FlowShield.Models;

/// <summary>How hard FlowShield pushes back when a blocked app appears.</summary>
public enum ShieldLevel
{
    /// <summary>Full-screen nudge overlay; dismissible.</summary>
    Soft = 1,

    /// <summary>Blocked apps are closed on sight. Blocklist stays editable.</summary>
    Firm = 2,

    /// <summary>Closed on sight and the blocklist locks for the sprint. Pro only.</summary>
    Sealed = 3,
}

public class BlockedApp
{
    public string Name { get; set; } = "";

    /// <summary>Process name without extension, e.g. "slack". Matched case-insensitively.</summary>
    public string ProcessName { get; set; } = "";

    public bool IsEnabled { get; set; } = true;

    /// <summary>Times this app was closed by the shield. Feeds the Today view.</summary>
    public int BlockCount { get; set; }

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
    public bool IsPro { get; set; }
    public string LicenseServerUrl { get; set; } = "http://localhost:3000";
    public string WebsiteUrl { get; set; } = "http://localhost:5500";
    public DateTime? LicenseCheckedUtc { get; set; }
    public string LicenseStatus { get; set; } = "";

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

    // ---- limits ---------------------------------------------------------
    public const int FreeBlockedAppLimit = 3;
    public const int FreeMaxSprintMinutes = 25;

    [JsonIgnore]
    public int BlockedAppLimit => IsPro ? int.MaxValue : FreeBlockedAppLimit;

    /// <summary>Deep-copy used by the settings service to snapshot before writes.</summary>
    public AppSettings Clone()
    {
        var json = System.Text.Json.JsonSerializer.Serialize(this);
        return System.Text.Json.JsonSerializer.Deserialize<AppSettings>(json) ?? new AppSettings();
    }
}
