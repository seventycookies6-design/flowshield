using System.Windows.Controls;
using System.Windows.Input;
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
    private int _closedThisSprint;
    private int _nudgesThisSprint;

    public TodayViewModel(MainViewModel main)
    {
        _main = main;

        _tick = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _tick.Tick += (_, _) => OnTick();

        StartCommand = new RelayCommand(StartSprint, CanStart);
        StopCommand = new RelayCommand(() => RequestEnd(), () => IsRunning);
        KeepGoingCommand = new RelayCommand(() => CloseEndPanel(keepGoing: true));
        EndAnywayCommand = new RelayCommand(EndAnyway);
        SaveJournalCommand = new RelayCommand(SaveJournal, () => JournalPromptVisible);
        GetProCommand = new RelayCommand(() => _main.OpenUpgradePage());

        // F4: Space on Today starts or ends the sprint, the same as clicking
        // StartSprintButton/StopSprintButton. Guarded so a space typed into
        // the intention field (or any text box) never also toggles a sprint.
        ToggleOrEndCommand = new RelayCommand(TogglePrimary, CanUseSpaceShortcut);

        // F4: Shift+1/2/3 pick a shield, the same as clicking the segmented
        // buttons — Ctrl+1..5 is reserved for page navigation (issue #37).
        SelectShieldSoftCommand = new RelayCommand(() => SelectedShield = ShieldLevel.Soft, CanChangeShield);
        SelectShieldFirmCommand = new RelayCommand(() => SelectedShield = ShieldLevel.Firm, CanChangeShield);
        SelectShieldSealedCommand = new RelayCommand(() => SelectedShield = ShieldLevel.Sealed, CanChangeShield);

        // F5: breaks and cycles. Three buttons on the summary card and the
        // cycle chooser above it; every rule they follow lives in CycleState.
        StartBreakCommand = new RelayCommand(StartBreak, () => BreakOfferVisible && !IsOnBreak);
        SkipBreakCommand = new RelayCommand(SkipBreak, () => BreakOfferVisible || IsOnBreak);
        StartNextSprintCommand = new RelayCommand(StartNextSprint, () => BreakOfferVisible || IsOnBreak);

        _customMinutesText = S.LastCustomSprintMinutes.ToString();
        _customMinutes = S.LastCustomSprintMinutes;
        _cycleSprints = S.CycleSprints;

        RefreshStats();
    }

    private AppSettings S => _main.Settings;

    public RelayCommand StartCommand { get; }

    /// <summary>The end button: cancels, ends, or opens the end panel, depending on the shield (F2).</summary>
    public RelayCommand StopCommand { get; }

    public RelayCommand KeepGoingCommand { get; }
    public RelayCommand EndAnywayCommand { get; }
    public RelayCommand SaveJournalCommand { get; }

    /// <summary>Space on Today (F4): the same TogglePrimary the tray's Start/End reuses.</summary>
    public RelayCommand ToggleOrEndCommand { get; }

    /// <summary>Shift+1/2/3 on Today (F4).</summary>
    public RelayCommand SelectShieldSoftCommand { get; }
    public RelayCommand SelectShieldFirmCommand { get; }
    public RelayCommand SelectShieldSealedCommand { get; }

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

        // Cancelling inside the grace period leaves no record, but it does stop
        // a cycle: the sprint it was part of never happened (F5).
        _cycle = _cycle.OnSprintAbandoned();
        BreakOfferVisible = false;

        S.ActiveSprint = null;
        _main.SaveSettings();

        SessionStateText = "Sprint cancelled";
        Raise(nameof(CycleProgressText));
        Raise(nameof(CycleProgressVisible));
        JournalPromptVisible = false;
        IntentionDisplayText = "";
        IntentionDisplayVisible = false;
        IntentionText = "";
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
            Raise(nameof(SprintRingVisible));
            Raise(nameof(PrimaryActionLabel));
            Raise(nameof(SessionStateText));
            Raise(nameof(SealedRestartHintVisible));
            Raise(nameof(SoftHardKillHintVisible));
            Raise(nameof(EndButtonVisible));
            Raise(nameof(EndButtonLabel));
            Raise(nameof(CanSwitchProfile));
        }
    }

    public bool NotRunning => !IsRunning;

    /// <summary>
    /// When the running sprint is due to finish, in UTC. Default when nothing is
    /// running. Read by the Soft notice (F7), which names the time the blocklist
    /// holds until.
    /// </summary>
    public DateTime EndsAtUtc => _endsAtUtc;

    private TimeSpan _remaining;
    /// <summary>Time left in the running sprint; drives the tray countdown (F19).</summary>
    public TimeSpan Remaining { get => _remaining; private set => Set(ref _remaining, value); }

    private string _remainingText = "25:00";
    public string RemainingText { get => _remainingText; private set => Set(ref _remainingText, value); }

    private double _progress;
    /// <summary>0→1 completion of the current sprint — or break (F5); drives the ring.</summary>
    public double Progress
    {
        get => _progress;
        private set
        {
            if (!Set(ref _progress, value)) return;
            Raise(nameof(SprintRingVisible));
            Raise(nameof(BreakRingVisible));
        }
    }

    public string PrimaryActionLabel => IsRunning ? "End sprint" : "Start sprint";

    private string _sessionStateText = "Ready when you are";
    public string SessionStateText { get => _sessionStateText; private set => Set(ref _sessionStateText, value); }

    private string _intentionDisplayText = "";
    /// <summary>The running sprint's intention, shown under the timer (F13).</summary>
    public string IntentionDisplayText { get => _intentionDisplayText; private set => Set(ref _intentionDisplayText, value); }

    private bool _intentionDisplayVisible;
    public bool IntentionDisplayVisible { get => _intentionDisplayVisible; private set => Set(ref _intentionDisplayVisible, value); }

    // ------------------------------------------------------------- controls

    public int[] SprintLengths { get; } = { 15, 25, 45, 60, 90 };

    /// <summary>The length the next sprint will run, preset or custom.</summary>
    private int _selectedMinutes = 25;
    public int SelectedMinutes
    {
        get => _selectedMinutes;
        set
        {
            if (!Set(ref _selectedMinutes, value)) return;
            Raise(nameof(PresetMinutes));
            Raise(nameof(CycleDescription));
            UpdateIdleDisplay();
        }
    }

    /// <summary>
    /// What the preset radio buttons bind to. While Custom is selected this is
    /// 0, so no preset lights up even when the typed value happens to equal
    /// one — otherwise WPF's radio group would uncheck Custom under the user
    /// as they typed "15" on the way to "150". Choosing a preset writes here
    /// and leaves custom mode.
    /// </summary>
    public int PresetMinutes
    {
        get => _isCustomSelected ? 0 : _selectedMinutes;
        set
        {
            if (!SprintLengths.Contains(value)) return;
            if (_isCustomSelected)
            {
                _isCustomSelected = false;
                Raise(nameof(IsCustomSelected));
                Raise(nameof(CustomInputVisible));
            }
            SelectedMinutes = value;
            Raise(nameof(PresetMinutes));
        }
    }

    // ------------------------------------------- custom sprint length (roadmap 2.3)

    public const int CustomMinMinutes = 5;
    public const int CustomMaxMinutes = 240;

    /// <summary>Parsed from <see cref="CustomMinutesText"/>; null when the text isn't a whole number.</summary>
    private int? _customMinutes;
    private string _customMinutesText = "";

    /// <summary>
    /// Bound to the text box as a string, so "abc" or "" is rejected with a
    /// message rather than silently leaving the previous length in place.
    /// </summary>
    public string CustomMinutesText
    {
        get => _customMinutesText;
        set
        {
            if (!Set(ref _customMinutesText, value ?? "")) return;
            _customMinutes = int.TryParse(_customMinutesText.Trim(), out var parsed) ? parsed : null;
            Raise(nameof(CustomMinutes));
            Raise(nameof(IsCustomMinutesValid));
            Raise(nameof(CustomMinutesError));
            Raise(nameof(CustomMinutesErrorVisible));
            ApplyCustomMinutes();
        }
    }

    /// <summary>The custom length in minutes, or 0 if the text isn't a valid one.</summary>
    public int CustomMinutes => IsCustomMinutesValid ? _customMinutes!.Value : 0;

    public bool IsCustomMinutesValid =>
        _customMinutes is >= CustomMinMinutes and <= CustomMaxMinutes;

    public string CustomMinutesError => IsCustomMinutesValid
        ? ""
        : $"Choose between {CustomMinMinutes} and {CustomMaxMinutes} minutes.";

    public bool CustomMinutesErrorVisible => _isCustomSelected && !IsCustomMinutesValid;

    private bool _isCustomSelected;
    public bool IsCustomSelected
    {
        get => _isCustomSelected;
        set
        {
            if (value == _isCustomSelected) return;

            // The radio's two-way binding writes true before any command runs,
            // so the lock check has to live here or the trial-expired user gets
            // the feature anyway.
            if (value && _main.IsLocked)
            {
                Raise(nameof(IsCustomSelected));
                _main.OpenUpgradePage();
                return;
            }

            _isCustomSelected = value;
            Raise(nameof(IsCustomSelected));
            Raise(nameof(CustomInputVisible));
            Raise(nameof(CustomMinutesErrorVisible));
            Raise(nameof(PresetMinutes));
            if (value) ApplyCustomMinutes();
        }
    }

    public bool CustomInputVisible => _isCustomSelected;

    public RelayCommand GetProCommand { get; }

    /// <summary>
    /// In custom mode with a valid number: make it the sprint length and
    /// remember it, so it survives a restart and is the default next time.
    /// Invalid input changes nothing and Start stays disabled.
    /// </summary>
    private void ApplyCustomMinutes()
    {
        if (!_isCustomSelected || !IsCustomMinutesValid) return;

        SelectedMinutes = _customMinutes!.Value;
        if (S.LastCustomSprintMinutes != _customMinutes.Value)
        {
            S.LastCustomSprintMinutes = _customMinutes.Value;
            _main.SaveSettings();
        }
    }

    /// <summary>Start is allowed unless custom mode is on with nothing valid typed.</summary>
    private bool CanStart() => !IsRunning && (!_isCustomSelected || IsCustomMinutesValid);

    public ShieldLevel[] ShieldLevels { get; } = { ShieldLevel.Soft, ShieldLevel.Firm, ShieldLevel.Sealed };

    private ShieldLevel _selectedShield = ShieldLevel.Firm;
    public ShieldLevel SelectedShield
    {
        get => _selectedShield;
        set
        {
            if (!Set(ref _selectedShield, value)) return;
            Raise(nameof(ShieldDescription));
            Raise(nameof(ShieldBestFor));
            Raise(nameof(SealedRestartHintVisible));
            Raise(nameof(SoftHardKillHintVisible));
        }
    }

    /// <summary>
    /// A Sealed sprint survives a reboot only if FlowShield starts again at
    /// sign-in, so say so before someone relies on it.
    /// </summary>
    public bool SealedRestartHintVisible =>
        !IsRunning && SelectedShield == ShieldLevel.Sealed && !S.StartWithWindows;

    public string ShieldDescription => ShieldCopy.Promise(SelectedShield);

    public string ShieldBestFor => ShieldCopy.BestFor(SelectedShield);

    /// <summary>
    /// Soft only records and nudges while hard kill mode is off, so when it is
    /// on the promise must not lie.
    /// </summary>
    public bool SoftHardKillHintVisible =>
        !IsRunning && SelectedShield == ShieldLevel.Soft && S.HardKillModeEnabled;

    // ------------------------------------------------------------- journal

    private bool _journalPromptVisible;
    public bool JournalPromptVisible
    {
        get => _journalPromptVisible;
        private set => Set(ref _journalPromptVisible, value);
    }

    private string _journalText = "";
    public string JournalText { get => _journalText; set => Set(ref _journalText, value); }

    /// <summary>
    /// Longest intention kept. A longer line wrapped inside the timer ring and
    /// pushed the buttons off the card, so it is capped here rather than only
    /// in the text box, which nothing enforces when the value is set or pasted
    /// programmatically.
    /// </summary>
    public const int MaxIntentionLength = 80;

    /// <summary>The optional "what are you working on?" line, captured when a sprint starts (F13).</summary>
    private string _intentionText = "";
    public string IntentionText
    {
        get => _intentionText;
        set
        {
            var capped = value ?? "";
            if (capped.Length > MaxIntentionLength) capped = capped[..MaxIntentionLength];
            Set(ref _intentionText, capped);
        }
    }

    /// <summary>The journal prompt repeats the intention when one was set (F13).</summary>
    public string JournalPromptTitle =>
        LastSessionIntention is null
            ? "What moved?"
            : $"You planned: {LastSessionIntention}. What moved?";

    private string? LastSessionIntention
    {
        get
        {
            var last = S.Sessions.LastOrDefault();
            return last is null || string.IsNullOrWhiteSpace(last.Intention) ? null : last.Intention.Trim();
        }
    }

    // --------------------------------------------------- sprint summary (F12)

    private string _summaryTitle = "";
    public string SummaryTitle { get => _summaryTitle; private set => Set(ref _summaryTitle, value); }

    private string _summaryMinutesText = "";
    public string SummaryMinutesText { get => _summaryMinutesText; private set => Set(ref _summaryMinutesText, value); }

    private string _summaryDistractionsText = "";
    public string SummaryDistractionsText { get => _summaryDistractionsText; private set => Set(ref _summaryDistractionsText, value); }

    private string _summaryMomentumText = "";
    public string SummaryMomentumText { get => _summaryMomentumText; private set => Set(ref _summaryMomentumText, value); }

    private string _summaryStreakText = "";
    public string SummaryStreakText { get => _summaryStreakText; private set => Set(ref _summaryStreakText, value); }

    private bool _summaryStreakVisible;
    public bool SummaryStreakVisible { get => _summaryStreakVisible; private set => Set(ref _summaryStreakVisible, value); }

    private string _summaryIntentionText = "";
    public string SummaryIntentionText { get => _summaryIntentionText; private set => Set(ref _summaryIntentionText, value); }

    private bool _summaryIntentionVisible;
    public bool SummaryIntentionVisible { get => _summaryIntentionVisible; private set => Set(ref _summaryIntentionVisible, value); }

    // ------------------------------------------ breaks and cycles (F5)

    /// <summary>
    /// Where the cycle is. Every rule about it — which break comes next,
    /// whether one is offered, whether another sprint follows — is decided by
    /// <see cref="CycleState"/>; this class only starts and stops the clock.
    /// </summary>
    private CycleState _cycle = CycleState.Nothing;

    private DateTime _breakEndsUtc;

    public RelayCommand StartBreakCommand { get; }
    public RelayCommand SkipBreakCommand { get; }
    public RelayCommand StartNextSprintCommand { get; }

    private bool _isOnBreak;
    /// <summary>
    /// A break is counting down and the shield is down with it.
    ///
    /// Deliberately not <see cref="IsRunning"/>: no sprint is running, so
    /// nothing that keys off a running sprint (enforcement, the F2 end flow,
    /// momentum) applies. What does follow a break is spelled out where it is
    /// read — the blocker stays stood down, and the trial lock waits.
    /// </summary>
    public bool IsOnBreak
    {
        get => _isOnBreak;
        private set
        {
            if (!Set(ref _isOnBreak, value)) return;
            Raise(nameof(BreakPanelVisible));
            Raise(nameof(BreakPanelTitle));
            Raise(nameof(BreakPanelText));
            Raise(nameof(StartBreakVisible));
            Raise(nameof(SprintRingVisible));
            Raise(nameof(BreakRingVisible));
        }
    }

    private bool _breakOfferVisible;
    /// <summary>A completed sprint's break is on offer and has not started yet.</summary>
    public bool BreakOfferVisible
    {
        get => _breakOfferVisible;
        private set
        {
            if (!Set(ref _breakOfferVisible, value)) return;
            Raise(nameof(BreakPanelVisible));
            Raise(nameof(BreakPanelTitle));
            Raise(nameof(BreakPanelText));
            Raise(nameof(StartBreakVisible));
        }
    }

    public bool BreakPanelVisible => BreakOfferVisible || IsOnBreak;

    public bool StartBreakVisible => BreakOfferVisible && !IsOnBreak;

    public string BreakPanelTitle => IsOnBreak ? "On a break" : "Take a break";

    public string BreakPanelText => IsOnBreak
        ? AppBlockerService.IsWithinSleepWindow(S)
            ? $"The sprint's shield is down, but your nightly sleep shield is still up — blocked apps are still closed until it ends at {SleepBlockingViewModel.Format(S.SleepBlockEndTime)}."
            : "The shield is down. Blocked apps are allowed until the break ends."
        : OfferedBreakIsLong
            ? $"{CycleState.LongBreakEvery} sprints in a row, so this break is "
              + $"{OfferedBreakMinutes} minutes. The shield stays down while it runs."
            : $"{OfferedBreakMinutes} minutes with the shield down. It changes nothing about your momentum.";

    /// <summary>The break the last completed sprint earned, short or long.</summary>
    private int OfferedBreakMinutes =>
        CycleState.BreakMinutes(S.CompletedSprintsInARow, S.ShortBreakMinutes, S.LongBreakMinutes);

    private bool OfferedBreakIsLong =>
        S.CompletedSprintsInARow > 0 && S.CompletedSprintsInARow % CycleState.LongBreakEvery == 0;

    /// <summary>
    /// Which arc the ring draws: primary for a sprint, text-muted for a break
    /// (DESIGN_SYSTEM §7, and §2's "teal means state or progress" — a break is
    /// neither a sprint nor progress through one).
    /// </summary>
    // The rings drain (TodayView.RingRemaining), so they show for as long as the
    // clock runs; the view hides the arc itself once nothing is left, so an
    // empty ring never paints a round-cap dot.
    public bool SprintRingVisible => !IsOnBreak && IsRunning;
    public bool BreakRingVisible => IsOnBreak;

    /// <summary>"Sprint 2 of 3" under the timer, or empty for a single sprint.</summary>
    public string CycleProgressText => _cycle.CycleLabel;

    public bool CycleProgressVisible => CycleProgressText.Length > 0;

    /// <summary>The cycle chooser's options: no cycle, or 2, 3 or 4 sprints.</summary>
    public int[] CycleChoices { get; } = CycleState.CycleChoices;

    private int _cycleSprints;
    /// <summary>How many sprints the next Start runs with breaks between them. 0 means one sprint.</summary>
    public int CycleSprints
    {
        get => _cycleSprints;
        set
        {
            if (!Set(ref _cycleSprints, value)) return;
            S.CycleSprints = value;
            _main.SaveSettings();
            Raise(nameof(CycleDescription));
        }
    }

    public string CycleDescription => CycleSprints > 1
        ? $"{CycleSprints} sprints of {SelectedMinutes} minutes, with a break between them, run one after another."
        : "One sprint. A break is offered when it finishes.";

    /// <summary>
    /// Start the break the last completed sprint earned.
    ///
    /// The blocker is already stood down — <see cref="EndSprint"/> stops it when
    /// the sprint ends — and nothing here starts it again. That is the whole of
    /// "during a break the shield is down": no new blocker mode, no exception
    /// list, simply no enforcement.
    /// </summary>
    private void StartBreak()
    {
        if (IsRunning || IsOnBreak || !BreakOfferVisible) return;

        var minutes = OfferedBreakMinutes;
        var now = DateTime.UtcNow;
        _breakEndsUtc = now + CycleState.BreakLength(minutes);
        _cycle = _cycle.OnBreakStarted();

        S.ActiveBreak = new RunningBreak
        {
            StartedUtc = now,
            EndsUtc = _breakEndsUtc,
            Minutes = minutes,
            SprintsPlanned = _cycle.SprintsPlanned,
            SprintsDone = _cycle.SprintsDone,
        };
        _main.SaveSettings();

        BeginBreakClock("Break — the shield is down");
        Log.Info($"break started: {minutes} minute(s)");
    }

    private void BeginBreakClock(string stateText)
    {
        BreakOfferVisible = false;
        IsOnBreak = true;
        SessionStateText = stateText;
        _main.OnSprintStateChanged();
        OnBreakTick();
        _tick.Start();
        CommandManager.InvalidateRequerySuggested();
    }

    /// <summary>Skipping is free: no momentum, no streak, no goal, nothing recorded.</summary>
    private void SkipBreak()
    {
        if (!BreakOfferVisible && !IsOnBreak) return;
        Log.Info(IsOnBreak ? "break cut short" : "break skipped");
        EndBreak(notify: false);
        ContinueCycleOrIdle();
    }

    /// <summary>Straight into the next sprint, whether or not a break is running.</summary>
    private void StartNextSprint()
    {
        if (!BreakOfferVisible && !IsOnBreak) return;
        EndBreak(notify: false);
        BreakOfferVisible = false;
        StartSprint();
    }

    /// <summary>
    /// Stops the break clock and clears the saved record.
    /// <paramref name="notify"/> is true only when the break ran its full length.
    /// </summary>
    private void EndBreak(bool notify)
    {
        BreakOfferVisible = false;
        if (!IsOnBreak)
        {
            if (S.ActiveBreak is not null)
            {
                S.ActiveBreak = null;
                _main.SaveSettings();
            }
            CommandManager.InvalidateRequerySuggested();
            return;
        }

        _tick.Stop();
        IsOnBreak = false;
        _cycle = _cycle.OnBreakEnded();
        S.ActiveBreak = null;
        _main.SaveSettings();

        SessionStateText = "Break over";
        UpdateIdleDisplay();
        _main.OnSprintStateChanged();
        CommandManager.InvalidateRequerySuggested();

        if (notify)
            _main.Notify(NotificationKind.BreakOver, "Break over",
                _cycle.StartsNextSprint
                    ? $"Back to it — {_cycle.CycleLabel.ToLowerInvariant()}."
                    : "Back to it when you're ready.");
    }

    /// <summary>In a cycle, the next sprint starts by itself; otherwise Today goes quiet.</summary>
    private void ContinueCycleOrIdle()
    {
        if (_cycle.StartsNextSprint) StartSprint();
        else UpdateIdleDisplay();
    }

    private void OnBreakTick()
    {
        var remaining = _breakEndsUtc - DateTime.UtcNow;
        if (remaining <= TimeSpan.Zero)
        {
            EndBreak(notify: true);
            ContinueCycleOrIdle();
            return;
        }

        Remaining = remaining;
        RemainingText = $"{(int)remaining.TotalMinutes:00}:{remaining.Seconds:00}";

        // #272: the nightly sleep window can begin during this break.
        Raise(nameof(BreakPanelText));

        var total = (_breakEndsUtc - (S.ActiveBreak?.StartedUtc ?? _breakEndsUtc)).TotalSeconds;
        Progress = total <= 0 ? 0 : Math.Clamp(1 - remaining.TotalSeconds / total, 0, 1);
    }

    /// <summary>
    /// Pick up a break that was running when FlowShield last closed (F5).
    ///
    /// A break whose time ran out while FlowShield was closed simply goes away:
    /// there is nothing to enforce, nothing to record and nobody to tell — a
    /// "break over" notice hours later would be noise. A cycle waiting behind it
    /// does not start a sprint by itself either; that needs someone at the desk.
    /// </summary>
    public void ResumeInterruptedBreak(DateTime? nowUtc = null)
    {
        var saved = S.ActiveBreak;
        if (saved is null || IsRunning || IsOnBreak) return;

        var now = nowUtc ?? DateTime.UtcNow;
        if (saved.Decide(now) == BreakResume.EndQuietly)
        {
            Log.Info("a saved break had already run out; ended quietly");
            S.ActiveBreak = null;
            _cycle = CycleState.Nothing;
            _main.SaveSettings();
            return;
        }

        _cycle = saved.ToCycle();
        _breakEndsUtc = saved.EndsUtc;
        Raise(nameof(CycleProgressText));
        Raise(nameof(CycleProgressVisible));
        BeginBreakClock("Break resumed — the shield is down");
        Log.Info($"break resumed, {(saved.EndsUtc - now).TotalSeconds:0} s left");
    }

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

    // ------------------------------------------------- momentum trend (F14)

    /// <summary>The chart's drawing area, in device-independent pixels.</summary>
    private const double TrendWidth = 250;
    private const double TrendHeight = 64;

    private System.Windows.Media.PointCollection _trendPoints = new();
    public System.Windows.Media.PointCollection TrendPoints
    {
        get => _trendPoints;
        private set => Set(ref _trendPoints, value);
    }

    private bool _trendVisible;
    /// <summary>
    /// Hidden until there is something to draw.
    ///
    /// Not "once a sprint exists": momentum only moves when a sprint is
    /// finished, so someone who has started a few and ended them all early has
    /// sessions but a score of zero. The line then sits exactly on the bottom
    /// gridline and the chart reads as broken rather than as "nothing yet".
    /// </summary>
    public bool TrendVisible { get => _trendVisible; private set => Set(ref _trendVisible, value); }

    private string _trendCeilingText = "";
    public string TrendCeilingText { get => _trendCeilingText; private set => Set(ref _trendCeilingText, value); }

    public string TrendRangeText => $"Last {MomentumTrend.Days} days";

    /// <summary>
    /// What the chart says, for anyone who cannot see it. A drawn line has no
    /// text, and naming the Polyline would not help — a shape is not surfaced
    /// to UI Automation either. This rides on a caption that is.
    /// </summary>
    public string TrendDescription =>
        $"Momentum over the last {MomentumTrend.Days} days, now {MomentumText}, {TrendCeilingText}";

    private bool _explainerVisible;
    public bool ExplainerVisible { get => _explainerVisible; private set => Set(ref _explainerVisible, value); }

    public string ExplainerToggleText => ExplainerVisible ? "Hide" : "How momentum works";

    private RelayCommand? _toggleExplainerCommand;
    public RelayCommand ToggleExplainerCommand => _toggleExplainerCommand ??= new RelayCommand(() =>
    {
        ExplainerVisible = !ExplainerVisible;
        Raise(nameof(ExplainerToggleText));
    });

    /// <summary>The rule in plain words, straight from the model that applies it.</summary>
    public IReadOnlyList<string> MomentumExplanation => MomentumTrend.Explanation;

    /// <summary>
    /// Redraws the 30-day line.
    ///
    /// The y axis starts at zero and tops out at the highest point in the
    /// window, so the line always fills the box. Scaling to the visible peak
    /// rather than to a fixed ceiling is the honest choice for a score with no
    /// maximum — but it does mean the same shape can represent very different
    /// numbers, which is why the peak is printed beside it.
    /// </summary>
    private void RefreshTrend(DateTime today)
    {
        var points = MomentumTrend.Points(S, today);
        TrendVisible = points.Any(p => p.Score > 0);
        if (!TrendVisible) return;

        var ceiling = MomentumTrend.Ceiling(points);
        var step = points.Count > 1 ? TrendWidth / (points.Count - 1) : 0;

        var drawn = new System.Windows.Media.PointCollection(points.Count);
        for (var i = 0; i < points.Count; i++)
        {
            var y = TrendHeight - (points[i].Score / ceiling * TrendHeight);
            drawn.Add(new System.Windows.Point(i * step, y));
        }
        drawn.Freeze();

        TrendPoints = drawn;
        TrendCeilingText = $"peak {ceiling:0}";
        Raise(nameof(TrendDescription));
    }

    // ----------------------------------------------------------- daily goal

    /// <summary>
    /// Guards the settle-on-refresh save. The first call comes from the
    /// constructor, before the window exists; the result is recomputed
    /// identically on the next launch, so skipping that one write is safe.
    /// </summary>
    private bool _settledOnce;

    private bool _goalVisible;
    /// <summary>False when no goal is set, which hides the bar entirely (F15).</summary>
    public bool GoalVisible { get => _goalVisible; private set => Set(ref _goalVisible, value); }

    private string _goalProgressText = "";
    public string GoalProgressText { get => _goalProgressText; private set => Set(ref _goalProgressText, value); }

    private double _goalFraction;
    public double GoalFraction { get => _goalFraction; private set => Set(ref _goalFraction, value); }

    private bool _goalMetToday;
    public bool GoalMetToday { get => _goalMetToday; private set => Set(ref _goalMetToday, value); }

    private string _goalNoteText = "";
    /// <summary>"Goal met" or "Day off" beside the bar; empty while it's in progress.</summary>
    public string GoalNoteText { get => _goalNoteText; private set => Set(ref _goalNoteText, value); }

    // -------------------------------------------------------------- actions

    public void TogglePrimary()
    {
        if (IsRunning) RequestEnd();
        else StartSprint();
    }

    /// <summary>
    /// The Space shortcut only fires on Today, and never while a text box has
    /// focus — typing a space into the intention field (or anywhere else)
    /// must stay a space, not also start or end a sprint (F4). Also refused
    /// while the first-run wizard covers the page: its own Start/Next/Back
    /// buttons are what should respond to a key press there, not Today's.
    /// </summary>
    private bool CanUseSpaceShortcut() =>
        _main.CurrentPage == AppPage.Today && !_main.FirstRun.IsVisible
        && Keyboard.FocusedElement is not TextBox;

    // -------------------------------------------- the blocklist in use (F9)

    /// <summary>
    /// Which blocklist the next sprint will enforce, as one caption line —
    /// "Blocking: School".
    ///
    /// One line and no numbers: while a sprint runs, the only thing on this page
    /// that matters is the timer (§1), so the profile says its name and stays out
    /// of the way.
    /// </summary>
    public string ProfileCaption => _main.BlockedApps.ProfileCaption;

    /// <summary>The switcher's chips, shared with the Blocked Apps page.</summary>
    public System.Collections.ObjectModel.ObservableCollection<BlocklistProfile> Profiles =>
        _main.BlockedApps.Profiles;

    /// <summary>
    /// Changing the profile before starting. The same command the Blocked Apps
    /// switcher uses, so Sealed's lock is one rule in one place.
    /// </summary>
    public RelayCommand SelectProfileCommand => _main.BlockedApps.SelectProfileCommand;

    /// <summary>More than one profile is worth a switcher; one is just a caption.</summary>
    public bool ProfileSwitcherVisible => Profiles.Count > 1;

    /// <summary>Idle only: a running sprint keeps the blocklist it started with.</summary>
    public bool CanSwitchProfile => !IsRunning && _main.BlockedApps.CanSwitchProfile;

    /// <summary>Called when the profile is renamed, switched, added or deleted.</summary>
    public void RefreshProfileCaption()
    {
        Raise(nameof(ProfileCaption));
        Raise(nameof(ProfileSwitcherVisible));
        Raise(nameof(CanSwitchProfile));
    }

    /// <summary>Shift+1/2/3 only change the shield where the segmented buttons do: idle, on Today.</summary>
    private bool CanChangeShield() =>
        _main.CurrentPage == AppPage.Today && !_main.FirstRun.IsVisible && !IsRunning;

    // ------------------------------------------- what is already running (F7)

    /// <summary>
    /// Blocked apps that were already open when Start was pressed.
    ///
    /// Empty whenever the panel is not showing.
    /// </summary>
    public System.Collections.ObjectModel.ObservableCollection<string> RunningBlockedApps { get; } = new();

    private bool _runningAppsPanelVisible;
    public bool RunningAppsPanelVisible
    {
        get => _runningAppsPanelVisible;
        private set => Set(ref _runningAppsPanelVisible, value);
    }

    /// <summary>
    /// The apps themselves, on one line.
    ///
    /// A TextBlock rather than a list of them: a Border, a StackPanel and an
    /// ItemsControl's generated rows are not surfaced to UI Automation, so a
    /// list nobody can read back is a list no test can check and no screen
    /// reader can announce.
    /// </summary>
    public string RunningAppsSummary => string.Join(", ", RunningBlockedApps);

    public string RunningAppsTitle => RunningBlockedApps.Count == 1
        ? "One blocked app is open"
        : $"{RunningBlockedApps.Count} blocked apps are open";

    /// <summary>
    /// What happens to them, in the words of the shield actually selected.
    ///
    /// Soft does not close anything, so promising a close there would be a
    /// lie; at Firm and above the warning is worth being specific about,
    /// because the point of this panel is the chance to save first.
    /// </summary>
    public string RunningAppsExplanation => SelectedShield == ShieldLevel.Soft
        ? "At Soft they stay open — FlowShield will just note them."
        : $"They will be asked to close when the sprint starts, with " +
          $"{GracefulClose.Grace.TotalSeconds:0} seconds to save.";

    private RelayCommand? _closeThemNowCommand;
    public RelayCommand CloseThemNowCommand =>
        _closeThemNowCommand ??= new RelayCommand(() => DismissRunningApps(closeThem: true));

    private RelayCommand? _startAnywayCommand;
    public RelayCommand StartAnywayCommand =>
        _startAnywayCommand ??= new RelayCommand(() => DismissRunningApps(closeThem: false));

    /// <summary>
    /// Set while the panel's answer is being acted on, so StartSprint knows not
    /// to put the panel straight back up.
    /// </summary>
    private bool _runningAppsAnswered;

    private void DismissRunningApps(bool closeThem)
    {
        if (!RunningAppsPanelVisible) return;

        RunningAppsPanelVisible = false;
        _runningAppsAnswered = true;
        Log.Info(closeThem
            ? $"pre-sprint: closing {RunningBlockedApps.Count} blocked app(s) first"
            : $"pre-sprint: starting with {RunningBlockedApps.Count} blocked app(s) open");

        // "Close them now" is not a separate closing path: starting the sprint
        // is what closes them, and it does it the same way as always — warning
        // first, grace period, then force. The difference the customer asked
        // for is that they said yes to it.
        //
        // "Start anyway" at Soft genuinely leaves them alone; at Firm the
        // shield still closes them, which is what the shield is for, and the
        // panel has just told them so.
        StartSprint();
    }

    private void StartSprint()
    {
        // The terms gate covers the page, but a covered button can still be
        // invoked by automation or a stray keyboard shortcut. Nothing may start
        // before the terms are accepted (legal checklist 2.3).
        if (_main.TermsGateVisible)
        {
            Log.Info("sprint refused: the terms have not been accepted");
            return;
        }

        // Same reasoning for the first-run wizard: it also covers the page,
        // but Space (or the tray) must not be able to reach through it and
        // start a sprint the wizard hasn't gotten to yet.
        if (_main.FirstRun.IsVisible)
        {
            Log.Info("sprint refused: the first-run wizard is still showing");
            return;
        }

        if (!CanStart()) return;

        // The lock screen covers this button once the trial ends, but the tray
        // menu and keyboard can still reach it.
        if (_main.IsLocked)
        {
            _main.Toast("Your free trial has ended. Buy FlowShield to start a sprint.");
            return;
        }

        // Say what is about to be closed while there is still time to save
        // (F7, roadmap 1.8). Asked once per press: answering it calls back in
        // here, and a second panel would be a loop.
        if (!_runningAppsAnswered)
        {
            var open = _main.Blocker.RunningBlockedApps(S);
            if (open.Count > 0)
            {
                RunningBlockedApps.Clear();
                foreach (var app in open) RunningBlockedApps.Add(app);
                Raise(nameof(RunningAppsTitle));
                Raise(nameof(RunningAppsSummary));
                Raise(nameof(RunningAppsExplanation));
                RunningAppsPanelVisible = true;
                Log.Info($"pre-sprint: {open.Count} blocked app(s) already open");
                return;
            }
        }
        _runningAppsAnswered = false;

        // A break on offer is over the moment a sprint starts, and a break still
        // running is cut short rather than left counting down behind the sprint.
        EndBreak(notify: false);

        // F5: the chooser only starts a cycle; a sprint inside one keeps the
        // cycle it is already part of.
        _cycle = _cycle.OnSprintStarted(CycleSprints);
        Raise(nameof(CycleProgressText));
        Raise(nameof(CycleProgressVisible));

        var now = DateTime.UtcNow;
        var intention = (IntentionText ?? "").Trim();
        _current = new FocusSession
        {
            StartedUtc = now,
            PlannedMinutes = SelectedMinutes,
            Shield = SelectedShield,
            MomentumAtStart = S.MomentumScore,
            Intention = intention,
        };

        // Saved before enforcement begins, so a crash one second in still
        // leaves a sprint to resume.
        S.ActiveSprint = new RunningSprint
        {
            StartedUtc = now,
            PlannedMinutes = SelectedMinutes,
            Shield = SelectedShield,
            LastSeenUtc = now,
            WatchedMinutes = 0,
            MomentumAtStart = S.MomentumScore,
            Intention = intention,

            // The blocklist this sprint enforces, written down rather than
            // inferred later (F9). F6's templates will set it before starting.
            ActiveProfileId = S.ActiveProfile.Id,

            CycleSprintsPlanned = _cycle.SprintsPlanned,
            CycleSprintsDone = _cycle.SprintsDone,
        };
        _main.SaveSettings();

        BeginRunning($"Shield {Roman(SelectedShield)} engaged");
        Log.Info($"sprint started: {SelectedMinutes}m at shield {SelectedShield}, "
                 + $"blocklist \"{S.ActiveProfile.Name}\"");

        _main.Notify(NotificationKind.SprintStarted, "Sprint started",
            $"{SelectedShield} shield on for {SelectedMinutes} minutes.");
    }

    private void BeginRunning(string stateText)
    {
        _endsAtUtc = _current!.StartedUtc + CycleState.SprintLength(_current.PlannedMinutes);
        _lastHeartbeatUtc = DateTime.UtcNow;
        _blocksThisSprint = 0;
        _closedThisSprint = 0;
        _nudgesThisSprint = 0;
        _endingSoonNotified = false;
        IsRunning = true;
        SessionStateText = stateText;
        JournalPromptVisible = false;
        IntentionDisplayText = string.IsNullOrWhiteSpace(_current.Intention) ? "" : _current.Intention;
        IntentionDisplayVisible = IntentionDisplayText.Length > 0;

        _main.Blocker.BeginEnforcing(_current.Shield);
        _main.OnSprintStateChanged();

        OnTick();
        _tick.Start();
    }

    /// <summary>How often a running sprint re-saves that FlowShield is still watching it.</summary>
    public static readonly TimeSpan HeartbeatInterval = TimeSpan.FromSeconds(30);

    /// <summary>
    /// The most one heartbeat may add to a sprint's watched time. A
    /// DispatcherTimer does not tick while the machine is suspended, so a gap
    /// far longer than the interval is time nothing was enforced for.
    /// </summary>
    public static readonly TimeSpan WatchedStretchCap = HeartbeatInterval * 2;

    private DateTime _lastHeartbeatUtc;

    /// <summary>"5 minutes left" fires once per sprint, not once a second.</summary>
    private bool _endingSoonNotified;

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
        if (saved is null || IsRunning)
        {
            // No sprint to pick up: a break might still be running (F5).
            if (saved is null) ResumeInterruptedBreak(nowUtc);
            return;
        }

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
                    MomentumAtStart = saved.MomentumAtStart,
                    Intention = saved.Intention,
                };
                _selectedMinutes = saved.PlannedMinutes;
                _selectedShield = saved.Shield;
                if (!SprintLengths.Contains(saved.PlannedMinutes))
                {
                    // A custom-length sprint comes back in custom mode, so the
                    // controls match the sprint that is actually running.
                    _isCustomSelected = true;
                    _customMinutes = saved.PlannedMinutes;
                    _customMinutesText = saved.PlannedMinutes.ToString();
                    Raise(nameof(IsCustomSelected));
                    Raise(nameof(CustomInputVisible));
                    Raise(nameof(CustomMinutesText));
                }
                Raise(nameof(SelectedMinutes));
                Raise(nameof(PresetMinutes));
                Raise(nameof(CycleDescription));
                Raise(nameof(SelectedShield));
                Raise(nameof(ShieldDescription));
                Raise(nameof(ShieldBestFor));

                // A sprint resumes on the blocklist it started with (F9).
                // Otherwise a Sealed sprint could come back enforcing a profile
                // swapped in while FlowShield was closed, which is the lock
                // undone by a restart.
                if (S.SetActiveProfile(saved.ActiveProfileId))
                {
                    _main.BlockedApps.ReloadActiveProfile();
                    Log.Info($"resumed sprint restored its blocklist: \"{S.ActiveProfile.Name}\"");
                }

                // The cycle comes back with the sprint, so "Sprint 2 of 3" is
                // still true and the run finishes itself (F5).
                _cycle = new CycleState(CyclePhase.Sprint, saved.CycleSprintsPlanned,
                                        saved.CycleSprintsDone);
                _cycleSprints = saved.CycleSprintsPlanned;
                Raise(nameof(CycleSprints));
                Raise(nameof(CycleProgressText));
                Raise(nameof(CycleProgressVisible));

                // A sprint saved by a build without WatchedMinutes (1.0.8 and
                // earlier) takes its watched time from the old estimate first,
                // while LastSeenUtc still says when it was last seen. Otherwise
                // the count would restart at zero here and the half-watched
                // rule would call a sprint watched all along interrupted.
                saved.WatchedMinutes ??= saved.WatchedSoFar;

                // LastSeenUtc moves up, but the gap it spans is deliberately
                // not added to WatchedMinutes: FlowShield was closed for it.
                saved.LastSeenUtc = now;
                // A sprint and a break cannot both be running; the sprint wins.
                S.ActiveBreak = null;
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
                    // An interrupted sprint ends where watching stopped, so its
                    // ActualMinutes (the minutes goal, History, the heatmap) is
                    // time actually enforced, not the whole planned length. A
                    // completed one ends at EndsUtc: its time is already up.
                    EndedUtc = RunningSprint.RecordedEnd(saved.StartedUtc, saved.EndsUtc,
                        saved.WatchedSoFar, now, completed, interrupted: !completed),
                    PlannedMinutes = saved.PlannedMinutes,
                    Shield = saved.Shield,
                    MomentumAtStart = saved.MomentumAtStart,
                    Intention = saved.Intention,
                    Completed = completed,
                    Interrupted = !completed,
                };
                // Added first, for the same reason as in EndSprint: the goal
                // rules count S.Sessions. And skipped under --short-sprints for
                // the same reason too, so there is no path at all by which that
                // flag can hand out credit.
                if (CycleState.SprintCountsAsProgress)
                {
                    S.Sessions.Add(session);
                    if (completed) ApplyMomentum(completed: true, session);
                }

                // The long-break run follows the same rule as a sprint ended in
                // front of you: a finish adds to it, anything else clears it.
                // No break is offered here — it ended while nobody was there.
                S.CompletedSprintsInARow = completed ? S.CompletedSprintsInARow + 1 : 0;
                _cycle = CycleState.Nothing;

                S.ActiveSprint = null;
                _main.SaveSettings();
                RefreshStats();

                SessionStateText = completed ? "Sprint finished while FlowShield was closed" : "Sprint interrupted";
                _main.Toast(completed
                    ? "Your last sprint finished while FlowShield was closed."
                    : "Your last sprint was interrupted — FlowShield wasn't running for most of it.");
                _main.Notify(
                    completed ? NotificationKind.SprintComplete : NotificationKind.SprintInterrupted,
                    completed ? "Sprint complete" : "Sprint interrupted",
                    completed
                        ? $"{session.PlannedMinutes} minutes finished while FlowShield was closed."
                        : "FlowShield wasn't running for most of it, so nothing was enforced.");
                break;

            default:
                S.ActiveSprint = null;
                _main.SaveSettings();
                break;
        }
    }

    private void OnTick()
    {
        // The one timer runs both clocks; a break has no shield, no heartbeat
        // and no end flow, so it takes the short path (F5).
        if (IsOnBreak)
        {
            OnBreakTick();
            return;
        }

        var now = DateTime.UtcNow;
        var remaining = _endsAtUtc - now;
        if (remaining <= TimeSpan.Zero)
        {
            // Time being up is not the same as the sprint having happened
            // (#203). A DispatcherTimer doesn't tick while the PC sleeps, so the
            // first tick after waking lands here with the whole nap behind it,
            // and so does winding the clock forward. Judge it the way F3 judges
            // a sprint that ran out while FlowShield was closed: finished only
            // if FlowShield was watching for at least half of it. The final
            // stretch goes through the same cap as every heartbeat, which is
            // what stops the gap itself from counting as watched.
            if (S.ActiveSprint is { } saved && CycleState.SprintCountsAsProgress)
            {
                saved.NoteStillWatching(now < saved.EndsUtc ? now : saved.EndsUtc, WatchedStretchCap);
                if (saved.Decide(now) == SprintResume.RecordInterrupted)
                {
                    EndSprint(completed: false, interrupted: true);
                    return;
                }
            }

            EndSprint(completed: true);
            return;
        }

        Raise(nameof(EndButtonLabel));
        UpdateEndPanel();

        if (S.ActiveSprint is not null && now - _lastHeartbeatUtc >= HeartbeatInterval)
        {
            _lastHeartbeatUtc = now;
            // Adds the stretch just watched as well as moving LastSeenUtc, so
            // F3's "running for at least half of it" measures time FlowShield
            // was actually up rather than the span between two timestamps.
            S.ActiveSprint.NoteStillWatching(now, WatchedStretchCap);
            _main.SaveSettings();
        }

        // "5 minutes left", once, and never on a sprint barely longer than that.
        if (!_endingSoonNotified
            && remaining <= NotificationPolicy.EndingSoon
            && !NotificationPolicy.TooShortForEndingSoon(_current?.PlannedMinutes ?? SelectedMinutes))
        {
            _endingSoonNotified = true;
            _main.Notify(NotificationKind.FiveMinutesLeft, "5 minutes left",
                "Nearly there — the shield comes down when the time is up.");
        }

        Remaining = remaining;
        RemainingText = remaining.TotalHours >= 1
            ? $"{(int)remaining.TotalHours}:{remaining.Minutes:00}:{remaining.Seconds:00}"
            : $"{(int)remaining.TotalMinutes:00}:{remaining.Seconds:00}";

        var total = CycleState.SprintLength(_current?.PlannedMinutes ?? SelectedMinutes).TotalSeconds;
        Progress = total <= 0 ? 0 : Math.Clamp(1 - remaining.TotalSeconds / total, 0, 1);
    }

    /// <param name="interrupted">
    /// The time ran out but FlowShield wasn't watching for most of it (#203):
    /// the PC slept, the clock jumped, or FlowShield was closed for most of a
    /// sprint it later resumed. Recorded exactly as F3 records the same thing on
    /// startup — neither finished nor given up, so no momentum either way, no
    /// break and no summary card — and only the minutes actually watched count
    /// towards the day.
    /// </param>
    private void EndSprint(bool completed, bool interrupted = false)
    {
        if (!IsRunning || _current is null) return;

        _tick.Stop();
        CloseEndPanel(keepGoing: false);
        IsRunning = false;

        // An interrupted sprint "ends" where FlowShield stopped watching it, and
        // a completed one no later than planned, so ActualMinutes — what the
        // minutes goal and the focus tiles add up — is the time the shield was
        // actually up, not the hours asleep (#203, #300).
        _current.EndedUtc = RunningSprint.RecordedEnd(
            _current.StartedUtc, _endsAtUtc, S.ActiveSprint?.WatchedSoFar ?? 0,
            DateTime.UtcNow, completed, interrupted);
        _current.Completed = completed;
        _current.Interrupted = interrupted;
        _current.BlocksEnforced = _blocksThisSprint;
        _current.AppsClosed = _closedThisSprint;
        _current.NudgesSent = _nudgesThisSprint;

        _main.Blocker.StopEnforcing();

        // Recorded before the momentum and goal rules are asked about it. They
        // read S.Sessions, so a sprint added afterwards was invisible to them:
        // "Daily goal met" fired on the next sprint instead of this one, and on
        // the day's last sprint never fired at all.
        //
        // Both are skipped under --short-sprints, which is what keeps that
        // test-only flag from being a cheat code: a five-second sprint claiming
        // to be ninety minutes would otherwise take ninety minutes' momentum, a
        // streak day and a goal's worth of progress. Under the flag it records
        // nothing and moves nothing, exactly as a sprint cancelled inside the
        // grace period does — see CycleState.SprintCountsAsProgress.
        if (CycleState.SprintCountsAsProgress)
        {
            S.Sessions.Add(_current);
            // Interrupted moves momentum neither way, as on F3's startup path.
            if (!interrupted) ApplyMomentum(completed, _current);
        }

        // F5: the cycle moves on, and the run of completed sprints that earns a
        // long break grows or resets. Neither is momentum, a streak or a goal —
        // those are ApplyMomentum's business and a break never reaches them.
        // An interrupted sprint clears the cycle, as F3's startup path does:
        // nobody was there to carry it on.
        if (completed)
        {
            S.CompletedSprintsInARow++;
            _cycle = _cycle.OnSprintCompleted();
        }
        else
        {
            S.CompletedSprintsInARow = 0;
            _cycle = interrupted ? CycleState.Nothing : _cycle.OnSprintAbandoned();
            // OfferBreakIfEarned normally announces the cycle's new state, and
            // an interrupted sprint skips it, so say here that "Sprint 2 of 3"
            // is gone.
            Raise(nameof(CycleProgressText));
            Raise(nameof(CycleProgressVisible));
        }

        S.ActiveSprint = null;
        _main.SaveSettings();

        // Before the card, not after it. The card shows the streak, and since
        // F15 the only thing that advances CurrentStreak is DailyGoal.Settle,
        // which runs in here. Built the other way round, the first sprint of a
        // streak was filled in while the streak was still zero, so the line was
        // collapsed and "Day 1" never appeared to the person who had just
        // earned it.
        RefreshStats();

        SessionStateText = completed ? "Sprint complete"
            : interrupted ? "Sprint interrupted"
            : "Sprint ended early";
        // No card or "what moved?" for an interrupted sprint: there is nothing
        // to sum up, and F3's startup path doesn't show one either.
        if (!interrupted)
        {
            UpdateSummaryCard(completed, _current);
            JournalPromptVisible = true;
        }
        JournalText = "";
        IntentionDisplayText = "";
        IntentionDisplayVisible = false;
        IntentionText = "";
        Raise(nameof(JournalPromptTitle));
        Progress = completed ? 1 : Progress;
        UpdateIdleDisplay();
        _main.OnSprintStateChanged();

        Log.Info($"sprint ended: completed={completed} interrupted={interrupted} momentum={S.MomentumScore:0.0}");

        if (completed)
        {
            _main.Notify(NotificationKind.SprintComplete, "Sprint complete",
                $"{_current.PlannedMinutes} minutes done. Momentum {S.MomentumScore:0.0}.",
                NotificationAction.OpenJournal);
        }
        else if (interrupted)
        {
            _main.Toast("Sprint interrupted — FlowShield wasn't watching for most of it.");
            _main.Notify(NotificationKind.SprintInterrupted, "Sprint interrupted",
                "The PC was asleep or FlowShield was closed for most of it, so it doesn't count as finished.");
        }

        if (!interrupted) OfferBreakIfEarned(completed);
    }

    /// <summary>
    /// The break offer that follows a sprint (F5).
    ///
    /// Only a completed sprint earns one: ending early is F2's territory, and a
    /// break for stopping would pay for the thing the shields exist to make
    /// harder. In a cycle with a sprint still to come the break starts by
    /// itself, which is what "sprint → break → sprint, automatically" means.
    /// </summary>
    private void OfferBreakIfEarned(bool completed)
    {
        Raise(nameof(CycleProgressText));
        Raise(nameof(CycleProgressVisible));
        Raise(nameof(BreakPanelText));

        if (CycleState.OffersBreak(completed))
        {
            BreakOfferVisible = true;
            if (_cycle.StartsNextSprint) StartBreak();
        }
        else
        {
            BreakOfferVisible = false;
        }

        // BreakOfferVisible/IsOnBreak flip from a timer tick, not a user input
        // event, so CommandManager's automatic requery (mouse/keyboard/focus)
        // never runs and Start/Skip break stay reported disabled until some
        // unrelated input happens to trigger one (see BlockedAppsViewModel's
        // own note on this). Ask for the requery explicitly.
        CommandManager.InvalidateRequerySuggested();

        if (_cycle.CycleFinished)
        {
            var ran = _cycle.SprintsPlanned;
            _cycle = _cycle.OnCycleFinished();
            Raise(nameof(CycleProgressText));
            Raise(nameof(CycleProgressVisible));
            _main.Toast($"Cycle done — {ran} sprints.");
        }
    }

    /// <summary>Fills the post-sprint card (F12) with what just happened.</summary>
    private void UpdateSummaryCard(bool completed, FocusSession session)
    {
        // Rounded once, so the title and the line can't disagree, and a small
        // loss never prints as "momentum −0".
        var delta = (int)Math.Round(S.MomentumScore - session.MomentumAtStart);

        SummaryTitle = completed
            ? "Sprint complete"
            : delta < 0
                ? $"Ended early — momentum −{Math.Abs(delta)}. It'll recover."
                : "Ended early. It'll recover.";
        SummaryMinutesText = $"{(int)Math.Round(session.ActualMinutes)} minutes focused";
        SummaryDistractionsText = DistractionSummary(session);
        SummaryMomentumText = $"{delta:+0;-0;0} → {S.MomentumScore:0}";
        SummaryStreakVisible = S.CurrentStreak > 0;
        SummaryStreakText = S.CurrentStreak == 1 ? "Day 1" : $"Day {S.CurrentStreak}";

        var intention = session.Intention?.Trim() ?? "";
        SummaryIntentionText = intention.Length == 0 ? "" : $"You planned: {intention}";
        SummaryIntentionVisible = intention.Length > 0;
    }

    private static string DistractionSummary(FocusSession session)
    {
        if (session.AppsClosed > 0 || session.NudgesSent > 0)
            return $"{session.AppsClosed} closed · {NudgeWord(session.NudgesSent)}";
        if (session.BlocksEnforced > 0)
            return CountWord(session.BlocksEnforced, "distraction") + " caught";
        return "No distractions caught";
    }

    private static string NudgeWord(int count) => count == 1 ? "1 nudge" : $"{count} nudges";
    private static string CountWord(int count, string word) => count == 1 ? $"1 {word}" : $"{count} {word}s";

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

            // The streak is settled rather than nudged: with a daily goal, the
            // day counts when the goal is met, not on its first sprint, and a
            // missed day has to break the streak even though no sprint ran to
            // notice (F15). With no goal set this lands on the old behaviour.
            if (DailyGoal.NoteProgress(S, today) && DailyGoal.IsSet(S))
                _main.Toast("Daily goal met.");

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

        // The summary card just closed. If the trial ran out while it was on
        // screen, this is the first moment the lock is allowed to appear (F20)
        // — check now rather than waiting up to a minute for the access timer.
        _main.RefreshAccess();
    }

    public void UpdateIdleDisplay()
    {
        if (IsRunning || IsOnBreak) return;
        RemainingText = $"{SelectedMinutes:00}:00";
        Progress = 0;
    }

    /// <summary>Counts one enforcement against the running sprint.</summary>
    public void RecordBlock(bool terminated)
    {
        if (!IsRunning) return;
        _blocksThisSprint++;
        if (terminated) _closedThisSprint++;
        else _nudgesThisSprint++;
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

        // Catches the day rolling over while the app is open, and the first
        // refresh after launch — the two moments a missed day becomes visible
        // without a sprint to trigger it (F15). Only writes on the rare pass
        // that actually moves the streak.
        if (DailyGoal.Settle(S, today) && _settledOnce) _main.SaveSettings();
        _settledOnce = true;

        MomentumText = S.MomentumScore.ToString("0");
        StreakText = S.CurrentStreak == 1 ? "1 day" : $"{S.CurrentStreak} days";
        RefreshTrend(today);
        RefreshGoal(today);
        Raise(nameof(SealedRestartHintVisible));
        Raise(nameof(SoftHardKillHintVisible));
    }

    /// <summary>Updates the daily goal bar, or hides it when no goal is set.</summary>
    private void RefreshGoal(DateTime today)
    {
        GoalVisible = DailyGoal.IsSet(S);
        if (!GoalVisible)
        {
            GoalProgressText = "";
            GoalNoteText = "";
            GoalFraction = 0;
            GoalMetToday = false;
            return;
        }

        GoalProgressText = DailyGoal.ProgressText(S, today);
        GoalFraction = DailyGoal.Fraction(S, today);
        GoalMetToday = DailyGoal.MetOn(S, today);
        GoalNoteText = DailyGoal.IsSkipped(S, today) ? "Day off"
            : GoalMetToday ? "Goal met"
            : "";
    }

    /// <summary>Called when access changes (purchase, deactivation, trial ending).</summary>
    public void OnTierChanged()
    {
        Raise(nameof(SelectedShield));
        Raise(nameof(ShieldDescription));
        Raise(nameof(ShieldBestFor));
    }

    private static string Roman(ShieldLevel level) => level switch
    {
        ShieldLevel.Soft => "I",
        ShieldLevel.Firm => "II",
        _ => "III",
    };
}
