namespace FlowShield.Models;

/// <summary>
/// The agreement a customer has to accept before FlowShield can close anything
/// (legal checklist 2.3, 9.4).
///
/// A liability limit only holds if the person agreed to it. A link in a footer
/// that nobody had to open is the weakest form of that, and the one courts
/// refuse most often — so the terms are put in front of the user once, with a
/// plain statement of the one thing that can cost them: FlowShield closes
/// programs, and unsaved work in them can be lost.
/// </summary>
public static class LegalTerms
{
    /// <summary>
    /// Bump this whenever the terms change materially. A different version
    /// means the gate appears again, so the recorded acceptance always refers
    /// to wording the customer actually saw.
    /// </summary>
    public const string Version = "1.0 (17 September 2026)";

    public const string Headline = "Before you start";

    /// <summary>The part that matters most, in the words the terms use.</summary>
    public const string DataLossWarning =
        "FlowShield closes programs you put on your block list. Any unsaved work in "
        + "them can be lost. It never closes Windows system processes, shells or "
        + "common developer tools.";

    public const string AgreementLine =
        "By continuing you agree to the Terms of Service and the Privacy Policy, "
        + "and you accept that FlowShield is provided as is.";

    public static bool Accepted(AppSettings settings) =>
        string.Equals(settings.TermsAcceptedVersion, Version, StringComparison.Ordinal);

    /// <summary>Records the acceptance against the version that was on screen.</summary>
    public static void Accept(AppSettings settings, DateTime? nowUtc = null)
    {
        settings.TermsAcceptedVersion = Version;
        settings.TermsAcceptedUtc = nowUtc ?? DateTime.UtcNow;
    }

    public static string TermsUrl(AppSettings settings) => Page(settings, "#terms");
    public static string PrivacyUrl(AppSettings settings) => Page(settings, "#privacy");

    private static string Page(AppSettings settings, string anchor) =>
        $"{(settings.WebsiteUrl ?? "").TrimEnd('/')}/legal.html{anchor}";
}
