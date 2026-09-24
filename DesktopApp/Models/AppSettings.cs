using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json.Serialization;

namespace FlowShield.Models;

/// <summary>How hard FlowShield pushes back when a blocked app appears.</summary>
public enum ShieldLevel
{
    /// <summary>Full-screen notice on its own screen; the blocked app keeps running unless you choose to close it.</summary>
    Soft = 1,

    /// <summary>Blocked apps are closed on sight. Blocklist stays editable.</summary>
    Firm = 2,

    /// <summary>Closed on sight and the blocklist locks for the sprint.</summary>
    Sealed = 3,
}

/// <summary>
/// One entry on the blocklist.
///
/// Implements INotifyPropertyChanged because the counts change while the list
/// is on screen — without it the "blocked N ×" label renders once and then lies
/// for the rest of the session.
/// </summary>
public class BlockedApp : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;

    private void Raise([CallerMemberName] string? name = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

    public string Name { get; set; } = "";

    /// <summary>Process name without extension, e.g. "slack". Matched case-insensitively.</summary>
    public string ProcessName { get; set; } = "";

    /// <summary>
    /// The app's other processes, e.g. steamwebhelper for Steam (F8). Without
    /// them, blocking Steam left its helper running. Empty in older settings files.
    /// </summary>
    public List<string> ExtraProcessNames { get; set; } = new();

    /// <summary>Where the icon came from, if known. Display only.</summary>
    public string? IconPath { get; set; }

    /// <summary>Every process name this entry blocks.</summary>
    [JsonIgnore]
    public IEnumerable<string> AllProcessNames =>
        new[] { ProcessName }.Concat(ExtraProcessNames)
            .Where(n => !string.IsNullOrWhiteSpace(n))
            .Select(n => n.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase);

    [JsonIgnore]
    public string ProcessSummary => string.Join(", ", AllProcessNames.Select(n => n + ".exe"));

    /// <summary>The suggestion catalog's category ("Chat", "Music" …) for
    /// this row's process, if it's a known app; null for a custom entry
    /// (UI-SPEC.md A3 category tag chip, graft from the raycast sketch).</summary>
    [JsonIgnore]
    public string? Category => AppPicker.CategoryFor(ProcessName);

    [JsonIgnore]
    public bool HasCategory => !string.IsNullOrEmpty(Category);

    private bool _isEnabled = true;
    public bool IsEnabled
    {
        get => _isEnabled;
        set { if (_isEnabled != value) { _isEnabled = value; Raise(); } }
    }

    private int _blockCount;
    /// <summary>Times this app was closed by the shield. Feeds the Today view.</summary>
    public int BlockCount
    {
        get => _blockCount;
        set { if (_blockCount != value) { _blockCount = value; Raise(); } }
    }

    public DateTime AddedUtc { get; set; } = DateTime.UtcNow;

    [JsonIgnore]
    public string DisplayName => string.IsNullOrWhiteSpace(Name) ? ProcessName : Name;

    /// <summary>
    /// A separate entry with the same target, used when a blocklist profile is
    /// duplicated (F9). The counts start again: they describe what happened on
    /// the profile they were counted on.
    /// </summary>
    public BlockedApp Copy() => new()
    {
        Name = Name,
        ProcessName = ProcessName,
        ExtraProcessNames = new List<string>(ExtraProcessNames),
        IconPath = IconPath,
        IsEnabled = IsEnabled,
        AddedUtc = AddedUtc,
    };
}

/// <summary>A completed or abandoned focus sprint.</summary>
public class FocusSession
{
    public DateTime StartedUtc { get; set; }
    public DateTime? EndedUtc { get; set; }
    public int PlannedMinutes { get; set; }
    public ShieldLevel Shield { get; set; } = ShieldLevel.Firm;
    public bool Completed { get; set; }
    public int BlocksEnforced { get; set; }

    /// <summary>Blocked apps the shield closed during the sprint (the firm side of BlocksEnforced).</summary>
    public int AppsClosed { get; set; }

    /// <summary>Nudges the shield sent during the sprint (the soft side of BlocksEnforced).</summary>
    public int NudgesSent { get; set; }

    /// <summary>
    /// Times the Soft notice was answered with Close or Back to work (1.0.10).
    /// A count only: which app is never recorded.
    /// </summary>
    public int TurnedBack { get; set; }

