using System.Collections.ObjectModel;
using System.Globalization;
using System.Windows.Input;
using FlowShield.Infrastructure;
using FlowShield.Models;
using FlowShield.Services;

namespace FlowShield.ViewModels;

/// <summary>
/// The Schedule page (F6): schedules and templates on top, and the sleep
/// window below them, unchanged, through <see cref="Sleep"/>.
/// Read-only during a Sealed sprint, like the blocklist.
/// </summary>
public class ScheduleViewModel : ViewModelBase
{
    private const string SealedText =
        "Sealed: schedules and templates stay as they are until this sprint ends.";

    /// <summary>Monday first, the way a school week reads (and ScheduleText lists days).</summary>
    private static readonly DayOfWeek[] WeekOrder =
    {
        DayOfWeek.Monday, DayOfWeek.Tuesday, DayOfWeek.Wednesday, DayOfWeek.Thursday,
        DayOfWeek.Friday, DayOfWeek.Saturday, DayOfWeek.Sunday,
    };

    private readonly MainViewModel _main;
    private AppSettings S => _main.Settings;

    public ScheduleViewModel(MainViewModel main)
    {
        _main = main;

        AddScheduleCommand = new RelayCommand(() => OpenScheduleEditor(null), () => CanEdit);
        EditScheduleCommand = new RelayCommand(p => OpenScheduleEditor(p as ScheduleRow), _ => CanEdit);
        DeleteScheduleCommand = new RelayCommand(p => DeleteSchedule(p as ScheduleRow), _ => CanEdit);
        SaveScheduleCommand = new RelayCommand(SaveSchedule, () => CanSaveSchedule);
        CancelScheduleCommand = new RelayCommand(() => ScheduleEditorVisible = false);

        NewTemplateCommand = new RelayCommand(() => OpenTemplateEditor(null), () => CanEdit);
        EditTemplateCommand = new RelayCommand(p => OpenTemplateEditor((p as TemplateRow)?.Template), _ => CanEdit);
        DeleteTemplateCommand = new RelayCommand(p => DeleteTemplate((p as TemplateRow)?.Template), _ => CanEdit);
        RestoreTemplatesCommand = new RelayCommand(RestoreTemplates, () => CanEdit);
        SaveTemplateCommand = new RelayCommand(SaveTemplate, () => CanEdit && TemplateEditorVisible);
        CancelTemplateCommand = new RelayCommand(() => TemplateEditorVisible = false);

        // Plans (#433): the sleep row's Edit opens the sleep window's own
        // settings, and a template's Start starts it from here as Today's does.
        EditSleepCommand = new RelayCommand(() =>
        {
            SleepEditorVisible = true;
            EditorOpened?.Invoke(this, PlansEditor.Sleep);
        });
        CloseSleepEditorCommand = new RelayCommand(() => SleepEditorVisible = false);
        StartTemplateCommand = new RelayCommand(p => StartTemplate(p as TemplateRow), p => p is TemplateRow);

        Refresh();
    }

    public RelayCommand AddScheduleCommand { get; }
    public RelayCommand EditScheduleCommand { get; }
    public RelayCommand DeleteScheduleCommand { get; }
    public RelayCommand SaveScheduleCommand { get; }
    public RelayCommand CancelScheduleCommand { get; }

    public RelayCommand NewTemplateCommand { get; }
    public RelayCommand EditTemplateCommand { get; }
    public RelayCommand DeleteTemplateCommand { get; }
    public RelayCommand RestoreTemplatesCommand { get; }
    public RelayCommand SaveTemplateCommand { get; }
    public RelayCommand CancelTemplateCommand { get; }

    // --------------------------------------------------------- Plans (#433)

    /// <summary>Edit on the sleep-blocking row.</summary>
    public RelayCommand EditSleepCommand { get; }

    /// <summary>Done, under the sleep window's settings.</summary>
    public RelayCommand CloseSleepEditorCommand { get; }

    /// <summary>Start on a template's row: the same start as Today's template cards.</summary>
    public RelayCommand StartTemplateCommand { get; }

    /// <summary>Which of the section's editors just opened, so the view can bring it into view.</summary>
    public enum PlansEditor { Sleep, Schedule, Template }

    public event EventHandler<PlansEditor>? EditorOpened;

    private bool _sleepEditorVisible;
    /// <summary>The sleep window's start, end and Save, under the Schedules rows.</summary>
    public bool SleepEditorVisible
    {
        get => _sleepEditorVisible;
        private set => Set(ref _sleepEditorVisible, value);
    }

