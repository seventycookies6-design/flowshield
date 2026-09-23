using System.Diagnostics;
using System.Runtime.InteropServices;
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
/// What is in front right now, while the Soft shield is up (F7, roadmap 1.7).
///
/// <see cref="DisplayName"/> is the blocked app's name when the foreground
/// window belongs to one, and null when it belongs to anything else — which is
/// how the Soft notice knows to come down again. FlowShield's own windows are
/// never reported at all, so the notice never reacts to itself.
/// </summary>
public record ForegroundSighting(string? DisplayName, IntPtr Window, DateTime AtUtc);

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
    /// Private snapshot of the active profile's blocklist, rebuilt whenever
    /// settings change (F9: only the active profile is ever enforced — the other
    /// profiles are lists the customer keeps, not lists the shield acts on).
    ///
    /// The timer thread must never enumerate <c>AppSettings.BlockedApps</c>
    /// directly: the UI thread adds to and removes from that same List, and an
    /// enumeration racing a mutation throws "Collection was modified" from
    /// inside a timer callback — where there is no good place to catch it.
    /// The copy is shallow on purpose, so the BlockedApp instances are still
    /// the ones the UI is bound to.
    /// </summary>
    private List<BlockedApp> _targets = new();

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

    /// <summary>
    /// Raised each sweep while the Soft shield is up, saying whether a blocked
    /// app is the foreground window (F7, roadmap 1.7). Never raised at Firm,
    /// Sealed or with hard kill on: those close the app instead.
    /// </summary>
    public event EventHandler<ForegroundSighting>? SoftForeground;

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
        _targets = settings.ActiveProfile.Apps.ToList();

        _timer = new System.Timers.Timer(2000) { AutoReset = true };
        _timer.Elapsed += (_, _) => Tick();
        _timer.Start();
    }

    /// <summary>
    /// Republish settings to the watcher. Must be called on the UI thread after
    /// any change to the blocklist, or after the active profile changes — it is
    /// what refreshes the private snapshot.
    /// </summary>
    public void UpdateSettings(AppSettings settings)
    {
        lock (_gate)
        {
            _settings = settings;
            _targets = settings.ActiveProfile.Apps.ToList();
        }
    }

    /// <summary>
    /// Blocked apps that are running right now, by display name (F7,
    /// roadmap 1.8).
    ///
    /// Used before a sprint starts, to tell the customer what is about to be
    /// closed while they can still do something about it. Read-only: it
    /// enforces nothing and changes nothing.
    /// </summary>
    public IReadOnlyList<string> RunningBlockedApps(AppSettings settings)
    {
        var targets = new Dictionary<string, BlockedApp>(StringComparer.OrdinalIgnoreCase);
        foreach (var app in settings.ActiveProfile.Apps)
        {
            if (!app.IsEnabled) continue;
            foreach (var processName in app.AllProcessNames) targets[processName] = app;
        }
        if (targets.Count == 0) return Array.Empty<string>();

        var found = new List<string>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var process in SafeGetProcesses())
        {
            try
            {
                var name = process.ProcessName;
                if (CriticalProcesses.Contains(name)) continue;
                if (!targets.TryGetValue(name, out var app)) continue;
                // One line per app, not per process — the same reason #138
                // counts apps: "Steam, Steam, Steam, Steam" is not a list.
                if (seen.Add(app.DisplayName)) found.Add(app.DisplayName);
            }
            catch
            {
                // A process that vanished mid-enumeration is not worth a log line.
            }
            finally
            {
                process.Dispose();
            }
        }

        found.Sort(StringComparer.CurrentCultureIgnoreCase);
        return found;
    }

    /// <summary>
    /// The Soft notice's "Close Discord" button (1.0.10). The user chose it;
    /// Soft never closes anything on its own. Asks every running process of
    /// that app to close, the way its own close button would, so unsaved work
    /// gets its "save changes?" prompt. Never kills, and never touches a
    /// critical process. Returns how many processes accepted the close
    /// request: 0 when none has a main window to close (an app hidden in the
    /// tray, or one whose main window is disabled behind its own prompt), when
    /// the app is not running, or when it is no longer on the active
    /// blocklist. 0 is not a failure; the caller says so in the log.
    /// </summary>
    public int AskToClose(string displayName, AppSettings settings)
    {
        var app = settings.ActiveProfile.Apps.FirstOrDefault(a =>
            a.IsEnabled && string.Equals(a.DisplayName, displayName, StringComparison.OrdinalIgnoreCase));
        if (app is null) return 0;

        var names = new HashSet<string>(app.AllProcessNames, StringComparer.OrdinalIgnoreCase);
        var asked = 0;
        foreach (var process in SafeGetProcesses())
        {
            try
            {
                var name = process.ProcessName;
                if (CriticalProcesses.Contains(name) || !names.Contains(name)) continue;
                if (process.CloseMainWindow())
                {
                    asked++;
                    Log.Info($"soft: asked {name} (pid {process.Id}) to close, as the user chose");
                }
            }
            catch (Exception ex)
            {
                Log.Warn($"soft: could not ask pid {Safe(() => process.Id)} to close: {ex.Message}");
            }
            finally
            {
                process.Dispose();
            }
        }
        return asked;
    }

    public void BeginEnforcing(ShieldLevel shield)
    {
        lock (_gate)
        {
            IsEnforcing = true;
            ActiveShield = shield;
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
        if (!enforcing && !sleepActive)
        {
            // Nothing is being enforced, so forget what was seen. A sprint
            // clears this through StopEnforcing; the sleep window has no such
            // moment, and the per-tick cleanup below never runs on the tick
            // that closes it. A deadline left over from 06:00 made the first
            // sweep of the next night kill the app on sight — no warning, no
            // seconds to save — and _present kept the sighting from counting.
            lock (_gate)
            {
                _present.Clear();
                _closingAt.Clear();
            }
            return;
        }

        // A scheduled sleep block closes apps. Nudging at 2am helps nobody —
        // there is no one watching the screen to be nudged. That is the
        // window's floor, not the sprint's: a Soft sprint running through the
        // night used to switch the nightly shield off entirely, which is less
        // enforcement than no sprint at all.
        if (sleepActive && shield < ShieldLevel.Firm) shield = ShieldLevel.Firm;

        var targets = new Dictionary<string, BlockedApp>(StringComparer.OrdinalIgnoreCase);
        foreach (var app in candidates)
        {
            if (!app.IsEnabled) continue;
            foreach (var processName in app.AllProcessNames) targets[processName] = app;
        }

        if (targets.Count == 0)
        {
            // #269: an empty profile has no pending enforcement state.
            lock (_gate)
            {
                _present.Clear();
                _closingAt.Clear();
            }
            return;
        }

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

            // Soft's only intervention is the notice, so it is the only shield
            // that looks at what is in front. Firm and Sealed close the app;
            // asking them to also put a full-screen panel over it would be
            // covering a window that is about to disappear.
            if (!terminate) ReportForeground(targets);

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

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    /// <summary>
    /// Says whether the foreground window belongs to a blocked app (F7,
    /// roadmap 1.7).
    ///
    /// Deliberately the timid version of this: two user-level calls that read
    /// which window has focus and which process owns it. No hooks, no injection
    /// into another process, nothing that needs a driver or admin rights — the
    /// same restraint as the rest of the blocker. It reads; it never acts.
    /// </summary>
    private void ReportForeground(Dictionary<string, BlockedApp> targets)
    {
        if (SoftForeground is null) return;

        var window = GetForegroundWindow();
        if (window == IntPtr.Zero) return;

        if (GetWindowThreadProcessId(window, out var pid) == 0 || pid == 0) return;

        // FlowShield's own windows — including the notice itself — are not a
        // sighting and not an absence of one. Reporting them would make the
        // notice close itself the moment it took focus.
        if (pid == (uint)Environment.ProcessId) return;

        string name;
        try
        {
            using var process = Process.GetProcessById((int)pid);
            name = process.ProcessName;
        }
        catch
        {
            // The window's process went away between the two calls.
            return;
        }

        var blocked = !CriticalProcesses.Contains(name) && targets.TryGetValue(name, out var app)
            ? app.DisplayName
            : null;

        SoftForeground.Invoke(this, new ForegroundSighting(blocked, window, DateTime.UtcNow));
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
