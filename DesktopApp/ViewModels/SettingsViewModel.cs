using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using FlowShield.Infrastructure;
using FlowShield.Models;
using FlowShield.Services;

namespace FlowShield.ViewModels;

public class SettingsViewModel : ViewModelBase
{
    private readonly MainViewModel _main;
    private readonly LicenseService _license;

    private readonly UpdateService _updates = new();

    public SettingsViewModel(MainViewModel main, LicenseService license)
    {
        _main = main;
        _license = license;

        CheckForUpdatesCommand = new AsyncRelayCommand(CheckForUpdatesAsync, () => !IsCheckingUpdates);
        RestartForUpdateCommand = new RelayCommand(RestartForUpdate, () => UpdateReady);
        _versionText = $"Version {_updates.CurrentVersion}";

        _licenseKeyInput = main.Settings.LicenseKey;
        _licenseEmailInput = main.Settings.LicenseEmail;

        ActivateCommand = new AsyncRelayCommand(ActivateAsync);
        GetProCommand = new RelayCommand(() => _main.OpenUpgradePage());
        DeactivateCommand = new AsyncRelayCommand(DeactivateAsync, () => IsPro);
        OpenLogCommand = new RelayCommand(OpenLog);
        SkipTodayCommand = new RelayCommand(ToggleSkipToday, () => CanSkipToday || SkippedToday);
        ExportJournalCommand = new RelayCommand(ExportJournal);

        RefreshLicenseStatus();
    }

    public AsyncRelayCommand ActivateCommand { get; }
    public RelayCommand GetProCommand { get; }
    public AsyncRelayCommand DeactivateCommand { get; }
    public RelayCommand OpenLogCommand { get; }
    public AsyncRelayCommand CheckForUpdatesCommand { get; }
    public RelayCommand RestartForUpdateCommand { get; }

    // ---------------------------------------------------------------- updates

    private string _versionText;
    public string VersionText { get => _versionText; private set => Set(ref _versionText, value); }

    private string _updateStatusText = "";
    public string UpdateStatusText { get => _updateStatusText; private set => Set(ref _updateStatusText, value); }

    private bool _isCheckingUpdates;
    public bool IsCheckingUpdates
    {
        get => _isCheckingUpdates;
        private set => Set(ref _isCheckingUpdates, value);
    }

    private bool _updateReady;
    public bool UpdateReady { get => _updateReady; private set => Set(ref _updateReady, value); }

    /// <summary>Updates only apply to an installed copy, not a dev build.</summary>
    public bool UpdatesSupported => _updates.IsSupported;

    private async Task CheckForUpdatesAsync()
    {
        if (!_updates.IsSupported)
        {
            UpdateStatusText = "Updates apply to installed copies only.";
            return;
        }

        IsCheckingUpdates = true;
        UpdateStatusText = "Checking for updates…";
        try
        {
            var version = await _updates.CheckAndDownloadAsync();
            if (version is null)
            {
                UpdateStatusText = "You're on the latest version.";
                UpdateReady = false;
            }
            else
            {
                UpdateStatusText = $"Version {version} downloaded — restart to apply.";
                UpdateReady = true;
            }
        }
        finally
        {
            IsCheckingUpdates = false;
        }
    }

    private void RestartForUpdate()
    {
        // A sealed sprint locks the blocklist precisely so it can't be escaped;
        // restarting would drop the shield entirely, so the update waits.
        if (_main.IsSprintRunning)
        {
            UpdateStatusText = "Finish your sprint first — the update will apply afterwards.";
            _main.Toast("The update will apply once this sprint ends.");
            return;
        }

        if (!_updates.ApplyAndRestart(sprintRunning: false))
        {
            UpdateStatusText = "Could not apply the update. See the diagnostic log.";
        }
    }

    // ------------------------------------------------------------- licensing

    private string _licenseKeyInput;
    public string LicenseKeyInput { get => _licenseKeyInput; set => Set(ref _licenseKeyInput, value); }

