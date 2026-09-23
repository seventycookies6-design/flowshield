using System.Windows.Threading;
using FlowShield.Models;
using Microsoft.Win32;

namespace FlowShield.Services;

/// <summary>
/// Runs the schedules (F6): a 15-second tick that asks <see cref="SchedulePlanner"/>
/// what is due and raises it. Deciding whether a start is allowed (terms,
/// first run, trial, a sprint already running) is the caller's job, through
/// the same gates as the Start button.
///
/// .NET caches the local time zone, so a zone change would leave every
/// schedule on the old zone's clock until a restart. Windows says when the
/// clock or the zone changes; the service then clears that cache and counts
/// from the change, so the jump is never read as time that passed.
/// </summary>
public sealed class ScheduleService
{
    public static readonly TimeSpan Interval = TimeSpan.FromSeconds(15);

    private readonly Func<IReadOnlyList<SprintSchedule>> _schedules;
    private readonly DispatcherTimer _timer = new() { Interval = Interval };
    private readonly HashSet<string> _headsUpShown = new(StringComparer.Ordinal);
    private DateTime _lastTickUtc;
    private bool _listening;

    public ScheduleService(Func<IReadOnlyList<SprintSchedule>> schedules)
    {
        _schedules = schedules;
        _timer.Tick += (_, _) => Tick(DateTime.UtcNow);
    }

    public event EventHandler<ScheduleAction>? Action;

    public void Start()
    {
        _lastTickUtc = DateTime.UtcNow;
        if (!_listening)
        {
            try
            {
                SystemEvents.TimeChanged += OnTimeChanged;
                _listening = true;
            }
            catch (Exception ex)
            {
                // Not fatal: schedules still run, on the zone this launch began in.
                Log.Warn($"schedules cannot follow clock changes: {ex.Message}");
            }
        }
        _timer.Start();
    }

    public void Stop()
    {
        _timer.Stop();
        if (!_listening) return;
        SystemEvents.TimeChanged -= OnTimeChanged;
        _listening = false;
    }

    public void Tick(DateTime nowUtc)
    {
        // A clock set backwards must not replay starts that already passed.
        if (nowUtc < _lastTickUtc) _lastTickUtc = nowUtc;

        var actions = SchedulePlanner.Decide(_schedules(), _lastTickUtc, nowUtc, TimeZoneInfo.Local, _headsUpShown);
        _lastTickUtc = nowUtc;

        foreach (var action in actions)
        {
            if (action.Kind == ScheduleActionKind.HeadsUp)
                _headsUpShown.Add(SchedulePlanner.HeadsUpKey(action.Schedule, action.StartUtc));
            Action?.Invoke(this, action);
        }
    }

    // Windows may raise this on its own thread; the tick runs on the timer's.
    private void OnTimeChanged(object? sender, EventArgs e) =>
        _timer.Dispatcher.BeginInvoke(ClockChanged);

    /// <summary>
    /// The clock or the time zone changed. Clears .NET's cached zone and
    /// counts from now, so a start the change passed over is neither replayed
    /// nor offered as missed.
    /// </summary>
    private void ClockChanged()
    {
        TimeZoneInfo.ClearCachedData();
        _lastTickUtc = DateTime.UtcNow;
        Log.Info("schedules: the clock or time zone changed; counting from now");
    }
}
