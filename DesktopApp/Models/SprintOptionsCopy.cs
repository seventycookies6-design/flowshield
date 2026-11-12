namespace FlowShield.Models;

/// <summary>
/// The one line the Now card shows for what Start will do (#147, redrawn in
/// #431): "One 45-minute sprint", followed by the blocklist line. The setup
/// panel holds the length, cycle and blocklist pickers; the shield selector
/// sits right under this line, so the line no longer repeats the shield.
///
/// The line has to say what Start will actually do, so it is built from the
/// same values Start reads, never from a template's name. No middle dots
/// (DESIGN_SYSTEM.md Part A, Voice; redesign README).
/// </summary>
public static class SprintOptionsCopy
{
    private static readonly string[] Counts = { "One", "One", "Two", "Three", "Four" };

    /// <summary>0 or 1 means a single sprint; 2 to 4 is a cycle with breaks between (F5).</summary>
    public static string CycleName(int cycleSprints) => cycleSprints > 1
        ? $"{cycleSprints} sprints with breaks"
        : "One sprint";

    /// <summary>
    /// "One 45-minute sprint", or "Three 45-minute sprints with breaks".
    /// <paramref name="minutes"/> is 0 while a custom length is being typed and
    /// isn't valid yet; the line says so rather than showing a length Start
    /// would refuse.
    /// </summary>
    public static string Summary(int minutes, int cycleSprints)
    {
        var count = cycleSprints > 1 && cycleSprints < Counts.Length ? Counts[cycleSprints] : "One";
        var many = cycleSprints > 1;
        if (minutes <= 0)
            return many ? $"{count} sprints of a custom length" : "One sprint of a custom length";
        return many ? $"{count} {minutes}-minute sprints with breaks" : $"One {minutes}-minute sprint";
    }
}
