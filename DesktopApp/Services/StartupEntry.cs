using Microsoft.Win32;

namespace FlowShield.Services;

/// <summary>
/// The per-user "start with Windows" Run value.
///
/// Installed copies run from Velopack's stable
/// %LOCALAPPDATA%\FlowShield\current\FlowShield.exe path. Refreshing the value
/// on an installed launch repairs a missing or stale entry. Development builds
/// share the installed app's settings, so they must never refresh it implicitly
/// and redirect sign-in to a disposable bin directory.
/// </summary>
public static class StartupEntry
{
    public const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    public const string ValueName = "FlowShield";

    public static void Set(bool enabled)
    {
        try
        {
            using var key = Registry.CurrentUser.CreateSubKey(RunKey, writable: true);

            if (enabled)
            {
                var exe = Environment.ProcessPath;
                if (string.IsNullOrWhiteSpace(exe))
                {
                    Log.Warn("could not register start-with-Windows: executable path unavailable");
                    return;
                }
                key.SetValue(ValueName, BuildCommand(exe));
            }
            else
            {
                key.DeleteValue(ValueName, throwOnMissingValue: false);
            }
            Log.Info($"start-with-Windows {(enabled ? "registered" : "removed")}");
        }
        catch (Exception ex)
        {
            Log.Error("could not update the Run key", ex);
        }
    }

    /// <summary>Repairs an enabled entry, but only from a Velopack-installed copy.</summary>
    public static void RefreshIfEnabled(bool enabled, bool isInstalled)
    {
        if (enabled && isInstalled) Set(true);
    }

    internal static string BuildCommand(string executablePath) =>
        $"\"{executablePath}\" --tray";
}

/// <summary>
/// What uninstalling removes (roadmap 1.5).
///
/// Velopack deletes the app folder but knows nothing about the registry, so a
/// Run value left behind would point Windows at a missing exe on every sign-in,
/// and a stale flowshield:// key would open nothing. The user's data in
/// %APPDATA%\FlowShield deliberately stays: it holds their licence and history.
/// </summary>
public static class Uninstall
{
    public static void CleanUp()
    {
        StartupEntry.Set(false);
        DeepLink.Unregister();
    }
}
