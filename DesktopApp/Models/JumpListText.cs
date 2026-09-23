namespace FlowShield.Models;

/// <summary>
/// The words on the taskbar Jump List (1.0.10, spec 5). Its entries are shell
/// menu text, where a single &amp; marks a keyboard mnemonic and is not
/// drawn: a template named "Maths &amp; Physics" would show as "Maths Physics"
/// with the P underlined. The shell's escape is &amp;&amp;. A JumpTask's
/// Description is a plain tooltip and stays as typed.
/// </summary>
public static class JumpListText
{
    /// <summary>The entry that starts <paramref name="templateName"/>, safe for a menu.</summary>
    public static string Title(string templateName) => $"Start {templateName.Replace("&", "&&")}";
}
