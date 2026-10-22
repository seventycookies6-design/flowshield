namespace FlowShield.Models;

/// <summary>
/// Where Basalt sends someone who needs help (Roadmap 4.3, #400). One place,
/// so the error dialog and Settings → About → Get help can't drift apart.
/// </summary>
public static class HelpLinks
{
    /// <summary>The support page on the site: the FAQ and how to reach us.</summary>
    public const string SupportUrl =
        "https://seventycookies6-design.github.io/flowshield/support.html";

    /// <summary>
    /// The address customers can write to. Null until the owner (Keenan)
    /// chooses a real one (#400): nothing is shown or shipped in its place,
    /// and never a placeholder. Set it here and the Get help card shows it
    /// with a Copy button; no other change is needed.
    /// </summary>
    public const string? SupportEmail = null;

    /// <summary>True only once <see cref="SupportEmail"/> holds a real address.</summary>
    public static bool HasSupportEmail => !string.IsNullOrWhiteSpace(SupportEmail);
}