    /// <summary>Momentum when the sprint started, so the summary can show what changed.</summary>
    public double MomentumAtStart { get; set; }

    /// <summary>Optional one-line intention set before the sprint (F13). Empty when skipped.</summary>
    public string Intention { get; set; } = "";

    /// <summary>The one-line "what moved?" answer captured when a sprint ends.</summary>
    public string Journal { get; set; } = "";

    /// <summary>
    /// FlowShield was closed for most of this sprint (a crash, a reboot, or
    /// quitting from Task Manager), so it was neither finished nor given up.
    /// Interrupted sprints don't change momentum.
    /// </summary>
    public bool Interrupted { get; set; }

    /// <summary>Ended by the user before its time was up (after the grace period).</summary>
    [JsonIgnore]
    public bool EndedEarly => EndedUtc.HasValue && !Completed && !Interrupted;

    [JsonIgnore]
    public double ActualMinutes =>
        EndedUtc.HasValue ? Math.Round((EndedUtc.Value - StartedUtc).TotalMinutes, 1) : 0;
}

/// <summary>
/// The sprint that is running right now, saved the moment it starts.
///
/// A sprint used to live only in memory, so a crash, a reboot or ending
/// FlowShield from Task Manager quietly ended it, which made even a Sealed
/// sprint trivially escapable. On the next launch this is read back and the
/// sprint resumes with its shield (and a Sealed blocklist lock) intact.
/// </summary>
public class RunningSprint
{
    public DateTime StartedUtc { get; set; }
    public int PlannedMinutes { get; set; }
    public ShieldLevel Shield { get; set; } = ShieldLevel.Firm;

    /// <summary>Momentum when the sprint started, restored if the sprint resumes (F12).</summary>
    public double MomentumAtStart { get; set; }

    /// <summary>The sprint's intention, kept so a resumed sprint can still show it (F13).</summary>
    public string Intention { get; set; } = "";

    /// <summary>
    /// The blocklist profile this sprint is enforcing (F9). Empty in settings
    /// files written before profiles existed, and empty is safe: resolution
    /// falls back to the stored active profile.
    ///
    /// Recorded per sprint so the templates F6 will add can pick a profile
    /// without changing what a running sprint is enforcing.
    /// </summary>
    public string ActiveProfileId { get; set; } = "";

    /// <summary>The cycle this sprint belongs to, so "Sprint 2 of 3" survives a restart (F5).</summary>
    public int CycleSprintsPlanned { get; set; }

    /// <summary>Sprints of that cycle already finished when this one started (F5).</summary>
    public int CycleSprintsDone { get; set; }

    /// <summary>
    /// The break length of the template this cycle was started from (F6), or
    /// null for a hand-started sprint, which uses the global break settings.
    /// Saved with the sprint so a restart mid-cycle keeps the template's breaks.
    /// </summary>
    public int? TemplateBreakMinutes { get; set; }

    /// <summary>Last time FlowShield confirmed it was still running this sprint.</summary>
    public DateTime LastSeenUtc { get; set; }

    /// <summary>
    /// Minutes FlowShield has actually been running this sprint, accumulated
    /// across restarts.
    ///
    /// Kept as a running total rather than inferred from
    /// <see cref="LastSeenUtc"/> minus <see cref="StartedUtc"/>, because
    /// resuming refreshes LastSeenUtc — so that subtraction counted every
    /// minute FlowShield was *closed* before the resume as watched, and
    /// reopening the app for a second near the end turned any abandoned sprint
    /// into a completed one.
    ///
    /// Null in settings files written before this existed; <see cref="Decide"/>
    /// falls back to the old estimate for those.
    /// </summary>
    public double? WatchedMinutes { get; set; }

    [JsonIgnore]
    public DateTime EndsUtc => StartedUtc.AddMinutes(PlannedMinutes);

    /// <summary>
    /// Records another stretch of FlowShield watching this sprint, and moves
    /// <see cref="LastSeenUtc"/> up to <paramref name="nowUtc"/>.
    ///
    /// The stretch is capped: if the heartbeat did not fire for an hour the
    /// machine was suspended, not watching, and the uncapped gap would credit
    /// the sprint with time nothing was enforced for.
    /// </summary>
    public void NoteStillWatching(DateTime nowUtc, TimeSpan cap)
    {
        var stretch = nowUtc - LastSeenUtc;
        if (stretch > TimeSpan.Zero)
            WatchedMinutes = (WatchedMinutes ?? 0) + Min(stretch, cap).TotalMinutes;
        LastSeenUtc = nowUtc;
    }

