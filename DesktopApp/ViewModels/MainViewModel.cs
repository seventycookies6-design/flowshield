using System.Diagnostics;
using System.Windows;
using System.Windows.Threading;
using FlowShield.Infrastructure;
using FlowShield.Models;
using FlowShield.Services;

namespace FlowShield.ViewModels;

public enum AppPage { Today, History, BlockedApps, SleepBlocking, Settings }

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

        // F9: a settings file written before profiles existed has one blocklist;
        // it becomes the Default profile here, before anything reads it.
        if (Settings.EnsureProfiles())
            Log.Info($"blocklist profiles ready: {Settings.Profiles.Count}, active \"{Settings.ActiveProfile.Name}\"");

        // F6: the three built-in templates arrive once, and a schedule whose
        // template is gone is dropped before anything reads it.
        if (Settings.EnsureTemplates())
            Log.Info($"study templates ready: {Settings.Templates.Count}, schedules {Settings.Schedules.Count}");

        Blocker = new AppBlockerService(settingsService, Settings);
        Blocker.Blocked += OnBlocked;
        Blocker.SoftForeground += OnSoftForeground;

        Today = new TodayViewModel(this);
        History = new HistoryViewModel(this);
        BlockedApps = new BlockedAppsViewModel(this);
        SleepBlocking = new SleepBlockingViewModel(this);
        Schedule = new ScheduleViewModel(this);
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
    public HistoryViewModel History { get; }
    public BlockedAppsViewModel BlockedApps { get; }
    public SleepBlockingViewModel SleepBlocking { get; }

    /// <summary>The Schedule page (F6), which holds the sleep window as well.</summary>
    public ScheduleViewModel Schedule { get; }

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

    /// <summary>
    /// A sprint or the break that follows it is under way (F5).
    ///
    /// The break counts: the shield is down, but the person is mid-routine, and
    /// interrupting them to sell something — or locking the app under them —
    /// three minutes before the next sprint would break F20's promise just as
    /// surely as doing it mid-sprint.
    /// </summary>
    public bool IsFocusInProgress => Today.IsRunning || Today.IsOnBreak;

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
            Raise(nameof(IsHistoryPage));
            Raise(nameof(IsBlockedAppsPage));
            Raise(nameof(IsSleepBlockingPage));
            Raise(nameof(IsSettingsPage));
            Raise(nameof(CurrentPageTitle));
            Raise(nameof(CurrentPageSubtitle));

            // Refresh the page being entered so it never shows stale state.
            switch (value)
            {
                case AppPage.Today: Today.RefreshStats(); break;
                // Sprints happen on another page, so History would otherwise
                // show whatever was true when the app started (F16).
                case AppPage.History: History.Refresh(); break;
                case AppPage.BlockedApps: BlockedApps.RefreshStatus(); break;
                case AppPage.SleepBlocking:
                    SleepBlocking.RefreshStatus();
                    Schedule.Refresh();
                    break;
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
    public bool IsHistoryPage => CurrentPage == AppPage.History;
    public bool IsBlockedAppsPage => CurrentPage == AppPage.BlockedApps;
    public bool IsSleepBlockingPage => CurrentPage == AppPage.SleepBlocking;
    public bool IsSettingsPage => CurrentPage == AppPage.Settings;

    public string CurrentPageTitle => CurrentPage switch
    {
        AppPage.Today => "Today",
        AppPage.History => "History",
        AppPage.BlockedApps => "Blocked Apps",
        AppPage.SleepBlocking => "Schedule",
        _ => "Settings",
    };

    public string CurrentPageSubtitle => CurrentPage switch
    {
        AppPage.Today => "Start a sprint and let the shield hold the line.",
        AppPage.History => "Your week, and every sprint you have run.",
        AppPage.BlockedApps => "What the shield closes while you're working.",
        AppPage.SleepBlocking => "Templates that start by themselves, and your nightly window.",
        _ => "License, startup and enforcement preferences.",
    };

    public string TierBadge =>
        IsPro ? "PURCHASED"
        : IsTrial ? $"TRIAL · {TrialDaysLeft} DAY{(TrialDaysLeft == 1 ? "" : "S")} LEFT"
        : "TRIAL ENDED";

    /// <summary>
    /// The tier badge's status dot (DESIGN_SYSTEM.md §7 "Tier badge"): primary
    /// while trialling, ok once bought, warn once the trial has ended with
    /// nothing bought. Looked up as a brush resource key by TierBadgeDotConverter.
    /// </summary>
    public string TierBadgeDotKey =>
        IsPro ? "Green" : IsTrial ? "Primary" : "Amber";

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

    /// <summary>
    /// A yes/no question with a named destructive button, in the same dialog
    /// Delete everything uses. True only when that button was pressed.
    /// </summary>
    public bool Confirm(string question, string confirmLabel) =>
        Views.ConfirmDeleteDialog.Ask(question, confirmLabel);

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
    /// Set once local data has been deleted (F23), so App.OnExit's normal
    /// save-on-shutdown does not write the in-memory settings straight back to
    /// disk and undo the delete.
    /// </summary>
    public bool SkipSaveOnExit { get; private set; }

    /// <summary>
    /// Settings → Your data → Delete everything (F23), after the file and logs
    /// are already gone: relaunch into a clean install and end this process.
    ///
    /// A new process, not an in-place reset, because this process is still
    /// holding the very settings the customer just asked to delete — reusing
    /// it risks something re-persisting them before it exits. --reset is the
    /// same flag the automation suite uses for a deterministic clean install.
    /// </summary>
    public void RestartToFirstRun()
    {
        SkipSaveOnExit = true;
        try
        {
            var exe = Environment.ProcessPath;
            if (!string.IsNullOrEmpty(exe))
                Process.Start(new ProcessStartInfo(exe, "--reset") { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            Log.Error("could not relaunch after deleting local data", ex);
        }
        Application.Current.Shutdown();
    }

    /// <summary>
    /// Picks up the trial running out (or a day ticking by) while the app is open.
    ///
    /// A sprint already under way is left to finish: locking mid-sprint would
    /// drop a shield the user deliberately raised, including a Sealed one. The
    /// sprint's summary card gets the same courtesy — the lock waits until it
    /// has been read and dismissed, so "trial ended" never interrupts "what
    /// moved?" (F20).
    /// </summary>
    public void RefreshAccess()
    {
        if (IsFocusInProgress || Today.JournalPromptVisible) return;

        var hasAccess = HasAccess;
        if (hasAccess != _lastHasAccess)
        {
            Log.Info(hasAccess ? "access granted" : "free trial ended; app locked");
            OnTierChanged();
        }
        else
        {
            Raise(nameof(TierBadge));   // the days-left count changes daily
            Raise(nameof(TierBadgeDotKey));
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
        Raise(nameof(TierBadgeDotKey));

        Today.OnTierChanged();
        BlockedApps.RefreshStatus();
        SleepBlocking.OnTierChanged();
        Schedule.Refresh();
        SettingsPage.RefreshLicenseStatus();
    }

    // ------------------------------------------------------ notifications (F19)

    /// <summary>Raised when a notification should appear; MainWindow shows it from the tray.</summary>
    public event EventHandler<Notification>? NotificationRequested;

    /// <summary>Shows a notification if the user still wants that kind. Returns true if it was shown.</summary>
    public bool Notify(NotificationKind kind, string title, string message,
                       NotificationAction action = NotificationAction.OpenApp)
    {
        if (!NotificationPolicy.ShouldShow(kind, Settings, IsFocusInProgress)) return false;
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
        Raise(nameof(IsFocusInProgress));
        BlockedApps.RefreshStatus();

        // So the page's Sealed lock follows the sprint. Null-safe: this can run
        // while the constructor is still building the page view models.
        Schedule?.Refresh();

        // An allowance belongs to the sprint it was granted in, and a notice
        // must never outlive the shield that raised it.
        _softOverlay.Reset();
        SoftOverlayDismissRequested?.Invoke(this, EventArgs.Empty);
    }

    // ------------------------------------------------- the Soft notice (F7, 1.7)

    private readonly SoftOverlayPolicy _softOverlay = new();

    /// <summary>What MainWindow needs to put the Soft notice on screen.</summary>
    public sealed record SoftOverlayRequest(
        string DisplayName, string Sentence, string TimeLeft, IntPtr Window);

    /// <summary>Show the Soft notice for a blocked app that has just come to the front.</summary>
    public event EventHandler<SoftOverlayRequest>? SoftOverlayRequested;

    /// <summary>Take the Soft notice down, if one is up.</summary>
    public event EventHandler? SoftOverlayDismissRequested;

    /// <summary>
    /// True while any FlowShield panel is up: the terms gate, the lock screen,
    /// the welcome, an activation prompt, the end-sprint flow, the "what moved?"
    /// prompt or the pre-sprint question.
    ///
    /// The Soft notice never opens over one of these. They are all things the
    /// user is in the middle of answering, and a full-screen panel from another
    /// window would take the keyboard away mid-sentence.
    /// </summary>
    public bool ModalPanelVisible =>
        TermsGateVisible || IsLocked || FirstRun.IsVisible || ActivationPromptVisible
        || Today.EndPanelVisible || Today.JournalPromptVisible || Today.RunningAppsPanelVisible;

    private void OnSoftForeground(object? sender, ForegroundSighting e)
    {
        var dispatcher = App.Current?.Dispatcher;
        if (dispatcher is null) return;

        dispatcher.Invoke(() =>
        {
            // The sighting was taken on the blocker's own thread; this runs on
            // the dispatcher afterwards, so the sprint can have been cancelled
            // or finished in between. A notice for a sprint that no longer
            // exists would stay up forever: enforcement has stopped, so no
            // later sighting would ever arrive to take it down.
            if (!IsSprintRunning || !Blocker.IsEnforcing)
            {
                if (_softOverlay.LeftTheForeground())
                    SoftOverlayDismissRequested?.Invoke(this, EventArgs.Empty);
                return;
            }

            if (e.DisplayName is null)
            {
                // Something that is not a blocked app is in front, so the notice
                // has done its job. FlowShield's own windows are never reported
                // here, so this is not the notice seeing itself.
                if (_softOverlay.LeftTheForeground())
                    SoftOverlayDismissRequested?.Invoke(this, EventArgs.Empty);
                return;
            }

            if (!Settings.ShowSoftOverlayEnabled) return;
            if (ModalPanelVisible) return;
            if (!_softOverlay.ShouldShow(e.DisplayName, DateTime.UtcNow)) return;

            Log.Info($"soft notice shown for {e.DisplayName}");
            SoftOverlayRequested?.Invoke(this, new SoftOverlayRequest(
                e.DisplayName,
                SoftOverlayCopy.Sentence(e.DisplayName, Today.EndsAtUtc.ToLocalTime()),
                SoftOverlayCopy.TimeLeft(Today.Remaining),
                e.Window));
        });
    }

    /// <summary>
    /// "Back to work" on the Soft notice. The blocked app is left running — Soft
    /// closes nothing, and that promise is the whole shield.
    /// </summary>
    public void SoftOverlayBackToWork(string displayName)
    {
        _softOverlay.BackToWork(displayName, DateTime.UtcNow);
        Log.Info($"soft notice dismissed: back to work from {displayName}");
    }

    /// <summary>
    /// "Allow 5 minutes". The sighting was already counted as a distraction when
    /// it happened, once, so this changes nothing about the count.
    /// </summary>
    public void SoftOverlayAllowFiveMinutes(string displayName)
    {
        _softOverlay.AllowFiveMinutes(displayName, DateTime.UtcNow);
        Toast(SoftOverlayCopy.Allowed(displayName));
        Log.Info($"soft notice: {displayName} allowed for "
                 + $"{SoftOverlayPolicy.AllowWindow.TotalMinutes:0} minutes");
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
