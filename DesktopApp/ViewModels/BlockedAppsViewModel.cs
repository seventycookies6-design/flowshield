using System.Collections.ObjectModel;
using System.Diagnostics;
using FlowShield.Infrastructure;
using FlowShield.Models;
using FlowShield.Services;

namespace FlowShield.ViewModels;

public class BlockedAppsViewModel : ViewModelBase
{
    private readonly MainViewModel _main;

    public BlockedAppsViewModel(MainViewModel main)
    {
        _main = main;
        Apps = new ObservableCollection<BlockedApp>(main.Settings.BlockedApps);

        AddCommand = new RelayCommand(AddApp, CanAdd);
        RemoveCommand = new RelayCommand(p => RemoveApp(p as BlockedApp), p => p is BlockedApp && !IsSealed);
        RefreshRunningCommand = new RelayCommand(LoadRunningProcesses);
        AddRunningCommand = new RelayCommand(AddSelectedRunning, () => SelectedRunning is not null && CanAdd());

        LoadRunningProcesses();
        RefreshStatus();
    }

    public ObservableCollection<BlockedApp> Apps { get; }
    public ObservableCollection<string> RunningProcesses { get; } = new();

    public RelayCommand AddCommand { get; }
    public RelayCommand RemoveCommand { get; }
    public RelayCommand RefreshRunningCommand { get; }
    public RelayCommand AddRunningCommand { get; }

    private string _newAppName = "";
    public string NewAppName
    {
        get => _newAppName;
        set
        {
            if (!Set(ref _newAppName, value)) return;
            RefreshStatus();

            // Add's CanExecute depends on this text. CommandManager only
            // requeries off user input, so a programmatic change (the running-
            // process picker, or a UI-Automation SetValue) would otherwise
            // leave the button stuck disabled.
            System.Windows.Input.CommandManager.InvalidateRequerySuggested();
        }
    }

    private string? _selectedRunning;
    public string? SelectedRunning { get => _selectedRunning; set => Set(ref _selectedRunning, value); }

    private BlockedApp? _selectedApp;
    public BlockedApp? SelectedApp { get => _selectedApp; set => Set(ref _selectedApp, value); }

    private string _statusText = "";
    public string StatusText { get => _statusText; private set => Set(ref _statusText, value); }

    private string _limitText = "";
    public string LimitText { get => _limitText; private set => Set(ref _limitText, value); }

    /// <summary>True while a Sealed sprint holds the blocklist shut.</summary>
    public bool IsSealed => _main.IsSprintRunning && _main.Blocker.ActiveShield == ShieldLevel.Sealed;

    public bool IsEditable => !IsSealed;

    public bool AtLimit => !_main.IsPro && Apps.Count >= AppSettings.FreeBlockedAppLimit;

    private bool CanAdd() => IsEditable && !AtLimit && !string.IsNullOrWhiteSpace(NewAppName);

    private void AddApp()
    {
        var raw = (NewAppName ?? "").Trim();
        if (raw.Length == 0) return;

        if (IsSealed)
        {
            _main.Toast("The blocklist is sealed until this sprint ends.");
            return;
        }

        if (AtLimit)
        {
            _main.Toast($"Free covers {AppSettings.FreeBlockedAppLimit} apps. Upgrade for unlimited.");
            return;
        }

        var processName = NormalizeProcessName(raw);

        if (AppBlockerService.CriticalProcesses.Contains(processName))
        {
            _main.Toast($"\"{processName}\" is a protected system process and can't be blocked.");
            return;
        }

        if (Apps.Any(a => string.Equals(a.ProcessName, processName, StringComparison.OrdinalIgnoreCase)))
        {
            _main.Toast($"{processName} is already on the list.");
            return;
        }

        var app = new BlockedApp
        {
            Name = Prettify(processName),
            ProcessName = processName,
            IsEnabled = true,
        };

        Apps.Add(app);
        _main.Settings.BlockedApps.Add(app);
        _main.SaveSettings();

        NewAppName = "";
        RefreshStatus();
        Log.Info($"blocked app added: {processName}");
    }

    private void AddSelectedRunning()
    {
        if (SelectedRunning is null) return;
        NewAppName = SelectedRunning;
        AddApp();
    }

    private void RemoveApp(BlockedApp? app)
    {
        if (app is null) return;
        if (IsSealed)
        {
            _main.Toast("The blocklist is sealed until this sprint ends.");
            return;
        }

        Apps.Remove(app);
        _main.Settings.BlockedApps.RemoveAll(a =>
            string.Equals(a.ProcessName, app.ProcessName, StringComparison.OrdinalIgnoreCase));
        _main.SaveSettings();
        RefreshStatus();
        Log.Info($"blocked app removed: {app.ProcessName}");
    }

    public void ToggleApp(BlockedApp app)
    {
        app.IsEnabled = !app.IsEnabled;
        _main.SaveSettings();
        RefreshStatus();
    }

    private void LoadRunningProcesses()
    {
        RunningProcesses.Clear();
        try
        {
            var names = Process.GetProcesses()
                .Select(p =>
                {
                    try { return p.ProcessName; } catch { return null; }
                    finally { p.Dispose(); }
                })
                .Where(n => !string.IsNullOrWhiteSpace(n))
                .Select(n => n!)
                .Where(n => !AppBlockerService.CriticalProcesses.Contains(n))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(n => n, StringComparer.OrdinalIgnoreCase);

            foreach (var n in names) RunningProcesses.Add(n);
        }
        catch (Exception ex)
        {
            Log.Error("failed to enumerate running processes", ex);
        }
    }

    public void RefreshStatus()
    {
        LimitText = _main.IsPro
            ? $"{Apps.Count} blocked · unlimited on Pro"
            : $"{Apps.Count} of {AppSettings.FreeBlockedAppLimit} used on Free";

        StatusText = IsSealed
            ? "Sealed — the blocklist is locked until this sprint ends."
            : AtLimit
                ? "Free limit reached. Upgrade to Pro for unlimited blocked apps."
                : $"{Apps.Count} app{(Apps.Count == 1 ? "" : "s")} on the shield.";

        Raise(nameof(AtLimit));
        Raise(nameof(IsSealed));
        Raise(nameof(IsEditable));
    }

    /// <summary>"C:\path\Slack.exe", "Slack.exe" and "slack" all normalise the same way.</summary>
    public static string NormalizeProcessName(string input)
    {
        var s = input.Trim().Trim('"');
        try { if (s.Contains('\\') || s.Contains('/')) s = System.IO.Path.GetFileName(s); } catch { /* keep raw */ }
        if (s.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) s = s[..^4];
        return s.Trim();
    }

    private static string Prettify(string processName) =>
        processName.Length == 0
            ? processName
            : char.ToUpperInvariant(processName[0]) + processName[1..];
}
