using System.Windows.Threading;
using FlowShield.Models;
using Microsoft.Win32;

namespace FlowShield.Services;

/// <summary>
/// Runs the schedules (F6): a 15-second tick (1 second under
/// <c>--short-schedules</c>) that asks <see cref="SchedulePlanner"/> what is
/// due and raises it. Deciding whether a start is allowed (terms, first run,
/// trial, a sprint already running) is the caller's job, through the same
/// gates as the Start button.
///
/// Every tick stamps its time on the settings
/// (<see cref="AppSettings.ScheduleLastCheckUtc"/>) before raising anything,
/// so a save that follows keeps it: a scheduled start saves settings, and so
/// does exit. The next launch counts from that stamp, so a start missed while
/// FlowShield was closed is inside the first tick's interval and the planner's
/// gap rule offers it, never starts it. A start handled before exit is at or
/// before the stamp of the tick that handled it, so it is never offered twice.
///
/// .NET caches the local time zone, so a zone change would leave every
/// schedule on the old zone's clock until a restart. Windows says when the
/// clock or the zone changes, and the service then clears that cache. It
/// does not restart its count there: Windows says the same on resume from
/// sleep and whenever its time sync steps the clock, and a restart would
/// erase the sleep gap (so no missed offer) and lose a start just before a
/// step. Every interval is in UTC, so a zone change can't replay one, and a
/// clock set forward is a gap like sleep: at most one missed offer.
///
/// The timer runs at Normal priority (#316). WPF's default, Background, sits
/// below input, rendering and the calls that serve UI Automation, and on a
/// busy UI thread that held ticks back for about a minute: past
/// <see cref="SchedulePlanner.OnTime"/> the planner reads that as a gap and
/// offers the start as missed. A tick is light (the planner, and a card
/// dropped when stale); a start it raises is the same work as the Start button.
/// </summary>
public sealed class ScheduleService
{
    public static TimeSpan Interval => SchedulePlanner.TickInterval;

    /// <summary>How far past its due time a tick may fire before it is logged.</summary>
    public static readonly TimeSpan LateTickThreshold = TimeSpan.FromSeconds(5);

    private readonly AppSettings _settings;
    private readonly DispatcherTimer _timer = new(DispatcherPriority.Normal);
    private readonly HashSet<string> _headsUpShown = new(StringComparer.Ordinal);
    private DateTime _lastTickUtc;
    private bool _listening;

    /// <summary>
    /// When the next tick is due, on <see cref="Environment.TickCount64"/>:
    /// the monotonic count the timer itself runs on, which a clock step
    /// doesn't move. Sleep does, so the first tick after waking is logged late.
    /// </summary>
    private long _dueMs;

    public ScheduleService(AppSettings settings)
    {
        _settings = settings;
        _timer.Tick += (_, _) => OnTimerTick();
    }

    public event EventHandler<ScheduleAction>? Action;

    /// <summary>
    /// Every tick, before anything is decided, with the tick's time. For
    /// housekeeping that runs on the clock rather than on a schedule: a card
    /// left up past its start goes stale whether or not anything is due.
    /// </summary>
    public event EventHandler<DateTime>? Ticked;

    public void Start()
    {
        var now = DateTime.UtcNow;
        _lastTickUtc = SchedulePlanner.SeedLastTick(_settings.ScheduleLastCheckUtc, now);
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
        _timer.Interval = Interval;
        _dueMs = Environment.TickCount64 + (long)Interval.TotalMilliseconds;
        _timer.Start();
    }

    public void Stop()
    {
        _timer.Stop();
        if (!_listening) return;
        SystemEvents.TimeChanged -= OnTimeChanged;
        _listening = false;
    }

    /// <summary>
    /// The timer's tick. One log line when it fires more than
    /// <see cref="LateTickThreshold"/> after it was due, so a starved timer
    /// can be told from a clock step (which moves the wall clock, not this
    /// count); nothing otherwise.
    /// </summary>
    private void OnTimerTick()
    {
        var late = TimeSpan.FromMilliseconds(Environment.TickCount64 - _dueMs);
        if (late > LateTickThreshold) Log.Info($"schedule tick {(long)late.TotalSeconds} s late");

        Tick(DateTime.UtcNow);

        // The timer counts its next interval from the end of this handler.
        _dueMs = Environment.TickCount64 + (long)_timer.Interval.TotalMilliseconds;
    }

    public void Tick(DateTime nowUtc)
    {
        // A clock set back counts from the new time: nothing between it and the
        // last tick is read as time that passed. A start the clock is set back
        // before is passed a second time, so it is raised again, like an alarm.
        if (nowUtc < _lastTickUtc) _lastTickUtc = nowUtc;

        // In memory only; the next save carries it (see the class comment).
        _settings.ScheduleLastCheckUtc = nowUtc;
        Ticked?.Invoke(this, nowUtc);

        var actions = SchedulePlanner.Decide(_settings.Schedules, _lastTickUtc, nowUtc, TimeZoneInfo.Local, _headsUpShown);
        _lastTickUtc = nowUtc;

        foreach (var action in actions)
        {
            if (action.Kind == ScheduleActionKind.HeadsUp)
                _headsUpShown.Add(SchedulePlanner.HeadsUpKey(action.Schedule, action.StartUtc));

            // One failing handler costs one log line, not the rest of the
            // tick: the count has already moved on, so an action dropped here
            // would never be raised again, and the exception would otherwise
            // reach the dispatcher's error dialog from a background tick.
            try
            {
                Action?.Invoke(this, action);
            }
            catch (Exception ex)
            {
                Log.Warn($"schedule {action.Kind} for {action.Schedule.Id} failed: {ex.Message}");
            }
        }
    }

    // Windows may raise this on its own thread; the tick runs on the timer's.
    // Queued at Send, the one priority above the timer's Normal, so the cache
    // is cleared before a tick that is already due.
    private void OnTimeChanged(object? sender, EventArgs e) =>
        _timer.Dispatcher.BeginInvoke(DispatcherPriority.Send, ClockChanged);

    /// <summary>
    /// The clock or the time zone changed. Clears .NET's cached zone so the
    /// next tick reads the new one. The count is left alone (see the class
    /// comment): the next tick still counts from the last one.
    /// </summary>
    private void ClockChanged()
    {
        TimeZoneInfo.ClearCachedData();
        Log.Info("schedules: the clock or time zone changed; reading the zone again");
    }
}
