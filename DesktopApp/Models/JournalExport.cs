using System.Globalization;
using System.Text;

namespace FlowShield.Models;

/// <summary>The file formats a journal export can be saved as (F17, roadmap 3.5).</summary>
public enum ExportFormat
{
    Csv = 0,
    Markdown = 1,
}

/// <summary>
/// Turns sessions and their journal lines into a file the customer keeps (F17).
///
/// Until now the journal could be written and never read: every sprint captured
/// an intention and a "what moved?" line that nothing could show again.
///
/// Deliberately free of any UI, clock or file system: History (F16) will render
/// the same rows, and "Export everything" (F23) will reuse these formatters for
/// its sessions section rather than growing a second copy. Everything here is a
/// pure function of the sessions it is handed.
/// </summary>
public static class JournalExport
{
    /// <summary>
    /// Sessions that started within the inclusive local-date range, oldest
    /// first. The range is compared in local time because the customer picked
    /// the dates off a local calendar; a sprint at 11pm belongs to the day they
    /// remember, not to tomorrow in UTC.
    /// </summary>
    public static List<FocusSession> InRange(
        IEnumerable<FocusSession> sessions, DateTime fromLocal, DateTime toLocal)
    {
        var from = fromLocal.Date;
        var to = toLocal.Date;
        if (to < from) (from, to) = (to, from);

        return sessions
            .Where(s =>
            {
                var day = s.StartedUtc.ToLocalTime().Date;
                return day >= from && day <= to;
            })
            .OrderBy(s => s.StartedUtc)
            .ToList();
    }

    // ------------------------------------------------------------------ CSV

    public static readonly string[] CsvHeader =
    {
        "date (local)", "start (local)", "planned minutes", "actual minutes",
        "shield", "completed", "ended early", "interrupted",
        "distractions blocked", "intention", "journal",
    };

    /// <summary>
    /// A row per session. Excel is the likely destination, so this is written
    /// with CRLF endings, and the caller writes it as UTF-8 *with* a BOM —
    /// without one, Excel on Windows mangles accents and emoji on a
    /// double-click.
    /// </summary>
    public static string ToCsv(IEnumerable<FocusSession> sessions)
    {
        var builder = new StringBuilder();
        builder.Append(string.Join(",", CsvHeader.Select(EscapeCsv))).Append("\r\n");

        foreach (var s in sessions)
        {
            var started = s.StartedUtc.ToLocalTime();
            var cells = new[]
            {
                started.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                started.ToString("HH:mm", CultureInfo.InvariantCulture),
                s.PlannedMinutes.ToString(CultureInfo.InvariantCulture),
                s.ActualMinutes.ToString("0.#", CultureInfo.InvariantCulture),
                ShieldName(s.Shield),
                Yes(s.Completed),
                Yes(s.EndedEarly),
                Yes(s.Interrupted),
                s.BlocksEnforced.ToString(CultureInfo.InvariantCulture),
                s.Intention ?? "",
                s.Journal ?? "",
            };
            builder.Append(string.Join(",", cells.Select(EscapeCsv))).Append("\r\n");
        }

        return builder.ToString();
    }

    /// <summary>
    /// Quotes a cell for CSV, after defusing anything a spreadsheet would treat
    /// as a formula.
    /// </summary>
    public static string EscapeCsv(string? value)
    {
        var text = Defuse(value ?? "");
        if (text.IndexOfAny(new[] { ',', '"', '\r', '\n' }) < 0) return text;
        return "\"" + text.Replace("\"", "\"\"") + "\"";
    }

    /// <summary>
    /// Stops a cell being executed as a formula when the file is opened.
    ///
    /// Intentions and journal lines are free text the customer typed. A cell
    /// starting with =, +, -, @, tab or carriage return is run as a formula by
    /// Excel and by Google Sheets, which is how an exported note becomes code
    /// execution on whoever opens it. A leading apostrophe makes it text again,
    /// and spreadsheets hide the apostrophe.
    /// </summary>
    public static string Defuse(string value)
    {
        if (value.Length == 0) return value;
        var first = value[0];
        return first is '=' or '+' or '-' or '@' or '\t' or '\r'
            ? "'" + value
            : value;
    }

