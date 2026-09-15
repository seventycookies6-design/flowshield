using Microsoft.Win32;

namespace FlowShield.Services;

/// <summary>The per-user "start with Windows" Run value.</summary>
public static class StartupEntry
{
    public const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    public const string ValueName = "FlowShield";

    public static void Set(bool enabled)
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(RunKey, writable: true);
            if (key is null) return;

            if (enabled)
            {
                var exe = Environment.ProcessPath;
                if (!string.IsNullOrEmpty(exe)) key.SetValue(ValueName, $"\"{exe}\" --tray");
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