    private string _licenseEmailInput;
    public string LicenseEmailInput { get => _licenseEmailInput; set => Set(ref _licenseEmailInput, value); }

    /// <summary>FlowShield has been bought and activated here.</summary>
    public bool IsPro => _main.IsPro;
    public bool IsNotPro => !_main.IsPro;

    /// <summary>Bought, or inside the free trial.</summary>
    public bool HasAccess => _main.HasAccess;

    private string _licenseStatusText = "";
    /// <summary>The line the automation suite asserts on. Contains "Licence active" once bought.</summary>
    public string LicenseStatusText { get => _licenseStatusText; private set => Set(ref _licenseStatusText, value); }

    private string _licenseDetailText = "";
    public string LicenseDetailText { get => _licenseDetailText; private set => Set(ref _licenseDetailText, value); }

    private bool _isBusy;
    public bool IsBusy { get => _isBusy; private set => Set(ref _isBusy, value); }

    private async Task ActivateAsync()
    {
        IsBusy = true;
        LicenseStatusText = "Checking your license…";
        LicenseDetailText = "";

        try
        {
            var result = await _license.ValidateAsync(LicenseKeyInput, LicenseEmailInput, _main.Settings);

            if (result.IsPro)
            {
                LicenseKeyInput = _main.Settings.LicenseKey;
                LicenseEmailInput = _main.Settings.LicenseEmail;
                _main.OnTierChanged();
                RefreshLicenseStatus();
                _main.Toast("FlowShield activated. Thanks for buying it.");
            }
            else
            {
                LicenseStatusText = "❌ Not activated";
                LicenseDetailText = result.Message;
            }
        }
        finally
        {
            IsBusy = false;
        }
    }

    private async Task DeactivateAsync()
    {
        await _license.DeactivateAsync(_main.Settings);
        LicenseKeyInput = "";
        LicenseEmailInput = "";
        _main.OnTierChanged();
        RefreshLicenseStatus();
        _main.Toast("Deactivated on this device. Its seat is free for another machine.");
    }

    private string _deviceText = "";
    public string DeviceText { get => _deviceText; private set => Set(ref _deviceText, value); }

    public void RefreshLicenseStatus()
    {
        var settings = _main.Settings;

        if (_main.IsPro)
        {
            LicenseStatusText = "✅ Licence active";
            var checkedAt = settings.LicenseCheckedUtc?.ToLocalTime();
            LicenseDetailText =
                (string.IsNullOrWhiteSpace(settings.LicenseEmail)
                    ? "FlowShield is yours — every feature, for good."
                    : $"Bought by {settings.LicenseEmail}. Every feature, for good.")
                + (checkedAt is null ? "" : $" Last verified {checkedAt:d MMM, HH:mm}.");

            // Shown while things are fine, not only once someone is locked out —
            // a seat limit discovered at the moment it blocks you feels arbitrary.
            DeviceText = settings.DeviceLimit > 0
                ? $"Active on {settings.DeviceCount} of {settings.DeviceLimit} devices. "
                  + "Deactivating here frees this one for another machine."
                : "";
        }
        else if (_main.IsTrial)
        {
            var days = _main.TrialDaysLeft;
            LicenseStatusText = $"Free trial — {days} day{(days == 1 ? "" : "s")} left";
            LicenseDetailText = "Everything is unlocked during the trial. Buy FlowShield once for $4.99 "
                                + "to keep it — no subscription.";
            DeviceText = "";
        }
        else
        {
            LicenseStatusText = "Trial ended";
            LicenseDetailText = "Buy FlowShield once for $4.99 to keep using it, or enter the licence "
                                + "key you received when you bought it.";
            DeviceText = "";
        }

        Raise(nameof(IsPro));
        Raise(nameof(IsNotPro));
        Raise(nameof(HasAccess));
        Raise(nameof(HasDeviceInfo));
    }

    public bool HasDeviceInfo => !string.IsNullOrEmpty(DeviceText);

    // ----------------------------------------------------------- preferences

