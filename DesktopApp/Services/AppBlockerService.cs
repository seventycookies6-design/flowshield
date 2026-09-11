using System.Diagnostics;
using FlowShield.Models;

namespace FlowShield.Services;

public record BlockEvent(
    BlockedApp App,
    string ProcessName,
    string DisplayName,
    ShieldLevel Shield,
    bool Terminated,
    DateTime AtUtc);

/// <summary>
/// Background watcher that enforces the blocklist while a sprint is running or
/// the sleep window is open.
///
/// Enforcement is deliberately conservative:
///   * it only acts while <see cref="IsEnforcing"/> is true;
///   * it never touches a process on <see cref="CriticalProcesses"/>;
///   * Soft shield raises a nudge instead of terminating anything.
/// Killing the wrong process on someone's machine is a far worse failure than
/// letting one distraction through, so the guard list is checked first and is
/// not user-editable.
/// </summary>
public class AppBlockerService : IDisposable
{
    /// <summary>
    /// Processes that are never terminated regardless of the blocklist —
    /// OS-critical, shells, and the tooling a developer needs to recover.
    /// </summary>
    public static readonly HashSet<string> CriticalProcesses = new(StringComparer.OrdinalIgnoreCase)
    {
        "system", "registry", "idle", "smss", "csrss", "wininit", "winlogon", "services",
        "lsass", "svchost", "dwm", "explorer", "fontdrvhost", "sihost", "ctfmon",
        "runtimebroker", "shellexperiencehost", "startmenuexperiencehost", "searchhost",
        "audiodg", "conhost", "openconsole", "windowsterminal",
        "cmd", "powershell", "pwsh", "wsl", "wslhost",
        "flowshield",                                  // never shoot ourselves
        "python", "pythonw", "node", "dotnet", "msbuild", "devenv", "code", "claude",
    };

    private readonly SettingsService _settingsService;
    private readonly System.Timers.Timer _timer;
    private readonly object _gate = new();

    private AppSettings _settings;

    /// <summary>
    /// Private snapshot of the blocklist, rebuilt whenever settings change.
    ///
    /// The timer thread must never enumerate <c>AppSettings.BlockedApps</c>
    /// directly: the UI thread adds to and removes from that same List, and an
    /// enumeration racing a mutation throws "Collection was modified" from
    /// inside a timer callback — where there is no good place to catch it.
    /// The copy is shallow on purpose, so the BlockedApp instances are still
    /// the ones the UI is bound to.
    /// </summary>
    private List<BlockedApp> _targets = new();

    private readonly HashSet<int> _handled = new();

    public event EventHandler<BlockEvent>? Blocked;

    /// <summary>True while a sprint is running or the sleep window is open.</summary>
    public bool IsEnforcing { get; private set; }

    public ShieldLevel ActiveShield { get; private set; } = ShieldLevel.Firm;

    /// <summary>Total enforcement actions since the service started.</summary>
    public int EnforcementCount { get; private set; }

    public double PollSeconds
    {
        get => _timer.Interval / 1000.0;
        set => _timer.Interval = Math.Max(250, value * 1000);
    }

    public AppBlockerService(SettingsService settingsService, AppSettings settings)
    {
        _settingsService = settingsService;
        _settings = settings;
        _targets = settings.BlockedApps.ToList();

        _timer = new System.Timers.Timer(2000) { AutoReset = true };
        _timer.Elapsed += (_, _) => Tick();
        _timer.Start();
    }

    /// <summary>
    /// Republish settings to the watcher. Must be called on the UI thread after
    /// any change to the blocklist — it is what refreshes the private snapshot.
    /// </summary>
    public void UpdateSettings(AppSettings settings)
    {
        lock (_gate)
        {
            _settings = settings;
            _targets = settings.BlockedApps.ToList();
        }
    }

    public void BeginEnforcing(ShieldLevel shield)
    {
        lock (_gate)
        {
            IsEnforcing = true;
            ActiveShield = shield;
            _handled.Clear();
        }
        Log.Info($"blocker enforcing at shield {shield}");
    }

    public void StopEnforcing()
    {
        lock (_gate)
        {
            IsEnforcing = false;
            _handled.Clear();
        }
        Log.Info("blocker stood down");
    }

    /// <summary>True when local time falls inside the configured sleep window.</summary>
    public static bool IsWithinSleepWindow(AppSettings settings, DateTime? nowLocal = null)
    {
        if (!settings.IsSleepBlockEnabled) return false;

        var now = (nowLocal ?? DateTime.Now).TimeOfDay;
        var start = settings.SleepBlockStartTime;
        var end = settings.SleepBlockEndTime;

        // A window like 22:00 → 06:00 wraps past midnight.
        return start <= end
            ? now >= start && now < end
            : now >= start || now < end;
    }

    private void Tick()
    {
        AppSettings settings;
        bool enforcing;
        ShieldLevel shield;
        List<BlockedApp> candidates;

        lock (_gate)
        {
            settings = _settings;
            enforcing = IsEnforcing;
            shield = ActiveShield;
            candidates = _targets;          // snapshot reference; never mutated in place
        }

        // The sleep window enforces on its own, without a running sprint.
        var sleepActive = IsWithinSleepWindow(settings);
        if (!enforcing && !sleepActive) return;

        // A scheduled sleep block closes apps. Nudging at 2am helps nobody —
        // there is no one watching the screen to be nudged.
        if (sleepActive && !enforcing) shield = ShieldLevel.Firm;

        var targets = new Dictionary<string, BlockedApp>(StringComparer.OrdinalIgnoreCase);
        foreach (var app in candidates)
        {
            if (!app.IsEnabled || string.IsNullOrWhiteSpace(app.ProcessName)) continue;
            targets[app.ProcessName.Trim()] = app;
        }

        if (targets.Count == 0) return;

        foreach (var process in SafeGetProcesses())
        {
            try
            {
                var name = process.ProcessName;
                if (CriticalProcesses.Contains(name)) continue;
                if (!targets.TryGetValue(name, out var app)) continue;

                lock (_gate)
                {
                    if (!_handled.Add(process.Id)) continue;
                }

                var terminate = shield >= ShieldLevel.Firm || settings.HardKillModeEnabled;
                if (terminate)
                {
                    process.Kill(entireProcessTree: false);
                    Log.Info($"terminated blocked process {name} (pid {process.Id}) at shield {shield}");
                }
                else
                {
                    Log.Info($"nudged blocked process {name} (pid {process.Id}) at shield {shield}");
                }

                // BlockCount is bound to the UI, so it is incremented by the
                // subscriber on the dispatcher rather than from this thread.
                EnforcementCount++;
                Blocked?.Invoke(this,
                    new BlockEvent(app, name, app.DisplayName, shield, terminate, DateTime.UtcNow));
            }
            catch (Exception ex)
            {
                // Access denied on an elevated process is routine — log and move on.
                Log.Warn($"could not enforce on pid {Safe(() => process.Id)}: {ex.Message}");
            }
            finally
            {
                process.Dispose();
            }
        }
    }

    private static IEnumerable<Process> SafeGetProcesses()
    {
        try { return Process.GetProcesses(); }
        catch (Exception ex)
        {
            Log.Error("process enumeration failed", ex);
            return Array.Empty<Process>();
        }
    }

    private static string Safe(Func<int> f)
    {
        try { return f().ToString(); } catch { return "?"; }
    }

    public void Dispose()
    {
        _timer.Stop();
        _timer.Dispose();
        GC.SuppressFinalize(this);
    }
}
