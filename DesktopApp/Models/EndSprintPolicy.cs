namespace FlowShield.Models;

/// <summary>How ending a running sprint works at a given moment.</summary>
public enum EndFlow
{
    /// <summary>Inside the grace period: ends with no penalty and nothing recorded.</summary>
    Cancel,

    /// <summary>Soft: ends straight away, recorded as ended early.</summary>
    Immediate,

    /// <summary>Firm: a confirmation whose "End anyway" unlocks after a short countdown.</summary>
    Confirm,

    /// <summary>Sealed: a longer countdown, then the phrase has to be typed.</summary>
    Sealed,
}

/// <summary>
/// The rules for getting out of a sprint (launch checklist F2).
///
/// If ending a sprint is effortless the shield is pointless, but a lock with no
/// way out is how people end up locked out of something they need. So the way
/// out gets harder as the shield gets stronger, and there's always one.
/// Kept free of UI so the rules can be tested on their own.
/// </summary>
public static class EndSprintPolicy
{
    /// <summary>The literal phrase a Sealed sprint needs before it can be ended.</summary>
    public const string SealedPhrase = "end my sprint";

    /// <summary>
    /// Shrinks every wait to a few seconds so the UI test suite doesn't sit
    /// through them. Set only by the --short-timers launch flag; it never skips
    /// a step, only shortens the waits.
    /// </summary>
    public static bool UseShortTimers { get; set; }

    /// <summary>Time after starting in which a sprint can be cancelled without penalty.</summary>
    // Short-timers is only set by --short-timers, which only the automation
    // suite passes. 3 s left no margin for a real UI-test process (app launch,
    // UIA probing, click dispatch) between starting a sprint and cancelling it
    // inside the grace period — cancel_sprint() kept losing the race under a
    // loaded machine even though nothing was actually broken (#222).
    //
    // 6 s was not enough either: #241's three cancel tests failed the same way
    // on an idle machine. A single UI-Automation element lookup on Today costs
    // one to two seconds, and those tests spend four to six of them between the
    // sprint starting and the click landing — the worst path measured about
    // eight. 15 s is roughly double that, which is the margin this needs to
    // stop being a coin toss. The real two minutes is untouched.
    public static TimeSpan GracePeriod => UseShortTimers ? TimeSpan.FromSeconds(15) : TimeSpan.FromMinutes(2);

    /// <summary>
    /// How long Firm's "End anyway" stays disabled.
    ///
    /// 6 s rather than 2 s under short timers, for the reason #222 widened the
    /// grace period: the UI suite cannot observe a window shorter than its own
    /// round trips. #242 reported the button as "enabled immediately"; the app
    /// log showed it unlocking 2.507 s after the panel opened — the countdown
    /// was exactly right, and the test simply could not read IsEnabled inside
    /// a 2 s window. The real 5 s is untouched.
    /// </summary>
    public static TimeSpan FirmConfirmDelay => UseShortTimers ? TimeSpan.FromSeconds(6) : TimeSpan.FromSeconds(5);

    /// <summary>
    /// How long Sealed makes you wait before the phrase can confirm. 8 s under
    /// short timers for the same reason as <see cref="FirmConfirmDelay"/>, with
    /// room for the phrase to be typed inside the window. The real 30 s stands.
    /// </summary>
    public static TimeSpan SealedCountdown => UseShortTimers ? TimeSpan.FromSeconds(8) : TimeSpan.FromSeconds(30);

    public static EndFlow FlowFor(ShieldLevel shield, TimeSpan elapsed) =>
        elapsed < GracePeriod
            ? EndFlow.Cancel
            : shield switch
            {
                ShieldLevel.Soft => EndFlow.Immediate,
                ShieldLevel.Firm => EndFlow.Confirm,
                _ => EndFlow.Sealed,
            };

    /// <summary>The wait before "End anyway" can be pressed, for the flows that have one.</summary>
    public static TimeSpan DelayFor(EndFlow flow) => flow switch
    {
        EndFlow.Confirm => FirmConfirmDelay,
        EndFlow.Sealed => SealedCountdown,
        _ => TimeSpan.Zero,
    };

    /// <summary>
    /// Momentum after ending a sprint early. Abandoning decays it rather than
    /// resetting it; giving up on a Sealed sprint, which you chose because you
    /// wanted it to hold, costs more.
    /// </summary>
    public static double MomentumAfterEndingEarly(double score, ShieldLevel shield) =>
        shield == ShieldLevel.Sealed
            ? Math.Round(Math.Max(0, score * 0.7 - 5), 1)
            : Math.Round(Math.Max(0, score * 0.85 - 2), 1);

    /// <summary>Forgiving about case and spacing, strict about the words.</summary>
    public static bool PhraseMatches(string? typed) =>
        string.Join(' ', (typed ?? "").Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries))
            .Equals(SealedPhrase, StringComparison.OrdinalIgnoreCase);
}