    /// <summary>
    /// Minutes FlowShield has watched this sprint, as every judgement of it
    /// should read them. Falls back to the old LastSeenUtc estimate for a
    /// sprint saved before <see cref="WatchedMinutes"/> existed, and is clamped
    /// to 0..PlannedMinutes so a hand-edited or damaged file can't produce a
    /// sprint that ended before it started or watched longer than it ran.
    /// </summary>
    [JsonIgnore]
    public double WatchedSoFar => Math.Clamp(
        WatchedMinutes ?? (Min(LastSeenUtc, EndsUtc) - StartedUtc).TotalMinutes,
        0, Math.Max(PlannedMinutes, 0));

    /// <summary>What to do with this sprint when FlowShield starts again.</summary>
    public SprintResume Decide(DateTime nowUtc)
    {
        if (PlannedMinutes <= 0) return SprintResume.Discard;
        if (nowUtc < EndsUtc) return SprintResume.Resume;

        // The time ran out while FlowShield was closed. It counts as finished
        // only if FlowShield was watching for at least half of it; otherwise
        // nothing was actually enforced, so it's recorded as interrupted.
        var watched = WatchedSoFar;
        return watched >= PlannedMinutes * CompletedIfWatchedFraction
            ? SprintResume.RecordCompleted
            : SprintResume.RecordInterrupted;
    }

    /// <summary>Share of a sprint FlowShield must have been running for it to count as finished.</summary>
    public const double CompletedIfWatchedFraction = 0.5;

    /// <summary>
    /// When a sprint that has just ended is recorded as ending, which is all
    /// <see cref="FocusSession.ActualMinutes"/> — the summary card, the minutes
    /// goal, History, the heatmap and the journal export — measures.
    ///
    /// An interrupted sprint ends where FlowShield stopped watching it (#203).
    /// Any other end is now, but never after the planned end: a
    /// DispatcherTimer doesn't tick while the PC sleeps, so the tick that
    /// finishes a sprint can come hours late, and the nap would count as focus
    /// (#300). The cap doesn't ask whether the sprint finished, because an End
    /// click can still be handled after waking before that first tick (the
    /// tick runs at Normal priority since #319, but input already queued can
    /// come first): it ends the sprint early with now hours past the planned
    /// end too. The caller still records that as ended early, momentum
    /// and all; only the minutes are capped. A real early end is before the
    /// planned end, so now is already right. Sessions saved before #300 keep
    /// the end they were saved with.
    /// </summary>
    public static DateTime RecordedEnd(DateTime startedUtc, DateTime plannedEndUtc,
                                       double watchedMinutes, DateTime nowUtc,
                                       bool completed, bool interrupted)
    {
        if (interrupted) return startedUtc + TimeSpan.FromMinutes(watchedMinutes);
        return nowUtc > plannedEndUtc ? plannedEndUtc : nowUtc;
    }

    private static DateTime Min(DateTime a, DateTime b) => a < b ? a : b;

    private static TimeSpan Min(TimeSpan a, TimeSpan b) => a < b ? a : b;
}

public enum SprintResume
{
    /// <summary>Time is left: carry on with the same shield and lock.</summary>
    Resume,
    /// <summary>Ended while closed, but FlowShield ran for most of it.</summary>
    RecordCompleted,
    /// <summary>Ended while closed, and FlowShield wasn't running for most of it.</summary>
    RecordInterrupted,
    /// <summary>Unreadable record; drop it.</summary>
    Discard,
}

public class AppSettings
{
    // ---- blocking -------------------------------------------------------

    private List<BlockedApp>? _legacyBlockedApps;

    /// <summary>
    /// The active profile's blocklist (F9).
    ///
    /// Kept under its old name, and still written to the settings file, for two
    /// reasons: a file this build writes still loads in an older one, and a file
    /// written before profiles existed has somewhere to land — the setter keeps
    /// that list aside and <see cref="EnsureProfiles"/> makes it the Default
    /// profile.
    /// </summary>
    public List<BlockedApp> BlockedApps
    {
        get => ActiveProfile.Apps;
        set => _legacyBlockedApps = value;
    }

    /// <summary>Every blocklist profile (F9). There is always at least one.</summary>
    public List<BlocklistProfile> Profiles { get; set; } = new();

