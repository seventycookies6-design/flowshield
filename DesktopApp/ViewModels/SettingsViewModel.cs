using System.Collections.ObjectModel;
using System.Linq;
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
        ExportDataCommand = new RelayCommand(ExportData);
        // A sealed sprint locks the blocklist precisely so it can't be escaped;
        // relaunching the app would drop the shield entirely, same guard as
        // RestartForUpdate above.
        DeleteEverythingCommand = new AsyncRelayCommand(DeleteEverythingAsync, () => !IsBusy && !_main.IsSprintRunning);

        ToggleDevicesCommand = new AsyncRelayCommand(ToggleDevicesAsync);
        RefreshDevicesCommand = new AsyncRelayCommand(() => LoadDevicesAsync(force: true));
        RequestReleaseCommand = new RelayCommand(p => { if (p is DeviceRowViewModel d) d.IsConfirmingRelease = true; });
        CancelReleaseCommand = new RelayCommand(p => { if (p is DeviceRowViewModel d) d.IsConfirmingRelease = false; });
        ConfirmReleaseCommand = new AsyncRelayCommand(p => ReleaseDeviceAsync(p as DeviceRowViewModel));

        RefreshLicenseStatus();
    }

    public AsyncRelayCommand ActivateCommand { get; }
    public RelayCommand GetProCommand { get; }
    public AsyncRelayCommand DeactivateCommand { get; }
    public RelayCommand OpenLogCommand { get; }
    public AsyncRelayCommand CheckForUpdatesCommand { get; }
    public RelayCommand RestartForUpdateCommand { get; }
    public AsyncRelayCommand ToggleDevicesCommand { get; }
    public AsyncRelayCommand RefreshDevicesCommand { get; }
    public RelayCommand RequestReleaseCommand { get; }
    public RelayCommand CancelReleaseCommand { get; }
    public AsyncRelayCommand ConfirmReleaseCommand { get; }

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

    /// <summary>Inside the free trial, licence not yet bought (UI-SPEC.md A3:
    /// gates the big "days left" number so it only shows while it's true).</summary>
    public bool IsTrial => _main.IsTrial;

    /// <summary>Days left in the free trial, for the big tabular number next
    /// to the licence status (UI-SPEC.md A3, matching the app-pages sketch's
    /// "05 days left" treatment).</summary>
    public int TrialDaysLeft => _main.TrialDaysLeft;

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
        // The licence server may be a sleeping Render free instance — the
        // first request after idle can take up to a minute. Roadmap 5.2:
        // start with the honest "contacting" copy; ValidateAsync's progress
        // callback swaps it for the "waking up" message once the wait has
        // gone on long enough to say so (LicenseWaitCopy.MessageFor).
        LicenseStatusText = LicenseWaitCopy.MessageFor(0);
        LicenseDetailText = "";

        var progress = new Progress<string>(message => LicenseStatusText = message);

        try
        {
            var result = await _license.ValidateAsync(LicenseKeyInput, LicenseEmailInput, _main.Settings, progress);

            if (result.IsPro)
            {
                LicenseKeyInput = _main.Settings.LicenseKey;
                LicenseEmailInput = _main.Settings.LicenseEmail;
                _main.OnTierChanged();
                RefreshLicenseStatus();
                _main.Toast("FlowShield activated. Thanks for buying it.");
            }
            else if (LicenseWaitCopy.IsTransportFailure(result.Definitive))
            {
                // A timeout or dropped connection is not a verdict on the key —
                // never word it like a rejection (Roadmap 5.2).
                LicenseStatusText = "Couldn't reach the licence server";
                LicenseDetailText = result.Message;
            }
            else if (result.Status == "device_limit_reached")
            {
                // Roadmap 5.7: show the cap right where it blocked the user,
                // with the list to act on inline, instead of just an error.
                LicenseStatusText = "❌ Not activated";
                var limit = _main.Settings.DeviceLimit > 0 ? _main.Settings.DeviceLimit : 3;
                LicenseDetailText = $"This licence is on {limit} PCs. Release one to activate here.";
                await LoadDevicesAsync(force: true);
                IsDevicesExpanded = true;
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
        Raise(nameof(IsTrial));
        Raise(nameof(TrialDaysLeft));
    }

    public bool HasDeviceInfo => !string.IsNullOrEmpty(DeviceText);

    // -------------------------------------------- devices (Roadmap 5.7)

    public ObservableCollection<DeviceRowViewModel> Devices { get; } = new();

    private bool _isDevicesExpanded;
    /// <summary>Card state, not a toggle for the list — collapsing does not
    /// clear what was already loaded, so re-expanding is instant.</summary>
    public bool IsDevicesExpanded { get => _isDevicesExpanded; private set => Set(ref _isDevicesExpanded, value); }

    private bool _isLoadingDevices;
    public bool IsLoadingDevices { get => _isLoadingDevices; private set => Set(ref _isLoadingDevices, value); }

    private string _devicesStatusText = "";
    public string DevicesStatusText { get => _devicesStatusText; private set => Set(ref _devicesStatusText, value); }

    private bool _devicesLoadedOnce;

    /// <summary>
    /// Roadmap 5.7: the list is fetched only when the card is expanded (the
    /// first time) or the Refresh button is pressed — never on a timer or in
    /// the background. Collapsing and re-expanding does not re-fetch.
    /// </summary>
    private async Task ToggleDevicesAsync()
    {
        IsDevicesExpanded = !IsDevicesExpanded;
        if (IsDevicesExpanded && !_devicesLoadedOnce)
        {
            await LoadDevicesAsync(force: false);
        }
    }

    private async Task LoadDevicesAsync(bool force)
    {
        if (!force && _devicesLoadedOnce) return;

        IsLoadingDevices = true;
        DevicesStatusText = "";
        try
        {
            var result = await _license.ListDevicesAsync(_main.Settings);
            _devicesLoadedOnce = true;

            Devices.Clear();
            if (!result.Ok)
            {
                DevicesStatusText = result.Error ?? "Couldn't load your devices.";
                return;
            }

            foreach (var device in result.Devices)
                Devices.Add(new DeviceRowViewModel(device));

            // The card already shows count/limit while things are fine
            // (DeviceText above); keep it in step with what was just fetched.
            // Routed through LicenseService.SaveDeviceCounts (its
            // MutateAndSave) rather than written directly here — #202.
            _license.SaveDeviceCounts(_main.Settings, result.DeviceCount, result.DeviceLimit);
            RefreshLicenseStatus();
        }
        finally
        {
            IsLoadingDevices = false;
        }
    }

    private async Task ReleaseDeviceAsync(DeviceRowViewModel? device)
    {
        if (device is null || !device.CanRelease) return;

        device.IsReleasing = true;
        try
        {
            var ok = await _license.ReleaseDeviceAsync(_main.Settings, device.DeviceToken);
            if (ok)
            {
                Devices.Remove(device);
                _main.Toast($"Released {device.Name}. That seat is free for another machine.");
                await LoadDevicesAsync(force: true);
            }
            else
            {
                device.IsConfirmingRelease = false;
                DevicesStatusText = "Couldn't release that device. Try again.";
            }
        }
        finally
        {
            device.IsReleasing = false;
        }
    }

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

    /// <summary>
    /// The Soft shield's full-screen notice (F7). Soft closes nothing, so this
    /// is the only thing it does that is visible from outside FlowShield —
    /// which is also why someone might want it off.
    /// </summary>
    public bool ShowSoftOverlayEnabled
    {
        get => _main.Settings.ShowSoftOverlayEnabled;
        set
        {
            if (_main.Settings.ShowSoftOverlayEnabled == value) return;
            _main.Settings.ShowSoftOverlayEnabled = value;
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

    /// <summary>
    /// Off by default (F4). MainWindow reacts to this changing by
    /// registering or unregistering Ctrl+Alt+F with <c>RegisterHotKey</c>,
    /// and turns it back off through this same setter if the combination
    /// turns out to be taken by another app.
    /// </summary>
    public bool GlobalHotkeyEnabled
    {
        get => _main.Settings.GlobalHotkeyEnabled;
        set
        {
            if (_main.Settings.GlobalHotkeyEnabled == value) return;
            _main.Settings.GlobalHotkeyEnabled = value;
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
    }

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

    /// <summary>
    /// Re-counts the sprints in the chosen range. Called when the Settings page
    /// is opened, because sprints are finished on another page entirely.
    /// </summary>
    public void RefreshExportState() => Raise(nameof(ExportRangeText));

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
            Raise(nameof(NotifyAppClosing));
            Raise(nameof(NotifyBreakOver));
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

    public bool NotifyAppClosing
    {
        get => IsOn(NotificationKind.AppClosing);
        set => SetNotification(NotificationKind.AppClosing, value);
    }

    public bool NotifyBreakOver
    {
        get => IsOn(NotificationKind.BreakOver);
        set => SetNotification(NotificationKind.BreakOver, value);
    }

    // ------------------------------------------------------------ breaks (F5)

    /// <summary>
    /// The two break lengths, as text for the same reason the custom sprint
    /// length is: "abc" has to be refused with a message rather than silently
    /// leaving the old number in place.
    /// </summary>
    private string? _shortBreakText;
    public string ShortBreakMinutesText
    {
        get => _shortBreakText ??= _main.Settings.ShortBreakMinutes.ToString();
        set => SetBreakMinutes(ref _shortBreakText, value, isLong: false);
    }

    private string? _longBreakText;
    public string LongBreakMinutesText
    {
        get => _longBreakText ??= _main.Settings.LongBreakMinutes.ToString();
        set => SetBreakMinutes(ref _longBreakText, value, isLong: true);
    }

    public string BreakMinutesError =>
        $"Choose between {CycleState.MinBreakMinutes} and {CycleState.MaxBreakMinutes} minutes.";

    private bool _shortBreakInvalid;
    public bool ShortBreakErrorVisible { get => _shortBreakInvalid; private set => Set(ref _shortBreakInvalid, value); }

    private bool _longBreakInvalid;
    public bool LongBreakErrorVisible { get => _longBreakInvalid; private set => Set(ref _longBreakInvalid, value); }

    public string LongBreakExplanation =>
        $"The longer break comes after every {CycleState.LongBreakEvery} completed sprints in a row.";

    private void SetBreakMinutes(ref string? field, string? value, bool isLong,
                                 [CallerMemberName] string? name = null)
    {
        var text = value ?? "";
        if (field == text) return;
        field = text;
        Raise(name);

        var valid = int.TryParse(text.Trim(), out var minutes) && CycleState.IsValidBreakMinutes(minutes);
        if (isLong) LongBreakErrorVisible = !valid;
        else ShortBreakErrorVisible = !valid;
        if (!valid) return;

        if (isLong) _main.Settings.LongBreakMinutes = minutes;
        else _main.Settings.ShortBreakMinutes = minutes;
        _main.SaveSettings();
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

    // --------------------------------------------------------- your data (F23)

    /// <summary>Where settings.json lives, shown so "Your data" says exactly
    /// where the DPAPI-encrypted file is, not just that one exists.</summary>
    public string DataFilePath => _main.SettingsService.SettingsPath;

    public RelayCommand ExportDataCommand { get; private set; } = null!;
    public AsyncRelayCommand DeleteEverythingCommand { get; private set; } = null!;

    private string _dataStatusText = "";
    public string DataStatusText
    {
        get => _dataStatusText;
        private set { Set(ref _dataStatusText, value); Raise(nameof(DataStatusVisible)); }
    }

    public bool DataStatusVisible => !string.IsNullOrEmpty(DataStatusText);

    private void ExportData()
    {
        var dialog = new Microsoft.Win32.SaveFileDialog
        {
            FileName = $"flowshield-data-{DateTime.Now:yyyy-MM-dd}.json",
            Filter = "JSON|*.json",
            AddExtension = true,
            OverwritePrompt = true,
        };

        // No default directory: the file goes where the customer says, same
        // rule as the journal export.
        if (dialog.ShowDialog() != true)
        {
            DataStatusText = "";
            return;
        }

        try
        {
            DataPrivacyService.Export(dialog.FileName, _main.Settings);
            DataStatusText = "Saved. Your licence key was left out.";
            _main.Toast("Data exported.");
        }
        catch (Exception ex)
        {
            Log.Info($"data export failed: {ex.Message}");
            DataStatusText = "Could not save that file. Try another folder.";
        }
    }

    private async Task DeleteEverythingAsync()
    {
        // The command's CanExecute already covers this; refused again here so
        // a covered or otherwise-invoked control can't relaunch the app out
        // from under a running (possibly Sealed) sprint. Same rule as
        // RestartForUpdate above.
        if (_main.IsSprintRunning)
        {
            DataStatusText = "Finish your sprint first — deleting everything restarts the app, which would end it.";
            _main.Toast("Delete everything once your sprint has ended.");
            return;
        }

        var dialog = new Views.ConfirmDeleteDialog();
        if (dialog.ShowDialog() != true) return;

        IsBusy = true;
        DataStatusText = "Deleting…";
        try
        {
            await DataPrivacyService.DeleteEverythingAsync(_license, _main.SettingsService, _main.Settings);
        }
        catch (Exception ex)
        {
            Log.Error("delete everything failed", ex);
            DataStatusText = "Couldn't delete everything — see the log.";
            IsBusy = false;
            return;
        }

        // No IsBusy = false here: the app is restarting, so there is no more
        // UI left to unblock.
        _main.RestartToFirstRun();
    }
}
