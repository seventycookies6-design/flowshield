using System.Globalization;
using FlowShield.Infrastructure;
using FlowShield.Services;

namespace FlowShield.ViewModels;

public class SleepBlockingViewModel : ViewModelBase
{
    private readonly MainViewModel _main;

    public SleepBlockingViewModel(MainViewModel main)
    {
        _main = main;
        _startText = Format(main.Settings.SleepBlockStartTime);
        _endText = Format(main.Settings.SleepBlockEndTime);

        SaveCommand = new RelayCommand(Save);
        GetProCommand = new RelayCommand(() => _main.OpenUpgradePage());
        RefreshStatus();
    }

    public RelayCommand SaveCommand { get; }
    public RelayCommand GetProCommand { get; }

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
                _main.Toast("Your free trial has ended. Buy FlowShield to use sleep blocking.");
                Raise();               // snap the toggle back
                return;
            }
            if (_main.Settings.IsSleepBlockEnabled == value) return;

            _main.Settings.IsSleepBlockEnabled = value;
            _main.SaveSettings();
            Raise();
            RefreshStatus();
            Log.Info($"sleep blocking {(value ? "enabled" : "disabled")}");
        }
    }

    private string _startText;
    public string StartText
    {
        get => _startText;
        set { if (Set(ref _startText, value)) RefreshStatus(); }
    }

    private string _endText;
    public string EndText
    {
        get => _endText;
        set { if (Set(ref _endText, value)) RefreshStatus(); }
    }

    private string _statusText = "";
    public string StatusText { get => _statusText; private set => Set(ref _statusText, value); }

    private string _windowText = "";
    public string WindowText { get => _windowText; private set => Set(ref _windowText, value); }

    private void Save()
    {
        if (_main.IsLocked)
        {
            _main.Toast("Your free trial has ended. Buy FlowShield to use sleep blocking.");
            return;
        }

        if (!TryParse(StartText, out var start))
        {
            StatusText = $"\"{StartText}\" isn't a valid time. Use HH:mm, e.g. 22:00.";
            return;
        }
        if (!TryParse(EndText, out var end))
        {
            StatusText = $"\"{EndText}\" isn't a valid time. Use HH:mm, e.g. 06:00.";
            return;
        }
        if (start == end)
        {
            StatusText = "Start and end can't be the same time — that window never opens.";
            return;
        }

        _main.Settings.SleepBlockStartTime = start;
        _main.Settings.SleepBlockEndTime = end;
        _main.SaveSettings();

        StartText = Format(start);
        EndText = Format(end);
        RefreshStatus();
        _main.Toast("Sleep window saved.");
        Log.Info($"sleep window saved: {start:hh\\:mm} → {end:hh\\:mm}");
    }

    public void RefreshStatus()
    {
        var enabled = _main.Settings.IsSleepBlockEnabled;
        var inWindow = AppBlockerService.IsWithinSleepWindow(_main.Settings);

        WindowText = $"{StartText} → {EndText}";

        StatusText = _main.IsLocked
            ? "Your free trial has ended. Buy FlowShield to schedule a nightly shield."
            : !enabled
                ? "Scheduled blocking is off."
                : inWindow
                    ? $"Active now — the shield is up until {EndText}."
                    : $"Armed. The shield raises itself at {StartText}.";

        Raise(nameof(HasAccess));
        Raise(nameof(IsLocked));
        Raise(nameof(IsEnabled));
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