    public bool StartWithWindows
    {
        get => _main.Settings.StartWithWindows;
        set
        {
            if (_main.Settings.StartWithWindows == value) return;
            _main.Settings.StartWithWindows = value;
            // This is an explicit user action, so it applies to whichever copy
            // is running. Only the automatic launch-time repair is install-only.
            StartupEntry.Set(value);
            _main.SaveSettings();
            Raise();
        }
    }

    public bool HardKillModeEnabled
    {
        get => _main.Settings.HardKillModeEnabled;
        set
        {
            if (value && _main.IsLocked)
            {
                _main.Toast("Your free trial has ended. Buy FlowShield to use hard kill mode.");
                Raise();
                return;
            }
            if (_main.Settings.HardKillModeEnabled == value) return;
            _main.Settings.HardKillModeEnabled = value;
            _main.SaveSettings();
            Raise();
        }
    }

    public bool MinimizeToTrayOnClose
    {
        get => _main.Settings.MinimizeToTrayOnClose;
        set
        {
            if (_main.Settings.MinimizeToTrayOnClose == value) return;
            _main.Settings.MinimizeToTrayOnClose = value;
            _main.SaveSettings();
            Raise();
        }
    }

    public string LicenseServerUrl
    {
        get => _main.Settings.LicenseServerUrl;
        set
        {
            var v = (value ?? "").Trim();
            if (_main.Settings.LicenseServerUrl == v) return;
            _main.Settings.LicenseServerUrl = v;
            _main.SaveSettings();
            Raise();
        }
    }

    public string SettingsFilePath => _main.SettingsService.SettingsPath;

    // -------------------------------------------------------- daily goal (F15)

    public bool GoalOff
    {
        get => _main.Settings.DailyGoalKind == DailyGoalKind.None;
        set { if (value) SetGoalKind(DailyGoalKind.None); }
    }

    public bool GoalInMinutes
    {
        get => _main.Settings.DailyGoalKind == DailyGoalKind.Minutes;
        set { if (value) SetGoalKind(DailyGoalKind.Minutes); }
    }

    public bool GoalInSprints
    {
        get => _main.Settings.DailyGoalKind == DailyGoalKind.Sprints;
        set { if (value) SetGoalKind(DailyGoalKind.Sprints); }
    }

    /// <summary>
    /// Switching kind re-reads the target rather than carrying it across:
    /// "90" as minutes is a normal day, "90" as sprints is nobody's day.
    /// </summary>
    private void SetGoalKind(DailyGoalKind kind)
    {
        if (_main.Settings.DailyGoalKind == kind) return;
        _main.Settings.DailyGoalKind = kind;

        _main.Settings.DailyGoalTarget = kind switch
        {
            DailyGoalKind.Minutes => 90,
            DailyGoalKind.Sprints => 3,
            _ => 0,
        };
        _goalTargetText = _main.Settings.DailyGoalTarget.ToString();

        _main.SaveSettings();
        RaiseGoalState();
    }

    private string _goalTargetText = "";

    /// <summary>
    /// Free text so a half-typed number doesn't fight the user. Anything that
    /// isn't a number in range is rejected and reported, not silently coerced.
    /// </summary>
    public string GoalTargetText
    {
        get => string.IsNullOrEmpty(_goalTargetText)
            ? _main.Settings.DailyGoalTarget.ToString()
            : _goalTargetText;
        set
        {
            _goalTargetText = value ?? "";
            Raise();

            var kind = _main.Settings.DailyGoalKind;
            if (kind == DailyGoalKind.None) return;

            if (!int.TryParse(_goalTargetText.Trim(), out var parsed))
            {
                GoalTargetError = "Enter a number.";
                return;
            }

            var clamped = DailyGoal.ClampTarget(kind, parsed);
            if (clamped != parsed)
            {
                GoalTargetError = kind == DailyGoalKind.Minutes
                    ? $"Between {DailyGoal.MinMinutes} and {DailyGoal.MaxMinutes} minutes."
                    : $"Between {DailyGoal.MinSprints} and {DailyGoal.MaxSprints} sprints.";
                return;
            }

            GoalTargetError = "";
            if (_main.Settings.DailyGoalTarget == clamped) return;
            _main.Settings.DailyGoalTarget = clamped;
            _main.SaveSettings();
            RaiseGoalState();
        }
    }

