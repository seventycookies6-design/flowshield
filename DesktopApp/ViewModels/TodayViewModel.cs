using System.Windows.Threading;
using FlowShield.Infrastructure;
using FlowShield.Models;
using FlowShield.Services;

namespace FlowShield.ViewModels;

public class TodayViewModel : ViewModelBase
{
    private readonly MainViewModel _main;
    private readonly DispatcherTimer _tick;

    private FocusSession? _current;
    private DateTime _endsAtUtc;

    /// <summary>
    /// Blocks enforced during the sprint currently running.
    ///
    /// Not the blocker's EnforcementCount, which counts everything since the
    /// process started — attributing that to one sprint inflated every session
    /// after the first.
    /// </summary>
    private int _blocksThisSprint;

    public TodayViewModel(MainViewModel main)
    {
        _main = main;

        _tick = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _tick.Tick += (_, _) => OnTick();

        StartCommand = new RelayCommand(StartSprint, () => !IsRunning);
        StopCommand = new RelayCommand(() => RequestEnd(), () => IsRunning);
        KeepGoingCommand = new RelayCommand(() => CloseEndPanel(keepGoing: true));
        EndAnywayCommand = new RelayCommand(EndAnyway);
        SaveJournalCommand = new RelayCommand(SaveJournal, () => JournalPromptVisible);

        RefreshStats();
    }

    private AppSettings S => _main.Settings;

    public RelayCommand StartCommand { get; }

    /// <summary>The end button: cancels, ends, or opens the end panel, depending on the shield (F2).</summary>
    public RelayCommand StopCommand { get; }

    public RelayCommand KeepGoingCommand { get; }
    public RelayCommand EndAnywayCommand { get; }
    public RelayCommand SaveJournalCommand { get; }

    // ------------------------------------------------------ ending a sprint (F2)

    /// <summary>Raised when an end panel opened by <see cref="RequestEnd"/> closes without ending.</summary>
    public event EventHandler? EndAbandoned;

    private DateTime _endUnlocksUtc;
    private EndFlow _endFlow;

    private bool _endPanelVisible;
    public bool EndPanelVisible
    {
        get => _endPanelVisible;
        private set
        {
            if (!Set(ref _endPanelVisible, value)) return;
            Raise(nameof(EndButtonVisible));
        }
    }

    public bool EndButtonVisible => IsRunning && !EndPanelVisible;

    private string _endPanelTitle = "";
    public string EndPanelTitle { get => _endPanelTitle; private set => Set(ref _endPanelTitle, value); }

    private string _endPanelText = "";
    public string EndPanelText { get => _endPanelText; private set => Set(ref _endPanelText, value); }

    private string _endCountdownText = "";
    public string EndCountdownText { get => _endCountdownText; private set => Set(ref _endCountdownText, value); }

    private bool _endAnywayEnabled;
    public bool EndAnywayEnabled { get => _endAnywayEnabled; private set => Set(ref _endAnywayEnabled, value); }

    public bool PhraseRequired => _endFlow == EndFlow.Sealed;

    public string SealedPhrase => EndSprintPolicy.SealedPhrase;

    private string _phraseText = "";
    public string PhraseText
    {
        get => _phraseText;
        set { if (Set(ref _phraseText, value)) UpdateEndPanel(); }
    }

    private TimeSpan Elapsed => _current is null ? TimeSpan.Zero : DateTime.UtcNow - _current.StartedUtc;

    /// <summary>The end button's label, which changes as the grace period runs out.</summary>
    public string EndButtonLabel => !IsRunning || _current is null
        ? "End sprint"
        : EndSprintPolicy.FlowFor(_current.Shield, Elapsed) switch
        {
            EndFlow.Cancel => "Cancel sprint",
            EndFlow.Immediate => "End sprint",
            EndFlow.Confirm => "End sprint…",
            _ => "I need to stop",
        };

