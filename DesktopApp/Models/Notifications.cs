namespace FlowShield.Models;

/// <summary>Everything FlowShield may notify about (launch checklist F19).</summary>
public enum NotificationKind
{
    SprintStarted,
    FiveMinutesLeft,
    SprintComplete,
    SprintInterrupted,

    /// <summary>A break has finished (F5).</summary>
    BreakOver,

    /// <summary>A scheduled sprint is about to start (F6).</summary>
    ScheduledSprint,

    /// <summary>One day of the free trial left.</summary>
    TrialEnding,

    /// <summary>
    /// A blocked app is about to be closed, with a few seconds to save (F7).
    ///
    /// This one interrupts on purpose. Every other notice can wait; a warning
    /// that arrives after the app has gone is not a warning.
    /// </summary>
    AppClosing,
}

/// <summary>
/// What clicking a notification does. <see cref="OpenToday"/> is for a notice
/// whose card is on Today (a schedule's heads-up or missed start, F6), so the
/// click lands where the body points rather than on whatever page was open.
/// </summary>
public enum NotificationAction { OpenApp, OpenJournal, OpenSettingsLicense, OpenToday }

public record Notification(NotificationKind Kind, string Title, string Message, NotificationAction Action);

/// <summary>
/// When FlowShield is allowed to interrupt you (F19).
///
/// A blocker that nags is a blocker people turn off, so the rules are strict:
/// everything is switchable, and nothing about money or the trial ever appears
/// during a sprint — that one is also F20's promise.
/// Kept free of UI so the rules can be tested on their own.
/// </summary>
public static class NotificationPolicy
{
    /// <summary>How long before the end the "5 minutes left" notice fires.</summary>
    public static readonly TimeSpan EndingSoon = TimeSpan.FromMinutes(5);

    /// <summary>Notifications that must never appear while a sprint is running.</summary>
    public static bool InterruptsFocus(NotificationKind kind) =>
        kind is NotificationKind.TrialEnding;

    public static bool ShouldShow(NotificationKind kind, AppSettings settings, bool sprintRunning) =>
        settings.IsNotificationOn(kind) && !(sprintRunning && InterruptsFocus(kind));

    /// <summary>A sprint short enough that "5 minutes left" would follow "started" immediately.</summary>
    public static bool TooShortForEndingSoon(int plannedMinutes) =>
        plannedMinutes <= EndingSoon.TotalMinutes + 1;

    /// <summary>
    /// The break countdown as the tray and the window title show it: "Break · 4:59".
    ///
    /// Seconds rather than minutes, unlike a sprint: a five-minute break rounded
    /// to whole minutes would read "5 minutes left" for most of itself (F5).
    /// </summary>
    public static string BreakLabel(TimeSpan remaining)
    {
        if (remaining < TimeSpan.Zero) remaining = TimeSpan.Zero;
        return $"Break · {(int)remaining.TotalMinutes}:{remaining.Seconds:00}";
    }

    /// <summary>The tray tooltip: what FlowShield is doing right now.</summary>
    public static string TrayText(bool running, ShieldLevel shield, TimeSpan remaining, bool onBreak = false)
    {
        // A break says so instead of naming a shield: during one the shield is
        // down, and claiming otherwise in the tooltip would be a lie (F5).
        if (onBreak) return $"FlowShield — {BreakLabel(remaining)}";
        if (!running) return "FlowShield — no sprint running";
        var minutes = Math.Max(1, (int)Math.Ceiling(remaining.TotalMinutes));
        return $"FlowShield — {shield} shield, {minutes} minute{(minutes == 1 ? "" : "s")} left";
    }

    /// <summary>What the countdown tray icon shows: minutes left, or hours over an hour.</summary>
    public static string TrayIconText(TimeSpan remaining)
    {
        if (remaining <= TimeSpan.Zero) return "0";
        var minutes = (int)Math.Ceiling(remaining.TotalMinutes);
        return minutes >= 100 ? $"{minutes / 60}h" : minutes.ToString();
    }
}
