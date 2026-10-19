using System.IO;
using Velopack;
using Velopack.Sources;
using FlowShield.Models;

namespace FlowShield.Services;

/// <summary>
/// Checks GitHub Releases for a newer build and applies it on next restart.
///
/// This exists because without it a shipped bug is permanent for everyone who
/// already installed. Updates are downloaded in the background and only take
/// effect when the user next restarts — never mid-session, because closing the
/// app during a sealed sprint would hand someone an escape hatch the whole
/// feature exists to remove.
/// </summary>
public class UpdateService : IUpdateService
{
    // Public repository, so no token is needed. The go-live batch (#166)
    // moves downloads off GitHub; keep the feed URL in this one constant.
    private const string ReleaseFeed = "https://github.com/seventycookies6-design/flowshield";

    private readonly UpdateManager? _manager;

    public UpdateService()
    {
        try
        {
            // VM testing only: never turn an override into another network feed.
            var feedOverride = Environment.GetEnvironmentVariable("FLOWSHIELD_UPDATE_FEED");
            IUpdateSource source;
            if (feedOverride is not null
                && Path.IsPathFullyQualified(feedOverride)
                && !feedOverride.StartsWith(@"\", StringComparison.Ordinal)
                && !feedOverride.StartsWith("/", StringComparison.Ordinal)
                && Directory.Exists(feedOverride))
            {
                source = new SimpleFileSource(new DirectoryInfo(feedOverride));
                Log.Info($"using local update feed: {feedOverride}");
            }
            else
            {
                if (feedOverride is not null)
                    Log.Warn("ignoring FLOWSHIELD_UPDATE_FEED: expected an existing absolute local directory");
                source = new GithubSource(ReleaseFeed, null, false);
            }
            _manager = new UpdateManager(source);
        }
        catch (Exception ex)
        {
            // A non-installed build (running from bin/ during development) has
            // no update context. That is normal, not an error.
            Log.Info($"updates unavailable in this context: {ex.Message}");
            _manager = null;
        }
    }

    /// <summary>True only for a properly installed copy.</summary>
    public bool IsSupported => _manager?.IsInstalled == true;

    public string CurrentVersion =>
        _manager?.CurrentVersion?.ToString()
        ?? typeof(UpdateService).Assembly.GetName().Version?.ToString(3)
        ?? "dev";

    private UpdateInfo? _pending;

    private VelopackAsset? PendingAsset => _pending?.TargetFullRelease
        ?? (IsSupported ? _manager?.UpdatePendingRestart : null);

    public bool UpdateReady => PendingAsset is not null;

    public string? PendingVersion => PendingAsset?.Version?.ToString();
    public string? PendingReleaseNotes => PendingAsset?.NotesMarkdown;

    /// <summary>Whether the last check failed, as opposed to finding nothing new.</summary>
    public bool LastCheckFailed { get; private set; }

    /// <summary>
    /// Look for an update and stage it. Returns the new version, or null.
    /// Never throws: a failed update check must not disturb a working app.
    /// </summary>
    public async Task<string?> CheckAndDownloadAsync()
    {
        if (_manager is null || !_manager.IsInstalled) return null;

        LastCheckFailed = false;
        try
        {
            var update = await _manager.CheckForUpdatesAsync();
            if (update is null)
            {
                Log.Info("update check: already on the latest version");
                return null;
            }

            Log.Info($"update available: {update.TargetFullRelease.Version}; downloading");
            await _manager.DownloadUpdatesAsync(update);

            _pending = update;
            Log.Info($"update {update.TargetFullRelease.Version} staged for next restart");
            return update.TargetFullRelease.Version.ToString();
        }
        catch (Exception ex)
        {
            Log.Warn($"update check failed: {ex.Message}");
            LastCheckFailed = true;
            return null;
        }
    }

    /// <summary>
    /// Restart into the downloaded update.
    ///
    /// Refused while a sprint is running: the caller is expected to check, but
    /// this is the guarantee. Restarting mid-sprint would drop the shield and
    /// let a sealed session be escaped by clicking "update".
    /// </summary>
    public bool ApplyAndRestart(UpdateActivity activity)
    {
        if (_manager is null || PendingAsset is not { } pending) return false;
        if (!UpdatePolicy.CanApply(activity))
        {
            Log.Info("update deferred: a routine or shield is active");
            return false;
        }

        try
        {
            Log.Info($"applying update {pending.Version} and restarting");
            _manager.ApplyUpdatesAndRestart(pending);
            return true;
        }
        catch (Exception ex)
        {
            Log.Error("applying the update failed", ex);
            return false;
        }
    }

    /// <summary>Actual exit only. The updater waits for us, then applies without relaunching.</summary>
    public bool ApplyOnQuit(UpdateActivity activity)
    {
        if (_manager is null || PendingAsset is not { } pending) return false;
        if (!UpdatePolicy.CanApply(activity)) return false;
        try
        {
            _manager.WaitExitThenApplyUpdates(pending, silent: true, restart: false);
            return true;
        }
        catch (Exception ex)
        {
            Log.Error("applying the update on exit failed", ex);
            return false;
        }
    }
}
