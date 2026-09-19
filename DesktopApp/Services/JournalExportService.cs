using System.IO;
using System.Text;
using FlowShield.Models;

namespace FlowShield.Services;

/// <summary>
/// Writes a journal export to a file the customer chose (F17).
///
/// The formatting lives in <see cref="JournalExport"/>; this is only the part
/// that touches the disk. Nothing is written anywhere except the path handed
/// in — no temp copy, no cache, nothing uploaded — which is what keeps the
/// privacy policy's "your journal never leaves your PC" true.
/// </summary>
public static class JournalExportService
{
    /// <summary>
    /// Writes the export and returns how many sessions it covered.
    ///
    /// CSV goes out as UTF-8 *with* a BOM and CRLF endings: Excel on Windows
    /// assumes the local codepage without one, which turns every accent and
    /// emoji in a journal line into mojibake on a double-click. Markdown is
    /// plain UTF-8, since the BOM shows up as stray characters in editors and
    /// renderers that don't expect it.
    /// </summary>
    public static int Write(
        string path,
        IEnumerable<FocusSession> sessions,
        DateTime fromLocal,
        DateTime toLocal,
        ExportFormat format)
    {
        var rows = JournalExport.InRange(sessions, fromLocal, toLocal);

        var (text, encoding) = format == ExportFormat.Csv
            ? (JournalExport.ToCsv(rows), new UTF8Encoding(encoderShouldEmitUTF8Identifier: true))
            : (JournalExport.ToMarkdown(rows, fromLocal, toLocal),
               new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));

        File.WriteAllText(path, text, encoding);
        Log.Info($"journal exported: {rows.Count} session(s), {format}");
        return rows.Count;
    }
}
