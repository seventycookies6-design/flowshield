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
        FirstRun = new FirstRunViewModel(this);
        ShowFirstRunCommand = new RelayCommand(() => FirstRun.Show());

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

        // Last, so a resumed sprint's length and shield aren't overwritten by
        // the defaults above.
        Today.ResumeInterruptedSprint();
    }

    public SettingsService SettingsService { get; }
    public AppSettings Settings { get; }
    public AppBlockerService Blocker { get; }

    public TodayViewModel Today { get; }
    public BlockedAppsViewModel BlockedApps { get; }
    public SleepBlockingViewModel SleepBlocking { get; }
    public SettingsViewModel SettingsPage { get; }
    public FirstRunViewModel FirstRun { get; }

    /// <summary>Settings → Show the welcome again.</summary>
    public RelayCommand ShowFirstRunCommand { get; }

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

    // ------------------------------------------------------ terms gate (legal 2.3)

    private bool _termsGateVisible;
    /// <summary>Covers everything until the terms on screen have been accepted.</summary>
    public bool TermsGateVisible { get => _termsGateVisible; private set => Set(ref _termsGateVisible, value); }

    public string TermsVersionText => $"Version {LegalTerms.Version}";
    public string TermsDataLossWarning => LegalTerms.DataLossWarning;
    public string TermsAgreementLine => LegalTerms.AgreementLine;

    /// <summary>"Accepted 17 September 2026" on the Settings page, or empty.</summary>
    public string TermsAcceptedText => Settings.TermsAcceptedUtc is { } when
        ? $"Terms {Settings.TermsAcceptedVersion} accepted {when.ToLocalTime():d MMMM yyyy}"
        : "";

    public bool HasAcceptedTerms => TermsAcceptedText.Length > 0;

    private RelayCommand? _acceptTermsCommand;
    public RelayCommand AcceptTermsCommand => _acceptTermsCommand ??= new RelayCommand(AcceptTerms);

    private RelayCommand? _openTermsCommand;
    public RelayCommand OpenTermsCommand =>
        _openTermsCommand ??= new RelayCommand(() => OpenUrl(LegalTerms.TermsUrl(Settings)));

    private RelayCommand? _openPrivacyCommand;
    public RelayCommand OpenPrivacyCommand =>
        _openPrivacyCommand ??= new RelayCommand(() => OpenUrl(LegalTerms.PrivacyUrl(Settings)));

    /// <summary>Shows the gate unless this version has already been accepted.</summary>
    public bool ShowTermsGateIfNeeded()
    {
        if (LegalTerms.Accepted(Settings)) return false;
        TermsGateVisible = true;
        Log.Info($"terms gate shown for version {LegalTerms.Version}");
        return true;
    }

    private void AcceptTerms()
    {
        LegalTerms.Accept(Settings);
        SaveSettings();
        TermsGateVisible = false;
        Raise(nameof(TermsAcceptedText));
        Raise(nameof(HasAcceptedTerms));
        Log.Info($"terms {LegalTerms.Version} accepted");

        // The welcome waits behind the gate, so a new user sees one thing at a time.
        FirstRun.ShowIfNew();
    }

    // ------------------------------------------------- flowshield:// links (1.4)

    private string? _pendingActivationKey;
    /// <summary>A key from an activation link, waiting for the user to confirm it.</summary>
    public string? PendingActivationKey
    {
        get => _pendingActivationKey;
        private set
        {
            if (!Set(ref _pendingActivationKey, value)) return;
            Raise(nameof(ActivationPromptVisible));
        }
    }

    public bool ActivationPromptVisible => PendingActivationKey is not null;

    private RelayCommand? _confirmActivationCommand;
    public RelayCommand ConfirmActivationCommand => _confirmActivationCommand ??= new RelayCommand(ConfirmActivation);

    private RelayCommand? _dismissActivationCommand;
    public RelayCommand DismissActivationCommand => _dismissActivationCommand ??= new RelayCommand(() =>
    {
        PendingActivationKey = null;
        Log.Info("activation link dismissed");
    });

    /// <summary>
    /// Handles a flowshield:// link. It only ever fills in the key and asks;
    /// activating always takes the user's click on ConfirmActivationCommand.
    /// </summary>
    public void HandleLink(string? link)
    {
        if (link is null) return;
        var key = DeepLink.ParseActivationKey(link);
        if (key is null)
        {
            Log.Info("ignored a flowshield:// link that isn't a valid activation link");
            return;
        }

        CurrentPage = AppPage.Settings;
        SettingsPage.LicenseKeyInput = key;
        PendingActivationKey = key;
        Log.Info("activation link received; waiting for confirmation");
    }

    private void ConfirmActivation()
    {
        if (PendingActivationKey is not { } key) return;
        PendingActivationKey = null;
        SettingsPage.LicenseKeyInput = key;
        SettingsPage.ActivateCommand.Execute(null);
    }

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
                case AppPage.Settings:
                    SettingsPage.RefreshLicenseStatus();
                    // The export card counts the sprints in its date range, and
                    // sprints happen on another page — without this it shows
                    // whatever was true when Settings was last built.
                    SettingsPage.RefreshExportState();
                    break;
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

        MaybeNotifyTrialEnding();
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

    // ------------------------------------------------------ notifications (F19)

    /// <summary>Raised when a notification should appear; MainWindow shows it from the tray.</summary>
    public event EventHandler<Notification>? NotificationRequested;

    /// <summary>Shows a notification if the user still wants that kind. Returns true if it was shown.</summary>
    public bool Notify(NotificationKind kind, string title, string message,
                       NotificationAction action = NotificationAction.OpenApp)
    {
        if (!NotificationPolicy.ShouldShow(kind, Settings, IsSprintRunning)) return false;
        NotificationRequested?.Invoke(this, new Notification(kind, title, message, action));
        Log.Info($"notification: {kind}");
        return true;
    }

    /// <summary>
    /// One notice on the last day of the trial, never during a sprint — it waits
    /// for the next check instead, which is F20's promise as well.
    /// </summary>
    public void MaybeNotifyTrialEnding()
    {
        if (!IsTrial || TrialDaysLeft > 1) return;
        var today = DateTime.Now.Date;
        if (Settings.TrialEndingNotifiedLocal?.Date == today) return;
        if (!Notify(NotificationKind.TrialEnding, "Your free trial ends tomorrow",
                    "Buy FlowShield once for $4.99 to keep it — no subscription.",
                    NotificationAction.OpenSettingsLicense)) return;

        Settings.TrialEndingNotifiedLocal = today;
        SaveSettings();
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
            // The follow-up kill after a grace period is the same distraction
            // as the warning that preceded it, so only one of the two counts.
            if (e.CountsAsDistraction)
            {
                e.App.BlockCount++;
                Settings.RecordBlock();
                Today.RecordBlock(e.Terminated);
                Today.RefreshStats();
                SaveSettings();
            }

            Toast(e.Outcome switch
            {
                BlockOutcome.Closing => GracefulClose.Warning(e.DisplayName),
                BlockOutcome.Closed => GracefulClose.Closed(e.DisplayName),
                _ => GracefulClose.Noted(e.DisplayName),
            });

            // A toast only exists inside FlowShield's own window, which during a
            // sprint is usually not the window you are looking at — so the one
            // warning that is worth interrupting for also goes to Windows.
            if (e.Outcome == BlockOutcome.Closing)
                Notify(NotificationKind.AppClosing, $"{e.DisplayName} is closing",
                       GracefulClose.Warning(e.DisplayName), NotificationAction.OpenApp);
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