    /// <summary>
    /// The profile enforcement and the Blocked Apps page use. Resolved through
    /// <see cref="ActiveProfile"/>, which tolerates an id that no longer exists.
    /// </summary>
    public string ActiveProfileId { get; set; } = "";

    /// <summary>The name the first profile is given when one is migrated or seeded.</summary>
    public const string DefaultProfileName = "Default";

    /// <summary>
    /// Profiles worth having, offered on the Blocked Apps page. Offered only:
    /// nothing creates them, so a customer who wants one list keeps one list.
    /// </summary>
    public static readonly string[] SuggestedProfileNames = { "School", "Gaming break", "Everything" };

    /// <summary>The longest a profile name may be, so a switcher chip stays a chip.</summary>
    public const int MaxProfileNameLength = 40;

    /// <summary>
    /// The profile a sprint would enforce right now.
    ///
    /// Forgiving on purpose. <see cref="ActiveProfileId"/> can name a profile
    /// that has since been deleted (by this build, or by another one sharing the
    /// settings file), and the blocker's timer thread reads this — so it falls
    /// back to the first profile, and seeds one if there are somehow none, rather
    /// than throwing where nothing can catch it.
    /// </summary>
    [JsonIgnore]
    public BlocklistProfile ActiveProfile
    {
        get
        {
            var named = FindProfile(ActiveProfileId);
            if (named is not null) return named;
            if (Profiles.Count > 0) return Profiles[0];

            var seeded = new BlocklistProfile
            {
                Name = DefaultProfileName,
                Apps = _legacyBlockedApps ?? new List<BlockedApp>(),
            };
            Profiles.Add(seeded);
            ActiveProfileId = seeded.Id;
            return seeded;
        }
    }

    /// <summary>The profile with this id, or null. An empty id never matches.</summary>
    public BlocklistProfile? FindProfile(string? id) =>
        string.IsNullOrEmpty(id)
            ? null
            : Profiles.FirstOrDefault(p => string.Equals(p.Id, id, StringComparison.Ordinal));

    /// <summary>
    /// Brings a settings file up to date with profiles, and repairs a broken
    /// one. Returns true if anything changed, so the caller knows to save.
    ///
    /// Run once at startup: the blocklist that used to be the only one becomes
    /// the Default profile, keeping its apps, their counts and their switches.
    /// </summary>
    public bool EnsureProfiles()
    {
        var changed = false;

        if (Profiles.Count == 0)
        {
            Profiles.Add(new BlocklistProfile
            {
                Name = DefaultProfileName,
                Apps = _legacyBlockedApps ?? new List<BlockedApp>(),
            });
            changed = true;
        }

        foreach (var profile in Profiles)
        {
            if (!string.IsNullOrEmpty(profile.Id)) continue;
            profile.Id = BlocklistProfile.NewId();
            changed = true;
        }

        // An active id pointing at nothing would otherwise be resolved on every
        // read; settle it once instead, so what is stored says what is used.
        if (FindProfile(ActiveProfileId) is null)
        {
            ActiveProfileId = Profiles[0].Id;
            changed = true;
        }

        return changed;
    }

    /// <summary>Adds a profile, optionally starting from a copy of another list.</summary>
    public BlocklistProfile AddProfile(string? name, IEnumerable<BlockedApp>? startFrom = null)
    {
        var profile = new BlocklistProfile
        {
            Name = UniqueProfileName(CleanProfileName(name)),
            Apps = startFrom?.Select(a => a.Copy()).ToList() ?? new List<BlockedApp>(),
        };
        Profiles.Add(profile);
        return profile;
    }

    /// <summary>Copies a profile, apps and all. Null if the id is unknown.</summary>
    public BlocklistProfile? DuplicateProfile(string? id)
    {
        var source = FindProfile(id);
        if (source is null) return null;

        var copy = source.Copy(UniqueProfileName($"{source.Name} copy"));
        Profiles.Add(copy);
        return copy;
    }

    /// <summary>Renames a profile. False if the id is unknown.</summary>
    public bool RenameProfile(string? id, string? name)
    {
        var profile = FindProfile(id);
        if (profile is null) return false;

        var wanted = CleanProfileName(name);
        if (wanted == profile.Name) return false;

        profile.Name = UniqueProfileName(wanted, except: profile);
        return true;
    }

