using System.IO;
using System.Text.Json;
using FlowShield.Models;

namespace FlowShield.Services;

/// <summary>
/// Backs Settings → Your data (F23): exactly what FlowShield stores, an export
/// of it, and a way to delete it. Every field this touches is also named in
/// <c>Website/legal.html</c>'s privacy policy and checked against this file by
/// the tier 5 claims test — change one, change the other in the same PR.
/// </summary>
public static class DataPrivacyService
{
    /// <summary>
    /// Writes everything DPAPI-encrypted in settings.json to a plain JSON file
    /// at a path the customer chose, minus the licence key.
    ///
    /// The key is a credential that activates FlowShield on another machine;
    /// putting it in an export the customer might paste into a support ticket
    /// or a forum post would be a worse privacy mistake than not exporting it.
    /// </summary>
    public static void Export(string path, AppSettings settings)
    {
        var payload = new
        {
            exportedUtc = DateTime.UtcNow,
            blockedApps = settings.BlockedApps,

            // Every profile, not just the active one, or the export is not
            // everything the app holds locally (F9).
            blocklistProfiles = settings.Profiles,
            activeProfileId = settings.ActiveProfileId,

            sleepBlocking = new
            {
                enabled = settings.IsSleepBlockEnabled,
                start = settings.SleepBlockStartTime,
                end = settings.SleepBlockEndTime,
            },
            sessions = settings.Sessions,
            momentumScore = settings.MomentumScore,
            currentStreak = settings.CurrentStreak,
            dailyGoal = new
            {
                kind = settings.DailyGoalKind.ToString(),
                target = settings.DailyGoalTarget,
            },
            licence = new
            {
                email = settings.LicenseEmail,
                status = settings.LicenseStatus,
                isPro = settings.IsPro,
                // licenseKey is deliberately not included.
            },
        };

        var json = JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true });
        File.WriteAllText(path, json);
        Log.Info("privacy export written (licence key excluded)");
    }

    /// <summary>
    /// Releases this machine's seat if one is held, then removes every trace
    /// FlowShield keeps here: the encrypted settings file and the logs folder.
    /// The caller is responsible for restarting into first run afterwards —
    /// this method only removes what is on disk.
    /// </summary>
    public static async Task DeleteEverythingAsync(
        LicenseService licenseService, SettingsService settingsService, AppSettings settings)
    {
        Log.Info("delete everything: starting");

        if (settings.IsPro || !string.IsNullOrWhiteSpace(settings.LicenseKey))
        {
            // Deactivating frees the seat on the server before the local record
            // that identifies it is gone. LicenseService.DeactivateAsync already
            // tolerates being offline.
            await licenseService.DeactivateAsync(settings);
        }

        settingsService.Reset();

        try
        {
            var logsDir = Path.GetDirectoryName(Log.Path);
            if (logsDir is not null && Directory.Exists(logsDir))
                Directory.Delete(logsDir, recursive: true);
        }
        catch (Exception ex)
        {
            // Best effort: the settings file (the part that matters for
            // licensing and personal content) is already gone by this point.
            System.Diagnostics.Debug.WriteLine($"could not remove the logs folder: {ex.Message}");
        }
    }
}
