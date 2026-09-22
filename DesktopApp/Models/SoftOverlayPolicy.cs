using System.Globalization;

namespace FlowShield.Models;

/// <summary>
/// When the Soft shield's full-screen notice may appear (launch checklist F7,
/// roadmap 1.7).
///
/// Soft closes nothing, so the notice is the whole intervention: a blocked app
/// comes to the foreground during a sprint and FlowShield says so, once, then
/// gets out of the way. Two rules keep it from becoming the thing people turn
/// off:
///
///   * <b>once per sighting.</b> The blocker sweeps every two seconds. Showing
///     the notice on every sweep while Discord is still in front would be a
///     flashing box, not a nudge, so it shows when the app <i>becomes</i> the
///     foreground window and not again until something else has been in front.
///   * <b>a suppression window.</b> "Allow 5 minutes" means five minutes of
///     silence for that app. "Back to work" gets a few quiet seconds too —
///     bringing FlowShield forward takes a moment, and the notice must not
///     reappear in the gap before it does.
///
/// Kept free of UI, timers and Win32 so both rules can be tested on their own
/// (tier 1). The sighting is still counted as a distraction by
/// <c>AppBlockerService</c>'s own one-per-app rule (#140); this class only
/// decides whether anything is drawn.
/// </summary>
public class SoftOverlayPolicy
{
    /// <summary>What "Allow 5 minutes" buys, per app.</summary>
    public static readonly TimeSpan AllowWindow = TimeSpan.FromMinutes(5);

    /// <summary>
    /// The quiet moment after "Back to work", so the notice does not come
    /// straight back while the blocked app is still the foreground window.
    /// </summary>
    public static readonly TimeSpan BackToWorkQuiet = TimeSpan.FromSeconds(5);

    private readonly Dictionary<string, DateTime> _quietUntil =
        new(StringComparer.OrdinalIgnoreCase);

    /// <summary>The blocked app in front right now, or null when none is.</summary>
    private string? _sighting;

    /// <summary>True while a notice is on screen, so it is only closed once.</summary>
    private bool _showing;

    /// <summary>
    /// A blocked app is the foreground window. True when the notice should be
    /// shown for it now.
    /// </summary>
    public bool ShouldShow(string displayName, DateTime nowUtc)
    {
        var isNewSighting = !string.Equals(_sighting, displayName, StringComparison.OrdinalIgnoreCase);
        _sighting = displayName;

        if (!isNewSighting) return false;
        if (IsQuiet(displayName, nowUtc)) return false;

        _showing = true;
        return true;
    }

    /// <summary>
    /// The foreground window is not a blocked app any more. Returns true when a
    /// notice was up and should now be taken down.
    /// </summary>
    public bool LeftTheForeground()
    {
        _sighting = null;
        var wasShowing = _showing;
        _showing = false;
        return wasShowing;
    }

    /// <summary>"Allow 5 minutes": no notice for this app until the window is up.</summary>
    public void AllowFiveMinutes(string displayName, DateTime nowUtc) =>
        Quieten(displayName, nowUtc, AllowWindow);

    /// <summary>"Back to work": down now, and quiet for a few seconds.</summary>
    public void BackToWork(string displayName, DateTime nowUtc) =>
        Quieten(displayName, nowUtc, BackToWorkQuiet);

    private void Quieten(string displayName, DateTime nowUtc, TimeSpan window)
    {
        _quietUntil[displayName] = nowUtc + window;
        // Cleared so returning to the app after the window counts as a fresh
        // sighting rather than the same one the user already answered.
        _sighting = null;
        _showing = false;
    }

    public bool IsQuiet(string displayName, DateTime nowUtc) =>
        _quietUntil.TryGetValue(displayName, out var until) && nowUtc < until;

    /// <summary>
    /// Forget everything. Called when enforcement starts or stops: an allowance
    /// is for the sprint it was granted in, never the next one.
    /// </summary>
    public void Reset()
    {
        _quietUntil.Clear();
        _sighting = null;
        _showing = false;
    }
}

/// <summary>
/// What the Soft notice says. DESIGN_SYSTEM.md §7 "Intervention moments" asks
/// for one sentence naming the app and the time left, and §9 for a calm voice:
/// state the fact, no telling-off, no exclamation marks.
/// </summary>
public static class SoftOverlayCopy
{
    /// <summary>"Discord is on your blocklist until 5:45 PM" — §7's own example.</summary>
    public static string Sentence(string displayName, DateTime endsAtLocal) =>
        $"{displayName} is on your blocklist until {Until(endsAtLocal)}";

    /// <summary>The sprint's end time in the user's own short-time format.</summary>
    public static string Until(DateTime endsAtLocal) =>
        endsAtLocal.ToString("t", CultureInfo.CurrentCulture);

    /// <summary>"25 minutes left in this sprint" — specific, per §9.</summary>
    public static string TimeLeft(TimeSpan remaining)
    {
        if (remaining <= TimeSpan.Zero) return "This sprint is ending";
        var minutes = (int)Math.Ceiling(remaining.TotalMinutes);
        return minutes == 1
            ? "1 minute left in this sprint"
            : $"{minutes} minutes left in this sprint";
    }

    /// <summary>The toast after "Allow 5 minutes", so the choice is on the record.</summary>
    public static string Allowed(string displayName) =>
        $"{displayName} allowed for 5 minutes. It still counted as a distraction.";
}