    /// <summary>
    /// Deletes a profile.
    ///
    /// Never the last one: there is always at least one blocklist, because the
    /// app with none has nowhere to put what it blocks and nothing to show on
    /// Today. Deleting the active profile moves the active id to what is left.
    /// </summary>
    public bool RemoveProfile(string? id)
    {
        if (Profiles.Count <= 1) return false;

        var profile = FindProfile(id);
        if (profile is null) return false;

        var wasActive = string.Equals(profile.Id, ActiveProfileId, StringComparison.Ordinal);
        Profiles.Remove(profile);
        if (wasActive) ActiveProfileId = Profiles[0].Id;
        return true;
    }

    /// <summary>Switches the active profile. False if the id is unknown or already active.</summary>
    public bool SetActiveProfile(string? id)
    {
        var profile = FindProfile(id);
        if (profile is null) return false;
        if (string.Equals(ActiveProfileId, profile.Id, StringComparison.Ordinal)) return false;

        ActiveProfileId = profile.Id;
        return true;
    }

    /// <summary>Trimmed, length-capped, never empty.</summary>
    public static string CleanProfileName(string? name)
    {
        var trimmed = (name ?? "").Trim();
        if (trimmed.Length == 0) return DefaultProfileName;
        return trimmed.Length <= MaxProfileNameLength
            ? trimmed
            : trimmed[..MaxProfileNameLength].TrimEnd();
    }

    /// <summary>
    /// The wanted name, or that name with a number after it. Two profiles called
    /// "School" would be indistinguishable on the switcher.
    /// </summary>
    public string UniqueProfileName(string wanted, BlocklistProfile? except = null)
    {
        bool Taken(string name) => Profiles.Any(p =>
            !ReferenceEquals(p, except) && string.Equals(p.Name, name, StringComparison.CurrentCultureIgnoreCase));

        if (!Taken(wanted)) return wanted;
        for (var n = 2; n < 100; n++)
        {
            var candidate = $"{wanted} {n}";
            if (!Taken(candidate)) return candidate;
        }
        return wanted;
    }

    // ---- study templates and schedules (F6) -----------------------------

    /// <summary>Named ways to run a sprint. Seeded with the three built-ins once.</summary>
    public List<StudyTemplate> Templates { get; set; } = new();

    /// <summary>When templates start by themselves.</summary>
    public List<SprintSchedule> Schedules { get; set; } = new();

    /// <summary>
    /// Set once the built-ins have been added, so someone who deletes every
    /// template doesn't find them back on the next launch.
    /// </summary>
    public bool TemplatesSeeded { get; set; }

    /// <summary>The template with this id, or null. An empty id never matches.</summary>
    public StudyTemplate? FindTemplate(string? id) =>
        string.IsNullOrEmpty(id)
            ? null
            : Templates.FirstOrDefault(t => string.Equals(t.Id, id, StringComparison.Ordinal));

    /// <summary>
    /// Seeds the built-ins on first run, repairs anything out of range, and
    /// drops schedules whose template no longer exists. Run once at startup,
    /// after <see cref="EnsureProfiles"/>. True if anything changed.
    /// </summary>
    public bool EnsureTemplates()
    {
        var changed = false;

        // A hand-edited file can hold null for either list, or a null entry
        // in one; like Normalize, repairing that counts as a change.
        if (Templates is null) { Templates = new List<StudyTemplate>(); changed = true; }
        if (Schedules is null) { Schedules = new List<SprintSchedule>(); changed = true; }
        changed |= Templates.RemoveAll(t => t is null) > 0;
        changed |= Schedules.RemoveAll(s => s is null) > 0;

        foreach (var template in Templates) changed |= template.Normalize();
        foreach (var schedule in Schedules) changed |= schedule.Normalize();

        if (!TemplatesSeeded)
        {
            // Through Restore, which adds only what is missing, so a file that
            // already holds a built-in without the mark doesn't get a second copy.
            RestoreBuiltInTemplates();
            TemplatesSeeded = true;
            changed = true;
        }

        // The page and its AutomationIds go by name, so no two may share one.
        // The earlier template keeps its name, as the earlier profile would.
        var seen = new HashSet<string>(StringComparer.CurrentCultureIgnoreCase);
        foreach (var template in Templates)
        {
            if (seen.Add(template.Name)) continue;
            template.Name = UniqueTemplateName(template.Name, except: template);
            seen.Add(template.Name);
            changed = true;
        }

        changed |= Schedules.RemoveAll(s => FindTemplate(s.TemplateId) is null) > 0;
        return changed;
    }

