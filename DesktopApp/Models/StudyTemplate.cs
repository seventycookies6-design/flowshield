using System.Text.Json.Serialization;

namespace FlowShield.Models;

/// <summary>
/// A named way to run a sprint (launch checklist F6): its length, shield,
/// cycle, break and blocklist, picked in one click on Today or started by a
/// schedule.
///
/// A preset, not a rule: choosing one fills in Today's controls, and each can
/// still be changed before Start. <see cref="ProfileId"/> empty (or naming a
/// profile that no longer exists) means "whichever profile is active",
/// resolved by <see cref="AppSettings.ProfileFor"/>.
/// </summary>
public class StudyTemplate
{
    public const int MaxNameLength = 40;

    /// <summary>Same bounds as Today's custom sprint length.</summary>
    public const int MinSprintMinutes = 5;
    public const int MaxSprintMinutes = 240;

    public const string UntitledName = "Untitled template";

    public string Id { get; set; } = NewId();
    public string Name { get; set; } = "";
    public int SprintMinutes { get; set; } = 25;
    public ShieldLevel Shield { get; set; } = ShieldLevel.Firm;

    /// <summary>One of <see cref="CycleState.CycleChoices"/>; 0 means a single sprint.</summary>
    public int CycleSprints { get; set; }

    /// <summary>The breaks inside this template's cycle. Hand-started sprints keep the global settings.</summary>
    public int BreakMinutes { get; set; } = CycleState.DefaultShortBreakMinutes;

    public string ProfileId { get; set; } = "";

    /// <summary>"homework", "exam" or "light" for a built-in, so Restore can find what's missing; empty for the user's own.</summary>
    public string BuiltInKey { get; set; } = "";

    [JsonIgnore]
    public bool IsBuiltIn => BuiltInKey.Length > 0;

    public static string NewId() => Guid.NewGuid().ToString("N");

    /// <summary>
    /// The three the checklist ships, as fresh instances with new ids on every
    /// call, so seeding or restoring can never share an object between lists.
    /// </summary>
    public static IReadOnlyList<StudyTemplate> BuiltIns() => new[]
    {
        new StudyTemplate
        {
            Name = "Homework evening", SprintMinutes = 45, Shield = ShieldLevel.Firm,
            CycleSprints = 3, BreakMinutes = 10, BuiltInKey = "homework",
        },
        new StudyTemplate
        {
            Name = "Exam prep", SprintMinutes = 90, Shield = ShieldLevel.Sealed,
            CycleSprints = 0, BreakMinutes = CycleState.DefaultShortBreakMinutes, BuiltInKey = "exam",
        },
        new StudyTemplate
        {
            Name = "Light study", SprintMinutes = 25, Shield = ShieldLevel.Soft,
            CycleSprints = 0, BreakMinutes = 5, BuiltInKey = "light",
        },
    };

    /// <summary>
    /// Brings every field into range: a hand-edited or older settings file can
    /// hold anything. Returns true if anything changed.
    /// </summary>
    public bool Normalize()
    {
        var before = (Id, Name, SprintMinutes, Shield, CycleSprints, BreakMinutes, ProfileId, BuiltInKey);

        if (string.IsNullOrWhiteSpace(Id)) Id = NewId();

        var name = (Name ?? "").Trim();
        if (name.Length == 0) name = UntitledName;
        if (name.Length > MaxNameLength) name = name[..MaxNameLength].TrimEnd();
        Name = name;

        SprintMinutes = Math.Clamp(SprintMinutes, MinSprintMinutes, MaxSprintMinutes);
        if (!Enum.IsDefined(Shield)) Shield = ShieldLevel.Firm;
        if (!CycleState.CycleChoices.Contains(CycleSprints)) CycleSprints = 0;
        BreakMinutes = Math.Clamp(BreakMinutes, CycleState.MinBreakMinutes, CycleState.MaxBreakMinutes);
        ProfileId ??= "";
        BuiltInKey ??= "";

        return before != (Id, Name, SprintMinutes, Shield, CycleSprints, BreakMinutes, ProfileId, BuiltInKey);
    }
}
