using System.IO;
using System.Xml.Linq;

namespace FlowShield.Models;

/// <summary>One Store app found in a package's manifest, ready for the picker (#348).</summary>
public record PackagedAppInfo(string Name, List<string> Processes, string? ExePath);

/// <summary>
/// Reads a Store package's <c>AppxManifest.xml</c> (and a Game Pass title's
/// <c>MicrosoftGame.config</c>) into the apps the picker can offer (#348).
///
/// Store apps have no Start Menu shortcut and no Uninstall key, so the
/// picker never saw them. Every packaged app still runs as its own process,
/// named by the manifest's <c>Executable</c>, so blocking it by process name
/// works once that name is on the list; this is how the name gets there.
///
/// Pure: the caller reads the files and supplies the lookup for names
/// written as <c>ms-resource:</c>, so tier 1 runs this exact code.
/// </summary>
public static class PackagedApp
{
    /// <summary>
    /// Processes that host other apps rather than being one. Every Game Pass
    /// title starts through its own copy of <c>gamelaunchhelper</c>, so
    /// blocking that name for one game would close the launcher of every game;
    /// <c>WWAHost</c> runs every web-based Store app; <c>ApplicationFrameHost</c>
    /// draws the window frame of every classic Store app. None is ever offered.
    /// </summary>
    public static readonly HashSet<string> SharedHosts = new(StringComparer.OrdinalIgnoreCase)
    {
        "gamelaunchhelper", "wwahost", "applicationframehost",
    };