    /// <summary>The schedule being edited, for its Delete inside the editor; null for a new one.</summary>
    public ScheduleRow? EditingScheduleRow => _editingSchedule is null
        ? null
        : Schedules.FirstOrDefault(r => ReferenceEquals(r.Schedule, _editingSchedule));

    /// <summary>The template being edited, for its Delete inside the editor; null for a new one.</summary>
    public TemplateRow? EditingTemplateRow => _editingTemplate is null
        ? null
        : Templates.FirstOrDefault(r => ReferenceEquals(r.Template, _editingTemplate));

    public bool CanDeleteEditedSchedule => EditingScheduleRow is not null;
    public bool CanDeleteEditedTemplate => EditingTemplateRow is not null;

    /// <summary>
    /// Start on a template row. The sprint runs on Today, and F7's open-apps
    /// question is asked there, so the start goes through Today and the page
    /// follows it; every gate (a sprint already running, the trial, Sealed)
    /// is Today's own.
    /// </summary>
    private void StartTemplate(TemplateRow? row)
    {
        if (row is null) return;
        _main.CurrentPage = AppPage.Today;
        _main.Today.StartTemplateCommand.Execute(row);
    }

    private void RaiseEditing()
    {
        Raise(nameof(EditingScheduleRow));
        Raise(nameof(EditingTemplateRow));
        Raise(nameof(CanDeleteEditedSchedule));
        Raise(nameof(CanDeleteEditedTemplate));
    }

    /// <summary>The sleep window, exactly as before (Miles's Roadmap 3.7 reworks it in place).</summary>
    public SleepBlockingViewModel Sleep => _main.SleepBlocking;

    /// <summary>Raised when templates are added, renamed or removed, so Today's chips and the Jump List follow.</summary>
    public event EventHandler? TemplatesChanged;

    private bool IsSealed => _main.IsSprintRunning && _main.Blocker.ActiveShield == ShieldLevel.Sealed;

    /// <summary>Sealed locks the blocklist for the sprint; schedules and templates follow the same rule.</summary>
    public bool CanEdit => !IsSealed && !_main.IsLocked;

    public ObservableCollection<ScheduleRow> Schedules { get; } = new();
    public ObservableCollection<TemplateRow> Templates { get; } = new();

    private string _nextUpText = "";
    /// <summary>"Next: tonight 17:00, Homework evening", or why there is none.</summary>
    public string NextUpText { get => _nextUpText; private set => Set(ref _nextUpText, value); }

    private string _statusText = "";
    /// <summary>The schedules card's line: a time that didn't parse, or the Sealed lock.</summary>
    public string StatusText { get => _statusText; private set => Set(ref _statusText, value); }

    /// <summary>Rebuilds the page from the settings. Run on entering the page and whenever the sprint or tier changes.</summary>
    public void Refresh()
    {
        // New row objects every time, never the same StudyTemplate cleared and
        // added back: UI Automation keeps its item peers by item, and reusing
        // them dropped every template's row and buttons from the tree (and so
        // from screen readers) after the first save.
        Templates.Clear();
        foreach (var t in S.Templates)
        {
            var profile = S.FindProfile(t.ProfileId);
            Templates.Add(new TemplateRow(t)
            {
                PlansDetail = $"{t.SprintMinutes} min at {t.Shield}, "
                              + (profile is null ? "the blocklist in use" : $"{profile.Name} blocklist"),
            });
        }

        Schedules.Clear();
        foreach (var s in S.Schedules)
            Schedules.Add(new ScheduleRow(s, S.FindTemplate(s.TemplateId)?.Name ?? "", SetScheduleEnabled));

        // An editor must not outlive what it edits: deleting a template takes
        // its schedules with it, and either row can be deleted mid-edit.
        if (_editingSchedule is not null && !S.Schedules.Contains(_editingSchedule)) ScheduleEditorVisible = false;
        if (_editingTemplate is not null && !S.Templates.Contains(_editingTemplate)) TemplateEditorVisible = false;
        if (ScheduleEditorVisible) RebuildTemplateChoices(EditorTemplate?.Id);

        NextUpText = BuildNextUp(DateTime.UtcNow, TimeZoneInfo.Local);

        if (IsSealed) StatusText = SealedText;
        else if (StatusText == SealedText) StatusText = "";
        RaiseEditing();

        Raise(nameof(CanEdit));
        CommandManager.InvalidateRequerySuggested();
    }

