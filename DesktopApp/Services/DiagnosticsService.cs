using System.Collections;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using FlowShield.Models;

namespace FlowShield.Services;

/// <summary>What a diagnostics bundle says about the machine and the build.</summary>
public sealed record DiagnosticsEnvironment(string AppVersion, string WindowsVersion, string DotNetRuntime)
{
    /// <summary>This PC, as .NET reports it.</summary>
    public static DiagnosticsEnvironment Current(string appVersion)
    {
        var v = Environment.OSVersion.Version;
        var bits = Environment.Is64BitOperatingSystem ? "64-bit" : "32-bit";
        return new DiagnosticsEnvironment(
            appVersion,
            $"Windows {v.Major}.{v.Minor}, build {v.Build} ({bits})",
            RuntimeInformation.FrameworkDescription);
    }
}

/// <summary>
/// Builds the plain-text diagnostics bundle behind Settings → About → Get help
/// (Roadmap 4.3, #400). The bundle is shown to the customer first and is never
/// sent anywhere by Basalt; they decide whether to attach it to an email.
///
/// Safe by construction, not by cleanup:
///  - settings are listed from an allow-list. A text setting that is not named
///    in <see cref="AllowedTextSettings"/> is shown as [redacted], so a field
///    added later can't leak by accident;
///  - journal entries, sprint intentions and sprint history are never read;
///  - a final pass scrubs the license key, email addresses, the device
///    identifier and token-shaped strings from everything, log lines included.
///
/// Depends only on <see cref="AppSettings"/> so the tier 1 probe can run it.
/// </summary>
public static class DiagnosticsService
{
    public const string Redacted = "[redacted]";

    /// <summary>How many lines of the newest log go into the bundle.</summary>
    public const int LogLineLimit = 200;

    /// <summary>The settings that hold history or journal text. Never listed, not even as a count.</summary>
    private static readonly HashSet<string> NeverListed = new()
    {
        nameof(AppSettings.Sessions),
        nameof(AppSettings.ActiveSprint),
        nameof(AppSettings.ActiveBreak),
    };

    /// <summary>
    /// The only text settings shown as they are: versions, the license status
    /// word and the two public addresses. Every other text setting is redacted.
    /// </summary>
    public static readonly IReadOnlyCollection<string> AllowedTextSettings = new[]
    {
        nameof(AppSettings.LicenseStatus),
        nameof(AppSettings.LicenseServerUrl),
        nameof(AppSettings.WebsiteUrl),
        nameof(AppSettings.LastRunVersion),
        nameof(AppSettings.PendingReleaseVersion),
        nameof(AppSettings.LastNotifiedUpdateVersion),
        nameof(AppSettings.TermsAcceptedVersion),
    };

    private static readonly Regex Email = new(
        @"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}", RegexOptions.Compiled);

    private static readonly Regex LicenseKeyShape = new(
        @"\bFS-[0-9A-Za-z]{4}-[0-9A-Za-z]{4}-[0-9A-Za-z]{4}-[0-9A-Za-z]{4}\b",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);

    // Device identifiers and device tokens are long hex strings.
    private static readonly Regex LongHex = new(@"\b[0-9a-fA-F]{32,}\b", RegexOptions.Compiled);

    // "token=abc", "key: abc", "Authorization: Bearer abc": keep the name, drop the value.
    private static readonly Regex NamedSecret = new(
        @"(?i)\b(token|secret|password|passwd|api[_-]?key|license[_-]?key|authorization)(\s*[:=]\s*)(bearer\s+)?\S+",
        RegexOptions.Compiled);

    // C:\Users\<name>\ names the person; the rest of the path stays useful.
    // A name may hold spaces or an apostrophe, so when a backslash follows,
    // the whole folder name goes.
    private static readonly Regex UserFolder = new(
        @"(?i)([A-Z]:\\Users\\)(?:[^\\/\r\n""]+(?=\\)|[^\\/\s""']+)", RegexOptions.Compiled);

