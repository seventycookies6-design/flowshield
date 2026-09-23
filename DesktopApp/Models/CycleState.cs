namespace FlowShield.Models;

/// <summary>What FlowShield is doing right now, as far as a cycle is concerned.</summary>
public enum CyclePhase
{
    /// <summary>Nothing is counting down.</summary>
    Idle,

    /// <summary>A sprint is running and the shield is up.</summary>
    Sprint,

    /// <summary>A break is running and the shield is down.</summary>
    Break,
}

/// <summary>
/// Breaks and study cycles (F5, roadmap 3.4), as pure rules.
///
/// Everything the feature decides lives here rather than in
/// <c>TodayViewModel</c>: which break comes next, whether one is offered at
/// all, and whether a cycle has another sprint to run. The view model only
/// starts and stops timers.
///
/// Three rules are worth stating out loud, because they are what keeps a break
/// from becoming a way to cheat or a way to lose progress:
///
///   * a break is offered only after a sprint that <em>finished</em>. Ending
///     early is already covered by F2, and a reward for stopping would undo it;
///   * a break never touches momentum, the streak or the daily goal. Nothing in
///     this file reads or writes any of them;
///   * skipping a break costs nothing. In a cycle, skipping simply moves on to
///     the next sprint.
/// </summary>
public readonly record struct CycleState(
    CyclePhase Phase,
    int SprintsPlanned,
    int SprintsDone)
{
    /// <summary>How many completed sprints in a row earn the longer break.</summary>
    public const int LongBreakEvery = 4;

    public const int DefaultShortBreakMinutes = 5;
    public const int DefaultLongBreakMinutes = 15;

    /// <summary>The range a break length may be set to in Settings.</summary>
    public const int MinBreakMinutes = 1;
    public const int MaxBreakMinutes = 60;

    /// <summary>Cycle lengths offered on Today. Zero means no cycle.</summary>
    public static readonly int[] CycleChoices = { 0, 2, 3, 4 };

    /// <summary>
    /// Set by --short-timers so the UI suite can run a whole cycle. It only
    /// shortens the break itself; every rule below is unchanged.
    /// </summary>
    public static bool UseShortTimers { get; set; }

    /// <summary>How long a break of <paramref name="minutes"/> actually runs.</summary>
    public static TimeSpan BreakLength(int minutes) =>
        UseShortTimers ? TimeSpan.FromSeconds(3) : TimeSpan.FromMinutes(Math.Max(minutes, 0));

    /// <summary>
    /// Set by --short-sprints, which makes a sprint run five seconds so tier 3
    /// can watch a whole cycle go round. Test only, and off unless that flag is
    /// passed: it is the one thing here that would make the product dishonest
    /// if it ever shipped on, so it changes nothing about lengths, validation or
    /// what is saved — only how long the clock runs.
    /// </summary>
    public static bool UseShortSprints { get; set; }

    /// <summary>How long a sprint of <paramref name="minutes"/> actually runs.</summary>
    public static TimeSpan SprintLength(int minutes) =>
        UseShortSprints ? TimeSpan.FromSeconds(5) : TimeSpan.FromMinutes(Math.Max(minutes, 0));

    /// <summary>
    /// Whether a finished sprint may be recorded and scored.
    ///
    /// False under --short-sprints, and this is the invariant that makes that
    /// flag safe to ship: five seconds is not ninety minutes, so a shortened
    /// sprint leaves no record and moves no score — no momentum, no streak day,
    /// no progress towards the daily goal — exactly as cancelling inside the
    /// grace period does. Like --expire-trial, the flag can only ever take
    /// credit away, never hand any out, so a customer who finds it on the
    /// command line gains nothing by passing it.
    /// </summary>
    public static bool SprintCountsAsProgress => !UseShortSprints;

    public static CycleState Nothing => new(CyclePhase.Idle, 0, 0);

    /// <summary>A run of more than one sprint, chosen before the first one started.</summary>
    public bool InCycle => SprintsPlanned > 1;

    /// <summary>The sprint running, or the one coming next: 1-based, capped at the plan.</summary>
    public int SprintNumber => Math.Min(SprintsDone + 1, Math.Max(SprintsPlanned, 1));

    /// <summary>"Sprint 2 of 3" on the timer, or empty when this is a single sprint.</summary>
    public string CycleLabel => InCycle ? $"Sprint {SprintNumber} of {SprintsPlanned}" : "";

    /// <summary>The cycle has run every sprint it promised.</summary>
    public bool CycleFinished => InCycle && SprintsDone >= SprintsPlanned;

    /// <summary>
    /// After a break ends — or is skipped — a cycle with sprints left starts the
    /// next one by itself. That automation is the whole point of a cycle; a
    /// single sprint goes back to idle instead.
    /// </summary>
    public bool StartsNextSprint => InCycle && SprintsDone < SprintsPlanned;

    /// <summary>A break follows a sprint that finished, and only one that finished.</summary>
    public static bool OffersBreak(bool completed) => completed;

    /// <summary>
    /// The break earned by <paramref name="completedInARow"/> completed sprints:
    /// the long one on every fourth, the short one otherwise.
    /// </summary>
    public static int BreakMinutes(int completedInARow, int shortMinutes, int longMinutes) =>
        completedInARow > 0 && completedInARow % LongBreakEvery == 0 ? longMinutes : shortMinutes;

    /// <summary>A break length typed into Settings, clamped to something sane.</summary>
    public static bool IsValidBreakMinutes(int minutes) =>
        minutes >= MinBreakMinutes && minutes <= MaxBreakMinutes;

    // ------------------------------------------------------------ transitions

    /// <summary>
    /// A sprint starts. <paramref name="sprintsPlanned"/> is the cycle chooser's
    /// value; it is only honoured when no cycle is already under way, so the
    /// second sprint of a 3 × 45 does not restart the count.
    /// </summary>
    public CycleState OnSprintStarted(int sprintsPlanned) =>
        InCycle && !CycleFinished
            ? this with { Phase = CyclePhase.Sprint }
            : new CycleState(CyclePhase.Sprint, Math.Max(sprintsPlanned, 0), 0);

    /// <summary>A sprint finished: it counts towards the cycle.</summary>
    public CycleState OnSprintCompleted() =>
        this with { Phase = CyclePhase.Idle, SprintsDone = SprintsDone + 1 };

    /// <summary>
    /// A sprint was ended early, cancelled or interrupted. The cycle stops here
    /// — F2 already decided what that costs, and it costs it once, for this
    /// sprint only.
    /// </summary>
    public CycleState OnSprintAbandoned() => Nothing;

    public CycleState OnBreakStarted() => this with { Phase = CyclePhase.Break };

    /// <summary>A break ended, was skipped, or was cut short. Free, either way.</summary>
    public CycleState OnBreakEnded() => this with { Phase = CyclePhase.Idle };

    /// <summary>The cycle is over; the next Start begins a fresh one.</summary>
    public CycleState OnCycleFinished() => this with { Phase = CyclePhase.Idle, SprintsPlanned = 0, SprintsDone = 0 };
}