    private string BuildNextUp(DateTime nowUtc, TimeZoneInfo zone)
    {
        if (S.Schedules.Count == 0) return "No schedules yet";

        var next = S.Schedules
            .Where(s => s.Enabled)
            .Select(s => (Schedule: s, At: ScheduleMatcher.NextStartUtc(s, nowUtc, zone)))
            .Where(x => x.At is not null)
            .OrderBy(x => x.At)
            .FirstOrDefault();
        if (next.Schedule is null) return "All your schedules are off";

        var name = S.FindTemplate(next.Schedule.TemplateId)?.Name ?? "";
        return ScheduleText.NextUp(name,
            TimeZoneInfo.ConvertTimeFromUtc(next.At!.Value, zone),
            TimeZoneInfo.ConvertTimeFromUtc(nowUtc, zone));
    }

    /// <summary>
    /// The refusal behind every change. The buttons are disabled as well, but a
    /// disabled or covered control can still be reached (CLAUDE.md, "Covered
    /// controls"), so the rule has to hold here too.
    /// </summary>
    private bool EnsureCanEdit()
    {
        if (CanEdit) return true;
        _main.Toast(IsSealed ? SealedText : "Your free trial has ended. Buy Basalt to change your schedules.");
        return false;
    }

    // ------------------------------------------------------ schedule editor

    private SprintSchedule? _editingSchedule;

    private bool _scheduleEditorVisible;
    public bool ScheduleEditorVisible
    {
        get => _scheduleEditorVisible;
        private set { if (Set(ref _scheduleEditorVisible, value)) CommandManager.InvalidateRequerySuggested(); }
    }

    /// <summary>The template picker: one chip per template, the one Save would use checked.</summary>
    public ObservableCollection<Choice<StudyTemplate>> EditorTemplates { get; } = new();

    /// <summary>Mon..Sun chips, Monday first.</summary>
    public ObservableCollection<Choice<DayOfWeek>> EditorDays { get; } = new();

    private StudyTemplate? EditorTemplate => EditorTemplates.FirstOrDefault(c => c.IsChosen)?.Value;

    private string _editorTime = "";
    public string EditorTime { get => _editorTime; set => Set(ref _editorTime, value); }

    private bool _editorAskFirst = true;
    public bool EditorAskFirst { get => _editorAskFirst; set => Set(ref _editorAskFirst, value); }

    private bool CanSaveSchedule =>
        CanEdit && ScheduleEditorVisible && EditorTemplate is not null && EditorDays.Any(d => d.IsChosen);

    private void OpenScheduleEditor(ScheduleRow? row)
    {
        if (!EnsureCanEdit()) return;

        _editingSchedule = row?.Schedule;
        var source = row?.Schedule ?? new SprintSchedule();   // a new one starts from the model's defaults
        RebuildTemplateChoices(row is null ? S.Templates.FirstOrDefault()?.Id : source.TemplateId);

        EditorDays.Clear();
        foreach (var day in WeekOrder)
        {
            var label = CultureInfo.InvariantCulture.DateTimeFormat.GetAbbreviatedDayName(day);
            EditorDays.Add(Watch(new Choice<DayOfWeek>(day, label, source.Days.Contains(day))
            {
                AutomationId = $"ScheduleDay_{label}",
                AccessibleName = CultureInfo.InvariantCulture.DateTimeFormat.GetDayName(day),
            }));
        }

        EditorTime = ScheduleText.Time(source.StartMinuteOfDay);
        EditorAskFirst = source.AskFirst;
        StatusText = "";
        ScheduleEditorVisible = true;
        RaiseEditing();
        EditorOpened?.Invoke(this, PlansEditor.Schedule);
    }

    /// <summary>One chip per template, keeping the choice when that template still exists.</summary>
    private void RebuildTemplateChoices(string? chosenId)
    {
        EditorTemplates.Clear();
        foreach (var t in S.Templates)
        {
            EditorTemplates.Add(Watch(new Choice<StudyTemplate>(t, t.Name, t.Id == chosenId)
            {
                AutomationId = $"ScheduleTemplate_{t.Name}",
            }));
        }
    }

    /// <summary>Save's enabled state follows the chips, which change without a keystroke to requery it.</summary>
    private static Choice<T> Watch<T>(Choice<T> choice)
    {
        choice.Changed += (_, _) => CommandManager.InvalidateRequerySuggested();
        return choice;
    }