    /// <summary>
    /// The whole bundle. <paramref name="knownSecrets"/> are values to remove
    /// wherever they appear (the license key, the email, the device id), on top
    /// of the pattern-based scrubbing.
    /// </summary>
    public static string Build(
        AppSettings settings,
        DiagnosticsEnvironment environment,
        IEnumerable<string> logLines,
        params string?[] knownSecrets)
    {
        var secrets = new List<string?>(knownSecrets) { settings.LicenseKey, settings.LicenseEmail };
        var sb = new StringBuilder();

        sb.AppendLine("Basalt diagnostics");
        sb.AppendLine($"Created: {DateTime.Now.ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture)} (local time)");
        sb.AppendLine("Nothing here was sent anywhere. License key, email addresses and device IDs are removed.");
        sb.AppendLine("Journal entries, sprint intentions and sprint history are not included.");
        sb.AppendLine();

        sb.AppendLine("== This PC ==");
        sb.AppendLine($"Basalt version: {environment.AppVersion}");
        sb.AppendLine($"Windows: {environment.WindowsVersion}");
        sb.AppendLine($".NET runtime: {environment.DotNetRuntime}");
        sb.AppendLine();

        sb.AppendLine("== Settings ==");
        foreach (var line in SettingsLines(settings)) sb.AppendLine(line);
        sb.AppendLine();

        var log = logLines.TakeLast(LogLineLimit).ToList();
        sb.AppendLine($"== Recent log (last {LogLineLimit} lines) ==");
        if (log.Count == 0) sb.AppendLine("(no log yet)");
        foreach (var line in log) sb.AppendLine(line);

        return Scrub(sb.ToString(), secrets);
    }

    /// <summary>The last <paramref name="maxLines"/> lines of the newest flowshield-*.log in a folder.</summary>
    public static IReadOnlyList<string> ReadRecentLog(string? logDirectory, int maxLines = LogLineLimit)
    {
        try
        {
            if (string.IsNullOrEmpty(logDirectory) || !Directory.Exists(logDirectory)) return Array.Empty<string>();

            // The date is in the file name, so the newest name is the newest day.
            var newest = Directory.GetFiles(logDirectory, "flowshield-*.log")
                .OrderByDescending(f => System.IO.Path.GetFileName(f), StringComparer.Ordinal)
                .FirstOrDefault();
            if (newest is null) return Array.Empty<string>();

            // The app may be writing to it right now.
            using var stream = new FileStream(newest, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            using var reader = new StreamReader(stream, Encoding.UTF8);
            var tail = new Queue<string>(maxLines + 1);
            while (reader.ReadLine() is { } line)
            {
                tail.Enqueue(line);
                if (tail.Count > maxLines) tail.Dequeue();
            }
            return tail.ToList();
        }
        catch
        {
            // A log that can't be read leaves a bundle without one, not a crash.
            return Array.Empty<string>();
        }
    }

    /// <summary>Removes known secrets and anything shaped like one from <paramref name="text"/>.</summary>
    public static string Scrub(string text, IEnumerable<string?> knownSecrets)
    {
        foreach (var secret in knownSecrets)
        {
            if (string.IsNullOrWhiteSpace(secret) || secret.Length < 3) continue;
            text = text.Replace(secret, Redacted, StringComparison.OrdinalIgnoreCase);
        }

        text = Email.Replace(text, Redacted);
        text = LicenseKeyShape.Replace(text, Redacted);
        text = LongHex.Replace(text, Redacted);
        text = NamedSecret.Replace(text, m => $"{m.Groups[1].Value}{m.Groups[2].Value}{Redacted}");
        text = UserFolder.Replace(text, m => m.Groups[1].Value + Redacted);
        return text;
    }

    private static IEnumerable<string> SettingsLines(AppSettings settings)
    {
        var properties = typeof(AppSettings)
            .GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Where(p => p.CanRead && p.GetIndexParameters().Length == 0
                        && p.GetCustomAttribute<JsonIgnoreAttribute>() is null
                        && !NeverListed.Contains(p.Name))
            .OrderBy(p => p.Name, StringComparer.Ordinal);

        foreach (var p in properties)
        {
            object? value;
            try { value = p.GetValue(settings); }
            catch { continue; }

            yield return $"{p.Name}: {Describe(p, value)}";
        }
    }

    private static string Describe(PropertyInfo p, object? value)
    {
        if (value is null) return "(not set)";

        if (value is string text)
        {
            if (text.Length == 0) return "(empty)";
            return AllowedTextSettings.Contains(p.Name) ? text : Redacted;
        }

        // Lists and dictionaries hold blocklists, templates and schedules:
        // how many is enough for support, the contents stay on this PC.
        if (value is ICollection collection) return $"{collection.Count} item{(collection.Count == 1 ? "" : "s")}";

        if (value is IFormattable formattable)
            return formattable.ToString(null, CultureInfo.InvariantCulture);

        var type = Nullable.GetUnderlyingType(p.PropertyType) ?? p.PropertyType;
        if (type.IsPrimitive || type.IsEnum) return Convert.ToString(value, CultureInfo.InvariantCulture) ?? "";

        // Any other object is state we didn't plan for; say that it exists, not what it holds.
        return "present";
    }
}
