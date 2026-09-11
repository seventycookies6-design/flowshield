using System.Diagnostics;
using System.Windows.Threading;
using FlowShield.Infrastructure;
using FlowShield.Models;
using FlowShield.Services;

namespace FlowShield.ViewModels;

public enum AppPage { Today, BlockedApps, SleepBlocking, Settings }

public class MainViewModel : ViewModelBase
{
    private readonly DispatcherTimer _toastTimer;

    public MainViewModel(SettingsService settingsService, LicenseService licenseService)
    {
        SettingsService = settingsService;
        Settings = settingsService.Load();

        Blocker = new AppBlockerService(settingsService, Settings);
        Blocker.Blocked += OnBlocked;

        Today = new TodayViewModel(this);
        BlockedApps = new BlockedAppsViewModel(this);
        SleepBlocking = new SleepBlockingViewModel(this);
        SettingsPage = new SettingsViewModel(this, licenseService);

        NavigateCommand = new RelayCommand(p =>
        {
            if (p is AppPage page) CurrentPage = page;
            else if (p is string s && Enum.TryParse<AppPage>(s, out var parsed)) CurrentPage = parsed;
        });

        GetProCommand = new RelayCommand(OpenUpgradePage);

        _toastTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(4) };
        _toastTimer.Tick += (_, _) => { _toastTimer.Stop(); ToastVisible = false; };

        Today.SelectedMinutes = Math.Min(
            Settings.DefaultSprintMinutes,
            Settings.IsPro ? int.MaxValue : AppSettings.FreeMaxSprintMinutes);
        Today.SelectedShield = Settings.DefaultShield;
        Today.UpdateIdleDisplay();
    }

    public SettingsService SettingsService { get; }
    public AppSettings Settings { get; }
    public AppBlockerService Blocker { get; }

    public TodayViewModel Today { get; }
    public BlockedAppsViewModel BlockedApps { get; }
    public SleepBlockingViewModel SleepBlocking { get; }
    public SettingsViewModel SettingsPage { get; }

    public RelayCommand NavigateCommand { get; }
    public RelayCommand GetProCommand { get; }

    public bool IsPro => Settings.IsPro;
    public bool IsNotPro => !Settings.IsPro;
    public bool IsSprintRunning => Today.IsRunning;

    // ------------------------------------------------------------ navigation

    private AppPage _currentPage = AppPage.Today;
    public AppPage CurrentPage
    {
        get => _currentPage;
        set
        {
            if (!Set(ref _currentPage, value)) return;

            Raise(nameof(IsTodayPage));
            Raise(nameof(IsBlockedAppsPage));
            Raise(nameof(IsSleepBlockingPage));
            Raise(nameof(IsSettingsPage));
            Raise(nameof(CurrentPageTitle));
            Raise(nameof(CurrentPageSubtitle));

            // Refresh the page being entered so it never shows stale state.
            switch (value)
            {
                case AppPage.Today: Today.RefreshStats(); break;
                case AppPage.BlockedApps: BlockedApps.RefreshStatus(); break;
                case AppPage.SleepBlocking: SleepBlocking.RefreshStatus(); break;
                case AppPage.Settings: SettingsPage.RefreshLicenseStatus(); break;
            }
        }
    }

    public bool IsTodayPage => CurrentPage == AppPage.Today;
    public bool IsBlockedAppsPage => CurrentPage == AppPage.BlockedApps;
    public bool IsSleepBlockingPage => CurrentPage == AppPage.SleepBlocking;
    public bool IsSettingsPage => CurrentPage == AppPage.Settings;

    public string CurrentPageTitle => CurrentPage switch
    {
        AppPage.Today => "Today",
        AppPage.BlockedApps => "Blocked Apps",
        AppPage.SleepBlocking => "Sleep Blocking",
        _ => "Settings",
    };

    public string CurrentPageSubtitle => CurrentPage switch
    {
        AppPage.Today => "Start a sprint and let the shield hold the line.",
        AppPage.BlockedApps => "What the shield closes while you're working.",
        AppPage.SleepBlocking => "A nightly window where the shield raises itself.",
        _ => "License, startup and enforcement preferences.",
    };

    public string TierBadge => IsPro ? "PRO" : "FREE";

    // ---------------------------------------------------------------- toast

    private string _toastText = "";
    public string ToastText { get => _toastText; private set => Set(ref _toastText, value); }

    private bool _toastVisible;
    public bool ToastVisible { get => _toastVisible; private set => Set(ref _toastVisible, value); }

    public void Toast(string message)
    {
        ToastText = message;
        ToastVisible = true;
        _toastTimer.Stop();
        _toastTimer.Start();
        Log.Info($"toast: {message}");
    }

    // -------------------------------------------------------------- plumbing

    public void SaveSettings()
    {
        try
        {
            Settings.DefaultSprintMinutes = Today.SelectedMinutes;
            Settings.DefaultShield = Today.SelectedShield;
            SettingsService.Save(Settings);
            Blocker.UpdateSettings(Settings);
        }
        catch (Exception ex)
        {
            Log.Error("saving settings failed", ex);
            Toast("Couldn't save settings — see the log in Settings.");
        }
    }

    /// <summary>Re-evaluates every Pro-gated surface after activation or deactivation.</summary>
    public void OnTierChanged()
    {
        Raise(nameof(IsPro));
        Raise(nameof(IsNotPro));
        Raise(nameof(TierBadge));

        Today.OnTierChanged();
        BlockedApps.RefreshStatus();
        SleepBlocking.OnTierChanged();
        SettingsPage.RefreshLicenseStatus();
    }

    public void OnSprintStateChanged()
    {
        Raise(nameof(IsSprintRunning));
        BlockedApps.RefreshStatus();
    }

    private void OnBlocked(object? sender, BlockEvent e)
    {
        // Marshalled to the dispatcher so the bound counters are mutated on the
        // UI thread — the blocker deliberately leaves them alone.
        var dispatcher = App.Current?.Dispatcher;
        if (dispatcher is null) return;

        dispatcher.Invoke(() =>
        {
            e.App.BlockCount++;
            Settings.RecordBlock();
            Today.RecordBlock();
            Today.RefreshStats();
            SaveSettings();

            Toast(e.Terminated
                ? $"{e.DisplayName} closed by the shield."
                : $"{e.DisplayName} is on your blocklist.");
        });
    }

    public void OpenUpgradePage()
    {
        var url = Settings.WebsiteUrl.TrimEnd('/') + "/index.html#pricing";
        Log.Info($"opening upgrade page {url}");
        OpenUrl(url);
        Toast("Opened the upgrade page in your browser.");
    }

    public void OpenUrl(string url)
    {
        try
        {
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            Log.Error($"could not open {url}", ex);
            Toast($"Couldn't open {url}");
        }
    }
}
