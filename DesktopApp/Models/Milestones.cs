namespace FlowShield.Models;

/// <summary>
/// The four quiet milestones (launch checklist F14, roadmap 3.2): the first
/// Sealed sprint, ten hours focused, a seven-day streak, and momentum 100.
/// </summary>
public enum MilestoneKind
{
    FirstSealed,
    TenHours,
    SevenDayStreak,
    MomentumHundred,
}

/// <summary>One milestone the person has earned, as settings.json keeps it.</summary>
public class MilestoneRecord
{
    /// <summary>The <see cref="MilestoneKind"/> name. A name rather than a number, so the file reads plainly and survives a reorder.</summary>
    public string Id { get; set; } = "";

    public DateTime EarnedUtc { get; set; }

    /// <summary>False until its card has been on Today once. A milestone is shown once, then only listed.</summary>
    public bool Shown { get; set; }
}

/// <summary>
/// Which milestones have been earned, and which of them still owe a card.
///
/// Milestones are recorded, not replayed, because each one has to be shown
/// once and then stay on History: a rule checked afresh every time would
/// either repeat the card or forget the milestone once the streak broke.
/// Everything that decides whether one is reached reads
/// <see cref="AppSettings.Sessions"/> or the score the app already keeps, so
/// nothing new is measured.
///
/// Kept free of UI so each rule can be tested on its own.
/// </summary>
public static class Milestones
{
    /// <summary>Focused time that earns "ten hours focused", in minutes.</summary>
    public const double TenHoursMinutes = 600;

    /// <summary>Days in a row that earn the streak milestone.</summary>
    public const int StreakDays = 7;

    /// <summary>The momentum score that earns its milestone.</summary>
    public const double MomentumTarget = 100;

    /// <summary>Every milestone, in the order History lists them as a fallback.</summary>
    public static IReadOnlyList<MilestoneKind> All { get; } = Enum.GetValues<MilestoneKind>();

    /// <summary>
    /// Whether the person has reached <paramref name="kind"/> by now.
    ///
    /// Ten hours leaves out interrupted sprints: Basalt was not running for
    /// most of those, so they are not focus the person did. Both the first
    /// Sealed sprint and the streak are checked against the live values, so a
    /// streak that breaks again does not take an earned milestone away;
    /// <see cref="Record"/> keeps what was reached.
    /// </summary>
    public static bool Reached(MilestoneKind kind, AppSettings s) => kind switch
    {
        MilestoneKind.FirstSealed => s.Sessions.Any(x => x.Completed && x.Shield == ShieldLevel.Sealed),
        MilestoneKind.TenHours => s.Sessions.Where(x => !x.Interrupted).Sum(x => x.ActualMinutes) >= TenHoursMinutes,
        MilestoneKind.SevenDayStreak => s.CurrentStreak >= StreakDays,
        MilestoneKind.MomentumHundred => s.MomentumScore >= MomentumTarget,
        _ => false,
    };

    /// <summary>The short name of a milestone, for its card and its History row.</summary>
    public static string Title(MilestoneKind kind) => kind switch
    {
        MilestoneKind.FirstSealed => "First Sealed sprint",
        MilestoneKind.TenHours => "Ten hours focused",
        MilestoneKind.SevenDayStreak => "Seven days in a row",
        MilestoneKind.MomentumHundred => "Momentum at 100",
        _ => "",
    };

    /// <summary>One plain sentence about a milestone, with no confetti and no praise to match.</summary>
    public static string Sentence(MilestoneKind kind) => kind switch
    {
        MilestoneKind.FirstSealed => "You finished a sprint on Sealed, the strictest shield.",
        MilestoneKind.TenHours => "Ten hours of sprints that really ran.",
        MilestoneKind.SevenDayStreak => "Seven days in a row with a finished focus day.",
        MilestoneKind.MomentumHundred => "Finished sprints have built your momentum to 100.",
        _ => "",
    };

    /// <summary>
    /// Run once at launch, before anything can be earned. It lists what the
    /// person had already reached (an upgrade brings a long history) without
    /// a card for each one, so the first card is for something done next.
    /// Running it at launch rather than at the first sprint end is what keeps
    /// a new person's first Sealed sprint from being swallowed by this.
    /// </summary>
    public static void Seed(AppSettings s, DateTime nowUtc)
    {
        if (s.MilestonesSeeded) return;
        s.MilestonesSeeded = true;

        foreach (var kind in All.Where(k => Reached(k, s)))
        {
            s.EarnedMilestones.Add(new MilestoneRecord
            {
                Id = kind.ToString(),
                EarnedUtc = nowUtc,
                Shown = true,
            });
        }
    }

    /// <summary>
    /// Records every milestone reached for the first time, and returns those
    /// that are new and still owe a card. The caller shows them and sets
    /// <see cref="MilestoneRecord.Shown"/>.
    /// </summary>
    public static IReadOnlyList<MilestoneRecord> Record(AppSettings s, DateTime nowUtc)
    {
        var fresh = new List<MilestoneRecord>();
        foreach (var kind in All.Where(k => Reached(k, s)))
        {
            var id = kind.ToString();
            if (s.EarnedMilestones.Any(r => r.Id == id)) continue;

            var record = new MilestoneRecord { Id = id, EarnedUtc = nowUtc, Shown = false };
            s.EarnedMilestones.Add(record);
            fresh.Add(record);
        }
        return fresh;
    }
}
