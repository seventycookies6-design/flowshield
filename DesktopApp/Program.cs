using System.Windows;
using FlowShield.Services;
using Velopack;

namespace FlowShield;

/// <summary>
/// Explicit entry point.
///
/// WPF normally generates Main for you, but Velopack must run before anything
/// else in the process. Install, update and uninstall all work by relaunching
/// the executable with special arguments, and those runs have to be handled and
/// exited before a window, a settings file or a second copy of the blocker
/// comes into existence. Doing it in App.OnStartup is already too late.
/// </summary>
public static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        try
        {
            VelopackApp.Build().Run();
        }
        catch (Exception ex)
        {
            // Running from bin/ during development has no install context.
            Log.Info($"Velopack bootstrap skipped: {ex.Message}");
        }

        // One copy per user (roadmap 1.3). Checked after Velopack's hook runs,
        // which must always be allowed through, and before settings load or the
        // blocker starts, so a second launch never touches either.
        using var instance = SingleInstance.TryAcquire();
        if (instance is null)
        {
            Log.Info(SingleInstance.SendToRunningInstance(args)
                ? "FlowShield is already running; brought it forward and exiting"
                : "FlowShield is already running but didn't answer; exiting");
            return;
        }

        var app = new App { Instance = instance };
        app.InitializeComponent();
        app.Run();
    }
}