    /// <summary>
    /// The wanted name, or that name with a number after it, kept inside
    /// <see cref="StudyTemplate.MaxNameLength"/> so a later Normalize can't cut
    /// the number off again. The template counterpart of <see cref="UniqueProfileName"/>.
    /// </summary>
    public string UniqueTemplateName(string wanted, StudyTemplate? except = null)
    {
        bool Taken(string name) => Templates.Any(t =>
            !ReferenceEquals(t, except) && string.Equals(t.Name, name, StringComparison.CurrentCultureIgnoreCase));

        if (!Taken(wanted)) return wanted;
        for (var n = 2; n < 100; n++)
        {
            var suffix = $" {n}";
            var candidate = StudyTemplate.Cut(wanted, StudyTemplate.MaxNameLength - suffix.Length) + suffix;
            if (!Taken(candidate)) return candidate;
        }
        return wanted;
    }

    /// <summary>
    /// Re-adds any built-in that is missing; never touches the user's own. A
    /// built-in whose name the user has since taken comes back with a number,
    /// as in <see cref="EnsureTemplates"/>. Returns how many came back.
    /// </summary>
    public int RestoreBuiltInTemplates()
    {
        var have = Templates.Select(t => t.BuiltInKey).ToHashSet(StringComparer.Ordinal);
        var missing = StudyTemplate.BuiltIns().Where(b => !have.Contains(b.BuiltInKey)).ToList();
        foreach (var template in missing)
        {
            template.Name = UniqueTemplateName(template.Name);
            Templates.Add(template);
        }
        return missing.Count;
    }

    /// <summary>The schedules that start this template, so deleting it can name them first.</summary>
    public IReadOnlyList<SprintSchedule> SchedulesUsing(string templateId) =>
        Schedules.Where(s => string.Equals(s.TemplateId, templateId, StringComparison.Ordinal)).ToList();

    /// <summary>Deletes a template and every schedule that starts it. Returns how many schedules went with it.</summary>
    public int DeleteTemplate(string id)
    {
        var template = FindTemplate(id);
        if (template is null) return 0;
        Templates.Remove(template);
        return Schedules.RemoveAll(s => string.Equals(s.TemplateId, id, StringComparison.Ordinal));
    }

    /// <summary>The blocklist a template runs with: its own profile, or the active one if it has none or it was deleted.</summary>
    public BlocklistProfile ProfileFor(StudyTemplate template) =>
        FindProfile(template.ProfileId) ?? ActiveProfile;

    // ---- sleep blocking -------------------------------------------------

    public bool IsSleepBlockEnabled { get; set; }
    public TimeSpan SleepBlockStartTime { get; set; } = new(22, 0, 0);
    public TimeSpan SleepBlockEndTime { get; set; } = new(6, 0, 0);

    // ---- preferences ----------------------------------------------------
    public bool StartWithWindows { get; set; }
    public bool HardKillModeEnabled { get; set; }
    public bool MinimizeToTrayOnClose { get; set; } = true;

    /// <summary>
    /// Off by default (F4, roadmap 3.9). When on, Ctrl+Alt+F starts the last
    /// sprint from anywhere, registered with <c>RegisterHotKey</c> — no admin
    /// rights, no global keyboard hook. Turned back off automatically if the
    /// combination is already taken by another app.
    /// </summary>
    public bool GlobalHotkeyEnabled { get; set; }

    /// <summary>
    /// The Soft shield's full-screen notice (F7, roadmap 1.7). On by default:
    /// without it Soft's only sign of life is a toast inside a window that is
    /// usually behind the distraction. Stored locally like everything else here.
    /// </summary>
    public bool ShowSoftOverlayEnabled { get; set; } = true;

    /// <summary>
    /// Which colour theme the app draws in (F21, DESIGN_SYSTEM.md §12).
    /// <see cref="AppTheme.System"/> by default: FlowShield then follows
    /// Windows' own app theme and changes with it, without a restart. Stored
    /// here like every other preference — it never leaves the PC.
    /// </summary>
    public AppTheme Theme { get; set; } = AppTheme.System;