/// <summary>What to do with a saved break when FlowShield starts again.</summary>
public enum BreakResume
{
    /// <summary>Time is left: carry on counting it down.</summary>
    Resume,

    /// <summary>It ran out while FlowShield was closed; drop it without a word.</summary>
    EndQuietly,
}

/// <summary>
/// The break that is running right now, saved the moment it starts (F5).
///
/// Persisted beside <see cref="RunningSprint"/> and for the same reason: a
/// break that vanished on a crash would silently become "no break", and in a
/// cycle it would lose the count of sprints run so far.
///
/// <see cref="EndsUtc"/> is stored rather than computed from
/// <see cref="Minutes"/> so a break started under --short-timers stays three
/// seconds long when it is read back.
/// </summary>
public class RunningBreak
{
    public DateTime StartedUtc { get; set; }
    public DateTime EndsUtc { get; set; }

    /// <summary>What the break was offered as, for display. 5 or 15 by default.</summary>
    public int Minutes { get; set; }

    /// <summary>The cycle this break sits inside, so it survives a restart too.</summary>
    public int SprintsPlanned { get; set; }
    public int SprintsDone { get; set; }

    /// <summary>
    /// The break length of the template this cycle was started from (F6), or
    /// null for a run begun by hand, which uses the global break settings.
    /// Carried by the break as <see cref="RunningSprint.TemplateBreakMinutes"/>
    /// is by the sprint, so a restart during a break keeps the template's
    /// later breaks too.
    /// </summary>
    public int? TemplateBreakMinutes { get; set; }

    public BreakResume Decide(DateTime nowUtc) =>
        EndsUtc <= nowUtc ? BreakResume.EndQuietly : BreakResume.Resume;

    /// <summary>The cycle state this break was saved with.</summary>
    public CycleState ToCycle() => new(CyclePhase.Break, SprintsPlanned, SprintsDone);
}
