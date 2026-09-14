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
    private readonly DispatcherTimer _accessTimer;
    private bool _lastHasAccess;

    public MainViewModel(SettingsService settingsService, LicenseService licenseService)
    {
        SettingsService = settingsService;
        Settings = settingsService.Load();

        // The trial clock starts on the first launch of a build that has one.
        // App.OnStartup saves right after construction, so this persists.
        if (Settings.EnsureTrialStarted())
            Log.Info($"free trial started; ends {Settings.TrialEndsUtc:u}");
        _lastHasAccess = HasAccess;

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

        // The trial can run out while the app is open (it usually lives in the
        // tray), so re-check periodically rather than only at launch.
        _accessTimer = new DispatcherTimer { Interval = TimeSpan.FromMinutes(1) };
        _accessTimer.Tick += (_, _) => RefreshAccess();
        _accessTimer.Start();

        Today.SelectedMinutes = Settings.DefaultSprintMinutes;
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

    /// <summary>FlowShield has been bought and activated on this machine.</summary>
    public bool IsPro => Settings.IsPro;
    public bool IsNotPro => !Settings.IsPro;

    /// <summary>Every feature is usable: bought, or inside the free trial.</summary>
    public bool HasAccess => Settings.HasAccessAt(DateTime.UtcNow);

    /// <summary>The trial has ended without a purchase; the lock screen is up.</summary>
    public bool IsLocked => !HasAccess;

    public bool IsTrial => !IsPro && HasAccess;

    public int TrialDaysLeft => Settings.TrialDaysLeftAt(DateTime.UtcNow);

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

    public string TierBadge =>
        IsPro ? "PURCHASED"
        : IsTrial ? $"TRIAL · {TrialDaysLeft} DAY{(TrialDaysLeft == 1 ? "" : "S")} LEFT"
        : "TRIAL ENDED";

    public string TrialEndedText =>
        "Your 7-day free trial has ended. Buy FlowShield once for $4.99 to keep using it — "
        + "no subscription. Already bought it? Enter your licence key below.";

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

    /// <summary>
    /// Picks up the trial running out (or a day ticking by) while the app is open.
    ///
    /// A sprint already under way is left to finish: locking mid-sprint would
    /// drop a shield the user deliberately raised, including a Sealed one.
    /// </summary>
    public void RefreshAccess()
    {
        if (IsSprintRunning) return;

        var hasAccess = HasAccess;
        if (hasAccess != _lastHasAccess)
        {
            Log.Info(hasAccess ? "access granted" : "free trial ended; app locked");
            OnTierChanged();
        }
        else
        {
            Raise(nameof(TierBadge));   // the days-left count changes daily
        }
    }

    /// <summary>Re-evaluates every gated surface after activation, deactivation or the trial ending.</summary>
    public void OnTierChanged()
    {
        _lastHasAccess = HasAccess;

        Raise(nameof(IsPro));
        Raise(nameof(IsNotPro));
        Raise(nameof(HasAccess));
        Raise(nameof(IsLocked));
        Raise(nameof(IsTrial));
        Raise(nameof(TrialDaysLeft));
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
        Toast("Opened the FlowShield store page in your browser.");
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
