using System.Collections.ObjectModel;
using System.Globalization;
using FlowShield.Infrastructure;
using FlowShield.Models;
using FlowShield.Services;

namespace FlowShield.ViewModels;

/// <summary>One choice in an hour or minute picker: 7 reads "07".</summary>
public sealed record TimePart(int Value, string Label);

public class SleepBlockingViewModel : ViewModelBase
{
    private const string TrialEndedToast = "Your free trial has ended. Buy Basalt to use sleep blocking.";
    private const string NoNightsText = "Choose at least one night. The window starts on the nights you pick.";

    public static IReadOnlyList<TimePart> HourOptions { get; } =
        Enumerable.Range(0, 24).Select(h => new TimePart(h, h.ToString("00", CultureInfo.InvariantCulture))).ToList();

    public static IReadOnlyList<TimePart> MinuteOptions { get; } =
        Enumerable.Range(0, 60).Select(m => new TimePart(m, m.ToString("00", CultureInfo.InvariantCulture))).ToList();

    private readonly MainViewModel _main;
    private readonly SleepWarningPlanner _warnings = new();

    public SleepBlockingViewModel(MainViewModel main)
    {
        _main = main;
        _startHour = main.Settings.SleepBlockStartTime.Hours;
        _startMinute = main.Settings.SleepBlockStartTime.Minutes;
        _endHour = main.Settings.SleepBlockEndTime.Hours;
        _endMinute = main.Settings.SleepBlockEndTime.Minutes;

        // Monday first, like the schedule editor. Nothing saved yet means every night.
        var saved = SleepWindow.From(main.Settings).Nights;
        foreach (var day in SleepWindow.EveryNight)
        {
            var label = CultureInfo.InvariantCulture.DateTimeFormat.GetAbbreviatedDayName(day);
            Nights.Add(new Choice<DayOfWeek>(day, label, saved.Contains(day))
            {
                AutomationId = $"SleepNight_{label}",
                AccessibleName = $"{CultureInfo.InvariantCulture.DateTimeFormat.GetDayName(day)} night",
            });
        }

        SaveCommand = new RelayCommand(Save);
        GetProCommand = new RelayCommand(() => _main.OpenUpgradePage());
        TurnOnStartWithWindowsCommand = new RelayCommand(TurnOnStartWithWindows);
        DismissStartupOfferCommand = new RelayCommand(() => { StartupOfferPending = false; RefreshStatus(); });
        RefreshStatus();
    }

    public RelayCommand SaveCommand { get; }
    public RelayCommand GetProCommand { get; }
    public RelayCommand TurnOnStartWithWindowsCommand { get; }
    public RelayCommand DismissStartupOfferCommand { get; }

    /// <summary>Mon..Sun, the nights the window starts on (drafted here, kept by Save).</summary>
    public ObservableCollection<Choice<DayOfWeek>> Nights { get; } = new();

    /// <summary>Bought, or inside the free trial.</summary>
    public bool HasAccess => _main.HasAccess;

    public bool IsLocked => _main.IsLocked;

    public bool IsEnabled
    {
        get => _main.Settings.IsSleepBlockEnabled;
        set
        {
            if (value && _main.IsLocked)
            {
                _main.Toast(TrialEndedToast);
                Raise();               // snap the toggle back
                return;
            }
            if (value && _main.Settings.SleepBlockDays is { Count: 0 })
            {
                // Saved with no night: switching it on would be a window that
                // never opens, which only looks like protection.
                _main.Toast(NoNightsText);
                StatusText = NoNightsText;
                Raise();
                return;
            }
            if (_main.Settings.IsSleepBlockEnabled == value) return;

            _main.Settings.IsSleepBlockEnabled = value;
            _main.SaveSettings();
            // The window only works while Basalt runs, so turning it on offers
            // Start with Windows when that is off; turning it off withdraws it.
            StartupOfferPending = value && !_main.Settings.StartWithWindows;
            Raise();
            RefreshStatus();
            Log.Info($"sleep blocking {(value ? "enabled" : "disabled")}");
        }
    }

    // ---- the window's times: two pickers each, hour and minute ----------

    private int _startHour, _startMinute, _endHour, _endMinute;

    public int StartHour { get => _startHour; set { if (Set(ref _startHour, value)) TimesChanged(); } }
    public int StartMinute { get => _startMinute; set { if (Set(ref _startMinute, value)) TimesChanged(); } }
    public int EndHour { get => _endHour; set { if (Set(ref _endHour, value)) TimesChanged(); } }
    public int EndMinute { get => _endMinute; set { if (Set(ref _endMinute, value)) TimesChanged(); } }

