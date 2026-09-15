namespace FlowShield.Models;

/// <summary>
/// Who sees the first-run welcome (launch checklist F18). Kept free of UI so
/// the rules can be tested on their own.
/// </summary>
public static class FirstRunPolicy
{
    /// <summary>Set by --skip-first-run so the UI test suite starts on Today.</summary>
    public static bool SkipForTests { get; set; }

    /// <summary>
    /// Shown once, to someone genuinely new: never to an existing user after an
    /// update, never over the trial-ended lock screen, and never on top of a
    /// sprint that a restart has just resumed.
    /// </summary>
    public static bool ShouldShow(AppSettings settings, bool hasAccess, bool sprintRunning) =>
        !SkipForTests
        && !settings.FirstRunCompleted
        && !IsExistingUser(settings)
        && hasAccess
        && !sprintRunning;

    /// <summary>Anyone with a blocklist or past sprints has already set FlowShield up.</summary>
    public static bool IsExistingUser(AppSettings settings) =>
        settings.BlockedApps.Count > 0 || settings.Sessions.Count > 0 || settings.ActiveSprint is not null;

    /// <summary>The suggestions ticked for the user to confirm: found on this PC, and never a browser.</summary>
    public static bool PreTicked(PickerEntry entry) =>
        entry.Source == PickerSource.Suggested
        && entry.ExePath is not null
        && !entry.Group.Equals("Browsers", StringComparison.OrdinalIgnoreCase);

    public static readonly int[] SprintLengths = { 25, 45 };
}
