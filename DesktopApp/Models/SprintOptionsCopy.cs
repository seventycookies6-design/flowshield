namespace FlowShield.Models;

/// <summary>
/// The one line Today shows in place of the length, shield and cycle pickers
/// (#147, the Today declutter): "25 min · Firm shield · One sprint".
///
/// Today leads with the timer and Start sprint, and the template chips already
/// preset all three choices (F6), so the pickers fold away behind this line and
/// its Change button. The line has to say what Start will actually do, so it
/// is built from the same values Start reads, never from a template's name.
/// </summary>
public static class SprintOptionsCopy
{
    public const string Separator = " · ";

    public static string ShieldName(ShieldLevel level) => level switch
    {
        ShieldLevel.Soft => "Soft shield",
        ShieldLevel.Firm => "Firm shield",
        _ => "Sealed shield",
    };

    /// <summary>0 or 1 means a single sprint; 2 to 4 is a cycle with breaks between (F5).</summary>
    public static string CycleName(int cycleSprints) => cycleSprints > 1
        ? $"{cycleSprints} sprints with breaks"
        : "One sprint";

    /// <summary>
    /// <paramref name="minutes"/> is 0 while a custom length is being typed and
    /// isn't valid yet; the line says so rather than showing a length Start
    /// would refuse.
    /// </summary>
    public static string Summary(int minutes, ShieldLevel shield, int cycleSprints)
    {
        var length = minutes > 0 ? $"{minutes} min" : "Custom length";
        return length + Separator + ShieldName(shield) + Separator + CycleName(cycleSprints);
    }
}