    /// <summary>
    /// Start ending the running sprint the way its shield allows. Also used by
    /// the tray's Quit and by closing the window, so neither bypasses the flow.
    /// Returns true if the sprint ended straight away.
    /// </summary>
    public bool RequestEnd()
    {
        if (!IsRunning || _current is null) return true;
        if (EndPanelVisible) return false;

        _endFlow = EndSprintPolicy.FlowFor(_current.Shield, Elapsed);
        switch (_endFlow)
        {
            case EndFlow.Cancel:
                CancelSprint();
                return true;

            case EndFlow.Immediate:
                EndSprint(completed: false);
                return true;

            default:
                _endUnlocksUtc = DateTime.UtcNow + EndSprintPolicy.DelayFor(_endFlow);
                _phraseText = "";
                Raise(nameof(PhraseText));
                Raise(nameof(PhraseRequired));

                var left = (int)Math.Ceiling((_endsAtUtc - DateTime.UtcNow).TotalMinutes);
                var after = EndSprintPolicy.MomentumAfterEndingEarly(S.MomentumScore, _current.Shield);
                EndPanelTitle = _endFlow == EndFlow.Sealed ? "This sprint is sealed" : "End this sprint early?";
                EndPanelText =
                    $"{left} minute{(left == 1 ? "" : "s")} left. Ending now counts as ended early: " +
                    $"momentum {S.MomentumScore:0} → {after:0}." +
                    (_endFlow == EndFlow.Sealed
                        ? $" If you really need to stop, wait for the countdown, then type \"{EndSprintPolicy.SealedPhrase}\"."
                        : "");
                EndPanelVisible = true;
                UpdateEndPanel();
                Log.Info($"end requested: {_endFlow} flow at shield {_current.Shield}");
                return false;
        }
    }

    private void UpdateEndPanel()
    {
        if (!EndPanelVisible) return;

        var wait = _endUnlocksUtc - DateTime.UtcNow;
        var waited = wait <= TimeSpan.Zero;
        EndCountdownText = waited
            ? (PhraseRequired && !EndSprintPolicy.PhraseMatches(PhraseText) ? "Type the phrase to confirm." : "")
            : $"You can end it in {(int)Math.Ceiling(wait.TotalSeconds)} s.";
        EndAnywayEnabled = waited && (!PhraseRequired || EndSprintPolicy.PhraseMatches(PhraseText));
    }

    private void EndAnyway()
    {
        // Re-checked here, not only through the button's enabled state, so no
        // route (keyboard, automation) can end a sprint before the wait is over.
        UpdateEndPanel();
        if (!EndPanelVisible || !EndAnywayEnabled) return;
        CloseEndPanel(keepGoing: false);
        EndSprint(completed: false);
    }

    private void CloseEndPanel(bool keepGoing)
    {
        if (!EndPanelVisible) return;
        EndPanelVisible = false;
        EndAnywayEnabled = false;
        _phraseText = "";
        Raise(nameof(PhraseText));
        if (keepGoing)
        {
            Log.Info("end cancelled: kept going");
            EndAbandoned?.Invoke(this, EventArgs.Empty);
        }
    }

    /// <summary>Inside the grace period: stop with no penalty and leave no record.</summary>
    private void CancelSprint()
    {
        if (!IsRunning) return;

        _tick.Stop();
        IsRunning = false;
        _current = null;
        _main.Blocker.StopEnforcing();

        S.ActiveSprint = null;
        _main.SaveSettings();

        SessionStateText = "Sprint cancelled";
        JournalPromptVisible = false;
        Progress = 0;
        UpdateIdleDisplay();
        RefreshStats();
        _main.OnSprintStateChanged();
        Raise(nameof(EndButtonVisible));
        Log.Info("sprint cancelled within the grace period");
    }

    // ---------------------------------------------------------------- timer

    private bool _isRunning;
    public bool IsRunning
    {
        get => _isRunning;
        private set
        {
            if (!Set(ref _isRunning, value)) return;
            Raise(nameof(NotRunning));
            Raise(nameof(PrimaryActionLabel));
            Raise(nameof(SessionStateText));
            Raise(nameof(SealedRestartHintVisible));
            Raise(nameof(EndButtonVisible));
            Raise(nameof(EndButtonLabel));
        }
    }

    public bool NotRunning => !IsRunning;

