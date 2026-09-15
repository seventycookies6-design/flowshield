using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Windows.Media;

namespace FlowShield.Models;

/// <summary>Where a picker entry came from, in the order results are ranked.</summary>
public enum PickerSource { Suggested, Installed, Running }

/// <summary>One app offered by the Blocked Apps picker (launch checklist F8).</summary>
public class PickerEntry : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;
    private void Raise([CallerMemberName] string? name = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

    public string Name { get; init; } = "";
    public List<string> Processes { get; init; } = new();
    public PickerSource Source { get; init; }

    /// <summary>"Chat", "Games & launchers"… for suggestions.</summary>
    public string Group { get; init; } = "";

    /// <summary>A warning shown with the entry, e.g. that a browser closes entirely.</summary>
    public string Note { get; init; } = "";

    public bool HasNote => Note.Length > 0;

    /// <summary>An exe on disk to take the icon from, when one is known.</summary>
    public string? ExePath { get; set; }

    private ImageSource? _icon;
    public ImageSource? Icon
    {
        get => _icon;
        set { _icon = value; Raise(); Raise(nameof(HasIcon)); }
    }

    public bool HasIcon => _icon is not null;

    public string Initial => Name.Length > 0 ? char.ToUpperInvariant(Name[0]).ToString() : "?";

    private bool _isAdded;
    /// <summary>Already on the blocklist.</summary>
    public bool IsAdded
    {
        get => _isAdded;
        set
        {
            if (_isAdded == value) return;
            _isAdded = value;
            Raise();
            Raise(nameof(ActionLabel));
            Raise(nameof(ActionName));
        }
    }

    public string ActionLabel => IsAdded ? "Added" : "Block";

    /// <summary>What a screen reader announces for the button.</summary>
    public string ActionName => IsAdded ? $"{Name} is blocked" : $"Block {Name}";

    public string SourceLabel => Source switch
    {
        PickerSource.Suggested => Group,
        PickerSource.Installed => "Installed",
        _ => "Running now",
    };

    /// <summary>Stable id for UI Automation: PickApp_steam.</summary>
    public string AutomationId =>
        "PickApp_" + new string(Processes.FirstOrDefault("app").Select(c => char.IsLetterOrDigit(c) ? c : '_').ToArray());
}

/// <summary>The built-in suggestions and the rules for searching and merging entries.</summary>
public static class AppPicker
{
    public const string ProtectedMessage =
        "FlowShield never closes Windows system processes, so your PC stays usable.";

    private sealed class SuggestionFile
    {
        [JsonPropertyName("groups")] public List<SuggestionGroup> Groups { get; set; } = new();
    }

    private sealed class SuggestionGroup
    {
        [JsonPropertyName("name")] public string Name { get; set; } = "";
        [JsonPropertyName("note")] public string? Note { get; set; }
        [JsonPropertyName("apps")] public List<SuggestionApp> Apps { get; set; } = new();
    }

    private sealed class SuggestionApp
    {
        [JsonPropertyName("name")] public string Name { get; set; } = "";
        [JsonPropertyName("processes")] public List<string> Processes { get; set; } = new();
        [JsonPropertyName("note")] public string? Note { get; set; }
    }

    private static List<PickerEntry>? _suggestions;

    /// <summary>A fresh copy of the suggestions, minus anything protected.</summary>
    public static List<PickerEntry> Suggestions(Func<string, bool> isProtected)
    {
        _suggestions ??= LoadSuggestions();
        return _suggestions
            .Select(s => new PickerEntry
            {
                Name = s.Name,
                Group = s.Group,
                Note = s.Note,
                Source = PickerSource.Suggested,
                Processes = s.Processes.Where(p => !isProtected(p)).ToList(),
            })
            .Where(s => s.Processes.Count > 0)
            .ToList();
    }

    private static List<PickerEntry> LoadSuggestions()
    {
        try
        {
            using var stream = typeof(AppPicker).Assembly.GetManifestResourceStream("FlowShield.app_suggestions.json");
            if (stream is null) return new();
            var file = JsonSerializer.Deserialize<SuggestionFile>(stream) ?? new();
            return file.Groups
                .SelectMany(g => g.Apps.Select(a => new PickerEntry
                {
                    Name = a.Name,
                    Group = g.Name,
                    Note = a.Note ?? g.Note ?? "",
                    Source = PickerSource.Suggested,
                    Processes = a.Processes,
                }))
                .ToList();
        }
        catch (Exception ex)
        {
            Services.Log.Error("could not load app suggestions", ex);
            return new();
        }
    }

    /// <summary>The suggestion that includes <paramref name="processName"/>, if any.</summary>
    public static PickerEntry? SuggestionFor(string processName, Func<string, bool> isProtected) =>
        Suggestions(isProtected).FirstOrDefault(s =>
            s.Processes.Contains(processName, StringComparer.OrdinalIgnoreCase));

    /// <summary>
    /// Combines suggestions with what's installed and running. An installed or
    /// running app that a suggestion already covers only lends it an exe for the
    /// icon, so Steam appears once, under its friendly name.
    /// </summary>
    public static List<PickerEntry> Merge(
        IEnumerable<PickerEntry> suggestions, IEnumerable<PickerEntry> discovered, Func<string, bool> isProtected)
    {
        var result = suggestions.ToList();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var s in result) foreach (var p in s.Processes) seen.Add(p);

        foreach (var d in discovered.OrderBy(d => d.Source))
        {
            var process = d.Processes.FirstOrDefault();
            if (string.IsNullOrWhiteSpace(process) || isProtected(process)) continue;

            var covering = result.FirstOrDefault(r =>
                r.Source == PickerSource.Suggested && r.Processes.Contains(process, StringComparer.OrdinalIgnoreCase));
            if (covering is not null)
            {
                covering.ExePath ??= d.ExePath;
                continue;
            }
            if (!seen.Add(process)) continue;
            result.Add(d);
        }
        return result;
    }

    /// <summary>
    /// Entries matching <paramref name="query"/> by name or process, best first:
    /// names that start with the query, then suggestions, installed, running.
    /// </summary>
    public static List<PickerEntry> Filter(IEnumerable<PickerEntry> entries, string? query)
    {
        var q = (query ?? "").Trim();
        if (q.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) q = q[..^4];

        var matches = q.Length == 0
            ? entries
            :entries.Where(e =>
                e.Name.Contains(q, StringComparison.OrdinalIgnoreCase)
                || e.Processes.Any(p => p.Contains(q, StringComparison.OrdinalIgnoreCase)));

        return matches
            .OrderBy(e => q.Length > 0 && e.Name.StartsWith(q, StringComparison.OrdinalIgnoreCase) ? 0 : 1)
            .ThenBy(e => e.Source)
            .ThenBy(e => e.Source == PickerSource.Suggested ? "" : e.Name, StringComparer.OrdinalIgnoreCase)
            .ToList();
    }
}
