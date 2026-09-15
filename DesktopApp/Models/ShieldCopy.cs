namespace FlowShield.Models;

/// <summary>
/// Customer-facing promises for each commitment mode (launch checklist F1).
/// Keep these short: they appear on Today and in the first-run welcome.
/// </summary>
public static class ShieldCopy
{
    public const string SoftPromise = "Notes distractions and nudges you.";
    public const string FirmPromise = "Closes blocked apps.";
    public const string SealedPromise = "Closes apps and locks the list until the sprint ends.";

    public const string SoftBestFor = "Best for classes or light work.";
    public const string FirmBestFor = "Best for homework.";
    public const string SealedBestFor = "Best for exams and deep work.";

    public static string Promise(ShieldLevel shield) => shield switch
    {
        ShieldLevel.Soft => SoftPromise,
        ShieldLevel.Firm => FirmPromise,
        _ => SealedPromise,
    };

    public static string BestFor(ShieldLevel shield) => shield switch
    {
        ShieldLevel.Soft => SoftBestFor,
        ShieldLevel.Firm => FirmBestFor,
        _ => SealedBestFor,
    };
}