    private string _remainingText = "25:00";
    public string RemainingText { get => _remainingText; private set => Set(ref _remainingText, value); }

    private double _progress;
    /// <summary>0→1 completion of the current sprint; drives the ring.</summary>
    public double Progress { get => _progress; private set => Set(ref _progress, value); }

    public string PrimaryActionLabel => IsRunning ? "End sprint" : "Start sprint";

    private string _sessionStateText = "Ready when you are";
    public string SessionStateText { get => _sessionStateText; private set => Set(ref _sessionStateText, value); }

    // ------------------------------------------------------------- controls

    public int[] SprintLengths { get; } = { 15, 25, 45, 60, 90 };

    private int _selectedMinutes = 25;
    public int SelectedMinutes
    {
        get => _selectedMinutes;
        set { if (Set(ref _selectedMinutes, value)) UpdateIdleDisplay(); }
    }

    public ShieldLevel[] ShieldLevels { get; } = { ShieldLevel.Soft, ShieldLevel.Firm, ShieldLevel.Sealed };

    private ShieldLevel _selectedShield = ShieldLevel.Firm;
    public ShieldLevel SelectedShield
    {
        get => _selectedShield;
        set
        {
            if (!Set(ref _selectedShield, value)) return;
            Raise(nameof(ShieldDescription));
            Raise(nameof(SealedRestartHintVisible));
        }
    }

    /// <summary>
    /// A Sealed sprint survives a reboot only if FlowShield starts again at
    /// sign-in, so say so before someone relies on it.
    /// </summary>
    public bool SealedRestartHintVisible =>
        !IsRunning && SelectedShield == ShieldLevel.Sealed && !S.StartWithWindows;

    public string ShieldDescription => SelectedShield switch
    {
        ShieldLevel.Soft => "Blocked apps get a nudge you can dismiss.",
        ShieldLevel.Firm => "Blocked apps are closed on sight.",
        _ => "Closed on sight, and the blocklist locks for the rest of the sprint.",
    };

    // ------------------------------------------------------------- journal

    private bool _journalPromptVisible;
    public bool JournalPromptVisible
    {
        get => _journalPromptVisible;
        private set => Set(ref _journalPromptVisible, value);
    }

    private string _journalText = "";
    public string JournalText { get => _journalText; set => Set(ref _journalText, value); }

    // --------------------------------------------------------------- stats

    private int _sessionsToday;
    public int SessionsToday { get => _sessionsToday; private set => Set(ref _sessionsToday, value); }

    private int _focusMinutesToday;
    public int FocusMinutesToday { get => _focusMinutesToday; private set => Set(ref _focusMinutesToday, value); }

    private int _blocksToday;
    public int BlocksToday { get => _blocksToday; private set => Set(ref _blocksToday, value); }

    private string _momentumText = "0";
    public string MomentumText { get => _momentumText; private set => Set(ref _momentumText, value); }

    private string _streakText = "0 days";
    public string StreakText { get => _streakText; private set => Set(ref _streakText, value); }

    // -------------------------------------------------------------- actions

    public void TogglePrimary()
    {
        if (IsRunning) RequestEnd();
        else StartSprint();
    }

    private void StartSprint()
    {
        if (IsRunning) return;

        // The lock screen covers this button once the trial ends, but the tray
        // menu and keyboard can still reach it.
        if (_main.IsLocked)
        {
            _main.Toast("Your free trial has ended. Buy FlowShield to start a sprint.");
            return;
        }

        var now = DateTime.UtcNow;
        _current = new FocusSession
        {
            StartedUtc = now,
            PlannedMinutes = SelectedMinutes,
            Shield = SelectedShield,
        };

        // Saved before enforcement begins, so a crash one second in still
        // leaves a sprint to resume.
        S.ActiveSprint = new RunningSprint
        {
            StartedUtc = now,
            PlannedMinutes = SelectedMinutes,
            Shield = SelectedShield,
            LastSeenUtc = now,
        };
        _main.SaveSettings();

        BeginRunning($"Shield {Roman(SelectedShield)} engaged");
        Log.Info($"sprint started: {SelectedMinutes}m at shield {SelectedShield}");
    }