    /// <summary>
    /// The apps in one package. Empty for frameworks, resource packages, web
    /// apps with no exe of their own, entries hidden from the Start menu, and
    /// anything whose name can't be resolved to readable text.
    /// </summary>
    /// <param name="manifestXml">The package's AppxManifest.xml.</param>
    /// <param name="gameConfigXml">MicrosoftGame.config beside it, when there is one.</param>
    /// <param name="packageRoot">The package's folder, for the exe path (icons).</param>
    /// <param name="packageFullName">The package full name, for resolving <c>ms-resource:</c> names.</param>
    /// <param name="loadIndirect">Resolves an <c>@{…}</c> indirect string (SHLoadIndirectString); null when it can't.</param>
    public static List<PackagedAppInfo> FromManifest(
        string manifestXml, string? gameConfigXml, string packageRoot,
        string packageFullName, Func<string, string?> loadIndirect)
    {
        var found = new List<PackagedAppInfo>();
        XElement package;
        try { package = XDocument.Parse(manifestXml).Root!; }
        catch { return found; }

        var properties = Child(package, "Properties");
        if (IsTrue(Child(properties, "Framework")?.Value) || IsTrue(Child(properties, "ResourcePackage")?.Value))
            return found;

        var identity = Child(package, "Identity")?.Attribute("Name")?.Value ?? "";
        string? Name(string? raw) => Readable(raw, identity, packageFullName, loadIndirect);
        var packageName = Name(Child(properties, "DisplayName")?.Value);

        // A Game Pass title: the manifest starts gamelaunchhelper, and the
        // game's own exes are listed in MicrosoftGame.config.
        if (!string.IsNullOrWhiteSpace(gameConfigXml))
        {
            var game = FromGameConfig(gameConfigXml, packageRoot, packageName, identity, packageFullName, loadIndirect);
            if (game is not null) found.Add(game);
            return found;
        }

        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var app in Descendants(Child(package, "Applications"), "Application"))
        {
            var exe = app.Attribute("Executable")?.Value;
            var process = ProcessName(exe);
            if (process is null || SharedHosts.Contains(process)) continue;

            var visuals = Descendants(app, "VisualElements").FirstOrDefault();
            // AppListEntry="none" is a helper the package keeps out of the
            // Start menu: not something anyone opens, so not something to block.
            if (string.Equals(visuals?.Attribute("AppListEntry")?.Value, "none", StringComparison.OrdinalIgnoreCase))
                continue;

            var name = Name(visuals?.Attribute("DisplayName")?.Value) ?? packageName;
            if (name is null || !seen.Add(process)) continue;

            found.Add(new PackagedAppInfo(name, new() { process }, Path.Combine(packageRoot, exe!)));
        }
        return found;
    }

    private static PackagedAppInfo? FromGameConfig(
        string xml, string packageRoot, string? packageName,
        string identity, string packageFullName, Func<string, string?> loadIndirect)
    {
        XElement game;
        try { game = XDocument.Parse(xml).Root!; }
        catch { return null; }

        var processes = new List<string>();
        string? firstExe = null;
        foreach (var exe in Descendants(Child(game, "ExecutableList"), "Executable"))
        {
            var file = exe.Attribute("Name")?.Value;
            var process = ProcessName(file);
            if (process is null || SharedHosts.Contains(process)) continue;
            if (processes.Contains(process, StringComparer.OrdinalIgnoreCase)) continue;
            processes.Add(process);
            firstExe ??= file;
        }
        if (processes.Count == 0) return null;

        var shown = Descendants(game, "ShellVisuals").FirstOrDefault()?.Attribute("DefaultDisplayName")?.Value;
        var name = Readable(shown, identity, packageFullName, loadIndirect) ?? packageName;
        return name is null ? null : new PackagedAppInfo(name, processes, Path.Combine(packageRoot, firstExe!));
    }

    /// <summary>
    /// "app\WhatsApp.exe" → "WhatsApp". Null for anything that isn't a plain
    /// exe: a missing attribute (web apps), a build token, a path that climbs out.
    /// </summary>
    public static string? ProcessName(string? executable)
    {
        if (string.IsNullOrWhiteSpace(executable)) return null;
        var path = executable.Trim().Replace('/', '\\');
        // Stays inside the package: no drive, no UNC or rooted path, no climbing out.
        if (path.Contains('$') || path.Contains("..") || path.Contains(':') || path.StartsWith('\\')) return null;
        if (!path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) return null;
        var name = Path.GetFileNameWithoutExtension(path.Split('\\').Last());
        return name.Length == 0 ? null : name;
    }

    /// <summary>
    /// The string SHLoadIndirectString needs for a manifest's
    /// <c>ms-resource:</c> name, using the documented forms: a bare key lives
    /// under the package's Resources map, "/x/y" is relative to the package,
    /// and "//x" is already a full URI.
    /// </summary>
    public static string IndirectString(string packageFullName, string identityName, string raw)
    {
        var key = raw["ms-resource:".Length..];
        var uri = key.StartsWith("//") ? "ms-resource:" + key
            : key.StartsWith("/") ? $"ms-resource://{identityName}{key}"
            : $"ms-resource://{identityName}/Resources/{key}";
        return $"@{{{packageFullName}?{uri}}}";
    }

    private static string? Readable(string? raw, string identity, string fullName, Func<string, string?> loadIndirect)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        var text = raw.Trim();
        if (text.StartsWith("ms-resource:", StringComparison.OrdinalIgnoreCase))
        {
            try { text = loadIndirect(IndirectString(fullName, identity, text))?.Trim() ?? ""; }
            catch { text = ""; }
        }
        // An unresolved key is not a name a customer would recognise.
        if (text.Length == 0 || text.StartsWith("ms-resource:", StringComparison.OrdinalIgnoreCase)) return null;
        return text;
    }

    private static bool IsTrue(string? value) =>
        string.Equals(value?.Trim(), "true", StringComparison.OrdinalIgnoreCase);

    // Manifests mix several namespaces (uap, uap10, desktop…) for the same
    // element names, so matching goes by local name only.
    private static XElement? Child(XElement? parent, string name) =>
        parent?.Elements().FirstOrDefault(e => e.Name.LocalName == name);

    private static IEnumerable<XElement> Descendants(XElement? parent, string name) =>
        parent?.Descendants().Where(e => e.Name.LocalName == name) ?? Enumerable.Empty<XElement>();
}
