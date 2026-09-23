using System.Windows;
using System.Windows.Threading;
using FlowShield.Services;
using FlowShield.ViewModels;

namespace FlowShield;

public partial class App : Application
{
    public static new App? Current => Application.Current as App;

    public MainViewModel? ViewModel { get; private set; }

    public bool DevMode { get; private set; }

    /// <summary>The single-instance lock taken in Program.Main; null only if run another way.</summary>
    public SingleInstance? Instance { get; init; }

    protected override void OnStartup(StartupEventArgs e)
    {
        // Velopack's bootstrap runs in Program.Main, before this point — the
        // install/update hooks must be handled before any window exists.
        base.OnStartup(e);

        DispatcherUnhandledException += OnDispatcherUnhandledException;
        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
            Log.Error($"fatal: {(args.ExceptionObject as Exception)?.Message ?? "unknown"}");

        var args = e.Args ?? Array.Empty<string>();
        // Links are left out of the log: an activation link carries a licence key.
        Log.Info($"FlowShield starting (args: {string.Join(' ', args.Select(a =>
            a.StartsWith(DeepLink.Scheme + ":", StringComparison.OrdinalIgnoreCase) ? "<link>" : a))})");

        // --short-timers shrinks F2's grace period and countdowns for the UI tests.
        // It only shortens waits; every step still has to be taken.
        if (args.Any(a => a.Equals("--short-timers", StringComparison.OrdinalIgnoreCase)))
        {
            Models.EndSprintPolicy.UseShortTimers = true;
            Models.GracefulClose.UseShortTimers = true;
            // F5: a three-second break, so tier 3 can run a whole cycle.
            Models.CycleState.UseShortTimers = true;
            Log.Info("short end-sprint timers enabled by --short-timers flag");
        }

        // --short-sprints makes a sprint five seconds long, so the UI suite can
        // watch a whole cycle (F5). Test only; it changes no rule, only a clock.
        if (args.Any(a => a.Equals("--short-sprints", StringComparison.OrdinalIgnoreCase)))
        {
            Models.CycleState.UseShortSprints = true;
            Log.Info("five-second sprints enabled by --short-sprints flag");
        }

        if (args.Any(a => a.Equals("--dev", StringComparison.OrdinalIgnoreCase)))
        {
            DevMode = true;
            Log.Info("dev mode enabled by --dev flag");
        }

        var settingsService = new SettingsService();

        // --reset gives the automation suite a deterministic clean install.
        if (args.Any(a => a.Equals("--reset", StringComparison.OrdinalIgnoreCase)))
        {
            settingsService.Reset();
            Log.Info("settings reset by --reset flag");
        }

        var licenseService = new LicenseService(settingsService);
        ViewModel = new MainViewModel(settingsService, licenseService);

        // The colour theme before any window exists, so the first frame is
        // already in the right one (F21). System is the default, and the app
        // then follows Windows for as long as that stays the choice.
        ThemeService.Initialise(ViewModel.Settings);
        // Repair an enabled Run value only from an installed copy. A dev build
        // shares these settings and must not redirect sign-in into bin/.
        var isInstalled = new UpdateService().IsSupported;
        StartupEntry.RefreshIfEnabled(ViewModel.Settings.StartWithWindows, isInstalled);
        // The same for flowshield://, which the install hook may not have had
        // time to register (#294).
        DeepLink.RefreshIfInstalled(isInstalled);

        // --server=http://host:port lets tests point at a throwaway server.
        var serverArg = args.FirstOrDefault(a => a.StartsWith("--server=", StringComparison.OrdinalIgnoreCase));
        if (serverArg is not null)
        {
            ViewModel.Settings.LicenseServerUrl = serverArg["--server=".Length..].Trim();
            Log.Info($"license server overridden: {ViewModel.Settings.LicenseServerUrl}");
        }

        var websiteArg = args.FirstOrDefault(a => a.StartsWith("--website=", StringComparison.OrdinalIgnoreCase));
        if (websiteArg is not null)
        {
            ViewModel.Settings.WebsiteUrl = websiteArg["--website=".Length..].Trim();
        }

        // --expire-trial backdates the trial so the automation suite can reach
        // the lock screen. It can only take access away, never grant it.
        if (args.Any(a => a.Equals("--expire-trial", StringComparison.OrdinalIgnoreCase)))
        {
            ViewModel.Settings.TrialStartedUtc =
                DateTime.UtcNow.AddDays(-(Models.AppSettings.TrialDays + 1));
            ViewModel.OnTierChanged();
            Log.Info("free trial expired by --expire-trial flag");
        }

        // --expire-trial-in=<seconds> backdates the trial so it runs out a few
        // seconds after launch, instead of already being over. It exists so the
        // automation suite can start a sprint on an active trial and watch it
        // cross the boundary mid-sprint (F20: the lock must wait for the sprint
        // to finish, never interrupt it).
        //
        // Same invariant as --expire-trial above: it can only move the trial's
        // start earlier (taking access away sooner), never later — an unbounded
        // seconds value must never grant, restart or extend a trial.
        var expireInArg = args.FirstOrDefault(a =>
            a.StartsWith("--expire-trial-in=", StringComparison.OrdinalIgnoreCase));
        if (expireInArg is not null
            && int.TryParse(expireInArg["--expire-trial-in=".Length..], out var expireInSeconds)
            && ViewModel.Settings.TrialStartedUtc is { } currentTrialStart)
        {
            var candidateStart = DateTime.UtcNow
                .AddDays(-Models.AppSettings.TrialDays)
                .AddSeconds(expireInSeconds);

            // Only ever pulls the start earlier. A large --expire-trial-in
            // value (or one bigger than TrialDays in seconds) would otherwise
            // compute a start in the future, handing out a fresh trial.
            if (candidateStart < currentTrialStart)
            {
                ViewModel.Settings.TrialStartedUtc = candidateStart;
                Log.Info($"free trial set to expire in {expireInSeconds}s by --expire-trial-in flag");
            }
            else
            {
                Log.Warn($"--expire-trial-in={expireInSeconds} ignored: it would move the trial "
                          + "start later, not earlier");
            }
        }

        // The first-run welcome (F18), decided after --expire-trial so a locked
        // trial never gets it. --skip-first-run keeps the UI tests on Today.
        if (args.Any(a => a.Equals("--skip-first-run", StringComparison.OrdinalIgnoreCase)))
            Models.FirstRunPolicy.SkipForTests = true;

        // --accept-terms records acceptance so the UI suite isn't stopped by the
        // gate on every clean launch. It only skips the screen, never the record.
        if (args.Any(a => a.Equals("--accept-terms", StringComparison.OrdinalIgnoreCase)))
        {
            Models.LegalTerms.Accept(ViewModel.Settings);
            Log.Info("terms accepted by the --accept-terms flag");
        }

        // The terms come first: nothing else is usable until they are accepted,
        // and the welcome opens from the gate once they are.
        if (!ViewModel.ShowTermsGateIfNeeded()) ViewModel.FirstRun.ShowIfNew();

        // Persist immediately so a settings file always exists after first run.
        // Without this, a session where the user changes nothing leaves no file
        // at all, and "is sleep blocking off?" becomes unanswerable from disk.
        ViewModel.SaveSettings();

        var window = new MainWindow { DataContext = ViewModel };
        MainWindow = window;

        var trayLaunch = args.Any(a => a.Equals("--tray", StringComparison.OrdinalIgnoreCase));
        if (trayLaunch)
        {
            // A hidden window must not cause WPF to end the message loop; the
            // tray menu's Quit action remains the explicit shutdown path.
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
        }

        if (!trayLaunch || !window.StartInTray())
        {
            // Never strand a background process if Windows cannot create a tray
            // icon. A visible window is the safe, recoverable fallback.
            window.Show();
        }

        // A later launch brings this copy forward instead of starting another.
        Instance?.Listen(launchArgs =>
        {
            Log.Info("second launch handed over");
            Dispatcher.BeginInvoke(() =>
            {
                window.BringToFront();
                ViewModel.HandleLink(DeepLink.FindLink(launchArgs));
            });
        });

        // Opened by a flowshield:// link while FlowShield wasn't running.
        ViewModel.HandleLink(DeepLink.FindLink(args));

        // Re-confirm an existing license in the background; never blocks the UI.
        _ = licenseService.RefreshAsync(ViewModel.Settings).ContinueWith(_ =>
            Dispatcher.Invoke(() => ViewModel.OnTierChanged()));
    }

    private static void OnDispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        Log.Error("unhandled UI exception", e.Exception);
        new Views.FriendlyErrorDialog(e.Exception).ShowDialog();
        e.Handled = true;
    }

    protected override void OnExit(ExitEventArgs e)
    {
        try
        {
            // Skipped after Settings → Your data → Delete everything (F23):
            // the file is already gone, and saving here would write the
            // in-memory settings straight back and undo the delete.
            if (ViewModel is { SkipSaveOnExit: false }) ViewModel.SaveSettings();
            ViewModel?.Blocker.Dispose();
        }
        catch (Exception ex)
        {
            Log.Error("shutdown cleanup failed", ex);
        }
        Log.Info("FlowShield exited");
        base.OnExit(e);
    }
}
