namespace FlowShield.Models;

/// <summary>
/// The taskbar Jump List's argument (1.0.10, spec 5): --start-sprint for the
/// tray's quick start, or --start-sprint=&lt;templateId&gt; for one template.
/// Written for each entry and read back here, so the two can't drift apart.
/// </summary>
public static class StartSprintArg
{
    public const string Flag = "--start-sprint";

    /// <summary>
    /// Whether <paramref name="args"/> asks for a sprint, and for which
    /// template: null for the plain flag or an empty id. Matched
    /// case-insensitively, like FlowShield's other switches.
    /// </summary>
    public static bool TryFind(IEnumerable<string> args, out string? templateId)
    {
        templateId = null;
        foreach (var arg in args)
        {
            if (arg.Equals(Flag, StringComparison.OrdinalIgnoreCase)) return true;
            if (arg.StartsWith(Flag + "=", StringComparison.OrdinalIgnoreCase))
            {
                var id = arg[(Flag.Length + 1)..].Trim();
                templateId = id.Length == 0 ? null : id;
                return true;
            }
        }
        return false;
    }

    /// <summary>
    /// The argument a template's entry runs with, or null when its id could
    /// not survive a command line: a space or a quote would split it into
    /// extra arguments. Every id FlowShield makes (<see cref="StudyTemplate.NewId"/>)
    /// is letters and digits only.
    /// </summary>
    public static string? For(string? templateId) =>
        !string.IsNullOrEmpty(templateId) && templateId.All(char.IsAsciiLetterOrDigit)
            ? $"{Flag}={templateId}"
            : null;
}