    private TimeSpan DraftStart => new(StartHour, StartMinute, 0);
    private TimeSpan DraftEnd => new(EndHour, EndMinute, 0);

    /// <summary>The start as picked, "22:00".</summary>
    public string StartText => Format(DraftStart);

    /// <summary>The end as picked, "06:00".</summary>
    public string EndText => Format(DraftEnd);

    private void TimesChanged()
    {
        Raise(nameof(StartText));
        Raise(nameof(EndText));
        RefreshStatus();
    }

    private string _statusText = "";
    public string StatusText { get => _statusText; private set => Set(ref _statusText, value); }

    private string _windowText = "";
    public string WindowText { get => _windowText; private set => Set(ref _windowText, value); }

    private string _nextText = "";
    /// <summary>"Next: Tonight 23:00 → 06:30", or empty while the window is off or can't open.</summary>
    public string NextText { get => _nextText; private set => Set(ref _nextText, value); }

    // ---- Start with Windows: the window only works while Basalt runs ----

    private bool _startupOfferPending;
    /// <summary>Set when the window has just been switched on without Start with Windows.</summary>
    public bool StartupOfferPending { get => _startupOfferPending; private set => Set(ref _startupOfferPending, value); }

    private bool _showStartupPanel;
    /// <summary>The window is on and Basalt isn't set to run at sign-in.</summary>
    public bool ShowStartupPanel { get => _showStartupPanel; private set => Set(ref _showStartupPanel, value); }

    private string _startupText = "";
    public string StartupText { get => _startupText; private set => Set(ref _startupText, value); }

    private string _startupTitle = "";
    public string StartupTitle { get => _startupTitle; private set => Set(ref _startupTitle, value); }

    private void TurnOnStartWithWindows()
    {
        // The Settings switch itself, so the registry entry and the saved
        // choice are exactly what that switch makes.
        _main.SettingsPage.StartWithWindows = true;
        StartupOfferPending = false;
        RefreshStatus();
        _main.Toast("Basalt will start when you sign in to Windows.");
    }

    // ---- Sleep-window ring (UI-SPEC.md A3): reuses the Today timer-ring's
    // dash-array trick (Theme.xaml's ProgressDash resource) with a rotation
    // offset, so the arc starts at the window's start time instead of always
    // at 12 o'clock. Both are presentation-only doubles, recomputed whenever
    // the window changes.

    private double _windowSweepFraction;
    /// <summary>The window's length as a fraction of 24h (0..1), handling a
    /// window that crosses midnight. Feeds the ring's StrokeDashArray via
    /// the shared ProgressDash converter, exactly like the Today ring's
    /// Progress.</summary>
    public double WindowSweepFraction { get => _windowSweepFraction; private set => Set(ref _windowSweepFraction, value); }

    private double _windowStartAngle;
    /// <summary>Degrees to rotate the arc so it begins at the start time's
    /// clock position (0 = midnight/top after the ring's own -90° offset,
    /// 360 = a full day). Bound to a RenderTransform Angle alongside the
    /// ring's existing -90° so the dash pattern's "on" segment starts there
    /// instead of at 12 o'clock.</summary>
    public double WindowStartAngle { get => _windowStartAngle; private set => Set(ref _windowStartAngle, value); }

    private static double SweepFraction(TimeSpan start, TimeSpan end)
    {
        var minutes = (end - start).TotalMinutes;
        if (minutes <= 0) minutes += TimeSpan.FromDays(1).TotalMinutes;
        return Math.Clamp(minutes / TimeSpan.FromDays(1).TotalMinutes, 0, 1);
    }

    private void Save()
    {
        if (_main.IsLocked)
        {
            _main.Toast(TrialEndedToast);
            return;
        }

        if (DraftStart == DraftEnd)
        {
            StatusText = "Start and end can't be the same time — that window never opens.";
            return;
        }

        var nights = Nights.Where(n => n.IsChosen).Select(n => n.Value).ToList();
        if (nights.Count == 0)
        {
            StatusText = NoNightsText;
            return;
        }

        var start = DraftStart;
        var end = DraftEnd;
        _main.Settings.SleepBlockStartTime = start;
        _main.Settings.SleepBlockEndTime = end;
        _main.Settings.SleepBlockDays = nights;
        _main.SaveSettings();

        RefreshStatus();
        _main.Toast("Sleep window saved.");
        Log.Info($"sleep window saved: {start:hh\\:mm} → {end:hh\\:mm}, {nights.Count} night(s)");
    }

