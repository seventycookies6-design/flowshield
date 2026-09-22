using System.Collections.ObjectModel;
using FlowShield.Infrastructure;
using FlowShield.Models;
using FlowShield.Services;

namespace FlowShield.ViewModels;

/// <summary>One row on the first run's "What distracts you?" step.</summary>
public class FirstRunApp : ViewModelBase
{
    public FirstRunApp(PickerEntry entry, bool isChecked, bool alreadyBlocked)
    {
        Entry = entry;
        _isChecked = isChecked || alreadyBlocked;
        AlreadyBlocked = alreadyBlocked;
    }

    public PickerEntry Entry { get; }
    public bool AlreadyBlocked { get; }
    public bool CanToggle => !AlreadyBlocked;

    /// <summary>Set once the user ticks or unticks it, so discovery never overrides their choice.</summary>
    public bool Touched { get; private set; }

    private bool _isChecked;
    public bool IsChecked
    {
        get => _isChecked;
        set { if (Set(ref _isChecked, value)) Touched = true; }
    }

    /// <summary>Sets the tick without counting as the user's choice.</summary>
    public void PreTick(bool value)
    {
        if (Touched || AlreadyBlocked) return;
        _isChecked = value;
        Raise(nameof(IsChecked));
    }

    public string Caption => AlreadyBlocked
        ? "Already blocked"
        : Entry.ExePath is not null ? $"{Entry.SourceLabel} · on this PC" : Entry.SourceLabel;

    public string AutomationId => "FirstRun" + Entry.AutomationId;
}

/// <summary>
/// The three-step welcome (launch checklist F18): what distracts you, how
/// strict, and the first sprint. It exists so a new user's first sprint
/// actually blocks something.
/// </summary>
public class FirstRunViewModel : ViewModelBase
{
    private readonly MainViewModel _main;
    private List<PickerEntry> _entries = new();
    private readonly Dictionary<string, FirstRunApp> _rows = new(StringComparer.OrdinalIgnoreCase);

    public FirstRunViewModel(MainViewModel main)
    {
        _main = main;
        NextCommand = new RelayCommand(() => Step = Math.Min(3, Step + 1));
        BackCommand = new RelayCommand(() => Step = Math.Max(1, Step - 1), () => Step > 1);
        SkipCommand = new RelayCommand(Skip);
        StartCommand = new RelayCommand(() => Finish(startSprint: true));
        FinishCommand = new RelayCommand(() => Finish(startSprint: false));
    }

    public RelayCommand NextCommand { get; }
    public RelayCommand BackCommand { get; }
    public RelayCommand SkipCommand { get; }
    public RelayCommand StartCommand { get; }
    public RelayCommand FinishCommand { get; }

    private bool _isVisible;
    public bool IsVisible { get => _isVisible; private set => Set(ref _isVisible, value); }

    private int _step = 1;
    public int Step
    {
        get => _step;
        set
        {
            if (!Set(ref _step, value)) return;
            Raise(nameof(IsStep1));
            Raise(nameof(IsStep2));
            Raise(nameof(IsStep3));
            Raise(nameof(StepText));
            Raise(nameof(NextVisible));
            System.Windows.Input.CommandManager.InvalidateRequerySuggested();
        }
    }

    public bool IsStep1 => Step == 1;
    public bool IsStep2 => Step == 2;
    public bool IsStep3 => Step == 3;
    public bool NextVisible => Step < 3;
    public string StepText => $"Step {Step} of 3";

    // ---------------------------------------------------- step 1: distractions

    public ObservableCollection<FirstRunApp> Apps { get; } = new();

    private string _query = "";
    public string Query
    {
        get => _query;
        set { if (Set(ref _query, value)) ApplyFilter(); }
    }

    public int CheckedCount => _rows.Values.Count(r => r.IsChecked && !r.AlreadyBlocked);

    // ------------------------------------------------------- step 2: strictness

    private ShieldLevel _shield = ShieldLevel.Firm;
    public ShieldLevel Shield { get => _shield; set => Set(ref _shield, value); }

    // The same canonical wording Today shows (F1) — first run and Today never
    // describe the shields differently.
    public string SoftPromise => ShieldCopy.Promise(ShieldLevel.Soft);
    public string SoftBestFor => ShieldCopy.BestFor(ShieldLevel.Soft);
    public string FirmPromise => ShieldCopy.Promise(ShieldLevel.Firm);
    public string FirmBestFor => ShieldCopy.BestFor(ShieldLevel.Firm);
    public string SealedPromise => ShieldCopy.Promise(ShieldLevel.Sealed);
    public string SealedBestFor => ShieldCopy.BestFor(ShieldLevel.Sealed);

    // ---------------------------------------------------- step 3: first sprint

    private int _minutes = 25;
    public int Minutes { get => _minutes; set => Set(ref _minutes, value); }

    private bool _startWithWindows;
    public bool StartWithWindows { get => _startWithWindows; set => Set(ref _startWithWindows, value); }

