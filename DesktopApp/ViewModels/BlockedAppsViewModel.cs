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

        // Every profile's list gets the F8 top-up, not just the active one: a
        // profile you switch to must not leak through steamwebhelper either.
        var upgraded = false;
        foreach (var profile in main.Settings.Profiles)
            if (UpgradeToFullSuggestions(profile.Apps)) upgraded = true;
        if (upgraded) main.SettingsService.Save(main.Settings);

        Apps = new ObservableCollection<BlockedApp>(ActiveApps);

        AddCommand = new RelayCommand(AddApp, CanAdd);
        RemoveCommand = new RelayCommand(p => RemoveApp(p as BlockedApp), p => p is BlockedApp && !IsSealed);
        RefreshRunningCommand = new RelayCommand(RefreshPicker);
        PickCommand = new RelayCommand(p => Pick(p as PickerEntry),
            p => p is PickerEntry { IsAdded: false } && IsEditable && !_main.IsLocked);
        ToggleAppCommand = new RelayCommand(p => ToggleApp(p as BlockedApp),
            p => p is BlockedApp && CanEditApps);

        SelectProfileCommand = new RelayCommand(p => SelectProfile(p as BlocklistProfile),
            p => p is BlocklistProfile && CanSwitchProfile);
        NewProfileCommand = new RelayCommand(p => NewProfile(p as string), p => CanEditProfiles);
        RenameProfileCommand = new RelayCommand(RenameActiveProfile, () => CanEditProfiles);
        DuplicateProfileCommand = new RelayCommand(DuplicateActiveProfile, () => CanEditProfiles);
        DeleteProfileCommand = new RelayCommand(AskToDeleteProfile, () => CanDeleteProfile);
        ConfirmDeleteProfileCommand = new RelayCommand(DeleteActiveProfile, () => CanDeleteProfile);
        CancelDeleteProfileCommand = new RelayCommand(() => DeleteProfileConfirmVisible = false);

        RefreshProfiles();

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
    public RelayCommand ToggleAppCommand { get; }

    // ------------------------------------------------- blocklist profiles (F9)

    public RelayCommand SelectProfileCommand { get; }
    public RelayCommand NewProfileCommand { get; }
    public RelayCommand RenameProfileCommand { get; }
    public RelayCommand DuplicateProfileCommand { get; }
    public RelayCommand DeleteProfileCommand { get; }
    public RelayCommand ConfirmDeleteProfileCommand { get; }
    public RelayCommand CancelDeleteProfileCommand { get; }

    /// <summary>The switcher's chips, in stored order.</summary>
    public ObservableCollection<BlocklistProfile> Profiles { get; } = new();

    /// <summary>The profile being edited on this page, and the only one enforced.</summary>
    public BlocklistProfile ActiveProfile => _main.Settings.ActiveProfile;

    /// <summary>The active profile's list — where an add or a remove lands.</summary>
    private List<BlockedApp> ActiveApps => ActiveProfile.Apps;

    public string ActiveProfileName => ActiveProfile.Name;

    /// <summary>Today's one-line caption, kept here so both pages say the same thing.</summary>
    public string ProfileCaption => $"Blocking: {ActiveProfile.Name}";

    /// <summary>
    /// Whether the switcher works. Sealed locks the active profile as well as
    /// the list: swapping the list a Sealed sprint enforces would be the same
    /// escape hatch as editing it, by another route.
    /// </summary>
    public bool CanSwitchProfile => !IsSealed;

    /// <summary>Rename, duplicate and new: the same lock, plus the trial gate.</summary>
    public bool CanEditProfiles => !IsSealed && !_main.IsLocked;

    /// <summary>There is always at least one profile, so the last one has no Delete.</summary>
    public bool CanDeleteProfile => CanEditProfiles && Profiles.Count > 1;

    /// <summary>Names offered, never created (see <see cref="AppSettings.SuggestedProfileNames"/>).</summary>
    public IReadOnlyList<string> SuggestedProfileNames => AppSettings.SuggestedProfileNames;

    private string _profileNameText = "";

    /// <summary>The rename and new-profile field.</summary>
    public string ProfileNameText
    {
        get => _profileNameText;
        set
        {
            if (!Set(ref _profileNameText, value)) return;
            System.Windows.Input.CommandManager.InvalidateRequerySuggested();
        }
    }

    private bool _deleteProfileConfirmVisible;

    /// <summary>Deleting a profile takes its list with it, so it asks first.</summary>
    public bool DeleteProfileConfirmVisible
    {
        get => _deleteProfileConfirmVisible;
        private set
        {
            if (!Set(ref _deleteProfileConfirmVisible, value)) return;
            Raise(nameof(DeleteProfileConfirmText));
        }
    }

    public string DeleteProfileConfirmText =>
        $"Delete \"{ActiveProfile.Name}\" and the {ActiveProfile.Apps.Count} app"
        + $"{(ActiveProfile.Apps.Count == 1 ? "" : "s")} on it?";

    private void SelectProfile(BlocklistProfile? profile)
    {
        if (profile is null) return;

        // Refused here, not only by a disabled chip: a covered or disabled
        // control can still be invoked by automation (#134), and the Sealed
        // promise has to hold in the view model.
        if (IsSealed)
        {
            _main.Toast("The blocklist is sealed until this sprint ends.");
            RefreshProfiles();
            return;
        }

        if (!_main.Settings.SetActiveProfile(profile.Id)) { RefreshProfiles(); return; }

        DeleteProfileConfirmVisible = false;
        _main.SaveSettings();            // also republishes the new list to the blocker
        ReloadActiveProfile();
        Log.Info($"blocklist profile switched to \"{profile.Name}\" ({profile.Apps.Count} apps)");
    }

    private void NewProfile(string? name)
    {
        if (!GuardProfileEdit()) return;

        // A new profile starts from the list already on screen, because "School"
        // is usually today's list minus one app rather than an empty page.
        var wanted = string.IsNullOrWhiteSpace(name) ? ProfileNameText : name;
        var profile = _main.Settings.AddProfile(wanted, ActiveApps);
        _main.Settings.SetActiveProfile(profile.Id);
        ProfileNameText = "";
        _main.SaveSettings();
        ReloadActiveProfile();
        _main.Toast($"Profile \"{profile.Name}\" added, starting from your current blocklist.");
        Log.Info($"blocklist profile added: \"{profile.Name}\"");
    }

    private void RenameActiveProfile()
    {
        if (!GuardProfileEdit()) return;
        if (string.IsNullOrWhiteSpace(ProfileNameText))
        {
            _main.Toast("Type a name for this profile first.");
            return;
        }

        var before = ActiveProfile.Name;
        if (!_main.Settings.RenameProfile(ActiveProfile.Id, ProfileNameText)) return;

        ProfileNameText = "";
        _main.SaveSettings();
        RefreshProfiles();
        _main.Toast($"Renamed to \"{ActiveProfile.Name}\".");
        Log.Info($"blocklist profile renamed: \"{before}\" to \"{ActiveProfile.Name}\"");
    }

    private void DuplicateActiveProfile()
    {
        if (!GuardProfileEdit()) return;

        var copy = _main.Settings.DuplicateProfile(ActiveProfile.Id);
        if (copy is null) return;

        _main.Settings.SetActiveProfile(copy.Id);
        _main.SaveSettings();
        ReloadActiveProfile();
        _main.Toast($"Profile \"{copy.Name}\" added.");
        Log.Info($"blocklist profile duplicated: \"{copy.Name}\"");
    }

    private void AskToDeleteProfile()
    {
        if (!GuardProfileEdit()) return;
        if (Profiles.Count <= 1)
        {
            _main.Toast("This is your only profile, so it stays.");
            return;
        }
        Raise(nameof(DeleteProfileConfirmText));
        DeleteProfileConfirmVisible = true;
    }

    private void DeleteActiveProfile()
    {
        if (!GuardProfileEdit()) return;

        var name = ActiveProfile.Name;
        if (!_main.Settings.RemoveProfile(ActiveProfile.Id))
        {
            _main.Toast("This is your only profile, so it stays.");
            DeleteProfileConfirmVisible = false;
            return;
        }

        DeleteProfileConfirmVisible = false;
        _main.SaveSettings();
        ReloadActiveProfile();
        _main.Toast($"Profile \"{name}\" deleted.");
        Log.Info($"blocklist profile deleted: \"{name}\"");
    }

    private bool GuardProfileEdit()
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

    /// <summary>
    /// Rebuilds the visible list from the active profile and refreshes the page.
    /// Public because a resumed sprint restores its own profile (F3 + F9).
    /// </summary>
    public void ReloadActiveProfile()
    {
        Apps.Clear();
        foreach (var app in ActiveApps) Apps.Add(app);
        RefreshProfiles();
        RefreshStatus();
        ApplyFilter();
    }

    /// <summary>Re-syncs the switcher chips, their checked state and the captions.</summary>
    public void RefreshProfiles()
    {
        var active = ActiveProfile;

        Profiles.Clear();
        foreach (var profile in _main.Settings.Profiles)
        {
            profile.IsActive = ReferenceEquals(profile, active);
            Profiles.Add(profile);
        }

        Raise(nameof(ActiveProfile));
        Raise(nameof(ActiveProfileName));
        Raise(nameof(ProfileCaption));
        Raise(nameof(CanSwitchProfile));
        Raise(nameof(CanEditProfiles));
        Raise(nameof(CanDeleteProfile));
        Raise(nameof(DeleteProfileConfirmText));
        _main.Today.RefreshProfileCaption();
    }

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
            ActiveApps.Add(app);      // the selected profile only (F9)
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

    /// <summary>False while a Sealed sprint holds the blocklist shut.</summary>
    public bool CanEditApps => !IsSealed;

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
        ActiveApps.RemoveAll(a =>
            string.Equals(a.ProcessName, app.ProcessName, StringComparison.OrdinalIgnoreCase));
        _main.SaveSettings();
        RefreshStatus();
        ApplyFilter();
        Log.Info($"blocked app removed: {app.ProcessName}");
    }

    public void ToggleApp(BlockedApp? app)
    {
        if (app is null) return;
        if (IsSealed)
        {
            _main.Toast("The blocklist is sealed until this sprint ends.");
            return;
        }
        // The switch's two-way IsChecked binding has already written the new
        // value into app.IsEnabled; this command persists it and refreshes.
        _main.SaveSettings();
        RefreshStatus();
    }

    public void RefreshStatus()
    {
        LimitText = $"{Apps.Count} blocked · no limit";

        StatusText = IsSealed
            ? $"Sealed — \"{ActiveProfile.Name}\" is locked until this sprint ends."
            : $"{Apps.Count} app{(Apps.Count == 1 ? "" : "s")} on \"{ActiveProfile.Name}\".";

        Raise(nameof(IsSealed));
        Raise(nameof(IsEditable));
        Raise(nameof(CanEditApps));
        Raise(nameof(CanSwitchProfile));
        Raise(nameof(CanEditProfiles));
        Raise(nameof(CanDeleteProfile));
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
