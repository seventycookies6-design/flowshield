using FlowShield.Infrastructure;
using FlowShield.Models;

namespace FlowShield.ViewModels;

/// <summary>
/// One row of Settings' "Your devices" list (Roadmap 5.7). Wraps the
/// server's <see cref="DeviceInfo"/> with the local, view-only "are you
/// sure?" state for its quiet Release button (DESIGN_SYSTEM.md §7).
/// </summary>
public class DeviceRowViewModel : ViewModelBase
{
    public DeviceRowViewModel(DeviceInfo device)
    {
        Name = device.IsCurrent ? $"{device.Name} (this PC)" : device.Name;
        DeviceToken = device.DeviceToken;
        IsCurrent = device.IsCurrent;
        LastSeenText = device.LastSeenUtc is { } utc
            ? $"Last seen {utc.ToLocalTime():d MMM, HH:mm}"
            : "Last seen unknown";
    }

    public string Name { get; }
    public string DeviceToken { get; }
    public bool IsCurrent { get; }
    public string LastSeenText { get; }

    /// <summary>Only other devices get a Release button — releasing this
    /// machine's own seat is Deactivate, not this list.</summary>
    public bool CanRelease => !IsCurrent;

    private bool _isConfirmingRelease;
    /// <summary>True between clicking Release and either confirming or cancelling.</summary>
    public bool IsConfirmingRelease
    {
        get => _isConfirmingRelease;
        set => Set(ref _isConfirmingRelease, value);
    }

    private bool _isReleasing;
    public bool IsReleasing { get => _isReleasing; set => Set(ref _isReleasing, value); }
}
