namespace FlowShield.Models;

/// <summary>What a daily goal is measured in. <see cref="None"/> means no goal.</summary>
public enum DailyGoalKind
{
    None = 0,
    Minutes = 1,
    Sprints = 2,
}

/// <summary>
/// An optional "2 sprints today" or "90 minutes today" target, and the streak
/// rules that follow from it (F15).
///
/// The streak already existed, but it counted any day with one completed sprint.
/// With a goal set it counts a day only when the goal is met, which makes the
/// number mean something: a five-minute sprint is no longer a day of focus.
///
/// Everything here is a pure function of settings plus a date, so the rules can
/// be tested without a window, a clock or a running sprint.
/// </summary>
public static class DailyGoal
{
    /// <summary>
    /// Days off allowed inside any seven-day window. Rolling rather than
    /// calendar-week: a fixed week lets someone skip Sunday and Monday back to
    /// back, which is two days off in a row from a one-a-week allowance.
    /// </summary>
    public const int SkipsPerWeek = 1;

    /// <summary>The window the allowance is measured over, ending on the day in question.</summary>
    public const int SkipWindowDays = 7;

    public const int MinMinutes = 5;
    public const int MaxMinutes = 720;
    public const int MinSprints = 1;
    public const int MaxSprints = 20;

    /// <summary>Whether a goal is set at all.</summary>
    public static bool IsSet(AppSettings s) =>
        s.DailyGoalKind != DailyGoalKind.None && s.DailyGoalTarget > 0;

    /// <summary>
    /// Progress towards the goal on <paramref name="day"/>, as (done, target).
    /// Returns (0, 0) when no goal is set.
    /// </summary>
    public static (int Done, int Target) ProgressOn(AppSettings s, DateTime day)
    {
        if (!IsSet(s)) return (0, 0);

        var date = day.Date;
        var todays = s.Sessions.Where(x => x.StartedUtc.ToLocalTime().Date == date).ToList();

        var done = s.DailyGoalKind switch
        {
            // Minutes count actual time focused, including a sprint that was
            // ended early: those minutes happened.
            DailyGoalKind.Minutes => (int)Math.Round(todays.Sum(x => x.ActualMinutes)),
            // Sprints count completed ones only, matching the Today tile.
            DailyGoalKind.Sprints => todays.Count(x => x.Completed),
            _ => 0,
        };

        return (done, s.DailyGoalTarget);
    }

    /// <summary>Whether the goal was met on <paramref name="day"/>.</summary>
    public static bool MetOn(AppSettings s, DateTime day)
    {
        if (!IsSet(s)) return false;
        var (done, target) = ProgressOn(s, day);
        return done >= target;
    }

    /// <summary>
    /// The old rule, kept exactly as it was for people with no goal: a day
    /// counts if it has at least one completed sprint.
    /// </summary>
    public static bool HadCompletedSprintOn(AppSettings s, DateTime day)
    {
        var date = day.Date;
        return s.Sessions.Any(x => x.Completed && x.StartedUtc.ToLocalTime().Date == date);
    }

    /// <summary>Whether <paramref name="day"/> was marked as a planned day off.</summary>
    public static bool IsSkipped(AppSettings s, DateTime day) =>
        s.SkipDatesLocal.Any(d => d.Date == day.Date);

    /// <summary>
    /// Skips used in the seven-day window ending on <paramref name="day"/>
    /// inclusive. Used both to enforce the allowance and to show what is left.
    /// </summary>
    public static int SkipsUsedInWindow(AppSettings s, DateTime day)
    {
        var end = day.Date;
        var start = end.AddDays(-(SkipWindowDays - 1));
        return s.SkipDatesLocal.Count(d => d.Date >= start && d.Date <= end);
    }

    /// <summary>Whether <paramref name="day"/> can still be marked as a day off.</summary>
    public static bool CanSkip(AppSettings s, DateTime day) =>
        IsSet(s)
        && !IsSkipped(s, day)
        && SkipsUsedInWindow(s, day) < SkipsPerWeek;

    /// <summary>Marks a planned day off. Returns false if the allowance is spent.</summary>
    public static bool Skip(AppSettings s, DateTime day)
    {
        if (!CanSkip(s, day)) return false;
        s.SkipDatesLocal.Add(day.Date);
        return true;
    }

    /// <summary>Undoes a skip, so a day off can be taken back the same day.</summary>
    public static bool Unskip(AppSettings s, DateTime day)
    {
        var removed = s.SkipDatesLocal.RemoveAll(d => d.Date == day.Date);
        return removed > 0;
    }

    /// <summary>How a single past day is judged when settling the streak.</summary>
    public enum DayVerdict
    {
        /// <summary>Counted: the goal was met, or with no goal, a sprint was completed.</summary>
        Counted,

        /// <summary>A planned day off: holds the streak without adding to it.</summary>
        Skipped,

