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
        if (UpgradeToFullSuggestions(main.Settings.BlockedApps)) main.SettingsService.Save(main.Settings);
        Apps = new ObservableCollection<BlockedApp>(main.Settings.BlockedApps);

        AddCommand = new RelayCommand(AddApp, CanAdd);
        RemoveCommand = new RelayCommand(p => RemoveApp(p as BlockedApp), p => p is BlockedApp && !IsSealed);
        RefreshRunningCommand = new RelayCommand(RefreshPicker);
        PickCommand = new RelayCommand(p => Pick(p as PickerEntry),
            p => p is PickerEntry { IsAdded: false } && IsEditable && !_main.IsLocked);

        _allEntries = AppPicker.Suggestions(IsProtected);
        ApplyFilter();
        RefreshPicker();
        RefreshStatus();
    }

    public ObservableCollection<BlockedApp> Apps { get; }

    public RelayCommand AddCommand { get; }
    public RelayCommand RemoveCommand { get; }
    public RelayCommand RefreshRunningCommand { get; }
    public RelayCommand PickCommand { get; }

    // ----------------------------------------------------------- picker (F8)

    private List<PickerEntry> _allEntries;

    /// <summary>What the picker shows for the current search.</summary>
    public ObservableCollection<PickerEntry> PickerResults { get; } = new();

    private string _pickerQuery = "";
    public string PickerQuery
    {
        get => _pickerQuery;
        set { if (Set(ref _pickerQuery, value)) ApplyFilter(); }
    }

    private string _pickerNotice = "";
    /// <summary>Explains an empty or protected search.</summary>
    public string PickerNotice
    {
        get => _pickerNotice;
        private set { if (Set(ref _pickerNotice, value)) Raise(nameof(HasPickerNotice)); }
    }

    public bool HasPickerNotice => PickerNotice.Length > 0;

    private static bool IsProtected(string processName) =>
        AppBlockerService.CriticalProcesses.Contains(NormalizeProcessName(processName));

    private void RefreshPicker()
    {
        var suggestions = AppPicker.Suggestions(IsProtected);
        Task.Run(() =>
        {
            var discovered = AppCatalog.Discover();
            var merged = AppPicker.Merge(suggestions, discovered, IsProtected);
            var icons = merged.Select(e => (Entry: e, Icon: AppCatalog.IconFor(e.ExePath))).ToList();
            Log.Info($"app picker: {discovered.Count} found on this PC, {merged.Count} listed, "
                     + $"{icons.Count(i => i.Icon is not null)} with icons");
            System.Windows.Application.Current?.Dispatcher.BeginInvoke(() =>
            {
                foreach (var (entry, icon) in icons) entry.Icon = icon;
                _allEntries = merged;
                ApplyFilter();
            });
        });
    }

    private void ApplyFilter()
    {
        var results = AppPicker.Filter(_allEntries, PickerQuery);
        PickerResults.Clear();
        foreach (var entry in results)
        {
            entry.IsAdded = IsOnList(entry);
            PickerResults.Add(entry);
        }

        var query = NormalizeProcessName(PickerQuery ?? "");
        PickerNotice = query.Length > 0 && IsProtected(query)
            ? AppPicker.ProtectedMessage
            : results.Count == 0 && query.Length > 0
                ? $"No app called “{PickerQuery!.Trim()}” found. Type its process name in the box on the left."
                : "";
    }

    private bool IsOnList(PickerEntry entry) =>
        entry.Processes.All(p => Apps.Any(a => a.AllProcessNames.Contains(p, StringComparer.OrdinalIgnoreCase)));

    /// <summary>Adds a picker entry without a toast; used by the first run.</summary>
    public bool AddEntry(PickerEntry entry)
    {
        var added = AddProcesses(entry.Name, entry.Processes, entry.ExePath);
        ApplyFilter();
        return added;
    }

    /// <summary>Whether every process of the entry is already blocked.</summary>
    public bool IsBlocked(PickerEntry entry) => IsOnList(entry);

    private void Pick(PickerEntry? entry)
    {
        if (entry is null || !CanEdit()) return;
        var added = AddProcesses(entry.Name, entry.Processes, entry.ExePath);
        if (added) _main.Toast($"{entry.Name} is on the shield.");
        ApplyFilter();
    }

    /// <summary>
    /// Adds an app with all its processes, or tops up the entry that already
    /// has one of them. Returns false if nothing changed.
    /// </summary>
    private bool AddProcesses(string name, IEnumerable<string> processes, string? iconPath)
    {
        var names = processes.Select(NormalizeProcessName)
            .Where(p => p.Length > 0 && !IsProtected(p))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
        if (names.Count == 0) return false;

        var existing = Apps.FirstOrDefault(a =>
            a.AllProcessNames.Any(p => names.Contains(p, StringComparer.OrdinalIgnoreCase)));
        if (existing is not null)
        {
            var missing = names.Where(n => !existing.AllProcessNames.Contains(n, StringComparer.OrdinalIgnoreCase)).ToList();
            if (missing.Count == 0)
            {
                _main.Toast($"{existing.DisplayName} is already on the list.");
                return false;
            }
            existing.ExtraProcessNames.AddRange(missing);
            existing.IconPath ??= iconPath;
        }
        else
        {
            var app = new BlockedApp
            {
                Name = name,
                ProcessName = names[0],
                ExtraProcessNames = names.Skip(1).ToList(),
                IconPath = iconPath,
                IsEnabled = true,
            };
            Apps.Add(app);
            _main.Settings.BlockedApps.Add(app);
        }

        _main.SaveSettings();
        RefreshStatus();
        Log.Info($"blocked app added: {string.Join(", ", names)}");
        return true;
    }

    /// <summary>
    /// Gives existing single-process entries the rest of their app's processes,
    /// so a Steam block saved before F8 stops leaking through steamwebhelper.
    /// </summary>
    public static bool UpgradeToFullSuggestions(List<BlockedApp> apps)
    {
        var changed = false;
        foreach (var app in apps)
        {
            var suggestion = AppPicker.SuggestionFor(app.ProcessName, IsProtected);
            if (suggestion is null) continue;
            foreach (var process in suggestion.Processes)
            {
                if (app.AllProcessNames.Contains(process, StringComparer.OrdinalIgnoreCase)) continue;
                app.ExtraProcessNames.Add(process);
                changed = true;
            }
        }
        return changed;
    }

    private bool CanEdit()
    {
        if (IsSealed)
        {
            _main.Toast("The blocklist is sealed until this sprint ends.");
            return false;
        }
        if (_main.IsLocked)
        {
            _main.Toast("Your free trial has ended. Buy FlowShield to edit the blocklist.");
            return false;
        }
        return true;
    }

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

    private BlockedApp? _selectedApp;
    public BlockedApp? SelectedApp { get => _selectedApp; set => Set(ref _selectedApp, value); }

    private string _statusText = "";
    public string StatusText { get => _statusText; private set => Set(ref _statusText, value); }

    private string _limitText = "";
    public string LimitText { get => _limitText; private set => Set(ref _limitText, value); }

    /// <summary>True while a Sealed sprint holds the blocklist shut.</summary>
    public bool IsSealed => _main.IsSprintRunning && _main.Blocker.ActiveShield == ShieldLevel.Sealed;

    public bool IsEditable => !IsSealed;

    private bool CanAdd() => IsEditable && !_main.IsLocked && !string.IsNullOrWhiteSpace(NewAppName);

    private void AddApp()
    {
        var raw = (NewAppName ?? "").Trim();
        if (raw.Length == 0) return;

        if (!CanEdit()) return;

        var processName = NormalizeProcessName(raw);

        if (AppBlockerService.CriticalProcesses.Contains(processName))
        {
            _main.Toast($"\"{processName}\" is a protected system process and can't be blocked.");
            return;
        }

        // Typing "steam" gets the whole of Steam, with the typed name kept first.
        var suggestion = AppPicker.SuggestionFor(processName, IsProtected);
        var processes = suggestion is null
            ? new List<string> { processName }
            : suggestion.Processes.Where(p => !p.Equals(processName, StringComparison.OrdinalIgnoreCase))
                .Prepend(processName).ToList();

        if (AddProcesses(suggestion?.Name ?? Prettify(processName), processes, null))
            NewAppName = "";
        ApplyFilter();
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
        ApplyFilter();
        Log.Info($"blocked app removed: {app.ProcessName}");
    }

    public void ToggleApp(BlockedApp app)
    {
        app.IsEnabled = !app.IsEnabled;
        _main.SaveSettings();
        RefreshStatus();
    }

    public void RefreshStatus()
    {
        LimitText = $"{Apps.Count} blocked · no limit";

        StatusText = IsSealed
            ? "Sealed — the blocklist is locked until this sprint ends."
            : $"{Apps.Count} app{(Apps.Count == 1 ? "" : "s")} on the shield.";

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
