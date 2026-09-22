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

    /// <summary>
    /// The plain-text bytes of the last thing actually written to disk, so a
    /// Save() that changed nothing can be coalesced away under <see cref="_gate"/>
    /// instead of re-encrypting and rewriting an identical file.
    /// </summary>
    private byte[]? _lastWrittenPlain;

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

                var loaded = JsonSerializer.Deserialize<AppSettings>(Encoding.UTF8.GetString(plain))
                       ?? new AppSettings();

                // Remember what disk already holds, so a Save() that changes
                // nothing after a fresh Load() is recognised as a no-op too.
                _lastWrittenPlain = plain;
                return loaded;
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

    /// <summary>
    /// Serializes and writes <paramref name="settings"/>.
    ///
    /// Callers own the threading contract, not this method: <c>settings</c> is
    /// the live, mutable object the rest of the app reads and writes, so it
    /// must already belong exclusively to whichever thread calls Save — the UI
    /// thread for every in-app change, and (via <see cref="LicenseService"/>'s
    /// dispatcher marshalling) for background licence verdicts too. Given
    /// that, Save still takes its own copy with <see cref="AppSettings.Clone"/>
    /// before doing anything slow, so the DPAPI encrypt and the file write —
    /// the part of this call that can't finish in a microsecond — never hold a
    /// reference to the object anything else might still be mutating (#202).
    /// </summary>
    public void Save(AppSettings settings)
    {
        var snapshot = settings.Clone();
        var plain = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(snapshot, JsonOpts));

        lock (_gate)
        {
            // Coalesce: a save that would write exactly what's already on
            // disk (a background refresh confirming the same status, a tick
            // that touched nothing) is skipped. There's nothing to lose on a
            // crash when nothing changed, and it saves an encrypt + a write.
            if (_lastWrittenPlain is not null && plain.AsSpan().SequenceEqual(_lastWrittenPlain))
                return;

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

            _lastWrittenPlain = plain;
        }
    }

    /// <summary>Wipes stored settings. Used by the automation suite's clean-state launch.</summary>
    public void Reset()
    {
        lock (_gate)
        {
            if (File.Exists(SettingsPath)) File.Delete(SettingsPath);
            // Otherwise the next Save() could see a match against the file
            // that was just deleted and wrongly coalesce itself away.
            _lastWrittenPlain = null;
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