    private void SaveSchedule()
    {
        if (!EnsureCanEdit() || !CanSaveSchedule || EditorTemplate is not { } template) return;
        if (!SleepBlockingViewModel.TryParse(EditorTime, out var time))
        {
            StatusText = $"\"{EditorTime}\" isn't a valid time. Use HH:mm, e.g. 17:00.";
            return;
        }

        var schedule = _editingSchedule ?? new SprintSchedule();
        schedule.TemplateId = template.Id;
        schedule.Days = EditorDays.Where(d => d.IsChosen).Select(d => d.Value).ToList();
        schedule.StartMinuteOfDay = (int)time.TotalMinutes;
        schedule.AskFirst = EditorAskFirst;
        schedule.Normalize();
        if (_editingSchedule is null) S.Schedules.Add(schedule);

        _main.SaveSettings();
        ScheduleEditorVisible = false;
        StatusText = "";
        Refresh();
        _main.Toast("Schedule saved.");
        Log.Info($"schedule saved: {template.Name} {ScheduleText.Days(schedule.Days)} "
                 + $"{ScheduleText.Time(schedule.StartMinuteOfDay)}, ask first {schedule.AskFirst}");
    }

    private void DeleteSchedule(ScheduleRow? row)
    {
        if (row is null || !EnsureCanEdit()) return;
        S.Schedules.Remove(row.Schedule);
        _main.SaveSettings();
        Refresh();
        // A card on Today for this schedule has nothing left to offer (F6).
        _main.Today.DropStaleHeadsUp(DateTime.UtcNow);
        _main.Today.RefreshUpNext(DateTime.UtcNow);
        Log.Info($"schedule deleted: {row.TemplateName}");
    }

    /// <summary>The row's on/off switch.</summary>
    private void SetScheduleEnabled(ScheduleRow row, bool enabled)
    {
        if (!EnsureCanEdit()) { row.RaiseEnabled(); return; }
        if (row.Schedule.Enabled == enabled) return;

        row.Schedule.Enabled = enabled;
        _main.SaveSettings();
        NextUpText = BuildNextUp(DateTime.UtcNow, TimeZoneInfo.Local);
        _main.Today.DropStaleHeadsUp(DateTime.UtcNow);
        _main.Today.RefreshUpNext(DateTime.UtcNow);
        Log.Info($"schedule {(enabled ? "on" : "off")}: {row.TemplateName}");
    }

    // ------------------------------------------------------ template editor

    private StudyTemplate? _editingTemplate;

    private bool _templateEditorVisible;
    public bool TemplateEditorVisible
    {
        get => _templateEditorVisible;
        private set { if (Set(ref _templateEditorVisible, value)) CommandManager.InvalidateRequerySuggested(); }
    }

    private string _templateName = "";
    public string TemplateName { get => _templateName; set => Set(ref _templateName, value); }

    private string _templateMinutes = "";
    public string TemplateMinutes { get => _templateMinutes; set => Set(ref _templateMinutes, value); }

    private ShieldLevel _templateShield = ShieldLevel.Firm;
    public ShieldLevel TemplateShield { get => _templateShield; set => Set(ref _templateShield, value); }

    private int _templateCycle;
    /// <summary>One of <see cref="CycleState.CycleChoices"/>; 0 is a single sprint.</summary>
    public int TemplateCycle { get => _templateCycle; set => Set(ref _templateCycle, value); }

    private string _templateBreak = "";
    public string TemplateBreak { get => _templateBreak; set => Set(ref _templateBreak, value); }

    /// <summary>"Sprint minutes (5-240)": the label over the field, from the same bounds Save checks.
    /// Sentence case like every field label since the redesign (#431, #433).</summary>
    public string SprintMinutesLabel =>
        $"Sprint minutes ({StudyTemplate.MinSprintMinutes}\u2013{StudyTemplate.MaxSprintMinutes})";

    /// <summary>"Break minutes (1-60)", likewise.</summary>
    public string BreakMinutesLabel =>
        $"Break minutes ({CycleState.MinBreakMinutes}\u2013{CycleState.MaxBreakMinutes})";

    /// <summary>"Active profile" first (a null value: whichever is active when it starts), then each blocklist.</summary>
    public ObservableCollection<Choice<BlocklistProfile?>> TemplateProfiles { get; } = new();

