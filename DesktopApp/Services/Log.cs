using System.IO;
using System.Text;

namespace FlowShield.Services;

/// <summary>
/// Tiny append-only file logger. The automation suite reads this to explain
/// failures that leave no trace in the UI.
/// </summary>
public static class Log
{
    private static readonly object Gate = new();
    private static string? _path;

    public static string Path => _path ??= Init();

    private static string Init()
    {
        var dir = System.IO.Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "FlowShield", "logs");
        Directory.CreateDirectory(dir);
        return System.IO.Path.Combine(dir, $"flowshield-{DateTime.Now:yyyy-MM-dd}.log");
    }

    public static void Info(string message) => Write("INFO", message);
    public static void Warn(string message) => Write("WARN", message);
    public static void Error(string message) => Write("ERROR", message);

    public static void Error(string message, Exception ex) =>
        Write("ERROR", $"{message} :: {ex.GetType().Name}: {ex.Message}");

    private static void Write(string level, string message)
    {
        var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} [{level,-5}] {message}{Environment.NewLine}";
        try
        {
            lock (Gate) File.AppendAllText(Path, line, Encoding.UTF8);
        }
        catch
        {
            // Logging must never take the app down.
        }
        System.Diagnostics.Debug.Write(line);
    }
}
