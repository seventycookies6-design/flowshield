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
        StopCommand = new RelayCommand(() => EndSprint(completed: false), () => IsRunning);
        SaveJournalCommand = new RelayCommand(SaveJournal, () => JournalPromptVisible);

        RefreshStats();
    }

    private AppSettings S => _main.Settings;

    public RelayCommand StartCommand { get; }
    public RelayCommand StopCommand { get; }
    public RelayCommand SaveJournalCommand { get; }

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
        set
        {
            // Free tier caps sprint length; snap back and explain rather than
            // silently accepting a value we won't honour.
            if (!_main.IsPro && value > AppSettings.FreeMaxSprintMinutes)
            {
                _main.Toast($"Sprints longer than {AppSettings.FreeMaxSprintMinutes} minutes are a Pro feature.");
                Set(ref _selectedMinutes, AppSettings.FreeMaxSprintMinutes);
                Raise(nameof(SelectedMinutes));
                UpdateIdleDisplay();
                return;
            }
            if (Set(ref _selectedMinutes, value)) UpdateIdleDisplay();
        }
    }

    public ShieldLevel[] ShieldLevels { get; } = { ShieldLevel.Soft, ShieldLevel.Firm, ShieldLevel.Sealed };

    private ShieldLevel _selectedShield = ShieldLevel.Firm;
    public ShieldLevel SelectedShield
    {
        get => _selectedShield;
        set
        {
            if (value == ShieldLevel.Sealed && !_main.IsPro)
            {
                _main.Toast("Shield III — Sealed is a Pro feature.");
                Set(ref _selectedShield, ShieldLevel.Firm);
                Raise(nameof(SelectedShield));
                Raise(nameof(ShieldDescription));
                return;
            }
            if (Set(ref _selectedShield, value)) Raise(nameof(ShieldDescription));
        }
    }

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
        if (IsRunning) EndSprint(completed: false);
        else StartSprint();
    }

    private void StartSprint()
    {
        if (IsRunning) return;

        _current = new FocusSession
        {
            StartedUtc = DateTime.UtcNow,
            PlannedMinutes = SelectedMinutes,
            Shield = SelectedShield,
        };

        _endsAtUtc = _current.StartedUtc.AddMinutes(SelectedMinutes);
        _blocksThisSprint = 0;
        IsRunning = true;
        SessionStateText = $"Shield {Roman(SelectedShield)} engaged";
        JournalPromptVisible = false;

        _main.Blocker.BeginEnforcing(SelectedShield);
        _main.OnSprintStateChanged();

        OnTick();
        _tick.Start();
        Log.Info($"sprint started: {SelectedMinutes}m at shield {SelectedShield}");
    }

    private void OnTick()
    {
        var remaining = _endsAtUtc - DateTime.UtcNow;
        if (remaining <= TimeSpan.Zero)
        {
            EndSprint(completed: true);
            return;
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
        IsRunning = false;

        _current.EndedUtc = DateTime.UtcNow;
        _current.Completed = completed;
        _current.BlocksEnforced = _blocksThisSprint;

        _main.Blocker.StopEnforcing();

        ApplyMomentum(completed, _current);

        S.Sessions.Add(_current);
        // Free tier keeps a week of history; Pro keeps everything.
        if (!_main.IsPro)
        {
            var cutoff = DateTime.UtcNow.AddDays(-7);
            S.Sessions.RemoveAll(s => s.StartedUtc < cutoff);
        }

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
            S.MomentumScore = Math.Round(Math.Max(0, S.MomentumScore * 0.85 - 2), 1);
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
    }

    /// <summary>Called when the Pro tier changes so gated choices re-evaluate.</summary>
    public void OnTierChanged()
    {
        if (!_main.IsPro)
        {
            if (SelectedShield == ShieldLevel.Sealed) SelectedShield = ShieldLevel.Firm;
            if (SelectedMinutes > AppSettings.FreeMaxSprintMinutes)
                SelectedMinutes = AppSettings.FreeMaxSprintMinutes;
        }
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