    private string _templateStatusText = "";
    /// <summary>The templates card's line: a length or break out of range.</summary>
    public string TemplateStatusText { get => _templateStatusText; private set => Set(ref _templateStatusText, value); }

    private void OpenTemplateEditor(StudyTemplate? template)
    {
        if (!EnsureCanEdit()) return;

        _editingTemplate = template;
        var source = template ?? new StudyTemplate();   // a new one starts from the model's defaults
        TemplateName = source.Name;
        TemplateMinutes = source.SprintMinutes.ToString(CultureInfo.InvariantCulture);
        TemplateShield = source.Shield;
        TemplateCycle = source.CycleSprints;
        TemplateBreak = source.BreakMinutes.ToString(CultureInfo.InvariantCulture);

        var profile = S.FindProfile(source.ProfileId);
        TemplateProfiles.Clear();
        TemplateProfiles.Add(new Choice<BlocklistProfile?>(null, "Active profile", profile is null)
        {
            // Not TemplateProfile_{name}: a profile called "Active" would collide.
            AutomationId = "TemplateProfileActive",
            AccessibleName = "Use whichever blocklist is active",
        });
        foreach (var p in S.Profiles)
        {
            TemplateProfiles.Add(new Choice<BlocklistProfile?>(p, p.Name, ReferenceEquals(p, profile))
            {
                AutomationId = $"TemplateProfile_{p.Name}",
                AccessibleName = $"Use the {p.Name} blocklist",
            });
        }

        TemplateStatusText = "";
        TemplateEditorVisible = true;
        RaiseEditing();
        EditorOpened?.Invoke(this, PlansEditor.Template);
    }

    private void SaveTemplate()
    {
        if (!EnsureCanEdit() || !TemplateEditorVisible) return;

        if (!int.TryParse(TemplateMinutes, NumberStyles.Integer, CultureInfo.InvariantCulture, out var minutes)
            || minutes < StudyTemplate.MinSprintMinutes || minutes > StudyTemplate.MaxSprintMinutes)
        {
            TemplateStatusText =
                $"Sprint length must be {StudyTemplate.MinSprintMinutes}\u2013{StudyTemplate.MaxSprintMinutes} minutes.";
            return;
        }
        if (!int.TryParse(TemplateBreak, NumberStyles.Integer, CultureInfo.InvariantCulture, out var breakMinutes)
            || !CycleState.IsValidBreakMinutes(breakMinutes))
        {
            TemplateStatusText = $"Breaks must be {CycleState.MinBreakMinutes}\u2013{CycleState.MaxBreakMinutes} minutes.";
            return;
        }

        var template = _editingTemplate ?? new StudyTemplate();
        template.Name = TemplateName;
        template.SprintMinutes = minutes;
        template.Shield = TemplateShield;
        template.CycleSprints = TemplateCycle;
        template.BreakMinutes = breakMinutes;
        template.ProfileId = TemplateProfiles.FirstOrDefault(c => c.IsChosen)?.Value?.Id ?? "";
        template.Normalize();
        // After Normalize, so the number is added to the cleaned name. Two
        // templates called "Mine" would be indistinguishable on the page.
        template.Name = S.UniqueTemplateName(template.Name, except: template);
        if (_editingTemplate is null) S.Templates.Add(template);

        _main.SaveSettings();
        TemplateEditorVisible = false;
        TemplateStatusText = "";
        Refresh();
        TemplatesChanged?.Invoke(this, EventArgs.Empty);
        _main.Toast($"\"{template.Name}\" saved.");
        Log.Info($"template saved: {template.Name}, {template.SprintMinutes}m at shield {template.Shield}, "
                 + $"cycle {template.CycleSprints}, breaks {template.BreakMinutes}m");
    }

    private void DeleteTemplate(StudyTemplate? template)
    {
        if (template is null || !EnsureCanEdit()) return;

        var count = S.SchedulesUsing(template.Id).Count;
        // Quoted, like Blocked Apps' "Delete "School" and the 3 apps on it?".
        var question = count switch
        {
            0 => $"Delete \"{template.Name}\"?",
            1 => $"Delete \"{template.Name}\" and the 1 schedule that starts it?",
            _ => $"Delete \"{template.Name}\" and the {count} schedules that start it?",
        };
        if (!_main.Confirm(question, "Delete")) return;

        // The dialog is modal, but a sprint can still start behind it (the
        // tray, the global hotkey), so ask again before changing anything.
        if (!EnsureCanEdit()) return;

        S.DeleteTemplate(template.Id);
        _main.SaveSettings();
        Refresh();
        TemplatesChanged?.Invoke(this, EventArgs.Empty);
        _main.Today.DropStaleHeadsUp(DateTime.UtcNow);
        _main.Today.RefreshUpNext(DateTime.UtcNow);
        Log.Info($"template deleted: {template.Name}, with {count} schedule(s)");
    }

