using Velopack;
using Velopack.Sources;

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
public class UpdateService
{
    // Public repository, so no token is needed to read releases.
    private const string ReleaseFeed = "https://github.com/seventycookies6-design/flowshield";

    private readonly UpdateManager? _manager;

    public UpdateService()
    {
        try
        {
            _manager = new UpdateManager(new GithubSource(ReleaseFeed, null, false));
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

    public bool UpdateReady => _pending is not null;

    public string? PendingVersion => _pending?.TargetFullRelease?.Version?.ToString();

    /// <summary>
    /// Look for an update and stage it. Returns the new version, or null.
    /// Never throws: a failed update check must not disturb a working app.
    /// </summary>
    public async Task<string?> CheckAndDownloadAsync()
    {
        if (_manager is null || !_manager.IsInstalled) return null;

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
    public bool ApplyAndRestart(bool sprintRunning)
    {
        if (_manager is null || _pending is null) return false;
        if (sprintRunning)
        {
            Log.Warn("update deferred: a sprint is running");
            return false;
        }

        try
        {
            Log.Info($"applying update {_pending.TargetFullRelease.Version} and restarting");
            _manager.ApplyUpdatesAndRestart(_pending);
            return true;
        }
        catch (Exception ex)
        {
            Log.Error("applying the update failed", ex);
            return false;
        }
    }
}