        /// <summary>Nothing happened, or the goal was missed. Breaks the streak.</summary>
        Missed,
    }

    /// <summary>
    /// Judges one day. A skip is checked first so that marking a day off is
    /// final — otherwise a stray two-minute sprint on a rest day would turn it
    /// into a counted day and silently spend the skip for nothing.
    /// </summary>
    public static DayVerdict Judge(AppSettings s, DateTime day)
    {
        if (IsSkipped(s, day)) return DayVerdict.Skipped;

        var counted = IsSet(s) ? MetOn(s, day) : HadCompletedSprintOn(s, day);
        return counted ? DayVerdict.Counted : DayVerdict.Missed;
    }

    /// <summary>
    /// Brings <see cref="AppSettings.CurrentStreak"/> up to date as of
    /// <paramref name="today"/>, walking every day since the last settlement.
    ///
    /// This exists because the streak used to be recalculated only when a sprint
    /// completed, so a missed day was never noticed until the next sprint — and
    /// with a goal, "yesterday fell short" has to break the streak even though
    /// nothing happened to trigger it. Today itself is judged but never counted
    /// as missed: the day isn't over.
    ///
    /// Idempotent, so it is safe on launch, at midnight and after every sprint.
    ///
    /// Returns true if anything changed, so the caller can save the settings
    /// file on the rare pass that matters instead of on every refresh.
    /// </summary>
    public static bool Settle(AppSettings s, DateTime today)
    {
        var date = today.Date;
        var streakBefore = s.CurrentStreak;
        var settledBefore = s.StreakSettledDayLocal;

        // First run, or a settings file from before F15: take the streak as
        // given rather than recomputing history that may not be in Sessions.
        if (s.StreakSettledDayLocal is null)
        {
            s.StreakSettledDayLocal = date;
            if (Judge(s, date) == DayVerdict.Counted) s.CurrentStreak = Math.Max(s.CurrentStreak, 1);
            return s.CurrentStreak != streakBefore || settledBefore != s.StreakSettledDayLocal;
        }

        var settled = s.StreakSettledDayLocal.Value.Date;

        // Clock moved backwards (travel, a wrong clock corrected). Re-judge
        // today rather than walking a negative range.
        if (date <= settled)
        {
            if (date == settled && Judge(s, date) == DayVerdict.Counted)
                s.CurrentStreak = Math.Max(s.CurrentStreak, 1);
            return s.CurrentStreak != streakBefore;
        }

        for (var day = settled.AddDays(1); day <= date; day = day.AddDays(1))
        {
            var verdict = Judge(s, day);

            if (day == date)
            {
                // Today is still open: it can add to the streak, never break it.
                if (verdict == DayVerdict.Counted) s.CurrentStreak++;
                break;
            }

            s.CurrentStreak = verdict switch
            {
                DayVerdict.Counted => s.CurrentStreak + 1,
                DayVerdict.Skipped => s.CurrentStreak,
                _ => 0,
            };
        }

        s.StreakSettledDayLocal = date;
        return s.CurrentStreak != streakBefore || settledBefore?.Date != date;
    }

    /// <summary>
    /// Records that today's goal has just been met, if it has. Called after a
    /// sprint so the streak ticks the moment the goal is reached rather than on
    /// the day's first sprint.
    ///
    /// Returns true the one time the day flips to counted, so the caller can
    /// congratulate without repeating it on every later sprint.
    /// </summary>
    public static bool NoteProgress(AppSettings s, DateTime today)
    {
        var date = today.Date;
        Settle(s, date);

        if (s.GoalMetDayLocal?.Date == date) return false;
        if (Judge(s, date) != DayVerdict.Counted) return false;

        s.GoalMetDayLocal = date;
        return true;
    }

    /// <summary>A short line for the Today bar: "42 / 90 minutes" or "1 / 3 sprints".</summary>
    public static string ProgressText(AppSettings s, DateTime day)
    {
        if (!IsSet(s)) return "";
        var (done, target) = ProgressOn(s, day);
        var unit = s.DailyGoalKind == DailyGoalKind.Minutes
            ? "minutes"
            : target == 1 ? "sprint" : "sprints";
        return $"{Math.Min(done, target)} / {target} {unit}";
    }

    /// <summary>Fraction of the goal done, clamped to 0–1 for the progress bar.</summary>
    public static double Fraction(AppSettings s, DateTime day)
    {
        if (!IsSet(s)) return 0;
        var (done, target) = ProgressOn(s, day);
        if (target <= 0) return 0;
        return Math.Clamp(done / (double)target, 0, 1);
    }

    /// <summary>Keeps a target inside the allowed range for its kind.</summary>
    public static int ClampTarget(DailyGoalKind kind, int target) => kind switch
    {
        DailyGoalKind.Minutes => Math.Clamp(target, MinMinutes, MaxMinutes),
        DailyGoalKind.Sprints => Math.Clamp(target, MinSprints, MaxSprints),
        _ => 0,
    };
}