    private void RestoreTemplates()
    {
        if (!EnsureCanEdit()) return;

        var added = S.RestoreBuiltInTemplates();
        if (added > 0)
        {
            _main.SaveSettings();
            Refresh();
            TemplatesChanged?.Invoke(this, EventArgs.Empty);
            Log.Info($"built-in templates restored: {added}");
        }
        _main.Toast(added switch
        {
            0 => "All three built-in templates are already here.",
            1 => "Restored 1 template.",
            _ => $"Restored {added} templates.",
        });
    }
}

/// <summary>One row on the Schedule page.</summary>
public class ScheduleRow : ViewModelBase
{
    private readonly Action<ScheduleRow, bool> _setEnabled;

    public ScheduleRow(SprintSchedule schedule, string templateName, Action<ScheduleRow, bool> setEnabled)
    {
        Schedule = schedule;
        TemplateName = templateName;
        _setEnabled = setEnabled;
    }

    public SprintSchedule Schedule { get; }
    public string Id => Schedule.Id;
    public string TemplateName { get; }

    /// <summary>"Homework evening, Mon-Thu, 17:00, asks first": the whole row in one line, for a screen reader.</summary>
    public string Summary => $"{TemplateName}, {Detail}";

    /// <summary>
    /// The line under the template's name on Plans (#433): "Mon-Thu, 17:00,
    /// Basalt asks 5 minutes before". Commas, not middle dots (design README).
    /// </summary>
    public string Detail =>
        $"{ScheduleText.Days(Schedule.Days)}, {ScheduleText.Time(Schedule.StartMinuteOfDay)}"
        + (Schedule.AskFirst ? ", Basalt asks 5 minutes before" : "");

    /// <summary>
    /// The row's switch. Set through the page, which saves it or, during a
    /// Sealed sprint, refuses and snaps the switch back. A two-way binding
    /// rather than a Click handler, so UI Automation's Toggle works too.
    /// </summary>
    public bool Enabled
    {
        get => Schedule.Enabled;
        set => _setEnabled(this, value);
    }

    public void RaiseEnabled() => Raise(nameof(Enabled));
}

/// <summary>
/// One template on the Schedule page or one of Today's chips, rebuilt on every
/// refresh like <see cref="ScheduleRow"/>.
/// </summary>
public class TemplateRow : ViewModelBase
{
    public TemplateRow(StudyTemplate template) => Template = template;

    public StudyTemplate Template { get; }
    public string Name => Template.Name;

    /// <summary>Today's template card (#431): "45 min at Firm", beside the shield's glyph.</summary>
    public string Detail => $"{Template.SprintMinutes} min at {Template.Shield}";
    public ShieldLevel Shield => Template.Shield;

    /// <summary>
    /// Plans' template row (#433): "45 min at Firm, Default blocklist", or "...,
    /// the blocklist in use" for a template that follows whichever is active.
    /// Filled in by the page, which knows the blocklists.
    /// </summary>
    public string PlansDetail { get; init; } = "";
}

/// <summary>One chip in an editor: a day, a template or a blocklist.</summary>
public class Choice<T> : ViewModelBase
{
    public Choice(T value, string label, bool chosen)
    {
        Value = value;
        Label = label;
        AccessibleName = label;
        _isChosen = chosen;
    }

    public T Value { get; }

    /// <summary>What the chip says.</summary>
    public string Label { get; }

    /// <summary>
    /// The chip's whole AutomationId, built where the chip is: ScheduleDay_Mon,
    /// ScheduleTemplate_{name}, TemplateProfile_{name}, TemplateProfileActive.
    /// </summary>
    public string AutomationId { get; init; } = "";

    /// <summary>What a screen reader says. The label unless it's set.</summary>
    public string AccessibleName { get; init; }

    public event EventHandler? Changed;

    private bool _isChosen;
    public bool IsChosen
    {
        get => _isChosen;
        set { if (Set(ref _isChosen, value)) Changed?.Invoke(this, EventArgs.Empty); }
    }
}