    /// <summary>The first-run welcome (F18) has been shown, finished or skipped.</summary>
    public bool FirstRunCompleted { get; set; }

    // ---- terms ----------------------------------------------------------

    /// <summary>
    /// The version of the terms this user accepted, or empty. See
    /// <see cref="LegalTerms"/>: the record is what makes the agreement mean
    /// something later.
    /// </summary>
    public string TermsAcceptedVersion { get; set; } = "";

    /// <summary>When they accepted, in UTC.</summary>
    public DateTime? TermsAcceptedUtc { get; set; }

    // ---- notifications (F19) --------------------------------------------

    /// <summary>The master switch. Off means FlowShield never notifies.</summary>
    public bool NotificationsEnabled { get; set; } = true;

    /// <summary>Which notifications are on. Anything missing counts as on.</summary>
    public Dictionary<string, bool> NotificationKinds { get; set; } = new();

    /// <summary>The day the "trial ends tomorrow" notice was shown, so it only happens once.</summary>
    public DateTime? TrialEndingNotifiedLocal { get; set; }

    /// <summary>
    /// When the scheduler last looked (F6), stamped on every tick and kept by
    /// whatever save follows. The next launch counts from it, so a start
    /// missed while FlowShield was closed is offered, never started. Not user
    /// data: it is not part of the Your data export. Null before the first
    /// run of a build that has it.
    /// </summary>
    public DateTime? ScheduleLastCheckUtc { get; set; }

    public bool IsNotificationOn(NotificationKind kind) =>
        NotificationsEnabled && (!NotificationKinds.TryGetValue(kind.ToString(), out var on) || on);

    public void SetNotification(NotificationKind kind, bool on) =>
        NotificationKinds[kind.ToString()] = on;

    // ---- licensing ------------------------------------------------------
    public string LicenseKey { get; set; } = "";
    public string LicenseEmail { get; set; } = "";

    /// <summary>
    /// True once a licence has been activated: FlowShield was bought. The name
    /// predates the one-time purchase (it meant "Pro subscriber") and is kept so
    /// existing settings files still load.
    /// </summary>
    public bool IsPro { get; set; }

    /// <summary>When the free trial began: the first launch of a build that has one.</summary>
    public DateTime? TrialStartedUtc { get; set; }
    /// <summary>
    /// Where licence validation goes. Points at the deployed service so a
    /// shipped build works without configuration; override it in Settings, or
    /// with --server= on the command line, to test against a local server.
    /// </summary>
    public string LicenseServerUrl { get; set; } = "https://flowshield-license-server.onrender.com";

    public string WebsiteUrl { get; set; } = "https://seventycookies6-design.github.io/flowshield";
    public DateTime? LicenseCheckedUtc { get; set; }
    public string LicenseStatus { get; set; } = "";

    /// <summary>Seats in use and allowed, as last reported by the server.</summary>
    public int DeviceCount { get; set; }

    public int DeviceLimit { get; set; }

    // ---- sessions & momentum -------------------------------------------
    public int DefaultSprintMinutes { get; set; } = 25;
    public int LastCustomSprintMinutes { get; set; } = 30;
    public ShieldLevel DefaultShield { get; set; } = ShieldLevel.Firm;
    public List<FocusSession> Sessions { get; set; } = new();

    /// <summary>The sprint in progress, or null. See <see cref="RunningSprint"/>.</summary>
    public RunningSprint? ActiveSprint { get; set; }

    // ---- breaks and cycles (F5) -----------------------------------------

    /// <summary>The break in progress, or null. See <see cref="RunningBreak"/>.</summary>
    public RunningBreak? ActiveBreak { get; set; }

    /// <summary>The usual break after a completed sprint.</summary>
    public int ShortBreakMinutes { get; set; } = CycleState.DefaultShortBreakMinutes;

    /// <summary>The longer break after every fourth completed sprint in a row.</summary>
    public int LongBreakMinutes { get; set; } = CycleState.DefaultLongBreakMinutes;

    /// <summary>
    /// Completed sprints in a row, which is what earns the long break. Reset by
    /// a sprint ended early or interrupted. Nothing else reads it — it is not
    /// the streak, and it never touches momentum or the daily goal.
    /// </summary>
    public int CompletedSprintsInARow { get; set; }

    /// <summary>The cycle chooser's last value on Today: 0 for no cycle.</summary>
    public int CycleSprints { get; set; }

