namespace FlowShield.Infrastructure;

/// <summary>
/// How big Today's timer ring is drawn for the page it sits on (#406, resized
/// for the Now card in #431). The ring is laid out at <see cref="Drawn"/> and
/// scaled as a whole, so it shrinks on a short window instead of pushing
/// Templates out of sight, and grows to the mockups' size on a tall one. Kept
/// apart from the view so tier 1 can run the rule itself.
/// </summary>
public static class TimerRingSize
{
    /// <summary>The size the ring's parts are laid out at, before scaling.</summary>
    public const double Drawn = 222;

    /// <summary>The smallest and largest the ring is shown: 160 on the small window, 228 on a tall one.</summary>
    public const double Smallest = 160, Largest = 228;

    /// <summary>
    /// The ring's size for a page <paramref name="height"/> tall: about a third
    /// of it, between <see cref="Smallest"/> and <see cref="Largest"/>. At the
    /// small window (1092 × 614, a page about 480 tall) that is the mockup's
    /// 160 or so, so the Now card, the side cards and Templates all fit.
    /// </summary>
    public static double For(double height) =>
        double.IsNaN(height) || double.IsInfinity(height)
            ? Smallest
            : Math.Clamp(Math.Round(height * 0.34), Smallest, Largest);
}
