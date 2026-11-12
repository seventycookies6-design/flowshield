using System.Globalization;

namespace FlowShield.Models;

/// <summary>
/// When the Soft shield's full-screen notice may appear (launch checklist F7,
/// roadmap 1.7).
///
/// Soft closes nothing on its own; the Close button is the user's choice,
/// carried out by <c>AppBlockerService.AskToClose</c>. So the notice is the
/// whole intervention: a blocked app comes to the foreground during a sprint
/// and Basalt says so, once, then gets out of the way. Two rules keep it
/// from becoming the thing people turn off:
///
///   * <b>once per sighting.</b> The blocker sweeps every two seconds. Showing
///     the notice on every sweep while Discord is still in front would be a
///     flashing box, not a nudge, so it shows when the app <i>becomes</i> the
///     foreground window and not again until something else has been in front.
///     Close leans on this rule hardest: the app may well stay in front after
///     the ask (its own "save changes?" prompt, or an app that ignores it),
///     and the notice must not come back over that prompt. So Close answers
///     the sighting rather than clearing it, and nothing shows again until the
///     app has left the foreground and returned.
///   * <b>a suppression window.</b> "Allow 5 minutes" means five minutes of
///     silence for that app. "Back to work" gets a few quiet seconds too —
///     bringing Basalt forward takes a moment, and the notice must not
///     reappear in the gap before it does. Close keeps the same few seconds,
///     so a quick bounce out of the app and back does not re-trigger it.
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
    /// study; one that grows keeps it from going stale. Under --short-timers
    /// every try waits three seconds: long enough for the UI suite to see the
    /// button disabled before the wait runs out, short enough not to wait on.
    /// </summary>
    public static TimeSpan AllowWait(int tryNumber)
    {
        if (UseShortTimers) return TimeSpan.FromSeconds(3);
        return TimeSpan.FromSeconds(tryNumber switch
        {
            <= 1 => 5,
            2 => 10,
            3 => 20,
            _ => 30,
        });
    }

    /// <summary>Set by --long-notice-lock, so the UI suite can act inside the lock.</summary>
    public static bool UseLongInputLock { get; set; }

    /// <summary>
    /// How long every button on the notice ignores input when it opens (#432,
    /// DESIGN_SYSTEM.md Part A, Interruptions): about 1.5 seconds, so someone
    /// still typing in the blocked app can't answer it by accident. Not
    /// shortened by --short-timers. --long-notice-lock stretches it to six
    /// seconds, longer than a UIA round trip, only so tier 3 can watch a click
    /// being ignored; it changes no rule, only the clock.
    /// </summary>
    public static TimeSpan InputLock =>
        UseLongInputLock ? TimeSpan.FromSeconds(6) : TimeSpan.FromMilliseconds(1500);

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

    /// <summary>
    /// "Close Discord": the user chose to close it. Counts as turned back and
    /// takes the notice down, with the same few quiet seconds as Back to work
    /// for a quick bounce. Unlike Back to work it keeps the sighting: the app
    /// may stay in front (its own "save changes?" prompt, or an app that
    /// ignores the ask), and the notice must not come back over that. It shows
    /// again only once the app has left the foreground and returned, which
    /// <see cref="LeftTheForeground"/> already handles.
    /// </summary>
    public void CloseIt(string displayName, DateTime nowUtc)
    {
        TurnedBack++;
        _quietUntil[displayName] = nowUtc + BackToWorkQuiet;
        _showing = false;
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
/// What the Soft notice says. DESIGN_SYSTEM.md Part A asks for plain,
/// specific words with no exclamation marks, and the redesign (#432) for the
/// customer's own plan as the headline, the blocklist fact under it, and
/// commas rather than middle dots between facts.
/// </summary>
public static class SoftOverlayCopy
{
    /// <summary>The name at the start of the line above the headline.</summary>
    public const string Brand = "Basalt";

    /// <summary>
    /// The line above the headline: "Basalt, Soft, your plan for this sprint",
    /// or "Basalt, Soft" when no plan was typed, so it never points at a plan
    /// that isn't there. A website's notice (F10 interim) shows at every
    /// shield, so it says what it is instead of naming one.
    /// </summary>
    public static string Eyebrow(bool hasPlan, bool isWebsite)
    {
        var what = isWebsite ? "website, notice only" : "Soft";
        return hasPlan ? $"{Brand}, {what}, your plan for this sprint" : $"{Brand}, {what}";
    }

    /// <summary>"Discord is on your blocklist until 5:45 PM", DESIGN_SYSTEM.md's own example.</summary>
    /// <remarks>
    /// One wording on every try (#432): the four rotating wordings of 1.0.10
    /// gave way to the try count, which says the same thing plainly.
    /// </remarks>
    public static string Sentence(string displayName, DateTime endsAtLocal) =>
        $"{displayName} is on your blocklist until {Until(endsAtLocal)}";

    /// <summary>The customer's plan for the sprint, trimmed, or nothing when none was typed.</summary>
    public static string Plan(string? plan) => (plan ?? "").Trim();

    /// <summary>
    /// The headline: the plan, or the blocklist sentence when there is no
    /// plan (#432). The sentence then isn't repeated under it.
    /// </summary>
    public static string Headline(string plan, string sentence) =>
        plan.Length > 0 ? plan : sentence;

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

    /// <summary>
    /// The try count shows from the second try only (#432): on the first, "1st
    /// try" is noise.
    /// </summary>
    public static bool ShowsTryLine(int tryNumber) => tryNumber >= 2;

    /// <summary>
    /// The Allow button's label: "Allow 5 minutes in 0:08" while its own wait
    /// runs, the plain label once it can be pressed. Text, so reduced motion
    /// changes nothing.
    /// </summary>
    public static string AllowLabel(TimeSpan left)
    {
        if (left <= TimeSpan.Zero) return "Allow 5 minutes";
        var seconds = (int)Math.Ceiling(left.TotalSeconds);
        return $"Allow 5 minutes in {seconds / 60}:{seconds % 60:00}";
    }

    /// <summary>
    /// The lock bar while the buttons ignore input (#432): "Buttons unlock in
    /// 0.9 s", counting down beside the bar. With reduced motion the bar is
    /// hidden and the text, which then doesn't tick either, still states the
    /// wait.
    /// </summary>
    public static string LockWait(TimeSpan left, bool reducedMotion)
    {
        if (reducedMotion)
            return $"Buttons unlock after {SoftOverlayPolicy.InputLock.TotalSeconds.ToString("0.#", CultureInfo.CurrentCulture)} seconds";
        var seconds = Math.Max(left.TotalSeconds, 0);
        return $"Buttons unlock in {seconds.ToString("0.0", CultureInfo.CurrentCulture)} s";
    }

    /// <summary>The lock bar's line once the buttons work: how to answer from the keyboard too.</summary>
    public const string Unlocked = "Click a button, or press Tab then Space.";

    /// <summary>The note under the headline: Soft's promise, in words.</summary>
    public const string CloseNote = "Nothing is closed unless you choose to.";

    /// <summary>
    /// The note on a website's notice (F10 interim): what Basalt does and does
    /// not do with the browser, in words.
    /// </summary>
    public const string WebsiteNote = "Your browser stays open. Basalt only reads the title of the tab in front.";

    /// <summary>The sprint's end time in the user's own short-time format.</summary>
    public static string Until(DateTime endsAtLocal) =>
        // A no-break space (and Windows' narrow one) keeps "10:29 AM" on one
        // line: the 52 px headline broke it as "10:29 / AM" on a real PC.
        endsAtLocal.ToString("t", CultureInfo.CurrentCulture)
            .Replace(' ', '\u00A0')
            .Replace('\u202F', '\u00A0');

    /// <summary>The countdown in the notice's ring: "14:50", or "1:02:03" past an hour.</summary>
    public static string Clock(TimeSpan remaining)
    {
        if (remaining <= TimeSpan.Zero) return "0:00";
        var seconds = (int)Math.Ceiling(remaining.TotalSeconds);
        return seconds >= 3600
            ? $"{seconds / 3600}:{seconds / 60 % 60:00}:{seconds % 60:00}"
            : $"{seconds / 60}:{seconds % 60:00}";
    }

    /// <summary>
    /// "25 minutes left in this sprint", specific, as Part A's voice asks. The
    /// ring's spoken name, so a screen reader hears more than "14:50".
    /// </summary>
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
