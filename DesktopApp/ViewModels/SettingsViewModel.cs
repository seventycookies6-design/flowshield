using System.Net.Http.Json;
using Microsoft.Win32;
using FlowShield.Infrastructure;
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
            ApplyStartWithWindows(value);
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

    private static void ApplyStartWithWindows(bool enabled) => StartupEntry.Set(enabled);

    private void OpenLog() => _main.OpenUrl(Log.Path);
}
