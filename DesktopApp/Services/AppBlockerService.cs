using System.Diagnostics;
using FlowShield.Models;

namespace FlowShield.Services;

/// <summary>What the shield did about a blocked app this time (F7).</summary>
public enum BlockOutcome
{
    /// <summary>Soft: noted, nothing closed.</summary>
    Noted,

    /// <summary>Firm and above: asked to close, with a grace period before the kill.</summary>
    Closing,

    /// <summary>Gone — it closed itself, or the grace period ran out, or hard kill.</summary>
    Closed,
}

public record BlockEvent(
    BlockedApp App,
    string ProcessName,
    string DisplayName,
    ShieldLevel Shield,
    bool Terminated,
    DateTime AtUtc,
    BlockOutcome Outcome = BlockOutcome.Noted,

    /// <summary>
    /// False for the follow-up kill after a grace period: the sighting was
    /// already counted when the warning went out, and counting it twice would
    /// undo #138.
    /// </summary>
    bool CountsAsDistraction = true);

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

    /// <summary>
    /// Blocklist entries that had at least one process running last sweep.
    ///
    /// "Distractions blocked" is a count the customer reads as "times something
    /// tried to pull me away", so it counts *apps*, not processes. Steam runs
    /// seven of them; closing it once was reporting seven distractions, and the
    /// number grew with however many processes an app happened to spawn rather
    /// than with anything the customer did. An entry counts when it appears,
    /// and cannot count again until it has gone away.
    /// </summary>
    private readonly HashSet<string> _present = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>
    /// Blocklist entries that have been asked to close, and when their grace
    /// period runs out (F7, roadmap 1.8).
    ///
    /// The sweep already runs every two seconds, so the deadline is checked
    /// there rather than on a timer per app: fewer moving parts, and an app
    /// that closes itself in the meantime simply never comes back round.
    /// </summary>
    private readonly Dictionary<string, DateTime> _closingAt =
        new(StringComparer.OrdinalIgnoreCase);

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
            _present.Clear();
            _closingAt.Clear();
        }
        Log.Info($"blocker enforcing at shield {shield}");
    }

    public void StopEnforcing()
    {
        lock (_gate)
        {
            IsEnforcing = false;
            _handled.Clear();
            _present.Clear();
            _closingAt.Clear();
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
            if (!app.IsEnabled) continue;
            foreach (var processName in app.AllProcessNames) targets[processName] = app;
        }

        if (targets.Count == 0) return;

        // Grouped by blocklist entry rather than walked process by process.
        // Closing gracefully is a decision about an *app* — warn once, ask all
        // of its windows to close, kill whatever is left when the grace period
        // runs out — and the old per-process loop could not express that: its
        // pid bookkeeping skipped a process it had already seen, which is
        // exactly the process the deadline needs to come back and kill.
        var running = new Dictionary<string, (BlockedApp App, List<Process> Processes)>(
            StringComparer.OrdinalIgnoreCase);

        foreach (var process in SafeGetProcesses())
        {
            var keep = false;
            try
            {
                var name = process.ProcessName;
                if (CriticalProcesses.Contains(name)) continue;
                if (!targets.TryGetValue(name, out var app)) continue;

                if (!running.TryGetValue(app.DisplayName, out var entry))
                {
                    entry = (app, new List<Process>());
                    running[app.DisplayName] = entry;
                }
                entry.Processes.Add(process);
                keep = true;
            }
            catch (Exception ex)
            {
                Log.Warn($"could not inspect pid {Safe(() => process.Id)}: {ex.Message}");
            }
            finally
            {
                if (!keep) process.Dispose();
            }
        }

        try
        {
            var hardKill = settings.HardKillModeEnabled;
            var terminate = shield >= ShieldLevel.Firm || hardKill;
            var graceful = GracefulClose.IsGraceful(shield, hardKill);
            var now = DateTime.UtcNow;

            foreach (var (key, entry) in running)
            {
                var app = entry.App;
                var processes = entry.Processes;

                bool firstSighting;
                lock (_gate) firstSighting = _present.Add(key);

                if (!terminate)
                {
                    // Soft notes it and leaves it alone.
                    Log.Info($"nudged blocked app {key} at shield {shield}");
                    if (firstSighting) Report(app, processes, shield, BlockOutcome.Noted, counts: true);
                    continue;
                }

                if (!graceful)
                {
                    // Hard kill is instant by design: someone who turned it on
                    // asked for no way round it, and ten seconds is a way round it.
                    KillAll(processes, shield);
                    if (firstSighting) Report(app, processes, shield, BlockOutcome.Closed, counts: true);
                    continue;
                }

                DateTime deadline;
                bool alreadyClosing;
                lock (_gate) alreadyClosing = _closingAt.TryGetValue(key, out deadline);

                if (!alreadyClosing)
                {
                    // Ask first. CloseMainWindow sends the same request the
                    // window's own close button does, so an app with unsaved
                    // work gets to put its "save before closing?" prompt up.
                    foreach (var process in processes)
                    {
                        try
                        {
                            if (process.CloseMainWindow())
                                Log.Info($"asked {process.ProcessName} (pid {process.Id}) to close");
                        }
                        catch (Exception ex)
                        {
                            Log.Warn($"could not ask pid {Safe(() => process.Id)} to close: {ex.Message}");
                        }
                    }

                    lock (_gate) _closingAt[key] = now + GracefulClose.Grace;
                    Log.Info($"{key} blocked at shield {shield}; closing in {GracefulClose.Grace.TotalSeconds:0} s");

                    // Counted here rather than at the kill: the distraction
                    // happened when the app appeared, and an app that takes the
                    // hint and closes itself must still count.
                    if (firstSighting) Report(app, processes, shield, BlockOutcome.Closing, counts: true);
                    continue;
                }

                if (now < deadline) continue;   // still saving; leave it alone

                KillAll(processes, shield);
                lock (_gate) _closingAt.Remove(key);
                // Not counted again: the sighting was counted when it was warned.
                Report(app, processes, shield, BlockOutcome.Closed, counts: false);
            }

            // Entries with nothing running any more are forgotten, so reopening
            // one counts as a fresh distraction — which is what the label
            // promises — and a half-finished close never outlives the app.
            lock (_gate)
            {
                _present.IntersectWith(running.Keys);
                foreach (var gone in _closingAt.Keys.Where(k => !running.ContainsKey(k)).ToList())
                    _closingAt.Remove(gone);
            }
        }
        finally
        {
            foreach (var entry in running.Values)
                foreach (var process in entry.Processes)
                    process.Dispose();
        }
    }

    private void KillAll(List<Process> processes, ShieldLevel shield)
    {
        foreach (var process in processes)
        {
            try
            {
                if (process.HasExited) continue;
                process.Kill(entireProcessTree: false);
                Log.Info($"terminated blocked process {process.ProcessName} (pid {process.Id}) at shield {shield}");
            }
            catch (Exception ex)
            {
                // Access denied on an elevated process is routine — log and move on.
                Log.Warn($"could not close pid {Safe(() => process.Id)}: {ex.Message}");
            }
        }
    }

    private void Report(BlockedApp app, List<Process> processes, ShieldLevel shield,
                        BlockOutcome outcome, bool counts)
    {
        var name = processes.Count > 0 ? SafeName(processes[0]) : app.ProcessName;
        if (counts) EnforcementCount++;

        // BlockCount is bound to the UI, so it is incremented by the subscriber
        // on the dispatcher rather than from this thread.
        Blocked?.Invoke(this, new BlockEvent(
            app, name, app.DisplayName, shield,
            Terminated: outcome != BlockOutcome.Noted,
            AtUtc: DateTime.UtcNow,
            Outcome: outcome,
            CountsAsDistraction: counts));
    }

    private static string SafeName(Process process)
    {
        try { return process.ProcessName; }
        catch { return ""; }
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
