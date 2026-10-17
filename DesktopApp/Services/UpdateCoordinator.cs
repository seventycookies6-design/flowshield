using FlowShield.Models;

namespace FlowShield.Services;

public interface IUpdateService
{
    bool IsSupported { get; }
    string CurrentVersion { get; }
    bool UpdateReady { get; }
    string? PendingVersion { get; }
    string? PendingReleaseNotes { get; }
    Task<string?> CheckAndDownloadAsync();
}

/// <summary>
/// Shared by the background timer and manual button. No timer or UI dependency:
/// the host supplies time and handles saving and native notification delivery.
/// </summary>
public sealed class UpdateCoordinator
{
    private readonly AppSettings _settings;
    private readonly IUpdateService _updates;
    private readonly Action _save;
    private readonly Func<UpdateActivity> _activity;
    private readonly Func<string, bool> _notify;
    private readonly DateTime _launchedUtc;
    private DateTime? _lastCheckUtc;
    private bool _stopped;

    public UpdateCoordinator(AppSettings settings, IUpdateService updates, Action save,
        Func<UpdateActivity> activity, Func<string, bool> notify, DateTime launchedUtc)
    {
        _settings = settings;
        _updates = updates;
        _save = save;
        _activity = activity;
        _notify = notify;
        _launchedUtc = launchedUtc;
    }

    public bool IsChecking { get; private set; }
    public event Action? Changed;

    public async Task TickAsync(DateTime nowUtc)
    {
        if (_stopped) return;
        if (UpdatePolicy.IsCheckDue(_settings.AutoCheckUpdates, _updates.IsSupported,
                _launchedUtc, _lastCheckUtc, nowUtc))
            await CheckAndDownloadAsync(nowUtc);
        if (!_stopped) NotifyIfReady();
    }

    public async Task<string?> CheckAndDownloadAsync(DateTime nowUtc)
    {
        if (_stopped || IsChecking || !_updates.IsSupported) return null;
        IsChecking = true;
        _lastCheckUtc = nowUtc; // Failures wait a day too; no repeated requests offline.
        Changed?.Invoke();
        try
        {
            var version = await _updates.CheckAndDownloadAsync();
            if (_stopped) return null;
            if (version is not null)
            {
                _settings.PendingReleaseVersion = version;
                _settings.PendingReleaseNotes = _updates.PendingReleaseNotes;
                _save(); // Notes must be on disk before the user can restart.
            }
            NotifyIfReady();
            return version;
        }
        catch (Exception ex)
        {
            Log.Warn($"background update check failed: {ex.Message}");
            return null;
        }
        finally
        {
            IsChecking = false;
            if (!_stopped) Changed?.Invoke();
        }
    }

    private void NotifyIfReady()
    {
        if (!_updates.UpdateReady || _updates.PendingVersion is not { } version
            || _settings.LastNotifiedUpdateVersion == version
            || !UpdatePolicy.CanApply(_activity())
            || !_settings.IsNotificationOn(NotificationKind.UpdateReady)) return;
        if (!_notify($"Basalt {version} is ready. It installs the next time Basalt restarts.")) return;
        _settings.LastNotifiedUpdateVersion = version;
        _save();
    }

    public void Stop() => _stopped = true;
}
