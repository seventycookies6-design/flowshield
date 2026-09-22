namespace FlowShield.Models;

/// <summary>
/// Roadmap 5.7 — one row of the licence's "Your devices" list, as read from
/// <c>POST /devices</c>.
///
/// <see cref="DeviceToken"/> is not the server's raw stored device id — the
/// server deliberately never returns that (see server.js's <c>deviceToken</c>
/// helper and its docstring "Names only, never the raw ids"). It is a
/// one-way, per-licence token the app can send back to release that specific
/// device without ever learning its real identifier.
/// </summary>
public record DeviceInfo(
    string Name,
    string DeviceToken,
    bool IsCurrent,
    DateTime? LastSeenUtc);

/// <summary>The outcome of asking the server which devices hold a seat.</summary>
public record DeviceListResult(
    bool Ok,
    IReadOnlyList<DeviceInfo> Devices,
    int DeviceCount,
    int DeviceLimit,
    string? Error = null);