    /// <summary>
    /// Re-reads everything the page shows from the settings and the clock.
    /// <paramref name="nowUtc"/> is for tests; the page passes nothing.
    /// </summary>
    public void RefreshStatus(DateTime? nowUtc = null)
    {
        var now = nowUtc ?? DateTime.UtcNow;
        var settings = _main.Settings;
        var enabled = settings.IsSleepBlockEnabled;
        // The saved window, the one enforcement and the warning read.
        var window = SleepWindow.From(settings);
        var current = enabled ? window.Current(now) : null;
        var next = enabled ? window.Next(now) : null;

        WindowText = $"{StartText} → {EndText}";
        NextText = next is null ? "" : $"Next: {SleepWindowCopy.Next(next, now, TimeZoneInfo.Local)}";

        WindowSweepFraction = SweepFraction(settings.SleepBlockStartTime, settings.SleepBlockEndTime);
        WindowStartAngle = -90 + settings.SleepBlockStartTime.TotalMinutes / TimeSpan.FromDays(1).TotalMinutes * 360.0;

        StatusText = _main.IsLocked
            ? "Your free trial has ended. Buy Basalt to schedule a nightly shield."
            : !enabled
                ? "Scheduled blocking is off."
                : !window.CanOpen
                    ? "No night is chosen, so the window never opens."
                    : current is not null
                        ? $"Active now — the shield is up until {SleepWindowCopy.Time(current.EndLocal.TimeOfDay)}."
                        : $"Armed. The shield raises itself at {SleepWindowCopy.Time(next!.StartLocal.TimeOfDay)}.";

        var startsAtSignIn = settings.StartWithWindows;
        ShowStartupPanel = enabled && !_main.IsLocked && !startsAtSignIn;
        if (startsAtSignIn) StartupOfferPending = false;
        StartupTitle = StartupOfferPending ? "Start Basalt when you sign in?" : "Basalt isn't set to start when you sign in";
        StartupText = StartupOfferPending
            ? "The sleep window only works while Basalt is running."
            : "The sleep window only works while Basalt is running. Turn this on so it is running at night.";

        Raise(nameof(HasAccess));
        Raise(nameof(IsLocked));
        Raise(nameof(IsEnabled));
    }

    /// <summary>
    /// The scheduler's tick (F6's, not a second timer): keeps the page's
    /// "Tonight" and "Active now" current while it is open, and sends the
    /// ten-minute warning when the planner says it is due.
    /// </summary>
    public void OnSchedulerTick(DateTime nowUtc)
    {
        if (_main.CurrentPage == AppPage.SleepBlocking) RefreshStatus(nowUtc);

        var notice = _warnings.Due(_main.Settings, _main.IsLocked, nowUtc,
            () => _main.Blocker.RunningBlockedApps(_main.Settings), _main.IsFocusInProgress);
        if (notice is not null) _main.Notify(notice.Kind, notice.Title, notice.Message, notice.Action);
    }

    public void OnTierChanged()
    {
        // A locked app must not keep closing programs every night.
        if (_main.IsLocked && _main.Settings.IsSleepBlockEnabled)
        {
            _main.Settings.IsSleepBlockEnabled = false;
            _main.SaveSettings();
        }
        RefreshStatus();
    }

    /// <summary>Accepts 22:00, 2200, 10pm, 10:30 PM — people type times many ways.</summary>
    public static bool TryParse(string? input, out TimeSpan value)
    {
        value = default;
        var s = (input ?? "").Trim();
        if (s.Length == 0) return false;

        string[] formats = { @"h\:mm", @"hh\:mm", @"H\:mm", @"HH\:mm", "hhmm", "HHmm" };
        if (TimeSpan.TryParseExact(s, formats, CultureInfo.InvariantCulture, out value))
            return value < TimeSpan.FromDays(1);

        if (DateTime.TryParse(s, CultureInfo.CurrentCulture, DateTimeStyles.NoCurrentDateDefault, out var dt))
        {
            value = dt.TimeOfDay;
            return true;
        }
        if (DateTime.TryParse(s, CultureInfo.InvariantCulture, DateTimeStyles.NoCurrentDateDefault, out dt))
        {
            value = dt.TimeOfDay;
            return true;
        }
        return false;
    }

    public static string Format(TimeSpan t) => $"{(int)t.TotalHours:00}:{t.Minutes:00}";
}
