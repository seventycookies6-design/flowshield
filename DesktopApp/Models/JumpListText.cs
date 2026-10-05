namespace FlowShield.Models;

/// <summary>
/// The words on the taskbar Jump List (1.0.10, spec 5). A JumpTask's Title is
/// drawn exactly as written, not as menu text: an &amp; is shown as typed, so a
/// template named "Maths &amp; Physics" reads "Start Maths &amp; Physics". The
/// shell's &amp;&amp; escape belongs to classic menus; applying it here showed
/// "Maths &amp;&amp; Physics" on Windows 11 (VM, 1.0.11).
/// </summary>
public static class JumpListText
{
    /// <summary>The entry that starts <paramref name="templateName"/>, as the Jump List draws it.</summary>
    public static string Title(string templateName) => $"Start {templateName}";
}
