namespace FlowShield.Models;

/// <summary>
/// What Today says about a break (F5): the offer, the break while it runs, and
/// the state line under the ring.
///
/// A break stands the sprint's shield down, but inside the nightly sleep window
/// the sleep shield keeps closing blocked apps (#272, #301). So every line that
/// says the shield is down has a sleep-window twin saying which shield is still
/// up. Pure, so tier 1 can pin each branch word for word.
/// </summary>
public static class BreakCopy
{
    /// <summary>The break card's line: the offer before a break starts, or the break running.</summary>
    /// <param name="sleepEndsText">When the sleep window closes, as the Sleep Blocking page writes it.</param>
    public static string PanelText(bool inSleepWindow, bool onBreak, bool isLong, int minutes, string sleepEndsText)
    {
        if (onBreak)
            return inSleepWindow
                ? $"The sprint's shield is down, but your nightly sleep shield is still up — blocked apps are still closed until it ends at {sleepEndsText}."
                : "The shield is down. Blocked apps are allowed until the break ends.";

        if (isLong)
            return inSleepWindow
                ? $"{CycleState.LongBreakEvery} sprints in a row, so this break is {minutes} minutes. The sprint's shield comes down, but your nightly sleep shield stays up until {sleepEndsText}, so blocked apps are still closed."
                : $"{CycleState.LongBreakEvery} sprints in a row, so this break is {minutes} minutes. The shield stays down while it runs.";

        return inSleepWindow
            ? $"{minutes} minutes with the sprint's shield down, but your nightly sleep shield stays up until {sleepEndsText}, so blocked apps are still closed."
            : $"{minutes} minutes with the shield down. It changes nothing about your momentum.";
    }

    /// <summary>
    /// The state line under the ring while a break runs. At its line the ring
    /// has about 177 px; since #304 the line wraps, centred, inside that. The
    /// two resumed lines are too long for one line, so they break after the
    /// dash themselves rather than wherever the width runs out ("the shield /
    /// is down"). Tier 5 lays out each one in the real view.
    /// </summary>
    /// <param name="resumed">The break was picked up again after FlowShield restarted (F5).</param>
    public static string Caption(bool inSleepWindow, bool resumed) => (resumed, inSleepWindow) switch
    {
        (false, false) => "Break — the shield is down",
        (true, false) => "Break resumed —\nthe shield is down",
        (false, true) => "Break — sleep shield still up",
        (true, true) => "Break resumed —\nsleep shield still up",
    };

    /// <summary>
    /// The five-minutes-left notification (#304). It speaks about the moment
    /// the time is up, so the caller asks about the sleep window at that
    /// moment: inside it only the sprint's shield comes down.
    /// </summary>
    /// <param name="inSleepWindow">The nightly sleep window is open when the sprint ends.</param>
    /// <param name="sleepEndsText">When the sleep window closes, as the Sleep Blocking page writes it.</param>
    public static string EndingSoon(bool inSleepWindow, string sleepEndsText) => inSleepWindow
        ? $"Nearly there — the sprint's shield comes down when the time is up, but your nightly sleep shield stays up until {sleepEndsText}."
        : "Nearly there — the shield comes down when the time is up.";
}