    // ------------------------------------------------------------- Markdown

    /// <summary>
    /// Grouped by day, newest first, so the most recent work is at the top
    /// where someone reading their own notes expects it.
    /// </summary>
    public static string ToMarkdown(
        IEnumerable<FocusSession> sessions, DateTime fromLocal, DateTime toLocal)
    {
        var from = fromLocal.Date;
        var to = toLocal.Date;
        if (to < from) (from, to) = (to, from);

        var builder = new StringBuilder();
        builder.Append("# FlowShield journal\r\n\r\n");
        builder.Append(
            $"{from:yyyy-MM-dd} to {to:yyyy-MM-dd}. Times are local.\r\n\r\n");

        var days = sessions
            .GroupBy(s => s.StartedUtc.ToLocalTime().Date)
            .OrderByDescending(g => g.Key);

        var any = false;
        foreach (var day in days)
        {
            any = true;
            builder.Append($"## {day.Key:yyyy-MM-dd}\r\n\r\n");

            foreach (var s in day.OrderBy(x => x.StartedUtc))
            {
                var started = s.StartedUtc.ToLocalTime();
                builder.Append(
                    $"- {started:HH:mm} · {s.ActualMinutes:0.#} min · "
                    + $"{ShieldName(s.Shield)} · {Outcome(s)}\r\n");

                if (!string.IsNullOrWhiteSpace(s.Intention))
                    builder.Append($"  - Intention: {EscapeMarkdown(s.Intention)}\r\n");

                if (!string.IsNullOrWhiteSpace(s.Journal))
                    builder.Append($"  - {EscapeMarkdown(s.Journal)}\r\n");

                builder.Append("\r\n");
            }
        }

        if (!any) builder.Append("No sprints in this range.\r\n");

        return builder.ToString();
    }

    /// <summary>
    /// Keeps a journal line from becoming structure. Someone writing "# done"
    /// or "- fixed the thing" should see that text, not a heading or a nested
    /// bullet that silently reshapes their export.
    /// </summary>
    public static string EscapeMarkdown(string value)
    {
        var text = (value ?? "").Replace("\r", " ").Replace("\n", " ").Trim();
        if (text.Length == 0) return text;

        var first = text[0];
        if (first is '#' or '-' or '*' or '>' or '+' or '|' or '`')
            text = "\\" + text;

        return text;
    }

    // ----------------------------------------------------------- file names

    /// <summary>
    /// "FlowShield journal 2026-09-01 to 2026-09-18.csv" — says what it is and
    /// what it covers, so a folder of them stays readable.
    /// </summary>
    public static string SuggestedFileName(
        DateTime fromLocal, DateTime toLocal, ExportFormat format)
    {
        var from = fromLocal.Date;
        var to = toLocal.Date;
        if (to < from) (from, to) = (to, from);

        var extension = format == ExportFormat.Csv ? "csv" : "md";
        return $"FlowShield journal {from:yyyy-MM-dd} to {to:yyyy-MM-dd}.{extension}";
    }

    // ------------------------------------------------------------- helpers

    public static string ShieldName(ShieldLevel shield) => shield switch
    {
        ShieldLevel.Soft => "Soft",
        ShieldLevel.Sealed => "Sealed",
        _ => "Firm",
    };

    /// <summary>
    /// "completed = false" hides the difference between giving up and losing
    /// the sprint to a crash, so the outcome is named rather than inferred.
    /// </summary>
    public static string Outcome(FocusSession session) =>
        session.Completed ? "completed"
        : session.Interrupted ? "interrupted"
        : session.EndedEarly ? "ended early"
        : "unfinished";

    private static string Yes(bool value) => value ? "yes" : "no";
}