    public string TrialLine => _main.IsTrial
        ? $"Everything is unlocked for {_main.TrialDaysLeft} day{(_main.TrialDaysLeft == 1 ? "" : "s")}."
        : "";

    public bool HasTrialLine => TrialLine.Length > 0;

    // ------------------------------------------------------------------ flow

    /// <summary>Opens the welcome if this user should see it. Called once at startup.</summary>
    public void ShowIfNew()
    {
        var s = _main.Settings;
        if (!s.FirstRunCompleted && FirstRunPolicy.IsExistingUser(s))
        {
            // An existing user who updated: record it so it never appears later.
            s.FirstRunCompleted = true;
            return;
        }
        if (FirstRunPolicy.ShouldShow(s, _main.HasAccess, _main.IsSprintRunning)) Show();
    }

    /// <summary>Opens the welcome with the current choices filled in (also from Settings).</summary>
    public void Show()
    {
        if (_main.IsSprintRunning)
        {
            _main.Toast("Finish this sprint first, then open the welcome again.");
            return;
        }

        Shield = _main.Today.SelectedShield;
        Minutes = FirstRunPolicy.SprintLengths.Contains(_main.Today.SelectedMinutes) ? _main.Today.SelectedMinutes : 25;
        StartWithWindows = _main.Settings.StartWithWindows;
        Query = "";
        Step = 1;
        _rows.Clear();
        LoadApps(new()); // filled below once we know what's installed
        Raise(nameof(TrialLine));
        Raise(nameof(HasTrialLine));

        // Seen counts as done: closing the window or a crash mid-way never brings it back uninvited.
        _main.Settings.FirstRunCompleted = true;
        _main.SaveSettings();
        IsVisible = true;
        Log.Info("first run shown");

        Task.Run(() =>
        {
            var merged = AppPicker.Merge(AppPicker.Suggestions(IsProtected), AppCatalog.Discover(), IsProtected);
            var icons = merged.Select(e => (Entry: e, Icon: AppCatalog.IconFor(e.ExePath))).ToList();
            System.Windows.Application.Current?.Dispatcher.BeginInvoke(() =>
            {
                foreach (var (entry, icon) in icons) entry.Icon = icon;
                LoadApps(merged);
            });
        });
    }

    private static bool IsProtected(string processName) =>
        AppBlockerService.CriticalProcesses.Contains(BlockedAppsViewModel.NormalizeProcessName(processName));

    private void LoadApps(List<PickerEntry> entries)
    {
        _entries = entries;
        foreach (var entry in entries)
        {
            var key = string.Join('|', entry.Processes);
            if (_rows.TryGetValue(key, out var row))
            {
                if (row.Entry.ExePath is null && entry.ExePath is not null) row.Entry.ExePath = entry.ExePath;
                row.Entry.Icon ??= entry.Icon;
                row.PreTick(FirstRunPolicy.PreTicked(row.Entry));
                continue;
            }
            var blocked = _main.BlockedApps.IsBlocked(entry);
            row = new FirstRunApp(entry, FirstRunPolicy.PreTicked(entry), blocked);
            row.PropertyChanged += (_, e) =>
            {
                if (e.PropertyName == nameof(FirstRunApp.IsChecked)) Raise(nameof(CheckedCount));
            };
            _rows[key] = row;
        }
        ApplyFilter();
        Raise(nameof(CheckedCount));
    }

    private void ApplyFilter()
    {
        // With no search: suggestions only, the ones on this PC first. A search covers everything found.
        var entries = string.IsNullOrWhiteSpace(Query)
            ? _entries.Where(e => e.Source == PickerSource.Suggested)
                .OrderBy(e => e.Group.Equals("Browsers", StringComparison.OrdinalIgnoreCase) ? 1 : 0)
                .ThenBy(e => e.ExePath is null ? 1 : 0)
                .ToList()
            : AppPicker.Filter(_entries, Query);

        Apps.Clear();
        foreach (var e in entries)
            if (_rows.TryGetValue(string.Join('|', e.Processes), out var row)) Apps.Add(row);
    }

    private void Skip()
    {
        IsVisible = false;
        Log.Info($"first run skipped at step {Step}");
    }

    private void Finish(bool startSprint)
    {
        foreach (var row in _rows.Values.Where(r => r.IsChecked && !r.AlreadyBlocked))
            _main.BlockedApps.AddEntry(row.Entry);

        _main.Today.SelectedShield = Shield;
        _main.Today.SelectedMinutes = Minutes;
        _main.SettingsPage.StartWithWindows = StartWithWindows;
        _main.SaveSettings();

        IsVisible = false;
        _main.CurrentPage = AppPage.Today;
        Log.Info($"first run finished: {CheckedCount} apps, shield {Shield}, {Minutes} min, "
                 + $"start with Windows {StartWithWindows}, sprint {(startSprint ? "started" : "not started")}");

        if (startSprint && _main.Today.StartCommand.CanExecute(null)) _main.Today.StartCommand.Execute(null);
    }
}