    private string _goalTargetError = "";
    public string GoalTargetError
    {
        get => _goalTargetError;
        private set { Set(ref _goalTargetError, value); Raise(nameof(GoalTargetErrorVisible)); }
    }

    public bool GoalTargetErrorVisible => !string.IsNullOrEmpty(GoalTargetError);

    public string GoalUnitLabel =>
        _main.Settings.DailyGoalKind == DailyGoalKind.Sprints ? "sprints per day" : "minutes per day";

    public bool GoalTargetVisible => _main.Settings.DailyGoalKind != DailyGoalKind.None;

    /// <summary>Days off left in the rolling week, for the button's caption.</summary>
    public string SkipRemainingText
    {
        get
        {
            var used = DailyGoal.SkipsUsedInWindow(_main.Settings, DateTime.Now);
            var left = Math.Max(0, DailyGoal.SkipsPerWeek - used);
            return left == 1 ? "1 day off left this week" : $"{left} days off left this week";
        }
    }

    public bool SkippedToday => DailyGoal.IsSkipped(_main.Settings, DateTime.Now);

    public bool CanSkipToday => DailyGoal.CanSkip(_main.Settings, DateTime.Now);

    public string SkipButtonText => SkippedToday ? "Undo day off" : "Take today off";

    public RelayCommand SkipTodayCommand { get; private set; } = null!;

    private void ToggleSkipToday()
    {
        var today = DateTime.Now;

        if (DailyGoal.IsSkipped(_main.Settings, today)) DailyGoal.Unskip(_main.Settings, today);
        else if (!DailyGoal.Skip(_main.Settings, today)) return;

        _main.SaveSettings();
        RaiseGoalState();
        _main.Today.RefreshStats();
    }