    private void BeginRunning(string stateText)
    {
        _endsAtUtc = _current!.StartedUtc.AddMinutes(_current.PlannedMinutes);
        _lastHeartbeatUtc = DateTime.UtcNow;
        _blocksThisSprint = 0;
        IsRunning = true;
        SessionStateText = stateText;
        JournalPromptVisible = false;

        _main.Blocker.BeginEnforcing(_current.Shield);
        _main.OnSprintStateChanged();

        OnTick();
        _tick.Start();
    }

    /// <summary>How often a running sprint re-saves that FlowShield is still watching it.</summary>
    public static readonly TimeSpan HeartbeatInterval = TimeSpan.FromSeconds(30);

    private DateTime _lastHeartbeatUtc;

    /// <summary>
    /// Pick up a sprint that was running when FlowShield last closed (F3).
    ///
    /// Called once at startup. With time left, the sprint carries on with its
    /// shield, so a Sealed blocklist stays locked. If the time ran out while
    /// FlowShield was closed, it is recorded as finished or interrupted
    /// according to <see cref="RunningSprint.Decide"/>.
    /// </summary>
    public void ResumeInterruptedSprint(DateTime? nowUtc = null)
    {
        var saved = S.ActiveSprint;
        if (saved is null || IsRunning) return;

        var now = nowUtc ?? DateTime.UtcNow;
        var decision = saved.Decide(now);
        Log.Info($"found a saved sprint from {saved.StartedUtc:u} ({saved.PlannedMinutes}m, {saved.Shield}): {decision}");

        switch (decision)
        {
            case SprintResume.Resume:
                _current = new FocusSession
                {
                    StartedUtc = saved.StartedUtc,
                    PlannedMinutes = saved.PlannedMinutes,
                    Shield = saved.Shield,
                };
                _selectedMinutes = saved.PlannedMinutes;
                _selectedShield = saved.Shield;
                Raise(nameof(SelectedMinutes));
                Raise(nameof(SelectedShield));
                Raise(nameof(ShieldDescription));

                saved.LastSeenUtc = now;
                _main.SaveSettings();

                var left = (int)Math.Ceiling((saved.EndsUtc - now).TotalMinutes);
                BeginRunning($"Sprint resumed — shield {Roman(saved.Shield)}");
                _main.Toast($"Sprint resumed — {left} minute{(left == 1 ? "" : "s")} left.");
                break;

            case SprintResume.RecordCompleted:
            case SprintResume.RecordInterrupted:
                var completed = decision == SprintResume.RecordCompleted;
                var session = new FocusSession
                {
                    StartedUtc = saved.StartedUtc,
                    EndedUtc = saved.EndsUtc,
                    PlannedMinutes = saved.PlannedMinutes,
                    Shield = saved.Shield,
                    Completed = completed,
                    Interrupted = !completed,
                };
                if (completed) ApplyMomentum(completed: true, session);

                S.Sessions.Add(session);
                S.ActiveSprint = null;
                _main.SaveSettings();
                RefreshStats();

                SessionStateText = completed ? "Sprint finished while FlowShield was closed" : "Sprint interrupted";
                _main.Toast(completed
                    ? "Your last sprint finished while FlowShield was closed."
                    : "Your last sprint was interrupted — FlowShield wasn't running for most of it.");
                break;

            default:
                S.ActiveSprint = null;
                _main.SaveSettings();
                break;
        }
    }

    private void OnTick()
    {
        var now = DateTime.UtcNow;
        var remaining = _endsAtUtc - now;
        if (remaining <= TimeSpan.Zero)
        {
            EndSprint(completed: true);
            return;
        }

        Raise(nameof(EndButtonLabel));
        UpdateEndPanel();

        if (S.ActiveSprint is not null && now - _lastHeartbeatUtc >= HeartbeatInterval)
        {
            _lastHeartbeatUtc = now;
            S.ActiveSprint.LastSeenUtc = now;
            _main.SaveSettings();
        }

        RemainingText = remaining.TotalHours >= 1
            ? $"{(int)remaining.TotalHours}:{remaining.Minutes:00}:{remaining.Seconds:00}"
            : $"{(int)remaining.TotalMinutes:00}:{remaining.Seconds:00}";

        var total = TimeSpan.FromMinutes(_current?.PlannedMinutes ?? SelectedMinutes).TotalSeconds;
        Progress = total <= 0 ? 0 : Math.Clamp(1 - remaining.TotalSeconds / total, 0, 1);
    }

