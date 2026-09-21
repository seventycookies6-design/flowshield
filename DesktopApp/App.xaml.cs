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
            Log.Info("short end-sprint timers enabled by --short-timers flag");
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
        // Repair an enabled Run value only from an installed copy. A dev build
        // shares these settings and must not redirect sign-in into bin/.
        StartupEntry.RefreshIfEnabled(
            ViewModel.Settings.StartWithWindows,
            new UpdateService().IsSupported);

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
            ViewModel?.SaveSettings();
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