    /// <summary>
    /// Compounding score: completed sprints add, abandoned ones decay it.
    /// Persisted rather than recomputed so decay is monotonic over time.
    /// </summary>
    public double MomentumScore { get; set; }

    public int CurrentStreak { get; set; }
    public DateTime? LastSessionDayLocal { get; set; }

    // ---- daily goal (F15) -----------------------------------------------

    /// <summary>What the daily goal is measured in, or None for no goal.</summary>
    public DailyGoalKind DailyGoalKind { get; set; } = DailyGoalKind.None;

    /// <summary>Minutes or sprints wanted per day. Meaningless when the kind is None.</summary>
    public int DailyGoalTarget { get; set; }

    /// <summary>
    /// The last day the streak was brought up to date. Without it a missed day
    /// is never noticed, because nothing runs on a day you don't focus.
    /// </summary>
    public DateTime? StreakSettledDayLocal { get; set; }

    /// <summary>The last day the goal was met, so the streak ticks once, not per sprint.</summary>
    public DateTime? GoalMetDayLocal { get; set; }

    /// <summary>Planned days off. See <see cref="DailyGoal.SkipsPerWeek"/>.</summary>
    public List<DateTime> SkipDatesLocal { get; set; } = new();

    /// <summary>
    /// Enforcement actions taken today, with the day they belong to.
    ///
    /// Stored rather than derived: the Today view previously summed every
    /// app's lifetime BlockCount and displayed it under a "TODAY" heading,
    /// which was simply the wrong number.
    /// </summary>
    public int BlocksToday { get; set; }

    public DateTime? BlocksTodayDateLocal { get; set; }

    /// <summary>Adds one of today's blocks, rolling the counter over at midnight.</summary>
    public void RecordBlock(DateTime? nowLocal = null)
    {
        var today = (nowLocal ?? DateTime.Now).Date;
        if (BlocksTodayDateLocal?.Date != today)
        {
            BlocksTodayDateLocal = today;
            BlocksToday = 0;
        }
        BlocksToday++;
    }

    /// <summary>Today's block count, or zero if the stored tally is stale.</summary>
    [JsonIgnore]
    public int BlocksTodayCurrent =>
        BlocksTodayDateLocal?.Date == DateTime.Now.Date ? BlocksToday : 0;

    // ---- trial & access -------------------------------------------------

    /// <summary>
    /// Length of the free trial. Everything is unlocked during it; afterwards the
    /// app is locked until FlowShield is bought. There is no free tier.
    /// </summary>
    public const int TrialDays = 7;

    /// <summary>Starts the trial clock on first launch. Returns true if it was just started.</summary>
    public bool EnsureTrialStarted(DateTime? nowUtc = null)
    {
        if (TrialStartedUtc is not null) return false;
        TrialStartedUtc = nowUtc ?? DateTime.UtcNow;
        return true;
    }

    [JsonIgnore]
    public DateTime? TrialEndsUtc => TrialStartedUtc?.AddDays(TrialDays);

    /// <summary>
    /// Whether the trial is running at <paramref name="nowUtc"/>.
    ///
    /// A clock more than a day behind the recorded start counts as ended:
    /// winding the clock back is the obvious way to stretch a trial, and a
    /// genuinely wrong clock is fixed by correcting it.
    /// </summary>
    public bool IsTrialActiveAt(DateTime nowUtc) =>
        TrialStartedUtc is { } start
        && nowUtc >= start.AddDays(-1)
        && nowUtc < start.AddDays(TrialDays);

    /// <summary>Whole days of trial left, rounded up, so the last day reads "1 day left".</summary>
    public int TrialDaysLeftAt(DateTime nowUtc) =>
        !IsTrialActiveAt(nowUtc) || TrialEndsUtc is not { } end
            ? 0
            : Math.Clamp((int)Math.Ceiling((end - nowUtc).TotalDays), 1, TrialDays);

    /// <summary>Every feature is available: bought, or inside the free trial.</summary>
    public bool HasAccessAt(DateTime nowUtc) => IsPro || IsTrialActiveAt(nowUtc);

    /// <summary>Deep-copy used by the settings service to snapshot before writes.</summary>
    public AppSettings Clone()
    {
        var json = System.Text.Json.JsonSerializer.Serialize(this);
        return System.Text.Json.JsonSerializer.Deserialize<AppSettings>(json) ?? new AppSettings();
    }
}
