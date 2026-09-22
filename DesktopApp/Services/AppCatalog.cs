using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using FlowShield.Models;
using Microsoft.Win32;

namespace FlowShield.Services;

/// <summary>
/// Finds the apps on this PC for the picker (F8): Start Menu shortcuts, the
/// installed-programs registry keys, and windows open right now. Everything is
/// read-only and needs no admin rights; anything unreadable is skipped.
/// </summary>
public static class AppCatalog
{
    private static readonly string WindowsDir =
        Environment.GetFolderPath(Environment.SpecialFolder.Windows);

    /// <summary>Installed and running apps. Slow (disk, registry, COM): call off the UI thread.</summary>
    public static List<PickerEntry> Discover()
    {
        var found = new List<PickerEntry>();
        Safely("running apps", () => found.AddRange(Running()));
        Safely("Start Menu shortcuts", () => found.AddRange(StartMenu()));
        Safely("installed programs", () => found.AddRange(Registered()));
        return found;
    }

    /// <summary>Processes with a visible window, so background services don't flood the list.</summary>
    private static IEnumerable<PickerEntry> Running()
    {
        foreach (var process in Process.GetProcesses())
        {
            PickerEntry? entry = null;
            try
            {
                if (process.MainWindowHandle == IntPtr.Zero) continue;
                string? path = null;
                try { path = process.MainModule?.FileName; } catch { /* elevated or 32/64-bit mismatch */ }
                if (path is not null && IsUnderWindows(path)) continue;

                var title = path is null ? null : FileVersionInfo.GetVersionInfo(path).FileDescription;
                entry = new PickerEntry
                {
                    Name = string.IsNullOrWhiteSpace(title) ? process.ProcessName : title.Trim(),
                    Processes = new() { process.ProcessName },
                    Source = PickerSource.Running,
                    ExePath = path,
                };
            }
            catch { /* exited while we looked */ }
            finally { process.Dispose(); }

            if (entry is not null) yield return entry;
        }
    }

    private static IEnumerable<PickerEntry> StartMenu()
    {
        var roots = new[]
        {
            Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
            Environment.GetFolderPath(Environment.SpecialFolder.CommonStartMenu),
        };
        var shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType is null) yield break;
        dynamic shell = Activator.CreateInstance(shellType)!;

        foreach (var root in roots.Where(Directory.Exists))
        {
            IEnumerable<string> links;
            try { links = Directory.EnumerateFiles(root, "*.lnk", SearchOption.AllDirectories).ToList(); }
            catch { continue; }

            foreach (var link in links)
            {
                string? target = null;
                try { target = (string)shell.CreateShortcut(link).TargetPath; } catch { /* broken shortcut */ }
                var entry = FromExe(Path.GetFileNameWithoutExtension(link), target, PickerSource.Installed);
                if (entry is not null) yield return entry;
            }
        }
    }

    private static IEnumerable<PickerEntry> Registered()
    {
        const string uninstall = @"Software\Microsoft\Windows\CurrentVersion\Uninstall";
        var hives = new (RegistryKey Hive, string Path)[]
        {
            (Registry.CurrentUser, uninstall),
            (Registry.LocalMachine, uninstall),
            (Registry.LocalMachine, @"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        };

        foreach (var (hive, path) in hives)
        {
            using var root = hive.OpenSubKey(path);
            if (root is null) continue;
            foreach (var name in root.GetSubKeyNames())
            {
                using var key = root.OpenSubKey(name);
                if (key is null || key.GetValue("SystemComponent") is 1) continue;
                var display = key.GetValue("DisplayName") as string;
                var icon = (key.GetValue("DisplayIcon") as string ?? "").Split(',')[0].Trim().Trim('"');
                var entry = FromExe(display, icon, PickerSource.Installed);
                if (entry is not null) yield return entry;
            }
        }
    }

    private static PickerEntry? FromExe(string? name, string? exe, PickerSource source)
    {
        if (string.IsNullOrWhiteSpace(name) || string.IsNullOrWhiteSpace(exe)) return null;
        if (!exe.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) || IsUnderWindows(exe)) return null;

        var process = Path.GetFileNameWithoutExtension(exe);
        if (AppPicker.IsNotAnApp(name, process)) return null;

        return new PickerEntry
        {
            Name = name.Trim(),
            Processes = new() { process },
            Source = source,
            ExePath = exe,
        };
    }

    /// <summary>The exe's own icon, frozen so it can cross threads; null if there isn't one.</summary>
    public static ImageSource? IconFor(string? exePath)
    {
        if (string.IsNullOrWhiteSpace(exePath) || !File.Exists(exePath)) return null;
        try
        {
            using var icon = System.Drawing.Icon.ExtractAssociatedIcon(exePath);
            if (icon is null) return null;
            var image = System.Windows.Interop.Imaging.CreateBitmapSourceFromHIcon(
                icon.Handle, Int32Rect.Empty, BitmapSizeOptions.FromEmptyOptions());
            image.Freeze();
            return image;
        }
        catch
        {
            return null;
        }
    }

    private static bool IsUnderWindows(string path) =>
        path.StartsWith(WindowsDir, StringComparison.OrdinalIgnoreCase);

    private static void Safely(string what, Action action)
    {
        try { action(); }
        catch (Exception ex) { Log.Warn($"app picker: couldn't read {what}: {ex.Message}"); }
    }
}