    private void EndSprint(bool completed)
    {
        if (!IsRunning || _current is null) return;

        _tick.Stop();
        CloseEndPanel(keepGoing: false);
        IsRunning = false;

        _current.EndedUtc = DateTime.UtcNow;
        _current.Completed = completed;
        _current.BlocksEnforced = _blocksThisSprint;

        _main.Blocker.StopEnforcing();

        ApplyMomentum(completed, _current);

        S.Sessions.Add(_current);
        S.ActiveSprint = null;
        _main.SaveSettings();

        SessionStateText = completed ? "Sprint complete" : "Sprint ended early";
        JournalPromptVisible = true;
        JournalText = "";
        Progress = completed ? 1 : Progress;
        UpdateIdleDisplay();
        RefreshStats();
        _main.OnSprintStateChanged();

        Log.Info($"sprint ended: completed={completed} momentum={S.MomentumScore:0.0}");
    }

    /// <summary>
    /// Momentum compounds on completion and decays — not resets — on an
    /// abandoned sprint. A single bad afternoon shouldn't erase a month.
    /// </summary>
    private void ApplyMomentum(bool completed, FocusSession session)
    {
        var today = DateTime.Now.Date;

        if (completed)
        {
            var weight = Math.Clamp(session.PlannedMinutes / 25.0, 0.5, 3.0);
            S.MomentumScore = Math.Round(S.MomentumScore + 10 * weight, 1);

            if (S.LastSessionDayLocal is null) S.CurrentStreak = 1;
            else
            {
                var gap = (today - S.LastSessionDayLocal.Value.Date).Days;
                S.CurrentStreak = gap switch
                {
                    0 => Math.Max(S.CurrentStreak, 1),
                    1 => S.CurrentStreak + 1,
                    _ => 1,
                };
            }
            S.LastSessionDayLocal = today;
        }
        else
        {
            S.MomentumScore = EndSprintPolicy.MomentumAfterEndingEarly(S.MomentumScore, session.Shield);
        }
    }

    private void SaveJournal()
    {
        var last = S.Sessions.LastOrDefault();
        if (last is not null) last.Journal = (JournalText ?? "").Trim();
        _main.SaveSettings();
        JournalPromptVisible = false;
        _main.Toast("Logged.");
    }

    public void UpdateIdleDisplay()
    {
        if (IsRunning) return;
        RemainingText = $"{SelectedMinutes:00}:00";
        Progress = 0;
    }

    /// <summary>Counts one enforcement against the running sprint.</summary>
    public void RecordBlock()
    {
        if (IsRunning) _blocksThisSprint++;
    }

    public void RefreshStats()
    {
        var today = DateTime.Now.Date;
        var todays = S.Sessions.Where(s => s.StartedUtc.ToLocalTime().Date == today).ToList();

        SessionsToday = todays.Count(s => s.Completed);
        FocusMinutesToday = (int)Math.Round(todays.Sum(s => s.ActualMinutes));

        // Today's blocks, not every block this install has ever made — that
        // lifetime total was being shown under a "TODAY" heading.
        BlocksToday = S.BlocksTodayCurrent;

        MomentumText = S.MomentumScore.ToString("0");
        StreakText = S.CurrentStreak == 1 ? "1 day" : $"{S.CurrentStreak} days";
        Raise(nameof(SealedRestartHintVisible));
    }

    /// <summary>Called when access changes (purchase, deactivation, trial ending).</summary>
    public void OnTierChanged()
    {
        Raise(nameof(SelectedShield));
        Raise(nameof(ShieldDescription));
    }

    private static string Roman(ShieldLevel level) => level switch
    {
        ShieldLevel.Soft => "I",
        ShieldLevel.Firm => "II",
        _ => "III",
    };
}