    private void RaiseGoalState()
    {
        Raise(nameof(GoalOff));
        Raise(nameof(GoalInMinutes));
        Raise(nameof(GoalInSprints));
        Raise(nameof(GoalTargetText));
        Raise(nameof(GoalTargetVisible));
        Raise(nameof(GoalUnitLabel));
        Raise(nameof(SkipRemainingText));
        Raise(nameof(SkippedToday));
        Raise(nameof(CanSkipToday));
        Raise(nameof(SkipButtonText));
        // RelayCommand rides CommandManager.RequerySuggested, so the button's
        // enabled state follows without being told.
        _main.Today.RefreshStats();
    // ---------------------------------------------------- journal export (F17)

    private DateTime _exportFrom = DateTime.Now.Date.AddDays(-29);
    public DateTime ExportFrom
    {
        get => _exportFrom;
        set { if (Set(ref _exportFrom, value)) RaiseExportState(); }
    }

    private DateTime _exportTo = DateTime.Now.Date;
    public DateTime ExportTo
    {
        get => _exportTo;
        set { if (Set(ref _exportTo, value)) RaiseExportState(); }
    }

    private ExportFormat _exportFormat = ExportFormat.Csv;

    public bool ExportAsCsv
    {
        get => _exportFormat == ExportFormat.Csv;
        set { if (value) SetExportFormat(ExportFormat.Csv); }
    }

    public bool ExportAsMarkdown
    {
        get => _exportFormat == ExportFormat.Markdown;
        set { if (value) SetExportFormat(ExportFormat.Markdown); }
    }

    private void SetExportFormat(ExportFormat format)
    {
        if (_exportFormat == format) return;
        _exportFormat = format;
        RaiseExportState();
    }

    private string _exportStatusText = "";
    public string ExportStatusText
    {
        get => _exportStatusText;
        private set { Set(ref _exportStatusText, value); Raise(nameof(ExportStatusVisible)); }
    }

    public bool ExportStatusVisible => !string.IsNullOrEmpty(ExportStatusText);

    /// <summary>How many sessions the chosen range covers, before saving anything.</summary>
    public string ExportRangeText
    {
        get
        {
            var count = JournalExport.InRange(_main.Settings.Sessions, ExportFrom, ExportTo).Count;
            return count == 1 ? "1 sprint in this range" : $"{count} sprints in this range";
        }
    }

    public RelayCommand ExportJournalCommand { get; private set; } = null!;

    private void ExportJournal()
    {
        var dialog = new Microsoft.Win32.SaveFileDialog
        {
            FileName = JournalExport.SuggestedFileName(ExportFrom, ExportTo, _exportFormat),
            Filter = _exportFormat == ExportFormat.Csv
                ? "CSV (spreadsheet)|*.csv"
                : "Markdown|*.md",
            AddExtension = true,
            OverwritePrompt = true,
        };

        // No default directory is set: the file goes where the customer says,
        // and nowhere else.
        if (dialog.ShowDialog() != true)
        {
            ExportStatusText = "";
            return;
        }

        try
        {
            var written = JournalExportService.Write(
                dialog.FileName, _main.Settings.Sessions, ExportFrom, ExportTo, _exportFormat);

            // An empty range still writes the file, with its header and nothing
            // under it — saying "nothing to export" after a save dialog would
            // leave someone wondering whether it failed.
            ExportStatusText = written == 0
                ? "Saved. No sprints in that range, so the file has headings only."
                : $"Saved {written} sprint{(written == 1 ? "" : "s")}.";
            _main.Toast("Journal exported.");
        }
        catch (Exception ex)
        {
            Log.Info($"journal export failed: {ex.Message}");
            ExportStatusText = "Could not save that file. Try another folder.";
        }
    }

    private void RaiseExportState()
    {
        Raise(nameof(ExportAsCsv));
        Raise(nameof(ExportAsMarkdown));
        Raise(nameof(ExportRangeText));
        ExportStatusText = "";
    }

    // ------------------------------------------------------ notifications (F19)

    /// <summary>The master switch; turning it off silences every notification.</summary>
    public bool NotificationsEnabled
    {
        get => _main.Settings.NotificationsEnabled;
        set
        {
            if (_main.Settings.NotificationsEnabled == value) return;
            _main.Settings.NotificationsEnabled = value;
            _main.SaveSettings();
            Raise();
            Raise(nameof(NotifySprintStarted));
            Raise(nameof(NotifyFiveMinutesLeft));
            Raise(nameof(NotifySprintComplete));
            Raise(nameof(NotifySprintInterrupted));
            Raise(nameof(NotifyTrialEnding));
        }
    }

    public bool NotifySprintStarted
    {
        get => IsOn(NotificationKind.SprintStarted);
        set => SetNotification(NotificationKind.SprintStarted, value);
    }

    public bool NotifyFiveMinutesLeft
    {
        get => IsOn(NotificationKind.FiveMinutesLeft);
        set => SetNotification(NotificationKind.FiveMinutesLeft, value);
    }

    public bool NotifySprintComplete
    {
        get => IsOn(NotificationKind.SprintComplete);
        set => SetNotification(NotificationKind.SprintComplete, value);
    }

    public bool NotifySprintInterrupted
    {
        get => IsOn(NotificationKind.SprintInterrupted);
        set => SetNotification(NotificationKind.SprintInterrupted, value);
    }

    public bool NotifyTrialEnding
    {
        get => IsOn(NotificationKind.TrialEnding);
        set => SetNotification(NotificationKind.TrialEnding, value);
    }

    private bool IsOn(NotificationKind kind) => _main.Settings.IsNotificationOn(kind);

    private void SetNotification(NotificationKind kind, bool on, [CallerMemberName] string? name = null)
    {
        if (IsOn(kind) == on) return;
        _main.Settings.SetNotification(kind, on);
        _main.SaveSettings();
        Raise(name);
    }

    private void OpenLog() => _main.OpenUrl(Log.Path);
}
