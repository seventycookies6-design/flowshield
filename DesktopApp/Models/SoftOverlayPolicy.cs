using System.Globalization;

namespace FlowShield.Models;

/// <summary>
/// When the Soft shield's full-screen notice may appear (launch checklist F7,
/// roadmap 1.7).
///
/// Soft closes nothing on its own; the Close button is the user's choice,
/// carried out by <c>AppBlockerService.AskToClose</c>. So the notice is the
/// whole intervention: a blocked app comes to the foreground during a sprint
/// and FlowShield says so, once, then gets out of the way. Two rules keep it
/// from becoming the thing people turn off:
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

    /// <summary>Set by --short-timers so the UI suite isn't waiting thirty seconds.</summary>
    public static bool UseShortTimers { get; set; }

    /// <summary>
    /// The wait before "Allow 5 minutes" can be pressed: 5, 10, 20, then 30
    /// seconds for every later try this sprint. A wait helped in the one sec
    /// study; one that grows keeps it from going stale.
    /// </summary>
    public static TimeSpan AllowWait(int tryNumber)
    {
        if (UseShortTimers) return TimeSpan.FromSeconds(1);
        return TimeSpan.FromSeconds(tryNumber switch
        {
            <= 1 => 5,
            2 => 10,
            3 => 20,
            _ => 30,
        });
    }

    /// <summary>Notices shown this sprint, across every app. The try number of the one on screen.</summary>
    public int Tries { get; private set; }

    /// <summary>Close or Back to work, this sprint. Allow doesn't count.</summary>
    public int TurnedBack { get; private set; }

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
        Tries++;
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

    /// <summary>"Back to work": down now, and quiet for a few seconds. Counts as turned back.</summary>
    public void BackToWork(string displayName, DateTime nowUtc)
    {
        TurnedBack++;
        Quieten(displayName, nowUtc, BackToWorkQuiet);
    }

    /// <summary>"Close Discord": the user chose to close it. Counts as turned back and goes quiet like Back to work.</summary>
    public void CloseIt(string displayName, DateTime nowUtc)
    {
        TurnedBack++;
        Quieten(displayName, nowUtc, BackToWorkQuiet);
    }

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
    /// is for the sprint it was granted in, never the next one, and so are the
    /// tries and turned-back counts.
    /// </summary>
    public void Reset()
    {
        _quietUntil.Clear();
        _sighting = null;
        _showing = false;
        Tries = 0;
        TurnedBack = 0;
    }
}

/// <summary>
/// What the Soft notice says. DESIGN_SYSTEM.md §7 "Intervention moments" asks
/// for one sentence naming the app and the time left, and §9 for a calm voice:
/// state the fact, no telling-off, no exclamation marks.
/// </summary>
public static class SoftOverlayCopy
{
    /// <summary>
    /// Four calm ways to say the same thing, chosen by the try number so the
    /// notice doesn't go stale (habituation fades fixed friction). Try 1 is
    /// DESIGN_SYSTEM.md section 7's own example.
    /// </summary>
    public static string Sentence(string displayName, DateTime endsAtLocal, int tryNumber)
    {
        var until = Until(endsAtLocal);
        return ((Math.Max(tryNumber, 1) - 1) % 4) switch
        {
            0 => $"{displayName} is on your blocklist until {until}",
            1 => $"You set this time aside until {until}",
            2 => $"{displayName} can wait until {until}",
            _ => $"This sprint runs until {until}. {displayName} will still be there",
        };
    }

    /// <summary>"Discord is on your blocklist until 5:45 PM" — §7's own example, the first try's wording.</summary>
    public static string Sentence(string displayName, DateTime endsAtLocal) =>
        Sentence(displayName, endsAtLocal, 1);

    /// <summary>"3rd try this sprint".</summary>
    public static string TryLine(int tryNumber)
    {
        var n = Math.Max(tryNumber, 1);
        var suffix = (n % 100) is 11 or 12 or 13 ? "th" : (n % 10) switch
        {
            1 => "st",
            2 => "nd",
            3 => "rd",
            _ => "th",
        };
        return $"{n}{suffix} try this sprint";
    }

    /// <summary>"You planned: finish chapter 3", or nothing when no intention was set.</summary>
    public static string Intention(string? intention)
    {
        var text = (intention ?? "").Trim();
        return text.Length == 0 ? "" : $"You planned: {text}";
    }

    /// <summary>
    /// The Allow button's label: the countdown after a middle dot while the
    /// wait runs ("0:08"), the plain label once it can be pressed. Text, so
    /// reduced motion changes nothing.
    /// </summary>
    public static string AllowLabel(TimeSpan left)
    {
        if (left <= TimeSpan.Zero) return "Allow 5 minutes";
        var seconds = (int)Math.Ceiling(left.TotalSeconds);
        return $"Allow 5 minutes \u00B7 {seconds / 60}:{seconds % 60:00}";
    }

    /// <summary>The note under the buttons: Soft's promise, in words.</summary>
    public const string CloseNote = "Nothing is closed unless you choose to.";

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
