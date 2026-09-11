using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FlowShield.Models;

namespace FlowShield.Services;

/// <summary>
/// Persists <see cref="AppSettings"/> to
/// <c>%APPDATA%\FlowShield\settings.json</c>, encrypted with Windows DPAPI
/// under the current user account.
///
/// Roaming AppData, deliberately, not Local. The installer puts the
/// application itself in <c>%LOCALAPPDATA%\FlowShield</c>, so settings kept
/// there would sit inside the install directory and could be wiped by an
/// update or uninstall — taking the customer's licence key with them.
///
/// The file is a small JSON envelope rather than a raw blob so it stays
/// inspectable (version, timestamp) without being readable:
/// <code>{ "version": 1, "protected": true, "entropy": "FlowShield.v1", "data": "&lt;base64&gt;" }</code>
/// </summary>
public class SettingsService
{
    /// <summary>Extra entropy mixed into the DPAPI blob. Not a secret — it scopes the blob to this app.</summary>
    public const string EntropyLabel = "FlowShield.v1";

    private static readonly byte[] Entropy = Encoding.UTF8.GetBytes(EntropyLabel);

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = null,
    };

    private readonly object _gate = new();

    public string SettingsDirectory { get; }
    public string SettingsPath { get; }

    /// <summary>Where settings used to live, before the installer claimed that path.</summary>
    private static string LegacyDirectory => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FlowShield");

    public SettingsService(string? overrideDirectory = null)
    {
        SettingsDirectory = overrideDirectory
            ?? Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "FlowShield");

        SettingsPath = Path.Combine(SettingsDirectory, "settings.json");
        Directory.CreateDirectory(SettingsDirectory);

        if (overrideDirectory is null) MigrateFromLegacyLocation();
    }

    /// <summary>
    /// Move settings written by a pre-installer build into the new location.
    ///
    /// Without this, anyone who used an earlier copy would silently appear to
    /// be on the Free tier after updating — their licence would look lost.
    /// Copy rather than move, so a failure leaves the original intact.
    /// </summary>
    private void MigrateFromLegacyLocation()
    {
        try
        {
            if (File.Exists(SettingsPath)) return;

            var legacy = Path.Combine(LegacyDirectory, "settings.json");
            if (!File.Exists(legacy)) return;

            // DPAPI is scoped to the user, not the path, so the blob still
            // decrypts after the move.
            File.Copy(legacy, SettingsPath, overwrite: false);
            Log.Info($"migrated settings from {legacy} to {SettingsPath}");
        }
        catch (Exception ex)
        {
            Log.Warn($"settings migration skipped: {ex.Message}");
        }
    }

    private sealed class Envelope
    {
        public int Version { get; set; } = 1;
        public bool Protected { get; set; } = true;
        public string Entropy { get; set; } = EntropyLabel;
        public string WrittenUtc { get; set; } = "";
        public string Data { get; set; } = "";
    }

    public AppSettings Load()
    {
        lock (_gate)
        {
            try
            {
                if (!File.Exists(SettingsPath)) return new AppSettings();

                var envelope = JsonSerializer.Deserialize<Envelope>(File.ReadAllText(SettingsPath));
                if (envelope is null || string.IsNullOrEmpty(envelope.Data)) return new AppSettings();

                var cipher = Convert.FromBase64String(envelope.Data);
                var plain = envelope.Protected
                    ? ProtectedData.Unprotect(cipher, Entropy, DataProtectionScope.CurrentUser)
                    : cipher;

                return JsonSerializer.Deserialize<AppSettings>(Encoding.UTF8.GetString(plain))
                       ?? new AppSettings();
            }
            catch (Exception ex)
            {
                // A corrupt or foreign-user blob must not brick the app. Move it
                // aside so the next save starts clean and the evidence survives.
                Log.Warn($"settings load failed ({ex.GetType().Name}: {ex.Message}); starting fresh");
                TryQuarantine();
                return new AppSettings();
            }
        }
    }

    public void Save(AppSettings settings)
    {
        lock (_gate)
        {
            var plain = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(settings, JsonOpts));
            var cipher = ProtectedData.Protect(plain, Entropy, DataProtectionScope.CurrentUser);

            var envelope = new Envelope
            {
                WrittenUtc = DateTime.UtcNow.ToString("o"),
                Data = Convert.ToBase64String(cipher),
            };

            // Write-then-replace so a crash mid-write cannot truncate the file.
            var temp = SettingsPath + ".tmp";
            File.WriteAllText(temp, JsonSerializer.Serialize(envelope, JsonOpts));

            if (File.Exists(SettingsPath)) File.Replace(temp, SettingsPath, null);
            else File.Move(temp, SettingsPath);
        }
    }

    /// <summary>Wipes stored settings. Used by the automation suite's clean-state launch.</summary>
    public void Reset()
    {
        lock (_gate)
        {
            if (File.Exists(SettingsPath)) File.Delete(SettingsPath);
        }
    }

    private void TryQuarantine()
    {
        try
        {
            if (!File.Exists(SettingsPath)) return;
            var dest = SettingsPath + $".corrupt-{DateTime.UtcNow:yyyyMMddHHmmss}";
            File.Move(SettingsPath, dest);
        }
        catch
        {
            // Best effort only.
        }
    }
}
