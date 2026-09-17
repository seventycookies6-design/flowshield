namespace FlowShield.Models;

/// <summary>
/// The one source for each shield's promise and "best for" wording (launch
/// checklist F1). Today, first run and the tests all read from here, so the
/// app's two surfaces and the website's shield section can't drift apart.
/// The scenarios mirror Website/index.html's "Three levels of resistance".
/// </summary>
public static class ShieldCopy
{
    /// <summary>Keeps to what AppBlockerService actually does at each level.</summary>
    public static string Promise(ShieldLevel level) => level switch
    {
        ShieldLevel.Soft => "Notes distractions and nudges you.",
        ShieldLevel.Firm => "Closes blocked apps.",
        _ => "Closes apps and locks the list until the sprint ends.",
    };

    public static string BestFor(ShieldLevel level) => level switch
    {
        ShieldLevel.Soft => "Best for classes or light work.",
        ShieldLevel.Firm => "Best for homework.",
        _ => "Best for exams and deep work.",
    };
}
