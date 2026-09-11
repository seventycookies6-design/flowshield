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

        var app = new App();
        app.InitializeComponent();
        app.Run();
    }
}
