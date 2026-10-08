namespace FlowShield.Models;

/// <summary>
/// What the shield stopped during one sprint, app by app, for the summary
/// card's "What Basalt stopped this sprint" list (#349, competitor gap 7).
///
/// Held in memory only and cleared when the next sprint starts. Nothing here
/// is saved with the session or sent anywhere: the names are the blocklist's
/// own, and the card is the only place they are shown. A sprint resumed after
/// a restart starts again from an empty list, like TurnedBack.
/// </summary>
public sealed class StoppedApps
{
    /// <summary>Lines shown before the rest fold into "and N more".</summary>
    public const int MaxLines = 5;

    private sealed class Entry
    {
        public string Name = "";
        public int Closed;
        public int Nudged;
        public int Total => Closed + Nudged;
    }

    // In order of first sighting, so ties keep the order they happened in.
    private readonly List<Entry> _entries = new();

    /// <summary>
    /// Counts one distraction against <paramref name="name"/>: closed when the
    /// shield closed it (or began to), a nudge when it only noticed it.
    /// The same app is one line whatever the capitalisation.
    /// </summary>
    public void Record(string? name, bool closed)
    {
        var trimmed = name?.Trim() ?? "";
        if (trimmed.Length == 0) return;

        var entry = _entries.FirstOrDefault(e =>
            string.Equals(e.Name, trimmed, StringComparison.OrdinalIgnoreCase));
        if (entry is null)
        {
            entry = new Entry { Name = trimmed };
            _entries.Add(entry);
        }

        if (closed) entry.Closed++;
        else entry.Nudged++;
    }

    public void Clear() => _entries.Clear();

    /// <summary>True when there is something to list.</summary>
    public bool Any => _entries.Count > 0;

    /// <summary>
    /// "What Basalt stopped this sprint" when anything was closed, and
    /// "caught" when the sprint only nudged, so a Soft sprint never claims a
    /// close that didn't happen. Empty when there is nothing to list.
    /// </summary>
    public string Title =>
        !Any ? ""
        : _entries.Any(e => e.Closed > 0) ? "What Basalt stopped this sprint"
        : "What Basalt caught this sprint";

    /// <summary>One app per line, most-stopped first, then "and N more apps".</summary>
    public string Text
    {
        get
        {
            var ordered = _entries
                .Select((e, i) => (e, i))
                .OrderByDescending(x => x.e.Total)
                .ThenBy(x => x.i)
                .Select(x => x.e)
                .ToList();

            var lines = ordered.Take(MaxLines).Select(Line).ToList();
            var rest = ordered.Count - MaxLines;
            if (rest > 0) lines.Add(rest == 1 ? "and 1 more app" : $"and {rest} more apps");
            return string.Join("\n", lines);
        }
    }

    private static string Line(Entry e)
    {
        var parts = new List<string>();
        if (e.Closed > 0) parts.Add(e.Closed == 1 ? "closed once" : $"closed {e.Closed} times");
        if (e.Nudged > 0) parts.Add(e.Nudged == 1 ? "1 nudge" : $"{e.Nudged} nudges");
        return $"{e.Name} · {string.Join(", ", parts)}";
    }
}
