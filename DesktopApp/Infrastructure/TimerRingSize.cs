namespace FlowShield.Infrastructure;

/// <summary>
/// How big Today's timer ring is drawn for the page it sits on (#406). The
/// ring is laid out at <see cref="Smallest"/> and scaled as a whole, so on a
/// tall page it grows instead of leaving the lower half of the window empty.
/// Kept apart from the view so tier 1 can run the rule itself.
/// </summary>
public static class TimerRingSize
{
    /// <summary>The ring's drawn size, and the most it grows to on a tall page.</summary>
    public const double Smallest = 222, Largest = 320;

    /// <summary>
    /// The ring's size for a page <paramref name="height"/> tall: about a third
    /// of it, between <see cref="Smallest"/> and <see cref="Largest"/>. A third
    /// leaves the chips, Start and the sprint summary visible below it without
    /// scrolling, on any page tall enough to grow the ring at all.
    /// </summary>
    public static double For(double height) =>
        double.IsNaN(height) || double.IsInfinity(height)
            ? Smallest
            : Math.Clamp(Math.Round(height * 0.34), Smallest, Largest);
}
