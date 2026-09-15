using Microsoft.Win32;

namespace FlowShield.Services;

/// <summary>
/// Keeps the current user's Windows sign-in command pointed at the executable
/// that is running now. Velopack installs each update in a versioned directory,
/// so the value must be refreshed after an update rather than written once.
/// </summary>
public static class StartupRegistrationService
{
    internal const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    internal const string RunValueName = "FlowShield";

    /// <summary>Registers or removes FlowShield from the current user's Run key.</summary>
    public static void SetEnabled(bool enabled)
    {
        try
        {
            using var key = Registry.CurrentUser.CreateSubKey(RunKey, writable: true);
            if (enabled)
            {
                var executablePath = Environment.ProcessPath;
                if (string.IsNullOrWhiteSpace(executablePath))
                {
                    Log.Warn("could not register start-with-Windows: executable path unavailable");
                    return;
                }

                key.SetValue(RunValueName, BuildCommand(executablePath));
            }
            else
            {
                key.DeleteValue(RunValueName, throwOnMissingValue: false);
            }

            Log.Info($"start-with-Windows {(enabled ? "registered" : "removed")}");
        }
        catch (Exception ex)
        {
            Log.Error("could not update the Run key", ex);
        }
    }

    /// <summary>
    /// Rewrites an enabled registration on every app launch. This repairs the
    /// executable path after Velopack moves an updated build to a new folder.
    /// </summary>
    public static void RefreshIfEnabled(bool enabled)
    {
        if (enabled) SetEnabled(true);
    }

    internal static string BuildCommand(string executablePath) =>
        $"\"{executablePath}\" --tray";
}
